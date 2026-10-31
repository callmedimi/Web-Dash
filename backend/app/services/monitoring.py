"""Monitoring Hub Service: Zabbix & Grafana Telemetry Integration (Phase 5 Step 5.9).

Provides:
- Fleet Health screen data: availability, CPU/memory/temperature, active problems by severity and province (Zabbix only, no SSH).
- Device Monitoring: live interface metrics table (admin/oper, rate, errors), time-range graphs, deep-links and embed URLs for Grafana.
- Interface search: keyword-based interface search across telemetry hosts with legacy router DB fallback.
- Alarm Center merge: combines SSH active alarms with Zabbix problems, providing quick device selection shortcuts into Alarm Clear / Down-Links jobs.
- Webhook intake: receives and normalizes external alert webhooks.
- Integrations diagnostics: tests Zabbix API, Grafana health, and mapping coverage %.
"""
from __future__ import annotations
import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models.device import Device
from backend.app.telemetry.base import TelemetryProvider, NullProvider, DisabledProvider
from backend.app.telemetry import (
    TelemetryHost,
    TelemetryProblem,
    TelemetryInterface,
    TelemetrySeries,
    TelemetryItemValue,
    get_telemetry_provider,
    GrafanaClient,
)
from backend.app.services.inventory import derive_province_and_site

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    0: "Not classified",
    1: "Information",
    2: "Warning",
    3: "Average",
    4: "High",
    5: "Disaster",
}


