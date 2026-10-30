# 06 — PHASE 4: SAFE CHANGE PIPELINE

Goal: every action that modifies a router follows **Plan → Pre-check → Approve → Apply → Verify → (Rollback)**.
This is the single biggest quality gap vs. enterprise tools. Resolves F-20, F-22, F-23, F-24. Branch `phase4`.

## Pipeline contract (implement once in `app/jobs/change.py`, reuse everywhere)
```
state machine per device:
  planned → prechecked → awaiting_approval → applying → verifying → verified
                                   └→ rejected                └→ rolled_back / failed_needs_attention
```
1. **Plan (dry-run)**: feature computes the exact list of config lines per device + human-readable reason. NO config command is sent. Output stored in `change_request.plan` and a unified text `diff`.
2. **Pre-check**: read-only commands prove assumptions (device reachable, os_family known, interface exists, state as expected, no pending uncommitted config, no other user in config mode if detectable). Any failed pre-check → device excluded with reason.
3. **Snapshot**: take running-config snapshot (`config_snapshot`, kind=running) before apply. Store hash + content.
4. **Approve**: dry-run results are shown in UI. Policy per feature (`settings`): `auto_approve_if_risk<=low` or `require_second_person` (approver ≠ requester) or `require_admin`. Default for any shutdown/config: **requires explicit approval click** and a typed confirmation (e.g. type device count).
5. **Apply**: per device, with device lock, small batches (`CHANGE_BATCH_SIZE`, default 5 devices at a time, stop-on-failure-rate `>20%`), delay between batches. Always leave the device in user view (`return`) in `finally`; if a view cannot be restored → mark `failed_needs_attention`, flag device in UI.
6. **Verify**: re-run the read-only checks that prove the intended state (e.g. `Administratively DOWN`), compare with expectation. Fail ⇒ trigger rollback if `auto_rollback=true`.
7. **Rollback**: re-apply inverse lines computed at plan time (e.g. `undo shutdown`) or restore from snapshot using the VRP8 commit-id mechanism where `verified:true` in the registry. Rollback result is its own recorded event.
8. **Persistence policy**: `save` of the config is a **separate, explicit option** (`save_after_apply`, default false) so a reboot can undo a bad change; UI shows "unsaved changes" badge per device.
9. Everything logged to `job_event` and `audit_log` with who approved what.

## Risk model
| Risk | Examples | Default policy |
|------|----------|----------------|
| low | read-only, clear alarms on already admin-down interfaces | auto-approve |
| medium | `shutdown` of a verified noconf interface | admin approval |
| high | anything touching routing, BGP, MPLS, VRF, trunk members, uplinks, interfaces with description/IP/service | blocked in this tool unless `ALLOW_HIGH_RISK=true` AND god approval |

---
## Step 4.1 — Change engine skeleton
Implement the state machine, tables `change_request`, API:
- `POST /api/v1/changes/plan` (feature + params → job in dry_run → returns change_request ids)
- `GET /api/v1/changes/{id}` (plan, diff, precheck results, status)
- `POST /api/v1/changes/{id}/approve|reject`  (CSRF + RBAC + audit)
- `POST /api/v1/changes/{id}/apply`, `/rollback`
**Verify:** unit tests with a fake feature: illegal transitions raise; approver rule enforced; double-apply is idempotent (second call 409).

## Step 4.2 — Re-implement **Alarm Clear + Noconf Shutdown** (the flagship) on the pipeline
Replaces `process_one` logic from `auto_clear_noconf.py` (keep the old function until parity tests pass, then move to `legacy/`).
**Decision table (strict — implement literally):**
| Interface state | Config check result | Action |
|-----------------|--------------------|--------|
| admin DOWN | any | `clear alarms` only (risk low) |
| not admin DOWN | `error` set or `EMPTY_OUTPUT` | **SKIP** (reason `CONFIG_UNREADABLE`) — never shutdown (F-20) |
| not admin DOWN | config only `{dcn, undo dcn, shutdown, undo shutdown}` AND interface is not a trunk member AND not a sub-interface parent AND has no description AND operational state is down for > `NOCONF_MIN_DOWN_MINUTES` (default 60; use `display interface` last-change info, else skip) | plan `shutdown` (risk medium) then clear alarms after verify |
| anything else | | SKIP (reason `HAS_CONFIG_OR_UP`) |
Additional rules:
- Interface extraction uses Step 3.3 grammar; `AMBIGUOUS`/`None` ⇒ skip with reason.
- Sub-interface alarm ⇒ operate on the **sub-interface only**; never the parent (F-21).
- Clearing: success **only** when device output explicitly indicates success (store the matched pattern in the event). Empty/"not found" ⇒ status `NOT_PRESENT` (separate from `CLEARED`), never counted as cleared (F-23).
- Enter alarm view with check; if unavailable ⇒ task `failed` with `ALARM_VIEW_UNAVAILABLE` and **no** clear commands sent (F-24).
- Report CSV columns: `ne_name, interface, sequence, alarm_description, decision, reason_code, action, status, verified, timestamp, job_id, approved_by`.
**Verify:** golden tests: empty config output ⇒ SKIP; sub-interface; ambiguous alarm; admin-down; noconf+shutdown+verify; verify-fail ⇒ rollback `undo shutdown` planned & executed.

## Step 4.3 — Config backup & diff service
- Job `config_backup`: `display current-configuration` (VRP) per device (read-only), normalized (strip timestamps/`---- More ----`), SHA-256, stored; skip storing if hash unchanged (but update `last_checked`).
- Diff view API: `GET /api/v1/devices/{id}/configs/diff?from=&to=` → unified diff + structured hunks.
- Schedulable (nightly) via Step 5.x scheduler. Retention: last 30 snapshots + 1/month for 12 months.
- Encrypt snapshot content at rest (same Fernet key) because configs contain secrets (SNMP communities, hashed passwords).
**Verify:** two fixture configs ⇒ expected diff; unchanged ⇒ no new row.

## Step 4.4 — License renewal on the pipeline
Port `license_renewal_logic.py`: dry-run shows which license file will be loaded and the current state; apply requires approval; verify re-reads `display license` and compares expiry. (Read the existing code first and keep its confirmation-event behavior: `pending_confirmations` becomes an approval step.)

## Step 4.5 — Compliance checks (read-only "policy as data")
YAML rules in `DATA_DIR/compliance/*.yml` (e.g. "SSH only, no telnet", "NTP servers present", "SNMP v3 only" (config rule on the router; the app itself does not use SNMP), "no interface UP without description"). Engine evaluates rules against the latest config snapshot per device → pass/fail table + remediation hint (never auto-remediate in this phase).
**Verify:** rules unit-tested with fixture configs.

## Step 4.6 — Blast-radius guard
Before any apply: if the plan touches > `MAX_DEVICES_PER_CHANGE` (default 50) or > `MAX_INTERFACES_PER_DEVICE` (default 20) → require god approval + typed confirmation. Show in UI as a red banner with counts.
