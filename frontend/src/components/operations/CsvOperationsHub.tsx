/**
 * CsvOperationsHub: Direct CSV Operations Console.
 * True Legacy Operational Engine:
 * 1. Alarm Clear via CSV / Manual (parse CSV / add IP -> SSH Netmiko -> live SSE terminal -> download report)
 * 2. Down-Links & Trunks Reporting via CSV (parse nodes -> province/age selector -> SSH Netmiko -> live SSE -> download Excel)
 * 3. SecureCRT Sessions Extractor via CSV (parse CSV -> generate sessions -> download ZIP)
 * 4. License Check & Renewal via CSV
 */
import React, { useState, useRef, useEffect } from "react";
import {
  FileSpreadsheet,
  Upload,
  Play,
  Download,
  AlertTriangle,
  Terminal,
  RotateCw,
  X,
  FileCode,
  ShieldCheck,
  Layers,
  Key,
  Plus,
  Trash2,
  Server,
} from "lucide-react";
import { apiClient } from "@/api/client";
import {
  getNetworkCredentials,
  setNetworkCredentials,
  NET_CREDS_EVENT,
} from "@/utils/networkCreds";
import { usePrefsStore } from "@/store/prefs";

export interface CsvRouterItem {
  name?: string;
  host: string;
  ne_type?: string;
  version?: string;
  lsr_id?: string;
  [key: string]: unknown;
}

export interface ManualRouterItem {
  name: string;
  host: string;
}

