# How it works (plain-English explainer)

A guide you can read to understand the system — and use to explain it to others. For setup steps see
[SETUP.md](../SETUP.md); for the technical entry point see [README.md](../README.md).

## The 30-second version

> We have a big old web app (Java/JSP/Struts). We want a modern version that looks and behaves *exactly* the
> same. This toolkit is a set of instructions + small tools that let GitHub Copilot do it automatically: it
> logs in, **reads the old screen's actual source code** (the JSP/AJAX) and **extracts the real color/font
> theme**, finds **every view — including the ones that load by AJAX** (the tabs and menus behind one link),
> and rebuilds each in **React from that source**, fed the **real backend data**. In full‑stack mode it also
> **reads the old server code** (which stored procedure each screen calls) and generates a matching **Spring
> Boot** service that returns the same data. Then it **mathematically checks** that the new version matches the
> original — view by view, field by field — instead of eyeballing it, and hands the AI a punch‑list to fix.

It runs in **two modes**: *full* (React **+** Spring Boot) or *frontend* (React only — the simpler fallback).

## The problem

A legacy app is hundreds of JSP/Struts screens with old JavaScript (Dojo, jQuery) and a data layer of stored
procedures behind Java DAOs. Rebuilding it by hand is slow, and "does the new screen really match the old one?"
is usually a judgment call. We need it **automatic**, **reusable for any such app**, and the match **provable**.

## The idea in one line

Point a spec‑driven agent at a **live running legacy screen + its source code** (JSP, AJAX, CSS, and the Java
data layer), build the new UI **and** API **from that source**, and replace "the AI looks at two pictures and
decides" with a **deterministic check** that produces a punch‑list of differences.

## The cast (who does what)

One **driver agent** (the instruction manual the AI follows — `modernize-flow` in full mode, `jsp2react` in
frontend mode) and four **skills** (small toolkits it runs):

| Piece | Role |
|---|---|
| **The driver agent** | Two modes. *Analysis:* log in, extract the theme, find every view (incl. AJAX, from the start), **parse each JSP into a "source model,"** (full) **trace the server code to its stored procedure**, capture everything. *Implementation:* one slice at a time, rebuild it from the source, feed real data, prove it matches. |
| **legacy-crawl-capture** | Parses the JSP source, finds every view (static + AJAX), captures each (screenshot + structure + the real responses), and quarantines error pages. |
| **react-replica-kit** | Extracts the theme, sets up the React app (real‑data wiring + login), builds each view, and makes a navigable review index. |
| **parity-verify** | The frontend proof engine — compares old vs new (structure, style, and that the real data rendered) and reports exactly what differs. |
| **springboot-target-kit** *(full mode)* | Traces action→service→DAO→**stored procedure**, generates the Spring Boot endpoint (controller→service→gateway→DTO), and proves its JSON reproduces the **recorded real data**. |

It also **reuses tools the pod already has** instead of reinventing them: the login tool, the screenshot tool,
the browser/testing tool, and the team memory. And it's **generic** — the app‑specific details (web address,
login, screen families, colors, database) live in one small `project.json`, so the same toolkit works on the
next app too.

## The loop (how one slice gets built)

```
1. Read status.md            → what's done, what's next (keeps the AI on track over a long run)
2. Read the SOURCE MODEL     → the parsed JSP (loops, fields, labels, which click loads which data)
   + theme (+ backend model)   + the real theme; (full) the stored proc + its inputs/columns. The screenshot is only the CHECK.
3. Build it 1:1 FROM SOURCE  → React from the source; (full) a Spring Boot endpoint from the backend model
4. Feed it the REAL data     → record (replay recorded responses) / live (proxy the real backend) / api (the new endpoint)
5. PROVE it matches          → run the checks; pass/fail + exactly what differs (incl. "data missing")
6. Fix from the list         → repeat 5–6 until it passes
7. Mark it verified, move on → update status.md, regenerate the index, next slice
```

The trick that keeps a long run from going off the rails: **one control/slice per turn, tracked in a checklist
file (status.md)** with rows as fine‑grained as a single dropdown or table. The AI never holds the whole app at once.

## How we "prove" a match (the important part)

A slice passes only when a **script — not the AI's opinion** — says so.

