/**
 * PWA manifest.
 *
 * Served from a route rather than a static file so the icons can be generated
 * inline as SVG data URIs -- one less binary asset to keep in sync, and it
 * renders crisply at every size an installed app is asked for.
 */

const ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#1d4ed8"/>
  <text x="256" y="352" font-family="system-ui,-apple-system,sans-serif"
        font-size="300" font-weight="700" fill="#ffffff" text-anchor="middle">A</text>
</svg>`;

const ICON_URI = `data:image/svg+xml,${encodeURIComponent(ICON)}`;

export function GET() {
  return Response.json({
    name: "ASTRA — Legal Metrology compliance",
    short_name: "ASTRA",
    description:
      "Scan packaged commodities against the Legal Metrology (Packaged " +
      "Commodities) Rules, 2011.",
    // The inspector installs this to scan, so that is where it opens.
    start_url: "/inspect",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f7f9",
    theme_color: "#1d4ed8",
    icons: [
      { src: ICON_URI, sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: ICON_URI, sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Inspect a package", url: "/inspect" },
      { name: "Enforcement overview", url: "/dashboard" },
    ],
  });
}
