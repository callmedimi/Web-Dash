"""Unit and golden tests for Step 4.2: Alarm Clear & Noconf Shutdown Pipeline Handler.

Verifies:
1. Strict decision table enforcement:
   - Admin-down -> CLEAR_ONLY
   - Empty/error config -> SKIP (CONFIG_UNREADABLE, F-20)
   - Sub-interface -> targets sub-interface only (F-21)
   - Ambiguous interface -> SKIP (AMBIGUOUS_OR_NO_INTERFACE)
   - Verified noconf -> SHUTDOWN_THEN_CLEAR
2. Rollback when shutdown verification fails.
3. Explicit confirmation logic (F-23): 'success' -> CLEARED, 'not found' -> NOT_PRESENT.
4. Alarm MDP view failure safety latch (F-24).
5. Plan/dry_run mode execution without side-effects.
6. Registration and execution through JobEngine.
"""
import pytest
from unittest.mock import MagicMock

from backend.app.jobs.handlers.alarm_clear import AlarmClearHandler
from backend.app.jobs.worker import TaskContext
from backend.app.jobs.engine import JobEngine


class MockConnection:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.commands_sent = []

    def send_command(self, cmd, expect_string=None):
        self.commands_sent.append(cmd)
        for pattern, resp in sorted(self.responses.items(), key=lambda x: len(x[0]), reverse=True):
            if pattern in cmd:
                return resp
        return "OK"


class MockDeviceSession:
    def __init__(self, run_responses=None, conn_responses=None):
        self.run_responses = run_responses or {}
        self.conn = MockConnection(conn_responses)
        self.commands_run = []
        self.config_blocks_run = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def run(self, cmd, **kwargs):
        self.commands_run.append((cmd, kwargs))
        if cmd == "display_alarm_active":
            return self.run_responses.get("display_alarm_active", "")
        if cmd == "display_interface":
            iface = kwargs.get("interface", "")
            return self.run_responses.get(f"display_interface_{iface}", self.run_responses.get("display_interface", ""))
        if cmd == "display_current_config_interface":
            iface = kwargs.get("interface", "")
            return self.run_responses.get(f"display_config_{iface}", self.run_responses.get("display_current_config_interface", ""))
        return "OK"

    def config_block(self, lines, dry_run=False):
        self.config_blocks_run.append({"lines": lines, "dry_run": dry_run})
        return {"dry_run": dry_run, "applied": not dry_run, "lines": lines}


def test_alarm_clear_no_active_alarms():
    """Verify handler gracefully skips when no alarms are active."""
    session_mock = MockDeviceSession(run_responses={"display_alarm_active": ""})
    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-1"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["status"] == "skipped"
    assert res["reason"] == "NO_ACTIVE_ALARMS"
    assert res["alarms_cleared"] == 0
    assert res["interfaces_shutdown"] == 0


def test_alarm_clear_ambiguous_alarm_skipped():
    """Verify alarm with ambiguous or missing interface reference is skipped."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "101       0x09100001 2     2026-10-30 14:00:00               System power module 1 failure\n"
    )
    session_mock = MockDeviceSession(run_responses={"display_alarm_active": raw_alarms})
    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-1"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["alarms_cleared"] == 0
    assert len(res["entries"]) == 1
    assert res["entries"][0]["decision"] == "SKIP"
    assert res["entries"][0]["reason_code"] == "AMBIGUOUS_OR_NO_INTERFACE"


def test_alarm_clear_subinterface_strict_handling():
    """F-21: Verify sub-interface alarm operates strictly on sub-interface and not parent."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "202       0x09100002 2     2026-10-30 14:00:00               Interface GigabitEthernet0/1/0.100 physical state is DOWN\n"
    )
    iface_raw = (
        "GigabitEthernet0/1/0.100 current state : Administratively DOWN\n"
        "Line protocol current state : DOWN\n"
        "Description: \n"
    )
    conn_responses = {
        "system-view": "[R1]",
        "alarm": "[R1-alarm]",
        "clear alarm active": "Clear alarm active sequence-number 202 successfully.",
        "return": "<R1>",
    }
    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/0.100": iface_raw,
            "display_config_GigabitEthernet0/1/0.100": "#\ninterface GigabitEthernet0/1/0.100\n#\nreturn",
        },
        conn_responses=conn_responses,
    )

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-sub"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["status"] == "success"
    assert res["alarms_cleared"] == 1
    assert res["interfaces_shutdown"] == 0

    entry = res["entries"][0]
    assert entry["interface"] == "GigabitEthernet0/1/0.100"
    assert entry["decision"] == "CLEAR_ONLY"
    assert entry["status"] == "CLEARED"


