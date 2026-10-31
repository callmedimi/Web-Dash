import React, { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { cn } from "@/utils/cn";

export interface TimeSeriesDef {
  label: string;
  stroke?: string;
  fill?: string;
  width?: number;
  step?: boolean;
  spanGaps?: boolean;
}

export interface TimeSeriesChartProps {
  /**
   * Aligned uPlot data format: [timestampsInSeconds, series1Values, series2Values, ...]
   * Null or undefined represents missing data/gaps.
   */
  data: uPlot.AlignedData;
  series: TimeSeriesDef[];
  title?: string;
  unit?: string;
  height?: number;
  syncKey?: string;
  className?: string;
}

/**
 * High-performance NOC TimeSeriesChart wrapped around uPlot.
 * Supports multi-series, stepped/linear curves, missing data gap handling,
 * synced crosshair cursors, and responsive resizing.
 */
export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({
  data,
  series,
  title,
  unit = "",
  height = 240,
  syncKey,
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Detect dark or light mode from document
    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    const gridColor = isDark ? "#252E39" : "#E2E6DF";
    const axisColor = isDark ? "#9AA7B5" : "#52606D";

    const width = containerRef.current.clientWidth || 400;

    // Build series configuration
    const uSeries: uPlot.Series[] = [
      {
        label: "Time",
      },
      ...series.map((s, idx) => {
        const defaultColor = idx === 0 ? "#2F5BEA" : idx === 1 ? "#4CC38A" : "#E8B04A";
        return {
          label: s.label,
          stroke: s.stroke || defaultColor,
          fill: s.fill,
          width: s.width ?? 1.5,
          spanGaps: s.spanGaps ?? false, // false creates gaps on missing data
          paths:
            s.step && uPlot.paths && typeof uPlot.paths.stepped === "function"
              ? uPlot.paths.stepped({ align: 1 })
              : undefined,
          points: { show: false },
        };
      }),
    ];

    const opts: uPlot.Options = {
      width,
      height,
      cursor: {
        drag: { setScale: false },
        sync: syncKey ? { key: syncKey } : undefined,
      },
      series: uSeries,
      axes: [
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          ticks: { stroke: gridColor, width: 1 },
          font: "11px 'JetBrains Mono', monospace",
        },
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          ticks: { stroke: gridColor, width: 1 },
          font: "11px 'JetBrains Mono', monospace",
          values: (_u, vals) => vals.map((v) => (v != null ? `${v}${unit ? " " + unit : ""}` : "")),
        },
      ],
      legend: {
        show: true,
      },
    };

    try {
      const u = new uPlot(opts, data, containerRef.current);
      chartRef.current = u;
    } catch {
      // JSDOM / headless canvas might fail or be stubbed; safely fall through
    }

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (chartRef.current && entry.contentRect.width > 0) {
          chartRef.current.setSize({
            width: Math.floor(entry.contentRect.width),
            height,
          });
        }
      }
    });

    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [series, height, syncKey, unit, data]);

  // Update chart data whenever data changes
  useEffect(() => {
    if (chartRef.current && data) {
      chartRef.current.setData(data);
    }
  }, [data]);

  return (
    <div
      className={cn(
        "rounded-[3px] border border-[var(--line)] bg-[var(--surface)] p-3 text-[var(--ink)] shadow-sm",
        className
      )}
      data-testid="time-series-chart"
    >
      {title && (
        <div className="mb-2 flex items-center justify-between border-b border-[var(--line)] pb-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-2)]">
            {title}
          </span>
          {unit && <span className="text-[11px] font-mono text-[var(--ink-2)]">[{unit}]</span>}
        </div>
      )}
      <div ref={containerRef} className="w-full overflow-hidden" style={{ minHeight: height }} />
    </div>
  );
};
