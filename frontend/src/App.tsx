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
