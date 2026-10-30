# 08 — PHASE 6: FRONTEND FOUNDATION & DESIGN SYSTEM

Goal: replace the single `templates/index.html` UI with a fast, dense, keyboard-friendly NOC console.
Branch `phase6`. Do this AFTER Phase 2 APIs exist (`/api/v1`). Old UI keeps working until Step 9.12.
Resolves F-60, F-61.

## 1. Product framing (design brief — follow it, don't re-interpret)
- **Subject:** a network-operations console for Huawei routers. **Audience:** NOC engineers, often on a
  night shift, often on big monitors, sometimes a laptop. **Primary job:** see what is wrong, decide, run a
  safe change, and prove it worked.
- **Feel:** calm, precise, instrument-like. Dense information, zero decoration. Status color is the ONLY loud thing.
- **Memorable element (spend boldness here only):** the **Run Timeline** — a live swimlane where each device is a row
  and each step (connect → pre-check → plan → apply → verify) is a tick that fills in real time. Everything else stays quiet.
- **Anti-patterns to avoid (generic "AI dashboard" tells):** identical rounded cards for everything, gradient washes, glow,
  big-number-with-sparkline hero tiles as decoration, all-caps tracked eyebrow labels above every heading,
  emoji as icons, fade-slide-up entrance animation on every block, one shadow on everything.

## 2. Stack (final)
React 18 + TypeScript (strict) + Vite · Tailwind CSS with CSS variables as tokens · TanStack Query (server state) ·
TanStack Table + TanStack Virtual (tables/logs) · Zustand (small UI state) · React Router (data router, route-level code splitting) ·
Radix UI primitives (dialog, popover, tabs, tooltip, dropdown — accessible) · `uPlot` for time-series charts (tiny, fast) ·
`@xyflow/react` (React Flow) for topology/path graphs · `diff` library + own renderer for config diffs · `cmdk` for command palette ·
`react-i18next` for fa/en · `vitest` + Testing Library + Playwright.
**No** CDN, **no** remote fonts/icons. Icons: bundled `lucide-react` (tree-shaken). Build output → `frontend/dist` → copied into the Python image and served by Flask at `/` (SPA fallback to `index.html`, long-cache hashed assets, `no-cache` for `index.html`).

## 3. Design tokens (create `frontend/src/styles/tokens.css` — values below are the contract)
**Light ("Paper") / Dark ("Night") — semantic names, not raw colors, are used in components.**
| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--bg` | `#ECEFEA` | `#161B22` | app background |
| `--surface` | `#F7F8F5` | `#1D242D` | panels/tables |
| `--surface-2` | `#E2E6DF` | `#252E39` | headers, hover rows |
| `--ink` | `#1F2933` | `#E4E9EF` | primary text |
| `--ink-2` | `#52606D` | `#9AA7B5` | secondary text |
| `--line` | `#C9D0C6` | `#323D4A` | borders/dividers |
| `--signal` (primary action) | `#2F5BEA` | `#6C8DFF` | buttons, focus, selection |
| `--ok` | `#2E8B57` | `#4CC38A` | up / success |
| `--warn` | `#C98500` | `#E8B04A` | degraded / needs attention |
| `--fault` | `#D23A2B` | `#FF6B5B` | down / failed / destructive |
| `--info-muted` | `#6B7C93` | `#7C8DA3` | unknown / skipped |
Contrast: all text/background pairs ≥ WCAG AA (4.5:1). Status is never color-only: always icon or text label too.
- **Radius:** 3 px for controls, 0–2 px for table cells, 6 px for dialogs only (hierarchy, not one radius for all).
- **Elevation:** no resting shadows on panels (use `--line`); shadow only on floating layers (menus, dialogs, toasts).
- **Spacing:** 4 px base scale (4, 8, 12, 16, 24, 32). Table row heights: compact 28 px, comfortable 36 px (user setting).
- **Type:** UI = *IBM Plex Sans* (Latin) + *Vazirmatn* (Persian), both self-hosted `woff2` in `frontend/public/fonts` with `font-display: swap` and real fallback stack; data/CLI = *JetBrains Mono* (tabular numerals on). Scale: 12 / 13 / 14 (base) / 16 / 20 / 24. Max line length 80 ch in prose. Sentence case everywhere; no all-caps labels.
- **Motion:** 120 ms ease-out only for user-triggered things (open/close/expand). Live-run ticks animate by state change only. Respect `prefers-reduced-motion`.
- **Density modes** (compact/comfortable) and **theme** (light/dark/system) persisted per user (`localStorage`, key `wd.prefs`).

## 4. Layout concept (ASCII — all screens inherit it)
```
┌──────────┬───────────────────────────────────────────────────────────────┐
│ Rail     │ Top bar: breadcrumb · global search (Ctrl+K) · job tray · user │
│ (icons + ├───────────────────────────────────────────────────────────────┤
│ labels,  │ Page header: title · primary action (right)                   │
│ collaps- │ ───────────────────────────────────────────────────────────── │
│ ible)    │ Content: tables / split views / timelines — fills the height  │
│          │ (no page-level scroll; panels scroll internally)              │
└──────────┴───────────────────────────────────────────────────────────────┘
```
- Rail items (permission-gated): Overview · Devices · Alarms · Changes · Jobs · Reports · Monitoring · Configs · Tools · Admin.
- **Job tray** (top bar): shows running jobs with progress; click → job detail drawer. Visible from every page.
- Direction-aware: use CSS **logical properties** (`margin-inline-start`, `inset-inline-end`) so the whole UI flips for Persian (RTL). Numbers, IPs, interface names, CLI output stay LTR (`dir="ltr"` + `unicode-bidi: isolate`).

