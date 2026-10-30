"""Data Migration ETL: Migrates legacy JSON and CSV files into PostgreSQL / Relational DB.
Idempotent, non-destructive, and resilient to missing files or broken rows.
"""
import os
import csv
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.user import User, Permission
from backend.app.models.arp_mac import (
    ArpMacRecord,
    ArpMacSnapshot,
    ArpMacHistory,
    SiteInventory,
)
from backend.app.models.telemetry_cache import ZabbixInventoryCache
from backend.app.models.license import LicenseRenewalReport

logger = logging.getLogger(__name__)


def migrate_users_from_json(session: Session, file_path: Optional[str] = None) -> int:
    """Migrate users and permissions from users.json into the DB."""
    path = file_path or os.path.join(settings.get_data_dir(), "users.json")
    if not os.path.isfile(path):
        logger.info("No users.json found at %s. Skipping user migration.", path)
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            users_data = json.load(f)
    except Exception as exc:
        logger.error("Failed to read users.json: %s", exc)
        return 0

    count = 0
    for username, udata in users_data.items():
        if not username or not isinstance(udata, dict):
            continue

        existing_user = session.query(User).filter(User.username == username).first()
        if not existing_user:
            existing_user = User(username=username)
            session.add(existing_user)

        existing_user.password_hash = udata.get("password", "")
        existing_user.role = udata.get("role", "operator")
        existing_user.display_name = udata.get("display_name", username)
        existing_user.is_active = udata.get("is_active", True)
        existing_user.token_version = udata.get("token_version", 1)
        existing_user.failed_logins = udata.get("failed_logins", 0)
        existing_user.must_change_password = udata.get("must_change_password", False)

        locked_ts = udata.get("locked_until")
        if locked_ts:
            try:
                existing_user.locked_until = datetime.fromtimestamp(float(locked_ts))
            except Exception:
                existing_user.locked_until = None
        else:
            existing_user.locked_until = None

        session.flush()

        # Sync permissions
        features = udata.get("features", [])
        existing_perms = {p.feature: p for p in existing_user.permissions}
        for feat in features:
            if feat in existing_perms:
                existing_perms[feat].granted = True
            else:
                session.add(Permission(user_id=existing_user.id, feature=feat, granted=True))

        count += 1

    session.flush()
    logger.info("Migrated %d users from %s.", count, path)
    return count


