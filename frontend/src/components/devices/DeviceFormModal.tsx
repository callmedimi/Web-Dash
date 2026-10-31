import React, { useState } from "react";
import { Server, X, AlertTriangle, Save } from "lucide-react";
import { apiClient } from "@/api/client";
import { DeviceItem } from "@/api/types";

export interface DeviceFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  device?: DeviceItem | null;
}

export const DeviceFormModal: React.FC<DeviceFormModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  device,
}) => {
  const isEdit = Boolean(device);
  const [name, setName] = useState(device?.name || "");
  const [mgmtIp, setMgmtIp] = useState(device?.mgmt_ip || "");
  const [vendor, setVendor] = useState(device?.vendor || "huawei");
  const [osFamily, setOsFamily] = useState(device?.os_family || "vrp8");
  const [model, setModel] = useState(device?.model || "");
  const [role, setRole] = useState(device?.role || "PE");
  const [province, setProvince] = useState(device?.province || "TEH");
  const [site, setSite] = useState(device?.site || "");
  const [tagsStr, setTagsStr] = useState(device?.tags?.join(", ") || "");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !mgmtIp.trim()) {
      setErrorMsg("Device name and Management IP are required.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    const tags = tagsStr
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const payload = {
      name: name.trim(),
      mgmt_ip: mgmtIp.trim(),
      vendor,
      os_family: osFamily,
      model: model.trim() || null,
      role,
      province: province.trim() || null,
      site: site.trim() || null,
      tags,
    };

    try {
      if (isEdit && device) {
        await apiClient.put(`/api/v1/devices/${device.id}`, payload);
      } else {
        await apiClient.post("/api/v1/devices", payload);
      }
      onSuccess();
      onClose();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save device");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-dialog border border-line bg-surface p-5 shadow-floating">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-signal" />
            <h3 className="text-sm font-semibold text-ink">
              {isEdit ? `Edit Device: ${device?.name}` : "Add New Managed Device"}
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
        <form onSubmit={handleSubmit} className="space-y-3.5 py-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">
                Device Name *
              </label>
              <input
                type="text"
                required
                disabled={isEdit}
                placeholder="e.g. PE-TEH-01"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-mono text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none disabled:opacity-60"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">
                Management IP *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. 10.200.1.1"
                value={mgmtIp}
                onChange={(e) => setMgmtIp(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-mono text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">Vendor</label>
              <select
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="huawei">Huawei</option>
                <option value="cisco">Cisco</option>
                <option value="juniper">Juniper</option>
                <option value="generic">Generic</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">OS Family</label>
              <select
                value={osFamily}
                onChange={(e) => setOsFamily(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="vrp8">VRP8 (NetEngine 40E/8000)</option>
                <option value="vrp5">VRP5 (Legacy S/AR series)</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-signal focus:outline-none"
              >
                <option value="PE">PE (Provider Edge)</option>
                <option value="P">P (Core Transit)</option>
                <option value="CORE">CORE</option>
                <option value="AGG">AGG (Aggregation)</option>
                <option value="ACCESS">ACCESS</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">Model</label>
              <input
                type="text"
                placeholder="e.g. NetEngine 40E-X8"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">Province</label>
              <input
                type="text"
                placeholder="e.g. TEH"
                value={province}
                onChange={(e) => setProvince(e.target.value.toUpperCase())}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-mono uppercase text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-ink-2 mb-1">Site</label>
              <input
                type="text"
                placeholder="e.g. TEH-SITE-01"
                value={site}
                onChange={(e) => setSite(e.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-ink-2 mb-1">
              Tags (comma separated)
            </label>
            <input
              type="text"
              placeholder="e.g. core, mpls, backbone, high-priority"
              value={tagsStr}
              onChange={(e) => setTagsStr(e.target.value)}
              className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none"
            />
          </div>

          {errorMsg && (
            <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 border-t border-line pt-3 mt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-medium text-white hover:bg-signal/90 disabled:opacity-50 transition-colors shadow-sm"
            >
              <Save className="h-3 w-3" />
              <span>{isSubmitting ? "Saving..." : isEdit ? "Update Device" : "Create Device"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
