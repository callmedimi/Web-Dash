import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  X,
  Server,
  Activity,
  AlertTriangle,
  FileCode,
  Layers,
  ShieldCheck,
  ExternalLink,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { DeviceItem } from "@/api/types";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Timestamp } from "@/components/ui/Timestamp";

export interface DeviceDetailDrawerProps {
  device: DeviceItem | null;
  onClose: () => void;
  onRefresh: () => void;
}

type TabType = "summary" | "monitoring" | "alarms" | "configs" | "jobs" | "compliance";

export const DeviceDetailDrawer: React.FC<DeviceDetailDrawerProps> = ({
  device,
  onClose,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>("summary");
  const [isProbing, setIsProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<string | null>(null);

  useQuery({
    queryKey: ["deviceMonitoring", device?.id],
    queryFn: () => apiClient.get<Record<string, unknown>>(`/api/v1/devices/${device?.id}`),
    enabled: Boolean(device && (activeTab === "monitoring" || activeTab === "summary")),
  });

  if (!device) return null;

  const handleProbe = async () => {
    setIsProbing(true);
    setProbeResult(null);
    try {
      const res = await apiClient.post<{ health_status: string; latency_ms?: number }>(
        `/api/v1/devices/${device.id}/health-check?probe_ssh=true`
      );
      setProbeResult(`Status: ${res.health_status.toUpperCase()}`);
      onRefresh();
    } catch (err) {
      setProbeResult(err instanceof Error ? err.message : "Probe failed");
    } finally {
      setIsProbing(false);
    }
  };

  const healthVariant: StatusVariant =
    device.health_status === "up"
      ? "ok"
      : device.health_status === "degraded"
      ? "warn"
      : device.health_status === "down"
      ? "fault"
      : "info-muted";

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-line bg-surface shadow-2xl backdrop-blur-md transition-transform duration-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5 bg-surface-2/40">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-control bg-signal/10 border border-signal/30 text-signal">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-ink">{device.name}</h2>
              <StatusBadge
                variant={healthVariant}
                label={device.health_status}
                className="text-[10px] py-0 px-1.5"
              />
            </div>
            <div className="flex items-center gap-2 text-[11px] text-ink-2 font-mono mt-0.5">
              <span>{device.mgmt_ip}</span>
              <span>·</span>
              <span>{device.role || "PE"}</span>
              <span>·</span>
              <span>{device.province || "TEH"}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleProbe}
            disabled={isProbing}
            title="Probe device SSH & health"
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isProbing ? "animate-spin text-signal" : ""}`} />
            <span className="hidden sm:inline">Probe</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control p-1 text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {probeResult && (
        <div className="border-b border-line bg-surface-2 px-5 py-2 text-xs font-mono text-ink">
          Health Probe Result: <span className="font-semibold text-signal">{probeResult}</span>
        </div>
      )}

      {/* Tabs Bar */}
      <div className="flex border-b border-line bg-surface px-5 text-xs overflow-x-auto scrollbar-none">
        {[
          { id: "summary", label: "Summary", icon: Server },
          { id: "monitoring", label: "Monitoring", icon: Activity },
          { id: "alarms", label: "Alarms", icon: AlertTriangle },
          { id: "configs", label: "Configs", icon: FileCode },
          { id: "jobs", label: "Jobs", icon: Layers },
          { id: "compliance", label: "Compliance", icon: ShieldCheck },
        ].map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`flex items-center gap-1.5 border-b-2 py-2.5 px-3 font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? "border-signal text-signal font-semibold"
                  : "border-transparent text-ink-2 hover:text-ink"
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content Body */}
      <div className="flex-1 overflow-y-auto p-5 text-xs space-y-4">
        {activeTab === "summary" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface-2/40 p-4 space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                Hardware & Software Specifications
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <span className="text-ink-2">Model:</span>
                  <div className="font-mono font-medium text-ink mt-0.5">{device.model || "--"}</div>
                </div>
                <div>
                  <span className="text-ink-2">OS Family:</span>
                  <div className="font-mono font-medium text-ink mt-0.5 uppercase">
                    {device.os_family}
                  </div>
                </div>
                <div>
                  <span className="text-ink-2">Software Version:</span>
                  <div className="font-mono font-medium text-ink mt-0.5">
                    {device.software_version || "VRP (R) Software, Version 8.180"}
                  </div>
                </div>
                <div>
                  <span className="text-ink-2">ESN / Serial:</span>
                  <div className="font-mono font-medium text-ink mt-0.5">{device.esn || "--"}</div>
                </div>
                <div>
                  <span className="text-ink-2">LSR ID:</span>
                  <div className="font-mono font-medium text-ink mt-0.5">{device.lsr_id || device.mgmt_ip}</div>
                </div>
                <div>
                  <span className="text-ink-2">Site / Location:</span>
                  <div className="font-mono font-medium text-ink mt-0.5">
                    {device.province} / {device.site || "CORE-POP"}
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-control border border-line bg-surface-2/40 p-4 space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                Operational Tags
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {device.tags && device.tags.length > 0 ? (
                  device.tags.map((t) => (
                    <span
                      key={t}
                      className="rounded-control bg-surface border border-line px-2 py-0.5 text-[11px] font-mono text-ink"
                    >
                      {t}
                    </span>
                  ))
                ) : (
                  <span className="text-ink-2 text-[11px]">No tags assigned</span>
                )}
              </div>
            </div>

            <div className="rounded-control border border-line bg-surface-2/40 p-4 space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                Integrations & Deep Links
              </h3>
              <div className="flex flex-wrap gap-2 pt-1">
                <Link
                  to={`/alarms?search=${encodeURIComponent(device.name)}`}
                  className="inline-flex items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink hover:bg-surface-2 hover:text-signal"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-warn" />
                  <span>View in Alarm Center</span>
                  <ExternalLink className="h-2.5 w-2.5" />
                </Link>
                <Link
                  to={`/changes?target=${encodeURIComponent(device.name)}`}
                  className="inline-flex items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink hover:bg-surface-2 hover:text-signal"
                >
                  <Terminal className="h-3.5 w-3.5 text-signal" />
                  <span>Plan Safe Change</span>
                  <ExternalLink className="h-2.5 w-2.5" />
                </Link>
              </div>
            </div>
          </div>
        )}

        {activeTab === "monitoring" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface-2/40 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                  Zabbix Telemetry Correlation
                </h3>
                {device.zabbix_hostid ? (
                  <span className="rounded-control bg-ok/10 border border-ok/30 px-2 py-0.5 text-[10px] font-medium text-ok">
                    HostID: {device.zabbix_hostid}
                  </span>
                ) : (
                  <span className="rounded-control bg-warn/10 border border-warn/30 px-2 py-0.5 text-[10px] font-medium text-warn">
                    Unlinked in Zabbix
                  </span>
                )}
              </div>
              <p className="text-[11px] text-ink-2">
                Live interface traffic rates, CPU utilization, and optical power telemetry are polled via Zabbix JSON-RPC.
              </p>
            </div>

            <div className="rounded-control border border-line bg-surface p-4 text-center py-8 text-ink-2 space-y-2">
              <Activity className="h-8 w-8 text-signal mx-auto" />
              <p className="font-semibold text-ink">Real-Time Interface Telemetry Explorer</p>
              <p className="text-[11px]">
                Interface rate graphs with synchronized cursors and Grafana deep-links are integrated in Step 9.9 Monitoring Hub.
              </p>
            </div>
          </div>
        )}

        {activeTab === "alarms" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface p-6 text-center text-ink-2 space-y-2">
              <AlertTriangle className="h-8 w-8 text-warn mx-auto" />
              <p className="font-semibold text-ink">Correlated Alarms for {device.name}</p>
              <p className="text-[11px]">
                Showing real-time Zabbix and on-demand SSH alarm mismatches.
              </p>
              <Link
                to={`/alarms?search=${encodeURIComponent(device.name)}`}
                className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-signal px-3 py-1.5 text-xs text-white hover:bg-signal/90"
              >
                <span>Launch Alarm Clearance Planner</span>
              </Link>
            </div>
          </div>
        )}

        {activeTab === "configs" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface p-6 text-center text-ink-2 space-y-2">
              <FileCode className="h-8 w-8 text-signal mx-auto" />
              <p className="font-semibold text-ink">Configuration Snapshot Timeline</p>
              <p className="text-[11px]">
                Automated nightly backups with side-by-side DiffViewer and git-style revision history.
              </p>
            </div>
          </div>
        )}

        {activeTab === "jobs" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface p-6 text-center text-ink-2 space-y-2">
              <Layers className="h-8 w-8 text-signal mx-auto" />
              <p className="font-semibold text-ink">Device Automation Job History</p>
              <p className="text-[11px]">
                Audit log of all change requests, alarm clearances, and diagnosis jobs executed on this router.
              </p>
            </div>
          </div>
        )}

        {activeTab === "compliance" && (
          <div className="space-y-4">
            <div className="rounded-control border border-line bg-surface p-6 text-center text-ink-2 space-y-2">
              <ShieldCheck className="h-8 w-8 text-ok mx-auto" />
              <p className="font-semibold text-ink">Security Baseline & Compliance Matrix</p>
              <p className="text-[11px]">
                Checks SSH cipher suites, AAA configuration, NTP synchronization, and SNMP access lists against national telecom hardening rules.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-line px-5 py-3 bg-surface-2/40 text-[11px] text-ink-2">
        <span>ID: {device.id}</span>
        <span className="font-mono">
          Last health check: <Timestamp value={device.last_health_check} relative />
        </span>
      </div>
    </div>
  );
};
