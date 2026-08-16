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
#: `search` joins the list with real accounts, 2026-08-15 — Ethan asked
#: for search history stored alongside bets and fantasy. The merge rule
#: for it is the same last-writer-wins every non-bets section uses.
PROFILE_SECTIONS = ("mybets", "fantasy", "bankroll", "search")
#: The signed-in session cookie. HttpOnly so page scripts cannot read it
#: — an XSS bug should not also be a session theft — and SameSite=Lax so
#: another site cannot ride it.
SESSION_COOKIE = "qb_session"

#: Sent on every response. Cheap, and the kind of thing that is obvious in
#: hindsight after it matters — measured 2026-08-15, the server was
#: sending none of them.
#:
#: `connect-src 'self'` is a REAL restriction here rather than decoration:
#: the page makes no browser-side request to any external host — Sleeper,
#: ESPN, Yahoo and Paddle are all reached by the SERVER — so an injected
#: script has nowhere to send what it steals.
#:
#: `script-src` still needs `'unsafe-inline'`, and that is honest rather
#: than ideal: the page carries 33 inline `onclick=` handlers. Removing
#: them is what would let this become a real defence against injection;
#: until then the value here is blocking EXTERNAL script sources, which it
#: does. Written down so the weakness is a known debt and not a surprise.
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy",
     "default-src 'self'; "
     # Headshots and team art come from ESPN/MLB CDNs at render time.
     "img-src 'self' https: data:; "
     "script-src 'self' 'unsafe-inline'; "
     "style-src 'self' 'unsafe-inline'; "
     "font-src 'self'; "
     "connect-src 'self'; "
     # Rocket Radar embeds the live pool chart for the selected coin from
     # whichever of the two indexers has that pool. WITHOUT THIS LINE
     # `default-src 'self'` applies to frames and both are refused — the
     # chart panel that is the whole point of the page comes up empty,
     # silently, with the refusal only in the browser console. It was
     # broken from the moment the security headers shipped until a
     # headless sweep read the console and said so; nothing in 4,400
     # tests could see it, because the page renders perfectly and it is
     # the BROWSER that declines to load the frame.
     #
     # Named hosts, not a wildcard: these are the only things this site
     # frames, and `frame-src https:` would let any injected iframe
     # anywhere load — which is most of what framing protection is for.
     #
     # BOTH apex and www for each, because CSP re-checks every redirect
     # hop: if dexscreener.com answers with a 301 to www (or geckoterminal
     # the other way), the frame is refused at the second hop and the
     # chart is blank again for a reason that looks nothing like this
     # line. Whether they actually redirect could not be measured from
     # here — the dev container's egress policy blocks both hosts — so
     # this covers the case instead of guessing at it. Four named hosts
     # is still a closed list.
     "frame-src https://dexscreener.com https://www.dexscreener.com "
     "https://geckoterminal.com https://www.geckoterminal.com; "
     "frame-ancestors 'none'; "
     "base-uri 'self'; "
     "form-action 'self'"),
)

#: The legacy name+PIN store is Ethan's own, from before real accounts.
#: POSTing a name that does not exist CREATES it, with no credential — on
#: a LAN that was the feature, and on a public server it is free disk for
#: anyone who finds the path. Verified 2026-08-15: three profiles created
#: from curl with no auth. New accounts go through email and password now;
#: this store keeps working for whoever already has one.
#: Per-IP request ceilings, sliding one-minute window. IN THE APP rather
#: than the proxy on purpose: Caddy has no built-in rate limiting (it
#: needs a third-party plugin), and a protection that depends on someone
#: remembering to install a plugin is one that will be missing on the day
#: it is needed.
#:
#: The read limit is deliberately generous — the board polls every 30s and
#: the meme page every 15s, so a real user in two tabs is already dozens of
#: requests a minute, and a limit that trips on normal use gets raised to
#: infinity by the first person it annoys.
RATE_READ_PER_MIN = 300
#: Auth is different: nobody legitimately signs in twenty times a minute.
#: This sits ON TOP of the per-email throttle in `engine.accounts` — that
#: one stops guessing at one account, this one stops spraying across many.
RATE_AUTH_PER_MIN = 20
_RATE: dict = {}
_RATE_LOCK = threading.Lock()


def rate_ok(key: str, limit: int, now: float | None = None) -> bool:
    """Sliding-window counter. False when this caller is over the limit."""
    import time as _t
    now = _t.time() if now is None else now
    with _RATE_LOCK:
        hits = [t for t in _RATE.get(key, []) if now - t < 60.0]
        if len(hits) >= limit:
            _RATE[key] = hits
            return False
        hits.append(now)
        _RATE[key] = hits
        # Bounded: this is memory, and an attacker with a botnet would
        # otherwise be filling it one key at a time.
        if len(_RATE) > 8192:
            for k in [k for k, v in list(_RATE.items())
                      if not v or now - v[-1] > 120][:2048]:
                _RATE.pop(k, None)
        return True


_RATE_LIMITED = ('{"error":"Too many requests — slow down and try again '
                 'in a minute."}')

_PROFILE_LOCAL_ONLY = (
    "New profiles cannot be created from another machine. This is the old "
    "PIN-based store, kept working for existing local use — make an "
    "account with an email and password instead.")