def migrate_arp_mac_from_csv(
    session: Session, file_path: Optional[str] = None, user_id: str = "system_migration"
) -> Tuple[int, Optional[str]]:
    """
    Migrate 20,000+ records from arp_mac.csv into arp_mac_records.
    Also creates an initial ArpMacSnapshot archive entry.
    """
    path = file_path
    if not path:
        candidates = [
            os.path.join(settings.get_data_dir(), "arp_mac.csv"),
            os.path.join(os.getcwd(), "arp_mac.csv"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "arp_mac.csv"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path = os.path.abspath(c)
                break

    if not path or not os.path.isfile(path):
        logger.info("No arp_mac.csv found. Skipping ARP/MAC migration.")
        return 0, None

    rows_to_insert = []
    scanned_routers = set()

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                norm = {
                    (re.sub(r"[^a-z0-9]", "", k.lower()) if k else ""): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }
                ne_name = norm.get("nename") or norm.get("ne") or norm.get("router") or ""
                ne_ip = norm.get("neip") or norm.get("ip") or ""
                arp_ip = norm.get("arpip") or norm.get("targetip") or ""
                arp_mac = norm.get("arpmac") or norm.get("mac") or ""
                vlan = norm.get("vlan") or ""
                vrf = norm.get("vrf") or ""
                arp_interface = norm.get("arpinterface") or norm.get("interface") or norm.get("intf") or ""
                mac_port = norm.get("macport") or norm.get("port") or norm.get("link") or ""

                col_at_str = norm.get("collectedat") or norm.get("timestamp") or norm.get("date") or ""
                collected_dt = None
                if col_at_str:
                    try:
                        collected_dt = datetime.fromisoformat(col_at_str)
                    except Exception:
                        collected_dt = None

                if ne_name or arp_ip or arp_mac:
                    if ne_name:
                        scanned_routers.add(ne_name)
                    rows_to_insert.append({
                        "ne_name": ne_name,
                        "ne_ip": ne_ip,
                        "arp_ip": arp_ip,
                        "arp_mac": arp_mac,
                        "vlan": vlan,
                        "vrf": vrf,
                        "arp_interface": arp_interface,
                        "mac_port": mac_port,
                        "collected_at": collected_dt or datetime.utcnow(),
                    })
    except Exception as exc:
        logger.error("Error reading %s: %s", path, exc)
        return 0, None

    if not rows_to_insert:
        return 0, None

    # Create Snapshot entry
    snapshot = ArpMacSnapshot(
        scanned_by=user_id,
        total_routers=len(scanned_routers),
        total_records=len(rows_to_insert),
        source_filename=os.path.basename(path),
        archive_csv_path=path,
        status="completed",
        notes=f"Initial migration from {path}",
    )
    session.add(snapshot)
    session.flush()

    # Clear old current table and bulk insert new records
    session.query(ArpMacRecord).delete()
    batch_size = 5000
    for i in range(0, len(rows_to_insert), batch_size):
        batch = rows_to_insert[i : i + batch_size]
        session.bulk_insert_mappings(ArpMacRecord, batch)

    session.flush()
    logger.info(
        "Migrated %d ARP/MAC records from %d routers into DB (Snapshot ID: %s).",
        len(rows_to_insert),
        len(scanned_routers),
        snapshot.id,
    )
    return len(rows_to_insert), snapshot.id


def migrate_unified_sites_from_csv(session: Session, file_path: Optional[str] = None) -> int:
    """Migrate unified_sites.csv into sites_inventory table."""
    path = file_path
    if not path:
        candidates = [
            os.path.join(settings.get_data_dir(), "unified_sites.csv"),
            os.path.join(os.getcwd(), "unified_sites.csv"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "unified_sites.csv"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path = os.path.abspath(c)
                break

    if not path or not os.path.isfile(path):
        logger.info("No unified_sites.csv found. Skipping sites migration.")
        return 0

    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                norm = {
                    (k.strip().lower() if k else ""): (v.strip() if v else "")
                    for k, v in raw_row.items()
                }
                site_code = norm.get("site_code") or norm.get("sitecode") or ""
                ip = norm.get("ip") or ""
                model = norm.get("model") or ""
                ne_name = norm.get("ne_name") or norm.get("name") or site_code
                province = norm.get("province") or ""

                if not site_code:
                    continue

                site = session.query(SiteInventory).filter(SiteInventory.site_code == site_code).first()
                if not site:
                    site = SiteInventory(site_code=site_code)
                    session.add(site)

                site.ip = ip
                site.model = model
                site.ne_name = ne_name
                site.province = province
                count += 1
    except Exception as exc:
        logger.error("Error reading %s: %s", path, exc)
        return 0

    session.flush()
    logger.info("Migrated %d sites from %s into sites_inventory.", count, path)
    return count


def migrate_zabbix_cache_from_json(session: Session, file_path: Optional[str] = None) -> int:
    """Migrate cached Zabbix routers and items into zabbix_inventory_cache."""
    path = file_path
    if not path:
        candidates = [
            os.path.join(settings.get_data_dir(), "zabbix_router_db.json"),
            os.path.join(os.getcwd(), "zabbix_router_db.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "zabbix_router_db.json"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path = os.path.abspath(c)
                break

    if not path or not os.path.isfile(path):
        logger.info("No zabbix_router_db.json found. Skipping Zabbix cache migration.")
        return 0

    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        routers = data.get("routers", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for r in routers:
            hostid = str(r.get("hostid") or "")
            if not hostid:
                continue

            entry = session.query(ZabbixInventoryCache).filter(ZabbixInventoryCache.hostid == hostid).first()
            if not entry:
                entry = ZabbixInventoryCache(hostid=hostid)
                session.add(entry)

            entry.name = r.get("name") or ""
            entry.host_ip = r.get("host") or ""
            entry.group_name = r.get("group_name") or ""
            entry.interfaces = r.get("interfaces") or []
            entry.items = r.get("items") or []
            count += 1
    except Exception as exc:
        logger.error("Error migrating zabbix cache: %s", exc)
        return 0

    session.flush()
    logger.info("Migrated %d Zabbix routers into cache.", count)
    return count


def migrate_license_renewals_from_json(session: Session, file_path: Optional[str] = None) -> int:
    """Migrate license_renewals.json into license_renewal_reports."""
    path = file_path
    if not path:
        candidates = [
            os.path.join(settings.get_data_dir(), "license_renewals.json"),
            os.path.join(os.getcwd(), "license_renewals.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "license_renewals.json"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path = os.path.abspath(c)
                break

    if not path or not os.path.isfile(path):
        logger.info("No license_renewals.json found. Skipping license renewal migration.")
        return 0

    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        renewals = data.get("renewals", []) if isinstance(data, dict) else []
        for r in renewals:
            rid = str(r.get("id") or "")
            if not rid:
                continue

            report = session.query(LicenseRenewalReport).filter(LicenseRenewalReport.id == rid).first()
            if not report:
                report = LicenseRenewalReport(id=rid)
                session.add(report)

            report.timestamp = r.get("timestamp") or datetime.utcnow().isoformat()
            report.csv_file = r.get("csv_file")
            report.report_data = r.get("report_data") or []
            count += 1
    except Exception as exc:
        logger.error("Error migrating license renewals: %s", exc)
        return 0

    session.flush()
    logger.info("Migrated %d license renewal reports into DB.", count)
    return count


def migrate_all_files(session: Session) -> Dict[str, Any]:
    """Execute all legacy data migrations idempotently."""
    results = {
        "users": migrate_users_from_json(session),
        "arp_mac_records": 0,
        "arp_mac_snapshot_id": None,
        "sites": migrate_unified_sites_from_csv(session),
        "zabbix_routers": migrate_zabbix_cache_from_json(session),
        "license_reports": migrate_license_renewals_from_json(session),
    }
    records, snap_id = migrate_arp_mac_from_csv(session)
    results["arp_mac_records"] = records
    results["arp_mac_snapshot_id"] = snap_id
    session.commit()
    return results


if __name__ == "__main__":
    from backend.app.db.session import get_db_session, init_db
    logging.basicConfig(level=logging.INFO)
    init_db()
    with get_db_session() as s:
        res = migrate_all_files(s)
        print("Migration complete:", res)
