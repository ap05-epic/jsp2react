---
name: legacy-crawl-capture
description: Parse the JSP source into a source-model, discover every view in a legacy JSP/Struts web app (static routes AND AJAX-loaded views, reached from the start), and capture each view as comparable evidence (screenshot + normalized DOM model + a11y + the REAL backend responses via HAR) with error-page quarantine. Use when converting a legacy JSP/Java/Struts UI to React and you need the source-driven, source-of-truth evidence the modernize-flow / jsp2react driver agent builds from and verifies against. Reuses the pod's webapp-snapshot (login/screenshots) and webapp-testing (Playwright/server) skills; adds JSP source extraction, AJAX view discovery, normalized capture, and real-response recording those skills do not provide.
---

# legacy-crawl-capture

Source-of-truth capture for the **jsp2react** system. fig2code extracts a static Figma design; this
skill extracts a **live, running legacy screen** — and the original JSP/Struts source behind it.

It is **source-driven**: the driver agent builds from parsed JSP source, not from a screenshot.
1. **Parse** each JSP into a `source-model.json` (loops/forms/labels/AJAX endpoints) — the BUILD INPUT
   (`extract_jsp.py`; see `references/jsp-source-extraction.md`).
2. **Discover** every view — static routes (`crawl_screens.py`) AND AJAX-loaded views reached from the
   start (`crawl_ajax.py` → `viewgraph.json`; see `references/ajax-crawl-and-viewgraph.md`).
3. **Capture** each view into a *normalized model* diffable against the React render (SAME script both
   sides) — with semantic readiness and **error-page quarantine**.
4. **Record the REAL backend responses** (`capture_screen.py --record-har`) and turn them into replay
   handlers (`capture_fixtures.py --har`) — real data, no hand-authored fakes.

> Always run a script with `--help` (and `--self-check` where offered) before first use — the CLI is
> the contract. These are black-box tools; do not read the source unless customizing.

## Prerequisites (reused pod skills — do not reinvent)

