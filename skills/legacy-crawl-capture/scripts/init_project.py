#!/usr/bin/env python3
"""
init_project.py — bootstrap project.json from the legacy URL + source, so the AGENT owns the config
(not the human). The driver agent runs this in analysis mode, then completes/confirms the few fields it
couldn't derive. Every other script reads the result via --project.

What it derives (deterministically, stdlib only):
  - legacyBaseUrl + contextRoot   from the URL          (http://h:8080/BAA/jsp/login.jsp -> .../, /BAA)
  - loginAction + loginFields     from the login JSP    (the form with a password field)
  - families + pathConventions    from the jsp/ subdirs  (one family per subdir; alt-root/contentlet/ipad/mobile)
  - db.sqlmapDir                  from the source tree  (dir holding iBATIS/MyBatis CALLABLE sqlmaps)
  - proxyPaths, viewport, ports, idPrefixes  sensible defaults
Fields it cannot derive are left blank with a TODO in "_todo" for the agent/human to fill.

Usage:
  python init_project.py --url http://host:8080/<ctx>/jsp/login.jsp \
      --webapp-dir <webapp> --source-dir <java-and-resources-root> --out work/project.json
  python init_project.py --self-check
"""
import argparse, json, os, re, sys, tempfile

PW_RE      = re.compile(r"""<(?:html:password|input[^>]*type\s*=\s*['"]password['"])[^>]*>""", re.I)
FORM_RE    = re.compile(r"""<(?:html:form|form)\b[^>]*\baction\s*=\s*['"]([^'"]+)['"]""", re.I)
INPUT_RE   = re.compile(r"""<(html:text|html:password|input)\b([^>]*)>""", re.I)
NAME_RE    = re.compile(r"""\b(?:name|property)\s*=\s*['"]([^'"]+)['"]""", re.I)
TYPE_RE    = re.compile(r"""\btype\s*=\s*['"]([^'"]+)['"]""", re.I)
PRUNE      = {"pdfjs", "dojo", "node_modules", "target", "dist", "build", ".git", "lib", "locale", "cmaps"}
KNOWN_CONV = {"pjsp": "alt-root", "contentlet": "contentlet", "ipad": "ipad", "mobile": "mobile"}


def parse_url(url):
    m = re.match(r"^([a-z]+://[^/]+)(/.*)?$", url or "", re.I)
    if not m:
        return "", ""
    base, path = m.group(1), (m.group(2) or "")
    segs = [s for s in path.split("/") if s]
    # context root = the first path segment (the deployed WAR context), unless it's a view dir like "jsp"
    # (which means the app is deployed at server root, i.e. no context root).
    ctx = ""
    if segs and segs[0].lower() != "jsp":
        ctx = "/" + segs[0]
    return base, ctx


