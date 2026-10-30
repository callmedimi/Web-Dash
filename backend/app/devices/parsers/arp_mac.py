"""Huawei ARP and MAC-address table parsers (Target Architecture §3)."""
import re
from typing import Dict, Any, List, Optional

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


def normalize_mac(mac: Optional[str]) -> str:
    """Normalize MAC address to lowercase alphanumeric without separators."""
    if not mac:
        return ""
    return re.sub(r"[^0-9a-fA-F]", "", str(mac)).lower()


def parse_display_arp(output: str) -> List[Dict[str, Any]]:
    """Parse 'display arp' output into list of structured ARP entries."""
    entries: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

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
                "arp_ip": m.group(1),
                "arp_mac": m.group(2).lower(),
                "normalized_mac": normalize_mac(m.group(2)),
                "interface": m.group(5),
                "vrf": m.group(6) or "",
                "vlan": "",
            }
            continue

        v = ARP_VLAN_CONT_RE.match(line)
        if v and current is not None:
            current["vlan"] = v.group(1)

    if current is not None:
        entries.append(current)

    return entries


def parse_display_mac(output: str) -> Dict[str, List[Dict[str, str]]]:
    """Parse 'display mac-address' output into a map of normalized MAC to ports and VLANs."""
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

        raw_mac = start.group(1).lower()
        norm_mac = normalize_mac(raw_mac)
        vlan = start.group(2)
        port = end.group(1)

        mac_map.setdefault(norm_mac, []).append({"vlan": vlan, "port": port})

    return mac_map
