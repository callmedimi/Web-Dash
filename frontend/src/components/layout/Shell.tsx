/**
 * Main NOC Console Application Shell.
 * Conforms strictly to plan/08_PHASE6_UI_DESIGN_SYSTEM.md §4:
 *
 * ┌──────────┬───────────────────────────────────────────────────────────────┐
 * │ Rail     │ Top bar: breadcrumb · global search (Ctrl+K) · job tray · user│
 * │ (icons + ├───────────────────────────────────────────────────────────────┤
 * │ labels,  │ Page header: title · primary action (right)                   │
 * │ collaps- │ ───────────────────────────────────────────────────────────── │
 * │ ible)    │ Content: tables / split views / timelines — fills the height  │
 * │          │ (no page-level scroll; panels scroll internally)              │
 * └──────────┴───────────────────────────────────────────────────────────────┘
 */
import React from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  Server,
  Crosshair,
  AlertTriangle,
  GitCommit,
  Terminal,
  FileText,
  Activity,
  FileCode,
  Wrench,
  Settings,
  ChevronLeft,
  ChevronRight,
  Search,
  Menu,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { usePrefsStore } from "@/store/prefs";
import { IdleTimeoutNotice } from "@/components/auth/IdleTimeoutNotice";
import { CommandPalette } from "@/components/ui/CommandPalette";

export const Shell: React.FC = () => {
  const { t } = useTranslation();
  const { user, readOnly, logout } = useAuthStore();
  const {
    resolvedTheme,
    density,
    lang,
    railCollapsed,
    toggleRail,
    toggleTheme,
    toggleDensity,
    toggleLanguage,
  } = usePrefsStore();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const handleOpenSearch = () => {
    window.dispatchEvent(new CustomEvent("open-command-palette"));
  };

  const navItems = [
    { to: "/", label: t("nav.overview"), icon: LayoutDashboard },
    { to: "/devices", label: t("nav.devices"), icon: Server },
    { to: "/targets", label: t("nav.targets"), icon: Crosshair },
    { to: "/alarms", label: t("nav.alarms"), icon: AlertTriangle },
    { to: "/changes", label: t("nav.changes"), icon: GitCommit },
    { to: "/jobs", label: t("nav.jobs"), icon: Terminal },
    { to: "/reports", label: t("nav.reports"), icon: FileText },
    { to: "/monitoring", label: t("nav.monitoring"), icon: Activity },
    { to: "/configs", label: t("nav.configs"), icon: FileCode },
    { to: "/tools", label: t("nav.tools"), icon: Wrench },
    ...(user?.role === "god" || user?.role === "admin"
      ? [{ to: "/admin", label: t("nav.admin"), icon: Settings }]
      : []),
  ];

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg text-ink">
      <IdleTimeoutNotice />
      <CommandPalette />

      {/* Top Bar */}
      <header className="flex h-12 flex-shrink-0 items-center justify-between border-b border-line bg-surface px-3 sm:px-4 z-20">
        {/* Left: Rail toggle button + Brand & Breadcrumb */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={toggleRail}
            aria-label={railCollapsed ? t("nav.expand") : t("nav.collapse")}
            title={railCollapsed ? t("nav.expand") : t("nav.collapse")}
            className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal transition-colors"
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-tight text-signal">
              {t("common.appTitle")}
            </span>
            <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2 hidden sm:inline">
              {t("common.noc")}
            </span>
          </div>
          <span className="text-ink-2 hidden sm:inline">/</span>
          <span className="text-xs font-medium text-ink hidden md:inline">
            {t("common.consoleTitle")}
          </span>
        </div>

        {/* Center: Global Search Bar (Ctrl+K) */}
        <div className="flex-1 max-w-xs mx-3 hidden md:block">
          <button
            type="button"
            onClick={handleOpenSearch}
            className="flex w-full items-center justify-between rounded-control border border-line bg-surface-2/60 px-2.5 py-1 text-xs text-ink-2 transition-colors hover:border-signal hover:bg-surface-2 focus:outline-none focus:ring-1 focus:ring-signal"
          >
            <span className="flex items-center gap-1.5 truncate">
              <Search className="h-3.5 w-3.5 text-ink-2" />
              <span className="text-[11px] truncate">{t("nav.search")}</span>
            </span>
            <kbd className="rounded border border-line bg-surface px-1 py-0.2 text-[10px] font-mono text-ink-2">
              Ctrl+K
            </kbd>
          </button>
        </div>

        {/* Right: Quick Preferences, Status, User Profile, Logout */}
        <div className="flex items-center gap-2">
          {/* Mobile Search Icon */}
          <button
            type="button"
            onClick={handleOpenSearch}
            aria-label="Search"
            className="md:hidden inline-flex h-7 w-7 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <Search className="h-3.5 w-3.5" />
          </button>

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
            <span className="text-[11px] font-medium hidden lg:inline">
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
            <span className="text-[11px] font-medium hidden lg:inline">
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
            <span className="font-medium hidden sm:inline">{t("common.systemReady")}</span>
          </div>

          <div className="h-4 w-px bg-line mx-0.5" />

          {user && (
            <div className="flex items-center gap-2">
              <div className="flex flex-col text-start">
                <span className="text-xs font-medium leading-none text-ink truncate max-w-[120px]">
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

      {/* Body Area: Left Navigation Rail + Main Viewport */}
      <div className="flex flex-1 overflow-hidden">
        {/* Navigation Rail */}
        <aside
          className={`flex flex-shrink-0 flex-col border-e border-line bg-surface transition-all duration-150 z-10 ${
            railCollapsed ? "w-14" : "w-52"
          }`}
        >
          <nav className="flex-1 overflow-y-auto p-1.5 space-y-0.5 scrollbar-thin">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                title={railCollapsed ? item.label : undefined}
                className={({ isActive }) =>
                  `group flex items-center gap-2.5 rounded-control px-2.5 py-2 text-xs transition-colors ${
                    isActive
                      ? "bg-signal/15 text-signal font-semibold border-e-2 border-signal rtl:border-e-0 rtl:border-s-2"
                      : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  }`
                }
              >
                <item.icon className="h-4 w-4 shrink-0 text-current" />
                {!railCollapsed && <span className="truncate">{item.label}</span>}
              </NavLink>
            ))}
          </nav>

          {/* Rail Collapse Toggle Footer */}
          <div className="border-t border-line p-2">
            <button
              type="button"
              onClick={toggleRail}
              title={railCollapsed ? t("nav.expand") : t("nav.collapse")}
              className="flex w-full items-center justify-center rounded-control p-1 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
            >
              {railCollapsed ? (
                <ChevronRight className="h-4 w-4 rtl:rotate-180" />
              ) : (
                <div className="flex items-center gap-1.5 w-full px-1">
                  <ChevronLeft className="h-4 w-4 rtl:rotate-180" />
                  <span className="text-[11px] font-medium">{t("nav.collapse")}</span>
                </div>
              )}
            </button>
          </div>
        </aside>

        {/* Main Content Viewport */}
        <main className="flex flex-1 flex-col overflow-hidden bg-bg">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
