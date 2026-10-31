"""VRF & Routing Hop-by-Hop Trace and Path Graph Service (Step 5.5).

Ports and enhances check_vrf_routing.py:
- VRF/Target IP strict validation
- RT/VRF mapping and BGP VPNv4 received-routes parsing
- Originator IP translation (transform_originator_ip)
- VRF routing table lookup and interface config inspection
- Per-hop result table and visual path graph construction (originator -> RR -> PE -> CE)
"""
from __future__ import annotations
import re
import ipaddress
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from validators import validate_vrf_name, validate_target_ip
from settings import (
    VRF_ROUTER_NAME,
    VRF_ROUTER_IP,
    VRF_RR_IP,
)
from backend.app.models.device import Device
from backend.app.devices.session import DeviceSession


PROTOCOL_CATEGORY_MAP = {
    'O':       'OSPF',
    'O_ASE':   'OSPF',
    'O_NSSA':  'OSPF',
    'OSPF':    'OSPF',
    'B':       'BGP',
    'IB':      'IBGP',
    'EB':      'EBGP',
    'BGP':     'BGP',
    'S':       'Static',
    'STATIC':  'Static',
    'D':       'Direct',
    'DIRECT':  'Direct',
    'R':       'RIP',
    'RIP':     'RIP',
    'ISIS':    'IS-IS',
    'ISIS_L1': 'IS-IS',
    'ISIS_L2': 'IS-IS',
    'UNR':     'UNR',
}

VRF_RT_MAP: Dict[str, List[str]] = {
    "MCCI_ADCC": ["65000:532"],
    "MCCI_Anarestan": ["65000:525"],
    "MCCI_B2B_AFTA": ["65000:530"],
    "MCCI_B2B_GITI": ["65000:528"],
    "MCCI_B2B_JUDIC": ["65000:526"],
    "MCCI_B2B_NAHAD": ["65000:520"],
    "MCCI_B2B_PIP": ["65000:512"],
    "MCCI_B2B_RW": ["65000:511"],
    "MCCI_Billing": ["65000:400"],
    "MCCI_CC": ["65000:602"],
    "MCCI_CDN": ["65000:5502"],
    "MCCI_CI": ["65000:510"],
    "MCCI_CM": ["65000:600"],
    "MCCI_CP": ["65000:200"],
    "MCCI_FTTX": ["65000:522"],
    "MCCI_GVMT": ["65000:550"],
    "MCCI_Hostiran": ["65000:513"],
    "MCCI_IPDR": ["65000:606"],
    "MCCI_IT": ["65000:2000"],
    "MCCI_ITG": ["65000:3000"],
    "MCCI_Internal": ["65000:700"],
    "MCCI_Internet": ["65000:500"],
    "MCCI_MOI": ["65000:505"],
    "MCCI_Mobin": ["65000:900"],
    "MCCI_OM": ["65000:300"],
    "MCCI_Roaming": ["65000:6000"],
    "MCCI_Taliya": ["65000:515"],
    "MCCI_UP": ["65000:100"],
    "MCCI_UP4G": ["65000:5000"],
    "MCCI_UP5G": ["65000:5005"],
    "MCCI_UPPS": ["65000:800"],
}


def _build_rt_to_vrf_map() -> Dict[str, List[str]]:
    rt_to_vrf: Dict[str, List[str]] = {}
    for vrf, rt_list in VRF_RT_MAP.items():
        for rt in rt_list:
            rt_to_vrf.setdefault(rt, []).append(vrf)
    return rt_to_vrf


RT_TO_VRF_MAP = _build_rt_to_vrf_map()