- **Login** → produce `auth_state.json` once via `webapp-snapshot/scripts/save_auth_state.py`
  (or creds-form / env-bypass / token-query per that skill's `SSO_AUTH_GUIDE.md`). All capture
  commands reuse it with `--auth-state auth_state.json`.
- **Playwright** is available because `webapp-testing` uses it. If a launch fails, see webapp-testing.
- **Two capture tools, different jobs — keep them separate:**
  `snapshot_single.py` (webapp-snapshot) = a **quick visual check** while debugging.
  **`capture_screen.py` (this skill) = the authoritative parity/evidence capture** — it enforces the
  readiness contract and writes the `usable` sidecar. Only its output is admissible as parity evidence.

## Scripts

### init_project.py — bootstrap `project.json` (the agent owns the config, not the human)
```bash
python scripts/init_project.py --url <legacy login URL> --webapp-dir <webapp> --source-dir <java/resources root> \
  --out work/project.json          # --self-check for a no-file sanity run
```
Derives `contextRoot`/`legacyBaseUrl` (from the URL), `loginAction`+`loginFields` (from the login JSP),
`families`+`pathConventions` (from the jsp/ subdirs), and `db.sqlmapDir` (from CALLABLE sqlmaps). Anything it
can't derive is left blank under `_todo` for the agent to complete. Run this FIRST in analysis mode, then finish
the `_todo` items. Every other script reads the result via `--project`.

### extract_jsp.py — parse a JSP into `source-model.json` (the BUILD INPUT)
```bash
python scripts/extract_jsp.py --jsp <webapp>/jsp/<flow>.jsp --webapp-dir <webapp> \
  --out <evidence>/<id_state>/source-model.json        # --self-check for a no-file sanity run
```
Pragmatic regex parser (stdlib only). Extracts taglibs, includes/Tiles, JSTL loops/conditionals,
`<html:*>` form fields, AJAX endpoints (JSP + referenced `*.js`), and message keys. The builder builds
the React structure FROM this; the screenshot only verifies. See `references/jsp-source-extraction.md`.

### crawl_ajax.py — discover AJAX views from the START → `viewgraph.json`
```bash
python scripts/crawl_ajax.py --start-url <post-login summary> --auth-state auth_state.json \
  --merge static-viewgraph.json --out viewgraph.json --max-states 40 --max-depth 3
```
Stateful Playwright crawl: clicks/hovers every interactive element from the start, follows AJAX, and
records each view with its **full from-start click-path** + triggered endpoint. Solves "one link = 30
views" and enforces "never open a deep link directly." Reconciles static + (optional Crawljax) states.
See `references/ajax-crawl-and-viewgraph.md`.

### crawl_screens.py — enumerate every screen (deterministic-first)
```bash
# Authoritative inventory from source (no browser): actions + JSPs + links, reconciled by family.
python scripts/crawl_screens.py \
  --struts-config <…>/WEB-INF/struts-config.xml \
  --webapp-dir   <…>/src/main/webapp \
  --out screens.json

# Also emit a viewgraph of the static routes to reconcile with the AJAX crawl (crawl_ajax.py --merge):
python scripts/crawl_screens.py --struts-config <…> --webapp-dir <…> \
  --out screens.json --emit-viewgraph static-viewgraph.json
```
Vendor/build dirs (`pdfjs`, `dojo`, `jquery*`, `lib`, `locale`, `node_modules`, `coverage`,
`target`, `dist`, `build`) are pruned automatically. `screens.json.reconciliation` is the
"did we miss a screen?" gate — every screen JSP/action must become a status.md row or an explicit
unmatched entry in spec.md §4.

### capture_screen.py — capture ONE state as comparable evidence (legacy OR react)
This is the **authoritative parity capture** (not a quick screenshot — see the snapshot note above).
It enforces *semantic readiness* so the bundle reflects a **usable** screen, not just a rendered one.
```bash
# Session-sensitive / AJAX legacy screen (recommended): FRESH from-start login, no stale cookie:
python scripts/capture_screen.py --profile profiles/f010_default.json --project work/project.json \
  --out-dir work/evidence/f010_default --name legacy --login --creds login.env --record-har

# Quick auth probe — verify login works in ISOLATION from capture (prints post-login title; exit 0/2):
python scripts/capture_screen.py --check-login --project work/project.json --creds login.env

# Or fully on the CLI:
python scripts/capture_screen.py --url <legacy-screen-url> --project work/project.json --login --creds login.env \
  --out-dir work/screenshots --name f010_default \
  --viewport 1920x1080 --wait-for "#pmenu" \
  --must-contain "<a label that proves real data loaded>" \
  --wait-for-gone ".loadingMask" --wait-ms 8000
```
Outputs `f010_default.{png,dom.html,model.json,a11y.json,network.json}` **plus a
`f010_default.capture.json` metadata sidecar** (actual URL, viewport, auth-state source, which
readiness checks ran and passed, asset statuses, settle time, key text markers, warnings, and a
`usable` flag). **`usable` is true only when every configured readiness check passed AND no expected
asset failed** — a `usable:false` PNG is not admissible parity evidence.

- **`--login` (+ `--project`, `--creds`)** does a FRESH from-start login in the capture context (warms the
  session), then navigates the target — the robust path for **session-sensitive / AJAX screens** where a saved
  `--auth-state` is a stale single cookie the server rotates. Reads `loginUrl`/`loginFields` from project.json;
  creds from a gitignored `login.env` (or `LEGACY_USER`/`LEGACY_PASS` env). The login POST is **redacted from the
  saved HAR**. `--check-login` runs just the login as an auth probe. `profiles` can set `"login": true` instead.
- **No-stall guarantee:** navigation uses `domcontentloaded` + a **bounded** networkidle settle, and the whole
  capture is wrapped so the **HAR always flushes and partial artifacts are written even on a timeout** — a hang
  becomes a `rejected` capture with a `nav_error` (exit 2), never a silent stall. `--channel chrome|msedge` falls
  back to a system browser when bundled Chromium isn't installed (`python -m playwright install chromium`).
- **`--record-har`** saves `<name>.har` — the REAL backend responses for record-mode replay (no fakes).
- **Error-page quarantine:** the document HTTP status + `errorSignatures` are checked; an error/wrong page
  is written under `_rejected/` and flagged `rejected:true`, NOT promoted as the view's evidence. Look
  around again instead of accepting it. (`usable` also requires it not be an error page.)
- **`--profile <file>`** loads a capture contract (`templates/capture-profile.json` schema). CLI flags
  override profile fields. The builder reuses the **same profile** for the React capture → comparable.
- **Same `--viewport`** for legacy and React — parity depends on it.
- **Readiness order** (prefer over a big `--wait-ms`): `--wait-for` selector → `--must-contain TEXT`
  (repeatable; the strongest "real data arrived" signal) → `--wait-for-gone` spinner/mask → fonts
  ready → `--wait-ms` small final settle. `--readiness-timeout` bounds each wait.
- `--workflow steps.json` (or a `workflow` array in the profile) navigates to a deep state first
  (vocab: navigate/click/fill/select/wait) — use it for login, tabs, modals, drill-downs.
- `<name>.model.json` is the normalized structural model that `parity-verify/dom_diff.py` consumes.
  **The builder captures the React render with this very script**, guaranteeing both models match shape.

See `references/runtime-readiness-and-auth.md` for *why* each readiness check exists, the
canonical-vs-misleading route rule, localhost/non-SSO troubleshooting, and timing calibration.

### capture_fixtures.py — REAL recorded responses → MSW replay handlers (record mode)
```bash
python scripts/capture_fixtures.py --har work/evidence/f010_default/legacy.har \
  --out <react-app>/src/mocks/f010_default        # or --network <…>.network.json
```
Writes `fixtures.json` + `handlers.ts` (MSW v2) keyed by `METHOD pathname`, returning the REAL recorded
bytes (no hand-authored data). This is the **record-mode** data layer; **live-mode** views skip it and use
the Vite proxy instead (see react-replica-kit `references/backend-data-modes.md`).

## Typical analysis-mode flow (source-driven)
```
PRE-CAPTURE TRIAGE            → reachable? auth e2e? canonical route? assets 200? one view hydrates?
                                (references/runtime-readiness-and-auth.md §1 — do this ONCE first)
save_auth_state.py            → auth_state.json                              (login skill; once)
extract_theme.py              → evidence/theme/{tokens.json,theme.css}       (colors/fonts from source)
crawl_screens.py --emit-viewgraph + crawl_ajax.py --merge → viewgraph.json   (static + AJAX views)
for each view:
  extract_jsp.py              → <view>/source-model.json                     (the BUILD INPUT)
  write capture profile (workflow = from-start click-path) → profiles/<view>.json
  capture_screen.py --profile --record-har → <view>/{legacy.png,model.json,legacy.har,capture.json}
                                              (usable? error pages → _rejected/)
  capture_fixtures.py --har   → src/mocks/<view>  (record-mode replay; live-mode views skip)
→ the driver agent writes spec.md (source model + capture contract), seeds status.md, MANIFEST.json,
  then build_index.py → evidence/INDEX.html (the navigable human index)
```
Skip triage and you risk capturing hundreds of views of confident-wrong evidence (unstyled pages, error
routes behind misleading `.do` links, views captured before async data hydrated).

## Reference
- `references/jsp-source-extraction.md` — the `source-model.json` schema and how the driver agent builds from it.
- `references/ajax-crawl-and-viewgraph.md` — stateful AJAX discovery, the from-start rule, the `viewgraph.json`
  schema, and optional Crawljax normalization.
- `references/runtime-readiness-and-auth.md` — **read before first capture.** Triage, semantic readiness,
  timing calibration, canonical-vs-misleading routes, localhost/non-SSO, styled detection, error quarantine,
  source-backed debugging before `blocked`, recovery.
- `references/struts-jsp-endpoint-mapping.md` — deriving each view's endpoints across the 3 backend layers
  (Struts `.do`, Spring REST, WS/feign→mainframe) and how that maps to the recorded responses + data wiring.
- `templates/capture-profile.json` (repo root `templates/`) — the per-view capture-contract schema consumed
  by `capture_screen.py --profile` and reused by the driver agent for the React capture.

