from __future__ import annotations
import netmiko
import re
import time


def parse_display_license(output: str) -> dict:
    result = {
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
    current_feature = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if ':' in stripped and not in_table and not stripped.startswith('-') and not current_feature:
            key, _, val = stripped.partition(':')
            key_lower = key.strip().lower()
            val = val.strip()
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


def parse_display_license_verbose(output: str) -> dict:
    result = {
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
    current_feature = None
    current_item = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if ':' in stripped and not stripped.startswith('-') and not current_feature:
            key, _, val = stripped.partition(':')
            key_lower = key.strip().lower()
            val = val.strip()
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
            elif stripped.startswith('Item name'):
                if current_item:
                    current_item['item_name'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Item type'):
                if current_item:
                    current_item['item_type'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Control value'):
                if current_item:
                    current_item['control_value'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Used value'):
                if current_item:
                    current_item['used_value'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Item state'):
                if current_item:
                    current_item['item_state'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Item expired date'):
                if current_item:
                    current_item['item_expired_date'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Item trial days'):
                if current_item:
                    current_item['item_trial_days'] = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('Description'):
                if current_item:
                    current_item['description'] = stripped.split(':', 1)[1].strip()

    return result


def try_display_license_verbose(conn, log, cmd_timeout) -> tuple[dict, bool]:
    commands_to_try = [
        'display license verbose',
        'display license verbose | no-more',
    ]
    for cmd in commands_to_try:
        try:
            log(f"Trying: {cmd}")
            out = conn.send_command(cmd, read_timeout=cmd_timeout)
            parsed = parse_display_license_verbose(out)
            if parsed.get('features') or parsed.get('items'):
                return parsed, True
        except Exception:
            continue
    return {}, False


def check_license_on_router(name, host, username, password, log, conn_timeout=30, cmd_timeout=90):
    conn = None
    result = {
        'name': name,
        'host': host,
        'status': 'success',
        'error': None,
        'license_info': {},
        'license_verbose_info': {},
    }

    for attempt in range(2):
        try:
            log(f"Connecting to {name} ({host}) ...")
            conn = netmiko.ConnectHandler(
                device_type='huawei_vrp',
                host=host,
                username=username,
                password=password,
                timeout=conn_timeout,
            )
            log(f"Connected to {name}")

            try:
                conn.send_command("screen-length 0 temporary", read_timeout=cmd_timeout)
            except Exception:
                try:
                    conn.send_command("screen-length disable", read_timeout=cmd_timeout)
                except Exception:
                    pass

            lic_output = conn.send_command('display license', read_timeout=cmd_timeout)
            lic_info = parse_display_license(lic_output)
            result['license_info'] = lic_info

            lic_ver_info, verbose_ok = try_display_license_verbose(conn, log, cmd_timeout)
            result['license_verbose_info'] = lic_ver_info

            if not verbose_ok and lic_info.get('items'):
                lic_ver_info = {
                    'active_license': lic_info.get('active_license', ''),
                    'license_state': lic_info.get('license_state', ''),
                    'product_name': lic_info.get('product_name', ''),
                    'product_version': lic_info.get('product_version', ''),
                    'features': [],
                    'items': [],
                }
                for feat in lic_info.get('features', []):
                    fcopy = dict(feat)
                    fcopy['items'] = []
                    for item in lic_info.get('items', []):
                        fcopy['items'].append({
                            'item_name': item['item_name'],
                            'item_type': item['item_type'],
                            'control_value': item['value'],
                            'item_state': '',
                            'item_expired_date': '',
                            'description': item['description'],
                        })
                        lic_ver_info['items'].append({
                            'item_name': item['item_name'],
                            'item_type': item['item_type'],
                            'control_value': item['value'],
                            'item_state': '',
                            'item_expired_date': '',
                            'description': item['description'],
                        })
                    lic_ver_info['features'].append(fcopy)
                result['license_verbose_info'] = lic_ver_info
                log("  (fallback: used display license items table)", "warn")

            conn.disconnect()

            exp = ''
            if lic_info.get('features'):
                exp = lic_info['features'][0].get('expired_date', '')
            pn = lic_info.get('product_name', '')
            state = lic_info.get('license_state', '')
            items_count = len(result['license_verbose_info'].get('items', []))
            log(f"{name}: {pn} | State: {state} | Expiry: {exp}")
            log(f"  Items: {items_count} feature item(s) parsed", 'success')

            return result

        except Exception as e:
            if attempt == 0:
                time.sleep(3)
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
