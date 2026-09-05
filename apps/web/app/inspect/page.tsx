"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { FindingsList } from "@/components/findings";
import {
  CALIBRATION_LABEL,
  CalibrationNote,
  Card,
  CardHeader,
  ErrorNote,
  ScoreBar,
  VerdictBadge,
  isTrustworthyCalibration,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ScanDetail } from "@/lib/types";

type Shape = "RECTANGULAR" | "CYLINDRICAL" | "OTHER";

const SHAPES: { value: Shape; label: string; hint: string }[] = [
  { value: "RECTANGULAR", label: "Box or pouch", hint: "height × width" },
  { value: "CYLINDRICAL", label: "Bottle or tin", hint: "40% of h × circumference" },
  { value: "OTHER", label: "Other shape", hint: "40% of surface area" },
];

const CATEGORIES = [
  "packaged_food",
  "beverages",
  "dairy",
  "cosmetics",
  "spices",
  "staples",
  "household",
  "drugs",
];

export default function InspectPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [shape, setShape] = useState<Shape>("RECTANGULAR");
  const [heightMm, setHeightMm] = useState("");
  const [widthMm, setWidthMm] = useState("");
  const [diameterMm, setDiameterMm] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [premises, setPremises] = useState("");
  const [perishable, setPerishable] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanDetail | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  // null while unknown. A deployment without the OCR stack says so through
  // /health, and this page then explains itself rather than offering a camera
  // that would only fail.
  const [scanningEnabled, setScanningEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => setScanningEnabled(h.scanning ?? true))
      .catch(() => setScanningEnabled(null));
  }, []);

  // Revoke the object URL when the preview changes, or a long session in the
  // field slowly leaks a blob per photograph.
  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      // A refused or unavailable fix is not an error worth showing: the scan is
      // still perfectly valid, it just will not appear on the map.
      () => undefined,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600_000 },
    );
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;

    setBusy(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.set("image", file);
    form.set("shape", shape);
    form.set("is_perishable", String(perishable));
    form.set("inspector_id", "LMO-0042");
    if (heightMm) form.set("height_mm", heightMm);
    if (shape === "CYLINDRICAL" ? diameterMm : widthMm) {
      form.set(shape === "CYLINDRICAL" ? "diameter_mm" : "width_mm",
        shape === "CYLINDRICAL" ? diameterMm : widthMm);
    }
    if (brand) form.set("brand", brand);
    if (category) form.set("commodity_category", category);
    if (premises) form.set("premises", premises);
    if (coords) {
      form.set("latitude", String(coords.lat));
      form.set("longitude", String(coords.lon));
    }

    try {
      const scan = await api.createScan(form);
      setResult(scan);
      requestAnimationFrame(() =>
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The scan could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Inspect a package</h1>
        <p className="mt-1 text-sm text-muted">
          Photograph the panel carrying the mandatory declarations. The report
          cites the provision behind every finding.
        </p>
      </header>

      {scanningEnabled === false ? (
        <Card className="mb-6 p-6">
          <h2 className="text-base font-semibold">
            Live scanning runs on the local build, not here
          </h2>
          <p className="mt-3 text-sm text-muted">
            Reading a label means OpenCV, ONNX Runtime and three OCR models —
            about 240&nbsp;MB, and a few seconds of real computation per
            photograph. This public deployment runs on a free instance with a
            tenth of a CPU, where the same scan would take roughly a minute and
            loading the models at startup is slow enough to fail a health check.
          </p>
          <p className="mt-3 text-sm text-muted">
            Rather than offer a camera that would time out, this deployment
            leaves the OCR stack out entirely and says so. Everything that does
            not need to read a photograph works exactly as it does locally:
          </p>
          <ul className="mt-3 space-y-1.5 text-sm text-muted">
            {[
              ["Enforcement overview", "/dashboard", "analytics and the violation map"],
              ["45 recorded inspections", "/scans", "each with its evidence image and every finding"],
              ["The rule pack", "/rulepack", "22 rules with their statutory citations"],
            ].map(([label, href, detail]) => (
              <li key={href} className="flex gap-2">
                <span aria-hidden className="text-pass">
                  ✓
                </span>
                <span>
                  <Link href={href} className="font-medium text-accent hover:underline">
                    {label}
                  </Link>{" "}
                  — {detail}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4 rounded-md bg-surface-2 px-3 py-2 text-sm">
            To scan a real package, run the API locally. See{" "}
            <code>DEPLOY.md</code> in the repository.
          </p>
        </Card>
      ) : null}

      {scanningEnabled !== false ? (
        <>
      <div className="mb-6 rounded-xl border border-accent/25 bg-accent-soft px-5 py-4">
        <h2 className="text-sm font-semibold">Put a card in the frame</h2>
        <p className="mt-1 text-sm">
          Lay any ID-card-sized card — Aadhaar, PAN, or a debit card — flat beside
          the package before you shoot. Every such card is 85.60 × 53.98 mm by
          international standard, which is what lets the system measure print
          height in millimetres.
        </p>
        <p className="mt-2 text-sm">
          Without one, the font-size rules are reported as{" "}
          <strong>undecided</strong> rather than guessed at.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-5">
        <Card>
          <CardHeader title="Photograph" subtitle="Shoot square-on, in even light" />
          <div className="p-5">
            <label
              htmlFor="capture"
              className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line bg-surface-2 px-6 py-10 text-center transition-colors hover:border-accent/50"
            >
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={preview}
                  alt="The package about to be assessed"
                  className="max-h-72 rounded-lg object-contain"
                />
              ) : (
                <>
                  <span aria-hidden className="text-3xl">
                    ⃞
                  </span>
                  <span className="mt-3 text-sm font-medium">
                    Take a photo or choose a file
                  </span>
                  <span className="mt-1 text-xs text-muted">
                    JPEG or PNG, up to 20 MB
                  </span>
                </>
              )}
            </label>
            <input
              id="capture"
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
              }}
            />
            {file ? (
              <p className="mt-3 text-center text-xs text-muted">
                {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
              </p>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Package shape and size"
            subtitle="Rule 9 keys the required print height to the area of the principal display panel, not to the net weight"
          />
          <div className="space-y-4 p-5">
            <fieldset>
              <legend className="sr-only">Package shape</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {SHAPES.map((option) => (
                  <label
                    key={option.value}
                    className={`cursor-pointer rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                      shape === option.value
                        ? "border-accent bg-accent-soft font-medium"
                        : "border-line hover:bg-surface-2"
                    }`}
                  >
                    <input
                      type="radio"
                      name="shape"
                      value={option.value}
                      checked={shape === option.value}
                      onChange={() => setShape(option.value)}
                      className="sr-only"
                    />
                    {option.label}
                    <span className="mt-0.5 block text-xs font-normal text-muted">
                      {option.hint}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Panel height (mm)"
                value={heightMm}
                onChange={setHeightMm}
                type="number"
                placeholder="180"
              />
              {shape === "CYLINDRICAL" ? (
                <Field
                  label="Diameter (mm)"
                  value={diameterMm}
                  onChange={setDiameterMm}
                  type="number"
                  placeholder="65"
                />
              ) : (
                <Field
                  label="Panel width (mm)"
                  value={widthMm}
                  onChange={setWidthMm}
                  type="number"
                  placeholder="110"
                />
              )}
            </div>
            <p className="text-xs text-muted">
              Leave these blank and the panel is estimated from the photograph —
              the height rules then carry lower confidence.
            </p>
          </div>
        </Card>

        <Card>
          <CardHeader title="Context" subtitle="Optional, but it makes the analytics useful" />
          <div className="grid gap-3 p-5 sm:grid-cols-2">
            <Field label="Brand" value={brand} onChange={setBrand} placeholder="Bharat Foods" />
            <div>
              <label className="mb-1 block text-xs font-medium text-muted">
                Commodity category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
              >
                <option value="">Not specified</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <Field
              label="Premises"
              value={premises}
              onChange={setPremises}
              placeholder="Shree General Stores, Pune"
            />
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input
                type="checkbox"
                checked={perishable}
                onChange={(e) => setPerishable(e.target.checked)}
                className="size-4 rounded border-line"
              />
              Perishable — requires a best-before date
            </label>
          </div>
        </Card>

        {error ? <ErrorNote>{error}</ErrorNote> : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={!file || busy}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg transition-opacity disabled:opacity-40"
          >
            {busy ? "Assessing…" : "Assess compliance"}
          </button>
          {file ? (
            <button
              type="button"
              onClick={reset}
              className="rounded-lg border border-line px-4 py-2.5 text-sm font-medium hover:bg-surface-2"
            >
              Clear
            </button>
          ) : null}
          <span className="text-xs text-muted">
            {coords
              ? `Location captured (${coords.lat.toFixed(3)}, ${coords.lon.toFixed(3)})`
              : "Location unavailable — the scan will not appear on the map"}
          </span>
        </div>
      </form>
        </>
      ) : null}

      {result ? (
        <div ref={resultRef} className="mt-10 space-y-5 scroll-mt-20">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <VerdictBadge verdict={result.verdict} size="lg" />
                <p className="mt-2 text-sm text-muted">
                  {result.report.summary.failed} violation
                  {result.report.summary.failed === 1 ? "" : "s"} ·{" "}
                  {result.report.summary.indeterminate} undecided ·{" "}
                  {result.report.summary.exempt} exempt
                </p>
              </div>
              <div className="text-right">
                <p className="tnum text-3xl font-semibold">
                  {result.compliance_score}
                  <span className="text-base text-muted">/100</span>
                </p>
                <p className="text-xs text-muted">of decidable rules</p>
              </div>
            </div>
            <div className="px-5 pb-5">
              <ScoreBar score={result.compliance_score} />
              <p className="mt-3 text-xs text-muted">
                Measured via{" "}
                <strong
                  className={
                    isTrustworthyCalibration(result.calibration_source)
                      ? "text-pass"
                      : "text-undecided"
                  }
                >
                  {CALIBRATION_LABEL[result.calibration_source ?? "NONE"]}
                </strong>{" "}
                · judged under {result.rulepack} ·{" "}
                <Link href={`/scans/${result.id}`} className="text-accent hover:underline">
                  open full record
                </Link>
              </p>
            </div>
          </Card>

          {result.report.calibration_note ? (
            <CalibrationNote note={result.report.calibration_note} />
          ) : null}

          <FindingsList report={result.report} />
        </div>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted">{label}</label>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
      />
    </div>
  );
}
