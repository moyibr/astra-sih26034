import { Card, CardHeader, ErrorNote, SeverityChip } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { RulePackDetail } from "@/lib/types";

export const metadata = { title: "Rule pack" };
export const dynamic = "force-dynamic";

export default async function RulePackPage() {
  let pack: RulePackDetail;
  try {
    pack = await api.activeRulepack();
  } catch (cause) {
    return (
      <ErrorNote>
        {cause instanceof ApiError ? cause.message : "The rule pack could not load."}
      </ErrorNote>
    );
  }

  const verified = pack.rules.filter((r) => r.verification === "VERIFIED");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{pack.title}</h1>
        <p className="mt-1 text-sm text-muted">
          Pack <code>{pack.identifier}</code> · in force from {pack.in_force_from} ·{" "}
          {pack.counts.rules} rules, {pack.counts.exemptions} exemptions
        </p>
        <p className="mt-3 max-w-3xl text-sm">
          The law is stored as versioned data, not scattered through code. Every
          report names the pack that judged it, so an inspection can be replayed
          years later and produce identical findings even after the rules have
          moved on.
        </p>
      </header>

      {pack.counts.awaiting_gazette_check > 0 ? (
        <div className="rounded-xl border border-undecided/30 bg-undecided-soft px-5 py-4">
          <h2 className="text-sm font-semibold text-undecided">
            {pack.counts.awaiting_gazette_check} of {pack.counts.rules} provisions are
            still awaiting confirmation
          </h2>
          <p className="mt-1 text-sm text-undecided">
            They were drafted from secondary sources and are marked below. They run,
            but none should be quoted in a hearing until it has been checked against
            the official gazette text. Publishing that distinction is the point:
            a regulator should never have to take our word for which rules ran.
          </p>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {Object.entries(pack.tables).map(([name, table]) => (
          <Card key={name}>
            <CardHeader
              title={name.replace(/_/g, "-").replace("table", "Table")}
              subtitle={table.description}
            />
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-5 py-2 font-medium">
                    Panel area ({table.key === "pdp_area_cm2" ? "cm²" : table.key})
                  </th>
                  <th className="px-3 py-2 text-right font-medium">Printed</th>
                  <th className="px-5 py-2 text-right font-medium">Embossed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {table.bands.map((band, index) => {
                  const previous = index > 0 ? table.bands[index - 1].upto : null;
                  const label =
                    band.upto == null
                      ? `above ${previous}`
                      : previous == null
                        ? `up to ${band.upto}`
                        : `${previous} – ${band.upto}`;
                  return (
                    <tr key={index}>
                      <td className="tnum px-5 py-2">{label}</td>
                      <td className="tnum px-3 py-2 text-right font-medium">
                        {band.printed.toFixed(1)} mm
                      </td>
                      <td className="tnum px-5 py-2 text-right font-medium">
                        {band.embossed.toFixed(1)} mm
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="border-t border-line px-5 py-3 text-xs text-muted">
              Keyed to the area of the principal display panel — not to the net
              weight of the commodity, which is how this provision is most often
              misquoted.
            </p>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader
          title="Exemptions"
          subtitle="Evaluated before any rule, so a carve-out is never reported as a violation"
        />
        <ul className="divide-y divide-line">
          {pack.exemptions.map((exemption) => (
            <li key={exemption.id} className="px-5 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <code className="text-xs font-semibold">{exemption.id}</code>
                {exemption.verification === "NEEDS_GAZETTE_CHECK" ? (
                  <PendingChip />
                ) : null}
                <span className="ml-auto text-xs text-muted">
                  suppresses {exemption.exempts.join(", ")}
                </span>
              </div>
              <p className="mt-1 text-sm">{exemption.reason}</p>
              <p className="mt-0.5 text-xs text-muted">{exemption.citation}</p>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader
          title="Rules"
          subtitle={`${verified.length} confirmed against the gazette, ${pack.counts.awaiting_gazette_check} pending`}
        />
        <ul className="divide-y divide-line">
          {pack.rules.map((rule) => (
            <li key={rule.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityChip severity={rule.severity} />
                <span className="text-sm font-semibold">{rule.title}</span>
                {rule.requires_calibration ? (
                  <span className="rounded border border-line px-1.5 py-0.5 text-[10px] font-medium text-muted">
                    needs a scale
                  </span>
                ) : null}
                {rule.scope === "platform" ? (
                  <span className="rounded border border-accent/30 bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium">
                    platform-level
                  </span>
                ) : null}
                {rule.verification === "NEEDS_GAZETTE_CHECK" ? <PendingChip /> : null}
                <code className="ml-auto text-[11px] text-muted">{rule.id}</code>
              </div>

              <p className="mt-1 text-xs text-muted">{rule.citation}</p>

              {rule.remedy ? (
                <p className="mt-2 text-sm">
                  <span className="text-muted">To comply: </span>
                  {rule.remedy}
                </p>
              ) : null}

              {rule.note ? (
                <p className="mt-2 rounded-md bg-surface-2 px-3 py-2 text-sm text-muted">
                  {rule.note}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader title="Sources" />
        <ul className="space-y-1.5 px-5 py-4 text-sm text-muted">
          {pack.gazette_refs.map((ref) => (
            <li key={ref}>{ref}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function PendingChip() {
  return (
    <span className="rounded border border-undecided/30 bg-undecided-soft px-1.5 py-0.5 text-[10px] font-medium text-undecided">
      awaiting gazette check
    </span>
  );
}
