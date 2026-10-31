import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Crosshair, X, CheckCircle2, AlertTriangle, Plus } from "lucide-react";
import { apiClient } from "@/api/client";
import { TargetSetItem } from "@/api/types";

export interface AddToTargetSetModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedDeviceIds: number[];
  selectedDeviceNames: string[];
}

export const AddToTargetSetModal: React.FC<AddToTargetSetModalProps> = ({
  isOpen,
  onClose,
  selectedDeviceIds,
  selectedDeviceNames,
}) => {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"existing" | "new">("new");
  const [selectedSetId, setSelectedSetId] = useState<string>("");
  const [setName, setSetName] = useState<string>("");
  const [setDescription, setSetDescription] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: targetSets = [] } = useQuery<TargetSetItem[]>({
    queryKey: ["targetSets"],
    queryFn: () => apiClient.get<TargetSetItem[]>("/api/v1/devices/target-sets"),
    enabled: isOpen,
  });

  const mutation = useMutation({
    mutationFn: async () => {
      setErrorMsg(null);
      if (mode === "new") {
        if (!setName.trim()) throw new Error("Target set name is required");
        return apiClient.post("/api/v1/devices/target-sets", {
          name: setName.trim(),
          description: setDescription.trim(),
          device_ids: selectedDeviceIds,
          filter_criteria: { names: selectedDeviceNames },
        });
      } else {
        if (!selectedSetId) throw new Error("Please select a target set");
        const existing = targetSets.find((t) => String(t.id) === selectedSetId);
        const combinedIds = Array.from(new Set([...(existing?.device_ids || []), ...selectedDeviceIds]));
        return apiClient.put(`/api/v1/devices/target-sets/${selectedSetId}`, {
          device_ids: combinedIds,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["targetSets"] });
      setSuccessMsg(`Successfully added ${selectedDeviceIds.length} devices to target set.`);
      setTimeout(() => {
        onClose();
        setSuccessMsg(null);
      }, 1500);
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : "Failed to update target set");
    },
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-dialog border border-line bg-surface p-5 shadow-floating">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-signal" />
            <h3 className="text-sm font-semibold text-ink">Add to Target Set</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control p-1 text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 py-4 text-xs">
          <div className="rounded-control bg-surface-2 p-2.5 text-ink-2">
            Adding <span className="font-mono font-bold text-ink">{selectedDeviceIds.length}</span>{" "}
            selected devices into a reusable automation target group.
          </div>

          {/* Mode Selector */}
          <div className="flex rounded-control border border-line bg-surface-2 p-0.5">
            <button
              type="button"
              onClick={() => setMode("new")}
              className={`flex-1 rounded-control py-1 text-center font-medium transition-colors ${
                mode === "new" ? "bg-signal text-white" : "text-ink-2 hover:text-ink"
              }`}
            >
              New Target Set
            </button>
            <button
              type="button"
              onClick={() => setMode("existing")}
              disabled={targetSets.length === 0}
              className={`flex-1 rounded-control py-1 text-center font-medium transition-colors ${
                mode === "existing" ? "bg-signal text-white" : "text-ink-2 hover:text-ink"
              }`}
            >
              Existing ({targetSets.length})
            </button>
          </div>

          {mode === "new" ? (
            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium text-ink-2 mb-1">
                  Target Set Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Tehran_Core_Routers"
                  value={setName}
                  onChange={(e) => setSetName(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-ink-2 mb-1">
                  Description (optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Core PE routers for automated alarm checks"
                  value={setDescription}
                  onChange={(e) => setSetDescription(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                />
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">
                Select Target Set *
              </label>
              <select
                value={selectedSetId}
                onChange={(e) => setSelectedSetId(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="">-- Choose Target Set --</option>
                {targetSets.map((ts) => (
                  <option key={ts.id} value={ts.id}>
                    {ts.name} ({ts.device_ids?.length || 0} devices)
                  </option>
                ))}
              </select>
            </div>
          )}

          {errorMsg && (
            <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="flex items-center gap-2 rounded-control border border-ok/30 bg-ok/10 p-3 text-xs text-ok">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-line pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-medium text-white hover:bg-signal/90 disabled:opacity-50 transition-colors shadow-sm"
          >
            <Plus className="h-3 w-3" />
            <span>{mutation.isPending ? "Saving..." : "Save to Target Set"}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
