"""Recovering a millimetre scale from a photograph.

Everything ASTRA says about font height depends on one question: how many
millimetres is a pixel worth? A photograph on its own cannot answer it. Some
object of known physical size has to appear in the frame.

We try four references in descending order of trustworthiness and record which
one succeeded, because a finding is only as defensible as the ruler behind it:

1. **ArUco fiducial** -- a printed marker, most accurate, but needs preparation.
2. **ID-1 card** -- any Aadhaar, PAN, debit or credit card. ISO/IEC 7810 fixes
   these at 85.60 x 53.98 mm worldwide, and every inspector already carries one.
   This is the practical field workflow.
3. **Declared package dimensions** -- available on e-commerce listings, which
   must carry them.
4. **EAN-13 barcode** -- last resort, and deliberately so. The symbol is
   37.29 mm wide including quiet zones *at 100% magnification*, but the standard
   permits 80% to 200%, so the true width lies anywhere between roughly 29.8 mm
   and 74.6 mm. Calibrating off one and then convicting a manufacturer would be
   a false accusation, which is why measurements from this source are marked too
   uncertain to sustain a violation.

Detecting a reference also gives us a homography onto its known rectangle, which
we use to rectify the whole image. Without that, perspective would compress
glyphs and manufacture violations out of nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from astra_schema import CalibrationSource, Scale

log = logging.getLogger(__name__)

# ISO/IEC 7810 ID-1: the format of essentially every wallet card in the world.
ID1_LONG_MM = 85.60
ID1_SHORT_MM = 53.98
ID1_ASPECT = ID1_LONG_MM / ID1_SHORT_MM  # ~1.586

# EAN-13 at 100% magnification (SC2), including both quiet zones.
EAN13_NOMINAL_WIDTH_MM = 37.29

ARUCO_DEFAULT_SIDE_MM = 30.0


@dataclass
class Calibration:
    """A recovered scale, plus the rectification that made it meaningful."""

    scale: Scale
    homography: np.ndarray | None = None
    rectified: np.ndarray | None = None
    reference_quad: np.ndarray | None = None

    @property
    def image(self) -> np.ndarray | None:
        return self.rectified


def _order_quad(pts: np.ndarray) -> np.ndarray:
    """Order four points as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def _rectify_from_quad(
    image: np.ndarray, quad: np.ndarray, long_mm: float, short_mm: float, px_per_mm: float = 12.0
) -> tuple[np.ndarray, np.ndarray, float]:
    """Map a known rectangle onto an axis-aligned one and rectify the image.

    Returns the warped image, the homography, and mm-per-pixel in the warped
    frame. Choosing the output resolution ourselves is what makes the scale
    exact: we know the reference is `long_mm` across, and we decide how many
    pixels that becomes.
    """
    ordered = _order_quad(quad)

    # Decide which pair of sides is the long one, so a card photographed in
    # portrait is handled as readily as one in landscape.
    top = np.linalg.norm(ordered[1] - ordered[0])
    right = np.linalg.norm(ordered[2] - ordered[1])
    if top < right:
        ordered = np.roll(ordered, -1, axis=0)

    out_w = float(long_mm * px_per_mm)
    out_h = float(short_mm * px_per_mm)
    dst = np.array([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]], dtype=np.float32)

    homography = cv2.getPerspectiveTransform(ordered, dst)

    h, w = image.shape[:2]
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)

    # Shift so the whole projected image stays inside the output canvas.
    min_xy = projected.min(axis=0)
    max_xy = projected.max(axis=0)
    shift = np.array([[1, 0, -min_xy[0]], [0, 1, -min_xy[1]], [0, 0, 1]], dtype=np.float64)
    homography = shift @ homography

    canvas_w = int(np.clip(max_xy[0] - min_xy[0], 1, 6000))
    canvas_h = int(np.clip(max_xy[1] - min_xy[1], 1, 6000))
    rectified = cv2.warpPerspective(image, homography, (canvas_w, canvas_h))

    return rectified, homography, 1.0 / px_per_mm


# -- reference detectors -----------------------------------------------------


