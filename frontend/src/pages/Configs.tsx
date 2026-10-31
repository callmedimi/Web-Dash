/**
 * Configs & Compliance Screen (`/configs`, `/compliance`).
 * Automated configuration snapshots, version timeline, side-by-side DiffViewer,
 * and province-level compliance matrix (% pass) with remediation CLI guidance.
 */
import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FileCode,
  ShieldCheck,
  RotateCw,
  GitCompare,
  Download,
  Copy,
  Check,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Layers,
  ArrowRight,
  Sliders,
  Terminal,
} from "lucide-react";
import { apiClient } from "@/api/client";
import {
  DeviceItem,
  DevicesListResponse,
  ConfigSnapshotItem,
  ConfigDiffResponse,
  ComplianceDashboardResponse,
} from "@/api/types";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DiffViewer } from "@/components/diff/DiffViewer";
import { cn } from "@/utils/cn";

export const Configs: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  // Determine active tab based on URL or local state
  const isComplianceRoute = location.pathname.includes("/compliance");
  const [activeTab, setActiveTab] = useState<"configs" | "compliance">(
    isComplianceRoute ? "compliance" : "configs"
  );

  useEffect(() => {
    if (location.pathname.includes("/compliance")) {
      setActiveTab("compliance");
    } else {
      setActiveTab("configs");
    }
  }, [location.pathname]);

  // Devices State
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [deviceSearch, setDeviceSearch] = useState("");

  // Config Snapshots State
  const [snapshots, setSnapshots] = useState<ConfigSnapshotItem[]>([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);
  const [snapshotContent, setSnapshotContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [backupSubmitting, setBackupSubmitting] = useState(false);
  const [backupJobBanner, setBackupJobBanner] = useState<string | null>(null);
  const [copiedConfig, setCopiedConfig] = useState(false);

  // Compare Mode State
  const [compareMode, setCompareMode] = useState(false);
  const [snapshotAId, setSnapshotAId] = useState<string>("");
  const [snapshotBId, setSnapshotBId] = useState<string>("");
  const [diffData, setDiffData] = useState<ConfigDiffResponse | null>(null);
  const [contentA, setContentA] = useState<string>("");
  const [contentB, setContentB] = useState<string>("");
  const [loadingDiff, setLoadingDiff] = useState(false);

  // Compliance State
  const [complianceData, setComplianceData] = useState<ComplianceDashboardResponse | null>(null);
  const [loadingCompliance, setLoadingCompliance] = useState(false);
  const [complianceProvince, setComplianceProvince] = useState<string>("ALL");
  const [selectedMatrixProvince, setSelectedMatrixProvince] = useState<string | null>(null);

  // 1. Fetch devices list for config picker
  const fetchDevices = useCallback(async () => {
    try {
      setLoadingDevices(true);
      const res = await apiClient.get<DevicesListResponse | DeviceItem[]>("/api/v1/devices");
      const list = Array.isArray(res) ? res : res.devices || [];
      setDevices(list);
      if (list.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(list[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch devices:", err);
    } finally {
      setLoadingDevices(false);
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  // Selected Device object
  const currentDevice = useMemo(() => {
    return devices.find((d) => d.id === selectedDeviceId) || null;
  }, [devices, selectedDeviceId]);

  // Filtered devices for picker
  const filteredDevices = useMemo(() => {
    if (!deviceSearch.trim()) return devices;
    const q = deviceSearch.toLowerCase();
    return devices.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.mgmt_ip.toLowerCase().includes(q) ||
        (d.province && d.province.toLowerCase().includes(q))
    );
  }, [devices, deviceSearch]);

  // 2. Fetch Snapshots for selected device
  const fetchSnapshots = useCallback(async (devId: number) => {
    try {
      setLoadingSnapshots(true);
      setSnapshots([]);
      setSelectedSnapshotId(null);
      setSnapshotContent(null);
      setDiffData(null);

      const list = await apiClient.get<ConfigSnapshotItem[]>(`/api/v1/devices/${devId}/configs`);
      setSnapshots(list || []);

      if (list && list.length > 0) {
        setSelectedSnapshotId(list[0].id);
        if (list.length >= 2) {
          setSnapshotAId(list[1].id);
          setSnapshotBId(list[0].id);
        } else {
          setSnapshotAId(list[0].id);
          setSnapshotBId(list[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch snapshots:", err);
    } finally {
      setLoadingSnapshots(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDeviceId) {
      fetchSnapshots(selectedDeviceId);
    }
  }, [selectedDeviceId, fetchSnapshots]);

  // 3. Fetch single snapshot decrypted content
  const fetchSnapshotContent = useCallback(async (devId: number, snapId: string) => {
    try {
      setLoadingContent(true);
      const res = await apiClient.get<ConfigSnapshotItem>(`/api/v1/devices/${devId}/configs/${snapId}`);
      setSnapshotContent(res.content || "");
    } catch (err) {
      console.error("Failed to fetch snapshot content:", err);
      setSnapshotContent("# Error loading decrypted configuration");
    } finally {
      setLoadingContent(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDeviceId && selectedSnapshotId && !compareMode) {
      fetchSnapshotContent(selectedDeviceId, selectedSnapshotId);
    }
  }, [selectedDeviceId, selectedSnapshotId, compareMode, fetchSnapshotContent]);

  // 4. Fetch Diff between Snapshot A and B
  const fetchDiff = useCallback(async (devId: number, fromId: string, toId: string) => {
    if (!fromId || !toId) return;
    try {
      setLoadingDiff(true);
      const [diffRes, snapA, snapB] = await Promise.all([
        apiClient.get<ConfigDiffResponse>(`/api/v1/devices/${devId}/configs/diff?from=${fromId}&to=${toId}`),
        apiClient.get<ConfigSnapshotItem>(`/api/v1/devices/${devId}/configs/${fromId}`),
        apiClient.get<ConfigSnapshotItem>(`/api/v1/devices/${devId}/configs/${toId}`),
      ]);
      setDiffData(diffRes);
      setContentA(snapA.content || "");
      setContentB(snapB.content || "");
    } catch (err) {
      console.error("Failed to load diff:", err);
    } finally {
      setLoadingDiff(false);
    }
  }, []);

  useEffect(() => {
    if (compareMode && selectedDeviceId && snapshotAId && snapshotBId) {
      fetchDiff(selectedDeviceId, snapshotAId, snapshotBId);
    }
  }, [compareMode, selectedDeviceId, snapshotAId, snapshotBId, fetchDiff]);

  // Trigger Backup Now
  const handleTriggerBackup = async () => {
    if (!selectedDeviceId) return;
    try {
      setBackupSubmitting(true);
      setBackupJobBanner(null);
      const res = await apiClient.post<{ status: string; job_id: string }>(
        `/api/v1/devices/${selectedDeviceId}/configs/backup`,
        { kind: "running" }
      );
      setBackupJobBanner(t("configs.backupQueued", { id: res.job_id || "NEW" }));
      setTimeout(() => {
        fetchSnapshots(selectedDeviceId);
      }, 2000);
    } catch (err) {
      console.error("Failed to submit backup job:", err);
    } finally {
      setBackupSubmitting(false);
    }
  };

  // Copy Config
  const handleCopyConfig = () => {
    if (!snapshotContent) return;
    navigator.clipboard.writeText(snapshotContent);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  };

  // Download Config File
  const handleDownloadConfig = (snapId: string) => {
    if (!selectedDeviceId) return;
    window.open(`/api/v1/devices/${selectedDeviceId}/configs/${snapId}/download`, "_blank");
  };

  // 5. Fetch Fleet Compliance
  const fetchCompliance = useCallback(async (province?: string) => {
    try {
      setLoadingCompliance(true);
      const qs = province && province !== "ALL" ? `?province=${province}` : "";
      const data = await apiClient.get<ComplianceDashboardResponse>(`/api/v1/compliance/dashboard${qs}`);
      setComplianceData(data);
    } catch (err) {
      console.error("Failed to fetch compliance dashboard:", err);
    } finally {
      setLoadingCompliance(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "compliance") {
      fetchCompliance(complianceProvince);
    }
  }, [activeTab, complianceProvince, fetchCompliance]);

  // Compliance rules list and province list accessors
  const activeRules = useMemo(() => {
    return complianceData?.rules_breakdown || complianceData?.rules || [];
  }, [complianceData]);

  const activeProvinces = useMemo(() => {
    return complianceData?.province_breakdown || complianceData?.province_stats || [];
  }, [complianceData]);

  // Compliance rules lookup
  const rulesMap = useMemo(() => {
    const map: Record<string, { name: string; severity: string; remediation_hint: string }> = {};
    for (const r of activeRules) {
      const rid = r.rule_id || r.id || "";
      if (rid) {
        map[rid] = {
          name: r.name,
          severity: r.severity,
          remediation_hint: r.remediation_hint,
        };
      }
    }
    return map;
  }, [activeRules]);

  // Filtered Violations / Failing Devices
  const failingDevices = useMemo(() => {
    if (!complianceData?.devices) return [];
    return complianceData.devices.filter((d) => {
      if (d.status === "COMPLIANT") return false;
      if (selectedMatrixProvince && d.province !== selectedMatrixProvince) return false;
      return true;
    });
  }, [complianceData, selectedMatrixProvince]);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg text-ink">
      {/* Header with Title and Mode Tabs */}
      <div className="flex flex-shrink-0 flex-wrap items-center justify-between border-b border-line bg-surface px-4 py-3 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold tracking-tight text-ink">
              {t("configs.title")}
            </h1>
            <span className="rounded-full bg-signal/10 px-2 py-0.5 text-[11px] font-mono font-medium text-signal">
              Step 9.10
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-2">
            {t("configs.subtitle")}
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-1.5 rounded-control border border-line bg-surface-2 p-1 text-xs">
          <button
            type="button"
            onClick={() => {
              setActiveTab("configs");
              navigate("/configs");
            }}
            className={cn(
              "flex items-center gap-1.5 rounded px-3 py-1 font-medium transition-colors",
              activeTab === "configs"
                ? "bg-surface text-ink shadow-sm font-semibold"
                : "text-ink-2 hover:text-ink"
            )}
          >
            <FileCode className="h-3.5 w-3.5" />
            <span>{t("configs.tabConfigs")}</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveTab("compliance");
              navigate("/compliance");
            }}
            className={cn(
              "flex items-center gap-1.5 rounded px-3 py-1 font-medium transition-colors",
              activeTab === "compliance"
                ? "bg-surface text-ink shadow-sm font-semibold"
                : "text-ink-2 hover:text-ink"
            )}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>{t("configs.tabCompliance")}</span>
          </button>
        </div>
      </div>

      {/* Backup Queued Banner */}
      {backupJobBanner && (
        <div className="flex items-center justify-between border-b border-signal/30 bg-signal/10 px-4 py-2 text-xs text-signal">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{backupJobBanner}</span>
          </div>
          <button
            type="button"
            onClick={() => setBackupJobBanner(null)}
            className="text-xs hover:underline"
          >
            &times;
          </button>
        </div>
      )}

      {/* TAB 1: Config Backups & Diff */}
      {activeTab === "configs" && (
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Router Picker & Snapshot Timeline */}
          <div className="w-80 flex-shrink-0 flex flex-col border-r border-line bg-surface/50">
            {/* Device Search Box */}
            <div className="p-3 border-b border-line">
              <label className="text-[11px] font-medium uppercase tracking-wider text-ink-2 mb-1.5 block">
                {t("configs.selectDevice")}
              </label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-ink-2" />
                <input
                  type="text"
                  placeholder={t("devices.searchPlaceholder", "Filter router...")}
                  value={deviceSearch}
                  onChange={(e) => setDeviceSearch(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface py-1.5 pl-8 pr-3 text-xs text-ink placeholder:text-ink-2 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
                />
              </div>
            </div>

            {/* Devices List */}
            <div className="flex-1 overflow-y-auto divide-y divide-line/40">
              {loadingDevices ? (
                <div className="p-4 text-center text-xs text-ink-2">Loading routers...</div>
              ) : filteredDevices.length === 0 ? (
                <div className="p-4 text-center text-xs text-ink-2">No routers found</div>
              ) : (
                filteredDevices.map((dev) => {
                  const isSelected = dev.id === selectedDeviceId;
                  return (
                    <button
                      key={dev.id}
                      type="button"
                      onClick={() => setSelectedDeviceId(dev.id)}
                      className={cn(
                        "w-full text-left px-3 py-2.5 transition-colors flex items-center justify-between",
                        isSelected
                          ? "bg-signal/10 border-l-2 border-signal font-medium text-ink"
                          : "hover:bg-surface-2/60 text-ink-2"
                      )}
                    >
                      <div className="truncate pr-2">
                        <div className="text-xs font-semibold text-ink truncate">{dev.name}</div>
                        <div className="text-[10px] text-ink-2 font-mono flex items-center gap-1.5 mt-0.5">
                          <span>{dev.mgmt_ip}</span>
                          <span>•</span>
                          <span>{dev.province || "N/A"}</span>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface border border-line text-ink-2">
                        {dev.role || "PE"}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Main Pane: Controls, Timeline & DiffViewer */}
          <div className="flex-1 flex flex-col overflow-hidden bg-bg">
            {/* Router Action Header */}
            {currentDevice ? (
              <div className="flex flex-shrink-0 items-center justify-between border-b border-line bg-surface px-4 py-2.5 gap-3">
                <div className="flex items-center gap-3">
                  <div>
                    <span className="text-sm font-semibold text-ink">{currentDevice.name}</span>
                    <span className="ml-2 font-mono text-xs text-ink-2">({currentDevice.mgmt_ip})</span>
                  </div>
                  <span className="rounded bg-surface-2 px-2 py-0.5 text-[11px] font-mono text-ink-2 border border-line">
                    {currentDevice.vendor?.toUpperCase()} {currentDevice.os_family?.toUpperCase()}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {/* Compare Mode Toggle */}
                  <button
                    type="button"
                    onClick={() => setCompareMode(!compareMode)}
                    disabled={snapshots.length < 2}
                    className={cn(
                      "flex items-center gap-1.5 rounded-control border px-2.5 py-1 text-xs font-medium transition-colors",
                      compareMode
                        ? "border-signal bg-signal/10 text-signal font-semibold"
                        : "border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-40"
                    )}
                  >
                    <GitCompare className="h-3.5 w-3.5" />
                    <span>{t("configs.compareMode")}</span>
                  </button>

                  {/* Trigger Backup Button */}
                  <button
                    type="button"
                    onClick={handleTriggerBackup}
                    disabled={backupSubmitting}
                    className="flex items-center gap-1.5 rounded-control bg-signal px-3 py-1 text-xs font-semibold text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    <RotateCw className={cn("h-3.5 w-3.5", backupSubmitting && "animate-spin")} />
                    <span>{t("configs.triggerBackup")}</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-4 text-center text-xs text-ink-2">Please select a router</div>
            )}

            {/* Compare Selectors Bar (Shown when compareMode is active) */}
            {compareMode && (
              <div className="flex items-center gap-3 border-b border-line bg-surface-2/60 px-4 py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-ink-2">{t("configs.snapshotA")}:</span>
                  <select
                    value={snapshotAId}
                    onChange={(e) => setSnapshotAId(e.target.value)}
                    className="rounded border border-line bg-surface px-2 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none"
                  >
                    {snapshots.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.taken_at ? new Date(s.taken_at).toLocaleString() : s.id} ({s.kind})
                      </option>
                    ))}
                  </select>
                </div>

                <ArrowRight className="h-4 w-4 text-ink-2" />

                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-ink-2">{t("configs.snapshotB")}:</span>
                  <select
                    value={snapshotBId}
                    onChange={(e) => setSnapshotBId(e.target.value)}
                    className="rounded border border-line bg-surface px-2 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none"
                  >
                    {snapshots.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.taken_at ? new Date(s.taken_at).toLocaleString() : s.id} ({s.kind})
                      </option>
                    ))}
                  </select>
                </div>

                {diffData && (
                  <div className="ml-auto flex items-center gap-2 font-mono text-[11px]">
                    <span className="text-ok font-semibold">
                      +{diffData.additions ?? diffData.stats?.additions ?? 0}
                    </span>
                    <span className="text-fault font-semibold">
                      -{diffData.deletions ?? diffData.stats?.deletions ?? 0}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex flex-col">
              {loadingSnapshots ? (
                <div className="flex-1 flex items-center justify-center text-xs text-ink-2">
                  <RotateCw className="h-5 w-5 animate-spin mr-2" />
                  Loading configuration history...
                </div>
              ) : snapshots.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                  <FileCode className="h-10 w-10 text-ink-2/40 mb-3" />
                  <p className="text-sm font-medium text-ink">{t("configs.noSnapshots")}</p>
                </div>
              ) : compareMode ? (
                /* DIFF VIEWER CONTAINER */
                <div className="flex-1 overflow-y-auto p-4">
                  {loadingDiff ? (
                    <div className="flex items-center justify-center h-48 text-xs text-ink-2">
                      <RotateCw className="h-5 w-5 animate-spin mr-2" />
                      Computing unified diff...
                    </div>
                  ) : (
                    <DiffViewer
                      oldContent={contentA}
                      newContent={contentB}
                      oldLabel={`Snapshot A: ${snapshotAId}`}
                      newLabel={`Snapshot B: ${snapshotBId}`}
                      title={t("configs.diffTitle")}
                    />
                  )}
                </div>
              ) : (
                /* SINGLE SNAPSHOT VIEW: Timeline Bar + Raw Decrypted Viewer */
                <div className="flex-1 flex flex-col overflow-hidden">
                  {/* Timeline Pills */}
                  <div className="flex items-center gap-2 overflow-x-auto border-b border-line bg-surface/30 px-4 py-2 flex-shrink-0">
                    <span className="text-[11px] font-medium text-ink-2 flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" />
                      {t("configs.snapshotTimeline")}:
                    </span>
                    {snapshots.map((s, idx) => {
                      const isSelected = s.id === selectedSnapshotId;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => setSelectedSnapshotId(s.id)}
                          className={cn(
                            "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-mono transition-colors whitespace-nowrap",
                            isSelected
                              ? "bg-signal text-bg font-semibold"
                              : "border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"
                          )}
                        >
                          <span>{s.taken_at ? new Date(s.taken_at).toLocaleDateString() : `#${idx + 1}`}</span>
                          <span className="text-[10px] opacity-75">({s.kind})</span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Active Snapshot Metadata Strip & Actions */}
                  {selectedSnapshotId && (
                    <div className="flex items-center justify-between border-b border-line bg-surface-2/40 px-4 py-2 text-xs flex-shrink-0">
                      <div className="flex items-center gap-4 text-ink-2 font-mono text-[11px]">
                        <span>
                          <strong className="text-ink">SHA-256:</strong>{" "}
                          {snapshots.find((s) => s.id === selectedSnapshotId)?.sha256?.substring(0, 16)}...
                        </span>
                        <span>
                          <strong className="text-ink">Size:</strong>{" "}
                          {snapshots.find((s) => s.id === selectedSnapshotId)?.size_bytes} B
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleCopyConfig}
                          className="flex items-center gap-1 rounded border border-line bg-surface px-2.5 py-1 text-xs text-ink hover:bg-surface-2 transition-colors"
                        >
                          {copiedConfig ? (
                            <>
                              <Check className="h-3.5 w-3.5 text-ok" />
                              <span className="text-ok font-medium">{t("configs.copied")}</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3.5 w-3.5" />
                              <span>{t("configs.copy")}</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          onClick={() => handleDownloadConfig(selectedSnapshotId)}
                          className="flex items-center gap-1 rounded border border-line bg-surface px-2.5 py-1 text-xs text-ink hover:bg-surface-2 transition-colors"
                        >
                          <Download className="h-3.5 w-3.5" />
                          <span>{t("configs.download")}</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Decrypted Raw Configuration Viewer */}
                  <div className="flex-1 overflow-y-auto p-4 bg-surface/20">
                    {loadingContent ? (
                      <div className="flex items-center justify-center h-48 text-xs text-ink-2">
                        <RotateCw className="h-5 w-5 animate-spin mr-2" />
                        Decrypting configuration snapshot...
                      </div>
                    ) : (
                      <pre className="font-mono text-xs leading-relaxed text-ink bg-surface border border-line p-4 rounded-control overflow-x-auto shadow-sm">
                        {snapshotContent || "# Empty configuration"}
                      </pre>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Fleet Policy Compliance */}
      {activeTab === "compliance" && (
        <div className="flex-1 flex flex-col overflow-y-auto p-4 space-y-4">
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-2">
                  {t("compliance.overallScore")}
                </span>
                <div className="text-2xl font-bold font-mono text-signal mt-1">
                  {complianceData?.summary.overall_compliance_pct ?? complianceData?.summary.compliance_pct ?? 100}%
                </div>
              </div>
              <ShieldCheck className="h-8 w-8 text-signal/30" />
            </div>

            <div className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-2">
                  {t("compliance.compliantCount")}
                </span>
                <div className="text-2xl font-bold font-mono text-ok mt-1">
                  {complianceData?.summary.compliant_devices ?? 0}
                </div>
              </div>
              <CheckCircle2 className="h-8 w-8 text-ok/30" />
            </div>

            <div className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-2">
                  {t("compliance.nonCompliantCount")}
                </span>
                <div className="text-2xl font-bold font-mono text-fault mt-1">
                  {complianceData?.summary.non_compliant_devices ?? 0}
                </div>
              </div>
              <AlertTriangle className="h-8 w-8 text-fault/30" />
            </div>

            <div className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-2">
                  {t("compliance.totalEvaluated")}
                </span>
                <div className="text-2xl font-bold font-mono text-ink mt-1">
                  {complianceData?.summary.evaluated_devices ?? 0}
                </div>
              </div>
              <Layers className="h-8 w-8 text-ink-2/30" />
            </div>
          </div>

          {/* Provincial Compliance Matrix (% Pass) */}
          <div className="rounded-control border border-line bg-surface p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-signal" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {t("compliance.matrixTitle")}
                </h2>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={complianceProvince}
                  onChange={(e) => setComplianceProvince(e.target.value)}
                  className="rounded border border-line bg-surface px-2.5 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none"
                >
                  <option value="ALL">{t("compliance.allProvinces")}</option>
                  <option value="TEH">TEH (Tehran)</option>
                  <option value="FRS">FRS (Fars)</option>
                  <option value="ISF">ISF (Isfahan)</option>
                  <option value="KRD">KRD (Kurdistan)</option>
                  <option value="KHZ">KHZ (Khuzestan)</option>
                  <option value="KRN">KRN (Kermanshah)</option>
                </select>
                {selectedMatrixProvince && (
                  <button
                    type="button"
                    onClick={() => setSelectedMatrixProvince(null)}
                    className="text-xs text-signal hover:underline"
                  >
                    Clear ({selectedMatrixProvince})
                  </button>
                )}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-line bg-surface-2 text-ink-2">
                    <th className="py-2 px-3 font-semibold">Province</th>
                    <th className="py-2 px-3 font-semibold font-mono">Evaluated</th>
                    <th className="py-2 px-3 font-semibold font-mono">Compliant</th>
                    {activeRules.map((rule) => {
                      const rid = rule.rule_id || rule.id || "";
                      return (
                        <th key={rid} className="py-2 px-3 font-semibold font-mono truncate max-w-[140px]" title={rule.name}>
                          {rid}
                        </th>
                      );
                    })}
                    <th className="py-2 px-3 font-semibold font-mono text-right">Pass %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40">
                  {loadingCompliance ? (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-ink-2">
                        Evaluating compliance matrix...
                      </td>
                    </tr>
                  ) : activeProvinces.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-ink-2">
                        No provincial compliance data available.
                      </td>
                    </tr>
                  ) : (
                    activeProvinces.map((prov) => {
                      const isSelected = selectedMatrixProvince === prov.province;
                      return (
                        <tr
                          key={prov.province}
                          onClick={() =>
                            setSelectedMatrixProvince(
                              isSelected ? null : prov.province
                            )
                          }
                          className={cn(
                            "cursor-pointer transition-colors hover:bg-surface-2/60",
                            isSelected && "bg-signal/10 font-medium"
                          )}
                        >
                          <td className="py-2.5 px-3 font-semibold text-ink flex items-center gap-1.5">
                            <span>{prov.province}</span>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-ink-2">{prov.evaluated_devices}</td>
                          <td className="py-2.5 px-3 font-mono text-ok">{prov.compliant_devices}</td>
                          {activeRules.map((rule) => {
                            const rid = rule.rule_id || rule.id || "";
                            const directPct = prov.rule_breakdown?.[rid];
                            const passed = prov.rules_passed?.[rid] ?? 0;
                            const failed = prov.failed_rules_summary?.[rid] ?? 0;
                            const total = passed + failed;
                            const pct = directPct !== undefined
                              ? Math.round(directPct)
                              : total > 0
                              ? Math.round((passed / total) * 100)
                              : 100;
                            return (
                              <td key={rid} className="py-2.5 px-3 font-mono">
                                <span
                                  className={cn(
                                    "px-1.5 py-0.5 rounded text-[11px] font-semibold",
                                    pct === 100
                                      ? "bg-ok/10 text-ok"
                                      : pct >= 80
                                      ? "bg-warn/10 text-warn"
                                      : "bg-fault/10 text-fault"
                                  )}
                                >
                                  {pct}%
                                </span>
                              </td>
                            );
                          })}
                          <td className="py-2.5 px-3 font-mono text-right">
                            <span
                              className={cn(
                                "font-bold",
                                prov.compliance_pct === 100
                                  ? "text-ok"
                                  : prov.compliance_pct >= 80
                                  ? "text-warn"
                                  : "text-fault"
                              )}
                            >
                              {prov.compliance_pct}%
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Failing Devices & Remediation Guidance */}
          <div className="rounded-control border border-line bg-surface p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-fault" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {t("compliance.violationsTitle")}
                </h2>
              </div>
              <span className="text-xs font-mono text-ink-2">
                {failingDevices.length} violating router(s)
              </span>
            </div>

            {failingDevices.length === 0 ? (
              <div className="p-6 text-center text-xs text-ok flex items-center justify-center gap-2">
                <CheckCircle2 className="h-4 w-4" />
                <span>{t("compliance.noViolations")}</span>
              </div>
            ) : (
              <div className="divide-y divide-line/40">
                {failingDevices.map((dev) => (
                  <div key={dev.device_id} className="py-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-ink">{dev.name}</span>
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 border border-line text-ink-2">
                          {dev.province}
                        </span>
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 border border-line text-ink-2">
                          {dev.role}
                        </span>
                        <StatusBadge variant="fault" label={`${dev.compliance_score}% score`} />
                      </div>

                      {/* Violated Rules List with Remediation CLI */}
                      <div className="mt-2 space-y-1.5">
                        {dev.failed_rules.map((rid) => {
                          const ruleInfo = rulesMap[rid];
                          return (
                            <div
                              key={rid}
                              className="rounded border border-fault/30 bg-fault/5 p-2 text-xs text-ink flex flex-col gap-1"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-fault flex items-center gap-1.5">
                                  <XCircle className="h-3.5 w-3.5" />
                                  [{rid}] {ruleInfo?.name || rid}
                                </span>
                                <span className="text-[10px] uppercase font-mono px-1 rounded bg-fault/10 text-fault font-semibold">
                                  {ruleInfo?.severity || "high"}
                                </span>
                              </div>
                              {ruleInfo?.remediation_hint && (
                                <div className="mt-1 font-mono text-[11px] bg-surface p-1.5 rounded border border-line text-ink flex items-center gap-2">
                                  <Terminal className="h-3.5 w-3.5 text-signal flex-shrink-0" />
                                  <span className="truncate">{ruleInfo.remediation_hint}</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Action: Plan Remediation */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        type="button"
                        onClick={() => navigate(`/changes?device=${dev.name}`)}
                        className="flex items-center gap-1 rounded bg-signal px-2.5 py-1 text-xs font-semibold text-bg hover:opacity-90 transition-opacity"
                      >
                        <span>{t("compliance.planRemediation")}</span>
                        <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
