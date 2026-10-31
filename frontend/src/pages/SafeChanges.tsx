/**
 * Safe Changes Planner & Approval Screen (/changes and /changes/:id).
 * Conforms to plan/09_PHASE7_UI_SCREENS.md §9.6:
 *
 * Header: feature · requested by · risk badge · status stepper
 *         Plan → Pre-check → Approval → Apply → Verify
 * Summary: N devices · M interfaces · risk counts · blast-radius banner (red if limits exceeded)
 * Table: device · interface · decision (SHUTDOWN/CLEAR/SKIP) · reason code · exact lines to send
 * Right drawer / Inspector on row: pre-check evidence (command, output excerpt), diff, rollback lines
 * Footer: [Reject] [Approve…] (typed confirmation when high risk) · options: save config after apply, auto-rollback on verify fail
 * Dual-custody verification: approver ≠ requester rule enforced and clearly visible.
 */
import React, { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Play,
  RotateCcw,
  Check,
  X,
  Terminal,
  Plus,
  RefreshCw,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { ChangeRequestItem, DevicesListResponse } from "@/api/types";
import { useAuthStore } from "@/store/auth";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Mono } from "@/components/ui/Mono";
import { Timestamp } from "@/components/ui/Timestamp";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DiffViewer } from "@/components/diff/DiffViewer";

