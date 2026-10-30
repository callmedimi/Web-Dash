"""Zabbix JSON-RPC 2.0 client and TelemetryProvider (Target Architecture §3 & Step 3.4).

Guarantees:
1. Strict read-only scope for monitoring.
2. JSON-RPC 2.0 error handling: NEVER retry business errors (F-27).
3. Version auto-detection (apiinfo.version) choosing Bearer token vs legacy auth.
4. Correct history value_type resolution from item (never hardcoded).
5. Circuit breaker: 5 consecutive failures opens breaker for 60s.
6. In-process caching with stale-while-error fallback.
"""
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Callable
import requests

from backend.app.telemetry.base import TelemetryProvider, TelemetryError
from backend.app.telemetry.models import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryItemValue,
    TelemetrySeries,
    TelemetrySeriesPoint,
    TelemetryInterface,
)
from backend.app.telemetry.cache import telemetry_cache

logger = logging.getLogger("telemetry.zabbix")


class ZabbixCircuitBreaker:
    """Circuit breaker opening after 5 consecutive HTTP/network failures for 60 seconds."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 60.0):
        self.threshold = failure_threshold
        self.cooldown = cooldown_seconds
        self.failure_count = 0
        self.cooldown_until = 0.0

    def is_open(self) -> bool:
        now = time.time()
        if now < self.cooldown_until:
            return True
        if self.cooldown_until > 0:
            # Cooldown passed, reset
            self.cooldown_until = 0.0
            self.failure_count = 0
        return False

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.cooldown_until = time.time() + self.cooldown
            logger.warning("Zabbix circuit breaker OPEN for %ds (Telemetry degraded)", self.cooldown)

    def record_success(self) -> None:
        self.failure_count = 0
        self.cooldown_until = 0.0


class ZabbixProvider(TelemetryProvider):
    """Zabbix API client implementing TelemetryProvider."""

    def __init__(
        self,
        url: str,
        token: str,
        timeout: float = 10.0,
        retries: int = 2,
        write_token: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.url = url.rstrip("/")
        if not self.url.endswith("/api_jsonrpc.php"):
            self.endpoint = f"{self.url}/api_jsonrpc.php"
        else:
            self.endpoint = self.url

        self.token = token
        self.write_token = write_token
        self.timeout = timeout
        self.retries = retries
        self.http_session = session or requests.Session()
        self.breaker = ZabbixCircuitBreaker()
        self._version: Optional[str] = None
        self._use_bearer: bool = True
        self._req_id: int = 1

    def detect_version(self) -> str:
        """Call apiinfo.version (unauthenticated) to detect Zabbix server version."""
        if self._version:
            return self._version

        payload = {
            "jsonrpc": "2.0",
            "method": "apiinfo.version",
            "params": [],
            "id": 1,
        }
        try:
            resp = self.http_session.post(self.endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            ver = data.get("result", "5.0.0")
            self._version = ver

            # Zabbix 5.4+ supports Authorization: Bearer <token>
            major_minor = [int(p) for p in ver.split(".")[:2] if p.isdigit()]
            if len(major_minor) >= 2:
                if major_minor[0] > 5 or (major_minor[0] == 5 and major_minor[1] >= 4):
                    self._use_bearer = True
                else:
                    self._use_bearer = False
            return self._version
        except Exception as exc:
            logger.warning("Could not detect Zabbix version: %s; defaulting to Bearer auth", exc)
            self._version = "unknown"
            self._use_bearer = True
            return self._version

    def _call(self, method: str, params: Dict[str, Any], use_write_token: bool = False) -> Any:
        """
        Execute JSON-RPC 2.0 call with retries only on HTTP/transport errors.
        NEVER retry JSON-RPC business errors (F-27).
        """
        if self.breaker.is_open():
            raise TelemetryError("Zabbix circuit breaker is open (Telemetry degraded)", code="CIRCUIT_OPEN")

        self._req_id += 1
        active_token = self.write_token if use_write_token and self.write_token else self.token

        headers = {
            "Content-Type": "application/json-rpc",
            "User-Agent": "WebDash-Telemetry/1.0",
        }

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._req_id,
        }

        if self._use_bearer:
            headers["Authorization"] = f"Bearer {active_token}"
        else:
            payload["auth"] = active_token

        attempt = 0
        while attempt <= self.retries:
            try:
                resp = self.http_session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()

                # JSON-RPC business error handling: NEVER retry!
                if "error" in data:
                    err = data["error"]
                    err_msg = err.get("data") or err.get("message") or "Unknown Zabbix error"
                    err_code = str(err.get("code", "ZABBIX_ERROR"))
                    logger.error("Zabbix JSON-RPC error in %s: %s (code: %s)", method, err_msg, err_code)
                    raise TelemetryError(f"Zabbix error ({err_code}): {err_msg}", code=err_code)

                self.breaker.record_success()
                return data.get("result")

            except requests.RequestException as req_exc:
                attempt += 1
                if attempt > self.retries:
                    self.breaker.record_failure()
                    logger.error("Zabbix connection failure for %s after %d retries: %s", method, attempt, req_exc)
                    raise TelemetryError(f"Zabbix connection failed: {req_exc}", code="CONNECTION_FAILED")
                time.sleep(1.0)

    # -----------------------------------------------------------------------
    # Provider Implementation
    # -----------------------------------------------------------------------

    def list_hosts(self, filters: Optional[Dict[str, Any]] = None) -> List[TelemetryHost]:
        """Fetch list of monitored hosts with 5 min caching."""
        cache_key = f"zabbix:hosts:{hash(str(filters))}"
        cached, is_stale = telemetry_cache.get(cache_key)

        try:
            params: Dict[str, Any] = {
                "output": ["hostid", "host", "name", "status", "available"],
                "selectInterfaces": ["ip", "dns", "useip", "main", "type"],
                "selectGroups": ["name"],
            }
            if filters:
                params.update(filters)

            raw_hosts = self._call("host.get", params)
            if not isinstance(raw_hosts, list):
                raw_hosts = []
            hosts: List[TelemetryHost] = []
            for h in raw_hosts:
                if not isinstance(h, dict):
                    continue
                interfaces = [
                    {"ip": iface.get("ip", ""), "main": str(iface.get("main", "0"))}
                    for iface in h.get("interfaces", [])
                    if isinstance(iface, dict)
                ]
                groups = [
                    g.get("name", "") for g in h.get("groups", [])
                    if isinstance(g, dict)
                ]
                hosts.append(TelemetryHost(
                    host_id=str(h.get("hostid")),
                    name=h.get("host", ""),
                    visible_name=h.get("name") or h.get("host", ""),
                    interfaces=interfaces,
                    groups=groups,
                    status="enabled" if h.get("status") == "0" else "disabled",
                    available=h.get("available") == "1",
                ))

            telemetry_cache.set(cache_key, hosts, ttl_seconds=300.0, stale_window_seconds=600.0)
            return hosts

        except Exception as exc:
            if cached is not None:
                logger.warning("Serving stale host list due to Zabbix error: %s", exc)
                return cached
            raise

    def get_problems(
        self,
        host_ids: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        severity_min: int = 0,
        since: Optional[int] = None,
    ) -> List[TelemetryProblem]:
        """Fetch active monitoring problems with 15s caching."""
        cache_key = f"zabbix:problems:{host_ids}:{groups}:{severity_min}:{since}"
        cached, is_stale = telemetry_cache.get(cache_key)

        try:
            params: Dict[str, Any] = {
                "output": ["eventid", "name", "severity", "clock", "acknowledged"],
                "selectHosts": ["hostid", "host", "name"],
                "selectTags": "extend",
                "severities": list(range(severity_min, 6)),
            }
            if host_ids:
                params["hostids"] = host_ids[:200]  # Respect batching cap
            if since:
                params["time_from"] = since

            raw_problems = self._call("problem.get", params)
            problems: List[TelemetryProblem] = []

            for p in raw_problems:
                hosts = p.get("hosts", [])
                host_id = hosts[0].get("hostid", "") if hosts else ""
                host_name = hosts[0].get("host", "") if hosts else ""
                tags = {t.get("tag", ""): t.get("value", "") for t in p.get("tags", [])}

                problems.append(TelemetryProblem(
                    event_id=str(p.get("eventid")),
                    host_id=host_id,
                    host_name=host_name,
                    name=p.get("name", ""),
                    severity=int(p.get("severity", 0)),
                    clock=int(p.get("clock", 0)),
                    acknowledged=p.get("acknowledged") == "1",
                    tags=tags,
                ))

            telemetry_cache.set(cache_key, problems, ttl_seconds=15.0, stale_window_seconds=300.0)
            return problems

        except Exception as exc:
            if cached is not None:
                logger.warning("Serving stale problems due to error: %s", exc)
                return cached
            raise

    def get_item_value(self, host_id: str, key_or_pattern: str) -> Optional[TelemetryItemValue]:
        """Fetch latest value for an item on host with 30s caching."""
        cache_key = f"zabbix:val:{host_id}:{key_or_pattern}"
        cached, _ = telemetry_cache.get(cache_key)

        try:
            params = {
                "hostids": [host_id],
                "search": {"key_": key_or_pattern},
                "output": ["itemid", "key_", "name", "lastvalue", "lastclock", "units", "value_type"],
                "limit": 1,
            }
            items = self._call("item.get", params)
            if not items:
                return None

            it = items[0]
            val_obj = TelemetryItemValue(
                item_id=str(it.get("itemid")),
                key=it.get("key_", ""),
                name=it.get("name", ""),
                value=it.get("lastvalue"),
                clock=int(it.get("lastclock", 0)),
                units=it.get("units", ""),
            )
            telemetry_cache.set(cache_key, val_obj, ttl_seconds=30.0, stale_window_seconds=300.0)
            return val_obj

        except Exception as exc:
            if cached is not None:
                return cached
            raise

    def get_series(
        self,
        host_id: str,
        key_or_pattern: str,
        t_from: int,
        t_to: int,
        max_points: int = 100,
    ) -> TelemetrySeries:
        """
        Fetch time series:
        - Resolves value_type from item.
        - Uses history.get if duration <= 24h (86400s), else trend.get.
        """
        cache_key = f"zabbix:series:{host_id}:{key_or_pattern}:{t_from}:{t_to}"
        cached, _ = telemetry_cache.get(cache_key)

        try:
            item_res = self._call("item.get", {
                "hostids": [host_id],
                "search": {"key_": key_or_pattern},
                "output": ["itemid", "key_", "value_type"],
                "limit": 1,
            })
            if not item_res:
                return TelemetrySeries(item_id="", key=key_or_pattern, points=[])

            it = item_res[0]
            item_id = str(it.get("itemid"))
            value_type = int(it.get("value_type", 0))

            duration = t_to - t_from
            points: List[TelemetrySeriesPoint] = []

            if duration <= 86400:
                hist_params = {
                    "itemids": [item_id],
                    "time_from": t_from,
                    "time_till": t_to,
                    "history": value_type,
                    "output": ["clock", "value"],
                    "limit": max_points * 2,
                }
                raw_hist = self._call("history.get", hist_params)
                for pt in raw_hist:
                    try:
                        points.append(TelemetrySeriesPoint(
                            clock=int(pt.get("clock", 0)),
                            value=float(pt.get("value", 0.0)),
                        ))
                    except ValueError:
                        pass
            else:
                trend_params = {
                    "itemids": [item_id],
                    "time_from": t_from,
                    "time_till": t_to,
                    "output": ["clock", "value_avg"],
                    "limit": max_points * 2,
                }
                raw_trends = self._call("trend.get", trend_params)
                for pt in raw_trends:
                    try:
                        points.append(TelemetrySeriesPoint(
                            clock=int(pt.get("clock", 0)),
                            value=float(pt.get("value_avg", 0.0)),
                        ))
                    except ValueError:
                        pass

            series = TelemetrySeries(item_id=item_id, key=key_or_pattern, points=points)
            telemetry_cache.set(cache_key, series, ttl_seconds=60.0, stale_window_seconds=600.0)
            return series

        except Exception as exc:
            if cached is not None:
                return cached
            raise

    def get_interface_table(self, host_id: str) -> List[TelemetryInterface]:
        """Fetch interface metrics table from host items."""
        params = {
            "hostids": [host_id],
            "search": {"key_": "net.if"},
            "output": ["key_", "lastvalue", "name"],
        }
        items = self._call("item.get", params)
        ifaces: Dict[str, TelemetryInterface] = {}

        for it in items:
            key = it.get("key_", "")
            val = it.get("lastvalue")
            # Extract interface name from key e.g. net.if.in[GigabitEthernet0/1/0]
            if "[" in key and "]" in key:
                if_name = key.split("[", 1)[1].rsplit("]", 1)[0].split(",")[0]
                if if_name not in ifaces:
                    ifaces[if_name] = TelemetryInterface(name=if_name)

                entry = ifaces[if_name]
                if "status" in key:
                    entry.oper_status = "UP" if str(val) == "1" else "DOWN"
                elif "in" in key and "errors" not in key:
                    try:
                        entry.in_rate = float(val)
                    except (ValueError, TypeError):
                        pass
                elif "out" in key and "errors" not in key:
                    try:
                        entry.out_rate = float(val)
                    except (ValueError, TypeError):
                        pass
                elif "errors" in key and "in" in key:
                    try:
                        entry.errors_in = float(val)
                    except (ValueError, TypeError):
                        pass
                elif "errors" in key and "out" in key:
                    try:
                        entry.errors_out = float(val)
                    except (ValueError, TypeError):
                        pass

        return list(ifaces.values())

    def ack_problem(self, event_id: str, message: str) -> bool:
        """Acknowledge problem in Zabbix (requires write token)."""
        if not self.write_token:
            raise TelemetryError("No write-scoped token configured for problem acknowledgment", code="NOT_CONFIGURED")

        params = {
            "eventids": [event_id],
            "action": 6,  # Acknowledge + Add message
            "message": message,
        }
        self._call("event.acknowledge", params, use_write_token=True)
        return True
