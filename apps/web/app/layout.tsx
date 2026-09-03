import type { Metadata, Viewport } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ASTRA — Legal Metrology compliance",
    template: "%s · ASTRA",
  },
  description:
    "Automated compliance checking for packaged commodities under the Legal " +
    "Metrology (Packaged Commodities) Rules, 2011.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "ASTRA", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f7f9" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0f14" },
  ],
  width: "device-width",
  initialScale: 1,
  // The inspector holds this at arm's length over a package; pinch-zoom is a
  // legitimate way to read fine print, so it is not disabled.
  maximumScale: 5,
};

const NAV = [
  { href: "/inspect", label: "Inspect" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/scans", label: "Inspections" },
  { href: "/rulepack", label: "Rule pack" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-40 border-b border-line bg-surface/85 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-6 px-4 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="grid size-7 place-items-center rounded-md bg-accent text-sm font-bold text-accent-fg"
              >
                A
              </span>
              <span className="text-sm font-semibold tracking-tight">ASTRA</span>
              <span className="hidden text-xs text-muted sm:inline">
                Legal Metrology compliance
              </span>
            </Link>

            <nav className="ml-auto flex items-center gap-1 overflow-x-auto">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
          {children}
        </main>

        <footer className="border-t border-line px-4 py-4 text-center text-xs text-muted sm:px-6">
          ASTRA triages, measures and evidences. It does not issue legal notices —
          a notice drafted here has no effect until a Legal Metrology Officer signs it.
        </footer>
      </body>
    </html>
  );
}
