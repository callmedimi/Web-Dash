# 02 — TARGET ARCHITECTURE

Design principle: **boring, robust, air-gap friendly.** Few moving parts, all in one container
(plus optional second container for the worker). No Redis/Kafka required.

## 1. Stack decisions (final — do not change)
| Layer | Choice | Why |
|-------|--------|-----|
| Web/API | **Flask 3 + blueprints**, served by **gunicorn** (gthread) | Keep existing code; minimal migration risk |
| DB | **SQLite (WAL mode)** via **SQLAlchemy 2 + Alembic** | Zero ops, persistent jobs/history/audit; upgrade path to PostgreSQL by changing one URL |
| Jobs | **Own job engine**: DB-backed queue + worker threads/processes inside the app (`jobs/`) | No Redis needed; survives restart |
| Device SSH | **netmiko** (keep) behind our own `devices/` abstraction | Existing know-how; abstraction allows later swap to scrapli/asyncssh |
| Parsing | **TextFSM templates** in repo + golden fixtures | Replace fragile regex |
| Telemetry | **Zabbix JSON-RPC API (primary) + Grafana HTTP API (secondary)** behind a `TelemetryProvider` interface; `requests` + TTL cache | Owner cannot run SNMP directly; reuse existing self-hosted monitoring; no polling load on routers |
| Secrets | **Fernet-encrypted credential vault** in DB, key from env/file | No plaintext creds, no browser-supplied creds |
| Frontend | **React 18 + TypeScript + Vite + Tailwind + TanStack Query/Table + Zustand** built to static files served by Flask | Fast, rich tables/graphs/diff viewer; build happens in Docker multi-stage, runtime has no node |
| Realtime | **SSE** with replay (`Last-Event-ID`) backed by DB log table | Works behind proxies, simple |
| Tests | pytest + fixtures; Vitest + Playwright (smoke) | |

## 2. Target repository layout
```
Web-Dash/
  plan/                      # this folder (keep)
  backend/
    app/
      __init__.py            # create_app()
      config.py              # env-based settings (pydantic-settings)
      extensions.py          # db, migrate
      security/              # auth, rbac, csrf, rate_limit, vault
      api/                   # blueprints: auth, users, devices, jobs, reports, license,
      |                      #   routing, ptp, arp, telemetry, sessions_export, backups, audit
      models/                # SQLAlchemy models
      jobs/                  # engine, queue, worker, locks, events (SSE)
      devices/               # connection pool, drivers (vrp5, vrp8), parsers, commands registry
      telemetry/             # zabbix + grafana providers, mapping, cache
      features/              # one package per feature (alarm_clear, down_links, vrf_check, license, ptp, arp, ...)
      services/              # zabbix etc. (moved from /services)
      templates_textfsm/     # *.textfsm
    migrations/              # alembic
    tests/
      fixtures/vrp/          # recorded device outputs (see file 05)
  frontend/                  # React app (see files 08, 09)
  legacy/                    # old root scripts moved here in Phase 2 (kept until parity proven)
  docker/                    # Dockerfile (multi-stage), entrypoint.sh, gunicorn.conf.py
  docker-compose.yml
  config.example.env
  Makefile                   # make test / lint / run / build
```

## 3. Data model (tables — columns are required unless "opt")
- `user(id, username unique ci, password_hash, role[god|admin|operator|viewer], display_name, is_active, token_version, failed_logins, locked_until opt, created_at)`
- `permission(user_id, feature, granted bool)`  — replaces JSON blob
- `device(id, name unique, mgmt_ip, vendor='huawei', os_family[vrp5|vrp8], model opt, esn opt, site opt, province opt, tags json, zabbix_hostid opt, grafana_vars json opt, credential_id opt, enabled, created_at)`
- `credential(id, name, kind[ssh_password|ssh_key|zabbix_token|grafana_token|webhook_secret], secret_encrypted, meta json)`
- `job(id uuid, type, status[queued|running|succeeded|failed|cancelled|partial], mode[dry_run|apply], created_by, created_at, started_at, finished_at, params json, summary json, parent_job_id opt)`
- `job_task(id, job_id, device_id, status, started_at, finished_at, result json, error opt)`
- `job_event(id bigint autoinc, job_id, task_id opt, ts, level, message, data json opt)`   ← SSE replay source
- `config_snapshot(id, device_id, taken_at, kind[running|saved], sha256, content_encrypted_or_text, job_id opt)`
- `change_request(id, job_id, device_id, plan json, diff text, status[proposed|approved|applied|verified|rolled_back|rejected], approver_id opt, ...)`
- `event(id, ts, source[zabbix|webdash|ssh], device_id opt, severity, title, data json)` (webhook/problem intake; short retention)
- (no `metric_sample` table: time series are fetched live from Zabbix/Grafana, cached in memory only)
- `audit_log(id, ts, user_id, ip, action, target, detail json)`  append-only
- `schedule(id, job_type, params json, cron, enabled, last_run_at)`

## 4. API conventions (all new endpoints)
- Prefix `/api/v1`. JSON only. Content-Type **must** be `application/json` (reject others → 415).
- Auth: session cookie (HttpOnly, SameSite=Lax, Secure when behind TLS) + CSRF header `X-CSRF-Token`.
- Errors: `{ "error": { "code": "VALIDATION_ERROR", "message": "...", "fields": {..} } }` with proper HTTP status. Never 500 for bad input.
- Validation: pydantic models for every request body.
- Lists: `?page=&page_size=&sort=&q=`; response `{items:[], total:int}`.
- Long operations: `POST /api/v1/jobs` → `202 {job_id}`; progress via `GET /api/v1/jobs/{id}/events` (SSE) and `GET /api/v1/jobs/{id}`.
- Every mutating call writes `audit_log`.
- Old endpoints (`/run-bulk`, …) stay as thin adapters until the new UI is complete, then removed in Step 10.9.

## 5. Concurrency & safety rules (engine-level, enforced centrally)
1. Global SSH concurrency cap (env `MAX_SSH_WORKERS`, default 20) shared by ALL jobs.
2. **Per-device mutex** (DB row lock or in-process keyed lock + `device_lock` table) — one config session per device.
3. Per-job cancellation token checked between devices AND between commands.
4. Every job has `mode=dry_run` first for any feature that changes a device (file 06).
5. Device credentials never leave the server; UI picks a credential profile by id.

## 6. Observability
JSON logs (one line per event) with `job_id`, `device`, `user`; `/healthz` (liveness), `/readyz`
(DB ok + worker alive); Prometheus text endpoint `/metrics` (job counts, durations, ssh failures)
so the team's Zabbix/Prometheus can scrape it.
