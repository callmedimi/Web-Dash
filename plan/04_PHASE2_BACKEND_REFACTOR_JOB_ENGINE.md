# 04 — PHASE 2: BACKEND REFACTOR + PERSISTENT JOB ENGINE

Goal: replace the 5 copy-pasted in-memory session stores with ONE persistent job engine,
split `app.py` into blueprints, keep behavior identical (golden tests first).
Resolves F-05, F-26, F-27, F-30, F-40…F-44. Branch `phase2`.

---
## Step 2.0 — Golden tests BEFORE refactor
**Goal:** freeze current behavior.
**Do:** create `backend/tests/` (or `tests/` for now). Build a **FakeDevice** test double that
replays recorded command→output pairs from `tests/fixtures/vrp/<scenario>/*.txt` and plugs into the
netmiko call sites via dependency injection (add a `connect(...)` factory parameter with default =
real netmiko; do not change behavior). Create fixtures by **sanitizing** outputs the team gives
you (replace IPs/names). Minimum scenarios: alarms with admin-down iface; alarms with noconf iface;
alarm text with sub-interface; empty output; `display license` / `display license verbose` (VRP5 and VRP8 samples).
**Verify:** `pytest` runs green on the unchanged code.
**Done-when:** ≥ 12 golden tests passing.

## Step 2.1 — Introduce package skeleton, config, DB
**Do:** create `backend/app/` per file 02 §2. `create_app()` factory, `config.py` (pydantic-settings; env prefix `WEBDASH_`), SQLAlchemy engine for SQLite with `PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`, Alembic initial migration with ALL tables from file 02 §3 (create even if unused yet).
`app.py` at repo root becomes a 5-line shim importing `create_app` (so `python app.py` and gunicorn both work).
**Don't:** move feature code yet.
**Verify:** `flask db upgrade` creates DB; app boots; `/healthz` 200.

## Step 2.2 — Job engine (the heart)
**Files:** `app/jobs/{engine.py,queue.py,worker.py,locks.py,events.py,cancel.py}`.
**Behavior spec (implement exactly):**
1. `submit(job_type, params, user, mode)` inserts `job` (status=queued) + one `job_task` per target device, returns `job_id`.
2. A worker pool (threads, size = `MAX_SSH_WORKERS`) pulls **tasks** (not jobs) from the DB with `SELECT … WHERE status='queued' ORDER BY created_at LIMIT 1` using an atomic `UPDATE … SET status='running' WHERE id=? AND status='queued'` claim. Fair scheduling: round-robin across jobs.
3. Before running a task the worker acquires the **device lock** (`locks.py`): unique row in `device_lock(device_id, owner_task_id, acquired_at, heartbeat_at)`. If locked → put task back to queued with `not_before = now+5s`. Locks older than 10 min without heartbeat are stale and reclaimed.
4. Task functions receive `ctx` with: `ctx.log(level, msg, data=None)` (writes `job_event` + pushes to SSE subscribers), `ctx.cancelled()` (checks `job.status=='cancelling'`), `ctx.device`, `ctx.creds` (decrypted just-in-time), `ctx.mode`.
5. Cancellation: `POST /jobs/{id}/cancel` sets status `cancelling`; queued tasks → `cancelled` immediately; running tasks stop at next `ctx.cancelled()` check; engine always disconnects the SSH session in a `finally`.
6. Job status roll-up: all succeeded → `succeeded`; mixture → `partial`; all failed → `failed`.
7. On app start: tasks left `running` → mark `failed` with error `interrupted by restart`; release their locks.
8. Retention: purge `job_event` older than `JOB_EVENT_RETENTION_DAYS` (default 30) daily; keep `job` + `summary` 1 year.
**Verify:** unit tests with fake task functions: concurrency cap respected; same device never runs 2 tasks at once; cancel mid-run; restart recovery.
**Done-when:** tests green; a stress test of 200 fake tasks over 20 fake devices finishes with max 20 parallel.

## Step 2.3 — Realtime events (SSE with replay) (F-42)
**Do:** `GET /api/v1/jobs/{id}/events` streams `job_event` rows as SSE. Supports `Last-Event-ID` (= `job_event.id`) and `?since=`. New events are delivered via an in-process broadcaster (one asyncio-free `queue.Queue` per subscriber, registered/unregistered in `try/finally`) — multiple tabs work. Heartbeat comment every 15 s. Closes with `event: done` when job is terminal AND all events sent.
**Verify:** open the stream twice, refresh mid-job → no lost lines, no duplicates.

## Step 2.4 — Ownership & access control on jobs (F-05, F-30)
**Do:** `GET /jobs`, `/jobs/{id}`, events, downloads: `operator` sees own jobs; `admin/god` see all. Job ids are UUID4 (full). Downloads (`csv`) are generated from DB rows each time (no mutation of stored data), always sorted deterministically.
**Verify:** user B requesting user A's job → 404 (not 403, avoid enumeration).

## Step 2.5 — Move features into blueprints (one per commit)
Order (smallest risk first): `auth/users` → `license_check` → `down_links report` → `vrf_routing` → `zabbix` → `arp` → `session_extractor` → `ptp` → `license_renewal` → `alarm_clear`.
For each: (1) move code into `app/features/<name>/` with a `run(ctx, params)` task function; (2) keep the OLD route path as a thin adapter that calls `engine.submit` and returns `{session_id: job_id, router_count}` so the current UI keeps working; (3) re-run golden tests; (4) delete the old in-memory store for that feature.
Collapse `_run_manual`/`_run_bulk` into one `alarm_clear` job (manual = targets given inline).
Move root scripts (`check-routing`, `auto_clear_noconf.py` CLI `main()`, etc.) to `legacy/` after parity.
**Done-when:** `grep -n "sessions: dict" -r backend` returns nothing; all golden tests pass; UI still works end-to-end.

## Step 2.6 — Structured logging + audit in DB
**Do:** JSON logging (`python-json-logger` or stdlib formatter) with fields `ts, level, logger, job_id, task_id, device, user`. Replace file audit from Step 1.4 by `audit_log` table (keep file as fallback). Add `/healthz`, `/readyz`, `/metrics` (job counts by status, task duration histogram, SSH failures by error class).

## Step 2.7 — User model → DB, roles
**Do:** migrate `users.json` into `user`/`permission` tables (one-time script, idempotent); roles become `god/admin/operator/viewer` where `viewer` = read-only features only. Keep `users.json` read-only for one release as backup, then delete in 10.9.
**Verify:** existing users can log in after migration; permissions identical.

## Step 2.8 — Credential vault (F-06)
**Do:** `credential` table; secrets encrypted with Fernet using key from `WEBDASH_VAULT_KEY` (file or env; refuse to start in prod if missing). API: create/list (never return secrets)/rotate/delete; credentials can be attached to a `device` or chosen per job (`credential_id`). Old UI endpoints that accept `username/password` in the body keep working for now but log a deprecation event; new API forbids passwords in job params.
**Verify:** DB dump contains no plaintext secrets; job param JSON never contains a password (test with grep).
