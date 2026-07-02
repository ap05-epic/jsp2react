# Prompt playbook — what to type into Copilot CLI

Copy-paste prompts for driving this system, field-tested on a real legacy app. Placeholders are in
`<angle brackets>`; pick the agent matching your installed mode: **`modernize-flow`** (full) or
**`jsp2react`** (frontend).

## What Copilot CLI needs (read once)

- **Name the agent in the first sentence** ("Use the modernize-flow agent…"). Copilot doesn't pick an
  agent by itself — without this you get plain Copilot, no workflow, no gates.
- **Detailed beats terse.** Copilot CLI (GPT‑5.4) follows explicit, step-listing prompts far more
  reliably than short ones. Every prompt below errs on the side of spelling things out.
- **Your prompt supplies FACTS + SCOPE + EVIDENCE.** The agent file already carries the rules (real
  components, real data, the verify gates) — you supply the facts it can't know (URLs, paths, entity
  IDs), the scope (which slice), and what evidence to show you back. Restating a critical rule anyway
  is cheap insurance against drift — these prompts do it deliberately.
- **Real paths only.** Give actual file paths (`work/project.json`, the evidence dir) — Copilot won't
  guess them and shouldn't.
- **One slice per prompt.** The whole system is built around it. Batch runs only with the guardrails
  prompt (G below), never "build everything".
- **Always end big runs with a blocker report** (J below). The blocker+resolution write-ups are the
  single most useful thing for improving the toolkit.

---

## The core lifecycle (run in order)

### A — Sanity check (right after `bash install.sh <mode>`; no crawling yet)

> "Read the toolkit repo's SETUP.md and README.md. Confirm the skills are under ~/.copilot/skills and the
> **<modernize-flow | jsp2react>** agent is discoverable, then run every script's `--self-check`
> (the loop in SETUP.md §6 step 0b) and report the results. Don't crawl or capture anything yet."

### B — Analyze (ONCE per app; builds the source-driven contract for ALL flows)

You give only the URL, how to log in, and the source path — the agent derives everything else.

> "Use the **<modernize-flow | jsp2react>** agent. Legacy URL = `<…>`. Log in with the app's login form;
> the gitignored creds file is at `<path/to/login.env>` — set `credsFile` in project.json and NEVER
> commit it. Legacy source is at `<…>`. **Bootstrap `project.json` yourself with init_project.py**
> (derive context root, login action/fields, families, db.sqlmapDir; complete any `_todo`), then
> **bootstrap status.md yourself**. Then: run pre-capture triage; **extract the theme**; **discover
> every view including AJAX** (crawl_screens --emit-viewgraph + crawl_ajax **--login --creds --project**
> from the start → viewgraph.json — never open deep links directly); for each flow **parse its JSP →
> source-model.json**, capture evidence + the **REAL responses** (--record-har; error pages
> auto-quarantine — look around again); (FULL mode) **trace the data layer → backend-model.json**.
> Write spec.md + status.md + MANIFEST.json, then build_index → evidence/INDEX.html. Begin with the
> login flow + one more flow, then continue across all flows. At the end, list every blocker you hit
> and how you resolved it."

### C — Implement the next slice (the repeat prompt; one slice per turn)

> "Use the **<modernize-flow | jsp2react>** agent. Read status.md and implement the next unblocked
> slice end to end: build it 1:1 **from its source-model.json + theme tokens** — **real React
> components only, never inject the captured legacy HTML** — using the **exact labels/tabs/columns
> from the captured dom.html** (never invent or reword one); (FULL) scaffold the Spring Boot endpoint
> from backend-model.json and fill the ServiceImpl with the legacy business logic + session binding;
> wire **real data** for its data mode (record = replay the captured HAR via capture_fixtures / live =
> proxy / api = the new endpoint); render and capture the React side **with the same profile**; run
> parity-verify (and verify_contract vs the HAR, FULL) and **fix from the concrete deltas in the
> report** until it passes or you hit a real blocker; then update status.md + regenerate INDEX.html.
> Show me the parity report numbers and the side-by-side, not just 'done'."

Then repeat with: **"Continue with the next slice."**

---

## Scenario prompts

### D — Capture an entity-gated / session-sensitive screen (deep URL shows an error)

For screens that need an account/entity selected first (the deep URL gives "session timeout" or an
empty shell). The from-start workflow is mandatory — this is the pattern that captured our first
hydrated screen.

