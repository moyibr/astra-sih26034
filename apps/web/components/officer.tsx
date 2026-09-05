"use client";

import { useEffect, useState } from "react";

import { api, officerToken, setOfficerToken } from "@/lib/api";
import { Card } from "@/components/ui";

/**
 * Signing in as the officer whose name goes on the record.
 *
 * Recording an override or signing a notice is attributable by design: the
 * whole argument for the system is that a human decision can be traced to the
 * human who made it. That was not true until recently — the officer arrived as
 * a text field anyone could fill in, on a public URL with no credential at all.
 *
 * So the identity now comes from a token the officer was issued, and the form
 * that used to ask them to type an ID is gone. Typing a name is not signing.
 */

export type WriteState = "checking" | "unavailable" | "locked" | "ready";

export function useWriteAccess(): [WriteState, (s: WriteState) => void] {
  const [state, setState] = useState<WriteState>("checking");

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => {
        if (cancelled) return;
        if (h.writes === false) setState("unavailable");
        else setState(officerToken() ? "ready" : "locked");
      })
      // An unreachable API is not the same as a deployment that declines
      // writes. Show the controls; the request will report the real problem.
      .catch(() => !cancelled && setState(officerToken() ? "ready" : "locked"));
    return () => {
      cancelled = true;
    };
  }, []);

  return [state, setState];
}

export function ReadOnlyNote() {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold">This deployment is read-only</h3>
      <p className="mt-2 text-sm text-muted">
        Recording an override and drafting a notice are how an officer acts on
        an inspection, and both are permanently attributed to them. This
        instance publishes recorded inspections and the rule pack; it does not
        accept decisions, so nothing here can be altered by whoever opens the
        link.
      </p>
      <p className="mt-2 text-sm text-muted">
        A departmental instance enables writes and issues each officer a token.
      </p>
    </Card>
  );
}

export function OfficerSignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [token, setToken] = useState("");

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold">Sign in to act on this inspection</h3>
      <p className="mt-2 text-sm text-muted">
        An override and a signed notice are recorded against you by name, so
        they need your officer token rather than a typed identifier. The token
        stays in this browser and is sent only with actions, never with
        ordinary browsing.
      </p>
      <form
        className="mt-3 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!token.trim()) return;
          setOfficerToken(token.trim());
          setToken("");
          onSignedIn();
        }}
      >
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Officer token"
          autoComplete="off"
          aria-label="Officer token"
          className="min-w-56 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={!token.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
        >
          Sign in
        </button>
      </form>
    </Card>
  );
}

export function SignedInBar({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 px-4 py-2.5">
      <p className="text-xs text-muted">
        Signed in. Actions below are recorded against you.
      </p>
      <button
        onClick={() => {
          setOfficerToken(null);
          onSignOut();
        }}
        className="text-xs font-medium text-accent hover:underline"
      >
        Sign out
      </button>
    </div>
  );
}
