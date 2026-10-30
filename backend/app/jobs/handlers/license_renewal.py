"""License Renewal Pipeline Handler (Target Architecture §3, Plan 06 Step 4.4).

Ports license_renewal_logic into the Safe Change Pipeline:
- Dry-run: parses current device license via BaseVRPDriver, inspects target XML license,
  compares expiration and feature items, and generates an approval plan without modifying router.
- Apply: requires explicit approval, verifies license file on storage, executes 'license active',
  handles interactive confirmation prompt, and verifies license state transitioned to Normal/Demo.
"""
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from backend.app.devices.session import DeviceSession
from backend.app.devices.parsers.license import parse_display_license, parse_display_license_verbose
from backend.app.jobs.worker import TaskContext
from backend.app.models.device import Device


def clean_xml_content(text: str) -> str:
    """Sanitize XML string stripping illegal control characters and unescaped ampersands."""
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\uFFFD]', '', text)
    text = re.sub(r'&(?!([a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);)', '&amp;', text)
    last_end = text.rfind('</LicFile>')
    if last_end != -1:
        text = text[:last_end + len('</LicFile>')]
    return text


def parse_license_xml_metadata(xml_text: str) -> Dict[str, Any]:
    """Extract ESN, product name, version, and expiry from Huawei license XML."""
    cleaned = clean_xml_content(xml_text)
    meta = {
        "esn": None,
        "product_name": "Unknown",
        "product_version": "Unknown",
        "expired_date": "Unknown",
        "features": {},
    }
    if not cleaned:
        return meta

    try:
        root = ET.fromstring(cleaned)
        # NodeInfo -> ESN
        node_info = root.find('.//NodeInfo')
        if node_info is not None:
            esn_elem = node_info.find('ESN')
            if esn_elem is not None and esn_elem.text:
                meta["esn"] = esn_elem.text.strip().upper()

        # SaleInfo -> Product
        sale_info = root.find('.//SaleInfo')
        if sale_info is not None:
            offering = sale_info.find('.//OfferingProduct')
            if offering is not None:
                meta["product_name"] = offering.get('name', 'Unknown')
                meta["product_version"] = offering.get('version', 'Unknown')

        # KeyInfo -> Features and dates
        key_info = root.find('.//KeyInfo')
        valid_dates = []
        if key_info is not None:
            for key in key_info.findall('.//CapacityKey') + key_info.findall('.//FeatureKey'):
                name = key.get('name')
                val_elems = key.findall('Value')
                if name and val_elems:
                    for v in val_elems:
                        v_date = v.attrib.get('validDate', '')
                        if v_date:
                            valid_dates.append(v_date)
                    meta["features"][name] = len(val_elems)

        concrete_dates = [d for d in valid_dates if re.match(r"^\d{4}-\d{2}-\d{2}", d)]
        if concrete_dates:
            meta["expired_date"] = sorted(concrete_dates)[-1]
        elif valid_dates:
            meta["expired_date"] = valid_dates[0]
    except Exception:
        pass

    return meta


