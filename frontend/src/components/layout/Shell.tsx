/**
 * Main NOC Console Application Shell.
 * Clean, Vibrant, Clutter-Free Layout with Granular RBAC and Pure Fa/En Localization.
 */
import React from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  Activity,
  Settings,
  ChevronLeft,
  ChevronRight,
  Search,
  Menu,
  FileSpreadsheet,
  Network,
  ShieldCheck,
  FileArchive,
  Clock,
  Radio,
  LogOut,
  Moon,
  Sun,
  User,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { usePrefsStore } from "@/store/prefs";
import { IdleTimeoutNotice } from "@/components/auth/IdleTimeoutNotice";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { CsvOperationsHub } from "@/components/operations/CsvOperationsHub";
import { NetworkCredentialsBar } from "@/components/layout/NetworkCredentialsBar";

export const Shell: React.FC = () => {
  const { t } = useTranslation();
  const { user, readOnly, logout } = useAuthStore();
  const {
    resolvedTheme,
    lang,
    railCollapsed,
    toggleRail,
    toggleTheme,
    toggleLanguage,
  } = usePrefsStore();
  const navigate = useNavigate();

  const [globalCsvOpen, setGlobalCsvOpen] = React.useState(false);

  // User Permission Helper (Enforces Granular RBAC configured in Admin Panel)
  const hasFeatureAccess = (featKey: string | string[]) => {
    if (!user) return false;
    if (user.role === "god" || user.role === "admin") return true;
    const features = user.features || {};
    const keys = Array.isArray(featKey) ? featKey : [featKey];
    return keys.some((k) => {
      const val = (features as any)[k];
      if (typeof val === "boolean") return val;
      if (val && typeof val === "object" && "granted" in val) return Boolean(val.granted);
      return false;
    });
  };

  // Pure Operational NOC Navigation Sections (Categorized, RBAC Filtered & Clean Fa/En)
  const navSections = [
    {
      id: "core",
      title: t("nav.secOps", "عملیات شبکه"),
      items: [
        {
          to: "/",
          label: t("nav.overview", "داشبورد عملیاتی"),
          icon: LayoutDashboard,
          activeColor: "text-signal",
          visible: true,
        },
        {
          to: "/alarms",
          label: t("nav.alarms", "پاکسازی آلارم"),
          icon: AlertTriangle,
          activeColor: "text-warn",
          visible: hasFeatureAccess(["alarm_clear_manual", "alarm_clear_bulk"]),
        },
        {
          to: "/reports",
          label: t("nav.reports", "گزارش‌ها و ترانک‌ها"),
          icon: FileText,
          activeColor: "text-signal",
          visible: hasFeatureAccess("reporting"),
        },
        {
          to: "/monitoring",
          label: t("nav.monitoring", "پایش و تلمتری زبیکس"),
          icon: Activity,
          activeColor: "text-ok",
          badge: "Live",
          visible:
            hasFeatureAccess(["zabbix_search", "zabbix_db_refresh"]) ||
            user?.role === "god" ||
            user?.role === "admin",
        },
      ],
    },
    {
      id: "tools",
      title: t("nav.secTools", "ابزارهای تشخیصی"),
      items: [
        {
          to: "/tools/vrf-routing",
          label: t("nav.routing", "بررسی روتینگ BGP و VRF"),
          icon: Network,
          activeColor: "text-sky-400",
          visible: hasFeatureAccess("vrf_routing"),
        },
        {
          to: "/tools/license",
          label: t("nav.license", "مدیریت و تمدید لایسنس"),
          icon: ShieldCheck,
          activeColor: "text-emerald-400",
          visible: hasFeatureAccess(["license_check", "license_renewal_admin"]),
        },
        {
          to: "/tools/sessions",
          label: t("nav.sessions", "سشن‌های SecureCRT"),
          icon: FileArchive,
          activeColor: "text-purple-400",
          visible: hasFeatureAccess("session_extractor"),
        },
        {
          to: "/tools/arp",
          label: t("nav.arpMac", "استعلام ARP و MAC"),
          icon: Search,
          activeColor: "text-indigo-400",
          visible: hasFeatureAccess(["zabbix_search", "code_site_search"]),
        },
        {
          to: "/tools/ptp",
          label: t("nav.ptp", "عیب‌یابی ساعت PTP"),
          icon: Clock,
          activeColor: "text-rose-400",
          visible: hasFeatureAccess("ptp_troubleshoot"),
        },
      ],
    },
    {
      id: "admin",
      title: t("nav.secAdmin", "مدیریت"),
      items: [
        {
          to: "/admin",
          label: t("nav.admin", "تنظیمات و دسترسی‌ها"),
          icon: Settings,
          activeColor: "text-slate-300",
          visible:
            user?.role === "god" ||
            user?.role === "admin" ||
            hasFeatureAccess(["user_management", "permission_management"]),
        },
      ],
    },
  ];

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      navigate("/login");
    }
  };

  const handleOpenSearch = () => {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })
    );
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg text-ink">
      <IdleTimeoutNotice />
      <CommandPalette />

      {/* Global CSV Operations Modal */}
      {globalCsvOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-4xl">
            <CsvOperationsHub
              initialTab="alarm_clear"
              onClose={() => setGlobalCsvOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Top Header Bar */}
      <header className="flex h-12 flex-shrink-0 items-center justify-between border-b border-line bg-surface/90 backdrop-blur-md px-3 sm:px-4 z-20 shadow-xs">
        {/* Left: Rail toggle button + Vibrant Brand Title */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleRail}
            aria-label={railCollapsed ? t("nav.expand") : t("nav.collapse")}
            title={railCollapsed ? t("nav.expand") : t("nav.collapse")}
            className="inline-flex h-7 w-7 items-center justify-center rounded-control border border-line/80 bg-surface-2/60 text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none transition-colors"
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-signal to-sky-400 text-white shadow-xs">
              <Radio className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold tracking-tight text-ink text-sm">
                Netmate
              </span>
              <span className="rounded-control bg-signal/15 px-1.5 py-0.2 text-[10px] font-mono font-bold text-signal border border-signal/20">
                NOC
              </span>
            </div>
          </div>
        </div>

        {/* Center: Global Search Bar (Ctrl+K) */}
        <div className="flex-1 max-w-xs mx-4 hidden md:block">
          <button
            type="button"
            onClick={handleOpenSearch}
            className="flex w-full items-center justify-between rounded-control border border-line/80 bg-surface-2/40 px-2.5 py-1 text-xs text-ink-2 transition-all hover:border-signal/60 hover:bg-surface-2 focus:outline-none"
          >
            <span className="flex items-center gap-1.5 truncate">
              <Search className="h-3.5 w-3.5 text-signal" />
              <span className="text-[11px] truncate text-ink-2">
                {t("nav.search", "جستجو... (Ctrl+K)")}
              </span>
            </span>
            <kbd className="rounded border border-line bg-surface px-1.5 py-0.2 text-[10px] font-mono text-ink-2 shadow-xs">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* Right: Quick Tools, Credentials Popover, Preferences & User */}
        <div className="flex items-center gap-2">
          {/* Shared Network Credentials Popover Button (De-cluttered & Sleek) */}
          <NetworkCredentialsBar />

          {/* Quick CSV Hub Button */}
          <button
            type="button"
            onClick={() => setGlobalCsvOpen(true)}
            title={t("nav.csvOps", "عملیات فایل CSV")}
            className="inline-flex h-8 items-center gap-1.5 rounded-control border border-signal/40 bg-signal/10 px-2.5 text-xs font-semibold text-signal hover:bg-signal/20 transition-all shadow-xs"
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{t("nav.csvOps", "عملیات فایل CSV")}</span>
          </button>

          {/* Mobile Search Icon */}
          <button
            type="button"
            onClick={handleOpenSearch}
            aria-label="Search"
            className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-control border border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <Search className="h-3.5 w-3.5" />
          </button>

          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={t("prefs.theme")}
            title={resolvedTheme === "dark" ? t("prefs.themeLight") : t("prefs.themeDark")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-control border border-line/80 bg-surface text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            {resolvedTheme === "dark" ? (
              <Sun className="h-3.5 w-3.5 text-warn" />
            ) : (
              <Moon className="h-3.5 w-3.5 text-signal" />
            )}
          </button>

          {/* Language Switcher Button (FA / EN) */}
          <button
            type="button"
            onClick={toggleLanguage}
            aria-label={t("prefs.language")}
            title={lang === "en" ? "تغییر به فارسی" : "Switch to English"}
            className="inline-flex h-8 items-center px-2 rounded-control border border-line/80 bg-surface text-xs font-bold text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            {lang === "en" ? "FA" : "EN"}
          </button>

          <div className="h-4 w-px bg-line/80 mx-1 hidden sm:block" />

          {/* User Profile Chip */}
          {user && (
            <div className="flex items-center gap-2 ps-1">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-signal/15 text-signal font-bold text-xs">
                {user.display_name?.charAt(0) || <User className="h-3.5 w-3.5" />}
              </div>
              <div className="flex flex-col text-start hidden lg:flex">
                <span className="text-xs font-semibold leading-none text-ink truncate max-w-[110px]">
                  {user.display_name}
                </span>
                <span className="text-[10px] font-mono text-signal uppercase leading-none mt-1 dir-ltr">
                  {user.role}
                </span>
              </div>
            </div>
          )}

          {/* Logout Button */}
          <button
            type="button"
            onClick={handleLogout}
            title={t("common.logout", "خروج")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-control border border-line/80 bg-surface text-ink-2 transition-colors hover:bg-fault/15 hover:text-fault hover:border-fault/30"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* Body Area: Navigation Rail + Main Viewport */}
      <div className="flex flex-1 overflow-hidden">
        {/* Navigation Rail (Vibrant, Alive & Clean) */}
        <aside
          className={`flex flex-shrink-0 flex-col border-e border-line bg-surface/95 backdrop-blur-md transition-all duration-200 z-10 ${
            railCollapsed ? "w-14" : "w-56"
          }`}
        >
          <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4 scrollbar-thin">
            {navSections.map((section) => {
              const visibleItems = section.items.filter((item) => item.visible);
              if (visibleItems.length === 0) return null;

              return (
                <div key={section.id} className="space-y-1">
                  {!railCollapsed && (
                    <div className="px-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-ink-2/70 select-none">
                      {section.title}
                    </div>
                  )}

                  {visibleItems.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      title={railCollapsed ? item.label : undefined}
                      className={({ isActive }) =>
                        `group flex items-center gap-2.5 rounded-control px-2.5 py-2 text-xs font-medium transition-all ${
                          isActive
                            ? "bg-gradient-to-r from-signal/20 via-signal/10 to-transparent text-signal font-semibold border-s-3 border-signal shadow-xs"
                            : "text-ink-2 hover:bg-surface-2 hover:text-ink hover:translate-x-0.5 rtl:hover:-translate-x-0.5"
                        }`
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0 transition-transform group-hover:scale-110" />
                      {!railCollapsed && (
                        <div className="flex flex-1 items-center justify-between truncate">
                          <span className="truncate">{item.label}</span>
                          {(item as any).badge && (
                            <span className="flex items-center gap-1 rounded-full bg-ok/15 px-1.5 py-0.2 text-[9px] font-bold text-ok ring-1 ring-ok/30">
                              <span className="h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
                              {(item as any).badge}
                            </span>
                          )}
                        </div>
                      )}
                    </NavLink>
                  ))}
                </div>
              );
            })}
          </nav>

          {/* Rail Collapse Toggle Footer & System Pulse */}
          <div className="border-t border-line/60 p-2 bg-surface/50">
            <div className="flex items-center justify-between">
              {!railCollapsed && (
                <div className="flex items-center gap-1.5 px-2 text-[10px] text-ok font-medium">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-ok" />
                  </span>
                  <span>{readOnly ? t("common.readOnly", "فقط‌خواندنی") : "سیستم آنلاین"}</span>
                </div>
              )}

              <button
                type="button"
                onClick={toggleRail}
                title={railCollapsed ? t("nav.expand") : t("nav.collapse")}
                className="flex items-center justify-center rounded-control p-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
              >
                {railCollapsed ? (
                  <ChevronRight className="h-4 w-4 rtl:rotate-180" />
                ) : (
                  <ChevronLeft className="h-4 w-4 rtl:rotate-180" />
                )}
              </button>
            </div>
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
