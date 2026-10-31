"""Down-Links Reporting and Analytics Service (Target Architecture §3 & Phase 5 Step 5.3).

Port of legacy reporting_logic.py with strict schema, multi-tab XLSX & CSV exports,
sliding-window burst detection analytics, and historical snapshot diffing.
"""
import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

from backend.app.devices.session import DeviceSession
from backend.app.devices.parsers.alarms import parse_active_alarms
from backend.app.devices.parsers.interface_ref import extract_interface
from backend.app.devices.parsers.interface import parse_interface_config
from backend.app.models.device import Device
from backend.app.models.down_link import DownLinkReport

TRUNK_IDS = ["0", "33", "85"]
CATEGORY_KEYWORDS = {"OSN": "OSN", "SPO": "SPO", "HRAN": "HRAN"}

FIELD_NAMES = [
    "NE NAME",
    "Interface type",
    "interface name",
    "interface description",
    "admin down or not",
    "alarm occur time",
    "Down Reason",
    "Trunk Memberships",
    "Category",
    "full configuration of the link",
]

TRUNK_FIELD_NAMES = [
    "Province",
    "NE Name",
    "Trunk Name",
    "Trunk Group",
    "Description",
    "Trunk Status",
    "Total Members",
    "Down Members Count",
    "Member Links Details",
    "Down Member Ports",
]


def classify_category(description: Optional[str]) -> str:
    """Classify link into service categories: OSN, SPO, HRAN, or Other."""
    desc_upper = (description or "").upper()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in desc_upper:
            return cat
    return "Other"


def validate_age_threshold(age_value: Any, age_unit: str) -> Tuple[int, timedelta]:
    """Validate age value and unit, returning (int_value, timedelta)."""
    try:
        val = int(age_value)
        if val < 0:
            raise ValueError("Age value cannot be negative")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid age value: '{age_value}'")

    unit = (age_unit or "").strip().lower()
    if unit in ("minute", "minutes", "min", "m"):
        return val, timedelta(minutes=val)
    elif unit in ("hour", "hours", "h"):
        return val, timedelta(hours=val)
    elif unit in ("day", "days", "d"):
        return val, timedelta(days=val)
    else:
        raise ValueError(f"Invalid age unit: '{age_unit}'. Must be minutes, hours, or days.")


