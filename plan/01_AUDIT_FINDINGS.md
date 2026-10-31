# 01 — AUDIT FINDINGS

Severity: **C** critical (fix first) · **H** high · **M** medium · **L** low.
"Fix in" = the plan step that resolves it. Evidence = file/function as read from the repo.

## A. Security

| ID | Sev | Finding | Evidence | Fix in |
|----|-----|---------|----------|--------|
| F-01 | C | **Default admin account with known password.** On first run `users.json` is created with user `Dimi`, password `god`, role `god`. | `auth.py::_init_default_users` | 1.2 |
| F-02 | H | **CSRF.** Routes call `request.get_json(force=True)` (ignores Content-Type) and session cookie has no SameSite. A third-party page can submit a `text/plain` POST that is parsed as JSON → any logged-in admin can be tricked into creating users / running jobs. | `app.py` all POST routes | 1.3 |
| F-03 | H | **Session carries role+permissions snapshot.** `session["user"]` stores role and permissions at login; revoking permissions or deleting a user does NOT take effect until cookie expires. No `PERMANENT_SESSION_LIFETIME`, no session reset on login (fixation). | `app.py::login`, `auth.py::permission_required` | 1.3 |
| F-04 | H | **No brute-force protection / audit trail** on `/login`. | `app.py::login` | 1.4 |
| F-05 | H | **IDOR on job sessions.** Any logged-in user can read `/stream/<sid>`, `/download/<sid>`, `/session/<sid>`, report/PTP/license equivalents for jobs started by others. IDs are only 12 hex chars. | `app.py` stream/download routes | 2.4 |
| F-06 | H | **Device credentials travel in every request body** (`username`/`password`) from the browser and live in thread args. Plain HTTP in the demo deployment. | `/run-manual`, `/run-bulk`, `/run-report`, … | 3.2 + 10.x |
| F-07 | M | **Mass assignment** in user update: `update_user(username, data)` writes any key from the JSON body (e.g. `role` with unvalidated value). Role only validated on create. | `app.py::admin_update_user`, `auth.py::update_user` | 1.5 |
| F-08 | M | `users.json` and `.secret_key` live in the app directory (not a volume) and `Dockerfile` does `COPY . .` → can be baked into the image; lost on rebuild. | `Dockerfile`, `auth.py`, `app.py` | 1.1, 10.1 |
| F-09 | M | No upload size limit (`MAX_CONTENT_LENGTH` unset); CSV fully read in memory. | `parse_csv_to_routers` | 1.6 |
| F-10 | M | No input schema validation: `int(data.get("age_value"))` raises → HTTP 500; bad payload shapes crash handlers. | `run_report`, `run_full_report` | 1.6 |
| F-11 | L | Container runs as root, Flask dev server (`python app.py`) used as production server. | `Dockerfile` | 10.1 |
| F-12 | L | Hardcoded infra constants in source (`HARDCODED_ROUTER_NAME/IP`, `HARDCODED_RR_IP`). | `check_vrf_routing.py` import list in `app.py` | 1.7 |

## B. Correctness bugs (software)

| ID | Sev | Finding | Evidence | Fix in |
|----|-----|---------|----------|--------|
| F-20 | C | **Empty `display current-configuration interface X` output ⇒ interface treated as "noconf" and SHUT DOWN.** `is_trivial_interface_config` returns True when no meaningful lines exist; a timeout/paging/empty reply looks identical to "no config". | `auto_clear_noconf.py::is_trivial_interface_config`, `process_one` | 4.2 |
| F-21 | C | **Wrong interface can be extracted from alarm text.** Regex fallback `\b(Eth-Trunk\d+)\b` matches the parent of `Eth-Trunk1.100`; no pattern for `100GE`, `10GE`, `25GE`, `Tunnel`, `Ethernet`, `GE`, sub-interfaces; `ifName=([^\s,]+)` can capture trailing `)`/`;`. A shutdown may hit the parent instead of the sub-interface. | `extract_interface_from_description` | 3.4, 4.2 |
| F-22 | H | **Automatic shutdown with no preview/approval/rollback**, no config save policy, view left uncertain on failure (no `return`/`quit` in exception path), `commit` failure swallowed. | `process_one` | 4.1–4.5 |
| F-23 | H | **Clear-success detection is wrong.** Empty reply, "does not exist", "not found", "no alarm" are all counted as `Success`. Counts and CSV report are inflated. | `process_one` | 4.2 |
| F-24 | M | `in_alarm_context` is set but never checked: if the `alarm` view is unavailable the code still sends `clear alarm active …` in the wrong view. | `process_one` | 4.2 |
| F-25 | M | Alarm regex requires `+HH:MM` timestamp; other device formats parse to 0 alarms silently ("no alarms" is reported for a parsing failure). | `parse_filtered_alarms` | 3.3 |
| F-26 | H | **Cancel does not cancel.** `break` inside `with ThreadPoolExecutor` still waits for running futures; all tasks were already submitted; only license job has a flag, others none. | `_run_license_check` and other runners | 2.3 |
| F-27 | H | **No per-device lock.** Two jobs (or two users) can configure the same router at the same time → VRP config lock/commit collisions. No global concurrency cap: each job spawns its own pool of 10. | all `_run_*` | 2.3, 3.2 |
| F-28 | M | `license_check.py`: on first attempt failure the connection is not disconnected before retry (leaked SSH session). | `check_license_on_router` | 3.3 |
| F-29 | M | `parse_display_license`: `in_table` never resets, so later lines are regex-matched as items; global keys are ignored after first `Feature name`. The fallback copies **all** items into **every** feature (duplication). | `license_check.py` | 3.3 |
| F-30 | L | `/download*` mutate stored data in place (`row["Timestamp"]=…`, `.sort()`) without the lock → race + changing results between downloads. | `download`, `download_report` | 2.4 |
| F-31 | M | Parsing by hand-written regex per command, no fixtures/tests, so any VRP version change breaks silently. | all parsers | 3.3 |
| F-32 | L | Device type `huawei_vrp` used for everything; VRP8 (NE40E/CE) has different commit semantics (`huawei_vrpv8` exists in netmiko). | all `ConnectHandler` | 3.1 |

