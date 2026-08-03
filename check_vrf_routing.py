import re
import ipaddress
import netmiko

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

# Hardcoded route reflector device
HARDCODED_ROUTER_NAME = "IRRHAC"
HARDCODED_ROUTER_IP = "10.0.101.23"
HARDCODED_RR_IP = "10.0.7.10"  # RR IP used in BGP commands (may differ from management IP)

# VRF name -> list of import RT values
VRF_RT_MAP = {
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


def _build_rt_to_vrf_map() -> dict[str, list[str]]:
    rt_to_vrf = {}
    for vrf, rt_list in VRF_RT_MAP.items():
        for rt in rt_list:
            rt_to_vrf.setdefault(rt, []).append(vrf)
    return rt_to_vrf


RT_TO_VRF_MAP = _build_rt_to_vrf_map()


def extract_rt_values(ext_community_str: str) -> list[str]:
    m = re.findall(r'RT\s*<\s*(\d+)\s*:\s*(\d+)\s*>', ext_community_str)
    return [f"{a}:{b}" for a, b in m]


def match_vrfs_by_rt(rt_values: list[str]) -> dict[str, list[str]]:
    matched = {}
    for rt in rt_values:
        vrfs = RT_TO_VRF_MAP.get(rt)
        if vrfs:
            matched[rt] = vrfs
    return matched


def parse_bgp_received_routes(output: str) -> list[dict]:
    raw_sections = re.split(r'^\s*Route Distinguisher:\s*', output, flags=re.MULTILINE)
    entries = []
    for section in raw_sections[1:]:
        lines = section.splitlines()
        rd = lines[0].strip() if lines else ''

        full_text = '\n'.join(lines)

        prefix_m = re.search(r"BGP routing table entry information of\s+(\S+)", full_text)
        # FIX: Strip the trailing colon from the prefix (e.g., "185.5.156.0/24:")
        prefix = prefix_m.group(1).rstrip(':') if prefix_m else ''

        ext_m = re.search(r"Ext-Community:\s*(.*?)(?:\n\S|\Z)", full_text, re.DOTALL)
        ext_community = ''
        rt_values = []
        if ext_m:
            ext_community = ext_m.group(1).strip().rstrip(',')
            rt_values = extract_rt_values(ext_community)

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

        matched_vrfs = match_vrfs_by_rt(rt_values)

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


def transform_originator_ip(ip: str) -> str:
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


def check_bgp_route(conn, target_ip: str, cmd_timeout=60) -> tuple[list[dict], str]:
    cmd = f'display bgp vpnv4 all routing-table peer {HARDCODED_RR_IP} received-routes {target_ip}'
    output = conn.send_command(cmd, read_timeout=cmd_timeout)
    entries = parse_bgp_received_routes(output)
    return entries, output


def get_router_interfaces(conn, cmd_timeout=60) -> list[dict]:
    output = conn.send_command('display interface brief', read_timeout=cmd_timeout)
    interfaces = []
    lines = output.splitlines()
    header_found = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r'^(Interface|PHY)\s', s):
            header_found = True
            continue
        if not header_found:
            continue
        if s.startswith('---') or s.startswith('Total') or s.startswith('Display'):
            continue
        parts = s.split()
        if len(parts) >= 4:
            interfaces.append({
                'interface': parts[0],
                'phy': parts[1],
                'protocol': parts[2],
                'description': parts[3] if len(parts) > 3 else '',
            })
    return interfaces


def get_interface_config_text(conn, interface_name: str, cmd_timeout=60) -> str:
    cmd = f'display current-configuration interface {interface_name}'
    try:
        output = conn.send_command(cmd, read_timeout=cmd_timeout)
        return output
    except Exception:
        return ''


def get_all_vrf_names(conn, cmd_timeout=60) -> list[str]:
    output = conn.send_command('display ip vpn-instance', read_timeout=cmd_timeout)
    vrfs = []
    for line in output.splitlines():
        s = line.strip()
        if not s or s.startswith('-') or s.startswith('Total') or s.startswith('Number'):
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if name and not name.startswith('(') and 'VPN-Instance' not in s:
            if ':' in parts[1] or len(parts) >= 3:
                vrfs.append(name)
    return vrfs


