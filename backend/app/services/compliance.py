"""Compliance Rule Evaluation Engine (Target Architecture §3, Plan 06 Step 4.5).

Implements "Policy as Data":
- Evaluates YAML-driven or built-in compliance rules against configuration snapshots.
- Read-only inspection (never auto-remediates in this phase).
- Produces PASS/FAIL audit records with severity and remediation guidance.
"""
import os
import re
import yaml
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.config_change import ConfigSnapshot
from backend.app.services.config_backup import ConfigBackupService

BUILTIN_COMPLIANCE_RULES: List[Dict[str, Any]] = [
    {
        "id": "SEC-001",
        "name": "SSH Only, Telnet Prohibited",
        "severity": "high",
        "description": "Telnet server must be disabled and SSH/STelnet enabled.",
        "must_contain": [r"(?i)\bstelnet\s+server\s+enable\b|\bssh\s+server\b"],
        "must_not_contain": [r"(?i)^\s*telnet\s+server\s+enable\b"],
        "remediation_hint": "Execute 'undo telnet server enable' and 'stelnet server enable'.",
    },
    {
        "id": "OPS-001",
        "name": "NTP Server Synchronization Configured",
        "severity": "medium",
        "description": "Network Time Protocol server must be configured for accurate logging.",
        "must_contain": [r"(?i)\bntp-service\s+(?:unicast-server|server|source-interface)\b"],
        "must_not_contain": [],
        "remediation_hint": "Configure authoritative NTP: 'ntp-service unicast-server <IP>'.",
    },
    {
        "id": "SEC-002",
        "name": "SNMPv3 Only, Legacy Communities Prohibited",
        "severity": "high",
        "description": "SNMP v1 and v2c cleartext communities must not be configured on router.",
        "must_contain": [],
        "must_not_contain": [
            r"(?i)\bsnmp-agent\s+sys-info\s+version\s+(?:v1|v2c)\b",
            r"(?i)\bsnmp-agent\s+community\s+read\b",
        ],
        "remediation_hint": "Configure SNMPv3 USM group and user with auth/priv encryption.",
    },
    {
        "id": "OPS-002",
        "name": "No Active Interface Without Description",
        "severity": "low",
        "type": "interface_description",
        "description": "All active physical/sub-interfaces should have an explicit description.",
        "remediation_hint": "Add a description to each active interface: 'description <PURPOSE>'.",
    },
]


def load_compliance_rules(rules_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load YAML compliance rules from rules_dir, merging with built-ins."""
    directory = rules_dir or os.path.join(settings.get_data_dir(), "compliance")
    rules: List[Dict[str, Any]] = list(BUILTIN_COMPLIANCE_RULES)

    if os.path.isdir(directory):
        for fname in os.listdir(directory):
            if fname.lower().endswith((".yml", ".yaml")):
                fpath = os.path.join(directory, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, list):
                            rules.extend(data)
                        elif isinstance(data, dict):
                            rules.append(data)
                except Exception:
                    pass

    return rules


def _check_interface_descriptions(config_text: str) -> Tuple[bool, List[str]]:
    """Inspect interfaces in config text; flag if active without description."""
    violations: List[str] = []
    current_iface: Optional[str] = None
    has_desc = False
    is_shutdown = False

    for line in config_text.splitlines():
        s = line.strip()
        if s.lower().startswith("interface "):
            if current_iface and not is_shutdown and not has_desc:
                # Loopback and Null interfaces are exempt
                if not any(ex in current_iface.lower() for ex in ["loopback", "null", "vlanif"]):
                    violations.append(current_iface)
            current_iface = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else s
            has_desc = False
            is_shutdown = False
        elif current_iface:
            if s.startswith("#") or s.lower() == "return":
                if not is_shutdown and not has_desc:
                    if not any(ex in current_iface.lower() for ex in ["loopback", "null", "vlanif"]):
                        violations.append(current_iface)
                current_iface = None
            elif s.lower().startswith("description "):
                has_desc = True
            elif s.lower() == "shutdown":
                is_shutdown = True

    if current_iface and not is_shutdown and not has_desc:
        if not any(ex in current_iface.lower() for ex in ["loopback", "null", "vlanif"]):
            violations.append(current_iface)

    passed = len(violations) == 0
    return passed, violations


def evaluate_compliance_on_config(
    config_text: str,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluate compliance rules against a normalized configuration string.
    Returns structured pass/fail table with remediation guidance.
    """
    active_rules = rules if rules is not None else load_compliance_rules()
    results: List[Dict[str, Any]] = []

    for rule in active_rules:
        rule_id = rule.get("id", "UNKNOWN")
        name = rule.get("name", "Unnamed Rule")
        severity = rule.get("severity", "medium")
        remediation = rule.get("remediation_hint", "")
        rule_type = rule.get("type", "regex")

        if rule_type == "interface_description":
            passed, violations = _check_interface_descriptions(config_text)
            results.append({
                "rule_id": rule_id,
                "name": name,
                "severity": severity,
                "status": "PASS" if passed else "FAIL",
                "details": f"Interfaces missing description: {violations}" if not passed else "All active interfaces have descriptions",
                "remediation_hint": remediation,
            })
            continue

        # Regex / String matching rules
        must_contain = rule.get("must_contain", [])
        must_not_contain = rule.get("must_not_contain", [])
        passed = True
        failed_reasons: List[str] = []

        # Check required patterns
        for pat in must_contain:
            if not re.search(pat, config_text, re.MULTILINE):
                passed = False
                failed_reasons.append(f"Missing required pattern '{pat}'")

        # Check prohibited patterns
        for pat in must_not_contain:
            match = re.search(pat, config_text, re.MULTILINE)
            if match:
                passed = False
                failed_reasons.append(f"Contains prohibited pattern '{pat}' (matched: '{match.group(0)}')")

        results.append({
            "rule_id": rule_id,
            "name": name,
            "severity": severity,
            "status": "PASS" if passed else "FAIL",
            "details": "; ".join(failed_reasons) if not passed else "Compliant",
            "remediation_hint": remediation,
        })

    return results


def evaluate_device_compliance(db_session: Session, device_id: int) -> Dict[str, Any]:
    """Fetch latest config snapshot for device and evaluate compliance."""
    latest_snap = (
        db_session.query(ConfigSnapshot)
        .filter(ConfigSnapshot.device_id == device_id)
        .order_by(ConfigSnapshot.taken_at.desc())
        .first()
    )

    if not latest_snap:
        return {
            "device_id": device_id,
            "status": "no_snapshot",
            "message": f"No configuration snapshots found for device {device_id}",
            "results": [],
            "passed_count": 0,
            "failed_count": 0,
        }

    config_text = ConfigBackupService.get_snapshot_decrypted(db_session, latest_snap.id) or ""
    eval_results = evaluate_compliance_on_config(config_text)

    passed_count = sum(1 for r in eval_results if r["status"] == "PASS")
    failed_count = sum(1 for r in eval_results if r["status"] == "FAIL")

    return {
        "device_id": device_id,
        "snapshot_id": latest_snap.id,
        "snapshot_taken_at": latest_snap.taken_at.isoformat() if latest_snap.taken_at else None,
        "rules_count": len(eval_results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "compliance_score": round((passed_count / len(eval_results)) * 100, 1) if eval_results else 100.0,
        "results": eval_results,
    }
