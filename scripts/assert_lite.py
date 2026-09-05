"""Guard the lite image against the vision stack creeping back in.

Run during the build of ``apps/api/Dockerfile.lite``. It asserts two things:

* the API imports and can serve, without OpenCV or ONNX Runtime installed; and
* those libraries really are absent.

The second check is the one that earns its place. The lite deployment is only
reliable while it stays small — a tenth of a CPU cannot afford to load ONNX
models at boot, and a health check will not wait for it. A stray module-level
``import cv2`` somewhere in the API would reintroduce that cost quietly, and
the failure would appear as a service that mysteriously stops starting rather
than as anything resembling its cause. Better to fail here, in the build, with
the reason on screen.
"""

from __future__ import annotations

import importlib.util
import sys

HEAVY = ("cv2", "onnxruntime", "rapidocr", "zxingcpp")


def main() -> int:
    import app.main  # noqa: F401

    print("api imports cleanly without the vision stack")

    present = [name for name in HEAVY if importlib.util.find_spec(name) is not None]
    if present:
        print(
            f"ERROR: {', '.join(present)} present in the lite image.\n"
            "Something now depends on the OCR stack. Either move that import "
            "inside the function that needs it, as app/services/scanning.py "
            "does, or this deployment will stop booting on a small instance.",
            file=sys.stderr,
        )
        return 1

    from app.services.scanning import scanning_available

    if scanning_available():
        print("ERROR: scanning reports itself available in the lite image.", file=sys.stderr)
        return 1

    print("lite: no vision stack, scanning correctly reports unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
