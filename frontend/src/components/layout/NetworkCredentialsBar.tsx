import React, { useState, useEffect } from "react";
import { KeyRound, Eye, EyeOff, ShieldCheck, X } from "lucide-react";
import {
  getNetworkCredentials,
  setNetworkCredentials,
  clearNetworkCredentials,
  NET_CREDS_EVENT,
} from "@/utils/networkCreds";

export const NetworkCredentialsBar: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

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

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setNetworkCredentials({ username: username.trim(), password });
    setIsSaved(true);
  };

  const handleClear = () => {
    clearNetworkCredentials();
    setUsername("");
    setPassword("");
    setIsSaved(false);
  };

  return (
    <form
      onSubmit={handleSave}
      className="hidden lg:flex items-center gap-1.5 rounded-control border border-line/60 bg-surface-2/60 px-2 py-0.5 text-xs text-ink"
      title="اعتبار مشترک TACACS / SSH برای اجرای فرآیندهای روترهای هواوی"
    >
      <div className="flex items-center gap-1 text-ink-2 text-[11px] font-medium whitespace-nowrap">
        <KeyRound className="h-3 w-3 text-signal" />
        <span className="hidden xl:inline">اعتبار شبکه:</span>
      </div>

      <input
        type="text"
        placeholder="یوزرنیم SSH/TACACS"
        value={username}
        onChange={(e) => {
          setUsername(e.target.value);
          setIsSaved(false);
        }}
        className="w-28 xl:w-32 rounded border border-line/70 bg-surface px-1.5 py-0.5 text-[11px] font-mono text-ink placeholder:text-ink-2/60 focus:border-signal focus:outline-none"
        autoComplete="off"
      />

      <div className="relative flex items-center">
        <input
          type={showPassword ? "text" : "password"}
          placeholder="رمز عبور"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setIsSaved(false);
          }}
          className="w-24 xl:w-28 rounded border border-line/70 bg-surface px-1.5 py-0.5 pr-6 text-[11px] font-mono text-ink placeholder:text-ink-2/60 focus:border-signal focus:outline-none"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="absolute right-1 text-ink-2 hover:text-ink"
          tabIndex={-1}
        >
          {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
        </button>
      </div>

      <button
        type="submit"
        disabled={!username.trim() || !password}
        className="rounded bg-signal px-2 py-0.5 text-[11px] font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity"
      >
        ثبت
      </button>

      {isSaved && (
        <div className="flex items-center gap-1 text-[10px] text-ok font-medium">
          <ShieldCheck className="h-3 w-3 text-ok" />
          <span className="hidden xl:inline">تنظیم شد</span>
          <button
            type="button"
            onClick={handleClear}
            title="پاک کردن اعتبار"
            className="text-ink-2 hover:text-fault ml-0.5"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        </div>
      )}
    </form>
  );
};
