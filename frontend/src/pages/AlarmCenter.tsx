/**
 * Alarm Center Screen (/alarms).
 * Conforms to plan/09_PHASE7_UI_SCREENS.md §9.5:
 * Split view: left = filters (device/province/level/age/interface/text + source Zabbix|SSH|both) with saved filters; right = table.
 * Row action "Plan alarm clear…".
 * Mismatch column highlights Zabbix-vs-SSH differences.
 * "Fetch live from devices" button runs an SSH read-only job on the selected devices and streams results in place.
 * Selecting alarms and pressing "Plan alarm clear" opens the Change planner (9.6) pre-filled.
 */
import React, { useState, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ColumnDef } from "@tanstack/react-table";
import {
  AlertTriangle,
  RefreshCw,
  Search,
  Filter,
  Terminal,
  Zap,
  Bookmark,
  ChevronDown,
  ArrowRight,
  ShieldAlert,
  FileSpreadsheet,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { apiClient } from "@/api/client";
import {
  UnifiedAlarmItem,
  ActiveAlarmsResponse,
  SavedAlarmFilter,
} from "@/api/types";
import { DataTable } from "@/components/datatable/DataTable";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Mono } from "@/components/ui/Mono";
import { CsvOperationsHub } from "@/components/operations/CsvOperationsHub";

