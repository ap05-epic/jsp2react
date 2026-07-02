# modernize-flow / jsp2react — Legacy JSP/Struts → React (+ Spring Boot), with proven fidelity

A **skills + agents** toolkit for GitHub Copilot CLI (GPT‑5.4) that modernizes a legacy JSP/Java/Struts app
**from its source**. Given the legacy URL + how to log in (+ a small `project.json`), it logs in, **extracts the
real color/font theme**, discovers **every view including AJAX‑loaded ones** (reached from the start), **parses
each JSP into a source model**, and builds a **React + TypeScript 1:1 replica from that source**, fed the **real
backend data** — and in full‑stack mode it also **traces the legacy data layer (action → service → DAO → stored
procedure)** and generates a **Spring Boot** endpoint (controller → service → SimpleJdbcCall gateway → DTO) that
**reproduces** that data. Every slice is **proven** against the running legacy app and the recorded responses.

It is **generic** (any legacy app via `project.json`) and **source‑driven** — the build input is the
JSP/AJAX/CSS/Java source; the running screen is the verification target (not a screenshot the AI guesses from).

**The docs, in reading order:** [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) — the whole system in plain
English (start here; use it to explain it to others) · [SETUP.md](SETUP.md) — install + first run ·
[docs/PROMPTS.md](docs/PROMPTS.md) — the copy-paste Copilot prompt playbook ·
[docs/REFERENCE.md](docs/REFERENCE.md) — every script on one page (the maintainer's map).

## Two modes (pick at install time)

| Mode | Agent | Target | Skills installed |
|---|---|---|---|
| **full** (default) | `modernize-flow` | React **+ Spring Boot** (calls the legacy stored procs) | all 4 |
| **frontend** (fallback) | `jsp2react` | React only (talks to the existing legacy backend) | 3 (no `springboot-target-kit`) |

The frontend mode is the safe retreat if the full‑stack path gets too complex — same UI engine, no backend.

## Quick start (manual phase)

```bash
git clone <this repo's URL>
cd modernize-flow
bash install.sh full        # or: bash install.sh frontend
```
`install.sh` does a **clean install**: it moves aside this toolkit's own managed skills/agents (backed up under
`~/.copilot/modernize-flow.backup/<timestamp>/`, never deleted), then installs exactly the chosen mode's set — so
the pod is never on stale files. It only touches files this toolkit owns **by exact name**; every other skill and
agent is untouched. The update routine is just `git pull && bash install.sh full`. (Plain‑English
walk‑through: [HOW‑IT‑WORKS § What `bash install.sh` actually does](docs/HOW-IT-WORKS.md#what-bash-installsh-actually-does).) Then in Copilot, run the **`modernize-flow`** (or **`jsp2react`**) agent and give
it the **legacy URL + how to log in + a `project.json`** — it bootstraps `status.md` itself and works one
control/slice at a time (exact prompts in [docs/PROMPTS.md](docs/PROMPTS.md)). Prereqs the installer checks: Node.js,
Python 3 + Playwright (full mode also checks for a JDK + Maven/Gradle).

**Fallback:** if the full‑stack path is too much for a given app, `bash install.sh frontend` switches to the
frontend‑only system (same UI engine, no backend generation) — no re‑clone needed.

## How it works (one driver agent + four skills + one contract)

```
status.md (control plane) · spec.md (contract) · MANIFEST.json (evidence ledger)
   ^ seeded in analysis mode · read + updated every implementation turn
   |
DRIVER AGENT — modernize-flow (full) · jsp2react (frontend-only fallback)
   | analysis: discover + parse + capture, then implement: build FROM SOURCE -> prove -> fix
   |
   +- legacy-crawl-capture    parse JSP · find AJAX views · capture evidence + real HAR
   +- react-replica-kit       theme · scaffold · build views · review index
   +- parity-verify           DOM-content + pixel + data-presence gate
   +- springboot-target-kit   action -> service -> DAO -> stored proc · verify  (FULL)
      (reuses pod skills: webapp-snapshot · webapp-testing · digimem)
```

**The loop (per control/slice, status‑driven so it never drifts over a long sweep):**
`READ status.md → READ source-model (+ backend-model, FULL) + theme + evidence → BUILD 1:1 FROM SOURCE → wire REAL
data (record HAR replay / live proxy / new api) → verify_screen.py (+ verify_contract.py, FULL) → FIX from the
concrete delta → mark verified → regenerate INDEX.html.`

## How each non‑negotiable is met

| Requirement | Where it's enforced |
|---|---|
| **Generic (any app)** | `project.json` (+ `examples/baa.project.json`) drives every script — context root, login, families, theme, db/sqlmaps. No app name is hardcoded in runtime logic. |
| **Built from source, not the image** | `extract_jsp.py` → `source-model.json` is the UI build input; `extract_backend.py` → `backend-model.json` is the data build input. The screenshot only verifies. |
| **Every view found (incl. AJAX)** | `crawl_ajax.py` walks UI states from the start (tabs/menus/drilldowns), reconciled with the static `crawl_screens.py` inventory into `viewgraph.json`; each view carries a from‑start click‑path. |
| **Right colors/fonts** | `extract_theme.py` harvests the legacy palette/fonts into `theme.css` tokens the app styles from — no per‑element guessing. |
| **Real data, never fakes** | Frontend: **record** replays the REAL recorded HAR / **live** proxies the real backend. Backend (FULL): the new endpoint calls the **same stored procedure** and is checked against the recorded HAR. No hand‑authored data. |
| **Full‑stack backend** | `springboot-target-kit` traces action→service→DAO→stored proc → `backend-model.json` → scaffolds controller/service/gateway/DTO/OpenAPI; the agent fills the business logic; `verify_contract.py` proves it vs the legacy HAR. |
| **No wrong pages accepted** | `capture_screen.py` checks HTTP status + error signatures and **quarantines** error/half‑loaded pages to `_rejected/`; never promoted as the view. |
| **Fidelity proven, not claimed** | Deterministic gates (`verify_screen.py` frontend, `verify_contract.py` backend; exit 0/2) — numeric reports + located diffs + side‑by‑side. The model fixes from findings; it does not judge by eye. |
| **Holds up over long runs** | One slice per iteration; control‑level `status.md` inventory + strict 6‑status lifecycle + recover‑before‑blocker + source‑backed debugging. |

## What's here

```
modernize-flow/
├── install.sh           ← clean install, MODE = full | frontend  (manual phase)
├── README.md            ← you are here
├── SETUP.md             ← detailed stand-up + the Copilot prompts (read this next)
├── docs/HOW-IT-WORKS.md ← plain-English explainer
├── docs/PROMPTS.md      ← copy-paste Copilot prompts (lifecycle, scenarios, anti-patterns)
├── docs/REFERENCE.md    ← every script on one page (the maintainer's map)
├── agents/              ← modernize-flow.agent.md (full) · jsp2react.agent.md (fallback)
├── skills/              ← the four skills (each: SKILL.md + scripts/ + references/)
├── templates/           ← the blueprint files the agent copies and fills itself
└── examples/            ← baa.project.json (a worked project config)
```

New here? Read **[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)** first — it explains the whole thing in plain language.

## Reuse & open source

Reuses the pod's existing skills: `webapp-snapshot` (login via `save_auth_state.py`), `webapp-testing` (Playwright),
`digimem` (team memory). Pulls MIT open‑source packages, installed manually (SETUP.md): **pixelmatch** + **pngjs**
(pixel diff), **MSW** (record‑mode HAR replay), **Vite/React/TypeScript** (scaffold). The Python extractors
(`extract_jsp`, `extract_theme`, `extract_backend`, …) and the Spring Boot scaffolder are stdlib‑only. The Spring
Boot target uses Spring's `SimpleJdbcCall`/`JdbcTemplate` against the legacy DB.

## Out of scope (so omissions aren't mistaken for gaps)

The **business‑logic translation** itself (the agent ports the legacy service/builder semantics — not auto‑generated);
mainframe/COBOL/BMS (delegated to the pod's separate `cics-analysis` agent); responsive/mobile; accessibility
remediation; animation modeling; CI wiring. The replica targets the legacy desktop viewport at parity. *(Backend
modernization is now IN scope in full mode — it was out of scope in v2.)*

---

Made by **Anshuman Pandey** · Summer Intern 2026 · AI Pod
