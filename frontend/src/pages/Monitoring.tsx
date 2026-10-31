/**
 * Monitoring Hub Screen (`/monitoring`).
 * Enterprise telemetry center: Fleet availability table, Interface rate explorer,
 * Grafana deep-links, and Telemetry Doctor integration status strip.
 */
import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  Server,
  Network,
  RotateCw,
  ExternalLink,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Radio,
  Copy,
  Check,
  Cpu,
  Layers,
  Thermometer,
  ShieldCheck,
} from "lucide-react";
import { apiClient } from "@/api/client";
import {
  FleetHealthResponse,
  TelemetryDoctorResponse,
  DeviceMonitoringResponse,
  MonitoringDeviceRow,
} from "@/api/types";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { cn } from "@/utils/cn";

export const Monitoring: React.FC = () => {
  const { t } = useTranslation();

  // Active Tab
  const [activeTab, setActiveTab] = useState<"fleet" | "interfaces" | "doctor">("fleet");

  // Fleet Health State
  const [fleetData, setFleetData] = useState<FleetHealthResponse | null>(null);
  const [loadingFleet, setLoadingFleet] = useState(true);
  const [isStale, setIsStale] = useState(false);

  // Filters
  const [filterProvince, setFilterProvince] = useState<string>("ALL");
  const [filterRole, setFilterRole] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Doctor State
  const [doctor, setDoctor] = useState<TelemetryDoctorResponse | null>(null);
  const [loadingDoctor, setLoadingDoctor] = useState(false);

  // Interface Explorer State
  const [selectedDeviceName, setSelectedDeviceName] = useState<string>("");
  const [deviceMonitoring, setDeviceMonitoring] = useState<DeviceMonitoringResponse | null>(null);
  const [loadingDeviceMon, setLoadingDeviceMon] = useState(false);
  const [interfaceSearch, setInterfaceSearch] = useState("");

  // Webhook copy state
  const [copiedWebhook, setCopiedWebhook] = useState(false);

  // Fetch Doctor & Integration Status
  const fetchDoctor = useCallback(async () => {
    try {
      setLoadingDoctor(true);
      const res = await apiClient.get<TelemetryDoctorResponse>("/api/v1/telemetry/doctor");
      setDoctor(res);
      if (res.zabbix.status !== "ok" || res.doctor_verdict === "DEGRADED") {
        setIsStale(true);
      } else {
        setIsStale(false);
      }
    } catch (err: unknown) {
      console.error("Doctor error:", err);
      setIsStale(true);
    } finally {
      setLoadingDoctor(false);
    }
  }, []);

  // Fetch Fleet Health
  const fetchFleetHealth = useCallback(async () => {
    try {
      setLoadingFleet(true);
      const qs = new URLSearchParams();
      if (filterProvince !== "ALL") qs.set("province", filterProvince);
      if (filterRole !== "ALL") qs.set("role", filterRole);

      const res = await apiClient.get<FleetHealthResponse>(
        `/api/v1/telemetry/fleet-health?${qs.toString()}`
      );
      setFleetData(res);

      // Auto-select first device if not selected
      if (!selectedDeviceName && res.devices && res.devices.length > 0) {
        setSelectedDeviceName(res.devices[0].name);
      }
    } catch (err: unknown) {
      console.error("Failed to load fleet health:", err);
      setIsStale(true);
    } finally {
      setLoadingFleet(false);
    }
  }, [filterProvince, filterRole, selectedDeviceName]);

  useEffect(() => {
    fetchDoctor();
    fetchFleetHealth();
  }, [fetchDoctor, fetchFleetHealth]);

  // Fetch Per-Device Monitoring Data
  const fetchDeviceMonitoring = useCallback(async (devName: string) => {
    if (!devName) return;
    try {
      setLoadingDeviceMon(true);
      const res = await apiClient.get<DeviceMonitoringResponse>(
        `/api/v1/telemetry/device/${encodeURIComponent(devName)}`
      );
      setDeviceMonitoring(res);
    } catch (err: unknown) {
      console.error("Failed to fetch device monitoring:", err);
      setDeviceMonitoring(null);
    } finally {
      setLoadingDeviceMon(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "interfaces" && selectedDeviceName) {
      fetchDeviceMonitoring(selectedDeviceName);
    }
  }, [activeTab, selectedDeviceName, fetchDeviceMonitoring]);

  // Filtered Devices
  const filteredDevices = useMemo(() => {
    if (!fleetData?.devices) return [];
    let rows = fleetData.devices;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      rows = rows.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          d.mgmt_ip.includes(q) ||
          d.province.toLowerCase().includes(q) ||
          (d.site && d.site.toLowerCase().includes(q))
      );
    }
    return rows;
  }, [fleetData, searchQuery]);

  // Filtered Interfaces for Explorer
  const filteredInterfaces = useMemo(() => {
    if (!deviceMonitoring?.interfaces) return [];
    if (!interfaceSearch.trim()) return deviceMonitoring.interfaces;
    const q = interfaceSearch.toLowerCase();
    return deviceMonitoring.interfaces.filter((i) => i.name.toLowerCase().includes(q));
  }, [deviceMonitoring, interfaceSearch]);

  // Helper rate formatter
  const formatRate = (bps?: number): string => {
    if (bps === undefined || bps === null) return "--";
    if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(2)} Gbps`;
    if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(2)} Mbps`;
    if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} Kbps`;
    return `${bps} bps`;
  };

  const getStatusVariant = (st: string): StatusVariant => {
    switch ((st || "").toUpperCase()) {
      case "HEALTHY":
        return "ok";
      case "WARNING":
        return "warn";
      case "CRITICAL":
      case "UNAVAILABLE":
        return "fault";
      case "UNMONITORED":
      default:
        return "info-muted";
    }
  };

  const webhookUrl = `${window.location.origin}/api/v1/telemetry/webhook`;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4 sm:p-6 overflow-hidden gap-4">
      {/* Stale Cache Banner when Zabbix is degraded */}
      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between text-xs text-amber-300 shrink-0">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
            <span>{t("monitoring.staleBanner")}</span>
          </div>
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono font-bold">
            STALE
          </span>
        </div>
      )}

      {/* Top Header & Integration Strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-[var(--border)] shrink-0">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--fg)] flex items-center gap-2">
            <Activity className="w-6 h-6 text-[var(--accent)]" />
            {t("monitoring.title")}
          </h1>
          <p className="text-xs sm:text-sm text-[var(--muted)] mt-0.5">{t("monitoring.subtitle")}</p>
        </div>

        {/* Integration Badges Strip */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {doctor && (
            <>
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md">
                <span className="text-[var(--muted)]">{t("monitoring.zabbixStatus")}:</span>
                <span
                  className={cn(
                    "font-semibold",
                    doctor.zabbix.status === "ok" ? "text-emerald-400" : "text-amber-400"
                  )}
                >
                  {doctor.zabbix?.status?.toUpperCase() || "OK"} ({doctor.zabbix?.version || "v5.0"})
                </span>
              </div>

              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md">
                <span className="text-[var(--muted)]">{t("monitoring.grafanaStatus")}:</span>
                <span
                  className={cn(
                    "font-semibold",
                    doctor.grafana?.status === "ok" ? "text-emerald-400" : "text-amber-400"
                  )}
                >
                  {doctor.grafana?.status?.toUpperCase() || "OK"}
                </span>
              </div>

              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md">
                <span className="text-[var(--muted)]">{t("monitoring.mappingCoverage")}:</span>
                <span className="font-semibold text-[var(--accent)] font-mono">
                  {doctor.coverage.coverage_pct}%
                </span>
              </div>
            </>
          )}

          <button
            onClick={() => {
              fetchDoctor();
              fetchFleetHealth();
            }}
            disabled={loadingFleet || loadingDoctor}
            className="inline-flex items-center gap-1 px-3 py-1 bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)] rounded-md transition text-xs font-medium"
          >
            <RotateCw className={cn("w-3.5 h-3.5", loadingFleet && "animate-spin")} />
            <span>{t("common.refresh")}</span>
          </button>
        </div>
      </div>

      {/* Sub-Tabs: Fleet | Interfaces | Doctor */}
      <div className="flex items-center gap-1.5 p-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded-lg w-fit shrink-0">
        <button
          onClick={() => setActiveTab("fleet")}
          className={cn(
            "px-3.5 py-1.5 text-xs font-semibold rounded-md transition flex items-center gap-1.5",
            activeTab === "fleet"
              ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
              : "text-[var(--muted)] hover:text-[var(--fg)]"
          )}
        >
          <Server className="w-3.5 h-3.5" />
          <span>{t("monitoring.tabFleet")}</span>
        </button>

        <button
          onClick={() => setActiveTab("interfaces")}
          className={cn(
            "px-3.5 py-1.5 text-xs font-semibold rounded-md transition flex items-center gap-1.5",
            activeTab === "interfaces"
              ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
              : "text-[var(--muted)] hover:text-[var(--fg)]"
          )}
        >
          <Network className="w-3.5 h-3.5" />
          <span>{t("monitoring.tabInterfaces")}</span>
        </button>

        <button
          onClick={() => setActiveTab("doctor")}
          className={cn(
            "px-3.5 py-1.5 text-xs font-semibold rounded-md transition flex items-center gap-1.5",
            activeTab === "doctor"
              ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
              : "text-[var(--muted)] hover:text-[var(--fg)]"
          )}
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>{t("monitoring.tabDoctor")}</span>
        </button>
      </div>

      {/* Main Tab Panels */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {/* Tab 1: Fleet Availability & Health */}
        {activeTab === "fleet" && (
          <div className="flex flex-col h-full gap-4 overflow-hidden">
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <span className="text-xs text-[var(--muted)]">{t("monitoring.availability")}</span>
                <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                  {fleetData?.summary.availability_pct ?? 0}%
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <span className="text-xs text-[var(--muted)]">{t("monitoring.totalDevices")}</span>
                <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                  {fleetData?.summary.monitored_devices ?? 0} / {fleetData?.summary.total_devices ?? 0}
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <span className="text-xs text-[var(--muted)]">{t("monitoring.activeProblems")}</span>
                <div className="text-xl font-bold font-mono text-red-400 mt-1">
                  {fleetData?.summary.total_active_problems ?? 0}
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <span className="text-xs text-[var(--muted)]">Telemetry Doctor</span>
                <div
                  className={cn(
                    "text-xl font-bold font-mono mt-1",
                    doctor?.doctor_verdict === "HEALTHY" ? "text-emerald-400" : "text-amber-400"
                  )}
                >
                  {doctor?.doctor_verdict ?? "HEALTHY"}
                </div>
              </div>
            </div>

            {/* Fleet Table Card */}
            <div className="flex-1 min-h-0 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-col overflow-hidden">
              {/* Filter Toolbar */}
              <div className="p-3 bg-[var(--surface-sunken)] border-b border-[var(--border)] flex flex-wrap items-center justify-between gap-3 shrink-0">
                <div className="relative w-64">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[var(--muted)]" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search router, IP, site..."
                    className="w-full text-xs pl-8 pr-3 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={filterProvince}
                    onChange={(e) => setFilterProvince(e.target.value)}
                    className="text-xs px-2.5 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)]"
                  >
                    <option value="ALL">All Provinces</option>
                    <option value="TEH">TEH (Tehran)</option>
                    <option value="ISF">ISF (Isfahan)</option>
                    <option value="FRS">FRS (Fars)</option>
                    <option value="KHO">KHO (Khorasan)</option>
                  </select>

                  <select
                    value={filterRole}
                    onChange={(e) => setFilterRole(e.target.value)}
                    className="text-xs px-2.5 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)]"
                  >
                    <option value="ALL">All Roles</option>
                    <option value="PE">PE (Provider Edge)</option>
                    <option value="P">P (Core)</option>
                    <option value="AGG">AGG (Aggregation)</option>
                  </select>
                </div>
              </div>

              {/* Table Data */}
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted)] font-medium sticky top-0 z-10">
                    <tr>
                      <th className="p-3">Device Name</th>
                      <th className="p-3">Management IP</th>
                      <th className="p-3">Province</th>
                      <th className="p-3">Role</th>
                      <th className="p-3">Zabbix Host ID</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Active Problems</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {loadingFleet && !fleetData ? (
                      <tr>
                        <td colSpan={8} className="p-8 text-center text-[var(--muted)]">
                          <RotateCw className="w-4 h-4 animate-spin mx-auto text-[var(--accent)]" />
                        </td>
                      </tr>
                    ) : filteredDevices.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="p-8 text-center text-[var(--muted)]">
                          No routers matching current filters.
                        </td>
                      </tr>
                    ) : (
                      filteredDevices.map((dev: MonitoringDeviceRow) => (
                        <tr key={dev.id} className="hover:bg-[var(--surface-hover)] transition">
                          <td className="p-3 font-mono font-semibold text-[var(--fg)]">
                            {dev.name}
                          </td>
                          <td className="p-3 font-mono text-[var(--muted)]">{dev.mgmt_ip}</td>
                          <td className="p-3 font-mono">{dev.province}</td>
                          <td className="p-3">
                            <span className="px-1.5 py-0.5 rounded bg-[var(--surface-sunken)] border border-[var(--border)] text-[var(--muted)] text-[10px]">
                              {dev.role}
                            </span>
                          </td>
                          <td className="p-3 font-mono text-[11px] text-[var(--muted)]">
                            {dev.zabbix_hostid || "--"}
                          </td>
                          <td className="p-3">
                            <StatusBadge
                              variant={getStatusVariant(dev.telemetry_status)}
                              label={dev.telemetry_status}
                            />
                          </td>
                          <td className="p-3">
                            {dev.problem_count > 0 ? (
                              <span className="px-2 py-0.5 text-[10px] rounded bg-red-500/20 text-red-400 font-semibold font-mono">
                                {dev.problem_count} problem(s)
                              </span>
                            ) : (
                              <span className="text-[10px] text-emerald-400 font-mono">None</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <button
                              onClick={() => {
                                setSelectedDeviceName(dev.name);
                                setActiveTab("interfaces");
                              }}
                              className="px-2.5 py-1 text-[11px] font-medium rounded bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)]"
                            >
                              Inspect Interfaces
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Interface Explorer */}
        {activeTab === "interfaces" && (
          <div className="flex flex-col h-full gap-4 overflow-hidden">
            {/* Device Picker & Telemetry Scalars Strip */}
            <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-4 shrink-0">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-xs font-semibold text-[var(--fg)]">Selected Router:</span>
                <select
                  value={selectedDeviceName}
                  onChange={(e) => setSelectedDeviceName(e.target.value)}
                  className="text-xs font-mono px-3 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] font-semibold"
                >
                  {(fleetData?.devices || []).map((d) => (
                    <option key={d.id} value={d.name}>
                      {d.name} ({d.mgmt_ip})
                    </option>
                  ))}
                </select>

                {deviceMonitoring && (
                  <div className="flex items-center gap-3 text-xs text-[var(--muted)] pl-2 border-l border-[var(--border)]">
                    <span className="flex items-center gap-1">
                      <Cpu className="w-3.5 h-3.5 text-[var(--accent)]" />
                      CPU: <strong className="text-[var(--fg)]">{deviceMonitoring.metrics.cpu?.value ?? "--"}%</strong>
                    </span>
                    <span className="flex items-center gap-1">
                      <Layers className="w-3.5 h-3.5 text-purple-400" />
                      Mem: <strong className="text-[var(--fg)]">{deviceMonitoring.metrics.memory?.value ?? "--"}%</strong>
                    </span>
                    <span className="flex items-center gap-1">
                      <Thermometer className="w-3.5 h-3.5 text-amber-400" />
                      Temp: <strong className="text-[var(--fg)]">{deviceMonitoring.metrics.temperature?.value ?? "--"}°C</strong>
                    </span>
                  </div>
                )}
              </div>

              {deviceMonitoring?.grafana?.deep_link && (
                <a
                  href={deviceMonitoring.grafana.deep_link}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>{t("monitoring.openGrafana")}</span>
                </a>
              )}
            </div>

            {/* Interface Table Card */}
            <div className="flex-1 min-h-0 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-col overflow-hidden">
              <div className="p-3 bg-[var(--surface-sunken)] border-b border-[var(--border)] flex items-center justify-between gap-3 shrink-0">
                <div className="relative w-72">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[var(--muted)]" />
                  <input
                    type="text"
                    value={interfaceSearch}
                    onChange={(e) => setInterfaceSearch(e.target.value)}
                    placeholder={t("monitoring.searchInterfaces")}
                    className="w-full text-xs pl-8 pr-3 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
                  />
                </div>

                <span className="text-xs text-[var(--muted)]">
                  {filteredInterfaces.length} interfaces
                </span>
              </div>

              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted)] font-medium sticky top-0 z-10">
                    <tr>
                      <th className="p-3">{t("monitoring.interfaceName")}</th>
                      <th className="p-3">{t("monitoring.adminOperStatus")}</th>
                      <th className="p-3">{t("monitoring.inRate")}</th>
                      <th className="p-3">{t("monitoring.outRate")}</th>
                      <th className="p-3">{t("monitoring.errorsDiscards")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {loadingDeviceMon ? (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-[var(--muted)]">
                          <RotateCw className="w-4 h-4 animate-spin mx-auto text-[var(--accent)]" />
                        </td>
                      </tr>
                    ) : filteredInterfaces.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-[var(--muted)]">
                          {t("monitoring.noInterfaces")}
                        </td>
                      </tr>
                    ) : (
                      filteredInterfaces.map((ifc) => {
                        const isUp = String(ifc.oper_status) === "1" || String(ifc.oper_status).toLowerCase() === "up";
                        return (
                          <tr key={ifc.name} className="hover:bg-[var(--surface-hover)] transition">
                            <td className="p-3 font-mono font-semibold text-[var(--fg)]">
                              {ifc.name}
                            </td>
                            <td className="p-3">
                              <StatusBadge
                                variant={isUp ? "ok" : "fault"}
                                label={isUp ? "Up / Up" : "Down"}
                              />
                            </td>
                            <td className="p-3 font-mono text-emerald-400 font-semibold">
                              {formatRate(ifc.in_rate_bps)}
                            </td>
                            <td className="p-3 font-mono text-cyan-400 font-semibold">
                              {formatRate(ifc.out_rate_bps)}
                            </td>
                            <td className="p-3 font-mono text-[var(--muted)]">
                              {ifc.errors_in ?? 0} in / {ifc.errors_out ?? 0} out
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Integration Doctor & Webhook URL */}
        {activeTab === "doctor" && (
          <div className="flex flex-col h-full gap-4 overflow-y-auto">
            {/* Diagnostics Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 shrink-0">
              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>Zabbix Telemetry Engine</span>
                  {doctor?.zabbix.status === "ok" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-amber-400" />
                  )}
                </div>
                <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                  {doctor?.zabbix?.status?.toUpperCase() || "OK"}
                </div>
                <p className="text-xs text-[var(--muted)] mt-1">
                  API Version: {doctor?.zabbix?.version || "Zabbix 5.0+"}
                </p>
              </div>

              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>Grafana Integration</span>
                  {doctor?.grafana?.status === "ok" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                  )}
                </div>
                <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                  {doctor?.grafana?.status?.toUpperCase() || "OK"}
                </div>
                <p className="text-xs text-[var(--muted)] mt-1">
                  URL: {doctor?.grafana.base_url || "Configured"}
                </p>
              </div>

              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>Inventory Mapping</span>
                  <Radio className="w-4 h-4 text-[var(--accent)]" />
                </div>
                <div className="text-xl font-bold font-mono text-[var(--accent)] mt-1">
                  {doctor?.coverage.coverage_pct}%
                </div>
                <p className="text-xs text-[var(--muted)] mt-1">
                  {doctor?.coverage.mapped_devices} of {doctor?.coverage.total_devices} devices mapped
                </p>
              </div>
            </div>

            {/* Webhook Configuration Box */}
            <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-col gap-3">
              <h4 className="text-xs font-bold text-[var(--fg)] flex items-center gap-2">
                <Radio className="w-4 h-4 text-[var(--accent)]" />
                {t("monitoring.webhookUrl")}
              </h4>
              <p className="text-xs text-[var(--muted)]">{t("monitoring.webhookHint")}</p>

              <div className="flex items-center gap-2 max-w-2xl">
                <input
                  type="text"
                  readOnly
                  value={webhookUrl}
                  className="flex-1 text-xs font-mono p-2 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] select-all"
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(webhookUrl);
                    setCopiedWebhook(true);
                    setTimeout(() => setCopiedWebhook(false), 2000);
                  }}
                  className="px-3 py-2 text-xs font-medium rounded bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white flex items-center gap-1.5 transition"
                >
                  {copiedWebhook ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedWebhook ? "Copied!" : "Copy"}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
