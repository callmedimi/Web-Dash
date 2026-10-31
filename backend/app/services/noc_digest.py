"""Daily NOC Digest Service (Target Architecture §3 & Phase 5 Step 5.13).

Generates comprehensive daily network operations digest:
- Alarms & Events: total, severity breakdown, top noisy devices
- Down Links: total down, service down, noconf down, province distribution
- Licenses: devices expiring within 7, 30, 90 days and expired devices
- Jobs: execution volume, success/failure rate, failed job details
- Compliance: overall fleet compliance %, rule compliance rates
- Executive Highlights & Overall Status (HEALTHY, ATTENTION_NEEDED, CRITICAL)
- Multi-format exports (XLSX multi-tab, UTF-8-SIG CSV, JSON)
"""
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.models.device import Device
from backend.app.models.license import LicenseRecord
from backend.app.models.job import Job
from backend.app.models.config_change import Event
from backend.app.models.down_link import DownLinkReport
from backend.app.services.compliance import evaluate_fleet_compliance
from backend.app.services.export_service import UnifiedExportService


class NocDigestService:
    """Aggregates multi-source network health telemetry into a unified daily digest."""

    @staticmethod
    def generate_digest(
        db_session: Optional[Session] = None,
        hours: int = 24,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate NOC metrics for the specified trailing window (default: trailing 24 hours).
        """
        end_time = target_date or datetime.now(timezone.utc).replace(tzinfo=None)
        start_time = end_time - timedelta(hours=hours)

        def _do_generate(session: Session) -> Dict[str, Any]:
            # 1. Alarms & Events Summary
            events_query = session.query(Event).filter(Event.ts >= start_time, Event.ts <= end_time)
            total_events = events_query.count()

            sev_counts: Dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "warning": 0, "info": 0}
            events_all = events_query.all()
            for ev in events_all:
                s = (ev.severity or "info").lower()
                sev_counts[s] = sev_counts.get(s, 0) + 1

            # Top noisy devices
            noisy_devices: List[Dict[str, Any]] = []
            try:
                top_dev_tuples = (
                    session.query(Event.device_id, func.count(Event.id).label("cnt"))
                    .filter(Event.ts >= start_time, Event.ts <= end_time, Event.device_id.isnot(None))
                    .group_by(Event.device_id)
                    .order_by(func.count(Event.id).desc())
                    .limit(5)
                    .all()
                )
                for dev_id, cnt in top_dev_tuples:
                    dev_obj = session.query(Device).filter(Device.id == dev_id).first()
                    dev_name = dev_obj.name if dev_obj else f"Device #{dev_id}"
                    noisy_devices.append({"device_id": dev_id, "name": dev_name, "event_count": cnt})
            except Exception:
                pass

            recent_critical_events = [
                {
                    "id": ev.id,
                    "ts": ev.ts.isoformat() if ev.ts else None,
                    "source": ev.source,
                    "device_id": ev.device_id,
                    "severity": ev.severity,
                    "title": ev.title,
                }
                for ev in events_all
                if (ev.severity or "").lower() in ("critical", "major")
            ][:10]

            # 2. Down-Links Summary
            latest_down_report = (
                session.query(DownLinkReport)
                .filter(DownLinkReport.created_at <= end_time)
                .order_by(DownLinkReport.created_at.desc())
                .first()
            )
            down_summary: Dict[str, Any] = {
                "available": latest_down_report is not None,
                "report_id": latest_down_report.id if latest_down_report else None,
                "total_down": latest_down_report.total_down if latest_down_report else 0,
                "service_down": latest_down_report.service_down if latest_down_report else 0,
                "noconf_down": latest_down_report.noconf_down if latest_down_report else 0,
                "scan_time": latest_down_report.created_at.isoformat() if latest_down_report and latest_down_report.created_at else None,
                "provinces": [],
            }
            if latest_down_report and isinstance(latest_down_report.analytics, dict):
                down_summary["provinces"] = latest_down_report.analytics.get("province_summary", [])

            # 3. License Expiration Summary
            all_devices = session.query(Device).all()
            total_monitored_devices = len(all_devices)

            expiring_7d: List[Dict[str, Any]] = []
            expiring_30d: List[Dict[str, Any]] = []
            expiring_90d: List[Dict[str, Any]] = []
            expired_devices: List[Dict[str, Any]] = []

            license_records = session.query(LicenseRecord).all()
            for rec in license_records:
                dev = rec.device
                dev_name = dev.name if dev else f"Device #{rec.device_id}"
                days = rec.days_to_expiry
                state = rec.license_state or "Normal"
                entry = {
                    "id": rec.id,
                    "device_id": rec.device_id,
                    "name": dev_name,
                    "mgmt_ip": dev.mgmt_ip if dev else "",
                    "role": dev.role if dev else "",
                    "province": dev.province if dev else "",
                    "days_remaining": days,
                    "license_state": state,
                    "expiry_date": rec.expiry_date,
                    "is_expired": rec.is_expired,
                }
                if rec.is_expired or (days is not None and days < 0):
                    expired_devices.append(entry)
                elif days is not None:
                    if days <= 7:
                        expiring_7d.append(entry)
                    elif days <= 30:
                        expiring_30d.append(entry)
                    elif days <= 90:
                        expiring_90d.append(entry)

            # 4. Jobs Execution Summary
            jobs_in_window = session.query(Job).filter(Job.created_at >= start_time, Job.created_at <= end_time).all()
            total_jobs = len(jobs_in_window)
            job_status_counts: Dict[str, int] = {}
            failed_jobs_list: List[Dict[str, Any]] = []

            for j in jobs_in_window:
                st = j.status or "unknown"
                job_status_counts[st] = job_status_counts.get(st, 0) + 1
                if st == "failed":
                    summary_dict = j.summary if isinstance(j.summary, dict) else {}
                    err_msg = summary_dict.get("error") or summary_dict.get("failure_reason") or "Unknown error"
                    failed_jobs_list.append({
                        "id": j.id,
                        "type": j.type,
                        "created_by": j.created_by,
                        "created_at": j.created_at.isoformat() if j.created_at else None,
                        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                        "error": str(err_msg),
                    })

            # 5. Fleet Compliance Summary
            compliance_data: Dict[str, Any] = {
                "overall_compliance_pct": 100.0,
                "total_devices": total_monitored_devices,
                "evaluated_devices": 0,
                "compliant_devices": 0,
                "non_compliant_devices": 0,
                "failed_rules_summary": {},
            }
            try:
                comp_result = evaluate_fleet_compliance(session)
                compliance_data["overall_compliance_pct"] = comp_result.get("overall_compliance_pct", 100.0)
                compliance_data["evaluated_devices"] = comp_result.get("total_evaluated", 0)
                compliance_data["compliant_devices"] = comp_result.get("total_compliant", 0)
                compliance_data["non_compliant_devices"] = comp_result.get("total_evaluated", 0) - comp_result.get("total_compliant", 0)
                compliance_data["failed_rules_summary"] = comp_result.get("rules_breakdown", {})
            except Exception:
                pass

            # 6. Highlights & Overall Verdict
            critical_alarm_count = sev_counts.get("critical", 0)
            failed_jobs_count = job_status_counts.get("failed", 0)
            expiring_soon_count = len(expiring_7d) + len(expired_devices)

            highlights: List[str] = []
            if critical_alarm_count > 0:
                highlights.append(f"{critical_alarm_count} critical active alarms requiring investigation.")
            if failed_jobs_count > 0:
                highlights.append(f"{failed_jobs_count} failed automation jobs detected in the last {hours} hours.")
            if expiring_soon_count > 0:
                highlights.append(f"{expiring_soon_count} devices with licenses expiring within 7 days or already expired.")
            if down_summary["service_down"] > 0:
                highlights.append(f"{down_summary['service_down']} service links reported down in latest scan.")
            comp_pct = compliance_data["overall_compliance_pct"]
            highlights.append(f"Fleet security configuration compliance is at {comp_pct:.1f}%.")

            if critical_alarm_count >= 5 or failed_jobs_count >= 5 or len(expired_devices) >= 3:
                overall_status = "CRITICAL"
            elif critical_alarm_count > 0 or failed_jobs_count > 0 or expiring_soon_count > 0 or down_summary["service_down"] > 0:
                overall_status = "ATTENTION_NEEDED"
            else:
                overall_status = "HEALTHY"

            return {
                "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "window_hours": hours,
                },
                "status": overall_status,
                "highlights": highlights,
                "metrics": {
                    "total_devices": total_monitored_devices,
                    "total_events": total_events,
                    "critical_alarms": critical_alarm_count,
                    "failed_jobs": failed_jobs_count,
                    "service_down_links": down_summary["service_down"],
                    "licenses_expiring_7d": len(expiring_7d),
                    "compliance_pct": compliance_data["overall_compliance_pct"],
                },
                "alarms": {
                    "total": total_events,
                    "severity_counts": sev_counts,
                    "top_noisy_devices": noisy_devices,
                    "recent_critical": recent_critical_events,
                },
                "down_links": down_summary,
                "licenses": {
                    "total_monitored": total_monitored_devices,
                    "expiring_7d_count": len(expiring_7d),
                    "expiring_30d_count": len(expiring_30d),
                    "expiring_90d_count": len(expiring_90d),
                    "expired_count": len(expired_devices),
                    "expiring_7d": expiring_7d,
                    "expired_devices": expired_devices,
                },
                "jobs": {
                    "total_executed": total_jobs,
                    "status_counts": job_status_counts,
                    "failed_jobs": failed_jobs_list,
                },
                "compliance": compliance_data,
            }

        if db_session:
            return _do_generate(db_session)
        with get_db_session() as s:
            return _do_generate(s)

    @staticmethod
    def export_digest(digest: Dict[str, Any], format_type: str = "xlsx") -> Tuple[bytes, str, str]:
        """
        Export generated NOC digest into desired format.
        Returns (content_bytes, mimetype, filename).
        """
        fmt = format_type.lower().strip()
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if fmt == "json":
            content = UnifiedExportService.export_json(digest)
            return content, "application/json", f"noc_digest_{date_str}.json"

        elif fmt == "csv":
            # Flatten high-level metrics into tabular CSV
            metrics_rows = [
                {"Section": "Period", "Metric": "Start Time", "Value": digest.get("period", {}).get("start")},
                {"Section": "Period", "Metric": "End Time", "Value": digest.get("period", {}).get("end")},
                {"Section": "Period", "Metric": "Window (Hours)", "Value": digest.get("period", {}).get("window_hours")},
                {"Section": "Status", "Metric": "Overall Status", "Value": digest.get("status")},
                {"Section": "Alarms", "Metric": "Total Events", "Value": digest.get("alarms", {}).get("total")},
                {"Section": "Alarms", "Metric": "Critical Alarms", "Value": digest.get("alarms", {}).get("severity_counts", {}).get("critical", 0)},
                {"Section": "Alarms", "Metric": "Major Alarms", "Value": digest.get("alarms", {}).get("severity_counts", {}).get("major", 0)},
                {"Section": "Down Links", "Metric": "Total Down Links", "Value": digest.get("down_links", {}).get("total_down", 0)},
                {"Section": "Down Links", "Metric": "Service Down", "Value": digest.get("down_links", {}).get("service_down", 0)},
                {"Section": "Licenses", "Metric": "Expiring <= 7 Days", "Value": digest.get("licenses", {}).get("expiring_7d_count", 0)},
                {"Section": "Licenses", "Metric": "Expired Count", "Value": digest.get("licenses", {}).get("expired_count", 0)},
                {"Section": "Jobs", "Metric": "Total Executed", "Value": digest.get("jobs", {}).get("total_executed", 0)},
                {"Section": "Jobs", "Metric": "Failed Jobs", "Value": digest.get("jobs", {}).get("status_counts", {}).get("failed", 0)},
                {"Section": "Compliance", "Metric": "Fleet Compliance %", "Value": f"{digest.get('compliance', {}).get('overall_compliance_pct', 100):.1f}%"},
            ]
            content = UnifiedExportService.export_csv(metrics_rows, fieldnames=["Section", "Metric", "Value"])
            return content, "text/csv; charset=utf-8-sig", f"noc_digest_{date_str}.csv"

        else:
            # Multi-tab XLSX workbook
            overview_rows = [
                {"Metric": "Overall Status", "Value": digest.get("status")},
                {"Metric": "Period Start", "Value": digest.get("period", {}).get("start")},
                {"Metric": "Period End", "Value": digest.get("period", {}).get("end")},
                {"Metric": "Total Monitored Devices", "Value": digest.get("metrics", {}).get("total_devices")},
                {"Metric": "Critical Alarms", "Value": digest.get("metrics", {}).get("critical_alarms")},
                {"Metric": "Service Down Links", "Value": digest.get("metrics", {}).get("service_down_links")},
                {"Metric": "Failed Jobs", "Value": digest.get("metrics", {}).get("failed_jobs")},
                {"Metric": "Licenses Expiring in 7 Days", "Value": digest.get("metrics", {}).get("licenses_expiring_7d")},
                {"Metric": "Fleet Compliance %", "Value": f"{digest.get('metrics', {}).get('compliance_pct', 100):.1f}%"},
            ]
            for idx, h in enumerate(digest.get("highlights", []), 1):
                overview_rows.append({"Metric": f"Highlight #{idx}", "Value": h})

            # Tab 2: Recent Critical Alarms
            alarms_rows = digest.get("alarms", {}).get("recent_critical", [])
            if not alarms_rows:
                alarms_rows = [{"Message": "No critical alarms reported in this period"}]

            # Tab 3: Down Links Province Distribution
            down_provinces = digest.get("down_links", {}).get("provinces", [])
            if not down_provinces:
                down_provinces = [{"Message": "No down links recorded"}]

            # Tab 4: Licenses At Risk
            lic_rows = digest.get("licenses", {}).get("expiring_7d", []) + digest.get("licenses", {}).get("expired_devices", [])
            if not lic_rows:
                lic_rows = [{"Message": "No licenses expiring within 7 days or expired"}]

            # Tab 5: Failed Jobs
            jobs_rows = digest.get("jobs", {}).get("failed_jobs", [])
            if not jobs_rows:
                jobs_rows = [{"Message": "All executed jobs succeeded"}]

            sheets = {
                "Executive Summary": overview_rows,
                "Critical Alarms": alarms_rows,
                "Down Links": down_provinces,
                "Licenses At Risk": lic_rows,
                "Failed Jobs": jobs_rows,
            }
            content = UnifiedExportService.export_xlsx(sheets)
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return content, mimetype, f"noc_digest_{date_str}.xlsx"
