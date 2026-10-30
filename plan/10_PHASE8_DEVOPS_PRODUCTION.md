# 10 — PHASE 8: DEVOPS & PRODUCTION

Goal: one-command, reproducible, secure, observable deployment that works in an isolated NOC network.
Resolves F-08, F-11, F-44, F-46. Branch `phase8`.

## Step 10.1 — Multi-stage Dockerfile (replace the current 12-line one)
- Stage 1 `node:20-slim`: `npm ci` + `npm run build` in `frontend/`.
- Stage 2 `python:3.11-slim`: install pinned `requirements.txt` (hash-pinned via `pip-compile --generate-hashes` or a lock file), copy `backend/` and `frontend/dist`.
- Run as **non-root** user (uid 10001); `WORKDIR /app`; data dir `/data` (volume); read-only root filesystem where possible (`tmpfs` for `/tmp`).
- Entrypoint `docker/entrypoint.sh`: wait for DB path writable → `alembic upgrade head` → first-run admin bootstrap (file 03 §1.2) → `exec gunicorn -c docker/gunicorn.conf.py "app:create_app()"`.
- gunicorn: `gthread`, `workers=1` (the job engine/scheduler live in-process; do NOT raise workers without moving the engine to a separate worker container), `threads=16`, `timeout=0` for SSE routes or dedicated `--worker-class gthread` with `keepalive`; graceful timeout 30 s; access log JSON.
- `HEALTHCHECK` → `/healthz`. `.dockerignore` from Step 1.1.
- **Offline build support:** document `make vendor` that downloads wheels (`pip download`) and `npm ci` cache into `vendor/` so the image can be built on an internet-connected machine and loaded (`docker save`/`load`) into the isolated network.
**Verify:** image < 400 MB; `docker run --read-only …` boots; `docker exec id` ≠ root; trivy/grype scan (if available) shows no critical vulns.

## Step 10.2 — docker-compose for production
Services: `webdash` (one container). Volumes: `webdash_data:/data`. Env file `config.env` (from `config.example.env`, extended with every setting in `config.py`, each with a comment). Resource limits (`cpus`, `mem_limit`), `restart: unless-stopped`, `stop_grace_period: 40s`, log rotation.
Optional second profile `proxy`: **Caddy or nginx** reverse proxy with TLS (internal CA/self-signed supported), HTTP→HTTPS redirect, HSTS, `proxy_buffering off` for `/api/v1/jobs/*/events` (SSE), request size limit 10 MB, gzip for static.
**Verify:** `COOKIE_SECURE=true` works behind the proxy; SSE streams live through it.

## Step 10.3 — Observability
- JSON logs to stdout (shipping is the site's job). Fields from Step 2.6.
- `/metrics` Prometheus text: `webdash_jobs_total{type,status}`, `webdash_task_duration_seconds` (histogram), `webdash_ssh_failures_total{reason}`, `webdash_changes_total{state}`, `webdash_telemetry_requests_total{provider,outcome}`, `webdash_telemetry_circuit_open{provider}`, `webdash_device_lock_waits_total`.
- Ship a ready Grafana dashboard JSON `docs/grafana/webdash-self.json` that the team can import into their existing Grafana (panels for the metrics above) and a Zabbix-friendly HTTP agent item list in `docs/zabbix/webdash-items.md` (since their stack is Zabbix-first).
- Alerts to define in docs (as suggestions): job failure ratio > 20 % in 1 h; telemetry circuit open > 5 min; no successful `config_backup` in 36 h; change stuck `awaiting_approval` > 24 h.

## Step 10.4 — Backups & restore
- Nightly **SQLite online backup** (`sqlite3 .backup` API) to `/data/backups/` with 14-day retention, integrity check (`PRAGMA integrity_check`) after each backup, encrypted with the vault key (or documented external encryption).
- `make restore BACKUP=…` documented and **tested in CI** (restore into temp dir, app boots, a known user can log in).
- The vault key is NOT inside backups; document key escrow procedure.

## Step 10.5 — Security hardening checklist (implement all)
- Dependency pinning + `pip-audit`/`npm audit` in CI (fail on high).
- Rate limit on `/login` (done in 1.4) and on expensive endpoints (job submit: 10/min/user).
- Security headers (Step 6.6). Cookie flags (Step 1.3).
- Secrets only via env/files; startup refuses `WEBDASH_ENV=production` with: default secret key, missing vault key, `DEBUG` on, `COOKIE_SECURE` off (unless `ALLOW_INSECURE_HTTP=true` explicit).
- Log scrubber: regex-mask anything resembling passwords/tokens/community strings in events and transcripts.
- SSH: pin host keys optionally (`device.ssh_hostkey_fingerprint`; mismatch → `HOSTKEY_CHANGED` error); document trade-off (default off for ops simplicity, visible warning in Admin → System).
- SBOM generation (`cyclonedx`) in CI artifacts.

## Step 10.6 — CI pipeline (GitHub Actions file `.github/workflows/ci.yml`, must also run locally via `make ci`)
Jobs: `lint` (ruff, mypy on `backend/app`), `test-backend` (pytest + coverage gate: parsers ≥ 90 %, jobs engine ≥ 85 %, overall ≥ 70 %), `test-frontend` (typecheck, lint, vitest, bundle budget), `e2e` (Playwright against compose with FakeDevice mode `WEBDASH_FAKE_DEVICES=true`), `build-image`, `audit`.
**Fake device mode:** an env switch that makes `DeviceSession` replay fixtures — lets UI e2e tests and demos run with zero real routers. It must be impossible to enable together with `WEBDASH_ENV=production`.

## Step 10.7 — Operations docs (`docs/`)
`INSTALL.md` (online + offline), `UPGRADE.md` (backup → pull → migrate → rollback), `RUNBOOK.md` (stuck job, locked device, Zabbix down, restore DB, rotate vault key, rotate Zabbix/Grafana tokens), `SECURITY.md`, `zabbix_setup.md`, `grafana_setup.md`, `DEVICE_COMMANDS.md` (generated from the command registry: every command, OS family, read-only flag, verified flag).

## Step 10.8 — Load & soak tests (with FakeDevice)
- 1 000 devices × alarm-plan job: finishes, memory flat (±10 %) over 1 h soak, SSE with 20 concurrent viewers OK.
- Kill -9 the container mid-job: restart recovers (tasks marked interrupted, locks released, no duplicate applies).
**Verify:** record results in `docs/PERF_RESULTS.md`.

## Step 10.9 — Remove legacy
Delete (after 11 §3 parity is 100 %): old `templates/`, `static/`, `users.json` reader, old route adapters (`/run-bulk`, `/run-manual`, `/stream/<sid>`, …), `legacy/` scripts. Update README. Tag release `v2.0.0`.
