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
    response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
    });
  } catch (cause) {
    throw new ApiError(
      `Could not reach the ASTRA API at ${API_BASE}. Is it running?`,
      0,
      cause,
    );
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
  health: () => request<{ status: string; rulepack: string; rules: number }>("/health"),

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
