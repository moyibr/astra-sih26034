import { notFound } from "next/navigation";

import { FindingsList } from "@/components/findings";
import { ScanActions } from "@/components/scan-actions";
import {
  Breadcrumb,
  CALIBRATION_LABEL,
  CalibrationNote,
  Card,
  CardHeader,
  ScoreBar,
  VerdictBadge,
  formatDateTime,
  isTrustworthyCalibration,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ScanDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ScanPage({ params }: PageProps<"/scans/[id]">) {
  const { id } = await params;

  let scan: ScanDetail;
  try {
    scan = await api.getScan(id);
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) notFound();
    throw cause;
  }

  const { summary } = scan.report;
  const scale = scan.fields.scale;

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Inspections", href: "/scans" },
          { label: scan.brand ?? scan.id.slice(0, 8) },
        ]}
      />

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <VerdictBadge verdict={scan.verdict} size="lg" />
            <span className="rounded-full border border-line px-2.5 py-0.5 text-xs font-medium text-muted">
              {scan.status.replace(/_/g, " ")}
            </span>
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">
            {scan.brand ?? "Unidentified brand"}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {[scan.premises, scan.district, scan.state].filter(Boolean).join(" · ") ||
              "No location recorded"}{" "}
            · {formatDateTime(scan.created_at)}
          </p>
        </div>
        <div className="text-right">
          <p className="tnum text-4xl font-semibold">
            {scan.compliance_score}
            <span className="text-lg text-muted">/100</span>
          </p>
          <p className="text-xs text-muted">
            {summary.passed} of {summary.passed + summary.failed} decidable rules passed
          </p>
          <div className="mt-2 w-40">
            <ScoreBar score={scan.compliance_score} />
          </div>
        </div>
      </header>

      {scan.report.calibration_note ? (
        <CalibrationNote note={scan.report.calibration_note} />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <FindingsList report={scan.report} />
          <ScanActions scan={scan} />
        </div>

        <div className="space-y-6">
          <Card className="overflow-hidden">
            <CardHeader title="Evidence" subtitle="The image the findings were drawn from" />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={api.scanImageUrl(scan.id)}
              alt="The inspected package"
              className="w-full bg-surface-2 object-contain"
            />
            <div className="border-t border-line px-5 py-3">
              <p className="text-xs text-muted">SHA-256 of the original file</p>
              <code className="mt-0.5 block font-mono text-[10px] leading-relaxed break-all">
                {scan.image_sha256}
              </code>
            </div>
          </Card>

          <Card>
            <CardHeader title="How it was measured" />
            <dl className="divide-y divide-line text-sm">
              <Row
                label="Reference object"
                value={CALIBRATION_LABEL[scan.calibration_source ?? "NONE"]}
                tone={isTrustworthyCalibration(scan.calibration_source) ? "pass" : "undecided"}
              />
              {scale ? (
                <>
                  <Row
                    label="Scale"
                    value={`${scale.mm_per_px.toFixed(4)} mm per pixel`}
                  />
                  <Row
                    label="Uncertainty"
                    value={`±${(scale.relative_uncertainty * 100).toFixed(1)}%`}
                    tone={scale.relative_uncertainty <= 0.1 ? "pass" : "undecided"}
                  />
                </>
              ) : (
                <Row label="Scale" value="Not recovered" tone="undecided" />
              )}
              <Row
                label="Panel area"
                value={
                  scan.fields.geometry.pdp_area_cm2
                    ? `${scan.fields.geometry.pdp_area_cm2.toFixed(0)} cm² (${scan.fields.geometry.shape.toLowerCase()})`
                    : "Not determined"
                }
              />
              <Row
                label="Contrast"
                value={
                  scan.fields.declaration_contrast_ratio
                    ? `${scan.fields.declaration_contrast_ratio.toFixed(1)}:1`
                    : "Not measured"
                }
              />
              <Row label="Rule pack" value={scan.rulepack} />
              <Row label="Engine" value={`v${scan.report.engine_version}`} />
            </dl>
          </Card>

          <Card>
            <CardHeader
              title="Declarations read"
              subtitle="What the extractor found before any rule was applied"
            />
            <dl className="divide-y divide-line text-sm">
              <Row
                label="Net quantity"
                value={
                  scan.fields.net_quantity.present
                    ? `${scan.fields.net_quantity.value ?? "?"} ${scan.fields.net_quantity.unit ?? ""}`
                    : "Not found"
                }
              />
              <Row
                label="MRP"
                value={
                  scan.fields.mrp.amount != null
                    ? `Rs ${scan.fields.mrp.amount}`
                    : "Not found"
                }
              />
              <Row
                label="Manufacture date"
                value={
                  scan.fields.manufacture_date.month
                    ? `${String(scan.fields.manufacture_date.month).padStart(2, "0")}/${scan.fields.manufacture_date.year}`
                    : "Not found"
                }
              />
              <Row
                label="Consumer care"
                value={
                  [
                    scan.fields.consumer_care.contact_name && "name",
                    scan.fields.consumer_care.address && "address",
                    scan.fields.consumer_care.phone && "phone",
                    scan.fields.consumer_care.email && "e-mail",
                  ]
                    .filter(Boolean)
                    .join(", ") || "Not found"
                }
              />
              <Row
                label="Origin"
                value={scan.fields.origin.country ?? "Not declared"}
              />
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pass" | "undecided";
}) {
  const toneClass =
    tone === "pass" ? "text-pass" : tone === "undecided" ? "text-undecided" : "";
  return (
    <div className="flex items-baseline justify-between gap-4 px-5 py-2.5">
      <dt className="shrink-0 text-xs text-muted">{label}</dt>
      <dd className={`tnum text-right text-sm font-medium ${toneClass}`}>{value}</dd>
    </div>
  );
}
