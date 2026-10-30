# 05 — PHASE 3: DEVICE LAYER (SSH + Telemetry via Zabbix/Grafana) — Huawei-first

Goal: one reliable, testable layer that ALL features use to talk to routers.
Resolves F-21, F-25, F-27, F-28, F-29, F-31, F-32. Branch `phase3`.

## Principles
- **SSH = actions, verification & deep diagnostics. Zabbix/Grafana (via API) = fast, wide, read-only monitoring data.** Never use SSH to poll what Zabbix already has. No direct SNMP from the app (owner constraint).
- Every device command is declared in a **command registry** (name, per-OS-family command string, parser, timeout, `read_only: bool`). Features reference commands by name, never by raw string.
- Every parser has: a TextFSM (or small pure function) + ≥3 sanitized fixtures + a unit test. A parser that cannot parse MUST raise `ParseError` — never return "empty = nothing found" (F-25).

## Platform differences (verify on target before use; keep in registry as data)
| Topic | VRP5 (e.g. older NE/ATN) | VRP8 (NE40E/CE/newer) |
|-------|--------------------------|------------------------|
| netmiko device_type | `huawei` / `huawei_vrp` (as repo) | `huawei_vrpv8` |
| Config model | immediate apply | candidate + `commit` |
| Disable paging | `screen-length 0 temporary` | same (keep fallback `screen-length disable`) |
| Rollback | `save` discipline + stored backup | commit-id rollback (confirm exact syntax on lab device) |
The architect could not verify exact rollback syntax on devices — Step 3.1 requires a **capability probe** and the registry must mark unverified commands `verified: false` until a human confirms on a lab device.

---
## Step 3.1 — `devices/` package: driver abstraction
**Files:** `app/devices/{session.py,drivers/vrp5.py,drivers/vrp8.py,registry.py,errors.py,pool.py}`.
**Spec:**
- `DeviceSession` context manager: connect (with retries: 2, backoff 3 s/9 s, only on connect/auth-timeout errors, NEVER retry after a config command was sent), set paging, expose `run(cmd_name, **vars)` (read) and `config_block(lines, *, dry_run)` (write; see file 06). Always `disconnect()` in `finally` — also between retries (fixes F-28).
- `detect_os_family(session)`: parse `display version` → vrp5/vrp8; cache result in `device.os_family`.
- Typed errors: `ConnectTimeout, AuthFailed, CommandTimeout, ViewError, ParseError, DeviceLocked, ConfigRejected`. Map netmiko exceptions to these once, here.
- Jump host / bastion (optional but build the hook): `device.jump_host_id` → SSH proxy (netmiko `ssh_config_file` or paramiko ProxyCommand). Off by default.
- Per-vendor timing knobs from settings: `conn_timeout`, `auth_timeout`, `banner_timeout`, `read_timeout`, `global_delay_factor`.
- Session logging to file is OFF by default (credentials risk); a debug flag per job writes redacted transcripts into `DATA_DIR/transcripts/` with password/secret patterns masked.
**Verify:** with FakeDevice transport: connect failure retried twice; after a config command, no retry; `disconnect` called exactly once per session in every path (assert with mock).

