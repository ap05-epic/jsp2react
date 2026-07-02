#!/usr/bin/env python3
"""
crawl_ajax.py — stateful AJAX view discovery (Playwright).

The static crawler only follows <a href> links, so it is blind to the AJAX "view explosion":
one link -> tabs / hover-menus / dropdowns / drill-downs that load 30+ partial views without a
URL change. This crawler finds them, and it enforces the hard rule for stateful Struts apps:

  NEVER open a deep view directly. Every view is reached by replaying a click-path FROM THE START.

Algorithm (bounded BFS over UI states):
  - reach a state = navigate the start URL, then replay its recorded steps (hover/click) in order
  - a "state" is identified by a DOM SIGNATURE (hash of the visible tag+text skeleton)
  - from each state, enumerate interactive candidates (links/buttons/tabs/menuitems/hover menus),
    and for EACH: replay parent path from start -> do the one action -> settle -> signature
  - a new signature => a new view; record {clickPathFromStart, triggeredEndpoints, domSignature,
    isError, label}. Error-looking views are recorded but NOT expanded.
  -> viewgraph.json : the full discovered inventory, every view with its from-start path.

Crawljax (optional, OSS) can be run separately for exhaustive state-graph discovery; normalize its
output to the same shape and fold it in with --merge (see references/ajax-crawl-and-viewgraph.md).

Usage:
  python crawl_ajax.py --start-url <url> --login --creds login.env --project project.json --out viewgraph.json
  python crawl_ajax.py --start-url <url> --auth-state auth_state.json --out viewgraph.json   # simple apps only
  python crawl_ajax.py --start-url <url> --merge crawljax.viewgraph.json --out viewgraph.json
  python crawl_ajax.py --self-check

Auth: for session-sensitive apps use --login (a FRESH from-start login in the crawl context — same proven
machinery as capture_screen.py; a saved --auth-state is often a stale single cookie the server rotates,
which lands every view on the app's error page).
"""
import argparse, json, os, hashlib
import capture_screen as cap   # shared, pod-proven login/browser machinery (same skill dir)

CANDIDATES_JS = r"""
() => {
  function cssPath(el){
    if (el.id) return '#' + CSS.escape(el.id);
    const parts=[];
    while (el && el.nodeType===1 && el.tagName!=='BODY' && el.tagName!=='HTML'){
      let sel = el.tagName.toLowerCase();
      const p = el.parentElement;
      if (p){ const sibs=[...p.children].filter(c=>c.tagName===el.tagName);
              if (sibs.length>1) sel += ':nth-of-type(' + (sibs.indexOf(el)+1) + ')'; }
      parts.unshift(sel); el = p;
    }
    return parts.join('>');
  }
  function vis(el){ const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden'||parseFloat(cs.opacity)===0) return false;
                    const r=el.getBoundingClientRect(); return r.width>0 && r.height>0; }
  const SEL='a,button,[onclick],[role=tab],[role=menuitem],[role=button],li>a,.tab,.menuItem,.menuitem,summary,[data-toggle],[data-url],[data-target]';
  const out=[], seen=new Set();
  for (const el of document.querySelectorAll(SEL)){
    if (!vis(el)) continue;
    const label=(el.innerText||el.getAttribute('aria-label')||el.title||'').replace(/\s+/g,' ').trim().slice(0,60);
    const href=(el.getAttribute('href')||'').trim();
    const role=el.getAttribute('role')||'';
    const ajaxy = (!href||href==='#'||href.toLowerCase().startsWith('javascript:')||el.hasAttribute('onclick')
                   ||el.hasAttribute('data-url')||el.hasAttribute('data-target')
                   ||['tab','menuitem','button'].includes(role)||el.classList.contains('tab'));
    const hover = (el.tagName==='LI' || !!el.querySelector('ul,.submenu,.dropdown') || el.classList.contains('menu'));
    const sel=cssPath(el); const key=sel+'|'+(hover?'hover':'click');
    if (seen.has(key)) continue; seen.add(key);
    out.push({selector:sel, kind:(hover?'hover':'click'), label, ajaxy});
  }
  // ajaxy first (most likely to load partial views), then the rest
  out.sort((a,b)=> (b.ajaxy?1:0)-(a.ajaxy?1:0));
  return out;
}
"""

