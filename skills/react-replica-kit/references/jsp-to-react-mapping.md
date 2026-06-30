# JSP / Struts / Dojo → React + TS mapping

**Build from the source model; verify against the capture.** The view's `source-model.json` (from
`extract_jsp.py`) is the BUILD INPUT — it states the loops, conditionals, form fields, AJAX endpoints,
and message keys. The captured `model.json` + `dom.html` are the VERIFICATION target (the rendered
result to match). Port the rendered result, not the Dojo/jQuery framework — but get the structure from
source, don't reconstruct it by eyeballing the screenshot. See `legacy-crawl-capture/references/jsp-source-extraction.md`.

> **DO NOT inject the legacy HTML.** Never `dangerouslySetInnerHTML` (or paste) the recorded contentlet/AJAX HTML
> fragments to "render" a screen. That is lift-and-shift, not modernization: the code stays legacy markup, it can't
> be restyled or maintained, and it silently passes `verify_screen` because injected legacy HTML *is* the legacy
> DOM. The recorded AJAX responses are the **DATA source** — extract the values (table rows/cells, fields, labels)
> into typed props and render them through **real React components**. Also build the app **shell** (nav tabs, header,
> the panel layout), not just the inner fragments. If a "React" view is really an HTML dump, it's rejected.

## Construct mapping

| Legacy construct | Rendered as | React + TS equivalent | Notes |
|---|---|---|---|
| `<%@ include file="x.jspf" %>` / Tiles insert | inline fragment | child component `<X/>` | one fragment → one component; keep the same DOM nesting |
| `<c:if test>` / `<% if %>` scriptlet | conditional region | `{cond && <…/>}` / ternary | drive from fixture/state, never invent the branch |
| `<c:forEach items>` / JSP loop | repeated rows | `items.map(...)` | same element shape per row |
| Struts `<html:form action="x.do">` + ActionForm | `<form>` POST | controlled `<form onSubmit>` → POST same `x.do` | keep field `name`s identical (they're the contract) |
| `<html:text property="acct"/>` | `<input name="acct">` | `<input name="acct" value=… onChange=…/>` | name/type/placeholder must match exactly |
| jQuery dataTables / clusterize grid | `<table>` with thead/tbody | plain `<table>` (or minimal virtualized list) | columns IN ORDER; no library that restyles |
| Dojo widget (dijit) | the DOM it expands to | plain elements matching that DOM | inspect captured `dom.html`; reproduce output, drop Dojo |
| `<bean:message key="x"/>` / `.properties` lookup | resolved label text | the **exact captured string** as a literal | do NOT re-translate or "improve" copy |
| server-rendered data baked in HTML | static text/rows | render from the REAL data (record: HAR replay / live: proxy) | same values the screenshot showed |
| later XHR/ajax populating a region | dynamic content | `useEffect`→`apiFetch(same path)`; real response (record/live) | endpoint from `source-model.ajaxEndpoints`; same path |
| `<img src="platform/images/x.svg">` | icon/image | `<img src="/assets/x.svg">` reuse the SAME asset | copy the asset; never recreate it |
| inline `onclick="location.href='y.do'"` | navigation | `onClick`→ route/POST to same target | preserve the action/target |

## "No new artifacts" — the hard rules

You may ONLY change the framework. You may NOT change what the user sees.

**Must match exactly** (DOM-lane gate enforces): every visible label and copy string, field order, tab
order, table columns (set + order + header text), validation/error text, the set of controls, the set of
visible elements, and reused asset identity.

**Must not do:** add a control/link/tooltip/empty-state the legacy screen doesn't have; remove one it
does; reword, re-case, or re-translate any copy; reorder fields or columns; swap an icon; introduce a
component-library look; add spacing/padding "to make it nicer"; collapse two states into one.

**May do:** use React/TS idioms (components, hooks, props, state), CSS Modules class names of your choosing
(the *class name* is internal; the *computed style* must match), and a router. Internal structure is free;
observable output is frozen.

## Forms & data wiring (REAL data — see backend-data-modes.md)

- Get the fields from `source-model.forms[]`; keep input `name` attributes identical to the ActionForm
  properties — they are the request contract and the parity key.
- Fetch through `src/api.ts` on the same `*.do` / REST path (from `source-model.ajaxEndpoints`). In **record**
  mode MSW replays the REAL recorded response; in **live** mode the Vite proxy hits the real backend with the
  session. Same path either way — never hand-author data.
- Validation messages come from `source-model.messageKeys` / the captured screen (`[MSG:bundle:key]`) —
  reproduce the exact text and the exact trigger; don't invent client validation the legacy screen lacks.

## When evidence is incomplete

If a visible state has no captured screenshot/DOM AND no source model, STOP and have the driver agent
(analysis mode) capture/parse it — do not infer layout, copy, columns, or controls. Never build from a quarantined
(`_rejected/`) error capture. (Mirrors fig2code's Missing State Protocol and "no visual inference".)
