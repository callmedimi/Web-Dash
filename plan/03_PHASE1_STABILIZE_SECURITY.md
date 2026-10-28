# 03 — PHASE 1: STABILIZE & SECURITY (no new features)

Goal: close critical holes in the CURRENT code base with the smallest possible diffs,
before any refactor. Work on a branch `phase1`. Resolves F-01…F-12 (except where noted).

---
## Step 1.0 — Audit unread files
**Goal:** complete the audit.
**Do:** Read every file listed in `00_START_HERE.md` §3 plus `templates/index.html`, all of `static/`,
all of `services/`, the remaining part of `app.py` (line ~1000 to end), `requirements.txt`,
`docker-compose.yml`, `.gitignore`, `config.example.*`.
For each, look for: hardcoded secrets/IPs, `shell=True`/`os.system`, string-built device commands
from user input (command injection into the router CLI), `eval/exec`, SQL string building, `debug=True`,
`verify=False`, files written to world-readable paths, credentials logged, unbounded loops.
**Output:** append rows `F-9x` to `01_AUDIT_FINDINGS.md` ("Agent additions"), same table format.
Also write `plan/NOTES_FROM_AGENT.md` with a 15-line summary of how the frontend is structured
(how it calls the API, how it renders logs, any framework used).
**Verify:** the file lists at least: every user-controlled value that is concatenated into a device
command (e.g. interface names, province, IPs, router names) — these become **input-validation** items in 1.6.
**Done-when:** both files exist and are committed.

## Step 1.1 — Secrets & state out of the image
**Goal (F-08):** `users.json`, `.secret_key`, uploads, and later the DB live in one data dir.
**Files:** `app.py`, `auth.py`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, new `.dockerignore`.
**Do:**
- Introduce env var `DATA_DIR` (default `./data`). `USERS_FILE`, secret key file, upload dir are placed under it.
- `.gitignore` and `.dockerignore` must exclude: `data/`, `users.json`, `.secret_key`, `*.env` (keep `config.example.env`), `__pycache__`, `.git`.
- compose: mount a named volume to `/data`, set `DATA_DIR=/data`.
- Secret key precedence: env `FLASK_SECRET_KEY` → file in `DATA_DIR` (created with mode 0600) → generate. Never write it inside the source tree.
**Don't:** change any route.
**Verify:** `docker compose up`, create a user, `docker compose down && up` → user still exists. `git status` shows no secrets.
**Done-when:** data survives rebuild; image contains no `users.json`/`.secret_key` (`docker run --rm image ls -a /app`).

## Step 1.2 — Kill the default `god/god` account (F-01)
**Do:**
- Remove the auto-created `Dimi/god` user.
- On startup, if there are zero users: read `INITIAL_ADMIN_USER` and `INITIAL_ADMIN_PASSWORD` from env; if missing, generate a random 20-char password, create user `admin` (role god), and print it **once** to stdout with a clear banner; set flag `must_change_password=true`.
- Enforce password policy on create/update: min 12 chars, not equal to username; reject known weak list (`god`, `admin`, `password`, `123456…`, small list in code).
- Add endpoint behavior: when `must_change_password` is true, every API except `/me`, `/logout`, and password-change returns 403 with code `PASSWORD_CHANGE_REQUIRED`.
**Verify:** fresh data dir → app prints credentials once; login with `god/god` fails; weak password rejected.
**Done-when:** unit tests for policy + first-run bootstrap pass.

## Step 1.3 — Session & CSRF hardening (F-02, F-03)
**Do:**
- Flask config: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE` from env `COOKIE_SECURE` (default False for http labs, True in prod docs), `PERMANENT_SESSION_LIFETIME=8h` (env), mark sessions permanent at login; idle timeout 30 min (store `last_seen`).
- At login: `session.clear()` first (fixation), then store only `{username, token_version}`.
- Every request (`before_request`) re-loads the user from `users.json`: if missing/disabled/token_version changed → 401. Role & permissions are read fresh each request (small cache ≤5 s allowed).
- On password change / role change / permission change / delete → bump `token_version`.
- CSRF: issue a random token in session; `GET /me` returns it; every POST/PUT/DELETE requires header `X-CSRF-Token` equal to it (constant-time compare). Exempt only `/login`.
- Replace all `request.get_json(force=True)` by a helper that **requires** `Content-Type: application/json` (415 otherwise) and returns 400 on malformed JSON.
- Frontend (current `index.html`/static JS): make the shared fetch wrapper send the CSRF header (find it in Step 1.0 notes).
**Verify:** (a) `curl -X POST -H 'Content-Type: text/plain' --data '{}' /admin/users` → 415/403. (b) POST without CSRF header → 403. (c) delete a user in another browser → their next request is 401.
**Done-when:** pytest covers a, b, c.

## Step 1.4 — Login throttling + audit (F-04)
**Do:** in-memory (later DB) counter per `(username, ip)`: 5 failures → 15-min lock, response always generic `Invalid credentials`; add constant-time-ish behavior for unknown users (hash a dummy). Add append-only `audit.log` (JSON lines in `DATA_DIR`) for: login ok/fail, logout, user create/update/delete, permission change, every job start (user, feature, device list size, **never** passwords).
**Verify:** 6th bad login returns 429; audit file has entries; grep shows no password strings.

## Step 1.5 — Validate user management input (F-07)
**Do:** `admin_update_user`: whitelist keys `{role, display_name, password, is_active}`; role ∈ `{god, admin, user}` (new roles come in Phase 2); ignore everything else; permissions payload must be `{feature_name: bool}` with feature in `DEFAULT_FEATURES`. `update_user` must not mutate the caller's dict. Cannot demote/disable the last `god`.
**Verify:** tests for each rejection.

## Step 1.6 — Input validation & limits (F-09, F-10)
**Do:**
- `MAX_CONTENT_LENGTH` = 10 MB (env).
- Add `pydantic` models (or manual validators) for every JSON route: routers list max 2000 items; `host`/`ip` must parse with `ipaddress` or match hostname regex; `name` ≤ 64 chars `[A-Za-z0-9._-]`; `age_value` int 1..3650; `age_unit` ∈ {hours, days}; `province` `[A-Z]{2,6}`.
- Every value that is later inserted into a device command (interface names, VRF names, IPs, province) must match a strict regex BEFORE use. Reject values containing whitespace, `;`, `|`, `&`, `$`, backticks, newlines.
- Convert all uncaught `ValueError/KeyError` into `400` with the error format of file 02 §4.
**Verify:** fuzz tests: payload with `"age_value":"abc"` → 400; interface `"GE0/0/1\nundo ..."` → 400.

## Step 1.7 — Move hardcoded infra constants to config (F-12)
**Do:** `HARDCODED_ROUTER_NAME/IP/RR_IP` and any other site constants found in 1.0 → `config.ini`/env (`config.example.*` already exist: extend them). Code reads from a single `settings` module; startup fails with a clear message when a required value is missing.
**Verify:** grep for dotted IPs in `*.py` returns nothing except tests.

## Step 1.8 — Safety net: kill-switch & read-only mode
**Do:** env `READ_ONLY_MODE=true` makes every route that sends configuration commands (alarm clear + shutdown, license renewal, anything using `system-view`) return 403 `READ_ONLY`. Admin UI shows a banner. Default false.
**Verify:** with flag on, `/run-bulk` and `/run-manual` refuse; reports still work.

## Step 1.9 — Phase 1 regression pass
Run the manual checklist in `11_TESTING_ACCEPTANCE.md` §2 (smoke) and tick it in `plan/NOTES_FROM_AGENT.md`.
Merge `phase1` → `main` only when green.
