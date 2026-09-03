"""Turning recognised text into the declarations the rule engine reasons about.

This is the last probabilistic step. Everything after it is deterministic, so
this module's job is to be honest rather than clever: when a declaration is
genuinely there, find it and say how sure we are; when it is not, say nothing
rather than guessing, because a confident guess here becomes a wrongly issued
notice three steps later.

Extraction is deliberately rule-based. Regular expressions over Indian label
conventions are boring, but they are inspectable, they behave identically on
every run, and when one misfires you can see exactly why. An optional LLM
normaliser (see ``llm.py``) is layered on top for labels whose layout defeats
patterns -- it may only *fill in* fields left empty here, and never overrule one.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from astra_schema import (
    ConsumerCare,
    FieldEvidence,
    NetQuantity,
    Origin,
    PackDate,
    Price,
    TextSpan,
)

log = logging.getLogger(__name__)

# -- vocabulary --------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_UNIT_ALTERNATION = (
    r"kgs?|kg|gms?|gm|g|mgs?|mg|mls?|ml|ltrs?|ltr|lts?|lt|litres?|liters?|l|cms?|cm|mms?|mm|m"
)

_NET_QTY_LABEL = re.compile(
    r"(?:net\s*(?:qty|quantity|wt|weight|vol|volume|content[s]?)|net)\s*[:.\-]?\s*"
    r"(\d+(?:[.,]\d+)?)\s*(" + _UNIT_ALTERNATION + r")\b",
    re.IGNORECASE,
)
_BARE_QTY = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(" + _UNIT_ALTERNATION + r")\b\.?", re.IGNORECASE
)
_COUNT_QTY = re.compile(
    r"\b(\d+)\s*(?:N|Nos?\.?|pieces?|pcs?\.?|units?|tablets?|sachets?)\b", re.IGNORECASE
)

_MRP_LABEL = re.compile(
    r"(?:m\.?\s?r\.?\s?p\.?|maximum\s+retail\s+price|max\.?\s+retail\s+price)", re.IGNORECASE
)
_MONEY = re.compile(r"(?:rs\.?|inr|₹)\s*(\d+(?:[.,]\d{1,2})?)", re.IGNORECASE)
_INCLUSIVE = re.compile(
    r"incl(?:usive|\.)?\s*(?:of)?\s*all\s*tax|incl\.?\s*of\s*all\s*taxes", re.IGNORECASE
)
_UNIT_PRICE = re.compile(
    r"(?:unit\s+sale\s+price|price\s+per\s+unit|(?:rs\.?|₹)\s*\d+(?:\.\d+)?\s*(?:/|per)\s*"
    r"(?:\d+\s*)?(?:" + _UNIT_ALTERNATION + r")\b)",
    re.IGNORECASE,
)

# "Manufactured by" introduces an address, not a date. The negative lookahead is
# what keeps a manufacturer's name from being parsed as a manufacturing date --
# a mistake that silently satisfies the month-and-year rule on packs that carry
# no date at all.
_MFD_LABEL = re.compile(
    r"(?:mfd|mfg|m\.f\.d|pkd|manufactured?|packed|date\s+of\s+(?:manufacture|packing))"
    # The word boundary matters. Without it `manufactured?` happily matches
    # just "manufacture", leaving the lookahead to inspect "d by" -- which is
    # not "by" -- so the guard silently does nothing and a manufacturer's name
    # gets parsed as a manufacturing date, quietly satisfying the
    # month-and-year rule on a pack that carries no date at all.
    r"\b(?!\s*(?:by\b|and\b|&))"
    r"(?:\s+on)?\s*[:.\-]?\s*",
    re.IGNORECASE,
)
_BEST_BEFORE_LABEL = re.compile(
    r"(?:best\s+before|use\s+by|exp(?:iry)?(?:\s+date)?|consume\s+before)\s*[:.\-]?\s*", re.IGNORECASE
)
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\b")
_DATE_MON_YEAR = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?[\s,\-/]*(\d{2,4})\b",
    re.IGNORECASE,
)
_DATE_MM_YYYY = re.compile(r"\b(0?[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})\b")

_MANUFACTURER_LABEL = re.compile(
    r"(?:manufactured?\s+(?:&\s+packed\s+)?by|packed\s+by|marketed\s+by|mfd\.?\s+by|"
    r"mfg\.?\s+by|imported\s+(?:&\s+packed\s+)?by|produced\s+by|name\s+of\s+manufacturer)"
    r"\s*[:.\-]?\s*",
    re.IGNORECASE,
)
_PINCODE = re.compile(r"\b[1-9]\d{5}\b")

_CARE_LABEL = re.compile(
    r"(?:consumer\s+(?:care|complaints?)|customer\s+(?:care|service|complaints?)|"
    r"for\s+(?:any\s+)?(?:complaints?|queries|grievances?)|grievance\s+officer|"
    r"contact\s+us|helpline)",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?:\+?91[\s\-]?)?(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4}|\b0?\d{2,5}[\s\-]?\d{6,8}\b)")
_EMAIL = re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b")
_DESIGNATION = re.compile(
    r"\b(?:[A-Z][a-z]+\s+)?(?:Customer\s+Care\s+Manager|Grievance\s+Officer|Nodal\s+Officer|"
    r"Consumer\s+Care\s+(?:Manager|Executive|Cell)|Manager|Director|Proprietor)\b"
)

# [ 	] rather than \s: a country name may contain spaces ("United Arab
# Emirates") but must never swallow the newline and absorb the declaration
# printed on the following line.
_ORIGIN_LABEL = re.compile(
    r"(?:country\s+of\s+origin|made\s+in|product\s+of|origin)[ 	]*[:.\-]?[ 	]*"
    r"([A-Za-z]{2,}(?:[ 	]+[A-Za-z]+){0,3})",
    re.IGNORECASE,
)
_IMPORT_HINT = re.compile(r"imported\s+by|country\s+of\s+origin", re.IGNORECASE)

_COMMON_NAME_LABEL = re.compile(
    r"(?:common\s+(?:or\s+generic\s+)?name|generic\s+name|product\s+name|name\s+of\s+(?:the\s+)?"
    r"commodity)\s*[:.\-]?\s*([^\n]{2,60})",
    re.IGNORECASE,
)


# -- helpers -----------------------------------------------------------------


def _spans_for(spans: list[TextSpan], needle: str, limit: int = 3) -> list[TextSpan]:
    """Spans whose text overlaps a matched fragment, for evidence crops."""
    if not needle:
        return []
    key = re.sub(r"\s+", "", needle.lower())[:24]
    if not key:
        return []
    hits = []
    for s in spans:
        flat = re.sub(r"\s+", "", s.text.lower())
        if key and (key in flat or flat in key or _overlap(flat, key) >= 4):
            hits.append(s)
    return hits[:limit]


def _overlap(a: str, b: str) -> int:
    """Length of the longest common substring, capped for speed."""
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
            if best >= 8:
                return best
    return best


def _line_after(text: str, match: re.Match, span_chars: int = 120) -> str:
    """The text following a label, stopping at a blank line or another label."""
    tail = text[match.end(): match.end() + span_chars]
    cut = re.split(r"\n\s*\n|(?=\b(?:MRP|Net Qty|Net Weight|Best Before)\b)", tail, maxsplit=1)[0]
    return cut.strip(" .:-\n")


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _normalise_unit(raw: str) -> tuple[str | None, float | None]:
    """Map a printed unit to its SI symbol and to a base-unit multiplier.

    Base units are grams for mass and millilitres for volume, which is what the
    Rule 26 small-package exemption and the Second Schedule sizes are keyed to.
    """
    token = raw.strip().rstrip(".").lower()
    table: dict[str, tuple[str, float]] = {
        "g": ("g", 1.0), "gm": ("g", 1.0), "gms": ("g", 1.0), "gram": ("g", 1.0),
        "grams": ("g", 1.0),
        "kg": ("kg", 1000.0), "kgs": ("kg", 1000.0),
        "mg": ("mg", 0.001), "mgs": ("mg", 0.001),
        "ml": ("ml", 1.0), "mls": ("ml", 1.0),
        "l": ("l", 1000.0), "lt": ("l", 1000.0), "lts": ("l", 1000.0),
        "ltr": ("l", 1000.0), "ltrs": ("l", 1000.0),
        "litre": ("l", 1000.0), "litres": ("l", 1000.0),
        "liter": ("l", 1000.0), "liters": ("l", 1000.0),
        "mm": ("mm", 1.0), "cm": ("cm", 10.0), "m": ("m", 1000.0),
    }
    hit = table.get(token)
    return (hit[0], hit[1]) if hit else (None, None)


_LOOKS_LIKE_DECLARATION = re.compile(
    r"net\s*(qty|quantity|wt|weight)|m\.?r\.?p\.?|maximum\s+retail|manufactured|packed\s+by|"
    r"customer\s+care|consumer\s+care|country\s+of\s+origin|best\s+before|unit\s+sale|"
    r"mfd|mfg|@|\bwww\.|tel\b",
    re.IGNORECASE,
)


# -- field extractors --------------------------------------------------------


def extract_net_quantity(text: str, spans: list[TextSpan]) -> NetQuantity:
    match = _NET_QTY_LABEL.search(text)
    confidence = 0.9
    if match is None:
        match = _BARE_QTY.search(text)
        confidence = 0.55  # no label, so we are inferring
    if match is not None:
        value = _to_float(match.group(1))
        printed_unit = match.group(2)
        symbol, multiplier = _normalise_unit(printed_unit)
        # Preserve exactly what was printed, including a stray full stop, so the
        # unit-symbol rule can quote the label rather than our tidied version.
        raw_unit = text[match.start(2): match.end(2)]
        if text[match.end(2): match.end(2) + 1] == ".":
            raw_unit += "."
        return NetQuantity(
            present=True,
            confidence=confidence,
            raw_text=match.group(0).strip(),
            value=value,
            unit=raw_unit,
            canonical_unit=symbol,
            value_in_base=(value * multiplier) if (value and multiplier) else None,
            spans=_spans_for(spans, match.group(0)),
        )

    count = _COUNT_QTY.search(text)
    if count is not None:
        return NetQuantity(
            present=True, confidence=0.6, raw_text=count.group(0).strip(),
            value=_to_float(count.group(1)), declared_by_count=True,
            spans=_spans_for(spans, count.group(0)),
        )
    return NetQuantity()


def extract_mrp(text: str, spans: list[TextSpan]) -> Price:
    """Find the retail sale price, and any rival price claiming to be one.

    Collecting every money-like figure near the words "MRP" is how a dual-price
    detector ends up accusing a perfectly compliant pack: the mandatory unit
    sale price sits right beside the retail price and is a different figure by
    design. We therefore gather amounts only from the window immediately
    following an MRP label, and drop any that falls inside a unit-sale-price
    declaration.
    """
    label = _MRP_LABEL.search(text)
    if label is None:
        return Price()

    unit_price_ranges = [m.span() for m in _UNIT_PRICE.finditer(text)]

    def inside_unit_price(pos: int) -> bool:
        return any(lo <= pos < hi for lo, hi in unit_price_ranges)

    amounts: list[float] = []
    for occurrence in _MRP_LABEL.finditer(text):
        window_end = min(len(text), occurrence.end() + 60)
        for money in _MONEY.finditer(text, occurrence.end(), window_end):
            if inside_unit_price(money.start()):
                continue
            value = _to_float(money.group(1))
            if value:
                amounts.append(round(value, 2))

    window = text[label.start(): label.start() + 90]
    return Price(
        present=True,
        confidence=0.9 if amounts else 0.5,
        raw_text=window.split("\n")[0].strip(),
        amount=amounts[0] if amounts else None,
        has_inclusive_of_taxes_phrase=bool(_INCLUSIVE.search(text)),
        candidate_amounts=sorted(set(amounts)),
        spans=_spans_for(spans, label.group(0)),
    )


def extract_unit_sale_price(text: str, spans: list[TextSpan]) -> Price:
    match = _UNIT_PRICE.search(text)
    if match is None:
        return Price()
    amount = _MONEY.search(match.group(0))
    return Price(
        present=True, confidence=0.7, raw_text=match.group(0).strip(),
        amount=_to_float(amount.group(1)) if amount else None,
        is_unit_sale_price=True, spans=_spans_for(spans, match.group(0)),
    )


def _parse_date(fragment: str) -> tuple[PackDate | None, str]:
    """Parse a date fragment, reporting whether it is genuinely undecidable.

    A hyphenated DD-MM-YYYY is lawful and ubiquitous in India, so it is *not*
    ambiguous merely for being hyphenated. It becomes ambiguous only when both
    leading components could be a month and nothing else on the label settles it.
    """
    named = _DATE_MON_YEAR.search(fragment)
    if named is not None:
        month = _MONTHS[named.group(1).lower()]
        year = int(named.group(2))
        year += 2000 if year < 100 else 0
        return PackDate(present=True, month=month, year=year, is_ambiguous=False), named.group(0)

    mm_yyyy = _DATE_MM_YYYY.search(fragment)
    if mm_yyyy is not None:
        return (
            PackDate(present=True, month=int(mm_yyyy.group(1)), year=int(mm_yyyy.group(2)),
                     is_ambiguous=False),
            mm_yyyy.group(0),
        )

    numeric = _DATE_NUMERIC.search(fragment)
    if numeric is not None:
        a, b = int(numeric.group(1)), int(numeric.group(2))
        year = int(numeric.group(3))
        year += 2000 if year < 100 else 0
        # Indian convention is DD-MM-YYYY, so read it that way; flag it only
        # when the other reading is equally possible.
        ambiguous = a <= 12 and b <= 12 and a != b
        day, month = (a, b) if b <= 12 else (b, a)
        return (
            PackDate(present=True, day=day, month=month, year=year, is_ambiguous=ambiguous),
            numeric.group(0),
        )

    year_only = re.search(r"\b(20\d{2})\b", fragment)
    if year_only is not None:
        return PackDate(present=True, year=int(year_only.group(1)), is_ambiguous=False), year_only.group(0)

    return None, ""


def extract_date(text: str, spans: list[TextSpan], *, best_before: bool = False) -> PackDate:
    label_re = _BEST_BEFORE_LABEL if best_before else _MFD_LABEL
    label = label_re.search(text)
    if label is None:
        return PackDate()

    fragment = text[label.end(): label.end() + 60]
    parsed, matched = _parse_date(fragment)
    if parsed is None:
        return PackDate(
            present=True, confidence=0.4,
            raw_text=(label.group(0) + fragment.split("\n")[0]).strip(),
            spans=_spans_for(spans, label.group(0)),
        )

    parsed.confidence = 0.85
    parsed.raw_text = matched.strip()
    parsed.spans = _spans_for(spans, matched or label.group(0))
    return parsed


def extract_manufacturer(text: str, spans: list[TextSpan]) -> FieldEvidence:
    label = _MANUFACTURER_LABEL.search(text)
    if label is not None:
        body = _line_after(text, label)
        if body:
            # A postal code is good evidence that an actual address followed the
            # company name, rather than just a brand.
            has_address = bool(_PINCODE.search(body)) or len(body) > 30
            return FieldEvidence(
                present=True,
                confidence=0.85 if has_address else 0.55,
                raw_text=f"{label.group(0).strip()} {body}".strip(),
                spans=_spans_for(spans, body),
            )

    pin = _PINCODE.search(text)
    if pin is not None:
        start = max(0, pin.start() - 90)
        return FieldEvidence(
            present=True, confidence=0.4,
            raw_text=text[start: pin.end()].replace("\n", " ").strip(),
            spans=_spans_for(spans, text[start: pin.end()]),
        )
    return FieldEvidence()


def extract_common_name(
    text: str, spans: list[TextSpan], *, claimed: set[str] | None = None
) -> FieldEvidence:
    label = _COMMON_NAME_LABEL.search(text)
    if label is not None:
        return FieldEvidence(
            present=True, confidence=0.85, raw_text=label.group(1).strip(),
            spans=_spans_for(spans, label.group(1)),
        )

    # Fall back to the largest text on the pack, which on Indian labels is
    # almost always the product name. Text already claimed by another
    # declaration is excluded first -- a net quantity is often the largest thing
    # printed, and without this the fallback confidently reports "100 g" as the
    # name of the commodity.
    claimed = claimed or set()
    measured = [
        s for s in spans
        if s.ink_height_px and len(s.text.strip()) >= 3 and s.text not in claimed
        and not _LOOKS_LIKE_DECLARATION.search(s.text)
    ]
    if measured:
        biggest = max(measured, key=lambda s: s.ink_height_px or 0)
        return FieldEvidence(
            present=True, confidence=0.45, raw_text=biggest.text.strip(), spans=[biggest],
        )
    return FieldEvidence()


def extract_consumer_care(text: str, spans: list[TextSpan]) -> ConsumerCare:
    label = _CARE_LABEL.search(text)
    if label is None:
        # A phone or e-mail with no consumer-care heading is not a compliant
        # declaration, but it is evidence of an attempt -- surface it so the rule
        # can report precisely what is missing.
        phone, email = _PHONE.search(text), _EMAIL.search(text)
        if not (phone or email):
            return ConsumerCare()
        return ConsumerCare(
            present=True, confidence=0.45,
            raw_text=(phone or email).group(0),
            phone=phone.group(0).strip() if phone else None,
            email=email.group(0) if email else None,
        )

    window = text[label.start(): label.start() + 260]
    phone = _PHONE.search(window)
    email = _EMAIL.search(window)
    designation = _DESIGNATION.search(window)
    pin = _PINCODE.search(window)

    address = None
    if pin is not None:
        start = max(0, pin.start() - 110)
        address = window[start: pin.end()].replace("\n", " ").strip(" ,.-")

    return ConsumerCare(
        present=True,
        confidence=0.8,
        raw_text=window.split("\n\n")[0].strip(),
        contact_name=designation.group(0).strip() if designation else None,
        address=address,
        phone=phone.group(0).strip() if phone else None,
        email=email.group(0) if email else None,
        spans=_spans_for(spans, label.group(0)),
    )


def extract_origin(text: str, spans: list[TextSpan]) -> Origin:
    label = _ORIGIN_LABEL.search(text)
    if label is not None:
        country = label.group(1).strip(" .:-\n").split("\n")[0].strip()
        country = re.split(r"\s{2,}", country)[0][:30].strip()
        if country:
            return Origin(
                present=True, confidence=0.8, raw_text=label.group(0).strip(),
                country=country, is_imported=country.lower() not in {"india", "bharat"},
                spans=_spans_for(spans, label.group(0)),
            )
    if _IMPORT_HINT.search(text):
        # We know it is imported but could not read the country: that is a
        # violation of the origin rule, not an unknown.
        return Origin(present=False, confidence=0.5, is_imported=True)
    return Origin()


def extract_all(text: str, spans: list[TextSpan]) -> dict:
    """Run every extractor over one label."""
    # Order matters. Every other declaration is resolved first so the
    # common-name fallback can be told which text is already spoken for.
    resolved = {
        "manufacturer": extract_manufacturer(text, spans),
        "net_quantity": extract_net_quantity(text, spans),
        "mrp": extract_mrp(text, spans),
        "unit_sale_price": extract_unit_sale_price(text, spans),
        "manufacture_date": extract_date(text, spans, best_before=False),
        "best_before": extract_date(text, spans, best_before=True),
        "consumer_care": extract_consumer_care(text, spans),
        "origin": extract_origin(text, spans),
    }
    claimed = {
        span.text
        for value in resolved.values()
        for span in (getattr(value, "spans", []) or [])
    }
    resolved["common_name"] = extract_common_name(text, spans, claimed=claimed)
    return resolved
