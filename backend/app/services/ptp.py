"""PTP & Telecom Sync Troubleshooting Service (Target Architecture §3 & Phase 5 Step 5.6).

Ports and enhances ptp_troubleshoot_service.py:
- Database-backed router and LLDP neighbor resolution (Device table + Zabbix)
- Upstream recursive clock tree traceback (Hop 0 -> Hop 1 -> ... -> Grandmaster)
- ITU-T G.8275.1 telecom sync health evaluation (offset, clock source, optics, alarms)
- Topology graph construction (nodes = routers, edges = PTP ports, colored by state)
- Automated Root Cause Analysis (RCA), text verdict, team demarcation, and handover ticket
"""
from __future__ import annotations
import os
import re
import ipaddress
from typing import Dict, Any, List, Optional, Tuple, Callable

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.models.device import Device
from backend.app.devices.session import DeviceSession
from ptp_troubleshoot_service import (
    parse_display_ptp_all,
    parse_display_ptp_interface,
    parse_display_clock_source,
    parse_display_interface,
    parse_display_alarm_active,
    parse_lldp_neighbor_brief,
    evaluate_hop_health,
    generate_demarcation_and_rca,
    resolve_router_info as legacy_resolve_router_info,
    PTP_OFFSET_HEALTHY_MAX_NS,
    PTP_OFFSET_WARNING_MAX_NS,
)


