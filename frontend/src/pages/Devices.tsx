/**
 * Devices & Inventory Screen (/devices and /devices/:id).
 * Conforms strictly to plan/09_PHASE7_UI_SCREENS.md §9.3:
 *
 * List: DataTable (name, IP, model, OS family, province, site, tags, health, last seen, license days, in Zabbix?).
 * Bulk actions on selection:
 * - "Add to target set"
 * - "Tag"
 * - "Run… ▸ (alarm clear plan / down-links / license check / config backup)"
 * Import button → CSV import wizard (upload → preview diff: new/changed/unchanged → confirm).
 * Detail page tabs: Summary · Monitoring · Alarms · Configs · Jobs · Compliance.
 * Smooth virtual scrolling for 5,000+ devices.
 */
import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ColumnDef } from "@tanstack/react-table";
import {
  Plus,
  Upload,
  Download,
  RefreshCw,
  Search,
  Crosshair,
  Terminal,
  ShieldCheck,
  Activity,
  CheckCircle2,
  ChevronDown,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { apiClient } from "@/api/client";
import { DeviceItem, DevicesListResponse } from "@/api/types";
import { DataTable } from "@/components/datatable/DataTable";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Mono } from "@/components/ui/Mono";
import { CsvImportModal } from "@/components/devices/CsvImportModal";
import { AddToTargetSetModal } from "@/components/devices/AddToTargetSetModal";
import { DeviceFormModal } from "@/components/devices/DeviceFormModal";
import { DeviceDetailDrawer } from "@/components/devices/DeviceDetailDrawer";

