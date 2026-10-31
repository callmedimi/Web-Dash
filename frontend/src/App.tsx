/**
 * Web-Dash Frontend Root Component.
 * Configures QueryClientProvider, React Router, Route Guards, and Session Bootstrap.
 */
import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import { usePrefsStore } from "@/store/prefs";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Shell } from "@/components/layout/Shell";
import { Login } from "@/pages/Login";
import { ChangePassword } from "@/pages/ChangePassword";
import { Dashboard } from "@/pages/Dashboard";
import { KitchenSink } from "@/pages/KitchenSink";
import { PlaceholderScreen } from "@/pages/PlaceholderScreen";

export const AppContent: React.FC = () => {
  const { checkAuth } = useAuthStore();
  const { initPrefs } = usePrefsStore();

  useEffect(() => {
    initPrefs();
    checkAuth();
  }, [initPrefs, checkAuth]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/_ui" element={<KitchenSink />} />
      <Route
        path="/change-password"
        element={
          <ProtectedRoute>
            <ChangePassword />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Shell />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route
          path="devices/*"
          element={
            <PlaceholderScreen
              title="Devices & Inventory"
              subtitle="Managed Huawei VRP routers, health states, and CSV inventory import"
              step="9.3"
              features={[
                "Virtual-scrolling DataTable with 5,000+ routers",
                "Bulk actions: add to target set, tagging, on-demand jobs",
                "CSV import wizard with diff preview (new / modified / unchanged)",
                "Device detail tabs: Summary, Monitoring, Alarms, Configs, Jobs, Compliance",
              ]}
            />
          }
        />
        <Route
          path="targets/*"
          element={
            <PlaceholderScreen
              title="Target Sets"
              subtitle="Named, reusable static and dynamic router groupings"
              step="9.4"
              features={[
                "Static router selection by province and role",
                "Dynamic query sets: province = TEH AND role = PE",
                "Target set preview with count and device badges",
                "Direct reuse as targets input in all automation forms",
              ]}
            />
          }
        />
        <Route
          path="alarms/*"
          element={
            <PlaceholderScreen
              title="Alarm Center"
              subtitle="Correlated Zabbix and SSH live alarm suppression and clearance"
              step="9.5"
              features={[
                "Split view with filters drawer and saved queries",
                "Zabbix vs. SSH real-time mismatch detection",
                "One-click launch into Safe Changes planner",
                "On-demand live read-only status refresh from devices",
              ]}
            />
          }
        />
        <Route
          path="changes/*"
          element={
            <PlaceholderScreen
              title="Safe Changes Planner"
              subtitle="Two-phase dry-run, approval matrix, and blast radius controls"
              step="9.6"
              features={[
                "Plan -> Pre-check -> Approval -> Apply -> Verify stepper",
                "Dual-custody verification (approver ≠ requester)",
                "Live CLI diff preview and automated rollback plans",
                "Blast radius limit enforcement and risk scoring",
              ]}
            />
          }
        />
        <Route
          path="jobs/*"
          element={
            <PlaceholderScreen
              title="Automation Jobs"
              subtitle="Real-time execution timelines, log streaming, and task management"
              step="9.7"
              features={[
                "SSE live event streaming without polling",
                "RunTimeline and resizable split LogViewer",
                "Immediate cancellation signal handling and drain",
                "Downloadable artifacts: CSV, XLSX, JSON",
              ]}
            />
          }
        />
        <Route
          path="reports/*"
          element={
            <PlaceholderScreen
              title="Reports & Analytics"
              subtitle="Down-links reports, license expiry warnings, and daily NOC digest"
              step="9.8"
              features={[
                "Target-based down-links query and analytics",
                "Automated scheduled cron reports",
                "Run-to-run comparison with new and recovered link highlights",
                "Executive PDF / Excel exports",
              ]}
            />
          }
        />
        <Route
          path="monitoring/*"
          element={
            <PlaceholderScreen
              title="Monitoring Hub"
              subtitle="Fleet health, telemetry status, and Grafana integration"
              step="9.9"
              features={[
                "Fleet availability, CPU, RAM, temperature from Zabbix",
                "Interface explorer with rate graphs and synchronized cursors",
                "Grafana deep-link panels and doctor diagnostics",
                "Offline cache with stale indicators during Zabbix outages",
              ]}
            />
          }
        />
        <Route
          path="configs/*"
          element={
            <PlaceholderScreen
              title="Configs & Compliance"
              subtitle="Automated backup snapshots, git-style diffs, and compliance checks"
              step="9.10"
              features={[
                "Device config snapshot timeline and versioning",
                "Side-by-side DiffViewer across any two snapshots",
                "Province-level compliance rules and violation remediation",
                "Automated nightly configuration backup pipeline",
              ]}
            />
          }
        />
        <Route
          path="tools/*"
          element={
            <PlaceholderScreen
              title="Diagnostics & Tools"
              subtitle="VRF routing, PTP sync, ARP/MAC lookup, session extractor, and command runner"
              step="9.11"
              features={[
                "VRF routing prefix lookup with interactive path graph",
                "PTP telecom synchronization tracer and verdict analyzer",
                "ARP/MAC site database lookup and collection jobs",
                "SecureCRT session extractor from CSV",
                "Allow-listed read-only command runner across fleet",
              ]}
            />
          }
        />
        <Route
          path="admin/*"
          element={
            <PlaceholderScreen
              title="System Administration"
              subtitle="User roles, credential vault, integrations, schedules, and audit log"
              step="9.12"
              features={[
                "Role-based access control (god, admin, operator, viewer)",
                "Hardware-grade Fernet encrypted credential vault",
                "Zabbix & Grafana integration doctor tests",
                "Immutable append-only audit trail export",
              ]}
            />
          }
        />
        <Route path="_ui" element={<KitchenSink />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
