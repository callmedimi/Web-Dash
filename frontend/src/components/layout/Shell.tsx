/**
 * Main NOC Console Application Shell.
 * Provides consistent header, session status, user indicator,
 * theme/density/i18n controls, and internal scroll panels.
 */
import React from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/auth";
import { usePrefsStore } from "@/store/prefs";
import { IdleTimeoutNotice } from "@/components/auth/IdleTimeoutNotice";

export const Shell: React.FC = () => {
  const { t } = useTranslation();
  const { user, readOnly, logout } = useAuthStore();
  const { resolvedTheme, density, lang, toggleTheme, toggleDensity, toggleLanguage } =
    usePrefsStore();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg text-ink">
      <IdleTimeoutNotice />

      {/* Top Bar */}
      <header className="flex h-12 flex-shrink-0 items-center justify-between border-b border-line bg-surface px-4">
        {/* Left: Brand & Breadcrumb */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-tight text-signal">
              {t("common.appTitle")}
            </span>
            <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2">
              {t("common.noc")}
            </span>
          </div>
          <span className="text-ink-2">/</span>
          <span className="text-xs font-medium text-ink">{t("common.consoleTitle")}</span>
        </div>

        {/* Right: Quick Preferences, Status, User Profile, Logout */}
        <div className="flex items-center gap-2.5">
          {/* Theme Toggle (Paper ☀️ / Night 🌙) */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={t("prefs.theme")}
            title={`${t("prefs.theme")}: ${resolvedTheme === "dark" ? t("prefs.themeDark") : t("prefs.themeLight")}`}
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            <span className="font-mono text-[11px]">
              {resolvedTheme === "dark" ? "🌙" : "☀️"}
            </span>
            <span className="text-[11px] font-medium hidden sm:inline">
              {resolvedTheme === "dark" ? t("prefs.themeDark") : t("prefs.themeLight")}
            </span>
          </button>

          {/* Density Toggle (Compact ↕️ / Comfortable ↔️) */}
          <button
            type="button"
            onClick={toggleDensity}
            aria-label={t("prefs.density")}
            title={`${t("prefs.density")}: ${density === "compact" ? t("prefs.densityCompact") : t("prefs.densityComfortable")}`}
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-xs text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            <span className="font-mono text-[11px]">↕️</span>
            <span className="text-[11px] font-medium hidden sm:inline">
              {density === "compact" ? t("prefs.densityCompact") : t("prefs.densityComfortable")}
            </span>
          </button>

          {/* Language Switcher (EN / FA) */}
          <button
            type="button"
            onClick={toggleLanguage}
            aria-label={t("prefs.language")}
            title={`${t("prefs.language")}: ${lang === "en" ? "فارسی" : "English"}`}
            className="inline-flex h-7 items-center rounded-control border border-line bg-surface px-2 text-[11px] font-semibold text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            {lang === "en" ? "FA" : "EN"}
          </button>

          <div className="h-4 w-px bg-line mx-0.5" />

          {readOnly && (
            <span className="inline-flex items-center gap-1 rounded-control bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">
              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
              {t("common.readOnly")}
            </span>
          )}

          <div className="inline-flex items-center gap-1.5 text-xs text-ok">
            <span className="h-2 w-2 rounded-full bg-ok" />
            <span className="font-medium">{t("common.systemReady")}</span>
          </div>

          <div className="h-4 w-px bg-line mx-0.5" />

          {user && (
            <div className="flex items-center gap-2">
              <div className="flex flex-col text-start">
                <span className="text-xs font-medium leading-none text-ink">
                  {user.display_name}
                </span>
                <span className="text-[10px] font-mono uppercase text-ink-2 leading-none mt-0.5 dir-ltr">
                  {user.role}
                </span>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex h-7 items-center justify-center rounded-control border border-line bg-surface px-2.5 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            {t("common.logout")}
          </button>
        </div>
      </header>

      {/* Main Content Area: fills height, panels scroll internally */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
};
