#!/usr/bin/env python3
"""
capture_fixtures.py — turn REAL recorded responses into MSW replay handlers (record mode).

Input  : --har <responses.har>  (preferred — the REAL backend responses recorded by
         capture_screen.py --record-har), and/or --network <name>.network.json files.
Output : <out>/fixtures.json     — { "<METHOD> <pathname>": {status, content_type, body, query_seen[]} }
         <out>/handlers.ts       — MSW v2 handlers replaying those responses (same endpoint paths).

This is the RECORD-mode data layer: the React replica renders the SAME REAL data the legacy screen
showed, with no live backend and NO hand-authored/fake fixtures. Same paths are wired, so live mode
(Vite proxy, MSW off) hits the real backend unchanged.

By default the top-level HTML document response is skipped (it's the page, not a data call the React
app makes); use --include-documents to keep it. Deterministic; no browser needed.
"""
import argparse, base64, json, os, sys
from urllib.parse import urlsplit


def load_records(paths):
    recs = []
    for p in paths or []:
        try:
            data = json.load(open(p, encoding="utf-8"))
            recs.extend(data if isinstance(data, list) else data.get("network", []))
        except Exception as e:
            print(f"[warn] {p}: {e}", file=sys.stderr)
    return recs


def har_records(paths):
    """Convert Playwright HAR entries -> the same rec shape build() consumes (REAL responses)."""
    recs = []
    for p in paths or []:
        try:
            log = json.load(open(p, encoding="utf-8")).get("log", {})
        except Exception as e:
            print(f"[warn] {p}: {e}", file=sys.stderr); continue
        for e in log.get("entries", []):
            req, resp = e.get("request", {}), e.get("response", {})
            content = resp.get("content", {})
            mime = content.get("mimeType", "") or ""
            text = content.get("text")
            if text is not None and content.get("encoding") == "base64":
                try:
                    text = base64.b64decode(text).decode("utf-8", "replace")
                except Exception:
                    text = None
            method = req.get("method", "GET")
            # Prefer Playwright's own resource type (xhr/fetch/document/stylesheet/...). Fall back to a
            # heuristic ONLY when it's absent: a GET text/html navigation is the skippable page document, but an
            # XHR HTML FRAGMENT (legacy contentlets are POST and/or return text/html) is REAL DATA — it must not
            # be misclassified as the document and dropped.
            rt = e.get("_resourceType")
            if not rt:
                low = mime.split(";", 1)[0].strip().lower()
                if low == "text/html":
                    rt = "document" if method.upper() == "GET" else "xhr"   # a POST html fragment is DATA
                elif low == "text/css":
                    rt = "stylesheet"
                elif "javascript" in low or low == "application/ecmascript":
                    rt = "script"
                elif low.startswith("image/"):
                    rt = "image"
                elif low.startswith("font/") or "font" in low:
                    rt = "font"
                else:
                    rt = "xhr"   # json / xml / plain / form-encoded = DATA
            recs.append({"method": method, "url": req.get("url", ""),
                         "status": resp.get("status", 200),
                         "resource_type": rt, "content_type": mime, "body": text})
    return recs


def key_for(rec):
    u = urlsplit(rec.get("url", ""))
    return f'{rec.get("method","GET").upper()} {u.path}', u.query


def body_value(rec):
    body = rec.get("body")
    ct = rec.get("content_type", "")
    if body is None:
        return None, ct
    if "json" in ct:
        try:
            return json.loads(body), ct
        except Exception:
            return body, ct
    return body, ct  # text/xml/html kept as string


