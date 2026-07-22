#!/usr/bin/env python3
"""Zero-dependency web server for the betting engine.

Serves the static dashboard in ``web/`` and exposes a live JSON API at
``/api/recommendations`` that re-runs the engine on every request — so the
threshold controls in the UI recalculate against the real model, not a cached
file. Uses only the Python standard library.

    python3 server.py           # http://localhost:8000
    python3 server.py 9000      # custom port
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from engine.pipeline import run_slate
from engine.rules import RuleConfig

ROOT = Path(__file__).parent
WEB = ROOT / "web"
SLATE = ROOT / "data" / "sample_slate.json"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write("  %s\n" % (fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/recommendations", "/api/recommendations/"):
            return self._api(parse_qs(parsed.query))
        return self._static(parsed.path)

    # --- API ---------------------------------------------------------------
    def _api(self, query: dict):
        def qf(name, default):
            try:
                return float(query.get(name, [default])[0])
            except (TypeError, ValueError):
                return default

        config = RuleConfig(
            min_confidence=qf("min_confidence", 6.0),
            min_edge=qf("min_edge", 0.02) / (100 if qf("min_edge", 0.02) > 1 else 1),
        )
        try:
            result = run_slate(SLATE, config)
            payload = json.dumps(result).encode()
        except Exception as exc:  # surface engine errors as JSON
            self._send(500, json.dumps({"error": str(exc)}).encode(), ".json")
            return
        self._send(200, payload, ".json")

    # --- Static files ------------------------------------------------------
    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        target = (WEB / path.lstrip("/")).resolve()
        # Prevent path traversal outside the web root.
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            self._send(404, b"Not found", ".html")
            return
        self._send(200, target.read_bytes(), target.suffix)

    def _send(self, code: int, body: bytes, suffix: str):
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"NFL prop engine running → http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
