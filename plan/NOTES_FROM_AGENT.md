# Agent Notes: Frontend Architecture & Command Injection Audit (Step 1.0)

## Frontend Structure Summary
1. The frontend is a monolithic Single Page Application (SPA) located entirely in `templates/index.html` (5728 lines, ~274 KB).
2. It uses local Bootstrap 5 (`static/css/bootstrap.min.css` and `static/js/bootstrap.bundle.min.js`) plus custom styles (`static/css/netmate.css`, `tokens.css`). No CDN is used.
3. No frontend JavaScript framework (React/Vue/Angular) is used in the current version; all logic is written in ~4400 lines of inline vanilla JavaScript (`<script>` block lines 1299–5726).
4. Tab navigation is handled by custom `initTabs()` and `selectSubItem()` helper functions that toggle CSS active classes and card display properties.
5. Authentication flow starts on `DOMContentLoaded` by calling `checkAuth()`, which queries `GET /me`. If unauthenticated, it displays `#authScreen` and hides the main UI.
6. The frontend contains no centralized API client or fetch wrapper; each feature function directly invokes `window.fetch()` with hardcoded endpoints.
7. CSRF protection is completely absent on the frontend; requests do not send an `X-CSRF-Token` or equivalent header.
8. Shared network credentials (`window.networkCreds = {username, password}`) are stored in a global JavaScript variable in memory when the user clicks "Set".
9. Every subsequent action payload (e.g., in alarm clear, reporting, VRF, license, PTP) sends these credentials in plaintext JSON bodies (`data.username`, `data.password`).
10. Live logging and real-time execution progress are consumed via `new EventSource('/events/' + sid)` or dedicated stream endpoints (`/stream-license/`, `/stream-lic-renewal/`, `/ptp/stream/`).
11. EventSource listeners parse incoming JSON messages and append formatted HTML log lines to DOM containers (e.g. `#logOutput`, `#ptpLiveLog`).
12. Terminal/log panels implement auto-scrolling to the bottom unless the user has manually scrolled upwards.
13. Status polling (`setInterval` querying `/status/<sid>` or `/ptp/session/<sid>`) acts as a secondary mechanism when streams complete or fail.
14. File uploads (CSV and license files) use native HTML drag-and-drop and `FormData` sent via `fetch` to `/parse-csv`, `/parse-csv-nodes`, `/match-licenses`, etc.
15. Data tables (e.g., for licenses, down links, PTP hops) are rendered via imperative string concatenation and `innerHTML` assignments with a custom `escapeHtml()` function.

## User-Controlled Values Concatenated into Router Commands (Audit for Step 1.6)
The following user-supplied values are directly interpolated into Huawei VRP CLI strings via f-strings/concatenation without strict regex sanitization:
1. `interface_name` / `iface` / `slave_interface` / `tid`: Interface identifiers (e.g. `display interface {iface}`, `int {iface}`, `display interface Eth-Trunk{tid}`, `display transceiver interface {intf} verbose`). Must be validated with strict interface regex `^(GE|10GE|25GE|40GE|100GE|Eth-Trunk|GigabitEthernet|XGigabitEthernet|Tunnel|LoopBack|NULL)\d+(\/\d+)*(\.\d+)?$`.
2. `vrf`: VPN instance name in `display ip routing-table vpn-instance {vrf} {ip}` and `display ip vpn-instance {vrf}`. Must be strictly alphanumerical `^[A-Za-z0-9_.-]{1,31}$`.
3. `ip` / `target_ip` / `originator_ip` / `prefix`: Target addresses in `display ip routing-table vpn-instance {vrf} {ip}` and `display bgp vpnv4 all routing-table peer {HARDCODED_RR_IP} received-routes {target_ip}`. Must be strictly validated using `ipaddress.ip_network` or `ipaddress.ip_address`.
4. `seq`: Alarm sequence number in `clear alarm active sequence {seq}`. Must be strictly integer `^\d+$`.
5. `filename`: License file name in `license verify {filename}` and `license active {filename}`. Must match `^[A-Za-z0-9_.-]+\.(dat|xml)$`.
6. `province`: Province code used in filtering and routing functions. Must match `^[A-Z]{2,6}$`.
7. `router_name` / `ne_name`: Hostname used in session logs and connection lookups. Must match `^[A-Za-z0-9_.-]{1,64}$`.

All of the above will be enforced via Pydantic request models and strict pre-execution regex checks in Step 1.6.

## Phase 1 Acceptance & Smoke Checklist (Step 1.9, 11_TESTING_ACCEPTANCE.md §2)
- [x] App boots from clean data dir; first-run admin printed once; login works (`tests/test_step_1_2_auth_bootstrap_and_policy.py`)
- [x] `/healthz` and `/readyz` OK (`tests/test_step_1_9_phase1_regression.py`)
- [x] CSV import of nodes works with validation (`/parse-csv`, `/parse-csv-nodes`)
- [x] `READ_ONLY_MODE=true` -> `/run-bulk`, `/run-manual`, and license renewals refuse with 403 `READ_ONLY`; reports still work (`tests/test_step_1_8_read_only_mode.py`)
- [x] Down-links report runs, CSV downloads, columns unchanged vs `FIELD_NAMES`
- [x] License check runs; validation enforced on routers
- [x] Zero hardcoded dotted IPs in non-test python code; settings loaded centrally from `settings.py` / `config.ini` (`tests/test_step_1_7_settings_and_config.py`)
- [x] Brute-force lockout (5 attempts -> 15 min lock) + audit logging in `DATA_DIR/audit.log` without plaintext passwords (`tests/test_step_1_4_login_throttling_and_audit.py`)
- [x] Session & CSRF hardening with constant-time token comparison (`tests/test_step_1_3_session_csrf_hardening.py`)
- [x] Input validation, limits & CLI delimiter rejection (`tests/test_step_1_6_input_validation_and_limits.py`)
- [x] All 59 automated pytest tests pass cleanly (`59 passed in 13.53s`)

