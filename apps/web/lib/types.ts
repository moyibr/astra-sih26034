/**
 * Shapes returned by the ASTRA API.
 *
 * These mirror `packages/schema`, which is the single source of truth. When a
 * contract changes there, it changes here; nothing in the UI should invent a
 * field the engine does not actually produce.
 */

export type FindingStatus =
  | "PASS"
  | "FAIL"
  | "INDETERMINATE"
  | "EXEMPT"
  | "NOT_APPLICABLE";

export type Severity = "CRITICAL" | "MAJOR" | "ADVISORY";

export type Verdict =
  | "COMPLIANT"
  | "PARTIALLY_COMPLIANT"
  | "NEEDS_REVIEW"
  | "NON_COMPLIANT";

export type CalibrationSource =
  | "ARUCO"
  | "ID1_CARD"
  | "DECLARED_DIMENSION"
  | "BARCODE_ASSUMED"
  | "MANUAL"
  | "NONE";

export interface Measurement {
  value_mm: number;
  ci_low_mm: number;
  ci_high_mm: number;
  source: CalibrationSource;
  detail: string | null;
}

export interface EvidenceRef {
  image_sha256: string;
  polygon: [number, number][];
  crop_uri: string | null;
  ocr_text: string | null;
  ocr_confidence: number | null;
  caption: string | null;
}

export interface Finding {
  rule_id: string;
  citation: string;
  title: string;
  status: FindingStatus;
  severity: Severity;
  measured: string | null;
  required: string | null;
  measurement: Measurement | null;
  confidence: number;
  explanation: string;
  remedy: string | null;
  exempted_by: string | null;
  evidence: EvidenceRef[];
}

export interface ReportSummary {
  total_rules: number;
  passed: number;
  failed: number;
  indeterminate: number;
  exempt: number;
  not_applicable: number;
  critical_violations: number;
  major_violations: number;
  advisory_violations: number;
  compliance_score: number;
}

export interface Report {
  scan_id: string;
  image_sha256: string;
  rulepack: string;
  evaluated_at: string;
  engine_version: string;
  findings: Finding[];
  summary: ReportSummary;
  calibration_note: string | null;
}

export interface ScanSummary {
  id: string;
  created_at: string;
  verdict: Verdict;
  compliance_score: number;
  critical_violations: number;
  major_violations: number;
  advisory_violations: number;
  indeterminate: number;
  calibration_source: CalibrationSource | null;
  source: string;
  status: string;
  brand: string | null;
  commodity_category: string | null;
  state: string | null;
  district: string | null;
  premises: string | null;
  latitude: number | null;
  longitude: number | null;
  rulepack: string;
}

export interface OverrideRecord {
  rule_id: string;
  engine_status: FindingStatus;
  officer_status: string;
  officer_id: string;
  reason: string;
  created_at: string;
}

export interface NoticeRecord {
  id: string;
  reference: string;
  status: "DRAFT" | "SIGNED" | "SERVED" | "DISPOSED";
  addressee: string | null;
  cited_rules: string[];
  body: string;
  signed_by: string | null;
  signed_at: string | null;
  created_at: string;
}

export interface ScanDetail extends ScanSummary {
  image_sha256: string;
  report: Report;
  fields: ExtractedFields;
  overrides: OverrideRecord[];
  notices: NoticeRecord[];
}

export interface FieldEvidence {
  present: boolean;
  raw_text: string | null;
  confidence: number;
  spans: { text: string; confidence: number; polygon: [number, number][] }[];
}

export interface ExtractedFields {
  scan_id: string;
  image_sha256: string;
  scale: {
    mm_per_px: number;
    source: CalibrationSource;
    relative_uncertainty: number;
    reference_detail: string | null;
  } | null;
  full_text: string;
  ocr_scripts_seen: string[];
  geometry: {
    shape: string;
    print_method: string;
    height_mm: number | null;
    width_mm: number | null;
    diameter_mm: number | null;
    pdp_area_cm2: number | null;
    pdp_area_confident: boolean;
  };
  manufacturer: FieldEvidence;
  common_name: FieldEvidence;
  net_quantity: FieldEvidence & {
    value: number | null;
    unit: string | null;
    canonical_unit: string | null;
  };
  mrp: FieldEvidence & { amount: number | null; candidate_amounts: number[] };
  unit_sale_price: FieldEvidence & { amount: number | null };
  manufacture_date: FieldEvidence & {
    month: number | null;
    year: number | null;
    is_ambiguous: boolean;
  };
  best_before: FieldEvidence & { month: number | null; year: number | null };
  consumer_care: FieldEvidence & {
    contact_name: string | null;
    address: string | null;
    phone: string | null;
    email: string | null;
  };
  origin: FieldEvidence & { country: string | null; is_imported: boolean | null };
  declaration_contrast_ratio: number | null;
}

export interface AnalyticsSummary {
  total_scans: number;
  non_compliant: number;
  partially_compliant?: number;
  compliant?: number;
  needs_review: number;
  compliance_rate: number | null;
  critical_violations: number;
  undecided_rules: number;
  unusable_calibration_rate: number | null;
  mean_compliance_score?: number;
  by_verdict: Record<string, number>;
  by_source: Record<string, number>;
}

export interface RuleStat {
  rule_id: string;
  title: string;
  citation: string;
  severity: Severity;
  violations: number;
  undecided: number;
}

export interface DimensionStat {
  key: string;
  scans: number;
  critical_violations: number;
  mean_compliance_score: number;
}

export interface HeatPoint {
  id: string;
  lat: number;
  lon: number;
  verdict: Verdict;
  critical: number;
  brand: string | null;
  category: string | null;
  district: string | null;
  state: string | null;
  weight: number;
}

export interface RulePackRule {
  id: string;
  title: string;
  citation: string;
  severity: Severity;
  scope: string;
  requires_calibration: boolean;
  applies_when: Record<string, unknown>;
  remedy: string | null;
  note: string | null;
  verification: "VERIFIED" | "NEEDS_GAZETTE_CHECK";
  check: string;
  implemented: boolean;
}

export interface RulePackDetail {
  identifier: string;
  title: string;
  jurisdiction: string;
  in_force_from: string;
  gazette_refs: string[];
  tables: Record<
    string,
    {
      description: string;
      key: string;
      unit: string;
      bands: { upto: number | null; printed: number; embossed: number }[];
    }
  >;
  exemptions: {
    id: string;
    citation: string;
    reason: string;
    exempts: string[];
    verification: string;
  }[];
  rules: RulePackRule[];
  counts: {
    rules: number;
    exemptions: number;
    awaiting_gazette_check: number;
  };
}
