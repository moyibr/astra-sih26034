"""What the vision pipeline hands to the rule engine.

This is the seam that keeps ASTRA legally defensible: everything upstream of
``ExtractedFields`` is probabilistic (OCR, layout, an optional LLM tidying up
messy text), and everything downstream is deterministic. A rule never sees an
image, so a rule's verdict can always be replayed and explained from data.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import PackageShape, PackageType, PrintMethod, ScanSource, Script
from .measurement import Measurement, Scale

Point = tuple[float, float]


class TextSpan(BaseModel):
    """One OCR'd token, located on the original (un-rectified) image."""

    text: str
    polygon: list[Point] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0, le=1)
    script: Script = Script.LATIN

    ink_height_px: float | None = None
    """Vertical extent of actual ink, not of the detector's bounding box.

    Rule 9 speaks of the height of a numeral or letter, so we measure the glyph
    itself. A bounding box includes leading and descenders and would flatter a
    non-compliant label by 20-40%.
    """
    ink_width_px: float | None = None

    height: Measurement | None = None
    width: Measurement | None = None


class FieldEvidence(BaseModel):
    """A declaration we believe we found, with everything needed to prove it."""

    present: bool = False
    raw_text: str | None = None
    spans: list[TextSpan] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)

    @property
    def numeral_spans(self) -> list[TextSpan]:
        return [s for s in self.spans if any(c.isdigit() for c in s.text)]


class NetQuantity(FieldEvidence):
    value: float | None = None
    unit: str | None = None
    """Unit exactly as printed, e.g. 'g', 'gms.', 'Gm' -- normalisation happens
    in the rule, so the rule can cite what was actually on the pack."""
    canonical_unit: str | None = None
    """SI symbol the printed unit maps to: g, kg, ml, l, m, cm."""
    value_in_base: float | None = None
    """Grams for mass, millilitres for volume -- used by the Rule 26 small-pack
    exemption and by Second Schedule pack-size checks."""
    declared_by_count: bool = False


class Price(FieldEvidence):
    amount: float | None = None
    currency: str = "INR"
    has_inclusive_of_taxes_phrase: bool = False
    is_unit_sale_price: bool = False
    candidate_amounts: list[float] = Field(default_factory=list)
    """Every distinct price-like figure found near an MRP marker.

    More than one is how a dual-MRP scam shows up: the same pack carrying a
    different maximum retail price for a different channel."""


class PackDate(FieldEvidence):
    month: int | None = None
    year: int | None = None
    day: int | None = None
    is_ambiguous: bool = False
    """True only when the format is genuinely undecidable -- both components
    <= 12 and no month name present. DD-MM-YYYY alone is common and lawful in
    India, so flagging every hyphenated date would drown the officer in noise."""


class ConsumerCare(FieldEvidence):
    contact_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class Origin(FieldEvidence):
    country: str | None = None
    is_imported: bool | None = None


class PackageGeometry(BaseModel):
    """Everything Rule 9(4) needs to size the principal display panel."""

    shape: PackageShape = PackageShape.OTHER
    print_method: PrintMethod = PrintMethod.PRINTED

    height_mm: float | None = None
    width_mm: float | None = None
    diameter_mm: float | None = None
    total_surface_area_mm2: float | None = None

    pdp_area_cm2: float | None = None
    pdp_area_confident: bool = False

    def compute_pdp_area_cm2(self) -> float | None:
        """Rule 9(4): area of the principal display panel.

        (a) rectangular  -> height x width of one side
        (b) cylindrical  -> 40% of (height x circumference)
        (c) other shapes -> 40% of total surface area

        Tops, bottoms, flanges of cans and the shoulders and necks of bottles
        and jars are excluded; the caller is responsible for not measuring them.
        """
        import math

        mm2: float | None = None
        if self.shape is PackageShape.RECTANGULAR and self.height_mm and self.width_mm:
            mm2 = self.height_mm * self.width_mm
        elif self.shape is PackageShape.CYLINDRICAL and self.height_mm and self.diameter_mm:
            mm2 = 0.40 * self.height_mm * math.pi * self.diameter_mm
        elif self.total_surface_area_mm2:
            mm2 = 0.40 * self.total_surface_area_mm2

        return mm2 / 100.0 if mm2 else None


class ExtractedFields(BaseModel):
    """The complete, deterministic view of one package."""

    # Provenance -----------------------------------------------------------
    scan_id: str
    image_sha256: str
    scale: Scale | None = None
    ocr_scripts_seen: list[Script] = Field(default_factory=list)
    full_text: str = ""

    # Context the rules branch on ------------------------------------------
    scan_source: ScanSource = ScanSource.FIELD_INSPECTION
    package_type: PackageType = PackageType.RETAIL
    commodity_category: str | None = None
    is_perishable: bool = False
    commodity_is_scheduled: bool = False
    """True when the commodity appears in the Second Schedule, which restricts
    it to prescribed pack sizes."""
    scheduled_sizes_base: list[float] = Field(default_factory=list)
    geometry: PackageGeometry = Field(default_factory=PackageGeometry)

    # Rule 6(1) declarations ------------------------------------------------
    manufacturer: FieldEvidence = Field(default_factory=FieldEvidence)
    common_name: FieldEvidence = Field(default_factory=FieldEvidence)
    net_quantity: NetQuantity = Field(default_factory=NetQuantity)
    mrp: Price = Field(default_factory=Price)
    unit_sale_price: Price = Field(default_factory=Price)
    manufacture_date: PackDate = Field(default_factory=PackDate)
    best_before: PackDate = Field(default_factory=PackDate)
    consumer_care: ConsumerCare = Field(default_factory=ConsumerCare)
    origin: Origin = Field(default_factory=Origin)

    # Rule 9 legibility -----------------------------------------------------
    min_letter_height: Measurement | None = None
    declaration_contrast_ratio: float | None = None
    """WCAG-style luminance contrast of declaration ink against its local
    background. Rule 9 requires a colour that 'contrasts conspicuously'; this
    turns a subjective phrase into a number an officer can defend."""

    # Platform-level context (e-commerce audits) ----------------------------
    platform_has_country_filter: bool | None = None
    platform_country_filter_sortable: bool | None = None
