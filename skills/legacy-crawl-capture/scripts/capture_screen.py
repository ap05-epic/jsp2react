#!/usr/bin/env python3
"""
capture_screen.py — capture ONE screen state as comparable evidence.

This is the single capture path used for BOTH the legacy screen and the React render,
so the two sides are always normalized identically and can be diffed deterministically.

Outputs (in --out-dir, prefixed by --name):
  <name>.png            screenshot at the exact viewport
  <name>.dom.html       raw page.content() (debug / reference)
  <name>.model.json     NORMALIZED structural model (the artifact parity-verify diffs)
  <name>.a11y.json      accessibility snapshot
  <name>.network.json   document/xhr/fetch responses (bodies for json/text, size-capped)

The .model.json schema is the contract consumed by parity-verify/dom_diff.py. Capturing the
legacy page and the React page with THIS script guarantees both models are shaped the same.

Requires Playwright (already on the pod via the webapp-testing skill):  pip install playwright ; playwright install chromium
"""
import argparse, json, sys, os, hashlib, datetime

# Curated computed-style properties — the ones that matter for 1:1 visual/structural parity.
STYLE_PROPS = [
    "display", "position", "visibility", "box-sizing",
    "font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing",
    "text-align", "text-transform", "text-decoration-line", "white-space",
    "color", "background-color", "opacity",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "border-top-style", "border-top-color", "border-radius",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "width", "height", "min-width", "min-height",
]

# In-page extractor. Returns a JSON-serializable normalized model. Runs in BOTH legacy and react pages.
EXTRACTOR_JS = r"""
(STYLE_PROPS) => {
  const SKIP = new Set(["SCRIPT","STYLE","NOSCRIPT","META","LINK","HEAD","TEMPLATE"]);
  const out = { title: document.title, url: location.href,
                viewport: {w: window.innerWidth, h: window.innerHeight},
                elements: [], tables: [], forms: [] };

  function visible(el){
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    return true;
  }
  function ownText(el){
    let t = "";
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.nodeValue;
    return t.replace(/\s+/g, " ").trim().slice(0, 400);
  }
  function accName(el){
    return (el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("alt") || "").trim().slice(0,200);
  }
  function styleOf(el){
    const cs = getComputedStyle(el); const o = {};
    for (const p of STYLE_PROPS){ o[p] = cs.getPropertyValue(p); }
    return o;
  }

  // depth-first walk; path = stable child-index chain (e.g. "0/2/1"), idx = DOM order
  let idx = 0;
  function walk2(el, path){
    if (!el || el.nodeType !== 1 || SKIP.has(el.tagName) || !visible(el)) return;
    const r = el.getBoundingClientRect();
    const cls = (typeof el.className === "string") ? el.className : (el.getAttribute("class") || "");
    const rec = { i: idx++, path, tag: el.tagName.toLowerCase(), id: el.id || "", classes: cls.trim(),
      role: el.getAttribute("role") || "", name: accName(el), text: ownText(el),
      box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      style: styleOf(el), tabindex: el.getAttribute("tabindex"),
      href: el.tagName === "A" ? (el.getAttribute("href") || "") : null, input: null };
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON"){
      rec.input = { name: el.getAttribute("name") || "", type: (el.getAttribute("type") || tag.toLowerCase()),
        placeholder: el.getAttribute("placeholder") || "", value: (el.value !== undefined ? String(el.value).slice(0,200) : ""),
        disabled: !!el.disabled, required: !!el.required };
      if (tag === "SELECT") rec.input.options = Array.from(el.options).map(o => (o.text||"").trim()).slice(0,200);
    }
    out.elements.push(rec);
    let ci = 0;
    for (const c of el.children){ walk2(c, path + "/" + ci); ci++; }
  }
  walk2(document.body, "0");

  // tables: ordered column headers + row count (column order is a parity-critical signal)
  for (const t of document.querySelectorAll("table")){
    if (!visible(t)) continue;
    const headers = Array.from(t.querySelectorAll("thead th, thead td"))
                      .map(h => ownText(h)).filter(x => x.length);
    const rows = t.querySelectorAll("tbody tr").length;
    out.tables.push({ headers, rowCount: rows });
  }
  // forms: field order + labels (validation/labelling parity)
  for (const f of document.querySelectorAll("form")){
    const fields = [];
    let order = 0;
    for (const el of f.querySelectorAll("input,select,textarea,button")){
      let label = "";
      if (el.id){ const l = f.querySelector('label[for="'+el.id+'"]'); if (l) label = ownText(l); }
      fields.push({ order: order++, name: el.getAttribute("name")||"", type: el.getAttribute("type")||el.tagName.toLowerCase(), label });
    }
    out.forms.push({ action: f.getAttribute("action")||"", method: (f.getAttribute("method")||"get").toLowerCase(), fields });
  }
  return out;
}
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_viewport(s):
    w, h = s.lower().split("x")
    return {"width": int(w), "height": int(h)}


def run_workflow(page, steps, timeout, settle_ms):
    """Navigate to a deep state before capture. Action vocabulary mirrors webapp-snapshot."""
    for st in steps:
        a = st.get("action")
        if a == "navigate":
            page.goto(st["url"], wait_until="domcontentloaded")
            settle(page, timeout, settle_ms)
        elif a == "click":
            page.click(st["selector"])
        elif a == "fill":
            page.fill(st["selector"], st.get("value", ""))
        elif a == "select":
            page.select_option(st["selector"], st.get("value"))
        elif a == "wait":
            if "selector" in st:
                page.wait_for_selector(st["selector"], timeout=st.get("timeout", 30000))
            else:
                page.wait_for_timeout(st.get("ms", 1000))
        else:
            raise SystemExit(f"unknown workflow action: {a!r}")


def load_profile(path):
    return json.load(open(path, encoding="utf-8")) if path else {}


def load_project(path):
    if not path:
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def settle(page, timeout, settle_ms):
    """Bounded, swallowed network-settle (mirrors crawl_ajax.settle). A session-sensitive / AJAX page with
    keepalive or long-poll XHR never reaches 'networkidle', so wait_until='networkidle' on goto blocks
    forever — this caps the wait and degrades instead of hanging."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    if settle_ms:
        page.wait_for_timeout(settle_ms)


