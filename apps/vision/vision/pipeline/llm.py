"""Optional LLM normaliser -- strictly a gap-filler, never a judge.

Regular expressions handle conventional Indian labels well and fail on creative
ones: a net quantity set vertically, a manufacturer address broken across four
columns, a consumer-care block laid out as a table. A language model reads those
comfortably.

It is confined by three rules, and the confinement is the point:

* It may only populate fields the deterministic extractor left **empty**. It can
  never overrule something the patterns already found.
* It returns fields, never verdicts. The rule engine downstream never learns
  that a model was involved.
* Anything it supplies is capped at a lower confidence than a pattern match, so
  a rule with a high confidence threshold will still refuse to rely on it.

With no API key configured the whole module is inert and the pipeline runs fully
offline, which is how it runs at the venue.
"""

from __future__ import annotations

import json
import logging
import os

from astra_schema import ConsumerCare, FieldEvidence, NetQuantity, Origin, Price

log = logging.getLogger(__name__)

#: Nothing the model supplies may exceed this, whatever it claims.
MAX_LLM_CONFIDENCE = 0.60

_PROMPT = """\
You are reading the OCR text of an Indian packaged-commodity label.

Extract ONLY the fields listed below that are genuinely present in the text.
Omit a field entirely rather than guessing. Do not infer, do not complete
partial addresses, and do not normalise a value into something the label does
not say.

Return a single JSON object with any of these keys:
  manufacturer      {"raw_text": str}
  common_name       {"raw_text": str}
  net_quantity      {"raw_text": str, "value": number, "unit": str}
  mrp               {"raw_text": str, "amount": number}
  consumer_care     {"contact_name": str, "address": str, "phone": str, "email": str}
  origin            {"country": str}

OCR text:
---
{text}
---
Return only the JSON object.
"""


def _enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and os.getenv(
        "LLM_NORMALISER_ENABLED", "false"
    ).lower() in {"1", "true", "yes"}


def fill_gaps(text: str, extracted: dict) -> dict:
    """Populate empty fields from the label text. Never touches a filled one."""
    if not _enabled():
        return extracted

    empty = [name for name, value in extracted.items() if not getattr(value, "present", False)]
    if not empty:
        return extracted

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("LLM_NORMALISER_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=1024,
            messages=[{"role": "user", "content": _PROMPT.replace("{text}", text[:4000])}],
        )
        payload = json.loads(_only_json(response.content[0].text))
    except Exception:
        log.warning("LLM normaliser unavailable; continuing with pattern extraction only",
                    exc_info=True)
        return extracted

    for name in empty:
        data = payload.get(name)
        if not isinstance(data, dict) or not data:
            continue
        try:
            extracted[name] = _build(name, data)
            log.info("LLM normaliser supplied %s", name)
        except Exception:
            log.debug("could not build %s from %r", name, data, exc_info=True)
    return extracted


def _only_json(raw: str) -> str:
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start: end + 1] if start >= 0 and end > start else "{}"


def _build(name: str, data: dict):
    common = {"present": True, "confidence": MAX_LLM_CONFIDENCE,
              "raw_text": data.get("raw_text") or json.dumps(data)[:160]}
    match name:
        case "net_quantity":
            return NetQuantity(**common, value=data.get("value"), unit=data.get("unit"))
        case "mrp":
            return Price(**common, amount=data.get("amount"))
        case "consumer_care":
            return ConsumerCare(
                **common, contact_name=data.get("contact_name"), address=data.get("address"),
                phone=data.get("phone"), email=data.get("email"),
            )
        case "origin":
            country = data.get("country")
            return Origin(**common, country=country,
                          is_imported=(country or "").lower() not in {"india", "bharat"})
        case _:
            return FieldEvidence(**common)