## 5. Build steps

### Step 6.1 — Scaffold
`frontend/` with Vite + TS strict, ESLint, Prettier, Tailwind, path alias `@/`. Scripts: `dev`, `build`, `typecheck`, `lint`, `test`.
Vite dev proxy `/api` → `http://localhost:5000`. **Verify:** `npm run build` outputs `dist/` < 250 KB gzip initial JS.

### Step 6.2 — API client + auth shell
`src/api/client.ts`: fetch wrapper — JSON only, sends `X-CSRF-Token` (from `GET /api/v1/me`), maps error format of file 02 §4 to a typed `ApiError`, handles 401 (redirect to login keeping return URL) and `PASSWORD_CHANGE_REQUIRED`. TanStack Query defaults: `staleTime` 15 s, retry 1 (never retry 4xx).
Login page, route guards by permission, logout, idle-timeout notice. **Verify:** Vitest tests with mocked fetch for 401/403/422 mapping.

### Step 6.3 — Tokens, theming, i18n
Implement tokens (§3), theme switch, density, fa/en + RTL switch (language stored per user). All strings via i18n keys (no hardcoded UI text). **Verify:** Playwright screenshot of a sample page in 4 combos (light/dark × LTR/RTL) — no overflow, no clipped text.

### Step 6.4 — Core components (each with a Storybook-less "kitchen sink" route `/_ui` for manual check + tests)
1. **DataTable** — virtualized rows (10 000 rows at 60 fps), column resize/reorder/hide, pinned first column, multi-sort, per-column filters, global quick filter, row selection (shift-range), sticky header, keyboard navigation (↑↓ Space Enter), **saved views** (named filter+column sets stored server-side `user_view` table), CSV/XLSX export of *current filtered view*, empty/loading/error states.
2. **LogViewer** — virtualized, monospaced, level colors + level icons, timestamps, device chip, search with next/prev, level/device filters, **follow tail toggle**, copy line/selection, download, handles 200 000 lines. Fed by the SSE hook.
3. **useJobEvents(jobId)** hook — SSE with `Last-Event-ID` replay, auto-reconnect with backoff, dedupe by event id, exposes `{events, status, progress}`.
4. **RunTimeline** (the memorable element) — rows = devices, columns = steps, cells = state glyph (queued/running/ok/skipped/failed) + duration on hover, click row → device log filter; handles 1 000 devices (virtualized rows). Sort by "needs attention first".
5. **DiffViewer** — side-by-side + unified, collapsible unchanged regions, line numbers, word-level highlight, jump to next change, copy hunk.
6. **StatusBadge / HealthDot** (icon + label + color), **Timestamp** (relative + exact on hover, 24 h, optional Jalali display), **Mono** (copyable IP/interface/serial chips).
7. **ConfirmDialog with typed confirmation** (for high-risk apply: user types the device count), **Drawer**, **Tabs**, **Toast** (aria-live), **CommandPalette** (Ctrl/Cmd+K: go to page, find device, run a recent job again), **TimeRangePicker** (15 m, 1 h, 6 h, 24 h, 7 d, custom).
8. **TimeSeriesChart** (uPlot wrapper: multi-series, hover crosshair, synced cursor across charts, step/line, units, gaps for missing data) and **TopologyGraph** (React Flow wrapper: auto layout via simple layered algorithm, node status colors, edge labels, fit-view, export PNG/SVG).
9. **GrafanaPanel** — iframe wrapper with load timeout → fallback card "Open in Grafana" (file 05 §3.4.3).
**Verify per component:** unit tests + one Playwright interaction test; axe-core accessibility check has zero serious/critical violations on `/_ui`.

### Step 6.5 — Performance & quality gates (CI-enforced)
- Initial JS ≤ 250 KB gzip; each route chunk ≤ 150 KB gzip; Lighthouse performance ≥ 90 on `/`.
- No layout shift on data load (reserve table height); no unvirtualized list > 200 rows anywhere.
- `typecheck`, `lint`, `test` must pass in CI; bundle-size check script fails the build when budgets are exceeded.

### Step 6.6 — Serve from Flask
Flask serves `frontend/dist`; SPA fallback for non-`/api` routes; correct cache headers; security headers: `Content-Security-Policy` (default-src 'self'; frame-src = configured `GRAFANA_URL` origin only; img-src 'self' data:; connect-src 'self'), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`.
**Verify:** no request to any external origin in the browser network tab (Playwright asserts this).

## 6. Copy & microcopy rules
- Buttons say what happens: "Plan changes", "Apply 12 changes", "Cancel job" — never "Submit/OK".
- The same action keeps the same name in button, toast, and log ("Apply" → "Applied").
- Errors say what failed and what to do: "Could not log in to PE-TEH-01 (authentication failed). Check the credential profile 'noc-ro'." No apologies, no vague "Something went wrong".
- Empty states invite the next action: "No jobs yet. Run a down-links report to see results here."
- Device/CLI-derived text is shown verbatim in mono, never translated.