#: Shown when a password would have to cross a network in the clear.
#: Names the fix rather than just refusing — "insecure connection" on its
#: own leaves someone with no idea what to do next.
_INSECURE_LOGIN = (
    "This page is being served over plain HTTP from another machine, so a "
    "password typed here would cross the network readable by anyone on it "
    "— and it is usually a password used somewhere else too. Sign in from "
    "the computer running the server, or put HTTPS in front of it: "
    "`tailscale serve --bg 8000` prints an https:// link that works from "
    "anywhere. (If this really is a network you trust, set "
    "QB_ALLOW_INSECURE_LOGIN=1 before starting the server.)")
MAX_PROFILE_BYTES = 1_000_000        # thousands of bets fit; junk bounces
#: Connecting or disconnecting Yahoo is the one action on this server that
#: changes what a third party may see, so it is restricted to the machine
#: running it. Reading stays LAN-wide like the rest of the site.
_YAHOO_LOCAL = ("Connect Yahoo from the computer running this server. "
                "Reading works from anywhere on your network, but granting "
                "or revoking access to a Yahoo account should not be "
                "possible from another device on the same wifi.")
MAX_TOMBSTONES = 500
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_-]{2,24}$")
_PROFILE_PIN = re.compile(r"^\d{4,12}$")
_PROFILE_LOCK = threading.Lock()


