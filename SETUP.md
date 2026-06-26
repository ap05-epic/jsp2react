# SETUP — standing up jsp2react on the pod (by hand)

Fastest path: clone the repo and run **one command**. The rest of this file explains what that command
does and how to run your first screen. Later, DigitCode (`dc agent install jsp2react`) replaces it.

```bash
git clone https://github.com/ap05-epic/jsp2react.git
cd jsp2react
bash install.sh
```

## 1. File tree

```
jsp2react/
├── install.sh                    # one-command setup (placement + deps + checks)
├── README.md
├── SETUP.md
├── docs/HOW-IT-WORKS.md
├── agents/
│   ├── jsp2react-analyzer.agent.md
│   └── jsp2react-builder.agent.md
├── skills/
│   ├── legacy-crawl-capture/
│   │   ├── SKILL.md
│   │   ├── scripts/{crawl_screens.py, capture_screen.py, capture_fixtures.py}
│   │   └── references/{struts-jsp-endpoint-mapping.md, runtime-readiness-and-auth.md}
│   ├── parity-verify/
│   │   ├── SKILL.md
│   │   ├── package.json          # declares pixelmatch + pngjs (install.sh runs `npm install` here)
│   │   ├── scripts/{verify_screen.py, dom_diff.py, pixel_diff.js}
│   │   └── references/parity-thresholds.md
│   └── react-replica-kit/
│       ├── SKILL.md
│       ├── scripts/{scaffold_app.sh, serve_review.py}
│       └── references/{jsp-to-react-mapping.md, css-porting.md}
└── templates/{STATUS.md, spec.md, MANIFEST.json, capture-profile.json}
```

## 2. What `install.sh` does (and the manual equivalent)

`bash install.sh` performs exactly these steps — run them by hand only if you want to:

| Step | Command it runs | Destination |
|---|---|---|
| place skills | `cp -r skills/* ~/.copilot/skills/` | `~/.copilot/skills/{legacy-crawl-capture,parity-verify,react-replica-kit}` |
| place agents | `cp agents/*.agent.md ~/.copilot/agents/` | `~/.copilot/agents/` (same place DigitCode/Copilot read agents) |
| pixel deps | `cd ~/.copilot/skills/parity-verify && npm install` | installs pixelmatch+pngjs (from `package.json`) so `pixel_diff.js` resolves them |
| checks | verifies Node, Python 3, Playwright are present | warns if anything's missing |

Override the targets if your pod differs: `COPILOT_SKILLS_DIR=… COPILOT_AGENTS_DIR=… bash install.sh`.
Templates are blueprints the **analyzer** copies and fills on its own — you don't edit them by hand (§5).

> Paths aren't hardcoded anywhere — the scripts resolve everything from `STATUS.md §2` at run time.

## 3. Prerequisites already on the pod (verify, don't install)

- **Python 3** with **Playwright** (`webapp-testing` uses it). If missing: `pip install playwright && playwright install chromium`.
- **Node 18+ / npm** (for the React app, Vite, and `pixel_diff.js`).
- Skills present: `webapp-snapshot`, `webapp-testing`, `digimem` (and optionally `playwright-cli`).

## 4. Open‑source dependencies to pull (manual, pinned)

All MIT. The pod can pull these from GitHub/npm; here is exactly what and from where.

| Package | Source | Install | Used by |
|---|---|---|---|
| `pixelmatch` | github.com/mapbox/pixelmatch | `npm i -D pixelmatch@^5.3.0` | `parity-verify/scripts/pixel_diff.js` |
| `pngjs` | github.com/lukeapage/pngjs | `npm i -D pngjs@^7.0.0` | `parity-verify/scripts/pixel_diff.js` |
| `msw` | github.com/mswjs/msw | `npm i -D msw@^2.0.0` | `react-replica-kit` (fixture rendering) |
| Vite + React + TS | github.com/vitejs/vite | `npm create vite@latest <app> -- --template react-ts` | `react-replica-kit/scripts/scaffold_app.sh` (runs this for you) |

### Nothing ships in the repo — `node_modules` is git‑ignored. Install on the pod:

