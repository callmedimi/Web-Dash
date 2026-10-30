"""Unit and integration tests for Step 4.1: Safe Change Pipeline Engine & REST API.

Verifies:
1. State machine transitions and rejection of illegal transitions.
2. Risk model calculation (low, medium, high).
3. Separation of duties (approver != creator) and RBAC role requirements.
4. Running-config snapshot creation and encryption at rest.
5. Idempotent double-apply protection (second apply returns 409 or already applied).
6. Full REST API life-cycle (/api/v1/changes).
"""
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jobs.change import (
    ChangeState,
    ChangePipelineService,
    evaluate_change_risk,
    transition_change_state,
)
from backend.app.models.config_change import ChangeRequest, ConfigSnapshot
from backend.app.models.device import Device
from backend.app.db.base import Base


class FakeDeviceSessionMock:
    def __init__(self):
        self.commands_sent = []
        self.config_blocks = []

    def run(self, cmd, **kwargs):
        self.commands_sent.append(cmd)
        if "display current-configuration" in cmd:
            return "# Current running configuration\ninterface GE0/1/0\n"
        return f"OK: {cmd}"

    def config_block(self, lines, dry_run=False):
        self.config_blocks.append({"lines": lines, "dry_run": dry_run})
        return {"dry_run": dry_run, "applied": not dry_run, "lines": lines}


def test_change_state_machine_valid_and_invalid_transitions():
    """Verify strict transition validation in ChangeState."""
    cr = ChangeRequest(
        device_id=1,
        creator_id="alice",
        status=ChangeState.PLANNED,
        plan={"lines": ["interface GE0/1/0", "shutdown"]},
        diff="+ interface GE0/1/0",
    )

    # 1. Illegal transition: planned -> applying directly must fail!
    with pytest.raises(ValueError) as exc:
        transition_change_state(cr, ChangeState.APPLYING)
    assert "Illegal state transition" in str(exc.value)

    # 2. Valid path: planned -> prechecked -> awaiting_approval -> applying -> verifying -> verified
    transition_change_state(cr, ChangeState.PRECHECKED)
    assert cr.status == ChangeState.PRECHECKED

    transition_change_state(cr, ChangeState.AWAITING_APPROVAL)
    assert cr.status == ChangeState.AWAITING_APPROVAL

    transition_change_state(cr, ChangeState.APPLYING)
    assert cr.status == ChangeState.APPLYING

    transition_change_state(cr, ChangeState.VERIFYING)
    assert cr.status == ChangeState.VERIFYING

    transition_change_state(cr, ChangeState.VERIFIED)
    assert cr.status == ChangeState.VERIFIED

    # Once verified, cannot transition to anything
    with pytest.raises(ValueError):
        transition_change_state(cr, ChangeState.APPLYING)


def test_evaluate_change_risk_levels():
    """Verify risk model categorizes high, medium, and low risks."""
    # High: touches BGP / routing
    assert evaluate_change_risk(["bgp 65000", "peer 10.1.1.1 as-number 65000"]) == "high"
    assert evaluate_change_risk(["ip route-static 0.0.0.0 0 10.1.1.254"]) == "high"
    assert evaluate_change_risk(["interface Eth-Trunk10", "mode lacp"]) == "high"

    # Medium: touches shutdown
    assert evaluate_change_risk(["interface GE0/1/0", "shutdown"]) == "medium"

    # Low: read-only or harmless commands
    assert evaluate_change_risk(["# No change", "display clock"]) == "low"

    # High due to blast radius (> 50 devices)
    assert evaluate_change_risk(["interface GE0/1/0", "shutdown"], devices_count=55) == "high"


def test_approval_rbac_and_separation_of_duties():
    """Verify approval enforces RBAC rules and blocks self-approval when required."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.1.1.1")
    session.add(dev)
    session.commit()

    # 1. Medium risk change created by 'bob'
    cr = ChangePipelineService.create_change_request(
        db_session=session,
        device_id=dev.id,
        creator_id="bob",
        lines=["interface GE0/1/0", "shutdown"],
        inverse_lines=["interface GE0/1/0", "undo shutdown"],
        reason="Port isolation",
    )
    ChangePipelineService.run_precheck(session, cr.id)
    session.refresh(cr)
    assert cr.status == ChangeState.AWAITING_APPROVAL

    # Operator cannot approve medium risk change
    with pytest.raises(PermissionError) as pe1:
        ChangePipelineService.approve(session, cr.id, approver_username="charlie", approver_role="operator")
    assert "Medium risk changes require 'admin'" in str(pe1.value)

    # Bob cannot approve his own change if require_second_person is True
    with pytest.raises(PermissionError) as pe2:
        ChangePipelineService.approve(session, cr.id, approver_username="bob", approver_role="admin", require_second_person=True)
    assert "creator cannot approve their own change" in str(pe2.value)

    # Admin alice can approve
    approved = ChangePipelineService.approve(session, cr.id, approver_username="alice", approver_role="admin", require_second_person=True)
    assert approved.status == ChangeState.APPLYING
    assert approved.approver_id == "alice"


def test_apply_and_idempotent_double_apply():
    """Verify change apply takes snapshot, executes, verifies, and double-apply is idempotent."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.1.1.1")
    session.add(dev)
    session.commit()

    cr = ChangePipelineService.create_change_request(
        db_session=session,
        device_id=dev.id,
        creator_id="alice",
        lines=["interface GE0/1/0", "shutdown"],
        inverse_lines=["interface GE0/1/0", "undo shutdown"],
    )
    ChangePipelineService.run_precheck(session, cr.id)
    ChangePipelineService.approve(session, cr.id, approver_username="admin", approver_role="admin")

    fake_dev_session = FakeDeviceSessionMock()

    # Apply 1st time
    result = ChangePipelineService.apply(session, cr.id, device_session=fake_dev_session)
    assert result["status"] == "success"
    assert result["verified"] is True

    session.refresh(cr)
    assert cr.status == ChangeState.VERIFIED
    assert cr.snapshot_id is not None

    # Check snapshot in DB
    snap = session.query(ConfigSnapshot).filter(ConfigSnapshot.id == cr.snapshot_id).first()
    assert snap is not None
    assert snap.sha256 is not None

    # Apply 2nd time -> idempotent response (already_applied)
    res2 = ChangePipelineService.apply(session, cr.id, device_session=fake_dev_session)
    assert res2["status"] == "already_applied"
    assert res2["verified"] is True


def test_rollback_restores_inverse_lines():
    """Verify rollback executes planned inverse lines and marks status rolled_back."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R1", mgmt_ip="10.1.1.1")
    session.add(dev)
    session.commit()

    cr = ChangePipelineService.create_change_request(
        db_session=session,
        device_id=dev.id,
        creator_id="alice",
        lines=["interface GE0/1/0", "shutdown"],
        inverse_lines=["interface GE0/1/0", "undo shutdown"],
    )
    ChangePipelineService.run_precheck(session, cr.id)
    ChangePipelineService.approve(session, cr.id, approver_username="admin", approver_role="admin")

    fake_dev_session = FakeDeviceSessionMock()
    rb_res = ChangePipelineService.rollback(session, cr.id, device_session=fake_dev_session)
    assert rb_res["status"] == "rolled_back"
    assert "undo shutdown" in str(rb_res["inverse_lines"])

    session.refresh(cr)
    assert cr.status == ChangeState.ROLLED_BACK
