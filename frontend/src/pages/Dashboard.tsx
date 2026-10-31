/**
 * Primary Dashboard / Operations Overview Screen.
 * Calm, instrument-like layout fulfilling NOC requirements.
 */
import React from "react";
import { useAuthStore } from "@/store/auth";
import { PermissionGate } from "@/components/auth/PermissionGate";

export const Dashboard: React.FC = () => {
  const { user } = useAuthStore();

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-4 space-y-4">
      {/* Page Header */}
      <div className="flex items-center justify-between border-b border-line pb-3">
        <div>
          <h1 className="text-base font-semibold text-ink">Operations Overview</h1>
          <p className="text-xs text-ink-2">
            Real-time status of managed Huawei VRP routers and active automation pipelines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-control bg-surface-2 px-2 py-1 text-xs font-mono text-ink-2">
            Environment: Air-Gapped
          </span>
        </div>
      </div>

      {/* Primary Status Metric Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">MANAGED ROUTERS</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-ink">--</span>
            <span className="text-xs text-ink-2">devices</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-xs text-ok">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            VRP5 / VRP8 Driver Ready
          </div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">ACTIVE ALARMS</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-ink">0</span>
            <span className="text-xs text-ok">critical</span>
          </div>
          <div className="mt-2 text-xs text-ink-2">Telemetry streaming active</div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">SAFE CHANGES</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-signal">2-Phase</span>
            <span className="text-xs text-ink-2">dry-run / apply</span>
          </div>
          <div className="mt-2 text-xs text-ink-2">Auto-rollback enabled</div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">CURRENT SESSION</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-base font-semibold font-mono text-ink">{user?.username}</span>
            <span className="rounded-control bg-surface-2 px-1 text-[10px] font-mono uppercase text-ink-2">
              {user?.role}
            </span>
          </div>
          <div className="mt-2 text-xs text-ink-2">CSRF Protected / Audit Logged</div>
        </div>
      </div>

      {/* Permission Gate Demo / Role-Specific Actions */}
      <div className="rounded-control border border-line bg-surface p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2 mb-2">
          Operations Authorization Matrix
        </h2>
        <div className="space-y-2 text-xs">
          <PermissionGate
            feature="user_management"
            fallback={
              <div className="rounded-control bg-surface-2 p-2.5 text-ink-2">
                <span className="font-medium text-ink">User Administration:</span> Locked (Requires{" "}
                <span className="font-mono">user_management</span> permission).
              </div>
            }
          >
            <div className="rounded-control bg-ok/10 border border-ok/30 p-2.5 text-ok">
              <span className="font-semibold">User Administration:</span> Unlocked. You have full
              administrative privilege to manage NOC operator accounts.
            </div>
          </PermissionGate>

          <PermissionGate
            feature="alarm_clear"
            fallback={
              <div className="rounded-control bg-surface-2 p-2.5 text-ink-2">
                <span className="font-medium text-ink">Alarm Suppression:</span> Locked.
              </div>
            }
          >
            <div className="rounded-control bg-surface-2 p-2.5 text-ink">
              <span className="font-medium">Alarm Clearance Tool:</span> Authorized for batch
              acknowledgment.
            </div>
          </PermissionGate>
        </div>
      </div>
    </div>
  );
};