**Frontend (every mode):** three checks. (1) **Structure** — every label, column, field order, tab order,
validation message, control must match *exactly* (catches "Acct #" vs "Account #"). (2) **Data** — the React side
actually rendered the **real data**, not an empty/half‑loaded table. (3) **Picture** — pixel‑by‑pixel, pointing at
*which element* is off; exact in record mode, advisory in live mode (font anti‑aliasing ignored; real
layout/spacing/color is not).

**Backend (full mode):** the new Spring Boot endpoint's JSON is compared against the **recorded real response**
from the old app (the same HAR file the capture saved). Every field the old response had must be present, with the
right type — and in record mode the same values. A missing field fails. *Same oracle, no new mechanism.*

The output is a short report saying *what* is different and *where*, so the AI makes a small targeted fix and
re‑checks. **The AI fixes from facts; it never decides "good enough" by eye.**

## How it gets real data (never fakes)

The copy must show **real backend data**, never hand‑made dummy data. Picked per slice:

- **record** — at capture we save the screen's *actual* responses to a file (a HAR). The React app replays those
  exact real bytes, so the picture check is exact. No live backend needed to render.
- **live** — the React app talks to the *real* backend through a dev proxy, reusing the login session — real‑time
  data; the match is judged on structure/style.
- **api** *(full mode)* — the React app calls the **new Spring Boot endpoint**, which calls the **same stored
  procedure** the old DAO used. That endpoint is itself checked against the recorded real response.

The login screen is rebuilt for real, so its session is what authorizes every data call.

## The promises it keeps

- **Exact copy (1:1):** built from the **source** (JSP for the UI, the Java/stored‑proc layer for the data), not
  guessed from a picture; enforced by the structure check + "never guess a view you haven't captured or parsed."
- **Nothing new added:** plain HTML/CSS, no UI component library, colors/fonts from the **extracted legacy theme**;
  the API speaks clean JSON without leaking JSP/Struts concepts. Only the framework changes, never the appearance.
- **Real data, never fakes:** every slice shows real backend data (recorded‑and‑replayed, live, or via the new SP‑backed endpoint).
- **No wrong pages slip through:** error/half‑loaded pages are detected and quarantined, never accepted.
- **Proven, not claimed:** a slice is "done" only when the check scripts pass; a generated **INDEX page** lists
  every view with its status (and, full mode, its backend‑contract result) for a human to glance at.
- **Reusable:** one `project.json` makes it work on any legacy JSP/Struts app, not just one.

## What `bash install.sh` actually does

Nothing magic — it's a **file copier with safety checks**. GitHub Copilot discovers skills in
`~/.copilot/skills/` and agents in `~/.copilot/agents/`; this repo is just the source of those files.
Running `bash install.sh full` (or `frontend`):

1. **Removes the old copies** of this toolkit's own skills + agents from `~/.copilot` — only files this
   toolkit owns, matched by name; your other skills and agents are never touched. This is why it's called
   a *clean install*: after every `git pull`, re-running it guarantees the pod runs the new files, never
   a stale mix of old and new.
2. **Copies in the chosen mode's set** — `full`: 4 skills + the `modernize-flow` agent; `frontend`:
   3 skills + the `jsp2react` agent (no Spring Boot kit). Omitting the mode means `full`.
3. **Installs the two pixel-diff packages** (`npm install` inside the `parity-verify` skill).
4. **Checks prerequisites** and prints exactly what's missing and how to get it (Node, Python +
   Playwright + a *launchable* browser; full mode also a JDK + Maven/Gradle). Checks only — it never
   installs anything system-wide itself.

It's safe to run repeatedly, and running the other mode cleanly switches modes. The whole update
routine is two commands: `git pull && bash install.sh full`.

## What you actually run

Install once, choosing a mode (`bash install.sh full` or `frontend`), then tell Copilot to run the
**`modernize-flow`** (or **`jsp2react`**) agent with just the **legacy URL, how to log in, and a `project.json`**.
The agent sets up its own tracking file (status.md), extracts the theme, discovers every view, parses the source
(and, full mode, the data layer), and captures everything — you don't configure screens by hand. Then run it
repeatedly (one slice per turn). The exact prompts are in [SETUP.md §6b](../SETUP.md). A generated `INDEX.html`
plus a side‑by‑side review page let you and your colleagues compare originals against the replicas, view by view.

> Not sure full‑stack will work out? Start in **frontend mode** (React only, talking to the existing backend) —
> it's the safe fallback — and move to full mode later. Switching is just `bash install.sh full`.