def find_login_jsp(webapp_dir):
    """First JSP that contains a password field — that's the login form."""
    if not webapp_dir or not os.path.isdir(webapp_dir):
        return None, ""
    best = None
    for dp, dns, fns in os.walk(webapp_dir):
        dns[:] = [d for d in dns if d not in PRUNE]
        for fn in fns:
            if not fn.lower().endswith((".jsp", ".jspf", ".html")):
                continue
            full = os.path.join(dp, fn)
            try:
                txt = open(full, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if PW_RE.search(txt):
                # prefer one whose name screams login
                if "login" in fn.lower() or "logon" in fn.lower() or "signon" in fn.lower():
                    return full, txt
                if best is None:
                    best = (full, txt)
    return best if best else (None, "")


def login_from_jsp(text, ctx):
    action = ""
    m = FORM_RE.search(text or "")
    if m:
        action = m.group(1)
        if not action.startswith("http"):
            # Struts form actions are CONTEXT-relative (a leading "/" is the context root, not the server root):
            # <html:form action="/loginAction.do"> resolves to <ctx>/loginAction.do at runtime.
            a = action if action.startswith("/") else "/" + action
            if ctx and not (a == ctx or a.startswith(ctx.rstrip("/") + "/")):
                a = ctx.rstrip("/") + a
            action = a
    user_field, pass_field = "", ""
    for im in INPUT_RE.finditer(text or ""):
        tag, attrs = im.group(1).lower(), im.group(2)
        nm = NAME_RE.search(attrs)
        if not nm:
            continue
        name = nm.group(1)
        is_pw = tag == "html:password" or (TYPE_RE.search(attrs) and TYPE_RE.search(attrs).group(1).lower() == "password")
        if is_pw and not pass_field:
            pass_field = name
        elif not is_pw and not user_field and tag in ("html:text", "input"):
            # first non-password text input before the password is the username
            if not pass_field:
                user_field = name
    return action, user_field, pass_field


def jsp_root(webapp_dir):
    for dp, dns, _fns in os.walk(webapp_dir):
        if os.path.basename(dp).lower() == "jsp":
            return dp
    return webapp_dir


def derive_families(webapp_dir):
    """Immediate subdirs of the jsp/ root -> families; known special dirs -> pathConventions."""
    families, conv = [], {}
    root = jsp_root(webapp_dir) if webapp_dir and os.path.isdir(webapp_dir) else None
    if not root or not os.path.isdir(root):
        return families, conv
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p) or name in PRUNE or name.startswith("."):
            continue
        low = name.lower()
        if low in ("inc", "include", "includes", "layouts", "layout", "common", "tags"):
            continue                                        # fragment/layout dirs aren't families
        if low in KNOWN_CONV:
            conv.setdefault(KNOWN_CONV[low], []).append("/jsp/%s/" % low)
        else:
            families.append(low)
    return families, conv


def find_sqlmap_dir(source_dir):
    """Dir holding iBATIS/MyBatis sqlmaps with a CALLABLE/{call ...} (the stored-proc maps)."""
    if not source_dir or not os.path.isdir(source_dir):
        return ""
    hits = {}
    for dp, dns, fns in os.walk(source_dir):
        dns[:] = [d for d in dns if d not in PRUNE]
        for fn in fns:
            if not fn.lower().endswith(".xml"):
                continue
            try:
                txt = open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read(20000)
            except Exception:
                continue
            low = txt.lower()
            if ("sqlmap" in low or "<mapper" in low) and "call" in low:
                hits[dp] = hits.get(dp, 0) + 1
    return max(hits, key=hits.get) if hits else ""


def build(url, webapp_dir, source_dir):
    base, ctx = parse_url(url)
    login_file, login_txt = find_login_jsp(webapp_dir)
    action, user_f, pass_f = login_from_jsp(login_txt, ctx)
    families, conv = derive_families(webapp_dir)
    sqlmap = find_sqlmap_dir(source_dir)

    todo = []
    if not ctx:
        todo.append("contextRoot: could not derive from --url; set the app's context-root path (e.g. /APP).")
    if not action:
        todo.append("loginAction: no <form action> found in the login JSP; set it (e.g. /<ctx>/loginAction.do).")
    if not (user_f and pass_f):
        todo.append("loginFields: confirm the login form's username/password input names.")
    if not families:
        todo.append("families: no jsp/ subdirs found; set the app's screen families or leave 'auto'.")
    if not sqlmap:
        todo.append("db.sqlmapDir: no CALLABLE sqlmaps found under --source-dir; set it (FULL mode) or leave blank if raw JDBC.")

    login_url = ""
    if login_file and webapp_dir and base:                       # full URL of the login form (used by capture --login)
        rel = os.path.relpath(login_file, webapp_dir).replace("\\", "/")
        login_url = base.rstrip("/") + ctx + "/" + rel.lstrip("/")

    proj = {
        "appName": (ctx.strip("/").upper() if ctx else ""),
        "contextRoot": ctx,
        "legacyBaseUrl": base or "http://127.0.0.1:8080",
        "legacySourceDir": webapp_dir or "",
        "loginAction": action,
        "loginUrl": login_url,
        "loginFields": {"user": user_f or "username", "password": pass_f or "password"},
        "families": families or "auto",
        "pathConventions": conv,
        "viewport": "1920x1080",
        "ports": {"react": 5173, "review": 8800, "backend": 8080},
        "idPrefixes": {"shared": "S", "screen": "F"},
        "errorSignatures": [],
        "proxyPaths": [p for p in [ctx, "/api"] if p],
        "db": {"jdbcUrl": "", "schema": "", "sqlmapDir": sqlmap},
        "targetFrontendDir": "",
        "targetBackendDir": "",
        "_discovered": {
            "loginJsp": (os.path.relpath(login_file, webapp_dir) if (login_file and webapp_dir) else login_file) or None,
            "fromUrl": {"legacyBaseUrl": base, "contextRoot": ctx},
            "sqlmapDir": sqlmap or None,
        },
        "_todo": todo,
    }
    return proj


