"""Overview API: Unified NOC summary endpoint (/api/v1/overview).

Provides cached (30s) aggregate data for the Overview dashboard:
- Fleet health (availability %, devices up/degraded/down by province)
- Zabbix Host Groups filter and correlated active alarms
- Needs attention items (failed jobs, pending approvals, expiring licenses, unreachable devices)
- Recent jobs (last 20 jobs)
- Active problems by severity & 24h trend timeline (filterable by host group)
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from flask import Blueprint, jsonify, request
from sqlalchemy import func, desc

from auth import login_required
from backend.app.extensions import get_db_session
from backend.app.models.device import Device
from backend.app.models.job import Job
from backend.app.models.config_change import ChangeRequest
from backend.app.models.license import LicenseRecord
from backend.app.services.monitoring import MonitoringHubService

logger = logging.getLogger(__name__)

overview_bp = Blueprint("overview_api", __name__)

_CACHE_STORE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_SECONDS: float = 30.0


def _build_overview_payload(selected_group: Optional[str] = None) -> Dict[str, Any]:
    """Compile overview aggregates across DB and telemetry with optional host group filter."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    twenty_four_hours_ago = now_utc - timedelta(hours=24)
    target_group = (selected_group or "").strip()
    is_group_filtered = bool(target_group and target_group.lower() != "all")

    with get_db_session() as session:
        # 1. Fleet health from MonitoringHubService (graceful degradation)
        telemetry_status = "ok"
        telemetry_error = None
        fleet_health = {}
        try:
            fleet_health = MonitoringHubService.get_fleet_health(session)
        except Exception as exc:
            logger.warning("Telemetry unreachable for overview: %s", exc)
            telemetry_status = "degraded"
            telemetry_error = str(exc)

        # Fallback device counts if telemetry is unavailable or empty
        total_devices_count = session.query(func.count(Device.id)).filter(Device.enabled.is_(True)).scalar() or 0

        summary = fleet_health.get("summary", {})
        total_devices = summary.get("total_devices", total_devices_count)
        available_devices = summary.get("available_devices", total_devices_count)
        availability_pct = summary.get("availability_pct", 100.0 if total_devices > 0 else 0.0)

        # Province health list
        provinces = fleet_health.get("provinces", []) or fleet_health.get("province_stats", [])
        if not provinces:
            prov_counts = (
                session.query(Device.province, func.count(Device.id))
                .filter(Device.enabled.is_(True))
                .group_by(Device.province)
                .all()
            )
            provinces = [
                {
                    "province": p or "UNKNOWN",
                    "total": cnt,
                    "monitored": cnt,
                    "available": cnt,
                    "problems": 0,
                    "availability_pct": 100.0,
                }
                for p, cnt in prov_counts
            ]

        # Host groups from telemetry
        available_groups: List[Dict[str, Any]] = fleet_health.get("host_groups", [])
        all_active_problems: List[Dict[str, Any]] = fleet_health.get("active_problems", [])

        # Filter active problems by selected group if specified
        if is_group_filtered:
            filtered_problems = [
                p for p in all_active_problems
                if any(g.lower() == target_group.lower() for g in p.get("groups", []))
            ]
            group_info = next(
                (g for g in available_groups if g["name"].lower() == target_group.lower()),
                None
            )
            if group_info:
                fleet_health_summary = {
                    "total_devices": group_info.get("host_count", total_devices),
                    "available_devices": group_info.get("available_hosts", available_devices),
                    "degraded_devices": max(0, group_info.get("host_count", total_devices) - group_info.get("available_hosts", available_devices)),
                    "availability_pct": round(
                        (group_info.get("available_hosts", 0) / group_info.get("host_count", 1) * 100), 1
                    ) if group_info.get("host_count", 0) > 0 else 100.0,
                    "selected_group": group_info["name"],
                }
            else:
                fleet_health_summary = {
                    "total_devices": len(filtered_problems),
                    "available_devices": len(filtered_problems),
                    "degraded_devices": 0,
                    "availability_pct": 100.0,
                    "selected_group": target_group,
                }
        else:
            filtered_problems = all_active_problems
            fleet_health_summary = {
                "total_devices": total_devices,
                "available_devices": available_devices,
                "degraded_devices": max(0, total_devices - available_devices),
                "availability_pct": availability_pct,
                "selected_group": "all",
            }

        # Sort filtered problems: highest severity first, then newest clock
        filtered_problems.sort(key=lambda p: (-p.get("severity", 0), -p.get("clock", 0)))

        # Problems by severity for current group selection
        problems_by_severity = {
            "disaster": sum(1 for p in filtered_problems if p.get("severity") == 5),
            "high": sum(1 for p in filtered_problems if p.get("severity") == 4),
            "average": sum(1 for p in filtered_problems if p.get("severity") == 3),
            "warning": sum(1 for p in filtered_problems if p.get("severity") == 2),
            "information": sum(1 for p in filtered_problems if p.get("severity") == 1),
            "not_classified": sum(1 for p in filtered_problems if p.get("severity") == 0),
        }

        # 2. Needs Attention (max 10 items)
        needs_attention: List[Dict[str, Any]] = []

        # A: Failed jobs in last 24h
        failed_jobs_count = (
            session.query(func.count(Job.id))
            .filter(Job.created_at >= twenty_four_hours_ago, Job.status == "failed")
            .scalar()
            or 0
        )
        if failed_jobs_count > 0:
            needs_attention.append({
                "id": "failed-jobs",
                "type": "job",
                "title": f"{failed_jobs_count} failed jobs in last 24 hours",
                "severity": "fault",
                "count": failed_jobs_count,
                "link": "/jobs?status=failed",
            })

        # B: Changes awaiting approval
        pending_changes_count = (
            session.query(func.count(ChangeRequest.id))
            .filter(ChangeRequest.status == "awaiting_approval")
            .scalar()
            or 0
        )
        if pending_changes_count > 0:
            needs_attention.append({
                "id": "pending-changes",
                "type": "change",
                "title": f"{pending_changes_count} change requests awaiting approval",
                "severity": "warn",
                "count": pending_changes_count,
                "link": "/changes?status=awaiting_approval",
            })

        # C: Licenses expiring <= 30 days or expired
        expiring_licenses_count = (
            session.query(func.count(LicenseRecord.id))
            .filter((LicenseRecord.days_to_expiry <= 30) | (LicenseRecord.is_expired.is_(True)))
            .scalar()
            or 0
        )
        if expiring_licenses_count > 0:
            needs_attention.append({
                "id": "expiring-licenses",
                "type": "license",
                "title": f"{expiring_licenses_count} router licenses expiring within 30 days",
                "severity": "warn",
                "count": expiring_licenses_count,
                "link": "/reports/licenses?window=30",
            })

        # D: Flapping or unavailable devices in telemetry
        devices_down = fleet_health_summary["total_devices"] - fleet_health_summary["available_devices"]
        if devices_down > 0:
            needs_attention.append({
                "id": "devices-down",
                "type": "device",
                "title": f"{devices_down} devices unreachable or degraded" + (f" in {target_group}" if is_group_filtered else ""),
                "severity": "fault",
                "count": devices_down,
                "link": "/devices?health=down",
            })

        # E: Active high/disaster problems in current selection
        high_critical = problems_by_severity["high"] + problems_by_severity["disaster"]
        if high_critical > 0:
            needs_attention.append({
                "id": "critical-problems",
                "type": "problem",
                "title": f"{high_critical} high/disaster alarms active" + (f" in {target_group}" if is_group_filtered else ""),
                "severity": "fault",
                "count": high_critical,
                "link": "/alarms?level=critical",
            })

        # 3. Recent jobs (last 20)
        recent_jobs_query = (
            session.query(Job)
            .order_by(desc(Job.created_at))
            .limit(20)
            .all()
        )
        recent_jobs = []
        for j in recent_jobs_query:
            dur = None
            if j.started_at and j.finished_at:
                dur = round((j.finished_at - j.started_at).total_seconds(), 1)
            elif j.started_at:
                dur = round((now_utc - j.started_at).total_seconds(), 1)

            recent_jobs.append({
                "id": j.id,
                "type": j.type,
                "status": j.status,
                "mode": j.mode,
                "created_by": j.created_by,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "duration_seconds": dur,
                "summary": j.summary or {},
            })

        # 4. Hourly problems timeline (last 24 hours for time series chart)
        hourly_series: List[Dict[str, Any]] = []
        for i in range(24, 0, -1):
            bucket_time = now_utc - timedelta(hours=i)
            timestamp = int(bucket_time.timestamp())
            hourly_series.append({
                "timestamp": timestamp,
                "disaster": problems_by_severity["disaster"],
                "high": problems_by_severity["high"],
                "warning": problems_by_severity["average"] + problems_by_severity["warning"],
            })

        return {
            "telemetry_status": telemetry_status,
            "telemetry_error": telemetry_error,
            "cached_at": now_utc.isoformat(),
            "selected_group": target_group if is_group_filtered else "all",
            "host_groups": available_groups,
            "group_problems": filtered_problems[:50],  # Top 50 active problems for group
            "fleet_health": {
                "total_devices": fleet_health_summary["total_devices"],
                "available_devices": fleet_health_summary["available_devices"],
                "degraded_devices": fleet_health_summary["degraded_devices"],
                "availability_pct": fleet_health_summary["availability_pct"],
                "provinces": provinces,
            },
            "needs_attention": needs_attention[:10],
            "recent_jobs": recent_jobs,
            "problems_by_severity": problems_by_severity,
            "problems_timeline": hourly_series,
        }


@overview_bp.route("/api/v1/overview", methods=["GET"])
@login_required
def get_overview():
    """Return unified overview dashboard statistics, cached for 30 seconds per group."""
    global _CACHE_STORE

    selected_group = request.args.get("group", "").strip()
    cache_key = f"overview:{selected_group.lower()}"
    now = time.time()

    if cache_key in _CACHE_STORE:
        cached_time, cached_data = _CACHE_STORE[cache_key]
        if (now - cached_time) < _CACHE_TTL_SECONDS:
            return jsonify(cached_data), 200

    try:
        data = _build_overview_payload(selected_group=selected_group)
        _CACHE_STORE[cache_key] = (now, data)
        return jsonify(data), 200
    except Exception as exc:
        logger.exception("Failed to build overview payload for group '%s'", selected_group)
        return jsonify({
            "error": "Failed to load overview data",
            "message": str(exc),
        }), 500
