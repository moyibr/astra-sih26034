"use client";

import { useState } from "react";

import type { Finding, FindingStatus, Report } from "@/lib/types";
import {
  Card,
  SeverityChip,
  StatusBadge,
  STATUS_STYLE,
} from "@/components/ui";

const ORDER: FindingStatus[] = [
  "FAIL",
  "INDETERMINATE",
  "PASS",
  "EXEMPT",
  "NOT_APPLICABLE",
];

const SEVERITY_RANK = { CRITICAL: 0, MAJOR: 1, ADVISORY: 2 } as const;

/**
 * One finding, expanded enough to be acted on without a second click.
 *
 * The measurement interval is shown in full rather than as a single figure.
 * An officer about to sign a notice needs to see the margin they are relying
 * on and the reference object it came from, because that is exactly what a
 * manufacturer's lawyer will ask about.
 */
export function FindingRow({ finding }: { finding: Finding }) {
  const isNoteworthy =
    finding.status === "FAIL" || finding.status === "INDETERMINATE";

  return (
    <div
      className={`px-5 py-4 ${
        finding.status === "FAIL" ? "border-l-2 border-l-fail" : ""
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={finding.status} />
        {finding.status === "FAIL" ? (
          <SeverityChip severity={finding.severity} />
        ) : null}
        <h3 className="text-sm font-semibold">{finding.title}</h3>
        <code className="ml-auto text-[11px] text-muted">{finding.rule_id}</code>
      </div>

      <p className="mt-1 text-xs text-muted">{finding.citation}</p>

      {(finding.measured || finding.required) && (
        <dl className="tnum mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
          {finding.measured ? (
            <div>
              <dt className="text-xs text-muted">Found</dt>
              <dd className="font-medium">{finding.measured}</dd>
            </div>
          ) : null}
          {finding.required ? (
            <div>
              <dt className="text-xs text-muted">Required</dt>
              <dd className="font-medium">{finding.required}</dd>
            </div>
          ) : null}
          {finding.measurement ? (
            <div>
              <dt className="text-xs text-muted">Interval</dt>
              <dd className="font-medium">
                {finding.measurement.ci_low_mm.toFixed(2)} –{" "}
                {finding.measurement.ci_high_mm.toFixed(2)} mm
              </dd>
            </div>
          ) : null}
        </dl>
      )}

      {isNoteworthy ? (
        <p className="mt-3 text-sm leading-relaxed">{finding.explanation}</p>
      ) : null}

      {finding.remedy ? (
        <p className="mt-2 rounded-md bg-surface-2 px-3 py-2 text-sm">
          <span className="font-medium">To comply: </span>
          {finding.remedy}
        </p>
      ) : null}

      {finding.evidence.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {finding.evidence.map((ref, index) => (
            <span
              key={index}
              className="rounded border border-line bg-surface-2 px-2 py-1 font-mono text-[11px] text-muted"
              title={ref.caption ?? undefined}
            >
              “{ref.ocr_text}”
              {ref.ocr_confidence != null
                ? ` · ${Math.round(ref.ocr_confidence * 100)}%`
                : ""}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function FindingsList({ report }: { report: Report }) {
  const [showAll, setShowAll] = useState(false);

  const sorted = [...report.findings].sort((a, b) => {
    const byStatus = ORDER.indexOf(a.status) - ORDER.indexOf(b.status);
    if (byStatus !== 0) return byStatus;
    return SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
  });

  const noteworthy = sorted.filter(
    (f) => f.status === "FAIL" || f.status === "INDETERMINATE",
  );
  const rest = sorted.filter(
    (f) => f.status !== "FAIL" && f.status !== "INDETERMINATE",
  );
  const visible = showAll ? sorted : noteworthy;

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Findings</h2>
          <p className="mt-0.5 text-xs text-muted">
            {report.summary.total_rules} rules assessed under {report.rulepack}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {ORDER.map((status) => {
            const count = report.findings.filter((f) => f.status === status).length;
            if (!count) return null;
            return (
              <span
                key={status}
                className={`tnum rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status].className}`}
              >
                {count} {STATUS_STYLE[status].label.toLowerCase()}
              </span>
            );
          })}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted">
          Every applicable rule passed.
        </p>
      ) : (
        <div className="divide-y divide-line">
          {visible.map((finding) => (
            <FindingRow key={finding.rule_id} finding={finding} />
          ))}
        </div>
      )}

      {rest.length > 0 ? (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="w-full border-t border-line px-5 py-3 text-sm font-medium text-accent hover:bg-surface-2"
        >
          {showAll
            ? "Show only violations and undecided checks"
            : `Show all ${sorted.length} rules, including the ${rest.length} that passed or did not apply`}
        </button>
      ) : null}
    </Card>
  );
}
