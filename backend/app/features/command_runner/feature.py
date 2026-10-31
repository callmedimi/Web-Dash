"""Command Runner Catalog Feature (Automation Catalog Step 5.11).

Provides:
- Allowlisted read-only commands list.
- Parallel multi-device execution.
- Output grep/regex search.
- Template rendering for change pipeline preview.
- CSV export.
"""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.command_runner import CommandRunnerService, CommandRunnerSecurityError


class CommandRunnerFeature(BaseFeature):
    """Automation catalog feature for multi-device read-only commands and output analysis."""

    spec = FeatureSpec(
        name="Command Runner",
        feature_key="command_runner",
        risk="low",
        needs_ssh=True,
        needs_telemetry=False,
        read_only=True,
        description="Execute verified read-only display commands across devices with template substitution and output regex search.",
        permission_key="operator",
        inputs={
            "action": "list | run | search | render_template | export",
            "command": "Logical name of allow-listed command (e.g. display_version, display_ntp_status)",
            "target_devices": "List of device names or IDs to execute against",
            "variables": "Command template variables (e.g. {'interface': 'GE0/1/0'})",
            "pattern": "String or regex pattern to search across command outputs",
            "is_regex": "True if pattern is a regular expression (default: False)",
            "case_sensitive": "True for case-sensitive matching (default: False)",
            "template_content": "Jinja2 config template string to render for change preview",
            "results": "Execution results list (for search or export actions)",
        },
        outputs={
            "allowlist": "List of available read-only commands and parameters",
            "execution": "Multi-device outputs and execution metrics",
            "search": "Matching line numbers, lines, and affected devices",
            "template": "Rendered config block for change pipeline intake",
            "csv": "Formatted CSV string",
        },
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        """Execute command runner action."""
        params = ctx.params or {}
        action = params.get("action", "run")
        session = ctx.db_session

        if action == "list":
            commands = CommandRunnerService.list_allowlisted_commands()
            return {
                "status": "success",
                "action": "list",
                "count": len(commands),
                "commands": commands,
            }

        elif action == "run":
            cmd_name = params.get("command")
            target_devices = params.get("target_devices") or []
            if not cmd_name or not target_devices:
                return {
                    "status": "error",
                    "error": "PARAMS_REQUIRED",
                    "message": "Both 'command' and 'target_devices' are required for action 'run'",
                }

            try:
                # Custom session_factory can be passed in ctx.params['_session_factory'] for testing
                session_factory = params.get("_session_factory")
                exec_res = CommandRunnerService.execute_on_devices(
                    db_session=session,
                    command_name=cmd_name,
                    target_devices=target_devices,
                    variables=params.get("variables"),
                    session_factory=session_factory,
                    timeout=params.get("timeout"),
                )
                return {
                    "status": "success",
                    "action": "run",
                    "data": exec_res,
                }
            except CommandRunnerSecurityError as sec_err:
                return {
                    "status": "error",
                    "error": "SECURITY_VIOLATION",
                    "message": str(sec_err),
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "error": "EXECUTION_ERROR",
                    "message": str(exc),
                }

        elif action == "search":
            results = params.get("results") or []
            pattern = params.get("pattern", "")
            if not pattern:
                return {
                    "status": "error",
                    "error": "PATTERN_REQUIRED",
                    "message": "Parameter 'pattern' is required for search",
                }

            try:
                search_res = CommandRunnerService.search_outputs(
                    results=results,
                    pattern=pattern,
                    is_regex=params.get("is_regex", False),
                    case_sensitive=params.get("case_sensitive", False),
                )
                return {
                    "status": "success",
                    "action": "search",
                    "data": search_res,
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "error": "SEARCH_ERROR",
                    "message": str(exc),
                }

        elif action == "render_template":
            tpl_str = params.get("template_content", "")
            vars_dict = params.get("variables", {})
            tpl_res = CommandRunnerService.render_config_template(tpl_str, vars_dict)
            return tpl_res

        elif action == "export":
            results = params.get("results") or []
            search_data = params.get("search_matches")
            csv_str = CommandRunnerService.export_results_csv(results, search_matches=search_data)
            return {
                "status": "success",
                "action": "export",
                "csv_data": csv_str,
            }

        else:
            return {
                "status": "error",
                "error": "UNKNOWN_ACTION",
                "message": f"Unsupported action '{action}'",
            }


# Register feature in catalog
command_runner_feature = CommandRunnerFeature()
feature_registry.register(command_runner_feature)