def detect_aruco(image: np.ndarray, marker_mm: float = ARUCO_DEFAULT_SIDE_MM) -> Calibration | None:
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    except Exception:  # OpenCV builds vary in where aruco lives
        log.debug("ArUco detection unavailable in this OpenCV build", exc_info=True)
        return None

    if ids is None or len(corners) == 0:
        return None

    quad = np.asarray(corners[0]).reshape(4, 2)
    rectified, homography, mm_per_px = _rectify_from_quad(
        image, quad, marker_mm, marker_mm, px_per_mm=20.0
    )
    scale = Scale(
        mm_per_px=mm_per_px,
        source=CalibrationSource.ARUCO,
        relative_uncertainty=0.010,
        reference_detail=f"ArUco marker, {marker_mm:g} mm side",
    )
    return Calibration(scale, homography, rectified, quad)


def _interior_edge_density(edges: np.ndarray, quad: np.ndarray) -> float:
    """How much detail lives inside a quadrilateral, ignoring its own outline.

    This is what separates a calibration card from a package. A card is
    essentially featureless; a package is covered in print. Aspect ratio alone
    cannot tell them apart -- a 110 x 180 mm carton has an aspect of 1.64 against
    the card's 1.586, well inside any usable tolerance -- so we look inside.
    """
    mask = np.zeros(edges.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, quad.reshape(-1, 2).astype(np.int32), 255)
    # Pull the mask well inside the border so the quad's own edge is excluded.
    eroded = cv2.erode(mask, np.ones((15, 15), np.uint8), iterations=2)
    area = int(eroded.sum() // 255)
    if area < 400:
        return 1.0
    return float(np.count_nonzero(edges[eroded > 0])) / area


def detect_id1_card(image: np.ndarray) -> Calibration | None:
    """Find a wallet-sized card lying flat beside the package.

    ISO/IEC 7810 fixes ID-1 at 85.60 x 53.98 mm, an aspect of 1.586, which is
    close enough to a great many cartons that shape alone is not identification.
    We therefore require a candidate to be both card-shaped *and* substantially
    blank inside, and among those we take the best-scoring rather than simply the
    largest -- picking the largest is exactly how a detector ends up calibrating
    off the package it was meant to measure.

    A roughly face-on photograph is assumed: at a steep angle perspective
    distorts the apparent ratio enough that a card stops looking like one, and we
    would rather find nothing than calibrate off a misidentified rectangle. The
    PWA guides the inspector to shoot flat, and ArUco remains the precise path.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = image.shape[0] * image.shape[1]

    best: tuple[float, np.ndarray] | None = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < frame_area * 0.01 or area > frame_area * 0.60:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue

        ordered = _order_quad(approx)
        side_a = (np.linalg.norm(ordered[1] - ordered[0]) + np.linalg.norm(ordered[2] - ordered[3])) / 2
        side_b = (np.linalg.norm(ordered[2] - ordered[1]) + np.linalg.norm(ordered[3] - ordered[0])) / 2
        if min(side_a, side_b) < 1:
            continue
        aspect = max(side_a, side_b) / min(side_a, side_b)
        if not (1.42 <= aspect <= 1.76):
            continue

        density = _interior_edge_density(edges, approx)
        if density > 0.020:
            continue  # too much print inside to be a blank card

        # Prefer a true card aspect and a clean interior. Both terms are
        # normalised so neither can dominate.
        score = abs(aspect - ID1_ASPECT) / 0.17 + density / 0.020
        if best is None or score < best[0]:
            best = (score, approx)

    if best is None:
        return None

    quad = best[1]
    rectified, homography, mm_per_px = _rectify_from_quad(
        image, quad, ID1_LONG_MM, ID1_SHORT_MM, px_per_mm=12.0
    )
    scale = Scale(
        mm_per_px=mm_per_px,
        source=CalibrationSource.ID1_CARD,
        relative_uncertainty=0.020,
        reference_detail="ID-1 card (ISO/IEC 7810), 85.60 x 53.98 mm",
    )
    return Calibration(scale, homography, rectified, quad)


def detect_barcode(image: np.ndarray) -> Calibration | None:
    """Last-resort calibration, and never one we will convict on.

    An EAN-13 symbol is 37.29 mm wide including quiet zones at 100% magnification,
    but the standard permits 80% to 200%. We record the assumption honestly and
    attach an uncertainty large enough that the engine will refuse to assert a
    millimetre violation from it.
    """
    try:
        import zxingcpp
    except ImportError:
        return None

    try:
        results = zxingcpp.read_barcodes(image)
    except Exception:
        log.debug("barcode decode failed", exc_info=True)
        return None
    if not results:
        return None

    symbol = results[0]
    pos = symbol.position
    corners = np.array(
        [[pos.top_left.x, pos.top_left.y], [pos.top_right.x, pos.top_right.y],
         [pos.bottom_right.x, pos.bottom_right.y], [pos.bottom_left.x, pos.bottom_left.y]],
        dtype=np.float32,
    )
    width_px = (
        np.linalg.norm(corners[1] - corners[0]) + np.linalg.norm(corners[2] - corners[3])
    ) / 2
    if width_px < 10:
        return None

    scale = Scale.from_reference(
        measured_px=float(width_px),
        known_mm=EAN13_NOMINAL_WIDTH_MM,
        source=CalibrationSource.BARCODE_ASSUMED,
        detail=(
            f"barcode {symbol.text} measured {width_px:.0f} px, assumed 37.29 mm "
            "(100% magnification); the standard permits 80%-200%"
        ),
    )
    return Calibration(scale, None, None, corners)


def estimate_package_extent(image: np.ndarray) -> tuple[float, float] | None:
    """Bounding box of the dominant foreground object, in pixels.

    A heuristic, and treated as one everywhere it is used.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    frame_area = image.shape[0] * image.shape[1]
    if cv2.contourArea(biggest) < frame_area * 0.05:
        return None
    _, _, w, h = cv2.boundingRect(biggest)
    return float(w), float(h)


def from_declared_dimension(
    image: np.ndarray, package_width_mm: float
) -> Calibration | None:
    """Scale from a dimension the seller declared, e.g. on a listing.

    The declared width belongs to the *package*, not to the photograph, so the
    scale has to be measured against the pixels the package actually occupies.
    Dividing by the full image width instead silently assumes the package fills
    the frame edge to edge; on an ordinary photograph with any margin around the
    subject that understates every millimetre by however much background is in
    shot, and understated millimetres are false violations.

    If the package cannot be located in the frame we return nothing rather than
    guess, and the caller falls through to a weaker reference or to none at all.
    """
    extent = estimate_package_extent(image)
    if extent is None:
        log.info("declared dimension supplied, but the package could not be located")
        return None

    width_px, _height_px = extent
    scale = Scale.from_reference(
        measured_px=width_px,
        known_mm=package_width_mm,
        source=CalibrationSource.DECLARED_DIMENSION,
        detail=(
            f"declared package width {package_width_mm:g} mm spanning "
            f"{width_px:.0f} px of the frame"
        ),
        # Segmenting the package edge is looser than finding a printed
        # fiducial, and the uncertainty has to say so.
        extra_uncertainty=0.05,
    )
    return Calibration(scale)


def from_manual(measured_px: float, known_mm: float) -> Calibration:
    """Scale from a width the inspector measured and typed in."""
    scale = Scale.from_reference(
        measured_px=measured_px,
        known_mm=known_mm,
        source=CalibrationSource.MANUAL,
        detail=f"inspector-entered reference, {known_mm:g} mm",
    )
    return Calibration(scale)


def calibrate(image: np.ndarray, *, package_width_mm: float | None = None) -> Calibration:
    """Try every reference in order and return the best available.

    Always returns a Calibration. When nothing is found the scale carries
    ``CalibrationSource.NONE`` and 100% uncertainty, which the rule engine reads
    as "measurement rules cannot be decided" rather than as a clean bill of
    health.
    """
    for detector in (detect_aruco, detect_id1_card):
        try:
            found = detector(image)
        except Exception:
            log.warning("calibration detector %s failed", detector.__name__, exc_info=True)
            continue
        if found is not None:
            log.info("calibrated via %s", found.scale.source)
            return found

    if package_width_mm:
        found = from_declared_dimension(image, package_width_mm)
        if found is not None:
            log.info("calibrated via declared package width")
            return found

    found = detect_barcode(image)
    if found is not None:
        log.info("calibrated via barcode (not usable for violations)")
        return found

    log.info("no calibration reference found in frame")
    return Calibration(
        Scale(
            mm_per_px=1.0,
            source=CalibrationSource.NONE,
            relative_uncertainty=1.0,
            reference_detail="no reference object detected in frame",
        )
    )
