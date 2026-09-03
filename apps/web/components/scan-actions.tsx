"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Finding, NoticeRecord, ScanDetail } from "@/lib/types";
import { Card, CardHeader, ErrorNote, formatDateTime } from "@/components/ui";

/**
 * The officer's side of the workflow.
 *
 * Two separate actions, kept visibly separate because they are different in
 * kind: recording that the engine got something wrong, and putting a name to a
 * notice. Only the second has legal effect, and the interface should never let
 * anyone slide from one into the other by accident.
 */
export function ScanActions({ scan }: { scan: ScanDetail }) {
  const router = useRouter();
  const [notice, setNotice] = useState<NoticeRecord | null>(
    scan.notices.at(-1) ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const violations = scan.report.findings.filter((f) => f.status === "FAIL");

  async function draft() {
    setBusy(true);
    setError(null);
    try {
      setNotice(await api.draftNotice(scan.id, scan.brand ?? undefined));
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not draft a notice.");
    } finally {
      setBusy(false);
    }
  }

  async function sign(officerId: string) {
    if (!notice) return;
    setBusy(true);
    setError(null);
    try {
      setNotice(await api.signNotice(notice.id, officerId));
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not sign the notice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <OverrideForm scan={scan} onDone={() => router.refresh()} />

      <Card>
        <CardHeader
          title="Notice"
          subtitle={
            violations.length === 0
              ? "Nothing to serve — no violations were found"
              : `${violations.length} violation${violations.length === 1 ? "" : "s"} available to cite`
          }
        />
        <div className="space-y-4 p-5">
          {error ? <ErrorNote>{error}</ErrorNote> : null}

          {!notice ? (
            <>
              <p className="text-sm text-muted">
                ASTRA prepares the draft so the officer is editing rather than
                typing. It carries no authority until signed.
              </p>
              <button
                type="button"
                onClick={draft}
                disabled={busy || violations.length === 0}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
              >
                {busy ? "Preparing…" : "Draft notice"}
              </button>
            </>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                    notice.status === "DRAFT"
                      ? "border-undecided/25 bg-undecided-soft text-undecided"
                      : "border-pass/25 bg-pass-soft text-pass"
                  }`}
                >
                  {notice.status}
                </span>
                <code className="text-xs text-muted">{notice.reference}</code>
                {notice.signed_by ? (
                  <span className="text-xs text-muted">
                    Signed by {notice.signed_by} on {formatDateTime(notice.signed_at!)}
                  </span>
                ) : null}
              </div>

              <pre className="max-h-96 overflow-auto rounded-lg border border-line bg-surface-2 p-4 text-xs leading-relaxed whitespace-pre-wrap">
                {notice.body}
              </pre>

              {notice.status === "DRAFT" ? <SignForm busy={busy} onSign={sign} /> : null}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}

function SignForm({
  busy,
  onSign,
}: {
  busy: boolean;
  onSign: (officerId: string) => void;
}) {
  const [officerId, setOfficerId] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (officerId.trim().length >= 2) onSign(officerId.trim());
      }}
      className="rounded-lg border border-line bg-surface-2 p-4"
    >
      <p className="text-sm font-medium">Sign as the issuing officer</p>
      <p className="mt-1 text-xs text-muted">
        Signing is what gives this notice effect. Your identifier is recorded
        against it permanently.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          value={officerId}
          onChange={(e) => setOfficerId(e.target.value)}
          placeholder="Officer ID, e.g. LMO-0042"
          className="min-w-56 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || officerId.trim().length < 2}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-40"
        >
          {busy ? "Signing…" : "Sign notice"}
        </button>
      </div>
    </form>
  );
}

function OverrideForm({
  scan,
  onDone,
}: {
  scan: ScanDetail;
  onDone: () => void;
}) {
  const [ruleId, setRuleId] = useState("");
  const [officerStatus, setOfficerStatus] = useState("PASS");
  const [officerId, setOfficerId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assessed: Finding[] = scan.report.findings.filter(
    (f) => f.status === "FAIL" || f.status === "INDETERMINATE" || f.status === "PASS",
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.overrideFinding(scan.id, {
        rule_id: ruleId,
        officer_status: officerStatus,
        officer_id: officerId.trim(),
        reason: reason.trim(),
      });
      setRuleId("");
      setReason("");
      onDone();
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The override was not recorded.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Record a disagreement"
        subtitle="The engine's finding is kept exactly as it was; this is appended alongside it"
      />
      <div className="p-5">
        {scan.overrides.length > 0 ? (
          <ul className="mb-4 space-y-2">
            {scan.overrides.map((o, i) => (
              <li key={i} className="rounded-lg border border-line bg-surface-2 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <code>{o.rule_id}</code>
                  <span className="text-muted">
                    engine said {o.engine_status} → officer says {o.officer_status}
                  </span>
                  <span className="ml-auto text-muted">
                    {o.officer_id} · {formatDateTime(o.created_at)}
                  </span>
                </div>
                <p className="mt-1.5">{o.reason}</p>
              </li>
            ))}
          </ul>
        ) : null}

        <form onSubmit={submit} className="space-y-3">
          {error ? <ErrorNote>{error}</ErrorNote> : null}

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="sm:col-span-2">
              <span className="mb-1 block text-xs font-medium text-muted">Finding</span>
              <select
                required
                value={ruleId}
                onChange={(e) => setRuleId(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
              >
                <option value="">Choose a finding…</option>
                {assessed.map((f) => (
                  <option key={f.rule_id} value={f.rule_id}>
                    [{f.status}] {f.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium text-muted">
                Officer&rsquo;s view
              </span>
              <select
                value={officerStatus}
                onChange={(e) => setOfficerStatus(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
              >
                <option value="PASS">Compliant</option>
                <option value="FAIL">Violation</option>
                <option value="INDETERMINATE">Cannot determine</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Officer ID</span>
            <input
              required
              value={officerId}
              onChange={(e) => setOfficerId(e.target.value)}
              placeholder="LMO-0042"
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              Reason (recorded permanently, and used to improve the extractor)
            </span>
            <textarea
              required
              minLength={8}
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Measured 2.7 mm with a calliper on the physical pack."
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
            />
          </label>

          <button
            type="submit"
            disabled={busy || !ruleId || reason.trim().length < 8}
            className="rounded-lg border border-line px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:opacity-40"
          >
            {busy ? "Recording…" : "Record override"}
          </button>
        </form>
      </div>
    </Card>
  );
}
