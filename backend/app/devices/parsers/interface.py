"""Huawei interface status and configuration parsers (Target Architecture §3 & F-20)."""
import re
from typing import Dict, Any, List, Optional
from backend.app.devices.errors import check_vrp_banner_errors

ALLOWED_TRIVIAL_COMMANDS = {
    "dcn",
    "undo dcn",
    "shutdown",
    "undo shutdown",
}


def parse_display_interface(output: str) -> Dict[str, Any]:
    """
    Parse 'display interface <if>' output.
    Returns:
        name: str
        physical_state: str (UP, DOWN, Administratively DOWN)
        protocol_state: str (UP, DOWN)
        description: str
        is_admin_down: bool
        last_change: Optional[str]
    """
    result: Dict[str, Any] = {
        "name": "",
        "physical_state": "UNKNOWN",
        "protocol_state": "UNKNOWN",
        "description": "",
        "is_admin_down": False,
        "last_change": None,
    }

    if not output:
        return result

    for line in output.splitlines():
        line_clean = line.strip()

        # Physical state line: e.g. "GigabitEthernet0/1/0 current state : UP"
        if "current state :" in line_clean and not line_clean.lower().startswith("line protocol"):
            parts = line_clean.split("current state :", 1)
            result["name"] = parts[0].strip()
            state = parts[1].strip()
            result["physical_state"] = state
            if "administratively down" in state.lower():
                result["is_admin_down"] = True

        # Protocol state line: e.g. "Line protocol current state : UP"
        elif "line protocol current state :" in line_clean.lower():
            state = line_clean.split(":", 1)[1].strip()
            result["protocol_state"] = state

        # Description line
        elif line_clean.lower().startswith("description:"):
            desc = line_clean.split(":", 1)[1].strip()
            result["description"] = desc

        # Last physical change line
        elif "last physical down time" in line_clean.lower() or "last physical up time" in line_clean.lower():
            if not result["last_change"] and ":" in line_clean:
                result["last_change"] = line_clean.split(":", 1)[1].strip()

    return result


def parse_interface_config(output: str) -> Dict[str, Any]:
    """
    Parse 'display current-configuration interface <if>' output.

    Safety rule (F-20):
    An empty reply is flagged as error='EMPTY_OUTPUT', NEVER as 'no configuration'.
    Error banners (Error:, Unrecognized command) are captured in error.
    """
    if not output or not output.strip():
        return {
            "lines": [],
            "is_empty": True,
            "error": "EMPTY_OUTPUT",
            "is_trivial": False,
        }

    # Check for CLI error banner
    err_banner = check_vrp_banner_errors(output)
    if err_banner:
        return {
            "lines": [],
            "is_empty": True,
            "error": err_banner,
            "is_trivial": False,
        }

    meaningful_lines: List[str] = []
    raw_lines: List[str] = []

    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        raw_lines.append(s)

        # Skip CLI banners / comments / prompt
        if s.startswith("#") or s.startswith("<") or s.startswith("[") or s.startswith("Info:") or s.startswith("^"):
            continue
        if s.lower().startswith("interface "):
            continue
        if s.lower() in ("return", "quit"):
            continue

        meaningful_lines.append(s.lower())

    if not raw_lines or (len(raw_lines) == 1 and raw_lines[0].lower() in ("return", "quit")):
        return {
            "lines": raw_lines,
            "is_empty": True,
            "error": "EMPTY_OUTPUT",
            "is_trivial": False,
        }

    # Check if configuration is trivial (only dcn, shutdown, or empty)
    is_trivial = len(meaningful_lines) == 0 or all(
        cmd in ALLOWED_TRIVIAL_COMMANDS for cmd in meaningful_lines
    )

    return {
        "lines": raw_lines,
        "is_empty": len(meaningful_lines) == 0,
        "error": None,
        "is_trivial": is_trivial,
    }