export const CsvOperationsHub: React.FC<{
  initialTab?: "alarm_clear" | "down_links" | "sessions" | "licenses";
  showTabs?: boolean;
  onClose?: () => void;
  className?: string;
}> = ({ initialTab = "alarm_clear", showTabs = true, onClose, className = "" }) => {
  const { lang } = usePrefsStore();
  const isFa = lang === "fa";

  const [activeTab, setActiveTab] = useState<"alarm_clear" | "down_links" | "sessions" | "licenses">(initialTab);

  // -------------------------------------------------------------
  // Shared Credentials State (Synchronized with Header Bar)
  // -------------------------------------------------------------
  const [username, setUsername] = useState(() => getNetworkCredentials().username || "admin");
  const [password, setPassword] = useState(() => getNetworkCredentials().password || "");
  const [credsSaved, setCredsSaved] = useState(() => Boolean(getNetworkCredentials().username && getNetworkCredentials().password));

  useEffect(() => {
    const creds = getNetworkCredentials();
    if (creds.username) setUsername(creds.username);
    if (creds.password) setPassword(creds.password);
    setCredsSaved(Boolean(creds.username && creds.password));

    const handleUpdate = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail.username) setUsername(detail.username);
      if (detail.password) setPassword(detail.password);
      setCredsSaved(Boolean(detail.username && detail.password));
    };

    window.addEventListener(NET_CREDS_EVENT, handleUpdate);
    return () => window.removeEventListener(NET_CREDS_EVENT, handleUpdate);
  }, []);

  const saveCredentials = () => {
    if (username.trim() && password) {
      setNetworkCredentials({ username: username.trim(), password });
      setCredsSaved(true);
    }
  };

  // -------------------------------------------------------------
  // 1. Alarm Clear State (Bulk CSV + Single Device Manual)
  // -------------------------------------------------------------
  const [alarmMode, setAlarmMode] = useState<"bulk" | "manual">("bulk");

  // Bulk State
  const [alarmFile, setAlarmFile] = useState<File | null>(null);
  const [alarmRouters, setAlarmRouters] = useState<CsvRouterItem[]>([]);
  const [alarmParsing, setAlarmParsing] = useState(false);
  const [alarmError, setAlarmError] = useState<string | null>(null);
  const [alarmRunning, setAlarmRunning] = useState(false);
  const [alarmSessionId, setAlarmSessionId] = useState<string | null>(null);
  const [alarmLogs, setAlarmLogs] = useState<string[]>([]);
  const [alarmDone, setAlarmDone] = useState(false);
  const alarmLogEndRef = useRef<HTMLDivElement>(null);

  // Manual State
  const [manualRouters, setManualRouters] = useState<ManualRouterItem[]>([
    { name: "", host: "" },
  ]);

  // -------------------------------------------------------------
  // 2. Down-Links CSV State
  // -------------------------------------------------------------
  const [reportFile, setReportFile] = useState<File | null>(null);
  const [reportRouters, setReportRouters] = useState<CsvRouterItem[]>([]);
  const [reportProvinces, setReportProvinces] = useState<string[]>([]);
  const [selectedProvince, setSelectedProvince] = useState<string>("");
  const [ageValue, setAgeValue] = useState<number>(2);
  const [ageUnit, setAgeUnit] = useState<string>("days");
  const [reportParsing, setReportParsing] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportRunning, setReportRunning] = useState(false);
  const [reportSessionId, setReportSessionId] = useState<string | null>(null);
  const [reportLogs, setReportLogs] = useState<string[]>([]);
  const [reportDone, setReportDone] = useState(false);
  const reportLogEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll logs
  useEffect(() => {
    alarmLogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [alarmLogs]);

  useEffect(() => {
    reportLogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [reportLogs]);

  // -------------------------------------------------------------
  // Handlers for Alarm Clear (Bulk CSV)
  // -------------------------------------------------------------
  const handleAlarmFileSelect = async (file: File) => {
    if (!file) return;
    setAlarmFile(file);
    setAlarmError(null);
    setAlarmParsing(true);
    setAlarmRouters([]);
    setAlarmSessionId(null);
    setAlarmLogs([]);
    setAlarmDone(false);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await apiClient.post<{ routers: CsvRouterItem[]; count: number }>(
        "/parse-csv",
        formData
      );
      if (res && res.routers) {
        setAlarmRouters(res.routers);
      } else {
        setAlarmError(isFa ? "فایل بارگذاری‌شده حاوی روتر معتبر نبود." : "Uploaded file contains no valid router entries.");
      }
    } catch (err: unknown) {
      setAlarmError(err instanceof Error ? err.message : (isFa ? "خطا در پردازش فایل CSV" : "Failed to parse CSV file"));
    } finally {
      setAlarmParsing(false);
    }
  };

  const handleRunBulkAlarmClear = async () => {
    if (alarmRouters.length === 0) return;
    const creds = getNetworkCredentials();
    const effectiveUser = username.trim() || creds.username;
    const effectivePass = password || creds.password;

    if (!effectiveUser || !effectivePass) {
      setAlarmError(
        isFa
          ? "لطفاً نام کاربری و رمز عبور SSH روترها را وارد نمایید."
          : "Please provide router SSH credentials."
      );
      return;
    }
    saveCredentials();

    setAlarmRunning(true);
    setAlarmError(null);
    setAlarmLogs([
      isFa
        ? `[INFO] شروع عملیات پاکسازی آلارم برای ${alarmRouters.length} روتر از طریق SSH...`
        : `[INFO] Starting SSH alarm clearing on ${alarmRouters.length} router(s)...`,
    ]);
    setAlarmDone(false);

    try {
      const res = await apiClient.post<{ session_id: string; router_count: number }>("/run-bulk", {
        routers: alarmRouters,
        username: effectiveUser,
        password: effectivePass,
      });

      const sid = res.session_id;
      setAlarmSessionId(sid);

      // Connect to SSE stream
      const eventSource = new EventSource(`/stream/${sid}`);
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.text) {
            setAlarmLogs((prev) => [...prev, data.text]);
          } else if (typeof data === "string") {
            setAlarmLogs((prev) => [...prev, data]);
          }
        } catch {
          if (event.data) setAlarmLogs((prev) => [...prev, event.data]);
        }
      };

      eventSource.addEventListener("done", () => {
        eventSource.close();
        setAlarmRunning(false);
        setAlarmDone(true);
        setAlarmLogs((prev) => [
          ...prev,
          isFa ? "[SUCCESS] عملیات پاکسازی با موفقیت پایان یافت." : "[SUCCESS] Alarm clear operation completed.",
        ]);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setAlarmRunning(false);
        setAlarmDone(true);
      };
    } catch (err: unknown) {
      setAlarmError(err instanceof Error ? err.message : "Execution failed");
      setAlarmRunning(false);
    }
  };

  // -------------------------------------------------------------
  // Handlers for Alarm Clear (Manual Single Device)
  // -------------------------------------------------------------
  const handleAddManualRow = () => {
    setManualRouters((prev) => [...prev, { name: "", host: "" }]);
  };

  const handleRemoveManualRow = (index: number) => {
    setManualRouters((prev) => prev.filter((_, i) => i !== index));
  };

  const handleRunManualAlarmClear = async () => {
    const validRouters = manualRouters.filter((r) => r.host.trim());
    if (validRouters.length === 0) {
      setAlarmError(isFa ? "لطفاً حداقل یک آدرس IP روتر وارد نمایید." : "Please enter at least one router IP address.");
      return;
    }

    const creds = getNetworkCredentials();
    const effectiveUser = username.trim() || creds.username;
    const effectivePass = password || creds.password;

    if (!effectiveUser || !effectivePass) {
      setAlarmError(
        isFa
          ? "لطفاً نام کاربری و رمز عبور SSH روترها را وارد نمایید."
          : "Please provide router SSH credentials."
      );
      return;
    }
    saveCredentials();

    setAlarmRunning(true);
    setAlarmError(null);
    setAlarmLogs([
      isFa
        ? `[INFO] شروع عملیات پاکسازی دستی برای ${validRouters.length} روتر...`
        : `[INFO] Starting manual alarm clearing on ${validRouters.length} router(s)...`,
    ]);
    setAlarmDone(false);

    try {
      const res = await apiClient.post<{ session_id: string; router_count: number }>("/run-manual", {
        routers: validRouters,
        username: effectiveUser,
        password: effectivePass,
      });

      const sid = res.session_id;
      setAlarmSessionId(sid);

      const eventSource = new EventSource(`/stream/${sid}`);
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.text) {
            setAlarmLogs((prev) => [...prev, data.text]);
          } else if (typeof data === "string") {
            setAlarmLogs((prev) => [...prev, data]);
          }
        } catch {
          if (event.data) setAlarmLogs((prev) => [...prev, event.data]);
        }
      };

      eventSource.addEventListener("done", () => {
        eventSource.close();
        setAlarmRunning(false);
        setAlarmDone(true);
        setAlarmLogs((prev) => [
          ...prev,
          isFa ? "[SUCCESS] عملیات پاکسازی دستی پایان یافت." : "[SUCCESS] Manual clear operation completed.",
        ]);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setAlarmRunning(false);
        setAlarmDone(true);
      };
    } catch (err: unknown) {
      setAlarmError(err instanceof Error ? err.message : "Execution failed");
      setAlarmRunning(false);
    }
  };

  // -------------------------------------------------------------
  // Handlers for Down-Links Report CSV
  // -------------------------------------------------------------
  const handleReportFileSelect = async (file: File) => {
    if (!file) return;
    setReportFile(file);
    setReportError(null);
    setReportParsing(true);
    setReportRouters([]);
    setReportProvinces([]);
    setReportSessionId(null);
    setReportLogs([]);
    setReportDone(false);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await apiClient.post<{
        routers: CsvRouterItem[];
        provinces: string[];
        count: number;
      }>("/parse-csv-nodes", formData);

      if (res && res.routers) {
        setReportRouters(res.routers);
        setReportProvinces(res.provinces || []);
        if (res.provinces && res.provinces.length > 0) {
          setSelectedProvince(res.provinces[0]);
        }
      } else {
        setReportError(isFa ? "فایل نودها حاوی روتر معتبر نبود." : "Nodes CSV file contains no valid entries.");
      }
    } catch (err: unknown) {
      setReportError(err instanceof Error ? err.message : (isFa ? "خطا در پردازش فایل نودها" : "Failed to parse nodes CSV"));
    } finally {
      setReportParsing(false);
    }
  };

  const handleRunReport = async () => {
    if (reportRouters.length === 0) return;
    const creds = getNetworkCredentials();
    const effectiveUser = username.trim() || creds.username;
    const effectivePass = password || creds.password;

    if (!effectiveUser || !effectivePass) {
      setReportError(
        isFa
          ? "لطفاً نام کاربری و رمز عبور SSH روترها را وارد نمایید."
          : "Please provide router SSH credentials."
      );
      return;
    }
    saveCredentials();

    setReportRunning(true);
    setReportError(null);
    setReportLogs([
      isFa
        ? `[INFO] شروع گزارش‌گیری ترانک‌ها و لینک‌های دان برای ${reportRouters.length} نود از طریق SSH...`
        : `[INFO] Starting trunk & down-link inspection on ${reportRouters.length} nodes...`,
    ]);
    setReportDone(false);

    try {
      const res = await apiClient.post<{ session_id: string; router_count: number }>("/run-report", {
        routers: reportRouters,
        province: selectedProvince || "ALL",
        age_value: ageValue,
        age_unit: ageUnit,
        username: effectiveUser,
        password: effectivePass,
      });

      const sid = res.session_id;
      setReportSessionId(sid);

      const eventSource = new EventSource(`/stream-report/${sid}`);
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.text) {
            setReportLogs((prev) => [...prev, data.text]);
          } else if (typeof data === "string") {
            setReportLogs((prev) => [...prev, data]);
          }
        } catch {
          if (event.data) setReportLogs((prev) => [...prev, event.data]);
        }
      };

      eventSource.addEventListener("done", () => {
        eventSource.close();
        setReportRunning(false);
        setReportDone(true);
        setReportLogs((prev) => [
          ...prev,
          isFa ? "[SUCCESS] گزارش‌گیری با موفقیت به پایان رسید. فایل‌های اکسل آماده دانلود هستند." : "[SUCCESS] Report completed. Excel/CSV files ready for download.",
        ]);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setReportRunning(false);
        setReportDone(true);
      };
    } catch (err: unknown) {
      setReportError(err instanceof Error ? err.message : "Execution failed");
      setReportRunning(false);
    }
  };

  return (
    <div className={`flex flex-col rounded-xl border border-line bg-surface shadow-sm overflow-hidden ${className}`}>
      {/* Top Header & Tab Navigation (if enabled) */}
      {showTabs && (
        <div className="flex flex-wrap items-center justify-between border-b border-line bg-surface-2/60 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-signal" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink">
              {isFa ? "مرکز عملیات با فایل CSV (اتصال SSH به تجهیزات)" : "Device CSV Operations Console (SSH Automation)"}
            </h2>
          </div>

          <div className="flex items-center gap-1">
            <div className="flex rounded-control border border-line bg-surface p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setActiveTab("alarm_clear")}
                className={`px-3 py-1 rounded-control font-semibold transition-colors ${
                  activeTab === "alarm_clear" ? "bg-signal text-white shadow-xs" : "text-ink-2 hover:text-ink"
                }`}
              >
                {isFa ? "پاکسازی آلارم" : "Alarm Clear"}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("down_links")}
                className={`px-3 py-1 rounded-control font-semibold transition-colors ${
                  activeTab === "down_links" ? "bg-signal text-white shadow-xs" : "text-ink-2 hover:text-ink"
                }`}
              >
                {isFa ? "گزارش لینک‌ها و ترانک‌ها" : "Down-Links & Trunks"}
              </button>
            </div>

            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="text-ink-2 hover:text-ink p-1 rounded hover:bg-surface-2 ml-2"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col p-4 space-y-4 overflow-y-auto">
        {/* Network Credentials Strip (Synchronized with Header) */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-line bg-surface-2/40 p-2.5 text-xs">
          <div className="flex items-center gap-1.5 text-ink-2 font-medium">
            <Key className="h-3.5 w-3.5 text-signal" />
            <span>{isFa ? "اطلاعات احراز هویت روترها (SSH / TACACS):" : "Router SSH / TACACS Credentials:"}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder={isFa ? "نام کاربری (Username)" : "Username"}
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                setCredsSaved(false);
              }}
              className="rounded-control border border-line bg-surface px-2.5 py-1 text-xs font-mono text-ink placeholder:text-ink-2/60 focus:outline-none focus:ring-1 focus:ring-signal w-32"
            />
            <input
              type="password"
              placeholder={isFa ? "کلمه عبور (Password)" : "Password"}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setCredsSaved(false);
              }}
              className="rounded-control border border-line bg-surface px-2.5 py-1 text-xs font-mono text-ink placeholder:text-ink-2/60 focus:outline-none focus:ring-1 focus:ring-signal w-36"
            />
            <button
              type="button"
              onClick={saveCredentials}
              className="rounded-control bg-surface border border-line hover:border-signal px-2 py-1 text-[11px] font-medium text-ink transition-colors"
            >
              {isFa ? "ثبت اعتبار" : "Save Auth"}
            </button>
            {credsSaved && (
              <span className="text-[10px] text-ok flex items-center gap-1 font-mono">
                <ShieldCheck className="h-3 w-3" />
                <span>{isFa ? "آماده اتصال" : "Ready"}</span>
              </span>
            )}
          </div>
        </div>

        {/* ========================================================= */}
        {/* 1. ALARM CLEAR (Bulk CSV + Manual Single Device)           */}
        {/* ========================================================= */}
        {activeTab === "alarm_clear" && (
          <div className="space-y-4">
            {/* Sub-tab Switcher: Bulk CSV vs Manual */}
            <div className="flex items-center gap-1 border-b border-line pb-2">
              <button
                type="button"
                onClick={() => setAlarmMode("bulk")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-control text-xs font-semibold transition-colors ${
                  alarmMode === "bulk" ? "bg-signal text-white shadow-xs" : "text-ink-2 hover:text-ink hover:bg-surface-2"
                }`}
              >
                <FileSpreadsheet className="h-3.5 w-3.5" />
                <span>{isFa ? "پاکسازی انبوه با فایل CSV روترها" : "Bulk CSV Clearing"}</span>
              </button>

              <button
                type="button"
                onClick={() => setAlarmMode("manual")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-control text-xs font-semibold transition-colors ${
                  alarmMode === "manual" ? "bg-signal text-white shadow-xs" : "text-ink-2 hover:text-ink hover:bg-surface-2"
                }`}
              >
                <Server className="h-3.5 w-3.5" />
                <span>{isFa ? "پاکسازی دستی تک‌روتر (Single Device Clear)" : "Single Device Clear"}</span>
              </button>
            </div>

            {/* Error Notice */}
            {alarmError && (
              <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{alarmError}</span>
              </div>
            )}

            {/* A. BULK CSV CLEARING */}
            {alarmMode === "bulk" && (
              <div className="space-y-4">
                {/* Drop Zone */}
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                      handleAlarmFileSelect(e.dataTransfer.files[0]);
                    }
                  }}
                  className="flex flex-col items-center justify-center rounded-control border-2 border-dashed border-line bg-surface-2/30 p-6 text-center transition-colors hover:border-signal/50 hover:bg-surface-2/60 cursor-pointer"
                  onClick={() => {
                    const input = document.createElement("input");
                    input.type = "file";
                    input.accept = ".csv";
                    input.onchange = (e) => {
                      const target = e.target as HTMLInputElement;
                      if (target.files && target.files[0]) {
                        handleAlarmFileSelect(target.files[0]);
                      }
                    };
                    input.click();
                  }}
                >
                  {alarmParsing ? (
                    <RotateCw className="h-8 w-8 text-signal animate-spin mb-2" />
                  ) : (
                    <Upload className="h-8 w-8 text-signal mb-2" />
                  )}
                  <p className="text-xs font-semibold text-ink">
                    {isFa ? "فایل CSV روترها را اینجا رها کنید، یا " : "Drag & drop your router CSV file here, or "}
                    <span className="text-signal underline">{isFa ? "کلیک برای انتخاب فایل" : "browse"}</span>
                  </p>
                  <p className="text-[11px] text-ink-2 mt-1">
                    {isFa
                      ? "ستون‌های مجاز: NE Name, NE IP Address, NE Type, Version, LSR ID"
                      : "Expected columns: NE Name, NE IP Address, NE Type, Version, LSR ID"}
                  </p>
                  {alarmFile && (
                    <div className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-signal/10 px-2 py-0.5 text-xs font-mono font-medium text-signal border border-signal/20">
                      <FileCode className="h-3.5 w-3.5" />
                      <span>{alarmFile.name} ({alarmRouters.length} {isFa ? "روتر" : "routers"})</span>
                    </div>
                  )}
                </div>

                {/* Parsed Preview Table & Action */}
                {alarmRouters.length > 0 && (
                  <div className="flex flex-col space-y-3 border border-line rounded-control bg-surface p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-ink flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-signal" />
                        <span>
                          {isFa
                            ? `پیش‌نمایش لیست روترها (${alarmRouters.length} دستگاه شناسایی شد)`
                            : `Parsed Routers (${alarmRouters.length} devices detected)`}
                        </span>
                      </span>

                      <button
                        type="button"
                        onClick={handleRunBulkAlarmClear}
                        disabled={alarmRunning}
                        className="flex items-center gap-1.5 rounded-control bg-signal px-4 py-1.5 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity"
                      >
                        {alarmRunning ? (
                          <RotateCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Play className="h-3.5 w-3.5 fill-current" />
                        )}
                        <span>
                          {alarmRunning
                            ? isFa ? "در حال اتصال و پاکسازی..." : "Clearing via SSH..."
                            : isFa ? "اجرای پاکسازی روی کلیه روترها" : "Run Clear on All Routers"}
                        </span>
                      </button>
                    </div>

                    <div className="max-h-56 overflow-y-auto border border-line/60 rounded">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-line bg-surface-2 text-ink-2 font-mono">
                            <th className="py-1.5 px-3">#</th>
                            <th className="py-1.5 px-3">NE Name</th>
                            <th className="py-1.5 px-3">IP Address</th>
                            <th className="py-1.5 px-3">NE Type</th>
                            <th className="py-1.5 px-3">Version</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line/40 font-mono">
                          {alarmRouters.slice(0, 100).map((r, i) => (
                            <tr key={i} className="hover:bg-surface-2/40">
                              <td className="py-1 px-3 text-ink-2">{i + 1}</td>
                              <td className="py-1 px-3 font-semibold text-ink">{r.name || "—"}</td>
                              <td className="py-1 px-3 text-signal">{r.host}</td>
                              <td className="py-1 px-3 text-ink-2">{r.ne_type || "—"}</td>
                              <td className="py-1 px-3 text-ink-2">{r.version || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* B. MANUAL SINGLE DEVICE CLEAR */}
            {alarmMode === "manual" && (
              <div className="space-y-4 border border-line rounded-control bg-surface p-4">
                <div className="flex items-center justify-between border-b border-line pb-2">
                  <h3 className="text-xs font-bold text-ink uppercase tracking-wider">
                    {isFa ? "وارد کردن دستی IP روترها برای پاکسازی" : "Manual Router IP Entry"}
                  </h3>
                  <button
                    type="button"
                    onClick={handleAddManualRow}
                    className="flex items-center gap-1 rounded bg-surface-2 px-2.5 py-1 text-xs text-ink hover:bg-surface-2/80 font-medium"
                  >
                    <Plus className="h-3.5 w-3.5 text-signal" />
                    <span>{isFa ? "افزودن روتر" : "Add Router"}</span>
                  </button>
                </div>

                <div className="space-y-2">
                  {manualRouters.map((row, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="text-xs font-mono text-ink-2 w-6">{idx + 1}.</span>
                      <input
                        type="text"
                        placeholder={isFa ? "نام روتر (اختیاری)" : "Router Name (optional)"}
                        value={row.name}
                        onChange={(e) => {
                          const val = e.target.value;
                          setManualRouters((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, name: val } : r))
                          );
                        }}
                        className="w-48 rounded border border-line bg-surface-2 px-2.5 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none"
                      />
                      <input
                        type="text"
                        placeholder={isFa ? "آدرس IP روتر (الزامی)*" : "Router IP Address (Required)*"}
                        value={row.host}
                        onChange={(e) => {
                          const val = e.target.value;
                          setManualRouters((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, host: val } : r))
                          );
                        }}
                        className="w-56 rounded border border-line bg-surface-2 px-2.5 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none"
                      />
                      {manualRouters.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveManualRow(idx)}
                          className="p-1 text-ink-2 hover:text-fault"
                          title="Remove"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div className="pt-2">
                  <button
                    type="button"
                    onClick={handleRunManualAlarmClear}
                    disabled={alarmRunning || manualRouters.every((r) => !r.host.trim())}
                    className="flex items-center gap-1.5 rounded-control bg-signal px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity"
                  >
                    {alarmRunning ? (
                      <RotateCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5 fill-current" />
                    )}
                    <span>
                      {alarmRunning
                        ? isFa ? "در حال اتصال و پاکسازی..." : "Clearing via SSH..."
                        : isFa ? "اجرای پاکسازی دستی" : "Run Manual Clear"}
                    </span>
                  </button>
                </div>
              </div>
            )}

            {/* Real-time SSE Terminal Stream Log Viewer */}
            {(alarmLogs.length > 0 || alarmRunning) && (
              <div className="flex flex-col space-y-2 border border-line rounded-control bg-[#0d1117] p-3 text-ink">
                <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                  <span className="text-xs font-mono text-gray-400 flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-signal" />
                    <span>{isFa ? "لاگ زنده اتصال SSH به روترها (Netmiko Stream)" : "Live Netmiko SSH Terminal Stream"}</span>
                  </span>

                  <div className="flex items-center gap-2">
                    {alarmRunning && (
                      <span className="flex items-center gap-1 text-[11px] text-signal font-mono">
                        <RotateCw className="h-3 w-3 animate-spin" />
                        <span>Running...</span>
                      </span>
                    )}

                    {alarmDone && alarmSessionId && (
                      <a
                        href={`/download/${alarmSessionId}`}
                        download
                        className="flex items-center gap-1 rounded bg-ok/20 border border-ok/40 px-2 py-0.5 text-xs text-ok hover:bg-ok/30 font-semibold"
                      >
                        <Download className="h-3 w-3" />
                        <span>{isFa ? "دانلود گزارش خروجی (CSV)" : "Download Report (CSV)"}</span>
                      </a>
                    )}
                  </div>
                </div>

                <div className="h-56 overflow-y-auto font-mono text-[11px] space-y-1 p-2 dir-ltr text-left">
                  {alarmLogs.map((log, i) => (
                    <div
                      key={i}
                      className={
                        log.includes("[ERROR]")
                          ? "text-red-400"
                          : log.includes("[SUCCESS]")
                          ? "text-green-400 font-semibold"
                          : log.includes("[INFO]")
                          ? "text-blue-300"
                          : "text-gray-300"
                      }
                    >
                      {log}
                    </div>
                  ))}
                  <div ref={alarmLogEndRef} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================= */}
        {/* 2. DOWN-LINKS & TRUNKS REPORTING (CSV Nodes)               */}
        {/* ========================================================= */}
        {activeTab === "down_links" && (
          <div className="space-y-4">
            {/* Drop Zone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleReportFileSelect(e.dataTransfer.files[0]);
                }
              }}
              className="flex flex-col items-center justify-center rounded-control border-2 border-dashed border-line bg-surface-2/30 p-6 text-center transition-colors hover:border-signal/50 hover:bg-surface-2/60 cursor-pointer"
              onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".csv";
                input.onchange = (e) => {
                  const target = e.target as HTMLInputElement;
                  if (target.files && target.files[0]) {
                    handleReportFileSelect(target.files[0]);
                  }
                };
                input.click();
              }}
            >
              {reportParsing ? (
                <RotateCw className="h-8 w-8 text-signal animate-spin mb-2" />
              ) : (
                <Upload className="h-8 w-8 text-signal mb-2" />
              )}
              <p className="text-xs font-semibold text-ink">
                {isFa ? "فایل CSV نودهای شبکه را اینجا رها کنید، یا " : "Drag & drop your Node CSV file here, or "}
                <span className="text-signal underline">{isFa ? "کلیک برای انتخاب فایل" : "browse"}</span>
              </p>
              <p className="text-[11px] text-ink-2 mt-1">
                {isFa
                  ? "ستون‌های مجاز: NE Name, NE IP Address, Province, NE Type"
                  : "Expected columns: NE Name, NE IP Address, Province, NE Type"}
              </p>
              {reportFile && (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-signal/10 px-2 py-0.5 text-xs font-mono font-medium text-signal border border-signal/20">
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{reportFile.name} ({reportRouters.length} {isFa ? "نود شناسایی شد" : "nodes detected"})</span>
                </div>
              )}
            </div>

            {/* Error Notice */}
            {reportError && (
              <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{reportError}</span>
              </div>
            )}

            {/* Filters, Controls & Run Button */}
            {reportRouters.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border border-line rounded-control bg-surface p-3.5">
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  {/* Province Selector */}
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-ink-2">{isFa ? "استان:" : "Province:"}</span>
                    <select
                      value={selectedProvince}
                      onChange={(e) => setSelectedProvince(e.target.value)}
                      className="rounded border border-line bg-surface-2 px-2.5 py-1 text-xs text-ink focus:border-signal focus:outline-none"
                    >
                      <option value="">{isFa ? "-- تمام استان‌ها --" : "-- All Provinces --"}</option>
                      {reportProvinces.map((prov) => (
                        <option key={prov} value={prov}>
                          {prov}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Min Age Input */}
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-ink-2">{isFa ? "حداقل قدمت قطعی:" : "Min Age:"}</span>
                    <input
                      type="number"
                      min={1}
                      max={365}
                      value={ageValue}
                      onChange={(e) => setAgeValue(Number(e.target.value))}
                      className="w-16 rounded border border-line bg-surface-2 px-2 py-1 text-xs text-ink font-mono focus:border-signal focus:outline-none text-center"
                    />
                    <select
                      value={ageUnit}
                      onChange={(e) => setAgeUnit(e.target.value)}
                      className="rounded border border-line bg-surface-2 px-2 py-1 text-xs text-ink focus:border-signal focus:outline-none"
                    >
                      <option value="hours">{isFa ? "ساعت" : "hours"}</option>
                      <option value="days">{isFa ? "روز" : "days"}</option>
                      <option value="weeks">{isFa ? "هفته" : "weeks"}</option>
                    </select>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleRunReport}
                  disabled={reportRunning}
                  className="flex items-center gap-1.5 rounded-control bg-signal px-4 py-1.5 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity"
                >
                  {reportRunning ? (
                    <RotateCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5 fill-current" />
                  )}
                  <span>
                    {reportRunning
                      ? isFa ? "در حال اتصال به نودها و استخراج ترانک‌ها..." : "Inspecting nodes via SSH..."
                      : isFa ? "اجرای گزارش‌گیری روی نودها" : "Run Report on Nodes"}
                  </span>
                </button>
              </div>
            )}

            {/* Real-time SSE Terminal Stream Log Viewer */}
            {(reportLogs.length > 0 || reportRunning) && (
              <div className="flex flex-col space-y-2 border border-line rounded-control bg-[#0d1117] p-3 text-ink">
                <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                  <span className="text-xs font-mono text-gray-400 flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-signal" />
                    <span>{isFa ? "لاگ زنده اتصال SSH به نودها (Netmiko Interface Inspection)" : "Live Netmiko Interface Inspection Stream"}</span>
                  </span>

                  <div className="flex items-center gap-2">
                    {reportRunning && (
                      <span className="flex items-center gap-1 text-[11px] text-signal font-mono">
                        <RotateCw className="h-3 w-3 animate-spin" />
                        <span>Running...</span>
                      </span>
                    )}

                    {reportDone && reportSessionId && (
                      <div className="flex items-center gap-2">
                        <a
                          href={`/download-report/${reportSessionId}`}
                          download
                          className="flex items-center gap-1 rounded bg-ok/20 border border-ok/40 px-2 py-0.5 text-xs text-ok hover:bg-ok/30 font-semibold"
                        >
                          <Download className="h-3 w-3" />
                          <span>{isFa ? "دانلود گزارش لینک‌های دان (Excel)" : "Download Down-Links Report"}</span>
                        </a>

                        <a
                          href={`/download-trunk-report/${reportSessionId}`}
                          download
                          className="flex items-center gap-1 rounded bg-signal/20 border border-signal/40 px-2 py-0.5 text-xs text-signal hover:bg-signal/30 font-semibold"
                        >
                          <Download className="h-3 w-3" />
                          <span>{isFa ? "دانلود گزارش ترانک‌ها (Excel)" : "Download Trunk Report"}</span>
                        </a>
                      </div>
                    )}
                  </div>
                </div>

                <div className="h-56 overflow-y-auto font-mono text-[11px] space-y-1 p-2 dir-ltr text-left">
                  {reportLogs.map((log, i) => (
                    <div
                      key={i}
                      className={
                        log.includes("[ERROR]")
                          ? "text-red-400"
                          : log.includes("[SUCCESS]")
                          ? "text-green-400 font-semibold"
                          : log.includes("[INFO]")
                          ? "text-blue-300"
                          : "text-gray-300"
                      }
                    >
                      {log}
                    </div>
                  ))}
                  <div ref={reportLogEndRef} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
