#!/usr/bin/env python3
import json
import netmiko
import re
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime


def parse_filtered_alarms(output):
    alarms = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(x in line for x in [
            'Sequence', '--------', '1:Critical', 'Info:', 'press CTRL_C',
            'It will take a long time', 'no active alarms'
        ]):
            continue
        match = re.match(
            r'^\s*(\d+)\s+(0x[0-9A-Fa-f]+)\s+(\d)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})\s+(.+)$',
            line
        )
        if match:
            seq, alarmid, level, date, time_, desc = match.groups()
            alarms.append({
                'sequence': int(seq),
                'alarmid': alarmid,
                'level': int(level),
                'date': date,
                'time': time_,
                'description': desc.strip()
            })
    return alarms


def extract_interface_from_description(description):
    patterns = [
        r'ifName=([^\s,]+)',
        r'InterfaceName=([^\s,]+)',
        r'mainIfname=([^\s,]+)',
        r'EntPhysicalName=([^\s,]+)',
        r'SubIfName=([^\s,]+)',
        r'Interface=([^\s,]+)',
        r'PortID=([^\s,]+)',
        r'\b(GigabitEthernet\d+/\d+/\d+)\b',
        r'\b(Vlanif\d+)\b',
        r'\b(Eth-Trunk\d+)\b',
        r'\b(XGigabitEthernet\d+/\d+/\d+)\b',
        r'\b(LoopBack\d+)\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    return None


def is_trivial_interface_config(config_lines):
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
        meaningful.append(s.lower())
    allowed = {'dcn', 'undo dcn', 'shutdown', 'undo shutdown'}
    return len(meaningful) == 0 or all(cmd in allowed for cmd in meaningful)


def process_router(name, router_info, username, password, conn_timeout, cmd_timeout, report_data):
    host = router_info.get('ip', '').strip()
    if not host:
        print(f"{name}: Skipped - no IP provided")
        return f"{name}: Skipped - no IP provided"

    def _log(msg, level="info"):
        print(f"  [{level.upper()}] {msg}")

    res = process_one(name, host, username, password, _log, conn_timeout, cmd_timeout)
    for entry in res["entries"]:
        entry["Timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report_data.append(entry)

    summary = f"{name}: {res['status']} — {res['alarms_cleared']} cleared, {res['interfaces_shutdown']} shutdown"
    if res["error"]:
        summary += f" ({res['error']})"
    print(summary)
    return summary


# ---------------------------------------------------------------------------
# Core processing  (with logging callback for live SSE)
# ---------------------------------------------------------------------------
def process_one(
    name: str,
    host: str,
    username: str,
    password: str,
    log,
    conn_timeout: int = 30,
    cmd_timeout: int = 90,
) -> dict:
    conn = None
    result = {
        "name": name,
        "host": host,
        "alarms_cleared": 0,
        "interfaces_shutdown": 0,
        "entries": [],
        "error": None,
        "status": "success",
    }

    try:
        log(f"Connecting to {name} ({host}) ...")
        conn = netmiko.ConnectHandler(
            device_type="huawei_vrp",
            host=host,
            username=username,
            password=password,
            timeout=conn_timeout,
        )
        log(f"Connected to {name}")

        try:
            conn.send_command("screen-length 0 temporary", read_timeout=cmd_timeout)
        except Exception:
            pass

        log("Fetching active alarms (excluding LDP/BFD) ...")
        alarms_output = conn.send_command(
            "display alarm active | exclude D_LDP_TNL | exclude BFD | no-more",
            read_timeout=cmd_timeout,
        )

        if not alarms_output.strip() or "no active alarms" in alarms_output.lower():
            conn.disconnect()
            result["status"] = "skipped"
            result["error"] = "No active alarms"
            log("No active alarms found — skipped", "warn")
            return result

        all_alarms = parse_filtered_alarms(alarms_output)
        log(f"Parsed {len(all_alarms)} alarm(s)")

        interface_to_alarms: dict[str, list] = {}
        for alarm in all_alarms:
            iface = extract_interface_from_description(alarm["description"])
            if iface:
                interface_to_alarms.setdefault(iface, []).append(alarm)

        if not interface_to_alarms:
            conn.disconnect()
            result["status"] = "skipped"
            result["error"] = "No interfaces extracted"
            log("No interface found in alarm descriptions — skipped", "warn")
            return result

        log(f"Found {len(interface_to_alarms)} interface(s) with alarms")

        targets: list[tuple[str, str, list]] = []

        for iface in sorted(interface_to_alarms.keys()):
            admin_down = False
            try:
                out = conn.send_command(f"display interface {iface}", read_timeout=cmd_timeout)
                if out:
                    for line in out.splitlines()[:5]:
                        if "Administratively DOWN" in line:
                            admin_down = True
                            break
            except Exception:
                pass

            is_noconf = False
            try:
                cfg_out = conn.send_command(
                    f"display current-configuration interface {iface}",
                    read_timeout=cmd_timeout,
                )
                raw_lines = [l.rstrip() for l in cfg_out.splitlines()]
                is_noconf = is_trivial_interface_config(raw_lines)
            except Exception:
                pass

            if is_noconf:
                action = "NoConf_AlreadyDown" if admin_down else "NoConf_Shutdown"
                if not admin_down:
                    shutdown_ok = False
                    try:
                        conn.send_command("sys", expect_string=r"\[.*\]", read_timeout=cmd_timeout)
                        conn.send_command(
                            f"interface {iface}", expect_string=r"\[.*\]", read_timeout=cmd_timeout
                        )
                        conn.send_command(
                            "shutdown", expect_string=r"\[.*\]", read_timeout=cmd_timeout
                        )
                        try:
                            conn.send_command(
                                "commit", expect_string=r"\[.*\]", read_timeout=cmd_timeout
                            )
                        except Exception:
                            pass
                        conn.send_command("return", expect_string=r"[<\[]", read_timeout=cmd_timeout)

                        vout = conn.send_command(
                            f"display interface {iface}", read_timeout=cmd_timeout
                        )
                        if vout:
                            first_lines = vout.splitlines()[:5]
                            status_line = first_lines[0] if first_lines else "(no lines)"
                            shutdown_ok = any(
                                "administratively" in line.lower()
                                for line in first_lines
                            )
                            if not shutdown_ok:
                                log(
                                    f"Interface {iface} state after shutdown: {status_line}",
                                    "warn",
                                )
                        else:
                            log(
                                f"display interface {iface} returned empty output",
                                "warn",
                            )

                        if shutdown_ok:
                            result["interfaces_shutdown"] += 1
                            log(f"Shutdown noconf interface {iface}")
                        else:
                            log(
                                f"Shutdown of {iface} did not take effect — skipping.",
                                "error",
                            )
                    except Exception as e:
                        log(f"Failed to shutdown {iface}: {e}", "error")

                    if shutdown_ok:
                        targets.append((iface, action, interface_to_alarms[iface]))
                else:
                    log(f"Noconf interface {iface} already administratively DOWN")
                    targets.append((iface, action, interface_to_alarms[iface]))
            elif admin_down:
                targets.append((iface, "AdminDown", interface_to_alarms[iface]))
                log(f"Admin-down interface {iface} — will clear alarms")
            else:
                count = len(interface_to_alarms[iface])
                log(f"Skipped {iface}: not admin-down and not noconf ({count} alarm(s))", "warn")

        if not targets:
            conn.disconnect()
            result["status"] = "skipped"
            result["error"] = "No interfaces matched criteria"
            log("No interfaces matched criteria", "warn")
            return result

        log(f"Targeting {sum(len(a) for _, _, a in targets)} alarm(s) across {len(targets)} interface(s)")

        conn.send_command("sys", expect_string=r"\[.*\]", read_timeout=cmd_timeout)
        in_alarm_context = False
        try:
            conn.send_command("alarm", expect_string=r"\[.*-alarm\]", read_timeout=cmd_timeout)
            in_alarm_context = True
            log("Entered alarm context")
        except Exception:
            log("Alarm MDP not available — cannot clear alarms on this device", "error")

        for iface, action, alarms in targets:
            for alarm in alarms:
                seq = alarm["sequence"]
                log(f"Clearing alarm seq {seq} on {iface} ({action}) ...")
                clear_status = "Failed"
                try:
                    res = conn.send_command(
                        f"clear alarm active sequence-number {seq}",
                        read_timeout=cmd_timeout,
                    )
                    lo = res.lower() if res else ""
                    if (
                        "success" in lo
                        or "does not exist" in lo
                        or "not found" in lo
                        or "no alarm" in lo
                        or res.strip() == ""
                    ):
                        result["alarms_cleared"] += 1
                        clear_status = "Success"
                except Exception:
                    clear_status = "Failed (Timeout)"

                result["entries"].append({
                    "NE_Name": name,
                    "Interface": iface,
                    "Sequence_Number": seq,
                    "Alarm_Description": alarm["description"][:100],
                    "Action": action,
                    "Clear_Status": clear_status,
                })

        conn.disconnect()
        log(
            f"Done — {result['alarms_cleared']} cleared, "
            f"{result['interfaces_shutdown']} shutdown",
            "success",
        )
        return result

    except Exception as e:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass
        result["status"] = "failed"
        result["error"] = str(e)
        log(f"Error: {e}", "error")
        return result


def generate_csv_report(report_data, filename="auto_clear_report.csv"):
    if not report_data:
        print("No data to write to CSV.")
        return
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['NE_Name', 'Interface', 'Sequence_Number', 'Alarm_Description', 'Action', 'Clear_Status', 'Timestamp']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_data)
    print(f"Report generated: {filename} ({len(report_data)} entries)")


def main():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Config error: {e}")
        return 1

    creds = config.get('credentials', {})
    settings = config.get('settings', {})
    routers = config.get('routers', {})
    report_data = []

    print(f"Processing {len(routers)} routers...")

    with ThreadPoolExecutor(max_workers=settings.get('num_threads', 10)) as executor:
        futures = [
            executor.submit(
                process_router, name, info, creds.get('user'), creds.get('password'),
                settings.get('conn_timeout', 30), settings.get('command_timeout', 90), report_data
            )
            for name, info in routers.items() if info.get('ip')
        ]
        results = [f.result() for f in futures]

    for res in results:
        print(f"  {res}")
    generate_csv_report(report_data)


if __name__ == '__main__':
    exit(main())
