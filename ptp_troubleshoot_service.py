"""
PTP & Telecom Sync Troubleshooting Engine
==========================================
Modular service providing:
1. Regex-based CLI parsers for Huawei VRP PTP, Clock Source, Interface Optics, Alarms, and LLDP.
2. Hop-by-hop automated diagnostic analysis against ITU-T G.8275.1 telecom sync standards.
3. Recursive upstream clock tree traceback (Hop 0 -> Hop 1 -> ... -> Root GM/BITS) with loop detection.
4. Automated Root Cause Analysis (RCA) and Team Demarcation (IP Team vs. Sync / Transmission Team).
5. Structured report generation with executive KPIs and copy-pasteable handover tickets.
"""

from __future__ import annotations

import os
import re
import csv
import json
import logging
import ipaddress
from typing import Dict, Any, List, Optional, Tuple, Callable

logger = logging.getLogger("ptp_troubleshoot")

# ---------------------------------------------------------------------------
# Telecom Sync & Optical Thresholds (ITU-T G.8275.1 / G.8262)
# ---------------------------------------------------------------------------
PTP_OFFSET_HEALTHY_MAX_NS = 100.0   # <= 100 ns: Optimal
PTP_OFFSET_WARNING_MAX_NS = 500.0   # 100 - 500 ns: Warning / Approaching limit
# > 500 ns: Critical Alarm (Exceeds ITU-T G.8275.1 standard for phase/time alignment)

DEFAULT_MAX_HOPS = 5
DEFAULT_CONNECT_TIMEOUT = 20
DEFAULT_COMMAND_TIMEOUT = 30

# Whitelisted read-only CLI commands for Huawei VRP
WHITELISTED_COMMANDS = [
    "screen-length 0 temporary",
    "display ptp all",
    "display clock source",
    "display clock config",
    "display alarm active | include PTP",
    "display alarm active | include ptp",
    "display lldp neighbor brief",
]


