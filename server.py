#!/usr/bin/env python3
"""Zero-dependency web server for the betting engine.

Serves the static dashboard in ``web/`` and exposes a live JSON API at
``/api/recommendations`` that re-runs the engine on every request — so the
threshold controls in the UI recalculate against the real model, not a cached
file. Uses only the Python standard library.

    python3 server.py           # http://localhost:8000, sample data
    python3 server.py 9000      # custom port
    python3 server.py --live    # serve pre-built live data (see LAUNCH.md)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from engine.pipeline import run_slate
from engine.mlb.pipeline import run_mlb_slate
from engine.rules import RuleConfig

ROOT = Path(__file__).parent
WEB = ROOT / "web"
SLATE = ROOT / "data" / "sample_slate.json"
MLB_SLATE = ROOT / "data" / "mlb_sample_slate.json"

# In --live mode the API serves these freshly-built files (written by
# mlb_build.py / nfl_build.py --out ...) instead of re-running the sample slate.
LIVE_FILES = {
    "nfl": WEB / "data" / "recommendations.json",
    "mlb": WEB / "data" / "mlb_recommendations.json",
    "nba": WEB / "data" / "nba.json",
    "wnba": WEB / "data" / "wnba.json",
    "cfb": WEB / "data" / "cfb.json",
}

# Sleeper league-sync proxy: the browser can't always call api.sleeper.app
# directly (CORS), so the site talks to us and we forward READ-ONLY requests.
# Allowlisted paths only — this must never become an open proxy.
SLEEPER_BASE = "https://api.sleeper.app/v1/"
_SLEEPER_OK = re.compile(
    r"^(user/[A-Za-z0-9_]{1,40}"
    r"|user/\d{1,25}/leagues/nfl/\d{4}"
    r"|league/\d{1,25}(/rosters|/users|/drafts)?"
    r"|draft/\d{1,25}(/picks)?"
    r"|players/nfl)$")


def sleeper_path_ok(path: str) -> bool:
    return bool(_SLEEPER_OK.match(path))


# ---------------------------------------------------------------------------
# Accounts — one name, every device.
#
# WHY: the site's personal data (My Bets, the Sleeper league link, the
# bankroll) lived in localStorage, which is scoped to ONE browser at ONE
# address. The laptop at localhost, the phone at the LAN address and a
# tailscale name are three different origins — three separate empty
# copies — and iOS evicts a site's storage after a week away. So the
# info had to be re-typed per device (Ethan, 2026-08-10: "make an
# account so you don't have to put in that info every time").
#
# WHAT AN ACCOUNT IS HERE: a JSON file under data/profiles/ on the
# machine already running this server. No cloud, no email, no third
# party — the data moves between devices through the same laptop that
# serves the site, and never further. The optional PIN keeps housemates
# on the same Wi-Fi out of your book; it is stored salted + hashed
# (PBKDF2) and checked on every request. Honesty about its strength:
# the site speaks plain HTTP on a LAN, so the PIN is a lock on the
# door, not encryption in transit — the threat model is "someone else
# on the couch", not a hostile network. Sportsbook credentials remain
# un-asked-for, same as always.
#
# SYNC CONTRACT (the client POSTs its sections, gets the merged truth
# back — one round trip is both push and pull):
#   - fantasy / bankroll: last-writer-wins by the section's `ts` stamp.
#   - mybets: UNION by bet signature, because a logged bet is the one
#     thing that must never be lost to a timestamp race between two
#     open devices. Deletions travel as signature tombstones so a
#     deleted bet stays deleted; on a signature collision the settled
#     copy beats the pending one (the common edit is marking a result).
PROFILE_DIR = ROOT / "data" / "profiles"
PROFILE_SECTIONS = ("mybets", "fantasy", "bankroll")
MAX_PROFILE_BYTES = 1_000_000        # thousands of bets fit; junk bounces
MAX_TOMBSTONES = 500
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_-]{2,24}$")
_PROFILE_PIN = re.compile(r"^\d{4,12}$")
_PROFILE_LOCK = threading.Lock()


def profile_name_ok(name) -> bool:
    return isinstance(name, str) and bool(_PROFILE_NAME.match(name))


def profile_pin_ok(pin) -> bool:
    return isinstance(pin, str) and bool(_PROFILE_PIN.match(pin))


def _pin_hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt),
                               60_000).hex()


def _pin_matches(profile: dict, pin) -> bool:
    stored = profile.get("pin")
    if not stored:
        return True                  # no PIN on the account → open door
    if not isinstance(pin, str) or not pin:
        return False
    return _pin_hash(pin, stored["salt"]) == stored["hash"]


def _profile_path(name: str) -> Path:
    return PROFILE_DIR / (name.lower() + ".json")


def _load_profile(name: str) -> dict | None:
    try:
        return json.loads(_profile_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_profile(profile: dict) -> None:
    """Atomic: the 20s-poll lesson from the meme board applies to any
    file two requests can touch — write beside, then replace."""
    path = _profile_path(profile["name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(profile), encoding="utf-8")
    os.replace(tmp, path)


def _num_str(v) -> str:
    """Match how the browser prints a number into the bet signature:
    String(25.0) is "25", String(25.5) is "25.5". Signatures computed
    here must equal the ones the client computes, or the client's
    tombstones would never match anything."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else repr(f)


