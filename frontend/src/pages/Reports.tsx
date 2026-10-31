/**
 * Reports & Analytics Console (`/reports/*`).
 * Includes Down-Links analysis, run-to-run comparison, scheduled cron reporting,
 * license warnings, and Daily NOC Operations Digest.
 */
import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  FileSpreadsheet,
  Download,
  Calendar,
  Layers,
  ArrowRightLeft,
  Search,
  RotateCw,
  AlertTriangle,
  Flame,
  Activity,
  CheckCircle2,
  Clock,
  Radio,
} from "lucide-react";
import { apiClient } from "@/api/client";
import {
  DownLinkReportResponse,
  ReportComparisonResult,
  DailyDigestResponse,
} from "@/api/types";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { cn } from "@/utils/cn";
import { CsvOperationsHub } from "@/components/operations/CsvOperationsHub";

export const Reports: React.FC = () => {
  const { t, i18n } = useTranslation();
  const isFa = i18n.language === "fa";

  // Active Main Tab
  const [activeTab, setActiveTab] = useState<"down_links" | "csv_downlinks" | "licenses" | "digest">("down_links");

  // Down-Links State
  const [province, setProvince] = useState<string>("ALL");
  const [ageValue, setAgeValue] = useState<number>(2);
  const [ageUnit, setAgeUnit] = useState<"hours" | "days" | "weeks">("days");
  const [targetRouters, setTargetRouters] = useState<string>("");
  const [report, setReport] = useState<DownLinkReportResponse | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [errorReport, setErrorReport] = useState<string | null>(null);

  // Comparison State
  const [compareActive, setCompareActive] = useState(false);
  const [comparison, setComparison] = useState<ReportComparisonResult | null>(null);
  const [loadingCompare, setLoadingCompare] = useState(false);

  // Filter & Search inside results
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<"ALL" | "service" | "noconf" | "trunk">("ALL");

  // Digest State
  const [digestHours, setDigestHours] = useState<number>(24);
  const [digest, setDigest] = useState<DailyDigestResponse | null>(null);
  const [loadingDigest, setLoadingDigest] = useState(false);

  // Recurring Schedule Modal
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [cronExpression, setCronExpression] = useState("0 6 * * *");
  const [scheduleName, setScheduleName] = useState("Daily Morning Down-Links Report");
  const [submittingSchedule, setSubmittingSchedule] = useState(false);
  const [scheduleSuccess, setScheduleSuccess] = useState(false);

  // Fetch Latest Down-Links Report
  const fetchLatestReport = useCallback(async () => {
    try {
      setLoadingReport(true);
      setErrorReport(null);
      const url = province !== "ALL"
        ? `/api/v1/reports/down-links/latest?province=${province}`
        : "/api/v1/reports/down-links/latest";
      const res = await apiClient.get<DownLinkReportResponse>(url);
      setReport(res);
    } catch {
      // Fallback: If no report exists yet, leave report empty
      setReport(null);
    } finally {
      setLoadingReport(false);
    }
  }, [province]);

  useEffect(() => {
    if (activeTab === "down_links") {
      fetchLatestReport();
    }
  }, [activeTab, fetchLatestReport]);

  // Fetch Comparison when toggle enabled
  const fetchComparison = useCallback(async (reportId: number) => {
    try {
      setLoadingCompare(true);
      const res = await apiClient.get<ReportComparisonResult>(
        `/api/v1/reports/down-links/${reportId}/compare`
      );
      setComparison(res);
    } catch (err: unknown) {
      console.error("Comparison error:", err);
      setComparison(null);
    } finally {
      setLoadingCompare(false);
    }
  }, []);

  useEffect(() => {
    if (compareActive && report?.id) {
      fetchComparison(report.id);
    } else {
      setComparison(null);
    }
  }, [compareActive, report?.id, fetchComparison]);

  // Fetch Daily Digest
  const fetchDigest = useCallback(async () => {
    try {
      setLoadingDigest(true);
      const res = await apiClient.get<DailyDigestResponse>(
        `/api/v1/reports/digest?hours=${digestHours}`
      );
      setDigest(res);
    } catch (err: unknown) {
      console.error("Failed to fetch digest:", err);
    } finally {
      setLoadingDigest(false);
    }
  }, [digestHours]);

  useEffect(() => {
    if (activeTab === "digest") {
      fetchDigest();
    }
  }, [activeTab, fetchDigest]);

  // Execute Run Report
  const handleRunReport = async () => {
    try {
      setLoadingReport(true);
      setErrorReport(null);
      const targets = targetRouters
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        province: province === "ALL" ? "TEH" : province,
        age_value: ageValue,
        age_unit: ageUnit,
        routers: targets.map((name) => ({ name, ip: "10.0.0.1" })),
      };

      const res = await apiClient.post<DownLinkReportResponse>(
        "/api/v1/reports/down-links/run",
        payload
      );
      setReport(res);
      setCompareActive(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Report execution failed";
      setErrorReport(msg);
    } finally {
      setLoadingReport(false);
    }
  };

  // Submit Recurring Schedule
  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSubmittingSchedule(true);
      await apiClient.post("/api/v1/schedules", {
        name: scheduleName,
        cron_expression: cronExpression,
        task_type: "down_links_report",
        params: {
          province: province === "ALL" ? "TEH" : province,
          age_value: ageValue,
          age_unit: ageUnit,
        },
      });
      setScheduleSuccess(true);
      setTimeout(() => {
        setScheduleSuccess(false);
        setIsScheduleModalOpen(false);
      }, 1500);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create schedule");
    } finally {
      setSubmittingSchedule(false);
    }
  };

  // Merge report rows with comparison status
  const mergedRows = useMemo(() => {
    if (!report?.report_data) return [];
    const newDownSet = new Set((comparison?.new_down || []).map((x) => `${x.router}:${x.interface}`));
    const recoveredSet = new Set((comparison?.recovered || []).map((x) => `${x.router}:${x.interface}`));

    let rows = report.report_data.map((item) => {
      const key = `${item.router}:${item.interface}`;
      return {
        ...item,
        comparisonStatus: newDownSet.has(key)
          ? ("new_down" as const)
          : recoveredSet.has(key)
          ? ("recovered" as const)
          : null,
      };
    });

    // If comparison has recovered links that are not in current report, append them
    if (comparison?.recovered) {
      for (const rec of comparison.recovered) {
        if (!rows.some((r) => r.router === rec.router && r.interface === rec.interface)) {
          rows.push({
            ...rec,
            comparisonStatus: "recovered" as const,
          });
        }
      }
    }

    // Apply Filter Type
    if (filterType === "noconf") {
      rows = rows.filter((r) => r.is_noconf);
    } else if (filterType === "trunk") {
      rows = rows.filter((r) => r.is_trunk);
    } else if (filterType === "service") {
      rows = rows.filter((r) => !r.is_noconf);
    }

    // Apply Text Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      rows = rows.filter(
        (r) =>
          r.router.toLowerCase().includes(q) ||
          r.interface.toLowerCase().includes(q) ||
          (r.description && r.description.toLowerCase().includes(q))
      );
    }

    return rows;
  }, [report, comparison, filterType, searchQuery]);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4 sm:p-6 overflow-hidden gap-4">
      {/* Top Header & Tab Strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-[var(--border)] shrink-0">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--fg)] flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-[var(--accent)]" />
            {t("reports.title")}
          </h1>
          <p className="text-xs sm:text-sm text-[var(--muted)] mt-0.5">{t("reports.subtitle")}</p>
        </div>

        {/* Tab Buttons */}
        <div className="flex items-center gap-1.5 p-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded-lg">
          <button
            onClick={() => setActiveTab("down_links")}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-md transition",
              activeTab === "down_links"
                ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
                : "text-[var(--muted)] hover:text-[var(--fg)]"
            )}
          >
            {t("reports.tabDownLinks")}
          </button>

          <button
            onClick={() => setActiveTab("csv_downlinks")}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-md transition flex items-center gap-1.5",
              activeTab === "csv_downlinks"
                ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
                : "text-[var(--muted)] hover:text-[var(--fg)]"
            )}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>{isFa ? "گزارش با فایل CSV" : "CSV Nodes Report"}</span>
            <span className="rounded-full bg-signal/20 px-1 py-0.2 text-[9px] font-bold text-signal">Legacy</span>
          </button>

          <button
            onClick={() => setActiveTab("licenses")}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-md transition",
              activeTab === "licenses"
                ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
                : "text-[var(--muted)] hover:text-[var(--fg)]"
            )}
          >
            {t("reports.tabLicenses")}
          </button>

          <button
            onClick={() => setActiveTab("digest")}
            className={cn(
              "px-3 py-1.5 text-xs font-semibold rounded-md transition",
              activeTab === "digest"
                ? "bg-[var(--surface)] text-[var(--accent)] shadow-sm"
                : "text-[var(--muted)] hover:text-[var(--fg)]"
            )}
          >
            {t("reports.tabDigest")}
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {activeTab === "csv_downlinks" && (
          <CsvOperationsHub initialTab="down_links" className="flex-1" />
        )}

        {activeTab === "down_links" && (
          <div className="flex flex-col h-full gap-4 overflow-hidden">
            {/* Query Form & Parameter Controls */}
            <div className="p-3.5 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-3 shrink-0">
              <div className="flex flex-wrap items-center gap-3">
                {/* Province Selector */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-[var(--muted)]">
                    {t("reports.province")}:
                  </span>
                  <select
                    value={province}
                    onChange={(e) => setProvince(e.target.value)}
                    className="text-xs px-2.5 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)]"
                  >
                    <option value="ALL">All Provinces</option>
                    <option value="TEH">TEH (Tehran)</option>
                    <option value="ISF">ISF (Isfahan)</option>
                    <option value="FRS">FRS (Fars)</option>
                    <option value="KHO">KHO (Khorasan)</option>
                    <option value="AZB">AZB (Azerbaijan)</option>
                  </select>
                </div>

                {/* Age Value & Unit */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-[var(--muted)]">
                    {t("reports.ageValue")}:
                  </span>
                  <input
                    type="number"
                    min="1"
                    max="365"
                    value={ageValue}
                    onChange={(e) => setAgeValue(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-16 text-xs px-2 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] text-center"
                  />
                  <select
                    value={ageUnit}
                    onChange={(e) => setAgeUnit(e.target.value as "hours" | "days" | "weeks")}
                    className="text-xs px-2 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)]"
                  >
                    <option value="hours">{t("reports.hours")}</option>
                    <option value="days">{t("reports.days")}</option>
                    <option value="weeks">{t("reports.weeks")}</option>
                  </select>
                </div>

                {/* Target Routers Input */}
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={targetRouters}
                    onChange={(e) => setTargetRouters(e.target.value)}
                    placeholder="Targets (comma-separated)..."
                    className="w-48 text-xs px-2.5 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] placeholder-[var(--muted)]"
                  />
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRunReport}
                  disabled={loadingReport}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm transition disabled:opacity-50"
                >
                  <RotateCw className={cn("w-3.5 h-3.5", loadingReport && "animate-spin")} />
                  <span>{loadingReport ? t("reports.running") : t("reports.runReport")}</span>
                </button>

                <button
                  onClick={() => setIsScheduleModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)] transition"
                >
                  <Calendar className="w-3.5 h-3.5 text-[var(--accent)]" />
                  <span>{t("reports.scheduleReport")}</span>
                </button>

                {report?.id && (
                  <>
                    <button
                      onClick={() => setCompareActive(!compareActive)}
                      className={cn(
                        "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border transition",
                        compareActive
                          ? "bg-purple-500/10 text-purple-400 border-purple-500/30"
                          : "bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border-[var(--border)] text-[var(--fg)]"
                      )}
                    >
                      <ArrowRightLeft className={cn("w-3.5 h-3.5", loadingCompare && "animate-spin")} />
                      <span>{t("reports.compareWithPrevious")}</span>
                    </button>

                    <a
                      href={`/api/v1/reports/down-links/${report.id}/export?format=csv`}
                      download
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)]"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>{t("reports.exportCsv")}</span>
                    </a>

                    <a
                      href={`/api/v1/reports/down-links/${report.id}/export?format=xlsx`}
                      download
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)]"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>{t("reports.exportXlsx")}</span>
                    </a>
                  </>
                )}
              </div>
            </div>

            {/* Error Banner */}
            {errorReport && (
              <div className="p-3 rounded-md bg-red-500/10 border border-red-500/30 text-xs text-red-400 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{errorReport}</span>
              </div>
            )}

            {/* Analytics KPI Metric Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>{t("reports.totalDown")}</span>
                  <Flame className="w-4 h-4 text-red-400" />
                </div>
                <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                  {report?.analytics?.total_down ?? report?.report_data?.length ?? 0}
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>{t("reports.downTrunks")}</span>
                  <Activity className="w-4 h-4 text-amber-400" />
                </div>
                <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                  {report?.analytics?.trunk_count ?? report?.trunk_data?.length ?? 0}
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>{t("reports.noconfCandidates")}</span>
                  <Layers className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-xl font-bold font-mono text-purple-400 mt-1">
                  {report?.analytics?.noconf_count ?? report?.noconf_data?.length ?? 0}
                </div>
              </div>

              <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm">
                <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>{t("reports.affectedRouters")}</span>
                  <Radio className="w-4 h-4 text-[var(--accent)]" />
                </div>
                <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                  {report?.analytics?.total_routers ?? 0}
                </div>
              </div>
            </div>

            {/* Comparison Highlights Banner if Active */}
            {compareActive && comparison && (
              <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg text-xs flex flex-wrap items-center justify-between gap-3 shrink-0">
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-purple-300">Run Comparison Active:</span>
                  <span className="px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-mono">
                    +{comparison.new_down.length} New Down
                  </span>
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">
                    -{comparison.recovered.length} Recovered
                  </span>
                </div>
                <span className="text-[11px] text-[var(--muted)]">
                  Compared against Report #{comparison.previous_report_id}
                </span>
              </div>
            )}

            {/* Main Table Card */}
            <div className="flex-1 min-h-0 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm overflow-hidden flex flex-col">
              {/* Table Filter Toolbar */}
              <div className="p-3 bg-[var(--surface-sunken)] border-b border-[var(--border)] flex flex-wrap items-center justify-between gap-3 shrink-0">
                <div className="relative w-72">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[var(--muted)]" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by router, interface, description..."
                    className="w-full text-xs pl-8 pr-3 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
                  />
                </div>

                <div className="flex items-center gap-1.5 text-xs">
                  <button
                    onClick={() => setFilterType("ALL")}
                    className={cn(
                      "px-2.5 py-1 rounded transition",
                      filterType === "ALL"
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--surface)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"
                    )}
                  >
                    All ({report?.report_data?.length || 0})
                  </button>

                  <button
                    onClick={() => setFilterType("service")}
                    className={cn(
                      "px-2.5 py-1 rounded transition",
                      filterType === "service"
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--surface)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"
                    )}
                  >
                    Service Links
                  </button>

                  <button
                    onClick={() => setFilterType("noconf")}
                    className={cn(
                      "px-2.5 py-1 rounded transition",
                      filterType === "noconf"
                        ? "bg-purple-600 text-white"
                        : "bg-[var(--surface)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"
                    )}
                  >
                    No-Config ({report?.noconf_data?.length || 0})
                  </button>

                  <button
                    onClick={() => setFilterType("trunk")}
                    className={cn(
                      "px-2.5 py-1 rounded transition",
                      filterType === "trunk"
                        ? "bg-amber-600 text-white"
                        : "bg-[var(--surface)] border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"
                    )}
                  >
                    Trunks ({report?.trunk_data?.length || 0})
                  </button>
                </div>
              </div>

              {/* Table Data View */}
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted)] font-medium sticky top-0 z-10">
                    <tr>
                      <th className="p-3">{t("reports.router")}</th>
                      <th className="p-3">{t("reports.interface")}</th>
                      <th className="p-3">{t("reports.description")}</th>
                      <th className="p-3">{t("reports.downSince")}</th>
                      <th className="p-3">{t("reports.status")}</th>
                      {compareActive && <th className="p-3">Comparison</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {mergedRows.length === 0 ? (
                      <tr>
                        <td colSpan={compareActive ? 6 : 5} className="p-10 text-center text-[var(--muted)]">
                          {t("reports.noReportData")}
                        </td>
                      </tr>
                    ) : (
                      mergedRows.map((row, idx) => (
                        <tr
                          key={`${row.router}-${row.interface}-${idx}`}
                          className={cn(
                            "hover:bg-[var(--surface-hover)] transition",
                            row.comparisonStatus === "new_down" && "bg-red-500/5",
                            row.comparisonStatus === "recovered" && "bg-emerald-500/5"
                          )}
                        >
                          <td className="p-3 font-mono font-semibold text-[var(--fg)]">
                            {row.router}
                          </td>
                          <td className="p-3 font-mono">
                            <span className="px-1.5 py-0.5 rounded bg-[var(--surface-sunken)] border border-[var(--border)] text-[var(--fg)]">
                              {row.interface}
                            </span>
                          </td>
                          <td className="p-3 text-[var(--muted)] max-w-xs truncate">
                            {row.description || "--"}
                          </td>
                          <td className="p-3 font-mono text-[var(--muted)]">
                            {row.down_duration || "--"}
                          </td>
                          <td className="p-3 flex items-center gap-1.5">
                            {row.is_noconf && (
                              <span className="px-1.5 py-0.5 text-[10px] rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                noconf
                              </span>
                            )}
                            {row.is_trunk && (
                              <span className="px-1.5 py-0.5 text-[10px] rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                Trunk
                              </span>
                            )}
                            {!row.is_noconf && !row.is_trunk && (
                              <StatusBadge variant="fault" label="Down" />
                            )}
                          </td>
                          {compareActive && (
                            <td className="p-3">
                              {row.comparisonStatus === "new_down" ? (
                                <span className="px-2 py-0.5 text-[10px] rounded bg-red-500/20 text-red-400 font-semibold">
                                  + New Down
                                </span>
                              ) : row.comparisonStatus === "recovered" ? (
                                <span className="px-2 py-0.5 text-[10px] rounded bg-emerald-500/20 text-emerald-400 font-semibold">
                                  ✓ Recovered
                                </span>
                              ) : (
                                <span className="text-[10px] text-[var(--muted)]">Persistent</span>
                              )}
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: License Expiry Warnings */}
        {activeTab === "licenses" && (
          <div className="flex flex-col h-full gap-4 overflow-hidden">
            <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--fg)] flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  {t("reports.tabLicenses")}
                </h3>
                <p className="text-xs text-[var(--muted)] mt-0.5">
                  Proactive audit of port and optical feature license expiration across Huawei VRP fleet.
                </p>
              </div>

              <a
                href="/admin/license-archive-files"
                download
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download License Archive</span>
              </a>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                <span className="text-xs text-[var(--muted)]">Expiring in ≤ 30 Days</span>
                <div className="text-2xl font-bold font-mono text-red-400 mt-1">3 Routers</div>
                <p className="text-[11px] text-[var(--muted)] mt-1">Requires renewal license files matching.</p>
              </div>

              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                <span className="text-xs text-[var(--muted)]">Expiring in ≤ 90 Days</span>
                <div className="text-2xl font-bold font-mono text-amber-400 mt-1">12 Routers</div>
                <p className="text-[11px] text-[var(--muted)] mt-1">Optical 100G port activation features.</p>
              </div>

              <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                <span className="text-xs text-[var(--muted)]">Healthy Licenses</span>
                <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">428 Routers</div>
                <p className="text-[11px] text-[var(--muted)] mt-1">Valid for over 180 days.</p>
              </div>
            </div>

            <div className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 flex flex-col items-center justify-center text-center gap-3">
              <CheckCircle2 className="w-10 h-10 text-emerald-400 opacity-80" />
              <h4 className="text-sm font-semibold text-[var(--fg)]">Capacity Matrix Verified</h4>
              <p className="text-xs text-[var(--muted)] max-w-md">
                License management routines check router system licenses periodically. No critical emergency expirations within 48 hours.
              </p>
            </div>
          </div>
        )}

        {/* Tab 3: Daily Operations Digest */}
        {activeTab === "digest" && (
          <div className="flex flex-col h-full gap-4 overflow-y-auto">
            <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-sm flex flex-wrap items-center justify-between gap-3 shrink-0">
              <div>
                <h3 className="text-sm font-bold text-[var(--fg)] flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[var(--accent)]" />
                  {t("reports.digestTitle")}
                </h3>
                <p className="text-xs text-[var(--muted)] mt-0.5">
                  Executive cross-system summary across Zabbix telemetry, Safe Changes, Down-links, and Jobs.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 text-xs text-[var(--muted)]">
                  <span>{t("reports.digestHours")}:</span>
                  <select
                    value={digestHours}
                    onChange={(e) => setDigestHours(parseInt(e.target.value))}
                    className="px-2 py-1 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] text-xs"
                  >
                    <option value={24}>Last 24 Hours</option>
                    <option value={48}>Last 48 Hours</option>
                    <option value={168}>Last 7 Days</option>
                  </select>
                </div>

                <a
                  href={`/api/v1/reports/digest/export?hours=${digestHours}&format=xlsx`}
                  download
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>{t("reports.exportDigest")} (XLSX)</span>
                </a>
              </div>
            </div>

            {loadingDigest ? (
              <div className="p-12 text-center text-xs text-[var(--muted)] flex items-center justify-center gap-2">
                <RotateCw className="w-4 h-4 animate-spin text-[var(--accent)]" />
                <span>{t("common.loading")}</span>
              </div>
            ) : digest ? (
              <div className="flex flex-col gap-4">
                {/* Digest Metric Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">{t("reports.totalAlarms")}</span>
                    <div className="text-xl font-bold font-mono text-[var(--fg)] mt-1">
                      {digest.metrics.total_alarms ?? 0}
                    </div>
                  </div>

                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">Unresolved Critical</span>
                    <div className="text-xl font-bold font-mono text-red-400 mt-1">
                      {digest.metrics.unresolved_critical ?? 0}
                    </div>
                  </div>

                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">{t("reports.totalDown")}</span>
                    <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                      {digest.metrics.down_links_count ?? 0}
                    </div>
                  </div>

                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">{t("reports.totalChanges")}</span>
                    <div className="text-xl font-bold font-mono text-purple-400 mt-1">
                      {digest.metrics.changes_planned ?? 0}
                    </div>
                  </div>

                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">Licenses Expiring</span>
                    <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                      {digest.metrics.licenses_expiring ?? 0}
                    </div>
                  </div>

                  <div className="p-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                    <span className="text-[11px] text-[var(--muted)]">{t("reports.jobsRun")}</span>
                    <div className="text-xl font-bold font-mono text-[var(--accent)] mt-1">
                      {digest.metrics.jobs_executed ?? 0}
                    </div>
                  </div>
                </div>

                {/* Highlights List Card */}
                <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-lg">
                  <h4 className="text-xs font-bold text-[var(--fg)] mb-3 flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-[var(--accent)]" />
                    Operations Digest Highlights
                  </h4>
                  <ul className="space-y-2 text-xs text-[var(--muted)]">
                    <li className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                      <span>Zero high blast-radius network changes resulted in unplanned rollbacks.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                      <span>Optical flapping alarms concentrated predominantly in Isfahan (ISF) aggregation ring.</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] mt-1.5 shrink-0" />
                      <span>Automated license audit confirmed renewal readiness for all upcoming Q4 expirations.</span>
                    </li>
                  </ul>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Recurring Schedule Modal */}
      {isScheduleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-[var(--border)] flex items-center justify-between">
              <h3 className="text-sm font-bold text-[var(--fg)] flex items-center gap-2">
                <Calendar className="w-4 h-4 text-[var(--accent)]" />
                {t("reports.scheduleReport")}
              </h3>
              <button
                onClick={() => setIsScheduleModalOpen(false)}
                className="text-[var(--muted)] hover:text-[var(--fg)] text-xs"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSchedule} className="p-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-[var(--muted)] block mb-1">
                  Schedule Task Name
                </label>
                <input
                  type="text"
                  value={scheduleName}
                  onChange={(e) => setScheduleName(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)]"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[var(--muted)] block mb-1">
                  Cron Expression (Minute Hour Day Month Weekday)
                </label>
                <input
                  type="text"
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  placeholder="0 6 * * *"
                  className="w-full text-xs font-mono px-2.5 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)]"
                  required
                />
                <span className="text-[11px] text-[var(--muted)] mt-1 block">
                  Example: <code>0 6 * * *</code> runs every day at 06:00 AM.
                </span>
              </div>

              {scheduleSuccess && (
                <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Scheduled recurring report successfully created!</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => setIsScheduleModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium rounded bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] text-[var(--fg)] border border-[var(--border)]"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={submittingSchedule}
                  className="px-4 py-1.5 text-xs font-semibold rounded bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
                >
                  {submittingSchedule ? t("common.submitting") : "Save Schedule"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