> "Use the **<modernize-flow | jsp2react>** agent. Capture the `<screen>` view. It is ENTITY-GATED —
> its deep URL lands on an error page, so build a from-start **workflow** capture profile instead:
> login → `<the click-path, e.g. fill the quick-search with test entity <ID>, then click its submit>`.
> The submit may be a JS button (`onclick=…`), not `input[type=submit]` — find the real selector in the
> captured dom.html. Use a BODY data label for `mustContain` (it scans body text, not the page title).
> Capture with `capture_screen.py --profile <profiles/….json> --login --creds <login.env> --project
> <project.json> --record-har`. Confirm the capture says `usable:true` and the HAR contains the AJAX
> data calls; if it lands in `_rejected/`, show me the capture.json and stop — don't accept it."

### E — Connect screens into a navigable user flow (multi-screen)

Once 2+ views are built, wire the navigation so the replica walks like the real app.

> "Use the **<modernize-flow | jsp2react>** agent. Goal: connect the built screens into the real USER
> FLOW `<screen A> → <screen B> [→ <screen C>]` with react-router-dom — one route per screen, and the
> real controls navigate: `<A>`'s `<submit/link/tab>` goes to `<B>`'s route, exactly like the legacy
> click-path. Each screen loads its OWN record-mode fixtures on mount (MSW). Keep every screen's
> verified 1:1 markup unchanged — this step only adds routing. Prove it in the browser: start at
> `<A>`, do `<the real user action>`, confirm `<B>` renders with its real data; screenshot each step
> and report that the click-through works. Note: in record mode the flow replays the captured
> journey/entity — that's expected; live mode is a config flip, not a rebuild."

### F — A verify gate is failing (fix from the report, not by eye)

> "Use the **<modernize-flow | jsp2react>** agent. `verify_screen` for `<view>` is failing
> (`<N critical deltas / pixel ratio>`). Read the parity report at `<…/parity/…>` and fix ONLY what the
> report lists as **critical (content) deltas** — labels, columns, controls, values — in the React
> component (never by restyling to taste, never by touching the oracle). **Nesting deltas are advisory
> and don't fail the gate — do not rebuild legacy nested markup to chase them.** Re-capture the React
> side with the SAME profile, re-run verify_screen, repeat until it passes or a critical delta needs
> evidence we don't have — then stop and show me that delta."

### G — Go wide (batch run with guardrails)

> "Use the **<modernize-flow | jsp2react>** agent. Work through status.md one slice at a time:
> implement → wire real data → verify → update status.md, then the next unblocked slice. If a slice is
> blocked, record the blocker in status.md and MOVE ON — do not grind on it. Stop after `<N>` slices,
> or when the same blocker repeats twice. Then give me a table: slice | status | parity numbers |
> blockers + how you resolved them."

### H — Review / showcase

> "Run react-replica-kit/scripts/serve_review.py against the work dir and the running React app so I
> can review legacy vs React side by side, and regenerate evidence/INDEX.html. Tell me which verified
> flows make the strongest demo (real data + visible business behavior) and give me the run steps."

### I — Backend slice on its own (FULL mode)

> "Use the **modernize-flow** agent. For the `<flow>` slice: run extract_backend on
> `<…/<Flow>Action.java>` → backend-model.json (show me the stored procedure name, typed params, and
> result columns it traced); scaffold_backend from it; fill the ServiceImpl with the LEGACY service's
> business semantics (match behavior before improving anything) and the session/entity binding; start
> the app; then verify_contract against `<…/legacy.har>` with `--match /api/<flow>` and fix the
> gateway/DTO mapping from the deltas until it passes. Show me the contract report."

### J — Blocker report (end every big session with this)

> "List every blocker you hit this session and how you resolved or worked around it — the exact error
> text, file paths, and what you changed. Also list anything you had to figure out that the skills'
> docs didn't cover. I'll feed this back into the toolkit."

---

## Anti-patterns (each of these caused a real failure)

| Don't type | What actually happens | Type instead |
|---|---|---|
| "…skip verification for now, just get it rendering" | You get a lift-and-shift: injected legacy HTML that *looks* right, isn't React, and would trivially "pass" later | Always demand the parity report in the same turn (prompt C) |
| "Capture `<deep .do URL>`" | The oracle becomes a session-timeout/error page | The from-start workflow capture (prompt D) |
| "Add the nav tabs" (no source pointed at) | Copilot invents plausible-but-wrong tab names | "…the **exact tab labels from the captured dom.html**" |
| "Make it look nicer / more modern" | Violates 1:1; the structural gate fails; churn | "Match the captured screen exactly — only the framework changes" |
| "Build the whole app" | Long-run drift, invented content, nothing verified | One slice (C), or the guardrailed batch (G) |
| "Mock some data so it renders" | Hand-authored fakes — forbidden, and parity is meaningless | Record mode: `capture_fixtures.py --har` replaying the REAL captured responses |
| "Use the saved auth_state for the crawl/capture" (session-sensitive app) | Stale single cookie → every view lands on the app's error page | `--login --creds --project` (fresh from-start login) |
