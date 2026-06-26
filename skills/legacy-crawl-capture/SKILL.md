---
name: legacy-crawl-capture
description: Discover every screen in a legacy JSP/Struts web app and capture each screen state as comparable evidence (screenshot + normalized DOM model + a11y + network), plus turn captured network traffic into MSW fixtures. Use when converting a legacy JSP/Java/Struts UI to React and you need to enumerate all screens and capture the source-of-truth evidence the jsp2react agents replicate and verify against. Reuses the pod's webapp-snapshot (login/screenshots) and webapp-testing (Playwright/server) skills; adds discovery, normalized capture, and fixture generation that those skills do not provide.
---

# legacy-crawl-capture

Source-of-truth capture for the **jsp2react** system. fig2code extracts a static Figma design; this
skill extracts a **live, running legacy screen** — and the original JSP/Struts source behind it.

It does three things the pod's existing skills don't:
1. **Discover** the full screen graph from `struts-config.xml` + JSP scan (so nothing is missed).
2. **Capture** each screen state into a *normalized model* that can be diffed deterministically
   against the React render (the SAME script captures both sides → always comparable).
3. **Fixture** the captured network so the React replica renders identical data with no backend.

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

### crawl_screens.py — enumerate every screen (deterministic-first)
```bash
# Authoritative inventory from source (no browser): actions + JSPs + links, reconciled by family.
python scripts/crawl_screens.py \
  --struts-config <…>/WEB-INF/struts-config.xml \
  --webapp-dir   <…>/BAA/src/main/webapp \
  --out screens.json

# Optional: also harvest the live reachable set (bounded BFS) once logged in.
python scripts/crawl_screens.py --webapp-dir <…> --runtime-url <summary-url> \
  --auth-state auth_state.json --max-pages 60 --out screens.json
```
Vendor/build dirs (`pdfjs`, `dojo`, `jquery*`, `lib`, `locale`, `node_modules`, `coverage`,
`target`, `dist`, `build`) are pruned automatically. `screens.json.reconciliation` is the
"did we miss a screen?" gate — every screen JSP/action must become a STATUS.md row or an explicit
unmatched entry in spec.md §4.

### capture_screen.py — capture ONE state as comparable evidence (legacy OR react)
This is the **authoritative parity capture** (not a quick screenshot — see the snapshot note above).
It enforces *semantic readiness* so the bundle reflects a **usable** screen, not just a rendered one.
```bash
# Driven by a per-screen capture profile (preferred — same contract reused for the React side):
python scripts/capture_screen.py --profile profiles/f010_fasummary.json \
  --out-dir work/screenshots --name f010_default --auth-state auth_state.json

# Or fully on the CLI:
python scripts/capture_screen.py --url <legacy-screen-url> \
  --out-dir work/screenshots --name f010_default --auth-state auth_state.json \
  --viewport 1920x1080 --wait-for "#pmenu" \
  --must-contain "Compensation" --must-contain "FA Profile" \
  --wait-for-gone ".loadingMask" --wait-ms 8000
```
Outputs `f010_default.{png,dom.html,model.json,a11y.json,network.json}` **plus a
`f010_default.capture.json` metadata sidecar** (actual URL, viewport, auth-state source, which
readiness checks ran and passed, asset statuses, settle time, key text markers, warnings, and a
`usable` flag). **`usable` is true only when every configured readiness check passed AND no expected
asset failed** — a `usable:false` PNG is not admissible parity evidence.

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

### capture_fixtures.py — captured traffic → MSW fixtures + handlers
```bash
python scripts/capture_fixtures.py --network work/screenshots/f010_default.network.json \
  --out <react-app>/src/mocks
```
Writes `fixtures.json` + `handlers.ts` (MSW v2) keyed by `METHOD pathname`. Data calls (xhr/fetch)
only by default; `--include-documents` to also keep HTML responses. See react-replica-kit for wiring.

## Typical analyzer flow
```
PRE-CAPTURE TRIAGE            → app reachable? auth end-to-end? assets 200? one page hydrates?
                                (see references/runtime-readiness-and-auth.md §1 — do this ONCE first)
save_auth_state.py            → auth_state.json            (login skill; once)
crawl_screens.py              → screens.json               (full inventory)
for each screen/state:
  write capture profile       → profiles/<screen>.json     (canonical route + readiness contract)
  capture_screen.py --profile → png + model + network + .capture.json (usable?)   (evidence bundle)
capture_fixtures.py           → src/mocks/{fixtures,handlers}
→ analyzer writes spec.md (incl. per-screen capture contract), seeds STATUS.md, updates MANIFEST.json
```
Skip triage and you risk capturing ~220 screens of confident-wrong evidence (unstyled pages, error
routes behind misleading `.do` links, screens captured before async data hydrated).

## Reference
- `references/runtime-readiness-and-auth.md` — **read before first capture.** Pre-capture triage,
  "page loaded ≠ screen usable" + the semantic-readiness order, BAA timing calibration, canonical-vs-
  misleading routes, localhost/non-SSO troubleshooting, styled-vs-unstyled detection, the per-screen
  capture contract, source-backed debugging before declaring `blocked`, and reset-evidence recovery.
- `references/struts-jsp-endpoint-mapping.md` — how to derive each screen's endpoints and data
  contracts from JSP/Struts source across the 3 backend layers (Struts `.do`, Spring REST,
  WS/feign→mainframe), and how that maps to fixtures + React data wiring.
- `templates/capture-profile.json` (repo root `templates/`) — the per-screen capture-contract schema
  consumed by `capture_screen.py --profile` and reused by the builder for the React capture.
