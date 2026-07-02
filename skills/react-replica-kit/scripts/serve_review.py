#!/usr/bin/env python3
"""
serve_review.py — browse legacy-vs-React side by side with the parity verdict.

Reads the parity reports already produced by parity-verify and serves a single page that, per screen,
shows: PASS/FAIL + pixel% + critical count, the side-by-side.png (legacy | react | diff), a link to the
full report, and (optionally) a live iframe to the running React app.

Usage:
  python scripts/serve_review.py --work-dir work --react-base-url http://localhost:5173 --port 8800
Then open http://localhost:8800
Stdlib only.
"""
import argparse, json, glob, os, sys, html, functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def collect(work_dir):
    # v2 per-view layout: <work>/<view>/parity/<name>.parity-report.json  (recursive glob handles either).
    rows = []
    reps = glob.glob(os.path.join(work_dir, "**", "*.parity-report.json"), recursive=True)
    for rep in sorted(reps):
        try:
            d = json.load(open(rep, encoding="utf-8"))
        except Exception:
            continue
        name = d.get("name") or os.path.basename(rep).split(".")[0]
        g = d.get("gate", {})
        viewdir = os.path.dirname(os.path.dirname(rep))          # <view>/  (parent of parity/)
        relview = os.path.relpath(viewdir, work_dir).replace("\\", "/")
        pref = "" if relview in (".", "") else relview + "/"
        rows.append({
            "name": name,
            "pass": bool(g.get("pass")),
            "ratio": g.get("pixel_ratio"),
            "critical": g.get("critical_structural"),
            "nesting": g.get("nesting_structural", 0),
            "data_mode": g.get("data_mode", "?"),
            "data_present": g.get("data_present", True),
            "sxs": f"{pref}parity/{name}.side-by-side.png",
            "legacy": f"{pref}legacy.png",
            "report": f"{pref}parity/{name}.parity-report.md",
        })
    return rows


def render(rows, react_base):
    passed = sum(1 for r in rows if r["pass"])
    cards = []
    for r in rows:
        badge = "✅ PASS" if r["pass"] else "❌ FAIL"
        color = "#137333" if r["pass"] else "#c5221f"
        ratio = f"{(r['ratio'] or 0)*100:.3f}%" if r["ratio"] is not None else "n/a"
        datatag = f"· data {html.escape(str(r['data_mode']))}{'' if r['data_present'] else ' ⚠️MISSING'}"
        live = (f'<iframe src="{html.escape(react_base)}#/{html.escape(r["name"])}" '
                f'width="480" height="300" style="border:1px solid #ccc"></iframe>') if react_base else ""
        cards.append(f"""
        <section style="margin:24px 0;border-top:1px solid #eee;padding-top:16px">
          <h2 style="font:600 16px sans-serif">{html.escape(r['name'])}
            <span style="color:{color}">{badge}</span>
            <small style="color:#555;font-weight:400">· pixel {ratio} · critical {r['critical']} · nesting {r['nesting']} {datatag}</small>
            <a href="{r['report']}" style="font-size:12px;margin-left:8px">report.md</a>
          </h2>
          <p style="font:12px sans-serif;color:#777">legend: legacy | react | diff</p>
          <img src="{r['sxs']}" style="max-width:100%;border:1px solid #ddd"
               onerror="this.replaceWith(Object.assign(document.createElement('em'),{{textContent:'no side-by-side.png yet — run verify_screen.py'}}))"/>
          {live}
        </section>""")
    return f"""<!doctype html><meta charset="utf-8"><title>jsp2react review</title>
    <body style="max-width:1100px;margin:24px auto;font-family:sans-serif">
    <h1>jsp2react — side-by-side review</h1>
    <p>{passed}/{len(rows)} screens verified. React app: {html.escape(react_base) or '(not provided)'}</p>
    {''.join(cards) or '<p>No parity reports found under work/parity/. Run verify_screen.py first.</p>'}
    </body>"""


def self_check():
    """Exercise collect() + render() on a synthetic parity report — no port, no browser."""
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="j2r_review_")
    try:
        os.makedirs(os.path.join(d, "v1", "parity"))
        json.dump({"name": "v1_default", "gate": {"pass": True, "pixel_ratio": 0.001,
                   "critical_structural": 0, "nesting_structural": 3, "data_mode": "record",
                   "data_present": True}},
                  open(os.path.join(d, "v1", "parity", "v1_default.parity-report.json"), "w"))
        rows = collect(d)
        assert len(rows) == 1 and rows[0]["pass"] and rows[0]["nesting"] == 3, rows
        page = render(rows, "")
        assert "v1_default" in page and "PASS" in page and "nesting 3" in page, page[:300]
        print(json.dumps({"self_check": "ok", "rows": 1, "render": "ok"}))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Serve a legacy-vs-React side-by-side review page.")
    if "--self-check" in sys.argv:
        return self_check()
    ap.add_argument("--work-dir", required=True, help="Evidence root (contains screenshots/ and parity/).")
    ap.add_argument("--react-base-url", default="", help="Running React dev server (optional live iframe).")
    ap.add_argument("--port", type=int, default=8800)
    args = ap.parse_args()

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = render(collect(args.work_dir), args.react_base_url).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

    handler = functools.partial(Handler, directory=args.work_dir)
    print(f"review server on http://localhost:{args.port}  (serving {args.work_dir})")
    ThreadingHTTPServer(("0.0.0.0", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