def compute_analytics(
    report_data: List[Dict[str, Any]],
    noconf_data: List[Dict[str, Any]],
    trunk_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive down-links analytics:
    - Service vs noconf counts by province
    - Top noisy devices per province
    - 5-minute sliding window burst detection per province
    - Category breakdown (OSN, SPO, HRAN, Other)
    - Trunk group stats
    """
    if trunk_data is None:
        trunk_data = []

    all_entries = report_data + noconf_data
    total = len(all_entries)

    by_province: Dict[str, Dict[str, Any]] = {}
    province_device_counts: Dict[str, Dict[str, int]] = {}
    province_timestamps: Dict[str, List[datetime]] = {}
    category_counts: Dict[str, int] = {"OSN": 0, "SPO": 0, "HRAN": 0, "Other": 0}

    for entry in all_entries:
        ne = entry.get("NE NAME", "")
        # Extract 2-letter or suffix province
        m = re.search(r'_([A-Za-z0-9]{2,4})$', ne)
        p = m.group(1).upper() if m else "Unknown"

        if p not in by_province:
            by_province[p] = {"service": 0, "noconf": 0, "devices": set()}

        is_noconf = entry in noconf_data
        if is_noconf:
            by_province[p]["noconf"] += 1
        else:
            by_province[p]["service"] += 1
        by_province[p]["devices"].add(ne)

        province_device_counts.setdefault(p, {}).setdefault(ne, 0)
        province_device_counts[p][ne] += 1

        cat = entry.get("Category", "Other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

        ts = entry.get("alarm occur time", "")
        if ts and ts != "Unknown":
            try:
                # Handle ISO with timezone or standard format
                clean_ts = ts.strip().replace("Z", "+00:00")
                if "+" in clean_ts or "-" in clean_ts[8:]:
                    dt = datetime.fromisoformat(clean_ts)
                else:
                    dt = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                province_timestamps.setdefault(p, []).append(dt)
            except Exception:
                pass

    province_summary = []
    for p, d in sorted(by_province.items()):
        dev_counts = province_device_counts.get(p, {})
        top_devices = [
            {"device_name": k, "count": v}
            for k, v in sorted(dev_counts.items(), key=lambda x: -x[1])[:5]
        ]

        # 5-minute sliding window burst detection (300 seconds)
        burst = False
        burst_start = ""
        burst_end = ""
        max_in_window = 0
        timestamps = province_timestamps.get(p, [])

        if len(timestamps) >= 3:
            timestamps.sort()
            best_start = timestamps[0]
            best_end = timestamps[0]
            left = 0
            for right in range(len(timestamps)):
                while (timestamps[right] - timestamps[left]).total_seconds() > 300:
                    left += 1
                count = right - left + 1
                if count >= 3 and count > max_in_window:
                    max_in_window = count
                    best_start = timestamps[left]
                    best_end = timestamps[right]
            if max_in_window >= 3:
                burst = True
                burst_start = best_start.strftime("%Y-%m-%d %H:%M:%S")
                burst_end = best_end.strftime("%Y-%m-%d %H:%M:%S")

        province_summary.append({
            "province": p,
            "service_count": d["service"],
            "noconf_count": d["noconf"],
            "total_count": d["service"] + d["noconf"],
            "device_count": len(d["devices"]),
            "top_devices": top_devices,
            "burst_detected": burst,
            "burst_count": max_in_window if burst else 0,
            "burst_start": burst_start,
            "burst_end": burst_end,
        })

    # Trunk group summaries
    trunk_summary = []
    for t in trunk_data:
        trunk_summary.append({
            "province": t.get("Province"),
            "ne_name": t.get("NE Name"),
            "trunk_name": t.get("Trunk Name"),
            "trunk_group": t.get("Trunk Group"),
            "status": t.get("Trunk Status"),
            "total_members": t.get("Total Members"),
            "down_members": t.get("Down Members Count"),
        })

    return {
        "total_down_links": total,
        "service_down_count": len(report_data),
        "noconf_down_count": len(noconf_data),
        "trunk_count": len(trunk_data),
        "province_summary": province_summary,
        "category_breakdown": category_counts,
        "trunk_summary": trunk_summary,
    }


class DownLinksService:
    """Down-Links scanning, comparison, and exporting engine."""

    @staticmethod
    def scan_device_down_links(
        device: Device,
        device_session: Any,
        age_value: int = 0,
        age_unit: str = "hours",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Scan a router for down links:
        - queries active alarms
        - filters physical down alarms
        - checks config (service vs noconf)
        - checks trunk membership
        """
        val, delta_threshold = validate_age_threshold(age_value, age_unit)
        cutoff_dt = datetime.now(timezone.utc) - delta_threshold

        alarm_out = device_session.run("display alarm active")
        parsed_alarms = parse_active_alarms(alarm_out, device_name=device.name)

        service_links = []
        noconf_links = []
        trunks = []

        seen_interfaces = set()

        for item in parsed_alarms:
            desc = item.get("description", "")
            # Match physical status down alarms
            if "physical status is Down" not in desc and "0x08520003" not in item.get("alarm_id", ""):
                continue

            # Check age threshold
            date_str = item.get("date", "")
            time_str = item.get("time", "")
            try:
                clean_time = time_str.strip().replace("Z", "+00:00")
                if "+" in clean_time or "-" in clean_time[8:]:
                    alarm_dt = datetime.fromisoformat(f"{date_str} {clean_time}")
                else:
                    alarm_dt = datetime.strptime(f"{date_str} {clean_time[:8]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if delta_threshold.total_seconds() > 0 and alarm_dt > cutoff_dt:
                    # Alarm is newer than threshold -> skip
                    continue
            except Exception:
                pass

            iface_ref = extract_interface(desc)
            if not iface_ref:
                continue

            iface_name = iface_ref.name
            if iface_name in seen_interfaces:
                continue
            seen_interfaces.add(iface_name)

            # Check interface current configuration
            cfg_out = device_session.run(f"display current-configuration interface {iface_name}")
            cfg_status = parse_interface_config(cfg_out)

            # Check admin down status
            intf_out = device_session.run(f"display interface {iface_name}")
            admin_down = "Administratively DOWN" in intf_out or "Admin: Down" in intf_out

            desc_match = re.search(r'description\s+(.+)', cfg_out, re.IGNORECASE)
            description = desc_match.group(1).strip() if desc_match else "No Description"
            category = classify_category(description)

            # Trunk check
            trunk_info = "None"
            for tid in TRUNK_IDS:
                if f"Eth-Trunk{tid}" in cfg_out or f"eth-trunk {tid}" in cfg_out.lower():
                    trunk_info = f"Eth-Trunk{tid}"
                    break

            entry = {
                "NE NAME": device.name,
                "Interface type": iface_name.split()[0] if " " in iface_name else iface_name[:2],
                "interface name": iface_name,
                "interface description": description,
                "admin down or not": "Admin DOWN" if admin_down else "UP (Oper DOWN)",
                "alarm occur time": f"{date_str} {time_str}",
                "Down Reason": "Physical Link Down",
                "Trunk Memberships": trunk_info,
                "Category": category,
                "full configuration of the link": cfg_out.strip(),
            }

            is_noconf = cfg_status.get("is_trivial", False) or cfg_status.get("is_empty", False)
            if is_noconf:
                noconf_links.append(entry)
            else:
                service_links.append(entry)

        return service_links, noconf_links, trunks

    @staticmethod
    def compare_reports(
        current_report: Dict[str, Any],
        previous_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare current down-links report against a previous/historical report.
        Identifies:
        - new_down_links: links down today that were not down in previous report
        - recovered_links: links that recovered (were down previously, now up)
        - persistent_down_links: links down in both reports
        """
        curr_service = current_report.get("report_data") or []
        curr_noconf = current_report.get("noconf_data") or []
        curr_all = curr_service + curr_noconf

        prev_service = previous_report.get("report_data") or []
        prev_noconf = previous_report.get("noconf_data") or []
        prev_all = prev_service + prev_noconf

        def link_key(entry: Dict[str, Any]) -> str:
            ne = entry.get("NE NAME") or entry.get("ne_name") or ""
            iface = entry.get("interface name") or entry.get("interface") or ""
            return f"{ne.strip().lower()}::{iface.strip().lower()}"

        curr_map = {link_key(e): e for e in curr_all if link_key(e)}
        prev_map = {link_key(e): e for e in prev_all if link_key(e)}

        curr_keys = set(curr_map.keys())
        prev_keys = set(prev_map.keys())

        new_keys = curr_keys - prev_keys
        recovered_keys = prev_keys - curr_keys
        persistent_keys = curr_keys & prev_keys

        new_down = [curr_map[k] for k in sorted(new_keys)]
        recovered = [prev_map[k] for k in sorted(recovered_keys)]
        persistent = [curr_map[k] for k in sorted(persistent_keys)]

        return {
            "comparison_summary": {
                "current_total": len(curr_all),
                "previous_total": len(prev_all),
                "new_down_count": len(new_down),
                "recovered_count": len(recovered),
                "persistent_count": len(persistent),
            },
            "new_down_links": new_down,
            "recovered_links": recovered,
            "persistent_down_links": persistent,
        }

    @staticmethod
    def export_csv(
        report_data: List[Dict[str, Any]],
        noconf_data: Optional[List[Dict[str, Any]]] = None,
        trunk_data: Optional[List[Dict[str, Any]]] = None,
    ) -> bytes:
        """Export down-links into CSV format with UTF-8-SIG encoding."""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=FIELD_NAMES, extrasaction="ignore")
        writer.writeheader()

        for row in report_data:
            writer.writerow(row)

        if noconf_data:
            for row in noconf_data:
                writer.writerow(row)

        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def export_xlsx(
        report_data: List[Dict[str, Any]],
        noconf_data: Optional[List[Dict[str, Any]]] = None,
        trunk_data: Optional[List[Dict[str, Any]]] = None,
        analytics: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Export comprehensive multi-tab Excel workbook using openpyxl."""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()

        # Styles
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        noconf_fill = PatternFill(start_color="595959", end_color="595959", fill_type="solid")
        border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        # Tab 1: Service Down Links
        ws1 = wb.active
        ws1.title = "Service Down Links"
        ws1.append(FIELD_NAMES)
        for col_idx in range(1, len(FIELD_NAMES) + 1):
            cell = ws1.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row in report_data:
            ws1.append([row.get(col, "") for col in FIELD_NAMES])

        # Tab 2: NoConf Down Links
        ws2 = wb.create_sheet(title="NoConf Down Links")
        ws2.append(FIELD_NAMES)
        for col_idx in range(1, len(FIELD_NAMES) + 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = noconf_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        if noconf_data:
            for row in noconf_data:
                ws2.append([row.get(col, "") for col in FIELD_NAMES])

        # Tab 3: Trunk Status
        ws3 = wb.create_sheet(title="Trunk Status")
        ws3.append(TRUNK_FIELD_NAMES)
        for col_idx in range(1, len(TRUNK_FIELD_NAMES) + 1):
            cell = ws3.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

        if trunk_data:
            for row in trunk_data:
                ws3.append([row.get(col, "") for col in TRUNK_FIELD_NAMES])

        # Tab 4: Analytics Summary
        ws4 = wb.create_sheet(title="Analytics Summary")
        ws4.append(["Metric", "Value"])
        ws4.cell(row=1, column=1).font = header_font
        ws4.cell(row=1, column=1).fill = header_fill
        ws4.cell(row=1, column=2).font = header_font
        ws4.cell(row=1, column=2).fill = header_fill

        if analytics:
            ws4.append(["Total Down Links", analytics.get("total_down_links", 0)])
            ws4.append(["Service Down Links", analytics.get("service_down_count", 0)])
            ws4.append(["NoConf Down Links", analytics.get("noconf_down_count", 0)])
            ws4.append(["Trunk Count", analytics.get("trunk_count", 0)])

            # Category Breakdown
            ws4.append([])
            ws4.append(["Category Breakdown", "Count"])
            for cat, count in (analytics.get("category_breakdown") or {}).items():
                ws4.append([cat, count])

            # Province Breakdown
            ws4.append([])
            ws4.append(["Province", "Total Down", "Service", "NoConf", "Burst Detected"])
            for p in analytics.get("province_summary") or []:
                ws4.append([
                    p.get("province"),
                    p.get("total_count"),
                    p.get("service_count"),
                    p.get("noconf_count"),
                    "YES" if p.get("burst_detected") else "No",
                ])

        # Auto-adjust column widths
        for ws in [ws1, ws2, ws3, ws4]:
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
