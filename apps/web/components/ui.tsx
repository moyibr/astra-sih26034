/**
 * Shared presentational pieces.
 *
 * The status vocabulary lives here rather than being re-derived per page, so
 * a violation looks identical in the officer's queue, on the scan detail and
 * on an inspector's phone. Consistency is not decoration in an enforcement
 * tool: someone is going to act on what this colour means.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import type { FindingStatus, Severity, Verdict } from "@/lib/types";

export const STATUS_STYLE: Record<
  FindingStatus,
  { label: string; className: string }
> = {
  FAIL: { label: "Violation", className: "bg-fail-soft text-fail border-fail/25" },
  PASS: { label: "Compliant", className: "bg-pass-soft text-pass border-pass/25" },
  INDETERMINATE: {
    label: "Undecided",
    className: "bg-undecided-soft text-undecided border-undecided/25",
  },
  EXEMPT: { label: "Exempt", className: "bg-exempt-soft text-exempt border-exempt/25" },
  NOT_APPLICABLE: {
    label: "Not applicable",
    className: "bg-neutral-soft text-neutral border-neutral/20",
  },
};

export const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  COMPLIANT: { label: "Compliant", className: "bg-pass-soft text-pass border-pass/25" },
  PARTIALLY_COMPLIANT: {
    label: "Partially compliant",
    className: "bg-undecided-soft text-undecided border-undecided/25",
  },
  NEEDS_REVIEW: {
    label: "Needs review",
    className: "bg-undecided-soft text-undecided border-undecided/25",
  },
  NON_COMPLIANT: {
    label: "Non-compliant",
    className: "bg-fail-soft text-fail border-fail/25",
  },
};

const SEVERITY_STYLE: Record<Severity, string> = {
  CRITICAL: "bg-fail text-white",
  MAJOR: "bg-undecided text-white",
  ADVISORY: "bg-neutral text-white",
};

export function StatusBadge({ status }: { status: FindingStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style.className}`}
    >
      {style.label}
    </span>
  );
}

export function VerdictBadge({
  verdict,
  size = "sm",
}: {
  verdict: Verdict;
  size?: "sm" | "lg";
}) {
  const style = VERDICT_STYLE[verdict];
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold ${style.className} ${
        size === "lg" ? "px-4 py-1.5 text-base" : "px-2.5 py-0.5 text-xs"
      }`}
    >
      {style.label}
    </span>
  );
}

export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${SEVERITY_STYLE[severity]}`}
    >
      {severity}
    </span>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "fail" | "pass" | "undecided";
}) {
  const toneClass = {
    default: "text-foreground",
    fail: "text-fail",
    pass: "text-pass",
    undecided: "text-undecided",
  }[tone];

  return (
    <Card className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`tnum mt-1.5 text-3xl font-semibold tracking-tight ${toneClass}`}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </Card>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mt-2 text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-fail/30 bg-fail-soft px-4 py-3 text-sm text-fail">
      {children}
    </div>
  );
}

/**
 * The banner shown when measurement rules could not be decided.
 *
 * Deliberately styled as guidance rather than as an error: it tells the
 * inspector what to do differently, because the fix is a second photograph
 * with a card in frame, not an escalation.
 */
export function CalibrationNote({ note }: { note: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-undecided/30 bg-undecided-soft px-4 py-3">
      <span aria-hidden className="text-undecided">
        ⌾
      </span>
      <p className="text-sm text-undecided">{note}</p>
    </div>
  );
}

export function ScoreBar({ score }: { score: number }) {
  const tone = score >= 90 ? "bg-pass" : score >= 70 ? "bg-undecided" : "bg-fail";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${score}%` }} />
    </div>
  );
}

export function Breadcrumb({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav className="mb-4 flex items-center gap-1.5 text-xs text-muted">
      {items.map((item, index) => (
        <span key={item.label} className="flex items-center gap-1.5">
          {index > 0 ? <span aria-hidden>/</span> : null}
          {item.href ? (
            <Link href={item.href} className="hover:text-foreground hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-foreground">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Calibration sources, described in the terms an officer would use. */
export const CALIBRATION_LABEL: Record<string, string> = {
  ARUCO: "ArUco marker",
  ID1_CARD: "ID-1 card",
  DECLARED_DIMENSION: "Declared dimensions",
  BARCODE_ASSUMED: "Barcode (assumed scale)",
  MANUAL: "Entered manually",
  NONE: "No reference",
};

export function isTrustworthyCalibration(source: string | null | undefined): boolean {
  return source === "ARUCO" || source === "ID1_CARD" || source === "MANUAL";
}
