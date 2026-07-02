# Reference — every file in this repo, on one page

The maintainer's map. Reading order for a new team member: [README](../README.md) (what this is) →
[HOW-IT-WORKS](HOW-IT-WORKS.md) (plain-English concepts) → [SETUP](../SETUP.md) (install + run) →
[PROMPTS](PROMPTS.md) (what to type into Copilot) → this page (what each file does when you need to
change something).

**The pipeline every screen goes through, and which script does each step:**

```
 login ─→ discover views ─→ parse source ─→ capture evidence ─→ make replay data ─→ build React ─→ prove it
 (capture_screen  (crawl_screens +   (extract_jsp +     (capture_screen      (capture_fixtures)   (the agent,   (verify_screen +
  --check-login)   crawl_ajax)        extract_backend*)   --login --record-har)                     by hand)      verify_contract*)
                                                                                            * = full mode only
```

## Agents (`agents/` → installed to `~/.copilot/agents/`)

The agent file is the **instruction manual Copilot follows** — the workflow, the rules, when to run which
script. It contains no code.

| File | Mode | What it drives |
|---|---|---|
| `modernize-flow.agent.md` | full | React **+ Spring Boot** (new endpoints calling the same stored procedures) |
| `jsp2react.agent.md` | frontend | React only, fed by the existing legacy backend — the simpler fallback |

## Skill: `legacy-crawl-capture` — read the legacy app

| Script | What it does | You'd touch it when… |
|---|---|---|
| `init_project.py` | Bootstraps `project.json` from the URL + login JSP + source tree (the agent runs this, not the human) | a new app's config fields don't auto-derive |
| `extract_jsp.py` | Parses one JSP → `source-model.json` (loops, forms, labels, AJAX endpoints) — the **build input** | a JSP construct isn't extracted |
| `crawl_screens.py` | Static inventory from `struts-config.xml` + the JSP tree (no browser) → `screens.json` + a static viewgraph | screens are missed/miscounted |
| `crawl_ajax.py` | Clicks/hovers through the running app from the start → `viewgraph.json` (every AJAX view + its from-start click-path). Needs `--login` on session-sensitive apps | tabs/menus aren't discovered |
| `capture_screen.py` | **The workhorse.** Captures one screen as evidence: screenshot + normalized DOM model + real responses (`--record-har`) + a `usable` verdict; quarantines error pages; `--login` = fresh from-start login; `--check-login` = auth probe | capture stalls, auth fails, wrong page accepted |
| `capture_fixtures.py` | Turns the recorded HAR into MSW replay handlers (`fixtures.json` + `handlers.ts`) — the record-mode data layer | a response type isn't replayed |

References: `jsp-source-extraction.md` (source-model schema), `ajax-crawl-and-viewgraph.md` (the from-start
rule), `runtime-readiness-and-auth.md` (**read before first capture** — triage, readiness, auth),
`struts-jsp-endpoint-mapping.md` (endpoint layers).

## Skill: `react-replica-kit` — build the new UI

| Script | What it does | You'd touch it when… |
|---|---|---|
| `extract_theme.py` | Harvests the legacy CSS → `tokens.json` + `theme.css` (the real colors/fonts the React app styles from) | a color/font token is missed |
| `scaffold_app.sh` | Creates the Vite + React + TS app wired for the three data modes (MSW record replay / live proxy) | the scaffold shape changes |
| `build_index.py` | Generates `evidence/INDEX.html` — the navigable per-view status/evidence index | the index layout changes |
| `serve_review.py` | Serves legacy vs React side-by-side for human review | the review page changes |

References: `jsp-to-react-mapping.md` (**the build rules** — construct table, "no new artifacts", the
no-HTML-injection rule), `backend-data-modes.md` (record/live/api), `css-porting.md`, `theme-extraction.md`.

## Skill: `parity-verify` — prove the UI matches

| Script | What it does | You'd touch it when… |
|---|---|---|
| `verify_screen.py` | **The frontend gate.** DOM-content diff + data-presence + pixel diff vs the captured oracle → pass/fail + a punch-list. Content deltas gate; nesting-only deltas (same content, different markup grouping) are advisory (`--strict-nesting` gates them) | the gate policy changes |
| `dom_diff.py` | The structural lane: compares the two normalized `model.json` files and classifies each delta content vs nesting | a delta type is noisy/missed |
| `pixel_diff.js` | The pixel lane (pixelmatch + pngjs; `install.sh` runs `npm install` here) | pixel thresholds/report change |

Reference: `parity-thresholds.md` (what ratios mean; when a big number is a capture problem, not a bug).

## Skill: `springboot-target-kit` — rebuild the data layer (full mode only)

| Script | What it does | You'd touch it when… |
|---|---|---|
| `extract_backend.py` | Traces Action → Service → DAO → **stored procedure** → `backend-model.json` (typed params + result columns) | a DAO/sqlmap pattern isn't traced |
| `scaffold_backend.py` | Generates the Spring Boot slice from that model: controller → service → `SimpleJdbcCall` gateway → DTO + OpenAPI | the generated shape changes |
| `verify_contract.py` | **The backend gate.** Diffs the new endpoint's JSON against the recorded legacy HAR (field/type/value) | the contract rules change |

References: `backend-layering.md`, `stored-procedure-mapping.md`, `session-auth-state.md`.

## Everything else

| File | What it is |
|---|---|
| `install.sh` | The installer — a **file copier with safety checks** (see [HOW-IT-WORKS](HOW-IT-WORKS.md#what-bash-installsh-actually-does)). Safe to re-run after every `git pull`. |
| `templates/project.json` | The one app-specific config every script reads (`--project`). The agent bootstraps it via `init_project.py`. |
| `templates/capture-profile.json` | Per-view capture contract (url/workflow/readiness) — reused verbatim for the React capture so both sides are comparable. |
| `templates/status.md` / `spec.md` / `MANIFEST.json` | The agent's control plane (feature checklist), durable contract, and evidence ledger — the agent creates and maintains them in the work repo. |
| `examples/baa.project.json` | A worked `project.json` (localhost example values). |

## The one health check

Every Python script (and `pixel_diff.js`) answers `--self-check` with no browser, files, or network —
run this after any change and before any commit:

```bash
cd skills
for f in legacy-crawl-capture/scripts/{init_project,extract_jsp,crawl_ajax,crawl_screens,capture_screen,capture_fixtures} \
         react-replica-kit/scripts/{extract_theme,build_index,serve_review} \
         parity-verify/scripts/{dom_diff,verify_screen} \
         springboot-target-kit/scripts/{extract_backend,scaffold_backend,verify_contract}; do
  python3 $f.py --self-check || echo "FAILED: $f"; done          # expect 14x {"self_check": "ok", ...}
node parity-verify/scripts/pixel_diff.js --self-check            # expect identical_diff_pixels: 0
```

## House rules (the short version)

- **Generic:** nothing app-specific in code — app facts live in `project.json` only.
- **Stdlib-only Python** in the scripts (Playwright is the one runtime dep, for browser steps).
- **Every script self-checks** (`--self-check`), and the CLI is the contract (`--help` before first use).
- **Never commit credentials** — `login.env` stays gitignored; the login POST is redacted from saved HARs.
- **Real data only, real components only** — no hand-authored fixtures, no `dangerouslySetInnerHTML` of
  captured legacy HTML (see `jsp-to-react-mapping.md`).
