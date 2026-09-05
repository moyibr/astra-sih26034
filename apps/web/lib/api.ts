/**
 * Typed client for the ASTRA API.
 *
 * Every read goes out with `cache: "no-store"`. An enforcement dashboard that
 * quietly serves a stale count is worse than one that is briefly empty: an
 * officer deciding where to spend the afternoon needs to know the figure in
 * front of them is the figure in the database.
 */

import type {
  AnalyticsSummary,
  DimensionStat,
  HeatPoint,
  NoticeRecord,
  RulePackDetail,
  RuleStat,
  ScanDetail,
  ScanSummary,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Whether we are talking to a developer's own machine or to the public one.
 *
 * The two failures look identical to fetch and mean completely different
 * things. Locally an unreachable API means the process is not running and the
 * fix is a command. On the public deployment it almost always means the free
 * instance is asleep -- it wakes on the next request -- and telling a visitor
 * to run uvicorn is both useless and untrue. */
export const IS_LOCAL_API = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(API_BASE);

export const UNREACHABLE_MESSAGE = IS_LOCAL_API
  ? `Could not reach the ASTRA API at ${API_BASE}. Is it running?`
  : "The API did not answer in time. The public instance sleeps after fifteen " +
    "minutes idle and takes up to a minute to wake, so this usually clears on a " +
    "second attempt.";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithOneRetry(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
    });
  } catch (cause) {
    throw new ApiError(UNREACHABLE_MESSAGE, 0, cause);
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text().catch(() => undefined);
    }
    throw new ApiError(
      describeError(detail) ?? `Request failed (${response.status})`,
      response.status,
      detail,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Try once more after a network failure, which a cold start looks like.
 *
 * The request that fails against a sleeping instance is usually the one that
 * wakes it, so a single retry turns a visible error into a slow page. Only
 * network failures are retried -- an HTTP error is an answer, and asking again
 * would only be slower. An aborted request is the caller's own decision and is
 * never retried. */
async function fetchWithOneRetry(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (cause) {
    if (init.signal?.aborted || (cause as Error)?.name === "AbortError") throw cause;
    await new Promise((resolve) => setTimeout(resolve, 2000));
    return await fetch(url, init);
  }
}

/** FastAPI reports validation problems as a list; flatten it into a sentence. */
function describeError(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail: unknown }).detail;
    if (typeof inner === "string") return inner;
    if (Array.isArray(inner)) {
      return inner
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item),
        )
        .join("; ");
    }
  }
  return undefined;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  health: (init?: RequestInit) =>
    request<{
      status: string;
      rulepack: string;
      rules: number;
      /** Whether this deployment can read a photograph. The public one cannot:
       *  it runs without the OCR stack, because the free tier's tenth of a CPU
       *  would take about a minute per scan. */
      scanning?: boolean;
    }>("/health", init),

  listScans: (params: {
    verdict?: string;
    status?: string;
    state?: string;
    brand?: string;
    commodity_category?: string;
    source?: string;
    limit?: number;
    offset?: number;
  } = {}) => request<ScanSummary[]>(`/api/scans${query(params)}`),

  getScan: (id: string) => request<ScanDetail>(`/api/scans/${id}`),

  scanImageUrl: (id: string) => `${API_BASE}/api/scans/${id}/image`,

  createScan: (form: FormData) =>
    request<ScanDetail>("/api/scans", { method: "POST", body: form }),

  overrideFinding: (
    id: string,
    body: { rule_id: string; officer_status: string; officer_id: string; reason: string },
  ) =>
    request<ScanDetail>(`/api/scans/${id}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  setStatus: (id: string, status: string) =>
    request<ScanDetail>(`/api/scans/${id}/status${query({ status })}`, {
      method: "POST",
    }),

  draftNotice: (id: string, addressee?: string) =>
    request<NoticeRecord>(`/api/scans/${id}/notice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ addressee: addressee || null }),
    }),

  signNotice: (noticeId: string, officerId: string) =>
    request<NoticeRecord>(`/api/notices/${noticeId}/sign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ officer_id: officerId }),
    }),

  summary: () => request<AnalyticsSummary>("/api/analytics/summary"),

  byRule: (limit = 25) => request<RuleStat[]>(`/api/analytics/by-rule${query({ limit })}`),

  byDimension: (
    dimension: "brand" | "commodity_category" | "state" | "district" | "platform",
    limit = 20,
  ) => request<DimensionStat[]>(`/api/analytics/by-dimension${query({ dimension, limit })}`),

  heatmap: (limit = 2000) => request<HeatPoint[]>(`/api/analytics/heatmap${query({ limit })}`),

  activeRulepack: () => request<RulePackDetail>("/api/rulepacks/active"),
};