**Automatic (you don't do these by hand):** `scaffold_app.sh` installs **Vite + React + TS, `msw`,
`pixelmatch`, and `pngjs` into the React app** and runs `npx msw init public/`. So scaffolding the app
covers all four packages for the app itself.

**The parity skill's pixel libs — `install.sh` already did this.** `pixel_diff.js` lives in the
`parity-verify` skill (a different folder than the React app), and Node resolves a script's `require()`
from its own folder upward — not from the React app. The skill ships a `package.json`, and `install.sh`
runs `npm install` there for you. If you skipped `install.sh`, do it once by hand:
```bash
cd ~/.copilot/skills/parity-verify && npm install      # reads package.json -> pixelmatch + pngjs
```
Verify: `node ~/.copilot/skills/parity-verify/scripts/pixel_diff.js --self-check` → expects
`{"self_check":"ok","identical_diff_pixels":0}`.

**Not npm (must already be on the pod):** Node.js + npm; and **Python 3 + Playwright** for capture
(`pip install playwright && playwright install chromium`). The Python scripts use the standard library only.

Notes:
- `pixel_diff.js` works with pixelmatch v5 (CommonJS) **and** v6/v7 (ESM) — its loader tries `require`
  then dynamic `import`; v5.3.0 is the simplest pin.
- Alternative to the manual step: run `verify_screen.py --pixel-diff <app>/node_modules/.../pixel_diff.js`
  or set `NODE_PATH` to the app's `node_modules`. The skill‑local install above is simplest.

## 5. Configuration — the analyzer fills `STATUS.md`, not you

This is autonomous: **you do not hand-fill STATUS.md.** The **analyzer agent creates and seeds it** on its
first run (kickoff prompt + repo discovery + defaults). The only things a human supplies — once, in the
kickoff prompt — are:

- **Legacy app URL** — the entry point; can't be guessed.
- **Login** — how to authenticate: point at the login skill / where credentials or `auth_state.json` live
  (the analyzer *invokes* login, it doesn't implement it). A one-time SSO step may be needed (a pre-step).
- *(optional)* the legacy **source root** and **target app path** — omit them and the analyzer discovers
  the source and defaults the target (`<work>/jsp2react-ui`).

Everything else in §1–§3 (webapp dir, struts-config, bundles, viewport `1920x1080`, evidence root, tool
paths, digimem domain) is discovered or defaulted. Edit STATUS.md afterward only to **override** a default
(e.g. a per-screen pixel threshold) or to scope the run. → Normal operation is just the prompts in §6b.

## 6. First‑run smoke test — OPTIONAL manual wiring check (one screen, run by hand)

This proves the pipeline works on the pod *before* you trust the agents with a full sweep. It's a manual
operator check using the scripts directly; the **autonomous run is §6b** (you just give the analyzer the
URL). Skip to §6b if you'd rather let Copilot do it.

```bash
# 0. sanity: every script answers --help / --self-check without a browser
python ~/.copilot/skills/legacy-crawl-capture/scripts/crawl_screens.py --self-check
python ~/.copilot/skills/legacy-crawl-capture/scripts/capture_screen.py --self-check
python ~/.copilot/skills/parity-verify/scripts/dom_diff.py --self-check
node   ~/.copilot/skills/parity-verify/scripts/pixel_diff.js --self-check          # needs pixelmatch+pngjs

# 1. login once  (login skill — produces the session everything reuses)
python ~/.copilot/skills/webapp-snapshot/scripts/save_auth_state.py --url <login-url> --output work/auth_state.json

# 2. discover screens (deterministic inventory)
python ~/.copilot/skills/legacy-crawl-capture/scripts/crawl_screens.py \
  --struts-config <…>/WEB-INF/struts-config.xml --webapp-dir <…>/webapp --out work/screens.json

# 3. capture ONE legacy screen — with SEMANTIC READINESS so the capture is USABLE, not just "rendered".
#    Readiness order: --wait-for selector -> --must-contain text -> --wait-for-gone spinner -> small --wait-ms.
#    Check the <name>.capture.json sidecar: "usable": true means readiness passed AND no CSS/JS 404.
#    (Or pass --profile work/profiles/f010.json — a reusable capture contract; see templates/capture-profile.json.)
python ~/.copilot/skills/legacy-crawl-capture/scripts/capture_screen.py \
  --url <screen-url> --out-dir work/screenshots --name f010_default \
  --auth-state work/auth_state.json --viewport 1920x1080 \
  --wait-for "#pmenu" --must-contain "Compensation" --wait-for-gone ".loadingMask" --wait-ms 8000
# Why each flag / localhost+auth+timing troubleshooting:
#   ~/.copilot/skills/legacy-crawl-capture/references/runtime-readiness-and-auth.md

# 4. fixtures + scaffold the app
python ~/.copilot/skills/legacy-crawl-capture/scripts/capture_fixtures.py \
  --network work/screenshots/f010_default.network.json --out <app>/src/mocks/f010
bash   ~/.copilot/skills/react-replica-kit/scripts/scaffold_app.sh <app>     # if not scaffolded yet

# 5. (builder builds src/screens/F010, runs `npm run dev`, then captures the react side)
#    REUSE the same readiness (viewport + must-contain text + settle) so both captures are comparable.
#    The Dojo ".loadingMask" won't exist in React — skip just that mechanical check with --wait-for-gone "".
python ~/.copilot/skills/legacy-crawl-capture/scripts/capture_screen.py \
  --url http://localhost:5173/#/f010 --out-dir work/react --name f010_default --viewport 1920x1080 \
  --wait-for "#root" --must-contain "Compensation" --wait-for-gone "" --wait-ms 8000

# 6. PROVE parity
python ~/.copilot/skills/parity-verify/scripts/verify_screen.py \
  --legacy-model work/screenshots/f010_default.model.json --legacy-png work/screenshots/f010_default.png \
  --react-model  work/react/f010_default.model.json       --react-png  work/react/f010_default.png \
  --out-dir work/parity --name f010_default --pixel-threshold 0.005
# exit 0 = PASS. Read work/parity/f010_default.parity-report.md for concrete deltas if it FAILS.

# review
python ~/.copilot/skills/react-replica-kit/scripts/serve_review.py --work-dir work --react-base-url http://localhost:5173
```

## 6b. What to type into Copilot (after the files are placed)

Copilot auto-discovers the skills; you invoke the agents the same way you invoke your existing `baa-*`
agents (by name / trigger phrase). Suggested prompts:

**Step A — sanity check the install (no crawling):**
> "Read jsp2react/SETUP.md and README.md. Confirm the three skills are under ~/.copilot/skills and both
> jsp2react agents are discoverable, then run the §6 self-checks (`--self-check` / `--help`) and report
> results. Don't crawl anything yet."

**Step B — analyze (run once; it builds the contract for ALL screens). You give it only the URL + login:**
> "Use the **jsp2react-analyzer** agent. Legacy app URL = `<…>`. Log in via
> webapp-snapshot/save_auth_state.py (creds/auth_state at `<…>`). The legacy source is at `<…>` *(omit this
> line to let it discover the source)*. **Bootstrap STATUS.md yourself**, then log in, **run pre-capture
> triage (app reachable, auth end-to-end, canonical post-login route, assets 200, one data-heavy page
> actually hydrates) before mass capture**, then crawl and capture every screen (write a capture profile
> per screen; a capture counts only when its `.capture.json` says `usable:true`), map each screen's
> endpoints, generate MSW fixtures, and write spec.md + STATUS.md + MANIFEST.json. Begin with the shell +
> one family, then continue across all families until the coverage matrix is met."

That's the whole human input: the **URL** and **how to log in** (source path optional). The analyzer
discovers/derives everything else into STATUS.md — you never hand-edit it.

**Step C — build (run repeatedly; one screen per turn):**
> "Use the **jsp2react-builder** agent. Read STATUS.md and implement the next screen end to end: port it
> 1:1, wire its MSW fixtures, render it, run parity-verify, and fix from the parity report until it
> PASSES, then update STATUS.md. Do one screen, then show me its parity-report.md and side-by-side.png."

Then simply: **"Continue with the next screen."** (repeat) — or, once you trust it,
**"Implement all remaining screens, verifying each before moving on; stop and tell me about any blocker."**

**Review:**
> "Run react-replica-kit/scripts/serve_review.py against the work dir and the running React app so I can
> review legacy vs React side by side."

## 7. Assumptions to verify on the pod (correct as needed)

1. `~/.copilot/skills/` is the skills dir and your Copilot agents dir is where `baa-*` live. Adjust paths in
   `STATUS.md §2` if not.
2. The legacy source (incl. `struts-config*.xml`, `.properties`) is readable; set its path in `STATUS.md`.
3. Login can yield a reusable `auth_state.json` (one manual SSO step may be needed — it's a pre‑step, not
   part of the agent loop).
4. Mainframe data is reached via WS/feign; **no live mainframe call is needed to render** (fixtures cover
   it). Use the team's `cics-analysis` agent for COMMAREA/DB2 contracts only if that source is in scope.
5. Pixel‑exact JSP↔React isn't realistic; the gate is **strict structural + thresholded pixel**. Tune
   `--pixel-threshold` per screen in `STATUS.md §3` (see `parity-thresholds.md`), never the structural gate.
6. Script CLIs here are the contract; if a reused pod skill's flags differ (OCR drift), run it with
   `--help` and adjust — the agents are told to do this.

## 8. If something fails
- Script import/`--self-check` fails → missing Python/Playwright or Node deps (§3, §4).
- Pixel ratio huge → almost always a capture mismatch (different viewport/data/fonts), not a real defect —
  see `parity-thresholds.md` "Making the comparison fair".
- Login redirects reappear mid‑run → session expired; re‑run step 1; note it in `STATUS.md §7`.
- Crawl misses screens → check `screens.json.reconciliation`; add missing actions/JSPs as spec §4 entries.
- Capture `usable:false`, or page looks unstyled / shows an error / is missing data → it "rendered" but
  isn't real evidence. Almost always: a misleading direct `*.do` route (use the real login→dispatcher
  flow), CSS/JS 404s (no live app base), or async data captured too early (raise readiness/settle). Full
  runbook incl. localhost/non‑SSO + timing: `legacy-crawl-capture/references/runtime-readiness-and-auth.md`.