def ts_literal(v):
    """Embed a fixture value as a TS expression."""
    return json.dumps(v, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="Build MSW replay handlers from REAL recorded responses (HAR) and/or network.json.")
    ap.add_argument("--har", nargs="+", help="One or more responses.har files (real responses from capture_screen.py --record-har). Preferred.")
    ap.add_argument("--network", nargs="+", help="One or more *.network.json files (alternative source).")
    ap.add_argument("--out", help="Output directory (fixtures.json + handlers.ts). Required for a real run.")
    ap.add_argument("--include-documents", action="store_true", help="Also include the top-level HTML document responses.")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        net = [{"method": "GET", "url": "http://h/app/summary.do?id=123", "status": 200,
                "resource_type": "xhr", "content_type": "application/json", "body": '{"rows":[1,2]}'}]
        fx = build(net, False)
        assert "GET /app/summary.do" in fx and fx["GET /app/summary.do"]["body"] == {"rows": [1, 2]}, fx
        har = {"log": {"entries": [{"request": {"method": "GET", "url": "http://h/api/comp?id=123"},
                "response": {"status": 200, "content": {"mimeType": "application/json", "text": '{"ok":true}'}}}]}}
        import tempfile
        tf = os.path.join(tempfile.gettempdir(), "j2r_selfcheck.har")
        json.dump(har, open(tf, "w"))
        fx2 = build(har_records([tf]), False)
        os.remove(tf)
        assert "GET /api/comp" in fx2 and fx2["GET /api/comp"]["body"] == {"ok": True}, fx2

        # regression: a POST text/html CONTENTLET is real data (kept); the GET text/html PAGE document and
        # static assets are dropped — this is the bug where AJAX HTML fragments were misclassified as documents.
        #   (assets carry NO _resourceType here, so they exercise the mime-based fallback)
        har3 = {"log": {"entries": [
            {"request": {"method": "GET", "url": "http://h/app/dispatcher.do?page=fasummary"},
             "response": {"status": 200, "content": {"mimeType": "text/html", "text": "<html>page</html>"}}},
            {"request": {"method": "POST", "url": "http://h/app/ajaxProfileAction.do"},
             "response": {"status": 200, "content": {"mimeType": "text/html", "text": "<div>profile</div>"}}},
            {"request": {"method": "GET", "url": "http://h/app/app.css"},
             "response": {"status": 200, "content": {"mimeType": "text/css", "text": "body{}"}}},
            {"request": {"method": "GET", "url": "http://h/app/jquery.min.js"},
             "response": {"status": 200, "content": {"mimeType": "application/javascript", "text": "var x=1"}}},
        ]}}
        tf3 = os.path.join(tempfile.gettempdir(), "j2r_selfcheck3.har")
        json.dump(har3, open(tf3, "w"))
        fx3 = build(har_records([tf3]), False)
        os.remove(tf3)
        assert "POST /app/ajaxProfileAction.do" in fx3, ("contentlet AJAX dropped", fx3)
        assert not any(k.endswith((".css", ".js")) or "dispatcher.do" in k for k in fx3), ("page/asset leaked", fx3)
        assert len(fx3) == 1, fx3
        print(json.dumps({"self_check": "ok", "network_keys": list(fx), "har_keys": list(fx2),
                          "regression_keys": list(fx3)}))
        return

    if not args.out:
        raise SystemExit("--out is required (or use --self-check)")
    if not (args.har or args.network):
        raise SystemExit("pass --har (preferred) and/or --network")
    recs = har_records(args.har) + load_records(args.network)
    fixtures = build(recs, args.include_documents)
    os.makedirs(args.out, exist_ok=True)
    json.dump(fixtures, open(os.path.join(args.out, "fixtures.json"), "w", encoding="utf-8"), indent=1)
    open(os.path.join(args.out, "handlers.ts"), "w", encoding="utf-8").write(render_handlers(fixtures))
    print(json.dumps({"ok": True, "endpoints": len(fixtures), "out": args.out,
                      "keys": list(fixtures)[:20]}, indent=1))


DATA_TYPES = {"xhr", "fetch"}  # the calls a React app actually replays for DATA


def build(recs, include_documents):
    fixtures = {}
    for rec in recs:
        rt = rec.get("resource_type")
        if rt == "document":
            if not include_documents:
                continue
        elif rt not in DATA_TYPES:
            continue  # skip assets (stylesheet/script/image/font/...) — not data the React app replays
        key, query = key_for(rec)
        body, ct = body_value(rec)
        if key not in fixtures:
            fixtures[key] = {"status": rec.get("status", 200), "content_type": ct,
                             "body": body, "query_seen": []}
        if query and query not in fixtures[key]["query_seen"]:
            fixtures[key]["query_seen"].append(query)
    return fixtures


def render_handlers(fixtures):
    lines = [
        "// AUTO-GENERATED by capture_fixtures.py — MSW v2 handlers returning captured legacy data.",
        "// Same endpoint paths as the legacy app, so disabling MSW hits the real backend unchanged.",
        "import { http, HttpResponse } from 'msw'",
        "import fixtures from './fixtures.json'",
        "",
        "type Fx = { status: number; content_type: string; body: unknown }",
        "const fx = fixtures as Record<string, Fx>",
        "",
        "function respond(key: string) {",
        "  const f = fx[key]",
        "  if (!f) return HttpResponse.json({ error: 'no fixture: ' + key }, { status: 501 })",
        "  if (f.content_type && f.content_type.includes('json')) return HttpResponse.json(f.body as any, { status: f.status })",
        "  return new HttpResponse(f.body as any, { status: f.status, headers: { 'content-type': f.content_type || 'text/plain' } })",
        "}",
        "",
        "export const handlers = [",
    ]
    for key in fixtures:
        method, path = key.split(" ", 1)
        verb = method.lower()
        if verb not in ("get", "post", "put", "patch", "delete", "head", "options"):
            verb = "all"
        lines.append(f"  http.{verb}({ts_literal(path)}, () => respond({ts_literal(key)})),")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
