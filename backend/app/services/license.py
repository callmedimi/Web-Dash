"""License Management Service (Phase 5 Step 5.4).

Ports and enhances license_check.py and license_renewal_logic.py:
- Parsers for 'display license' and 'display license verbose'
- Days to expiry and alert level calculation (<=90/60/30/7 days, expired)
- Fleet table querying, filtering, and summary statistics
- XML/ZIP license file parsing and ESN router matching
- Safe Change Pipeline renewal planning
"""
from __future__ import annotations
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models.device import Device
from backend.app.models.license import LicenseRecord
from backend.app.jobs.change import ChangePipelineService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_xml_content(text: str) -> str:
    """Strip illegal XML characters and unclosed tails."""
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\uFFFD]', '', text)
    text = re.sub(r'&(?!([a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);)', '&amp;', text)
    last_end = text.rfind('</LicFile>')
    if last_end != -1:
        text = text[:last_end + len('</LicFile>')]
    return text


class LicenseService:
    """Core domain logic for Huawei VRP license checking and management."""

    @staticmethod
    def parse_display_license(output: str) -> Dict[str, Any]:
        """Parse standard 'display license' output."""
        result: Dict[str, Any] = {
            'active_license': '',
            'license_state': '',
            'revoke_ticket': '',
            'license_mode': '',
            'product_name': '',
            'product_version': '',
            'license_serial_no': '',
            'creator': '',
            'created_time': '',
            'country': '',
            'custom': '',
            'office': '',
            'features': [],
            'items': [],
        }
        lines = output.splitlines()
        in_table = False
        current_feature: Optional[Dict[str, str]] = None

        mapping = {
            'active license': 'active_license',
            'license state': 'license_state',
            'revoke ticket': 'revoke_ticket',
            'license mode': 'license_mode',
            'product name': 'product_name',
            'product version': 'product_version',
            'license serial no': 'license_serial_no',
            'creator': 'creator',
            'created time': 'created_time',
            'country': 'country',
            'custom': 'custom',
            'office': 'office',
        }

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if ':' in stripped and not in_table and not stripped.startswith('-') and not current_feature:
                key, _, val = stripped.partition(':')
                key_lower = key.strip().lower()
                val = val.strip()
                if key_lower in mapping:
                    result[mapping[key_lower]] = val
                    continue

            if stripped.startswith('Feature name'):
                current_feature = {
                    'feature_name': stripped.split(':', 1)[1].strip() if ':' in stripped else '',
                    'authorize_type': '',
                    'expired_date': '',
                    'trial_days': '',
                }
                result['features'].append(current_feature)
                continue

            if current_feature:
                if stripped.startswith('Authorize type'):
                    current_feature['authorize_type'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Expired date'):
                    current_feature['expired_date'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Trial days'):
                    current_feature['trial_days'] = stripped.split(':', 1)[1].strip()

            if 'Item name' in stripped and 'Value' in stripped:
                in_table = True
                continue

            if in_table:
                if stripped.startswith('---') or stripped.startswith('==='):
                    continue
                m = re.match(r'\s*(\S+)\s+(\S+)\s+(\S+)\s+(.*)', stripped)
                if m:
                    result['items'].append({
                        'item_name': m.group(1),
                        'item_type': m.group(2),
                        'value': m.group(3).strip(),
                        'description': m.group(4).strip(),
                    })

        return result

    @staticmethod
    def parse_display_license_verbose(output: str) -> Dict[str, Any]:
        """Parse 'display license verbose' output."""
        result: Dict[str, Any] = {
            'active_license': '',
            'license_state': '',
            'revoke_ticket': '',
            'license_mode': '',
            'product_name': '',
            'product_version': '',
            'license_esn': '',
            'license_serial_no': '',
            'creator': '',
            'created_time': '',
            'country': '',
            'custom': '',
            'office': '',
            'features': [],
            'items': [],
        }
        lines = output.splitlines()
        current_feature: Optional[Dict[str, Any]] = None
        current_item: Optional[Dict[str, str]] = None

        mapping = {
            'active license': 'active_license',
            'license state': 'license_state',
            'revoke ticket': 'revoke_ticket',
            'license mode': 'license_mode',
            'product name': 'product_name',
            'product version': 'product_version',
            'license file esn': 'license_esn',
            'license serial no': 'license_serial_no',
            'creator': 'creator',
            'created time': 'created_time',
            'country': 'country',
            'custom': 'custom',
            'office': 'office',
        }

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if ':' in stripped and not stripped.startswith('-') and not current_feature:
                key, _, val = stripped.partition(':')
                key_lower = key.strip().lower()
                val = val.strip()
                if key_lower in mapping:
                    result[mapping[key_lower]] = val
                    continue

            if stripped.startswith('Feature name'):
                current_feature = {
                    'feature_name': stripped.split(':', 1)[1].strip() if ':' in stripped else '',
                    'authorize_type': '',
                    'expired_date': '',
                    'trial_days': '',
                    'items': [],
                }
                result['features'].append(current_feature)
                current_item = None
                continue

            if current_feature:
                if stripped.startswith('Authorize type'):
                    current_feature['authorize_type'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Expired date') and not stripped.startswith('Item expired'):
                    current_feature['expired_date'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Trial days'):
                    current_feature['trial_days'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Sale name'):
                    current_item = {
                        'sale_name': stripped.split(':', 1)[1].strip(),
                        'item_name': '',
                        'item_type': '',
                        'control_value': '',
                        'used_value': '',
                        'item_state': '',
                        'item_expired_date': '',
                        'item_trial_days': '',
                        'description': '',
                    }
                    current_feature['items'].append(current_item)
                    result['items'].append(current_item)
                elif stripped.startswith('Item name') and current_item:
                    current_item['item_name'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Item type') and current_item:
                    current_item['item_type'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Control value') and current_item:
                    current_item['control_value'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Used value') and current_item:
                    current_item['used_value'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Item state') and current_item:
                    current_item['item_state'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Item expired date') and current_item:
                    current_item['item_expired_date'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Item trial days') and current_item:
                    current_item['item_trial_days'] = stripped.split(':', 1)[1].strip()
                elif stripped.startswith('Description') and current_item:
                    current_item['description'] = stripped.split(':', 1)[1].strip()

        return result

    @staticmethod
    def calculate_days_to_expiry(
        expired_date_str: str,
        trial_days_str: str = "",
        reference_date: Optional[datetime] = None,
    ) -> Tuple[Optional[int], bool, str]:
        """Calculate days remaining to license expiry.

        Returns:
            (days_to_expiry, is_expired, normalized_expiry_string)
            None for days_to_expiry indicates permanent or unparsed unlimited.
        """
        ref_dt = reference_date or utc_now()
        if ref_dt.tzinfo is None:
            ref_dt = ref_dt.replace(tzinfo=timezone.utc)

        clean_str = (expired_date_str or "").strip()
        if not clean_str or clean_str.upper() in ("PERMANENT", "UNLIMITED", "NEVER", "NONE", "DEFAULT"):
            return None, False, clean_str.upper() or "PERMANENT"

        # Check for numeric trial days fallback
        trial_val = 0
        if trial_days_str and trial_days_str.isdigit():
            trial_val = int(trial_days_str)

        # Parse date formats
        parsed_dt: Optional[datetime] = None
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                parsed_dt = datetime.strptime(clean_str[:19].strip(), fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue

        if not parsed_dt:
            if trial_val > 0:
                expiry_dt = ref_dt + timedelta(days=trial_val)
                return trial_val, False, expiry_dt.strftime("%Y-%m-%d")
            return None, False, clean_str

        # Calculate difference
        delta_days = (parsed_dt.date() - ref_dt.date()).days
        is_expired = delta_days < 0
        norm_str = parsed_dt.strftime("%Y-%m-%d")
        return delta_days, is_expired, norm_str

    @staticmethod
    def determine_alert_level(days_to_expiry: Optional[int], is_expired: bool) -> str:
        """Determine alert level based on expiry threshold."""
        if is_expired or (days_to_expiry is not None and days_to_expiry < 0):
            return "EXPIRED"
        if days_to_expiry is None:
            return "OK"
        if days_to_expiry <= 7:
            return "CRITICAL_7"
        if days_to_expiry <= 30:
            return "WARN_30"
        if days_to_expiry <= 60:
            return "WARN_60"
        if days_to_expiry <= 90:
            return "WARN_90"
        return "OK"

    @classmethod
    def scan_device_license(
        cls,
        device: Device,
        device_session: Any,
        reference_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Connect to device, run license commands, and extract structured license info."""
        # 1. Standard display license
        lic_output = device_session.run("display license")
        parsed_lic = cls.parse_display_license(lic_output)

        # 2. Verbose display license
        try:
            verb_output = device_session.run("display license verbose")
            parsed_verb = cls.parse_display_license_verbose(verb_output)
            verbose_ok = bool(parsed_verb.get("features") or parsed_verb.get("items"))
        except Exception:
            parsed_verb = {}
            verbose_ok = False

        # Fallback to standard items if verbose failed
        if not verbose_ok and parsed_lic.get("items"):
            parsed_verb = {
                "active_license": parsed_lic.get("active_license", ""),
                "license_state": parsed_lic.get("license_state", ""),
                "product_name": parsed_lic.get("product_name", ""),
                "product_version": parsed_lic.get("product_version", ""),
                "features": [],
                "items": [],
            }
            for feat in parsed_lic.get("features", []):
                fcopy = dict(feat)
                fcopy["items"] = []
                for itm in parsed_lic.get("items", []):
                    item_dict = {
                        "sale_name": itm["item_name"],
                        "item_name": itm["item_name"],
                        "item_type": itm["item_type"],
                        "control_value": itm.get("value", ""),
                        "used_value": "0",
                        "item_state": "Normal",
                        "item_expired_date": "",
                        "description": itm.get("description", ""),
                    }
                    fcopy["items"].append(item_dict)
                    parsed_verb["items"].append(item_dict)
                parsed_verb["features"].append(fcopy)

        # Determine master fields
        product_name = (
            parsed_verb.get("product_name")
            or parsed_lic.get("product_name")
            or device.model
            or "Unknown"
        )
        product_version = (
            parsed_verb.get("product_version")
            or parsed_lic.get("product_version")
            or device.software_version
            or "Unknown"
        )
        license_state = (
            parsed_verb.get("license_state")
            or parsed_lic.get("license_state")
            or "Normal"
        )
        active_license = (
            parsed_verb.get("active_license")
            or parsed_lic.get("active_license")
            or ""
        )
        serial_no = (
            parsed_verb.get("license_serial_no")
            or parsed_lic.get("license_serial_no")
            or ""
        )
        esn = (
            parsed_verb.get("license_esn")
            or device.esn
            or ""
        )

        # Calculate earliest expiry across all features
        features = parsed_verb.get("features") or parsed_lic.get("features") or []
        items = parsed_verb.get("items") or parsed_lic.get("items") or []

        min_days: Optional[int] = None
        final_is_expired = False
        final_expiry_str = "PERMANENT"

        for f in features:
            exp_str = f.get("expired_date", "")
            trial_str = f.get("trial_days", "")
            d_days, is_exp, norm_str = cls.calculate_days_to_expiry(
                exp_str, trial_str, reference_date=reference_date
            )
            if is_exp:
                final_is_expired = True
                final_expiry_str = norm_str
                min_days = d_days
                break
            if d_days is not None:
                if min_days is None or d_days < min_days:
                    min_days = d_days
                    final_expiry_str = norm_str

        # Calculate items used count vs total
        items_total = len(items)
        items_used = 0
        for itm in items:
            used_val = str(itm.get("used_value", "0")).strip()
            if used_val.isdigit() and int(used_val) > 0:
                items_used += 1
            elif itm.get("item_state", "").lower() in ("normal", "activated", "in-use"):
                items_used += 1

        alert_level = cls.determine_alert_level(min_days, final_is_expired)

        return {
            "device_id": device.id,
            "device_name": device.name,
            "product_name": product_name,
            "product_version": product_version,
            "license_state": license_state,
            "active_license": active_license,
            "license_serial_no": serial_no,
            "esn": esn,
            "days_to_expiry": min_days,
            "expiry_date": final_expiry_str,
            "is_expired": final_is_expired,
            "alert_level": alert_level,
            "features": features,
            "items": items,
            "items_used_count": items_used,
            "items_total_count": items_total,
        }

    @classmethod
    def save_device_license(
        cls,
        db_session: Session,
        device_id: int,
        data: Dict[str, Any],
    ) -> LicenseRecord:
        """Upsert license record into database."""
        now = utc_now()
        rec = db_session.query(LicenseRecord).filter(LicenseRecord.device_id == device_id).first()
        if not rec:
            rec = LicenseRecord(device_id=device_id)
            db_session.add(rec)

        rec.product_name = data.get("product_name", "")
        rec.product_version = data.get("product_version", "")
        rec.license_state = data.get("license_state", "Unknown")
        rec.active_license = data.get("active_license", "")
        rec.license_serial_no = data.get("license_serial_no", "")
        rec.esn = data.get("esn", "")
        rec.days_to_expiry = data.get("days_to_expiry")
        rec.expiry_date = data.get("expiry_date", "")
        rec.is_expired = data.get("is_expired", False)
        rec.alert_level = data.get("alert_level", "OK")
        rec.features = data.get("features", [])
        rec.items = data.get("items", [])
        rec.items_used_count = data.get("items_used_count", 0)
        rec.items_total_count = data.get("items_total_count", 0)
        rec.last_checked = now
        rec.updated_at = now

        db_session.commit()
        db_session.refresh(rec)
        return rec

    @staticmethod
    def get_fleet_summary(db_session: Session, province: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate summary of license status across the entire fleet or given province."""
        dev_query = db_session.query(Device).filter(Device.enabled == True)
        if province:
            dev_query = dev_query.filter(Device.province == province)
        devices = dev_query.all()
        dev_ids = [d.id for d in devices]

        if not dev_ids:
            return {
                "total_devices": 0,
                "scanned_devices": 0,
                "unscanned_devices": 0,
                "counts_by_alert": {
                    "OK": 0,
                    "WARN_90": 0,
                    "WARN_60": 0,
                    "WARN_30": 0,
                    "CRITICAL_7": 0,
                    "EXPIRED": 0,
                },
                "products": {},
                "states": {},
            }

        records = db_session.query(LicenseRecord).filter(LicenseRecord.device_id.in_(dev_ids)).all()
        scanned_dev_ids = {r.device_id for r in records}

        alert_counts = {
            "OK": 0,
            "WARN_90": 0,
            "WARN_60": 0,
            "WARN_30": 0,
            "CRITICAL_7": 0,
            "EXPIRED": 0,
        }
        product_counts: Dict[str, int] = {}
        state_counts: Dict[str, int] = {}

        for r in records:
            lvl = r.alert_level or "OK"
            alert_counts[lvl] = alert_counts.get(lvl, 0) + 1

            pn = r.product_name or "Unknown"
            product_counts[pn] = product_counts.get(pn, 0) + 1

            st = r.license_state or "Unknown"
            state_counts[st] = state_counts.get(st, 0) + 1

        return {
            "total_devices": len(devices),
            "scanned_devices": len(scanned_dev_ids),
            "unscanned_devices": len(devices) - len(scanned_dev_ids),
            "counts_by_alert": alert_counts,
            "products": product_counts,
            "states": state_counts,
        }

    @staticmethod
    def list_fleet_licenses(
        db_session: Session,
        province: Optional[str] = None,
        alert_level: Optional[str] = None,
        product: Optional[str] = None,
        state: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Query fleet license table with filtering and pagination."""
        q = (
            db_session.query(Device, LicenseRecord)
            .outerjoin(LicenseRecord, Device.id == LicenseRecord.device_id)
            .filter(Device.enabled == True)
        )

        if province:
            q = q.filter(Device.province == province)
        if alert_level:
            q = q.filter(LicenseRecord.alert_level == alert_level)
        if product:
            q = q.filter(LicenseRecord.product_name.ilike(f"%{product}%"))
        if state:
            q = q.filter(LicenseRecord.license_state == state)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                or_(
                    Device.name.ilike(pattern),
                    Device.mgmt_ip.ilike(pattern),
                    Device.site.ilike(pattern),
                    LicenseRecord.esn.ilike(pattern),
                    LicenseRecord.product_name.ilike(pattern),
                )
            )

        total_count = q.count()
        offset = max(0, (page - 1) * page_size)
        rows = q.order_by(
            LicenseRecord.days_to_expiry.asc().nullslast(),
            Device.name.asc()
        ).offset(offset).limit(page_size).all()

        items = []
        for dev, rec in rows:
            if rec:
                item = rec.to_dict()
            else:
                item = {
                    "id": None,
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "mgmt_ip": dev.mgmt_ip,
                    "province": dev.province,
                    "site": dev.site,
                    "product_name": dev.model or "Unknown",
                    "product_version": dev.software_version or "Unknown",
                    "license_state": "Not Scanned",
                    "active_license": "",
                    "license_serial_no": "",
                    "esn": dev.esn or "",
                    "days_to_expiry": None,
                    "expiry_date": "",
                    "is_expired": False,
                    "alert_level": "UNSCANNED",
                    "features_count": 0,
                    "items_used_count": 0,
                    "items_total_count": 0,
                    "last_checked": None,
                }
            items.append(item)

        return {
            "items": items,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size else 1,
        }

    @staticmethod
    def check_expiring_licenses(
        db_session: Session,
        thresholds: Tuple[int, ...] = (90, 60, 30, 7),
    ) -> List[Dict[str, Any]]:
        """Nightly license check for scheduler; finds all expiring/expired devices and returns structured alerts."""
        records = (
            db_session.query(LicenseRecord)
            .join(Device, LicenseRecord.device_id == Device.id)
            .filter(Device.enabled == True)
            .all()
        )

        alerts = []
        for r in records:
            if r.is_expired or (r.days_to_expiry is not None and r.days_to_expiry < 0):
                alerts.append({
                    "device_id": r.device_id,
                    "device_name": r.device.name if r.device else "",
                    "mgmt_ip": r.device.mgmt_ip if r.device else "",
                    "province": r.device.province if r.device else "",
                    "alert_level": "EXPIRED",
                    "days_to_expiry": r.days_to_expiry,
                    "expiry_date": r.expiry_date,
                    "product_name": r.product_name,
                    "message": f"License for {r.device.name if r.device else ''} has EXPIRED on {r.expiry_date}.",
                })
                continue

            if r.days_to_expiry is not None:
                for th in sorted(thresholds):
                    if r.days_to_expiry <= th:
                        level = f"WARN_{th}" if th > 7 else "CRITICAL_7"
                        alerts.append({
                            "device_id": r.device_id,
                            "device_name": r.device.name if r.device else "",
                            "mgmt_ip": r.device.mgmt_ip if r.device else "",
                            "province": r.device.province if r.device else "",
                            "alert_level": level,
                            "threshold_days": th,
                            "days_to_expiry": r.days_to_expiry,
                            "expiry_date": r.expiry_date,
                            "product_name": r.product_name,
                            "message": f"License for {r.device.name if r.device else ''} expires in {r.days_to_expiry} days ({r.expiry_date}).",
                        })
                        break

        return alerts

    @classmethod
    def parse_license_file_content(cls, file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Parse uploaded .xml or .zip license file and extract ESN, product, and features."""
        xml_entries: List[Tuple[str, str]] = []  # (xml_filename, xml_text)

        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file_content), "r") as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        raw = zf.read(name)
                        xml_entries.append((name, raw.decode("utf-8", errors="replace")))
        else:
            xml_entries.append((filename, file_content.decode("utf-8", errors="replace")))

        results = []
        for xml_name, raw_text in xml_entries:
            try:
                cleaned = clean_xml_content(raw_text)
                root = ET.fromstring(cleaned)

                esn = ""
                node_info = root.find(".//NodeInfo")
                if node_info is not None:
                    esn_elem = node_info.find("ESN")
                    if esn_elem is not None and esn_elem.text:
                        esn = esn_elem.text.strip()

                product_name = ""
                product_ver = ""
                prod_elem = root.find(".//Product")
                if prod_elem is not None:
                    name_elem = prod_elem.find("Name")
                    if name_elem is not None and name_elem.text:
                        product_name = name_elem.text.strip()
                    ver_elem = prod_elem.find("Version")
                    if ver_elem is not None and ver_elem.text:
                        product_ver = ver_elem.text.strip()

                features = []
                for feat in root.findall(".//Feature"):
                    fname = feat.find("Name")
                    fexp = feat.find("ExpiredDate")
                    features.append({
                        "feature_name": fname.text.strip() if fname is not None and fname.text else "",
                        "expired_date": fexp.text.strip() if fexp is not None and fexp.text else "",
                    })

                results.append({
                    "filename": xml_name,
                    "esn": esn,
                    "product_name": product_name,
                    "product_version": product_ver,
                    "features": features,
                    "raw_xml": cleaned,
                })
            except Exception as exc:
                results.append({
                    "filename": xml_name,
                    "esn": "",
                    "error": str(exc),
                })

        return results

    @classmethod
    def match_license_to_devices(
        cls,
        db_session: Session,
        parsed_entries: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Match extracted license files to devices in inventory by ESN or name."""
        devices = db_session.query(Device).filter(Device.enabled == True).all()

        matched = []
        unmatched = []

        for entry in parsed_entries:
            esn = (entry.get("esn") or "").strip().upper()
            if not esn:
                unmatched.append({**entry, "reason": "No ESN found in license XML"})
                continue

            found_dev = None
            # 1. Exact match on ESN or name
            for dev in devices:
                dev_esn = (dev.esn or "").strip().upper()
                dev_name = dev.name.strip().upper()
                if esn in (dev_esn, dev_name):
                    found_dev = dev
                    break

            # 2. Substring match
            if not found_dev and len(esn) >= 6:
                for dev in devices:
                    dev_esn = (dev.esn or "").strip().upper()
                    dev_name = dev.name.strip().upper()
                    if (dev_esn and esn in dev_esn) or (dev_esn and dev_esn in esn):
                        found_dev = dev
                        break
                    if (dev_name and esn in dev_name) or (dev_name and dev_name in esn):
                        found_dev = dev
                        break

            if found_dev:
                matched.append({
                    "device_id": found_dev.id,
                    "device_name": found_dev.name,
                    "mgmt_ip": found_dev.mgmt_ip,
                    "province": found_dev.province,
                    "matched_esn": esn,
                    "filename": entry.get("filename"),
                    "product_name": entry.get("product_name"),
                    "product_version": entry.get("product_version"),
                    "features": entry.get("features", []),
                })
            else:
                unmatched.append({
                    "filename": entry.get("filename"),
                    "esn": esn,
                    "reason": f"No device in inventory matched ESN {esn}",
                })

        return matched, unmatched

    @classmethod
    def plan_license_renewal(
        cls,
        db_session: Session,
        device: Device,
        license_filename: str,
        creator_id: str = "admin",
        reason: str = "Scheduled License Renewal",
    ):
        """Create a Safe Change Pipeline ChangeRequest for license renewal."""
        base_name = os.path.basename(license_filename)
        # Commands to execute
        commands = [
            f"license verify {base_name}",
            f"license active {base_name}",
        ]
        # Rollback commands (re-read current active or rollback notice)
        rec = db_session.query(LicenseRecord).filter(LicenseRecord.device_id == device.id).first()
        prev_active = rec.active_license if rec and rec.active_license else ""
        if prev_active:
            rollback_commands = [f"license active {prev_active}"]
        else:
            rollback_commands = [f"# Revert license active for {device.name} if verify failed"]

        cr = ChangePipelineService.create_change_request(
            db_session=db_session,
            device_id=device.id,
            creator_id=creator_id,
            lines=commands,
            inverse_lines=rollback_commands,
            reason=f"{reason} (File: {base_name})",
            risk_level="medium",
        )
        return cr
