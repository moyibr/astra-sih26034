# Rule citations and verification status

Every citation in `packages/rulepacks/packs/lmpc-2011/v2026.07.01.yaml` is listed
here with where it came from and whether it has been checked against the official
gazette text.

**Anyone can be asked in the Q&A "which rule says that?" — this file is the
answer sheet.** Nothing here may be quoted in the pitch while still marked
`NEEDS_GAZETTE_CHECK`.

## Primary source of truth

The consolidated rules on **indiacode.nic.in** are authoritative. Secondary
sources (law-firm briefings, IndianKanoon, tax portals) were used for drafting
and are recorded below, but they disagree with each other on several points and
must not be the final citation.

## Verified

| Rule | Provision | Notes |
|---|---|---|
| Rule 6(1)(a) | Name and complete address of manufacturer / packer / importer | Consistent across all sources. |
| Rule 6(1)(b) | Common or generic name of the commodity | Consistent. |
| Rule 6(1)(c) | Net quantity in standard units or number | Consistent. |
| Rule 6(1)(e) | Retail sale price, inclusive of all taxes | Consistent. |
| Rule 9, Table-I | Numeral height by **area of the principal display panel** | See below. |
| Rule 9, Table-II | Numeral height where quantity is by length, area or number | See below. |
| Rule 9 | Letters ≥ 1 mm; ≥ 2 mm when blown, formed, moulded, embossed or perforated | Consistent. |
| Rule 9 | Width of a letter or numeral ≥ ⅓ of its height, except `1`, `i`, `I`, `l` | Consistent. |
| Rule 9(4) | PDP area: rectangular = h × w; cylindrical = 40% × h × circumference; other = 40% of total surface area | Consistent. |

### The font-height tables

This is the provision most often misquoted — including in most SIH write-ups of
this problem statement, which claim the threshold is keyed to **net weight**. It
is not. It is keyed to the **area of the principal display panel in cm²**.

**Table-I** — net quantity declared by weight or volume:

| PDP area (cm²) | Printed | Blown / formed / moulded / embossed |
|---|---|---|
| up to 50 | 1.0 mm | 1.5 mm |
| 50 – 100 | 1.5 mm | 3.0 mm |
| 100 – 500 | 2.5 mm | 4.0 mm |
| 500 – 2500 | 4.0 mm | 6.0 mm |
| above 2500 | 6.0 mm | 6.0 mm |

**Table-II** — net quantity declared by length, area or number:

| PDP area (cm²) | Printed | Embossed |
|---|---|---|
| up to 100 | 1 mm | 2 mm |
| 100 – 500 | 2 mm | 4 mm |
| 500 – 2500 | 4 mm | 6 mm |
| above 2500 | 6 mm | 6 mm |

Band boundaries are implemented as **inclusive of their upper value**, so a
panel of exactly 50 cm² attracts the 1.0 mm requirement. Where the drafting is
ambiguous we resolve it in favour of the person who would be penalised.

## Needs gazette check

These are drafted from secondary sources and **must** be confirmed before the
pitch. Each one is flagged `NEEDS_GAZETTE_CHECK` in the rule pack.

| # | Item | The specific question to answer |
|---|---|---|
| 1 | Rule 6(1) sub-clause lettering | Sources order the clauses differently and some cite a clause `(ac)` for consumer care. Record the actual lettering in the current consolidated text. |
| 2 | Consumer care conjunction | Are **name and address and (telephone or e-mail)** required, or must both channels appear? Currently implemented as "at least one channel". |
| 3 | Table-I `≤ 50 cm²` embossed value | One source gives 1.5 mm, another 2.0 mm. Currently 1.5 mm. |
| 4 | PDP rule number | IndianKanoon renders the PDP provision as "Section 7"; most practitioner sources cite **Rule 9**. Confirm which numbering the consolidated text uses, and cite both if genuinely ambiguous. |
| 5 | Rule 26 exemption thresholds | Confirm the ≤ 10 g / 10 ml threshold and the exact list of exempted commodity classes. |
| 6 | Unit sale price | Confirm the sub-rule number for the requirement effective 01.10.2022 and which packages are excluded. |
| 7 | Month/year relaxations | The 01.10.2022 amendment relaxed month-and-year for some categories (food, seeds, cosmetics per one source). Confirm scope. |
| 8 | Second Schedule pack sizes | Transcribe the actual prescribed quantities per commodity into the rule pack; currently the check has no data loaded and returns INDETERMINATE. |
| 9 | Dual MRP | Confirm the precise provision prohibiting differing retail sale prices, and the correct penalty section of the Legal Metrology Act, 2009. |
| 10 | Penalty sections | Exact sections and amounts to quote on a notice. Do not quote figures found on blogs. |
| 11 | Rule 6(10) / 6(10A) text | Obtain the notification text of the Amendment Rules, 2026 (notified 13.02.2026, in force 01.07.2026) and record the verbatim wording of 6(10A). |

## On the colour-contrast rule

Rule 9 requires a colour that "contrasts conspicuously with the background". The
rule states **no number**. We apply a WCAG 2.x luminance contrast ratio of 4.5:1
as a published, defensible working proxy, and the generated finding says so in
terms. Do not let this be presented as a statutory figure.

## Secondary sources consulted

- Legal Metrology (Packaged Commodities) Rules, 2011 — consolidated PDF, Maharashtra Legal Metrology
- IndianKanoon — principal display panel provision, incl. Table-I and Table-II
- TaxGuru — FAQs on the LMPC Rules, 2011
- SCC Online / Mondaq — Legal Metrology (Packaged Commodities) Amendment Rules, 2026
- iPleaders — overview of rule numbering