class PtpTroubleshootService:
    """Enterprise telecom synchronization and PTP hop-by-hop diagnostics service."""

    @classmethod
    def resolve_router(
        cls,
        db_session: Optional[Session],
        identifier: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve router identifier (Name, IP, Site Code, LSR ID) using DB inventory first, then legacy."""
        if not identifier:
            return None
        raw = identifier.strip()

        # 1. Check DB inventory
        if db_session is not None:
            dev = db_session.query(Device).filter(
                or_(
                    Device.name.ilike(raw),
                    Device.mgmt_ip == raw,
                    Device.site.ilike(raw),
                    Device.lsr_id == raw,
                )
            ).first()
            if dev:
                return {
                    "device_id": dev.id,
                    "name": dev.name,
                    "host": dev.mgmt_ip,
                    "site_code": dev.site or "",
                    "model": dev.model or "Huawei Router",
                    "role": dev.role or "PE",
                    "os_family": dev.os_family or "vrp8",
                    "source": "Inventory DB",
                }

        # 2. Check direct IP address
        try:
            ipaddress.ip_address(raw)
            return {
                "name": raw,
                "host": raw,
                "site_code": "",
                "model": "Generic Huawei NE",
                "role": "PE",
                "os_family": "vrp8",
                "source": "Direct IP",
            }
        except ValueError:
            pass

        # 3. Fallback to legacy resolution (zabbix_router_db.json / unified_sites.csv)
        legacy = legacy_resolve_router_info(raw)
        if legacy:
            return {
                "name": legacy.get("name", raw),
                "host": legacy.get("host", raw),
                "site_code": legacy.get("site_code", ""),
                "model": legacy.get("model", "Huawei NE"),
                "role": "PE",
                "os_family": "vrp8",
                "source": legacy.get("source", "Legacy Lookup"),
            }

        return None

    @classmethod
    def resolve_neighbor_ip(
        cls,
        db_session: Optional[Session],
        neighbor_name: str,
        lldp_mgmt_ip: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve upstream neighbor management IP from LLDP data and Inventory DB."""
        if lldp_mgmt_ip:
            try:
                ipaddress.ip_address(lldp_mgmt_ip.strip())
                return lldp_mgmt_ip.strip()
            except ValueError:
                pass

        if not neighbor_name:
            return None

        # Clean neighbor name (strip domain suffix or interface)
        clean_name = neighbor_name.split(".")[0].strip()

        if db_session is not None:
            dev = db_session.query(Device).filter(
                or_(
                    Device.name.ilike(clean_name),
                    Device.name.ilike(f"{clean_name}%"),
                    Device.site.ilike(clean_name),
                )
            ).first()
            if dev:
                return dev.mgmt_ip

        # Fallback to legacy
        res = cls.resolve_router(db_session, clean_name)
        if res and res.get("host"):
            return res["host"]

        return None

    @classmethod
    def run_traceback(
        cls,
        db_session: Optional[Session],
        target_identifier: str,
        max_hops: int = 5,
        session_mock: Optional[Any] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """Execute automated live PTP diagnostic and upstream traceback hop-by-hop.

        Constructs per-hop diagnostic evaluations, visual topology graph,
        Root Cause Analysis, and text verdict.
        """
        def _log(msg: str, level: str = "info"):
            if log_callback:
                log_callback(msg, level)

        target_info = cls.resolve_router(db_session, target_identifier)
        if not target_info:
            target_info = {
                "name": target_identifier,
                "host": target_identifier,
                "site_code": "",
                "model": "Generic Huawei NE",
                "role": "PE",
                "os_family": "vrp8",
                "source": "Direct Input",
            }

        _log(f"Initiating PTP traceback for target '{target_info['name']}' ({target_info['host']}) ...", "highlight")

        hop_chain: List[Dict[str, Any]] = []
        visited_hosts = set()
        current_node = target_info
        hop_index = 0

        while hop_index < max_hops:
            current_name = current_node.get("name", "Unknown")
            current_host = current_node.get("host", "").strip()

            if not current_host:
                _log(f"Hop {hop_index}: Missing IP address for node '{current_name}' — ending trace.", "warn")
                break

            if current_host in visited_hosts:
                _log(f"Hop {hop_index}: Loop detected at {current_host} ({current_name}) — terminating traceback.", "warn")
                break
            visited_hosts.add(current_host)

            _log(f"Hop {hop_index}: Connecting to {current_name} ({current_host}) ...", "info")

            hop_record: Dict[str, Any] = {
                "hop": hop_index,
                "name": current_name,
                "host": current_host,
                "site_code": current_node.get("site_code", ""),
                "model": current_node.get("model", ""),
                "role": current_node.get("role", "PE"),
                "ptp": {},
                "clock_source": {},
                "interface": {},
                "alarms": [],
                "lldp": {},
                "evaluation": {},
                "error": None,
            }

            try:
                # 1. Fetch CLI outputs
                if session_mock is not None:
                    ptp_raw = session_mock.run("display ptp all")
                    clk_raw = session_mock.run("display clock source")
                    alarm_raw = session_mock.run("display alarm active | include PTP")
                    lldp_raw = session_mock.run("display lldp neighbor brief")
                else:
                    os_fam = current_node.get("os_family", "vrp8")
                    with DeviceSession(device_name=current_name, host=current_host, os_family=os_fam) as ds:
                        ptp_raw = ds.run("display ptp all")
                        clk_raw = ds.run("display clock source")
                        alarm_raw = ds.run("display alarm active | include PTP")
                        lldp_raw = ds.run("display lldp neighbor brief")

                # Parse basic PTP & clock source
                ptp_data = parse_display_ptp_all(ptp_raw)
                hop_record["ptp"] = ptp_data
                hop_record["clock_source"] = parse_display_clock_source(clk_raw)
                hop_record["alarms"] = parse_display_alarm_active(alarm_raw)

                slave_interface = ptp_data.get("receive_number", "")
                parent_dev_name = ""
                parent_dev_ip = ""

                # Query interface details & optics if slave interface exists
                if slave_interface:
                    if session_mock is not None:
                        iface_raw = session_mock.run(f"display ptp interface {slave_interface}")
                        opt_raw = session_mock.run(f"display interface {slave_interface}")
                    else:
                        with DeviceSession(device_name=current_name, host=current_host, os_family=os_fam) as ds:
                            iface_raw = ds.run(f"display ptp interface {slave_interface}")
                            opt_raw = ds.run(f"display interface {slave_interface}")

                    iface_data = parse_display_ptp_interface(iface_raw)
                    optics_data = parse_display_interface(opt_raw)
                    iface_data["optics"] = optics_data
                    hop_record["interface"] = iface_data

                    # Resolve LLDP neighbor for slave interface
                    neighbors = parse_lldp_neighbor_brief(lldp_raw, target_local_iface=slave_interface)
                    if neighbors:
                        hop_record["lldp"] = neighbors[0]
                        parent_dev_name = neighbors[0].get("neighbor_device") or neighbors[0].get("neighbor_dev", "")
                        parent_dev_ip = neighbors[0].get("neighbor_ip", "")

                # Evaluate Hop Health
                eval_data = evaluate_hop_health(hop_record)
                hop_record["evaluation"] = eval_data
                hop_chain.append(hop_record)

                # Check termination (Reached Root GM or no slave port)
                step_removed = ptp_data.get("step_removed")
                if not slave_interface or step_removed == 1 or step_removed == 0:
                    _log(f"Hop {hop_index}: Reached clock distribution root / Grandmaster ({current_name})", "success")
                    break

                # Resolve next upstream neighbor node using DB inventory
                resolved_parent_ip = cls.resolve_neighbor_ip(
                    db_session=db_session,
                    neighbor_name=parent_dev_name,
                    lldp_mgmt_ip=parent_dev_ip,
                )

                if resolved_parent_ip:
                    next_node = cls.resolve_router(db_session, resolved_parent_ip) or {
                        "name": parent_dev_name or resolved_parent_ip,
                        "host": resolved_parent_ip,
                        "site_code": "",
                        "model": "Huawei Router",
                        "role": "AGG",
                        "os_family": "vrp8",
                    }
                elif parent_dev_name:
                    next_node = cls.resolve_router(db_session, parent_dev_name) or {
                        "name": parent_dev_name,
                        "host": "",
                        "site_code": "",
                        "model": "Huawei Router",
                        "role": "AGG",
                        "os_family": "vrp8",
                    }
                else:
                    _log(f"Hop {hop_index}: No upstream neighbor identified on slave interface — ending trace.", "warn")
                    break

                current_node = next_node
                hop_index += 1

            except Exception as exc:
                err_msg = str(exc)
                _log(f"Hop {hop_index}: SSH diagnostic failed on {current_name} ({current_host}): {err_msg}", "warn")
                hop_record["error"] = err_msg
                hop_record["evaluation"] = {
                    "status": "CRITICAL",
                    "findings": [f"SSH Diagnostic Error: {err_msg}"],
                    "is_gm_loss": False,
                    "is_physical_defect": False,
                    "is_fiber_asymmetry_candidate": False,
                }
                hop_chain.append(hop_record)
                break

        # Generate RCA and Demarcation
        demarcation = generate_demarcation_and_rca(hop_chain)

        # Assemble Visual Topology Graph
        topology_graph = cls.build_topology_graph(hop_chain)

        # Assemble Text Verdict
        text_verdict = cls.build_text_verdict(hop_chain, demarcation)

        return {
            "target": target_info,
            "hop_count": len(hop_chain),
            "overall_status": demarcation.get("overall_status", "UNKNOWN"),
            "text_verdict": text_verdict,
            "topology_graph": topology_graph,
            "demarcation": demarcation,
            "hop_chain": hop_chain,
        }

    @classmethod
    def build_topology_graph(cls, hop_chain: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build node-edge graph structure colored by sync state (HEALTHY, WARNING, CRITICAL)."""
        nodes = []
        edges = []

        for i, hop in enumerate(hop_chain):
            status = hop.get("evaluation", {}).get("status", "HEALTHY")
            ptp = hop.get("ptp", {})
            clock_class = ptp.get("clock_class")
            step = ptp.get("step_removed")

            role_label = "Grandmaster (T-GM)" if step in (0, 1) or i == len(hop_chain) - 1 else (
                "Boundary Clock (T-BC)" if i > 0 else "Slave (Target)"
            )

            offset = ptp.get("realtime_t2_t1") or ptp.get("time_offset")
            offset_str = f"{offset:+.1f} ns" if offset is not None else "N/A"

            node_id = f"hop_{i}"
            nodes.append({
                "id": node_id,
                "name": hop.get("name", f"Hop-{i}"),
                "host": hop.get("host", ""),
                "hop_index": i,
                "role": role_label,
                "status": status,
                "clock_id": ptp.get("local_clock_id", ""),
                "clock_class": clock_class,
                "offset": offset_str,
                "findings": hop.get("evaluation", {}).get("findings", []),
                "is_faulty": status == "CRITICAL",
            })

            # Edge to previous downstream node
            if i > 0:
                prev_node_id = f"hop_{i-1}"
                downstream_hop = hop_chain[i-1]
                iface_info = downstream_hop.get("interface", {})
                port_name = iface_info.get("interface_name") or downstream_hop.get("ptp", {}).get("receive_number", "PTP")
                link_status = downstream_hop.get("evaluation", {}).get("status", "HEALTHY")
                t2_t1 = iface_info.get("realtime_t2_t1")

                edges.append({
                    "source": node_id,  # From upstream (master/parent)
                    "target": prev_node_id,  # To downstream (slave)
                    "port": port_name,
                    "state": link_status,
                    "offset_ns": t2_t1,
                    "path_delay_ns": iface_info.get("path_delay"),
                    "label": f"{port_name} ({t2_t1:+.1f} ns)" if t2_t1 is not None else port_name,
                })

        return {
            "nodes": nodes,
            "edges": edges,
        }

    @staticmethod
    def build_text_verdict(hop_chain: List[Dict[str, Any]], demarcation: Dict[str, Any]) -> str:
        """Generate high-level NOC verdict string."""
        overall = demarcation.get("overall_status", "HEALTHY")
        if overall == "HEALTHY":
            return "All evaluated nodes in the PTP distribution chain are healthy and in-sync (ITU-T G.8275.1 compliant, offset <= 100 ns)."

        # Find the earliest upstream node where failure occurred
        faulty_hops = [h for h in hop_chain if h.get("evaluation", {}).get("status") in ("CRITICAL", "WARNING")]
        if not faulty_hops:
            return demarcation.get("root_cause", "PTP anomaly detected.")

        deepest = faulty_hops[-1]  # Root cause is furthest upstream faulty hop
        hop_num = deepest.get("hop", 0)
        node_name = deepest.get("name", "Unknown")
        findings = deepest.get("evaluation", {}).get("findings", [])
        finding_summary = findings[0] if findings else "Synchronization anomaly detected"

        team = demarcation.get("responsible_team", "IP Team")
        return f"Sync degradation originating at Hop {hop_num} ({node_name}): {finding_summary}. Best clock lost at hop {hop_num}. Assigned: {team}."