# ---------------------------------------------------------------------------
# Parser: `display ptp all`
# ---------------------------------------------------------------------------
def parse_display_ptp_all(output: str) -> Dict[str, Any]:
    """
    Parses Huawei VRP `display ptp all` output.
    Extracts PTP state, profile, device type, local/grand/parent clock IDs,
    active slave receive interface, step removed, clock class, time source,
    and Realtime(T2-T1).
    """
    data: Dict[str, Any] = {
        "raw_output": output,
        "ptp_state": "",
        "domain_value": None,
        "device_type": "",
        "local_clock_id": "",
        "time_lock_success": None,
        "ptp_profile": "",
        "grand_clock_id": "",
        "receive_number": "",         # Active slave interface receiving sync
        "parent_clock_id": "",
        "parent_portnumber": "",
        "step_removed": None,
        "clock_class": None,
        "time_source": "",
        "realtime_t2_t1": None,       # In nanoseconds
        "pathdelay": None,
        "time_offset": None,
    }

    if not output:
        return data

    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        # PTP state & Domain value
        m = re.search(r'PTP\s+state\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["ptp_state"] = m.group(1).lower()

        m = re.search(r'Domain\s+value\s*:\s*(\d+)', line_clean, re.I)
        if m:
            try:
                data["domain_value"] = int(m.group(1))
            except ValueError:
                pass

        # Device type & Local clock ID
        m = re.search(r'Device\s+type\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["device_type"] = m.group(1)

        m = re.search(r'Local\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["local_clock_id"] = m.group(1).lower().replace("-", "")

        # Time lock success & PTP profile
        m = re.search(r'Time\s+lock\s+success\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["time_lock_success"] = m.group(1).lower() in ("yes", "true", "success")

        m = re.search(r'PTP\s+profile\s*:\s*(.+?)(?:\s{2,}|$)', line_clean, re.I)
        if m:
            data["ptp_profile"] = m.group(1).strip()

        # Grand clock ID & Receive number (Active slave interface)
        m = re.search(r'Grand\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["grand_clock_id"] = m.group(1).lower().replace("-", "")

        m = re.search(r'Receive\s+number\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["receive_number"] = m.group(1)

        # Parent clock ID & Parent portnumber
        m = re.search(r'Parent\s+clock\s+ID\s*:\s*([0-9a-fA-F\-]+)', line_clean, re.I)
        if m:
            data["parent_clock_id"] = m.group(1).lower().replace("-", "")

        m = re.search(r'Parent\s+portnumber\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["parent_portnumber"] = m.group(1)

        # Step removed & Clock class
        m = re.search(r'Step\s+removed\s*:\s*(\d+)', line_clean, re.I)
        if m:
            try:
                data["step_removed"] = int(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Clock\s+class\s*:\s*(\d+)', line_clean, re.I)
        if m:
            try:
                data["clock_class"] = int(m.group(1))
            except ValueError:
                pass

        # Time Source & Realtime(T2-T1)
        m = re.search(r'Time\s+Source\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["time_source"] = m.group(1).lower()

        m = re.search(r'Realtime\(T2-T1\)\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["realtime_t2_t1"] = float(m.group(1))
            except ValueError:
                pass

        # Pathdelay & Time offset
        m = re.search(r'Pathdelay\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["pathdelay"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Time\s+offset\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["time_offset"] = float(m.group(1))
            except ValueError:
                pass

    return data


# ---------------------------------------------------------------------------
# Parser: `display ptp interface <interface>`
# ---------------------------------------------------------------------------
def parse_display_ptp_interface(output: str) -> Dict[str, Any]:
    """
    Parses Huawei VRP `display ptp interface <name>` output.
    Captures Port state, Path delay, Realtime(T2-T1), Time offset, and Port asymmetry delay.
    """
    data: Dict[str, Any] = {
        "raw_output": output,
        "interface_name": "",
        "port_state": "",
        "path_delay": None,
        "realtime_t2_t1": None,
        "time_offset": None,
        "port_asymmetry_delay": None,
        "delay_mechanism": "",
    }

    if not output:
        return data

    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        m = re.search(r'Interface\s+name\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["interface_name"] = m.group(1)

        m = re.search(r'Port\s+state\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["port_state"] = m.group(1).lower()

        m = re.search(r'Path\s+delay\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["path_delay"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Realtime\(T2-T1\)\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["realtime_t2_t1"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Time\s+offset\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["time_offset"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'(?:Port\s+)?asymmetry\s+delay\s*:\s*([\-\d\.]+)', line_clean, re.I)
        if m:
            try:
                data["port_asymmetry_delay"] = float(m.group(1))
            except ValueError:
                pass

        m = re.search(r'Delay\s+mechanism\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["delay_mechanism"] = m.group(1)

    return data


# ---------------------------------------------------------------------------
# Parser: `display clock source`
# ---------------------------------------------------------------------------
def parse_display_clock_source(output: str) -> Dict[str, Any]:
    """
    Parses Huawei VRP `display clock source` output.
    Captures:
      - System trace source State: lock mode / free-run / holdover
      - Current system trace source: ptp / BITS / interface
      - Frequency lock success: yes / no
      - Clock source table rows (Source, Pri, In-SSM, Out-SSM, State, Ref)
    """
    data: Dict[str, Any] = {
        "raw_output": output,
        "trace_source_state": "",
        "current_trace_source": "",
        "frequency_lock_success": None,
        "sources": [],
    }

    if not output:
        return data

    in_table = False
    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        m = re.search(r'System\s+trace\s+source\s+State\s*:\s*(.+)$', line_clean, re.I)
        if m:
            data["trace_source_state"] = m.group(1).strip().lower()
            continue

        m = re.search(r'Current\s+system\s+trace\s+source\s*:\s*(.+)$', line_clean, re.I)
        if m:
            data["current_trace_source"] = m.group(1).strip().lower()
            continue

        m = re.search(r'Frequency\s+lock\s+success\s*:\s*(\S+)', line_clean, re.I)
        if m:
            data["frequency_lock_success"] = m.group(1).strip().lower() in ("yes", "true", "success")
            continue

        if re.search(r'Source\s+Pri', line_clean, re.I):
            in_table = True
            continue

        if in_table:
            # Matches rows like:
            # GE0/2/0    ---/---         dnu      dnu       normal    no
            # ptp        1  /---         prc      --        normal    yes
            parts = line_clean.split()
            if len(parts) >= 6:
                src_name = parts[0]
                pri = parts[1]
                in_ssm = parts[2].lower()
                out_ssm = parts[3].lower()
                state = parts[4].lower()
                ref = parts[5].lower()
                data["sources"].append({
                    "source": src_name,
                    "priority": pri,
                    "in_ssm": in_ssm,
                    "out_ssm": out_ssm,
                    "state": state,
                    "referenced": ref in ("yes", "true", "y"),
                })

    return data


# ---------------------------------------------------------------------------
# Parser: `display interface <name>` (Universal Layer-1 & Optics)
# ---------------------------------------------------------------------------
def parse_display_interface(output: str) -> Dict[str, Any]:
    """
    Parses Huawei VRP `display interface <name>` output.
    Captures:
      - Physical state: UP / DOWN / Administratively DOWN
      - Line protocol state: UP / DOWN
      - Description
      - Transceiver info: Identifier (e.g. SFP+), Wavelength, Transmission Distance
      - Rx Power (dBm) and working range [min, max]
      - Tx Power (dBm) and working range [min, max]
      - CRC errors, input drops, output drops
    """
    data: Dict[str, Any] = {
        "raw_output": output,
        "interface_name": "",
        "physical_state": "",
        "line_protocol": "",
        "description": "",
        "transceiver_identifier": "",
        "wavelength": "",
        "transmission_distance": "",
        "rx_power_dbm": None,
        "rx_power_range": None,
        "tx_power_dbm": None,
        "tx_power_range": None,
        "crc_errors": 0,
        "input_errors": 0,
        "input_drops": 0,
        "output_drops": 0,
        "optical_status": "UNKNOWN",  # HEALTHY, WARNING, CRITICAL, NOT_APPLICABLE
        "optical_detail": "",
    }

    if not output:
        return data

    lines = output.splitlines()
    if lines:
        first_line = lines[0].strip()
        m = re.search(r'(\S+)\s+current\s+state\s*:\s*(.+)$', first_line, re.I)
        if m:
            data["interface_name"] = m.group(1)
            data["physical_state"] = m.group(2).strip().upper()

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        m = re.search(r'Line\s+protocol\s+current\s+state\s*:\s*(.+)$', line_clean, re.I)
        if m:
            data["line_protocol"] = m.group(1).strip().upper()

        m = re.search(r'Description\s*:\s*(.+)$', line_clean, re.I)
        if m and not data["description"]:
            data["description"] = m.group(1).strip()

        m = re.search(r'Transceiver\s+Identifier\s*:\s*([^\r\n,]+)', line_clean, re.I)
        if m:
            data["transceiver_identifier"] = m.group(1).strip()

        m = re.search(r'WaveLength\s*:\s*([^\r\n,]+)', line_clean, re.I)
        if m:
            data["wavelength"] = m.group(1).strip()

        m = re.search(r'Transmission\s+Distance\s*:\s*([^\r\n,]+)', line_clean, re.I)
        if m:
            data["transmission_distance"] = m.group(1).strip()

        # Rx Power:  -4.57dBm, Working range: [-14.400,  0.499]dBm
        m = re.search(r'Rx\s+Power\s*:\s*([\-\d\.]+)\s*dBm(?:,\s*Working\s+range\s*:\s*\[([\-\d\.]+)\s*,\s*([\-\d\.]+)\])?', line_clean, re.I)
        if m:
            try:
                data["rx_power_dbm"] = float(m.group(1))
            except ValueError:
                pass
            if m.group(2) and m.group(3):
                try:
                    data["rx_power_range"] = (float(m.group(2)), float(m.group(3)))
                except ValueError:
                    pass

        # Tx Power:  -4.12dBm, Working range: [-8.198,  0.499]dBm
        m = re.search(r'Tx\s+Power\s*:\s*([\-\d\.]+)\s*dBm(?:,\s*Working\s+range\s*:\s*\[([\-\d\.]+)\s*,\s*([\-\d\.]+)\])?', line_clean, re.I)
        if m:
            try:
                data["tx_power_dbm"] = float(m.group(1))
            except ValueError:
                pass
            if m.group(2) and m.group(3):
                try:
                    data["tx_power_range"] = (float(m.group(2)), float(m.group(3)))
                except ValueError:
                    pass

        # CRC errors & Drops
        # e.g.: ... packets, ... bytes, 0 CRC
        m = re.search(r'(\d+)\s+CRC', line_clean, re.I)
        if m:
            try:
                data["crc_errors"] = int(m.group(1))
            except ValueError:
                pass

        m = re.search(r'(\d+)\s+input\s+errors', line_clean, re.I)
        if m:
            try:
                data["input_errors"] = int(m.group(1))
            except ValueError:
                pass

        m = re.search(r'(\d+)\s+drops', line_clean, re.I)
        if m:
            val = int(m.group(1))
            if "input" in line_clean.lower():
                data["input_drops"] = val
            elif "output" in line_clean.lower():
                data["output_drops"] = val

    # Optical health evaluation
    rx = data["rx_power_dbm"]
    rx_range = data["rx_power_range"]

    if rx is not None:
        if rx_range:
            low_limit, high_limit = rx_range
            if rx < low_limit:
                data["optical_status"] = "CRITICAL"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is BELOW minimum threshold ({low_limit:.2f} dBm)"
            elif rx > high_limit:
                data["optical_status"] = "WARNING"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is ABOVE maximum threshold ({high_limit:.2f} dBm)"
            elif rx <= low_limit + 1.5:
                data["optical_status"] = "WARNING"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is approaching low threshold ({low_limit:.2f} dBm)"
            else:
                data["optical_status"] = "HEALTHY"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm within operating range [{low_limit:.2f}, {high_limit:.2f}] dBm"
        else:
            # Fallback thresholds when transceiver range isn't reported
            if rx <= -22.0:
                data["optical_status"] = "CRITICAL"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is critically degraded (<= -22 dBm)"
            elif rx <= -17.0:
                data["optical_status"] = "WARNING"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is marginal (<= -17 dBm)"
            else:
                data["optical_status"] = "HEALTHY"
                data["optical_detail"] = f"Rx Power {rx:.2f} dBm is normal"
    else:
        data["optical_status"] = "NOT_APPLICABLE"
        data["optical_detail"] = "No optical transceiver power metrics detected"

    return data


# ---------------------------------------------------------------------------
# Parser: `display alarm active`
# ---------------------------------------------------------------------------
def parse_display_alarm_active(output: str) -> List[Dict[str, Any]]:
    """
    Parses active PTP, Clock, and Sync alarms on Huawei VRP.
    Detects alarms such as:
      - The ptp time offset sum is abnormal.
      - hwPtpTimeOffsetSumP2P, hwPtpAlarmThresholdOffsetSum
      - Clock Source Unlocked
      - PTP Clock Source Degraded
    """
    alarms = []
    if not output:
        return alarms

    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("----") or "Sequence" in line_clean:
            continue

        lower = line_clean.lower()
        if "no active alarm" in lower or "it will take a long time" in lower:
            continue

        # Check for PTP or Clock relevance
        is_ptp = "ptp" in lower or "clock" in lower or "sync" in lower or "offset" in lower

        offset_val = None
        threshold_val = None

        m_offset = re.search(r'hwPtpTimeOffsetSumP2P\s*=\s*([\-\d]+)', line_clean)
        if m_offset:
            try:
                offset_val = int(m_offset.group(1))
            except ValueError:
                pass

        m_thresh = re.search(r'hwPtpAlarmThresholdOffsetSum\s*=\s*([\-\d]+)', line_clean)
        if m_thresh:
            try:
                threshold_val = int(m_thresh.group(1))
            except ValueError:
                pass

        alarm_type = "GENERAL_ALARM"
        if "offset" in lower and ("abnormal" in lower or "exceed" in lower):
            alarm_type = "PTP_TIME_OFFSET_ABNORMAL"
        elif "clock source unlocked" in lower or ("source" in lower and "unlock" in lower):
            alarm_type = "CLOCK_SOURCE_UNLOCKED"
        elif "degraded" in lower:
            alarm_type = "PTP_SOURCE_DEGRADED"

        if is_ptp:
            alarms.append({
                "raw": line_clean,
                "alarm_type": alarm_type,
                "offset_val": offset_val,
                "threshold_val": threshold_val,
            })

    return alarms


# ---------------------------------------------------------------------------
# Parser: `display lldp neighbor brief` and `display lldp neighbor interface`
# ---------------------------------------------------------------------------
def parse_lldp_neighbor_brief(output: str, target_local_iface: str = "") -> List[Dict[str, str]]:
    """
    Parses `display lldp neighbor brief`.
    Matches columns: Local Intf, Neighbor Dev, Neighbor Intf, Exptime (sec)
    """
    neighbors = []
    if not output:
        return neighbors

    # Normalize target interface name for comparison (e.g. GigabitEthernet0/2/0 -> GE0/2/0)
    norm_target = _normalize_interface_name(target_local_iface).lower() if target_local_iface else ""

    lines = output.splitlines()
    in_table = False
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        if "Local Intf" in line_clean and "Neighbor Dev" in line_clean:
            in_table = True
            continue

        if in_table:
            parts = line_clean.split()
            if len(parts) >= 3:
                local_if = parts[0]
                neigh_dev = parts[1]
                neigh_if = parts[2]
                exptime = parts[3] if len(parts) > 3 else ""

                entry = {
                    "local_interface": local_if,
                    "neighbor_device": neigh_dev,
                    "neighbor_interface": neigh_if,
                    "exptime": exptime,
                }
                neighbors.append(entry)

    if norm_target and neighbors:
        # Sort so that exact matching local interface comes first
        def _match_score(item):
            norm_local = _normalize_interface_name(item["local_interface"]).lower()
            return 0 if norm_local == norm_target else 1
        neighbors.sort(key=_match_score)

    return neighbors


def parse_lldp_neighbor_detail(output: str) -> Dict[str, str]:
    """
    Parses `display lldp neighbor interface <iface>` for detailed TLVs.
    Captures: Management address, System name, Chassis ID, Port ID.
    """
    data = {
        "neighbor_ip": "",
        "system_name": "",
        "chassis_id": "",
        "port_id": "",
        "port_description": "",
    }
    if not output:
        return data

    for line in output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        m = re.search(r'Management\s+address\s*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line_clean, re.I)
        if m and not data["neighbor_ip"]:
            data["neighbor_ip"] = m.group(1)

        m = re.search(r'System\s+name\s*:\s*(\S+)', line_clean, re.I)
        if m and not data["system_name"]:
            data["system_name"] = m.group(1)

        m = re.search(r'Chassis\s+ID\s*:\s*([0-9a-fA-F\:\.\-]+)', line_clean, re.I)
        if m and not data["chassis_id"]:
            data["chassis_id"] = m.group(1)

        m = re.search(r'Port\s+ID\s*:\s*(\S+)', line_clean, re.I)
        if m and not data["port_id"]:
            data["port_id"] = m.group(1)

    return data


def _normalize_interface_name(name: str) -> str:
    """Shortens interface names to abbreviations for robust cross-matching."""
    if not name:
        return ""
    s = name.strip()
    replacements = [
        (r'^GigabitEthernet', 'GE'),
        (r'^XGigabitEthernet', 'XGE'),
        (r'^100GE', '100GE'),
        (r'^40GE', '40GE'),
        (r'^Eth-Trunk', 'Eth-Trunk'),
        (r'^Ethernet', 'Eth'),
    ]
    for pattern, rep in replacements:
        s = re.sub(pattern, rep, s, flags=re.I)
    return s


# ---------------------------------------------------------------------------
# Inventory Lookup & IP Resolution
# ---------------------------------------------------------------------------
def resolve_router_info(identifier: str, base_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Resolves a device by IP, Hostname, or Site Code across:
    1. Direct IPv4 validation
    2. Cached Zabbix DB (zabbix_router_db.json)
    3. Unified Sites CSV (unified_sites.csv)
    """
    if not identifier:
        return None

    raw = identifier.strip()
    base = base_dir or os.path.dirname(os.path.abspath(__file__))

    # 1. Direct IP address
    try:
        ipaddress.ip_address(raw)
        return {
            "name": raw,
            "host": raw,
            "site_code": "",
            "model": "Unknown (Direct IP)",
            "source": "Direct IP",
        }
    except ValueError:
        pass

    # 2. Search zabbix_router_db.json
    db_path = os.path.join(base, "zabbix_router_db.json")
    if os.path.isfile(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)
                routers = db_data.get("routers", [])
                for r in routers:
                    h_name = (r.get("host") or r.get("name") or "").strip()
                    h_ip = (r.get("ip") or "").strip()
                    if raw.lower() == h_name.lower() or raw.lower() in h_name.lower():
                        if h_ip:
                            return {
                                "name": h_name,
                                "host": h_ip,
                                "site_code": "",
                                "model": r.get("groups", [{}])[0].get("name", "") if r.get("groups") else "Huawei Router",
                                "source": "Zabbix DB",
                            }
        except Exception as e:
            logger.warning("Error searching zabbix_router_db.json: %s", e)

    # 3. Search unified_sites.csv
    unified_csv = os.path.join(base, "unified_sites.csv")
    if os.path.isfile(unified_csv):
        try:
            with open(unified_csv, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    norm = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                    s_code = norm.get("site_code") or norm.get("sitecode") or ""
                    ip = norm.get("ip") or ""
                    model = norm.get("model") or ""
                    ne_name = norm.get("ne_name") or norm.get("name") or s_code

                    if raw.lower() in (s_code.lower(), ne_name.lower(), ip.lower()):
                        if ip:
                            return {
                                "name": ne_name or s_code,
                                "host": ip,
                                "site_code": s_code,
                                "model": model or "Huawei NE",
                                "source": "Unified Sites CSV",
                            }
        except Exception as e:
            logger.warning("Error searching unified_sites.csv: %s", e)

    return None


def search_candidate_routers(keyword: str, base_dir: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Searches device inventory by keyword (Hostname, Site Code, or IP)
    and returns a list of candidate matching routers.
    """
    keyword_clean = (keyword or "").strip().lower()
    if not keyword_clean:
        return []

    base = base_dir or os.path.dirname(os.path.abspath(__file__))
    matches = []
    seen_ips = set()

    # 1. Direct IP match candidate
    try:
        ipaddress.ip_address(keyword_clean)
        matches.append({
            "name": keyword_clean,
            "host": keyword_clean,
            "site_code": "",
            "model": "Direct IP Entry",
            "source": "Manual",
        })
        seen_ips.add(keyword_clean)
    except ValueError:
        pass

    # 2. Check Zabbix DB
    db_path = os.path.join(base, "zabbix_router_db.json")
    if os.path.isfile(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)
                routers = db_data.get("routers", [])
                for r in routers:
                    h_name = (r.get("host") or r.get("name") or "").strip()
                    h_ip = (r.get("ip") or "").strip()
                    if not h_ip or h_ip in seen_ips:
                        continue

                    if keyword_clean in h_name.lower() or keyword_clean in h_ip.lower():
                        group_name = ""
                        if r.get("groups") and isinstance(r["groups"], list):
                            group_name = r["groups"][0].get("name", "")
                        matches.append({
                            "name": h_name,
                            "host": h_ip,
                            "site_code": "",
                            "model": group_name or "Huawei Router",
                            "source": "Zabbix Inventory",
                        })
                        seen_ips.add(h_ip)
                        if len(matches) >= limit:
                            return matches
        except Exception as e:
            logger.warning("Error reading Zabbix DB for candidates: %s", e)

    # 3. Check unified_sites.csv
    unified_csv = os.path.join(base, "unified_sites.csv")
    if os.path.isfile(unified_csv):
        try:
            with open(unified_csv, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    norm = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                    s_code = norm.get("site_code") or norm.get("sitecode") or ""
                    ip = norm.get("ip") or ""
                    model = norm.get("model") or ""
                    ne_name = norm.get("ne_name") or norm.get("name") or s_code

                    if not ip or ip in seen_ips:
                        continue

                    if (keyword_clean in s_code.lower() or
                        keyword_clean in ne_name.lower() or
                        keyword_clean in ip.lower()):
                        matches.append({
                            "name": ne_name or s_code,
                            "host": ip,
                            "site_code": s_code,
                            "model": model or "Huawei NE",
                            "source": "Unified Sites",
                        })
                        seen_ips.add(ip)
                        if len(matches) >= limit:
                            return matches
        except Exception as e:
            logger.warning("Error reading Unified Sites for candidates: %s", e)

    return matches


# ---------------------------------------------------------------------------
# Diagnostic Evaluation per Hop
# ---------------------------------------------------------------------------
def evaluate_hop_health(hop_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates PTP parameters, Clock Source, Optics, and Alarms on a single hop.
    Returns:
      - status: HEALTHY, WARNING, CRITICAL
      - kpis: dictionary of core metrics
      - findings: list of human-readable findings
      - is_gm_loss: boolean (Grandmaster / GPS loss of lock)
      - is_fiber_asymmetry_candidate: boolean
      - is_physical_defect: boolean
    """
    findings = []
    status = "HEALTHY"

    ptp = hop_data.get("ptp", {})
    clock = hop_data.get("clock_source", {})
    interface = hop_data.get("interface", {})
    alarms = hop_data.get("alarms", [])

    clock_class = ptp.get("clock_class")
    time_source = ptp.get("time_source", "")
    t2_t1 = ptp.get("realtime_t2_t1")
    ptp_state = ptp.get("ptp_state", "")

    is_gm_loss = False
    is_physical_defect = False
    is_fiber_asymmetry_candidate = False

    # 1. Physical Layer & Optical Checks
    if interface:
        phy_state = interface.get("physical_state", "")
        if phy_state and phy_state != "UP":
            status = "CRITICAL"
            is_physical_defect = True
            findings.append(f"Slave physical interface is {phy_state}")

        opt_status = interface.get("optical_status", "")
        if opt_status == "CRITICAL":
            status = "CRITICAL"
            is_physical_defect = True
            findings.append(interface.get("optical_detail", "Optical power critically degraded"))
        elif opt_status == "WARNING":
            if status != "CRITICAL":
                status = "WARNING"
            findings.append(interface.get("optical_detail", "Optical power warning"))

        crc = interface.get("crc_errors", 0)
        if crc > 0:
            if status != "CRITICAL":
                status = "WARNING"
            findings.append(f"Interface recorded {crc} CRC errors (possible cable/transceiver degradation)")

    # 2. Grandmaster / GPS Loss of Lock (Holdover Mode)
    # ITU-T G.8275.1: Class 6 = Locked to PRC/GNSS. Class 7 = Holdover.
    # Time Source: 0x20 = Atomic/GPS, 0xa0 = Internal oscillator.
    if clock_class == 7 or (clock_class and clock_class > 7 and clock_class <= 135):
        status = "CRITICAL"
        is_gm_loss = True
        findings.append(f"Grandmaster Clock Class is {clock_class} (Holdover Mode - GNSS loss of lock)")
    elif clock_class == 248 or (clock_class and clock_class > 135):
        status = "CRITICAL"
        findings.append(f"PTP Clock Class is {clock_class} (Free-Running / Unlocked)")

    if time_source in ("0xa0", "a0"):
        if clock_class == 7 or clock_class == 6:
            is_gm_loss = True
            status = "CRITICAL"
            findings.append("Time Source is 0xa0 (Internal Oscillator - Grandmaster reference disconnected)")

    # 3. Realtime (T2-T1) Offset Check
    if t2_t1 is not None:
        abs_t2_t1 = abs(t2_t1)
        if abs_t2_t1 > PTP_OFFSET_WARNING_MAX_NS:
            status = "CRITICAL"
            is_fiber_asymmetry_candidate = True
            findings.append(
                f"Realtime(T2-T1) is {t2_t1:.0f} ns (CRITICAL: exceeds {PTP_OFFSET_WARNING_MAX_NS:.0f} ns limit)"
            )
        elif abs_t2_t1 > PTP_OFFSET_HEALTHY_MAX_NS:
            if status != "CRITICAL":
                status = "WARNING"
            findings.append(
                f"Realtime(T2-T1) is {t2_t1:.0f} ns (WARNING: exceeds {PTP_OFFSET_HEALTHY_MAX_NS:.0f} ns optimal threshold)"
            )
        else:
            findings.append(f"Realtime(T2-T1) is healthy ({t2_t1:.0f} ns <= {PTP_OFFSET_HEALTHY_MAX_NS:.0f} ns)")

    # 4. Clock Source / SyncE State
    if clock:
        trace_state = clock.get("trace_source_state", "")
        freq_lock = clock.get("frequency_lock_success")
        if trace_state and "lock" not in trace_state:
            status = "CRITICAL"
            findings.append(f"System trace source state is '{trace_state}' (Not in lock mode)")
        if freq_lock is False:
            status = "CRITICAL"
            findings.append("System frequency lock is FALSE (SyncE unlocked)")

        for src in clock.get("sources", []):
            if src.get("referenced"):
                in_ssm = src.get("in_ssm", "")
                if in_ssm in ("dnu", "sec", "failed"):
                    status = "CRITICAL"
                    findings.append(f"Referenced clock source SSM quality is abnormal ({in_ssm.upper()})")

    # 5. Active Alarms
    for alm in alarms:
        findings.append(f"Active Alarm: {alm.get('raw')}")

    if not findings:
        findings.append("All PTP, SyncE, and optical metrics are within normal operational thresholds.")

    return {
        "status": status,
        "is_gm_loss": is_gm_loss,
        "is_physical_defect": is_physical_defect,
        "is_fiber_asymmetry_candidate": is_fiber_asymmetry_candidate,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Demarcation & Root Cause Analysis (RCA) Engine
# ---------------------------------------------------------------------------
def generate_demarcation_and_rca(hop_chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes the entire hop chain from Hop 0 (Target) through Hop N (Root)
    to establish root cause, responsible team, actionable CLI fixes,
    and a copy-pasteable handover ticket.
    """
    if not hop_chain:
        return {
            "overall_status": "UNKNOWN",
            "root_cause": "No diagnostic hops recorded.",
            "responsible_team": "Unknown",
            "action_items": [],
            "handover_ticket": "",
        }

    target_hop = hop_chain[0]
    target_name = target_hop.get("name", "Target")
    target_eval = target_hop.get("evaluation", {})

    overall_status = "HEALTHY"
    for h in hop_chain:
        h_st = h.get("evaluation", {}).get("status", "HEALTHY")
        if h_st == "CRITICAL":
            overall_status = "CRITICAL"
            break
        elif h_st == "WARNING" and overall_status != "CRITICAL":
            overall_status = "WARNING"

    # Case 1: Physical Defect on Hop 0 or Upstream
    if target_eval.get("is_physical_defect"):
        slave_if = target_hop.get("ptp", {}).get("receive_number", "Slave Port")
        opt_det = target_hop.get("interface", {}).get("optical_detail", "Optical signal degraded")
        return {
            "overall_status": "CRITICAL",
            "root_cause": (
                f"Layer-1 Physical / Optical Defect on {target_name} ({slave_if}). {opt_det}."
            ),
            "responsible_team": "IP Team (Transmission / Fiber Maintenance)",
            "action_items": [
                f"Inspect fiber patch cord and clean optical LC connectors on {target_name} ({slave_if}).",
                "Check SFP/SFP+ optical transceiver Tx/Rx power using physical optical power meter.",
                "Measure fiber link attenuation (OTDR test) between target and upstream parent.",
                f"Replace optical transceiver module on {slave_if} if Rx power remains out of spec.",
            ],
            "handover_ticket": _format_handover_ticket(
                target_name=target_name,
                alarm_summary="PTP Time Offset Abnormal / Physical Link Degraded",
                root_cause=f"Degraded optical power / CRC errors on slave interface {slave_if}. {opt_det}",
                team="IP Team (Transmission / Fiber Line Check)",
                recommended_action=f"Perform fiber optical cleaning, check patch cords on {target_name} port {slave_if}.",
                hop_chain=hop_chain,
            ),
        }

    # Case 2: Grandmaster / GNSS Antenna Loss of Lock (Holdover Mode)
    gm_loss_detected = any(h.get("evaluation", {}).get("is_gm_loss") for h in hop_chain)
    if gm_loss_detected:
        root_hop = hop_chain[-1]
        root_name = root_hop.get("name", "Grandmaster")
        return {
            "overall_status": "CRITICAL",
            "root_cause": (
                f"Grandmaster / Primary Reference Clock Loss of Lock. The timing tree entered Holdover Mode "
                f"(Clock Class 7 / Time Source 0xa0 detected at {root_name})."
            ),
            "responsible_team": "Sync & Power Team (Timing Infrastructure)",
            "action_items": [
                f"Check GNSS / GPS antenna status and satellite lock at central timing site ({root_name}).",
                "Inspect BITS clock reference and atomic clock oscillator health.",
                "Verify antenna lightning surge protector and RF coaxial cabling for attenuation/water ingress.",
                "Verify BITS 2MHz / 2Mbit/s external clock cable connectivity to router BITS port.",
            ],
            "handover_ticket": _format_handover_ticket(
                target_name=target_name,
                alarm_summary="PTP Clock Source Unlocked / Grandmaster Holdover",
                root_cause=f"Primary Grandmaster / BITS timing reference at {root_name} lost satellite/PRC lock (Clock Class 7).",
                team="Sync & Power Team",
                recommended_action=f"Dispatch Sync team to verify GNSS antenna tracking and BITS clock outputs at {root_name}.",
                hop_chain=hop_chain,
            ),
        }

    # Case 3: Fiber Delay Asymmetry (Upstream is healthy, Hop 0 has high offset)
    if len(hop_chain) >= 2:
        parent_hop = hop_chain[1]
        parent_name = parent_hop.get("name", "Parent Node")
        parent_eval = parent_hop.get("evaluation", {})
        parent_t2_t1 = parent_hop.get("ptp", {}).get("realtime_t2_t1")

        target_t2_t1 = target_hop.get("ptp", {}).get("realtime_t2_t1")
        slave_if = target_hop.get("ptp", {}).get("receive_number", "Slave Port")

        # Parent is in-sync (T2-T1 <= 500ns, Class 6) but target has large T2-T1 offset
        parent_is_clean = (
            parent_eval.get("status") in ("HEALTHY", "WARNING") and
            parent_t2_t1 is not None and abs(parent_t2_t1) <= PTP_OFFSET_WARNING_MAX_NS
        )

        if parent_is_clean and target_t2_t1 is not None and abs(target_t2_t1) > PTP_OFFSET_WARNING_MAX_NS:
            asymmetry_delta = target_t2_t1 - (parent_t2_t1 or 0)
            return {
                "overall_status": "CRITICAL",
                "root_cause": (
                    f"Fiber Propagation Delay Asymmetry between {target_name} ({slave_if}) and upstream parent {parent_name}. "
                    f"Upstream {parent_name} is In-Sync (T2-T1: {parent_t2_t1:.0f} ns), while {target_name} has high offset "
                    f"(T2-T1: {target_t2_t1:.0f} ns, jump of ~{asymmetry_delta:.0f} ns). Optics and SyncE are clean."
                ),
                "responsible_team": "IP Team (Network Operations / Transmission)",
                "action_items": [
                    f"Verify Tx and Rx fiber paths between {target_name} and {parent_name} are identical in route and length.",
                    f"If fibers follow different physical spans or dispersion-compensating fiber, calibrate delay asymmetry on {target_name}:",
                    f"  [CLI Fix]: system-view",
                    f"  [CLI Fix]: interface {slave_if}",
                    f"  [CLI Fix]: ptp delay-asymmetry <offset-ns>",
                    f"  [CLI Fix]: commit",
                ],
                "handover_ticket": _format_handover_ticket(
                    target_name=target_name,
                    alarm_summary="PTP Time Offset Abnormal (Fiber Delay Asymmetry)",
                    root_cause=(
                        f"Significant propagation delay asymmetry between {target_name} ({slave_if}) and parent {parent_name}. "
                        f"Upstream parent has normal T2-T1 ({parent_t2_t1:.0f} ns), but target measured {target_t2_t1:.0f} ns."
                    ),
                    team="IP Team",
                    recommended_action=(
                        f"Audit fiber span routing between {target_name} and {parent_name}. "
                        f"Configure 'ptp delay-asymmetry' on interface {slave_if}."
                    ),
                    hop_chain=hop_chain,
                ),
            }

    # Case 4: Upstream Clock Tree Degradation (Both Hop 0 and Hop 1+ are abnormal)
    if overall_status == "CRITICAL":
        faulty_hop = next((h for h in reversed(hop_chain) if h.get("evaluation", {}).get("status") == "CRITICAL"), target_hop)
        faulty_name = faulty_hop.get("name", "Upstream Node")
        return {
            "overall_status": "CRITICAL",
            "root_cause": (
                f"Clock Distribution Degradation originating at upstream node {faulty_name}. "
                f"Sync errors are propagating downstream through the clock tree to {target_name}."
            ),
            "responsible_team": "IP Team & Sync Team (Clock Tree Audit)",
            "action_items": [
                f"Investigate upstream clock source health on {faulty_name}.",
                "Inspect intermediate microwave/DWDM optical transponders carrying PTP timestamps.",
                "Verify ITU-T G.8275.1 boundary clock (T-BC) configurations across all intermediate hops.",
            ],
            "handover_ticket": _format_handover_ticket(
                target_name=target_name,
                alarm_summary="PTP Downstream Error Propagation",
                root_cause=f"Sync failure originates upstream at node {faulty_name} and cascades down the clock tree.",
                team="IP Team / Sync Team",
                recommended_action=f"Troubleshoot clock distribution starting at upstream node {faulty_name}.",
                hop_chain=hop_chain,
            ),
        }

    # Default: Healthy
    return {
        "overall_status": overall_status,
        "root_cause": "All evaluated nodes in the PTP distribution chain are healthy and in-sync.",
        "responsible_team": "None (System Operational)",
        "action_items": [
            "No corrective action required. PTP offset, SyncE SSM, and optical power levels are within ITU-T G.8275.1 standards."
        ],
        "handover_ticket": "System Normal: PTP time synchronization is fully locked and operational.",
    }


def _format_handover_ticket(
    target_name: str,
    alarm_summary: str,
    root_cause: str,
    team: str,
    recommended_action: str,
    hop_chain: List[Dict[str, Any]],
) -> str:
    """Formats a concise, copy-pasteable technical handover ticket."""
    chain_str = " -> ".join([h.get("name", "Node") for h in hop_chain])
    target_hop = hop_chain[0] if hop_chain else {}
    ptp = target_hop.get("ptp", {})

    ticket = (
        "===============================================================\n"
        f"NOC PTP & SYNC TROUBLESHOOTING TICKET - {target_name}\n"
        "===============================================================\n"
        f"Assigned Team      : {team}\n"
        f"Priority           : HIGH / CRITICAL\n"
        f"Alarm Type         : {alarm_summary}\n"
        f"Target Device      : {target_name} ({target_hop.get('host', 'N/A')})\n"
        f"Slave Interface    : {ptp.get('receive_number', 'N/A')}\n"
        f"PTP Offset (T2-T1) : {ptp.get('realtime_t2_t1', 'N/A')} ns\n"
        f"Clock Class        : {ptp.get('clock_class', 'N/A')}\n"
        f"Clock Tree Path    : {chain_str}\n"
        "---------------------------------------------------------------\n"
        f"ROOT CAUSE ANALYSIS:\n{root_cause}\n"
        "---------------------------------------------------------------\n"
        f"RECOMMENDED ACTION:\n{recommended_action}\n"
        "==============================================================="
    )
    return ticket


# ---------------------------------------------------------------------------
# Upstream Traceback SSH Diagnostic Engine
# ---------------------------------------------------------------------------
def run_ptp_troubleshoot_traceback(
    target_identifier: str,
    username: str,
    password: str,
    log_callback: Optional[Callable[[str, str], None]] = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
) -> Dict[str, Any]:
    """
    Executes automated live PTP diagnostic and recursive upstream traceback:
    Hop 0 (Target) -> Hop 1 (Parent) -> ... -> Root (GM / BITS)
    Connects to Huawei VRP routers via SSH using authenticated engineer credentials.
    """
    import netmiko

    def _log(msg: str, level: str = "info"):
        if log_callback:
            log_callback(msg, level)
        logger.info("[%s] %s", level.upper(), msg)

    _log(f"Initiating PTP automated troubleshooting for target '{target_identifier}' ...", "highlight")

    # Resolve initial target
    target_info = resolve_router_info(target_identifier)
    if not target_info:
        target_info = {
            "name": target_identifier,
            "host": target_identifier,
            "site_code": "",
            "model": "Generic Huawei NE",
            "source": "Direct Input",
        }

    hop_chain: List[Dict[str, Any]] = []
    visited_hosts = set()
    visited_clock_ids = set()

    current_node = target_info
    hop_index = 0

    while hop_index < max_hops:
        current_name = current_node.get("name", "Unknown")
        current_host = current_node.get("host", "").strip()

        if not current_host:
            _log(f"Hop {hop_index}: Missing IP address for node '{current_name}' — terminating traceback.", "warn")
            break

        if current_host in visited_hosts:
            _log(f"Hop {hop_index}: Loop detected at host {current_host} ({current_name}) — terminating traceback.", "warn")
            break

        visited_hosts.add(current_host)

        _log(f"Hop {hop_index}: Connecting to {current_name} ({current_host}) via SSH ...", "info")

        conn = None
        hop_record: Dict[str, Any] = {
            "hop": hop_index,
            "name": current_name,
            "host": current_host,
            "site_code": current_node.get("site_code", ""),
            "model": current_node.get("model", ""),
            "ptp": {},
            "clock_source": {},
            "interface": {},
            "alarms": [],
            "lldp": {},
            "evaluation": {},
            "error": None,
        }

        try:
            conn = netmiko.ConnectHandler(
                device_type="huawei_vrp",
                host=current_host,
                username=username,
                password=password,
                timeout=connect_timeout,
            )
            _log(f"Hop {hop_index}: Connected successfully to {current_name}", "success")

            try:
                conn.send_command("screen-length 0 temporary", read_timeout=command_timeout)
            except Exception:
                pass

            # 1. `display ptp all`
            _log(f"Hop {hop_index}: Fetching PTP operational status ('display ptp all') ...", "info")
            ptp_raw = conn.send_command("display ptp all", read_timeout=command_timeout)
            ptp_data = parse_display_ptp_all(ptp_raw)
            hop_record["ptp"] = ptp_data

            local_cid = ptp_data.get("local_clock_id")
            if local_cid:
                if local_cid in visited_clock_ids:
                    _log(f"Hop {hop_index}: Loop detected on Clock ID '{local_cid}' — terminating traceback.", "warn")
                    hop_chain.append(hop_record)
                    break
                visited_clock_ids.add(local_cid)

            slave_interface = ptp_data.get("receive_number") or ""
            _log(
                f"Hop {hop_index}: Device Type={ptp_data.get('device_type')}, Clock Class={ptp_data.get('clock_class')}, "
                f"Realtime(T2-T1)={ptp_data.get('realtime_t2_t1')} ns, Slave Interface={slave_interface or 'None (Root/GM)'}",
                "info"
            )

            # 2. `display interface <slave-interface>` & Optical metrics
            if slave_interface:
                _log(f"Hop {hop_index}: Checking slave interface health ('display interface {slave_interface}') ...", "info")
                iface_raw = conn.send_command(f"display interface {slave_interface}", read_timeout=command_timeout)
                iface_data = parse_display_interface(iface_raw)
                hop_record["interface"] = iface_data

                if iface_data.get("rx_power_dbm") is not None:
                    _log(
                        f"Hop {hop_index}: Optical status={iface_data.get('optical_status')} "
                        f"(Rx={iface_data.get('rx_power_dbm'):.2f} dBm, Tx={iface_data.get('tx_power_dbm', 0.0):.2f} dBm, CRC={iface_data.get('crc_errors')})",
                        "info"
                    )

            # 3. `display clock source`
            _log(f"Hop {hop_index}: Checking system clock PLL & SSM ('display clock source') ...", "info")
            clock_raw = conn.send_command("display clock source", read_timeout=command_timeout)
            clock_data = parse_display_clock_source(clock_raw)
            hop_record["clock_source"] = clock_data

            # 4. `display alarm active`
            _log(f"Hop {hop_index}: Checking active sync alarms ...", "info")
            alarm_raw = conn.send_command("display alarm active | include PTP", read_timeout=command_timeout)
            alarm_data = parse_display_alarm_active(alarm_raw)
            hop_record["alarms"] = alarm_data

            # 5. LLDP neighbor discovery for Upstream Parent
            parent_dev_name = ""
            parent_dev_ip = ""
            if slave_interface:
                _log(f"Hop {hop_index}: Querying LLDP neighbor on slave interface {slave_interface} ...", "info")
                lldp_raw = conn.send_command("display lldp neighbor brief", read_timeout=command_timeout)
                neighbors = parse_lldp_neighbor_brief(lldp_raw, target_local_iface=slave_interface)

                if neighbors:
                    primary_neigh = neighbors[0]
                    parent_dev_name = primary_neigh.get("neighbor_device", "")
                    hop_record["lldp"] = primary_neigh
                    _log(f"Hop {hop_index}: Detected upstream neighbor via LLDP: {parent_dev_name} ({primary_neigh.get('neighbor_interface')})", "info")

                    # Try detailed LLDP to get management IP
                    try:
                        lldp_det_raw = conn.send_command(f"display lldp neighbor interface {slave_interface}", read_timeout=command_timeout)
                        det = parse_lldp_neighbor_detail(lldp_det_raw)
                        if det.get("neighbor_ip"):
                            parent_dev_ip = det["neighbor_ip"]
                            hop_record["lldp"]["neighbor_ip"] = parent_dev_ip
                    except Exception:
                        pass

            # Evaluate hop health
            evaluation = evaluate_hop_health(hop_record)
            hop_record["evaluation"] = evaluation
            _log(f"Hop {hop_index} Evaluation: Status={evaluation.get('status')}", "highlight" if evaluation.get('status') != "HEALTHY" else "success")

            hop_chain.append(hop_record)

            # Stopping condition: Reached Root GM or no slave interface
            step_removed = ptp_data.get("step_removed")
            if not slave_interface or step_removed == 1 or (step_removed == 0):
                _log(f"Hop {hop_index}: Reached clock distribution root / Grandmaster ({current_name})", "success")
                break

            # Resolve next upstream node
            next_node = None
            if parent_dev_ip:
                next_node = resolve_router_info(parent_dev_ip) or {
                    "name": parent_dev_name or parent_dev_ip,
                    "host": parent_dev_ip,
                    "site_code": "",
                    "model": "Huawei Router",
                }
            elif parent_dev_name:
                resolved = resolve_router_info(parent_dev_name)
                if resolved and resolved.get("host"):
                    next_node = resolved
                else:
                    _log(f"Hop {hop_index}: Could not resolve management IP for upstream neighbor '{parent_dev_name}' — ending trace.", "warn")
                    break
            else:
                _log(f"Hop {hop_index}: No upstream LLDP neighbor or parent IP identified — ending trace.", "warn")
                break

            current_node = next_node
            hop_index += 1

        except Exception as exc:
            err_msg = str(exc)
            _log(f"Hop {hop_index}: Live SSH connection failed on {current_name} ({current_host}): {err_msg}", "warn")

            hop_record["error"] = err_msg
            hop_record["evaluation"] = {
                "status": "CRITICAL",
                "findings": [f"SSH Diagnostic Error: {err_msg}"],
                "is_gm_loss": False,
                "is_physical_defect": False,
                "is_fiber_asymmetry_candidate": False,
            }
            hop_chain.append(hop_record)
            break
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    _log("Generating Root Cause Analysis (RCA) and Team Demarcation ...", "info")
    demarcation = generate_demarcation_and_rca(hop_chain)

    _log(f"Troubleshooting Complete! Result: {demarcation.get('overall_status')} -> {demarcation.get('responsible_team')}", "highlight")

    return {
        "target": target_info,
        "hop_count": len(hop_chain),
        "hop_chain": hop_chain,
        "demarcation": demarcation,
    }

