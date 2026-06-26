<!--
  spec.md  —  jsp2react screen catalog & parity contract
  ------------------------------------------------------
  Written/refreshed by jsp2react-analyzer. Read selectively by jsp2react-builder
  (Section 1 once on first run, then only the assigned screen's section).

  This is the DURABLE baseline: what every legacy screen is, the evidence proving it,
  its states, its endpoints/data contracts, and its acceptance criteria. STATUS.md is the
  live journal; this file is the contract. Keep them reconciled.

  EVIDENCE TAGS (every visible requirement carries at least one):
    [SHOT:file.png]        captured legacy screenshot            — highest visual authority
    [DOM:selector]         from captured legacy rendered DOM     — structural authority
    [CSS:file:selector]    from captured computed styles         — exact style values
    [JSP:path:line]        confirmed in JSP/fragment source      — structure/conditionals
    [ACTION:Class#method]  Struts action / Spring controller     — behavior/forward/endpoint
    [ENDPOINT:METHOD path] the data call (struts .do / REST / WS-feign)
    [MSG:bundle:key]       exact label/validation text from a .properties bundle
    [ASSET:path]           existing icon/font/image to REUSE (never recreate)
    [INFERRED]             assumed, no direct evidence           — low confidence, keep easy to change
  Rule: NEVER infer a visible state. If a visible state has no [SHOT]/[DOM] evidence, capture it or
  mark the screen `blocked` in STATUS.md — do not invent layout, copy, columns, or controls.
-->

# <Project> — Screen Catalog & Parity Contract

## Section 1 — Legacy & Target Context  (read fully once)

**Legacy stack.** <e.g. Struts 1 + JSP (Tiles) on Spring Boot; client JS = Dojo/jQuery/dataTables;
server: struts/action → service → builder → dao → WS-feign (mainframe).>
**Where truth lives.** Rendered runtime DOM is the visual source of truth (Dojo/jQuery generate markup
at runtime — do not port the JS framework). `.properties` bundles give exact copy/validation text.
**Target conventions.** Fresh Vite + React + TS. One screen → one route + one component tree. Plain
HTML/CSS port via CSS Modules; no component library. MSW serves captured fixtures. (See react-replica-kit.)
**Naming.** Screen `F0xx` → `src/screens/<Name>/` (`<Name>.tsx`, `<Name>.module.css`, `handlers.ts`).

## Section 2 — Flow / Family Overview

| Family | Purpose | # Screens | Reach path (how to navigate there) | Key dependencies |
|--------|---------|-----------|-------------------------------------|------------------|
| shell | login + summary scaffold | <n> | entry URL → login → summary hydrates (~Ns) | — |
| fa | <…> | <n> | summary menu → … | FA context (e.g. AB10) |
| … | … | … | … | … |

**Recommended build sequence:** shell → <family> → … (foundational screens first).

## Section 3 — Per-Screen Specs

> One subsection per Screen Inventory row. Template below; copy per screen.

### F0xx — <Screen name>  ·  family: <fa>  ·  route: `<action.do>` → target `/<route>`

- **Description.** <what it is / what the user does here>
- **Reach path.** <exact runtime steps to navigate here from the summary shell, incl. waits/context>
- **Capture contract** (mirrors `profiles/<id_state>.json`; the builder reuses it to capture React):
  - canonical route: `<dispatcherAction.do?page=…&fanum=…>` (works only with a live session)
  - misleading routes (NOT verification targets): `<e.g. direct loginAction.do → error page>`
  - auth context: <pre-auth | authenticated via login-form submit; reuse auth_state.json> · viewport: `1920x1080`
  - readiness: waitFor `<#anchor>` · mustContain `<"Compensation","FA Profile">` · waitForGone `<.loadingMask>`
  - settle: `~Nms` after readiness (data-heavy detail screens need more — see runtime-readiness-and-auth.md)
  - expected assets: `<theme/…, platform/styleSheets/…>` (must be 200; styled-vs-unstyled guard)
  - known failure modes: <e.g. opening the .do without a session shows login; widgets hydrate ~Ns late>
- **Visible states** (enumerate ALL; each needs evidence):
  - default — [SHOT:f0xx_default.png] [DOM:#main]
  - empty — [SHOT:f0xx_empty.png]
  - error/validation — [SHOT:f0xx_error.png] [MSG:errors.properties:fa.required]
  - <tab/modal/expanded/selected/loading/read-only…>
- **Layout & controls** (the 1:1 inventory — copy, labels, field order, tab order, columns):
  - <region/control> — label "<exact>" [MSG:…] · order <n> · [CSS:f0xx.computed.json:.label]
  - table columns (in order): <Col1 | Col2 | …> [DOM:table#grid thead]
  - buttons/actions: <Go | Export PDF | Export Excel> [ASSET:platform/images/pdf.svg]
- **Endpoints / data contract** (what the screen calls; becomes the MSW fixture):
  | METHOD | path | layer (struts/REST/WS-feign) | request | response shape (→ fixture) | source |
  |---|---|---|---|---|---|
  | GET | <…/fateamprofile.do?…> | struts | <params> | <fields…> | [ACTION:FaTeamProfileAction] |
- **Assets to reuse.** [ASSET:theme/fonts/…] [ASSET:js/lib/ubs-icons/…]
- **Success criteria** (ALL must pass before `verified`):
  - [ ] legacy + React captures both `usable:true` (.capture.json: readiness passed, no asset 404)
  - [ ] parity-verify PASS for every visible state (0 critical structural deltas; pixel ≤ threshold)
  - [ ] copy/labels/validation text exact (DOM-diff clean)
  - [ ] field order, tab order, table columns exact
  - [ ] renders standalone from MSW fixture (no live backend)
  - [ ] endpoints wired to same paths (data-wiring QA, if in scope)

## Section 4 — JSP / Struts Inventory Reconciliation

Every `*.jsp` and every `struts-config` action is accounted for (mapped to a screen, a shared
fragment/bucket, or explicitly unresolved). Counts must reconcile against the repo.

- JSPs found in repo: <n>  ·  JSP rows recorded: <n>  ·  unmatched: <list>
- Struts actions found: <n>  ·  rows recorded: <n>  ·  unmatched: <list>

| JSP / action | type (screen/fragment/layout/contentlet/ipad/alt-root) | maps to | relationship (Tiles/forward/include) |
|---|---|---|---|
| <jsp/fateamprofile.jsp> | screen | F0xx | forward from fateamprofile.do |
| <jsp/inc/header.jspf> | fragment | shared:header | included by many |

## Section 5 — Open Questions

| # | Question | Status (RESOLVED/PENDING/N-A) | Default assumption to implement | Source |
|---|----------|-------------------------------|---------------------------------|--------|
| 1 | — | PENDING | — | — |

## Appendix A — Target File Tree (to create)
<the React app screens/components to create, mirroring Section 3 IDs>

## Appendix B — Shared Types / API Contracts
<TypeScript interfaces for the endpoint responses captured as fixtures>
