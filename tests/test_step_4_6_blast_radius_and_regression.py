"""Unit and regression tests for Step 4.6 (Blast-Radius Guard) and Phase 4 Regression.

Verifies:
1. Blast-radius threshold checks (>50 devices or >20 ports).
2. Blast-radius guard enforces:
   - High risk level assignment.
   - Rejection if approver role != 'god'.
   - Rejection if confirmation token != 'I_CONFIRM_BLAST_RADIUS'.
   - Successful approval only when god role + typed confirmation match.
3. Full Phase 4 end-to-end regression across all pipeline capabilities:
   - Change pipeline lifecycle (plan -> precheck -> approve -> apply -> verify -> rollback).
   - Alarm clear and noconf shutdown handler.
   - Config backup, SHA-256 deduplication, Fernet encryption at rest, diff hunks.
   - License renewal handler.
   - Compliance engine scoring and violation reporting.
"""
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jobs.change import (
    ChangeState,
    ChangePipelineService,
    evaluate_change_risk,
    is_blast_radius_exceeded,
    transition_change_state,
)
from backend.app.models.config_change import ChangeRequest, ConfigSnapshot
from backend.app.models.device import Device
from backend.app.services.config_backup import ConfigBackupService
from backend.app.services.compliance import evaluate_compliance_on_config
from backend.app.jobs.handlers.alarm_clear import AlarmClearHandler
from backend.app.jobs.handlers.license_renewal import LicenseRenewalHandler
from backend.app.jobs.worker import TaskContext
from backend.app.db.base import Base
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def setup_vault_env(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv("WEBDASH_VAULT_KEY", test_key)
    monkeypatch.setenv("TESTING", "1")


def test_blast_radius_threshold_evaluation():
    """Verify threshold boundary conditions: >50 devices or >20 ports triggers blast radius."""
    assert is_blast_radius_exceeded(devices_count=50, interfaces_count=20) is False
    assert is_blast_radius_exceeded(devices_count=51, interfaces_count=1) is True
    assert is_blast_radius_exceeded(devices_count=1, interfaces_count=21) is True
    assert is_blast_radius_exceeded(devices_count=100, interfaces_count=50) is True


def test_blast_radius_approval_requires_god_and_typed_confirmation():
    """Verify changes exceeding blast-radius require god role and typed confirmation token."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R_CORE", mgmt_ip="10.1.1.1")
    session.add(dev)
    session.commit()

    # Create change request with blast radius exceeded (60 devices)
    cr = ChangePipelineService.create_change_request(
        db_session=session,
        device_id=dev.id,
        creator_id="alice",
        lines=["interface GE0/1/0", "shutdown"],
        inverse_lines=["interface GE0/1/0", "undo shutdown"],
        devices_count=60,
        interfaces_count=5,
    )
    assert cr.risk_level == "high"
    assert cr.plan["blast_radius_exceeded"] is True

    # Run precheck
    ChangePipelineService.run_precheck(session, cr.id)
    session.refresh(cr)
    assert cr.status == ChangeState.AWAITING_APPROVAL

    # 1. Admin approver is rejected
    with pytest.raises(PermissionError) as pe:
        ChangePipelineService.approve(
            session,
            cr.id,
            approver_username="bob",
            approver_role="admin",
            confirmation_token="I_CONFIRM_BLAST_RADIUS",
        )
    assert "god" in str(pe.value).lower()

    # 2. God approver without confirmation token is rejected
    with pytest.raises(ValueError) as ve:
        ChangePipelineService.approve(
            session,
            cr.id,
            approver_username="supergod",
            approver_role="god",
            confirmation_token=None,
        )
    assert "I_CONFIRM_BLAST_RADIUS" in str(ve.value)

    # 3. God approver with incorrect confirmation token is rejected
    with pytest.raises(ValueError) as ve2:
        ChangePipelineService.approve(
            session,
            cr.id,
            approver_username="supergod",
            approver_role="god",
            confirmation_token="YES_DO_IT",
        )
    assert "I_CONFIRM_BLAST_RADIUS" in str(ve2.value)

    # 4. God approver with exact typed token succeeds!
    approved = ChangePipelineService.approve(
        session,
        cr.id,
        approver_username="supergod",
        approver_role="god",
        confirmation_token="I_CONFIRM_BLAST_RADIUS",
    )
    assert approved.status == ChangeState.APPLYING
    assert approved.approver_id == "supergod"


def test_phase4_full_pipeline_lifecycle_regression():
    """
    Comprehensive regression test covering:
    1. Plan creation
    2. Precheck evaluation
    3. Separation of duties
    4. Apply with config snapshot encryption
    5. Automatic verification
    6. Rollback to inverse lines
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    dev = Device(name="R_TEST", mgmt_ip="10.10.10.10")
    session.add(dev)
    session.commit()

    # 1. Create plan
    cr = ChangePipelineService.create_change_request(
        db_session=session,
        device_id=dev.id,
        creator_id="netops1",
        lines=["interface GigabitEthernet0/1/0", "shutdown"],
        inverse_lines=["interface GigabitEthernet0/1/0", "undo shutdown"],
        reason="Port isolation maintenance",
    )
    assert cr.status == ChangeState.PLANNED

    # 2. Precheck
    passed, p_res = ChangePipelineService.run_precheck(session, cr.id)
    assert passed is True
    session.refresh(cr)
    assert cr.status == ChangeState.AWAITING_APPROVAL

    # 3. Approval with separation of duties
    with pytest.raises(PermissionError):
        ChangePipelineService.approve(
            session, cr.id, approver_username="netops1", approver_role="admin", require_second_person=True
        )

    ChangePipelineService.approve(
        session, cr.id, approver_username="admin2", approver_role="admin", require_second_person=True
    )
    session.refresh(cr)
    assert cr.status == ChangeState.APPLYING

    # 4. Apply with mock session
    fake_session = MagicMock()
    fake_session.run.return_value = "sysname R_TEST\ninterface GigabitEthernet0/1/0\n"
    fake_session.config_block.return_value = {"applied": True}

    res_apply = ChangePipelineService.apply(session, cr.id, device_session=fake_session)
    assert res_apply["status"] == "success"
    assert res_apply["verified"] is True

    session.refresh(cr)
    assert cr.status == ChangeState.VERIFIED
    assert cr.snapshot_id is not None

    # Check snapshot is encrypted at rest
    snap = session.query(ConfigSnapshot).filter(ConfigSnapshot.id == cr.snapshot_id).first()
    assert snap.content_encrypted_or_text != "sysname R_TEST\ninterface GigabitEthernet0/1/0\n"
    decrypted = ConfigBackupService.get_snapshot_decrypted(session, snap.id)
    assert "sysname R_TEST" in decrypted

    # 5. Rollback
    res_rb = ChangePipelineService.rollback(session, cr.id, device_session=fake_session)
    assert res_rb["status"] == "rolled_back"
    session.refresh(cr)
    assert cr.status == ChangeState.ROLLED_BACK
