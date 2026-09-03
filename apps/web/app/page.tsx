import Link from "next/link";

import { Card } from "@/components/ui";

const SURFACES = [
  {
    href: "/inspect",
    title: "Inspect a package",
    body: "Photograph the panel and get a cited report in seconds, with the evidence each finding rests on.",
    cta: "Open the inspector",
  },
  {
    href: "/dashboard",
    title: "Enforcement overview",
    body: "Which provisions are breached, by which brands, in which districts — so finite inspector hours go where they count.",
    cta: "Open the dashboard",
  },
  {
    href: "/rulepack",
    title: "The rule pack",
    body: "Every rule, threshold and exemption the engine applies, published in full with its statutory citation.",
    cta: "Read the rules",
  },
];

const PRINCIPLES = [
  {
    title: "The law is versioned data",
    body: "Rules and citations live in a signed pack, not in code. Every report names the pack that judged it, so an inspection replays identically years later.",
  },
  {
    title: "Measurements carry their uncertainty",
    body: "A millimetre read off a photograph is only as good as the object used to scale it. Anything too imprecise to defend can never produce a violation.",
  },
  {
    title: "The model never decides",
    body: "OCR and an optional normaliser produce fields. Every verdict comes from a deterministic engine, so every verdict can be explained.",
  },
  {
    title: "Undecided is an answer",
    body: "A poor photograph returns “re-shoot with a card in frame”, never an accusation. Suppressing false positives is worth as much as catching violations.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <p className="text-xs font-semibold tracking-widest text-accent uppercase">
          Smart India Hackathon 2026 · SIH26034
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance">
          Compliance checking for packaged commodities, with the evidence to back it.
        </h1>
        <p className="mt-4 text-lg text-muted text-pretty">
          ASTRA scans products, images and labels against the Legal Metrology
          (Packaged Commodities) Rules, 2011 — including the e-commerce
          amendments in force since 1 July 2026 — and returns findings an officer
          can actually stand behind.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {SURFACES.map((surface) => (
          <Link key={surface.href} href={surface.href} className="group">
            <Card className="flex h-full flex-col p-5 transition-colors group-hover:border-accent/40">
              <h2 className="text-base font-semibold">{surface.title}</h2>
              <p className="mt-2 flex-1 text-sm text-muted">{surface.body}</p>
              <span className="mt-4 text-sm font-medium text-accent">
                {surface.cta} →
              </span>
            </Card>
          </Link>
        ))}
      </section>

      <section>
        <h2 className="text-sm font-semibold tracking-wide uppercase text-muted">
          How it stays defensible
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {PRINCIPLES.map((principle) => (
            <Card key={principle.title} className="p-5">
              <h3 className="text-sm font-semibold">{principle.title}</h3>
              <p className="mt-1.5 text-sm text-muted">{principle.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-line bg-surface-2 p-6">
        <h2 className="text-base font-semibold">On authority</h2>
        <p className="mt-2 max-w-3xl text-sm text-muted">
          ASTRA does not issue legal notices. Only a Legal Metrology Officer can.
          The system triages, measures and evidences; it auto-drafts a notice with
          cited findings for an officer to review and sign, and records every
          override against the engine. The aim is to remove the drudgery from
          enforcement, not the authority.
        </p>
      </section>
    </div>
  );
}
