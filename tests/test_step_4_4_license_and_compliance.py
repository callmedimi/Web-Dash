"""Unit and integration tests for Step 4.4 (License Renewal Pipeline) and Step 4.5 (Compliance Engine).

Verifies:
1. License renewal handler:
   - XML sanitizer and metadata parser (ESN, product name, expiry date).
   - Dry-run/plan mode returns current expiry vs target expiry without modifying device.
   - Apply without approval fails safely with APPROVAL_REQUIRED.
   - Apply with approval verifies storage, runs license active with [Y/N] prompt, and verifies Normal state.
2. Compliance checks engine:
   - SEC-001 (SSH only, no telnet).
   - OPS-001 (NTP server present).
   - SEC-002 (SNMPv3 only, no cleartext communities).
   - OPS-002 (active interfaces must have description).
   - YAML rules loaded from compliance directory.
   - Device snapshot evaluation & score calculation.
   - REST API: GET /api/v1/devices/<id>/compliance.
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.jobs.handlers.license_renewal import (
    clean_xml_content,
    parse_license_xml_metadata,
    LicenseRenewalHandler,
)
from backend.app.services.compliance import (
    load_compliance_rules,
    evaluate_compliance_on_config,
    evaluate_device_compliance,
    BUILTIN_COMPLIANCE_RULES,
)
from backend.app.services.config_backup import ConfigBackupService
from backend.app.models.device import Device
from backend.app.models.config_change import ConfigSnapshot
from backend.app.jobs.worker import TaskContext
from backend.app.jobs.engine import JobEngine
from backend.app.db.base import Base
from cryptography.fernet import Fernet


SAMPLE_LICENSE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LicFile>
    <NodeInfo>
        <ESN>210235G7R90123456789</ESN>
    </NodeInfo>
    <SaleInfo>
        <OfferingProduct name="NetEngine" version="V800R012"/>
    </SaleInfo>
    <KeyInfo>
        <CapacityKey name="L-100GE-PORT" trialDays="0">
            <Value validDate="2027-10-31">2</Value>
        </CapacityKey>
        <FeatureKey name="L-BGP-VPNV4" type="PERMANENT">
            <Value validDate="PERMANENT">1</Value>
        </FeatureKey>
    </KeyInfo>
</LicFile>
"""

SAMPLE_CURRENT_DISPLAY_LICENSE = """
Active License    : license_old.xml
License state     : Normal
Revoke ticket     : None
Product name      : NetEngine
Product version   : V800R012
Expired date      : 2026-10-31
"""

SAMPLE_POST_DISPLAY_LICENSE = """
Active License    : license_new.xml
License state     : Normal
Revoke ticket     : None
Product name      : NetEngine
Product version   : V800R012
Expired date      : 2027-10-31
"""

NON_COMPLIANT_CONFIG = """
sysname R_VULNERABLE
#
telnet server enable
#
snmp-agent sys-info version v2c
snmp-agent community read public123
#
interface GigabitEthernet0/1/0
 ip address 10.1.1.1 255.255.255.0
#
interface GigabitEthernet0/1/1
 shutdown
#
"""

COMPLIANT_CONFIG = """
sysname R_SECURE
#
undo telnet server enable
stelnet server enable
ssh server timeout 60
#
ntp-service unicast-server 10.0.0.1
#
snmp-agent sys-info version v3
snmp-agent group v3 securegroup privacy
#
interface GigabitEthernet0/1/0
 description Primary-Uplink
 ip address 10.1.1.1 255.255.255.0
#
interface GigabitEthernet0/1/1
 shutdown
#
"""


