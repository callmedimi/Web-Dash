"""Command Runner Service (Automation Catalog Step 5.11).

Provides:
- Allowlisted read-only multi-device CLI command execution.
- Strict read_only: True enforcement via DeviceCommand registry.
- High-performance parallel multi-device collector.
- Regex and substring search across command outputs.
- Safe Jinja2 config template rendering for planned changes (goes through change pipeline).
- CSV export for multi-device outputs.
"""
from __future__ import annotations
import csv
import io
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable
from jinja2 import Environment, BaseLoader, select_autoescape
from sqlalchemy.orm import Session

from backend.app.models.device import Device
from backend.app.devices.registry import default_registry, CommandRegistry, DeviceCommand
from backend.app.devices.pool import create_device_session
from backend.app.devices.session import DeviceSession

logger = logging.getLogger(__name__)


class CommandRunnerSecurityError(PermissionError):
    """Raised when an execution attempts to run a non-read-only or unregistered command."""
    pass


class CommandRunnerService:
    """Enterprise power tool for executing verified read-only commands across Huawei routers."""

    @classmethod
    def list_allowlisted_commands(
        cls, registry: Optional[CommandRegistry] = None
    ) -> List[Dict[str, Any]]:
        """Return all declared commands that have read_only=True."""
        reg = registry or default_registry
        allowlisted = []
        for cmd in reg.list_commands():
            if cmd.read_only:
                allowlisted.append({
                    "name": cmd.name,
                    "description": cmd.description,
                    "timeout": cmd.timeout,
                    "verified": cmd.verified,
                    "family_commands": cmd.family_commands,
                    "read_only": True,
                })
        return sorted(allowlisted, key=lambda c: c["name"])

    @classmethod
    def validate_command(
        cls, command_name: str, registry: Optional[CommandRegistry] = None
    ) -> DeviceCommand:
        """Validate command existence and verify that read_only is True."""
        reg = registry or default_registry
        if not reg.has(command_name):
            raise KeyError(f"Command '{command_name}' is not registered in allowlist")

        cmd = reg.get(command_name)
        if not cmd.read_only:
            raise CommandRunnerSecurityError(
                f"Command '{command_name}' is NOT read-only. Mutation commands are prohibited in Command Runner."
            )
        return cmd

    @classmethod
    def execute_on_devices(
        cls,
        db_session: Session,
        command_name: str,
        target_devices: List[str],
        variables: Optional[Dict[str, Any]] = None,
        session_factory: Optional[Callable[[Device], DeviceSession]] = None,
        max_workers: int = 10,
        timeout: Optional[int] = None,
        registry: Optional[CommandRegistry] = None,
    ) -> Dict[str, Any]:
        """
        Execute an allow-listed read-only command across a target set of devices in parallel.
        """
        cmd_meta = cls.validate_command(command_name, registry=registry)
        vars_dict = variables or {}
        cmd_timeout = timeout or cmd_meta.timeout

        # Resolve devices from inventory
        dev_map: Dict[str, Device] = {}
        for identifier in target_devices:
            cleaned = str(identifier).strip()
            if cleaned.isdigit():
                d = db_session.query(Device).filter(Device.id == int(cleaned)).first()
            else:
                d = db_session.query(Device).filter(Device.name.ilike(cleaned)).first()
            if d:
                dev_map[d.name] = d

        start_time = time.time()
        results: List[Dict[str, Any]] = []

        def _run_single(dev_name: str) -> Dict[str, Any]:
            dev_record = dev_map.get(dev_name)
            if not dev_record:
                return {
                    "device_name": dev_name,
                    "device_id": None,
                    "status": "failed",
                    "error": "DEVICE_NOT_FOUND",
                    "output": "",
                    "duration_ms": 0,
                }

            t0 = time.time()
            try:
                os_family = dev_record.os_family or "vrp8"
                formatted_cmd = cmd_meta.format(os_family, **vars_dict)

                # Acquire session via factory or pool
                if session_factory:
                    sess = session_factory(dev_record)
                else:
                    sess = create_device_session(
                        device_name=dev_record.name,
                        db_session=db_session,
                        jitter=False,
                    )

                with sess:
                    raw_out = sess.run(formatted_cmd, timeout=cmd_timeout)
                    dur_ms = int((time.time() - t0) * 1000)
                    return {
                        "device_name": dev_record.name,
                        "device_id": dev_record.id,
                        "command_sent": formatted_cmd,
                        "status": "success",
                        "output": raw_out or "",
                        "error": None,
                        "duration_ms": dur_ms,
                    }
            except Exception as exc:
                dur_ms = int((time.time() - t0) * 1000)
                logger.warning("Failed command execution on %s: %s", dev_name, exc)
                return {
                    "device_name": dev_name,
                    "device_id": dev_record.id if dev_record else None,
                    "command_sent": command_name,
                    "status": "failed",
                    "output": "",
                    "error": str(exc),
                    "duration_ms": dur_ms,
                }

        # Execute in thread pool
        with ThreadPoolExecutor(max_workers=min(max_workers, max(len(target_devices), 1))) as executor:
            futures = {executor.submit(_run_single, d): d for d in target_devices}
            for fut in as_completed(futures):
                results.append(fut.result())

        total_dur_ms = int((time.time() - start_time) * 1000)
        succeeded_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")

        return {
            "command": command_name,
            "variables": vars_dict,
            "total_devices": len(target_devices),
            "succeeded": succeeded_count,
            "failed": failed_count,
            "total_duration_ms": total_dur_ms,
            "results": sorted(results, key=lambda r: r["device_name"]),
        }

    @classmethod
    def search_outputs(
        cls,
        results: List[Dict[str, Any]],
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform grep or regex search across collected multi-device outputs.
        Returns matching line numbers, lines, and matched device summaries.
        """
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled_pattern = None

        if is_regex:
            try:
                compiled_pattern = re.compile(pattern, flags)
            except re.error as err:
                raise ValueError(f"Invalid regular expression pattern: {err}")
        else:
            escaped = re.escape(pattern)
            compiled_pattern = re.compile(escaped, flags)

        matches_by_device: List[Dict[str, Any]] = []
        total_matched_lines = 0

        for r in results:
            dev_name = r.get("device_name", "UNKNOWN")
            output = r.get("output", "")
            lines = output.splitlines()
            matched_lines: List[Dict[str, Any]] = []

            for idx, line in enumerate(lines, start=1):
                if compiled_pattern.search(line):
                    matched_lines.append({
                        "line_number": idx,
                        "line": line.strip(),
                    })

            if matched_lines:
                total_matched_lines += len(matched_lines)
                matches_by_device.append({
                    "device_name": dev_name,
                    "device_id": r.get("device_id"),
                    "match_count": len(matched_lines),
                    "lines": matched_lines,
                })

        return {
            "pattern": pattern,
            "is_regex": is_regex,
            "case_sensitive": case_sensitive,
            "matched_devices_count": len(matches_by_device),
            "total_matches_count": total_matched_lines,
            "matches": matches_by_device,
        }

    @classmethod
    def render_config_template(
        cls,
        template_content: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Render Jinja2 configuration template for planned change preview.
        Enforces that rendered output is returned for approval pipeline, never applied directly.
        """
        if not template_content:
            return {
                "status": "error",
                "error": "EMPTY_TEMPLATE",
                "message": "Template content cannot be empty",
            }

        try:
            env = Environment(
                loader=BaseLoader(),
                autoescape=select_autoescape(default=False),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            tpl = env.from_string(template_content)
            rendered = tpl.render(**variables)
            return {
                "status": "success",
                "rendered_config": rendered.strip(),
                "variables_applied": variables,
                "lines_count": len(rendered.strip().splitlines()),
                "direct_execution_blocked": True,
                "notice": "Rendered config must be submitted to Change Pipeline (/api/v1/changes/plan) for approval.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": "TEMPLATE_SYNTAX_ERROR",
                "message": f"Failed to render configuration template: {exc}",
            }

    @classmethod
    def export_results_csv(
        cls,
        results: List[Dict[str, Any]],
        search_matches: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Export command execution outputs and search match counts to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        has_search = search_matches is not None
        headers = ["Device Name", "Status", "Duration (ms)", "Error"]
        if has_search:
            headers.append("Match Count")
            headers.append("Matched Lines Snippet")
        headers.append("Output")

        writer.writerow(headers)

        matches_map = {}
        if has_search and "matches" in search_matches:
            for m in search_matches["matches"]:
                matches_map[m["device_name"]] = m

        for r in results:
            d_name = r.get("device_name", "")
            status = r.get("status", "")
            dur = r.get("duration_ms", 0)
            err = r.get("error", "") or ""
            raw_out = r.get("output", "")

            row = [d_name, status, dur, err]

            if has_search:
                dev_m = matches_map.get(d_name)
                if dev_m:
                    m_count = dev_m["match_count"]
                    snippets = " | ".join(f"[L{l['line_number']}]: {l['line']}" for l in dev_m["lines"][:3])
                    row.extend([m_count, snippets])
                else:
                    row.extend([0, ""])

            # Clean output for CSV cell
            row.append(raw_out.replace("\r", ""))
            writer.writerow(row)

        return output.getvalue()