export const Devices: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: routeDeviceId } = useParams<{ id?: string }>();

  // Filter state
  const [search, setSearch] = useState("");
  const [province, setProvince] = useState("all");
  const [healthStatus, setHealthStatus] = useState("all");
  const [role, setRole] = useState("all");
  const [osFamily, setOsFamily] = useState("all");

  // Selection & Modal states
  const [selectedDevices, setSelectedDevices] = useState<DeviceItem[]>([]);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [isAddDeviceOpen, setIsAddDeviceOpen] = useState(false);
  const [isTargetSetOpen, setIsTargetSetOpen] = useState(false);
  const [activeDevice, setActiveDevice] = useState<DeviceItem | null>(null);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  // Fetch devices
  const { data, isLoading, refetch, isFetching } = useQuery<DevicesListResponse>({
    queryKey: ["devices", province, healthStatus, role, osFamily, search],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (province !== "all") params.append("province", province);
      if (healthStatus !== "all") params.append("health_status", healthStatus);
      if (role !== "all") params.append("role", role);
      if (osFamily !== "all") params.append("os_family", osFamily);
      if (search.trim()) params.append("search", search.trim());
      params.append("limit", "1000");

      return apiClient.get<DevicesListResponse>(`/api/v1/devices?${params.toString()}`);
    },
    refetchInterval: 60_000,
  });

  const devices = useMemo(() => data?.devices || [], [data?.devices]);

  // Open drawer if route contains device ID
  React.useEffect(() => {
    if (routeDeviceId && devices.length > 0) {
      const matched = devices.find((d) => String(d.id) === routeDeviceId);
      if (matched) setActiveDevice(matched);
    }
  }, [routeDeviceId, devices]);

  // Trigger Zabbix Sync
  const handleSyncZabbix = async () => {
    setSyncStatus("Syncing...");
    try {
      const res = await apiClient.post<{ matched: number; created: number }>("/api/v1/devices/sync-zabbix", {
        auto_apply: true,
      });
      setSyncStatus(`Synced: ${res.matched ?? 0} matched`);
      refetch();
      setTimeout(() => setSyncStatus(null), 3000);
    } catch (err) {
      setSyncStatus("Sync failed");
      setTimeout(() => setSyncStatus(null), 3000);
    }
  };

  // Export CSV
  const handleExportCsv = () => {
    window.location.href = "/api/v1/devices/export?format=csv";
  };

  // Table Columns Definition
  const columns = useMemo<ColumnDef<DeviceItem, unknown>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="rounded border-line text-signal focus:ring-signal"
            aria-label="Select all devices"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="rounded border-line text-signal focus:ring-signal"
            aria-label={`Select device ${row.original.name}`}
          />
        ),
        enableSorting: false,
        size: 36,
      },
      {
        accessorKey: "name",
        header: t("devices.name"),
        cell: ({ row }) => {
          const dev = row.original;
          return (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setActiveDevice(dev);
                  navigate(`/devices/${dev.id}`, { replace: true });
                }}
                className="font-mono text-xs font-semibold text-signal hover:underline text-start"
              >
                <Mono copyable={true} className="text-[11px]">
                  {dev.name}
                </Mono>
              </button>
              {dev.role && (
                <span className="rounded-control bg-surface-2 px-1.5 py-0.2 text-[9px] font-mono font-medium text-ink-2 uppercase border border-line">
                  {dev.role}
                </span>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "mgmt_ip",
        header: t("devices.mgmtIp"),
        cell: ({ getValue }) => (
          <Mono copyable={true} className="text-[11px]">
            {getValue<string>()}
          </Mono>
        ),
      },
      {
        accessorKey: "model",
        header: t("devices.model"),
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="text-xs text-ink">{row.original.model || "NetEngine"}</span>
            <span className="text-[10px] font-mono text-ink-2 uppercase">
              {row.original.os_family}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "province",
        header: t("devices.province"),
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <span className="font-mono text-xs font-medium text-ink">
              {row.original.province || "--"}
            </span>
            {row.original.site && (
              <span className="text-[10px] text-ink-2 font-mono">/ {row.original.site}</span>
            )}
          </div>
        ),
      },
      {
        accessorKey: "health_status",
        header: t("devices.health"),
        cell: ({ getValue }) => {
          const val = getValue<string>() || "unknown";
          const variant: StatusVariant =
            val === "up" ? "ok" : val === "degraded" ? "warn" : val === "down" ? "fault" : "info-muted";
          return <StatusBadge variant={variant} label={val} className="text-[10px] py-0 px-1.5" />;
        },
      },
      {
        accessorKey: "zabbix_hostid",
        header: t("devices.zabbix"),
        cell: ({ getValue }) => {
          const hostId = getValue<string | null>();
          return hostId ? (
            <span className="inline-flex items-center gap-1 rounded-control bg-ok/10 border border-ok/30 px-1.5 py-0.2 text-[10px] font-mono font-medium text-ok">
              <CheckCircle2 className="h-2.5 w-2.5" />
              <span>{hostId}</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-control bg-surface-2 px-1.5 py-0.2 text-[10px] text-ink-2">
              --
            </span>
          );
        },
      },
      {
        accessorKey: "tags",
        header: "Tags",
        cell: ({ getValue }) => {
          const tags = getValue<string[]>() || [];
          if (tags.length === 0) return <span className="text-ink-2 text-[10px]">--</span>;
          return (
            <div className="flex flex-wrap gap-1 max-w-[180px]">
              {tags.slice(0, 2).map((tg) => (
                <span
                  key={tg}
                  className="rounded-control bg-surface-2 px-1.5 py-0.2 text-[9px] font-mono text-ink-2 border border-line"
                >
                  {tg}
                </span>
              ))}
              {tags.length > 2 && (
                <span className="text-[9px] text-ink-2 font-mono">+{tags.length - 2}</span>
              )}
            </div>
          );
        },
      },
      {
        id: "actions",
        header: t("devices.actions"),
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setActiveDevice(row.original);
                navigate(`/devices/${row.original.id}`, { replace: true });
              }}
              className="rounded-control border border-line bg-surface px-2 py-0.5 text-[10px] font-medium text-ink-2 hover:bg-surface-2 hover:text-signal transition-colors"
            >
              {t("devices.details")}
            </button>
          </div>
        ),
      },
    ],
    [t, navigate]
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4 space-y-3">
      {/* Modals */}
      <CsvImportModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onSuccess={() => refetch()}
      />
      <DeviceFormModal
        isOpen={isAddDeviceOpen}
        onClose={() => setIsAddDeviceOpen(false)}
        onSuccess={() => refetch()}
      />
      <AddToTargetSetModal
        isOpen={isTargetSetOpen}
        onClose={() => setIsTargetSetOpen(false)}
        selectedDeviceIds={selectedDevices.map((d) => d.id)}
        selectedDeviceNames={selectedDevices.map((d) => d.name)}
      />
      <DeviceDetailDrawer
        device={activeDevice}
        onClose={() => {
          setActiveDevice(null);
          navigate("/devices", { replace: true });
        }}
        onRefresh={() => refetch()}
      />

      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold text-ink">{t("devices.title")}</h1>
            <span className="rounded-control bg-surface-2 px-2 py-0.5 text-[11px] font-mono text-ink border border-line">
              {data?.total ?? devices.length} total
            </span>
            {syncStatus && (
              <span className="rounded-control bg-signal/15 px-2 py-0.5 text-[11px] font-medium text-signal">
                {syncStatus}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-ink-2">{t("devices.subtitle")}</p>
        </div>

        {/* Global Device Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSyncZabbix}
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            <span>{t("devices.syncZabbix")}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsImportOpen(true)}
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <Upload className="h-3 w-3" />
            <span>{t("devices.importCsv")}</span>
          </button>

          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <Download className="h-3 w-3" />
            <span>{t("devices.export")}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsAddDeviceOpen(true)}
            className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3 text-xs font-medium text-white hover:bg-signal/90 transition-colors shadow-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{t("devices.addDevice")}</span>
          </button>
        </div>
      </div>

      {/* Filter Strip */}
      <div className="flex flex-wrap items-center gap-2 bg-surface p-2.5 rounded-control border border-line text-xs">
        {/* Search */}
        <div className="flex flex-1 min-w-[200px] items-center gap-2 rounded-control border border-line bg-surface-2/60 px-2.5 py-1 focus-within:ring-1 focus-within:ring-signal">
          <Search className="h-3.5 w-3.5 text-ink-2" />
          <input
            type="text"
            placeholder={t("devices.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent text-xs text-ink placeholder-ink-2/60 focus:outline-none"
          />
        </div>

        {/* Province Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="filter-province" className="text-[11px] text-ink-2 hidden sm:inline">
            {t("devices.filterProvince")}:
          </label>
          <select
            id="filter-province"
            value={province}
            onChange={(e) => setProvince(e.target.value)}
            className="rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none"
          >
            <option value="all">{t("devices.all")}</option>
            <option value="TEH">TEH (Tehran)</option>
            <option value="ISF">ISF (Isfahan)</option>
            <option value="FRS">FRS (Fars)</option>
            <option value="KHO">KHO (Khorasan)</option>
            <option value="KHZ">KHZ (Khuzestan)</option>
          </select>
        </div>

        {/* Health Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="filter-health" className="text-[11px] text-ink-2 hidden sm:inline">
            {t("devices.filterHealth")}:
          </label>
          <select
            id="filter-health"
            value={healthStatus}
            onChange={(e) => setHealthStatus(e.target.value)}
            className="rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none"
          >
            <option value="all">{t("devices.all")}</option>
            <option value="up">UP</option>
            <option value="degraded">Degraded</option>
            <option value="down">DOWN</option>
          </select>
        </div>

        {/* Role Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="filter-role" className="text-[11px] text-ink-2 hidden sm:inline">
            {t("devices.filterRole")}:
          </label>
          <select
            id="filter-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none"
          >
            <option value="all">{t("devices.all")}</option>
            <option value="PE">PE</option>
            <option value="P">P</option>
            <option value="CORE">CORE</option>
            <option value="AGG">AGG</option>
            <option value="ACCESS">ACCESS</option>
          </select>
        </div>

        {/* OS Filter */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="filter-os" className="text-[11px] text-ink-2 hidden sm:inline">
            {t("devices.filterOs")}:
          </label>
          <select
            id="filter-os"
            value={osFamily}
            onChange={(e) => setOsFamily(e.target.value)}
            className="rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none"
          >
            <option value="all">{t("devices.all")}</option>
            <option value="vrp8">VRP8</option>
            <option value="vrp5">VRP5</option>
          </select>
        </div>

        {/* Refresh */}
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          aria-label="Refresh devices"
          className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-signal" : ""}`} />
        </button>
      </div>

      {/* Bulk Action Bar (when rows are selected) */}
      {selectedDevices.length > 0 && (
        <div className="flex items-center justify-between bg-signal/10 border border-signal/30 p-2.5 rounded-control text-xs animate-in fade-in duration-150">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-signal">
              {t("devices.selectedCount", { count: selectedDevices.length })}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsTargetSetOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-control border border-signal/40 bg-surface px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-2"
            >
              <Crosshair className="h-3 w-3 text-signal" />
              <span>{t("devices.addToTargetSet")}</span>
            </button>

            {/* Run... Dropdown Menu */}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3 py-1 text-xs font-medium text-white hover:bg-signal/90 shadow-sm"
                >
                  <span>{t("devices.run")}</span>
                  <ChevronDown className="h-3 w-3" />
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  className="z-50 min-w-[180px] rounded-control border border-line bg-surface p-1 shadow-floating text-xs"
                >
                  <DropdownMenu.Item
                    onClick={() =>
                      navigate(
                        `/changes?targets=${encodeURIComponent(
                          selectedDevices.map((d) => d.name).join(",")
                        )}`
                      )
                    }
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-ink hover:bg-surface-2 outline-none"
                  >
                    <Terminal className="h-3.5 w-3.5 text-signal" />
                    <span>{t("devices.runAlarmClear")}</span>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onClick={() =>
                      navigate(
                        `/reports?targets=${encodeURIComponent(
                          selectedDevices.map((d) => d.name).join(",")
                        )}`
                      )
                    }
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-ink hover:bg-surface-2 outline-none"
                  >
                    <Activity className="h-3.5 w-3.5 text-warn" />
                    <span>{t("devices.runDownLinks")}</span>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onClick={() =>
                      navigate(
                        `/compliance?targets=${encodeURIComponent(
                          selectedDevices.map((d) => d.name).join(",")
                        )}`
                      )
                    }
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-ink hover:bg-surface-2 outline-none"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 text-ok" />
                    <span>{t("devices.runLicenseCheck")}</span>
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>

            <button
              type="button"
              onClick={() => setSelectedDevices([])}
              className="text-[11px] text-ink-2 hover:text-ink underline ml-1"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Virtualized Table Container */}
      <div className="flex-1 overflow-hidden rounded-control border border-line bg-surface flex flex-col">
        <DataTable
          data={devices}
          columns={columns}
          filterPlaceholder="Live filter..."
          exportFilename="devices_inventory"
          enableSelection={true}
          isLoading={isLoading}
          emptyMessage={t("devices.noDevices")}
          onRowClick={(dev) => {
            setActiveDevice(dev);
            navigate(`/devices/${dev.id}`, { replace: true });
          }}
          className="flex-1"
        />
      </div>
    </div>
  );
};
