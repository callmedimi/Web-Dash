/**
 * Radial / Speedometer SVG Gauge Component for Executive and Managerial Dashboards.
 * Fully air-gapped, zero external dependencies, SVG-based with smooth CSS animations.
 */
import React from "react";
import { cn } from "@/utils/cn";

export interface RadialGaugeProps {
  value: number; // 0 to 100
  title: string;
  subtitle?: string;
  unit?: string;
  target?: number; // Optional SLA benchmark (e.g., 99.5)
  thresholds?: {
    warn: number;
    fault: number;
    invert?: boolean; // If true, lower is better
  };
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
  trend?: "up" | "down" | "flat";
  trendValue?: string;
  className?: string;
}

export const RadialGauge: React.FC<RadialGaugeProps> = ({
  value,
  title,
  subtitle,
  unit = "%",
  target,
  thresholds = { warn: 90, fault: 80, invert: false },
  size = "md",
  icon,
  trend,
  trendValue,
  className,
}) => {
  // Clamp value between 0 and 100
  const clampedValue = Math.min(100, Math.max(0, value));

  // Determine status color
  const isGood = thresholds.invert
    ? clampedValue <= thresholds.warn
    : clampedValue >= thresholds.warn;
  const isFault = thresholds.invert
    ? clampedValue >= thresholds.fault
    : clampedValue < thresholds.fault;

  let strokeColor = "#10B981"; // Emerald / Ok
  let statusBadgeClass = "bg-ok/10 text-ok border-ok/30";
  let statusText = "عالی (Optimal)";

  if (isFault) {
    strokeColor = "#EF4444"; // Red / Fault
    statusBadgeClass = "bg-fault/10 text-fault border-fault/30";
    statusText = "بحرانی (Critical)";
  } else if (!isGood) {
    strokeColor = "#F59E0B"; // Amber / Warn
    statusBadgeClass = "bg-warn/10 text-warn border-warn/30";
    statusText = "هشدار (Warning)";
  }

  // SVG Geometry for a 220-degree arc
  // Radius R = 75, Center (100, 100)
  // Arc angle spans from 160 deg to 380 deg (220 deg total)
  const radius = 70;
  const strokeWidth = size === "lg" ? 14 : size === "sm" ? 9 : 12;
  const arcTotalAngle = 220; // degrees
  const circumference = (arcTotalAngle / 360) * (2 * Math.PI * radius);
  const strokeDashoffset = circumference - (clampedValue / 100) * circumference;

  // Calculate target indicator position if specified
  let targetAngle = 0;
  let targetX = 0;
  let targetY = 0;
  if (target !== undefined) {
    const targetClamped = Math.min(100, Math.max(0, target));
    // Start angle is 160 degrees. 220 degrees span.
    targetAngle = 160 + (targetClamped / 100) * arcTotalAngle;
    const rad = (targetAngle * Math.PI) / 180;
    targetX = 100 + (radius + 2) * Math.cos(rad);
    targetY = 100 + (radius + 2) * Math.sin(rad);
  }

  // Arc path generator: start at 160°, end at 380° (20°)
  // Angle 160°:
  const startRad = (160 * Math.PI) / 180;
  const endRad = (380 * Math.PI) / 180;
  const x1 = 100 + radius * Math.cos(startRad);
  const y1 = 100 + radius * Math.sin(startRad);
  const x2 = 100 + radius * Math.cos(endRad);
  const y2 = 100 + radius * Math.sin(endRad);

  const arcPath = `M ${x1} ${y1} A ${radius} ${radius} 0 1 1 ${x2} ${y2}`;

  const dimensions =
    size === "lg"
      ? "w-64 h-52"
      : size === "sm"
      ? "w-44 h-36"
      : "w-56 h-44";

  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-between rounded-control border border-line bg-surface p-4 transition-all hover:border-signal/40 hover:shadow-sm",
        className
      )}
    >
      {/* Header: Title + Icon + Status */}
      <div className="flex w-full items-center justify-between border-b border-line/60 pb-2 mb-1">
        <div className="flex items-center gap-2">
          {icon && <div className="text-signal">{icon}</div>}
          <div>
            <h3 className="text-xs font-semibold text-ink leading-tight">{title}</h3>
            {subtitle && (
              <p className="text-[10px] text-ink-2 truncate max-w-[130px]">{subtitle}</p>
            )}
          </div>
        </div>
        <span
          className={cn(
            "rounded-control border px-1.5 py-0.5 text-[10px] font-medium leading-none",
            statusBadgeClass
          )}
        >
          {statusText}
        </span>
      </div>

      {/* Speedometer Arc SVG */}
      <div className={cn("relative flex items-center justify-center", dimensions)}>
        <svg
          viewBox="10 15 180 150"
          className="w-full h-full overflow-visible"
        >
          <defs>
            <linearGradient id={`gauge-grad-${title.replace(/\s+/g, "-")}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#2563EB" />
              <stop offset="60%" stopColor={strokeColor} />
              <stop offset="100%" stopColor={strokeColor} />
            </linearGradient>
            <filter id="gauge-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Background Track */}
          <path
            d={arcPath}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            className="text-line/40 dark:text-line/60"
          />

          {/* Active Progress Arc */}
          <path
            d={arcPath}
            fill="none"
            stroke={`url(#gauge-grad-${title.replace(/\s+/g, "-")})`}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className="transition-all duration-700 ease-out"
            filter="url(#gauge-glow)"
          />

          {/* Target Benchmark Marker Tick */}
          {target !== undefined && (
            <circle
              cx={targetX}
              cy={targetY}
              r={size === "lg" ? 4.5 : 3.5}
              fill="#FFFFFF"
              stroke="#2563EB"
              strokeWidth={2}
              className="drop-shadow-md"
            >
              <title>Target SLA: {target}%</title>
            </circle>
          )}

          {/* Gauge Center Readout */}
          <text
            x="100"
            y="98"
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-ink font-mono font-bold text-2xl tracking-tight"
          >
            {clampedValue.toFixed(1)}
            <tspan className="text-sm font-normal text-ink-2 ml-0.5">{unit}</tspan>
          </text>

          {/* Subtext below the number */}
          <text
            x="100"
            y="124"
            textAnchor="middle"
            className="fill-ink-2 text-[10px] font-sans"
          >
            {target !== undefined ? `هدف SLA: ${target}%` : "پایش مستمر تله‌متری"}
          </text>
        </svg>
      </div>

      {/* Footer Benchmark / Trend indicator */}
      <div className="flex w-full items-center justify-between border-t border-line/60 pt-2 text-[11px] text-ink-2">
        <div className="flex items-center gap-1">
          {trend === "up" && (
            <span className="text-ok font-semibold inline-flex items-center">
              ▲ {trendValue || "+0.4%"}
            </span>
          )}
          {trend === "down" && (
            <span className="text-fault font-semibold inline-flex items-center">
              ▼ {trendValue || "-0.8%"}
            </span>
          )}
          {(!trend || trend === "flat") && (
            <span className="text-ink-2 font-mono">● نرمال</span>
          )}
          <span className="text-[10px]">نسبت به دوره قبل</span>
        </div>

        {target !== undefined && (
          <span className="font-mono text-[10px] text-signal font-semibold">
            هدف: {target}%
          </span>
        )}
      </div>
    </div>
  );
};
