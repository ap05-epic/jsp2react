# Runtime readiness & auth — making captures *real*, not just *rendered*

A screenshot that "rendered" is not automatically valid parity evidence. On a real legacy
JSP/Struts app (local Tomcat, enterprise session behavior, async data) a capture can look fine
and still be wrong: unstyled HTML, an error page behind a misleading route, or a screen captured
before its backend data hydrated. This reference is the runbook for avoiding that. It is grounded
in a real local run of the BAA app; the rules generalize to any legacy app this system targets.

> **Quick-screenshot vs evidence.** `snapshot_single.py` (webapp-snapshot) is a *quick visual
> check*. **`capture_screen.py` is the authoritative parity/evidence capture** — it enforces the
> readiness contract below and writes a `.capture.json` sidecar that marks whether the capture is
> `usable`. Only `capture_screen.py` output is admissible as parity evidence. Never blur the two.

---

## 1. Pre-capture triage (run ONCE before crawling/capturing anything)

Do not start capturing screens until the app is actually capture-ready. Confirm, in order:

1. **Login page reachable** — e.g. `GET http://127.0.0.1:8080/<ctx>/jsp/login.jsp` returns 200 and the form.
2. **Auth works end-to-end** — submitting the real login form lands on the authenticated app, and a
   reusable session can be saved (`save_auth_state.py` → `auth_state.json`).
3. **The real post-login route is valid** — you can reach an authenticated dispatcher route *after*
   login (not a standalone error page — see §4).
4. **Assets return 200** — the main stylesheet(s) and scripts load (no 404s on `theme/`,
   `platform/styleSheets/`, etc.). `capture_screen.py` records per-asset status automatically.
5. **At least one data-heavy page actually hydrates** — pick a representative detail screen and
   confirm its backend-driven content appears (not just the page chrome).

If any step fails, fix it (or document the blocker) **before** mass capture. A single bad runtime
assumption multiplied across hundreds of screens is the most expensive failure mode. This triage exists
because one real local run (BAA) was "reachable + login partially worked" yet deeper session continuity
and styling were still broken — capturing then would have produced a folder of confident-wrong PNGs.

**Triage checklist (the agent confirms all before capture begins):**
- [ ] app reachable  - [ ] auth working  - [ ] assets loading 200
- [ ] canonical route confirmed  - [ ] readiness checks defined  - [ ] viewport fixed  - [ ] output paths chosen

---

## 2. "Page loaded" ≠ "screen usable" — semantic readiness

`networkidle` alone is **not** sufficient for these apps. In one real app (BAA), data-heavy sections
(e.g. Compensation, ranking, profile, practice-management) populate asynchronously *after* the first HTML
and after network goes idle. Treat a page as captured only when its *meaning* is present.

`capture_screen.py` enforces readiness in this order (each step is optional per screen; configure via
the capture profile — see §7):

1. **wait for selector** — a structural anchor exists (`--wait-for "#pmenu"`).
2. **wait for required text markers** — the real content is present
   (e.g. `--must-contain "Compensation"`). This is the strongest signal that
   backend data actually arrived, not just the shell.
3. **wait for spinner/mask to disappear** — `--wait-for-gone ".loadingMask"`.
4. **fonts settle** — `document.fonts.ready` (automatic).
5. **small final settle** — `--wait-ms` as the **last** step, not the strategy.

> Prefer semantic readiness over raw sleeps. `--wait-ms` is a safety margin, not the mechanism. A
> screen that needs a 13-second blind sleep to look right is a screen whose real readiness signal you
> haven't identified yet — find the selector/text/mask instead, then add a small settle on top.

Each readiness check's pass/fail is recorded in the `.capture.json` sidecar, and the capture is only
flagged `usable: true` when **all configured readiness checks passed and no expected asset failed**.

---

## 3. Timing rules (example calibration from BAA; tune per app)

For data-heavy authenticated pages, after live navigation reaches `networkidle`:

