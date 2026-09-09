"""
Site ARP & MAC Lookup Service
=============================
Modular service to cross-reference:
1. Site_Code in unified_sites.csv -> IP, model
2. IP in arp_mac.csv (ARP_IP)     -> ARP_MAC
3. ARP_MAC in arp_mac.csv         -> All rows sharing that same MAC

Outputs combined details:
  Site_Code, IP, Model, NE, NE_IP, ARP_MAC, Vlan, VRF, ARP_Interface, MAC_Port
"""

import os
import re
import csv
import glob
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from netmiko import (
    ConnectHandler,
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)

logger = logging.getLogger(__name__)

# Base search paths for CSV files
DEFAULT_DIRS = [
    os.getcwd(),
    os.path.dirname(os.path.abspath(__file__)),
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
]


def normalize_mac(mac: Optional[str]) -> str:
    """Normalize MAC address for reliable matching (lowercase alphanumeric only)."""
    if not mac:
        return ""
    return re.sub(r"[^0-9a-fA-F]", "", str(mac)).lower()


def resolve_file_path(filename: str, env_var: Optional[str] = None) -> Optional[str]:
    """Find the full path of a target CSV file across common project locations."""
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val and os.path.isfile(env_val):
            return os.path.abspath(env_val)

    for base_dir in DEFAULT_DIRS:
        direct_path = os.path.join(base_dir, filename)
        if os.path.isfile(direct_path):
            return os.path.abspath(direct_path)

        # Fallback for timestamped files (e.g. arp_mac_*.csv)
        if "*" in filename or filename.startswith("arp_mac"):
            pattern = os.path.join(base_dir, "arp_mac*.csv")
            matches = glob.glob(pattern)
            if matches:
                # Return the latest file by modification time
                matches.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(matches[0])

    return None


