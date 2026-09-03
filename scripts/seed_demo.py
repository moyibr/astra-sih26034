"""Seed a realistic corpus of scans so the dashboard has something to show.

A heatmap with four points on it proves nothing. This generates a few hundred
synthetic labels spread across districts, brands and categories, with a
violation mix that behaves the way the real world does -- most packs broadly
compliant, a minority badly wrong, and a long tail of undecidable measurements
where nobody put a reference card in frame.

    python scripts/seed_demo.py --count 200

It writes through the same service the API uses, so nothing here is a fixture
the rest of the system does not also produce.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml" / "eval"))
sys.path.insert(0, str(ROOT / "apps" / "api"))

import synth  # noqa: E402

from astra_schema import PackageShape, ScanSource  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.services import scanning  # noqa: E402

# Districts with rough centroids, so the map looks like India rather than noise.
LOCATIONS = [
    ("Maharashtra", "Pune", 18.5204, 73.8567),
    ("Maharashtra", "Mumbai Suburban", 19.0760, 72.8777),
    ("Maharashtra", "Nagpur", 21.1458, 79.0882),
    ("Delhi", "New Delhi", 28.6139, 77.2090),
    ("Karnataka", "Bengaluru Urban", 12.9716, 77.5946),
    ("Tamil Nadu", "Chennai", 13.0827, 80.2707),
    ("West Bengal", "Kolkata", 22.5726, 88.3639),
    ("Gujarat", "Ahmedabad", 23.0225, 72.5714),
    ("Uttar Pradesh", "Lucknow", 26.8467, 80.9462),
    ("Rajasthan", "Jaipur", 26.9124, 75.7873),
    ("Telangana", "Hyderabad", 17.3850, 78.4867),
    ("Kerala", "Ernakulam", 9.9312, 76.2673),
]

BRANDS = [
    ("Bharat Foods", "packaged_food", 0.10),
    ("Ganga Snacks", "packaged_food", 0.55),
    ("Himalaya Naturals", "cosmetics", 0.35),
    ("Deccan Spices", "spices", 0.25),
    ("Coastal Beverages", "beverages", 0.15),
    ("Sunrise Dairy", "dairy", 0.20),
    ("Nimbus Cosmetics", "cosmetics", 0.70),
    ("Vindhya Grains", "staples", 0.30),
]

PLATFORMS = [None, None, None, "marketplace-a", "marketplace-b", "quick-commerce-c"]

PREMISES = [
    "Shree General Stores", "New Apna Bazaar", "Sai Provision Mart",
    "Krishna Kirana", "City Supermarket", "Annapurna Stores",
]


def build_label(rng: random.Random, violation_rate: float) -> tuple[bytes, dict, dict]:
    """Render one label, sometimes deliberately defective."""
    offend = rng.random() < violation_rate

    # Panel size varies, which is the whole point: the required glyph height
    # follows the panel, so identical print is lawful on one pack and not on
    # another.
    width_mm = rng.choice([70.0, 90.0, 110.0, 140.0])
    height_mm = rng.choice([120.0, 150.0, 180.0, 220.0])

    net_qty_mm = rng.uniform(1.0, 1.9) if offend else rng.uniform(2.8, 4.5)
    body_mm = rng.uniform(0.7, 1.0) if offend else rng.uniform(1.4, 2.2)

    declarations = synth.default_declarations(net_qty_mm=net_qty_mm, body_mm=body_mm)

    if offend and rng.random() < 0.4:
        # Drop the consumer-care block down to an e-mail alone.
        declarations = [
            d for d in declarations
            if "Customer Care" not in d.text and "Tel 1800" not in d.text
        ]
    if offend and rng.random() < 0.3:
        declarations = [d for d in declarations if "inclusive of all taxes" not in d.text]
        declarations.append(synth.Declaration("MRP Rs 40.00", body_mm))

    # A third of inspections are shot without a reference card, which is what
    # actually happens in the field.
    with_card = rng.random() > 0.33

    png, truth = synth.render(
        synth.LabelSpec(
            width_mm=width_mm, height_mm=height_mm,
            declarations=declarations, with_id1_card=with_card,
        )
    )
    meta = {"width_mm": width_mm, "height_mm": height_mm, "with_card": with_card}
    return png, truth, meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=26034)
    parser.add_argument("--violation-rate", type=float, default=0.35)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    init_db()

    session = SessionLocal()
    created = 0
    try:
        for index in range(args.count):
            state, district, lat, lon = rng.choice(LOCATIONS)
            brand, category, brand_risk = rng.choice(BRANDS)
            platform = rng.choice(PLATFORMS)

            # A brand's own risk profile drives whether this pack offends, so
            # the "worst offenders" table means something.
            rate = min(0.95, args.violation_rate * 0.4 + brand_risk)
            png, _truth, meta = build_label(rng, rate)

            scanning.run_scan(
                session, png,
                inspector_id=f"LMO-{rng.randint(1, 40):04d}",
                source=ScanSource.ECOMMERCE_LISTING if platform else ScanSource.FIELD_INSPECTION,
                shape=PackageShape.RECTANGULAR,
                height_mm=meta["height_mm"], width_mm=meta["width_mm"],
                commodity_category=category, brand=brand,
                # Jitter the centroid so points spread across the district.
                latitude=lat + rng.uniform(-0.09, 0.09),
                longitude=lon + rng.uniform(-0.09, 0.09),
                state=state, district=district,
                premises=None if platform else f"{rng.choice(PREMISES)}, {district}",
                platform=platform,
                listing_url=f"https://{platform}.example/p/{rng.randint(10000, 99999)}" if platform else None,
            )
            session.commit()
            created += 1
            if created % 10 == 0:
                print(f"  {created}/{args.count} scans seeded", flush=True)
    finally:
        session.close()

    print(f"\nSeeded {created} scans. Start the API and open the dashboard.")


if __name__ == "__main__":
    main()