- **Normal authenticated pages:** wait **≥ ~5s** for backend sections to populate.
- **Deep detail screens (example: an `<entity>` like AB10):** wait **~8s more** (≈13s total) — the
  data-heavy sections (e.g. Compensation, ranking, profile) settle late, and theme/fonts stabilize
  slightly after the initial HTML render.

Encode these as `waitMs` in the per-screen capture profile, *on top of* the semantic readiness checks
in §2 — never as a replacement for them. These numbers are a starting calibration from one machine;
the readiness selectors/text are what make the capture correct, the settle time just absorbs jitter.

---

## 4. Canonical route vs misleading route

Record, per screen family, **how to legitimately reach the authenticated state** — and which routes
*look* right but aren't:

- **Misleading route (do NOT use as a verification target):** opening the app's login action directly
  (e.g. `/<ctx>/loginAction.do`, from `project.loginAction`) shows a **standalone error page**, not the
  logged-in UI. A direct GET of a `*.do` action that
  normally runs mid-session will route to login/error.
- **Canonical authenticated route:** submit the **real login form**, let the app navigate into the
  authenticated flow, then verify the resulting **dispatcher** page. For deep links the stable shape is:
  `dispatcherAction.do?page=<page>&fanum=<entity>&entityLevel=<level>`
  e.g. `http://127.0.0.1:8080/<ctx>/dispatcherAction.do?page=<flow>&fanum=AB10&entityLevel=COM9999`
  This works **only with a live logged-in session** — reuse `auth_state.json` (`--auth-state`) or run
  the login workflow first (`--profile` with a `workflow`).
- **Routes that only work after a workflow step** (a form submit, a quick-search for an entity like
  `AB10`) belong in a reusable workflow JSON, not as a bare URL.

The driver agent (analysis mode) records the canonical route, the misleading routes, and any required
workflow step in the screen's capture profile and in `spec.md`, so the implementation step never
re-discovers this by trial and error.

---

## 5. localhost / non-SSO troubleshooting

Local Tomcat deployments with explicit (non-SSO) login fail in ways that *look* like login bugs but
are actually deeper session/route assumptions. Distinguish three failure classes:

| Symptom | Likely class | Tell |
|---|---|---|
| Login form rejects creds / no redirect | **Auth** | never reach any authenticated page |
| Logged in, but deep navigation 500s/redirects to error | **Session continuity** | login OK, then dispatcher route dies |
| Page renders but looks like raw HTML | **Assets** | stylesheet/script URLs non-200 (see §6) |

Specific localhost gotchas seen in one real app (and the kind of source fix that resolved them — for
context when the blocker is runtime logic, not browser automation):

- The app tried to **recover auth through enterprise platform/SSO paths** that don't exist on local Tomcat,
  turning a missing-platform-cookie into a fatal relogin. Fixed in the **main dispatcher action** (local
  explicit-login no longer forces a fatal platform relogin when platform cookies are absent).
- A **base-action session check** applied **localhost-only timeout/error** behavior from the missing
  platform context on `localhost`/`127.0.0.1`, blocking deep navigation (e.g. a quick-search for an entity).
  Fixed by bypassing that check on localhost.

You don't need these exact files — the point is: **session continuity failures after a successful
login are usually platform/GCS assumptions, not credentials.** Look there before blaming login.

Credentials for the local app live in the app repo (e.g. a `login.env`); reference
them via env, never hard-code secrets into a profile.

### 5b. Session-sensitive screens — capture with a FRESH from-start login, not a saved cookie

A saved `auth_state.json` is often just **one `JSESSIONID` cookie**. For a protected, AJAX-hydrated screen
that depends on session state established by navigating the post-login landing first, replaying that lone
cookie into a fresh browser context **fails**: the server rejects/rotates it and serves a "Session timeout"
error page (it issues a new `Set-Cookie` and never fires the contentlet AJAX). The cookie expired, or it was
never sufficient for that flow.

The tell: the request **sends** your `JSESSIONID`, the server **responds with a new one** + the timeout page,
and **no contentlet AJAX runs**. That is a session-sensitive screen.

