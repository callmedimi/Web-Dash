/**
 * Permission and Role Gate Component for fine-grained authorization.
 */
import React from "react";
import { useAuthStore } from "@/store/auth";
import { UserRole } from "@/api/types";

interface PermissionGateProps {
  feature?: string;
  roles?: UserRole[];
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export const PermissionGate: React.FC<PermissionGateProps> = ({
  feature,
  roles,
  fallback = null,
  children,
}) => {
  const { user } = useAuthStore();

  if (!user) {
    return <>{fallback}</>;
  }

  // God role always bypasses all permission checks
  if (user.role === "god") {
    return <>{children}</>;
  }

  // Check role restriction if specified
  if (roles && roles.length > 0) {
    if (!roles.includes(user.role)) {
      return (
        <>
          {fallback || (
            <div className="rounded-control border border-line bg-surface p-4 text-xs text-ink-2">
              <span className="font-medium text-fault">Access Restricted:</span> Your role (
              <span className="font-mono">{user.role}</span>) does not have permission to view this
              action.
            </div>
          )}
        </>
      );
    }
  }

  // Check feature permission if specified
  if (feature) {
    const hasFeature = Boolean(user.features?.[feature]);
    if (!hasFeature) {
      return (
        <>
          {fallback || (
            <div className="rounded-control border border-line bg-surface p-4 text-xs text-ink-2">
              <span className="font-medium text-fault">Feature Disabled:</span> The feature{" "}
              <span className="font-mono">{feature}</span> is not enabled for your account.
            </div>
          )}
        </>
      );
    }
  }

  return <>{children}</>;
};