def launch_browser(p, channel=None):
    """Launch bundled Chromium; if it isn't installed, fall back to a system Chrome/Edge channel."""
    attempts = [dict(channel=channel)] if channel else [dict(), dict(channel="chrome"), dict(channel="msedge")]
    last = None
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, **kw)
        except Exception as e:
            last = e
    raise SystemExit("Could not launch a browser (%s). Install one with:  python -m playwright install chromium  "
                     "(Linux: also `playwright install-deps`), or pass --channel chrome|msedge for a system browser." % last)


def _read_env_file(p):
    vals = {}
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def load_creds(path, anchors=None):
    """Resolve login creds from a KEY=VALUE env file. If `path` doesn't exist, search for a file with that
    basename (default login.env) in the anchor dirs and a few parent levels — so the conventional creds file
    is found even when it lives at the app root rather than next to project.json. Values are never logged."""
    name = os.path.basename(path) if path else "login.env"
    candidates = [path] if path else []
    for a in (anchors or []):
        d = os.path.abspath(a)
        for _ in range(4):                       # the file + a few levels up from each anchor
            candidates.append(os.path.join(d, name))
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
    candidates.append(name)                      # bare basename in CWD
    seen = set()
    for c in candidates:
        c = os.path.abspath(c)
        if c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c):
            return _read_env_file(c)
    return {}


def cred_value(creds, primary, fallbacks):
    """Case-insensitively pull a credential from the creds dict by the configured field name, then common
    variants — so a login.env keyed USERNAME=/PASSWORD=/userId= still works without matching loginFields exactly."""
    lower = {k.lower(): v for k, v in (creds or {}).items()}
    for k in [primary] + fallbacks:
        v = lower.get((k or "").lower())
        if v:
            return v
    return None


def login_url_for(proj):
    if proj.get("loginUrl"):
        return proj["loginUrl"]
    base = (proj.get("legacyBaseUrl") or "").rstrip("/")
    ctx = proj.get("contextRoot") or ""
    return base + ctx + "/jsp/login.jsp"   # convention fallback when init_project didn't record loginUrl


