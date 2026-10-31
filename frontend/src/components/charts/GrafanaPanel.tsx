import React, { useState, useEffect, useRef } from "react";
import { cn } from "@/utils/cn";
import { ExternalLink, RefreshCw, AlertTriangle } from "lucide-react";

export interface GrafanaPanelProps {
  src: string;
  title: string;
  grafanaUrl?: string;
  timeoutMs?: number;
  height?: number | string;
  className?: string;
}

/**
 * Embedded Grafana Panel with connection timeout fallback card.
 * If iframe fails to load or exceeds timeout, displays an informative NOC
 * fallback card with a direct 'Open in Grafana' link.
 */
export const GrafanaPanel: React.FC<GrafanaPanelProps> = ({
  src,
  title,
  grafanaUrl,
  timeoutMs = 6000,
  height = 260,
  className,
}) => {
  const [loaded, setLoaded] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setLoaded(false);
    setTimedOut(false);

    timerRef.current = window.setTimeout(() => {
      setTimedOut(!loaded);
    }, timeoutMs);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [src, timeoutMs, reloadKey, loaded]);

  const handleRetry = () => {
    setReloadKey((k) => k + 1);
  };

  const targetUrl = grafanaUrl || src;

  return (
    <div
      className={cn(
        "relative rounded-[3px] border border-[var(--line)] bg-[var(--surface)] text-[var(--ink)] overflow-hidden shadow-sm flex flex-col",
        className
      )}
      style={{ height }}
      data-testid="grafana-panel"
    >
      {/* Panel Header */}
      <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-1.5 bg-[var(--surface-2)]">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--ink)]">
          {title}
        </span>
        <div className="flex items-center gap-2">
          {grafanaUrl && (
            <a
              href={grafanaUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[11px] text-[var(--signal)] hover:underline"
              title="Open in Grafana"
            >
              <span>Open in Grafana</span>
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </div>

      {/* Panel Body */}
      <div className="relative flex-1 w-full h-full">
        {/* Loading state */}
        {!loaded && !timedOut && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[var(--surface)] text-[var(--ink-2)] text-xs">
            <RefreshCw size={16} className="animate-spin text-[var(--signal)]" />
            <span>Loading Grafana telemetry...</span>
          </div>
        )}

        {/* Fallback card if timed out */}
        {timedOut && !loaded ? (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-[var(--surface)] text-[var(--ink)]"
            data-testid="grafana-fallback-card"
          >
            <div className="rounded-full bg-[var(--warn)]/10 p-2 text-[var(--warn)] mb-2">
              <AlertTriangle size={20} />
            </div>
            <h4 className="text-sm font-semibold mb-1">Grafana Panel Unavailable</h4>
            <p className="text-xs text-[var(--ink-2)] max-w-sm mb-4">
              The telemetry panel took longer than {Math.round(timeoutMs / 1000)}s to load or direct
              embedding is restricted.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRetry}
                className="flex items-center gap-1.5 rounded-[3px] border border-[var(--line)] bg-[var(--surface-2)] px-3 py-1 text-xs font-medium text-[var(--ink)] hover:bg-[var(--surface)]"
              >
                <RefreshCw size={12} />
                <span>Retry</span>
              </button>
              <a
                href={targetUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-[3px] bg-[var(--signal)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
              >
                <span>Open in Grafana</span>
                <ExternalLink size={12} />
              </a>
            </div>
          </div>
        ) : (
          <iframe
            key={reloadKey}
            src={src}
            title={title}
            className="w-full h-full border-0"
            onLoad={() => setLoaded(true)}
            sandbox="allow-scripts allow-same-origin"
          />
        )}
      </div>
    </div>
  );
};
