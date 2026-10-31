/**
 * Primary Dashboard / Operations Overview Screen.
 * Calm, instrument-like layout fulfilling NOC requirements.
 * Fully localized with Persian and English support.
 */
import React from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/auth";
import { PermissionGate } from "@/components/auth/PermissionGate";

export const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-4 space-y-4">
      {/* Page Header */}
      <div className="flex items-center justify-between border-b border-line pb-3">
        <div>
          <h1 className="text-base font-semibold text-ink">{t("dashboard.overviewTitle")}</h1>
          <p className="text-xs text-ink-2">{t("dashboard.overviewSubtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-control bg-surface-2 px-2 py-1 text-xs font-mono text-ink-2">
            {t("dashboard.envAirGapped")}
          </span>
        </div>
      </div>

      {/* Primary Status Metric Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">{t("dashboard.managedRouters")}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-ink dir-ltr">--</span>
            <span className="text-xs text-ink-2">{t("dashboard.devices")}</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-xs text-ok">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            {t("dashboard.driverReady")}
          </div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">{t("dashboard.activeAlarms")}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-ink dir-ltr">0</span>
            <span className="text-xs text-ok">{t("dashboard.critical")}</span>
          </div>
          <div className="mt-2 text-xs text-ink-2">{t("dashboard.telemetryActive")}</div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">{t("dashboard.safeChanges")}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold font-mono text-signal">
              {t("dashboard.twoPhase")}
            </span>
            <span className="text-xs text-ink-2">{t("dashboard.dryRunApply")}</span>
          </div>
          <div className="mt-2 text-xs text-ink-2">{t("dashboard.autoRollback")}</div>
        </div>

        <div className="rounded-control border border-line bg-surface p-3">
          <div className="text-[11px] font-medium text-ink-2">{t("dashboard.currentSession")}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-base font-semibold font-mono text-ink dir-ltr">
              {user?.username}
            </span>
            <span className="rounded-control bg-surface-2 px-1 text-[10px] font-mono uppercase text-ink-2 dir-ltr">
              {user?.role}
            </span>
          </div>
          <div className="mt-2 text-xs text-ink-2">{t("dashboard.csrfProtected")}</div>
        </div>
      </div>

      {/* Permission Gate Demo / Role-Specific Actions */}
      <div className="rounded-control border border-line bg-surface p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-2 mb-2">
          {t("dashboard.authMatrixTitle")}
        </h2>
        <div className="space-y-2 text-xs">
          <PermissionGate
            feature="user_management"
            fallback={
              <div className="rounded-control bg-surface-2 p-2.5 text-ink-2">
                {t("dashboard.userAdminLocked")}
              </div>
            }
          >
            <div className="rounded-control bg-ok/10 border border-ok/30 p-2.5 text-ok">
              {t("dashboard.userAdminUnlocked")}
            </div>
          </PermissionGate>

          <PermissionGate
            feature="alarm_clear"
            fallback={
              <div className="rounded-control bg-surface-2 p-2.5 text-ink-2">
                {t("dashboard.alarmToolLocked")}
              </div>
            }
          >
            <div className="rounded-control bg-surface-2 p-2.5 text-ink">
              {t("dashboard.alarmToolUnlocked")}
            </div>
          </PermissionGate>
        </div>
      </div>
    </div>
  );
};
