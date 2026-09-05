import Link from "next/link";

import {
  ApiUnavailable,
  CALIBRATION_LABEL,
  Card,
  EmptyState,
  VerdictBadge,
  formatDateTime,
  isTrustworthyCalibration,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ScanSummary } from "@/lib/types";

export const metadata = { title: "Inspections" };
export const dynamic = "force-dynamic";

const FILTERS = [
  { value: "", label: "All" },
  { value: "NON_COMPLIANT", label: "Non-compliant" },
  { value: "PARTIALLY_COMPLIANT", label: "Partially compliant" },
  { value: "NEEDS_REVIEW", label: "Needs review" },
  { value: "COMPLIANT", label: "Compliant" },
];

export default async function ScansPage({
  searchParams,
}: PageProps<"/scans">) {
  const params = await searchParams;
  const verdict = typeof params.verdict === "string" ? params.verdict : "";

  let scans: ScanSummary[];
  try {
    scans = await api.listScans({ verdict: verdict || undefined, limit: 200 });
  } catch (cause) {
    return (
      <ApiUnavailable
        what="Inspections"
        message={cause instanceof ApiError ? cause.message : undefined}
      />
    );
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inspections</h1>
          <p className="mt-1 text-sm text-muted">
            {scans.length} record{scans.length === 1 ? "" : "s"}
            {verdict ? ` matching ${verdict.toLowerCase().replace(/_/g, " ")}` : ""}
          </p>
        </div>
        <nav className="flex flex-wrap gap-1.5">
          {FILTERS.map((filter) => (
            <Link
              key={filter.value || "all"}
              href={filter.value ? `/scans?verdict=${filter.value}` : "/scans"}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                verdict === filter.value
                  ? "border-accent bg-accent-soft"
                  : "border-line hover:bg-surface-2"
              }`}
            >
              {filter.label}
            </Link>
          ))}
        </nav>
      </header>

      {scans.length === 0 ? (
        <EmptyState title="Nothing to show">
          Seed the database or{" "}
          <Link href="/inspect" className="text-accent hover:underline">
            scan a package
          </Link>
          .
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-4xl text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-5 py-2.5 font-medium">Verdict</th>
                  <th className="px-3 py-2.5 font-medium">Brand</th>
                  <th className="px-3 py-2.5 font-medium">Category</th>
                  <th className="px-3 py-2.5 font-medium">Location</th>
                  <th className="px-3 py-2.5 text-right font-medium">Critical</th>
                  <th className="px-3 py-2.5 text-right font-medium">Undecided</th>
                  <th className="px-3 py-2.5 text-right font-medium">Score</th>
                  <th className="px-3 py-2.5 font-medium">Measured via</th>
                  <th className="px-5 py-2.5 font-medium">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {scans.map((scan) => (
                  <tr key={scan.id} className="hover:bg-surface-2">
                    <td className="px-5 py-2.5">
                      <Link href={`/scans/${scan.id}`} className="inline-block">
                        <VerdictBadge verdict={scan.verdict} />
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/scans/${scan.id}`}
                        className="font-medium hover:underline"
                      >
                        {scan.brand ?? "—"}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-muted">
                      {scan.commodity_category?.replace(/_/g, " ") ?? "—"}
                    </td>
                    <td className="max-w-56 truncate px-3 py-2.5 text-muted">
                      {scan.premises ?? [scan.district, scan.state].filter(Boolean).join(", ") ?? "—"}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right font-semibold">
                      {scan.critical_violations > 0 ? (
                        <span className="text-fail">{scan.critical_violations}</span>
                      ) : (
                        <span className="text-muted">0</span>
                      )}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {scan.indeterminate > 0 ? (
                        <span className="text-undecided">{scan.indeterminate}</span>
                      ) : (
                        <span className="text-muted">0</span>
                      )}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right font-medium">
                      {scan.compliance_score}
                    </td>
                    <td className="px-3 py-2.5 text-xs">
                      <span
                        className={
                          isTrustworthyCalibration(scan.calibration_source)
                            ? "text-pass"
                            : "text-undecided"
                        }
                      >
                        {CALIBRATION_LABEL[scan.calibration_source ?? "NONE"]}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-xs whitespace-nowrap text-muted">
                      {formatDateTime(scan.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