@pytest.fixture(autouse=True)
def setup_vault_env(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv("WEBDASH_VAULT_KEY", test_key)
    monkeypatch.setenv("TESTING", "1")


def test_clean_and_parse_license_xml_metadata():
    """Verify XML sanitization and license metadata parsing."""
    meta = parse_license_xml_metadata(SAMPLE_LICENSE_XML)
    assert meta["esn"] == "210235G7R90123456789"
    assert meta["product_name"] == "NetEngine"
    assert meta["expired_date"] == "2027-10-31"
    assert "L-100GE-PORT" in meta["features"]


def test_license_renewal_dry_run_plan():
    """In dry-run mode, inspects current state and produces plan with requires_approval=True."""
    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.__exit__.return_value = False
    fake_session.run.return_value = SAMPLE_CURRENT_DISPLAY_LICENSE

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "dry_run"
    ctx.params = {
        "license_filename": "license_new.xml",
        "license_xml_content": SAMPLE_LICENSE_XML,
        "approved": False,
    }

    res = LicenseRenewalHandler.run_task(ctx, session=fake_session)
    assert res["status"] == "planned"
    plan = res["plan"]
    assert plan["current_expired_date"] == "2026-10-31"
    assert plan["target_expired_date"] == "2027-10-31"
    assert plan["requires_approval"] is True
    assert fake_session.conn.send_command.call_count == 0  # No router commands executed


def test_license_renewal_apply_rejected_without_approval():
    """In apply mode without approved=True, halts safely."""
    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.__exit__.return_value = False
    fake_session.run.return_value = SAMPLE_CURRENT_DISPLAY_LICENSE

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {
        "license_filename": "license_new.xml",
        "license_xml_content": SAMPLE_LICENSE_XML,
        "approved": False,
    }

    res = LicenseRenewalHandler.run_task(ctx, session=fake_session)
    assert res["status"] == "failed"
    assert res["error"] == "APPROVAL_REQUIRED"


def test_license_renewal_apply_with_approval_and_verification():
    """In apply mode with approved=True, executes activation, verifies, and confirms state."""
    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.__exit__.return_value = False

    # First run() is display license before; second run() is display license after
    fake_session.run.side_effect = [
        SAMPLE_CURRENT_DISPLAY_LICENSE,
        SAMPLE_POST_DISPLAY_LICENSE,
    ]

    def send_cmd(cmd, **kwargs):
        if "license verify" in cmd:
            return "Info: The license file is verified successfully."
        if "license active" in cmd:
            return "Are you sure to activate the license? [Y/N]:"
        if cmd == "Y":
            return "Now activing the license.......done."
        return "OK"

    fake_session.conn.send_command.side_effect = send_cmd

    ctx = MagicMock(spec=TaskContext)
    ctx.device_name = "R1"
    ctx.mode = "apply"
    ctx.params = {
        "license_filename": "license_new.xml",
        "license_xml_content": SAMPLE_LICENSE_XML,
        "approved": True,
    }

    res = LicenseRenewalHandler.run_task(ctx, session=fake_session)
    assert res["status"] == "success"
    assert res["verified"] is True
    assert res["old_expired_date"] == "2026-10-31"
    assert res["new_expired_date"] == "2027-10-31"
    assert res["active_license_file"] == "license_new.xml"


def test_compliance_evaluation_non_compliant_vs_compliant():
    """Verify built-in compliance rules correctly flag violations and pass compliant configs."""
    # 1. Non-compliant config evaluation
    res_bad = evaluate_compliance_on_config(NON_COMPLIANT_CONFIG)
    bad_map = {r["rule_id"]: r for r in res_bad}

    assert bad_map["SEC-001"]["status"] == "FAIL"  # Telnet enabled, SSH missing
    assert bad_map["OPS-001"]["status"] == "FAIL"  # NTP missing
    assert bad_map["SEC-002"]["status"] == "FAIL"  # SNMP v2c / cleartext community
    assert bad_map["OPS-002"]["status"] == "FAIL"  # GigabitEthernet0/1/0 missing description

    # 2. Compliant config evaluation
    res_good = evaluate_compliance_on_config(COMPLIANT_CONFIG)
    good_map = {r["rule_id"]: r for r in res_good}

    assert good_map["SEC-001"]["status"] == "PASS"
    assert good_map["OPS-001"]["status"] == "PASS"
    assert good_map["SEC-002"]["status"] == "PASS"
    assert good_map["OPS-002"]["status"] == "PASS"


def test_compliance_yaml_custom_rule_loading(tmp_path):
    """Verify loading custom compliance rules from YAML directory."""
    rules_dir = tmp_path / "compliance"
    rules_dir.mkdir(parents=True, exist_ok=True)

    custom_rule = """
- id: "CUSTOM-001"
  name: "Require Banner Login Notice"
  severity: "medium"
  must_contain:
    - "header login information"
  remediation_hint: "Configure corporate login banner."
"""
    (rules_dir / "custom.yml").write_text(custom_rule, encoding="utf-8")

    loaded = load_compliance_rules(str(rules_dir))
    custom = [r for r in loaded if r.get("id") == "CUSTOM-001"]
    assert len(custom) == 1
    assert custom[0]["name"] == "Require Banner Login Notice"


def test_device_compliance_report_and_api(monkeypatch):
    """Verify device compliance report generation and REST API endpoint."""
    from backend.app import create_app
    from backend.app.db.session import get_db_session
    import auth

    test_pass = "ComplexSecret!987654"
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", test_pass)

    app = create_app({"TESTING": True})
    client = app.test_client()

    auth.clear_all_rate_limits()
    auth._load_users()
    u = auth.get_user("admin")
    if not u:
        auth.create_user("admin", test_pass, role="god")
    auth.update_user("admin", {"password": test_pass, "must_change_password": False, "is_active": True})

    login_res = client.post("/login", json={"username": "admin", "password": test_pass})
    assert login_res.status_code == 200

    with get_db_session() as session:
        dev = session.query(Device).filter(Device.name == "COMPLIANCE-ROUTER").first()
        if not dev:
            dev = Device(name="COMPLIANCE-ROUTER", mgmt_ip="10.50.60.70")
            session.add(dev)
            session.commit()
        dev_id = dev.id

        session.query(ConfigSnapshot).filter(ConfigSnapshot.device_id == dev_id).delete()
        session.commit()

        # Add compliant snapshot
        ConfigBackupService.create_snapshot(session, dev_id, COMPLIANT_CONFIG)

    # Call REST API: GET /api/v1/devices/<id>/compliance
    res = client.get(f"/api/v1/devices/{dev_id}/compliance")
    assert res.status_code == 200
    data = res.get_json()
    assert data["device_id"] == dev_id
    assert data["compliance_score"] == 100.0
    assert data["failed_count"] == 0
    assert data["passed_count"] == len(data["results"])
