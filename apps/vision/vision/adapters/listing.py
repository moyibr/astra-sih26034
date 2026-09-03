"""Assessing an e-commerce listing rather than a photograph.

Rule 6(10) requires the mandatory declarations to appear on the listing itself,
not merely on the pack inside the carton, and since 1 July 2026 Rule 6(10A)
requires a platform selling imported goods to expose a country-of-origin filter
that is both searchable and sortable. Neither is a question about pixels.

So this path reuses the field extractor over the listing's own text and skips
the vision pipeline entirely. That has a consequence worth stating plainly: with
no image there is no scale, so every millimetre rule comes back
``INDETERMINATE``. That is correct. A listing page cannot tell you how tall the
print on the physical pack is, and a system that guessed would be inventing
evidence.

Ingestion is by catalogue CSV. A crawler is easy to demonstrate and fragile to
depend on -- platform markup changes, terms of service differ, and anti-bot
measures exist -- so the dependable path is the one a platform or a regulator
can actually be asked to provide, and the crawler stays a demonstration.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field

from astra_schema import ExtractedFields, FieldEvidence, PackageType, ScanSource

from ..pipeline import extract

log = logging.getLogger(__name__)

#: Columns a catalogue export is expected to carry. Only `listing_id` is
#: required; everything else contributes what it can.
KNOWN_COLUMNS = {
    "listing_id",
    "platform",
    "url",
    "brand",
    "category",
    "title",
    "description",
    "declarations",
    "net_quantity",
    "mrp",
    "manufacturer",
    "consumer_care",
    "country_of_origin",
    "manufacture_date",
    "best_before",
    "is_perishable",
    "has_country_filter",
    "country_filter_sortable",
}

_TRUTHY = {"1", "true", "yes", "y", "t"}
_FALSY = {"0", "false", "no", "n", "f"}


def _tri_state(raw: str | None) -> bool | None:
    """Parse a boolean column, keeping "not stated" distinct from "no".

    The difference matters: a platform we never audited must not be recorded as
    a platform that failed the audit.
    """
    if raw is None:
        return None
    token = raw.strip().lower()
    if token in _TRUTHY:
        return True
    if token in _FALSY:
        return False
    return None


@dataclass
class Listing:
    """One row of a catalogue export."""

    listing_id: str
    platform: str | None = None
    url: str | None = None
    brand: str | None = None
    category: str | None = None
    is_perishable: bool = False
    has_country_filter: bool | None = None
    country_filter_sortable: bool | None = None
    text: str = ""
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        """Content hash of the listing text.

        Serves the same purpose as the image digest on a field inspection: it
        pins exactly what was assessed, so a seller who later edits the listing
        cannot quietly change what the finding was made against.
        """
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def parse_csv(payload: bytes | str) -> list[Listing]:
    """Read a catalogue export into listings.

    Unknown columns are kept and appended to the assessed text rather than
    dropped. Platforms name their fields differently, and a declaration we did
    not anticipate is still a declaration.
    """
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("the CSV has no header row")

    listings: list[Listing] = []
    for index, row in enumerate(reader, start=2):  # row 1 is the header
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        listing_id = clean.get("listing_id") or clean.get("id") or f"row-{index}"

        # Everything textual becomes the assessed body, so the same extractor
        # that reads a label can read a listing.
        parts: list[str] = []
        for key, value in clean.items():
            if not value or key in {"listing_id", "id", "url", "platform"}:
                continue
            if key in {"has_country_filter", "country_filter_sortable", "is_perishable"}:
                continue
            # Label the fragment so the extractor's patterns have something to
            # anchor on, exactly as a printed label would.
            parts.append(value if key in {"title", "description", "declarations"} else f"{key.replace('_', ' ')}: {value}")

        listings.append(
            Listing(
                listing_id=listing_id,
                platform=clean.get("platform") or None,
                url=clean.get("url") or None,
                brand=clean.get("brand") or None,
                category=clean.get("category") or None,
                is_perishable=_tri_state(clean.get("is_perishable")) or False,
                has_country_filter=_tri_state(clean.get("has_country_filter")),
                country_filter_sortable=_tri_state(clean.get("country_filter_sortable")),
                text="\n".join(parts),
                raw=clean,
            )
        )

    log.info("parsed %d listings", len(listings))
    return listings


def to_fields(listing: Listing) -> ExtractedFields:
    """Build the engine's input from a listing, with no image involved."""
    extracted = extract.extract_all(listing.text, [])

    # On a label the common name is found by falling back to the largest print
    # on the pack. A listing has no typography to fall back on, but it has
    # something better: the title is the product name, stated by the seller.
    title = listing.raw.get("title") or listing.raw.get("name")
    if title and not extracted["common_name"].present:
        extracted["common_name"] = FieldEvidence(
            present=True,
            confidence=0.8,
            raw_text=title,
        )

    return ExtractedFields(
        scan_id=hashlib.sha256(
            f"{listing.platform}:{listing.listing_id}".encode()
        ).hexdigest()[:32],
        image_sha256=listing.digest,
        # No photograph, therefore no scale, therefore no millimetre findings.
        scale=None,
        full_text=listing.text,
        ocr_scripts_seen=[],
        scan_source=ScanSource.ECOMMERCE_LISTING,
        package_type=PackageType.RETAIL,
        commodity_category=listing.category,
        is_perishable=listing.is_perishable,
        platform_has_country_filter=listing.has_country_filter,
        platform_country_filter_sortable=listing.country_filter_sortable,
        **extracted,
    )


def sample_csv() -> str:
    """A small catalogue exercising the cases that matter, for the demo."""
    return (
        "listing_id,platform,url,brand,category,title,declarations,"
        "country_of_origin,has_country_filter,country_filter_sortable\n"
        "SKU-1001,marketplace-a,https://marketplace-a.example/p/1001,Bharat Foods,"
        "packaged_food,Potato Chips Salted,"
        '"Net Quantity: 100 g. MRP Rs 40.00 inclusive of all taxes. Manufactured by: '
        'Bharat Foods Pvt Ltd, Plot 14, MIDC, Pune 411018. Customer Care Manager, '
        'Plot 14, MIDC, Pune 411018. Tel 1800-123-4567. Mfd: Aug 2026",'
        "India,true,true\n"
        "SKU-1002,marketplace-a,https://marketplace-a.example/p/1002,Nimbus Cosmetics,"
        "cosmetics,Face Cream,"
        '"Net Weight: 50 gms. MRP Rs 299. For complaints email care@nimbus.example",'
        "Vietnam,true,false\n"
        "SKU-1003,quick-commerce-c,https://quick-commerce-c.example/p/1003,Ganga Snacks,"
        "packaged_food,Namkeen Mix,"
        '"100 gms. Mfd: 05-08-2027",'
        "Vietnam,false,false\n"
    )
