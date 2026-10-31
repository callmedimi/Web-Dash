"""Command Runner REST API (Automation Catalog Step 5.11)."""
from flask import Blueprint, request, jsonify, Response

from auth import login_required
from backend.app.db.session import get_db_session
from backend.app.services.command_runner import (
    CommandRunnerService,
    CommandRunnerSecurityError,
)

command_runner_bp = Blueprint("command_runner", __name__)


@command_runner_bp.route("/allowlist", methods=["GET"])
@login_required
def get_allowlisted_commands():
    """List all approved read-only CLI commands."""
    commands = CommandRunnerService.list_allowlisted_commands()
    return jsonify({
        "status": "success",
        "count": len(commands),
        "commands": commands,
    }), 200


@command_runner_bp.route("/run", methods=["POST"])
@login_required
def run_command_on_devices():
    """Execute an allowlisted read-only command on target devices."""
    payload = request.get_json(silent=True) or {}
    cmd_name = payload.get("command")
    targets = payload.get("target_devices") or []
    variables = payload.get("variables") or {}
    timeout = payload.get("timeout")

    if not cmd_name or not targets:
        return jsonify({
            "error": "PARAMS_REQUIRED",
            "message": "Both 'command' and 'target_devices' are required",
        }), 400

    with get_db_session() as session:
        try:
            res = CommandRunnerService.execute_on_devices(
                db_session=session,
                command_name=cmd_name,
                target_devices=targets,
                variables=variables,
                timeout=timeout,
            )
            return jsonify({
                "status": "success",
                "data": res,
            }), 200
        except CommandRunnerSecurityError as sec_err:
            return jsonify({
                "error": "SECURITY_VIOLATION",
                "message": str(sec_err),
            }), 403
        except KeyError as key_err:
            return jsonify({
                "error": "UNKNOWN_COMMAND",
                "message": str(key_err),
            }), 404
        except Exception as exc:
            return jsonify({
                "error": "EXECUTION_ERROR",
                "message": str(exc),
            }), 500


@command_runner_bp.route("/search", methods=["POST"])
@login_required
def search_command_outputs():
    """Perform substring or regex search across collected device outputs."""
    payload = request.get_json(silent=True) or {}
    results = payload.get("results") or []
    pattern = payload.get("pattern", "")
    is_regex = payload.get("is_regex", False)
    case_sensitive = payload.get("case_sensitive", False)

    if not pattern:
        return jsonify({
            "error": "PATTERN_REQUIRED",
            "message": "Parameter 'pattern' is required",
        }), 400

    try:
        search_res = CommandRunnerService.search_outputs(
            results=results,
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
        )
        return jsonify({
            "status": "success",
            "data": search_res,
        }), 200
    except ValueError as val_err:
        return jsonify({
            "error": "INVALID_REGEX",
            "message": str(val_err),
        }), 400


@command_runner_bp.route("/render-template", methods=["POST"])
@login_required
def render_template_preview():
    """Render Jinja2 configuration template for planned change preview."""
    payload = request.get_json(silent=True) or {}
    tpl_str = payload.get("template_content", "")
    vars_dict = payload.get("variables", {})

    res = CommandRunnerService.render_config_template(tpl_str, vars_dict)
    if res.get("status") == "error":
        return jsonify(res), 400
    return jsonify(res), 200


@command_runner_bp.route("/export", methods=["POST"])
@login_required
def export_results():
    """Export collected outputs and search matches as CSV."""
    payload = request.get_json(silent=True) or {}
    results = payload.get("results") or []
    search_data = payload.get("search_matches")

    csv_data = CommandRunnerService.export_results_csv(results, search_matches=search_data)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="command_runner_results.csv"',
        },
    )