def test_alarm_clear_unreadable_config_guard():
    """F-20: Unreadable config or CLI error banner MUST NEVER shutdown interface."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "303       0x09100003 2     2026-10-30 14:00:00               Loss of signal on GigabitEthernet0/1/1\n"
    )
    iface_raw = (
        "GigabitEthernet0/1/1 current state : DOWN\n"
        "Line protocol current state : DOWN\n"
    )
    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/1": iface_raw,
            "display_config_GigabitEthernet0/1/1": "% Error: Unrecognized command found at '^' position.",
        }
    )

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-unreadable"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert len(session_mock.config_blocks_run) == 0  # Absolutely NO shutdown commands
    entry = res["entries"][0]
    assert entry["decision"] == "SKIP"
    assert entry["reason_code"] == "CONFIG_UNREADABLE"


def test_alarm_clear_verified_noconf_shutdown_and_clear():
    """Verified noconf port: shuts down, verifies admin down, clears alarm."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "404       0x09100004 2     2026-10-30 14:00:00               GigabitEthernet0/1/2 is DOWN\n"
    )
    initial_iface_raw = (
        "GigabitEthernet0/1/2 current state : DOWN\n"
        "Line protocol current state : DOWN\n"
        "Description: \n"
    )
    verified_iface_raw = (
        "GigabitEthernet0/1/2 current state : Administratively DOWN\n"
        "Line protocol current state : DOWN\n"
        "Description: \n"
    )
    noconf_cfg = "#\ninterface GigabitEthernet0/1/2\n#\nreturn"

    def dynamic_run(cmd, **kwargs):
        session_mock.commands_run.append((cmd, kwargs))
        if cmd == "display_alarm_active":
            return raw_alarms
        if cmd == "display_interface":
            if session_mock.config_blocks_run:
                return verified_iface_raw
            return initial_iface_raw
        if cmd == "display_current_config_interface":
            return noconf_cfg
        return "OK"

    session_mock = MockDeviceSession(
        conn_responses={
            "system-view": "[R1]",
            "alarm": "[R1-alarm]",
            "clear alarm active": "Clear alarm active sequence-number 404 successfully.",
            "return": "<R1>",
        }
    )
    session_mock.run = dynamic_run

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-noconf"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["status"] == "success"
    assert res["interfaces_shutdown"] == 1
    assert res["alarms_cleared"] == 1
    assert session_mock.config_blocks_run[0]["lines"] == ["interface GigabitEthernet0/1/2", "shutdown"]


