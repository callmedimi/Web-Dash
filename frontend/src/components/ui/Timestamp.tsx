/**
 * Timestamp component with relative time, exact hover tooltip, and 24-hour display.
 */
import React, { useState, useEffect } from "react";
import { cn } from "@/utils/cn";

export interface TimestampProps {
  value?: string | number | Date | null | undefined;
  isoString?: string | number | Date | null | undefined;
  relative?: boolean;
  className?: string;
}

function parseDate(val: string | number | Date | null | undefined): Date | null {
  if (!val) return null;
  if (val instanceof Date) return isNaN(val.getTime()) ? null : val;
  if (typeof val === "number") {
    // If seconds timestamp, convert to ms
    const ms = val < 1e11 ? val * 1000 : val;
    return new Date(ms);
  }
  const parsed = new Date(val);
  return isNaN(parsed.getTime()) ? null : parsed;
}

function formatRelative(d: Date): string {
  const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return d.toISOString().slice(0, 10);
}

function formatExact24h(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const year = d.getUTCFullYear();
  const month = pad(d.getUTCMonth() + 1);
  const day = pad(d.getUTCDate());
  const hours = pad(d.getUTCHours());
  const min = pad(d.getUTCMinutes());
  const sec = pad(d.getUTCSeconds());
  return `${year}-${month}-${day} ${hours}:${min}:${sec} UTC`;
}

export const Timestamp: React.FC<TimestampProps> = ({
  value,
  isoString,
  relative = false,
  className,
}) => {
  const date = parseDate(value ?? isoString);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!relative || !date) return;
    const interval = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(interval);
  }, [relative, date]);

  if (!date) {
    return <span className={cn("text-ink-2 font-mono text-xs", className)}>--</span>;
  }

  const exactStr = formatExact24h(date);
  const displayStr = relative ? formatRelative(date) : exactStr;

  return (
    <time
      dateTime={date.toISOString()}
      title={exactStr}
      className={cn("font-mono text-xs text-ink-2 hover:text-ink cursor-default dir-ltr", className)}
    >
      {displayStr}
    </time>
  );
};
