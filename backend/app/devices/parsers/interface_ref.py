"""Interface Reference extraction and normalization (Target Architecture §3 & F-21).

Normalizes Huawei interface names (GE -> GigabitEthernet, 10GE -> XGigabitEthernet, etc.)
Handles sub-interfaces (.NNN), strips punctuation, and detects ambiguous alarm lines
referencing multiple distinct interfaces.
"""
import re
from dataclasses import dataclass
from typing import Optional, Set, Tuple


@dataclass
class InterfaceRef:
    """Normalized interface reference."""
    name: str
    parent: str
    is_sub: bool = False
    ambiguous: bool = False


# Canonical prefixes and their normalizations
PREFIX_MAPPING = [
    (re.compile(r"^100GE", re.IGNORECASE), "100GE"),
    (re.compile(r"^40GE", re.IGNORECASE), "40GE"),
    (re.compile(r"^25GE", re.IGNORECASE), "25GE"),
    (re.compile(r"^(?:10GE|XGE|XGigabitEthernet)", re.IGNORECASE), "XGigabitEthernet"),
    (re.compile(r"^(?:GigabitEthernet|GE)", re.IGNORECASE), "GigabitEthernet"),
    (re.compile(r"^(?:Eth-Trunk|EthTrunk)", re.IGNORECASE), "Eth-Trunk"),
    (re.compile(r"^(?:Virtual-Ethernet|VirtualEthernet)", re.IGNORECASE), "Virtual-Ethernet"),
    (re.compile(r"^(?:Ethernet|Eth)", re.IGNORECASE), "Ethernet"),
    (re.compile(r"^Vlanif", re.IGNORECASE), "Vlanif"),
    (re.compile(r"^(?:LoopBack|Loopback)", re.IGNORECASE), "LoopBack"),
    (re.compile(r"^Tunnel", re.IGNORECASE), "Tunnel"),
    (re.compile(r"^Serial", re.IGNORECASE), "Serial"),
    (re.compile(r"^Cpos", re.IGNORECASE), "Cpos"),
    (re.compile(r"^Pos", re.IGNORECASE), "Pos"),
]

# Alarm tag patterns (e.g. ifName=GE0/1/0)
TAG_PATTERNS = [
    re.compile(r'\bifName=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bInterfaceName=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bmainIfname=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bSubIfName=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bEntPhysicalName=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bInterface=([^\s,;)]+)', re.IGNORECASE),
    re.compile(r'\bPortID=([^\s,;)]+)', re.IGNORECASE),
]

# Raw interface pattern in text
RAW_IFACE_PATTERN = re.compile(
    r'\b((?:100GE|40GE|25GE|10GE|XGE|XGigabitEthernet|GigabitEthernet|GE|Eth-Trunk|EthTrunk|Virtual-Ethernet|VirtualEthernet|Ethernet|Eth|Vlanif|LoopBack|Loopback|Tunnel|Serial|Cpos|Pos)[\d/]+(?::\d+)?(?:\.\d+)?)\b',
    re.IGNORECASE,
)

PUNCTUATION_STRIP = "),;.:'\""


def normalize_interface_name(raw: str) -> Optional[Tuple[str, str, bool]]:
    """
    Normalize raw interface name string to (canonical_name, parent_name, is_sub).
    Returns None if raw does not match standard interface pattern.
    """
    cleaned = raw.strip().strip(PUNCTUATION_STRIP)
    if not cleaned:
        return None

    # Check for sub-interface suffix (.NNN)
    is_sub = False
    sub_suffix = ""
    dot_idx = cleaned.find(".")
    if dot_idx != -1:
        base_part = cleaned[:dot_idx]
        sub_suffix = cleaned[dot_idx:]
        is_sub = True
    else:
        base_part = cleaned

    for pattern, canonical in PREFIX_MAPPING:
        m = pattern.search(base_part)
        if m:
            slot_part = base_part[m.end():]
            if slot_part:
                parent_norm = f"{canonical}{slot_part}"
                full_norm = f"{parent_norm}{sub_suffix}"
                return full_norm, parent_norm, is_sub

    return None


def extract_interface(description: str) -> Optional[InterfaceRef]:
    """
    Extract and normalize interface reference from alarm or CLI description.
    Returns None if:
    - No interface is found.
    - Multiple different interfaces are found (ambiguous alarm description).
    """
    if not description:
        return None

    found_norm_candidates: Set[Tuple[str, str, bool]] = set()

    # 1. Search tagged alarm patterns first (higher confidence)
    for tag_pat in TAG_PATTERNS:
        for match in tag_pat.finditer(description):
            raw_val = match.group(1)
            norm = normalize_interface_name(raw_val)
            if norm:
                found_norm_candidates.add(norm)

    # 2. Also search untagged interface regex occurrences
    for match in RAW_IFACE_PATTERN.finditer(description):
        raw_val = match.group(1)
        norm = normalize_interface_name(raw_val)
        if norm:
            found_norm_candidates.add(norm)

    if not found_norm_candidates:
        return None

    # Check distinct parent interfaces found
    parents = {c[1] for c in found_norm_candidates}
    if len(parents) > 1:
        # Ambiguity detected (different interfaces in one description)
        return None

    # Single interface or sub-interface relationship: pick the most specific (e.g. sub-interface if present)
    candidates_list = sorted(list(found_norm_candidates), key=lambda x: (x[2], len(x[0])), reverse=True)
    full_name, parent_name, is_sub = candidates_list[0]

    return InterfaceRef(
        name=full_name,
        parent=parent_name,
        is_sub=is_sub,
        ambiguous=False,
    )