def bet_sig(b: dict) -> str:
    return "|".join([str(b.get("date", "")), str(b.get("book", "")),
                     str(b.get("desc", "")).lower().strip(),
                     _num_str(b.get("stake")), _num_str(b.get("odds"))])


def _clean_section(sec) -> dict | None:
    if not isinstance(sec, dict):
        return None
    try:
        ts = int(sec.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0
    return {"ts": max(0, ts), "data": sec.get("data")}


def _merge_mybets(stored: dict | None, incoming: dict | None) -> dict:
    """Union by signature minus tombstones — never lose a bet to a race."""
    def rows_of(sec):
        d = (sec or {}).get("data") or {}
        rows = d.get("rows") if isinstance(d, dict) else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def dels_of(sec):
        d = (sec or {}).get("data") or {}
        dels = d.get("deleted") if isinstance(d, dict) else None
        return [s for s in dels if isinstance(s, str)] if isinstance(dels, list) else []

    deleted = list(dict.fromkeys(dels_of(stored) + dels_of(incoming)))[-MAX_TOMBSTONES:]
    dead = set(deleted)
    merged: dict[str, dict] = {}
    for r in rows_of(stored) + rows_of(incoming):     # incoming later → wins ties
        sig = bet_sig(r)
        if sig in dead:
            continue
        prev = merged.get(sig)
        # The common edit is pending → win/loss; never let a stale
        # pending copy from the other device un-settle a graded bet.
        if prev and str(prev.get("result", "pending")) != "pending" \
                and str(r.get("result", "pending")) == "pending":
            continue
        merged[sig] = r
    s_ts = (stored or {}).get("ts", 0)
    i_ts = (incoming or {}).get("ts", 0)
    out = {"ts": max(s_ts, i_ts), "data": {"rows": list(merged.values()),
                                           "deleted": deleted}}
    # If the union differs from what the client just sent, bump the stamp
    # past the client's own so it adopts the merged book on this reply.
    sent = {bet_sig(r): str(r.get("result", "pending")) for r in rows_of(incoming)}
    got = {k: str(v.get("result", "pending")) for k, v in merged.items()}
    if got != sent or set(dels_of(incoming)) != dead:
        out["ts"] = max(out["ts"], int(time.time() * 1000)) + 1
    return out


def merge_sections(stored: dict, incoming: dict) -> dict:
    out = dict(stored)
    for key in PROFILE_SECTIONS:
        inc = _clean_section(incoming.get(key))
        if key == "mybets":
            if inc is not None or key in out:
                out[key] = _merge_mybets(out.get(key), inc)
            continue
        if inc is None:
            continue
        cur = out.get(key)
        # STRICT newer-than: an equal stamp means "nothing changed here
        # since my last sync", and adopting it anyway would let a client
        # whose localStorage was error-cleared (the Sleeper catch path
        # removes ff_user without re-stamping) erase the stored copy.
        if cur is None or inc["ts"] > cur.get("ts", 0):
            out[key] = inc
    return out


def _public(profile: dict) -> dict:
    return {"name": profile["name"], "has_pin": bool(profile.get("pin")),
            "sections": profile.get("sections", {})}


def profile_get(name, pin) -> tuple[int, dict]:
    if not profile_name_ok(name):
        return 400, {"error": "account names are 2–24 letters, digits, - or _"}
    with _PROFILE_LOCK:
        profile = _load_profile(name)
    if profile is None:
        return 404, {"error": f"no account named “{name}” — create it first"}
    if not _pin_matches(profile, pin):
        return 403, {"error": "wrong PIN for that account"}
    return 200, _public(profile)


def profile_sync(name, pin, sections) -> tuple[int, dict]:
    """Create-or-merge. POSTing to a fresh name IS account creation (the
    PIN sent then becomes the account's PIN); POSTing to an existing one
    verifies the PIN, merges per the contract, and returns the result."""
    if not profile_name_ok(name):
        return 400, {"error": "account names are 2–24 letters, digits, - or _"}
    if pin and not profile_pin_ok(pin):
        return 400, {"error": "PIN must be 4–12 digits"}
    if sections is None:
        sections = {}
    if not isinstance(sections, dict):
        return 400, {"error": "sections must be an object"}
    with _PROFILE_LOCK:
        profile = _load_profile(name)
        if profile is None:
            profile = {"name": name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "sections": {}}
            if pin:
                salt = os.urandom(16).hex()
                profile["pin"] = {"salt": salt, "hash": _pin_hash(pin, salt)}
        elif not _pin_matches(profile, pin):
            return 403, {"error": "wrong PIN for that account"}
        profile["sections"] = merge_sections(profile.get("sections", {}), sections)
        _save_profile(profile)
    return 200, _public(profile)


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


_TLS_HINTED = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write("  %s\n" % (fmt % args))

    def handle_one_request(self):
        # A TLS ClientHello (first byte 0x16) on this plain-HTTP port means
        # a phone typed — or Safari silently upgraded to — https://. Without
        # this check the log sprays cipher-suite bytes as "Bad request
        # version" garbage; name the actual problem once instead.
        try:
            peek = self.rfile.peek(1)[:1]
        except Exception:
            peek = b""
        if peek == b"\x16":
            global _TLS_HINTED
            if not _TLS_HINTED:
                _TLS_HINTED = True
                sys.stderr.write(
                    "  ↳ A device tried HTTPS against this HTTP-only server.\n"
                    "    On the phone, spell out http:// in the address —\n"
                    "    Safari silently upgrades bare addresses to https.\n"
                    "    Want a real https:// URL? Run:  tailscale serve --bg 8000\n"
                    "    then use the https://…ts.net link it prints. docs/PHONE.md has details.\n")
            self.close_connection = True
            return
        super().handle_one_request()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/recommendations", "/api/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="nfl")
        if parsed.path in ("/api/mlb/recommendations", "/api/mlb/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="mlb")
        if parsed.path in ("/api/nba/recommendations", "/api/nba/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="nba")
        if parsed.path in ("/api/wnba/recommendations", "/api/wnba/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="wnba")
        if parsed.path in ("/api/cfb/recommendations", "/api/cfb/recommendations/"):
            return self._api(parse_qs(parsed.query), sport="cfb")
        if parsed.path in ("/api/draftadvice", "/api/draftadvice/"):
            return self._draft_advice(parse_qs(parsed.query))
        if parsed.path.startswith("/api/sleeper/"):
            return self._sleeper(parsed.path[len("/api/sleeper/"):].strip("/"))
        if parsed.path.startswith("/api/profile/"):
            code, body = profile_get(parsed.path[len("/api/profile/"):].strip("/"),
                                     self.headers.get("X-Profile-Pin") or "")
            return self._send(code, json.dumps(body).encode(), ".json")
        return self._static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/profile/"):
            return self._send(404, b'{"error":"unknown endpoint"}', ".json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_PROFILE_BYTES:
            return self._send(413, b'{"error":"profile payload too large"}', ".json")
        try:
            body = json.loads(self.rfile.read(length))
            assert isinstance(body, dict)
        except Exception:
            return self._send(400, b'{"error":"body must be a JSON object"}', ".json")
        code, out = profile_sync(
            parsed.path[len("/api/profile/"):].strip("/"),
            body.get("pin") or self.headers.get("X-Profile-Pin") or "",
            body.get("sections"))
        self._send(code, json.dumps(out).encode(), ".json")

    def _draft_advice(self, query: dict):
        """Pick-by-pick advice for a live Sleeper draft.

        WHY THIS IS A SERVER ENDPOINT rather than more JavaScript. The
        survival model has real arithmetic in it — a reach window fitted
        from the room's own picks, and a probability derived from it — and
        arithmetic that decides what to do with a first-round pick belongs
        somewhere it can be unit-tested. The browser already polls the
        picks; this reads the SAME cached fetch, so the endpoint costs no
        extra request to Sleeper.

        Both reads go through the allowlist, exactly as `_sleeper` does.
        """
        draft_id = (query.get("draft") or [""])[0].strip()
        user_id = (query.get("user") or [""])[0].strip()
        if not re.fullmatch(r"\d{1,25}", draft_id):
            return self._send(400, b'{"error":"bad draft id"}', ".json")
        from engine import fantasy_pick, fantasy_ranks
        from engine.sources.fetch import fetch_text, DataUnavailable

        def grab(path, ttl):
            if not sleeper_path_ok(path):
                raise DataUnavailable(f"path not allowlisted: {path}")
            cache = "sleeper_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
            return json.loads(fetch_text(SLEEPER_BASE + path, cache, ttl=ttl))

        try:
            # Same TTLs the proxy uses: the draft's shape barely moves,
            # the picks are polled DURING a live draft and ten seconds is
            # already the floor. Reusing them means this endpoint rides
            # the browser's existing poll rather than doubling it.
            draft = grab(f"draft/{draft_id}", ttl=300)
            raw = grab(f"draft/{draft_id}/picks", ttl=10)
        except (DataUnavailable, ValueError) as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(),
                              ".json")

        picks = []
        for p in raw or []:
            meta = (p or {}).get("metadata") or {}
            name = " ".join(x for x in (meta.get("first_name"),
                                        meta.get("last_name")) if x)
            key = fantasy_ranks.normalize(name)
            if key:
                picks.append({"key": key, "player": name,
                              "picked_by": str(p.get("picked_by") or ""),
                              "pick_no": p.get("pick_no")})

        # The board and the consensus ranks come off the built payload —
        # the same file the page is already showing.
        try:
            blob = json.loads((WEB / "data" / "fantasy.json").read_text())
        except Exception:                                     # noqa: BLE001
            blob = {}
        board = []
        for i, row in enumerate((blob.get("draft_kit") or {}).get("board") or []):
            key = fantasy_ranks.normalize(row.get("player"))
            if key:
                board.append({**row, "key": key})
        ranks = {r["key"]: (r.get("consensus") or i + 1)
                 for i, r in enumerate((blob.get("ranks") or {}).get("rows") or [])
                 if r.get("key")}
        if not ranks:                       # no ranks built yet: use the board
            ranks = {r["key"]: i + 1 for i, r in enumerate(board)}

        # STARTER SLOTS COME FROM THE DRAFT, NOT FROM A GUESS. Sleeper's
        # settings carry slots_qb / slots_rb / … , so a superflex or a
        # 3-WR league gets its own needs rather than a 12-team default
        # that would tell a superflex room to take one quarterback.
        st = draft.get("settings") or {}
        slots = {}
        for pos in ("QB", "RB", "WR", "TE"):
            n = st.get("slots_" + pos.lower())
            if isinstance(n, (int, float)) and n > 0:
                slots[pos] = int(n)
        if not slots:
            slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
        out = fantasy_pick.advice(draft, picks, ranks, board, user_id, slots)
        out["slots"] = slots
        self._send(200, json.dumps(out).encode(), ".json")

    def _sleeper(self, path: str):
        """Forward an allowlisted read to Sleeper's free public API. The big
        players file gets a day-long disk cache; everything else 5 minutes."""
        if not sleeper_path_ok(path):
            return self._send(404, b'{"error":"unsupported sleeper path"}', ".json")
        from engine.sources.fetch import fetch_text, DataUnavailable
        # players/nfl is ~5MB and changes daily; draft picks are polled DURING
        # a live draft, where five minutes of cache would show a board three
        # rounds stale. Everything else can sit for five minutes.
        ttl = (86400 if path == "players/nfl"
               else 10 if path.endswith("/picks") else 300)
        cache = "sleeper_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
        try:
            body = fetch_text(SLEEPER_BASE + path, cache, ttl=ttl)
        except DataUnavailable as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(), ".json")
        self._send(200, body.encode(), ".json")

    # --- API ---------------------------------------------------------------
    def _api(self, query: dict, sport: str = "nfl"):
        def qf(name, default):
            try:
                return float(query.get(name, [default])[0])
            except (TypeError, ValueError):
                return default

        # Live mode: serve the pre-built file if one exists. The frontend
        # re-applies the confidence/edge filters client-side, so the sliders
        # still work against this data.
        if getattr(self.server, "live_mode", False):
            live = LIVE_FILES.get(sport)
            if live and live.is_file():
                self._send(200, live.read_bytes(), ".json",
                           mtime=live.stat().st_mtime)
                return
            # No build yet → fall through to the sample pipeline below so the
            # page still loads (with a clear note in LAUNCH.md on how to build).

        # The site's slider sends min_edge in PERCENT (0, 0.5, 1, 2, …). The
        # old ">1 means percent" guess turned a 1% or 0.5% setting into a
        # 100%/50% edge floor that filtered every prop. No real edge floor
        # exceeds 20%, so anything above that is percent; below is a fraction.
        raw_edge = qf("min_edge", 2.0)
        config = RuleConfig(
            min_confidence=qf("min_confidence", 6.0),
            min_edge=raw_edge / 100.0 if raw_edge >= 0.2 else raw_edge,
            max_juice=int(qf("max_juice", -350)),
        )
        # NBA/WNBA/CFB have no sample pipeline — the built file is the only
        # source. (The frontend re-applies its filters client-side anyway.)
        if sport in ("nba", "wnba", "cfb"):
            live = LIVE_FILES[sport]
            if live.is_file():
                self._send(200, live.read_bytes(), ".json",
                           mtime=live.stat().st_mtime)
            else:
                # Full shared-schema shape even when nothing is built — a
                # stub missing keys crashed the frontend renderers once.
                self._send(200, json.dumps({
                    "date": "", "status": "not built", "sport": sport,
                    "games": [], "recommendations": [], "game_bets": [],
                    "long_shots": [], "longshot_watch": [],
                    "market_scan": {}, "counts": {"props_analyzed": 0,
                                                  "recommended": 0},
                }).encode(), ".json")
            return
        try:
            if sport == "mlb":
                result = run_mlb_slate(MLB_SLATE, config)
            else:
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
        # Browsers probe /favicon.ico on their own, before they have parsed
        # the <link rel="icon"> that points at our SVG. We only ship the one
        # icon, so hand it back here too — otherwise every single page load
        # logs a 404 that means nothing.
        if path == "/favicon.ico":
            path = "/favicon.svg"
        target = (WEB / path.lstrip("/")).resolve()
        # Prevent path traversal outside the web root. is_relative_to (not a
        # string prefix) so a sibling like web2/ could never slip through.
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            self._send(404, b"Not found", ".html")
            return
        self._send(200, target.read_bytes(), target.suffix,
                   mtime=target.stat().st_mtime)

    def _send(self, code: int, body: bytes, suffix: str, mtime: float | None = None):
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # When the payload came from a file on disk, say when that file was
        # last written. The site's freshness chip used to time its own
        # fetch, which is always a few seconds old — so a phone across town
        # read "Updated 4s ago" over a board the laptop stopped rebuilding
        # hours earlier. This is the age of the DATA, and it needs no build
        # script to cooperate: every payload is a file, and a build that
        # fails leaves the old one (and its old timestamp) in place.
        if mtime is not None:
            self.send_header("Last-Modified", formatdate(mtime, usegmt=True))
            self.send_header("Access-Control-Expose-Headers", "Last-Modified")
        self.end_headers()
        self.wfile.write(body)


def _lan_ip():
    """This machine's LAN address — the URL a phone on the same Wi-Fi can
    open. The UDP connect never sends a packet; it just makes the OS pick
    the outbound interface. None when there's no usable network."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def main() -> None:
    args = sys.argv[1:]
    live = "--live" in args
    ports = [a for a in args if not a.startswith("--")]
    port = int(ports[0]) if ports else 8000

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.live_mode = live  # read by Handler._api

    mode = "LIVE data" if live else "sample data"
    print(f"Qellys Book running ({mode}) → http://localhost:{port}")
    lan = _lan_ip()
    if lan:
        print(f"  On your phone (same Wi-Fi): http://{lan}:{port}")
    if live:
        for sport, path in LIVE_FILES.items():
            state = "ready" if path.is_file() else "not built yet — see LAUNCH.md"
            print(f"  {sport.upper()}: {path.relative_to(ROOT)} ({state})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
