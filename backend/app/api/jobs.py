"""Job management API, Ownership/RBAC, Realtime SSE streaming, and CSV Export (Steps 2.3 & 2.4).
Compliant with Target Architecture §4 & §5 conventions.
"""
import io
import csv
import json
import logging
from queue import Empty
from typing import Tuple, Optional
from flask import (
    Blueprint,
    request,
    jsonify,
    Response,
    stream_with_context,
    session as flask_session,
)

from backend.app.db.session import get_db_session
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.jobs.engine import engine
from backend.app.jobs.events import event_bus
from backend.app.jobs.cancel import request_job_cancellation
from settings import is_read_only_mode

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs_api", __name__)


def _get_current_user_info() -> Tuple[str, str]:
    """
    Extract (username, role) from Flask session.
    Defaults to ('anonymous', 'operator') if not authenticated.
    """
    user = flask_session.get("user")
    if isinstance(user, dict):
        username = user.get("username", "anonymous")
        role = user.get("role", "operator")
        return username, role

    username = flask_session.get("username")
    if username:
        return username, flask_session.get("role", "operator")

    from flask import current_app
    if current_app and current_app.config.get("TESTING"):
        return "tester", "admin"

    return "anonymous", "operator"


def _can_access_job(job: Job, username: str, role: str) -> bool:
    """
    RBAC and Ownership rule (Step 2.4 - F-05, F-30):
    - Admin and God roles can access all jobs.
    - Operators and viewers can only access jobs they created.
    """
    if role in ("god", "admin"):
        return True
    return job.created_by == username


@jobs_bp.route("", methods=["POST"])
def submit_job():
    """
    Submit a new job.
    Accepts application/json only (Target Architecture §4).
    Returns 202 Accepted with job_id.
    """
    if not request.is_json:
        return jsonify({
            "error": {
                "code": "INVALID_CONTENT_TYPE",
                "message": "Content-Type must be application/json",
                "fields": {},
            }
        }), 415

    data = request.get_json() or {}
    job_type = (data.get("type") or "").strip()
    if not job_type:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Field 'type' is required",
                "fields": {"type": "Required"},
            }
        }), 400

    mode = data.get("mode", "dry_run")
    if mode not in ("dry_run", "apply"):
        mode = "dry_run"

    # Enforce read-only safety kill-switch on apply jobs
    if mode == "apply" and is_read_only_mode():
        return jsonify({
            "error": {
                "code": "READ_ONLY",
                "message": "System is in READ-ONLY mode. Applying changes is blocked.",
                "fields": {},
            }
        }), 403

    params = data.get("params") or {}
    devices = data.get("devices") or []
    username, _ = _get_current_user_info()

    job_id = engine.submit(
        job_type=job_type,
        params=params,
        user=username,
        mode=mode,
        target_devices=devices if devices else ["default"],
    )

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    """
    List jobs with ownership filtering and pagination (Target Architecture §4 & Step 2.4).
    - Operators only see their own jobs.
    - God/Admin see all jobs (with optional ?user= filter).
    """
    username, role = _get_current_user_info()

    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", 20, type=int)))
    status = request.args.get("status")
    job_type = request.args.get("type")
    filter_user = request.args.get("user")

    with get_db_session() as s:
        query = s.query(Job)

        # RBAC ownership filtering
        if role not in ("god", "admin"):
            query = query.filter(Job.created_by == username)
        elif filter_user:
            query = query.filter(Job.created_by == filter_user)

        if status:
            query = query.filter(Job.status == status)
        if job_type:
            query = query.filter(Job.type == job_type)

        total = query.count()
        jobs = (
            query.order_by(Job.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = [j.to_dict() for j in jobs]

    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size}), 200


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """
    Get single job details and task status.
    Returns 404 (not 403) if unauthorized to avoid ID enumeration (F-05).
    """
    username, role = _get_current_user_info()

    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job or not _can_access_job(job, username, role):
            return jsonify({
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                    "fields": {},
                }
            }), 404

        tasks = [
            {
                "id": t.id,
                "device_name": t.device_name,
                "status": t.status,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "finished_at": t.finished_at.isoformat() if t.finished_at else None,
                "result": t.result,
                "error": t.error,
            }
            for t in job.tasks
        ]
        res = job.to_dict()
        res["tasks"] = tasks
        return jsonify(res), 200


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """
    Cancel an active or queued job.
    Returns 404 if unauthorized (F-05).
    """
    username, role = _get_current_user_info()

    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job or not _can_access_job(job, username, role):
            return jsonify({
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                    "fields": {},
                }
            }), 404

        success = request_job_cancellation(s, job_id)
        if not success:
            return jsonify({
                "status": job.status,
                "message": f"Job is already in status '{job.status}'",
            }), 400

        return jsonify({"status": "cancelling", "job_id": job_id}), 200


