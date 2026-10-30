# 11 — TESTING & ACCEPTANCE

## 1. Test pyramid (what to write, where)
| Layer | Tool | Must cover |
|-------|------|-----------|
| Parsers | pytest + fixtures (`tests/fixtures/vrp/`) | every parser: normal, empty, error banner, wrapped lines, VRP5 + VRP8 |
| Decision logic | pytest | alarm-clear decision table (file 06 §4.2) — every row + edge cases |
| Job engine | pytest | concurrency cap, device mutex, cancel, restart recovery, retention |
| Change pipeline | pytest | state machine, approvals, rollback, blast radius |
| Telemetry | pytest + fake HTTP server + fixtures (`tests/fixtures/zabbix/`, `/grafana/`) | paging, history type, token fallback, cache stale, circuit breaker |
| API | pytest (Flask test client) | auth, CSRF, RBAC, validation errors, IDOR (404 on others' jobs) |
| Security | pytest | text/plain POST rejected; default creds gone; mass-assignment; injection strings in interface/VRF/IP fields |
| Frontend units | Vitest + Testing Library | api client, hooks (`useJobEvents` replay/dedupe), components |
| E2E | Playwright with `WEBDASH_FAKE_DEVICES=true` | flows in §3 |
| Accessibility | axe-core in Playwright | zero serious/critical on every screen |
| Visual | Playwright screenshots (light/dark × LTR/RTL) | no overflow/clipping |

## 2. Smoke checklist (run after EVERY phase; tick in `plan/NOTES_FROM_AGENT.md`)
- [ ] App boots from clean data dir; first-run admin printed once; login works
- [ ] `/healthz` and `/readyz` OK
- [ ] CSV import of nodes works (sanitized sample)
- [ ] Alarm clear in **dry-run** against FakeDevice produces a plan; apply is blocked without approval
- [ ] Down-links report runs, CSV downloads, columns unchanged vs `FIELD_NAMES`
- [ ] License check runs; rows show expiry
- [ ] Cancel a running job: stops within 10 s, SSH sessions closed
- [ ] Restart container mid-job: job marked interrupted, no stuck lock
- [ ] Zabbix integration test button OK (or clear error text)

## 3. Feature parity checklist (old → new). Every line must be verified by a test or a recorded manual check
- [ ] Login/logout/me; roles god/admin/user permissions identical to old `user_has_access`
- [ ] User management: create/update/delete, cannot delete self / last god
- [ ] Permission management per feature
- [ ] Alarm clear — manual targets
- [ ] Alarm clear — bulk CSV
- [ ] Reporting — per province / full / trunk report / analytics / CSV downloads
- [ ] VRF routing check (+ batch)
- [ ] License check (+ cancel)
- [ ] License renewal (+ confirmation step → approval)
- [ ] Zabbix interface search / code-site search / DB refresh
- [ ] Session extractor ZIP
- [ ] PTP troubleshoot traceback
- [ ] Site ARP / IP ARP lookup + collector job start/status/stop
- [ ] All CSV exports keep column names/order and `utf-8-sig` encoding

## 4. Golden scenarios for the flagship (alarm clear) — must exist as tests
1. Admin-down interface with 3 alarms → plan: clear 3 (low risk), no shutdown.
2. Up interface with config → SKIP `HAS_CONFIG_OR_UP`.
3. Noconf interface, down > threshold, no description → plan SHUTDOWN (medium), verify OK → clear.
4. Noconf but **empty config output** → SKIP `CONFIG_UNREADABLE` (regression test for F-20).
5. Alarm on `Eth-Trunk1.100` → target `Eth-Trunk1.100`, never `Eth-Trunk1` (regression for F-21).
6. Alarm text mentioning two interfaces → SKIP `AMBIGUOUS_INTERFACE`.
7. Shutdown applied but verify says not admin-down → rollback executed, status `rolled_back`.
8. Alarm view unavailable → task failed `ALARM_VIEW_UNAVAILABLE`, zero clear commands sent (assert on FakeDevice transcript).
9. Clear returns "not found" → status `NOT_PRESENT`, not counted as cleared.
10. Cancel between devices → remaining devices `cancelled`, SSH sessions closed.
11. Two jobs target the same device → second waits for the lock; transcript shows no interleaving.
12. `READ_ONLY_MODE=true` → apply refused with 403.

## 5. Final acceptance (project is DONE only if ALL true)
**Security**
- [ ] No default credentials; no secrets in git history of the new code or in the image
- [ ] CSRF + SameSite + session invalidation verified by tests
- [ ] All device-bound strings validated; fuzz tests pass
**Safety**
- [ ] Every device-changing feature goes through plan → approve → apply → verify (+ rollback)
- [ ] No code path can shut down an interface when config/state could not be read
- [ ] Direct SNMP code absent; Zabbix/Grafana writes limited to opt-in ack/annotations
**Reliability**
- [ ] Jobs persist across restart; cancel works; per-device lock works; concurrency cap works
- [ ] Soak test (10.8) passed and documented
**Quality**
- [ ] CI green (lint, types, tests, coverage gates, bundle budgets, audit)
- [ ] Parser coverage ≥ 90 %; golden scenarios (§4) pass
**UI**
- [ ] All screens in file 09 implemented; axe has no serious/critical issues; RTL and dark mode verified
- [ ] No external network requests from the browser (Playwright assertion)
- [ ] Performance budgets met; 10 000-row table and 200 000-line log stay smooth
**Ops**
- [ ] One-command deploy (`docker compose up -d`), offline install documented and tested
- [ ] Backup + restore tested; runbook exists
- [ ] Legacy code removed; `v2.0.0` tagged

## 6. When you are stuck (agent protocol)
1. Re-read the step's **Don't** list. 2. Re-run its **Verify**. 3. If a repo file differs from the plan, write it in
`NOTES_FROM_AGENT.md` and take the smallest safe interpretation. 4. If a device command/OID/Zabbix item key is unknown,
mark it `verified:false` / `TODO(confirm)` and ask the owner — **never invent it**.
