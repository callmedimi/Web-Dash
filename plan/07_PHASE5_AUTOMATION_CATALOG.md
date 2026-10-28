# 07 — PHASE 5: AUTOMATION CATALOG (what the platform can do)

Goal: make Web-Dash a **Huawei-first NOC automation hub** that beats generic tools on the daily tasks
of this team. Build features as `app/features/<name>/` task functions on top of Phases 2–4.
Each feature = `Spec` (inputs, outputs, risk, permissions) → `run(ctx)` → fixtures + tests → API → UI screen (file 09).
Branch `phase5`. Priority order = build order.

## Feature template (copy for each feature; fill all fields before coding)
```
name / feature_key / risk (low|medium|high) / needs_ssh / needs_telemetry(zabbix|grafana) / read_only
inputs (typed) / outputs (typed) / device commands used (registry names)
failure modes + reason codes / report columns / permission key
```

---
## 5.1 Inventory & Discovery (foundation — build first)
- **Import** NMS export CSV (current `parse_csv_to_routers` logic: `NE Name`, `NE IP Address`, `NE Type (MPU Type)`, `Software Version`, `LSR ID`, `ESN`) into `device` table (upsert by name; show diff of what changed; keep old CSV import UI path working).
- **Province/site derivation** from the `_XXX` suffix convention already used by `filter_routers_by_province` → stored fields `province`, `site`; editable.
- **Groups & tags** (e.g. `province:TEH`, `role:PE`, `vendor-os:vrp8`) and saved **target sets** (replaces re-uploading CSV for every job).
- **Zabbix sync** job (Step 3.4.4): link devices to Zabbix hosts, report unmatched/ambiguous both ways, suggest model/site/tags from Zabbix groups.
- Device health badge: `monitored-ok (zabbix) / ssh-ok / unreachable / auth-failed / not-in-zabbix`.

## 5.2 Alarm Center
- Unified alarm table from SSH `display alarm active` (on demand) with filters: device, province, level, age, interface, text; saved filters.
- "Clear" and "Clear + shutdown noconf" go through the change pipeline (file 06).
- Statistics: top noisy devices/interfaces, alarm age histogram.

## 5.3 Down-Links Report (port `reporting_logic.py`)
- Same fields/columns as now (keep `FIELD_NAMES`, `TRUNK_FIELD_NAMES`), run per province or all; `age_value/age_unit` validated.
- Output: table + analytics charts (`compute_analytics` results) + CSV + XLSX download.
- Scheduling: daily report per province, stored as job history; "compare with yesterday" (new down links / recovered).

## 5.4 License Management (port `license_check.py`, `license_renewal_logic.py`)
- Fleet table: device, product, state, **days to expiry**, features, items used/total.
- **Scheduler**: nightly check; alert when expiry ≤ 90/60/30/7 days.
- Renewal pipeline per 4.4.

## 5.5 VRF / Routing Check (port `check_vrf_routing.py`)
- Inputs: VRF + prefix/IP (+ optional device set). Output: per-hop result table and a **path graph** (originator → RR → PE) rendered in UI.
- Keep `transform_originator_ip` behavior; commands come from the registry.
- Pre-validation of VRF names/IPs (Step 1.6).

## 5.6 PTP / Sync Troubleshoot (port `ptp_troubleshoot_service.py`)
- Traceback hop-by-hop with `max_hops`; output as **topology graph** (nodes = routers, edges = PTP ports, colored by state) + a text verdict ("best clock lost at hop 3 …"), downloadable report.
- Use inventory + Zabbix host data to resolve neighbor IPs faster when possible; SSH only for hop details.

## 5.7 ARP / MAC Lookup (port `site_arp_service.py`)
- Lookup by site code or IP; background **collector jobs** (`start_collector_job` semantics) with progress, stop button (now real cancellation), results searchable table, CSV export. Cache results with TTL and show freshness.

## 5.8 Session Extractor (port `session_extractor_service.py`)
- Generates SecureCRT sessions ZIP from CSV. **Security review required in Step 1.0**: confirm no passwords are embedded in generated files; if they are, remove them (use key/“prompt on connect”).
- Add presets (folder structure by province/role).

## 5.9 Monitoring Hub: Zabbix + Grafana (port `services/zabbix_service.py`, build on Step 3.4)
- Keep the existing Zabbix interface search working (same inputs/outputs) but re-implement on `ZabbixProvider`; `license_db`/DB-refresh logic stays until parity is proven.
- **Fleet Health** screen data: availability, CPU/mem/temperature, active problems per device/province — from Zabbix only (no SSH).
- **Device Monitoring tab:** interface table (admin/oper, rates, errors) + time-range graphs (native charts from `get_series`) + "Open in Grafana" deep link + optional embedded Grafana panel (Step 3.4.3 mode A).
- **Alarm Center merge** (Zabbix problems vs SSH alarms) and "select devices from problems" shortcut into Alarm Clear / Down-Links jobs.
- **Webhook intake** + notifications (5.12).
- Settings page "Integrations": test connection buttons (`apiinfo.version`, token validity, Grafana `/api/health`), `telemetry-doctor` results, mapping coverage %.
- Tokens only in the vault; read-only by default; write scopes (ack, annotations) are separate and opt-in.

## 5.10 Config Backup, Diff, Compliance (file 06 §4.3, 4.5)
- Device page tab "Configs": timeline, diff viewer, download, "who/what changed" correlation with `job` history.
- Compliance dashboard: % compliant per rule per province.

## 5.11 Command Runner (power tool, read-only by default)
- Run an allow-listed set of **read-only** `display …` commands on many devices with templates + variables, collect output, search across outputs (e.g. "find every device where `display ntp status` is unsynchronized"). 
- Registry flag `read_only:true` is required; anything else is impossible from this screen. Output stored per task; grep/regex search across a job's outputs; export.
- Optional **config templates** (Jinja2) for planned changes → goes through the change pipeline (never direct).

## 5.12 Scheduler & Notifications
- `schedule` table + in-app scheduler (single leader via DB lease). Cron syntax with validation; UI to pause/resume/run-now.
- Notifications (all optional, all local/air-gap safe): SMTP email, generic webhook (Telegram/Slack/Eitaa gateways via URL), syslog. Triggers: job failed, change awaiting approval, license expiring, device flapping, compliance regression.

## 5.13 Reporting & Exports
- Unified export service: CSV (utf-8-sig, as now), XLSX, JSON. Large exports streamed.
- "Daily NOC digest" scheduled report (alarms, down links, licenses, failed jobs).

## 5.14 Public API & CLI (for other teams/tools)
- API tokens (hashed in DB, scoped, expiring) for automation; OpenAPI spec served at `/api/v1/openapi.json` + a UI docs page.
- Small CLI wrapper (`webdash-cli`) that calls the API (list devices, start job, wait, download).

## 5.15 Out of scope (do NOT build)
Auto-remediation without approval; direct SNMP of any kind; Zabbix/Grafana writes other than optional ack/annotations; changes to routing/BGP/MPLS config; telnet; any cloud service; user-supplied arbitrary config commands.
