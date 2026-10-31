/**
 * Jobs & Automation Screen (`/jobs`, `/jobs/:id`).
 * Master-Detail view with real-time RunTimeline swimlane, streaming LogViewer,
 * task results inspection, CSV/JSON export, and cancellation controls.
 */
import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Play,
  RotateCw,
  XCircle,
  Download,
  Search,
  Terminal,
  Activity,
  Copy,
  Check,
  Plus,
  Layers,
  FileText,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { JobItem, JobTaskItem, JobListResponse } from "@/api/types";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { RunTimeline, DeviceTimelineRow, TimelineStepKey } from "@/components/timeline/RunTimeline";
import { LogViewer } from "@/components/logviewer/LogViewer";
import { useJobEvents } from "@/components/logviewer/useJobEvents";
import { cn } from "@/utils/cn";

export const Jobs: React.FC = () => {
  const { id: routeJobId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // Jobs state
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Selected Job Details
  const [selectedJobId, setSelectedJobId] = useState<string | null>(routeJobId || null);
  const [selectedJob, setSelectedJob] = useState<JobItem | null>(null);
  const [activeTab, setActiveTab] = useState<"timeline" | "results" | "params">("timeline");
  const [cancelling, setCancelling] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  // New Job Modal
  const [isNewJobOpen, setIsNewJobOpen] = useState(false);
  const [newJobType, setNewJobType] = useState("alarm_clear");
  const [newJobMode, setNewJobMode] = useState<"dry_run" | "apply">("dry_run");
  const [newJobDevices, setNewJobDevices] = useState("");
  const [submittingJob, setSubmittingJob] = useState(false);

  // SSE Live Streaming for selected job
  const { events: sseEvents, status: sseStatus } = useJobEvents(selectedJobId);

  // Fetch Jobs List
  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const qs = new URLSearchParams({ page: "1", page_size: "50" });
      if (typeFilter !== "ALL") qs.set("type", typeFilter);
      if (statusFilter !== "ALL") qs.set("status", statusFilter);

      const res = await apiClient.get<JobListResponse>(`/api/v1/jobs?${qs.toString()}`);
      setJobs(res.items || []);
      setTotalJobs(res.total || 0);

      // Default select first job if none selected
      if (!selectedJobId && res.items && res.items.length > 0) {
        setSelectedJobId(res.items[0].id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load jobs";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter, selectedJobId]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Sync selected job with route param
  useEffect(() => {
    if (routeJobId && routeJobId !== selectedJobId) {
      setSelectedJobId(routeJobId);
    }
  }, [routeJobId, selectedJobId]);

  // Fetch Single Job Detail when selectedJobId changes
  const fetchJobDetail = useCallback(async (jobId: string) => {
    try {
      const res = await apiClient.get<JobItem>(`/api/v1/jobs/${jobId}`);
      setSelectedJob(res);
    } catch (err: unknown) {
      console.error("Failed to load job details:", err);
    }
  }, []);

  useEffect(() => {
    if (selectedJobId) {
      fetchJobDetail(selectedJobId);
    } else {
      setSelectedJob(null);
    }
  }, [selectedJobId, fetchJobDetail]);

  // Filtered jobs
  const filteredJobs = useMemo(() => {
    if (!searchQuery.trim()) return jobs;
    const q = searchQuery.toLowerCase();
    return jobs.filter(
      (j) =>
        j.id.toLowerCase().includes(q) ||
        j.type.toLowerCase().includes(q) ||
        j.created_by.toLowerCase().includes(q)
    );
  }, [jobs, searchQuery]);

  // Map tasks to RunTimeline rows
  const timelineDevices: DeviceTimelineRow[] = useMemo(() => {
    if (!selectedJob?.tasks || selectedJob.tasks.length === 0) {
      // Fallback virtual row if tasks not individually broken down
      if (!selectedJob) return [];
      const isSuccess = selectedJob.status === "succeeded";
      const isFailed = selectedJob.status === "failed";
      const isRunning = selectedJob.status === "running";
      return [
        {
          deviceId: selectedJob.id,
          deviceName: "Fleet Execution Target",
          site: "Core NOC",
          overallStatus: isSuccess ? "succeeded" : isFailed ? "failed" : isRunning ? "running" : "pending",
          steps: {
            connect: { state: isSuccess || isRunning ? "succeeded" : isFailed ? "failed" : "pending" },
            pre_check: { state: isSuccess || isRunning ? "succeeded" : isFailed ? "failed" : "pending" },
            plan: { state: isSuccess || isRunning ? "succeeded" : isFailed ? "failed" : "pending" },
            apply: { state: isSuccess ? "succeeded" : isFailed ? "failed" : isRunning ? "running" : "pending" },
            verify: { state: isSuccess ? "succeeded" : isFailed ? "failed" : "pending" },
          },
        },
      ];
    }

    return selectedJob.tasks.map((task: JobTaskItem) => {
      const st = task.status;
      const isSucc = st === "succeeded";
      const isFail = st === "failed";
      const isRun = st === "running";
      const isSkip = st === "skipped" || st === "cancelled";

      const stepRecord: Record<TimelineStepKey, { state: "pending" | "running" | "succeeded" | "failed" | "skipped" }> = {
        connect: { state: isSucc || isRun ? "succeeded" : isFail ? "failed" : isSkip ? "skipped" : "pending" },
        pre_check: { state: isSucc || isRun ? "succeeded" : isFail ? "failed" : isSkip ? "skipped" : "pending" },
        plan: { state: isSucc || isRun ? "succeeded" : isFail ? "failed" : isSkip ? "skipped" : "pending" },
        apply: { state: isSucc ? "succeeded" : isRun ? "running" : isFail ? "failed" : isSkip ? "skipped" : "pending" },
        verify: { state: isSucc ? "succeeded" : isFail ? "failed" : isSkip ? "skipped" : "pending" },
      };

      const overall: "pending" | "running" | "succeeded" | "failed" =
        isSucc ? "succeeded" : isFail ? "failed" : isRun ? "running" : "pending";

      return {
        deviceId: task.id,
        deviceName: task.device_name,
        site: task.device_name.split("-")[1] || "Core",
        model: "Huawei VRP",
        overallStatus: overall,
        steps: stepRecord,
      };
    });
  }, [selectedJob]);

  // Handle Cancel Job
  const handleCancel = async () => {
    if (!selectedJobId) return;
    try {
      setCancelling(true);
      await apiClient.post(`/api/v1/jobs/${selectedJobId}/cancel`, {});
      await fetchJobDetail(selectedJobId);
      await fetchJobs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to cancel job");
    } finally {
      setCancelling(false);
    }
  };

  // Handle Run Again
  const handleRunAgain = async () => {
    if (!selectedJob) return;
    try {
      setSubmittingJob(true);
      const res = await apiClient.post<{ job_id: string }>("/api/v1/jobs", {
        type: selectedJob.type,
        mode: selectedJob.mode,
        params: selectedJob.params || {},
        devices: selectedJob.tasks?.map((t) => t.device_name) || ["default"],
      });
      setIsNewJobOpen(false);
      await fetchJobs();
      navigate(`/jobs/${res.job_id}`);
      setSelectedJobId(res.job_id);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to run job");
    } finally {
      setSubmittingJob(false);
    }
  };

  // Submit New Job
  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSubmittingJob(true);
      const targetList = newJobDevices
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await apiClient.post<{ job_id: string }>("/api/v1/jobs", {
        type: newJobType,
        mode: newJobMode,
        params: {},
        devices: targetList.length > 0 ? targetList : ["default"],
      });

      setIsNewJobOpen(false);
      setNewJobDevices("");
      await fetchJobs();
      navigate(`/jobs/${res.job_id}`);
      setSelectedJobId(res.job_id);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to submit job");
    } finally {
      setSubmittingJob(false);
    }
  };

  // Helper badge variant
  const getStatusVariant = (st: string): StatusVariant => {
    switch (st) {
      case "succeeded":
        return "ok";
      case "failed":
        return "fault";
      case "running":
        return "signal";
      case "cancelling":
      case "cancelled":
        return "warn";
      case "queued":
      default:
        return "info-muted";
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] p-4 sm:p-6 overflow-hidden gap-4">
      {/* Top Banner & Action Strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-[var(--border)] shrink-0">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--fg)] flex items-center gap-2">
            <Activity className="w-6 h-6 text-[var(--accent)]" />
            {t("jobs.title")}
          </h1>
          <p className="text-xs sm:text-sm text-[var(--muted)] mt-0.5">{t("jobs.subtitle")}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              fetchJobs();
              if (selectedJobId) fetchJobDetail(selectedJobId);
            }}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--fg)] transition"
          >
            <RotateCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            <span>{t("common.refresh")}</span>
          </button>

          <button
            onClick={() => setIsNewJobOpen(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            <span>{t("jobs.newJob")}</span>
          </button>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0 overflow-hidden">
        {/* Left Column: Jobs Queue List (4 cols) */}
        <div className="lg:col-span-4 flex flex-col bg-[var(--surface)] border border-[var(--border)] rounded-lg overflow-hidden shadow-sm">
          {/* List Search & Filter Header */}
          <div className="p-3 bg-[var(--surface-sunken)] border-b border-[var(--border)] flex flex-col gap-2 shrink-0">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[var(--muted)]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("jobs.search")}
                className="w-full text-xs pl-8 pr-3 py-1.5 bg-[var(--surface)] border border-[var(--border)] rounded-md text-[var(--fg)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="text-xs px-2 py-1 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)]"
              >
                <option value="ALL">{t("jobs.allTypes")}</option>
                <option value="alarm_clear">alarm_clear</option>
                <option value="down_links_report">down_links_report</option>
                <option value="license_check">license_check</option>
                <option value="config_backup">config_backup</option>
                <option value="ptp_troubleshoot">ptp_troubleshoot</option>
                <option value="vrf_routing_check">vrf_routing_check</option>
              </select>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-xs px-2 py-1 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--fg)]"
              >
                <option value="ALL">{t("jobs.allStatuses")}</option>
                <option value="queued">queued</option>
                <option value="running">running</option>
                <option value="succeeded">succeeded</option>
                <option value="failed">failed</option>
                <option value="cancelled">cancelled</option>
              </select>
            </div>
          </div>

          {/* List Rows */}
          <div className="flex-1 overflow-y-auto divide-y divide-[var(--border)]">
            {loading && jobs.length === 0 ? (
              <div className="p-8 text-center text-xs text-[var(--muted)] flex items-center justify-center gap-2">
                <RotateCw className="w-4 h-4 animate-spin text-[var(--accent)]" />
                <span>{t("common.loading")}</span>
              </div>
            ) : error ? (
              <div className="p-4 text-xs text-red-400 text-center">{error}</div>
            ) : filteredJobs.length === 0 ? (
              <div className="p-8 text-center text-xs text-[var(--muted)]">
                {t("jobs.noJobs")}
              </div>
            ) : (
              filteredJobs.map((j) => {
                const isSelected = j.id === selectedJobId;
                return (
                  <div
                    key={j.id}
                    onClick={() => {
                      setSelectedJobId(j.id);
                      navigate(`/jobs/${j.id}`, { replace: true });
                    }}
                    className={cn(
                      "p-3 cursor-pointer transition flex flex-col gap-1.5 hover:bg-[var(--surface-hover)]",
                      isSelected && "bg-[var(--surface-selected)] border-l-4 border-l-[var(--accent)]"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-[var(--fg)] truncate">
                        {j.type}
                      </span>
                      <StatusBadge variant={getStatusVariant(j.status)} label={j.status} />
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[var(--muted)]">
                      <span className="font-mono truncate">{j.id.slice(0, 8)}...</span>
                      <span>{j.created_by}</span>
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-[var(--muted)] pt-0.5">
                      <span className="capitalize">{j.mode}</span>
                      <span>
                        {j.created_at ? new Date(j.created_at).toLocaleTimeString() : "--"}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Total Counter Strip */}
          <div className="p-2 bg-[var(--surface-sunken)] border-t border-[var(--border)] text-[11px] text-[var(--muted)] flex items-center justify-between shrink-0">
            <span>{t("devices.total")}: {totalJobs}</span>
            <span>{t("jobs.refreshKeep")}</span>
          </div>
        </div>

        {/* Right Column: Master Detail View (8 cols) */}
        <div className="lg:col-span-8 flex flex-col bg-[var(--surface)] border border-[var(--border)] rounded-lg overflow-hidden shadow-sm">
          {selectedJob ? (
            <div className="flex flex-col h-full overflow-hidden">
              {/* Job Header & Controls */}
              <div className="p-4 bg-[var(--surface-sunken)] border-b border-[var(--border)] shrink-0 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <StatusBadge
                    variant={getStatusVariant(selectedJob.status)}
                    label={selectedJob.status}
                    pulse={selectedJob.status === "running"}
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-[var(--fg)]">
                        {selectedJob.type}
                      </span>
                      <span className="text-xs font-mono px-1.5 py-0.5 bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--muted)] flex items-center gap-1">
                        {selectedJob.id}
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(selectedJob.id);
                            setCopiedId(true);
                            setTimeout(() => setCopiedId(false), 2000);
                          }}
                          className="hover:text-[var(--fg)]"
                        >
                          {copiedId ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        </button>
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-[var(--muted)] mt-0.5">
                      <span>{t("jobs.user")}: <strong className="text-[var(--fg)]">{selectedJob.created_by}</strong></span>
                      <span>•</span>
                      <span>{t("jobs.mode")}: <strong className="text-[var(--fg)]">{selectedJob.mode}</strong></span>
                      <span>•</span>
                      <span>
                        {t("jobs.started")}:{" "}
                        {selectedJob.started_at ? new Date(selectedJob.started_at).toLocaleTimeString() : "Queued"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-2">
                  {(selectedJob.status === "queued" || selectedJob.status === "running") && (
                    <button
                      onClick={handleCancel}
                      disabled={cancelling}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 transition"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>{cancelling ? t("jobs.cancelling") : t("jobs.cancel")}</span>
                    </button>
                  )}

                  <button
                    onClick={handleRunAgain}
                    disabled={submittingJob}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[var(--fg)] border border-[var(--border)] transition"
                  >
                    <RotateCw className="w-3.5 h-3.5" />
                    <span>{t("jobs.runAgain")}</span>
                  </button>

                  <a
                    href={`/api/v1/jobs/${selectedJob.id}/download`}
                    download
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[var(--fg)] border border-[var(--border)] transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>{t("jobs.downloadCsv")}</span>
                  </a>
                </div>
              </div>

              {/* Sub-Tabs: Timeline & Logs | Results & Tasks | Params */}
              <div className="flex items-center gap-4 px-4 bg-[var(--surface)] border-b border-[var(--border)] shrink-0">
                <button
                  onClick={() => setActiveTab("timeline")}
                  className={cn(
                    "py-2.5 text-xs font-medium border-b-2 flex items-center gap-1.5 transition",
                    activeTab === "timeline"
                      ? "border-[var(--accent)] text-[var(--accent)]"
                      : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
                  )}
                >
                  <Activity className="w-3.5 h-3.5" />
                  <span>{t("jobs.swimlaneTitle")}</span>
                </button>

                <button
                  onClick={() => setActiveTab("results")}
                  className={cn(
                    "py-2.5 text-xs font-medium border-b-2 flex items-center gap-1.5 transition",
                    activeTab === "results"
                      ? "border-[var(--accent)] text-[var(--accent)]"
                      : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
                  )}
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span>
                    {t("jobs.resultsTitle")} ({selectedJob.tasks?.length || 0})
                  </span>
                </button>

                <button
                  onClick={() => setActiveTab("params")}
                  className={cn(
                    "py-2.5 text-xs font-medium border-b-2 flex items-center gap-1.5 transition",
                    activeTab === "params"
                      ? "border-[var(--accent)] text-[var(--accent)]"
                      : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
                  )}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>{t("jobs.summary")}</span>
                </button>
              </div>

              {/* Tab Contents */}
              <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
                {activeTab === "timeline" && (
                  <div className="flex flex-col gap-4 h-full">
                    {/* Top: RunTimeline Swimlane */}
                    <div className="bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md p-3">
                      <div className="flex items-center justify-between pb-2 mb-2 border-b border-[var(--border)]">
                        <span className="text-xs font-semibold text-[var(--fg)] flex items-center gap-1.5">
                          <Activity className="w-3.5 h-3.5 text-[var(--accent)]" />
                          {t("jobs.swimlaneTitle")}
                        </span>
                        <span className="text-[11px] text-[var(--muted)]">
                          {timelineDevices.length} {t("jobs.targets")}
                        </span>
                      </div>
                      <RunTimeline
                        devices={timelineDevices}
                        height={180}
                      />
                    </div>

                    {/* Bottom: Streaming LogViewer */}
                    <div className="bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md flex-1 flex flex-col min-h-[300px]">
                      <div className="flex items-center justify-between p-2.5 bg-[var(--surface)] border-b border-[var(--border)]">
                        <span className="text-xs font-semibold text-[var(--fg)] flex items-center gap-1.5">
                          <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                          {t("jobs.logsTitle")}
                        </span>
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "text-[10px] px-2 py-0.5 rounded font-mono",
                              sseStatus === "open"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-[var(--surface)] text-[var(--muted)]"
                            )}
                          >
                            {sseStatus === "open" ? "SSE LIVE" : sseStatus.toUpperCase()}
                          </span>
                        </div>
                      </div>
                      <div className="flex-1 overflow-hidden p-2">
                        <LogViewer
                          events={sseEvents}
                          isStreaming={sseStatus === "open"}
                          height={280}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "results" && (
                  <div className="bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-[var(--surface)] border-b border-[var(--border)] text-[var(--muted)] font-medium">
                        <tr>
                          <th className="p-3">{t("jobs.taskDevice")}</th>
                          <th className="p-3">{t("jobs.taskStatus")}</th>
                          <th className="p-3">{t("jobs.taskDuration")}</th>
                          <th className="p-3">{t("jobs.taskResult")}</th>
                          <th className="p-3">{t("jobs.taskError")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {(!selectedJob.tasks || selectedJob.tasks.length === 0) ? (
                          <tr>
                            <td colSpan={5} className="p-6 text-center text-[var(--muted)]">
                              {t("jobs.noTasks")}
                            </td>
                          </tr>
                        ) : (
                          selectedJob.tasks.map((task) => (
                            <tr key={task.id} className="hover:bg-[var(--surface-hover)]">
                              <td className="p-3 font-mono font-semibold text-[var(--fg)]">
                                {task.device_name}
                              </td>
                              <td className="p-3">
                                <StatusBadge
                                  variant={getStatusVariant(task.status)}
                                  label={task.status}
                                />
                              </td>
                              <td className="p-3 font-mono text-[var(--muted)]">
                                {task.started_at && task.finished_at
                                  ? `${(
                                      (new Date(task.finished_at).getTime() -
                                        new Date(task.started_at).getTime()) /
                                      1000
                                    ).toFixed(2)}s`
                                  : "--"}
                              </td>
                              <td className="p-3 font-mono text-[11px] max-w-xs truncate text-[var(--muted)]">
                                {task.result ? JSON.stringify(task.result) : "--"}
                              </td>
                              <td className="p-3 font-mono text-[11px] text-red-400">
                                {task.error || "--"}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeTab === "params" && (
                  <div className="flex flex-col gap-4">
                    <div className="bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md p-4">
                      <h4 className="text-xs font-semibold text-[var(--fg)] mb-2">
                        {t("jobs.summary")}
                      </h4>
                      <pre className="text-xs font-mono bg-[var(--surface)] p-3 rounded border border-[var(--border)] overflow-x-auto text-[var(--fg)]">
                        {JSON.stringify(selectedJob.summary || {}, null, 2)}
                      </pre>
                    </div>

                    <div className="bg-[var(--surface-sunken)] border border-[var(--border)] rounded-md p-4">
                      <h4 className="text-xs font-semibold text-[var(--fg)] mb-2">
                        Input Parameters
                      </h4>
                      <pre className="text-xs font-mono bg-[var(--surface)] p-3 rounded border border-[var(--border)] overflow-x-auto text-[var(--fg)]">
                        {JSON.stringify(selectedJob.params || {}, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-xs text-[var(--muted)] flex flex-col items-center justify-center gap-2 h-full">
              <Activity className="w-8 h-8 opacity-40 text-[var(--accent)]" />
              <span>Select an automation job from the left list to view execution details.</span>
            </div>
          )}
        </div>
      </div>

      {/* New Job Modal */}
      {isNewJobOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-[var(--border)] flex items-center justify-between">
              <h3 className="text-sm font-bold text-[var(--fg)] flex items-center gap-2">
                <Play className="w-4 h-4 text-[var(--accent)]" />
                {t("jobs.newJob")}
              </h3>
              <button
                onClick={() => setIsNewJobOpen(false)}
                className="text-[var(--muted)] hover:text-[var(--fg)] text-xs"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateJob} className="p-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-[var(--muted)] block mb-1">
                  {t("jobs.type")}
                </label>
                <select
                  value={newJobType}
                  onChange={(e) => setNewJobType(e.target.value)}
                  className="w-full text-xs px-2.5 py-1.5 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)]"
                >
                  <option value="alarm_clear">alarm_clear (Huawei VRP noconf & link flap)</option>
                  <option value="down_links_report">down_links_report (Fiber & Trunk report)</option>
                  <option value="license_check">license_check (Optical & Port licenses)</option>
                  <option value="config_backup">config_backup (Hourly snapshot)</option>
                  <option value="ptp_troubleshoot">ptp_troubleshoot (Sync trace)</option>
                  <option value="vrf_routing_check">vrf_routing_check (Prefix path graph)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-[var(--muted)] block mb-1">
                  {t("jobs.mode")}
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setNewJobMode("dry_run")}
                    className={cn(
                      "px-3 py-1.5 text-xs font-medium rounded border transition text-center",
                      newJobMode === "dry_run"
                        ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                        : "bg-[var(--surface-sunken)] text-[var(--fg)] border-[var(--border)] hover:bg-[var(--surface-hover)]"
                    )}
                  >
                    Dry-Run (Simulate)
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewJobMode("apply")}
                    className={cn(
                      "px-3 py-1.5 text-xs font-medium rounded border transition text-center",
                      newJobMode === "apply"
                        ? "bg-red-600 text-white border-red-600"
                        : "bg-[var(--surface-sunken)] text-[var(--fg)] border-[var(--border)] hover:bg-[var(--surface-hover)]"
                    )}
                  >
                    Apply (Network Changes)
                  </button>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-[var(--muted)] block mb-1">
                  {t("jobs.targets")} (comma or line separated)
                </label>
                <textarea
                  value={newJobDevices}
                  onChange={(e) => setNewJobDevices(e.target.value)}
                  placeholder="PE-TEH-ROUTER-01, PE-TEH-ROUTER-02"
                  rows={3}
                  className="w-full text-xs font-mono p-2 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-[var(--fg)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => setIsNewJobOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium rounded bg-[var(--surface-sunken)] hover:bg-[var(--surface-hover)] text-[var(--fg)] border border-[var(--border)]"
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={submittingJob}
                  className="px-4 py-1.5 text-xs font-semibold rounded bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
                >
                  {submittingJob ? t("common.submitting") : t("jobs.newJob")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