def _acct():
    """`engine.accounts`, imported on first use.

    Deferred because importing it builds the dummy scrypt verifier that
    equalizes login timing — 40ms of work that a launcher which never
    serves an account request should not pay at startup.
    """
    from engine import accounts as _a
    return _a


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

    def _rate_limited(self, limit: int, bucket: str = "read") -> bool:
        """True when this caller is over the ceiling.

        SEPARATE BUCKETS PER KIND, which the first cut got wrong: with one
        counter per IP, the strict auth limit saw every ordinary page poll
        too, so a couple of minutes of normal browsing would have locked
        the same person out of signing in. Measured — 19 of 25 signups got
        through instead of 20, and the missing one was a GET.

        The caller is `_client_ip`, so behind a proxy one busy user cannot
        spend everybody's budget by all of them looking like 127.0.0.1.
        """
        if rate_ok(f"{bucket}:{self._client_ip()}", limit):
            return False
        self._send(429, _RATE_LIMITED.encode(), ".json")
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and self._rate_limited(RATE_READ_PER_MIN):
            return
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
        if parsed.path in ("/api/leaguedesk", "/api/leaguedesk/"):
            return self._league_desk(parse_qs(parsed.query))
        if parsed.path.startswith("/api/yahoo/"):
            return self._yahoo(parsed.path[len("/api/yahoo/"):].strip("/"),
                               parse_qs(parsed.query))
        if parsed.path.startswith("/api/account/"):
            return self._account_get(
                parsed.path[len("/api/account/"):].strip("/"))
        if parsed.path.startswith("/api/billing/"):
            return self._billing_get(
                parsed.path[len("/api/billing/"):].strip("/"))
        if parsed.path.startswith("/api/sleeper/"):
            return self._sleeper(parsed.path[len("/api/sleeper/"):].strip("/"))
        if parsed.path.startswith("/api/profile/"):
            code, body = profile_get(parsed.path[len("/api/profile/"):].strip("/"),
                                     self.headers.get("X-Profile-Pin") or "")
            return self._send(code, json.dumps(body).encode(), ".json")
        return self._static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        # The Paddle webhook is EXEMPT: it is already authenticated by
        # signature, and a retry burst during an incident is exactly when
        # we least want to start dropping payment events on the floor.
        if not parsed.path.startswith("/api/billing/webhook"):
            auth = parsed.path.startswith("/api/account/")
            if self._rate_limited(
                    RATE_AUTH_PER_MIN if auth else RATE_READ_PER_MIN,
                    "auth" if auth else "read"):
                return
        if parsed.path.startswith("/api/yahoo/"):
            return self._yahoo_post(
                parsed.path[len("/api/yahoo/"):].strip("/"))
        if parsed.path.startswith("/api/billing/"):
            # RAW BYTES, and parsed nowhere before the signature is checked.
            # Paddle signs the body it sent; JSON that has been parsed and
            # re-serialized is different bytes — key order, spacing, unicode
            # escapes — so a re-serialized body fails to verify even when it
            # is perfectly honest.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_PROFILE_BYTES:
                self.close_connection = True
                return self._send(413, b'{"error":"body too large"}', ".json")
            raw = self.rfile.read(length) if length > 0 else b""
            return self._billing_post(
                parsed.path[len("/api/billing/"):].strip("/"), raw)
        if parsed.path.startswith("/api/account/"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_PROFILE_BYTES:
                self.close_connection = True     # body goes unread
                return self._send(413, b'{"error":"body too large"}', ".json")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                assert isinstance(body, dict)
            except Exception:                                # noqa: BLE001
                return self._send(400, b'{"error":"body must be a JSON object"}',
                                  ".json")
            return self._account_post(
                parsed.path[len("/api/account/"):].strip("/"), body)
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
        # CREATING one is local-only; syncing an existing one is not, so a
        # phone that already has a profile keeps working exactly as before.
        _name = parsed.path[len("/api/profile/"):].strip("/")
        if (profile_name_ok(_name) and _load_profile(_name) is None
                and not (self._local_only() or self._via_tailnet())):
            return self._send(403, json.dumps({"error": _PROFILE_LOCAL_ONLY}
                                              ).encode(), ".json")
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

    def _league_desk(self, query: dict):
        """Your optimal lineup and the trades worth proposing, in one read.

        Both answers need the same three things — the league's SCORING,
        its ROSTER SLOTS, and every roster in it — so they are fetched
        once and answered together rather than twice. The scoring and the
        slots come from the league itself: a half-PPR TE-premium
        superflex league does not have the same best lineup as the
        default, and using a default here would quietly answer a
        different league's question.
        """
        league_id = (query.get("league") or [""])[0].strip()
        user_id = (query.get("user") or [""])[0].strip()
        platform = (query.get("platform") or ["sleeper"])[0].strip().lower()
        if platform not in ("sleeper", "espn", "yahoo"):
            return self._send(400, b'{"error":"unknown platform"}', ".json")
        # THE ID CHECK IS PER PLATFORM. `\d{1,25}` is right for Sleeper
        # and ESPN and rejects every Yahoo league key ever issued — they
        # look like `461.l.1234567`, and a shared regex would have made
        # the Yahoo path unreachable while looking like a bad league id.
        if platform == "yahoo":
            if not re.fullmatch(r"[0-9]{1,6}\.l\.[0-9]{1,12}", league_id):
                return self._send(
                    400, b'{"error":"bad yahoo league key"}', ".json")
            return self._league_desk_yahoo(league_id, query)
        if not re.fullmatch(r"\d{1,25}", league_id):
            return self._send(400, b'{"error":"bad league id"}', ".json")
        from engine import fantasy_lineup, fantasy_ranks, fantasy_trade
        from engine.db import connect
        from engine.sources.fetch import fetch_text, DataUnavailable

        if platform == "espn":
            return self._league_desk_espn(league_id, user_id, query)

        def grab(path, ttl):
            if not sleeper_path_ok(path):
                raise DataUnavailable(f"path not allowlisted: {path}")
            cache = "sleeper_" + re.sub(r"[^A-Za-z0-9]+", "_", path) + ".json"
            return json.loads(fetch_text(SLEEPER_BASE + path, cache, ttl=ttl))

        try:
            league = grab(f"league/{league_id}", ttl=600)
            rosters = grab(f"league/{league_id}/rosters", ttl=300)
            users = grab(f"league/{league_id}/users", ttl=600)
            players = grab("players/nfl", ttl=86400)
        except (DataUnavailable, ValueError) as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(),
                              ".json")

        def rows_for(roster):
            out = []
            for pid in (roster or {}).get("players") or []:
                p = (players or {}).get(str(pid)) or {}
                name = " ".join(x for x in (p.get("first_name"),
                                            p.get("last_name")) if x)
                pos = (p.get("position") or "").upper()
                if name and pos:
                    out.append({"player": name, "position": pos})
            return out

        owner = {}
        for u in users or []:
            owner[str(u.get("user_id"))] = (u.get("display_name")
                                            or u.get("username") or "?")
        mine, rivals = [], {}
        for r in rosters or []:
            who = str(r.get("owner_id") or "")
            rows = rows_for(r)
            if who == str(user_id):
                mine = rows
            elif rows:
                rivals[owner.get(who, f"Team {r.get('roster_id')}")] = rows

        conn = connect()
        try:
            season = max((int(s[0]) for s in conn.execute(
                "SELECT DISTINCT season FROM player_game_logs WHERE sport='nfl'"
            ).fetchall()), default=0)
            means = fantasy_lineup.per_game(conn, season) if season else {}
        finally:
            conn.close()

        scoring = league.get("scoring_settings") or {}
        slots = fantasy_lineup.starting_slots(league.get("roster_positions"))
        out = {
            "league": league.get("name"), "season": season,
            "slots": slots, "has_me": bool(mine),
            "lineup": fantasy_lineup.lineup(mine, slots, scoring, means)
                      if mine else None,
        }
        trades = (fantasy_trade.generate(mine, rivals, slots, scoring, means)
                  if mine and rivals else [])
        out["trades"] = trades[:12]
        out["trade_summary"] = fantasy_trade.summary(trades)
        self._send(200, json.dumps(out).encode(), ".json")

    def _league_desk_espn(self, league_id: str, member_id: str, query: dict):
        """The same desk, reading an ESPN league instead of a Sleeper one.

        Split out rather than branched inline so the two platforms cannot
        drift into each other's assumptions — the ANSWER is shared
        (`fantasy_lineup` and `fantasy_trade` never learn where the league
        came from), the READING is not.
        """
        from engine import fantasy_lineup, fantasy_trade
        from engine.db import connect
        from engine.sources import espnfantasy
        from engine.sources.fetch import DataUnavailable
        import datetime as _dt
        try:
            season = int((query.get("season") or [""])[0])
        except (TypeError, ValueError):
            season = _dt.date.today().year
        try:
            lg = espnfantasy.league(season, league_id)
        except DataUnavailable as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(),
                              ".json")

        conn = connect()
        try:
            stat_season = max((int(s[0]) for s in conn.execute(
                "SELECT DISTINCT season FROM player_game_logs WHERE sport='nfl'"
            ).fetchall()), default=0)
            means = (fantasy_lineup.per_game(conn, stat_season)
                     if stat_season else {})
        finally:
            conn.close()

        rosters = dict(lg.get("rosters") or {})
        mine_label = espnfantasy.owner_of(
            espnfantasy.fetch_league(season, league_id), member_id)
        mine = rosters.pop(mine_label, []) if mine_label else []
        slots = fantasy_lineup.starting_slots(lg.get("slots"))
        scoring = lg.get("scoring") or {}
        trades = (fantasy_trade.generate(mine, rosters, slots, scoring, means)
                  if mine and rosters else [])
        out = {
            "platform": "espn", "league": lg.get("name"),
            "season": stat_season, "slots": slots, "has_me": bool(mine),
            "lineup": (fantasy_lineup.lineup(mine, slots, scoring, means)
                       if mine else None),
            "trades": trades[:12],
            "trade_summary": fantasy_trade.summary(trades),
            # THE SCORING RULES WE COULD NOT READ. Reported to the page,
            # not swallowed: a rule silently ignored is a lineup silently
            # wrong, and ESPN describes scoring as numeric ids this
            # container has never been able to confirm against a live
            # response.
            "unmapped_scoring": lg.get("unmapped") or [],
        }
        self._send(200, json.dumps(out).encode(), ".json")

    # --- accounts: email and password, ours ---------------------------------
    #
    # Ethan, 2026-08-15: "make a feature where you can make an account on
    # our website with email and password so we can store peoples bets and
    # fantasy leauges and search history".
    #
    # The older name+PIN profile store still answers on /api/profile/ so
    # nobody's existing data disappears; this is the path that replaces it.
    # The MERGE is shared — `merge_sections` and the bet-signature rules
    # below are the same code both stores use, because two implementations
    # of "never lose a logged bet to a device race" is one too many.
    def _cookie(self, name: str) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def _client_ip(self) -> str:
        """Who is actually calling, once there is a proxy in front.

        BEHIND CADDY, `self.client_address` IS CADDY. Every request would
        arrive from 127.0.0.1, `_local_only()` would be true for the whole
        internet, and both guards built on it — the cleartext-password
        refusal and local-only profile creation — would be open doors that
        still looked shut. Found while writing the deploy config, before
        any of it shipped, which is the only reason it is a note rather
        than an incident.

        THE LAST ENTRY, NOT THE FIRST. `X-Forwarded-For` is a list a
        client can start and each hop appends to, so the first entry is
        whatever the caller felt like claiming. The last is the one OUR
        proxy wrote, describing the peer it actually saw.

        And it is trusted ONLY when the connection came from loopback —
        i.e. from the proxy on this machine. A direct caller can set the
        header to anything, and believing it would let anyone claim to be
        127.0.0.1.
        """
        peer = (self.client_address or ("",))[0]
        if peer not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return peer
        raw = self.headers.get("X-Forwarded-For") or ""
        hops = [p.strip() for p in raw.split(",") if p.strip()]
        return hops[-1] if hops else peer

    def _is_https(self) -> bool:
        """Whether the browser's leg of this request was encrypted.

        The server itself speaks plain HTTP; a Tailscale serve or any
        reverse proxy in front terminates TLS and says so in a header.
        This decides the cookie's `Secure` flag — setting it
        unconditionally would make sign-in silently impossible over the
        LAN address, and never setting it would let the cookie ride a
        plaintext request when there IS a TLS front.
        """
        fwd = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
        return fwd.lower() == "https"

    def _session_cookie(self, token: str, clear: bool = False) -> list:
        bits = [f"{SESSION_COOKIE}={'' if clear else token}", "Path=/",
                "HttpOnly", "SameSite=Lax",
                f"Max-Age={0 if clear else _acct().SESSION_TTL}"]
        if self._is_https():
            bits.append("Secure")
        return [("Set-Cookie", "; ".join(bits))]

    def _account(self, conn):
        """The signed-in account for this request, or None."""
        return _acct().session_user(conn, self._cookie(SESSION_COOKIE))

    def _account_get(self, path: str):
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if path == "me":
                # `insecure` lets the page say so BEFORE anybody types a
                # password, rather than only refusing after they have.
                out = {"signed_in": bool(who),
                       "insecure": self._transport_is_cleartext(),
                       "allowed": self._password_transport_ok()}
                if who:
                    out["email"] = who["email"]
                return self._send(200, json.dumps(out).encode(), ".json")
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "data":
                return self._send(200, json.dumps(
                    {"email": who["email"],
                     "sections": A.get_sections(conn, who["id"])}).encode(),
                    ".json")
            if path == "export":
                # Everything we hold, on request. If we are going to keep
                # people's data we have to be able to hand it back.
                return self._send(200, json.dumps(
                    A.export_user(conn, who["id"]), indent=1).encode(), ".json")
            return self._send(404, b'{"error":"unknown account endpoint"}',
                              ".json")
        finally:
            conn.close()

    #: Endpoints that carry a PASSWORD in the body. These are the ones
    #: refused over a cleartext connection to another machine — see
    #: `_password_transport_ok`.
    PASSWORD_PATHS = ("signup", "login", "password", "delete")

    def _via_tailnet(self) -> bool:
        """Whether this request arrived through the Tailscale tunnel.

        `http://` OVER A TAILNET IS NOT CLEARTEXT. Tailscale is WireGuard:
        the packets are encrypted device-to-device before they touch any
        network, so the scheme in the address bar describes the last inch
        rather than the wire. Refusing a password here would be refusing
        a connection that is genuinely private — and worse in practice
        than allowing it, because the way round it is
        QB_ALLOW_INSECURE_LOGIN=1, which disables the check EVERYWHERE
        including the coffee shop.

        BOTH ENDS ARE CHECKED, and that is the point. `100.64.0.0/10` is
        RFC 6598 shared space: Tailscale uses it, but so do some ISPs for
        carrier-grade NAT, so a client address in that range proves
        nothing on its own. Requiring that OUR OWN socket for this
        connection is also a tailnet address means the packet arrived on
        the tailnet interface — which a CGNAT'd public path does not do,
        because that lands on the LAN or WAN address instead.

        The limit, stated rather than hidden: a network that put both
        machines inside 100.64.0.0/10 for real would read as a tailnet
        here. That is a narrow shape — home LANs are 192.168/10.x and
        CGNAT sits upstream of the router, not on it — and a much smaller
        hole than the blanket override it replaces.
        """
        import ipaddress
        nets = (ipaddress.ip_network("100.64.0.0/10"),      # Tailscale IPv4
                ipaddress.ip_network("fd7a:115c:a1e0::/48"))  # …and IPv6
        try:
            peer = ipaddress.ip_address(self._client_ip())
            mine = ipaddress.ip_address(self.connection.getsockname()[0])
        except (ValueError, IndexError, OSError, AttributeError):
            return False
        inside = lambda a: any(a in n for n in nets)        # noqa: E731
        return inside(peer) and inside(mine)

    def _transport_is_cleartext(self) -> bool:
        """Whether this connection would carry a password readable.

        A FACT ABOUT THE WIRE, kept separate from whether we allow it.
        The override removes the refusal; it does not make the connection
        private, and reporting `insecure: false` because somebody set an
        environment variable would be the page telling a comfortable lie
        about the network. A tailnet is a different case entirely: there
        the encryption is real, it is just not TLS.
        """
        return not (self._is_https() or self._local_only()
                    or self._via_tailnet())

    def _password_transport_ok(self) -> bool:
        """Whether a password may cross this connection at all.

        THE HASHING ON OUR END DOES NOTHING FOR THIS. scrypt protects the
        password at rest; a password typed into a plain-HTTP page has
        already crossed the network in the clear before it ever reaches
        the hash, and anyone on that Wi-Fi has it — for this site and for
        wherever else they reused it.

        Three cases, and only the middle one is a refusal:

          * LOOPBACK — the browser is on this machine. Nothing crosses a
            network, so http://localhost is genuinely fine and blocking it
            would break the normal way this app is used.
          * ANOTHER MACHINE, no TLS — refused, with the fix named.
          * TLS in front (X-Forwarded-Proto: https) — fine.

        `QB_ALLOW_INSECURE_LOGIN=1` overrides it for someone who has read
        this and decided their network is theirs. Deliberately an
        environment variable rather than a settings toggle: it should take
        a decision, not a mis-tap.
        """
        if not self._transport_is_cleartext():
            return True
        import os as _os
        return _os.environ.get("QB_ALLOW_INSECURE_LOGIN", "") == "1"

    def _account_post(self, path: str, body: dict):
        A = _acct()
        if path not in ("signup", "login", "logout", "data", "password",
                        "delete"):
            return self._send(404, b'{"error":"unknown account endpoint"}',
                              ".json")
        if path in self.PASSWORD_PATHS and not self._password_transport_ok():
            return self._send(400, json.dumps({"error": _INSECURE_LOGIN}
                                              ).encode(), ".json")
        conn = A.connect()
        try:
            if path in ("signup", "login"):
                if path == "signup":
                    code, out = A.create_user(
                        conn, body.get("email"), body.get("password"),
                        confirmed=bool(body.get("confirmed")))
                else:
                    code, out = A.authenticate(
                        conn, body.get("email"), body.get("password"))
                if code != 200:
                    return self._send(code, json.dumps(out).encode(), ".json")
                token = A.start_session(conn, out["id"])
                # The token goes in the cookie and NOWHERE in the body: a
                # page script that can read it can also exfiltrate it, and
                # HttpOnly is only a promise if we keep it.
                return self._send(200, json.dumps(
                    {"signed_in": True, "email": out["email"]}).encode(),
                    ".json", headers=self._session_cookie(token))
            token = self._cookie(SESSION_COOKIE)
            if path == "logout":
                A.end_session(conn, token)
                return self._send(200, b'{"signed_in":false}', ".json",
                                  headers=self._session_cookie("", clear=True))
            who = A.session_user(conn, token)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "data":
                sections = body.get("sections")
                if not isinstance(sections, dict):
                    return self._send(400, b'{"error":"sections must be an object"}',
                                      ".json")
                stored = A.get_sections(conn, who["id"])
                merged = merge_sections(stored, sections)
                A.save_sections(conn, who["id"], merged)
                A.touch_session(conn, token)
                return self._send(200, json.dumps(
                    {"email": who["email"], "sections": merged}).encode(),
                    ".json")
            if path == "password":
                code, out = A.change_password(conn, who["id"],
                                              body.get("old"), body.get("new"))
                if code != 200:
                    return self._send(code, json.dumps(out).encode(), ".json")
                # change_password drops every session, this one included.
                return self._send(200, json.dumps(out).encode(), ".json",
                                  headers=self._session_cookie("", clear=True))
            if path == "delete":
                # Typing the password again, because this is not undoable
                # and a mis-tap should not be able to do it.
                code, _ = A.authenticate(conn, who["email"],
                                         body.get("password"))
                if code != 200:
                    # Shown to the person verbatim now that the client
                    # stopped inventing its own text for every failure.
                    return self._send(403, b'{"error":"Wrong password."}',
                                      ".json")
                # A live subscription is the one thing deletion cannot
                # clean up: Paddle is the system of record for the money,
                # and dropping our row leaves a card being charged every
                # month with nothing on this side to match it to. So the
                # account has to be unsubscribed first — and the way out
                # is one button away on the same card.
                stuck = self._live_subscription(conn, who["id"])
                if stuck:
                    return self._send(409, json.dumps({"error": stuck}).encode(),
                                      ".json")
                A.delete_user(conn, who["id"])
                return self._send(200, b'{"deleted":true}', ".json",
                                  headers=self._session_cookie("", clear=True))
        finally:
            conn.close()

    def _live_subscription(self, conn, user_id: int) -> str:
        """Message to refuse deletion with, or "" to let it through.

        Deletion is the one account action that can cost somebody money
        after they have stopped using the site. `delete_user` clears our
        `subscriptions` row, but Paddle never hears about it: the card
        keeps being charged on schedule, and the row that said whose card
        it was is gone. The person then has a charge they cannot place and
        we have a payment we cannot refund to an account.

        So a paying account is asked to cancel first, which is one button
        away on the same card and happens on Paddle's own portal. Nobody
        is trapped: cancelling flips the status through the webhook, and
        `past_due` and `trialing` are refused too because both still have
        a live subscription behind them.

        Returns a string rather than a bool because the whole point is
        telling the person *why* — the old client turned every non-200
        from this endpoint into "Wrong password.", which was the least
        useful sentence available.
        """
        try:
            from engine import billing as BI
            have = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "subscriptions" not in have:
                return ""              # billing never ran on this install
            st = BI.status_for(conn, user_id)
        except Exception:                                    # noqa: BLE001
            # A billing lookup that breaks must not block someone from
            # deleting their account. Erring the other way would mean a
            # bug in code that is switched off holds their data hostage.
            return ""
        if not st.get("entitled"):
            return ""
        return ("This account still has a subscription. Cancel it first "
                "under Manage billing — otherwise your card keeps being "
                "charged and we lose the record of whose card it is. "
                "Once it is cancelled, delete works normally.")

    # --- billing: Paddle holds the card, we hold a status ------------------
    def _billing_get(self, path: str):
        from engine import billing as BI
        from engine import paddle as PAY
        A = _acct()
        if path != "status":
            return self._send(404, b'{"error":"unknown billing endpoint"}',
                              ".json")
        conn = A.connect()
        try:
            BI.init(conn)
            who = self._account(conn)
            out = {"configured": PAY.configured(), "signed_in": bool(who)}
            if PAY.configured():
                # Paddle's sandbox is a SEPARATE account with separate
                # keys, so "are we live" is a question about which base
                # URL the requests go to — not, as with Stripe, a prefix
                # on the key.
                out["live"] = not PAY.sandbox()
            if who:
                out.update(BI.status_for(conn, who["id"],
                                         describe_with=PAY.describe))
            return self._send(200, json.dumps(out).encode(), ".json")
        finally:
            conn.close()

    def _billing_post(self, path: str, raw: bytes):
        from engine import billing as BI
        from engine import paddle as PAY
        A = _acct()
        if path == "webhook":
            return self._billing_webhook(raw)
        if path not in ("checkout", "portal"):
            return self._send(404, b'{"error":"unknown billing endpoint"}',
                              ".json")
        conn = A.connect()
        try:
            BI.init(conn)
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            base = self._site_base()
            try:
                if path == "checkout":
                    url = PAY.start_checkout(
                        who["id"], who["email"], f"{base}/?paid=1#mybets")
                else:
                    cust = BI.status_for(conn, who["id"]).get("customer_id")
                    if not cust:
                        return self._send(400, json.dumps(
                            {"error": "No subscription to manage yet."}
                        ).encode(), ".json")
                    url = PAY.open_portal(cust, f"{base}/#mybets")
            except BI.BillingUnavailable as exc:
                # paddle re-exports this class deliberately, so one except
                # covers both halves and the caller never has to know
                # which processor is behind the endpoint.
                return self._send(502, json.dumps({"error": str(exc)}).encode(),
                                  ".json")
            return self._send(200, json.dumps({"url": url}).encode(), ".json")
        finally:
            conn.close()

    def _site_base(self) -> str:
        """The address this browser reached us on, for Paddle's return trip.

        Read from the request rather than configured, because this site
        answers on localhost, a LAN address and a tailscale name, and a
        hardcoded one would send two of those three somewhere they cannot
        get back from.
        """
        host = (self.headers.get("X-Forwarded-Host")
                or self.headers.get("Host") or "127.0.0.1:8000")
        scheme = "https" if self._is_https() else "http"
        return f"{scheme}://{host}"

    def _billing_webhook(self, raw: bytes):
        """Paddle telling us somebody paid. THE ONLY THING THAT GRANTS
        ACCESS, and a public URL, so it lives or dies on the signature.

        Refuses outright when no notification secret is configured. An
        unsigned-but-accepted webhook endpoint is a free-subscription
        button for anybody who finds the path, and "we will add the
        secret later" is how it ships that way.

        THE RAW BODY, NEVER A RE-SERIALISED ONE. The signature is over
        bytes; parsing and re-encoding JSON changes key order and spacing
        and makes an honest payload fail to verify.
        """
        from engine import billing as BI
        from engine import paddle as PAY
        A = _acct()
        try:
            _api_key, whsec, _price = PAY.keys()
        except BI.BillingUnavailable:
            return self._send(503, b'{"error":"billing not configured"}',
                              ".json")
        if not whsec:
            return self._send(503, json.dumps(
                {"error": f"No {PAY.ENV_WEBHOOK_SECRET} set, so this endpoint "
                          "cannot tell a real Paddle event from a forged "
                          "one. Refusing rather than trusting it."}).encode(),
                ".json")
        sig = self.headers.get("Paddle-Signature") or ""
        if not PAY.verify_signature(raw, sig, whsec):
            return self._send(400, b'{"error":"bad signature"}', ".json")
        try:
            payload = json.loads(raw or b"{}")
            assert isinstance(payload, dict)
        except Exception:                                    # noqa: BLE001
            return self._send(400, b'{"error":"not JSON"}', ".json")
        conn = A.connect()
        try:
            BI.init(conn)
            # A retry is not a second grant.
            #
            # `event_id`, NOT `id`. Paddle names it differently from
            # Stripe, and the failure is silent in the worst direction:
            # already_handled() treats an empty id as "not seen before"
            # and returns False every time, so the replay guard would
            # have been switched off while still looking present. A
            # retried subscription.created is then a second grant.
            if BI.already_handled(conn, payload.get("event_id")
                                  or payload.get("id")):
                return self._send(200, b'{"received":true,"duplicate":true}',
                                  ".json")
            event = PAY.read_event(payload)
            applied = BI.apply_event(conn, event) if event else False
            # 200 EVEN WHEN WE DID NOTHING. Paddle retries anything that is
            # not 2xx, so an event we do not act on must still be
            # acknowledged or it comes back forever.
            return self._send(200, json.dumps(
                {"received": True, "applied": bool(applied)}).encode(), ".json")
        finally:
            conn.close()

    def _league_desk_yahoo(self, league_key: str, query: dict):
        """The same desk again, reading a Yahoo league through OAuth2.

        The only platform here that needs anything of yours, and the only
        one whose access can be handed back: you approve it on Yahoo's own
        screen, this app never sees a password, and revoking it from a
        Yahoo account page kills the token dead. That is why Yahoo is
        built and a private ESPN league is not.

        WHO IS "ME" IS NOT TYPED. Yahoo flags your own team in the
        payload, so there is no id to look up and no way to select
        somebody else's roster by accident.
        """
        from engine import fantasy_lineup, fantasy_trade
        from engine.db import connect
        from engine.sources import yahoofantasy
        from engine.sources.fetch import DataUnavailable
        try:
            lg = yahoofantasy.league(league_key)
        except DataUnavailable as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(),
                              ".json")

        conn = connect()
        try:
            stat_season = max((int(s[0]) for s in conn.execute(
                "SELECT DISTINCT season FROM player_game_logs WHERE sport='nfl'"
            ).fetchall()), default=0)
            means = (fantasy_lineup.per_game(conn, stat_season)
                     if stat_season else {})
        finally:
            conn.close()

        rosters = dict(lg.get("rosters") or {})
        mine = rosters.pop(lg.get("mine"), []) if lg.get("mine") else []
        slots = fantasy_lineup.starting_slots(lg.get("slots"))
        scoring = lg.get("scoring") or {}
        trades = (fantasy_trade.generate(mine, rosters, slots, scoring, means)
                  if mine and rosters else [])
        out = {
            "platform": "yahoo", "league": lg.get("name"),
            "season": stat_season, "slots": slots, "has_me": bool(mine),
            "my_team": lg.get("mine"),
            "lineup": (fantasy_lineup.lineup(mine, slots, scoring, means)
                       if mine else None),
            "trades": trades[:12],
            "trade_summary": fantasy_trade.summary(trades),
            # THE RULES WE DID NOT APPLY, split in two because they mean
            # different things: `unmapped_scoring` is a gap in our map and
            # a bug to fix, `not_modelled_scoring` is the kicker and
            # defense scoring this app has never projected. Reporting them
            # as one number would hide the first inside the second.
            "unmapped_scoring": lg.get("unmapped") or [],
            "not_modelled_scoring": lg.get("not_modelled") or [],
        }
        self._send(200, json.dumps(out).encode(), ".json")

    # --- Yahoo's connection, which is the only credential this app holds ----
    def _local_only(self) -> bool:
        """True when the request came from this machine.

        READING the site is LAN-wide, as everything here always has been.
        GRANTING or REVOKING Yahoo access is not: it is the one action on
        this server that changes what a third party may see, and a phone
        on the same coffee-shop wifi should not be able to take it.
        """
        # Through `_client_ip`, NOT the raw peer: behind a reverse proxy
        # the peer is always the proxy, and reading it directly would make
        # this true for the entire internet.
        host = self._client_ip()
        return host in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost")

    def _yahoo(self, path: str, query: dict):
        from engine.sources import yahoofantasy as yf
        from engine.sources.fetch import DataUnavailable
        if path == "status":
            # Deliberately says whether a token EXISTS, never what it is.
            try:
                cid, _ = yf.credentials()
                app = True
            except DataUnavailable:
                app = False
            return self._send(200, json.dumps(
                {"connected": yf.connected(), "app_registered": app}).encode(),
                ".json")
        if path == "start":
            if not self._local_only():
                return self._send(403, json.dumps({"error": _YAHOO_LOCAL}
                                                  ).encode(), ".json")
            try:
                cid, _ = yf.credentials()
            except DataUnavailable as exc:
                return self._send(400, json.dumps({"error": str(exc)}).encode(),
                                  ".json")
            return self._send(200, json.dumps(
                {"url": yf.authorize_url(cid)}).encode(), ".json")
        if path == "leagues":
            try:
                return self._send(200, json.dumps(
                    {"leagues": yf.my_leagues()}).encode(), ".json")
            except DataUnavailable as exc:
                return self._send(502, json.dumps({"error": str(exc)}).encode(),
                                  ".json")
        return self._send(404, b'{"error":"unknown yahoo endpoint"}', ".json")

    def _yahoo_post(self, path: str):
        from engine.sources import yahoofantasy as yf
        from engine.sources.fetch import DataUnavailable
        if path not in ("connect", "disconnect"):
            return self._send(404, b'{"error":"unknown yahoo endpoint"}',
                              ".json")
        if not self._local_only():
            return self._send(403, json.dumps({"error": _YAHOO_LOCAL}).encode(),
                              ".json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = {}
        if 0 < length <= 4096:
            try:
                body = json.loads(self.rfile.read(length)) or {}
            except Exception:                                # noqa: BLE001
                body = {}
        elif length > 4096:
            # An approval code is a few dozen characters. Anything larger
            # is not one — and the body goes UNREAD, so the connection has
            # to close rather than let keep-alive parse those bytes as the
            # next request.
            self.close_connection = True
            return self._send(413, b'{"error":"body too large"}', ".json")
        if path == "disconnect":
            try:
                Path(yf.TOKEN_PATH).unlink(missing_ok=True)
            except OSError as exc:
                return self._send(500, json.dumps({"error": str(exc)}).encode(),
                                  ".json")
            return self._send(200, b'{"connected":false}', ".json")
        code = str((body or {}).get("code") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._~-]{4,128}", code):
            return self._send(400, json.dumps(
                {"error": "That does not look like a Yahoo approval code. "
                          "It is the short string Yahoo shows after you "
                          "approve the app."}).encode(), ".json")
        try:
            out = yf.exchange_code(code)
        except DataUnavailable as exc:
            return self._send(502, json.dumps({"error": str(exc)}).encode(),
                              ".json")
        # `out` carries no token — only that it worked. See exchange_code.
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

    #: What we tell the world we are. The default is
    #: `BaseHTTP/0.6 Python/3.11.15`, which hands an attacker the exact
    #: stack and patch level to look up CVEs against — free reconnaissance
    #: for nothing in return. Caddy strips it too, but that only helps
    #: when Caddy is in front, and the app should not be volunteering it
    #: in the first place.
    server_version = "Qellys"
    sys_version = ""

    def _send(self, code: int, body: bytes, suffix: str, mtime: float | None = None,
              headers: list | None = None):
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        # HSTS only over HTTPS. On a plain-HTTP LAN address it does
        # nothing at best; announced from a name that later needs to serve
        # HTTP it is a self-inflicted outage browsers remember for months.
        if self._is_https():
            self.send_header("Strict-Transport-Security",
                             "max-age=31536000; includeSubDomains")
        for name, value in (headers or []):
            self.send_header(name, value)
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
    # `--bind 127.0.0.1` for a public deployment: the app sits behind a
    # reverse proxy that terminates TLS, and binding all interfaces would
    # leave the plain-HTTP port reachable from outside as well — the proxy
    # in front then protects nothing, because anyone can go around it.
    bind = "0.0.0.0"
    if "--bind" in args:
        i = args.index("--bind")
        if i + 1 < len(args):
            bind = args[i + 1]
            args = args[:i] + args[i + 2:]
    ports = [a for a in args if not a.startswith("--")]
    port = int(ports[0]) if ports else 8000

    server = ThreadingHTTPServer((bind, port), Handler)
    server.live_mode = live  # read by Handler._api

    mode = "LIVE data" if live else "sample data"
    print(f"Qellys Book running ({mode}) → http://localhost:{port}")
    if bind != "0.0.0.0":
        print(f"  Bound to {bind} only — reachable through a proxy, not directly.")
    lan = _lan_ip() if bind == "0.0.0.0" else None
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