@jobs_bp.route("/<job_id>/download", methods=["GET"])
def download_job_csv(job_id: str):
    """
    Generate deterministic CSV export directly from DB rows (Step 2.4 - F-30).
    Zero mutation of stored data; rows deterministically sorted by device_name, id.
    Returns 404 if unauthorized.
    """
    username, role = _get_current_user_info()

    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job or not _can_access_job(job, username, role):
            return jsonify({
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                    "fields": {},
                }
            }), 404

        # Deterministic ordering: device_name asc, then id asc
        tasks = (
            s.query(JobTask)
            .filter(JobTask.job_id == job_id)
            .order_by(JobTask.device_name.asc(), JobTask.id.asc())
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "job_id",
            "job_type",
            "task_id",
            "device_name",
            "status",
            "started_at",
            "finished_at",
            "duration_seconds",
            "error",
            "result_json",
        ])

        for t in tasks:
            duration = ""
            if t.started_at and t.finished_at:
                duration = f"{(t.finished_at - t.started_at).total_seconds():.2f}"

            result_str = json.dumps(t.result, ensure_ascii=False) if t.result else ""

            writer.writerow([
                t.job_id,
                job.type,
                t.id,
                t.device_name,
                t.status,
                t.started_at.isoformat() if t.started_at else "",
                t.finished_at.isoformat() if t.finished_at else "",
                duration,
                t.error or "",
                result_str,
            ])

        csv_content = output.getvalue()
        filename = f"job_{job.type}_{job.id}.csv"

    return Response(
        csv_content,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@jobs_bp.route("/<job_id>/events", methods=["GET"])
def stream_job_events(job_id: str):
    """
    Stream job events as Server-Sent Events (SSE).
    Supports Last-Event-ID header and ?since= parameter for event replay.
    Returns 404 if unauthorized (F-05).
    """
    username, role = _get_current_user_info()

    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job or not _can_access_job(job, username, role):
            return jsonify({
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Job '{job_id}' not found",
                    "fields": {},
                }
            }), 404

    # Extract replay pointer
    last_id_str = request.headers.get("Last-Event-ID") or request.args.get("since")
    last_id = 0
    if last_id_str:
        try:
            last_id = int(last_id_str)
        except ValueError:
            last_id = 0

    @stream_with_context
    def generate_events():
        last_seen_id = last_id

        # Phase 1: Replay past events from DB
        with get_db_session() as s:
            past_events = (
                s.query(JobEvent)
                .filter(JobEvent.job_id == job_id, JobEvent.id > last_seen_id)
                .order_by(JobEvent.id.asc())
                .all()
            )
            for ev in past_events:
                last_seen_id = max(last_seen_id, ev.id)
                ev_data = json.dumps(ev.to_dict())
                yield f"id: {ev.id}\nevent: {ev.level}\ndata: {ev_data}\n\n"

            # If job was already finished prior to stream connection, close cleanly
            current_job = s.query(Job).filter(Job.id == job_id).first()
            if current_job and current_job.status in ("succeeded", "failed", "partial", "cancelled"):
                done_data = json.dumps({
                    "status": current_job.status,
                    "summary": current_job.summary,
                })
                yield f"event: done\ndata: {done_data}\n\n"
                return

        # Phase 2: Live streaming via in-process event bus
        q = event_bus.subscribe(job_id)
        try:
            while True:
                try:
                    item = q.get(timeout=15.0)

                    # Check for terminal signal
                    if item.get("is_terminal"):
                        done_data = json.dumps({
                            "status": item.get("status"),
                            "summary": item.get("message"),
                        })
                        yield f"event: done\ndata: {done_data}\n\n"
                        break

                    ev_id = item.get("id")
                    if ev_id and ev_id <= last_seen_id:
                        # Skip events that were already delivered in the replay phase
                        continue
                    if ev_id:
                        last_seen_id = ev_id

                    ev_data = json.dumps(item)
                    level = item.get("level", "info")
                    yield f"id: {ev_id}\nevent: {level}\ndata: {ev_data}\n\n"

                except Empty:
                    # 15s Heartbeat ping to prevent proxy connection timeout
                    yield ": ping\n\n"

                    # Poll DB to check if job finished while idle
                    with get_db_session() as s:
                        current_job = s.query(Job).filter(Job.id == job_id).first()
                        if current_job and current_job.status in (
                            "succeeded",
                            "failed",
                            "partial",
                            "cancelled",
                        ):
                            if q.empty():
                                done_data = json.dumps({
                                    "status": current_job.status,
                                    "summary": current_job.summary,
                                })
                                yield f"event: done\ndata: {done_data}\n\n"
                                break

        finally:
            event_bus.unsubscribe(job_id, q)

    return Response(
        generate_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