def get_vrf_route_on_originator(conn, vrf: str, target_ip: str, cmd_timeout=60) -> dict:
    routes, raw = get_vrf_routes(conn, vrf, target_ip, cmd_timeout)
    interfaces = set()
    for r in routes:
        if r.get('interface'):
            interfaces.add(r['interface'])
    interface_configs = {}
    for iface in sorted(interfaces):
        cfg = get_interface_config_text(conn, iface, cmd_timeout)
        if cfg:
            interface_configs[iface] = cfg
    return {
        'vrf': vrf,
        'target_ip': target_ip,
        'routes': routes,
        'route_count': len(routes),
        'interfaces': sorted(interfaces),
        'interface_configs': interface_configs,
    }


def get_sysname(conn, cmd_timeout=10) -> str:
    try:
        output = conn.send_command('display current-configuration | include sysname', read_timeout=cmd_timeout)
        for line in output.splitlines():
            s = line.strip()
            if s.lower().startswith('sysname'):
                parts = s.split(None, 1)
                return parts[1].strip() if len(parts) > 1 else ''
    except Exception:
        pass
    try:
        prompt = conn.find_prompt()
        return prompt.strip('<>[]')
    except Exception:
        return ''


def query_vrf_route_and_configs(conn, vrf: str, target_ip: str, cmd_timeout=60) -> dict:
    routes, raw = get_vrf_routes(conn, vrf, target_ip, cmd_timeout)
    interfaces = set()
    for r in routes:
        if r.get('interface'):
            interfaces.add(r['interface'])
    interface_configs = {}
    for iface in sorted(interfaces):
        cfg = get_interface_config_text(conn, iface, cmd_timeout)
        if cfg:
            interface_configs[iface] = cfg
    return {
        'vrf': vrf,
        'target_ip': target_ip,
        'routes': routes,
        'route_count': len(routes),
        'interfaces': sorted(interfaces),
        'interface_configs': interface_configs,
    }


def get_router_vlan_interfaces(conn, cmd_timeout=60) -> list[dict]:
    output = conn.send_command('display vlan', read_timeout=cmd_timeout)
    vlan_ifaces = []
    header_found = False
    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r'^VLAN-ID\s', s) or 'VLAN-ID' in s:
            header_found = True
            continue
        if not header_found:
            continue
        if s.startswith('---') or s.startswith('Total') or s.startswith('Display'):
            continue
        parts = s.split()
        if parts and parts[0].isdigit():
            vlan_ifaces.append({
                'vlan_id': parts[0],
                'type': parts[1] if len(parts) > 1 else '',
                'status': parts[2] if len(parts) > 2 else '',
                'interfaces': ' '.join(parts[3:]) if len(parts) > 3 else '',
            })
    return vlan_ifaces


def parse_interface_config(text: str) -> dict:
    lines = text.splitlines()
    result = {
        'interface_name': '',
        'description': '',
        'vpn_instance': '',
        'ip_address': '',
        'subnet_mask': '',
    }
    for line in lines:
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


def split_interface_configs(text: str) -> list[str]:
    blocks = []
    current = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith('interface ') and current:
            blocks.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append('\n'.join(current))
    return blocks


def get_vrf_routes(conn, vrf: str, ip: str = '', cmd_timeout=60) -> tuple[list[dict], str]:
    if ip:
        cmd = f'display ip routing-table vpn-instance {vrf} {ip}'
    else:
        cmd = f'display ip routing-table vpn-instance {vrf}'
    output = conn.send_command(cmd, read_timeout=cmd_timeout)
    return _parse_routing_table(output), output


def _parse_routing_table(output: str) -> list[dict]:
    routes = []
    lines = output.splitlines()
    header_found = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # FIX: Huawei uses "Destinations/Mask" (plural), checking for both to be safe
        if ('Destination/Mask' in s or 'Destinations/Mask' in s) and 'Proto' in s:
            header_found = True
            continue
        if not header_found:
            continue
        if s.startswith('---') or s.startswith('Total') or s.startswith('Display') or s.startswith('Route Number') or s.startswith('Summary'):
            continue
        parts = s.split()
        if len(parts) >= 6:
            dest_col = parts[0]
            if '/' in dest_col:
                destination, mask = dest_col.split('/', 1)
                offset = 1
            else:
                destination = dest_col
                mask = parts[1]
                offset = 2
            proto = parts[offset] if len(parts) > offset else ''
            pre = parts[offset + 1] if len(parts) > offset + 1 else ''
            cost = parts[offset + 2] if len(parts) > offset + 2 else ''
            flags = parts[offset + 3] if len(parts) > offset + 3 else ''
            nexthop = parts[offset + 4] if len(parts) > offset + 4 else ''
            interface = parts[offset + 5] if len(parts) > offset + 5 else ''
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