## Step 3.2 — Concurrency + rate limits
**Do:** central semaphore `MAX_SSH_WORKERS` (shared with job engine, don't duplicate), per-site optional cap `site.max_parallel` (default 5) to protect small links, per-device lock from 2.2. Add jittered start (0–500 ms) to avoid login storms. Circuit breaker per device: after 3 consecutive connect failures in 10 min, mark `device.health='unreachable'` and skip for 5 min (job shows `SKIPPED_UNREACHABLE`).
**Verify:** simulated 300 devices, cap respected; breaker opens/closes with a fake clock.

## Step 3.3 — Parsers (replace hand regex)
**Files:** `app/devices/parsers/*.py` + `templates_textfsm/huawei_*.textfsm` + fixtures.
**Build these parsers (each with fixtures VRP5+VRP8 where applicable):**
1. `display alarm active` (use TextFSM; tolerate timestamp with `+HH:MM`, `Z`, no timezone, and 2-line wrapped descriptions). Output: list of `{sequence, alarm_id, level, date, time, description}`. If the raw text has > 3 non-banner lines but 0 parsed rows → raise `ParseError` (F-25).
2. `display interface <if>` (first lines: physical/protocol state, `Administratively DOWN`, description, last change).
3. `display current-configuration interface <if>` → `{lines:[...], is_empty:bool, error:str|None}`; detect device error banners (`Error:`, `Unrecognized command`, `Wrong parameter`) explicitly → `error` set; **an empty reply is `error='EMPTY_OUTPUT'`, never "no config"** (F-20 root cause).
4. `display license` and `display license verbose` — rewrite as a small state machine: sections reset correctly; items always belong to the feature currently being parsed; **no cartesian fallback** (F-29): if verbose is unavailable return basic data with `items_detail_available=false`.
5. `display ip routing-table vpn-instance <vrf> <prefix>`, `display bgp vpnv4 vpn-instance <vrf> routing-table <prefix>`: only if the current `check_vrf_routing.py` already does this — port exactly its commands.
6. `display arp` / `display mac-address` parsers used by ARP/MAC lookup (port from `site_arp_service.py`).
7. `display ptp …` outputs used by PTP troubleshoot (port from `ptp_troubleshoot_service.py`).
8. `display version`, `display device`, `display cpu-usage`, `display memory-usage`, `display temperature all`, `display optical-module`… (only as needed by Phase 5 features).
**Interface-name extraction (F-21):** implement `extract_interface(description) -> InterfaceRef|None` with an explicit, ordered grammar: normalize names (`GE`, `GigabitEthernet`, `10GE`, `25GE`, `40GE`, `100GE`, `XGigabitEthernet`, `Eth-Trunk`, `Ethernet`, `Vlanif`, `LoopBack`, `Tunnel`, `Virtual-Ethernet`, `Serial`, `Pos`, `Cpos`…) including **sub-interface suffix `.NNN`**; strip trailing punctuation `)`,`;`,`,`,`.`; returns `{name, parent, is_sub}`. Ambiguity (two different interfaces in one alarm) → return `None` and mark `AMBIGUOUS`. Property-based/fuzz tests with ≥ 40 real-looking alarm lines.
**Verify:** `pytest -k parsers` green; coverage on parsers ≥ 90 %.

## Step 3.4 — Telemetry subsystem: Zabbix (primary) + Grafana (secondary) — NO direct SNMP
**Decision (from the owner):** the app host cannot send SNMP to routers. Monitoring data comes from the
team's **self-hosted Zabbix and Grafana via their HTTP APIs**. Direct SNMP code is NOT built in this plan
(only an empty `NullProvider`-style interface so it could be added later). Do not add `pysnmp`.

**Files:** `app/telemetry/{base.py,zabbix.py,grafana.py,mapping.py,cache.py,models.py}`; settings `ZABBIX_URL`, `GRAFANA_URL`; tokens live in the credential vault (kind `zabbix_token`, `grafana_token`).

### 3.4.1 Provider interface (`base.py`) — every telemetry consumer uses ONLY this
`TelemetryProvider` methods (all read-only, all return typed dataclasses, all raise `TelemetryError(code)`):
- `list_hosts(filters)` → hosts with id, name, visible name, interfaces/IPs, groups, tags, status (enabled/disabled), availability
- `get_problems(host_ids|groups|severity_min|since)` → active problems (event id, host, name, severity, clock, acknowledged, tags)
- `get_item_value(host_id, key_or_name_pattern)` → latest value + timestamp + units
- `get_series(host_id, key_or_name_pattern, t_from, t_to, max_points)` → time series (uses history for ≤ 24 h, trends beyond)
- `get_interface_table(host_id)` → per-interface: name, admin status, oper status, last change (if items exist), in/out rate, errors
- `ack_problem(event_id, message)` → **optional write**, only if a separate write-scoped token is configured; otherwise raises `NOT_CONFIGURED`
Providers: `ZabbixProvider` (implements all), `GrafanaProvider` (implements `get_series` via datasource queries + annotations/dashboard links), `DisabledProvider`.

### 3.4.2 Zabbix client rules (`zabbix.py`)
- JSON-RPC 2.0 over `POST {ZABBIX_URL}/api_jsonrpc.php`. Authenticate with an **API token** (Zabbix user → API tokens). Send as `Authorization: Bearer <token>` on versions that support it; on older versions use the legacy `auth` field. Detect version with `apiinfo.version` (no auth needed) at startup and choose; store in `/readyz` output.
- Methods used (all read): `host.get`, `hostgroup.get`, `item.get`, `history.get`, `trend.get`, `problem.get`, `event.get`, `trigger.get`. Write (optional, separate token): `event.acknowledge`.
- Token must belong to a **read-only Zabbix user** limited to the relevant host groups. Document this in `docs/zabbix_setup.md`.
- Hard rules: timeout 10 s, 2 retries only for network errors/5xx, **never** retry JSON-RPC business errors; page large results (`limit` + manual paging); request only needed `output` fields; batch by `hostids` (≤ 200 per call); respect `MAX_ZABBIX_CONCURRENCY` (default 4). `history.get` needs the correct `history` value type (0 float, 1 char, 2 log, 3 unsigned int, 4 text) — resolve it from `item.value_type`, never hardcode.
- **Item discovery is configuration, not code:** Huawei templates differ per team. Provide `DATA_DIR/telemetry_map.yml` mapping logical metrics → item key/name patterns, e.g. `cpu_usage`, `mem_usage`, `temperature`, `if_oper_status`, `if_in_rate`, `if_out_rate`, `if_errors_in`. Ship an example file with `TODO: confirm with your template` comments; the agent must NOT invent real key names. A UI/CLI check `telemetry-doctor` lists which logical metrics resolve for N sample hosts and which don't.
- Cache: in-process TTL cache (`cache.py`): host list 5 min, problems 15 s, latest values 30 s, series 60 s; cache key includes provider + params; stale-while-error (serve stale up to 10 min with `stale=true` flag when Zabbix is down).
- Circuit breaker: 5 consecutive failures → open for 60 s; UI shows "Telemetry degraded".

### 3.4.3 Grafana client rules (`grafana.py`)
- Auth: **service account token**, Viewer role. `GET /api/health` for readiness; `GET /api/search`, `GET /api/dashboards/uid/<uid>` to resolve dashboard/panel links.
- Two usage modes — implement mode A fully, mode B as optional:
  - **A. Deep links + embeds:** store per-device or per-group `dashboard_uid` + `panel_id` + variable mapping (e.g. `var-host=<device.name>`) in `telemetry_map.yml`; UI builds links/`d-solo` iframe URLs with `from/to`, `theme`, `kiosk`. Embedding requires Grafana `allow_embedding = true` and an auth method for the viewer (SSO/auth-proxy/anonymous-viewer) — document in `docs/grafana_setup.md`; UI must degrade to "Open in Grafana" link if the iframe fails to load.
  - **B. Data via API:** `POST /api/ds/query` against a Zabbix datasource UID (or Prometheus if present) to fetch series for our own native charts. Only if A is insufficient; verify request shape against the installed Grafana version before coding (record sample request/response as fixtures).
- Annotations: write-back of job events as Grafana annotations (`POST /api/annotations`, tags `webdash`, `job:<type>`) is **optional and off by default** (`GRAFANA_ANNOTATE=false`) — useful to see "alarm-clear ran here" on graphs. Needs an Editor-scoped token; separate from the read token.
- Never proxy the Grafana token to the browser. If the browser must load Grafana content, it goes through the user's own Grafana login/SSO.

### 3.4.4 Device ↔ monitoring mapping (`mapping.py`)
- Column `device.zabbix_hostid` (nullable) + `device.grafana_vars` json.
- Job `telemetry_sync`: match devices to Zabbix hosts by (1) exact host name == `device.name`, (2) visible name, (3) management IP in host interfaces. Output a report: matched / ambiguous (multiple hosts) / missing in Zabbix / Zabbix hosts not in inventory. Ambiguous never auto-linked — UI lets an admin pick.
- Use this to fill `device.model`/`site`/`tags` suggestions from Zabbix groups/tags (suggestion only; human confirms).

### 3.4.5 What the telemetry layer is used for
- Fleet health table (availability, CPU/mem/temp, active problems) — **no SSH needed**.
- Interface up/down overview and traffic/error graphs per interface.
- **Alarm Center merge:** show Zabbix problems next to SSH `display alarm active` for the same device; highlight mismatches (device shows alarm, Zabbix doesn't, and vice-versa).
- **Pre-filter for SSH jobs:** "devices with active problems on interfaces" → candidate list for alarm clearing / down-link report, so SSH only touches relevant routers (big reduction in SSH load).
- Flap/trend hints for the change pipeline's risk model (e.g. interface flapped recently → not a shutdown candidate).
- **Webhook intake (optional):** `POST /api/v1/integrations/zabbix/webhook` (static bearer secret from vault, IP allow-list) so a Zabbix media type can push problem events into our `event` table → live "problem" badges and notifications. A webhook event can only *propose* a change (file 06 plan step), never apply one.
- **Truth rule:** Zabbix/Grafana data is *advisory and delayed*. Anything that decides a config change or verifies it (state after shutdown, interface really admin-down, alarm really cleared) MUST be confirmed over SSH.
**Verify:** record sanitized Zabbix JSON-RPC responses for `host.get`, `problem.get`, `item.get`, `history.get`, `trend.get` as fixtures (`tests/fixtures/zabbix/`) and test the provider against a fake HTTP server; tests for token-version fallback, paging, history type resolution, cache stale-while-error, circuit breaker; grep proves no `pysnmp`/`snmp` socket code and no Zabbix write method outside `ack_problem`.

## Step 3.5 — What to ask whom (put in `docs/` and in UI help)
| Need | Source |
|------|--------|
| Is device alive / availability, uptime, model | Zabbix |
| Interface up/down list across 1000 devices | Zabbix (interface items) |
| Interface traffic/errors history | Zabbix history/trends, or Grafana panel |
| CPU/mem/temperature trend | Zabbix, or Grafana panel |
| Active problems / alarm history | Zabbix `problem.get` / `event.get` |
| Alarms list + clear | SSH |
| Config read/diff/backup | SSH |
| Any configuration change or its verification | SSH only |
| License details | SSH |
| PTP / routing / BGP deep diagnostics | SSH |
| Optical power (DOM) | Zabbix if an item exists, else SSH |

## Step 3.6 — Optional (build hook only, do not enable): NETCONF
Add `devices/netconf.py` interface stub (`get_config`, `edit_config`) and a settings flag `ENABLE_NETCONF=false`. Reason: VRP8 supports structured config via NETCONF/YANG which removes screen-scraping for future features. No implementation beyond the stub in this plan.
