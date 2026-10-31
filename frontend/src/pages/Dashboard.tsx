/**
 * Operations Overview Screen (/ or /overview).
 * Conforms strictly to plan/09_PHASE7_UI_SCREENS.md §9.2:
 *
 * ┌ Fleet health (Zabbix)        ┬ Needs attention (list, max 10)             ┐
 * │ availability %, devices up/  │ failed jobs · changes awaiting approval ·  │
 * │ degraded/down by province    │ licenses expiring ≤ 30 d · devices flapping│
 * ├──────────────────────────────┴────────────────────────────────────────────┤
 * │ Recent jobs (table, last 20)  │  Active problems by severity (Zabbix)      │
 * └───────────────────────────────────────────────────────────────────────────┘
 *
 * Every number is a link to the filtered list behind it.
 * No decorative sparklines; chart answers "problems over last 24 h by severity".
 * Graceful degradation when Zabbix telemetry is offline.
 */
import React from "react";
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
  Clock,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { OverviewResponse } from "@/api/types";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Mono } from "@/components/ui/Mono";
import { Timestamp } from "@/components/ui/Timestamp";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";

export const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<OverviewResponse>({
    queryKey: ["overview"],
    queryFn: () => apiClient.get<OverviewResponse>("/api/v1/overview"),
    refetchInterval: 30_000,
  });

  const fleet = data?.fleet_health;
  const needsAttention = data?.needs_attention || [];
  const recentJobs = data?.recent_jobs || [];
  const problemsBySev = data?.problems_by_severity;
  // Prepare uPlot aligned data: [timestamps, disasterSeries, highSeries, warningSeries]
  const chartData = React.useMemo<[number[], number[], number[], number[]]>(() => {
    const timeline = data?.problems_timeline;
    if (!timeline || timeline.length === 0) {
      const now = Math.floor(Date.now() / 1000);
      return [[now - 3600, now], [0, 0], [0, 0], [0, 0]];
    }
    const timestamps = timeline.map((p) => p.timestamp);
    const disasters = timeline.map((p) => p.disaster);
    const highs = timeline.map((p) => p.high);
    const warnings = timeline.map((p) => p.warning);
    return [timestamps, disasters, highs, warnings];
  }, [data?.problems_timeline]);

  const chartSeries = React.useMemo(
    () => [
      {
        label: t("dashboard.disaster"),
        stroke: "#D23A2B",
        fill: "rgba(210, 58, 43, 0.15)",
        width: 2,
      },
      {
        label: t("dashboard.high"),
        stroke: "#C98500",
        fill: "rgba(201, 133, 0, 0.15)",
        width: 1.5,
      },
      {
        label: t("dashboard.warning"),
        stroke: "#2F5BEA",
        fill: "rgba(47, 91, 234, 0.1)",
        width: 1.5,
      },
    ],
    [t]
  );

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-4 space-y-4">
      {/* Screen Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold text-ink">{t("dashboard.overviewTitle")}</h1>
            {data?.telemetry_status === "degraded" ? (
              <span
                title={data?.telemetry_error || t("dashboard.telemetryDegraded")}
                className="inline-flex items-center gap-1 rounded-control bg-warn/15 px-2 py-0.5 text-[11px] font-medium text-warn border border-warn/30"
              >
                <AlertTriangle className="h-3 w-3" />
                {t("dashboard.telemetryDegraded")}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-control bg-ok/10 px-2 py-0.5 text-[11px] font-medium text-ok border border-ok/30">
                <CheckCircle2 className="h-3 w-3" />
                {t("dashboard.telemetryOk")}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-ink-2">{t("dashboard.overviewSubtitle")}</p>
        </div>

        <div className="flex items-center gap-2">
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
            <span>{isFetching ? "..." : t("common.refresh")}</span>
          </button>
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-72 animate-pulse rounded-control border border-line bg-surface p-4" />
          <div className="h-72 animate-pulse rounded-control border border-line bg-surface p-4" />
          <div className="h-80 animate-pulse rounded-control border border-line bg-surface p-4" />
          <div className="h-80 animate-pulse rounded-control border border-line bg-surface p-4" />
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
            <span>Failed to load overview telemetry</span>
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

      {!isLoading && data && (
        <>
          {/* Top Row: Fleet Health & Needs Attention */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Panel 1: Fleet Health (Zabbix) */}
            <div className="flex flex-col rounded-control border border-line bg-surface p-4">
              <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
                <div className="flex items-center gap-2">
                  <Server className="h-4 w-4 text-signal" />
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                    {t("dashboard.fleetHealth")}
                  </h2>
                </div>
                <Link
                  to="/monitoring"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-signal hover:underline"
                >
                  <span>{t("common.viewAll")}</span>
                  <ArrowRight className="h-3 w-3 rtl:rotate-180" />
                </Link>
              </div>

              {/* Top stat banner: Availability % + Counts */}
              <div className="grid grid-cols-4 gap-2 mb-4">
                <Link
                  to="/monitoring"
                  className="rounded-control bg-surface-2 p-2.5 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] uppercase font-medium text-ink-2">
                    {t("dashboard.availability")}
                  </div>
                  <div className="text-lg font-mono font-bold text-ok dir-ltr mt-0.5">
                    {fleet?.availability_pct ?? 0}%
                  </div>
                </Link>

                <Link
                  to="/devices?health=up"
                  className="rounded-control bg-surface-2 p-2.5 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] uppercase font-medium text-ink-2">
                    {t("dashboard.devicesUp")}
                  </div>
                  <div className="text-lg font-mono font-bold text-ok dir-ltr mt-0.5">
                    {fleet?.available_devices ?? 0}
                  </div>
                </Link>

                <Link
                  to="/devices?health=degraded"
                  className="rounded-control bg-surface-2 p-2.5 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] uppercase font-medium text-ink-2">
                    {t("dashboard.devicesDegraded")}
                  </div>
                  <div className="text-lg font-mono font-bold text-warn dir-ltr mt-0.5">
                    {fleet?.degraded_devices ?? 0}
                  </div>
                </Link>

                <Link
                  to="/devices?health=down"
                  className="rounded-control bg-surface-2 p-2.5 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] uppercase font-medium text-ink-2">
                    {t("dashboard.devicesDown")}
                  </div>
                  <div className="text-lg font-mono font-bold text-fault dir-ltr mt-0.5">
                    {Math.max(0, (fleet?.total_devices ?? 0) - (fleet?.available_devices ?? 0))}
                  </div>
                </Link>
              </div>

              {/* Province Table */}
              <div className="flex-1 overflow-x-auto">
                <div className="text-[11px] font-semibold text-ink-2 mb-1.5 flex items-center justify-between">
                  <span>{t("dashboard.provinceBreakdown")}</span>
                  <span className="text-[10px] font-mono text-ink-2">
                    {fleet?.provinces?.length || 0} provinces
                  </span>
                </div>
                <div className="max-h-48 overflow-y-auto border border-line rounded-control">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-surface-2 sticky top-0 border-b border-line text-[11px] font-semibold text-ink-2">
                      <tr>
                        <th className="px-2.5 py-1.5">{t("dashboard.province")}</th>
                        <th className="px-2 py-1.5 text-right font-mono">Total</th>
                        <th className="px-2 py-1.5 text-right font-mono text-ok">Up</th>
                        <th className="px-2 py-1.5 text-right font-mono text-fault">Down</th>
                        <th className="px-2.5 py-1.5 text-right font-mono">Avail</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60">
                      {(fleet?.provinces || []).map((p) => (
                        <tr
                          key={p.province}
                          onClick={() => navigate(`/devices?province=${encodeURIComponent(p.province)}`)}
                          className="hover:bg-surface-2/80 cursor-pointer transition-colors"
                        >
                          <td className="px-2.5 py-1 font-mono font-medium text-ink">
                            {p.province}
                          </td>
                          <td className="px-2 py-1 text-right font-mono text-ink-2">
                            {p.total}
                          </td>
                          <td className="px-2 py-1 text-right font-mono text-ok">
                            {p.available}
                          </td>
                          <td className="px-2 py-1 text-right font-mono text-fault">
                            {p.total - p.available}
                          </td>
                          <td className="px-2.5 py-1 text-right font-mono font-semibold text-ink dir-ltr">
                            {p.availability_pct}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Panel 2: Needs Attention (List, max 10) */}
            <div className="flex flex-col rounded-control border border-line bg-surface p-4">
              <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-fault" />
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                    {t("dashboard.needsAttention")}
                  </h2>
                </div>
                <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[11px] font-mono text-ink-2">
                  {needsAttention.length} items
                </span>
              </div>

              {needsAttention.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center p-6 text-center text-xs text-ink-2">
                  <CheckCircle2 className="h-8 w-8 text-ok mb-2" />
                  <p className="font-medium text-ink">{t("dashboard.noAttentionItems")}</p>
                </div>
              ) : (
                <div className="flex-1 space-y-2 overflow-y-auto max-h-72">
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

          {/* Bottom Row: Recent Jobs & Active Problems Chart */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Panel 3: Recent Jobs (Table, last 20) */}
            <div className="flex flex-col rounded-control border border-line bg-surface p-4">
              <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-signal" />
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                    {t("dashboard.recentJobs")}
                  </h2>
                </div>
                <Link
                  to="/jobs"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-signal hover:underline"
                >
                  <span>{t("dashboard.viewAllJobs")}</span>
                  <ArrowRight className="h-3 w-3 rtl:rotate-180" />
                </Link>
              </div>

              {recentJobs.length === 0 ? (
                <div className="flex flex-1 items-center justify-center p-6 text-xs text-ink-2">
                  <HelpCircle className="h-5 w-5 text-info-muted mb-1 mr-1" />
                  <span>{t("dashboard.noRecentJobs")}</span>
                </div>
              ) : (
                <div className="flex-1 overflow-x-auto border border-line rounded-control max-h-72 overflow-y-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-surface-2 sticky top-0 border-b border-line text-[11px] font-semibold text-ink-2">
                      <tr>
                        <th className="px-2.5 py-1.5">{t("dashboard.jobType")}</th>
                        <th className="px-2 py-1.5">{t("dashboard.jobStatus")}</th>
                        <th className="px-2 py-1.5">{t("dashboard.jobMode")}</th>
                        <th className="px-2 py-1.5">{t("dashboard.jobCreator")}</th>
                        <th className="px-2 py-1.5">{t("dashboard.jobStarted")}</th>
                        <th className="px-2.5 py-1.5 text-right">{t("dashboard.jobDuration")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60">
                      {recentJobs.map((job) => {
                        const statusVariant =
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
                            <td className="px-2.5 py-1.5">
                              <Mono copyable={false} className="text-[11px]">
                                {job.type}
                              </Mono>
                            </td>
                            <td className="px-2 py-1.5">
                              <StatusBadge
                                variant={statusVariant}
                                label={job.status}
                                className="text-[10px] py-0 px-1.5"
                              />
                            </td>
                            <td className="px-2 py-1.5 text-[11px] font-mono text-ink-2">
                              {job.mode}
                            </td>
                            <td className="px-2 py-1.5 text-[11px] font-mono text-ink">
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

            {/* Panel 4: Active Problems by Severity (Zabbix) + Chart */}
            <div className="flex flex-col rounded-control border border-line bg-surface p-4">
              <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-warn" />
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                    {t("dashboard.activeProblems")}
                  </h2>
                </div>
                <Link
                  to="/alarms"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-signal hover:underline"
                >
                  <span>{t("common.viewAll")}</span>
                  <ArrowRight className="h-3 w-3 rtl:rotate-180" />
                </Link>
              </div>

              {/* Severity Counts Strip */}
              <div className="grid grid-cols-5 gap-1.5 mb-3">
                <Link
                  to="/alarms?severity=disaster"
                  className="rounded-control bg-fault/10 border border-fault/30 p-2 text-center transition-colors hover:bg-fault/20"
                >
                  <div className="text-[10px] font-semibold text-fault uppercase">
                    {t("dashboard.disaster")}
                  </div>
                  <div className="text-base font-mono font-bold text-fault dir-ltr mt-0.5">
                    {problemsBySev?.disaster ?? 0}
                  </div>
                </Link>

                <Link
                  to="/alarms?severity=high"
                  className="rounded-control bg-warn/10 border border-warn/30 p-2 text-center transition-colors hover:bg-warn/20"
                >
                  <div className="text-[10px] font-semibold text-warn uppercase">
                    {t("dashboard.high")}
                  </div>
                  <div className="text-base font-mono font-bold text-warn dir-ltr mt-0.5">
                    {problemsBySev?.high ?? 0}
                  </div>
                </Link>

                <Link
                  to="/alarms?severity=average"
                  className="rounded-control bg-surface-2 p-2 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] font-medium text-ink-2 uppercase">
                    {t("dashboard.average")}
                  </div>
                  <div className="text-base font-mono font-bold text-ink dir-ltr mt-0.5">
                    {problemsBySev?.average ?? 0}
                  </div>
                </Link>

                <Link
                  to="/alarms?severity=warning"
                  className="rounded-control bg-surface-2 p-2 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] font-medium text-ink-2 uppercase">
                    {t("dashboard.warning")}
                  </div>
                  <div className="text-base font-mono font-bold text-ink dir-ltr mt-0.5">
                    {problemsBySev?.warning ?? 0}
                  </div>
                </Link>

                <Link
                  to="/alarms?severity=information"
                  className="rounded-control bg-surface-2 p-2 text-center transition-colors hover:bg-line/40"
                >
                  <div className="text-[10px] font-medium text-ink-2 uppercase">
                    {t("dashboard.information")}
                  </div>
                  <div className="text-base font-mono font-bold text-ink-2 dir-ltr mt-0.5">
                    {problemsBySev?.information ?? 0}
                  </div>
                </Link>
              </div>

              {/* 24h Problem Trend Chart */}
              <div className="flex-1 flex flex-col">
                <div className="text-[11px] font-semibold text-ink-2 mb-1 flex items-center justify-between">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {t("dashboard.problemsTimeline")}
                  </span>
                </div>
                <div className="flex-1 rounded-control border border-line bg-surface-2/40 p-2 min-h-[170px]">
                  <TimeSeriesChart
                    data={chartData}
                    series={chartSeries}
                    height={165}
                    unit=""
                  />
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