def test_alarm_clear_shutdown_verify_failure_triggers_rollback():
    """Verify shutdown verification failure triggers rollback 'undo shutdown' and aborts clear."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "505       0x09100005 2     2026-10-30 14:00:00               GigabitEthernet0/1/3 is DOWN\n"
    )
    iface_raw = (
        "GigabitEthernet0/1/3 current state : DOWN\n"
        "Line protocol current state : DOWN\n"
    )
    noconf_cfg = "#\ninterface GigabitEthernet0/1/3\n#\nreturn"

    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/3": iface_raw,
            "display_config_GigabitEthernet0/1/3": noconf_cfg,
        }
    )

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-rollback"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["interfaces_shutdown"] == 0
    assert res["alarms_cleared"] == 0

    blocks = [b["lines"] for b in session_mock.config_blocks_run]
    assert ["interface GigabitEthernet0/1/3", "shutdown"] in blocks
    assert ["interface GigabitEthernet0/1/3", "undo shutdown"] in blocks


def test_alarm_clear_explicit_confirmation_and_not_present():
    """F-23: Explicit confirmation 'success' -> CLEARED; 'not exist' -> NOT_PRESENT."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "601       0x09100006 2     2026-10-30 14:00:00               GigabitEthernet0/1/4 is Administratively DOWN\n"
        "602       0x09100007 2     2026-10-30 14:00:00               GigabitEthernet0/1/5 is Administratively DOWN\n"
    )
    admin_down = "GigabitEthernet0/1/4 current state : Administratively DOWN\nLine protocol current state : DOWN\n"

    def dynamic_send_cmd(cmd, expect_string=None):
        session_mock.conn.commands_sent.append(cmd)
        if "sequence-number 601" in cmd:
            return "Clear alarm active sequence-number 601 successfully."
        if "sequence-number 602" in cmd:
            return "Error: Alarm 602 does not exist."
        return "[R1]"

    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/4": admin_down,
            "display_interface_GigabitEthernet0/1/5": admin_down,
            "display_config_GigabitEthernet0/1/4": "#\nreturn",
            "display_config_GigabitEthernet0/1/5": "#\nreturn",
        }
    )
    session_mock.conn.send_command = dynamic_send_cmd

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-conf"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["alarms_cleared"] == 1  # 601 counted, 602 NOT counted!
    entries = {e["sequence"]: e for e in res["entries"]}
    assert entries[601]["status"] == "CLEARED"
    assert entries[601]["verified"] is True
    assert entries[602]["status"] == "NOT_PRESENT"
    assert entries[602]["verified"] is False


def test_alarm_clear_alarm_view_unavailable_fails_task():
    """F-24: Failure to enter alarm MDP view halts task with ALARM_VIEW_UNAVAILABLE."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "701       0x09100008 2     2026-10-30 14:00:00               GigabitEthernet0/1/6 is Administratively DOWN\n"
    )
    admin_down = "GigabitEthernet0/1/6 current state : Administratively DOWN\nLine protocol current state : DOWN\n"

    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/6": admin_down,
            "display_config_GigabitEthernet0/1/6": "#\nreturn",
        },
        conn_responses={
            "system-view": "[R1]",
            "alarm": "% Error: Unrecognized command 'alarm'.",
            "return": "<R1>",
        },
    )

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {}
    ctx.job_id = "job-noview"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["status"] == "failed"
    assert res["error"] == "ALARM_VIEW_UNAVAILABLE"
    assert res["alarms_cleared"] == 0
    assert not any("clear alarm active" in cmd for cmd in session_mock.conn.commands_sent)


def test_alarm_clear_dry_run_mode_produces_plan_only():
    """In dry_run / plan mode, no commands that modify router state are run."""
    raw_alarms = (
        "Sequence  AlarmId    Level Date       Time                   Description\n"
        "------------------------------------------------------------------------------------------------------------------------\n"
        "801       0x09100009 2     2026-10-30 14:00:00               GigabitEthernet0/1/7 is DOWN\n"
    )
    down_iface = "GigabitEthernet0/1/7 current state : DOWN\nLine protocol current state : DOWN\n"
    noconf_cfg = "#\ninterface GigabitEthernet0/1/7\n#\nreturn"

    session_mock = MockDeviceSession(
        run_responses={
            "display_alarm_active": raw_alarms,
            "display_interface_GigabitEthernet0/1/7": down_iface,
            "display_config_GigabitEthernet0/1/7": noconf_cfg,
        }
    )

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "dry_run"
    ctx.params = {}
    ctx.job_id = "job-plan"

    res = AlarmClearHandler.run_task(ctx, session=session_mock)
    assert res["status"] == "planned"
    assert res["interfaces_shutdown"] == 1
    assert res["alarms_cleared"] == 0
    assert len(session_mock.config_blocks_run) == 0
    assert len(session_mock.conn.commands_sent) == 0
    assert res["entries"][0]["status"] == "PLANNED"


def test_job_engine_has_alarm_clear_handler():
    """Verify JobEngine has alarm_clear handler registered by default."""
    engine = JobEngine(max_workers=1)
    assert "alarm_clear" in engine._handlers
    assert engine._handlers["alarm_clear"] == AlarmClearHandler.run_task