def read_unified_sites(file_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Read unified_sites.csv and return standardized rows."""
    target_path = file_path or resolve_file_path("unified_sites.csv", "UNIFIED_SITES_CSV")
    if not target_path or not os.path.isfile(target_path):
        logger.warning("unified_sites.csv not found (searched: %s)", target_path)
        return []

    results: List[Dict[str, str]] = []
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                norm_row = {
                    (k.strip().lower() if k else ""): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }
                site_code = norm_row.get("site_code") or norm_row.get("sitecode") or ""
                ip = norm_row.get("ip") or ""
                model = norm_row.get("model") or ""

                if site_code:
                    results.append({
                        "site_code": site_code,
                        "ip": ip,
                        "model": model,
                    })
    except Exception as exc:
        logger.error("Error reading unified_sites.csv from %s: %s", target_path, exc)
    return results


def read_arp_mac_records(file_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Read arp_mac.csv and return standardized rows."""
    target_path = file_path or resolve_file_path("arp_mac.csv", "ARP_MAC_CSV")
    if not target_path or not os.path.isfile(target_path):
        logger.warning("arp_mac.csv not found (searched: %s)", target_path)
        return []

    results: List[Dict[str, str]] = []
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                norm_row = {
                    (k.strip().lower() if k else ""): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }
                ne = norm_row.get("ne") or norm_row.get("ne_name") or ""
                ne_ip = norm_row.get("ne_ip") or norm_row.get("neip") or ""
                arp_ip = norm_row.get("arp_ip") or norm_row.get("arpip") or ""
                arp_mac = norm_row.get("arp_mac") or norm_row.get("arpmac") or ""
                vlan = norm_row.get("vlan") or ""
                vrf = norm_row.get("vrf") or ""
                arp_interface = (
                    norm_row.get("arp_interface")
                    or norm_row.get("interface")
                    or norm_row.get("arp_intf")
                    or ""
                )
                mac_port = (
                    norm_row.get("mac_port")
                    or norm_row.get("port")
                    or norm_row.get("macport")
                    or ""
                )
                collected_at = norm_row.get("collected_at") or ""

                results.append({
                    "ne": ne,
                    "ne_ip": ne_ip,
                    "arp_ip": arp_ip,
                    "arp_mac": arp_mac,
                    "vlan": vlan,
                    "vrf": vrf,
                    "arp_interface": arp_interface,
                    "mac_port": mac_port,
                    "collected_at": collected_at,
                })
    except Exception as exc:
        logger.error("Error reading arp_mac.csv from %s: %s", target_path, exc)
    return results


def lookup_site_arp_mac_details(
    site_code: str,
    unified_sites_path: Optional[str] = None,
    arp_mac_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main lookup pipeline:
    1. Search Site_Code in unified_sites.csv
    2. Search matching IP in arp_mac.csv (ARP_IP) -> get ARP_MAC
    3. Query all rows matching that same ARP_MAC
    4. Return merged records with requested fields.
    """
    cleaned_code = site_code.strip()
    if not cleaned_code:
        return {
            "success": False,
            "error": "Site code is required.",
            "results": [],
            "count": 0,
        }

    unified_resolved = unified_sites_path or resolve_file_path("unified_sites.csv", "UNIFIED_SITES_CSV")
    arp_resolved = arp_mac_path or resolve_file_path("arp_mac.csv", "ARP_MAC_CSV")

    if not unified_resolved or not os.path.isfile(unified_resolved):
        return {
            "success": False,
            "error": "unified_sites.csv file not found.",
            "results": [],
            "count": 0,
        }

    if not arp_resolved or not os.path.isfile(arp_resolved):
        return {
            "success": False,
            "error": "arp_mac.csv file not found.",
            "results": [],
            "count": 0,
        }

    # Step 1: Search site_code in unified_sites.csv (case-insensitive)
    all_sites = read_unified_sites(unified_resolved)
    code_lower = cleaned_code.lower()
    matched_sites = [
        s for s in all_sites if s["site_code"].strip().lower() == code_lower
    ]

    # Fallback to loose match if exact not found
    if not matched_sites:
        matched_sites = [
            s for s in all_sites if code_lower in s["site_code"].strip().lower()
        ]

    if not matched_sites:
        return {
            "success": False,
            "error": f"Site Code '{cleaned_code}' not found in unified_sites.csv.",
            "results": [],
            "count": 0,
            "unified_path": unified_resolved,
            "arp_path": arp_resolved,
        }

    # Step 2: Read ARP/MAC table and find matching MAC(s) for site IP(s)
    all_arp_records = read_arp_mac_records(arp_resolved)
    target_ips = {s["ip"].strip() for s in matched_sites if s["ip"].strip()}

    if not target_ips:
        return {
            "success": False,
            "error": f"Site Code '{cleaned_code}' has no IP address defined in unified_sites.csv.",
            "sites": matched_sites,
            "results": [],
            "count": 0,
        }

    # Find ARP_MAC for target IPs
    matched_macs: Set[str] = set()
    ip_to_site: Dict[str, Dict[str, str]] = {s["ip"].strip(): s for s in matched_sites}

    for record in all_arp_records:
        rec_ip = record["arp_ip"].strip()
        rec_mac = record["arp_mac"].strip()
        if rec_ip in target_ips and rec_mac:
            matched_macs.add(normalize_mac(rec_mac))

    if not matched_macs:
        ip_str = ", ".join(sorted(target_ips))
        return {
            "success": False,
            "error": f"No ARP entry found in arp_mac.csv for IP(s): {ip_str} (Site: {cleaned_code}).",
            "sites": matched_sites,
            "results": [],
            "count": 0,
        }

    # Step 3: Find all details of the same MAC(s) in arp_mac.csv
    combined_rows: List[Dict[str, Any]] = []

    # Map each normalized MAC back to primary site info
    primary_site = matched_sites[0]

    for record in all_arp_records:
        rec_mac_norm = normalize_mac(record["arp_mac"])
        if rec_mac_norm in matched_macs:
            # Check if this row's IP matches a specific site record, else use primary
            site_info = ip_to_site.get(record["arp_ip"].strip(), primary_site)

            combined_rows.append({
                "Site_Code": site_info["site_code"],
                "VRF": record["vrf"],
                "VRF_IP": site_info["ip"],
                "Site_Model": site_info["model"],
                "IP": site_info["ip"],
                "Model": site_info["model"],
                "NE": record["ne"],
                "NE_IP": record["ne_ip"],
                "ARP_MAC": record["arp_mac"],
                "Vlan": record["vlan"],
                "ARP_Interface": record["arp_interface"],
                "MAC_Port": record["mac_port"],
                "Link": record["mac_port"],
                "collected_at": record.get("collected_at", ""),
            })

    return {
        "success": True,
        "site_code": cleaned_code,
        "count": len(combined_rows),
        "results": combined_rows,
        "sites": matched_sites,
        "macs": list(matched_macs),
        "unified_path": unified_resolved,
        "arp_path": arp_resolved,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Collector Engine (from collector.py)
# ──────────────────────────────────────────────────────────────────────────────

CSV_HEADERS = [
    "ne_name", "ne_ip", "arp_ip", "arp_mac",
    "vlan", "vrf", "arp_interface", "mac_port", "collected_at",
]

TARGET_NE_PREFIXES = ("IL", "BR", "BA", "BC")

NE_TYPE_MAP = {
    "ne20e":   "huawei",
    "ne40e":   "huawei",
    "ne8000":  "huawei",
    "ce6800":  "huawei",
    "ce12800": "huawei",
    "s5700":   "huawei",
    "s6700":   "huawei",
    "s12700":  "huawei",
}

ARP_LINE_RE = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+"
    r"(\d*)\s+"
    r"([A-Z]\s*-\d*)\s+"
    r"(\S+)"
    r"(?:\s+(\S+))?"
)
ARP_VLAN_CONT_RE = re.compile(r"^\s{20,}(\d+)\s*/")
MAC_START_RE = re.compile(
    r"^([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+(\d+)"
)
MAC_END_RE = re.compile(
    r"(\S+)\s+(dynamic|static|blackhole)\s*(?:\S*/-\s*)?$"
)


def resolve_device_type(ne_type: str) -> str:
    """Map a free-text NE type to a netmiko device_type string."""
    if not ne_type:
        return "huawei"
    key = ne_type.strip().lower()
    for prefix, dev_type in NE_TYPE_MAP.items():
        if key.startswith(prefix):
            return dev_type
    return "huawei"


def parse_arp(output: str) -> List[Dict[str, str]]:
    """Return a list of ARP entry dicts from raw command output."""
    entries: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith(("IP ADDRESS", "----", "display arp", "Total", "  VLAN/CEVLAN")):
            continue

        m = ARP_LINE_RE.match(line)
        if m:
            if current is not None:
                entries.append(current)
            current = {
                "arp_ip":    m.group(1),
                "arp_mac":   m.group(2).lower(),
                "interface": m.group(5),
                "vrf":       m.group(6) or "",
                "vlan":      "",
            }
            continue

        v = ARP_VLAN_CONT_RE.match(line)
        if v and current is not None:
            current["vlan"] = v.group(1)
            continue

    if current is not None:
        entries.append(current)

    return entries


def _extract_vlan_from_interface(iface: str) -> str:
    """Extract VLAN from interface name (Vlanif1325 → 1325, Eth-Trunk33.3226 → 3226)."""
    m = re.search(r"[Vv]lanif(\d+)", iface)
    if m:
        return m.group(1)
    m = re.search(r"\.(\d+)$", iface)
    if m:
        return m.group(1)
    return ""


def parse_mac_table(output: str) -> Dict[str, List[Dict[str, str]]]:
    """Parse MAC-address table output."""
    mac_map: Dict[str, List[Dict[str, str]]] = {}

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        start = MAC_START_RE.match(line)
        if not start:
            continue
        end = MAC_END_RE.search(line)
        if not end:
            continue

        mac = start.group(1).lower()
        vlan = start.group(2)
        port = end.group(1)

        mac_map.setdefault(mac, []).append({"vlan": vlan, "port": port})

    return mac_map


def enrich_from_mac_table(arp_entry: Dict[str, str], mac_table: Dict[str, List[Dict[str, str]]]) -> None:
    """Enrich VLAN and MAC_Port fields from MAC table."""
    if not arp_entry.get("vlan"):
        vlan = _extract_vlan_from_interface(arp_entry.get("interface", ""))
        if vlan:
            arp_entry["vlan"] = vlan
        else:
            mac = arp_entry.get("arp_mac", "")
            if mac in mac_table:
                arp_entry["vlan"] = mac_table[mac][0]["vlan"]

    mac = arp_entry.get("arp_mac", "")
    if mac in mac_table:
        arp_entry["mac_port"] = mac_table[mac][0]["port"]
    else:
        arp_entry["mac_port"] = ""


def collect_router_arp_mac(
    ne_name: str,
    ip: str,
    ne_type: str,
    username: str,
    password: str,
    timeout: int = 20,
    cmd_timeout: int = 60,
    log_cb=None,
) -> List[Dict[str, str]]:
    """Connect to router via SSH, run display arp and mac-address, parse, return flat rows."""
    def _log(msg: str):
        logger.info("[%s] %s", ne_name, msg)
        if log_cb:
            log_cb(f"[{ne_name}] {msg}")

    device_type = resolve_device_type(ne_type)
    conn_params = {
        "device_type": device_type,
        "host":        ip,
        "username":    username,
        "password":    password,
        "timeout":     timeout,
        "session_timeout": timeout,
        "auth_timeout":    timeout,
    }

    rows: List[Dict[str, str]] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = None

    try:
        _log(f"Connecting to {ip} ({device_type})...")
        conn = ConnectHandler(**conn_params)
        _log("Connected. Sending 'display arp all | no-more'...")

        arp_raw = conn.send_command("display arp all | no-more", read_timeout=cmd_timeout)
        arp_entries = parse_arp(arp_raw)
        _log(f"Parsed {len(arp_entries)} ARP entries.")

        _log("Sending 'display mac-address | no-more'...")
        mac_raw = conn.send_command("display mac-address | no-more", read_timeout=cmd_timeout)
        mac_table = parse_mac_table(mac_raw)
        _log(f"Parsed {len(mac_table)} MAC table entries.")

        for entry in arp_entries:
            enrich_from_mac_table(entry, mac_table)
            rows.append({
                "ne_name":        ne_name,
                "ne_ip":          ip,
                "arp_ip":         entry["arp_ip"],
                "arp_mac":        entry["arp_mac"],
                "vlan":           entry["vlan"],
                "vrf":            entry["vrf"],
                "arp_interface":  entry["interface"],
                "mac_port":       entry["mac_port"],
                "collected_at":   now_str,
            })
        _log(f"Collection finished: {len(rows)} entries gathered.")

    except NetmikoAuthenticationException:
        _log("Authentication failed!")
    except NetmikoTimeoutException:
        _log("Connection timed out!")
    except Exception as exc:
        _log(f"Error: {exc}")
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass

    return rows


# ──────────────────────────────────────────────────────────────────────────────
# NE CSV File Parsing & Filtering (IL, BR, BA, BC)
# ──────────────────────────────────────────────────────────────────────────────

def parse_ne_csv_content(content_bytes_or_str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], int]:
    """
    Parse uploaded NE info CSV content.
    Filters NEs starting with IL, BR, BA, or BC (case-insensitive).
    Returns (matched_routers, skipped_routers, total_raw_count).
    """
    if isinstance(content_bytes_or_str, bytes):
        try:
            text = content_bytes_or_str.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content_bytes_or_str.decode("latin-1")
    else:
        text = str(content_bytes_or_str)

    lines = text.splitlines()

    def _clean(line: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", line).strip()

    header_idx = -1
    for i, line in enumerate(lines):
        cl = _clean(line).lower()
        if "ne name" in cl or cl.startswith("name,") or cl.startswith("ne,") or "router" in cl:
            header_idx = i
            break

    if header_idx == -1:
        header_idx = 0

    cleaned = [_clean(l) for l in lines]
    reader = csv.DictReader(cleaned[header_idx:])

    matched: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    total = 0

    for row in reader:
        norm = {
            (k.strip().lower() if k else ""): (v.strip() if v else "")
            for k, v in row.items()
        }
        ne_name = (
            norm.get("ne name") or norm.get("ne_name") or norm.get("name") or norm.get("ne") or ""
        )
        ne_ip = (
            norm.get("ne ip address") or norm.get("ne_ip") or norm.get("ip") or norm.get("ip address") or ""
        )
        ne_type = (
            norm.get("ne type (mpu type)") or norm.get("ne type") or norm.get("ne_type") or norm.get("model") or ""
        )

        if not ne_name or not ne_ip:
            continue

        total += 1
        item = {"name": ne_name, "ip": ne_ip, "ne_type": ne_type}
        if ne_name.upper().startswith(TARGET_NE_PREFIXES):
            matched.append(item)
        else:
            skipped.append(item)

    return matched, skipped, total


def get_target_arp_mac_csv_path() -> str:
    """Resolve target path for arp_mac.csv."""
    existing = resolve_file_path("arp_mac.csv", "ARP_MAC_CSV")
    if existing:
        return existing
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "arp_mac.csv")


def save_or_update_arp_mac_csv(
    new_rows: List[Dict[str, str]],
    scanned_ne_names: Set[str],
    target_path: Optional[str] = None,
) -> str:
    """
    Create or update arp_mac.csv.
    Preserves rows from NEs not included in this scan, replaces rows for scanned NEs.
    Normalizes field names from existing files regardless of header case/alias.
    """
    target = target_path or get_target_arp_mac_csv_path()
    existing_rows: List[Dict[str, str]] = []
    scanned_upper = {n.upper().strip() for n in scanned_ne_names}

    if os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for raw_row in reader:
                    norm = {
                        (re.sub(r"[^a-z0-9]", "", k.lower()) if k else ""): (v.strip() if v else "")
                        for k, v in raw_row.items()
                    }
                    ne_name = (
                        norm.get("nename")
                        or norm.get("ne")
                        or norm.get("router")
                        or norm.get("name")
                        or ""
                    )

                    # Skip empty rows or already-scanned routers
                    if not ne_name or ne_name.upper() in scanned_upper:
                        continue

                    # Standardize dictionary keys to CSV_HEADERS
                    standardized = {
                        "ne_name": ne_name,
                        "ne_ip": norm.get("neip") or norm.get("ip") or "",
                        "arp_ip": norm.get("arpip") or norm.get("targetip") or "",
                        "arp_mac": norm.get("arpmac") or norm.get("mac") or "",
                        "vlan": norm.get("vlan") or "",
                        "vrf": norm.get("vrf") or "",
                        "arp_interface": (
                            norm.get("arpinterface")
                            or norm.get("interface")
                            or norm.get("intf")
                            or ""
                        ),
                        "mac_port": (
                            norm.get("macport")
                            or norm.get("port")
                            or norm.get("link")
                            or ""
                        ),
                        "collected_at": (
                            norm.get("collectedat")
                            or norm.get("timestamp")
                            or norm.get("date")
                            or ""
                        ),
                    }
                    existing_rows.append(standardized)
        except Exception as exc:
            logger.error("Error reading existing %s: %s", target, exc)

    all_rows = existing_rows + new_rows

    with open(target, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    return target


# ──────────────────────────────────────────────────────────────────────────────
# Background Collector Runner State & Orchestration
# ──────────────────────────────────────────────────────────────────────────────

_collector_job_lock = threading.Lock()
_active_collector_job = {
    "status": "idle",  # idle | running | done | error | stopped
    "total": 0,
    "completed": 0,
    "current_router": "",
    "rows_collected": 0,
    "scanned_nes": [],
    "logs": [],
    "error": None,
    "target_csv": "",
    "stop_requested": False,
}


def get_collector_job_status() -> Dict[str, Any]:
    """Get active collector job status."""
    with _collector_job_lock:
        return {
            "status": _active_collector_job["status"],
            "total": _active_collector_job["total"],
            "completed": _active_collector_job["completed"],
            "current_router": _active_collector_job["current_router"],
            "rows_collected": _active_collector_job["rows_collected"],
            "logs": _active_collector_job["logs"][-60:],
            "error": _active_collector_job["error"],
            "target_csv": _active_collector_job["target_csv"],
        }


def stop_collector_job() -> None:
    """Request active collector job to halt."""
    with _collector_job_lock:
        if _active_collector_job["status"] == "running":
            _active_collector_job["stop_requested"] = True
            _active_collector_job["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Stop requested.")


def start_collector_job(
    routers: List[Dict[str, str]],
    username: str,
    password: str,
    max_workers: int = 10,
    target_csv: Optional[str] = None,
) -> bool:
    """Start background collection thread on filtered routers."""
    global _active_collector_job

    with _collector_job_lock:
        if _active_collector_job["status"] == "running":
            return False

        _active_collector_job = {
            "status": "running",
            "total": len(routers),
            "completed": 0,
            "current_router": "",
            "rows_collected": 0,
            "scanned_nes": [r["name"] for r in routers],
            "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] Started ARP/MAC collector for {len(routers)} target routers (threads: {max_workers})."],
            "error": None,
            "target_csv": target_csv or get_target_arp_mac_csv_path(),
            "stop_requested": False,
        }

    def _worker():
        all_collected: List[Dict[str, str]] = []
        scanned_names: Set[str] = set()

        def _log(msg: str):
            t_str = datetime.now().strftime("%H:%M:%S")
            line = f"[{t_str}] {msg}"
            with _collector_job_lock:
                _active_collector_job["logs"].append(line)

        try:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ArpCollect") as executor:
                futures = {}
                for r in routers:
                    with _collector_job_lock:
                        if _active_collector_job["stop_requested"]:
                            break
                    f = executor.submit(
                        collect_router_arp_mac,
                        r["name"],
                        r["ip"],
                        r.get("ne_type", ""),
                        username,
                        password,
                        log_cb=_log,
                    )
                    futures[f] = r["name"]

                for future in as_completed(futures):
                    ne_name = futures[future]
                    with _collector_job_lock:
                        if _active_collector_job["stop_requested"]:
                            _log("Halting remaining router tasks...")
                            break
                        _active_collector_job["completed"] += 1
                        _active_collector_job["current_router"] = ne_name

                    try:
                        rows = future.result()
                        scanned_names.add(ne_name)
                        all_collected.extend(rows)
                        with _collector_job_lock:
                            _active_collector_job["rows_collected"] = len(all_collected)
                    except Exception as exc:
                        _log(f"Failed on {ne_name}: {exc}")

            out_path = save_or_update_arp_mac_csv(
                all_collected,
                scanned_names,
                _active_collector_job["target_csv"],
            )

            with _collector_job_lock:
                if _active_collector_job["stop_requested"]:
                    _active_collector_job["status"] = "stopped"
                    _active_collector_job["logs"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Job stopped. Saved {len(all_collected)} rows to {out_path}."
                    )
                else:
                    _active_collector_job["status"] = "done"
                    _active_collector_job["logs"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Successfully updated {out_path} ({len(all_collected)} rows from {len(scanned_names)} routers)."
                    )

        except Exception as exc:
            with _collector_job_lock:
                _active_collector_job["status"] = "error"
                _active_collector_job["error"] = str(exc)
                _active_collector_job["logs"].append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Fatal error: {exc}"
                )

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True

