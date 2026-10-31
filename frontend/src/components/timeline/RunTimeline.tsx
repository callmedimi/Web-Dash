/**
 * RunTimeline Component — The Memorable Element of Web-Dash.
 * Live swimlane displaying each device as a row and each execution stage
 * (connect -> pre-check -> plan -> apply -> verify) as a real-time filling tick.
 * Virtualized to support 1,000+ devices with 'needs attention first' sorting.
 */
import React, { useState, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Minus,
  ArrowUpDown,
  Search,
} from "lucide-react";
import { usePrefsStore } from "@/store/prefs";
import { cn } from "@/utils/cn";

export type StepState = "pending" | "running" | "succeeded" | "failed" | "skipped";

export interface StepResult {
  state: StepState;
  durationMs?: number;
  detail?: string;
}

export type TimelineStepKey = "connect" | "pre_check" | "plan" | "apply" | "verify";

export interface DeviceTimelineRow {
  deviceId: string;
  deviceName: string;
  model?: string;
  site?: string;
  steps: Record<TimelineStepKey, StepResult>;
  overallStatus: "pending" | "running" | "succeeded" | "failed";
}

export type TimelineDeviceRow = DeviceTimelineRow;
export type TimelineStepDef = { id?: string; key?: TimelineStepKey; label: string };

export interface RunTimelineProps {
  devices?: DeviceTimelineRow[];
  items?: DeviceTimelineRow[];
  title?: string;
  steps?: TimelineStepDef[];
  selectedDeviceId?: string | null;
  onSelectDevice?: (deviceId: string) => void;
  height?: number | string;
  className?: string;
}

const STEP_DEFINITIONS: { key: TimelineStepKey; label: string }[] = [
  { key: "connect", label: "Connect" },
  { key: "pre_check", label: "Pre-Check" },
  { key: "plan", label: "Plan" },
  { key: "apply", label: "Apply" },
  { key: "verify", label: "Verify" },
];