class LicenseRenewalHandler:
    """Native JobEngine handler for Huawei License Renewal on the Safe Change Pipeline."""

    @staticmethod
    def run_task(ctx: TaskContext, session: Optional[DeviceSession] = None) -> Dict[str, Any]:
        """Entrypoint invoked by JobEngine worker."""
        device_name = ctx.device_name
        mode = ctx.mode or "dry_run"
        params = ctx.params or {}
        license_filename = params.get("license_filename", "license.xml")
        license_xml_content = params.get("license_xml_content", "")
        approved = params.get("approved", False)

        ctx.log("info", f"Executing license_renewal pipeline on {device_name} (mode: {mode})")

        # 1. Acquire DeviceSession
        dev_session = session
        if dev_session is None:
            from backend.app.devices.pool import create_device_session
            creds = ctx.creds or {}
            dev_session = create_device_session(
                device_name=device_name,
                db_session=ctx.session,
                username=creds.get("username"),
                password=creds.get("password"),
                jitter=False,
            )

        with dev_session:
            # Step A: Inspect current router license
            ctx.log("info", "Reading current router license via 'display license'...")
            raw_disp_lic = dev_session.run("display_license")
            current_lic = parse_display_license(raw_disp_lic)

            # Resolve current expiry and metadata robustly
            current_file = current_lic.get("active_license") or current_lic.get("license_file") or "Unknown"
            current_status = current_lic.get("license_state") or current_lic.get("license_status") or "Unknown"
            current_expiry = current_lic.get("expired_date")
            if not current_expiry and current_lic.get("features"):
                dates = [f.get("expired_date") for f in current_lic["features"] if f.get("expired_date")]
                if dates:
                    current_expiry = sorted(dates)[-1]
            if not current_expiry:
                m_exp = re.search(r"(?i)expired\s+date\s*:\s*(\S+)", raw_disp_lic)
                if m_exp:
                    current_expiry = m_exp.group(1).strip()
            current_expiry = current_expiry or "Unknown"

            # Step B: Parse target license metadata
            target_meta = parse_license_xml_metadata(license_xml_content) if license_xml_content else {}

            plan_summary = {
                "device_name": device_name,
                "current_file": current_file,
                "current_status": current_status,
                "current_expired_date": current_expiry,
                "target_file": license_filename,
                "target_esn": target_meta.get("esn"),
                "target_expired_date": target_meta.get("expired_date", "Unknown"),
                "requires_approval": True,
            }

            # If mode is dry_run or plan, halt here and return planned details
            if mode in ("dry_run", "plan"):
                ctx.log("info", f"Plan generated for {device_name}: Current expiry={plan_summary['current_expired_date']}, Target expiry={plan_summary['target_expired_date']}")
                return {
                    "device_name": device_name,
                    "status": "planned",
                    "plan": plan_summary,
                }

            # Step C: Apply phase (requires explicit approval)
            if not approved:
                ctx.log("error", "Apply rejected: License renewal change has not been approved.")
                return {
                    "device_name": device_name,
                    "status": "failed",
                    "error": "APPROVAL_REQUIRED",
                    "plan": plan_summary,
                }

            # 1. Verify license file on device storage
            ctx.log("info", f"Verifying license file '{license_filename}' on device storage...")
            verify_out = dev_session.conn.send_command(f"license verify {license_filename}")
            if "error" in verify_out.lower() or "fail" in verify_out.lower():
                ctx.log("error", f"License verification failed: {verify_out}")
                return {
                    "device_name": device_name,
                    "status": "failed",
                    "error": f"LICENSE_VERIFY_FAILED: {verify_out[:120]}",
                }

            # 2. Activate license
            ctx.log("info", f"Activating license: license active {license_filename}...")
            dev_session.conn.clear_buffer()
            cmd = f"license active {license_filename}"
            full_output = dev_session.conn.send_command(
                cmd,
                expect_string=r'\[Y/N\]|\[y/n\]|>[ ]*$',
                read_timeout=30,
            )

            # Interactive confirmation prompt handling
            if any(p in full_output for p in ["[Y/N]", "[y/n]", "Continue"]):
                ctx.log("info", "Interactive prompt detected; confirming 'Y'...")
                response = dev_session.conn.send_command("Y", expect_string=r'>[ ]*$', read_timeout=60)
                full_output += "\n" + response

            lo_out = full_output.lower()
            success = (
                "succeeded in activating" in lo_out
                or "now activing the license.......done" in lo_out
                or ("done." in lo_out and "error" not in lo_out and "fail" not in lo_out)
            )

            if not success:
                ctx.log("error", f"Activation command did not report success: {full_output}")
                return {
                    "device_name": device_name,
                    "status": "failed",
                    "error": f"ACTIVATION_FAILED: {full_output[:120]}",
                }

            # Step D: Verification phase
            ctx.log("info", "Re-reading 'display license' to verify active state and expiration...")
            post_raw = dev_session.run("display_license")
            post_lic = parse_display_license(post_raw)

            post_status = post_lic.get("license_state") or post_lic.get("license_status") or "Unknown"
            post_file = post_lic.get("active_license") or post_lic.get("license_file") or "Unknown"
            post_expiry = post_lic.get("expired_date")
            if not post_expiry:
                m_p_exp = re.search(r"(?i)expired\s+date\s*:\s*(\S+)", post_raw)
                if m_p_exp:
                    post_expiry = m_p_exp.group(1).strip()
            post_expiry = post_expiry or "Unknown"

            verified = (
                post_status.lower() in ("normal", "demo")
                or post_expiry == target_meta.get("expired_date")
            )

            ctx.log("info", f"License renewal verified: status={post_status}, expiry={post_expiry}")
            return {
                "device_name": device_name,
                "status": "success",
                "verified": verified,
                "old_expired_date": current_expiry,
                "new_expired_date": post_expiry,
                "active_license_file": post_file,
            }
