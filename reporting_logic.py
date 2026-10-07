import re
import netmiko
import time as ttime
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TRUNK_IDS = ['0', '33', '85']
CATEGORY_KEYWORDS = {'OSN': 'OSN', 'SPO': 'SPO', 'HRAN': 'HRAN'}

FIELD_NAMES = [
    'NE NAME',
    'Interface type',
    'interface name',
    'interface description',
    'admin down or not',
    'alarm occur time',
    'Down Reason',
    'Trunk Memberships',
    'Category',
    'full configuration of the link'
]

TRUNK_FIELD_NAMES = [
    'Province',
    'NE Name',
    'Trunk Name',
    'Trunk Group',
    'Description',
    'Trunk Status',
    'Total Members',
    'Down Members Count',
    'Member Links Details',
    'Down Member Ports'
]


def classify_category(description):
    desc_upper = description.upper()
    if 'OSN' in desc_upper:
        return 'OSN'
    if 'SPO' in desc_upper:
        return 'SPO'
    if 'HRAN' in desc_upper:
        return 'HRAN'
    return 'Other'


def parse_filtered_alarms(output: str):
    alarms = []
    for line in output.splitlines():
        line = line.strip()
        if not line or any(x in line for x in ['Sequence', '--------', '1:Critical', 'Info:', 'press CTRL_C', 'no active alarms']):
            continue
        match = re.match(
            r'^\s*(\d+)\s+(0x[0-9A-Fa-f]+)\s+(\d)\s+(\d{4}-\d{2}-\d{2})\s+'
            r'(\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:?\d{2})?)\s+(.+)$',
            line
        )
        if not match:
            continue
        date_str = match.group(4)
        time_str = match.group(5)
        desc = match.group(6).strip()
        dt = None
        for fmt in ('%Y-%m-%d %H:%M:%S%z', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(f"{date_str} {time_str}", fmt)
                break
            except Exception:
                pass
        interface_name = 'Unknown'
        for key in ['ifName=', 'InterfaceName=', 'mainIfname=', 'EntPhysicalName=', 'SubIfName=', 'Interface=', 'PortID=']:
            m = re.search(f'{key}([^,\\s\\)]+)', desc)
            if m:
                interface_name = m.group(1)
                break
        else:
            m = re.search(r'(XGigabitEthernet|XGE|100GE|40GE|10GE|GigabitEthernet|GE|Eth-Trunk|Ethernet|Vlanif|LoopBack)[^,\s\)]*', desc, re.IGNORECASE)
            if m:
                interface_name = m.group(0)
        down_reason = "OperStatus=DOWN"
        if 'DownReason=LOS' in desc:
            down_reason = "DownReason=LOS"
        elif 'AlarmName=ETH_LOS' in desc:
            down_reason = "AlarmName=ETH_LOS"
        elif 'The status of the physical interface is Down' in desc:
            down_reason = "The status of the physical interface is Down"
        elif 'AdminStatus=DOWN, OperStatus=DOWN' in desc:
            down_reason = "AdminStatus=DOWN, OperStatus=DOWN"
        elif 'AdminStatus=UP, OperStatus=DOWN' in desc:
            down_reason = "AdminStatus=UP, OperStatus=DOWN"
        elif 'OperStatus=DOWN' in desc:
            down_reason = "OperStatus=DOWN"
        alarms.append({
            'datetime': dt,
            'description': desc,
            'interface_name': interface_name,
            'down_reason': down_reason
        })
    return alarms


def get_interface_details(conn, interface_name):
    try:
        output = conn.send_command(f'display interface {interface_name}', read_timeout=30)
        if not output.strip():
            raise ValueError("Empty output")
        lines = output.splitlines()
        first_line = lines[0]
        admin_down = 'Administratively DOWN' in first_line
        description = ''
        for line in lines:
            if re.search(r'Description\s*:', line, re.IGNORECASE):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    desc = parts[1].strip()
                    if desc and desc not in ('NULL', ''):
                        description = desc
                break
        return description, admin_down
    except Exception:
        return get_interface_details_from_config(conn, interface_name)


def get_interface_details_from_config(conn, interface_name):
    description = ''
    admin_down = True
    try:
        output = conn.send_command(
            f'display current-configuration interface {interface_name}', read_timeout=60
        )
        config_lines = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(('return', 'quit', '#')):
                config_lines.append(stripped)
        if not config_lines:
            raise ValueError("No config lines")
        for line in config_lines:
            if line.startswith('description '):
                description = line[len('description '):].strip()
                break
        has_shutdown = any(line.strip() == 'shutdown' for line in config_lines)
        admin_down = has_shutdown
        return description or 'Description not available', admin_down
    except Exception:
        return 'Description not available', True


def determine_interface_type(name):
    n = name.lower()
    if 'vlanif' in n:
        return 'VLAN'
    elif 'eth-trunk' in n or 'trunk' in n:
        return 'TRUNK'
    elif 'xgigabitethernet' in n or 'xge' in n or '10ge' in n:
        return '10GE'
    elif '100ge' in n:
        return '100GE'
    elif '40ge' in n:
        return '40GE'
    elif 'gigabitethernet' in n or re.search(r'^ge\d+[/\d]*', n):
        return 'GE'
    elif 'ethernet' in n or 'eth' in n:
        return 'ETH'
    else:
        return 'OTHER'


def is_trivial_interface_config(config_lines):
    if not config_lines:
        return False
    meaningful = []
    for line in config_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            continue
        if s.lower().startswith('interface '):
            continue
        if s in ('return', 'quit'):
            continue
        if s.startswith('Info:') or s.startswith('^'):
            continue
        if 'error' in s.lower() or 'wrong parameter' in s.lower() or 'unrecognized' in s.lower():
            return False
        meaningful.append(s.lower())
    allowed = {'dcn', 'undo dcn', 'shutdown', 'undo shutdown'}
    return len(meaningful) == 0 or all(cmd in allowed for cmd in meaningful)


def check_ba_bc_trunks(conn, name, read_timeout=30):
    trunk_records = []
    trunk_members = {}
    if not name.upper().startswith(('BA', 'BC')):
        return trunk_records, trunk_members

    m_prov = re.search(r'_([A-Za-z]{2})', name) or re.search(r'_(..)', name)
    prov = m_prov.group(1).upper() if m_prov else 'Unknown'

    # Discover any Eth-Trunk interfaces that have TO_VPLS in description
    vpls_tids = set()
    try:
        vpls_out = conn.send_command('display interface description | include TO_VPLS', read_timeout=read_timeout)
        for m in re.finditer(r'Eth-Trunk(\d+)', vpls_out, re.IGNORECASE):
            vpls_tids.add(m.group(1))
    except Exception:
        pass

    # Build candidate trunks: 0, 85, plus 33 and any discovered VPLS trunks
    candidate_tids = ['0', '85']
    for tid in sorted(vpls_tids | {'33'}, key=lambda x: int(x) if x.isdigit() else 999):
        if tid not in candidate_tids:
            candidate_tids.append(tid)

    for tid in candidate_tids:
        try:
            trunk_out = conn.send_command(f'display interface Eth-Trunk{tid}', read_timeout=read_timeout)
            if not trunk_out or 'Error:' in trunk_out or 'Wrong parameter' in trunk_out or 'unrecognized' in trunk_out.lower():
                continue

            lines = trunk_out.splitlines()
            first_line = lines[0] if lines else ''
            trunk_status = 'DOWN'
            for line in lines[:5]:
                l_upper = line.upper()
                if 'ADMINISTRATIVELY DOWN' in l_upper:
                    trunk_status = 'DOWN'
                    break
                if 'CURRENT STATE' in l_upper:
                    if ': UP' in l_upper or ' : UP' in l_upper or l_upper.endswith(' UP'):
                        trunk_status = 'UP'
                    elif ': DOWN' in l_upper or ' : DOWN' in l_upper or l_upper.endswith(' DOWN'):
                        trunk_status = 'DOWN'
                    break

            description = ''
            for line in lines:
                if re.search(r'Description\s*:', line, re.IGNORECASE):
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        d = parts[1].strip()
                        if d and d not in ('NULL', ''):
                            description = d
                    break

            is_vpls = bool(re.search(r'TO_VPLS', description, re.IGNORECASE))

            # Non-0 and non-85 trunks are only included if description matches TO_VPLS
            if tid not in ('0', '85') and not is_vpls:
                continue

            # If description matches TO_VPLS, it belongs to VPLS (even if tid is 0)
            if is_vpls:
                trunk_group = 'VPLS'
            elif tid == '85':
                trunk_group = 'Resilience'
            elif tid == '0':
                trunk_group = 'UPlink'
            else:
                trunk_group = f'Eth-Trunk{tid}'

            members = []
            member_details = []
            down_members = []
            capture = False
            for line in lines:
                s = line.strip()
                if s.startswith('PortName') and 'Status' in s:
                    capture = True
                    continue
                if capture:
                    if re.match(r'^[-]+$', s):
                        continue
                    if s.startswith('The Number of Ports'):
                        break
                    if not s:
                        continue
                    parts = s.split()
                    if len(parts) >= 2:
                        p_name = parts[0]
                        p_stat = parts[1].capitalize()
                        members.append(p_name)
                        member_details.append(f"{p_name} ({p_stat})")
                        if p_stat.lower() == 'down':
                            down_members.append(p_name)

            if members:
                trunk_members[tid] = members

            trunk_records.append({
                'Province': prov,
                'NE Name': name,
                'Trunk Name': f'Eth-Trunk{tid}',
                'Trunk Group': trunk_group,
                'Description': description or 'No description',
                'Trunk Status': trunk_status,
                'Total Members': len(members),
                'Down Members Count': len(down_members),
                'Member Links Details': ', '.join(member_details) if member_details else 'No members',
                'Down Member Ports': ', '.join(down_members) if down_members else 'None',
            })
        except Exception:
            pass

    return trunk_records, trunk_members


def process_one_report(name, host, username, password, log, conn_timeout=20, cmd_timeout=60, age_value=2, age_unit='days'):
    conn = None
    result = {
        'name': name,
        'host': host,
        'data': [],
        'noconf_data': [],
        'trunk_data': [],
        'status': 'success',
        'error': None,
    }

    for attempt in range(2):
        try:
            log(f"Connecting to {name} ({host})...")
            conn = netmiko.ConnectHandler(
                device_type='huawei',
                host=host,
                username=username,
                password=password,
                timeout=conn_timeout
            )
            try:
                conn.send_command('screen-length 0 temporary', read_timeout=cmd_timeout)
            except Exception:
                pass

            cmd = (
                'display alarm active | include '
                '"AdminStatus=DOWN, OperStatus=DOWN|'
                'AdminStatus=UP, OperStatus=DOWN|'
                'DownReason=LOS|'
                'AlarmName=ETH_LOS|'
                'The status of the physical interface is Down|'
                'OperStatus=DOWN"'
            )
            output = conn.send_command(cmd, read_timeout=cmd_timeout)
            alarms = parse_filtered_alarms(output)

            trunk_records, trunk_members = check_ba_bc_trunks(conn, name, read_timeout=cmd_timeout)
            result['trunk_data'] = trunk_records

            if not alarms:
                conn.disconnect()
                if trunk_records:
                    result['status'] = 'success'
                    log(f"{name}: 0 alarms, {len(trunk_records)} trunk(s) checked", 'info')
                else:
                    result['status'] = 'skipped'
                    result['error'] = 'No matching alarms'
                    log(f"No matching alarms on {name}", 'warn')
                return result

            utc = ZoneInfo("UTC")
            if age_unit == 'hours':
                age_threshold = datetime.now(utc) - timedelta(hours=age_value)
            else:
                age_threshold = datetime.now(utc) - timedelta(days=age_value)

            report_data = []
            noconf_data = []
            seen = set()

            for alarm in alarms:
                intf_name = alarm['interface_name']
                if intf_name == 'Unknown' or (name, intf_name) in seen:
                    continue

                if re.fullmatch(r'(?i)ethernet0/0/0', intf_name):
                    continue
                if re.fullmatch(r'(?i)eth-trunk85', intf_name):
                    continue

                seen.add((name, intf_name))

                if alarm['datetime']:
                    try:
                        alarm_dt = alarm['datetime']
                        if alarm_dt.tzinfo is None:
                            alarm_dt = alarm_dt.replace(tzinfo=utc)
                        if alarm_dt.astimezone(utc) >= age_threshold:
                            continue
                    except Exception:
                        pass

                description, admin_down = get_interface_details(conn, intf_name)

                if 'rubika' in description.lower():
                    continue

                config_lines_raw = []
                config_text = 'Config not available'
                config_fetch_ok = False
                try:
                    config_output = conn.send_command(
                        f'display current-configuration interface {intf_name}', read_timeout=60
                    )
                    config_lines_raw = [line.rstrip() for line in config_output.splitlines()]
                    display_lines = [
                        line for line in config_lines_raw
                        if line.strip() and not line.strip().startswith('#')
                    ]
                    config_text = '\n'.join(display_lines) if display_lines else 'No config found'
                    config_fetch_ok = True
                except Exception:
                    config_lines_raw = []
                    config_text = 'Config fetch error'

                entry = {
                    'NE NAME': name,
                    'Interface type': determine_interface_type(intf_name),
                    'interface name': intf_name,
                    'interface description': description,
                    'admin down or not': 'Yes' if admin_down else 'No',
                    'alarm occur time': alarm['datetime'].strftime('%Y-%m-%d %H:%M:%S%z')
                        if alarm['datetime'] else 'Unknown',
                    'Down Reason': alarm['down_reason'],
                    'Category': classify_category(description),
                    'full configuration of the link': config_text
                }

                if config_fetch_ok and is_trivial_interface_config(config_lines_raw):
                    noconf_data.append(entry)
                else:
                    report_data.append(entry)

            for entry_list in (report_data, noconf_data):
                for entry in entry_list:
                    intf = entry.get('interface name', '')
                    matched = []
                    for tid, members in trunk_members.items():
                        if any(intf.lower() == m.lower() for m in members):
                            matched.append(f'Eth-Trunk{tid}')
                    entry['Trunk Memberships'] = ', '.join(matched) if matched else ''

            conn.disconnect()
            member_count = sum(1 for e in report_data + noconf_data if e.get('Trunk Memberships'))
            log(f"{name}: {len(report_data)} service, {len(noconf_data)} noconf"
                + (f", {member_count} trunk-member(s)" if member_count else ""))
            result['data'] = report_data
            result['noconf_data'] = noconf_data
            return result

        except Exception as e:
            if attempt == 0:
                ttime.sleep(3)
            else:
                if conn:
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
                result['status'] = 'failed'
                result['error'] = str(e)
                log(f"Error on {name}: {e}", 'error')
                return result

    result['status'] = 'failed'
    result['error'] = 'Max retries exceeded'
    return result


def extract_provinces(routers):
    provinces = set()
    for r in routers:
        name = r.get('name', '')
        m = re.search(r'_(..)', name)
        if m:
            provinces.add(m.group(1))
    return sorted(provinces)


def filter_routers_by_province(routers, province):
    return [r for r in routers if f'_{province}' in r.get('name', '')]


def compute_analytics(report_data, noconf_data, trunk_data=None):
    if trunk_data is None:
        trunk_data = []
    all_entries = report_data + noconf_data
    total = len(all_entries)

    by_province = {}
    for entry in all_entries:
        ne = entry.get('NE NAME', '')
        m = re.search(r'_(..)', ne)
        p = m.group(1) if m else 'Unknown'
        if p not in by_province:
            by_province[p] = {"service": 0, "noconf": 0, "devices": set()}
        is_noconf = entry in noconf_data
        if is_noconf:
            by_province[p]["noconf"] += 1
        else:
            by_province[p]["service"] += 1
        by_province[p]["devices"].add(ne)

    province_summary = []
    # Per-province device alarm counts (for top-N per province)
    province_device_counts = {}
    for entry in all_entries:
        ne = entry.get('NE NAME', '')
        m = re.search(r'_(..)', ne)
        p = m.group(1) if m else 'Unknown'
        province_device_counts.setdefault(p, {}).setdefault(ne, 0)
        province_device_counts[p][ne] += 1

    # Collect timestamps per province for burst detection
    province_timestamps = {}
    for entry in all_entries:
        ne = entry.get('NE NAME', '')
        m = re.search(r'_(..)', ne)
        p = m.group(1) if m else 'Unknown'
        ts = entry.get('alarm occur time', '')
        if ts and ts != 'Unknown':
            try:
                dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S%z')
                province_timestamps.setdefault(p, []).append(dt)
            except Exception:
                pass

    for p, d in sorted(by_province.items()):
        dev_counts = province_device_counts.get(p, {})
        top_devices = sorted(dev_counts.items(), key=lambda x: -x[1])[:5]

        # 5-minute sliding window burst check (window: 300s)
        burst = False
        burst_start = ''
        burst_end = ''
        timestamps = province_timestamps.get(p, [])
        if len(timestamps) >= 3:
            timestamps.sort()
            max_in_window = 0
            best_start = timestamps[0]
            best_end = timestamps[0]
            left = 0
            for right in range(len(timestamps)):
                while (timestamps[right] - timestamps[left]).total_seconds() > 300:
                    left += 1
                count = right - left + 1
                if count >= 3 and count > max_in_window:
                    max_in_window = count
                    best_start = timestamps[left]
                    best_end = timestamps[right]
            if max_in_window >= 3:
                burst = True
                burst_start = best_start.strftime('%Y-%m-%d %H:%M:%S')
                burst_end = best_end.strftime('%Y-%m-%d %H:%M:%S')
        elif len(timestamps) == 2:
            timestamps.sort()
            if (timestamps[1] - timestamps[0]).total_seconds() <= 300:
                burst = True
                burst_start = timestamps[0].strftime('%Y-%m-%d %H:%M:%S')
                burst_end = timestamps[1].strftime('%Y-%m-%d %H:%M:%S')

        province_summary.append({
            "province": p,
            "devices": len(d["devices"]),
            "service": d["service"],
            "noconf": d["noconf"],
            "total": d["service"] + d["noconf"],
            "top_devices": [{"name": ne, "alarms": c} for ne, c in top_devices],
            "burst": burst,
            "burst_start": burst_start,
            "burst_end": burst_end,
        })

    by_reason = {}
    for entry in all_entries:
        r = entry.get('Down Reason', 'Unknown')
        by_reason[r] = by_reason.get(r, 0) + 1
    sorted_reasons = sorted(by_reason.items(), key=lambda x: -x[1])
    top_reasons = [{"reason": r, "count": c} for r, c in sorted_reasons]

    by_iface_type = {}
    for entry in all_entries:
        t = entry.get('Interface type', 'OTHER')
        by_iface_type[t] = by_iface_type.get(t, 0) + 1
    sorted_ifaces = sorted(by_iface_type.items(), key=lambda x: -x[1])
    iface_types = [{"type": t, "count": c} for t, c in sorted_ifaces]

    by_category = {}
    for entry in all_entries:
        cat = entry.get('Category', 'Other')
        by_category[cat] = by_category.get(cat, 0) + 1
    sorted_cats = sorted(by_category.items(), key=lambda x: -x[1])
    category_summary = [{"category": c, "count": n} for c, n in sorted_cats]

    # --- Interface-level aggregation ---
    # group by (ne_name, interface_name) → list of reasons
    interface_groups = {}
    for entry in all_entries:
        key = (entry.get('NE NAME', ''), entry.get('interface name', ''))
        reason = entry.get('Down Reason', 'Unknown')
        if key not in interface_groups:
            interface_groups[key] = {
                'ne_name': key[0],
                'interface': key[1],
                'reasons': {},
                'is_noconf': entry in noconf_data,
            }
        interface_groups[key]['reasons'][reason] = \
            interface_groups[key]['reasons'].get(reason, 0) + 1

    total_interfaces = len(interface_groups)
    interfaces_with_multi = sum(
        1 for g in interface_groups.values() if sum(g['reasons'].values()) > 1
    )
    alarm_count_dist = {}
    for g in interface_groups.values():
        c = sum(g['reasons'].values())
        bucket = '3+' if c >= 3 else str(c)
        alarm_count_dist[bucket] = alarm_count_dist.get(bucket, 0) + 1

    # top interfaces by alarm count
    sorted_ifaces_by_count = sorted(
        interface_groups.values(),
        key=lambda g: -sum(g['reasons'].values())
    )[:15]
    top_interfaces = [{
        'ne': g['ne_name'],
        'interface': g['interface'],
        'alarms': sum(g['reasons'].values()),
        'distinct_reasons': len(g['reasons']),
        'reasons': ', '.join(f'{r}({c})' for r, c in sorted(g['reasons'].items(), key=lambda x: -x[1])),
    } for g in sorted_ifaces_by_count]

    # --- Description-based grouping for ETH, GE, 10GE, etc. ---
    # Extract site/circuit codes (_XX12345) from descriptions and group interfaces that share one.
    # Excludes interface designations (e.g. _GE0/1/0) by forbidding interface prefixes and requiring 3-5 digits.
    code_pattern = re.compile(r'_(?!(?:GE|FE|XE|ET|PO|LO|GI|FA|XG)\d)[A-Z]{2}\d{3,5}(?![/\d])')
    code_groups = {}  # code -> list of {ne, interface, description, iface_type}
    for entry in all_entries:
        if entry.get('Interface type') not in ('GE', 'ETH', '10GE', '40GE', '100GE'):
            continue
        desc = entry.get('interface description', '')
        codes = code_pattern.findall(desc.upper())
        if not codes:
            continue
        ne = entry.get('NE NAME', '')
        intf = entry.get('interface name', '')
        for code in set(codes):
            code_groups.setdefault(code, []).append({
                'ne': ne,
                'interface': intf,
                'description': desc,
                'iface_type': entry.get('Interface type', ''),
            })

    # Filter groups with at least 2 entries (meaningful grouping) and sort by group size
    site_groups = []
    for code, members in sorted(code_groups.items(), key=lambda x: -len(x[1])):
        if len(members) < 2:
            continue
        site_groups.append({
            'code': code,
            'size': len(members),
            'members': sorted(members, key=lambda m: (m['ne'], m['interface'])),
        })

    # --- Eth-Trunk member analytics (BA/BC devices) ---
    trunk_entries = [e for e in all_entries if e.get('Trunk Memberships')]
    trunk_by_trunk = {}
    for e in trunk_entries:
        memberships = e.get('Trunk Memberships', '')
        for tname in memberships.split(', '):
            if not tname:
                continue
            trunk_by_trunk.setdefault(tname, []).append({
                'ne': e.get('NE NAME', ''),
                'interface': e.get('interface name', ''),
                'type': e.get('Interface type', ''),
                'reason': e.get('Down Reason', ''),
                'description': e.get('interface description', ''),
            })

    trunk_summary = []
    for tname, members in sorted(trunk_by_trunk.items()):
        trunk_summary.append({
            'trunk': tname,
            'count': len(members),
            'members': sorted(members, key=lambda m: (m['ne'], m['interface'])),
        })

    by_down_reason_with_category = {}
    for entry in all_entries:
        r = entry.get('Down Reason', 'Unknown')
        cat = entry.get('Category', 'Other')
        key = (r, cat)
        by_down_reason_with_category[key] = by_down_reason_with_category.get(key, 0) + 1

    # --- Dedicated Eth-Trunk Section (UPlink, VPLS, Resilience on BA/BC) ---
    trunk_section = {
        "trunks": {},
        "total_records": len(trunk_data),
        "total_down_trunks_all": sum(1 for r in trunk_data if r.get('Trunk Status') == 'DOWN'),
        "total_up_trunks_all": sum(1 for r in trunk_data if r.get('Trunk Status') == 'UP'),
        "total_down_members_all": sum(r.get('Down Members Count', 0) for r in trunk_data),
        "all_records": trunk_data,
    }
    for grp in ['UPlink', 'VPLS', 'Resilience']:
        if grp == 'VPLS':
            recs = [
                r for r in trunk_data
                if r.get('Trunk Group') in ('VPLS', 'TO_VPLS') or re.search(r'TO_VPLS', r.get('Description', ''), re.IGNORECASE)
            ]
        elif grp == 'UPlink':
            recs = [
                r for r in trunk_data
                if (r.get('Trunk Group') == 'UPlink' or (r.get('Trunk Name') == 'Eth-Trunk0' and r.get('Trunk Group') not in ('VPLS', 'TO_VPLS') and not re.search(r'TO_VPLS', r.get('Description', ''), re.IGNORECASE)))
            ]
        elif grp == 'Resilience':
            recs = [
                r for r in trunk_data
                if r.get('Trunk Group') == 'Resilience' or (r.get('Trunk Name') == 'Eth-Trunk85' and r.get('Trunk Group') not in ('VPLS', 'TO_VPLS') and not re.search(r'TO_VPLS', r.get('Description', ''), re.IGNORECASE))
            ]
        else:
            recs = []

        up_count = sum(1 for r in recs if r.get('Trunk Status') == 'UP')
        down_count = sum(1 for r in recs if r.get('Trunk Status') == 'DOWN')
        down_members = sum(r.get('Down Members Count', 0) for r in recs)
        total_members = sum(r.get('Total Members', 0) for r in recs)
        trunk_section["trunks"][grp] = {
            "name": grp,
            "total_nodes": len(recs),
            "up": up_count,
            "down": down_count,
            "down_members_total": down_members,
            "total_members": total_members,
            "records": recs,
        }

    return {
        "total": total,
        "total_service": len(report_data),
        "total_noconf": len(noconf_data),
        "province_summary": province_summary,
        "top_down_reasons": top_reasons,
        "interface_types": iface_types,
        "category_summary": category_summary,
        "interface_aggregation": {
            "total_interfaces": total_interfaces,
            "interfaces_with_multi": interfaces_with_multi,
            "alarm_count_distribution": alarm_count_dist,
            "top_interfaces": top_interfaces,
        },
        "site_groups": site_groups,
        "trunk_members": {
            "total_down_members": len(trunk_entries),
            "by_trunk": trunk_summary,
        },
        "trunk_section": trunk_section,
    }