SIGNATURE_JS = r"""
() => {
  const SKIP=new Set(['SCRIPT','STYLE','NOSCRIPT','META','LINK','HEAD','TEMPLATE']);
  function vis(el){ const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden') return false;
                    const r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
  const parts=[];
  const walk=(el)=>{ if(!el||el.nodeType!==1||SKIP.has(el.tagName)||!vis(el)) return;
    let t=''; for(const n of el.childNodes) if(n.nodeType===3) t+=n.nodeValue;
    t=t.replace(/\s+/g,' ').trim().slice(0,40);
    parts.push(el.tagName.toLowerCase()+(el.id?('#'+el.id):'')+(t?(':'+t):''));
    for(const c of el.children) walk(c); };
  walk(document.body);
  return {skeleton: parts.join('\n'), title: document.title, url: location.href, bodyLen: document.body.innerText.length};
}
"""

# Generic error markers (app-agnostic). App-specific ones — notably the app's own LOGIN route, which a
# session-expiry redirect lands on and is a classic misleading target — are added at runtime from
# --project (loginAction) + project.errorSignatures. See EXTRA_MARKERS below.
ERROR_MARKERS = ("error 500", "error 404", "http status 5", "http status 4", "exception",
                 "stack trace", "not found", "forbidden", "page not found", "an error has occurred")
EXTRA_MARKERS = []   # populated in main() from project.json (login route basename + errorSignatures)


def load_project(path):
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def project_error_markers(proj):
    """Login route (basename) + any project.errorSignatures, lowercased — app-specific misleading targets."""
    marks = []
    login = (proj.get("loginAction") or "").strip()
    if login:
        base = login.rstrip("/").split("/")[-1].lower()
        if base:
            marks.append(base)            # e.g. 'loginaction.do' — derived, not hardcoded
    marks += [str(s).lower() for s in (proj.get("errorSignatures") or [])]
    return marks


def sig_hash(skeleton):
    return hashlib.sha1(skeleton.encode("utf-8", "replace")).hexdigest()[:16]


def looks_like_error(snap):
    blob = ((snap.get("title", "") + " " + snap.get("url", "")).lower())
    if any(mk in blob for mk in ERROR_MARKERS) or any(mk in blob for mk in EXTRA_MARKERS):
        return True
    if snap.get("bodyLen", 1) < 15:   # essentially blank
        return True
    return False


def reconcile(*lists):
    """Merge view lists (e.g. Playwright + normalized Crawljax) by domSignature: dedup,
    union triggeredEndpoints, keep the SHORTEST from-start path. Pure — unit-tested by --self-check."""
    by_sig, order = {}, []
    for lst in lists:
        for st in lst or []:
            key = st.get("domSignature") or st.get("id") or json.dumps(st.get("clickPathFromStart", []))
            if key not in by_sig:
                by_sig[key] = dict(st); order.append(key)
            else:
                ex = by_sig[key]
                ex["triggeredEndpoints"] = sorted(set(ex.get("triggeredEndpoints", [])) |
                                                  set(st.get("triggeredEndpoints", [])))
                if len(st.get("clickPathFromStart", [])) < len(ex.get("clickPathFromStart", [])):
                    ex["clickPathFromStart"] = st["clickPathFromStart"]
    return [by_sig[k] for k in order]


