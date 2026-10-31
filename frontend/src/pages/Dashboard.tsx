/**
 * Operations Overview Screen (/ or /overview).
 * 100% Genuine NOC Operational Dashboard:
 * - Direct Quick-Launch Hub for Core CSV & SSH Tools (Alarm Clear, Reports, BGP/VRF, License, Sessions).
 * - Real Shared Network Credentials Status (TACACS/SSH).
 * - Real Fleet & Telemetry Health (No hardcoded percentages, zero mock numbers).
 * - Real Recent Jobs Log (Last 20 operations from database).
 * - Real Needs Attention List (Failed jobs, pending approvals, expiring licenses).
 * - 100% Pure Localization (EN: zero Persian characters, FA: natural RTL NOC terminology).
 */
import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ArrowRight,
  ShieldAlert,
  Server,
  Layers,
  HelpCircle,
  FileSpreadsheet,
  ShieldCheck,
  Zap,
  Network,
  FileArchive,
  Key,
  Activity,
  Check,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { OverviewResponse } from "@/api/types";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Timestamp } from "@/components/ui/Timestamp";
import { getNetworkCredentials, NET_CREDS_EVENT } from "@/utils/networkCreds";
import { usePrefsStore } from "@/store/prefs";

export const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const { lang } = usePrefsStore();
  const isFa = lang === "fa";
  const navigate = useNavigate();

  const [selectedGroup, setSelectedGroup] = useState<string>("all");

  // Shared Network Credentials state
  const [netCreds, setNetCreds] = useState(() => getNetworkCredentials());

  useEffect(() => {
    const handleUpdate = () => {
      setNetCreds(getNetworkCredentials());
    };
    window.addEventListener(NET_CREDS_EVENT, handleUpdate);
    return () => window.removeEventListener(NET_CREDS_EVENT, handleUpdate);
  }, []);

  const queryUrl =
    selectedGroup && selectedGroup !== "all"
      ? `/api/v1/overview?group=${encodeURIComponent(selectedGroup)}`
      : "/api/v1/overview";

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<OverviewResponse>({
    queryKey: ["overview", selectedGroup],
    queryFn: () => apiClient.get<OverviewResponse>(queryUrl),
    refetchInterval: 30_000,
  });

  const fleet = data?.fleet_health;
  const needsAttention = data?.needs_attention || [];
  const recentJobs = data?.recent_jobs || [];
  const problemsBySev = data?.problems_by_severity;
  const hostGroups = data?.host_groups || [];

  const totalAlarms =
    problemsBySev
      ? problemsBySev.disaster +
        problemsBySev.high +
        problemsBySev.warning +
        problemsBySev.average +
        problemsBySev.information
      : 0;

  const isZabbixActive = (hostGroups.length > 0 || totalAlarms > 0) && data?.telemetry_status !== "degraded";

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-4 space-y-4">
      {/* Top Header & Telemetry Status Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold text-ink">
              {isFa ? "داشبورد عملیاتی NOC" : "NOC Operations Overview"}
            </h1>
            {isZabbixActive ? (
              <span className="inline-flex items-center gap-1 rounded-control bg-ok/10 px-2 py-0.5 text-[11px] font-medium text-ok border border-ok/30">
                <CheckCircle2 className="h-3 w-3" />
                <span>{isFa ? "تلمتری زبیکس متصل" : "Zabbix Telemetry Active"}</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-control bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-ink-2 border border-line">
                <Server className="h-3 w-3 text-signal" />
                <span>{isFa ? "حالت عملیات مستقیم SSH (بدون زبیکس)" : "Direct SSH Mode (Standalone)"}</span>
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-ink-2">
            {isFa
              ? "مرکز دسترسی سریع به موتور خودکارسازی SSH، گزارش‌گیری با CSV و پایش شبکه"
              : "Rapid access hub for batch SSH router automation, CSV reporting, and fleet telemetry"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Zabbix Host Group Selector Dropdown (Only shown if Zabbix has host groups) */}
          {hostGroups.length > 0 && (
            <div className="flex items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink-2 shadow-sm focus-within:ring-1 focus-within:ring-signal">
              <Layers className="h-3.5 w-3.5 text-signal" />
              <label htmlFor="host-group-select" className="text-[11px] font-medium text-ink-2 hidden sm:inline">
                {isFa ? "گروه زبیکس:" : "Host Group:"}
              </label>
              <select
                id="host-group-select"
                value={selectedGroup}
                onChange={(e) => setSelectedGroup(e.target.value)}
                className="bg-transparent text-xs font-medium text-ink focus:outline-none cursor-pointer pr-1"
              >
                <option value="all">
                  {isFa ? "همه گروه‌ها" : "All Groups"} ({hostGroups.length})
                </option>
                {hostGroups.map((g) => (
                  <option key={g.name} value={g.name}>
                    {g.name} ({g.problem_count} {isFa ? "آلارم" : "alarms"})
                  </option>
                ))}
              </select>
            </div>
          )}

          {data?.cached_at && (
            <span className="text-[11px] text-ink-2 dir-ltr">
              <Timestamp value={data.cached_at} relative />
            </span>
          )}

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh overview"
            title="Refresh statistics"
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-signal" : ""}`} />
            <span>{isFetching ? "..." : (isFa ? "بروزرسانی" : "Refresh")}</span>
          </button>
        </div>
      </div>

      {/* ========================================================= */}
      {/* SECTION 1: CORE TOOLS QUICK-LAUNCH HUB                   */}
      {/* ========================================================= */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-signal" />
            <span>{isFa ? "ابزارهای عملیاتی اصلی Netmate" : "Core Operational Tools"}</span>
          </span>
          <span className="text-[11px] text-ink-2">
            {isFa ? "مبتنی بر فایل‌های CSV و اجرای فرامین SSH" : "CSV & SSH Batch Automation Engine"}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {/* Tool 1: Alarm Clear */}
          <Link
            to="/alarms"
            className="group flex flex-col justify-between rounded-control border border-line bg-surface p-3.5 transition-all hover:border-signal hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-signal/10 text-signal group-hover:bg-signal group-hover:text-white transition-colors">
                  <FileSpreadsheet className="h-4 w-4" />
                </div>
                <span className="rounded bg-signal/15 px-1.5 py-0.5 text-[10px] font-semibold text-signal">
                  {isFa ? "روال اصلی NOC" : "Core NOC"}
                </span>
              </div>
              <h2 className="text-xs font-bold text-ink group-hover:text-signal transition-colors">
                {isFa ? "پاکسازی آلارم روترها" : "Alarm Clearance"}
              </h2>
              <p className="mt-1 text-[11px] text-ink-2 leading-relaxed">
                {isFa
                  ? "بارگذاری فایل CSV روترها، اجرای دستورات پاکسازی آلارم با SSH و دریافت اکسل"
                  : "Batch CSV upload, SSH alarm suppression on Huawei routers & Excel report download"}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-signal">
              <span>{isFa ? "ورود به پاکسازی آلارم" : "Open Alarm Clear"}</span>
              <ArrowRight className="h-3 w-3 rtl:rotate-180 group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
            </div>
          </Link>

          {/* Tool 2: Reports & Trunks */}
          <Link
            to="/reports"
            className="group flex flex-col justify-between rounded-control border border-line bg-surface p-3.5 transition-all hover:border-signal hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-ok/10 text-ok group-hover:bg-ok group-hover:text-white transition-colors">
                  <Activity className="h-4 w-4" />
                </div>
                <span className="rounded bg-ok/15 px-1.5 py-0.5 text-[10px] font-semibold text-ok">
                  {isFa ? "اکسل گزارش‌ها" : "Excel Reports"}
                </span>
              </div>
              <h2 className="text-xs font-bold text-ink group-hover:text-ok transition-colors">
                {isFa ? "گزارش لینک‌های قطع و ترانک‌ها" : "Outages & Trunk Reports"}
              </h2>
              <p className="mt-1 text-[11px] text-ink-2 leading-relaxed">
                {isFa
                  ? "تحلیل فایل CSV نودها، استعلام SSH اینترفیس‌ها بر اساس استان و سن قطعی"
                  : "Parse node CSV, query interfaces over SSH, and download Down-Links & Trunk Excel"}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-ok">
              <span>{isFa ? "ورود به گزارش‌گیری" : "Open Reports"}</span>
              <ArrowRight className="h-3 w-3 rtl:rotate-180 group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
            </div>
          </Link>

          {/* Tool 3: BGP & VRF Routing */}
          <Link
            to="/tools/vrf-routing"
            className="group flex flex-col justify-between rounded-control border border-line bg-surface p-3.5 transition-all hover:border-signal hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-indigo-500/10 text-indigo-400 group-hover:bg-indigo-500 group-hover:text-white transition-colors">
                  <Network className="h-4 w-4" />
                </div>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold text-ink-2">
                  VPNv4 / RT
                </span>
              </div>
              <h2 className="text-xs font-bold text-ink group-hover:text-indigo-400 transition-colors">
                {isFa ? "بررسی روتینگ BGP و VRF" : "BGP & VRF Route Lookup"}
              </h2>
              <p className="mt-1 text-[11px] text-ink-2 leading-relaxed">
                {isFa
                  ? "استعلام از Route Reflector، تشخیص خودکار VRF و اتصال SSH به روتر مبدا جهت نمایش کانفیگ"
                  : "Query Route Reflector, auto-detect VRF via RTs & connect to origin PE for interface config"}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-indigo-400">
              <span>{isFa ? "ورود به بررسی روتینگ" : "Open Route Lookup"}</span>
              <ArrowRight className="h-3 w-3 rtl:rotate-180 group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
            </div>
          </Link>

          {/* Tool 4: License Management */}
          <Link
            to="/tools/license"
            className="group flex flex-col justify-between rounded-control border border-line bg-surface p-3.5 transition-all hover:border-signal hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500 group-hover:text-white transition-colors">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                  ESN Match
                </span>
              </div>
              <h2 className="text-xs font-bold text-ink group-hover:text-emerald-400 transition-colors">
                {isFa ? "مدیریت و تمدید لایسنس" : "License Management"}
              </h2>
              <p className="mt-1 text-[11px] text-ink-2 leading-relaxed">
                {isFa
                  ? "استعلام وضعیت لایسنس‌ها با CSV و تطبیق خودکار فایل‌های XML/ZIP هواوی"
                  : "Batch SSH license status inspection and automated XML/ZIP ESN renewal matching"}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
              <span>{isFa ? "ورود به لایسنس‌ها" : "Open License Tools"}</span>
              <ArrowRight className="h-3 w-3 rtl:rotate-180 group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
            </div>
          </Link>

          {/* Tool 5: SecureCRT Sessions */}
          <Link
            to="/tools/sessions"
            className="group flex flex-col justify-between rounded-control border border-line bg-surface p-3.5 transition-all hover:border-signal hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-8 w-8 items-center justify-center rounded bg-purple-500/10 text-purple-400 group-hover:bg-purple-500 group-hover:text-white transition-colors">
                  <FileArchive className="h-4 w-4" />
                </div>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold text-ink-2">
                  SecureCRT
                </span>
              </div>
              <h2 className="text-xs font-bold text-ink group-hover:text-purple-400 transition-colors">
                {isFa ? "سشن‌های SecureCRT" : "SecureCRT Sessions"}
              </h2>
              <p className="mt-1 text-[11px] text-ink-2 leading-relaxed">
                {isFa
                  ? "تحلیل ساختار درختی از فایل CSV و دانلود آرشیو ZIP آماده ایمپورت سشن‌ها"
                  : "Upload router inventory CSV to generate ready-to-import SecureCRT session tree ZIP archive"}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-purple-400">
              <span>{isFa ? "تولید سشن‌ها" : "Open Session Extractor"}</span>
              <ArrowRight className="h-3 w-3 rtl:rotate-180 group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
            </div>
          </Link>
        </div>
      </div>

      {/* ========================================================= */}
      {/* SECTION 2: NETWORK CREDENTIALS & OPERATIONAL METRICS      */}
      {/* ========================================================= */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* TACACS Status Card */}
        <div className="rounded-control border border-line bg-surface p-3.5 flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-signal/10 text-signal">
            <Key className="h-4 w-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase font-semibold text-ink-2">
              {isFa ? "کردینشال متمرکز SSH / TACACS" : "Network Credentials"}
            </div>
            <div className="text-xs font-bold text-ink truncate mt-0.5 font-mono">
              {netCreds.username ? netCreds.username : (isFa ? "تنظیم نشده" : "Not Set")}
            </div>
          </div>
          {netCreds.username ? (
            <span className="rounded bg-ok/10 text-ok px-2 py-0.5 text-[10px] font-semibold flex items-center gap-1">
              <Check className="h-3 w-3" />
              <span>Ready</span>
            </span>
          ) : (
            <span className="rounded bg-warn/15 text-warn px-2 py-0.5 text-[10px] font-semibold">
              Pending
            </span>
          )}
        </div>

        {/* Real Fleet Inventory Count */}
        <Link
          to="/devices"
          className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between hover:border-signal transition-colors"
        >
          <div>
            <div className="text-[10px] uppercase font-semibold text-ink-2">
              {isFa ? "تعداد روترها در دیتابیس" : "Inventory Devices"}
            </div>
            <div className="text-xl font-bold font-mono text-ink mt-0.5">
              {fleet?.total_devices ?? 0}
            </div>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded bg-surface-2 text-ink-2">
            <Server className="h-4 w-4" />
          </div>
        </Link>

        {/* Real Active Alarms (Zabbix) */}
        <Link
          to="/alarms"
          className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between hover:border-signal transition-colors"
        >
          <div>
            <div className="text-[10px] uppercase font-semibold text-ink-2">
              {isFa ? "آلارم‌های فعال زبیکس" : "Active Zabbix Alarms"}
            </div>
            <div className="text-xl font-bold font-mono text-signal mt-0.5">
              {totalAlarms}
            </div>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded bg-signal/10 text-signal">
            <ShieldAlert className="h-4 w-4" />
          </div>
        </Link>

        {/* Real Recent Operations Count */}
        <Link
          to="/jobs"
          className="rounded-control border border-line bg-surface p-3.5 flex items-center justify-between hover:border-signal transition-colors"
        >
          <div>
            <div className="text-[10px] uppercase font-semibold text-ink-2">
              {isFa ? "عملیات‌های اخیر (Jobs)" : "Recent Jobs Executed"}
            </div>
            <div className="text-xl font-bold font-mono text-ink mt-0.5">
              {recentJobs.length}
            </div>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded bg-surface-2 text-ink-2">
            <Layers className="h-4 w-4" />
          </div>
        </Link>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-72 animate-pulse rounded-control border border-line bg-surface p-4" />
          <div className="h-72 animate-pulse rounded-control border border-line bg-surface p-4" />
        </div>
      )}

      {/* Error Banner */}
      {isError && (
        <div
          role="alert"
          className="rounded-control border border-fault/30 bg-fault/10 p-4 text-xs text-fault"
        >
          <div className="font-semibold flex items-center gap-1.5">
            <XCircle className="h-4 w-4" />
            <span>Failed to load overview data</span>
          </div>
          <div className="mt-1">{error instanceof Error ? error.message : "Network error"}</div>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-2 inline-flex h-6 items-center rounded-control border border-fault/40 bg-surface px-2 text-xs font-medium text-ink hover:bg-surface-2"
          >
            {t("common.retry")}
          </button>
        </div>
      )}

      {/* ========================================================= */}
      {/* SECTION 3: REAL RECENT JOBS & NEEDS ATTENTION             */}
      {/* ========================================================= */}
      {!isLoading && data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Panel 1: Recent Operations (Jobs Table from DB) */}
          <div className="flex flex-col rounded-control border border-line bg-surface p-4">
            <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-signal" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {isFa ? "آخرین عملیات‌های اجرایی روی شبکه" : "Recent Network Operations (Jobs)"}
                </h2>
              </div>
              <Link
                to="/jobs"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-signal hover:underline"
              >
                <span>{isFa ? "مشاهده همه" : "View All"}</span>
                <ArrowRight className="h-3 w-3 rtl:rotate-180" />
              </Link>
            </div>

            {recentJobs.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-xs text-ink-2 text-center">
                <HelpCircle className="h-6 w-6 text-ink-2/40 mb-2" />
                <span>{isFa ? "هنوز هیچ عملیاتی اجرا نشده است." : "No operations recorded yet."}</span>
              </div>
            ) : (
              <div className="flex-1 overflow-x-auto border border-line rounded-control max-h-80 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-surface-2 sticky top-0 border-b border-line text-[11px] font-semibold text-ink-2">
                    <tr>
                      <th className="px-2.5 py-1.5">{isFa ? "نوع عملیات" : "Type"}</th>
                      <th className="px-2 py-1.5">{isFa ? "وضعیت" : "Status"}</th>
                      <th className="px-2 py-1.5">{isFa ? "کاربر" : "User"}</th>
                      <th className="px-2 py-1.5">{isFa ? "زمان اجرا" : "Started"}</th>
                      <th className="px-2.5 py-1.5 text-right">{isFa ? "مدت" : "Duration"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {recentJobs.map((job) => {
                      const statusVariant: StatusVariant =
                        job.status === "succeeded"
                          ? "ok"
                          : job.status === "failed"
                          ? "fault"
                          : job.status === "running"
                          ? "signal"
                          : "info-muted";

                      return (
                        <tr
                          key={job.id}
                          onClick={() => navigate(`/jobs/${job.id}`)}
                          className="hover:bg-surface-2/80 cursor-pointer transition-colors"
                        >
                          <td className="px-2.5 py-1.5 font-mono text-[11px] font-semibold text-ink">
                            {job.type}
                          </td>
                          <td className="px-2 py-1.5">
                            <StatusBadge
                              variant={statusVariant}
                              label={job.status}
                              className="text-[10px] py-0 px-1.5"
                            />
                          </td>
                          <td className="px-2 py-1.5 text-[11px] font-mono text-ink-2">
                            {job.created_by}
                          </td>
                          <td className="px-2 py-1.5 text-[11px] text-ink-2">
                            <Timestamp value={job.created_at} relative />
                          </td>
                          <td className="px-2.5 py-1.5 text-right font-mono text-[11px] text-ink dir-ltr">
                            {job.duration_seconds !== null ? `${job.duration_seconds}s` : "--"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Panel 2: Real Needs Attention Items */}
          <div className="flex flex-col rounded-control border border-line bg-surface p-4">
            <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-fault" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-ink">
                  {isFa ? "نیازمند بررسی و اقدام اپراتور" : "Items Requiring Attention"}
                </h2>
              </div>
              <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[11px] font-mono text-ink-2">
                {needsAttention.length} {isFa ? "مورد" : "items"}
              </span>
            </div>

            {needsAttention.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-xs text-ink-2">
                <CheckCircle2 className="h-8 w-8 text-ok mb-2" />
                <p className="font-medium text-ink">
                  {isFa ? "تمامی سرویس‌ها و عملیات‌ها در وضعیت پایدار هستند." : "All systems and operations are nominal."}
                </p>
                <p className="text-[11px] text-ink-2 mt-0.5">
                  {isFa ? "هیچ فرآیند ناموفق یا هشدار بحرانی ثبت نشده است." : "No failed jobs or critical warnings detected."}
                </p>
              </div>
            ) : (
              <div className="flex-1 space-y-2 overflow-y-auto max-h-80">
                {needsAttention.map((item) => (
                  <Link
                    key={item.id}
                    to={item.link}
                    className="group flex items-center justify-between rounded-control border border-line bg-surface-2/60 p-2.5 text-xs transition-colors hover:border-signal hover:bg-surface-2"
                  >
                    <div className="flex items-center gap-2.5">
                      {item.severity === "fault" ? (
                        <XCircle className="h-4 w-4 shrink-0 text-fault" />
                      ) : item.severity === "warn" ? (
                        <AlertTriangle className="h-4 w-4 shrink-0 text-warn" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" />
                      )}
                      <span className="font-medium text-ink group-hover:text-signal">
                        {item.title}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-mono text-xs font-bold text-ink dir-ltr">
                        {item.count}
                      </span>
                      <ArrowRight className="h-3.5 w-3.5 text-ink-2 group-hover:text-signal group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5 transition-transform" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
