"""Alarm Center Service (Target Architecture §3 & Phase 5 Step 5.2).

Unified active alarms querying, normalization, filtering, statistics,
and safe change pipeline integration.
"""
from collections import Counter
from datetime import datetime, timezone
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.devices.session import DeviceSession
from backend.app.devices.parsers.alarms import parse_active_alarms
from backend.app.devices.parsers.interface_ref import extract_interface
from backend.app.models.device import Device
from backend.app.jobs.change import ChangePipelineService

LEVEL_NAMES: Dict[int, str] = {
    1: "Critical",
    2: "Major",
    3: "Minor",
    4: "Warning",
}

LEVEL_NUMBERS: Dict[str, int] = {
    "CRITICAL": 1,
    "MAJOR": 2,
    "MINOR": 3,
    "WARNING": 4,
}


def calculate_alarm_age_minutes(date_str: str, time_str: str) -> Optional[int]:
    """Calculate minutes elapsed since alarm generated date and time."""
    try:
        # Time string might have timezone offset (+03:30, Z) or just HH:MM:SS
        clean_time = time_str.strip()
        dt_full = f"{date_str.strip()} {clean_time}"

        # Standard ISO 8601 parsing
        if "+" in clean_time or "-" in clean_time[8:] or "Z" in clean_time:
            dt = datetime.fromisoformat(dt_full.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(dt_full[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff_seconds = (now - dt).total_seconds()
        return max(0, int(diff_seconds / 60))
    except Exception:
        return None


class AlarmCenterService:
    """Core logic for on-demand alarm fetching, filtering, and analytics."""

    @staticmethod
    def parse_device_alarm_output(
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """Parse raw 'display alarm active' CLI output and enrich with device metadata."""
        parsed = parse_active_alarms(output, device_name=device.name)
        enriched = []

        for item in parsed:
            desc = item.get("description", "")
            iface_ref = extract_interface(desc)
            if iface_ref:
                iface_norm = iface_ref.name
                parent_iface = iface_ref.parent
                is_sub = iface_ref.is_sub
            else:
                iface_norm = None
                parent_iface = None
                is_sub = False

            level_num = item.get("level", 4)
            level_name = LEVEL_NAMES.get(level_num, "Warning")

            age = calculate_alarm_age_minutes(item.get("date", ""), item.get("time", ""))

            enriched.append({
                "device_id": device.id,
                "device_name": device.name,
                "province": device.province or "Unknown",
                "site": device.site or "Unknown",
                "sequence": item.get("sequence"),
                "alarm_id": item.get("alarm_id"),
                "level": level_num,
                "level_name": level_name,
                "date": item.get("date"),
                "time": item.get("time"),
                "description": desc,
                "interface": iface_norm,
                "parent_interface": parent_iface,
                "is_subinterface": is_sub,
                "age_minutes": age,
            })

        return enriched

    @staticmethod
    def query_device_alarms(
        device: Device,
        device_session: Optional[Any] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch active alarms from single device via SSH session."""
        try:
            if device_session is not None:
                out = device_session.run("display alarm active")
            else:
                with DeviceSession(
                    ip=device.mgmt_ip,
                    os_family=device.os_family,
                    device_name=device.name,
                ) as sess:
                    out = sess.run("display alarm active")

            alarms = AlarmCenterService.parse_device_alarm_output(out, device)
            return alarms, None
        except Exception as e:
            return [], str(e)

    @staticmethod
    def filter_alarms(
        alarms: List[Dict[str, Any]],
        device_name: Optional[str] = None,
        province: Optional[str] = None,
        site: Optional[str] = None,
        level: Optional[str] = None,
        interface: Optional[str] = None,
        search_text: Optional[str] = None,
        min_age_minutes: Optional[int] = None,
        max_age_minutes: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Apply multi-dimensional filtering to unified alarm list."""
        filtered = alarms

        if device_name:
            pat = device_name.strip().lower()
            filtered = [a for a in filtered if pat in a["device_name"].lower()]

        if province:
            p_clean = province.strip().upper()
            filtered = [a for a in filtered if (a.get("province") or "").upper() == p_clean]

        if site:
            s_clean = site.strip().lower()
            filtered = [a for a in filtered if s_clean in (a.get("site") or "").lower()]

        if level:
            lvl_clean = level.strip().upper()
            target_num = LEVEL_NUMBERS.get(lvl_clean)
            if target_num:
                filtered = [a for a in filtered if a.get("level") == target_num]
            else:
                filtered = [a for a in filtered if (a.get("level_name") or "").upper() == lvl_clean]

        if interface:
            if_clean = interface.strip().lower()
            filtered = [a for a in filtered if if_clean in (a.get("interface") or "").lower()]

        if search_text:
            st = search_text.strip().lower()
            filtered = [
                a for a in filtered
                if st in a["description"].lower()
                or st in a["device_name"].lower()
                or st in a.get("alarm_id", "").lower()
            ]

        if min_age_minutes is not None:
            filtered = [a for a in filtered if (a.get("age_minutes") or 0) >= min_age_minutes]

        if max_age_minutes is not None:
            filtered = [a for a in filtered if (a.get("age_minutes") or 0) <= max_age_minutes]

        return filtered

    @staticmethod
    def compute_statistics(alarms: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute aggregated statistics across alarms."""
        total = len(alarms)
        device_counts = Counter(a["device_name"] for a in alarms)
        interface_counts = Counter(
            f"{a['device_name']}:{a['interface']}" for a in alarms if a.get("interface")
        )
        province_counts = Counter(a.get("province", "Unknown") for a in alarms)
        level_counts = Counter(a.get("level_name", "Warning") for a in alarms)

        # Age histogram buckets
        histogram = {
            "< 1h": 0,
            "1h - 6h": 0,
            "6h - 24h": 0,
            "1d - 7d": 0,
            "> 7d": 0,
        }

        for a in alarms:
            age = a.get("age_minutes")
            if age is None:
                continue
            if age < 60:
                histogram["< 1h"] += 1
            elif age < 360:
                histogram["1h - 6h"] += 1
            elif age < 1440:
                histogram["6h - 24h"] += 1
            elif age < 10080:
                histogram["1d - 7d"] += 1
            else:
                histogram["> 7d"] += 1

        top_noisy_devices = [
            {"device_name": k, "count": v}
            for k, v in device_counts.most_common(10)
        ]

        top_noisy_interfaces = [
            {"target": k, "count": v}
            for k, v in interface_counts.most_common(10)
        ]

        return {
            "total_alarms": total,
            "top_noisy_devices": top_noisy_devices,
            "top_noisy_interfaces": top_noisy_interfaces,
            "level_breakdown": {
                "Critical": level_counts.get("Critical", 0),
                "Major": level_counts.get("Major", 0),
                "Minor": level_counts.get("Minor", 0),
                "Warning": level_counts.get("Warning", 0),
            },
            "age_histogram": histogram,
            "by_province": dict(province_counts.most_common()),
        }

    @staticmethod
    def plan_alarm_clears(
        session: Session,
        alarm_items: List[Dict[str, Any]],
        creator_id: str,
        noconf_shutdown: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Convert selected alarm items into Safe Change Pipeline plan requests.
        Ensures all clears follow Step 4.2 pipeline contract (Plan -> Approve -> Apply -> Verify).
        """
        # Group alarms by device_id
        by_device: Dict[int, List[Dict[str, Any]]] = {}
        for a in alarm_items:
            dev_id = a.get("device_id")
            if dev_id:
                by_device.setdefault(dev_id, []).append(a)

        change_requests = []
        for dev_id, dev_alarms in by_device.items():
            dev = session.query(Device).filter(Device.id == dev_id).first()
            if not dev:
                continue

            clear_lines = []
            for item in dev_alarms:
                seq = item.get("sequence")
                if seq is not None:
                    clear_lines.append(f"clear alarm active sequence {seq}")

            if not clear_lines:
                continue

            # Plan through ChangePipelineService
            cr = ChangePipelineService.create_change_request(
                db_session=session,
                device_id=dev.id,
                creator_id=creator_id,
                lines=clear_lines,
                inverse_lines=[],
                reason=f"Alarm Center clear for {len(clear_lines)} alarm(s) (noconf={noconf_shutdown})",
                risk_level="low",
            )
            change_requests.append(cr.to_dict())

        return change_requests

