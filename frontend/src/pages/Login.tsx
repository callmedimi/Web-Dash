/**
 * Login Screen for Web-Dash NOC Console.
 * Follows Design Brief: calm, instrument-like, dense, zero gimmicks.
 * Fully localized with theme and language toggles.
 */
import React, { useState } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/auth";
import { usePrefsStore } from "@/store/prefs";
import { ApiError } from "@/api/types";

export const Login: React.FC = () => {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, isAuthenticated } = useAuthStore();
  const { resolvedTheme, lang, toggleTheme, toggleLanguage } = usePrefsStore();
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
      setErrorMsg(t("auth.requiredFields"));
      return;
    }

    setIsSubmitting(true);
    try {
      await login({ username: trimmedUser, password });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setErrorMsg(t("auth.accountLocked"));
        } else {
          setErrorMsg(err.message || t("auth.invalidCredentials"));
        }
      } else {
        setErrorMsg(t("auth.authError"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen w-screen items-center justify-center bg-bg p-4 text-ink">
      <div className="w-full max-w-sm rounded-dialog border border-line bg-surface p-6 shadow-floating">
        {/* Header with Quick Theme and Language Controls */}
        <div className="mb-6 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold tracking-tight text-signal">
                {t("common.appTitle")}
              </span>
              <span className="rounded-control bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono uppercase text-ink-2">
                {t("common.noc")}
              </span>
            </div>
            <h1 className="mt-2 text-sm font-medium text-ink">{t("auth.signInTitle")}</h1>
            <p className="mt-1 text-xs text-ink-2">{t("auth.signInSubtitle")}</p>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={t("prefs.theme")}
              title={`${t("prefs.theme")}: ${resolvedTheme === "dark" ? t("prefs.themeDark") : t("prefs.themeLight")}`}
              className="inline-flex h-6 w-6 items-center justify-center rounded-control border border-line bg-surface text-xs text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {resolvedTheme === "dark" ? "🌙" : "☀️"}
            </button>
            <button
              type="button"
              onClick={toggleLanguage}
              aria-label={t("prefs.language")}
              title={`${t("prefs.language")}: ${lang === "en" ? "فارسی" : "English"}`}
              className="inline-flex h-6 px-1.5 items-center justify-center rounded-control border border-line bg-surface text-[10px] font-semibold text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {lang === "en" ? "FA" : "EN"}
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div
            role="alert"
            className="mb-4 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault"
          >
            <div className="font-medium">{t("auth.authError")}</div>
            <div className="mt-0.5">{errorMsg}</div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-xs font-medium text-ink-2 mb-1">
              {t("auth.username")}
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60 font-mono dir-ltr"
              placeholder={t("auth.usernamePlaceholder")}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-medium text-ink-2 mb-1">
              {t("auth.password")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              className="h-8 w-full rounded-control border border-line bg-surface-2 px-2.5 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal disabled:opacity-60 font-mono dir-ltr"
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
                {t("auth.signingIn")}
              </span>
            ) : (
              t("auth.signInButton")
            )}
          </button>
        </form>

        {/* Security Notice */}
        <div className="mt-6 border-t border-line pt-3 text-[11px] text-ink-2/80">
          {t("auth.sessionSecurityNotice")}
        </div>
      </div>
    </div>
  );
};
