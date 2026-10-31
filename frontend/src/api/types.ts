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

export interface HostGroupSummary {
  name: string;
  host_count: number;
  available_hosts: number;
  problem_count: number;
  severity_counts: Record<string, number>;
}

export interface ActiveProblemItem {
  event_id: string;
  host_id: string;
  host_name: string;
  device_name: string;
  name: string;
  severity: number;
  severity_name: string;
  clock: number;
  clock_iso: string;
  acknowledged: boolean;
  groups: string[];
  tags: Record<string, string>;
}

export interface OverviewResponse {
  telemetry_status: "ok" | "degraded" | "disabled";
  telemetry_error: string | null;
  cached_at: string;
  selected_group?: string;
  host_groups?: HostGroupSummary[];
  group_problems?: ActiveProblemItem[];
  fleet_health: {
    total_devices: number;
    available_devices: number;
    degraded_devices: number;
    availability_pct: number;
    selected_group?: string;
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

export interface DeviceItem {
  id: number;
  name: string;
  mgmt_ip: string;
  vendor: string;
  os_family: string;
  model: string | null;
  esn: string | null;
  software_version: string | null;
  lsr_id: string | null;
  role: string | null;
  site: string | null;
  province: string | null;
  tags: string[];
  health_status: "up" | "degraded" | "down" | "unknown" | string;
  last_health_check: string | null;
  zabbix_hostid: string | null;
  grafana_vars: Record<string, unknown>;
  credential_id: number | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DevicesListResponse {
  total: number;
  count: number;
  offset: number;
  limit: number;
  devices: DeviceItem[];
}

export interface TargetSetItem {
  id: number;
  name: string;
  description: string | null;
  filter_criteria: Record<string, unknown>;
  device_ids: number[];
  created_by_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CsvImportSummary {
  total_rows?: number;
  imported?: number;
  updated?: number;
  skipped?: number;
  errors?: string[];
  error?: string;
  message?: string;
}

export interface UnifiedAlarmItem {
  device_name: string;
  sequence?: number | string;
  level_name: "Critical" | "Major" | "Minor" | "Warning" | string;
  level_number?: number;
  date?: string;
  time?: string;
  age_minutes?: number;
  interface?: string | null;
  description: string;
  is_noconf?: boolean;
  source?: "zabbix" | "ssh" | "both" | string;
  acknowledged?: boolean;
  mismatch?: boolean;
}

export interface ActiveAlarmsResponse {
  total_alarms: number;
  devices_queried: number;
  alarms: UnifiedAlarmItem[];
  statistics?: {
    by_level?: Record<string, number>;
    noisy_devices?: Array<{ device: string; count: number }>;
    noisy_interfaces?: Array<{ interface: string; count: number }>;
  };
  errors?: Array<{ device_name: string; error: string }>;
}

export interface SavedAlarmFilter {
  id: number;
  name: string;
  criteria: Record<string, unknown>;
  created_by?: string;
}



