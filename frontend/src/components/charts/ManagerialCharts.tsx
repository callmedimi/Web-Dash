/**
 * Managerial & Executive Charts for Web-Dash Overview.
 * High visual polish, pure SVG / CSS (zero external charting bloat, air-gapped).
 */
import React from "react";
import { cn } from "@/utils/cn";
import { MapPin, ShieldAlert, CheckCircle2 } from "lucide-react";

export interface ProvinceStat {
  province: string;
  total: number;
  available: number;
  down: number;
  pct: number;
}

export interface ManagerialChartsProps {
  provinces?: ProvinceStat[];
  problemsBySeverity?: {
    disaster: number;
    high: number;
    warning: number;
    average: number;
    information: number;
  };
  totalAlarms?: number;
  onSelectProvince?: (province: string) => void;
  className?: string;
}

export const ManagerialCharts: React.FC<ManagerialChartsProps> = ({
  provinces = [],
  problemsBySeverity = { disaster: 0, high: 0, warning: 0, average: 0, information: 0 },
  totalAlarms,
  onSelectProvince,
  className,
}) => {
  // Sort provinces by most down links first
  const sortedProvinces = React.useMemo(() => {
    return [...provinces]
      .sort((a, b) => b.down - a.down || a.pct - b.pct)
      .slice(0, 8); // Top 8 provinces
  }, [provinces]);

  const maxDown = Math.max(1, ...sortedProvinces.map((p) => p.down));

  // Severity breakdown
  const sev = problemsBySeverity;
  const total =
    totalAlarms !== undefined
      ? totalAlarms
      : sev.disaster + sev.high + sev.warning + sev.average + sev.information;

  // Donut geometry
  const radius = 54;
  const circumference = 2 * Math.PI * radius;

  const categories = [
    { label: "فاجعه‌بار (Disaster)", count: sev.disaster, color: "#EF4444" },
    { label: "بحرانی (High)", count: sev.high, color: "#F97316" },
    { label: "هشدار (Warning)", count: sev.warning, color: "#3B82F6" },
    { label: "متوسط (Average)", count: sev.average, color: "#8B5CF6" },
    { label: "اطلاعاتی (Info)", count: sev.information, color: "#64748B" },
  ];

  let accumulatedPercent = 0;
  const donutSegments = categories.map((cat) => {
    const pct = total > 0 ? cat.count / total : 0;
    const strokeDasharray = `${pct * circumference} ${circumference}`;
    const strokeDashoffset = -accumulatedPercent * circumference;
    accumulatedPercent += pct;
    return {
      ...cat,
      pct: (pct * 100).toFixed(1),
      strokeDasharray,
      strokeDashoffset,
    };
  });

  return (
    <div className={cn("grid grid-cols-1 gap-4 lg:grid-cols-2", className)}>
      {/* Chart 1: Province Down-Links Bar Chart */}
      <div className="flex flex-col rounded-control border border-line bg-surface p-4">
        <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-signal" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">
              تفکیک استانی لینک‌های قطع و اختلالات (Down-Links by Province)
            </h3>
          </div>
          <span className="text-[10px] font-mono font-medium text-ink-2 bg-surface-2 px-1.5 py-0.5 rounded-control">
            {sortedProvinces.length} استان بحرانی
          </span>
        </div>

        {sortedProvinces.length === 0 ? (
          <div className="flex flex-1 items-center justify-center p-6 text-xs text-ink-2">
            <CheckCircle2 className="h-6 w-6 text-ok mr-2" />
            <span>هیچ قطعی استانی ثبت نشده است.</span>
          </div>
        ) : (
          <div className="flex-1 space-y-2.5 overflow-y-auto max-h-72 pr-1">
            {sortedProvinces.map((p) => {
              const widthPct = Math.min(100, Math.max(8, (p.down / maxDown) * 100));
              const isHigh = p.down >= 3;
              return (
                <div
                  key={p.province}
                  onClick={() => onSelectProvince?.(p.province)}
                  className="group flex flex-col gap-1 cursor-pointer rounded-control p-1.5 transition-colors hover:bg-surface-2"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono font-medium text-ink group-hover:text-signal">
                      {p.province}
                    </span>
                    <div className="flex items-center gap-2 font-mono text-[11px]">
                      <span className={cn("font-bold", isHigh ? "text-fault" : "text-warn")}>
                        {p.down} قطعی
                      </span>
                      <span className="text-ink-2">/</span>
                      <span className="text-ok font-medium">{p.pct}% پایداری</span>
                    </div>
                  </div>

                  {/* Horizontal Bar */}
                  <div className="h-2 w-full rounded-full bg-surface-2 overflow-hidden flex">
                    <div
                      style={{ width: `${widthPct}%` }}
                      className={cn(
                        "h-full rounded-full transition-all duration-500",
                        isHigh
                          ? "bg-gradient-to-r from-warn to-fault"
                          : "bg-gradient-to-r from-signal to-warn"
                      )}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Chart 2: Executive Severity Distribution Donut */}
      <div className="flex flex-col rounded-control border border-line bg-surface p-4">
        <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-signal" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">
              توزیع شدت و ریسک رویدادها (Executive Risk Distribution)
            </h3>
          </div>
          <span className="text-[10px] font-mono font-bold text-ink bg-surface-2 px-1.5 py-0.5 rounded-control">
            مجموع: {total}
          </span>
        </div>

        <div className="flex flex-1 flex-col sm:flex-row items-center justify-center gap-6 p-2">
          {/* SVG Donut */}
          <div className="relative h-40 w-40 shrink-0 flex items-center justify-center">
            <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90 transform">
              {/* Background circle */}
              <circle
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                stroke="currentColor"
                strokeWidth="14"
                className="text-line/40"
              />

              {/* Segments */}
              {donutSegments.map((seg, idx) => (
                <circle
                  key={idx}
                  cx="70"
                  cy="70"
                  r={radius}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="14"
                  strokeDasharray={seg.strokeDasharray}
                  strokeDashoffset={seg.strokeDashoffset}
                  strokeLinecap="round"
                  className="transition-all duration-700 hover:opacity-80"
                />
              ))}
            </svg>

            {/* Donut Center */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center">
              <span className="font-mono text-xl font-bold text-ink leading-none">{total}</span>
              <span className="text-[10px] text-ink-2 mt-1">کل رویدادها</span>
            </div>
          </div>

          {/* Legend and Percentages */}
          <div className="flex flex-1 flex-col justify-center space-y-1.5 text-xs w-full">
            {donutSegments.map((seg, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-1 rounded hover:bg-surface-2/60 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full shrink-0 shadow-sm"
                    style={{ backgroundColor: seg.color }}
                  />
                  <span className="text-[11px] font-medium text-ink">{seg.label}</span>
                </div>
                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="font-bold text-ink">{seg.count}</span>
                  <span className="text-ink-2 text-[10px] w-10 text-left dir-ltr">({seg.pct}%)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
