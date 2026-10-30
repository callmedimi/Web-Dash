"""Tests for Step 2.3: Realtime Server-Sent Events (SSE) streaming and Replay."""
import json
import time
import pytest
from backend.app import create_app
from backend.app.db.session import get_db_session
from backend.app.models.job import Job, JobTask, JobEvent
from backend.app.jobs.engine import engine
from backend.app.jobs.events import event_bus


@pytest.fixture
def app_client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


@pytest.fixture
def clean_jobs():
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.commit()
    yield
    with get_db_session() as s:
        s.query(JobEvent).delete()
        s.query(JobTask).delete()
        s.query(Job).delete()
        s.commit()


def test_submit_and_get_job(app_client, clean_jobs):
    """Test POST /api/v1/jobs and GET /api/v1/jobs/<id>."""
    res = app_client.post(
        "/api/v1/jobs",
        json={
            "type": "alarm_clear",
            "mode": "dry_run",
            "params": {"timeout": 30},
            "devices": ["ROUTER-A", "ROUTER-B"],
        },
    )
    assert res.status_code == 202
    data = res.get_json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Get job details
    res_get = app_client.get(f"/api/v1/jobs/{job_id}")
    assert res_get.status_code == 200
    job_data = res_get.get_json()
    assert job_data["id"] == job_id
    assert job_data["type"] == "alarm_clear"
    assert len(job_data["tasks"]) == 2


def test_submit_job_validation_and_read_only(app_client, clean_jobs, monkeypatch):
    """Test validation errors and read-only mode protection."""
    # 415 for non-JSON
    res_ct = app_client.post("/api/v1/jobs", data="not-json", content_type="text/plain")
    assert res_ct.status_code == 415

    # 400 for missing type
    res_type = app_client.post("/api/v1/jobs", json={"params": {}})
    assert res_type.status_code == 400
    assert res_type.get_json()["error"]["code"] == "VALIDATION_ERROR"

    # 403 on apply in read-only mode
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    res_ro = app_client.post("/api/v1/jobs", json={"type": "alarm_clear", "mode": "apply"})
    assert res_ro.status_code == 403
    assert res_ro.get_json()["error"]["code"] == "READ_ONLY"


def test_sse_historical_replay(app_client, clean_jobs):
    """Test that SSE replays past events from DB using ?since= or Last-Event-ID."""
    job_id = engine.submit("test_replay", {}, "tester", target_devices=["DEV-1"])

    with get_db_session() as s:
        ev1 = event_bus.publish_event(s, job_id, None, "info", "Event number 1")
        ev2 = event_bus.publish_event(s, job_id, None, "warning", "Event number 2")
        ev3 = event_bus.publish_event(s, job_id, None, "error", "Event number 3")
        # Mark job terminal so stream closes immediately after replay
        job = s.query(Job).filter(Job.id == job_id).first()
        job.status = "succeeded"
        job.summary = {"total": 1, "succeeded": 1}
        s.commit()
        ev1_id = ev1.id

    # Stream with no pointer -> receives all 3 events + done
    res = app_client.get(f"/api/v1/jobs/{job_id}/events")
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    content = res.get_data(as_text=True)
    assert "Event number 1" in content
    assert "Event number 2" in content
    assert "Event number 3" in content
    assert "event: done" in content

    # Stream with Last-Event-ID = ev1_id -> replays ONLY event 2 & 3
    res_replay = app_client.get(
        f"/api/v1/jobs/{job_id}/events",
        headers={"Last-Event-ID": str(ev1_id)},
    )
    replay_content = res_replay.get_data(as_text=True)
    assert "Event number 1" not in replay_content
    assert "Event number 2" in replay_content
    assert "Event number 3" in replay_content
    assert "event: done" in replay_content


def test_sse_not_found(app_client, clean_jobs):
    """Test 404 on non-existent job events stream."""
    res = app_client.get("/api/v1/jobs/non-existent-uuid/events")
    assert res.status_code == 404


def test_job_cancel_endpoint(app_client, clean_jobs):
    """Test POST /api/v1/jobs/<id>/cancel."""
    job_id = engine.submit("cancel_test", {}, "tester", target_devices=["DEV-1", "DEV-2"])

    res = app_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert res.status_code == 200
    assert res.get_json()["status"] == "cancelling"

    # Verify DB state
    with get_db_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        assert job.status == "cancelling"
        tasks = s.query(JobTask).filter(JobTask.job_id == job_id).all()
        assert all(t.status == "cancelled" for t in tasks)


def test_sse_multiple_subscribers_concurrent(clean_jobs):
    """Test that two simultaneous subscribers to the same job receive all events."""
    job_id = engine.submit("multi_sub_test", {}, "tester", target_devices=["DEV-1"])

    q1 = event_bus.subscribe(job_id)
    q2 = event_bus.subscribe(job_id)

    with get_db_session() as s:
        event_bus.publish_event(s, job_id, None, "info", "Concurrent event 1")
        event_bus.publish_event(s, job_id, None, "info", "Concurrent event 2")

    item1_q1 = q1.get_nowait()
    item2_q1 = q1.get_nowait()
    item1_q2 = q2.get_nowait()
    item2_q2 = q2.get_nowait()

    assert "Concurrent event 1" in item1_q1["message"]
    assert "Concurrent event 2" in item2_q1["message"]
    assert "Concurrent event 1" in item1_q2["message"]
    assert "Concurrent event 2" in item2_q2["message"]

    event_bus.unsubscribe(job_id, q1)
    event_bus.unsubscribe(job_id, q2)
