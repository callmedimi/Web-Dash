"""Huawei routing table and BGP VPNv4 parsers (Target Architecture §3)."""
import re
from typing import Dict, Any, List

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


def parse_routing_table(output: str) -> List[Dict[str, Any]]:
    """Parse 'display ip routing-table vpn-instance ...' CLI output."""
    routes: List[Dict[str, Any]] = []
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

        # Handle wrapped interface line from previous entry
        if routes and not routes[-1]['interface']:
            if len(parts) == 1 and any(parts[0].lower().startswith(p) for p in (
                'vlan', 'ge', 'eth', 'loop', 'null', 'tun', 'xge', '10ge', '100ge', '40ge', '25ge', 'pos', 'ser'
            )):
                routes[-1]['interface'] = parts[0]
                continue
            elif len(parts) == 2 and parts[0].lower() == 'vlanif':
                routes[-1]['interface'] = f"{parts[0]}{parts[1]}"
                continue

        # Handle ECMP continuation lines
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


def parse_bgp_received_routes(output: str) -> List[Dict[str, Any]]:
    """Parse 'display bgp vpnv4 all routing-table peer ... received-routes ...' output."""
    raw_sections = re.split(r'^\s*Route Distinguisher:\s*', output, flags=re.MULTILINE)
    entries: List[Dict[str, Any]] = []

    for section in raw_sections[1:]:
        lines = section.splitlines()
        rd = lines[0].strip() if lines else ''
        full_text = '\n'.join(lines)

        prefix_m = re.search(r"BGP routing table entry information of\s+(\S+)", full_text)
        prefix = prefix_m.group(1).rstrip(':') if prefix_m else ''

        ext_m = re.search(r"Ext-Community:\s*(.*?)(?:\n\S|\Z)", full_text, re.DOTALL)
        ext_community = ext_m.group(1).strip().rstrip(',') if ext_m else ''

        rt_matches = re.findall(r'RT\s*<\s*(\d+)\s*:\s*(\d+)\s*>', ext_community)
        rt_values = [f"{a}:{b}" for a, b in rt_matches]

        originator_m = re.search(r'Originator:\s*(\S+)', full_text)
        originator = originator_m.group(1) if originator_m else ''

        nexthop_m = re.search(r'Original nexthop:\s*(\S+)', full_text)
        nexthop = nexthop_m.group(1) if nexthop_m else ''

        from_m = re.search(r'From:\s*(\S+)', full_text)
        from_ip = from_m.group(1) if from_m else ''

        entries.append({
            'route_distinguisher': rd,
            'prefix': prefix,
            'ext_community': ext_community,
            'rt_values': rt_values,
            'originator': originator,
            'nexthop': nexthop,
            'from': from_ip,
        })

    return entries
