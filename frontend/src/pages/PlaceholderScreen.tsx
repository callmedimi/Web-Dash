import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Construction, CheckCircle2, Shield, Layers } from "lucide-react";

export interface PlaceholderScreenProps {
  title: string;
  subtitle: string;
  step: string;
  description?: string;
  features?: string[];
}

export const PlaceholderScreen: React.FC<PlaceholderScreenProps> = ({
  title,
  subtitle,
  step,
  description,
  features = [],
}) => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-6 space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold text-ink">{title}</h1>
            <span className="rounded-control bg-signal/15 px-2 py-0.5 text-[11px] font-mono font-medium text-signal border border-signal/30">
              Phase 7 §{step}
            </span>
          </div>
          <p className="mt-1 text-xs text-ink-2">{subtitle}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-surface px-2.5 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <ArrowLeft className="h-3 w-3 rtl:rotate-180" />
            <span>Back</span>
          </button>
          <Link
            to="/"
            className="inline-flex h-7 items-center gap-1.5 rounded-control bg-signal px-3 text-xs font-medium text-white hover:bg-signal/90 transition-colors shadow-sm"
          >
            <span>Overview Dashboard</span>
            <ArrowRight className="h-3 w-3 rtl:rotate-180" />
          </Link>
        </div>
      </div>

      {/* Screen Overview Card */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-control border border-line bg-surface p-5 space-y-4">
          <div className="flex items-center gap-2 text-ink">
            <Construction className="h-5 w-5 text-warn" />
            <h2 className="text-sm font-semibold">Active Development Pipeline</h2>
          </div>

          <p className="text-xs text-ink-2 leading-relaxed">
            {description ||
              "This screen is scheduled in Phase 7 UI Screens (plan/09_PHASE7_UI_SCREENS.md). The backend automation engines, database models, and security policies are active and operational."}
          </p>

          {features.length > 0 && (
            <div className="space-y-2 pt-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
                Included Capabilities:
              </h3>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {features.map((f, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-2 rounded-control border border-line bg-surface-2/50 p-2 text-xs"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5 text-ok shrink-0 mt-0.5" />
                    <span className="text-ink">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Security & System Info Side Card */}
        <div className="rounded-control border border-line bg-surface p-5 space-y-4">
          <div className="flex items-center gap-2 text-ink">
            <Shield className="h-4 w-4 text-signal" />
            <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2">
              Security & Environment
            </h2>
          </div>

          <ul className="space-y-2.5 text-xs">
            <li className="flex items-center justify-between border-b border-line/60 pb-2">
              <span className="text-ink-2">Environment</span>
              <span className="font-mono font-medium text-ok">Air-Gapped Local</span>
            </li>
            <li className="flex items-center justify-between border-b border-line/60 pb-2">
              <span className="text-ink-2">Driver Framework</span>
              <span className="font-mono font-medium text-ink">VRP5 / VRP8 Hybrid</span>
            </li>
            <li className="flex items-center justify-between border-b border-line/60 pb-2">
              <span className="text-ink-2">Change Safety</span>
              <span className="font-mono font-medium text-signal">2-Phase Dry-Run / Apply</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-ink-2">Telemetry</span>
              <span className="font-mono font-medium text-ink">Zabbix Correlated</span>
            </li>
          </ul>

          <div className="pt-2">
            <Link
              to="/_ui"
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-control border border-line bg-surface-2 p-2 text-xs font-medium text-ink hover:bg-surface-2/80 transition-colors"
            >
              <Layers className="h-3.5 w-3.5 text-warn" />
              <span>Inspect UI Kitchen Sink</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};
