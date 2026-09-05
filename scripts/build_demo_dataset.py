"""Build the demo dataset that ships inside the repository.

    python scripts/build_demo_dataset.py

Writes ``data/demo/astra.db`` and ``data/demo/uploads/`` — a database of
inspections together with the evidence images they were drawn from.

**Why this is committed rather than generated during a build.** Producing these
inspections means running the real pipeline: OpenCV, ONNX Runtime, three OCR
models and about a minute of computation. Putting that on the critical path of
every deployment is what broke three of them. It also has to be redone every
time a container restarts on a host with no persistent disk, which is exactly
the hosting a free tier provides.

Generating it once, here, where the full stack is installed and fast, means the
deployed image only has to copy a file. The build stops depending on OCR
entirely, and every environment shows byte-identical inspections — which the
previous arrangement could not promise.

The images are written as JPEG rather than PNG purely for size: roughly 3 MB
against 13 MB, which is the difference between a reasonable thing to keep in
git and an unreasonable one. The stored bytes are what gets hashed, so the
evidence digests remain consistent with the files on disk.
"""

from __future__ import annotations

import argparse
import io
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "data" / "demo"

# The API reads these once, at import time, so they have to be set before
# anything from `app` is imported.
os.environ["DATABASE_URL"] = f"sqlite:///{(DEMO_DIR / 'astra.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(DEMO_DIR / "uploads")
os.environ["EVIDENCE_DIR"] = str(DEMO_DIR / "evidence")

sys.path.insert(0, str(ROOT / "ml" / "eval"))
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

import random  # noqa: E402

from PIL import Image  # noqa: E402

from astra_schema import PackageShape, ScanSource  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.services import scanning  # noqa: E402
from seed_demo import BRANDS, LOCATIONS, PLATFORMS, PREMISES, build_label  # noqa: E402


def to_jpeg(png_bytes: bytes, quality: int = 82) -> bytes:
    """Re-encode a rendered label as JPEG.

    Done before the image reaches the pipeline, so what is scanned, what is
    hashed and what is stored on disk are all the same bytes.
    """
    with Image.open(io.BytesIO(png_bytes)) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=45)
    parser.add_argument("--seed", type=int, default=26034)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()

    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    (DEMO_DIR / "uploads").mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    init_db()
    session = SessionLocal()

    try:
        for index in range(args.count):
            state, district, lat, lon = rng.choice(LOCATIONS)
            brand, category, brand_risk = rng.choice(BRANDS)
            platform = rng.choice(PLATFORMS)

            png, _truth, meta = build_label(rng, min(0.95, 0.14 + brand_risk))

            scanning.run_scan(
                session, to_jpeg(png, args.quality),
                inspector_id=f"LMO-{rng.randint(1, 40):04d}",
                source=ScanSource.ECOMMERCE_LISTING if platform else ScanSource.FIELD_INSPECTION,
                shape=PackageShape.RECTANGULAR,
                height_mm=meta["height_mm"], width_mm=meta["width_mm"],
                commodity_category=category, brand=brand,
                latitude=lat + rng.uniform(-0.09, 0.09),
                longitude=lon + rng.uniform(-0.09, 0.09),
                state=state, district=district,
                premises=None if platform else f"{rng.choice(PREMISES)}, {district}",
                platform=platform,
                listing_url=f"https://{platform}.example/p/{rng.randint(10000, 99999)}" if platform else None,
            )
            session.commit()
            if (index + 1) % 5 == 0:
                print(f"  {index + 1}/{args.count}", flush=True)
    finally:
        session.close()

    images = list((DEMO_DIR / "uploads").glob("*"))
    size = sum(f.stat().st_size for f in images) + (DEMO_DIR / "astra.db").stat().st_size
    print(f"\n{args.count} inspections, {len(images)} images, {size / 1e6:.1f} MB total")
    print(f"written to {DEMO_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