class VrfRoutingService:
    """Enterprise VRF and BGP VPNv4 routing investigation service."""

    @staticmethod
    def validate_vrf_and_target(vrf: str, target: str) -> Tuple[str, str]:
        """Strictly validate VRF name and target IP/prefix."""
        clean_vrf = validate_vrf_name(vrf.strip())
        raw_target = target.strip()
        # Handle CIDR or single IP
        if "/" in raw_target:
            ip_part, mask_part = raw_target.split("/", 1)
            clean_ip = validate_target_ip(ip_part)
            if not mask_part.isdigit() or not (0 <= int(mask_part) <= 32):
                raise ValueError("Invalid prefix length in target CIDR")
            clean_target = f"{clean_ip}/{mask_part}"
        else:
            clean_target = validate_target_ip(raw_target)
        return clean_vrf, clean_target

    @staticmethod
    def extract_rt_values(ext_community_str: str) -> List[str]:
        """Extract Route Target values from BGP Ext-Community string."""
        m = re.findall(r'RT\s*<\s*(\d+)\s*:\s*(\d+)\s*>', ext_community_str)
        return [f"{a}:{b}" for a, b in m]

    @staticmethod
    def match_vrfs_by_rt(rt_values: List[str]) -> Dict[str, List[str]]:
        """Find matching VRF names for given RT values."""
        matched = {}
        for rt in rt_values:
            vrfs = RT_TO_VRF_MAP.get(rt)
            if vrfs:
                matched[rt] = vrfs
        return matched

    @staticmethod
    def transform_originator_ip(ip: str) -> str:
        """Transform originator BGP router-id/loopback IP to its management IP.

        Applies production subnet remapping:
        {91: 101, 92: 102, 93: 103, 94: 104, 157: 86} or third octet + 100.
        """
        parts = ip.split('.')
        if len(parts) != 4:
            return ip
        try:
            third = int(parts[2])
        except ValueError:
            return ip
        mapping = {91: 101, 92: 102, 93: 103, 94: 104, 157: 86}
        parts[2] = str(mapping.get(third, third + 100))
        return '.'.join(parts)

    @classmethod
    def parse_bgp_received_routes(cls, output: str) -> List[Dict[str, Any]]:
        """Parse 'display bgp vpnv4 all routing-table ... received-routes' output."""
        raw_sections = re.split(r'^\s*Route Distinguisher:\s*', output, flags=re.MULTILINE)
        entries = []
        for section in raw_sections[1:]:
            lines = section.splitlines()
            rd = lines[0].strip() if lines else ''
            full_text = '\n'.join(lines)

            prefix_m = re.search(r"BGP routing table entry information of\s+(\S+)", full_text)
            prefix = prefix_m.group(1).rstrip(':') if prefix_m else ''

            ext_m = re.search(r"Ext-Community:\s*(.*?)(?:\n\S|\Z)", full_text, re.DOTALL)
            ext_community = ''
            rt_values = []
            if ext_m:
                ext_community = ext_m.group(1).strip().rstrip(',')
                rt_values = cls.extract_rt_values(ext_community)

            originator_m = re.search(r'Originator:\s*(\S+)', full_text)
            originator = originator_m.group(1) if originator_m else ''

            nexthop_m = re.search(r'Original nexthop:\s*(\S+)', full_text)
            nexthop = nexthop_m.group(1) if nexthop_m else ''

            from_m = re.search(r'From:\s*(\S+)', full_text)
            from_ip = from_m.group(1) if from_m else ''

            as_path_line = ''
            for line in lines:
                if 'AS-path' in line or 'origin' in line:
                    as_path_line = line.strip()
                    break

            matched_vrfs = cls.match_vrfs_by_rt(rt_values)
            matched_vrf_names = sorted(set(
                v for vlist in matched_vrfs.values() for v in vlist
            ))

            entries.append({
                'route_distinguisher': rd,
                'prefix': prefix,
                'ext_community': ext_community,
                'rt_values': rt_values,
                'matched_vrfs': matched_vrfs,
                'matched_vrf_names': matched_vrf_names,
                'originator': originator,
                'nexthop': nexthop,
                'from': from_ip,
                'as_path_line': as_path_line,
            })
        return entries

    @staticmethod
    def parse_routing_table(output: str) -> List[Dict[str, Any]]:
        """Parse 'display ip routing-table vpn-instance ...' output."""
        routes = []
        lines = output.splitlines()
        header_found = False
        last_destination = ''
        last_mask = ''

        for line in lines:
            s = line.strip()
            if not s:
                continue
            if ('Destination/Mask' in s or 'Destinations/Mask' in s) and 'Proto' in s:
                header_found = True
                continue
            if not header_found:
                continue
            if s.startswith(('---', 'Total', 'Display', 'Route Number', 'Summary')):
                continue

            parts = s.split()
            if not parts:
                continue

            if routes and not routes[-1]['interface']:
                if len(parts) == 1 and any(parts[0].lower().startswith(p) for p in ('vlan', 'ge', 'eth', 'loop', 'null', 'tun', 'xge', '10ge', '100ge', '40ge', '25ge', 'pos', 'ser')):
                    routes[-1]['interface'] = parts[0]
                    continue
                elif len(parts) == 2 and parts[0].lower() == 'vlanif':
                    routes[-1]['interface'] = f"{parts[0]}{parts[1]}"
                    continue

            if parts[0].upper() in PROTOCOL_CATEGORY_MAP and last_destination and len(parts) >= 5:
                destination = last_destination
                mask = last_mask
                offset = 0
            elif len(parts) >= 6:
                dest_col = parts[0]
                if '/' in dest_col:
                    destination, mask = dest_col.split('/', 1)
                    offset = 1
                else:
                    destination = dest_col
                    mask = parts[1]
                    offset = 2
                last_destination = destination
                last_mask = mask
            else:
                continue

            proto = parts[offset] if len(parts) > offset else ''
            pre = parts[offset + 1] if len(parts) > offset + 1 else ''
            cost = parts[offset + 2] if len(parts) > offset + 2 else ''
            rem = parts[offset + 3:]
            if len(rem) >= 2:
                interface = rem[-1]
                nexthop = rem[-2]
                flags = ' '.join(rem[:-2])
            elif len(rem) == 1:
                nexthop = rem[0]
                interface = ''
                flags = ''
            else:
                flags = ''
                nexthop = ''
                interface = ''

            proto_category = PROTOCOL_CATEGORY_MAP.get(proto, proto)
            routes.append({
                'destination': destination,
                'mask': mask,
                'proto': proto,
                'proto_category': proto_category,
                'pre': pre,
                'cost': cost,
                'flags': flags,
                'nexthop': nexthop,
                'interface': interface,
            })
        return routes

    @staticmethod
    def parse_interface_config(text: str) -> Dict[str, str]:
        """Parse Huawei interface configuration snippet."""
        result = {
            'interface_name': '',
            'description': '',
            'vpn_instance': '',
            'ip_address': '',
            'subnet_mask': '',
        }
        for line in text.splitlines():
            s = line.strip()
            if s.lower().startswith('interface '):
                result['interface_name'] = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ''
            elif s.lower().startswith('description '):
                result['description'] = s[len('description '):].strip()
            elif 'ip binding vpn-instance' in s.lower():
                m = re.search(r'ip\s+binding\s+vpn-instance\s+(\S+)', s, re.IGNORECASE)
                if m:
                    result['vpn_instance'] = m.group(1)
            elif s.lower().startswith('ip address'):
                parts = s.split()
                if len(parts) >= 3:
                    result['ip_address'] = parts[2]
                if len(parts) >= 4:
                    result['subnet_mask'] = parts[3]
        return result

    @staticmethod
    def ip_matches_route(ip: str, destination: str, mask: str) -> bool:
        """Check if an IP falls within route destination/mask."""
        if not ip or not destination or not mask:
            return False
        try:
            clean_ip = ip.split("/")[0]
            if '.' in mask:
                prefix_len = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
            else:
                prefix_len = int(mask)
            network = ipaddress.IPv4Network(f"{destination}/{prefix_len}", strict=False)
            return ipaddress.IPv4Address(clean_ip) in network
        except ValueError:
            return False

    @classmethod
    def trace_vrf_route(
        cls,
        db_session: Session,
        vrf: str,
        target_ip_or_prefix: str,
        ingress_device_id: Optional[int] = None,
        session_mock: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute hop-by-hop VRF routing trace and assemble topology path graph.

        Path flow:
        Originator PE (Egress) -> Route Reflector (BGP VPNv4) -> Ingress PE -> Target/CE
        """
        clean_vrf, clean_target = cls.validate_vrf_and_target(vrf, target_ip_or_prefix)
        target_host_ip = clean_target.split("/")[0]

        # 1. Resolve Ingress / RR Device
        ingress_dev = None
        if ingress_device_id:
            ingress_dev = db_session.query(Device).filter(Device.id == ingress_device_id).first()
        if not ingress_dev:
            ingress_dev = db_session.query(Device).filter(
                Device.enabled == True,
                Device.role == "RR",
            ).first()
        if not ingress_dev:
            # Fallback to configured settings or first enabled device
            ingress_dev = db_session.query(Device).filter(Device.mgmt_ip == VRF_ROUTER_IP).first()
        if not ingress_dev:
            ingress_dev = db_session.query(Device).filter(Device.enabled == True).first()

        rr_name = ingress_dev.name if ingress_dev else VRF_ROUTER_NAME
        rr_ip = ingress_dev.mgmt_ip if ingress_dev else VRF_ROUTER_IP
        rr_peer_ip = VRF_RR_IP

        # 2. Query Route Reflector / BGP VPNv4
        bgp_cmd = f"display bgp vpnv4 all routing-table peer {rr_peer_ip} received-routes {target_host_ip}"
        bgp_entries = []
        rr_output = ""

        if session_mock is not None:
            rr_output = session_mock.run(bgp_cmd)
        else:
            if ingress_dev:
                with DeviceSession(ip=ingress_dev.mgmt_ip, os_family=ingress_dev.os_family, device_name=ingress_dev.name) as ds:
                    rr_output = ds.run(bgp_cmd)

        bgp_entries = cls.parse_bgp_received_routes(rr_output)

        originator_ip = ""
        route_distinguisher = ""
        rt_values = []
        matched_vrfs = []

        if bgp_entries:
            primary_entry = bgp_entries[0]
            originator_ip = primary_entry.get("originator", "")
            route_distinguisher = primary_entry.get("route_distinguisher", "")
            rt_values = primary_entry.get("rt_values", [])
            matched_vrfs = primary_entry.get("matched_vrf_names", [])

        # 3. Resolve Originator PE
        transformed_originator_ip = cls.transform_originator_ip(originator_ip) if originator_ip else ""
        originator_dev = None
        if transformed_originator_ip:
            originator_dev = db_session.query(Device).filter(
                (Device.mgmt_ip == transformed_originator_ip) |
                (Device.lsr_id == originator_ip) |
                (Device.mgmt_ip == originator_ip)
            ).first()

        originator_name = originator_dev.name if originator_dev else (
            f"PE-{transformed_originator_ip.replace('.', '-')}" if transformed_originator_ip else "Originator-PE"
        )
        originator_mgmt_ip = originator_dev.mgmt_ip if originator_dev else transformed_originator_ip

        # 4. Query Originator PE for VRF routing and interface
        vrf_cmd = f"display ip routing-table vpn-instance {clean_vrf} {target_host_ip}"
        vrf_output = ""
        matching_routes = []
        outgoing_iface = ""
        iface_config = {}

        if originator_mgmt_ip:
            if session_mock is not None:
                vrf_output = session_mock.run(vrf_cmd)
            else:
                try:
                    os_fam = originator_dev.os_family if originator_dev else "vrp8"
                    with DeviceSession(ip=originator_mgmt_ip, os_family=os_fam, device_name=originator_name) as ods:
                        vrf_output = ods.run(vrf_cmd)
                except Exception:
                    vrf_output = ""

            parsed_routes = cls.parse_routing_table(vrf_output)
            matching_routes = [
                r for r in parsed_routes
                if cls.ip_matches_route(target_host_ip, r.get("destination", ""), r.get("mask", ""))
            ]
            if not matching_routes and parsed_routes:
                matching_routes = parsed_routes

            if matching_routes:
                outgoing_iface = matching_routes[0].get("interface", "")
                if outgoing_iface and outgoing_iface.lower() not in ("null0", "inloopback0", "inloop0"):
                    iface_cmd = f"display current-configuration interface {outgoing_iface}"
                    if session_mock is not None:
                        cfg_out = session_mock.run(iface_cmd)
                    else:
                        try:
                            with DeviceSession(ip=originator_mgmt_ip, os_family=os_fam, device_name=originator_name) as ods:
                                cfg_out = ods.run(iface_cmd)
                        except Exception:
                            cfg_out = ""
                    iface_config = cls.parse_interface_config(cfg_out)

        # 5. Assemble Per-Hop Table
        hops = []
        # Hop 1: Ingress Router / RR
        hops.append({
            "hop_index": 1,
            "role": "RR",
            "device_name": rr_name,
            "device_ip": rr_ip,
            "peer_ip": rr_peer_ip,
            "status": "success" if bgp_entries else "no_bgp_route",
            "protocol": "BGP-VPNv4",
            "prefix": clean_target,
            "route_distinguisher": route_distinguisher,
            "route_targets": rt_values,
            "matched_vrfs": matched_vrfs,
            "details": {
                "originator_reported": originator_ip,
                "transformed_ip": transformed_originator_ip,
                "entry_count": len(bgp_entries),
            },
        })

        # Hop 2: Originator PE
        best_route = matching_routes[0] if matching_routes else {}
        hops.append({
            "hop_index": 2,
            "role": "PE",
            "device_name": originator_name,
            "device_ip": originator_mgmt_ip or originator_ip or "Unknown",
            "status": "success" if matching_routes else ("no_route_in_vrf" if originator_mgmt_ip else "unreachable"),
            "protocol": best_route.get("proto_category", "Direct"),
            "prefix": f"{best_route.get('destination', clean_target)}/{best_route.get('mask', '32')}",
            "nexthop": best_route.get("nexthop", ""),
            "interface": outgoing_iface or "Unknown",
            "cost": best_route.get("cost", "0"),
            "preference": best_route.get("pre", "0"),
            "details": {
                "vrf": clean_vrf,
                "routes_matched": len(matching_routes),
            },
        })

        # Hop 3: Egress Interface / Next-Hop / CE
        hops.append({
            "hop_index": 3,
            "role": "CE",
            "device_name": iface_config.get("description") or f"CE-via-{outgoing_iface or 'NextHop'}",
            "device_ip": iface_config.get("ip_address") or best_route.get("nexthop") or target_host_ip,
            "status": "success" if outgoing_iface else "unresolved",
            "protocol": "Direct/FIB",
            "prefix": clean_target,
            "interface": outgoing_iface,
            "details": {
                "description": iface_config.get("description", ""),
                "configured_vrf": iface_config.get("vpn_instance", clean_vrf),
                "ip_mask": f"{iface_config.get('ip_address', '')} {iface_config.get('subnet_mask', '')}".strip(),
            },
        })

        # 6. Assemble Path Graph
        nodes = [
            {
                "id": "node_rr",
                "label": f"Route Reflector: {rr_name}",
                "role": "RR",
                "ip": rr_ip,
                "status": "success" if bgp_entries else "warning",
                "subtitle": f"BGP Peer: {rr_peer_ip}",
            },
            {
                "id": "node_originator",
                "label": f"Originator PE: {originator_name}",
                "role": "PE",
                "ip": originator_mgmt_ip or originator_ip,
                "status": "success" if matching_routes else "error",
                "subtitle": f"VRF: {clean_vrf}",
            },
            {
                "id": "node_destination",
                "label": f"Target: {iface_config.get('description') or clean_target}",
                "role": "CE",
                "ip": target_host_ip,
                "status": "success" if outgoing_iface else "warning",
                "subtitle": f"Interface: {outgoing_iface or 'None'}",
            },
        ]

        edges = [
            {
                "source": "node_originator",
                "target": "node_rr",
                "label": f"BGP VPNv4 ({route_distinguisher or 'RD'})",
                "protocol": "BGP-VPNv4",
                "details": f"RT: {', '.join(rt_values) if rt_values else 'None'}",
            },
            {
                "source": "node_originator",
                "target": "node_destination",
                "label": f"{best_route.get('proto_category', 'Direct')} via {outgoing_iface or 'FIB'}",
                "protocol": best_route.get("proto_category", "Direct"),
                "details": f"NextHop: {best_route.get('nexthop', target_host_ip)}",
            },
        ]

        overall_status = "resolved" if (bgp_entries and matching_routes) else (
            "partial" if (bgp_entries or matching_routes) else "not_found"
        )

        return {
            "vrf": clean_vrf,
            "target": clean_target,
            "status": overall_status,
            "hops": hops,
            "path_graph": {
                "nodes": nodes,
                "edges": edges,
            },
            "bgp_routes": bgp_entries,
            "vrf_routes": matching_routes,
            "interface_config": iface_config,
            "summary": {
                "route_reflector": rr_name,
                "originator_name": originator_name,
                "originator_ip": originator_mgmt_ip,
                "outgoing_interface": outgoing_iface,
                "nexthop": best_route.get("nexthop", ""),
                "protocol": best_route.get("proto_category", ""),
                "route_distinguisher": route_distinguisher,
                "route_targets": rt_values,
                "matched_vrfs": matched_vrfs,
            },
        }
