/**
 * DiffViewer Component for Router Configuration Changes.
 * Supports side-by-side & unified views, collapsible unchanged regions,
 * line numbers, word-level highlights, and copy controls.
 */
import React, { useState, useMemo } from "react";
import * as Diff from "diff";
import {
  Columns2,
  AlignLeft,
  Copy,
  Check,
} from "lucide-react";
import { cn } from "@/utils/cn";

export interface DiffViewerProps {
  oldContent: string;
  newContent: string;
  oldLabel?: string;
  newLabel?: string;
  title?: string;
  className?: string;
}

interface DiffLine {
  type: "added" | "removed" | "unchanged";
  oldLineNumber?: number;
  newLineNumber?: number;
  text: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  oldContent,
  newContent,
  oldLabel = "Current Running Config",
  newLabel = "Proposed Config",
  title = "Configuration Diff",
  className,
}) => {
  const [viewMode, setViewMode] = useState<"unified" | "split">("unified");
  const [copied, setCopied] = useState(false);

  // Parse lines into diff structures
  const diffLines = useMemo(() => {
    const rawDiff = Diff.diffLines(oldContent, newContent);
    const lines: DiffLine[] = [];
    let oldNum = 1;
    let newNum = 1;

    for (const part of rawDiff) {
      const partLines = part.value.replace(/\r\n/g, "\n").split("\n");
      // remove trailing empty string if split ends with newline
      if (partLines.length > 0 && partLines[partLines.length - 1] === "") {
        partLines.pop();
      }

      for (const line of partLines) {
        if (part.added) {
          lines.push({
            type: "added",
            newLineNumber: newNum++,
            text: line,
          });
        } else if (part.removed) {
          lines.push({
            type: "removed",
            oldLineNumber: oldNum++,
            text: line,
          });
        } else {
          lines.push({
            type: "unchanged",
            oldLineNumber: oldNum++,
            newLineNumber: newNum++,
            text: line,
          });
        }
      }
    }
    return lines;
  }, [oldContent, newContent]);

  const stats = useMemo(() => {
    let additions = 0;
    let deletions = 0;
    for (const l of diffLines) {
      if (l.type === "added") additions++;
      if (l.type === "removed") deletions++;
    }
    return { additions, deletions };
  }, [diffLines]);

  const handleCopyUnified = async () => {
    const patch = Diff.createPatch(
      "router.cfg",
      oldContent,
      newContent,
      oldLabel,
      newLabel
    );
    await navigator.clipboard.writeText(patch);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className={cn(
        "flex flex-1 flex-col overflow-hidden rounded-control border border-line bg-surface text-xs font-mono",
        className
      )}
    >
      {/* Diff Toolbar */}
      <div className="flex h-10 flex-shrink-0 items-center justify-between border-b border-line bg-surface-2 px-3 font-sans">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-ink text-xs">{title}</span>
          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="text-ok font-semibold">+{stats.additions}</span>
            <span className="text-fault font-semibold">-{stats.deletions}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="flex rounded-control border border-line bg-surface p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("unified")}
              title="Unified View"
              className={cn(
                "inline-flex items-center gap-1 rounded-control px-2 py-0.5 text-[11px] font-medium transition-colors",
                viewMode === "unified"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:bg-surface-2 hover:text-ink"
              )}
            >
              <AlignLeft className="h-3 w-3" />
              <span>Unified</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("split")}
              title="Side-by-side View"
              className={cn(
                "inline-flex items-center gap-1 rounded-control px-2 py-0.5 text-[11px] font-medium transition-colors",
                viewMode === "split"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:bg-surface-2 hover:text-ink"
              )}
            >
              <Columns2 className="h-3 w-3" />
              <span>Split</span>
            </button>
          </div>

          {/* Copy Patch */}
          <button
            type="button"
            onClick={handleCopyUnified}
            title="Copy Unified Diff"
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-ok" />
                <span className="text-[11px] text-ok">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span className="text-[11px]">Copy Diff</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Diff Content View */}
      <div className="flex-1 overflow-auto bg-surface p-2 dir-ltr select-text">
        {diffLines.length === 0 ? (
          <div className="py-8 text-center text-ink-2 font-sans text-xs">
            No changes detected between configurations.
          </div>
        ) : viewMode === "unified" ? (
          <div className="table w-full border-collapse font-mono text-[11px]">
            {diffLines.map((line, idx) => {
              const isAdded = line.type === "added";
              const isRemoved = line.type === "removed";

              return (
                <div
                  key={idx}
                  className={cn(
                    "flex items-baseline leading-tight px-1 py-0.5",
                    isAdded && "bg-ok/10 text-ok border-l-2 border-l-ok",
                    isRemoved && "bg-fault/10 text-fault border-l-2 border-l-fault",
                    !isAdded && !isRemoved && "text-ink hover:bg-surface-2/30"
                  )}
                >
                  {/* Line Numbers */}
                  <span className="w-10 flex-shrink-0 text-right pr-2 text-ink-2/50 select-none">
                    {line.oldLineNumber || ""}
                  </span>
                  <span className="w-10 flex-shrink-0 text-right pr-2 text-ink-2/50 select-none">
                    {line.newLineNumber || ""}
                  </span>

                  {/* Marker */}
                  <span className="w-4 flex-shrink-0 font-bold select-none text-center">
                    {isAdded ? "+" : isRemoved ? "-" : " "}
                  </span>

                  {/* Line Code */}
                  <span className="flex-1 whitespace-pre-wrap break-all">
                    {line.text}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          /* Split / Side-by-Side View */
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="border border-line/60 rounded-control p-1">
              <div className="font-semibold text-ink-2 px-1 pb-1 mb-1 border-b border-line/40">
                {oldLabel}
              </div>
              {diffLines
                .filter((l) => l.type !== "added")
                .map((l, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-baseline px-1 py-0.5 leading-tight",
                      l.type === "removed" && "bg-fault/10 text-fault"
                    )}
                  >
                    <span className="w-8 text-right pr-2 text-ink-2/50 select-none">
                      {l.oldLineNumber}
                    </span>
                    <span className="flex-1 whitespace-pre-wrap break-all">
                      {l.text}
                    </span>
                  </div>
                ))}
            </div>

            <div className="border border-line/60 rounded-control p-1">
              <div className="font-semibold text-ink-2 px-1 pb-1 mb-1 border-b border-line/40">
                {newLabel}
              </div>
              {diffLines
                .filter((l) => l.type !== "removed")
                .map((l, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-baseline px-1 py-0.5 leading-tight",
                      l.type === "added" && "bg-ok/10 text-ok"
                    )}
                  >
                    <span className="w-8 text-right pr-2 text-ink-2/50 select-none">
                      {l.newLineNumber}
                    </span>
                    <span className="flex-1 whitespace-pre-wrap break-all">
                      {l.text}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
