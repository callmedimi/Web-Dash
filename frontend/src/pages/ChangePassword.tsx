/**
 * Password Change Screen for Mandatory / Self-Service Credentials Update.
 */
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { ApiError } from "@/api/types";

export const ChangePassword: React.FC = () => {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { user, changePassword } = useAuthStore();
  const navigate = useNavigate();

  const validatePolicy = (): string | null => {
    if (!currentPassword) return "Current password is required.";
    if (!newPassword) return "New password is required.";
    if (newPassword.length < 8) return "New password must be at least 8 characters long.";
    if (newPassword === currentPassword) return "New password must be different from current password.";
    if (newPassword !== confirmPassword) return "Password confirmation does not match.";
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    const clientErr = validatePolicy();
    if (clientErr) {
      setErrorMsg(clientErr);
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setSuccessMsg("Password updated successfully. Redirecting...");
      setTimeout(() => {
        navigate("/", { replace: true });
      }, 1200);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMsg(err.message || "Failed to update password.");
      } else {
        setErrorMsg("Failed to communicate with authentication service.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen w-screen items-center justify-center bg-bg p-4 text-ink">
      <div className="w-full max-w-md rounded-dialog border border-line bg-surface p-6 shadow-floating">
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold tracking-tight text-signal">Web-Dash</span>
            <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2">
              SECURITY
            </span>
          </div>
          <h1 className="mt-2 text-sm font-medium text-ink">
            {user?.must_change_password ? "Mandatory Password Update" : "Change Password"}
          </h1>
          <p className="mt-1 text-xs text-ink-2">
            {user?.must_change_password
              ? "Your temporary password must be updated before accessing network operations."
              : "Update your console login credentials."}
          </p>
        </div>

        {errorMsg && (
          <div
            role="alert"
            className="mb-4 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault"
          >
            <div className="font-medium">Password Policy Error</div>
            <div className="mt-0.5">{errorMsg}</div>
          </div>
        )}

        {successMsg && (
          <div
            role="status"
            className="mb-4 rounded-control border border-ok/30 bg-ok/10 p-3 text-xs text-ok"
          >
            <div className="font-medium">{successMsg}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="currentPassword"
              className="block text-xs font-medium text-ink-2 mb-1"
            >
              Current Password
            </label>
            <input
              id="currentPassword"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink font-mono focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60"
            />
          </div>

          <div>
            <label
              htmlFor="newPassword"
              className="block text-xs font-medium text-ink-2 mb-1"
            >
              New Password
            </label>
            <input
              id="newPassword"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink font-mono focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60"
            />
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="block text-xs font-medium text-ink-2 mb-1"
            >
              Confirm New Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink font-mono focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60"
            />
          </div>

          {/* Policy hints */}
          <div className="rounded-control bg-surface-2 p-2.5 text-[11px] text-ink-2">
            <span className="font-medium text-ink">Password Requirements:</span>
            <ul className="mt-1 list-disc list-inside space-y-0.5">
              <li>Minimum 8 characters</li>
              <li>Must contain uppercase and lowercase letters</li>
              <li>Must contain at least one digit and one special character</li>
            </ul>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex h-8 w-full items-center justify-center rounded-control bg-signal px-4 text-xs font-medium text-white transition-opacity hover:opacity-95 focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60"
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Updating password...
              </span>
            ) : (
              "Update password"
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
