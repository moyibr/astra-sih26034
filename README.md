# ASTRA

**Automated compliance checking for packaged commodities under the Legal
Metrology (Packaged Commodities) Rules, 2011.**

Smart India Hackathon 2026 · Problem Statement **SIH26034** · Ministry of
Consumer Affairs, Food & Public Distribution.

> *Software System to check compliance of Packaged Commodities under Legal
> Metrology (Packaged Commodities) Rules, 2011 by scanning products, images and
> labels.*

---

## What it does

Photograph a package — or ingest an e-commerce listing — and get back a cited,
evidence-backed compliance report in seconds, covering the mandatory
declarations, the legibility requirements, and the 2026 e-commerce amendments.

Three surfaces over one shared rule engine:

1. **Inspector PWA** — camera capture, offline-capable, verdict with evidence crops.
2. **E-commerce audit** — bulk catalogue ingestion and platform-level checks.
3. **Regulator dashboard** — heatmaps, category and brand risk, case management,
   auto-drafted notices for an officer to review and sign.

## What makes it defensible

Most compliance demos are "OCR → regex → red or green". Four decisions separate
this one:

**The law is data, and it is versioned.** Rules, citations, thresholds and
exemptions live in `packages/rulepacks/packs/`, not scattered through Python.
Every report pins the pack that judged it (`lmpc-2011@2026.07.01`), so a scan
taken today can be replayed years later and produce identical findings even
after the law has moved on.

**Measurements carry their own uncertainty.** A millimetre figure read off a
photograph is only as good as the reference object used to convert pixels into
millimetres. Every measurement records which calibrator produced it, and a
measurement too imprecise to defend can never produce a violation — however
damning its midpoint looks. This is why an EAN-13 barcode, which may legally be
printed anywhere between 80% and 200% magnification, is the *last* calibration
source we will use and never one we will convict on.

**The model never decides.** OCR and an optional LLM normaliser produce
`ExtractedFields`. Everything downstream is deterministic and replayable. A rule
never sees an image, so a rule's verdict can always be explained.

**Absence of evidence is not evidence of violation.** `INDETERMINATE` is a
first-class outcome. A dim photograph produces "I could not tell, re-shoot with
a card in frame" — never a notice.

## Status

| Component | State |
|---|---|
| `packages/schema` — frozen data contracts | ✅ done |
| `packages/rulepacks` — 22 rules, 3 exemptions, 16 check operators | ✅ done, 37 tests passing |
| `apps/vision` — calibration, OCR, measurement | 🚧 in progress |
| `apps/api` — FastAPI, cases, notices | ⬜ next |
| `apps/web` — dashboard + inspector PWA | ⬜ next |
| `ml/eval` — golden set and accuracy report | ⬜ next |

## Quick start

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e packages/schema -e packages/rulepacks
./.venv/Scripts/python.exe -m pytest
```

See the engine reason through seven real-world scenarios, including the two
where it deliberately refuses to accuse anyone:

```bash
./.venv/Scripts/python.exe scripts/demo_scenarios.py
```

## Layout

```
packages/schema/     frozen contracts shared by every service
packages/rulepacks/  law-as-code: versioned YAML + deterministic evaluator
apps/vision/         calibration, OCR, glyph measurement, field extraction
apps/api/            FastAPI: cases, findings, notices, analytics
apps/web/            Next.js dashboard and inspector PWA
ml/eval/             golden set and the published accuracy report
docs/rule-citations.md   every citation, and what still needs gazette checking
```

## A note on authority

ASTRA does not issue legal notices. Only a Legal Metrology Officer can. The
system triages, measures and evidences; it auto-*drafts* a notice with cited
findings for an officer to review and sign, and it records every override. The
aim is to remove the drudgery from enforcement, not the authority.