class MonitoringHubService:
    """Enterprise NOC telemetry monitoring hub integrating Zabbix and Grafana."""

    @classmethod
    def get_fleet_health(
        cls,
        db_session: Session,
        provider: Optional[TelemetryProvider] = None,
        filter_province: Optional[str] = None,
        filter_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compile fleet-wide health status from Zabbix telemetry (no SSH needed)."""
        active_provider = provider or get_telemetry_provider()

        # 1. Fetch enabled devices from inventory
        dev_query = db_session.query(Device).filter(Device.enabled.is_(True))
        if filter_province:
            dev_query = dev_query.filter(Device.province.ilike(filter_province.strip()))
        if filter_role:
            dev_query = dev_query.filter(Device.role.ilike(filter_role.strip()))
        devices = dev_query.order_by(Device.province.asc(), Device.name.asc()).all()

        # 2. Fetch Zabbix hosts & problems
        telemetry_hosts: Dict[str, TelemetryHost] = {}
        ip_to_host: Dict[str, TelemetryHost] = {}
        name_to_host: Dict[str, TelemetryHost] = {}
        active_problems: List[TelemetryProblem] = []

        try:
            hosts_list = active_provider.list_hosts() if hasattr(active_provider, "list_hosts") else active_provider.get_hosts()
            for h in hosts_list:
                telemetry_hosts[h.host_id] = h
                name_to_host[h.name.strip().lower()] = h
                if h.visible_name:
                    name_to_host[h.visible_name.strip().lower()] = h
                for iface in h.interfaces:
                    if iface.get("ip"):
                        ip_to_host[iface["ip"].strip()] = h

            active_problems = active_provider.get_problems()
        except Exception as exc:
            logger.warning("Could not fetch Zabbix telemetry for fleet health: %s", exc)

        # Map problems by host_id
        problems_by_host: Dict[str, List[Dict[str, Any]]] = {}
        severity_counts: Dict[str, int] = {name: 0 for name in SEVERITY_MAP.values()}

        for p in active_problems:
            sev_name = SEVERITY_MAP.get(p.severity, "Warning")
            severity_counts[sev_name] = severity_counts.get(sev_name, 0) + 1
            prob_dict = {
                "event_id": p.event_id,
                "host_id": p.host_id,
                "name": p.name,
                "severity": p.severity,
                "severity_name": sev_name,
                "clock": p.clock,
                "clock_iso": datetime.fromtimestamp(p.clock).isoformat() if p.clock else "",
                "acknowledged": p.acknowledged,
                "tags": p.tags,
            }
            problems_by_host.setdefault(p.host_id, []).append(prob_dict)

        # 3. Correlate devices with telemetry and calculate province statistics
        device_rows: List[Dict[str, Any]] = []
        province_stats: Dict[str, Dict[str, Any]] = {}
        total_monitored = 0
        total_available = 0

        for d in devices:
            prov = d.province or derive_province_and_site(d.name)[0] or "UNKNOWN"
            if prov not in province_stats:
                province_stats[prov] = {
                    "province": prov,
                    "total": 0,
                    "monitored": 0,
                    "available": 0,
                    "problems": 0,
                }
            province_stats[prov]["total"] += 1

            # Match host by zabbix_hostid, mgmt_ip, or name
            matched_host: Optional[TelemetryHost] = None
            if d.zabbix_hostid and d.zabbix_hostid in telemetry_hosts:
                matched_host = telemetry_hosts[d.zabbix_hostid]
            elif d.mgmt_ip and d.mgmt_ip.strip() in ip_to_host:
                matched_host = ip_to_host[d.mgmt_ip.strip()]
            elif d.name.strip().lower() in name_to_host:
                matched_host = name_to_host[d.name.strip().lower()]

            if matched_host:
                total_monitored += 1
                province_stats[prov]["monitored"] += 1
                is_avail = matched_host.available
                if is_avail:
                    total_available += 1
                    province_stats[prov]["available"] += 1

                host_probs = problems_by_host.get(matched_host.host_id, [])
                if host_probs:
                    province_stats[prov]["problems"] += len(host_probs)
                    telemetry_status = "CRITICAL" if any(p["severity"] >= 4 for p in host_probs) else "WARNING"
                else:
                    telemetry_status = "HEALTHY" if is_avail else "UNAVAILABLE"

                host_id = matched_host.host_id
            else:
                host_probs = []
                telemetry_status = "UNMONITORED"
                host_id = ""

            device_rows.append({
                "id": d.id,
                "name": d.name,
                "mgmt_ip": d.mgmt_ip,
                "role": d.role or "PE",
                "province": prov,
                "site": d.site or "",
                "zabbix_hostid": host_id,
                "telemetry_host_id": host_id,
                "telemetry_status": telemetry_status,
                "is_available": matched_host.available if matched_host else False,
                "problem_count": len(host_probs),
                "problems": host_probs,
            })

        total_devices = len(devices)
        overall_availability_pct = round((total_available / total_monitored * 100), 1) if total_monitored > 0 else 0.0

        # Collect host groups summary and correlate with active problems
        group_stats: Dict[str, Dict[str, Any]] = {}
        for h in telemetry_hosts.values():
            for gname in h.groups:
                if not gname:
                    continue
                if gname not in group_stats:
                    group_stats[gname] = {
                        "name": gname,
                        "host_count": 0,
                        "available_hosts": 0,
                        "problem_count": 0,
                        "severity_counts": {name: 0 for name in SEVERITY_MAP.values()},
                    }
                group_stats[gname]["host_count"] += 1
                if h.available:
                    group_stats[gname]["available_hosts"] += 1
                h_probs = problems_by_host.get(h.host_id, [])
                group_stats[gname]["problem_count"] += len(h_probs)
                for prob in h_probs:
                    s_name = prob.get("severity_name", "Warning")
                    group_stats[gname]["severity_counts"][s_name] = group_stats[gname]["severity_counts"].get(s_name, 0) + 1

        # Enriched active problems with device name and host groups
        enriched_problems: List[Dict[str, Any]] = []
        for p in active_problems:
            h = telemetry_hosts.get(p.host_id)
            h_groups = h.groups if h else []
            s_name = SEVERITY_MAP.get(p.severity, "Warning")
            dev_name = (h.visible_name if h else None) or (h.name if h else p.host_name) or p.host_name
            enriched_problems.append({
                "event_id": p.event_id,
                "host_id": p.host_id,
                "host_name": h.name if h else p.host_name,
                "device_name": dev_name,
                "name": p.name,
                "severity": p.severity,
                "severity_name": s_name,
                "clock": p.clock,
                "clock_iso": datetime.fromtimestamp(p.clock).isoformat() if p.clock else "",
                "acknowledged": p.acknowledged,
                "groups": h_groups,
                "tags": p.tags,
            })

        sorted_groups = sorted(list(group_stats.values()), key=lambda g: (-g["problem_count"], g["name"]))

        return {
            "summary": {
                "total_devices": total_devices,
                "monitored_devices": total_monitored,
                "unmonitored_devices": total_devices - total_monitored,
                "available_devices": total_available,
                "availability_pct": overall_availability_pct,
                "total_active_problems": len(active_problems),
                "problems_by_severity": severity_counts,
            },
            "province_stats": list(province_stats.values()),
            "devices": device_rows,
            "host_groups": sorted_groups,
            "active_problems": enriched_problems,
        }

    @classmethod
    def get_device_monitoring(
        cls,
        db_session: Session,
        device_identifier: str,
        provider: Optional[TelemetryProvider] = None,
        grafana_client: Optional[GrafanaClient] = None,
        t_from: str = "now-6h",
        t_to: str = "now",
    ) -> Dict[str, Any]:
        """Fetch per-device monitoring tab data: interfaces, metrics, CPU/mem series, and Grafana links."""
        active_provider = provider or get_telemetry_provider()
        grafana = grafana_client or GrafanaClient()

        # Resolve device
        dev = db_session.query(Device).filter(
            or_(
                Device.name.ilike(device_identifier.strip()),
                Device.mgmt_ip == device_identifier.strip(),
            )
        ).first()

        dev_name = dev.name if dev else device_identifier
        dev_ip = dev.mgmt_ip if dev else ""
        telemetry_host_id = (dev.zabbix_hostid if dev else "") or ""

        # Resolve host in telemetry if not set
        if not telemetry_host_id:
            try:
                host_list = active_provider.list_hosts() if hasattr(active_provider, "list_hosts") else active_provider.get_hosts()
                for h in host_list:
                    if h.name.lower() == dev_name.lower() or any(i.get("ip") == dev_ip for i in h.interfaces):
                        telemetry_host_id = h.host_id
                        break
            except Exception:
                pass

        interfaces_data: List[Dict[str, Any]] = []
        cpu_val = None
        mem_val = None
        temp_val = None
        series_data: List[Dict[str, Any]] = []

        if telemetry_host_id:
            try:
                # 1. Interfaces
                ifaces = active_provider.get_interface_table(telemetry_host_id)
                for ifc in ifaces:
                    interfaces_data.append({
                        "name": ifc.name,
                        "admin_status": ifc.admin_status,
                        "oper_status": ifc.oper_status,
                        "in_rate_bps": ifc.in_rate,
                        "out_rate_bps": ifc.out_rate,
                        "errors_in": ifc.errors_in,
                        "errors_out": ifc.errors_out,
                    })

                # 2. Scalar items
                cpu_item = active_provider.get_item_value(telemetry_host_id, "cpu")
                if cpu_item and cpu_item.value is not None:
                    cpu_val = {"value": cpu_item.value, "units": cpu_item.units or "%", "clock": cpu_item.clock}

                mem_item = active_provider.get_item_value(telemetry_host_id, "memory") or active_provider.get_item_value(telemetry_host_id, "vm.memory")
                if mem_item and mem_item.value is not None:
                    mem_val = {"value": mem_item.value, "units": mem_item.units or "%", "clock": mem_item.clock}

                temp_item = active_provider.get_item_value(telemetry_host_id, "temperature")
                if temp_item and temp_item.value is not None:
                    temp_val = {"value": temp_item.value, "units": temp_item.units or "C", "clock": temp_item.clock}

                # 3. Time Series for CPU / Bandwidth
                now_ts = int(time.time())
                from_ts = now_ts - 21600  # 6h default
                s_obj = active_provider.get_series(telemetry_host_id, "cpu", from_ts, now_ts, max_points=60)
                if s_obj and s_obj.points:
                    series_data = [{"clock": p.clock, "value": p.value} for p in s_obj.points]

            except Exception as exc:
                logger.warning("Failed querying telemetry for device %s: %s", dev_name, exc)

        # Grafana deep link and embed URL (Step 3.4.3 Mode A)
        variables = {"host": dev_name, "ip": dev_ip}
        deep_link = grafana.build_dashboard_url("huawei-routers", t_from=t_from, t_to=t_to, variables=variables)
        embed_url = grafana.build_embed_url("huawei-routers", panel_id=1, t_from=t_from, t_to=t_to, variables=variables)

        return {
            "device": {
                "name": dev_name,
                "mgmt_ip": dev_ip,
                "telemetry_host_id": telemetry_host_id,
                "role": dev.role if dev else "PE",
                "province": dev.province if dev else "",
            },
            "metrics": {
                "cpu": cpu_val,
                "memory": mem_val,
                "temperature": temp_val,
            },
            "interfaces": interfaces_data,
            "series": series_data,
            "grafana": {
                "deep_link": deep_link,
                "embed_url": embed_url,
            },
        }

    @classmethod
    def search_interfaces(
        cls,
        db_session: Session,
        keyword: str,
        provider: Optional[TelemetryProvider] = None,
    ) -> Dict[str, Any]:
        """Search interfaces across monitored devices with keyword matching and legacy DB fallback."""
        cleaned = keyword.strip()
        if not cleaned:
            return {"keyword": cleaned, "count": 0, "results": []}

        active_provider = provider or get_telemetry_provider()
        results: List[Dict[str, Any]] = []

        # 1. Try active TelemetryProvider
        try:
            hosts = active_provider.list_hosts() if hasattr(active_provider, "list_hosts") else active_provider.get_hosts()
            kw_lower = cleaned.lower()

            for h in hosts:
                # If host matches or interface matches
                host_matches = kw_lower in h.name.lower() or kw_lower in h.visible_name.lower()
                try:
                    ifaces = active_provider.get_interface_table(h.host_id)
                    for ifc in ifaces:
                        if host_matches or kw_lower in ifc.name.lower():
                            results.append({
                                "host_id": h.host_id,
                                "host_name": h.name,
                                "visible_name": h.visible_name,
                                "interface": ifc.name,
                                "oper_status": ifc.oper_status,
                                "in_rate_bps": ifc.in_rate,
                                "out_rate_bps": ifc.out_rate,
                            })
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Telemetry search failed: %s; checking legacy DB fallback", exc)

        # 2. Fallback to zabbix_router_db.json if provider returned nothing
        if not results:
            from services.zabbix_service import ZabbixService
            legacy_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "zabbix_router_db.json"))
            if os.path.isfile(legacy_db):
                try:
                    legacy_res = ZabbixService.search_router_db(
                        keyword=cleaned,
                        db_path=legacy_db,
                        search_host=True,
                        search_interface=True,
                        case_sensitive=False,
                        partial=True,
                    )
                    results = legacy_res
                except Exception as exc:
                    logger.error("Legacy router DB search failed: %s", exc)

        return {
            "keyword": cleaned,
            "count": len(results),
            "results": results,
        }

    @classmethod
    def merge_alarms(
        cls,
        db_session: Session,
        ssh_alarms: List[Dict[str, Any]],
        provider: Optional[TelemetryProvider] = None,
    ) -> Dict[str, Any]:
        """Merge SSH active alarms with Zabbix telemetry problems and provide device selection shortcut."""
        active_provider = provider or get_telemetry_provider()
        zabbix_problems: List[TelemetryProblem] = []

        try:
            zabbix_problems = active_provider.get_problems()
        except Exception as exc:
            logger.warning("Failed to fetch Zabbix problems for alarm merge: %s", exc)

        combined: List[Dict[str, Any]] = []
        problematic_devices: Set[str] = set()

        # Add SSH alarms
        for alm in ssh_alarms:
            dev_name = alm.get("device_name") or alm.get("device") or "Unknown"
            problematic_devices.add(dev_name)
            combined.append({
                "source": "SSH",
                "device": dev_name,
                "alarm_text": alm.get("text") or alm.get("alarm_name") or "",
                "severity": alm.get("level", "WARNING"),
                "interface": alm.get("interface", ""),
                "time": alm.get("time", ""),
            })

        # Add Zabbix problems
        for p in zabbix_problems:
            dev_name = p.host_name or "Unknown"
            problematic_devices.add(dev_name)
            sev_name = SEVERITY_MAP.get(p.severity, "Warning")
            combined.append({
                "source": "ZABBIX",
                "device": dev_name,
                "alarm_text": p.name,
                "severity": sev_name.upper(),
                "interface": p.tags.get("interface", ""),
                "time": datetime.fromtimestamp(p.clock).isoformat() if p.clock else "",
                "event_id": p.event_id,
            })

        # Device selection shortcut for Alarm Clear / Down-Links jobs
        device_selection_shortcut = sorted(list(problematic_devices))

        return {
            "total_alarms": len(combined),
            "ssh_alarms_count": len(ssh_alarms),
            "zabbix_problems_count": len(zabbix_problems),
            "unique_affected_devices": len(device_selection_shortcut),
            "device_selection_shortcut": device_selection_shortcut,
            "alarms": combined,
        }

    @classmethod
    def test_integrations(
        cls,
        provider: Optional[TelemetryProvider] = None,
        grafana_client: Optional[GrafanaClient] = None,
        db_session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Run telemetry doctor diagnostic test suite on Zabbix and Grafana integrations."""
        active_provider = provider or get_telemetry_provider()
        grafana = grafana_client or GrafanaClient()

        # 1. Zabbix Health & Version
        zabbix_status = "ok"
        zabbix_version = "unknown"
        zabbix_error = None
        try:
            if hasattr(active_provider, "detect_version"):
                zabbix_version = active_provider.detect_version()
            else:
                zabbix_version = "mock-5.0"
        except Exception as exc:
            zabbix_status = "error"
            zabbix_error = str(exc)

        # 2. Grafana Health Check
        grafana_health = grafana.check_health()
        grafana_status = "ok" if grafana_health.get("status") == "ok" or grafana_health.get("database") == "ok" else (
            "degraded" if "error" in grafana_health else "ok"
        )

        # 3. Inventory Mapping Coverage %
        total_devices = 0
        mapped_devices = 0
        coverage_pct = 0.0

        if db_session is not None:
            devs = db_session.query(Device).filter(Device.enabled.is_(True)).all()
            total_devices = len(devs)
            mapped_devices = sum(1 for d in devs if d.zabbix_hostid)
            coverage_pct = round((mapped_devices / total_devices * 100), 1) if total_devices > 0 else 0.0

        return {
            "zabbix": {
                "status": zabbix_status,
                "version": zabbix_version,
                "error": zabbix_error,
            },
            "grafana": {
                "status": grafana_status,
                "base_url": grafana.base_url,
                "details": grafana_health,
            },
            "coverage": {
                "total_devices": total_devices,
                "mapped_devices": mapped_devices,
                "coverage_pct": coverage_pct,
            },
            "doctor_verdict": "HEALTHY" if zabbix_status == "ok" and grafana_status == "ok" else "DEGRADED",
        }

    @classmethod
    def process_webhook(cls, payload: Dict[str, Any], db_session: Session) -> Dict[str, Any]:
        """Intake and normalize an alert webhook from Zabbix or external monitoring."""
        event_name = payload.get("event_name") or payload.get("name") or payload.get("title") or "Unnamed Problem"
        hostname = payload.get("hostname") or payload.get("host") or ""
        severity = payload.get("severity", "WARNING")
        timestamp = payload.get("clock") or datetime.now().isoformat()

        logger.info("Webhook received: [%s] on host '%s' (severity: %s)", event_name, hostname, severity)

        # Correlate with Device if hostname provided
        device_match = None
        if hostname:
            device_match = db_session.query(Device).filter(
                or_(
                    Device.name.ilike(hostname.strip()),
                    Device.mgmt_ip == hostname.strip(),
                )
            ).first()

        return {
            "status": "accepted",
            "event_name": event_name,
            "hostname": hostname,
            "device_id": device_match.id if device_match else None,
            "severity": str(severity).upper(),
            "timestamp": timestamp,
        }
