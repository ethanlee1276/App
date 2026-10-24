"""Lighthouse on the first screen, so a slower night is a number, not a feeling.

    python3 tools/lighthouse_check.py                  # three runs, the median, against the baseline
    python3 tools/lighthouse_check.py --write-baseline # after a change that is meant to move it

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 15, Lighthouse in the nightly run beside the browser checks. It
serves the real app (server.Handler, as rendercheck does) with the same
board the first-screen test loads (tests/test_the_first_screen_holds_still),
runs Lighthouse's mobile preset (a mid-range phone: the CPU slowed 4x, a slow
4G connection, simulated) three times, and takes the median of each number,
because one Lighthouse run wanders by several points.

It fails (exit 1) when the median falls clearly past the baseline in
tools/lighthouse_baseline.json: the score 10 points down, the largest paint
or time-to-interactive 30% slower, blocked time 50% and 150 ms worse, or the
layout shifting past 0.1 (Google's "good" line). A single bad night is run
again before it is called a regression (the nightly prompt says so); the
baseline moves only with --write-baseline, after a change meant to move it.

Lighthouse is fetched by npx at a pinned version (or LIGHTHOUSE names a
binary); Chromium is the preinstalled one (or CHROME_PATH). Neither present:
it says so and exits 0 — that is the environment, not the page.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools" / "lighthouse_baseline.json"
VERSION = "13.5.0"
RUNS = 3
#: What each number may drift before the night is called slower.
SLACK = {"score": -10, "lcp_ms": 1.30, "tti_ms": 1.30, "tbt_ms": (1.5, 150), "cls": 0.1}


def _chrome() -> str:
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            return pw.chromium.executable_path
    except Exception:                                               # noqa: BLE001
        return shutil.which("chromium") or shutil.which("google-chrome") or ""


def _lighthouse() -> list:
    if os.environ.get("LIGHTHOUSE"):
        return [os.environ["LIGHTHOUSE"]]
    return [shutil.which("npx") or "npx", "--yes", f"lighthouse@{VERSION}"] if shutil.which("npx") else []


#: What Caddy compresses (deploy/Caddyfile `encode`); the rest goes as is.
TEXT = (".js", ".css", ".html", ".svg", ".webmanifest")


def _serve(board: bytes):
    """The real handler, with the first-screen test's board where the page
    asks for one (and an empty object for every other data file), and the
    code served as the box serves it: the trimmed copy where engine/shrink
    makes one, compressed — so the numbers are the live site's, not those
    of a 2.4 MB uncompressed script."""
    import gzip
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, str(ROOT))
    from engine import shrink
    from server import Handler as App, WEB
    cache: dict = {}

    class Handler(App):
        def log_message(self, *a, **kw):
            pass

        def do_GET(self):
            p = urlparse(self.path).path
            if p.startswith(("/data/recommendations", "/api/recommendations")):
                return self._send(200, board, ".json")
            if p.startswith("/data/") or p.startswith("/api/"):
                return self._send(200, b"{}", ".json")
            rel = "index.html" if p in ("", "/") else p.lstrip("/")
            f = WEB / rel
            if (rel.endswith(TEXT) and rel != "sw.js" and "gzip" in (self.headers.get("Accept-Encoding") or "")
                    and f.is_file() and f.resolve().is_relative_to(WEB.resolve())):
                if rel not in cache:
                    src = f.read_text(encoding="utf-8")
                    try:
                        src = shrink.trimmed(rel, src) if rel in shrink.FILES else src
                    except Exception:                               # noqa: BLE001 — the box serves the original then too
                        pass
                    cache[rel] = gzip.compress(src.encode("utf-8"), 6)
                return self._send(200, cache[rel], Path(rel).suffix, headers=[("Content-Encoding", "gzip")])
            return super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _board() -> bytes:
    sys.path.insert(0, str(ROOT / "tests"))
    from test_the_first_screen_holds_still import _board as board
    return json.dumps(board()).encode()


def numbers(report: dict) -> dict:
    """The five numbers out of one Lighthouse report."""
    a = report.get("audits") or {}
    val = lambda k: (a.get(k) or {}).get("numericValue")          # noqa: E731
    score = ((report.get("categories") or {}).get("performance") or {}).get("score")
    return {"score": round(score * 100) if score is not None else None,
            "lcp_ms": round(val("largest-contentful-paint") or 0), "tbt_ms": round(val("total-blocking-time") or 0),
            "cls": round(val("cumulative-layout-shift") or 0, 3), "tti_ms": round(val("interactive") or 0),
            "fcp_ms": round(val("first-contentful-paint") or 0), "si_ms": round(val("speed-index") or 0)}


def median(runs: list) -> dict:
    return {k: (statistics.median([r[k] for r in runs if r.get(k) is not None]) if any(r.get(k) is not None for r in runs)
                else None) for k in runs[0]}


def verdict(now: dict, base: dict) -> list:
    """What got clearly slower than the baseline, in words; [] when nothing did."""
    out = []
    if base.get("score") is not None and now.get("score") is not None and now["score"] < base["score"] + SLACK["score"]:
        out.append(f"score {now['score']:.0f} (baseline {base['score']:.0f})")
    for k, name in (("lcp_ms", "largest paint"), ("tti_ms", "interactive")):
        if base.get(k) and now.get(k) and now[k] > base[k] * SLACK[k]:
            out.append(f"{name} {now[k] / 1000:.1f} s (baseline {base[k] / 1000:.1f} s)")
    mult, add = SLACK["tbt_ms"]
    if base.get("tbt_ms") is not None and now.get("tbt_ms") is not None and now["tbt_ms"] > max(base["tbt_ms"] * mult, base["tbt_ms"] + add):
        out.append(f"blocked {now['tbt_ms']:.0f} ms (baseline {base['tbt_ms']:.0f} ms)")
    if now.get("cls") is not None and now["cls"] > SLACK["cls"]:
        out.append(f"layout shift {now['cls']:.3f} (over 0.1)")
    return out


def line(m: dict) -> str:
    return (f"performance {m['score']:.0f} · largest paint {m['lcp_ms'] / 1000:.1f} s · blocked {m['tbt_ms']:.0f} ms · "
            f"shift {m['cls']:.3f} · interactive {m['tti_ms'] / 1000:.1f} s")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    chrome, lh = _chrome(), _lighthouse()
    if not chrome or not os.path.exists(chrome) or not lh:
        print(f"Lighthouse skipped: {'no Chromium' if not chrome or not os.path.exists(chrome) else 'no npx'} in this environment.")
        return 0
    srv, port = _serve(_board())
    out_dir = Path(tempfile.mkdtemp())
    runs = []
    try:
        for i in range(RUNS):
            path = out_dir / f"run{i}.json"
            cmd = lh + [f"http://127.0.0.1:{port}/index.html?sport=nfl#recommended", "--quiet", "--output=json",
                        f"--output-path={path}", "--only-categories=performance",
                        "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage"]
            got = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                 env=dict(os.environ, CHROME_PATH=chrome))
            if got.returncode != 0 or not path.exists():
                print(f"Lighthouse run {i + 1} failed: {(got.stderr or got.stdout).strip()[-400:]}")
                continue
            runs.append(numbers(json.loads(path.read_text(encoding="utf-8"))))
    finally:
        srv.shutdown()
        srv.server_close()
    if not runs:
        print("Lighthouse could not finish a run (see above).")
        return 1
    m = median(runs)
    print(f"Lighthouse, mobile preset, median of {len(runs)}: {line(m)}")
    if "--write-baseline" in argv:
        BASELINE.write_text(json.dumps(dict(m, measured=time.strftime("%Y-%m-%d"), lighthouse=VERSION), indent=1) + "\n")
        print(f"Baseline written: {BASELINE.relative_to(ROOT)}")
        return 0
    try:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("No baseline yet: run with --write-baseline.")
        return 0
    worse = verdict(m, base)
    if worse:
        print("SLOWER than the baseline (" + base.get("measured", "?") + "): " + "; ".join(worse))
        return 1
    print(f"Within the baseline of {base.get('measured', '?')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