def self_check():
    d = tempfile.mkdtemp(prefix="init_project_")
    web = os.path.join(d, "src", "main", "webapp")
    jsp = os.path.join(web, "jsp")
    for sub in ("orders", "claims", "contentlet", "inc"):
        os.makedirs(os.path.join(jsp, sub))
    res = os.path.join(d, "src", "main", "resources", "sqlmaps")
    os.makedirs(res)
    with open(os.path.join(jsp, "login.jsp"), "w", encoding="utf-8") as f:
        f.write('<html:form action="/loginAction.do">'
                '<html:text property="empId"/>'
                '<input type="password" name="pin"/>'
                '<input type="submit"/></html:form>')
    with open(os.path.join(jsp, "orders", "list.jsp"), "w", encoding="utf-8") as f:
        f.write("<c:forEach items='${x}' var='r'/>")
    with open(os.path.join(res, "Order.xml"), "w", encoding="utf-8") as f:
        f.write('<sqlMap namespace="o"><procedure id="p">{ call APP.GET_ORDERS(?) }</procedure></sqlMap>')

    p = build("http://host:8080/ACME/jsp/login.jsp", web, os.path.join(d, "src"))
    assert p["contextRoot"] == "/ACME", p["contextRoot"]
    assert p["legacyBaseUrl"] == "http://host:8080", p["legacyBaseUrl"]
    assert p["loginAction"] == "/ACME/loginAction.do", p["loginAction"]
    assert p["loginUrl"] == "http://host:8080/ACME/jsp/login.jsp", p["loginUrl"]
    assert p["loginFields"] == {"user": "empId", "password": "pin"}, p["loginFields"]
    assert "orders" in p["families"] and "claims" in p["families"], p["families"]
    assert "inc" not in p["families"], "fragment dir leaked into families"
    assert p["pathConventions"].get("contentlet") == ["/jsp/contentlet/"], p["pathConventions"]
    assert p["db"]["sqlmapDir"] == res, p["db"]["sqlmapDir"]
    assert p["appName"] == "ACME", p["appName"]
    assert p["_todo"] == [], "unexpected TODOs: %s" % p["_todo"]
    # a bare URL with no source should still produce a usable skeleton + TODOs, not crash
    p2 = build("http://h:9090/APP/", "", "")
    assert p2["contextRoot"] == "/APP" and p2["_todo"], p2["_todo"]
    print(json.dumps({"self_check": "ok", "ctx": p["contextRoot"], "loginAction": p["loginAction"],
                      "loginFields": p["loginFields"], "families": p["families"],
                      "sqlmapDir_found": bool(p["db"]["sqlmapDir"]), "todos_when_bare": len(p2["_todo"])}))


def main():
    ap = argparse.ArgumentParser(description="Bootstrap project.json from the legacy URL + source (the agent runs this, then completes it).")
    ap.add_argument("--url", help="A legacy URL (the login page is ideal) — derives legacyBaseUrl + contextRoot.")
    ap.add_argument("--webapp-dir", help="Legacy webapp dir — derives login fields + families.")
    ap.add_argument("--source-dir", help="Java/resources root — derives db.sqlmapDir (FULL mode).")
    ap.add_argument("--out", help="Write project.json here (default: stdout).")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return
    if not args.url and not args.webapp_dir:
        raise SystemExit("need at least --url or --webapp-dir to derive a project.json")
    proj = build(args.url or "", args.webapp_dir or "", args.source_dir or "")
    text = json.dumps(proj, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote %s" % args.out)
        if proj["_todo"]:
            print("TODO (complete these before running):")
            for t in proj["_todo"]:
                print("  - " + t)
    else:
        print(text)


if __name__ == "__main__":
    main()
