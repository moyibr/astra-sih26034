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

const BUILD_SHA = process.env.NEXT_PUBLIC_BUILD_SHA ?? "dev";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      {/*
        suppressHydrationWarning covers this element's own attributes only, not
        its subtree, so a real mismatch anywhere in the app is still reported.
        It is here because extensions -- Grammarly is the usual one -- stamp
        attributes like data-gr-ext-installed onto <body> before React
        hydrates, which React cannot tell apart from our own markup drifting.
        Nothing sets a dynamic attribute on <body>, so there is nothing here
        worth warning about, and an inspector demonstrating this should not be
        met with a red overlay caused by their own browser.
      */}
      <body className="flex min-h-full flex-col" suppressHydrationWarning>
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
          <p>
            ASTRA triages, measures and evidences. It does not issue legal notices —
            a notice drafted here has no effect until a Legal Metrology Officer signs it.
          </p>
          {/* The commit this page was built from. Deployments are cached at the
              edge for minutes at a time, so without this there is no way to
              tell what is actually live short of guessing. */}
          <p className="mt-1.5">
            <a
              href={`https://github.com/moyibr/astra-sih26034/commit/${BUILD_SHA}`}
              className="font-mono hover:underline"
              title="The commit this build was made from"
            >
              build {BUILD_SHA}
            </a>
          </p>
        </footer>
      </body>
    </html>
  );
}