def main():
    ap = argparse.ArgumentParser(description="Discover AJAX views via from-the-start click-path BFS -> viewgraph.json")
    ap.add_argument("--start-url", help="The authenticated start view (e.g. the post-login summary). Required for crawl.")
    ap.add_argument("--auth-state", help="Playwright storage_state json (saved session) — simple apps only; "
                                         "session-sensitive apps need --login (a saved single cookie goes stale).")
    ap.add_argument("--login", action="store_true",
                    help="FRESH from-start login in the crawl context before crawling (loginUrl/loginFields from "
                         "--project; creds from --creds / project.credsFile / LEGACY_USER+LEGACY_PASS).")
    ap.add_argument("--creds", help="KEY=VALUE creds file for --login (default: project.credsFile or a nearby login.env).")
    ap.add_argument("--channel", help="Browser channel, e.g. chrome|msedge (default: bundled chromium, then chrome, then msedge).")
    ap.add_argument("--out", help="Write viewgraph.json here. Required for a real run.")
    ap.add_argument("--viewport", default="1920x1080")
    ap.add_argument("--max-states", type=int, default=40, help="Stop after discovering this many distinct views.")
    ap.add_argument("--max-depth", type=int, default=3, help="Max click-path length from start.")
    ap.add_argument("--max-actions", type=int, default=25, help="Max candidate actions probed per state.")
    ap.add_argument("--settle-ms", type=int, default=1500, help="Settle wait after each action (AJAX hydration).")
    ap.add_argument("--readiness-timeout", type=int, default=15000)
    ap.add_argument("--merge", action="append", help="Normalized external viewgraph(s) (e.g. from Crawljax) to fold in.")
    ap.add_argument("--project", help="project.json — supplies the app's login route + errorSignatures as misleading-target markers.")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        # project-driven markers: the app's own login route is a misleading target, derived not hardcoded
        EXTRA_MARKERS[:] = project_error_markers({"loginAction": "/DEMO/loginAction.do", "errorSignatures": ["oops page"]})
        assert looks_like_error({"title": "x", "url": "/DEMO/loginAction.do", "bodyLen": 99}), "project login marker miss"
        assert looks_like_error({"title": "Oops Page", "url": "/y", "bodyLen": 99}), "project errorSignature miss"
        EXTRA_MARKERS[:] = []
        try:
            import playwright  # noqa
            pw = True
        except Exception:
            pw = False
        a = [{"domSignature": "s1", "clickPathFromStart": [{"selector": "#a"}, {"selector": "#b"}],
              "triggeredEndpoints": ["/x.do"]}]
        b = [{"domSignature": "s1", "clickPathFromStart": [{"selector": "#a"}], "triggeredEndpoints": ["/y.do"]},
             {"domSignature": "s2", "clickPathFromStart": [], "triggeredEndpoints": []}]
        merged = reconcile(a, b)
        assert len(merged) == 2, "reconcile should dedup s1"
        s1 = [m for m in merged if m["domSignature"] == "s1"][0]
        assert s1["triggeredEndpoints"] == ["/x.do", "/y.do"], "endpoints not unioned"
        assert len(s1["clickPathFromStart"]) == 1, "shortest path not kept"
        assert looks_like_error({"title": "HTTP Status 500", "url": "/e", "bodyLen": 99}), "error miss"
        assert not looks_like_error({"title": "FA Profile", "url": "/ok", "bodyLen": 500}), "false error"
        # --login wiring: the shared capture_screen machinery must be importable and resolve cred variants
        assert cap.cred_value({"USERNAME": "u"}, "user", ["username"]) == "u", "shared login machinery broken"
        assert cap.login_ok("FA Search", "http://h/APP/loginAction.do", False, ["loginaction.do"], "loginaction.do"), \
            "login_ok should accept an authenticated landing on the login-action route"
        print(json.dumps({"self_check": "ok", "playwright_importable": pw, "reconciled": len(merged),
                          "login_machinery": "shared-with-capture_screen"}))
        return

    if not args.start_url or not args.out:
        raise SystemExit("--start-url and --out are required (or use --self-check)")
    proj = load_project(args.project)
    EXTRA_MARKERS[:] = project_error_markers(proj)   # app login route + errorSignatures
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise SystemExit("Playwright not available (%s). pip install playwright && playwright install chromium" % e)

    w, h = (int(x) for x in args.viewport.lower().split("x"))
    states, seen, warnings = [], {}, []

    def settle(page):
        try:
            page.wait_for_load_state("networkidle", timeout=args.readiness_timeout)
        except Exception:
            pass
        page.wait_for_timeout(args.settle_ms)

    def snapshot(page):
        return page.evaluate(SIGNATURE_JS)

    def do_action(page, step):
        sel, kind = step["selector"], step.get("kind", "click")
        if kind == "hover":
            page.hover(sel, timeout=args.readiness_timeout)
        else:
            page.click(sel, timeout=args.readiness_timeout)

    def reach(page, path):
        # wait_until="commit" (not domcontentloaded): slow legacy pages can block past the nav timeout before
        # DOMContentLoaded fires — the exact capture_screen stall. settle() supplies the bounded wait after.
        page.goto(args.start_url, wait_until="commit")
        settle(page)
        for step in path:
            do_action(page, step)
            settle(page)

    def action_endpoints(page, cand):
        """Perform one action while recording xhr/fetch URLs it triggers."""
        hits = []
        def on_resp(r):
            try:
                if r.request.resource_type in ("xhr", "fetch"):
                    hits.append(r.request.method + " " + r.url)
            except Exception:
                pass
        page.on("response", on_resp)
        try:
            do_action(page, cand)
        finally:
            settle(page)
            page.remove_listener("response", on_resp)
        return sorted(set(hits))

    with sync_playwright() as p:
        browser = cap.launch_browser(p, args.channel)   # bundled chromium -> chrome -> msedge fallback
        ctx_kwargs = {"viewport": {"width": w, "height": h}, "device_scale_factor": 1}
        if args.auth_state:
            ctx_kwargs["storage_state"] = args.auth_state
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        if args.login:
            # creds resolution mirrors capture_screen: --creds wins; else project.credsFile (relative to
            # project.json's dir); else load_creds searches for login.env near the anchors. Env vars work too.
            creds_path = args.creds
            pdir = os.path.dirname(os.path.abspath(args.project)) if args.project else os.getcwd()
            if not creds_path and proj.get("credsFile"):
                cf = proj["credsFile"]
                creds_path = cf if os.path.isabs(cf) else os.path.join(pdir, cf)
            anchors = [d for d in [pdir, proj.get("legacySourceDir"), os.getcwd()] if d]
            cap.do_login(page, proj, cap.load_creds(creds_path, anchors), args.readiness_timeout, args.settle_ms)
            still_login = page.locator("input[type=password]").count() > 0
            lb = (proj.get("loginAction") or "").rstrip("/").split("/")[-1].lower()
            if not cap.login_ok(page.title(), page.url, still_login, list(ERROR_MARKERS) + EXTRA_MARKERS, lb):
                ctx.close(); browser.close()
                raise SystemExit("--login did not authenticate (still on the login/error page). Check the creds "
                                 "file + project.json loginFields; probe with capture_screen.py --check-login.")

        reach(page, [])
        snap0 = snapshot(page)
        sig0 = sig_hash(snap0["skeleton"])
        states.append({"id": "v0000", "clickPathFromStart": [], "triggeredEndpoints": [],
                       "domSignature": sig0, "isError": looks_like_error(snap0),
                       "label": "start", "title": snap0.get("title", ""), "url": snap0.get("url", "")})
        seen[sig0] = "v0000"
        queue = [[]]

        while queue and len(states) < args.max_states:
            path = queue.pop(0)
            if len(path) >= args.max_depth:
                continue
            try:
                reach(page, path)
            except Exception as e:
                warnings.append("could not reach path %s: %s" % ([s["selector"] for s in path], e))
                continue
            try:
                candidates = page.evaluate(CANDIDATES_JS)[: args.max_actions]
            except Exception as e:
                warnings.append("candidate scan failed: %s" % e); candidates = []

            for cand in candidates:
                if len(states) >= args.max_states:
                    break
                try:
                    reach(page, path)                       # fresh replay to parent (actions mutate DOM)
                    endpoints = action_endpoints(page, cand)
                    snap = snapshot(page)
                except Exception as e:
                    warnings.append("action %r failed: %s" % (cand.get("selector"), e)); continue
                sig = sig_hash(snap["skeleton"])
                if sig in seen:
                    continue
                err = looks_like_error(snap)
                vid = "v%04d" % len(states)
                newpath = path + [{"selector": cand["selector"], "kind": cand["kind"], "label": cand["label"]}]
                states.append({"id": vid, "clickPathFromStart": newpath, "triggeredEndpoints": endpoints,
                               "domSignature": sig, "isError": err, "label": cand["label"],
                               "title": snap.get("title", ""), "url": snap.get("url", "")})
                seen[sig] = vid
                if not err:
                    queue.append(newpath)

        ctx.close(); browser.close()

    # fold in any external (e.g. Crawljax-normalized) viewgraphs
    external = []
    for mf in (args.merge or []):
        try:
            data = json.load(open(mf, encoding="utf-8"))
            external.append(data.get("states", data) if isinstance(data, dict) else data)
        except Exception as e:
            warnings.append("could not merge %s: %s" % (mf, e))
    final_states = reconcile(states, *external)

    vg = {"start_url": args.start_url, "viewport": args.viewport, "count": len(final_states),
          "errors": sum(1 for s in final_states if s.get("isError")),
          "states": final_states, "warnings": warnings}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(vg, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({"ok": True, "out": args.out, "views": len(final_states),
                      "error_views": vg["errors"], "warnings": len(warnings)}))


if __name__ == "__main__":
    main()
