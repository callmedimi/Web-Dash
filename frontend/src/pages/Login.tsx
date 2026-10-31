/**
 * Login Screen for Web-Dash NOC Console.
 * Follows Design Brief: calm, instrument-like, dense, zero gimmicks.
 */
import React, { useState } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { ApiError } from "@/api/types";

export const Login: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, isAuthenticated } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  // Return URL after successful authentication
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/";

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const trimmedUser = username.trim();
    if (!trimmedUser || !password) {
      setErrorMsg("Username and password are required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const user = await login({ username: trimmedUser, password });
      if (user.must_change_password) {
        navigate("/change-password", { replace: true });
      } else {
        navigate(from, { replace: true });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setErrorMsg(
            "Account temporarily locked due to too many failed login attempts. Please wait 15 minutes."
          );
        } else {
          setErrorMsg(err.message || "Invalid credentials.");
        }
      } else {
        setErrorMsg("Failed to connect to authentication service.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen w-screen items-center justify-center bg-bg p-4 text-ink">
      <div className="w-full max-w-sm rounded-dialog border border-line bg-surface p-6 shadow-floating">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold tracking-tight text-signal">Web-Dash</span>
            <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2">
              NOC
            </span>
          </div>
          <h1 className="mt-2 text-sm font-medium text-ink">Sign in to Operations Console</h1>
          <p className="mt-1 text-xs text-ink-2">
            Air-gapped Huawei VRP automation & telemetry console.
          </p>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div
            role="alert"
            className="mb-4 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault"
          >
            <div className="font-medium">Authentication Error</div>
            <div className="mt-0.5">{errorMsg}</div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="username"
              className="block text-xs font-medium text-ink-2 mb-1"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60 font-mono"
              placeholder="e.g. operator"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-xs font-medium text-ink-2 mb-1"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60 font-mono"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex h-8 w-full items-center justify-center rounded-control bg-signal px-4 text-xs font-medium text-white transition-opacity hover:opacity-95 focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60"
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Signing in...
              </span>
            ) : (
              "Sign in to console"
            )}
          </button>
        </form>

        {/* Security Notice */}
        <div className="mt-6 border-t border-line pt-3 text-[11px] text-ink-2/80">
          Strict session security & audit logging active. Inactivity timeout: 30 minutes.
        </div>
      </div>
    </div>
  );
};