def do_login(page, proj, creds, timeout, settle_ms):
    """Fresh from-start login IN this browser context, warming the session for protected routes — the robust
    path for session-sensitive screens where a saved single-cookie auth_state is stale/insufficient. Mirrors
    the proven flow: GET login page -> fill -> submit -> land."""
    fields = proj.get("loginFields") or {}
    uf, pf = fields.get("user", "username"), fields.get("password", "password")
    user = cred_value(creds, uf, ["user", "username", "userid", "uid", "login"]) or os.environ.get("LEGACY_USER")
    pw   = cred_value(creds, pf, ["password", "passwd", "pass", "pwd"]) or os.environ.get("LEGACY_PASS")
    if not user or not pw:
        raise SystemExit(
            "--login: no credentials found. Provide them ONE of these ways (do NOT commit creds):\n"
            "  - a gitignored creds file next to your project.json named login.env with lines:\n"
            "        %s=...\n        %s=...\n"
            "  - pass --creds <path/to/login.env>, or set \"credsFile\" in project.json to that path\n"
            "  - or export LEGACY_USER / LEGACY_PASS in the environment" % (uf, pf))
    page.goto(login_url_for(proj), wait_until="domcontentloaded")
    settle(page, timeout, settle_ms)
    page.fill("input[name='%s']" % uf, user)
    page.fill("input[name='%s']" % pf, pw)
    try:
        page.click("input[type=submit], button[type=submit], button:not([type])", timeout=timeout)
    except Exception:
        page.press("input[name='%s']" % pf, "Enter")   # form with no explicit submit button
    settle(page, timeout, settle_ms)


def login_ok(title, final_url, still_login, error_signatures, login_basename):
    """Did login succeed? An authenticated app can legitimately LAND on its login-action route (the post-login
    landing), so the login basename is NOT an error signal here — judge by the password field being gone + the
    HARD error signatures (case-insensitive; the login basename is excluded). Generic: no app names."""
    blob = (title + " " + final_url).lower()
    lb = (login_basename or "").lower()
    hard = [s for s in error_signatures if s and s != lb]
    is_error = any(s in blob for s in hard)
    return (not still_login) and (not is_error)


