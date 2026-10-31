"""Site ARP & MAC Address Lookup and Collector Service (Phase 5 Step 5.7).

Provides:
- Database-backed Site and IP ARP/MAC lookup with fallback to legacy CSVs.
- Cross-referencing: Site_Code -> IP -> ARP_MAC -> Shared MAC devices across fleet.
- In-memory result cache with Time-To-Live (TTL) and freshness indicators.
- Background collector job execution with thread-safe progress tracking and real cancellation.
- Database persistence (ArpMacRecord, ArpMacSnapshot, ArpMacHistory).
- Search filtering and UTF-8-SIG CSV export.
"""
from __future__ import annotations
import csv
import io
import re
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models.arp_mac import (
    ArpMacRecord,
    ArpMacSnapshot,
    ArpMacHistory,
    SiteInventory,
)
from backend.app.models.device import Device
from site_arp_service import (
    normalize_mac,
    parse_arp,
    parse_mac_table,
    enrich_from_mac_table,
    parse_ne_csv_content,
    TARGET_NE_PREFIXES,
    lookup_site_arp_mac_details as legacy_lookup_site,
    lookup_ip_arp_mac_details as legacy_lookup_ip,
    save_or_update_arp_mac_csv,
    get_target_arp_mac_csv_path,
)

logger = logging.getLogger(__name__)


