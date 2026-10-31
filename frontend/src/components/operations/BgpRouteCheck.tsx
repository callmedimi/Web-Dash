import React, { useState } from "react";
import {
  Search,
  Network,
  Server,
  AlertTriangle,
  Copy,
  Check,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { getNetworkCredentials } from "@/utils/networkCreds";
import { usePrefsStore } from "@/store/prefs";

interface BgpEntry {
  prefix: string;
  route_distinguisher?: string;
  route_target?: string[];
  matched_vrf_names?: string[];
  originator?: string;
  as_path?: string;
  nexthop?: string;
}

interface BgpCheckResponse {
  target_ip: string;
  router?: {
    name: string;
    ip: string;
  };
  entry_count: number;
  entries: BgpEntry[];
}

interface OriginatorInterfaceResult {
  interface: string;
  ip_address?: string;
  config?: string;
  status?: string;
}

interface OriginatorResponse {
  status: string;
  originator_ip: string;
  management_ip?: string;
  sysname?: string;
  connected?: boolean;
  results: Array<{
    vrf: string;
    has_route: boolean;
    interfaces?: OriginatorInterfaceResult[];
    matching_routes?: any[];
  }>;
}

export const BgpRouteCheck: React.FC = () => {
  const { lang } = usePrefsStore();
  const isFa = lang === "fa";

  const [targetIp, setTargetIp] = useState("10.200.1.5");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bgpResult, setBgpResult] = useState<BgpCheckResponse | null>(null);

  // Originator resolution state
  const [originatorResults, setOriginatorResults] = useState<Record<string, OriginatorResponse>>({});
  const [loadingOriginator, setLoadingOriginator] = useState<string | null>(null);
  const [copiedConfig, setCopiedConfig] = useState<string | null>(null);

  const handleCheckBgp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetIp.trim()) return;

    setLoading(true);
    setError(null);
    setBgpResult(null);
    setOriginatorResults({});

    const netCreds = getNetworkCredentials();

    try {
      const res = await apiClient.post<BgpCheckResponse>("/check-bgp-route", {
        target_ip: targetIp.trim(),
        username: netCreds.username || undefined,
        password: netCreds.password || undefined,
      });
      setBgpResult(res);
    } catch (err: any) {
      setError(
        err?.message ||
          (isFa
            ? "خطا در اتصال به Route Reflector و بررسی روت BGP"
            : "Failed to connect to Route Reflector and inspect BGP routes")
      );
    } finally {
      setLoading(false);
    }
  };

  const handleShowOriginatorInterfaces = async (entry: BgpEntry) => {
    if (!entry.originator) return;
    const origKey = `${entry.originator}_${entry.prefix}`;
    setLoadingOriginator(origKey);

    const netCreds = getNetworkCredentials();

    try {
      const res = await apiClient.post<OriginatorResponse>("/show-originator-interfaces", {
        originator_ip: entry.originator,
        vrf_list: entry.matched_vrf_names || [],
        target_ip: targetIp.trim(),
        prefix: entry.prefix,
        username: netCreds.username || undefined,
        password: netCreds.password || undefined,
      });
      setOriginatorResults((prev) => ({
        ...prev,
        [origKey]: res,
      }));
    } catch (err: any) {
      alert(
        isFa
          ? `خطا در استعلام از روتر مبدا (${entry.originator}): ${err?.message || err}`
          : `Failed to query Originator PE (${entry.originator}): ${err?.message || err}`
      );
    } finally {
      setLoadingOriginator(null);
    }
  };

  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedConfig(id);
    setTimeout(() => setCopiedConfig(null), 2000);
  };

  return (
    <div className="space-y-4">
      {/* Search Header Card */}
      <div className="rounded-control border border-line bg-surface p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Network className="h-4 w-4 text-signal" />
          <h2 className="text-sm font-semibold text-ink">
            {isFa
              ? "بررسی هوشمند روت BGP و رهگیری اینترفیس مقصد"
              : "Smart BGP Route Check & Destination Interface Tracing"}
          </h2>
        </div>
        <p className="text-xs text-ink-2 mb-4">
          {isFa
            ? "با وارد کردن IP مقصد، سیستم به صورت خودکار به Route Reflector مرکزی متصل شده، جدول BGP VPNv4 را بررسی می‌کند، از روی Route Targetها نام VRF را تشخیص داده، روتر لبه (Originator PE) را شناسایی و کانفیگ کامل اینترفیس مقصد را استخراج می‌کند."
            : "Enter a destination IP to query the Core Route Reflector, automatically inspect BGP VPNv4 tables, resolve the VRF from Route Targets, identify the Originator PE, and pull the active destination interface configuration."}
        </p>

        <form onSubmit={handleCheckBgp} className="flex flex-wrap items-center gap-2">
          <div className="flex-1 min-w-[240px] max-w-md">
            <input
              type="text"
              placeholder={
                isFa
                  ? "آدرس IP مقصد (مثال: 10.200.1.5 یا 172.16.0.1)"
                  : "Target Destination IP (e.g. 10.200.1.5 or 172.16.0.1)"
              }
              value={targetIp}
              onChange={(e) => setTargetIp(e.target.value)}
              className="w-full rounded border border-line bg-surface py-2 px-3 text-xs font-mono text-ink focus:border-signal focus:outline-none"
              autoComplete="off"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !targetIp.trim()}
            className="flex items-center gap-1.5 rounded-control bg-signal px-4 py-2 text-xs font-semibold text-bg hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            <span>
              {loading
                ? isFa ? "در حال استعلام BGP..." : "Querying BGP..."
                : isFa ? "بررسی روت BGP" : "Check BGP Route"}
            </span>
          </button>
        </form>

        {error && (
          <div className="mt-3 flex items-center gap-2 rounded border border-fault/30 bg-fault/10 p-2.5 text-xs text-fault">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Results Section */}
      {bgpResult && (
        <div className="space-y-4 animate-in fade-in">
          {/* Summary Box */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-line/60 bg-surface-2/40 px-4 py-2.5 text-xs">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-signal" />
              <span>
                {isFa ? "مرجع استعلام BGP:" : "BGP Query Source:"}{" "}
                <strong className="text-ink font-mono">{bgpResult.router?.name || "Route Reflector"}</strong>{" "}
                ({bgpResult.router?.ip})
              </span>
            </div>
            <div className="font-mono text-ink-2">
              {isFa ? "تعداد رکوردهای یافت شده:" : "Matched Entries Found:"}{" "}
              <strong className="text-signal">{bgpResult.entry_count}</strong>
            </div>
          </div>

          {bgpResult.entry_count === 0 ? (
            <div className="rounded-control border border-line bg-surface p-8 text-center text-xs text-ink-2">
              {isFa
                ? "هیچ روت BGP متناظری برای این آدرس IP در جداول VPNv4 یافت نشد."
                : "No matching BGP VPNv4 route found for this IP address."}
            </div>
          ) : (
            <div className="space-y-4">
              {bgpResult.entries.map((entry, idx) => {
                const origKey = `${entry.originator}_${entry.prefix}`;
                const origData = originatorResults[origKey];
                const isResolving = loadingOriginator === origKey;

                return (
                  <div
                    key={idx}
                    className="rounded-control border border-line bg-surface overflow-hidden shadow-sm"
                  >
                    {/* BGP Record Header */}
                    <div className="bg-surface-2/80 border-b border-line p-3 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="rounded bg-signal/10 px-2 py-0.5 text-xs font-mono font-semibold text-signal">
                          Prefix: {entry.prefix}
                        </span>

                        {entry.matched_vrf_names && entry.matched_vrf_names.length > 0 && (
                          <div className="flex items-center gap-1">
                            <span className="text-[11px] text-ink-2">
                              {isFa ? "VRF تشخیص داده شده:" : "Detected VRF:"}
                            </span>
                            {entry.matched_vrf_names.map((v) => (
                              <span
                                key={v}
                                className="rounded bg-ok/10 border border-ok/30 px-1.5 py-0.5 text-[10px] font-mono font-bold text-ok"
                              >
                                {v}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {entry.originator && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-ink-2">
                            {isFa ? "روتر لبه مبدا (Originator):" : "Originator PE:"}
                          </span>
                          <span className="font-mono font-semibold text-signal">{entry.originator}</span>
                        </div>
                      )}
                    </div>

                    {/* BGP Route Parameters */}
                    <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono border-b border-line/40">
                      <div>
                        <span className="text-ink-2 block text-[10px]">Route Distinguisher (RD):</span>
                        <span className="text-ink">{entry.route_distinguisher || "—"}</span>
                      </div>
                      <div>
                        <span className="text-ink-2 block text-[10px]">Route Targets (RTs):</span>
                        <span className="text-ink">{entry.route_target?.join(", ") || "—"}</span>
                      </div>
                      <div>
                        <span className="text-ink-2 block text-[10px]">Next Hop &amp; AS Path:</span>
                        <span className="text-ink">
                          {entry.nexthop || "Direct"} {entry.as_path ? `(AS: ${entry.as_path})` : ""}
                        </span>
                      </div>
                    </div>

                    {/* Action & Interface Resolution */}
                    <div className="p-4 bg-surface-2/20">
                      {entry.originator ? (
                        <div>
                          {!origData && (
                            <button
                              type="button"
                              onClick={() => handleShowOriginatorInterfaces(entry)}
                              disabled={isResolving}
                              className="flex items-center gap-2 rounded bg-signal/15 border border-signal/40 px-3 py-1.5 text-xs font-semibold text-signal hover:bg-signal/25 disabled:opacity-50 transition-colors"
                            >
                              {isResolving ? (
                                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Terminal className="h-3.5 w-3.5" />
                              )}
                              <span>
                                {isResolving
                                  ? isFa
                                    ? `در حال اتصال به روتر مبدا (${entry.originator})...`
                                    : `Connecting to Originator PE (${entry.originator})...`
                                  : isFa
                                    ? `🔎 استعلام اینترفیس و کانفیگ روتر مبدا (${entry.originator})`
                                    : `🔎 Fetch Originator PE Interface Config (${entry.originator})`}
                              </span>
                            </button>
                          )}

                          {origData && (
                            <div className="space-y-3 mt-2">
                              {/* Originator Banner */}
                              <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-line bg-surface p-2.5 text-xs">
                                <div className="flex items-center gap-2">
                                  <Server className="h-4 w-4 text-ok" />
                                  <span>
                                    {isFa ? "روتر لبه مبدا:" : "Edge Originator PE:"}{" "}
                                    <strong className="text-ink">{origData.sysname || "—"}</strong>{" "}
                                    (mgmt: {origData.management_ip || origData.originator_ip})
                                  </span>
                                </div>
                                <span className="rounded bg-ok/10 text-ok px-2 py-0.5 text-[11px] font-mono">
                                  Connected OK
                                </span>
                              </div>

                              {/* Interfaces & Config */}
                              {origData.results?.map((res, rIdx) => (
                                <div key={rIdx} className="space-y-2">
                                  {res.interfaces?.map((iface, iIdx) => {
                                    const codeId = `code_${origKey}_${rIdx}_${iIdx}`;
                                    const isCopied = copiedConfig === codeId;

                                    return (
                                      <div
                                        key={iIdx}
                                        className="rounded border border-line bg-surface overflow-hidden"
                                      >
                                        <div className="bg-surface-2/60 px-3 py-2 flex items-center justify-between border-b border-line text-xs font-mono">
                                          <div className="flex items-center gap-2">
                                            <span className="font-bold text-ink">{iface.interface}</span>
                                            {iface.ip_address && (
                                              <span className="text-ink-2">({iface.ip_address})</span>
                                            )}
                                          </div>
                                          <button
                                            type="button"
                                            onClick={() =>
                                              handleCopyText(iface.config || "", codeId)
                                            }
                                            className="flex items-center gap-1 text-[11px] text-ink-2 hover:text-signal transition-colors"
                                          >
                                            {isCopied ? (
                                              <>
                                                <Check className="h-3 w-3 text-ok" />
                                                <span className="text-ok">
                                                  {isFa ? "کپی شد" : "Copied!"}
                                                </span>
                                              </>
                                            ) : (
                                              <>
                                                <Copy className="h-3 w-3" />
                                                <span>
                                                  {isFa ? "کپی کانفیگ" : "Copy Config"}
                                                </span>
                                              </>
                                            )}
                                          </button>
                                        </div>

                                        <pre className="p-3 text-[11px] font-mono text-ink bg-surface-2/20 overflow-x-auto max-h-60 dir-ltr text-left">
                                          <code>{iface.config || "display current-configuration interface ..."}</code>
                                        </pre>
                                      </div>
                                    );
                                  })}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-xs text-ink-2">
                          {isFa
                            ? "روتر Originator در این رکورد ثبت نشده است."
                            : "No Originator PE recorded in this BGP entry."}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