def redact_har(har_path, login_basename):
    """Strip credentials from the saved HAR: the login POST body + cookie/auth headers on the login request.
    The repo is public and HAR embeds request bodies — the password must never land in an artifact."""
    if not login_basename or not os.path.exists(har_path):
        return
    try:
        har = json.load(open(har_path, encoding="utf-8"))
        for e in har.get("log", {}).get("entries", []):
            req = e.get("request", {})
            if login_basename in (req.get("url") or "").lower():
                if req.get("postData"):
                    req["postData"]["text"] = "[REDACTED]"
                    for pp in (req["postData"].get("params") or []):
                        pp["value"] = "[REDACTED]"
                for h in (req.get("headers") or []):
                    if h.get("name", "").lower() in ("cookie", "authorization"):
                        h["value"] = "[REDACTED]"
        json.dump(har, open(har_path, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass


def safe_sha(p):
    return sha256(p) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser(description="Capture one screen state as comparable evidence (png + normalized model + a11y + network + capture metadata) with semantic readiness.")
    ap.add_argument("--url", help="URL to capture (legacy screen OR react render). May instead come from --profile.")
    ap.add_argument("--out-dir", help="Directory for output artifacts. Required for a real capture (not --self-check).")
    ap.add_argument("--name", help="Base name, e.g. f010_default. Required for a real capture (not --self-check).")
    ap.add_argument("--profile", help="Capture-profile JSON (url/workflow/viewport/readiness markers). CLI flags override its keys. Use the SAME profile for the legacy AND react capture so both sides are comparable.")
    ap.add_argument("--auth-state", help="Playwright storage_state json (login reuse; from save_auth_state.py).")
    ap.add_argument("--viewport", help="WIDTHxHEIGHT; use the SAME value for legacy and react (default 1920x1080).")
    ap.add_argument("--wait-for", help="CSS selector that must APPEAR before capture.")
    ap.add_argument("--must-contain", action="append", default=None, help="Text that must APPEAR before capture (repeatable). Proves the screen is USABLE, not just loaded.")
    ap.add_argument("--wait-for-gone", help="CSS selector that must DISAPPEAR before capture (e.g. a loading mask/spinner).")
    ap.add_argument("--wait-ms", type=int, default=None, help="Final settle wait, applied LAST after the readiness checks above (not the main strategy).")
    ap.add_argument("--readiness-timeout", type=int, default=30000, help="Max ms to wait for each readiness check.")
    ap.add_argument("--workflow", help="JSON file of navigate/click/fill/select/wait steps to reach a deep state before capture.")
    ap.add_argument("--full-page", action="store_true", help="Full scrollable page (default: viewport only, recommended for parity).")
    ap.add_argument("--body-cap", type=int, default=500_000, help="Max response body bytes stored per request.")
    ap.add_argument("--record-har", action="store_true", help="Record a HAR of the REAL backend responses (responses.har) so the React app can replay real data with no fakes.")
    ap.add_argument("--error-signature", action="append", default=None, help="Extra text that marks an error/wrong page (repeatable). Matched against title+url+body; a hit QUARANTINES the capture.")
    ap.add_argument("--project", help="project.json — supplies the app's login route + errorSignatures as quarantine markers (generic, not hardcoded), and (with --login) the login URL + fields.")
    ap.add_argument("--login", action="store_true", help="Perform a FRESH from-start login inside the capture context before navigating. The robust path for session-sensitive / AJAX screens; reads loginUrl/loginAction/loginFields from --project. Prefer this over a stale --auth-state.")
    ap.add_argument("--check-login", action="store_true", help="Auth probe: log in, print the post-login url/title, exit 0 if authenticated (no password field / not an error page) else 2. Verifies auth in ISOLATION from capture.")
    ap.add_argument("--creds", help="KEY=VALUE env file with login creds (default: login.env). Also honors LEGACY_USER/LEGACY_PASS env vars. Keep it gitignored — never commit creds.")
    ap.add_argument("--channel", help="Browser channel chrome|msedge instead of bundled Chromium (for pods where only a system browser is installed).")
    ap.add_argument("--settle-ms", type=int, default=None, help="Fixed wait after the bounded network-settle that follows each navigation (default 1000).")
    ap.add_argument("--self-check", action="store_true", help="Validate environment/args + gate/login logic without launching a browser, then exit.")
    args = ap.parse_args()

    prof = load_profile(args.profile)
    url = args.url or prof.get("url")
    vp = parse_viewport(args.viewport or prof.get("viewport") or "1920x1080")
    wait_for = args.wait_for if args.wait_for is not None else prof.get("waitFor")
    must_contain = args.must_contain if args.must_contain is not None else prof.get("mustContain", [])
    wait_for_gone = args.wait_for_gone if args.wait_for_gone is not None else prof.get("waitForGone")
    wait_ms = args.wait_ms if args.wait_ms is not None else int(prof.get("waitMs", 0))
    rt_timeout = args.readiness_timeout
    settle_ms = args.settle_ms if args.settle_ms is not None else int(prof.get("settleMs", 1000))
    do_login_flag = args.login or bool(prof.get("login"))
    record_har = args.record_har or bool(prof.get("recordHar"))
    # error signatures (all lowercased, matched against title+url+body):
    #   generic defaults  +  app-specific from project.json (login route basename + errorSignatures)  +  profile  +  CLI.
    # The app's own LOGIN route is a classic misleading target (session-expiry redirect) — derived from
    # project.loginAction, NOT hardcoded to any one app.
    proj = load_project(args.project)
    proj_login = (proj.get("loginAction") or "").rstrip("/").split("/")[-1].lower()   # lowercased: compared against lowercased blobs + the HAR url
    cred_anchors = [d for d in [
        (os.path.dirname(os.path.abspath(args.project)) if args.project else None),
        (proj.get("legacySourceDir") or None),
        os.getcwd(),
    ] if d]
    # creds path: --creds wins; else project.credsFile (resolved relative to project.json's dir); else load_creds
    # defaults to searching for "login.env" near the project. LEGACY_USER/LEGACY_PASS env vars always work too.
    creds_path = args.creds
    if not creds_path and proj.get("credsFile"):
        cf = proj["credsFile"]
        pdir = os.path.dirname(os.path.abspath(args.project)) if args.project else os.getcwd()
        creds_path = cf if os.path.isabs(cf) else os.path.join(pdir, cf)
    error_signatures = [s.lower() for s in (
        ["http status 5", "http status 4", "error 500", "error 404", "exception report",
         "stack trace", "page not found", "an error has occurred"]
        + ([proj_login] if proj_login else [])
        + list(proj.get("errorSignatures", []) or [])
        + list(prof.get("errorSignatures", []) or [])
        + list(args.error_signature or []))]

    if args.self_check:
        try:
            import playwright  # noqa
            ok = True
        except Exception:
            ok = False

        # --- exercise the no-browser logic the fix depends on, with a fake page ---
        class _FakePage:
            def __init__(self, raise_on=()):
                self.calls = []; self.raise_on = set(raise_on)
            def _rec(self, name, *a):
                self.calls.append((name,) + a)
                if name in self.raise_on:
                    raise RuntimeError("boom:" + name)
            def wait_for_load_state(self, state, timeout=None): self._rec("wait_for_load_state", state)
            def wait_for_timeout(self, ms): self._rec("wait_for_timeout", ms)
            def goto(self, u, wait_until=None): self._rec("goto", u)
            def fill(self, sel, val): self._rec("fill", sel)
            def click(self, sel, timeout=None): self._rec("click", sel)
            def press(self, sel, key): self._rec("press", sel)

        # 1. settle() swallows a networkidle timeout and STILL settles (the anti-hang guarantee)
        fp = _FakePage(raise_on={"wait_for_load_state"})
        settle(fp, 100, 5)
        assert any(c[0] == "wait_for_timeout" for c in fp.calls), "settle must not hang/raise on a never-idle page"

        # 2. do_login builds project-driven selectors and submits; missing creds is a clear error
        sproj = {"loginUrl": "http://h/APP/jsp/login.jsp", "loginFields": {"user": "empId", "password": "pin"}}
        fp2 = _FakePage()
        do_login(fp2, sproj, {"empId": "u", "pin": "p"}, 100, 5)
        joined = " ".join(str(c) for c in fp2.calls)
        assert "jsp/login.jsp" in joined and "input[name='empId']" in joined and "input[name='pin']" in joined, fp2.calls
        try:
            do_login(_FakePage(), sproj, {}, 100, 5)
            raise AssertionError("do_login should SystemExit on missing creds")
        except SystemExit:
            pass
        assert login_url_for({"legacyBaseUrl": "http://h:8080", "contextRoot": "/APP"}).endswith("/APP/jsp/login.jsp")

        # 3. redact_har strips the login POST password + cookie/auth headers (public repo: no creds in artifacts)
        import tempfile
        hp = os.path.join(tempfile.mkdtemp(prefix="cap_sc_"), "t.har")
        json.dump({"log": {"entries": [
            {"request": {"url": "http://h/APP/loginAction.do", "method": "POST",
                         "postData": {"text": "user=u&password=secret", "params": [{"name": "password", "value": "secret"}]},
                         "headers": [{"name": "Cookie", "value": "JSESSIONID=x"}]}},
            {"request": {"url": "http://h/APP/dispatcherAction.do", "method": "GET", "headers": []}}]}},
            open(hp, "w"))
        redact_har(hp, "loginaction.do")
        assert "secret" not in open(hp).read(), "password leaked through redaction"

        # 4. login_ok: an authenticated landing ON the login-action route is NOT an error (the exact pod
        #    false-negative). Pass a MIXED-CASE basename to prove the case-insensitive exclusion holds.
        sigs = ["exception report", "loginaction.do", "http status 5"]
        assert login_ok("FA Search", "http://h/BAA/loginAction.do", False, sigs, "loginAction.do") is True
        assert login_ok("Login", "http://h/BAA/jsp/login.jsp", True, sigs, "loginAction.do") is False   # password still present
        assert login_ok("HTTP Status 500", "http://h/x", False, sigs, "loginAction.do") is False        # real hard error

        # 5. load_creds finds the conventional login.env at an ANCHOR's PARENT, not just the literal path
        cdir = tempfile.mkdtemp(prefix="cap_creds_")
        deep = os.path.join(cdir, "modernization"); os.makedirs(deep)
        with open(os.path.join(cdir, "login.env"), "w") as f:
            f.write("user=alice\npassword=topsecret\n")
        got = load_creds("login.env", [deep])
        assert got.get("user") == "alice" and got.get("password") == "topsecret", got

        # 6. cred_value: case-insensitive + variant key lookup (a file keyed USERNAME=/PASSWORD= still resolves)
        assert cred_value({"USERNAME": "bob", "PASSWORD": "x"}, "user", ["username"]) == "bob"
        assert cred_value({"userId": "c"}, "user", ["userid"]) == "c"
        assert cred_value({}, "user", ["username"]) is None

        out_base = os.path.join(args.out_dir, args.name) if (args.out_dir and args.name) else None
        print(json.dumps({"self_check": "ok", "viewport": vp, "out_base": out_base, "playwright_importable": ok,
                          "record_har": record_har, "error_signatures": len(error_signatures),
                          "checks": {"settle_swallows": True, "do_login_selectors": True, "creds_guard": True,
                                     "har_redacted": True, "login_ok_landing": True, "creds_search": True,
                                     "cred_variants": True},
                          "resolved": {"url": url, "login": do_login_flag, "wait_for": wait_for,
                                       "must_contain": must_contain, "wait_for_gone": wait_for_gone, "wait_ms": wait_ms}}))
        return

    if args.check_login:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise SystemExit("Playwright not available (%s). pip install playwright && playwright install chromium" % e)
        creds = load_creds(creds_path, cred_anchors)
        final_url, title, still_login = "", "", True
        with sync_playwright() as p:
            browser = launch_browser(p, args.channel)
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            page.set_default_timeout(rt_timeout); page.set_default_navigation_timeout(rt_timeout)
            try:
                do_login(page, proj, creds, rt_timeout, settle_ms)
                final_url, title = page.url, (page.title() or "")
                still_login = page.query_selector("input[type=password]") is not None
            finally:
                try: ctx.close()
                except Exception: pass
                try: browser.close()
                except Exception: pass
        authed = login_ok(title, final_url, still_login, error_signatures, proj_login)
        print(json.dumps({"check_login": "ok", "final_url": final_url, "title": title,
                          "authenticated": authed, "password_field_present": still_login, "error_page": not authed}))
        sys.exit(0 if authed else 2)

    if not args.out_dir or not args.name:
        raise SystemExit("--out-dir and --name are required for a capture")
    if not url:
        raise SystemExit('no URL: pass --url or put "url" in --profile')
    os.makedirs(args.out_dir, exist_ok=True)
    har_path = os.path.join(args.out_dir, args.name + ".har")  # provisional; moved to _rejected/ if quarantined
    # `base` (output path prefix) is decided AFTER load — a quarantined error capture goes under _rejected/.

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise SystemExit(f"Playwright not available ({e}). On the pod: pip install playwright && playwright install chromium")

    # workflow steps: explicit --workflow file > profile inline list > profile path
    steps = None
    if args.workflow:
        steps = json.load(open(args.workflow))
    elif isinstance(prof.get("workflow"), list):
        steps = prof["workflow"]
    elif isinstance(prof.get("workflow"), str):
        steps = json.load(open(prof["workflow"]))
    network, assets = [], []
    creds = load_creds(creds_path, cred_anchors) if do_login_flag else {}

    doc_status = {"code": None}  # status of the top-level navigation document (mutable holder)
    base = os.path.join(args.out_dir, args.name)   # re-pointed to _rejected/ after load if it's an error/partial page
    readiness = {"wait_for": None, "must_contain": {}, "wait_for_gone": None, "fonts": False, "settle_ms": wait_ms}
    warnings, nav_error, error_page, sig_hit = [], None, False, None
    final_url, title, body_sample, body_font = url, "", "", ""
    asset_fail, stylesheets, scripts = [], 0, 0
    model = {"title": "", "url": url, "viewport": {}, "elements": [], "tables": [], "forms": []}
    a11y = None

    with sync_playwright() as p:
        browser = launch_browser(p, args.channel)
        ctx_kwargs = {"viewport": vp, "device_scale_factor": 1}
        if args.auth_state:
            ctx_kwargs["storage_state"] = args.auth_state
        if record_har:
            ctx_kwargs.update(record_har_path=har_path, record_har_content="embed", record_har_mode="full")
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.set_default_timeout(rt_timeout)
        page.set_default_navigation_timeout(rt_timeout)

        def on_response(resp):
            try:
                rt = resp.request.resource_type
                if rt == "document" and resp.request.is_navigation_request():
                    doc_status["code"] = resp.status   # final top-level document status (e.g. 500 = error page)
                if rt in ("document", "xhr", "fetch"):
                    rec = {"method": resp.request.method, "url": resp.url, "status": resp.status,
                           "resource_type": rt, "content_type": resp.headers.get("content-type", "")}
                    ct = rec["content_type"]
                    if ("json" in ct) or ("text" in ct) or ("xml" in ct):
                        body = resp.body()
                        if body and len(body) <= args.body_cap:
                            rec["body"] = body.decode("utf-8", "replace")
                    network.append(rec)
                elif rt in ("stylesheet", "script", "font", "image"):
                    assets.append({"url": resp.url, "status": resp.status, "resource_type": rt})  # health only, no body
            except Exception:
                pass  # opaque/redirected responses can't be read; skip quietly

        page.on("response", on_response)
        try:
            try:
                if do_login_flag:
                    do_login(page, proj, creds, rt_timeout, settle_ms)   # fresh from-start login, warms the session
                if steps:
                    run_workflow(page, steps, rt_timeout, settle_ms)
                else:
                    page.goto(url, wait_until="domcontentloaded")
                    settle(page, rt_timeout, settle_ms)                  # bounded — never hangs on a never-idle page

                # --- semantic readiness, in order: selector -> text markers -> spinner gone -> fonts -> settle ---
                # ("page loaded" != "screen usable"; networkidle alone misses async-hydrated widgets)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=rt_timeout); readiness["wait_for"] = True
                    except Exception:
                        readiness["wait_for"] = False; warnings.append(f"selector never appeared: {wait_for}")
                for marker in (must_contain or []):
                    try:
                        page.wait_for_function("t => document.body && document.body.innerText.includes(t)",
                                               arg=marker, timeout=rt_timeout)
                        readiness["must_contain"][marker] = True
                    except Exception:
                        readiness["must_contain"][marker] = False
                        warnings.append(f"text marker never appeared: {marker!r}")
                if wait_for_gone:
                    try:
                        page.wait_for_selector(wait_for_gone, state="hidden", timeout=rt_timeout); readiness["wait_for_gone"] = True
                    except Exception:
                        readiness["wait_for_gone"] = False; warnings.append(f"element never disappeared: {wait_for_gone}")
                try:
                    page.evaluate("document.fonts ? document.fonts.ready : null"); readiness["fonts"] = True
                except Exception:
                    pass
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
            except Exception as e:
                nav_error = "%s: %s" % (type(e).__name__, e)
                warnings.append("navigation/capture error -> " + nav_error)

            # styled-vs-unstyled / asset health (partial but still informative even after a nav_error)
            asset_fail = [a for a in assets if a["resource_type"] in ("stylesheet", "script") and a["status"] >= 400]
            stylesheets = sum(1 for a in assets if a["resource_type"] == "stylesheet")
            scripts = sum(1 for a in assets if a["resource_type"] == "script")
            if asset_fail:
                warnings.append(f"{len(asset_fail)} CSS/JS asset(s) returned >=400 — page may be unstyled/broken")
            try:
                body_font = page.evaluate("getComputedStyle(document.body).fontFamily") or ""
            except Exception:
                body_font = ""
            try:
                final_url = page.url
            except Exception:
                pass
            try:
                title = page.title()
            except Exception:
                title = ""
            try:
                body_sample = page.evaluate("document.body ? document.body.innerText.slice(0,4000) : ''") or ""
            except Exception:
                body_sample = ""
            # --- error/partial detection: a page can satisfy 'loaded' yet be a 500 / login / wrong view;
            #     a nav stall/timeout (nav_error) is ALSO treated as rejected so it never poses as evidence ---
            blob = (title + " " + final_url + " " + body_sample).lower()
            sig_hit = next((s for s in error_signatures if s and s in blob), None)
            http_err = (doc_status["code"] is not None and doc_status["code"] >= 400)
            error_page = bool(sig_hit or http_err or nav_error)
            if error_page:
                warnings.append("error/partial page (status=%s, signature=%r, nav_error=%s) -> quarantined to _rejected/"
                                % (doc_status["code"], sig_hit, bool(nav_error)))

            # quarantined captures go under _rejected/ so they are NOT promoted as the view's evidence
            target_dir = os.path.join(args.out_dir, "_rejected") if error_page else args.out_dir
            os.makedirs(target_dir, exist_ok=True)
            base = os.path.join(target_dir, args.name)

            # defensive writes — whatever DID render is still evidence after a stall/timeout (each guarded)
            try:
                page.screenshot(path=base + ".png", full_page=args.full_page)
            except Exception as e:
                warnings.append("screenshot failed: %s" % e)
            try:
                open(base + ".dom.html", "w", encoding="utf-8").write(page.content())
            except Exception as e:
                warnings.append("dom dump failed: %s" % e)
            try:
                model = page.evaluate(EXTRACTOR_JS, STYLE_PROPS)
            except Exception as e:
                warnings.append("model extract failed: %s" % e)
            json.dump(model, open(base + ".model.json", "w", encoding="utf-8"), indent=1)
            try:
                a11y = page.accessibility.snapshot()
            except Exception:
                a11y = None
            json.dump(a11y, open(base + ".a11y.json", "w", encoding="utf-8"), indent=1)
            json.dump(network, open(base + ".network.json", "w", encoding="utf-8"), indent=1)
        finally:
            try:
                ctx.close()        # HAR flushes ONLY on context close — must run even on a stall/timeout
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    # HAR flushed on context close. Redact creds from the login request, then relocate next to the artifacts.
    if record_har and do_login_flag:
        redact_har(har_path, proj_login)
    har_out = None
    if record_har and os.path.exists(har_path):
        har_out = base + ".har"
        if os.path.abspath(har_out) != os.path.abspath(har_path):
            os.replace(har_path, har_out)

    # usable = no nav error/stall AND readiness passed AND no CSS/JS failed AND not an error page
    usable = (not nav_error
              and readiness["wait_for"] is not False
              and all(readiness["must_contain"].values())
              and readiness["wait_for_gone"] is not False
              and not asset_fail
              and not error_page)

    meta = {
        "name": args.name, "url": url, "final_url": final_url, "title": title,
        "viewport": args.viewport or prof.get("viewport") or "1920x1080",
        "auth_state": bool(args.auth_state), "login": do_login_flag, "profile": args.profile,
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "readiness": readiness, "usable": usable, "rejected": error_page, "nav_error": nav_error,
        "error": {"is_error_page": error_page, "doc_status": doc_status["code"], "signature_hit": sig_hit, "nav_error": nav_error},
        "warnings": warnings,
        "assets": {"ok": not asset_fail, "failed": asset_fail[:20], "stylesheets": stylesheets, "scripts": scripts},
        "body_font_family": body_font, "har": har_out,
        "sha256": {"png": safe_sha(base + ".png"), "dom": safe_sha(base + ".dom.html")},
        "elements": len(model.get("elements", [])), "tables": len(model.get("tables", [])), "network_records": len(network),
    }
    json.dump(meta, open(base + ".capture.json", "w", encoding="utf-8"), indent=1)

    print(json.dumps({"ok": not nav_error, "name": args.name, "usable": usable, "rejected": error_page,
                      "error_page": error_page, "nav_error": nav_error, "warnings": warnings,
                      "png": base + ".png", "model": base + ".model.json", "capture": base + ".capture.json",
                      "har": har_out, "elements": meta["elements"], "network_records": meta["network_records"]}, indent=1))
    sys.exit(0 if usable else 2)


if __name__ == "__main__":
    main()
