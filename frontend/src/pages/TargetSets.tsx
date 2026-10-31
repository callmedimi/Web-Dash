/**
 * Target Sets Management Screen (/targets).
 * Conforms to plan/09_PHASE7_UI_SCREENS.md §9.4:
 * Named, reusable device sets: static (pick devices) or dynamic (query: province = TEH AND tag = PE AND not in maintenance).
 * Preview count + list. Used as the "targets" input in every job form.
 */
import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Crosshair,
  Plus,
  Search,
  Layers,
  Filter,
  Trash2,
  Edit2,
  Play,
  Server,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { TargetSetItem, DeviceItem } from "@/api/types";
import { StatusBadge, StatusVariant } from "@/components/ui/StatusBadge";
import { Mono } from "@/components/ui/Mono";
import { Timestamp } from "@/components/ui/Timestamp";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { TargetSetModal } from "@/components/targets/TargetSetModal";

interface ResolvedTargetSetData {
  target_set: TargetSetItem;
  count: number;
  devices: DeviceItem[];
}

export const TargetSets: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [selectedSet, setSelectedSet] = useState<TargetSetItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSet, setEditingSet] = useState<TargetSetItem | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);

  // Fetch target sets
  const {
    data: targetSets = [],
    isLoading,
    refetch,
    isFetching,
  } = useQuery<TargetSetItem[]>({
    queryKey: ["targetSets"],
    queryFn: () => apiClient.get<TargetSetItem[]>("/api/v1/devices/target-sets"),
  });

  // Filtered target sets
  const filteredSets = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return targetSets;
    return targetSets.filter(
      (ts) =>
        ts.name.toLowerCase().includes(q) ||
        (ts.description && ts.description.toLowerCase().includes(q))
    );
  }, [targetSets, search]);

  // Set initial selected set if none selected
  React.useEffect(() => {
    if (!selectedSet && filteredSets.length > 0) {
      setSelectedSet(filteredSets[0]);
    } else if (selectedSet) {
      // update selectedSet reference if refreshed
      const updated = filteredSets.find((ts) => ts.id === selectedSet.id);
      if (updated) setSelectedSet(updated);
    }
  }, [filteredSets, selectedSet]);

  // Fetch resolved devices for currently selected target set
  const { data: resolvedData, isLoading: isLoadingResolved } =
    useQuery<ResolvedTargetSetData>({
      queryKey: ["targetSetDevices", selectedSet?.id],
      queryFn: () =>
        apiClient.get<ResolvedTargetSetData>(
          `/api/v1/devices/target-sets/${selectedSet?.id}/devices`
        ),
      enabled: Boolean(selectedSet?.id),
    });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/v1/devices/target-sets/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["targetSets"] });
      setDeleteTargetId(null);
      if (selectedSet?.id === deleteTargetId) {
        setSelectedSet(null);
      }
    },
  });

  const isDynamicSet = (ts: TargetSetItem) => {
    const crit = ts.filter_criteria || {};
    return Boolean(crit.province || crit.role || crit.os_family || crit.tags);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4 space-y-3">
      {/* Create / Edit Modal */}
      <TargetSetModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingSet(null);
        }}
        onSuccess={() => refetch()}
        targetSet={editingSet}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteTargetId !== null}
        onOpenChange={(op) => {
          if (!op) setDeleteTargetId(null);
        }}
        onConfirm={() => {
          if (deleteTargetId !== null) deleteMutation.mutate(deleteTargetId);
        }}
        title="Delete Target Set"
        description="Are you sure you want to permanently delete this target set? Any saved references will be removed."
        confirmLabel="Delete"
        destructive={true}
      />

      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold text-ink">{t("targets.title")}</h1>
            <span className="rounded-control bg-surface-2 px-2 py-0.5 text-[11px] font-mono text-ink border border-line">
              {targetSets.length} sets
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-2">{t("targets.subtitle")}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh target sets"
            className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin text-signal" : ""}`} />
          </button>

          <button
            type="button"
            onClick={() => {
              setEditingSet(null);
              setIsModalOpen(true);
            }}
            className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3 text-xs font-medium text-white hover:bg-signal/90 transition-colors shadow-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{t("targets.createTargetSet")}</span>
          </button>
        </div>
      </div>

      {/* Main Split View Container */}
      <div className="flex flex-1 gap-4 overflow-hidden">
        {/* Left List Column */}
        <div className="flex w-full md:w-96 flex-col rounded-control border border-line bg-surface overflow-hidden">
          {/* Search Box */}
          <div className="p-2.5 border-b border-line">
            <div className="flex items-center gap-2 rounded-control border border-line bg-surface-2/60 px-2.5 py-1 focus-within:ring-1 focus-within:ring-signal text-xs">
              <Search className="h-3.5 w-3.5 text-ink-2" />
              <input
                type="text"
                placeholder={t("targets.searchPlaceholder")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-transparent text-xs text-ink placeholder-ink-2/60 focus:outline-none"
              />
            </div>
          </div>

          {/* Sets List */}
          <div className="flex-1 overflow-y-auto divide-y divide-line/60">
            {isLoading ? (
              <div className="p-6 text-center text-xs text-ink-2">Loading target sets...</div>
            ) : filteredSets.length === 0 ? (
              <div className="p-6 text-center text-xs text-ink-2">
                {t("targets.noTargetSets")}
              </div>
            ) : (
              filteredSets.map((ts) => {
                const isSelected = selectedSet?.id === ts.id;
                const dynamic = isDynamicSet(ts);
                const count = ts.device_ids?.length || 0;

                return (
                  <div
                    key={ts.id}
                    onClick={() => setSelectedSet(ts)}
                    className={`flex items-start justify-between p-3.5 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-signal/10 border-l-2 border-signal"
                        : "hover:bg-surface-2/60"
                    }`}
                  >
                    <div className="space-y-1 min-w-0 pr-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-ink truncate">
                          {ts.name}
                        </span>
                        {dynamic ? (
                          <span className="inline-flex items-center gap-1 rounded bg-signal/15 px-1.5 py-0.2 text-[9px] font-mono font-medium text-signal">
                            <Filter className="h-2.5 w-2.5" />
                            <span>{t("targets.dynamic")}</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded bg-surface-2 px-1.5 py-0.2 text-[9px] font-mono font-medium text-ink-2 border border-line">
                            <Layers className="h-2.5 w-2.5" />
                            <span>{t("targets.static")}</span>
                          </span>
                        )}
                      </div>

                      {ts.description && (
                        <p className="text-[11px] text-ink-2 line-clamp-1">{ts.description}</p>
                      )}

                      <div className="flex items-center gap-2 text-[10px] text-ink-2 font-mono pt-0.5">
                        <span className="text-signal font-semibold">
                          {t("targets.deviceCount", { count })}
                        </span>
                        <span>·</span>
                        <Timestamp value={ts.updated_at || ts.created_at} relative />
                      </div>
                    </div>

                    <ChevronRight className="h-4 w-4 text-ink-2 shrink-0 self-center" />
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Preview Column */}
        <div className="hidden md:flex flex-1 flex-col rounded-control border border-line bg-surface overflow-hidden">
          {selectedSet ? (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Target Set Preview Header */}
              <div className="flex items-center justify-between border-b border-line p-4 bg-surface-2/30">
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-control bg-signal/10 text-signal border border-signal/30">
                      <Crosshair className="h-4 w-4" />
                    </div>
                    <div>
                      <h2 className="text-sm font-bold text-ink">{selectedSet.name}</h2>
                      <div className="flex items-center gap-2 text-[11px] text-ink-2">
                        <span>
                          {isDynamicSet(selectedSet) ? t("targets.dynamic") : t("targets.static")}
                        </span>
                        <span>·</span>
                        <span className="font-mono text-signal font-semibold">
                          {resolvedData?.count ?? selectedSet.device_ids?.length ?? 0} devices
                        </span>
                      </div>
                    </div>
                  </div>
                  {selectedSet.description && (
                    <p className="text-xs text-ink-2 pt-1">{selectedSet.description}</p>
                  )}
                </div>

                {/* Target Set Actions */}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const devNames = (resolvedData?.devices || []).map((d) => d.name);
                      navigate(
                        `/changes?targets=${encodeURIComponent(
                          devNames.length > 0 ? devNames.join(",") : selectedSet.name
                        )}`
                      );
                    }}
                    className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3 text-xs font-medium text-white hover:bg-signal/90 transition-colors shadow-sm"
                  >
                    <Play className="h-3 w-3 fill-current" />
                    <span>{t("targets.runJob")}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setEditingSet(selectedSet);
                      setIsModalOpen(true);
                    }}
                    className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
                  >
                    <Edit2 className="h-3 w-3" />
                    <span>{t("targets.edit")}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDeleteTargetId(selectedSet.id)}
                    className="inline-flex h-7 items-center gap-1.5 rounded-control border border-fault/30 bg-surface px-2 text-xs text-fault hover:bg-fault/10 transition-colors"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>

              {/* Dynamic Query Rules Banner (if dynamic) */}
              {isDynamicSet(selectedSet) && (
                <div className="border-b border-line bg-surface-2/50 px-4 py-2.5 flex items-center gap-3 text-xs">
                  <span className="font-semibold text-ink-2">Query Criteria:</span>
                  <div className="flex flex-wrap gap-1.5">
                    {Boolean(selectedSet.filter_criteria?.province) && (
                      <span className="rounded bg-surface px-2 py-0.5 text-[10px] font-mono border border-line text-ink">
                        Province = {String(selectedSet.filter_criteria.province)}
                      </span>
                    )}
                    {Boolean(selectedSet.filter_criteria?.role) && (
                      <span className="rounded bg-surface px-2 py-0.5 text-[10px] font-mono border border-line text-ink">
                        Role = {String(selectedSet.filter_criteria.role)}
                      </span>
                    )}
                    {Boolean(selectedSet.filter_criteria?.os_family) && (
                      <span className="rounded bg-surface px-2 py-0.5 text-[10px] font-mono border border-line text-ink">
                        OS = {String(selectedSet.filter_criteria.os_family)}
                      </span>
                    )}
                    {Array.isArray(selectedSet.filter_criteria?.tags) &&
                      selectedSet.filter_criteria.tags.map((tg: string) => (
                        <span
                          key={tg}
                          className="rounded bg-surface px-2 py-0.5 text-[10px] font-mono border border-line text-signal"
                        >
                          Tag = {tg}
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {/* Resolved Devices Table / List */}
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-ink-2 pb-1">
                  <span>{t("targets.resolvedDevices")}</span>
                  <span className="font-mono">
                    {resolvedData?.count ?? 0} matches
                  </span>
                </div>

                {isLoadingResolved ? (
                  <div className="py-8 text-center text-xs text-ink-2">
                    Resolving matched routers...
                  </div>
                ) : (resolvedData?.devices || []).length === 0 ? (
                  <div className="py-8 text-center text-xs text-ink-2">
                    No routers currently matched by this target set criteria.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                    {resolvedData?.devices.map((dev) => {
                      const healthVariant: StatusVariant =
                        dev.health_status === "up"
                          ? "ok"
                          : dev.health_status === "degraded"
                          ? "warn"
                          : dev.health_status === "down"
                          ? "fault"
                          : "info-muted";

                      return (
                        <div
                          key={dev.id}
                          className="flex items-center justify-between p-2.5 rounded-control border border-line bg-surface-2/40 hover:border-signal/40 transition-colors"
                        >
                          <div className="space-y-0.5 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <Server className="h-3 w-3 text-signal shrink-0" />
                              <Mono className="text-xs font-semibold truncate">
                                {dev.name}
                              </Mono>
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] font-mono text-ink-2">
                              <span>{dev.mgmt_ip}</span>
                              {dev.province && <span>· {dev.province}</span>}
                              {dev.role && <span>· {dev.role}</span>}
                            </div>
                          </div>

                          <StatusBadge
                            variant={healthVariant}
                            label={dev.health_status}
                            className="text-[9px] py-0 px-1"
                          />
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-8 text-center text-xs text-ink-2">
              {t("targets.selectToPreview")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
