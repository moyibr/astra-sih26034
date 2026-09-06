# Demo runbook

For the day. Follow it in order; it assumes nothing about the venue's network.

---

## The evening before

```bash
git pull && make install && make check
```

`make check` must print **Ready**. It verifies the things that have actually
gone wrong: packages importable, OCR models already on disk so nothing is
downloaded live, the rule pack loading, the demo inspections present, ports
free, frontend dependencies installed.

Then rehearse the whole thing once **with the wifi switched off**. Not as a
formality — the offline path is the one you are presenting from, and the only
way to know it works is to do it.

Pack:

- The laptop, and its charger.
- **Any wallet-sized card** — a metro card, a loyalty card, an expired debit
  card. This is the measuring reference for the four size rules; without it
  they report *undecided* and the other eighteen are unaffected. Do not use an
  identity document: photographing an Aadhaar card to check a biscuit packet
  is a question you do not want asked in the Q&A.
- **Four or five real packets.** A compliant one and a bad one at minimum.
  Check them the night before so you know what each will say.
- A phone with the demo video on it, in case the laptop itself fails.

---

## Twenty minutes before

Two terminals. The first needs an officer configured, or the override and
notice actions will refuse every request -- recording a decision is attributed
to a named officer now, so there has to be one:

```bash
ASTRA_OFFICERS="demo-token:LMO-0007:Anita Rao" make api
```

```bash
make web
```

Wait for the API to log `OCR models warmed`. That line means the first scan will
be fast rather than loading models while somebody watches.

Open `http://localhost:3000`, scan one packet, confirm you get a verdict. Leave
both terminals running and the browser open on the landing page.

If you are also showing the public link, open
`https://astra-sih26034-api.onrender.com/health` once now and wait for it to
answer. A scheduled ping keeps it awake between 05:00 and 01:00 IST, so it
should be instant -- but if the workflow has been failing, waking it has taken
anywhere from fifty seconds to eight minutes. Find that out now rather than
while someone is watching.

---

## The sixty seconds that matter

Do this first, before any slide.

1. **Pick up a packet from your own bag.** Not a prepared image — the point is
   that it is arbitrary.
2. **Lay any wallet card flat beside it** and photograph both together.
   A metro or loyalty card, not an identity document.
3. **Read the verdict aloud**, and read the citation with it: *"Rule 9,
   Table-I — required 2.5 mm, measured 1.29 mm, interval 1.12 to 1.46."*

Then, and this is the part worth practising:

4. **Take the card away and shoot the same packet again.** It now returns
   **undecided**, not a violation — and it tells you to put a card back in the
   frame.

That second shot is the strongest thing you can show. Anybody can build
something that flags a problem. Refusing to accuse someone when the evidence
cannot support it is the harder and more valuable behaviour, and it is what
separates a tool an officer could actually use from a demo.

---

## If you are asked

**"How accurate is it?"** Open `docs/accuracy.md`. 0.041 mm mean error, the true
value inside the reported interval 100% of the time, precision and recall 1.000
on the height rule. Then volunteer the limitation before they find it: that
corpus is rendered, so it answers whether the geometry is right, not how the
system copes with foil and glare. The golden set of photographed labels is the
next milestone.

**"Which rule says that?"** Open `/rulepack`. Every rule, threshold and
exemption with its citation — including the thirteen still marked *awaiting
gazette check*, which are published rather than hidden. Do not quote those as
settled law.

**"Doesn't the font rule depend on the weight?"** No, and this is the provision
most often misquoted. Rule 9 keys the minimum height to the **area of the
principal display panel** in cm², not the net quantity. The table is on
`/rulepack`.

**"Can it issue the notice automatically?"** No, and it should not. Only a Legal
Metrology Officer can. The system drafts the notice with its citations and
evidence; a named officer signs it. Show the draft — it says on its face that it
has no effect until signed, and it names the checks it is *not* alleging.

**"What stops me signing a notice as someone else?"** Show it: open an
inspection and the actions are behind a sign-in. The officer's identity comes
from their token, never from a field in the request, and the signature is an
HMAC over the evidence digest and timestamp -- alter the notice afterwards and
it stops verifying. On the public link the same actions are declined outright,
because a showcase should not accept decisions at all.

**"What about the e-commerce rules?"** Import the sample catalogue and show
Rule 6(10A) — the country-of-origin filter requirement in force since
1 July 2026. It is a question about a platform's search architecture, not about
any single pack.

---

## When something goes wrong

| Symptom | What to do |
| --- | --- |
| Frontend says it cannot reach the API | The API terminal has stopped. Restart `make api`. Both must be running. |
| A scan returns *undecided* on everything | The card was not in frame or not flat. Re-shoot; that is the system working. |
| A scan is slow the first time | Models loading. Should not happen if you warmed it; carry on talking. |
| Port already in use | Something is still running from earlier. `make check` will say so. |
| The laptop dies | The phone, and the video. Do not try to fix the laptop in front of judges. |

**If a scan gives an answer you did not expect, do not hide it.** Read what it
says and why. A tool that reports its own uncertainty honestly is the argument
you are making; a presenter who talks over an inconvenient result undermines it
far more than the result does.

---

## What not to claim

Three things this system deliberately does not do. Saying so first is stronger
than being caught:

- **It does not issue notices.** It drafts them for an officer to sign.
- **It does not replace the inspector's judgement.** Every override is recorded,
  with a reason, and the engine's original finding is kept untouched.
- **It has not been tested on real packaging at scale yet.** The measurement
  numbers come from rendered labels. Say so before someone asks.