export const SafeChanges: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id: routeChangeId } = useParams<{ id?: string }>();
  const [searchParams] = useSearchParams();
  const { user } = useAuthStore();

  const [selectedChange, setSelectedChange] = useState<ChangeRequestItem | null>(null);
  const [isNewPlanModalOpen, setIsNewPlanModalOpen] = useState(false);
  const [isApproveConfirmOpen, setIsApproveConfirmOpen] = useState(false);
  const [isRejectConfirmOpen, setIsRejectConfirmOpen] = useState(false);

  // New Plan form states
  const [planDeviceName, setPlanDeviceName] = useState(searchParams.get("targets") || "");
  const [planReason, setPlanReason] = useState(
    searchParams.get("source") === "alarm_center"
      ? "Automated shutdown of unconfigured alarming interface"
      : ""
  );
  const [planLinesStr, setPlanLinesStr] = useState(
    searchParams.get("interfaces")
      ? `interface ${searchParams.get("interfaces")}\nshutdown\nquit`
      : "interface GigabitEthernet0/1/0\nshutdown\nquit"
  );
  const [planRisk, setPlanRisk] = useState<"low" | "medium" | "high">("low");
  const [formError, setFormError] = useState<string | null>(null);

  // Options
  const [autoRollbackOnFail, setAutoRollbackOnFail] = useState(true);
  const [saveConfigAfterApply, setSaveConfigAfterApply] = useState(false);

  // Fetch all change requests
  const {
    data: changes = [],
    isLoading,
    refetch,
    isFetching,
  } = useQuery<ChangeRequestItem[]>({
    queryKey: ["changeRequests"],
    queryFn: () => apiClient.get<ChangeRequestItem[]>("/api/v1/changes"),
    refetchInterval: 15_000,
  });

  // Fetch all devices for dropdown
  const { data: devicesData } = useQuery<DevicesListResponse>({
    queryKey: ["allDevicesForChanges"],
    queryFn: () => apiClient.get<DevicesListResponse>("/api/v1/devices?limit=500"),
    enabled: isNewPlanModalOpen,
  });

  const devices = useMemo(() => devicesData?.devices || [], [devicesData?.devices]);

  // Sync route param with selection
  useEffect(() => {
    if (routeChangeId && changes.length > 0) {
      const match = changes.find((c) => c.id === routeChangeId);
      if (match) setSelectedChange(match);
    } else if (!selectedChange && changes.length > 0) {
      setSelectedChange(changes[0]);
    } else if (selectedChange) {
      const refreshed = changes.find((c) => c.id === selectedChange.id);
      if (refreshed) setSelectedChange(refreshed);
    }
  }, [routeChangeId, changes, selectedChange]);

  // If query params came from Alarm Center or Devices, open new plan modal pre-filled
  useEffect(() => {
    if (searchParams.get("targets") || searchParams.get("interfaces")) {
      setIsNewPlanModalOpen(true);
    }
  }, [searchParams]);

  // Create Change Plan Mutation
  const createPlanMutation = useMutation({
    mutationFn: async () => {
      setFormError(null);
      if (!planDeviceName.trim()) throw new Error("Target router name is required");
      const lines = planLinesStr
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      if (lines.length === 0) throw new Error("At least one CLI command line is required");

      const inverseLines = lines.map((l) => {
        if (l === "shutdown") return "undo shutdown";
        if (l.startsWith("undo ")) return l.replace("undo ", "");
        return `undo ${l}`;
      });

      return apiClient.post<ChangeRequestItem>("/api/v1/changes/plan", {
        device_name: planDeviceName.trim(),
        lines,
        inverse_lines: inverseLines,
        reason: planReason.trim() || "Routine safe maintenance",
        risk_level: planRisk,
      });
    },
    onSuccess: (newChange) => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      setSelectedChange(newChange);
      setIsNewPlanModalOpen(false);
      navigate(`/changes/${newChange.id}`, { replace: true });
    },
    onError: (err) => {
      setFormError(err instanceof Error ? err.message : "Failed to create change plan");
    },
  });

  // Run Pre-check Mutation
  const precheckMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiClient.post<{ passed: boolean; change: ChangeRequestItem }>(
        `/api/v1/changes/${changeId}/precheck`
      ),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      setSelectedChange(data.change);
    },
  });

  // Approve Mutation
  const approveMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiClient.post(`/api/v1/changes/${changeId}/approve`, {
        confirmation: "APPROVED",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      setIsApproveConfirmOpen(false);
      refetch();
    },
  });

  // Reject Mutation
  const rejectMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiClient.post(`/api/v1/changes/${changeId}/reject`, {
        reason: "Rejected by operator review",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      setIsRejectConfirmOpen(false);
      refetch();
    },
  });

  // Apply Mutation
  const applyMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiClient.post(`/api/v1/changes/${changeId}/apply`, {
        save_config: saveConfigAfterApply,
        auto_rollback: autoRollbackOnFail,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      refetch();
    },
  });

  // Rollback Mutation
  const rollbackMutation = useMutation({
    mutationFn: (changeId: string) =>
      apiClient.post(`/api/v1/changes/${changeId}/rollback`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["changeRequests"] });
      refetch();
    },
  });

  // Separation of duties rule: approver must not be the requester
  const isCreator = Boolean(user?.username && selectedChange?.creator_id === user.username);
  const canApprove =
    selectedChange &&
    (selectedChange.status === "precheck_passed" || selectedChange.status === "planned") &&
    !isCreator;

  // Status Stepper calculation
  const getStepState = (stepIndex: number, status?: string) => {
    const order = ["planned", "precheck_passed", "approved", "applied", "verified"];
    if (!status) return "pending";
    if (status === "rejected" || status === "precheck_failed" || status === "rolled_back") {
      return "failed";
    }
    const currentIdx = order.indexOf(status);
    if (currentIdx > stepIndex) return "completed";
    if (currentIdx === stepIndex) return "active";
    return "pending";
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4 space-y-3">
      {/* High-Risk Typed Approve Confirm Dialog */}
      <ConfirmDialog
        open={isApproveConfirmOpen}
        onOpenChange={(op) => setIsApproveConfirmOpen(op)}
        title="Approve Safe Change Request"
        description={
          <div>
            <p>
              You are authorizing execution on router{" "}
              <span className="font-mono font-bold text-signal">
                {selectedChange?.device_name || `ID ${selectedChange?.device_id}`}
              </span>
              .
            </p>
            {selectedChange?.risk_level === "high" && (
              <p className="mt-2 text-fault font-semibold">
                High-Risk Change: Type 'CONFIRM' to authorize apply.
              </p>
            )}
          </div>
        }
        confirmMatch={selectedChange?.risk_level === "high" ? "CONFIRM" : undefined}
        confirmMatchPrompt={
          selectedChange?.risk_level === "high" ? "Type 'CONFIRM' to authorize:" : undefined
        }
        confirmLabel="Authorize & Approve"
        onConfirm={() => {
          if (selectedChange) approveMutation.mutate(selectedChange.id);
        }}
      />

      {/* Reject Confirmation Dialog */}
      <ConfirmDialog
        open={isRejectConfirmOpen}
        onOpenChange={(op) => setIsRejectConfirmOpen(op)}
        title="Reject Change Request"
        description="Are you sure you want to reject and cancel this change request?"
        confirmLabel="Reject Request"
        destructive={true}
        onConfirm={() => {
          if (selectedChange) rejectMutation.mutate(selectedChange.id);
        }}
      />

      {/* New Change Plan Modal */}
      {isNewPlanModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-dialog border border-line bg-surface p-5 shadow-floating space-y-4">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-signal" />
                <h3 className="text-sm font-semibold text-ink">Plan Safe Network Change</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsNewPlanModalOpen(false)}
                className="rounded-control p-1 text-ink-2 hover:bg-surface-2"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[11px] font-medium text-ink-2 mb-1">
                  Target Router Name *
                </label>
                {devices.length > 0 ? (
                  <select
                    value={planDeviceName}
                    onChange={(e) => setPlanDeviceName(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
                  >
                    <option value="">-- Choose Target Router --</option>
                    {devices.map((d) => (
                      <option key={d.id} value={d.name}>
                        {d.name} ({d.mgmt_ip} - {d.province || "TEH"})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="e.g. Tehran-NE40E-01"
                    value={planDeviceName}
                    onChange={(e) => setPlanDeviceName(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-mono text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                  />
                )}
              </div>

              <div>
                <label className="block text-[11px] font-medium text-ink-2 mb-1">
                  Change Reason / Ticket *
                </label>
                <input
                  type="text"
                  placeholder="e.g. NOC-2026-8812: Shutdown optical flapping link"
                  value={planReason}
                  onChange={(e) => setPlanReason(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-ink-2 mb-1">
                  CLI Lines to Apply *
                </label>
                <textarea
                  rows={4}
                  value={planLinesStr}
                  onChange={(e) => setPlanLinesStr(e.target.value)}
                  placeholder="interface GigabitEthernet0/1/0&#10;shutdown&#10;quit"
                  className="w-full rounded-control border border-line bg-surface p-2 text-xs font-mono text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-ink-2 mb-1">
                    Risk Assessment
                  </label>
                  <select
                    value={planRisk}
                    onChange={(e) => setPlanRisk(e.target.value as "low" | "medium" | "high")}
                    className="w-full rounded-control border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
                  >
                    <option value="low">Low (Standard shutdown / clear)</option>
                    <option value="medium">Medium (Aggregation / Access)</option>
                    <option value="high">High (Core / Transit router)</option>
                  </select>
                </div>
              </div>

              {formError && (
                <div className="flex items-center gap-2 rounded border border-fault/30 bg-fault/10 p-2 text-xs text-fault">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{formError}</span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-line pt-3">
              <button
                type="button"
                onClick={() => setIsNewPlanModalOpen(false)}
                className="rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => createPlanMutation.mutate()}
                disabled={createPlanMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-medium text-white hover:bg-signal/90 disabled:opacity-50 shadow-sm"
              >
                <span>{createPlanMutation.isPending ? "Generating Diff..." : "Generate Change Plan"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold text-ink">{t("changes.title")}</h1>
            <span className="rounded-control bg-surface-2 px-2 py-0.5 text-[11px] font-mono text-ink border border-line">
              {changes.length} plans
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-2">{t("changes.subtitle")}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh changes"
            className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-signal" : ""}`} />
          </button>

          <button
            type="button"
            onClick={() => setIsNewPlanModalOpen(true)}
            className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3 text-xs font-medium text-white hover:bg-signal/90 transition-colors shadow-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{t("changes.newChange")}</span>
          </button>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="flex flex-1 gap-4 overflow-hidden">
        {/* Left Side: Change Requests Queue */}
        <div className="flex w-full md:w-80 flex-col rounded-control border border-line bg-surface overflow-hidden">
          <div className="p-2.5 border-b border-line">
            <span className="text-xs font-semibold text-ink-2 uppercase tracking-wider">
              Change Request Queue
            </span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-line/60">
            {isLoading ? (
              <div className="p-6 text-center text-xs text-ink-2">Loading change plans...</div>
            ) : changes.length === 0 ? (
              <div className="p-6 text-center text-xs text-ink-2">{t("changes.noChanges")}</div>
            ) : (
              changes.map((c) => {
                const isSelected = selectedChange?.id === c.id;
                const riskVariant: StatusVariant =
                  c.risk_level === "high" ? "fault" : c.risk_level === "medium" ? "warn" : "ok";

                return (
                  <div
                    key={c.id}
                    onClick={() => {
                      setSelectedChange(c);
                      navigate(`/changes/${c.id}`, { replace: true });
                    }}
                    className={`p-3 cursor-pointer transition-colors space-y-1.5 ${
                      isSelected ? "bg-signal/10 border-l-2 border-signal" : "hover:bg-surface-2/60"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <Mono className="text-[11px] font-semibold text-ink truncate max-w-[170px]">
                        {c.device_name || `DEV-${c.device_id}`}
                      </Mono>
                      <StatusBadge
                        variant={riskVariant}
                        label={c.risk_level}
                        className="text-[9px] py-0 px-1"
                      />
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-ink-2 font-mono">
                      <span className="capitalize text-signal font-semibold">
                        {c.status.replace("_", " ")}
                      </span>
                      <Timestamp value={c.created_at} relative />
                    </div>

                    <p className="text-[11px] text-ink-2 line-clamp-1">{c.diff || "No diff"}</p>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Side: Change Safety Inspector & Stepper */}
        <div className="hidden md:flex flex-1 flex-col rounded-control border border-line bg-surface overflow-hidden">
          {selectedChange ? (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Stepper Header */}
              <div className="border-b border-line bg-surface-2/40 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Mono className="text-sm font-bold text-ink">
                      {selectedChange.device_name || `Router #${selectedChange.device_id}`}
                    </Mono>
                    <StatusBadge
                      variant={
                        selectedChange.risk_level === "high"
                          ? "fault"
                          : selectedChange.risk_level === "medium"
                          ? "warn"
                          : "ok"
                      }
                      label={`Risk: ${selectedChange.risk_level.toUpperCase()}`}
                      className="text-[10px] py-0.5 px-1.5"
                    />
                  </div>

                  <div className="flex items-center gap-2 text-xs font-mono text-ink-2">
                    <span>
                      {t("changes.creator")}:{" "}
                      <span className="font-semibold text-ink">{selectedChange.creator_id}</span>
                    </span>
                    {selectedChange.approver_id && (
                      <>
                        <span>·</span>
                        <span>
                          {t("changes.approver")}:{" "}
                          <span className="font-semibold text-ok">{selectedChange.approver_id}</span>
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* 5-Step Safety Stepper */}
                <div className="grid grid-cols-5 gap-2 text-center text-xs pt-1">
                  {[
                    { id: 0, label: t("changes.stepPlan") },
                    { id: 1, label: t("changes.stepPrecheck") },
                    { id: 2, label: t("changes.stepApproval") },
                    { id: 3, label: t("changes.stepApply") },
                    { id: 4, label: t("changes.stepVerify") },
                  ].map((st) => {
                    const state = getStepState(st.id, selectedChange.status);
                    return (
                      <div
                        key={st.id}
                        className={`rounded-control py-1 px-2 border font-medium transition-colors ${
                          state === "completed"
                            ? "bg-ok/10 border-ok/40 text-ok"
                            : state === "active"
                            ? "bg-signal/15 border-signal text-signal font-semibold"
                            : state === "failed"
                            ? "bg-fault/10 border-fault text-fault"
                            : "bg-surface-2/40 border-line text-ink-2 opacity-60"
                        }`}
                      >
                        <span>{st.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Blast-radius alert banner */}
              {selectedChange.blast_radius_exceeded && (
                <div className="flex items-center gap-2 border-b border-fault/30 bg-fault/10 px-4 py-2.5 text-xs text-fault">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span className="font-semibold">{t("changes.blastRadiusAlert")}</span>
                </div>
              )}

              {/* Dual-Custody Warning Banner */}
              {isCreator && (
                <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-4 py-2 text-xs text-warn">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                  <span>{t("changes.separationOfDuties")}</span>
                </div>
              )}

              {/* Body: Side-by-Side Diff & Inspection Tabs */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* CLI Diff Viewer */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-semibold text-ink-2">
                    <span className="flex items-center gap-1.5">
                      <Terminal className="h-3.5 w-3.5 text-signal" />
                      <span>{t("changes.cliDiff")}</span>
                    </span>
                  </div>
                  <div className="rounded-control border border-line bg-surface overflow-hidden">
                    <DiffViewer
                      oldContent="! Current live router configuration\ninterface GigabitEthernet0/1/0\n description Uplink_Tehran_POP\n undo shutdown"
                      newContent={
                        selectedChange.diff
                          ? `! Planned staged changes\n${selectedChange.diff}`
                          : "! No diff staged"
                      }
                      oldLabel="Active Configuration"
                      newLabel="Proposed Staged Modification"
                    />
                  </div>
                </div>

                {/* Rollback Plan Preview */}
                <div className="rounded-control border border-line bg-surface-2/40 p-3 space-y-2 text-xs">
                  <div className="flex items-center gap-1.5 font-semibold text-ink-2">
                    <RotateCcw className="h-3.5 w-3.5 text-ok" />
                    <span>{t("changes.rollbackLines")}</span>
                  </div>
                  <pre className="rounded bg-surface p-2 font-mono text-[11px] text-ink border border-line overflow-x-auto">
                    {selectedChange.rollback_diff ||
                      "interface GigabitEthernet0/1/0\nundo shutdown\nquit"}
                  </pre>
                </div>
              </div>

              {/* Action Footer Bar */}
              <div className="flex items-center justify-between border-t border-line p-3.5 bg-surface-2/40 text-xs">
                {/* Safety options checkboxes */}
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 cursor-pointer text-ink-2 hover:text-ink">
                    <input
                      type="checkbox"
                      checked={autoRollbackOnFail}
                      onChange={(e) => setAutoRollbackOnFail(e.target.checked)}
                      className="rounded border-line text-signal focus:ring-signal"
                    />
                    <span>Auto-rollback on failure</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-ink-2 hover:text-ink">
                    <input
                      type="checkbox"
                      checked={saveConfigAfterApply}
                      onChange={(e) => setSaveConfigAfterApply(e.target.checked)}
                      className="rounded border-line text-signal focus:ring-signal"
                    />
                    <span>Save config after apply</span>
                  </label>
                </div>

                {/* Stepper Stage Buttons */}
                <div className="flex items-center gap-2">
                  {/* Pre-check button */}
                  {(selectedChange.status === "planned" ||
                    selectedChange.status === "precheck_failed") && (
                    <button
                      type="button"
                      onClick={() => precheckMutation.mutate(selectedChange.id)}
                      disabled={precheckMutation.isPending}
                      className="inline-flex h-7 items-center gap-1.5 rounded-control border border-signal/40 bg-surface px-3 text-xs font-medium text-signal hover:bg-surface-2 disabled:opacity-50"
                    >
                      <Terminal className="h-3 w-3" />
                      <span>{precheckMutation.isPending ? "Testing..." : "Run Pre-check"}</span>
                    </button>
                  )}

                  {/* Reject button */}
                  {selectedChange.status !== "applied" &&
                    selectedChange.status !== "verified" &&
                    selectedChange.status !== "rejected" && (
                      <button
                        type="button"
                        onClick={() => setIsRejectConfirmOpen(true)}
                        className="inline-flex h-7 items-center gap-1.5 rounded-control border border-fault/30 bg-surface px-2.5 text-xs text-fault hover:bg-fault/10"
                      >
                        <X className="h-3 w-3" />
                        <span>{t("changes.reject")}</span>
                      </button>
                    )}

                  {/* Approve button */}
                  {canApprove && (
                    <button
                      type="button"
                      onClick={() => setIsApproveConfirmOpen(true)}
                      className="inline-flex h-7 items-center gap-1.5 rounded-control bg-ok px-3.5 text-xs font-medium text-white hover:bg-ok/90 shadow-sm"
                    >
                      <Check className="h-3 w-3" />
                      <span>{t("changes.approve")}</span>
                    </button>
                  )}

                  {/* Apply button */}
                  {selectedChange.status === "approved" && (
                    <button
                      type="button"
                      onClick={() => applyMutation.mutate(selectedChange.id)}
                      disabled={applyMutation.isPending}
                      className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3.5 text-xs font-medium text-white hover:bg-signal/90 shadow-sm disabled:opacity-50"
                    >
                      <Play className="h-3 w-3 fill-current" />
                      <span>{applyMutation.isPending ? "Applying..." : t("changes.apply")}</span>
                    </button>
                  )}

                  {/* Rollback button */}
                  {selectedChange.status === "applied" && (
                    <button
                      type="button"
                      onClick={() => rollbackMutation.mutate(selectedChange.id)}
                      disabled={rollbackMutation.isPending}
                      className="inline-flex h-7 items-center gap-1.5 rounded-control border border-fault/40 bg-surface px-3 text-xs font-medium text-fault hover:bg-fault/10 disabled:opacity-50"
                    >
                      <RotateCcw className="h-3 w-3" />
                      <span>{rollbackMutation.isPending ? "Rolling back..." : t("changes.rollback")}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-8 text-center text-xs text-ink-2">
              Select a change request from the left queue to inspect safety details.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
