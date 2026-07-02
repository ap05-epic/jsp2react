# AJAX crawl & the view graph — finding the "30 views behind one link"

The legacy app's views aren't all static routes. One link opens a shell whose tabs, hover-menus,
dropdowns, and drill-downs load **30+ partial views over AJAX with no URL change**. Following `<a href>`
links (the static crawler) cannot see them. v2 adds a stateful crawler and one hard rule:

> **Never open a deep view by direct URL. Every view is reached by replaying a click-path FROM THE START.**
> (Struts is stateful; a direct jump bypasses the server-side setup and lands on an error/login page.)

## The two crawlers, reconciled into one `viewgraph.json`

**1. Static baseline** — `crawl_screens.py` (struts-config + JSP scan). Emit it as viewgraph states:
```bash
python scripts/crawl_screens.py --struts-config <…> --webapp-dir <…> \
  --out screens.json --emit-viewgraph static-viewgraph.json
```

**2. Stateful AJAX crawl** — `crawl_ajax.py` (Playwright), the view explosion, from the start:
```bash
python scripts/crawl_ajax.py --start-url <post-login summary> --login --creds login.env --project project.json \
  --merge static-viewgraph.json --out viewgraph.json \
  --max-states 40 --max-depth 3 --max-actions 25 --settle-ms 1500
```
`--login` does a fresh from-start login in the crawl context (same machinery as `capture_screen.py`) —
required for session-sensitive apps, where a saved `--auth-state` single cookie goes stale/rotates and
every crawled view then lands on the app's error page.
It BFS-walks UI states: from each state it re-navigates to the start, replays the parent click-path, then
probes each interactive element (link/button/tab/menuitem/hover-menu). A new DOM signature = a new view,
recorded with its **full from-start click-path** + the endpoint it triggered. Error-looking views are
recorded but not expanded. `--merge` folds in the static states (and any normalized Crawljax output).

Run it **per family/menu** (families come from `project.families`, or are auto-inferred) with deliberate
bounds; **log what you bounded** (no silent caps). Increase
`--max-*`/`--settle-ms` for deep or slow families.

## `viewgraph.json` schema
```jsonc
{ "start_url":"…","count":N,"errors":M,"states":[
  { "id":"v0007", "domSignature":"<sha1>", "isError":false, "label":"<View>",   // example: a "Compensation" tab
    "clickPathFromStart":[ {"selector":"#search","kind":"click","label":"Search"},
                           {"selector":"a.tab[data-tab=comp]","kind":"click","label":"<View>"} ],
    "triggeredEndpoints":["GET https://…/<ctx>/<flow>.do?tab=comp"],
    "title":"…","url":"…" } ] }
```
Each state becomes a status.md row. Its `clickPathFromStart` becomes the capture profile's `workflow`
(navigate/click/fill/select/wait) so capture and the React replay both reach it the same way.

## Crawljax (optional, OSS — exhaustive state-graph)
Crawljax (github.com/crawljax/crawljax, Apache-2.0) is purpose-built for event-driven AJAX discovery. Use
it when you want a more exhaustive automated state graph than the Playwright crawler. It's Java and in
maintenance mode, so treat it as an optional booster:
1. Run a Crawljax crawl of the start URL (its own config) to produce its state-flow output.
2. Normalize each Crawljax state to the schema above (id, domSignature, clickPathFromStart, triggeredEndpoints).
3. `crawl_ajax.py --merge crawljax.viewgraph.json` reconciles it (dedup by domSignature, union endpoints,
   keep the shortest from-start path).

## Rules
- A view with no from-start path is not a view you can faithfully reproduce — find the path or mark it blocked.
- Reconcile by `domSignature`: the same rendered state reached two ways is ONE view (shortest path wins).
- Error/login states discovered by the crawler are flagged `isError` and must not be promoted as real views
  (the capture step also quarantines them — see runtime-readiness-and-auth.md).
