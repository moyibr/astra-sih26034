import type { HeatPoint } from "@/lib/types";

/**
 * A deliberately tile-free map.
 *
 * Every mapping library worth using fetches raster or vector tiles from a
 * server, and this system has to work in a hall with no usable network. So the
 * points are projected onto a plain equirectangular canvas over India's
 * bounding box: no tiles, no API key, no dependency, and nothing that stops
 * working when the wifi does.
 *
 * It is a distribution plot, not a cartographic product, and it does not
 * pretend otherwise.
 */

const BOUNDS = { minLat: 6.5, maxLat: 35.8, minLon: 68.0, maxLon: 97.5 };
const WIDTH = 620;
const HEIGHT = 660;

function project(lat: number, lon: number) {
  const x = ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * WIDTH;
  // Latitude increases northward, screen y increases downward.
  const y = ((BOUNDS.maxLat - lat) / (BOUNDS.maxLat - BOUNDS.minLat)) * HEIGHT;
  return { x, y };
}

const VERDICT_FILL: Record<string, string> = {
  NON_COMPLIANT: "var(--fail)",
  PARTIALLY_COMPLIANT: "var(--undecided)",
  NEEDS_REVIEW: "var(--undecided)",
  COMPLIANT: "var(--pass)",
};

export function ViolationMap({ points }: { points: HeatPoint[] }) {
  const plotted = points.filter(
    (p) =>
      p.lat >= BOUNDS.minLat &&
      p.lat <= BOUNDS.maxLat &&
      p.lon >= BOUNDS.minLon &&
      p.lon <= BOUNDS.maxLon,
  );

  // Draw the worst last so serious violations are never hidden under a pile of
  // compliant scans.
  const ordered = [...plotted].sort((a, b) => a.weight - b.weight);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Distribution of ${plotted.length} inspections across India, coloured by verdict`}
      >
        <defs>
          <pattern id="grid" width="62" height="66" patternUnits="userSpaceOnUse">
            <path
              d="M 62 0 L 0 0 0 66"
              fill="none"
              stroke="var(--border)"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="var(--surface-2)" rx="12" />
        <rect width={WIDTH} height={HEIGHT} fill="url(#grid)" rx="12" />

        {ordered.map((point) => {
          const { x, y } = project(point.lat, point.lon);
          const radius = 3 + Math.min(point.critical, 4) * 1.6;
          return (
            <circle
              key={point.id}
              cx={x}
              cy={y}
              r={radius}
              fill={VERDICT_FILL[point.verdict] ?? "var(--neutral)"}
              fillOpacity={point.verdict === "COMPLIANT" ? 0.35 : 0.7}
              stroke={VERDICT_FILL[point.verdict] ?? "var(--neutral)"}
              strokeOpacity={0.5}
              strokeWidth={0.5}
            >
              <title>
                {[point.district, point.state].filter(Boolean).join(", ")}
                {point.brand ? ` — ${point.brand}` : ""}
                {` (${point.verdict.toLowerCase().replace(/_/g, " ")}`}
                {point.critical
                  ? `, ${point.critical} critical violation${point.critical === 1 ? "" : "s"})`
                  : ")"}
              </title>
            </circle>
          );
        })}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted">
        {[
          ["Non-compliant", "var(--fail)"],
          ["Partially / needs review", "var(--undecided)"],
          ["Compliant", "var(--pass)"],
        ].map(([label, colour]) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-2.5 rounded-full"
              style={{ background: colour }}
            />
            {label}
          </span>
        ))}
        <span className="ml-auto">Marker size reflects critical violations</span>
      </div>
    </div>
  );
}
