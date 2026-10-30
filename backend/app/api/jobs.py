"""Job management API and Realtime Server-Sent Events (SSE) streaming (Step 2.3).
Compliant with Target Architecture §4 conventions.
"""
import json
import logging
from queue import Empty
from typing import Optional
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

jobs_bp = Blueprint("jobs_api", __name__, url_prefix="/api/v1/jobs")


def _get_current_username() -> str:
    """Extract authenticated username from Flask session or default to anonymous."""
    user = flask_session.get("user")
    if isinstance(user, dict):
        return user.get("username", "anonymous")
    return str(user) if user else "system"


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

    job_id = engine.submit(
        job_type=job_type,
        params=params,
        user=_get_current_username(),
        mode=mode,
        target_devices=devices if devices else ["default"],
    )

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    """
    List jobs with pagination and filters (Target Architecture §4).
    ?page=1&page_size=20&status=&type=
    """
    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", 20, type=int)))
    status = request.args.get("status")
    job_type = request.args.get("type")

    with get_db_session() as s:
        query = s.query(Job)
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
    """Get single job details and task status."""
    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job:
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
    """Cancel an active or queued job."""
    with get_db_session() as s:
        success = request_job_cancellation(s, job_id)
        if not success:
            job = s.query(Job).filter(Job.id == job_id).first()
            if not job:
                return jsonify({"error": {"code": "NOT_FOUND", "message": "Job not found"}}), 404
            return jsonify({"status": job.status, "message": f"Job is already in status '{job.status}'"}), 400

        return jsonify({"status": "cancelling", "job_id": job_id}), 200


@jobs_bp.route("/<job_id>/events", methods=["GET"])
def stream_job_events(job_id: str):
    """
    Stream job events as Server-Sent Events (SSE).
    Supports Last-Event-ID header and ?since= parameter for event replay.
    Multiple clients/tabs supported without interference.
    Heartbeat comment every 15s to keep connections alive through proxies.
    Closes with event: done when job reaches terminal state.
    """
    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": {"code": "NOT_FOUND", "message": "Job not found"}}), 404

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
