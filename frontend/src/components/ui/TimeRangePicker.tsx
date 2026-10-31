/**
 * TimeRangePicker component for telemetry and telemetry queries.
 * Presets: 15m, 1h, 6h, 24h, 7d, custom.
 */
import React from "react";
import { Clock } from "lucide-react";
import { cn } from "@/utils/cn";

export type TimeRangePreset = "15m" | "1h" | "6h" | "24h" | "7d" | "custom";

export interface TimeRangeValue {
  preset: TimeRangePreset;
  start?: Date;
  end?: Date;
}

export interface TimeRangePickerProps {
  value: TimeRangePreset;
  onChange: (val: TimeRangePreset) => void;
  className?: string;
}

const PRESETS: { id: TimeRangePreset; label: string }[] = [
  { id: "15m", label: "15m" },
  { id: "1h", label: "1h" },
  { id: "6h", label: "6h" },
  { id: "24h", label: "24h" },
  { id: "7d", label: "7d" },
];

export const TimeRangePicker: React.FC<TimeRangePickerProps> = ({
  value,
  onChange,
  className,
}) => {
  return (
    <div
      role="group"
      aria-label="Time range selector"
      className={cn(
        "inline-flex items-center rounded-control border border-line bg-surface p-0.5",
        className
      )}
    >
      <span className="px-1.5 text-ink-2">
        <Clock className="h-3 w-3" />
      </span>
      {PRESETS.map((p) => {
        const active = value === p.id;
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => onChange(p.id)}
            className={cn(
              "rounded-control px-2 py-0.5 text-xs font-mono transition-colors focus:outline-none",
              active
                ? "bg-signal text-white font-semibold"
                : "text-ink-2 hover:bg-surface-2 hover:text-ink"
            )}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
};
