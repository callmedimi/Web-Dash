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

export interface ChangeRequestItem {
  id: string;
  device_id: number;
  device_name?: string;
  creator_id: string;
  approver_id?: string | null;
  risk_level: "low" | "medium" | "high";
  status:
    | "planned"
    | "precheck_passed"
    | "precheck_failed"
    | "awaiting_approval"
    | "approved"
    | "applied"
    | "verified"
    | "rolled_back"
    | "rejected";
  plan: Record<string, unknown>;
  diff: string;
  rollback_diff?: string;
  precheck_results?: Record<string, unknown>;
  verification_results?: Record<string, unknown>;
  job_id?: string | null;
  blast_radius_exceeded?: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface JobTaskItem {
  id: string;
  device_name: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled" | "skipped" | string;
  started_at?: string | null;
  finished_at?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface JobItem {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "partial" | string;
  mode: "dry_run" | "apply" | string;
  created_by: string;
  created_at: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  params?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  parent_job_id?: string | null;
  tasks?: JobTaskItem[];
}

export interface JobListResponse {
  items: JobItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DownLinkItem {
  router: string;
  interface: string;
  description?: string;
  down_duration?: string;
  is_noconf?: boolean;
  is_trunk?: boolean;
  status?: string;
  line_protocol?: string;
}

export interface DownLinkReportResponse {
  id: number;
  province?: string;
  created_at: string;
  report_data: DownLinkItem[];
  noconf_data?: DownLinkItem[];
  trunk_data?: DownLinkItem[];
  analytics?: {
    total_down?: number;
    total_routers?: number;
    noconf_count?: number;
    trunk_count?: number;
    by_province?: Record<string, number>;
  };
}

export interface ReportComparisonResult {
  current_report_id: number;
  previous_report_id: number;
  previous_created_at?: string;
  new_down: DownLinkItem[];
  recovered: DownLinkItem[];
  persistent_down?: DownLinkItem[];
}

export interface DailyDigestResponse {
  generated_at: string;
  window_hours: number;
  metrics: {
    total_alarms?: number;
    unresolved_critical?: number;
    down_links_count?: number;
    changes_planned?: number;
    licenses_expiring?: number;
    jobs_executed?: number;
  };
  highlights?: string[];
}

export interface MonitoringDeviceRow {
  id: number;
  name: string;
  mgmt_ip: string;
  role: string;
  province: string;
  site: string;
  zabbix_hostid?: string;
  telemetry_host_id?: string;
  telemetry_status: "HEALTHY" | "WARNING" | "CRITICAL" | "UNAVAILABLE" | "UNMONITORED" | string;
  is_available: boolean;
  problem_count: number;
  problems?: Array<{
    name: string;
    severity: number;
    severity_name: string;
    clock: number;
  }>;
}

export interface FleetHealthResponse {
  summary: {
    total_devices: number;
    monitored_devices: number;
    unmonitored_devices: number;
    available_devices: number;
    availability_pct: number;
    total_active_problems: number;
    problems_by_severity?: Record<string, number>;
  };
  province_stats: Array<{
    province: string;
    total: number;
    monitored: number;
    available: number;
    problems: number;
  }>;
  devices: MonitoringDeviceRow[];
  host_groups?: Array<{
    name: string;
    host_count: number;
    available_hosts: number;
    problem_count: number;
  }>;
  active_problems?: Array<{
    event_id: string;
    device_name: string;
    name: string;
    severity_name: string;
    clock_iso: string;
  }>;
}

export interface TelemetryDoctorResponse {
  zabbix: {
    status: "ok" | "degraded" | "error" | string;
    version?: string;
    error?: string | null;
  };
  grafana: {
    status: "ok" | "degraded" | "error" | string;
    base_url?: string;
    details?: Record<string, unknown>;
  };
  coverage: {
    total_devices: number;
    mapped_devices: number;
    coverage_pct: number;
  };
  doctor_verdict: "HEALTHY" | "DEGRADED" | string;
}

export interface DeviceMonitoringResponse {
  device: {
    name: string;
    mgmt_ip: string;
    role: string;
    province: string;
    telemetry_host_id?: string;
  };
  metrics: {
    cpu?: { value: number; units: string } | null;
    memory?: { value: number; units: string } | null;
    temperature?: { value: number; units: string } | null;
  };
  interfaces: Array<{
    name: string;
    admin_status?: number | string;
    oper_status?: number | string;
    in_rate_bps?: number;
    out_rate_bps?: number;
    errors_in?: number;
    errors_out?: number;
  }>;
  series?: Array<{ clock: number; value: number }>;
  grafana?: {
    deep_link?: string;
    embed_url?: string;
  };
}

export interface ConfigSnapshotItem {
  id: string;
  device_id: number;
  kind: "running" | "startup" | "candidate" | string;
  sha256: string;
  size_bytes: number;
  taken_at: string;
  author?: string;
  change_id?: number | null;
  metadata?: Record<string, unknown>;
  content?: string;
}

export interface ConfigDiffResponse {
  device_id?: number;
  from_snapshot_id?: string;
  to_snapshot_id?: string;
  unified_diff: string;
  hunks?: Array<{
    old_start?: number;
    old_lines?: number;
    new_start?: number;
    new_lines?: number;
    lines?: string[];
  }>;
  stats?: {
    additions: number;
    deletions: number;
    modifications: number;
  };
  additions?: number;
  deletions?: number;
  changed?: boolean;
}

export interface ComplianceRule {
  id?: string;
  rule_id?: string;
  name: string;
  severity: "high" | "medium" | "low" | string;
  description: string;
  remediation_hint: string;
  passed_devices?: number;
  failed_devices?: number;
  compliance_pct?: number;
}

export interface ProvinceComplianceStat {
  province: string;
  total_devices: number;
  evaluated_devices: number;
  compliant_devices: number;
  non_compliant_devices: number;
  compliance_pct: number;
  failed_rules_summary?: Record<string, number>;
  rules_passed?: Record<string, number>;
  rules_failed?: Record<string, number>;
  rule_breakdown?: Record<string, number>;
}

export interface DeviceComplianceItem {
  device_id: number;
  name: string;
  province: string;
  role: string;
  status: "COMPLIANT" | "NON_COMPLIANT" | "NO_SNAPSHOT" | string;
  compliance_score: number;
  passed_count: number;
  failed_count: number;
  failed_rules: string[];
  snapshot_id?: string | null;
  snapshot_taken_at?: string | null;
}

export interface ComplianceDashboardResponse {
  summary: {
    total_devices: number;
    evaluated_devices: number;
    compliant_devices: number;
    non_compliant_devices: number;
    compliance_pct?: number;
    overall_compliance_pct?: number;
  };
  rules?: ComplianceRule[];
  rules_breakdown?: ComplianceRule[];
  province_stats?: ProvinceComplianceStat[];
  province_breakdown?: ProvinceComplianceStat[];
  devices: DeviceComplianceItem[];
}

export interface VrfRouteHop {
  hop_number?: number;
  router_name: string;
  router_ip: string;
  vrf: string;
  route_target?: string;
  next_hop?: string;
  outgoing_interface?: string;
  status: "ok" | "divergent" | "blackhole" | string;
}

export interface VrfTraceResponse {
  status: string;
  target_ip: string;
  vrf: string;
  hops: VrfRouteHop[];
  nodes?: Array<{ id: string; label: string; ip?: string; status?: string }>;
  edges?: Array<{ source: string; target: string; label?: string }>;
  matching_routes?: Array<Record<string, unknown>>;
}

export interface PtpTraceResponse {
  status: string;
  target: string;
  verdict: string;
  grandmaster_id?: string;
  clock_accuracy?: string;
  offset_from_master_ns?: number;
  hops?: Array<{
    device_name: string;
    clock_role: string;
    ip: string;
    state: string;
    offset_ns?: number;
  }>;
}

export interface ArpLookupResult {
  ne_name: string;
  ip_address: string;
  mac_address: string;
  interface_name: string;
  vlan?: string | number;
  site_code?: string;
  last_seen?: string;
}

export interface AllowlistedCommand {
  name: string;
  command_template: string;
  description: string;
  platforms: string[];
  category: string;
  variables?: Array<{
    name: string;
    description: string;
    default?: string;
    required?: boolean;
  }>;
}