export const RunTimeline: React.FC<RunTimelineProps> = ({
  devices,
  items,
  title = "Run Timeline",
  steps,
  selectedDeviceId,
  onSelectDevice,
  height,
  className,
}) => {
  const activeDevices = useMemo(() => devices ?? items ?? [], [devices, items]);
  const activeStepDefs = steps && steps.length > 0
    ? steps.map(s => ({ key: (s.key || s.id || "connect") as TimelineStepKey, label: s.label }))
    : STEP_DEFINITIONS;
  const { density } = usePrefsStore();
  const rowHeight = density === "compact" ? 32 : 40;

  const [sortMode, setSortMode] = useState<"attention" | "alphabetical">("attention");
  const [filterQuery, setFilterQuery] = useState("");

  const containerRef = useRef<HTMLDivElement>(null);

  // Sorting: attention first puts failed > running > pending > succeeded
  const sortedAndFiltered = useMemo(() => {
    let list = [...activeDevices];

    if (filterQuery.trim()) {
      const q = filterQuery.toLowerCase().trim();
      list = list.filter(
        (d) =>
          d.deviceName.toLowerCase().includes(q) ||
          d.site?.toLowerCase().includes(q) ||
          d.model?.toLowerCase().includes(q)
      );
    }

    if (sortMode === "attention") {
      const rank = (status: string) => {
        switch (status) {
          case "failed":
            return 1;
          case "running":
            return 2;
          case "pending":
            return 3;
          case "succeeded":
          default:
            return 4;
        }
      };
      list.sort((a, b) => rank(a.overallStatus) - rank(b.overallStatus));
    } else {
      list.sort((a, b) => a.deviceName.localeCompare(b.deviceName));
    }

    return list;
  }, [activeDevices, filterQuery, sortMode]);

  // Virtualizer for smooth 1,000 rows
  const rowVirtualizer = useVirtualizer({
    count: sortedAndFiltered.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => rowHeight,
    overscan: 20,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();

  const renderStepGlyph = (step: StepResult) => {
    const formatDuration = (ms?: number) => {
      if (ms === undefined) return "";
      return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
    };

    switch (step.state) {
      case "succeeded":
        return (
          <div
            title={`Succeeded ${formatDuration(step.durationMs)}`}
            className="flex h-5 w-5 items-center justify-center rounded-control bg-ok/15 text-ok"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
          </div>
        );
      case "failed":
        return (
          <div
            title={`Failed ${formatDuration(step.durationMs)}${step.detail ? `: ${step.detail}` : ""}`}
            className="flex h-5 w-5 items-center justify-center rounded-control bg-fault/15 text-fault"
          >
            <XCircle className="h-3.5 w-3.5" />
          </div>
        );
      case "running":
        return (
          <div
            title="Running..."
            className="flex h-5 w-5 items-center justify-center rounded-control bg-signal/15 text-signal"
          >
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-signal border-t-transparent" />
          </div>
        );
      case "skipped":
        return (
          <div
            title="Skipped"
            className="flex h-5 w-5 items-center justify-center rounded-control bg-surface-2 text-ink-2/60"
          >
            <Minus className="h-3.5 w-3.5" />
          </div>
        );
      case "pending":
      default:
        return (
          <div
            title="Queued"
            className="flex h-5 w-5 items-center justify-center rounded-control border border-line/60 bg-surface text-ink-2/40"
          >
            <Clock className="h-3 w-3" />
          </div>
        );
    }
  };

  return (
    <div
      style={height ? { height } : undefined}
      className={cn(
        "flex flex-1 flex-col overflow-hidden rounded-control border border-line bg-surface text-xs text-ink",
        className
      )}
    >
      {/* Timeline Header Toolbar */}
      <div className="flex h-10 flex-shrink-0 items-center justify-between border-b border-line bg-surface-2 px-3 gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-ink">{title}</span>
          <span className="text-[11px] font-mono text-ink-2">
            ({sortedAndFiltered.length.toLocaleString()} devices)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Quick Filter */}
          <div className="flex items-center gap-1.5 rounded-control border border-line bg-surface px-2 py-0.5">
            <Search className="h-3 w-3 text-ink-2" />
            <input
              type="text"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="Filter devices..."
              className="w-28 sm:w-36 bg-transparent text-[11px] text-ink placeholder-ink-2/60 outline-none font-mono"
            />
          </div>

          {/* Sort Switcher */}
          <button
            type="button"
            onClick={() =>
              setSortMode(sortMode === "attention" ? "alphabetical" : "attention")
            }
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-[11px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none"
          >
            <ArrowUpDown className="h-3 w-3" />
            <span>
              {sortMode === "attention" ? "Attention First" : "Alphabetical"}
            </span>
          </button>
        </div>
      </div>

      {/* Grid Headers: Device info + Step Columns */}
      <div className="flex h-8 flex-shrink-0 items-center border-b border-line bg-surface px-3 font-semibold text-[11px] text-ink-2 select-none">
        <div className="w-48 flex-shrink-0">Device</div>
        <div className="hidden sm:block w-24 flex-shrink-0 text-center">Status</div>
        <div className="flex flex-1 items-center justify-around">
          {activeStepDefs.map((s) => (
            <div key={s.key} className="w-16 text-center">
              {s.label}
            </div>
          ))}
        </div>
      </div>

      {/* Virtualized Swimlane Body */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-surface"
        style={{ willChange: "transform" }}
      >
        {sortedAndFiltered.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink-2">
            No devices matching timeline query.
          </div>
        ) : (
          <div
            style={{
              height: `${totalSize}px`,
              width: "100%",
              position: "relative",
            }}
          >
            {virtualRows.map((virtualRow) => {
              const row = sortedAndFiltered[virtualRow.index];
              const isSelected = selectedDeviceId === row.deviceId;

              return (
                <div
                  key={row.deviceId}
                  onClick={() => onSelectDevice?.(row.deviceId)}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  className={cn(
                    "flex items-center px-3 border-b border-line/40 transition-colors cursor-pointer select-none",
                    virtualRow.index % 2 === 0 ? "bg-surface" : "bg-surface-2/20",
                    isSelected && "bg-signal/15 border-l-2 border-l-signal",
                    "hover:bg-surface-2"
                  )}
                >
                  {/* Device Name & Site */}
                  <div className="w-48 flex-shrink-0 truncate flex flex-col justify-center">
                    <span className="font-mono text-xs font-semibold text-ink leading-tight truncate">
                      {row.deviceName}
                    </span>
                    {(row.model || row.site) && (
                      <span className="text-[10px] text-ink-2 leading-tight truncate">
                        {row.model} {row.site ? `• ${row.site}` : ""}
                      </span>
                    )}
                  </div>

                  {/* Overall Status Badge */}
                  <div className="hidden sm:flex w-24 flex-shrink-0 justify-center">
                    <span
                      className={cn(
                        "rounded-control px-1.5 py-0.2 text-[10px] font-mono uppercase font-semibold",
                        row.overallStatus === "succeeded" && "bg-ok/15 text-ok",
                        row.overallStatus === "failed" && "bg-fault/15 text-fault",
                        row.overallStatus === "running" && "bg-signal/15 text-signal",
                        row.overallStatus === "pending" && "bg-surface-2 text-ink-2"
                      )}
                    >
                      {row.overallStatus}
                    </span>
                  </div>

                  {/* Swimlane Step Glyphs */}
                  <div className="flex flex-1 items-center justify-around">
                    {activeStepDefs.map((stepDef) => (
                      <div key={stepDef.key} className="w-16 flex justify-center">
                        {renderStepGlyph(row.steps[stepDef.key])}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
