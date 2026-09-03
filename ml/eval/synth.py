"""Synthetic labels with exact millimetre ground truth.

Measuring font height from a photograph is the hardest claim ASTRA makes, and
the honest way to test it is against labels whose true dimensions we set
ourselves. A rendered label is drawn at a known pixels-per-millimetre, with an
ID-1 calibration card of exactly the right size in frame and declarations set to
exactly the cap heights we asked for -- so the ground truth is arithmetic rather
than a calliper reading, and the whole measurement chain can be scored to a
tenth of a millimetre before a single real photograph is collected.

This does not replace the golden set of real photographs. Real labels bring
glare, curvature, foil, motion blur and creative typography, and the accuracy
report must be built on them. Synthetic labels answer a narrower and prior
question: given a clean image, is the geometry itself correct?
"""

from __future__ import annotations

import io
import pathlib
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

# Candidate fonts, in preference order. Bundled DejaVu first so the generator
# behaves identically on a teammate's machine and in CI.
_FONT_CANDIDATES = [
    pathlib.Path(ImageFont.__file__).parent / "fonts" / "DejaVuSans.ttf",
    pathlib.Path("C:/Windows/Fonts/arial.ttf"),
    pathlib.Path("C:/Windows/Fonts/calibri.ttf"),
    pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    pathlib.Path("/System/Library/Fonts/Helvetica.ttc"),
]

ID1_LONG_MM = 85.60
ID1_SHORT_MM = 53.98


def _font_path() -> str:
    for candidate in _FONT_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("no usable TrueType font found for synthetic rendering")


def _cap_height_px(font: ImageFont.FreeTypeFont) -> float:
    """Ink height of a digit, which is what Rule 9 calls the height of a numeral."""
    bbox = font.getbbox("0")
    return float(bbox[3] - bbox[1])


def font_for_cap_height(target_px: float) -> ImageFont.FreeTypeFont:
    """Binary-search a font size whose digits are exactly ``target_px`` tall.

    Point size is not cap height -- the ratio depends on the typeface -- so we
    measure rather than assume. This is what makes the ground truth exact.
    """
    path = _font_path()
    low, high = 1, 400
    best = ImageFont.truetype(path, 10)
    for _ in range(24):
        mid = (low + high) / 2
        font = ImageFont.truetype(path, int(round(mid)))
        height = _cap_height_px(font)
        best = font
        if abs(height - target_px) <= 0.5:
            return font
        if height < target_px:
            low = mid
        else:
            high = mid
    return best


@dataclass
class Declaration:
    """One line of text, set at a precise physical cap height."""

    text: str
    height_mm: float
    colour: tuple[int, int, int] = (10, 10, 10)


@dataclass
class LabelSpec:
    """A package to render, described in millimetres throughout."""

    width_mm: float = 110.0
    height_mm: float = 180.0
    px_per_mm: float = 10.0
    background: tuple[int, int, int] = (250, 248, 244)
    with_id1_card: bool = True
    declarations: list[Declaration] = field(default_factory=list)

    @property
    def pdp_area_cm2(self) -> float:
        """Rule 9(4)(a): a rectangular package's panel is height x width."""
        return (self.width_mm * self.height_mm) / 100.0


def default_declarations(*, net_qty_mm: float = 3.0, body_mm: float = 2.0) -> list[Declaration]:
    return [
        Declaration("Bharat Foods Pvt Ltd", body_mm * 1.6),
        Declaration("Potato Chips - Salted", body_mm * 1.3),
        Declaration("Net Quantity: 100 g", net_qty_mm),
        Declaration("MRP Rs 40.00 (inclusive of all taxes)", body_mm),
        Declaration("Unit Sale Price: Rs 0.40 per g", body_mm),
        Declaration("Mfd: Aug 2026", body_mm),
        Declaration("Manufactured by: Bharat Foods Pvt Ltd,", body_mm),
        Declaration("Plot 14, MIDC, Pune 411018", body_mm),
        Declaration("Customer Care Manager, Plot 14, MIDC,", body_mm),
        Declaration("Pune 411018. Tel 1800-123-4567", body_mm),
        Declaration("care@bharatfoods.example", body_mm),
        Declaration("Country of Origin: India", body_mm),
    ]


def render(spec: LabelSpec) -> tuple[bytes, dict]:
    """Render a label and return its PNG bytes alongside exact ground truth."""
    declarations = spec.declarations or default_declarations()
    ppm = spec.px_per_mm

    # Canvas leaves room beneath the package for the calibration card.
    card_band_mm = (ID1_SHORT_MM + 12) if spec.with_id1_card else 0
    canvas_w = int(round((spec.width_mm + 20) * ppm))
    canvas_h = int(round((spec.height_mm + 20 + card_band_mm) * ppm))

    image = Image.new("RGB", (canvas_w, canvas_h), (225, 228, 232))
    draw = ImageDraw.Draw(image)

    pack_x0, pack_y0 = int(10 * ppm), int(10 * ppm)
    pack_x1 = pack_x0 + int(spec.width_mm * ppm)
    pack_y1 = pack_y0 + int(spec.height_mm * ppm)
    draw.rectangle([pack_x0, pack_y0, pack_x1, pack_y1], fill=spec.background,
                   outline=(120, 120, 120), width=2)

    truth_lines: list[dict] = []
    y = pack_y0 + int(8 * ppm)
    for decl in declarations:
        target_px = decl.height_mm * ppm
        font = font_for_cap_height(target_px)
        actual_px = _cap_height_px(font)
        draw.text((pack_x0 + int(6 * ppm), y), decl.text, font=font, fill=decl.colour)
        truth_lines.append(
            {
                "text": decl.text,
                "requested_height_mm": decl.height_mm,
                # What was actually drawn, after rounding to an integer point
                # size. This -- not the request -- is the ground truth.
                "actual_height_mm": round(actual_px / ppm, 3),
            }
        )
        y += int(actual_px + 6 * ppm * 0.5)

    if spec.with_id1_card:
        card_x0 = pack_x0
        card_y0 = pack_y1 + int(6 * ppm)
        card_x1 = card_x0 + int(round(ID1_LONG_MM * ppm))
        card_y1 = card_y0 + int(round(ID1_SHORT_MM * ppm))
        # High contrast against the grey surround so edge detection finds it.
        draw.rectangle([card_x0, card_y0, card_x1, card_y1], fill=(255, 255, 255),
                       outline=(20, 20, 20), width=3)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    truth = {
        "px_per_mm": ppm,
        "package_width_mm": spec.width_mm,
        "package_height_mm": spec.height_mm,
        "pdp_area_cm2": round(spec.pdp_area_cm2, 2),
        "has_id1_card": spec.with_id1_card,
        "declarations": truth_lines,
        "min_declaration_height_mm": round(min(t["actual_height_mm"] for t in truth_lines), 3),
        "net_quantity_height_mm": next(
            (t["actual_height_mm"] for t in truth_lines if "Net Quantity" in t["text"]), None
        ),
    }
    return buffer.getvalue(), truth


def compliant_label(**kwargs) -> tuple[bytes, dict]:
    """A pack whose net-quantity numerals clear the 2.5 mm this panel needs."""
    return render(LabelSpec(declarations=default_declarations(net_qty_mm=3.2), **kwargs))


def undersized_label(**kwargs) -> tuple[bytes, dict]:
    """The same pack with the net quantity set well under the requirement."""
    return render(
        LabelSpec(declarations=default_declarations(net_qty_mm=1.2, body_mm=1.1), **kwargs)
    )
