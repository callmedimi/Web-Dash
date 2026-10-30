"""Huawei license parsers with state machine and F-29 safety checks."""
import re
from typing import Dict, Any, List, Optional


def parse_display_license(output: str) -> Dict[str, Any]:
    """
    Parse 'display license' basic output using a clean state machine.
    """
    result: Dict[str, Any] = {
        "active_license": "",
        "license_state": "",
        "revoke_ticket": "",
        "license_mode": "",
        "product_name": "",
        "product_version": "",
        "license_serial_no": "",
        "creator": "",
        "created_time": "",
        "country": "",
        "custom": "",
        "office": "",
        "features": [],
        "items": [],
        "items_detail_available": False,
    }

    if not output:
        return result

    lines = output.splitlines()
    in_table = False
    current_feature: Optional[Dict[str, Any]] = None

    header_keys = {
        "active license": "active_license",
        "license state": "license_state",
        "revoke ticket": "revoke_ticket",
        "license mode": "license_mode",
        "product name": "product_name",
        "product version": "product_version",
        "license serial no": "license_serial_no",
        "license file esn": "license_serial_no",
        "creator": "creator",
        "created time": "created_time",
        "country": "country",
        "custom": "custom",
        "office": "office",
    }

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Header metadata
        if ":" in stripped and not in_table and not stripped.startswith("-") and not current_feature:
            key, _, val = stripped.partition(":")
            k_low = key.strip().lower()
            if k_low in header_keys:
                result[header_keys[k_low]] = val.strip()
                continue

        # Feature boundary
        if stripped.lower().startswith("feature name"):
            feat_name = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            current_feature = {
                "feature_name": feat_name,
                "authorize_type": "",
                "expired_date": "",
                "trial_days": "",
            }
            result["features"].append(current_feature)
            continue

        if current_feature and not in_table:
            low = stripped.lower()
            if low.startswith("authorize type"):
                current_feature["authorize_type"] = stripped.split(":", 1)[1].strip()
            elif low.startswith("expired date") and not low.startswith("item expired"):
                current_feature["expired_date"] = stripped.split(":", 1)[1].strip()
            elif low.startswith("trial days"):
                current_feature["trial_days"] = stripped.split(":", 1)[1].strip()

        # Item table boundary
        if "item name" in stripped.lower() and "value" in stripped.lower():
            in_table = True
            current_feature = None
            result["items_detail_available"] = True
            continue

        if in_table:
            if stripped.startswith("-") or stripped.startswith("="):
                continue
            m = re.match(r"^\s*(\S+)\s+(\S+)\s+(\S+)?\s*(.*)", stripped)
            if m:
                item_name = m.group(1)
                item_val = m.group(2) if m.group(2) else ""
                desc = m.group(4).strip() if m.group(4) else (m.group(3).strip() if m.group(3) else "")
                result["items"].append({
                    "item_name": item_name,
                    "value": item_val,
                    "description": desc,
                })

    return result


def parse_display_license_verbose(output: str) -> Dict[str, Any]:
    """
    Parse 'display license verbose' output.
    Items strictly belong to the feature currently being parsed (no cartesian fallback, F-29).
    """
    result: Dict[str, Any] = {
        "active_license": "",
        "license_state": "",
        "revoke_ticket": "",
        "license_mode": "",
        "product_name": "",
        "product_version": "",
        "license_esn": "",
        "license_serial_no": "",
        "creator": "",
        "created_time": "",
        "country": "",
        "custom": "",
        "office": "",
        "features": [],
        "items": [],
        "items_detail_available": False,
    }

    if not output:
        return result

    lines = output.splitlines()
    current_feature: Optional[Dict[str, Any]] = None
    current_item: Optional[Dict[str, Any]] = None

    header_keys = {
        "active license": "active_license",
        "license state": "license_state",
        "revoke ticket": "revoke_ticket",
        "license mode": "license_mode",
        "product name": "product_name",
        "product version": "product_version",
        "license file esn": "license_esn",
        "license serial no": "license_serial_no",
        "creator": "creator",
        "created time": "created_time",
        "country": "country",
        "custom": "custom",
        "office": "office",
    }

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if ":" in stripped and not stripped.startswith("-") and not current_feature:
            key, _, val = stripped.partition(":")
            k_low = key.strip().lower()
            if k_low in header_keys:
                result[header_keys[k_low]] = val.strip()
                continue

        # Feature start
        if stripped.lower().startswith("feature name"):
            feat_name = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            current_feature = {
                "feature_name": feat_name,
                "authorize_type": "",
                "expired_date": "",
                "trial_days": "",
                "items": [],
            }
            result["features"].append(current_feature)
            current_item = None
            continue

        if current_feature:
            low = stripped.lower()
            if low.startswith("authorize type"):
                current_feature["authorize_type"] = stripped.split(":", 1)[1].strip()
            elif low.startswith("expired date") and not low.startswith("item expired"):
                current_feature["expired_date"] = stripped.split(":", 1)[1].strip()
            elif low.startswith("trial days"):
                current_feature["trial_days"] = stripped.split(":", 1)[1].strip()
            elif low.startswith("item name"):
                item_name = stripped.split(":", 1)[1].strip()
                current_item = {
                    "item_name": item_name,
                    "item_type": "",
                    "value": "",
                    "description": "",
                    "item_expired": "",
                    "feature_name": current_feature["feature_name"],
                }
                current_feature["items"].append(current_item)
                result["items"].append(current_item)
                result["items_detail_available"] = True
            elif current_item:
                if low.startswith("item type"):
                    current_item["item_type"] = stripped.split(":", 1)[1].strip()
                elif low.startswith("value"):
                    current_item["value"] = stripped.split(":", 1)[1].strip()
                elif low.startswith("description"):
                    current_item["description"] = stripped.split(":", 1)[1].strip()
                elif low.startswith("item expired"):
                    current_item["item_expired"] = stripped.split(":", 1)[1].strip()

    return result