**Fix — let `capture_screen.py` log in fresh, in the same context it captures from:**
```bash
capture_screen.py --login --project work/project.json --creds login.env \
  --url '<dispatcher …deep route>' --record-har --name <view>_legacy --out-dir work/evidence/<view>
```
`--login` (or a profile's `"login": true`) does the proven flow — GET the login page → fill
`loginFields` → submit → land (warming the session) — then navigates the deep route in the **same** browser
context, so the session is valid for the protected route. Use `--check-login` first to confirm auth alone.

The canonical recovery this mirrors (provable with curl from one cookie jar — login page → POST login →
reuse the new `JSESSIONID` → GET the dispatcher route returns the real screen):
```bash
curl -c jar -b jar  <base>/<ctx>/jsp/login.jsp -o /dev/null
curl -c jar -b jar -e <base>/<ctx>/jsp/login.jsp -d 'user=$U&password=$P' <base><loginAction>   # warms the session
curl -c jar -b jar  '<base>/<ctx>/dispatcherAction.do?login=true&page=<flow>'                    # real screen HTML
```
If even `--login` stalls, it's not auth — the capture now writes partial artifacts + a `nav_error` (exit 2)
instead of hanging, so inspect the `_rejected/` HAR/PNG to see where it died. Browser not launching at all →
`python -m playwright install chromium` (Linux: also `playwright install-deps`) or `--channel chrome|msedge`.

---

## 6. Styled-vs-unstyled detection

Several early screenshots (on the BAA app) were wrong because saved HTML was rendered **without a live
`/<ctx>/` base URL**, so relative CSS/JS didn't resolve — the page rendered as raw unstyled HTML. Always
capture against the **live local app base**, never a detached `.html` file.

`capture_screen.py` warns when a page probably didn't load correctly, using these signals:

- expected stylesheet/script/font URLs return **non-200** (tracked per asset);
- major CSS assets missing;
- computed `body` font unexpectedly falls back to a bare serif/sans default (a hint that theme CSS
  never applied).

When `usable` is false or warnings list asset failures, **do not** treat the PNG as parity evidence —
fix the asset/base-URL problem and recapture.

---

## 7. The per-screen capture contract (and why the agent reuses it)

Everything above is captured, per screen, in a machine-readable **capture profile** (see
`templates/capture-profile.json`). One profile records: canonical route, required auth context,
viewport, readiness selectors/text, spinner-gone selector, settle timing, expected assets, and known
failure modes.

- The driver agent (**analysis mode**) writes one profile per screen and stores it with the evidence.
- `capture_screen.py --profile <file>` consumes it to capture the **legacy** side.
- The driver agent (**implementation mode**) reuses the **same profile** (same viewport, readiness
  criteria, settle timing, key content expectations) to capture the **React** side.

Comparable captures are the precondition for a trustworthy parity diff: if legacy waited for
`Compensation` text at 1920×1080 with an 8s settle, the React capture must do the identical thing.
This is how readiness becomes deterministic and reruns stop requiring manual re-debugging.

---

## 8. Source-backed debugging before declaring a blocker

For local modernization, the blocker is often **app runtime logic**, not browser automation. Before
marking a screen `blocked`, and when capture repeatedly fails for the same screen, the agent (analysis
mode) is permitted (and expected) to investigate the **app source** to explain the failure:

- inspect session/auth code (the base action, the dispatcher action, login filters);
- identify localhost-only assumptions (platform/SSO cookie checks);
- trace a broken post-login route to the action that rejects it;
- report precisely when a **runtime patch** is required vs. when it's a capture-config problem.

Declare `blocked` only after this source-backed pass, and record *what* in the runtime is broken
(file + reason) so a human can patch it — not just "capture failed."

---

## 9. Recovery from reset evidence

If `status.md` or the evidence folder is wiped, the essential capture knowledge is **not** lost: it
can be rebuilt from (a) source discovery (struts-config, JSP links), (b) this runbook, and (c) the
saved capture profiles. The agent rebuilds status.md and re-captures from those, rather than
depending on prior-session chat notes.
