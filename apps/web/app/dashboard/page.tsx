import Link from "next/link";

import { ViolationMap } from "@/components/map";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorNote,
  SeverityChip,
  Stat,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type {
  AnalyticsSummary,
  DimensionStat,
  HeatPoint,
  RuleStat,
} from "@/lib/types";

export const metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let summary: AnalyticsSummary;
  let rules: RuleStat[];
  let brands: DimensionStat[];
  let categories: DimensionStat[];
  let districts: DimensionStat[];
  let points: HeatPoint[];

  try {
    [summary, rules, brands, categories, districts, points] = await Promise.all([
      api.summary(),
      api.byRule(12),
      api.byDimension("brand", 8),
      api.byDimension("commodity_category", 8),
      api.byDimension("district", 8),
      api.heatmap(),
    ]);
  } catch (cause) {
    return (
      <ErrorNote>
        {cause instanceof ApiError
          ? cause.message
          : "The dashboard could not load."}{" "}
        Start the API with <code>uvicorn app.main:app --app-dir apps/api</code>, then
        seed some inspections with <code>python scripts/seed_demo.py</code>.
      </ErrorNote>
    );
  }

  if (summary.total_scans === 0) {
    return (
      <EmptyState title="No inspections recorded yet">
        Run <code>python scripts/seed_demo.py --count 60</code> to populate the
        dashboard, or <Link href="/inspect" className="text-accent hover:underline">
        scan a package</Link>.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Enforcement overview</h1>
        <p className="mt-1 text-sm text-muted">
          {summary.total_scans} inspections assessed under the rules in force.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Non-compliant"
          value={summary.non_compliant}
          tone="fail"
          hint={`${Math.round((summary.non_compliant / summary.total_scans) * 100)}% of inspections`}
        />
        <Stat
          label="Critical violations"
          value={summary.critical_violations}
          tone="fail"
          hint="Across all inspections"
        />
        <Stat
          label="Undecided checks"
          value={summary.undecided_rules}
          tone="undecided"
          hint="Not alleged against anyone"
        />
        <Stat
          label="Shot without a reference"
          value={
            summary.unusable_calibration_rate == null
              ? "—"
              : `${summary.unusable_calibration_rate}%`
          }
          tone={
            (summary.unusable_calibration_rate ?? 0) > 25 ? "undecided" : "default"
          }
          hint="Millimetre rules cannot be decided"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title="Most breached provisions"
            subtitle="Where enforcement effort would go furthest"
          />
          {rules.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-muted">
              No violations recorded.
            </p>
          ) : (
            <div className="divide-y divide-line">
              {rules.map((rule) => {
                const share = Math.round((rule.violations / summary.total_scans) * 100);
                return (
                  <div key={rule.rule_id} className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <SeverityChip severity={rule.severity} />
                      <span className="text-sm font-medium">{rule.title}</span>
                      <span className="tnum ml-auto text-sm font-semibold">
                        {rule.violations}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted">{rule.citation}</p>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full bg-fail"
                          style={{ width: `${Math.min(100, share)}%` }}
                        />
                      </div>
                      <span className="tnum w-10 text-right text-xs text-muted">
                        {share}%
                      </span>
                      {rule.undecided > 0 ? (
                        <span className="tnum text-xs text-undecided">
                          +{rule.undecided} undecided
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Where the violations are"
            subtitle={`${points.length} geolocated inspections`}
          />
          <div className="p-5">
            {points.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted">
                No inspection carries a location yet.
              </p>
            ) : (
              <ViolationMap points={points} />
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <OffenderTable title="Brands" subtitle="Ranked by critical violations" rows={brands} />
        <OffenderTable title="Categories" subtitle="Where to target audits" rows={categories} />
        <OffenderTable title="Districts" subtitle="Where to send inspectors" rows={districts} />
      </div>
    </div>
  );
}

function OffenderTable({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: DimensionStat[];
}) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      {rows.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted">No data.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-5 py-2 font-medium">Name</th>
              <th className="px-2 py-2 text-right font-medium">Scans</th>
              <th className="px-2 py-2 text-right font-medium">Critical</th>
              <th className="px-5 py-2 text-right font-medium">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="max-w-40 truncate px-5 py-2.5 font-medium">
                  {row.key.replace(/_/g, " ")}
                </td>
                <td className="tnum px-2 py-2.5 text-right text-muted">{row.scans}</td>
                <td className="tnum px-2 py-2.5 text-right font-semibold text-fail">
                  {row.critical_violations}
                </td>
                <td
                  className={`tnum px-5 py-2.5 text-right font-medium ${
                    row.mean_compliance_score >= 90
                      ? "text-pass"
                      : row.mean_compliance_score >= 70
                        ? "text-undecided"
                        : "text-fail"
                  }`}
                >
                  {row.mean_compliance_score}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