export const AlarmCenter: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // Mode: Live Alarms vs Direct CSV Bulk Clearance
  const [centerMode, setCenterMode] = useState<"live" | "csv_bulk">(
    searchParams.get("tab") === "csv" ? "csv_bulk" : "live"
  );

  // Filter States
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [province, setProvince] = useState(searchParams.get("province") || "all");
  const [level, setLevel] = useState(searchParams.get("level") || "all");
  const [source, setSource] = useState(searchParams.get("source") || "both");
  const [interfaceFilter, setInterfaceFilter] = useState("");
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(true);

  // Selection & UI States
  const [selectedAlarms, setSelectedAlarms] = useState<UnifiedAlarmItem[]>([]);
  const [isLiveFetching, setIsLiveFetching] = useState(false);
  const [newFilterName, setNewFilterName] = useState("");
  const [isSavingFilter, setIsSavingFilter] = useState(false);

  // Fetch saved presets
  const { data: savedFilters = [] } = useQuery<SavedAlarmFilter[]>({
    queryKey: ["alarmSavedFilters"],
    queryFn: () => apiClient.get<SavedAlarmFilter[]>("/api/v1/alarms/filters"),
  });

  // Fetch active alarms
  const {
    data: alarmsData,
    isLoading,
    refetch,
    isFetching,
  } = useQuery<ActiveAlarmsResponse>({
    queryKey: ["activeAlarms", province, level, source],
    queryFn: async () => {
      const payload: Record<string, unknown> = {};
      if (province !== "all") payload.province = province;
      if (level !== "all") payload.level = level;
      if (source !== "both") payload.source = source;
      return apiClient.post<ActiveAlarmsResponse>("/api/v1/alarms/active", payload);
    },
    refetchInterval: 30_000,
  });

  const allAlarms = useMemo(() => alarmsData?.alarms || [], [alarmsData?.alarms]);

  // Client-side quick filter
  const filteredAlarms = useMemo(() => {
    let result = allAlarms;
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (a) =>
          a.device_name.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q) ||
          (a.interface && a.interface.toLowerCase().includes(q))
      );
    }
    if (interfaceFilter.trim()) {
      const iface = interfaceFilter.toLowerCase().trim();
      result = result.filter(
        (a) => a.interface && a.interface.toLowerCase().includes(iface)
      );
    }
    return result;
  }, [allAlarms, search, interfaceFilter]);

  // Save Filter Mutation
  const saveFilterMutation = useMutation({
    mutationFn: (name: string) =>
      apiClient.post("/api/v1/alarms/filters", {
        name,
        criteria: { province, level, source, search, interface: interfaceFilter },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alarmSavedFilters"] });
      setNewFilterName("");
      setIsSavingFilter(false);
    },
  });

  // Live on-demand fetch from devices via Netmiko
  const handleFetchLive = async () => {
    setIsLiveFetching(true);
    try {
      await refetch();
    } finally {
      setIsLiveFetching(false);
    }
  };

  // Launch Safe Changes Planner pre-filled with selected alarms
  const handlePlanAlarmClear = useCallback(
    (targets?: UnifiedAlarmItem[]) => {
      const toPlan = targets || selectedAlarms;
      if (toPlan.length === 0) return;

      const deviceNames = Array.from(new Set(toPlan.map((a) => a.device_name))).join(",");
      const interfaces = Array.from(
        new Set(toPlan.map((a) => a.interface).filter(Boolean))
      ).join(",");

      navigate(
        `/changes?targets=${encodeURIComponent(deviceNames)}&interfaces=${encodeURIComponent(
          interfaces
        )}&source=alarm_center`
      );
    },
    [navigate, selectedAlarms]
  );

  // Table Columns Definition
  const columns = useMemo<ColumnDef<UnifiedAlarmItem, unknown>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="rounded border-line text-signal focus:ring-signal"
            aria-label="Select all alarms"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="rounded border-line text-signal focus:ring-signal"
            aria-label={`Select alarm on ${row.original.device_name}`}
          />
        ),
        enableSorting: false,
        size: 36,
      },
      {
        accessorKey: "device_name",
        header: t("dashboard.device"),
        cell: ({ getValue }) => (
          <Mono copyable={true} className="text-xs font-semibold text-signal">
            {getValue<string>()}
          </Mono>
        ),
      },
      {
        accessorKey: "level_name",
        header: t("dashboard.severity"),
        cell: ({ getValue }) => {
          const val = (getValue<string>() || "Warning").toLowerCase();
          const variant: StatusVariant =
            val === "critical" || val === "disaster"
              ? "fault"
              : val === "major" || val === "high"
              ? "warn"
              : val === "minor" || val === "average"
              ? "signal"
              : "info-muted";

          return (
            <div className="flex items-center gap-1.5">
              <StatusBadge
                variant={variant}
                label={getValue<string>()}
                pulse={variant === "fault"}
                className="text-[10px] py-0 px-1.5 font-bold uppercase tracking-wider"
              />
            </div>
          );
        },
      },
      {
        id: "source",
        header: t("alarmCenter.source"),
        cell: ({ row }) => {
          const alarm = row.original;
          const src = alarm.source || "both";
          return (
            <div className="flex items-center gap-1">
              <span className="rounded bg-surface-2 px-1.5 py-0.2 text-[9px] font-mono text-ink-2 uppercase border border-line">
                {src}
              </span>
              {alarm.mismatch && (
                <span
                  title={t("alarmCenter.mismatchWarning")}
                  className="rounded bg-warn/15 border border-warn/30 px-1 py-0.2 text-[9px] font-bold text-warn inline-flex items-center gap-0.5"
                >
                  <AlertTriangle className="h-2.5 w-2.5" />
                  <span>{t("alarmCenter.mismatch")}</span>
                </span>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "interface",
        header: t("alarmCenter.interfaceFilter"),
        cell: ({ row }) => {
          const iface = row.original.interface;
          if (!iface) return <span className="text-ink-2 text-[10px]">--</span>;
          return (
            <div className="flex items-center gap-1">
              <Mono copyable={true} className="text-[11px] text-ink">
                {iface}
              </Mono>
              {row.original.is_noconf && (
                <span className="rounded bg-fault/15 border border-fault/30 px-1 text-[9px] font-mono font-medium text-fault">
                  noconf
                </span>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "description",
        header: t("dashboard.alarmTitle"),
        cell: ({ getValue }) => (
          <span className="text-xs text-ink font-mono line-clamp-1">
            {getValue<string>()}
          </span>
        ),
      },
      {
        accessorKey: "age_minutes",
        header: t("dashboard.age"),
        cell: ({ getValue }) => {
          const mins = getValue<number | undefined>();
          if (mins === undefined || mins === null) return <span className="text-ink-2 text-[10px]">--</span>;
          const display =
            mins < 60
              ? `${mins}m`
              : mins < 1440
              ? `${Math.floor(mins / 60)}h ${mins % 60}m`
              : `${Math.floor(mins / 1440)}d`;
          return <span className="text-[11px] font-mono text-ink-2">{display}</span>;
        },
      },
      {
        id: "actions",
        header: t("devices.actions"),
        cell: ({ row }) => (
          <button
            type="button"
            onClick={() => handlePlanAlarmClear([row.original])}
            className="inline-flex items-center gap-1 rounded-control border border-line bg-surface px-2 py-0.5 text-[10px] font-medium text-signal hover:bg-surface-2 transition-colors"
          >
            <Terminal className="h-3 w-3" />
            <span>Plan Clear</span>
          </button>
        ),
      },
    ],
    [t, handlePlanAlarmClear]
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4 space-y-3">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold text-ink">{t("alarmCenter.title")}</h1>
            <span className="rounded-control bg-surface-2 px-2 py-0.5 text-[11px] font-mono text-ink border border-line">
              {filteredAlarms.length} active
            </span>
            {alarmsData?.devices_queried ? (
              <span className="text-[11px] text-ink-2">
                across {alarmsData.devices_queried} devices
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-ink-2">{t("alarmCenter.subtitle")}</p>
        </div>

        {/* Global Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Mode Switcher: Live Telemetry Alarms vs Direct CSV Bulk Clearance */}
          <div className="flex rounded-control border border-line bg-surface p-0.5 text-xs shadow-sm">
            <button
              type="button"
              onClick={() => setCenterMode("live")}
              className={`inline-flex items-center gap-1 rounded-control px-2.5 py-1 text-xs font-semibold transition-colors ${
                centerMode === "live"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:text-ink hover:bg-surface-2"
              }`}
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>آلارم‌های زابیکس (Live Alarms)</span>
            </button>
            <button
              type="button"
              onClick={() => setCenterMode("csv_bulk")}
              className={`inline-flex items-center gap-1.5 rounded-control px-2.5 py-1 text-xs font-semibold transition-colors ${
                centerMode === "csv_bulk"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:text-ink hover:bg-surface-2"
              }`}
            >
              <FileSpreadsheet className="h-3.5 w-3.5" />
              <span>پاکسازی با فایل CSV</span>
              <span className="rounded-full bg-signal/20 px-1 py-0.2 text-[9px] font-bold text-signal">Legacy</span>
            </button>
          </div>

          {centerMode === "live" && (
            <>
              <button
                type="button"
                onClick={() => setIsFilterDrawerOpen(!isFilterDrawerOpen)}
                className={`inline-flex h-7 items-center gap-1.5 rounded-control border border-line px-2.5 text-xs transition-colors ${
                  isFilterDrawerOpen ? "bg-surface-2 text-signal" : "bg-surface text-ink-2 hover:bg-surface-2"
                }`}
              >
                <Filter className="h-3 w-3" />
                <span>{t("alarmCenter.filterDrawer")}</span>
              </button>

              <button
                type="button"
                onClick={handleFetchLive}
                disabled={isLiveFetching || isFetching}
                className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50 transition-colors"
              >
                <Zap className={`h-3 w-3 text-warn ${isLiveFetching ? "animate-bounce" : ""}`} />
                <span>
                  {isLiveFetching ? t("alarmCenter.fetching") : t("alarmCenter.fetchLive")}
                </span>
              </button>

              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                aria-label="Refresh alarms"
                className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-signal" : ""}`} />
              </button>
            </>
          )}
        </div>
      </div>

      {centerMode === "csv_bulk" ? (
        <CsvOperationsHub initialTab="alarm_clear" className="flex-1" />
      ) : (
        /* Main Split View */
        <div className="flex flex-1 gap-4 overflow-hidden">
          {/* Left Filter Drawer */}
          {isFilterDrawerOpen && (
            <div className="flex w-72 flex-col rounded-control border border-line bg-surface p-3.5 space-y-3.5 text-xs overflow-y-auto shrink-0 animate-in slide-in-from-left-2 duration-150">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <span className="font-semibold text-ink flex items-center gap-1.5">
                  <Filter className="h-3.5 w-3.5 text-signal" />
                  <span>{t("alarmCenter.filterDrawer")}</span>
                </span>

              {/* Saved Presets Dropdown */}
              {savedFilters.length > 0 && (
                <DropdownMenu.Root>
                  <DropdownMenu.Trigger asChild>
                    <button
                      type="button"
                      className="text-[11px] text-signal hover:underline flex items-center gap-1"
                    >
                      <Bookmark className="h-3 w-3" />
                      <span>{t("alarmCenter.savedFilters")}</span>
                      <ChevronDown className="h-2.5 w-2.5" />
                    </button>
                  </DropdownMenu.Trigger>
                  <DropdownMenu.Portal>
                    <DropdownMenu.Content
                      align="end"
                      className="z-50 min-w-[160px] rounded-control border border-line bg-surface p-1 shadow-floating text-xs"
                    >
                      {savedFilters.map((sf) => (
                        <DropdownMenu.Item
                          key={sf.id}
                          onClick={() => {
                            const c = sf.criteria || {};
                            if (c.province) setProvince(String(c.province));
                            if (c.level) setLevel(String(c.level));
                            if (c.source) setSource(String(c.source));
                            if (c.search) setSearch(String(c.search));
                            if (c.interface) setInterfaceFilter(String(c.interface));
                          }}
                          className="flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-ink hover:bg-surface-2 outline-none"
                        >
                          <span>{sf.name}</span>
                        </DropdownMenu.Item>
                      ))}
                    </DropdownMenu.Content>
                  </DropdownMenu.Portal>
                </DropdownMenu.Root>
              )}
            </div>

            {/* Free Text Search */}
            <div>
              <label className="block text-[11px] text-ink-2 mb-1">
                {t("alarmCenter.search")}
              </label>
              <div className="flex items-center gap-1.5 rounded-control border border-line bg-surface-2/60 px-2 py-1">
                <Search className="h-3 w-3 text-ink-2" />
                <input
                  type="text"
                  placeholder="Router name or text..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full bg-transparent text-xs text-ink placeholder-ink-2/60 focus:outline-none"
                />
              </div>
            </div>

            {/* Severity Level Filter */}
            <div>
              <label className="block text-[11px] text-ink-2 mb-1">
                {t("alarmCenter.level")}
              </label>
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="all">{t("alarmCenter.allLevels")}</option>
                <option value="Critical">Critical</option>
                <option value="Major">Major</option>
                <option value="Minor">Minor</option>
                <option value="Warning">Warning</option>
              </select>
            </div>

            {/* Source Filter */}
            <div>
              <label className="block text-[11px] text-ink-2 mb-1">
                {t("alarmCenter.source")}
              </label>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="both">{t("alarmCenter.allSources")}</option>
                <option value="zabbix">{t("alarmCenter.zabbixOnly")}</option>
                <option value="ssh">{t("alarmCenter.sshOnly")}</option>
              </select>
            </div>

            {/* Province Filter */}
            <div>
              <label className="block text-[11px] text-ink-2 mb-1">
                {t("devices.filterProvince")}
              </label>
              <select
                value={province}
                onChange={(e) => setProvince(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="all">{t("devices.all")}</option>
                <option value="TEH">TEH (Tehran)</option>
                <option value="ISF">ISF (Isfahan)</option>
                <option value="FRS">FRS (Fars)</option>
                <option value="KHO">KHO (Khorasan)</option>
                <option value="KHZ">KHZ (Khuzestan)</option>
              </select>
            </div>

            {/* Interface Filter */}
            <div>
              <label className="block text-[11px] text-ink-2 mb-1">
                {t("alarmCenter.interfaceFilter")}
              </label>
              <input
                type="text"
                placeholder="e.g. GigabitEthernet0/1/0"
                value={interfaceFilter}
                onChange={(e) => setInterfaceFilter(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs font-mono text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>

            {/* Save Preset Button */}
            <div className="pt-2 border-t border-line">
              {isSavingFilter ? (
                <div className="space-y-1.5">
                  <input
                    type="text"
                    placeholder="Filter preset name..."
                    value={newFilterName}
                    onChange={(e) => setNewFilterName(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none"
                  />
                  <div className="flex items-center gap-1.5 justify-end">
                    <button
                      type="button"
                      onClick={() => setIsSavingFilter(false)}
                      className="text-[10px] text-ink-2 hover:text-ink px-1.5 py-0.5"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (newFilterName.trim()) saveFilterMutation.mutate(newFilterName.trim());
                      }}
                      disabled={!newFilterName.trim()}
                      className="rounded bg-signal px-2 py-0.5 text-[10px] text-white hover:bg-signal/90"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setIsSavingFilter(true)}
                  className="w-full rounded-control border border-line bg-surface-2/60 py-1 text-[11px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors flex items-center justify-center gap-1"
                >
                  <Bookmark className="h-3 w-3" />
                  <span>{t("alarmCenter.saveFilter")}</span>
                </button>
              )}
            </div>

            {/* Noisy Entities Statistics */}
            {alarmsData?.statistics?.noisy_devices && alarmsData.statistics.noisy_devices.length > 0 && (
              <div className="pt-2 border-t border-line space-y-1.5">
                <span className="font-semibold text-ink-2 text-[11px] uppercase tracking-wider">
                  {t("alarmCenter.noisyDevices")}
                </span>
                <div className="space-y-1">
                  {alarmsData.statistics.noisy_devices.slice(0, 4).map((nd) => (
                    <div
                      key={nd.device}
                      onClick={() => setSearch(nd.device)}
                      className="flex items-center justify-between p-1 rounded hover:bg-surface-2 cursor-pointer text-[11px]"
                    >
                      <Mono className="text-[10px] text-signal font-semibold truncate max-w-[150px]">
                        {nd.device}
                      </Mono>
                      <span className="font-mono text-ink-2">{nd.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Right Main Table */}
        <div className="flex flex-1 flex-col overflow-hidden rounded-control border border-line bg-surface">
          {/* Bulk Selection Bar */}
          {selectedAlarms.length > 0 && (
            <div className="flex items-center justify-between bg-signal/10 border-b border-signal/30 p-2.5 text-xs animate-in fade-in duration-150">
              <span className="font-semibold text-signal flex items-center gap-1.5">
                <ShieldAlert className="h-3.5 w-3.5" />
                <span>{t("alarmCenter.selectedCount", { count: selectedAlarms.length })}</span>
              </span>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handlePlanAlarmClear()}
                  className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3 py-1 text-xs font-medium text-white hover:bg-signal/90 shadow-sm"
                >
                  <Terminal className="h-3 w-3" />
                  <span>{t("alarmCenter.planClear")}</span>
                  <ArrowRight className="h-3 w-3" />
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedAlarms([])}
                  className="text-[11px] text-ink-2 hover:text-ink underline ml-1"
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          {/* Alarms DataTable */}
          <div className="flex-1 overflow-hidden flex flex-col">
            <DataTable
              data={filteredAlarms}
              columns={columns}
              filterPlaceholder="Filter active alarms..."
              exportFilename="active_alarms"
              enableSelection={true}
              isLoading={isLoading}
              emptyMessage={t("alarmCenter.noAlarms")}
              className="flex-1"
            />
          </div>
        </div>
      </div>
    )}
  </div>
);
};