class ArpCache:
    """Thread-safe in-memory TTL cache for ARP/MAC lookups."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str, ttl_seconds: int = 300) -> Optional[Dict[str, Any]]:
        norm_key = key.strip().lower()
        now = time.time()
        with self._lock:
            entry = self._cache.get(norm_key)
            if not entry:
                return None
            cached_at = entry.get("timestamp", 0)
            age = now - cached_at
            if age > ttl_seconds:
                # Expired
                del self._cache[norm_key]
                return None
            # Return copy with freshness metadata
            result = dict(entry["data"])
            result["freshness"] = {
                "cached_at": datetime.fromtimestamp(cached_at).isoformat(),
                "age_seconds": round(age, 1),
                "ttl_seconds": ttl_seconds,
                "is_fresh": True,
            }
            return result

    def set(self, key: str, data: Dict[str, Any]):
        norm_key = key.strip().lower()
        with self._lock:
            self._cache[norm_key] = {
                "timestamp": time.time(),
                "data": dict(data),
            }

    def clear(self):
        with self._lock:
            self._cache.clear()


# Global cache instance
arp_cache = ArpCache()


class SiteArpService:
    """Enterprise Site and IP ARP/MAC lookup and search service."""

    @classmethod
    def lookup(
        cls,
        db_session: Optional[Session],
        query: str,
        ttl_seconds: int = 300,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Unified lookup router: auto-detects Site Code vs IP address with TTL caching."""
        if not query or not query.strip():
            return {
                "success": False,
                "error": "Site code or IP address is required.",
                "results": [],
                "count": 0,
            }

        cleaned = query.strip()
        cache_key = f"query:{cleaned}"

        if not force_refresh:
            cached = arp_cache.get(cache_key, ttl_seconds=ttl_seconds)
            if cached:
                return cached

        # Check if query is IPv4 address
        is_ip = bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", cleaned))

        if is_ip:
            result = cls.lookup_by_ip(db_session, cleaned)
        else:
            result = cls.lookup_by_site(db_session, cleaned)

        # Attach freshness info
        result["freshness"] = {
            "cached_at": datetime.now().isoformat(),
            "age_seconds": 0.0,
            "ttl_seconds": ttl_seconds,
            "is_fresh": True,
        }

        if result.get("success"):
            arp_cache.set(cache_key, result)

        return result

    @classmethod
    def lookup_by_site(
        cls,
        db_session: Optional[Session],
        site_code: str,
    ) -> Dict[str, Any]:
        """Lookup by Site Code: Site -> IP -> MAC -> all records matching that MAC."""
        cleaned = site_code.strip()
        matched_sites: List[Dict[str, str]] = []

        # 1. Search in DB SiteInventory first
        if db_session is not None:
            sites_q = db_session.query(SiteInventory).filter(
                or_(
                    SiteInventory.site_code.ilike(cleaned),
                    SiteInventory.site_code.ilike(f"{cleaned}%"),
                )
            ).all()
            for s in sites_q:
                matched_sites.append({
                    "site_code": s.site_code,
                    "ip": s.ip,
                    "model": s.model or "-",
                })

            # Check Device table if no SiteInventory entry
            if not matched_sites:
                devs = db_session.query(Device).filter(
                    or_(
                        Device.site.ilike(cleaned),
                        Device.name.ilike(f"%{cleaned}%"),
                    )
                ).all()
                for d in devs:
                    matched_sites.append({
                        "site_code": d.site or d.name,
                        "ip": d.mgmt_ip,
                        "model": d.model or "-",
                    })

        # 2. Fallback to legacy file if DB didn't find anything
        if not matched_sites:
            legacy_res = legacy_lookup_site(cleaned)
            if legacy_res.get("success") or legacy_res.get("count", 0) > 0:
                return legacy_res
            if not db_session:
                return legacy_res

        if not matched_sites:
            return {
                "success": False,
                "error": f"Site Code '{cleaned}' not found.",
                "site_code": cleaned,
                "results": [],
                "count": 0,
            }

        target_ips = {s["ip"].strip() for s in matched_sites if s.get("ip")}
        ip_to_site = {s["ip"].strip(): s for s in matched_sites if s.get("ip")}

        if not target_ips:
            return {
                "success": False,
                "error": f"Site Code '{cleaned}' has no IP address assigned.",
                "site_code": cleaned,
                "sites": matched_sites,
                "results": [],
                "count": 0,
            }

        # Query ArpMacRecord table for target IPs
        arp_records = db_session.query(ArpMacRecord).filter(
            or_(
                ArpMacRecord.arp_ip.in_(target_ips),
                ArpMacRecord.ne_ip.in_(target_ips),
            )
        ).all()

        if not arp_records:
            # Fallback to legacy file lookup
            legacy_res = legacy_lookup_site(cleaned)
            if legacy_res.get("success") and legacy_res.get("count", 0) > 0:
                return legacy_res
            return {
                "success": False,
                "error": f"No ARP entry found for Site '{cleaned}' (IPs: {', '.join(sorted(target_ips))}).",
                "site_code": cleaned,
                "sites": matched_sites,
                "results": [],
                "count": 0,
            }

        matched_macs: Set[str] = set()
        direct_rows: List[ArpMacRecord] = []
        for r in arp_records:
            norm_m = normalize_mac(r.arp_mac)
            if norm_m:
                matched_macs.add(norm_m)
                direct_rows.append(r)

        # Query all records sharing that same MAC
        related_rows: List[ArpMacRecord] = []
        if matched_macs:
            # Match either raw or formatted
            all_by_mac = db_session.query(ArpMacRecord).filter(
                ArpMacRecord.arp_mac.in_([r.arp_mac for r in direct_rows])
            ).all()
            for r in all_by_mac:
                if r not in direct_rows:
                    related_rows.append(r)

        # Assemble combined rows
        combined = cls._assemble_rows(direct_rows + related_rows, ip_to_site, default_site=matched_sites[0])
        direct_macs = list(dict.fromkeys(r.arp_mac for r in direct_rows if r.arp_mac))

        return {
            "success": True,
            "site_code": cleaned,
            "count": len(combined),
            "results": combined,
            "sites": matched_sites,
            "macs": direct_macs if direct_macs else list(matched_macs),
        }

    @classmethod
    def lookup_by_ip(
        cls,
        db_session: Optional[Session],
        ip_address: str,
    ) -> Dict[str, Any]:
        """Lookup by IP address: IP -> MAC -> all records sharing that MAC."""
        cleaned = ip_address.strip()

        if db_session is None:
            return legacy_lookup_ip(cleaned)

        # Find direct matches by arp_ip or ne_ip
        direct_matches = db_session.query(ArpMacRecord).filter(
            or_(
                ArpMacRecord.arp_ip == cleaned,
                ArpMacRecord.ne_ip == cleaned,
            )
        ).all()

        if not direct_matches:
            # Fallback to legacy
            legacy_res = legacy_lookup_ip(cleaned)
            if legacy_res.get("success") and legacy_res.get("count", 0) > 0:
                return legacy_res
            return {
                "success": False,
                "error": f"No ARP entry found for IP: {cleaned}.",
                "query_ip": cleaned,
                "results": [],
                "count": 0,
            }

        matched_mac_strs = {r.arp_mac for r in direct_matches if r.arp_mac}
        normalized_macs = {normalize_mac(m) for m in matched_mac_strs if normalize_mac(m)}

        # Find related records sharing the same MAC
        related_matches = db_session.query(ArpMacRecord).filter(
            ArpMacRecord.arp_mac.in_(matched_mac_strs),
            ArpMacRecord.arp_ip != cleaned,
            ArpMacRecord.ne_ip != cleaned,
        ).all()

        # Resolve site inventory for IPs
        all_records = direct_matches + related_matches
        ip_set = {r.arp_ip for r in all_records if r.arp_ip} | {r.ne_ip for r in all_records if r.ne_ip}

        ip_to_site: Dict[str, Dict[str, str]] = {}
        sites = db_session.query(SiteInventory).filter(SiteInventory.ip.in_(ip_set)).all()
        for s in sites:
            ip_to_site[s.ip] = {"site_code": s.site_code, "model": s.model or "-", "ip": s.ip}

        combined = cls._assemble_rows(all_records, ip_to_site)
        direct_macs = list(dict.fromkeys(r.arp_mac for r in direct_matches if r.arp_mac))
        site_display = combined[0]["Site_Code"] if combined and combined[0]["Site_Code"] != "-" else ""

        return {
            "success": True,
            "query_ip": cleaned,
            "site_code": site_display,
            "count": len(combined),
            "results": combined,
            "macs": direct_macs,
        }

    @staticmethod
    def _assemble_rows(
        records: List[ArpMacRecord],
        ip_to_site: Dict[str, Dict[str, str]],
        default_site: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        combined: List[Dict[str, Any]] = []
        seen = set()

        for r in records:
            key = (r.ne_name, r.arp_ip, r.arp_mac, r.vlan, r.arp_interface, r.mac_port)
            if key in seen:
                continue
            seen.add(key)

            rec_ip = r.arp_ip.strip() or r.ne_ip.strip()
            site_info = ip_to_site.get(rec_ip) or default_site or {
                "site_code": "-",
                "model": "-",
                "ip": rec_ip,
            }

            combined.append({
                "Site_Code": site_info.get("site_code") or "-",
                "VRF": r.vrf or "",
                "VRF_IP": rec_ip,
                "Site_Model": site_info.get("model") or "-",
                "IP": rec_ip,
                "Model": site_info.get("model") or "-",
                "NE": r.ne_name,
                "NE_IP": r.ne_ip,
                "ARP_MAC": r.arp_mac,
                "Vlan": r.vlan or "",
                "ARP_Interface": r.arp_interface or "",
                "MAC_Port": r.mac_port or "",
                "Link": r.mac_port or "",
                "collected_at": r.collected_at.isoformat() if r.collected_at else "",
            })

        return combined

    @staticmethod
    def filter_results(
        results: List[Dict[str, Any]],
        keyword: Optional[str] = None,
        vlan: Optional[str] = None,
        vrf: Optional[str] = None,
        ne_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Filter results table by multiple column criteria."""
        filtered = results
        if keyword:
            kw = keyword.strip().lower()
            filtered = [
                r for r in filtered
                if any(kw in str(v).lower() for v in r.values())
            ]
        if vlan:
            vl = vlan.strip()
            filtered = [r for r in filtered if r.get("Vlan") == vl]
        if vrf:
            vf = vrf.strip().lower()
            filtered = [r for r in filtered if vf in str(r.get("VRF", "")).lower()]
        if ne_name:
            ne = ne_name.strip().lower()
            filtered = [r for r in filtered if ne in str(r.get("NE", "")).lower()]
        return filtered

    @staticmethod
    def export_csv(results: List[Dict[str, Any]]) -> str:
        """Export list of ARP/MAC results to CSV string formatted with UTF-8 BOM."""
        fieldnames = [
            "Site_Code", "IP", "Model", "NE", "NE_IP",
            "ARP_MAC", "Vlan", "VRF", "ARP_Interface", "MAC_Port", "collected_at"
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)
        return out.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Background Collector Engine with Real Cancellation
# ──────────────────────────────────────────────────────────────────────────────

class ArpCollectorManager:
    """Thread-safe background collector job manager with graceful cancellation and DB persistence."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._active_job: Dict[str, Any] = {
            "status": "idle",  # idle | running | done | stopped | error
            "total": 0,
            "completed": 0,
            "current_router": "",
            "rows_collected": 0,
            "logs": [],
            "error": None,
            "started_at": None,
            "finished_at": None,
        }

    def get_status(self) -> Dict[str, Any]:
        """Return snapshot of current collector job status."""
        with self._lock:
            total = self._active_job["total"]
            completed = self._active_job["completed"]
            pct = round((completed / total * 100), 1) if total > 0 else 0.0
            return {
                "status": self._active_job["status"],
                "total": total,
                "completed": completed,
                "progress_pct": pct,
                "current_router": self._active_job["current_router"],
                "rows_collected": self._active_job["rows_collected"],
                "logs": list(self._active_job["logs"][-60:]),
                "error": self._active_job["error"],
                "started_at": self._active_job["started_at"],
                "finished_at": self._active_job["finished_at"],
            }

    def stop(self) -> bool:
        """Signal real cancellation to the running collector job."""
        with self._lock:
            if self._active_job["status"] == "running":
                self._stop_event.set()
                self._active_job["status"] = "stopped"
                self._active_job["logs"].append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Cancellation requested by user."
                )
                return True
        return False

    def start_job(
        self,
        routers: List[Dict[str, Any]],
        username: str = "",
        password: str = "",
        max_workers: int = 10,
        db_session_factory: Optional[Callable[[], Session]] = None,
        session_mock: Optional[Any] = None,
    ) -> bool:
        """Start collector background job if not already running."""
        with self._lock:
            if self._active_job["status"] == "running":
                return False

            self._stop_event.clear()
            self._active_job = {
                "status": "running",
                "total": len(routers),
                "completed": 0,
                "current_router": "",
                "rows_collected": 0,
                "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] Starting ARP/MAC collector for {len(routers)} routers (concurrency: {max_workers})."],
                "error": None,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
            }

        def _worker():
            all_collected: List[Dict[str, Any]] = []
            scanned_names: Set[str] = set()

            def _log(msg: str):
                t_str = datetime.now().strftime("%H:%M:%S")
                with self._lock:
                    self._active_job["logs"].append(f"[{t_str}] {msg}")

            try:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ArpWorker") as executor:
                    futures = {}
                    for r in routers:
                        if self._stop_event.is_set():
                            break

                        ne_name = r.get("name") or r.get("ne_name", "")
                        ne_ip = r.get("ip") or r.get("mgmt_ip", "")

                        f = executor.submit(
                            self._collect_single_router,
                            ne_name=ne_name,
                            ne_ip=ne_ip,
                            ne_type=r.get("ne_type", ""),
                            username=username,
                            password=password,
                            session_mock=session_mock,
                            log_cb=_log,
                        )
                        futures[f] = ne_name

                    for future in as_completed(futures):
                        ne_name = futures[future]
                        if self._stop_event.is_set():
                            _log(f"Aborting execution for remaining routers (stop requested).")
                            for f in futures:
                                f.cancel()
                            break

                        with self._lock:
                            self._active_job["completed"] += 1
                            self._active_job["current_router"] = ne_name

                        try:
                            rows = future.result()
                            scanned_names.add(ne_name)
                            all_collected.extend(rows)
                            with self._lock:
                                self._active_job["rows_collected"] = len(all_collected)
                        except Exception as exc:
                            _log(f"Failed on {ne_name}: {exc}")

                # Save results to Database
                if db_session_factory and all_collected:
                    self._persist_to_db(db_session_factory, all_collected, scanned_names)

                # Also update local fallback CSV
                try:
                    save_or_update_arp_mac_csv(all_collected, scanned_names)
                except Exception as exc:
                    _log(f"Warning: could not update arp_mac.csv: {exc}")

                # Invalidate lookup cache
                arp_cache.clear()

                with self._lock:
                    self._active_job["finished_at"] = datetime.now().isoformat()
                    if self._stop_event.is_set():
                        self._active_job["status"] = "stopped"
                        self._active_job["logs"].append(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Job successfully cancelled. Gathered {len(all_collected)} rows from {len(scanned_names)} routers."
                        )
                    else:
                        self._active_job["status"] = "done"
                        self._active_job["logs"].append(
                            f"[{datetime.now().strftime('%H:%M:%S')}] Scan finished. Saved {len(all_collected)} rows across {len(scanned_names)} routers."
                        )

            except Exception as exc:
                with self._lock:
                    self._active_job["status"] = "error"
                    self._active_job["error"] = str(exc)
                    self._active_job["finished_at"] = datetime.now().isoformat()
                    self._active_job["logs"].append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Fatal collector failure: {exc}"
                    )

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True

    def _collect_single_router(
        self,
        ne_name: str,
        ne_ip: str,
        ne_type: str,
        username: str,
        password: str,
        session_mock: Optional[Any],
        log_cb: Callable[[str], None],
    ) -> List[Dict[str, Any]]:
        """Collect ARP and MAC entries from a single router."""
        if self._stop_event.is_set():
            return []

        log_cb(f"Collecting from {ne_name} ({ne_ip}) ...")
        now_dt = datetime.now()

        if session_mock is not None:
            if self._stop_event.is_set():
                return []
            arp_raw = session_mock.run("display arp all | no-more")
            if self._stop_event.is_set():
                return []
            mac_raw = session_mock.run("display mac-address | no-more")
        else:
            if self._stop_event.is_set():
                return []
            from site_arp_service import collect_router_arp_mac
            return collect_router_arp_mac(
                ne_name=ne_name,
                ip=ne_ip,
                ne_type=ne_type,
                username=username,
                password=password,
                log_cb=log_cb,
            )

        arp_entries = parse_arp(arp_raw)
        mac_table = parse_mac_table(mac_raw)

        rows = []
        for entry in arp_entries:
            enrich_from_mac_table(entry, mac_table)
            rows.append({
                "ne_name": ne_name,
                "ne_ip": ne_ip,
                "arp_ip": entry["arp_ip"],
                "arp_mac": entry["arp_mac"],
                "vlan": entry.get("vlan", ""),
                "vrf": entry.get("vrf", ""),
                "arp_interface": entry.get("interface", ""),
                "mac_port": entry.get("mac_port", ""),
                "collected_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            })

        log_cb(f"Finished {ne_name}: gathered {len(rows)} entries.")
        return rows

    def _persist_to_db(
        self,
        db_session_factory: Callable[[], Session],
        rows: List[Dict[str, Any]],
        scanned_ne_names: Set[str],
    ) -> None:
        """Upsert ArpMacRecord and store ArpMacSnapshot."""
        try:
            with db_session_factory() as session:
                # 1. Clear previous records for scanned routers
                if scanned_ne_names:
                    session.query(ArpMacRecord).filter(
                        ArpMacRecord.ne_name.in_(scanned_ne_names)
                    ).delete(synchronize_session=False)

                # 2. Insert new live records
                db_records = []
                for r in rows:
                    coll_at = None
                    if r.get("collected_at"):
                        try:
                            coll_at = datetime.strptime(r["collected_at"], "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            coll_at = datetime.utcnow()

                    rec = ArpMacRecord(
                        ne_name=r["ne_name"],
                        ne_ip=r.get("ne_ip", ""),
                        arp_ip=r.get("arp_ip", ""),
                        arp_mac=r.get("arp_mac", ""),
                        vlan=r.get("vlan") or "",
                        vrf=r.get("vrf") or "",
                        arp_interface=r.get("arp_interface") or "",
                        mac_port=r.get("mac_port") or "",
                        collected_at=coll_at or datetime.utcnow(),
                    )
                    db_records.append(rec)

                session.add_all(db_records)

                # 3. Create ArpMacSnapshot archive
                snapshot = ArpMacSnapshot(
                    scanned_by="system_collector",
                    total_routers=len(scanned_ne_names),
                    total_records=len(rows),
                    status="completed",
                )
                session.add(snapshot)
                session.flush()

                # 4. Insert history items
                history_items = [
                    ArpMacHistory(
                        snapshot_id=snapshot.id,
                        ne_name=r["ne_name"],
                        ne_ip=r.get("ne_ip", ""),
                        arp_ip=r.get("arp_ip", ""),
                        arp_mac=r.get("arp_mac", ""),
                        vlan=r.get("vlan") or "",
                        vrf=r.get("vrf") or "",
                        arp_interface=r.get("arp_interface") or "",
                        mac_port=r.get("mac_port") or "",
                        collected_at=datetime.utcnow(),
                    )
                    for r in rows
                ]
                session.add_all(history_items)
                session.commit()
                logger.info("Persisted %d ARP records and snapshot %s to DB", len(rows), snapshot.id)
        except Exception as exc:
            logger.error("Failed to persist ARP collector results to DB: %s", exc)


# Global collector manager
arp_collector_manager = ArpCollectorManager()