## C. Architecture / scalability

| ID | Sev | Finding | Fix in |
|----|-----|---------|--------|
| F-40 | H | **5 copy-pasted in-memory session stores** (`sessions`, `report_sessions`, `license_sessions`, `ptp_sessions`, `lic_renewal_sessions`), each with own lock/queue/log helpers. Never cleaned up → memory leak (logs lists + queues grow forever). | 2.1–2.2 |
| F-41 | H | All state lost on restart; cannot run >1 worker; job history impossible. | 2.1 |
| F-42 | M | SSE uses a single `Queue` consumer: a second tab or reconnect sees nothing/only partial logs; refresh loses live view. No `Last-Event-ID` replay. | 2.4 |
| F-43 | M | `app.py` is a 2300-line monolith; root contains scripts without extension (`check-routing`), mixed with `services/`. `_run_manual` and `_run_bulk` are near duplicates. | 2.5 |
| F-44 | M | No structured logging, no metrics, no health endpoint, no audit log of who ran what on which device. | 2.6, 10.3 |
| F-45 | M | No scheduling (license expiry, backups, reports must be manual). | 5.x |
| F-46 | L | Zero tests, no CI, no lint, no type check. | 11 |

## D. UI/UX (from architecture; templates not readable by the architect)
| ID | Sev | Finding | Fix in |
|----|-----|---------|--------|
| F-60 | H | Single `index.html` SPA with per-feature ad-hoc JS (assumed). Verify in Step 1.0. | 8.x |
| F-61 | M | Credentials typed on every run; no saved targets/groups; no job history; no diff/preview; logs as plain text. | 9.x |

## Agent additions (append here during Step 1.0)

| ID | Sev | Finding | Evidence | Fix in |
|----|-----|---------|----------|--------|
| F-90 | C | **CLI Command Injection via Unsanitized Device Commands.** User-controlled parameters (`target_ip`, `vrf`, `ip`, `interface_name`, `tid`, `iface`, `seq`, `slave_interface`, `filename`) are formatted directly into VRP commands with f-strings without regex validation or newline stripping. If input contains `\n` or CLI delimiters, attacker can break out to `system-view` and execute arbitrary configuration on core routers. | `check_vrf_routing.py::get_vrf_routes`, `check_bgp_route`; `reporting_logic.py`; `auto_clear_noconf.py::process_one`; `ptp_troubleshoot_service.py`; `license_renewal_logic.py` | 1.6 |
| F-91 | H | **Missing Authentication on PTP Diagnostic Endpoints.** Endpoints `/ptp/stream/<sid>` (line 2285) and `/ptp/session/<sid>` (line 2319) lack `@login_required`. The authorization check `if user_info and not user_has_access(...)` evaluates to False when unauthenticated (`user_info is None`), allowing unauthenticated attackers to inspect active PTP traces and stream logs. | `app.py::ptp_stream`, `app.py::ptp_session_details` | 1.3 |
| F-92 | H | **Unsafe File Access & In-Tree Persistence in License Database.** `services/license_db.py` saves `license_renewals.json` directly inside the source tree (`services/`). Endpoint `/download-archived-license/<filename>` checks file existence in working directory if not found in `license_archive` (`if os.path.isfile(safe_filename)`). | `services/license_db.py`, `app.py::download_archived_license` | 1.1 |
| F-93 | M | **6th In-Memory Session Store.** `session_extractor_jobs` (dict with 2-hour purge loop) adds another ephemeral in-memory state store alongside `SESSIONS`, `REPORT_SESSIONS`, `LICENSE_SESSIONS`, `ROUTING_SESSIONS`, and `PTP_SESSIONS`. | `app.py::create_session_extractor_job` | 2.1 |
| F-94 | M | **Ad-Hoc Frontend Architecture Without Central API Wrapper or CSRF Handling.** `templates/index.html` contains >4400 lines of inline vanilla JS. Each module issues direct `fetch()` calls independently with no centralized error handler, no CSRF token header, and network credentials (`window.networkCreds`) held in memory and submitted in plaintext JSON bodies. | `templates/index.html` | 1.3, 8.x |
| F-95 | L | **Hardcoded Infrastructure IPs and Router Identifiers.** Hardcoded values `HARDCODED_ROUTER_NAME`, `HARDCODED_ROUTER_IP`, `HARDCODED_RR_IP` in `check_vrf_routing.py` and `app.py` must be moved to centralized settings/env. | `check_vrf_routing.py`, `app.py` | 1.7 |
| F-96 | L | **Minimal Dependencies & Unsafe Docker Volume Mount.** `requirements.txt` lacks pinned versions and excludes production WSGI servers (Gunicorn) or Pydantic. `docker-compose.yml` mounts root `.:/app` directly, defeating container isolation. | `requirements.txt`, `docker-compose.yml` | 1.1, 10.1 |

