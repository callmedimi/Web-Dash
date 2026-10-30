"""Huawei IEEE 1588 PTP parser (Target Architecture §3)."""
import re
from typing import Dict, Any


def parse_display_ptp_all(output: str) -> Dict[str, Any]:
    """Parse 'display ptp all' output extracting clock IDs, state, and offset."""
    data: Dict[str, Any] = {
        "ptp_state": "",
        "domain_value": None,
        "device_type": "",
        "local_clock_id": "",
        "time_lock_success": None,
        "ptp_profile": "",
        "grand_clock_id": "",
        "receive_number": "",
        "parent_clock_id": "",
        "parent_portnumber": "",
        "step_removed": None,
        "clock_class": None,
        "time_source": "",
        "realtime_t2_t1": None,
        "pathdelay": None,
        "time_offset": None,
    }

    if not output:
        return data

    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        m = re.search(r'PTP\s+state\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["ptp_state"] = m.group(1).lower()

        m = re.search(r'Domain\s+value\s*:\s*(\d+)', line_clean, re.I)
        if m:
            try:
                data["domain_value"] = int(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Device\s+type\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["device_type"] = m.group(1)

        m = re.search(r'Local\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["local_clock_id"] = m.group(1).lower().replace("-", "")

        m = re.search(r'Time\s+lock\s+success\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["time_lock_success"] = m.group(1).lower() in ("yes", "true", "success")

        m = re.search(r'PTP\s+profile\s*:\s*(.+?)(?:\s{2,}|$)', line_clean, re.I)
        if m:
            data["ptp_profile"] = m.group(1).strip()

        m = re.search(r'Grand\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["grand_clock_id"] = m.group(1).lower().replace("-", "")

        m = re.search(r'Receive\s+number\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["receive_number"] = m.group(1)

        m = re.search(r'Parent\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["parent_clock_id"] = m.group(1).lower().replace("-", "")

        m = re.search(r'Parent\s+portnumber\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["parent_portnumber"] = m.group(1)

        m = re.search(r'Step\s+removed\s*:\s*(\d+)', line_clean, re.I)
        if m:
            try:
                data["step_removed"] = int(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Realtime\(T2\-T1\)\(ns\)\s*:\s*([+\-]?\d+(?:\.\d+)?)', line_clean, re.I)
        if m:
            try:
                data["realtime_t2_t1"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Time\s+offset\(ns\)\s*:\s*([+\-]?\d+(?:\.\d+)?)', line_clean, re.I)
        if m:
            try:
                data["time_offset"] = float(m.group(1))
            except ValueError:
                pass

    return data