def ip_matches_route(ip: str, destination: str, mask: str) -> bool:
    # FIX: Use ipaddress module to properly check if an IP falls within a subnet
    if not ip or not destination or not mask:
        return False
    try:
        if '.' in mask:
            prefix_len = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
        else:
            prefix_len = int(mask)
            
        network = ipaddress.IPv4Network(f"{destination}/{prefix_len}", strict=False)
        return ipaddress.IPv4Address(ip) in network
    except ValueError:
        return False


# FIX: Added target_ip parameter to check a specific host IP instead of the interface base IP
def batch_check_routing(username: str, password: str, config_text: str, target_ip: str = '', conn_timeout=20, cmd_timeout=60) -> dict:
    config_blocks = split_interface_configs(config_text)
    parsed_list = [parse_interface_config(b) for b in config_blocks]

    parsed_list = [p for p in parsed_list if p['interface_name']]

    if not parsed_list:
        return {'status': 'no_configs', 'error': 'No valid interface configs found', 'results': []}

    vrf_cache = {}
    conn = None
    try:
        conn = netmiko.ConnectHandler(
            device_type='huawei',
            host=HARDCODED_ROUTER_IP,
            username=username,
            password=password,
            timeout=conn_timeout
        )
        # FIX: Disable pagination and increase terminal width to prevent output truncation/wrapping
        conn.send_command('screen-length 0 temporary')
        conn.send_command('terminal width 512')
    except Exception as e:
        return {'status': 'connection_failed', 'error': f'Failed to connect to {HARDCODED_ROUTER_NAME} ({HARDCODED_ROUTER_IP}): {e}', 'results': []}

    results = []
    try:
        for parsed in parsed_list:
            vrf = parsed['vpn_instance']
            interface_ip = parsed['ip_address']
            
            # FIX: If a specific target_ip is provided, use it. Otherwise, fallback to the interface IP.
            ip_to_check = target_ip if target_ip else interface_ip

            if not vrf:
                results.append({
                    'interface': parsed['interface_name'],
                    'description': parsed['description'],
                    'vpn_instance': '',
                    'interface_ip': interface_ip or '—',
                    'checked_ip': ip_to_check or '—',
                    'has_route': None,
                    'reason': 'No vpn-instance configured',
                    'routes_count': 0,
                })
                continue

            cache_key = (vrf, ip_to_check)
            if cache_key not in vrf_cache:
                routes, raw = get_vrf_routes(conn, vrf, ip_to_check if ip_to_check else '', cmd_timeout)
                vrf_cache[cache_key] = {'routes': routes, 'raw': raw}

            vrf_data = vrf_cache[cache_key]
            matching = [r for r in vrf_data['routes'] if ip_matches_route(ip_to_check, r['destination'], r['mask'])]

            has_route = len(matching) > 0 if ip_to_check else None
            results.append({
                'interface': parsed['interface_name'],
                'description': parsed['description'],
                'vpn_instance': vrf,
                'interface_ip': interface_ip or '—',
                'checked_ip': ip_to_check or '—',
                'has_route': has_route,
                'reason': f'Found {len(matching)} matching route(s) for {ip_to_check}' if matching else f'No matching route for {ip_to_check} in VRF' if ip_to_check else 'No IP address configured',
                'routes_count': len(vrf_data['routes']),
                'matching_routes': matching[:10],
            })

    except Exception as e:
        return {'status': 'error', 'error': str(e), 'results': results}
    finally:
        # FIX: Safely disconnect in a finally block to ensure it always runs
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass

    unique_vrfs = set(k[0] for k in vrf_cache)
    return {
        'status': 'success',
        'router': {'name': HARDCODED_ROUTER_NAME, 'ip': HARDCODED_ROUTER_IP},
        'vrf_count': len(unique_vrfs),
        'queries': len(vrf_cache),
        'results': results,
    }