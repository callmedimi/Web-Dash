/**
 * Virtualized LogViewer Component for live streaming and static inspection.
 * Capable of rendering up to 200,000 log lines with follow-tail, level filtering,
 * regex search, device chips, and copy/download controls.
 */
import React, { useState, useRef, useEffect, useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Search,
  Download,
  Copy,
  Check,
  Activity,
} from "lucide-react";
import { JobEvent, EventLevel } from "./useJobEvents";
import { cn } from "@/utils/cn";

export type { JobEvent, EventLevel };
export type LogLine = JobEvent;

export interface LogViewerProps {
  events?: JobEvent[];
  lines?: JobEvent[];
  title?: string;
  isStreaming?: boolean;
  isLive?: boolean;
  height?: number | string;
  onToggleTail?: () => void;
  className?: string;
}

export const LogViewer: React.FC<LogViewerProps> = ({
  events,
  lines,
  title = "Console Logs",
  isStreaming = false,
  isLive,
  height,
  onToggleTail,
  className,
}) => {
  const activeEvents = useMemo(() => events ?? lines ?? [], [events, lines]);
  const activeStreaming = isLive ?? isStreaming;
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLevel, setSelectedLevel] = useState<string>("ALL");
  const [selectedDevice, setSelectedDevice] = useState<string>("ALL");
  const [followTail, setFollowTail] = useState(true);
  const [copiedAll, setCopiedAll] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);

  // Extract unique device list
  const deviceList = useMemo(() => {
    const devs = new Set<string>();
    for (const e of activeEvents) {
      if (e.device) devs.add(e.device);
    }
    return Array.from(devs).sort();
  }, [activeEvents]);

  // Filtered log events
  const filteredEvents = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return activeEvents.filter((e) => {
      // Level filter
      if (selectedLevel !== "ALL" && e.level !== selectedLevel) {
        return false;
      }
      // Device filter
      if (selectedDevice !== "ALL" && e.device !== selectedDevice) {
        return false;
      }
      // Search query
      if (q) {
        const matchesMsg = e.message.toLowerCase().includes(q);
        const matchesDev = e.device?.toLowerCase().includes(q) ?? false;
        if (!matchesMsg && !matchesDev) return false;
      }
      return true;
    });
  }, [activeEvents, searchQuery, selectedLevel, selectedDevice]);

  // Virtualizer
  const rowVirtualizer = useVirtualizer({
    count: filteredEvents.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 22,
    overscan: 25,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();

  // Follow tail auto-scroll effect
  useEffect(() => {
    if (followTail && containerRef.current && filteredEvents.length > 0) {
      rowVirtualizer.scrollToIndex(filteredEvents.length - 1, { align: "end" });
    }
  }, [filteredEvents.length, followTail, rowVirtualizer]);

  // Disable follow tail if user scrolls up
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const isAtBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 40;
    if (!isAtBottom && followTail) {
      setFollowTail(false);
    }
  };

  const handleCopyAll = async () => {
    const rawText = filteredEvents
      .map((e) => `[${e.ts}] [${e.level}] ${e.device ? `[${e.device}] ` : ""}${e.message}`)
      .join("\n");
    await navigator.clipboard.writeText(rawText);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 1500);
  };

  const handleDownload = () => {
    const rawText = filteredEvents
      .map((e) => `[${e.ts}] [${e.level}] ${e.device ? `[${e.device}] ` : ""}${e.message}`)
      .join("\n");
    const blob = new Blob([rawText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `webdash-logs-${Date.now()}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getLevelColor = (level: EventLevel) => {
    switch (level) {
      case "ERROR":
      case "CRITICAL":
        return "text-fault";
      case "WARNING":
      case "WARN":
        return "text-warn";
      case "INFO":
        return "text-signal";
      case "DEBUG":
      default:
        return "text-ink-2";
    }
  };

  return (
    <div
      style={height ? { height } : undefined}
      className={cn(
        "flex flex-1 flex-col overflow-hidden rounded-control border border-line bg-surface font-mono text-xs text-ink",
        className
      )}
    >
      {/* Log Header Toolbar */}
      <div className="flex h-10 flex-shrink-0 items-center justify-between border-b border-line bg-surface-2 px-3 gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-ink text-xs font-sans">{title}</span>
          {activeStreaming && (
            <span className="inline-flex items-center gap-1 rounded-control bg-ok/10 px-1.5 py-0.5 text-[10px] font-medium text-ok font-sans">
              <span className="h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
              Live
            </span>
          )}
          <span className="text-[11px] font-mono text-ink-2">
            ({filteredEvents.length.toLocaleString()} lines)
          </span>
        </div>

        {/* Toolbar Controls */}
        <div className="flex items-center gap-2">
          {/* Search Box */}
          <div className="flex items-center gap-1.5 rounded-control border border-line bg-surface px-2 py-0.5">
            <Search className="h-3 w-3 text-ink-2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search logs..."
              className="w-28 sm:w-40 bg-transparent text-[11px] text-ink placeholder-ink-2/60 outline-none"
            />
          </div>

          {/* Level Filter Dropdown */}
          <select
            value={selectedLevel}
            onChange={(e) => setSelectedLevel(e.target.value)}
            className="h-7 rounded-control border border-line bg-surface px-2 text-[11px] text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            <option value="ALL">All Levels</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </select>

          {/* Device Filter Dropdown */}
          {deviceList.length > 0 && (
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              className="h-7 max-w-xs rounded-control border border-line bg-surface px-2 text-[11px] text-ink focus:outline-none focus:ring-1 focus:ring-signal"
            >
              <option value="ALL">All Devices</option>
              {deviceList.map((dev) => (
                <option key={dev} value={dev}>
                  {dev}
                </option>
              ))}
            </select>
          )}

          {/* Follow Tail Button */}
          <button
            type="button"
            onClick={() => {
              setFollowTail(!followTail);
              onToggleTail?.();
              if (!followTail && filteredEvents.length > 0) {
                rowVirtualizer.scrollToIndex(filteredEvents.length - 1, { align: "end" });
              }
            }}
            title={followTail ? "Auto-scroll active" : "Auto-scroll paused"}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-control border px-2 text-[11px] font-sans font-medium transition-colors focus:outline-none",
              followTail
                ? "border-signal bg-signal/15 text-signal"
                : "border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"
            )}
          >
            <Activity className="h-3 w-3" />
            <span>Follow</span>
          </button>

          {/* Copy All */}
          <button
            type="button"
            onClick={handleCopyAll}
            title="Copy logs to clipboard"
            className="inline-flex h-7 items-center justify-center rounded-control border border-line bg-surface px-2 text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none"
          >
            {copiedAll ? <Check className="h-3 w-3 text-ok" /> : <Copy className="h-3 w-3" />}
          </button>

          {/* Download */}
          <button
            type="button"
            onClick={handleDownload}
            title="Download log file"
            className="inline-flex h-7 items-center justify-center rounded-control border border-line bg-surface px-2 text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none"
          >
            <Download className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Virtual Log Window */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto p-2 bg-surface select-text dir-ltr"
        style={{ willChange: "transform" }}
      >
        {filteredEvents.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink-2 font-sans">
            No log events available.
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
              const item = filteredEvents[virtualRow.index];
              return (
                <div
                  key={virtualRow.key}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  className="flex items-baseline gap-2 px-1 hover:bg-surface-2/40 leading-tight text-[11px] font-mono"
                >
                  {/* Timestamp */}
                  <span className="text-ink-2/70 flex-shrink-0 select-none">
                    {(() => {
                      const t = item.ts || item.timestamp || "";
                      return t.length > 19 ? t.slice(11, 23) : t;
                    })()}
                  </span>

                  {/* Level */}
                  <span
                    className={cn(
                      "font-semibold flex-shrink-0 w-12 text-center select-none uppercase",
                      getLevelColor(item.level)
                    )}
                  >
                    {item.level.slice(0, 5)}
                  </span>

                  {/* Device Tag (if present) */}
                  {item.device && (
                    <span className="rounded bg-surface-2 px-1 py-0.2 text-[10px] text-ink-2 flex-shrink-0 select-none border border-line/40">
                      {item.device}
                    </span>
                  )}

                  {/* Message */}
                  <span className="text-ink flex-1 whitespace-pre-wrap break-all">
                    {item.message}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
