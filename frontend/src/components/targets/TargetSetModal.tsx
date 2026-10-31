import React, { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Crosshair,
  X,
  Layers,
  Search,
  Check,
  AlertTriangle,
  Save,
  Filter,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { TargetSetItem, DevicesListResponse } from "@/api/types";
import { Mono } from "@/components/ui/Mono";

export interface TargetSetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetSet?: TargetSetItem | null;
}

export const TargetSetModal: React.FC<TargetSetModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  targetSet,
}) => {
  const queryClient = useQueryClient();
  const isEdit = Boolean(targetSet);

  const [type, setType] = useState<"static" | "dynamic">("static");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<number[]>([]);
  const [deviceSearch, setDeviceSearch] = useState("");

  // Dynamic filter criteria
  const [filterProvince, setFilterProvince] = useState("all");
  const [filterRole, setFilterRole] = useState("all");
  const [filterOs, setFilterOs] = useState("all");
  const [filterTags, setFilterTags] = useState("");

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch all devices for static picker and dynamic preview
  const { data: devicesData } = useQuery<DevicesListResponse>({
    queryKey: ["allDevicesForTargetSets"],
    queryFn: () => apiClient.get<DevicesListResponse>("/api/v1/devices?limit=2000"),
    enabled: isOpen,
  });

  const devices = useMemo(() => devicesData?.devices || [], [devicesData?.devices]);

  // Initialize form when targetSet changes
  useEffect(() => {
    if (targetSet) {
      setName(targetSet.name);
      setDescription(targetSet.description || "");
      setSelectedDeviceIds(targetSet.device_ids || []);

      const criteria = targetSet.filter_criteria || {};
      const isDynamic = Boolean(
        criteria.province || criteria.role || criteria.os_family || criteria.tags
      );
      setType(isDynamic ? "dynamic" : "static");

      setFilterProvince((criteria.province as string) || "all");
      setFilterRole((criteria.role as string) || "all");
      setFilterOs((criteria.os_family as string) || "all");
      setFilterTags(Array.isArray(criteria.tags) ? criteria.tags.join(", ") : "");
    } else {
      setName("");
      setDescription("");
      setSelectedDeviceIds([]);
      setType("static");
      setFilterProvince("all");
      setFilterRole("all");
      setFilterOs("all");
      setFilterTags("");
    }
    setErrorMsg(null);
  }, [targetSet, isOpen]);

  // Dynamically matched devices preview
  const matchedDynamicDevices = useMemo(() => {
    if (type !== "dynamic") return [];
    return devices.filter((d) => {
      if (filterProvince !== "all" && d.province !== filterProvince) return false;
      if (filterRole !== "all" && d.role !== filterRole) return false;
      if (filterOs !== "all" && d.os_family !== filterOs) return false;
      if (filterTags.trim()) {
        const requiredTags = filterTags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean);
        const deviceTags = (d.tags || []).map((t) => t.toLowerCase());
        const hasTags = requiredTags.every((rt) => deviceTags.includes(rt));
        if (!hasTags) return false;
      }
      return true;
    });
  }, [devices, type, filterProvince, filterRole, filterOs, filterTags]);

  // Filtered devices for static selection
  const filteredStaticDevices = useMemo(() => {
    const q = deviceSearch.toLowerCase().trim();
    if (!q) return devices.slice(0, 50);
    return devices
      .filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          d.mgmt_ip.includes(q) ||
          (d.province && d.province.toLowerCase().includes(q))
      )
      .slice(0, 50);
  }, [devices, deviceSearch]);

  const toggleDeviceSelection = (id: number) => {
    setSelectedDeviceIds((prev) =>
      prev.includes(id) ? prev.filter((dId) => dId !== id) : [...prev, id]
    );
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error("Target set name is required");

      let payload: Record<string, unknown>;
      if (type === "static") {
        if (selectedDeviceIds.length === 0) {
          throw new Error("Please select at least one device for the static target set");
        }
        payload = {
          name: name.trim(),
          description: description.trim() || null,
          device_ids: selectedDeviceIds,
          filter_criteria: {},
        };
      } else {
        const criteria: Record<string, unknown> = {};
        if (filterProvince !== "all") criteria.province = filterProvince;
        if (filterRole !== "all") criteria.role = filterRole;
        if (filterOs !== "all") criteria.os_family = filterOs;
        if (filterTags.trim()) {
          criteria.tags = filterTags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);
        }

        payload = {
          name: name.trim(),
          description: description.trim() || null,
          device_ids: matchedDynamicDevices.map((d) => d.id),
          filter_criteria: criteria,
        };
      }

      if (isEdit && targetSet) {
        return apiClient.put(`/api/v1/devices/target-sets/${targetSet.id}`, payload);
      } else {
        return apiClient.post("/api/v1/devices/target-sets", payload);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["targetSets"] });
      onSuccess();
      onClose();
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save target set");
    },
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-dialog border border-line bg-surface p-5 shadow-floating flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-signal" />
            <h3 className="text-sm font-semibold text-ink">
              {isEdit ? `Edit Target Set: ${targetSet?.name}` : "Create Reusable Target Set"}
            </h3>
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

        {/* Form Body */}
        <div className="space-y-4 py-4 text-xs overflow-y-auto flex-1">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">
                Target Set Name *
              </label>
              <input
                type="text"
                placeholder="e.g. Tehran_PE_Routers"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">
                Description (optional)
              </label>
              <input
                type="text"
                placeholder="e.g. Tehran PE routers for automated changes"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>
          </div>

          {/* Type Toggle */}
          <div>
            <label className="block text-[11px] font-medium text-ink-2 mb-1.5">
              Target Selection Type
            </label>
            <div className="flex rounded-control border border-line bg-surface-2 p-0.5">
              <button
                type="button"
                onClick={() => setType("static")}
                className={`flex-1 rounded-control py-1.5 text-center font-medium transition-colors flex items-center justify-center gap-1.5 ${
                  type === "static" ? "bg-signal text-white" : "text-ink-2 hover:text-ink"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                <span>Static (Pick Devices)</span>
              </button>
              <button
                type="button"
                onClick={() => setType("dynamic")}
                className={`flex-1 rounded-control py-1.5 text-center font-medium transition-colors flex items-center justify-center gap-1.5 ${
                  type === "dynamic" ? "bg-signal text-white" : "text-ink-2 hover:text-ink"
                }`}
              >
                <Filter className="h-3.5 w-3.5" />
                <span>Dynamic Query (Rules)</span>
              </button>
            </div>
          </div>

          {/* Static Device Selector */}
          {type === "static" ? (
            <div className="space-y-2 border border-line rounded-control p-3 bg-surface-2/30">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-ink">
                  Selected Routers:{" "}
                  <span className="font-mono text-signal font-bold">
                    {selectedDeviceIds.length}
                  </span>
                </span>
                {selectedDeviceIds.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setSelectedDeviceIds([])}
                    className="text-[10px] text-ink-2 hover:text-ink underline"
                  >
                    Clear selection
                  </button>
                )}
              </div>

              {/* Search input for static device picker */}
              <div className="flex items-center gap-2 rounded-control border border-line bg-surface px-2.5 py-1">
                <Search className="h-3.5 w-3.5 text-ink-2" />
                <input
                  type="text"
                  placeholder="Filter routers by name, IP, province..."
                  value={deviceSearch}
                  onChange={(e) => setDeviceSearch(e.target.value)}
                  className="w-full bg-transparent text-xs text-ink placeholder-ink-2/60 focus:outline-none"
                />
              </div>

              {/* Devices Checkbox List */}
              <div className="max-h-48 overflow-y-auto space-y-1 rounded border border-line bg-surface p-1">
                {filteredStaticDevices.map((dev) => {
                  const isChecked = selectedDeviceIds.includes(dev.id);
                  return (
                    <div
                      key={dev.id}
                      onClick={() => toggleDeviceSelection(dev.id)}
                      className={`flex items-center justify-between p-1.5 rounded cursor-pointer transition-colors ${
                        isChecked ? "bg-signal/15 text-signal font-medium" : "hover:bg-surface-2"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`flex h-4 w-4 items-center justify-center rounded border ${
                            isChecked
                              ? "border-signal bg-signal text-white"
                              : "border-line bg-surface"
                          }`}
                        >
                          {isChecked && <Check className="h-3 w-3" />}
                        </div>
                        <Mono className="text-[11px]">{dev.name}</Mono>
                        <span className="font-mono text-[10px] text-ink-2">{dev.mgmt_ip}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px]">
                        <span className="font-mono text-ink-2">{dev.province || "--"}</span>
                        {dev.role && (
                          <span className="rounded bg-surface-2 px-1 text-[9px] font-mono uppercase text-ink-2 border border-line">
                            {dev.role}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Dynamic Query Builder */
            <div className="space-y-3 border border-line rounded-control p-3 bg-surface-2/30">
              <div className="grid grid-cols-3 gap-2.5">
                <div>
                  <label className="block text-[11px] text-ink-2 mb-1">Province</label>
                  <select
                    value={filterProvince}
                    onChange={(e) => setFilterProvince(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
                  >
                    <option value="all">All Provinces</option>
                    <option value="TEH">TEH (Tehran)</option>
                    <option value="ISF">ISF (Isfahan)</option>
                    <option value="FRS">FRS (Fars)</option>
                    <option value="KHO">KHO (Khorasan)</option>
                    <option value="KHZ">KHZ (Khuzestan)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-ink-2 mb-1">Role</label>
                  <select
                    value={filterRole}
                    onChange={(e) => setFilterRole(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
                  >
                    <option value="all">All Roles</option>
                    <option value="PE">PE</option>
                    <option value="P">P</option>
                    <option value="CORE">CORE</option>
                    <option value="AGG">AGG</option>
                    <option value="ACCESS">ACCESS</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] text-ink-2 mb-1">OS Family</label>
                  <select
                    value={filterOs}
                    onChange={(e) => setFilterOs(e.target.value)}
                    className="w-full rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
                  >
                    <option value="all">All OS</option>
                    <option value="vrp8">VRP8</option>
                    <option value="vrp5">VRP5</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[11px] text-ink-2 mb-1">
                  Required Tags (comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. core, mpls"
                  value={filterTags}
                  onChange={(e) => setFilterTags(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
                />
              </div>

              {/* Dynamic Live Result Counter */}
              <div className="flex items-center justify-between rounded-control bg-surface border border-line p-2 text-xs">
                <span className="text-ink-2">Dynamic query currently matches:</span>
                <span className="font-mono font-bold text-signal">
                  {matchedDynamicDevices.length} devices
                </span>
              </div>
            </div>
          )}

          {errorMsg && (
            <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
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
            <Save className="h-3 w-3" />
            <span>
              {mutation.isPending
                ? "Saving..."
                : isEdit
                ? "Update Target Set"
                : "Create Target Set"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};
