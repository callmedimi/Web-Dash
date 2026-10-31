/**
 * API and Authentication Types for Web-Dash NOC Console.
 */

export interface FieldErrors {
  [fieldName: string]: string[] | string;
}

export interface ApiProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  code?: string;
  error?: string | { code?: string; message?: string; fields?: FieldErrors };
  message?: string;
  fields?: FieldErrors;
  invalid_params?: Array<{ name: string; reason: string }>;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly fields?: FieldErrors;
  public readonly raw?: unknown;

  constructor(
    message: string,
    status: number,
    code = "UNKNOWN_ERROR",
    fields?: FieldErrors,
    raw?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.raw = raw;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export type UserRole = "god" | "admin" | "operator" | "viewer" | string;

export interface UserInfo {
  username: string;
  role: UserRole;
  display_name: string;
  must_change_password: boolean;
  features: Record<string, boolean>;
  csrf_token?: string;
  read_only?: boolean;
}

export interface MeResponse {
  authenticated: boolean;
  username?: string;
  role?: UserRole;
  display_name?: string;
  must_change_password?: boolean;
  features?: Record<string, boolean>;
  csrf_token?: string;
  read_only?: boolean;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  username: string;
  role: UserRole;
  display_name: string;
  must_change_password: boolean;
  features: Record<string, boolean>;
  csrf_token: string;
  read_only?: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  status: string;
  message?: string;
}

export interface ProvinceHealth {
  province: string;
  total: number;
  monitored: number;
  available: number;
  problems: number;
  availability_pct: number;
}

export interface NeedsAttentionItem {
  id: string;
  type: "job" | "change" | "license" | "device" | "problem";
  title: string;
  severity: "fault" | "warn" | "ok";
  count: number;
  link: string;
}

export interface RecentJobItem {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  mode: "dry_run" | "apply";
  created_by: string;
  created_at: string | null;
  duration_seconds: number | null;
  summary: Record<string, unknown>;
}

export interface ProblemsTimelineBucket {
  timestamp: number;
  disaster: number;
  high: number;
  warning: number;
}

export interface OverviewResponse {
  telemetry_status: "ok" | "degraded" | "disabled";
  telemetry_error: string | null;
  cached_at: string;
  fleet_health: {
    total_devices: number;
    available_devices: number;
    degraded_devices: number;
    availability_pct: number;
    provinces: ProvinceHealth[];
  };
  needs_attention: NeedsAttentionItem[];
  recent_jobs: RecentJobItem[];
  problems_by_severity: {
    disaster: number;
    high: number;
    average: number;
    warning: number;
    information: number;
    not_classified: number;
  };
  problems_timeline: ProblemsTimelineBucket[];
}

