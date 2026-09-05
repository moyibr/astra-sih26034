"""Is this machine ready to demo, right now, with no network?

    python scripts/preflight.py     (or: make check)

Run this before walking into a room. Every check is something that has actually
gone wrong at some point, and each failure prints the one command that fixes it
rather than a description of the problem.

The bar is deliberately "with the wifi off". The venue's network is not a
dependency worth accepting for a live demo, so anything that would quietly
reach for the internet -- an OCR model downloading on first use, a font, a map
tile -- is treated as a failure here rather than discovered in front of judges.
"""

from __future__ import annotations

import importlib.util
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

_failures: list[str] = []
_warnings: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}OK  {RESET} {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def fail(label: str, fix: str) -> None:
    print(f"  {RED}FAIL{RESET} {label}\n       {DIM}fix: {fix}{RESET}")
    _failures.append(label)


def warn(label: str, detail: str) -> None:
    print(f"  {YELLOW}WARN{RESET} {label}\n       {DIM}{detail}{RESET}")
    _warnings.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


# -- checks ------------------------------------------------------------------


def check_packages() -> None:
    section("Packages")
    for name, fix in (
        ("astra_schema", "make install"),
        ("astra_rules", "make install"),
        ("vision", "make install"),
        ("fastapi", "make install"),
        ("sqlalchemy", "make install"),
    ):
        if importlib.util.find_spec(name):
            ok(name)
        else:
            fail(f"{name} not importable", fix)


def check_ocr() -> None:
    section("Live scanning")
    missing = [n for n in ("cv2", "onnxruntime", "rapidocr") if not importlib.util.find_spec(n)]
    if missing:
        fail(
            f"OCR stack incomplete: {', '.join(missing)}",
            'pip install -e "apps/vision[ocr]"',
        )
        return
    ok("OpenCV, ONNX Runtime, RapidOCR installed")

    # The models are the offline risk: RapidOCR downloads them on first use, and
    # first use must not be in front of an audience with no network.
    try:
        import rapidocr

        models = pathlib.Path(rapidocr.__file__).parent / "models"
        onnx = list(models.glob("*.onnx")) if models.exists() else []
        if len(onnx) >= 3:
            size = sum(f.stat().st_size for f in onnx) / 1e6
            ok("OCR models cached on disk", f"{len(onnx)} files, {size:.0f} MB, no download needed")
        else:
            fail(
                f"only {len(onnx)} OCR model(s) cached; they download on first use",
                "run `make demo-bundle` once while online to fetch them",
            )
    except Exception as exc:  # pragma: no cover - defensive
        warn("could not verify the OCR model cache", str(exc))


def check_engine() -> None:
    section("Rule engine")
    try:
        from astra_rules import CHECKS, RulePack

        pack = RulePack.load("lmpc-2011@2026.07.01")
        unimplemented = sorted({r.check.op for r in pack.rules} - set(CHECKS))
        if unimplemented:
            fail(f"rules with no implementation: {unimplemented}", "check packages/rulepacks")
        else:
            ok(f"{pack.identifier}", f"{len(pack.rules)} rules, {len(pack.exemptions)} exemptions")
    except Exception as exc:
        fail(f"rule pack will not load: {exc}", "make test-fast")


def check_data() -> None:
    section("Data")
    from app.config import settings

    bundle = settings.demo_bundle_dir / "astra.db"
    images = list((settings.demo_bundle_dir / "uploads").glob("*")) if settings.demo_bundle_dir.exists() else []
    if bundle.exists() and images:
        ok("committed demo bundle present", f"{len(images)} evidence images")
    else:
        fail("demo bundle missing", "make demo-bundle")

    # Present on disk is not the same as present in the repository, and a
    # deployment only gets what git carries. A `*.db` rule once re-excluded the
    # database while leaving its images tracked, which would have restored 45
    # photographs and no records to attach them to -- an empty dashboard, with
    # nothing locally to suggest anything was wrong.
    _check_bundle_is_committed(bundle)

    db_path = pathlib.Path(settings.database_url.split("///", 1)[-1])
    if db_path.exists():
        try:
            from app.db import SessionLocal
            from app.models import Scan

            session = SessionLocal()
            count = session.query(Scan).count()
            session.close()
            if count:
                ok("working database seeded", f"{count} inspections")
            else:
                warn("working database is empty", "it will seed from the bundle on first boot")
        except Exception as exc:
            warn("could not read the working database", str(exc))
    else:
        ok("working database absent", "it will seed from the committed bundle on boot")


def _check_bundle_is_committed(bundle: pathlib.Path) -> None:
    import subprocess

    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(bundle.relative_to(ROOT).as_posix())],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        warn("could not ask git whether the demo bundle is tracked", "is git on PATH?")
        return

    if tracked.returncode == 0:
        ok("demo bundle tracked by git", "a deployment will receive it")
    else:
        fail(
            "the demo database exists locally but is not tracked by git",
            "check .gitignore ordering, then: git add -f data/demo/astra.db",
        )


def check_ports() -> None:
    section("Ports")
    for port, who in ((8000, "API"), (3000, "frontend")):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.4)
            in_use = probe.connect_ex(("127.0.0.1", port)) == 0
        if in_use:
            warn(f"port {port} is already in use", f"the {who} may already be running, which is fine")
        else:
            ok(f"port {port} free", f"for the {who}")


def check_frontend() -> None:
    section("Frontend")
    web = ROOT / "apps" / "web"
    if (web / "node_modules").exists():
        ok("node_modules installed")
    else:
        fail("frontend dependencies missing", "cd apps/web && npm install")

    env = web / ".env.development"
    if env.exists() and "localhost:8000" in env.read_text(encoding="utf-8"):
        ok(".env.development points at the local API")
    else:
        warn(".env.development missing or not pointing at localhost:8000",
             "the dev frontend may try to reach the deployed API instead")


def main() -> int:
    print("ASTRA pre-flight - can this machine demo with the wifi off?")
    for check in (check_packages, check_ocr, check_engine, check_data, check_ports, check_frontend):
        try:
            check()
        except Exception as exc:  # pragma: no cover - a check must never abort the run
            fail(f"{check.__name__} raised {type(exc).__name__}: {exc}", "see the traceback above")

    print()
    if _failures:
        print(f"{RED}{len(_failures)} blocking issue(s){RESET} - fix these before demoing:")
        for f in _failures:
            print(f"  - {f}")
        return 1

    if _warnings:
        print(f"{YELLOW}Ready, with {len(_warnings)} note(s).{RESET}")
    else:
        print(f"{GREEN}Ready.{RESET}")

    print(f"\n{DIM}Start it with two terminals:{RESET}")
    print("  make api")
    print("  make web")
    print(f"{DIM}Then open http://localhost:3000{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
