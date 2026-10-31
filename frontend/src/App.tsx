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
import { Devices } from "@/pages/Devices";
import { TargetSets } from "@/pages/TargetSets";
import { AlarmCenter } from "@/pages/AlarmCenter";
import { SafeChanges } from "@/pages/SafeChanges";
import { Jobs } from "@/pages/Jobs";
import { Reports } from "@/pages/Reports";
import { Monitoring } from "@/pages/Monitoring";
import { Configs } from "@/pages/Configs";
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
        <Route path="devices" element={<Devices />} />
        <Route path="devices/:id" element={<Devices />} />
        <Route path="targets" element={<TargetSets />} />
        <Route path="alarms" element={<AlarmCenter />} />
        <Route path="changes" element={<SafeChanges />} />
        <Route path="changes/:id" element={<SafeChanges />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:id" element={<Jobs />} />
        <Route path="reports" element={<Reports />} />
        <Route path="reports/*" element={<Reports />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="monitoring/*" element={<Monitoring />} />
        <Route path="configs" element={<Configs />} />
        <Route path="configs/*" element={<Configs />} />
        <Route path="compliance" element={<Configs />} />
        <Route path="compliance/*" element={<Configs />} />
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
