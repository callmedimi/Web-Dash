/**
 * Route guard requiring an authenticated active session.
 * Automatically handles redirect to /login with return URL,
 * or /change-password if temporary password must be changed.
 */
import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/auth";

interface ProtectedRouteProps {
  children: React.ReactElement;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { t } = useTranslation();
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-bg text-ink">
        <div className="flex items-center gap-3 rounded-control border border-line bg-surface px-4 py-3 shadow-floating">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-signal border-t-transparent" />
          <span className="text-sm font-medium">{t("auth.authenticatingSession")}</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};
