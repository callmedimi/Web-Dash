# 09 — PHASE 7: UI SCREENS (one step per screen)

Prereq: files 04–08 done for the feature behind the screen. Each screen = route, layout (ASCII), data sources (API),
behaviors, states, permissions, acceptance. Use ONLY components from file 08 §6.4. Branch `phase7`.
Order = build order. After each screen: Playwright happy-path test + axe check + RTL screenshot.

---
## 9.1 Login & first-run password change  (`/login`, `/change-password`)
Centered single form on `--bg`; no marketing text. Fields: username, password; error inline under form. First run with `PASSWORD_CHANGE_REQUIRED` redirects to change-password (policy hints shown live: ≥ 12 chars). Lockout (429) shows remaining time.
**Accept:** keyboard-only login works; wrong password message identical for unknown user.

## 9.2 Overview  (`/`)
```
┌ Fleet health (Zabbix)        ┬ Needs attention (list, max 10)             ┐
│ availability %, devices up/  │ failed jobs · changes awaiting approval ·  │
│ degraded/down by province    │ licenses expiring ≤ 30 d · devices flapping│
├──────────────────────────────┴────────────────────────────────────────────┤
│ Recent jobs (table, last 20)  │  Active problems by severity (Zabbix)      │
└───────────────────────────────────────────────────────────────────────────┘
```
Every number is a link to the filtered list behind it. No decorative sparklines; a chart appears only if it answers a question (e.g., problems over last 24 h by severity).
**Data:** `/api/v1/overview` (aggregates; cached 30 s; degrade gracefully if Zabbix is down → "Telemetry degraded" chip, other panels still load).

## 9.3 Devices  (`/devices`, `/devices/:id`)
List: DataTable (name, IP, model, OS family, province, site, tags, health, last seen, license days, in Zabbix?). Bulk actions on selection: "Add to target set", "Tag", "Run… ▸ (alarm clear plan / down-links / license check / config backup)". Import button → CSV import wizard (upload → preview diff: new/changed/unchanged → confirm).
Detail page tabs: **Summary** (identity, health, links) · **Monitoring** (interface table + graphs + Grafana panel) · **Alarms** (SSH on demand + Zabbix) · **Configs** (timeline + diff) · **Jobs** (history for device) · **Compliance**.
**Accept:** 5 000 devices scroll smoothly; saved view persists after reload.

## 9.4 Target sets  (`/targets`)
Named, reusable device sets: static (pick devices) or dynamic (query: province = TEH AND tag = PE AND not in maintenance). Preview count + list. Used as the "targets" input in every job form.

## 9.5 Alarm Center  (`/alarms`)
Split view: left = filters (device/province/level/age/interface/text + source Zabbix|SSH|both) with saved filters; right = table. Row action "Plan alarm clear…". Mismatch column highlights Zabbix-vs-SSH differences. "Fetch live from devices" button runs an SSH read-only job on the selected devices and streams results in place.
**Accept:** selecting alarms and pressing "Plan alarm clear" opens the Change planner (9.6) pre-filled.

## 9.6 Change planner & approval  (`/changes`, `/changes/:id`)  — the safety UX
```
Header: feature · requested by · risk badge · status stepper
        Plan → Pre-check → Approval → Apply → Verify
┌ Summary: N devices · M interfaces · risk counts · blast-radius banner (red if limits exceeded)
├ Table: device · interface · decision (SHUTDOWN/CLEAR/SKIP) · reason code · exact lines to send
├ Right drawer on row: pre-check evidence (command, output excerpt), diff, rollback lines
└ Footer: [Reject] [Approve…] (typed confirmation when high risk) · options: save config after apply (off), auto-rollback on verify fail (on)
```
After approval the page switches to the **RunTimeline** with live log drawer. Per-device failure shows "needs attention" with a one-click "Rollback this device".
**Accept:** approver ≠ requester rule visible and enforced; skipped items always show *why*; the exact CLI lines are visible before approval.

## 9.7 Jobs  (`/jobs`, `/jobs/:id`)
List: type, status, mode (dry-run/apply), user, targets, started, duration, summary. Detail: RunTimeline (top) + LogViewer (bottom, resizable split) + Results tab (typed table per feature) + Downloads (CSV/XLSX/JSON) + "Run again with same parameters". Cancel button (real cancellation, shows "Cancelling…" until tasks stop). Live updates via `useJobEvents`; refresh keeps everything (replay).
**Accept:** two tabs show identical live state; killing the server mid-job then restart → tasks show "interrupted by restart".

## 9.8 Reports  (`/reports/down-links`, `/reports/licenses`, `/reports/digest`)
Form (targets, province, age value/unit validated inline) → run → results table + analytics charts (from `compute_analytics` fields) + export. "Compare with previous run" toggle highlights new/recovered rows. Schedules created from the same form ("Run every day at 06:00").

## 9.9 Monitoring Hub  (`/monitoring`)
Fleet table (availability, CPU, mem, temp, active problems) ← Zabbix; interface explorer (pick device → interfaces with rate graphs, synced cursors); "Open in Grafana" deep links; integration status strip (Zabbix OK/degraded, Grafana OK/degraded, mapping coverage %).
**Accept:** with Zabbix unreachable, page shows cached data with "stale" label, never a blank screen.

## 9.10 Configs & Compliance  (`/configs`, `/compliance`)
Configs: device picker → snapshot timeline → DiffViewer (any two snapshots) → download. Compliance: matrix rules × provinces (% pass), click → failing devices table with remediation hint text.

## 9.11 Tools
- **Routing check** (`/tools/vrf-routing`): VRF + prefix → result table + path graph (React Flow).
- **PTP troubleshoot** (`/tools/ptp`): target → live traceback; topology graph with state colors; verdict text; download report.
- **ARP/MAC lookup** (`/tools/arp`): site/IP search, collector job control (start/stop with real cancel), searchable results.
- **Session extractor** (`/tools/sessions`): CSV upload → preview folder tree → download ZIP.
- **Command runner** (`/tools/runner`): choose allow-listed read-only command, targets, optional variables → results grouped by device, cross-device search/grep, export.
Each tool shares the same job UX (RunTimeline + LogViewer).

## 9.12 Admin  (`/admin/*`)
Users (create/disable/role/reset password), Permissions matrix (feature × user), Credential profiles (create/rotate/delete; secrets never displayed), Integrations (Zabbix/Grafana URL, test buttons, `telemetry-doctor` result table), Schedules (pause/resume/run-now), Notifications, Audit log (filter by user/action/device/date, export), System (version, DB size, worker status, read-only mode toggle with banner).
**Accept:** non-admin cannot see the rail items; direct URL access returns a 403 page; audit log shows every change made in this phase.

## 9.13 Cut-over
Feature parity checklist in `11_TESTING_ACCEPTANCE.md` §3 must be 100 % ticked. Then: make the new UI the default at `/`, serve the old page at `/legacy` for one release, then remove old `templates/` + `static/` + legacy adapters (Step 10.9).

## Global UI behaviors (apply to every screen)
- URL reflects state (filters, selected tab, time range) so links are shareable.
- Every table: loading skeleton, empty state, error state with retry.
- Keyboard: `g` then `d/a/j/c` jump to Devices/Alarms/Jobs/Changes; `/` focuses search; `?` shows shortcuts.
- Destructive or device-changing buttons are never the default focus.
- Maintenance banner when `READ_ONLY_MODE=true`: "Read-only mode: changes are disabled."
