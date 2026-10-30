# 00 — START HERE (read fully before touching any file)

You are the IMPLEMENTER agent. A senior architect wrote this plan. Your job is to execute it
exactly, step by step. Do not redesign. Do not skip steps. Do not "improve" beyond the step.

## 0. Project in one paragraph
`Web-Dash` (repo: github.com/callmedimi/Web-Dash) is a Flask web app used by a NOC team to run
SSH automation against **Huawei VRP routers** (NE/CX/ATN/CE families) through `netmiko`:
alarm clearing + shutting "noconf" interfaces, down-link reporting, VRF routing checks,
license check/renewal, Zabbix lookups, PTP (telecom sync) troubleshooting, ARP/MAC lookups,
SecureCRT session extraction, user/permission management. UI = one `templates/index.html`
+ `static/`. State = in-memory Python dicts. Auth = `users.json`.

Goal: turn it into a **production-grade, Huawei-first network automation platform**
(safe by default, observable, fast UI) that can compete with tools like Oxidized, NetBox+Ansible/AWX,
and Itential-style products — for Huawei estates.

## 1. File map of this plan (do in this order)
| # | File | What it delivers |
|---|------|------------------|
| 01 | 01_AUDIT_FINDINGS.md | Every bug/risk found, with ID (F-xx). Later files reference these IDs |
| 02 | 02_TARGET_ARCHITECTURE.md | Final folder layout, modules, data model, API rules |
| 03 | 03_PHASE1_STABILIZE_SECURITY.md | Critical fixes WITHOUT changing features |
| 04 | 04_PHASE2_BACKEND_REFACTOR_JOB_ENGINE.md | Blueprints + persistent job engine |
| 05 | 05_PHASE3_DEVICE_LAYER_SSH_TELEMETRY.md | SSH layer, parsers, Zabbix/Grafana telemetry (no direct SNMP) |
| 06 | 06_PHASE4_SAFE_CHANGE_PIPELINE.md | Dry-run → approve → apply → verify → rollback |
| 07 | 07_PHASE5_AUTOMATION_CATALOG.md | Feature list (what the tool can do) |
| 08 | 08_PHASE6_UI_DESIGN_SYSTEM.md | Frontend stack, tokens, components |
| 09 | 09_PHASE7_UI_SCREENS.md | Every screen, layout, behavior |
| 10 | 10_PHASE8_DEVOPS_PRODUCTION.md | Docker, gunicorn, CI, backups, observability |
| 11 | 11_TESTING_ACCEPTANCE.md | Tests + final acceptance checklist |

**Owner constraint:** the app cannot do SNMP directly. Monitoring data = self-hosted Zabbix + Grafana APIs. SSH remains the only channel that changes or verifies device state.

## 2. Iron rules (violating any = task failed)
1. **One step at a time.** Each step has `Goal / Files / Do / Don't / Verify / Done-when`.
   Finish and VERIFY a step before starting the next. If Verify fails, fix it; never move on.
2. **Never run commands against real network devices.** All device code must be testable with
   recorded outputs (fixtures) or a fake device. No real IPs/passwords in code, tests, or logs.
3. **Never remove an existing feature** unless a step says so. Refactors keep behavior
   (use the golden tests from file 11).
4. **No secrets in git.** No default passwords. No hardcoded IPs/router names (they go to config).
5. **No network at runtime.** The app may be deployed in an air-gapped NOC. No CDN links, no Google
   Fonts, no external APIs. All JS/CSS/fonts are bundled locally.
6. **Small commits.** One commit per step, message: `step <id>: <title>`.
7. **If something in the repo differs from this plan** (file missing, function renamed), STOP,
   write the difference into `plan/NOTES_FROM_AGENT.md`, and continue with the closest safe
   interpretation. Do not guess silently.
8. **Do not invent device commands.** Use only commands already in the repo or listed in this plan.
   Huawei VRP5 vs VRP8 differ — see file 05 section "Platform differences".
9. **Every new function gets a docstring and a unit test** (except pure UI markup).
10. Keep Python 3.11, type hints everywhere in new code.

## 3. What the architect did NOT see (you must audit in Step 1.0)
The architect could read: `app.py` (first ~1000 lines), `auth.py`, `auto_clear_noconf.py`,
`license_check.py`, `Dockerfile`, repo root listing. NOT readable: `templates/`, `static/`,
`services/`, the rest of `app.py`, `reporting_logic.py`, `check_vrf_routing.py`,
`site_arp_service.py`, `ptp_troubleshoot_service.py`, `session_extractor_service.py`,
`license_renewal_logic.py`, `requirements.txt`, compose file. Step 1.0 makes you audit them
and append findings to `01_AUDIT_FINDINGS.md` under "Agent additions".

## 4. Definition of done (whole project)
See file 11 section "Final acceptance". Nothing is done until that checklist is all green.

## 5. Report format after each step
Reply with exactly: `STEP <id> DONE | files changed: ... | verify: <what you ran> -> <result>`.
If blocked: `STEP <id> BLOCKED | reason: ... | needs: ...`.
