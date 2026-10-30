"""Huawei active alarms parser (Target Architecture §3 & F-25).

Parses 'display alarm active' outputs:
- Supports timestamps with +HH:MM, -HH:MM, Z, or no timezone.
- Supports multi-line wrapped alarm descriptions.
- Raises ParseError if raw text contains substantial content (> 3 non-banner lines)
  but zero alarms could be parsed, preventing silent failures.
"""
import re
from typing import List, Dict, Any, Optional
from backend.app.devices.errors import ParseError

BANNER_PATTERNS = [
    re.compile(r"^\s*Sequence\s+AlarmId", re.IGNORECASE),
    re.compile(r"^-{5,}"),
    re.compile(r"^={5,}"),
    re.compile(r"^\s*1:Critical", re.IGNORECASE),
    re.compile(r"^\s*Info:", re.IGNORECASE),
    re.compile(r"^\s*press\s+CTRL_C", re.IGNORECASE),
    re.compile(r"^\s*It will take a long time", re.IGNORECASE),
    re.compile(r"^\s*no active alarms", re.IGNORECASE),
    re.compile(r"^\s*Total\s+alarms?:", re.IGNORECASE),
    re.compile(r"^\s*<[^>]+>"),  # prompt line
    re.compile(r"^\s*\[[^\]]+\]"),  # sysview prompt
]

ALARM_LINE_REGEX = re.compile(
    r"^\s*(\d+)\s+(0x[0-9A-Fa-f]+)\s+(\d)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:?\d{2}|Z)?)\s+(.+)$"
)


def is_banner_or_noise(line: str) -> bool:
    """Check if line is a CLI banner, table header, or separator."""
    s = line.strip()
    if not s:
        return True
    for pat in BANNER_PATTERNS:
        if pat.search(s):
            return True
    return False


def parse_active_alarms(output: str, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parse 'display alarm active' CLI output.
    Returns list of dicts:
        sequence (int), alarm_id (str), level (int), date (str), time (str), description (str)
    """
    if not output or not output.strip():
        return []

    alarms: List[Dict[str, Any]] = []
    non_banner_lines_count = 0
    lines = output.splitlines()

    for line in lines:
        if not line.strip():
            continue

        if is_banner_or_noise(line):
            continue

        non_banner_lines_count += 1
        m = ALARM_LINE_REGEX.match(line)

        if m:
            seq, alarm_id, level, dt, tm, desc = m.groups()
            alarms.append({
                "sequence": int(seq),
                "alarm_id": alarm_id,
                "level": int(level),
                "date": dt,
                "time": tm,
                "description": desc.strip(),
            })
        elif alarms:
            # Check if this is a wrapped description line for the preceding alarm
            indent_or_continuation = line.strip()
            if indent_or_continuation:
                alarms[-1]["description"] += f" {indent_or_continuation}"

    # F-25 Safety Check: if raw text had > 3 non-banner lines but 0 parsed rows, raise ParseError
    if non_banner_lines_count > 3 and len(alarms) == 0:
        raise ParseError(
            f"Failed to parse active alarms: output contained {non_banner_lines_count} lines of unparsed text (F-25)",
            raw_output=output[:500],
            device_name=device_name,
        )

    return alarms
