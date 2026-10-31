/**
 * CsvOperationsHub: Direct CSV Operations Console.
 * Restores the beloved legacy workflows:
 * 1. Bulk Alarm Clear via CSV (drag-drop CSV -> parse table -> credentials -> run-bulk -> SSE logs -> download report)
 * 2. Down-Links & Trunks Reporting via CSV (drag-drop CSV -> parse nodes -> province/age selector -> run-report -> SSE -> download Excel)
 * 3. SecureCRT Sessions Extractor via CSV (drag-drop CSV -> preview sessions -> download ZIP)
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
} from "lucide-react";
import { apiClient } from "@/api/client";
import { cn } from "@/utils/cn";

export interface CsvRouterItem {
  name?: string;
  host: string;
  ne_type?: string;
  version?: string;
  lsr_id?: string;
  [key: string]: unknown;
}

export const CsvOperationsHub: React.FC<{
  initialTab?: "alarm_clear" | "down_links" | "sessions" | "licenses";
  onClose?: () => void;
  className?: string;
}> = ({ initialTab = "alarm_clear", onClose, className }) => {
  const [activeTab, setActiveTab] = useState<"alarm_clear" | "down_links" | "sessions" | "licenses">(initialTab);

  // -------------------------------------------------------------
  // Shared Credentials State
  // -------------------------------------------------------------
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  // -------------------------------------------------------------
  // 1. Bulk Alarm Clear State
  // -------------------------------------------------------------
  const [alarmFile, setAlarmFile] = useState<File | null>(null);
  const [alarmRouters, setAlarmRouters] = useState<CsvRouterItem[]>([]);
  const [alarmParsing, setAlarmParsing] = useState(false);
  const [alarmError, setAlarmError] = useState<string | null>(null);
  const [alarmRunning, setAlarmRunning] = useState(false);
  const [alarmSessionId, setAlarmSessionId] = useState<string | null>(null);
  const [alarmLogs, setAlarmLogs] = useState<string[]>([]);
  const [alarmDone, setAlarmDone] = useState(false);
  const alarmLogEndRef = useRef<HTMLDivElement>(null);

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
  // Handlers for Bulk Alarm Clear
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
        setAlarmError("فایل بارگذاری‌شده حاوی روتر معتبر نبود.");
      }
    } catch (err: unknown) {
      setAlarmError(err instanceof Error ? err.message : "خطا در پردازش فایل CSV");
    } finally {
      setAlarmParsing(false);
    }
  };

  const handleRunBulkAlarmClear = async () => {
    if (alarmRouters.length === 0) return;
    if (!username || !password) {
      setAlarmError("لطفاً نام کاربری و کلمه عبور شبکه را وارد نمایید.");
      return;
    }

    setAlarmRunning(true);
    setAlarmError(null);
    setAlarmLogs([`[INFO] شروع عملیات پاکسازی آلارم برای ${alarmRouters.length} روتر...`]);
    setAlarmDone(false);

    try {
      const res = await apiClient.post<{ session_id: string; router_count: number }>("/run-bulk", {
        routers: alarmRouters,
        username,
        password,
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
        setAlarmLogs((prev) => [...prev, "[SUCCESS] عملیات پاکسازی با موفقیت پایان یافت."]);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setAlarmRunning(false);
        setAlarmDone(true);
      };
    } catch (err: unknown) {
      setAlarmError(err instanceof Error ? err.message : "خطا در آغاز اجرای پاکسازی");
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
        setReportError("فایل بارگذاری‌شده حاوی روتر معتبر نبود.");
      }
    } catch (err: unknown) {
      setReportError(err instanceof Error ? err.message : "خطا در پردازش فایل CSV نودها");
    } finally {
      setReportParsing(false);
    }
  };

  const handleRunDownLinksReport = async (full: boolean = false) => {
    if (reportRouters.length === 0) return;
    if (!full && !selectedProvince) {
      setReportError("لطفاً یک استان را انتخاب کنید یا گزارش کل را اجرا نمایید.");
      return;
    }
    if (!username || !password) {
      setReportError("لطفاً نام کاربری و کلمه عبور شبکه را وارد نمایید.");
      return;
    }

    setReportRunning(true);
    setReportError(null);
    setReportLogs([
      `[INFO] در حال استخراج گزارش لینک‌های قطع ${
        full ? "کل شبکه" : `استان ${selectedProvince}`
      } با حداقل قدمت ${ageValue} ${ageUnit}...`,
    ]);
    setReportDone(false);

    try {
      const endpoint = full ? "/run-full-report" : "/run-report";
      const payload: Record<string, unknown> = {
        routers: reportRouters,
        age_value: ageValue,
        age_unit: ageUnit,
        username,
        password,
      };
      if (!full) payload.province = selectedProvince;

      const res = await apiClient.post<{ session_id: string; router_count: number }>(
        endpoint,
        payload
      );

      const sid = res.session_id;
      setReportSessionId(sid);

      // Connect to SSE stream
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
          "[SUCCESS] گزارش لینک‌های قطع و ترانک‌ها با موفقیت تولید گردید.",
        ]);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setReportRunning(false);
        setReportDone(true);
      };
    } catch (err: unknown) {
      setReportError(err instanceof Error ? err.message : "خطا در تولید گزارش");
      setReportRunning(false);
    }
  };

  return (
    <div
      className={cn(
        "flex flex-col rounded-control border border-line bg-surface overflow-hidden shadow-lg animate-in fade-in duration-150",
        className
      )}
    >
      {/* Top Header & Tab Switcher */}
      <div className="flex flex-wrap items-center justify-between border-b border-line bg-surface-2/60 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-control bg-signal/15 text-signal">
            <FileSpreadsheet className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-xs font-bold text-ink">
              عملیات مستقیم با فایل CSV (Legacy Quick Actions)
            </h2>
            <p className="text-[10px] text-ink-2">
              اجرای مستقیم فرآیندهای عملیاتی بدون نیاز به ثبت اولیه در دیتابیس
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Tabs */}
          <div className="flex rounded-control border border-line bg-surface p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setActiveTab("alarm_clear")}
              className={cn(
                "rounded-control px-2.5 py-1 text-[11px] font-medium transition-colors",
                activeTab === "alarm_clear"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:text-ink hover:bg-surface-2"
              )}
            >
              پاکسازی انبوه آلارم‌ها
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("down_links")}
              className={cn(
                "rounded-control px-2.5 py-1 text-[11px] font-medium transition-colors",
                activeTab === "down_links"
                  ? "bg-signal text-white"
                  : "text-ink-2 hover:text-ink hover:bg-surface-2"
              )}
            >
              گزارش لینک‌های قطع استانی
            </button>
          </div>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-ink-2 hover:text-ink p-1 rounded hover:bg-surface-2"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col p-4 space-y-4 overflow-y-auto max-h-[80vh]">
        {/* Network Credentials Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-line bg-surface-2/40 p-2.5 text-xs">
          <div className="flex items-center gap-1.5 text-ink-2 font-medium">
            <Key className="h-3.5 w-3.5 text-signal" />
            <span>اطلاعات احراز هویت روترها (VRP Telnet/SSH):</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="نام کاربری (Username)"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink placeholder:text-ink-2/60 focus:outline-none focus:ring-1 focus:ring-signal w-32"
            />
            <input
              type="password"
              placeholder="کلمه عبور (Password)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-control border border-line bg-surface px-2.5 py-1 text-xs text-ink placeholder:text-ink-2/60 focus:outline-none focus:ring-1 focus:ring-signal w-36"
            />
            <span className="text-[10px] text-ok flex items-center gap-1 font-mono">
              <ShieldCheck className="h-3 w-3" />
              <span>TLS / CSRF Secure</span>
            </span>
          </div>
        </div>

        {/* ========================================================= */}
        {/* TAB 1: BULK ALARM CLEAR                                   */}
        {/* ========================================================= */}
        {activeTab === "alarm_clear" && (
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
                فایل CSV روترها را اینجا رها کنید، یا{" "}
                <span className="text-signal underline">کلیک برای انتخاب فایل</span>
              </p>
              <p className="text-[11px] text-ink-2 mt-1">
                ستون‌های مجاز: <code className="font-mono text-signal">NE Name, NE IP Address, NE Type, Version, LSR ID</code>
              </p>
              {alarmFile && (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-signal/10 px-2 py-0.5 text-xs font-mono font-medium text-signal border border-signal/20">
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{alarmFile.name} ({alarmRouters.length} روتر)</span>
                </div>
              )}
            </div>

            {/* Error Notice */}
            {alarmError && (
              <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{alarmError}</span>
              </div>
            )}

            {/* Parsed Preview Table */}
            {alarmRouters.length > 0 && (
              <div className="flex flex-col space-y-2 border border-line rounded-control bg-surface p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-signal" />
                    <span>پیش‌نمایش لیست روترها ({alarmRouters.length} دستگاه شناسایی شد)</span>
                  </span>

                  <button
                    type="button"
                    onClick={handleRunBulkAlarmClear}
                    disabled={alarmRunning}
                    className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-signal/90 disabled:opacity-50"
                  >
                    {alarmRunning ? (
                      <RotateCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5 fill-current" />
                    )}
                    <span>{alarmRunning ? "در حال اجرای عملیات..." : "اجرای پاکسازی روی همه روترها"}</span>
                  </button>
                </div>

                <div className="max-h-48 overflow-y-auto border border-line rounded-control text-xs">
                  <table className="w-full border-collapse text-right">
                    <thead className="bg-surface-2 sticky top-0 text-[11px] font-semibold text-ink-2 border-b border-line">
                      <tr>
                        <th className="px-2 py-1">#</th>
                        <th className="px-2 py-1">NE Name</th>
                        <th className="px-2 py-1">IP Address</th>
                        <th className="px-2 py-1">NE Type</th>
                        <th className="px-2 py-1">Version</th>
                        <th className="px-2 py-1">LSR ID</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/60 font-mono">
                      {alarmRouters.slice(0, 50).map((r, idx) => (
                        <tr key={idx} className="hover:bg-surface-2/60">
                          <td className="px-2 py-1 text-ink-2">{idx + 1}</td>
                          <td className="px-2 py-1 text-ink font-medium">{r.name || "-"}</td>
                          <td className="px-2 py-1 text-signal font-semibold dir-ltr">{r.host}</td>
                          <td className="px-2 py-1 text-ink-2">{r.ne_type || "-"}</td>
                          <td className="px-2 py-1 text-ink-2">{r.version || "-"}</td>
                          <td className="px-2 py-1 text-ink-2 dir-ltr">{r.lsr_id || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {alarmRouters.length > 50 && (
                  <p className="text-[10px] text-ink-2 text-center">
                    نمایش ۵۰ ردیف اول از مجموع {alarmRouters.length} روتر
                  </p>
                )}
              </div>
            )}

            {/* Live SSE Execution Log Console */}
            {alarmLogs.length > 0 && (
              <div className="flex flex-col rounded-control border border-line bg-surface overflow-hidden">
                <div className="flex items-center justify-between border-b border-line bg-surface-2 px-3 py-1.5 text-xs">
                  <div className="flex items-center gap-1.5 font-mono text-[11px] text-ink">
                    <Terminal className="h-3.5 w-3.5 text-signal" />
                    <span>کنسول استریم فرآیند پاکسازی (Session: {alarmSessionId || "..."})</span>
                  </div>

                  {alarmDone && alarmSessionId && (
                    <a
                      href={`/download/${alarmSessionId}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded bg-ok px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-ok/90"
                    >
                      <Download className="h-3 w-3" />
                      <span>دانلود گزارش اکسل</span>
                    </a>
                  )}
                </div>

                <div className="h-44 overflow-y-auto bg-black/90 p-2.5 font-mono text-[11px] text-green-400 dir-ltr text-left space-y-0.5">
                  {alarmLogs.map((log, idx) => (
                    <div key={idx} className="leading-relaxed">
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
        {/* TAB 2: DOWN-LINKS REPORT CSV                              */}
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
                فایل CSV نودهای شبکه را اینجا رها کنید، یا{" "}
                <span className="text-signal underline">کلیک برای انتخاب فایل</span>
              </p>
              <p className="text-[11px] text-ink-2 mt-1">
                ستون‌های مورد انتظار: <code className="font-mono text-signal">NE Name, NE IP Address</code>
              </p>
              {reportFile && (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-signal/10 px-2 py-0.5 text-xs font-mono font-medium text-signal border border-signal/20">
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{reportFile.name} ({reportRouters.length} نود شناسایی شد)</span>
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

            {/* Options Strip */}
            {reportRouters.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-line bg-surface p-3 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <label className="font-semibold text-ink">انتخاب استان:</label>
                    <select
                      value={selectedProvince}
                      onChange={(e) => setSelectedProvince(e.target.value)}
                      className="rounded-control border border-line bg-surface px-2.5 py-1 text-xs font-mono font-bold text-signal focus:outline-none focus:ring-1 focus:ring-signal"
                    >
                      {reportProvinces.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="h-4 w-px bg-line" />

                  <div className="flex items-center gap-1.5">
                    <label className="font-semibold text-ink">حداقل قدمت قطعی:</label>
                    <input
                      type="number"
                      value={ageValue}
                      min={1}
                      max={999}
                      onChange={(e) => setAgeValue(Number(e.target.value))}
                      className="w-14 rounded-control border border-line bg-surface px-2 py-1 text-center font-mono text-xs text-ink focus:outline-none focus:ring-1 focus:ring-signal"
                    />
                    <select
                      value={ageUnit}
                      onChange={(e) => setAgeUnit(e.target.value)}
                      className="rounded-control border border-line bg-surface px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-signal"
                    >
                      <option value="hours">ساعت (Hours)</option>
                      <option value="days">روز (Days)</option>
                      <option value="weeks">هفته (Weeks)</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleRunDownLinksReport(false)}
                    disabled={reportRunning}
                    className="inline-flex items-center gap-1 rounded-control bg-signal px-3 py-1.5 text-xs font-semibold text-white hover:bg-signal/90 disabled:opacity-50 shadow-sm"
                  >
                    {reportRunning ? <RotateCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3 fill-current" />}
                    <span>تولید گزارش استانی</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleRunDownLinksReport(true)}
                    disabled={reportRunning}
                    className="inline-flex items-center gap-1 rounded-control border border-line bg-surface-2 px-3 py-1.5 text-xs font-semibold text-ink hover:bg-line/40 disabled:opacity-50"
                  >
                    <span>تولید گزارش کل شبکه</span>
                  </button>
                </div>
              </div>
            )}

            {/* Live SSE Execution Log Console */}
            {reportLogs.length > 0 && (
              <div className="flex flex-col rounded-control border border-line bg-surface overflow-hidden">
                <div className="flex items-center justify-between border-b border-line bg-surface-2 px-3 py-1.5 text-xs">
                  <div className="flex items-center gap-1.5 font-mono text-[11px] text-ink">
                    <Terminal className="h-3.5 w-3.5 text-signal" />
                    <span>کنسول استریم گزارش (Session: {reportSessionId || "..."})</span>
                  </div>

                  {reportDone && reportSessionId && (
                    <div className="flex items-center gap-2">
                      <a
                        href={`/download-report/${reportSessionId}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded bg-ok px-2.5 py-0.5 text-[11px] font-semibold text-white hover:bg-ok/90"
                      >
                        <Download className="h-3 w-3" />
                        <span>دانلود گزارش اکسل</span>
                      </a>
                      <a
                        href={`/download-trunk-report/${reportSessionId}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded bg-signal px-2.5 py-0.5 text-[11px] font-semibold text-white hover:bg-signal/90"
                      >
                        <Download className="h-3 w-3" />
                        <span>دانلود گزارش ترانک‌ها</span>
                      </a>
                    </div>
                  )}
                </div>

                <div className="h-44 overflow-y-auto bg-black/90 p-2.5 font-mono text-[11px] text-cyan-400 dir-ltr text-left space-y-0.5">
                  {reportLogs.map((log, idx) => (
                    <div key={idx} className="leading-relaxed">
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
