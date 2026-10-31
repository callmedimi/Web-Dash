/**
 * Main NOC Console Application Shell.
 * Provides consistent header, session status, user indicator, and internal scroll panels.
 */
import React from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { IdleTimeoutNotice } from "@/components/auth/IdleTimeoutNotice";

export const Shell: React.FC = () => {
  const { user, readOnly, logout } = useAuthStore();
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
            <span className="font-semibold tracking-tight text-signal">Web-Dash</span>
            <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2">
              NOC
            </span>
          </div>
          <span className="text-ink-2">/</span>
          <span className="text-xs font-medium text-ink">Huawei VRP Console</span>
        </div>

        {/* Right: Status, Read-Only indicator, User Profile, Logout */}
        <div className="flex items-center gap-3">
          {readOnly && (
            <span className="inline-flex items-center gap-1 rounded-control bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">
              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
              READ-ONLY
            </span>
          )}

          <div className="inline-flex items-center gap-1.5 text-xs text-ok">
            <span className="h-2 w-2 rounded-full bg-ok" />
            <span className="font-medium">System Ready</span>
          </div>

          <div className="h-4 w-px bg-line" />

          {user && (
            <div className="flex items-center gap-2">
              <div className="flex flex-col text-right">
                <span className="text-xs font-medium leading-none text-ink">
                  {user.display_name}
                </span>
                <span className="text-[10px] font-mono uppercase text-ink-2 leading-none mt-0.5">
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
            Logout
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
