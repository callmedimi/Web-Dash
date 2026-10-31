import React, { useState, useEffect, useRef } from "react";
import { KeyRound, Eye, EyeOff, ShieldCheck, X, ChevronDown, Lock, CheckCircle2 } from "lucide-react";
import {
  getNetworkCredentials,
  setNetworkCredentials,
  clearNetworkCredentials,
  NET_CREDS_EVENT,
} from "@/utils/networkCreds";
import { usePrefsStore } from "@/store/prefs";

export const NetworkCredentialsBar: React.FC = () => {
  const { lang } = usePrefsStore();
  const isFa = lang === "fa";

  const [isOpen, setIsOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const creds = getNetworkCredentials();
    setUsername(creds.username);
    setPassword(creds.password);
    setIsSaved(Boolean(creds.username && creds.password));

    const handleUpdate = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setUsername(detail.username || "");
      setPassword(detail.password || "");
      setIsSaved(Boolean(detail.username && detail.password));
    };

    window.addEventListener(NET_CREDS_EVENT, handleUpdate);
    return () => window.removeEventListener(NET_CREDS_EVENT, handleUpdate);
  }, []);

  // Handle click outside to close popover
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setNetworkCredentials({ username: username.trim(), password });
    setIsSaved(true);
    setIsOpen(false);
  };

  const handleClear = () => {
    clearNetworkCredentials();
    setUsername("");
    setPassword("");
    setIsSaved(false);
    setIsOpen(false);
  };

  return (
    <div className="relative inline-block" ref={popoverRef}>
      {/* Sleek Compact Trigger Pill */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`inline-flex h-8 items-center gap-2 rounded-control px-2.5 text-xs font-medium transition-all shadow-sm ${
          isSaved
            ? "border border-ok/40 bg-ok/10 text-ok hover:bg-ok/20 ring-1 ring-ok/20"
            : "border border-line/80 bg-surface-2/60 text-ink-2 hover:border-signal/50 hover:text-ink hover:bg-surface-2"
        }`}
        title={
          isSaved
            ? isFa
              ? `اعتبار SSH فعال: ${username}`
              : `Active SSH Auth: ${username}`
            : isFa
              ? "تنظیم اعتبار مشترک SSH/TACACS"
              : "Set shared SSH/TACACS credentials"
        }
      >
        {isSaved ? (
          <>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ok opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-ok" />
            </span>
            <ShieldCheck className="h-3.5 w-3.5 text-ok shrink-0" />
            <span className="font-mono font-semibold max-w-[100px] truncate text-ink">
              {username}
            </span>
            <span className="rounded bg-ok/20 px-1 py-0.2 text-[10px] text-ok hidden sm:inline">
              {isFa ? "متصل" : "Ready"}
            </span>
          </>
        ) : (
          <>
            <KeyRound className="h-3.5 w-3.5 text-signal shrink-0" />
            <span className="text-[11px] font-medium hidden sm:inline">
              {isFa ? "اعتبار SSH" : "SSH Auth"}
            </span>
          </>
        )}
        <ChevronDown
          className={`h-3 w-3 text-ink-2 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {/* Floating Glassmorphic Popover Modal */}
      {isOpen && (
        <div className="absolute end-0 top-full mt-2 w-80 rounded-xl border border-line bg-surface/95 p-4 shadow-floating backdrop-blur-md z-50 animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between border-b border-line/60 pb-2.5 mb-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-signal/10 text-signal">
                <Lock className="h-4 w-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-ink">
                  {isFa ? "اعتبار مشترک شبکه (TACACS / SSH)" : "Shared Network Credentials"}
                </h4>
                <p className="text-[10px] text-ink-2">
                  {isFa ? "برای اتصال به کلیه روترهای هواوی" : "Used across all Huawei routers"}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded p-1 text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <form onSubmit={handleSave} className="space-y-3">
            <div>
              <label className="text-[11px] font-semibold text-ink-2 mb-1 block">
                {isFa ? "نام کاربری (Username)" : "Username"}
              </label>
              <input
                type="text"
                placeholder="e.g. noc_operator"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  setIsSaved(false);
                }}
                className="w-full rounded-control border border-line bg-surface-2 px-2.5 py-1.5 text-xs font-mono text-ink placeholder:text-ink-2/50 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
                autoComplete="off"
                autoFocus
              />
            </div>

            <div>
              <label className="text-[11px] font-semibold text-ink-2 mb-1 block">
                {isFa ? "کلمه عبور (Password)" : "Password"}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setIsSaved(false);
                  }}
                  className="w-full rounded-control border border-line bg-surface-2 px-2.5 py-1.5 pr-8 text-xs font-mono text-ink placeholder:text-ink-2/50 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute end-2 top-1/2 -translate-y-1/2 text-ink-2 hover:text-ink p-1"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            <div className="pt-1 flex items-center justify-between gap-2">
              {isSaved ? (
                <button
                  type="button"
                  onClick={handleClear}
                  className="flex items-center gap-1.5 rounded-control border border-fault/30 bg-fault/10 px-3 py-1.5 text-xs font-medium text-fault hover:bg-fault/20 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                  <span>{isFa ? "پاکسازی" : "Clear"}</span>
                </button>
              ) : (
                <span className="text-[10px] text-ink-2">
                  {isFa ? "ذخیره در سشن مرورگر" : "Session memory only"}
                </span>
              )}

              <button
                type="submit"
                disabled={!username.trim() || !password}
                className="flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity ml-auto"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>{isFa ? "ذخیره اعتبار" : "Save Credentials"}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
