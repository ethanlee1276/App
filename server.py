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

import csv
import hashlib
import io
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
from engine import routes

ROOT = Path(__file__).parent
#: The served tree. QB_WEB_DIR overrides it, for the same reason
#: QB_ACCOUNTS_DB overrides the database: a test that has to prove the
#: paywall seals the public path must not do that to the working copy,
#: and a test that redacts your real boards as a side effect is worse
#: than no test. Also useful for a staging tree on the same box.
WEB = Path(os.environ.get("QB_WEB_DIR", "").strip() or (ROOT / "web"))
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
    # The week's board: one row per roster, sharing a matchup_id. This is
    # the only way to know WHO you are playing, which is the whole of
    # IDEAS #7 — the desk answered every question against the field
    # before it, and you do not play the field.
    r"|league/\d{1,25}/matchups/\d{1,2}"
    # Which week it is, from the league's own scorekeeper rather than
    # from a calendar this server would have to guess with.
    r"|state/nfl"
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
#:
#: `settings` joins it 2026-08-25 (odds format, stake display, time zone,
#: favourite teams, which leagues show in the nav) under the same rule.
#: MUST STAY IN STEP WITH engine/accounts.SECTIONS: this tuple is the
#: merge contract and that one is what the database will store, so a
#: section named in only one of them syncs in one direction and looks
#: like a device that will not remember you.
PROFILE_SECTIONS = ("mybets", "fantasy", "bankroll", "search", "settings")
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

#: The window every counter is measured over.
_RATE_WINDOW = 60.0
#: How often the sweep may run. Once per this many seconds, NOT once per
#: request — see `_rate_sweep` for what that cost me.
_RATE_SWEEP_EVERY = 30.0
#: Hard ceiling on tracked callers, so memory cannot follow traffic
#: upward without limit on a 1 GB box.
_RATE_MAX_KEYS = 50_000
_RATE_SWEPT_AT = 0.0


def _rate_sweep(now: float) -> None:
    """Drop expired counters. CALLER HOLDS `_RATE_LOCK`.

    THIS USED TO RUN ON EVERY REQUEST once the table passed 8192 keys,
    and it built `list(_RATE.items())` — a full copy of the table — to do
    it. Under the global lock. Measured 2026-08-22:

           1,000 keys   0.002 ms per request
           8,000 keys   0.068 ms
          16,000 keys   3.587 ms
          64,000 keys  21.982 ms

    Every API request takes this lock, so past ~8k distinct callers the
    whole site serialises behind one O(n) scan: at 64k tracked addresses
    that is ~45 requests per second TOTAL, on any hardware. And it is a
    spiral, not a plateau — the slower it gets the more requests are in
    flight, the more addresses arrive, the slower it gets.

    That is precisely the shape of the traffic this site was being made
    ready for: an Instagram post, tens of thousands of phones, most of
    them new addresses. It would not have crashed. It would have gone
    treacle-slow at exactly the moment it mattered and recovered by
    itself afterwards, which is the hardest kind of outage to explain.

    Now: at most once every `_RATE_SWEEP_EVERY` seconds, so the O(n) cost
    is amortised over thirty seconds of traffic rather than paid per
    request. Entries older than the window are dead weight by definition
    — nothing reads them — so the sweep can take all of them at once
    instead of 2048 at a time.
    """
    global _RATE_SWEPT_AT
    _RATE_SWEPT_AT = now
    for k in [k for k, v in _RATE.items()
              if not v or now - v[-1] >= _RATE_WINDOW]:
        _RATE.pop(k, None)
    if len(_RATE) <= _RATE_MAX_KEYS:
        return
    # Still over after dropping the dead: trim the oldest last-seen first,
    # since those are the closest to expiring anyway. Down to 90% of the
    # cap rather than exactly to it, so the next arrival does not trigger
    # another sweep immediately — which would put the per-request O(n)
    # straight back.
    keep = _RATE_MAX_KEYS * 9 // 10
    for k in sorted(_RATE, key=lambda k: _RATE[k][-1])[:len(_RATE) - keep]:
        _RATE.pop(k, None)


def rate_ok(key: str, limit: int, now: float | None = None) -> bool:
    """Sliding-window counter. False when this caller is over the limit."""
    import time as _t
    now = _t.time() if now is None else now
    with _RATE_LOCK:
        hits = [t for t in _RATE.get(key, []) if now - t < _RATE_WINDOW]
        over = len(hits) >= limit
        if not over:
            hits.append(now)
        _RATE[key] = hits
        if (now - _RATE_SWEPT_AT >= _RATE_SWEEP_EVERY
                or len(_RATE) > _RATE_MAX_KEYS):
            _rate_sweep(now)
        return not over


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


def _streak():
    """`engine.streak`, imported on first use — same posture as _acct()."""
    from engine import streak as _s
    return _s


#: The streak slate, cached on mtime. The file is rewritten by the
#: refresh sweep a few times an hour and read on every game request;
#: re-parsing it per request would be work the mtime already answers.
_STREAK_SLATE = {"mtime": 0.0, "doc": None}
_STREAK_LOCK = threading.Lock()


def streak_slate() -> dict:
    """The published slate — the FREE public copy, which for a free file
    IS the full copy (see engine/gate.py FREE_FILES)."""
    path = WEB / "data" / "streak.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    with _STREAK_LOCK:
        if _STREAK_SLATE["doc"] is None or mtime != _STREAK_SLATE["mtime"]:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
            if not isinstance(doc, dict):
                return {}
            _STREAK_SLATE["doc"] = doc
            _STREAK_SLATE["mtime"] = mtime
        return _STREAK_SLATE["doc"] or {}


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
    # The receipts download. `text/csv` rather than a generic stream so a
    # phone offers "open in Numbers" instead of asking what to do with it.
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


_TLS_HINTED = False


#: The service worker's cache name, stamped with what it actually caches.
#:
#: THE RULE THE FILE STATES ABOUT ITSELF WAS BROKEN TWICE. sw.js says
#: "bump VERSION on any shell change" and records that v1 shipped two
#: shell deploys late. It then sat on "qb-v3" through 2,149 more lines of
#: index.html, styles.css, app.js and visuals.js — including the
#: 2026-08-19 phone-drawer fix. The worker is network-first, so a healthy
#: phone still gets fresh files; but the cache is the fallback for EVERY
#: request the network loses, and one lost styles.css on cellular hands
#: back a pre-fix stylesheet inside an installed PWA with no address bar
#: to reveal it. A rule that depends on remembering is not a rule, so the
#: version is now derived rather than typed: the hash covers exactly the
#: files SHELL lists, read from sw.js so the two can never drift. Change
#: any of them and the name changes; `activate` deletes every other cache
#: on the next launch, and no pre-fix bundle can outlive a deploy.
_SW_CACHE: dict = {}
_SW_LOCK = threading.Lock()

#: The serialized subscriber boards, reused until the file on disk moves.
#:
#: WHY THIS EXISTS. `/api/board/<name>` is the hot path — every signed-in
#: page polls it every 30 seconds — and it was reading the board off
#: disk, parsing it to a dict, and re-serializing that dict back to bytes
#: ON EVERY REQUEST, only ever to send exactly what the file already
#: contained. Measured 2026-08-22 against a board shaped like the real
#: one (293 recommendations, 884 on the edge board, ~1.7 MB):
#:
#:     read + parse    29.4 ms
#:     re-serialize    32.3 ms
#:     per request     61.7 ms of pure CPU
#:
#: On one vCPU that is 21% of the core at a hundred subscribers and the
#: WHOLE core at five hundred, for work whose answer is identical every
#: time until the next rebuild sixty seconds later.
#:
#: Keyed by board name, so the table holds at most one entry per board
#: that exists — six or seven — rather than growing with traffic. The
#: stamp is the file's mtime and size, the same shape `sw_body` uses:
#: a rebuild changes it, and nothing else has to remember to invalidate.
#:
#: THIS CACHES BYTES, NOT PERMISSION. The entitlement check still runs on
#: every request, after this, exactly as before.
_BOARD_CACHE: dict = {}
_BOARD_LOCK = threading.Lock()


def file_bytes(path, key: str = ""):
    """``(body, mtime, etag)`` for a JSON file on disk, cached by stamp.

    The same cache serves the SUBSCRIBER copy in data/built and the
    redacted public copy in web/data, because both are polled on the same
    30-second clock by the same page and re-reading either per request
    costs the same.
    """
    key = key or str(path)
    try:
        st = path.stat()
    except OSError:
        return None, None, None
    stamp = (st.st_mtime_ns, st.st_size)
    with _BOARD_LOCK:
        hit = _BOARD_CACHE.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1], st.st_mtime, hit[2]
    try:
        body = path.read_bytes()
    except OSError:
        return None, None, None
    etag = '"%s"' % hashlib.sha256(body).hexdigest()[:20]
    with _BOARD_LOCK:
        _BOARD_CACHE[key] = (stamp, body, etag)
    return body, st.st_mtime, etag


def board_bytes(name: str):
    """``(body, mtime, etag)`` for a board, or ``(None, None, None)``."""
    from engine import gate
    path = gate.full_board_file(name)
    if path is None:
        return None, None, None
    try:
        st = path.stat()
    except OSError:
        return None, None, None
    stamp = (st.st_mtime_ns, st.st_size)
    with _BOARD_LOCK:
        hit = _BOARD_CACHE.get(name)
        if hit is not None and hit[0] == stamp:
            return hit[1], st.st_mtime, hit[2]
    # Read OUTSIDE the lock: a cold read of a megabyte-and-a-half must
    # not hold every other board's requests behind it, and two threads
    # racing to fill the same entry cost one duplicated parse rather than
    # a queue. The loser overwrites with an identical value.
    payload = gate.full_board(name)
    if payload is None:
        return None, None, None
    body = json.dumps(payload).encode()
    # Hashed once per rebuild, not once per request — it rides in the same
    # cache entry as the bytes it describes, so the two cannot disagree.
    etag = '"%s"' % hashlib.sha256(body).hexdigest()[:20]
    with _BOARD_LOCK:
        _BOARD_CACHE[name] = (stamp, body, etag)
    return body, st.st_mtime, etag


def _sw_shell(body: str, web: Path = WEB) -> list[Path]:
    """The files sw.js precaches, as paths on disk.

    Read out of sw.js rather than listed here, so the hash can only ever
    cover what the worker actually caches. A second copy of the list is a
    second thing to forget, which is the failure this replaces.
    """
    m = re.search(r"const SHELL = \[(.*?)\];", body, re.S)
    if not m:
        return []
    out = []
    for url in re.findall(r'"([^"]+)"', m.group(1)):
        rel = "index.html" if url == "/" else url.lstrip("/")
        f = (web / rel).resolve()
        if f.is_relative_to(web.resolve()) and f.is_file():
            out.append(f)
    return out


def sw_body(web: Path = WEB) -> bytes:
    """sw.js with VERSION replaced by a hash of the shell it caches.

    Recomputed only when a shell file's size or mtime moves, so the
    common case is a dict lookup rather than re-reading the bundle on
    every page load.
    """
    src = web / "sw.js"
    body = src.read_text()
    files = [src] + _sw_shell(body, web)
    stamp = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    with _SW_LOCK:
        hit = _SW_CACHE.get(stamp)
        if hit is not None:
            return hit
        h = hashlib.sha256()
        for f in files:
            h.update(f.read_bytes())
        out = re.sub(r'const VERSION = "[^"]*";',
                     'const VERSION = "qb-%s";' % h.hexdigest()[:12],
                     body, count=1).encode()
        _SW_CACHE.clear()                      # one entry: the current shell
        _SW_CACHE[stamp] = out
    return out


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
        if parsed.path in ("/api/players/search", "/api/players/search/"):
            return self._players_search(parse_qs(parsed.query))
        if parsed.path in ("/api/players/logs", "/api/players/logs/"):
            return self._players_logs(parse_qs(parsed.query))
        if parsed.path in ("/api/players/fantasy", "/api/players/fantasy/"):
            return self._players_fantasy(parse_qs(parsed.query))
        if parsed.path in ("/api/players/versus", "/api/players/versus/"):
            return self._players_versus(parse_qs(parsed.query))
        if parsed.path in ("/api/leaguedesk", "/api/leaguedesk/"):
            return self._league_desk(parse_qs(parsed.query))
        if parsed.path.startswith("/api/yahoo/"):
            return self._yahoo(parsed.path[len("/api/yahoo/"):].strip("/"),
                               parse_qs(parsed.query))
        if parsed.path.startswith("/api/account/"):
            return self._account_get(
                parsed.path[len("/api/account/"):].strip("/"))
        if parsed.path.startswith("/api/board/"):
            return self._api_board(parsed.path[len("/api/board/"):].strip("/"))
        if parsed.path.startswith("/api/streak/"):
            return self._streak_get(
                parsed.path[len("/api/streak/"):].strip("/"))
        if parsed.path.startswith("/api/tailfade/"):
            return self._tailfade_get(
                parsed.path[len("/api/tailfade/"):].strip("/"))
        if parsed.path.startswith("/api/social/"):
            return self._social_get(
                parsed.path[len("/api/social/"):].strip("/"))
        if parsed.path.startswith("/api/alerts/"):
            return self._alerts_get(
                parsed.path[len("/api/alerts/"):].strip("/"))
        if parsed.path.startswith("/api/billing/"):
            return self._billing_get(
                parsed.path[len("/api/billing/"):].strip("/"))
        if parsed.path.startswith("/api/sleeper/"):
            return self._sleeper(parsed.path[len("/api/sleeper/"):].strip("/"))
        if parsed.path in ("/api/record/receipts.csv",):
            return self._receipts_csv()
        if parsed.path in ("/unsubscribe", "/unsubscribe/"):
            return self._unsubscribe(parse_qs(parsed.query))
        if parsed.path.startswith("/api/profile/"):
            code, body = profile_get(parsed.path[len("/api/profile/"):].strip("/"),
                                     self.headers.get("X-Profile-Pin") or "")
            return self._send(code, json.dumps(body).encode(), ".json")
        if self._entity_page(parsed.path):
            return
        return self._static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        # The Paddle webhook is EXEMPT: it is already authenticated by
        # signature, and a retry burst during an incident is exactly when
        # we least want to start dropping payment events on the floor.
        # One-click unsubscribe (RFC 8058). Before the rate limiter and
        # before every auth path: a mail client POSTs here on the
        # reader's behalf with no cookie, and the header on every digest
        # promises it answers.
        if parsed.path in ("/unsubscribe", "/unsubscribe/"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if 0 < length <= MAX_PROFILE_BYTES:
                self.rfile.read(length)          # read and discard the body
            return self.do_POST_unsubscribe(parse_qs(parsed.query))
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
        if parsed.path.startswith("/api/streak/"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_PROFILE_BYTES:
                self.close_connection = True
                return self._send(413, b'{"error":"body too large"}', ".json")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                assert isinstance(body, dict)
            except Exception:                            # noqa: BLE001
                return self._send(400, b'{"error":"body must be a JSON object"}',
                                  ".json")
            return self._streak_post(
                parsed.path[len("/api/streak/"):].strip("/"), body)
        if parsed.path.startswith("/api/tailfade/"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_PROFILE_BYTES:
                self.close_connection = True
                return self._send(413, b'{"error":"body too large"}', ".json")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                assert isinstance(body, dict)
            except Exception:                            # noqa: BLE001
                return self._send(400, b'{"error":"body must be a JSON object"}',
                                  ".json")
            return self._tailfade_post(
                parsed.path[len("/api/tailfade/"):].strip("/"), body)
        if (parsed.path.startswith("/api/social/")
                or parsed.path.startswith("/api/alerts/")):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_PROFILE_BYTES:
                self.close_connection = True
                return self._send(413, b'{"error":"body too large"}', ".json")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                assert isinstance(body, dict)
            except Exception:                            # noqa: BLE001
                return self._send(400, b'{"error":"body must be a JSON object"}',
                                  ".json")
            if parsed.path.startswith("/api/alerts/"):
                return self._alerts_post(
                    parsed.path[len("/api/alerts/"):].strip("/"), body)
            return self._social_post(
                parsed.path[len("/api/social/"):].strip("/"), body)
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

    @staticmethod
    def _kit_board() -> list:
        """The draft board off the built payload, or [] if it is not there.

        Handed to `fantasy_lineup.with_board` so that a player with no
        game logs is valued at his projection instead of at zero. Before
        this, the optimiser benched a first-round rookie behind a
        4.0-point receiver and `fantasy_trade` proposed no deal involving
        him in either direction — measured on a fixture roster
        2026-08-20. Never fatal: no payload means the old behaviour, not
        a dead endpoint.
        """
        try:
            blob = json.loads((WEB / "data" / "fantasy.json").read_text())
        except Exception:                                     # noqa: BLE001
            return []
        return (blob.get("draft_kit") or {}).get("board") or []

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
        my_roster_id = None
        by_roster = {}
        for r in rosters or []:
            who = str(r.get("owner_id") or "")
            rows = rows_for(r)
            by_roster[int(r.get("roster_id") or 0)] = rows
            if who == str(user_id):
                mine = rows
                my_roster_id = r.get("roster_id")
            elif rows:
                rivals[owner.get(who, f"Team {r.get('roster_id')}")] = rows

        conn = connect()
        try:
            season = max((int(s[0]) for s in conn.execute(
                "SELECT DISTINCT season FROM player_game_logs WHERE sport='nfl'"
            ).fetchall()), default=0)
            means = fantasy_lineup.per_game(conn, season) if season else {}
            means = fantasy_lineup.with_board(means, self._kit_board())
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

        # THE TEAM YOU ARE ACTUALLY PLAYING (IDEAS #7). Everything above
        # answers against the field; a head-to-head league is one game
        # against one roster, and which start is right depends on the
        # scoreboard rather than on the projection alone. See
        # engine/fantasy_h2h.py.
        from engine import fantasy_h2h
        out["standings"] = fantasy_h2h.standings(rosters, owner)
        out["me_roster_id"] = (int(my_roster_id)
                               if my_roster_id is not None else None)
        try:
            week = int((query.get("week") or [""])[0])
        except (TypeError, ValueError):
            week = 0
        if not 1 <= week <= 18:
            # The league's own scorekeeper first — `leg` is the week it
            # is scoring right now — and Sleeper's NFL state as the
            # fallback. Neither is a calendar this server has to guess
            # with, which is the third option and the wrong one.
            week = int(((league.get("settings") or {}).get("leg") or 0))
        if not 1 <= week <= 18:
            try:
                week = int((grab("state/nfl", ttl=1800) or {}).get("week") or 0)
            except (DataUnavailable, ValueError):
                week = 0
        out["week"] = week if 1 <= week <= 18 else None
        opp_rows, opp_name = None, None
        if out["week"] and my_roster_id is not None:
            try:
                board = grab(f"league/{league_id}/matchups/{out['week']}",
                             ttl=300)
            except (DataUnavailable, ValueError):
                board = []
            opp_id = fantasy_h2h.opponent_roster_id(board, my_roster_id)
            if opp_id is not None:
                opp_rows = by_roster.get(opp_id) or None
                for r in rosters or []:
                    if int(r.get("roster_id") or 0) == opp_id:
                        opp_name = owner.get(str(r.get("owner_id") or ""),
                                             f"Team {opp_id}")
                        break
        if mine:
            h2h = fantasy_h2h.head_to_head(mine, opp_rows,
                                           league.get("roster_positions"),
                                           scoring, means)
            h2h["opponent"] = opp_name
            h2h["swings"] = fantasy_h2h.swings(h2h)
            out["h2h"] = h2h
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
            means = fantasy_lineup.with_board(means, self._kit_board())
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

        AND THEN CLOUDFLARE WENT IN FRONT (2026-08-21), which added a hop
        the whole scheme above had not accounted for:

            browser → Cloudflare → Caddy → here

        Caddy still reports the peer it saw, and that peer is now a
        Cloudflare edge server. Every visitor in a city collapsed onto a
        handful of addresses, so `rate_ok` was counting a whole region
        into one bucket — 300 API calls and 20 sign-ins a minute for all
        of them together. Quiet sites never notice. The moment traffic
        arrives it starts turning real customers away, which is precisely
        backwards.

        Cloudflare passes the real address in `CF-Connecting-IP`. That
        header is believed ONLY when the machine that spoke to our proxy
        was genuinely Cloudflare, checked against their published ranges
        — see engine/cfips.py for why a header alone will not do, and for
        what happens when the list is not installed (nothing: this falls
        through to the last hop, exactly as before).
        """
        peer = (self.client_address or ("",))[0]
        if peer not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return peer
        raw = self.headers.get("X-Forwarded-For") or ""
        hops = [p.strip() for p in raw.split(",") if p.strip()]
        edge = hops[-1] if hops else peer
        try:
            from engine import cfips
            if cfips.is_cloudflare(edge):
                # `visitor` refuses anything that is not a public address:
                # Cloudflare never reports a caller as 127.0.0.1, and
                # `_local_only` below would believe it.
                real = cfips.visitor(self.headers.get("CF-Connecting-IP"))
                if real:
                    return real
        except Exception:                                    # noqa: BLE001
            # Identifying the caller must never be the thing that fails a
            # request. Worst case we are back to the edge address, which
            # is what we had a moment ago.
            pass
        return edge

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
            if path == "digest":
                from engine import digest as DG, mailer
                out = DG.optin_get(conn, who["id"])
                # The TOKEN never leaves the server. It is a bearer
                # credential for one action, and a page that holds it
                # can leak it into a referrer, a screenshot or a
                # support ticket. The unsubscribe link is minted into
                # the email itself, which is the only place it belongs.
                out.pop("token", None)
                # …and the page is told whether mail can go out at all,
                # so it can say "not switched on yet" instead of
                # offering a subscription to nothing.
                out["available"] = mailer.configured()
                return self._send(200, json.dumps(out).encode(), ".json")
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
                        "delete", "signout-all", "digest"):
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
            if path == "signout-all":
                # THIS session too, so the browser is told to forget
                # itself as well — anything else leaves a page showing an
                # account for a session that no longer exists.
                n = A.end_all_sessions(conn, who["id"])
                return self._send(
                    200, json.dumps({"ended": n}).encode(), ".json",
                    headers=self._session_cookie("", clear=True))
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
            if path == "digest":
                # Two booleans and nothing else. The token is minted
                # server-side and never accepted from a client — a
                # caller that could choose its own unsubscribe token
                # could choose somebody else's.
                from engine import digest as DG
                out = DG.optin_set(conn, who["id"],
                                   bool(body.get("morning")),
                                   bool(body.get("nightly")))
                out.pop("token", None)
                A.touch_session(conn, token)
                return self._send(200, json.dumps(out).encode(), ".json")
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

    # --- tail or fade ----------------------------------------------------
    # Calls are validated against the SERVED board (the full copy, via
    # board_source) — the browser names a player and a market, the board
    # decides everything else. Entitlement-gated with the paywall on:
    # the validation's own 404-vs-409 answers would otherwise let a
    # signed-out prober map the board one name at a time.

    def _tailfade_get(self, path: str):
        if path != "me":
            return self._send(404, b'{"error":"unknown tailfade endpoint"}',
                              ".json")
        from engine import tailfade as TF
        from engine import ledger as _led
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            lconn = _led.connect()
            try:
                out = TF.me(conn, who["id"], lconn)
            finally:
                lconn.close()
        finally:
            conn.close()
        return self._send(200, json.dumps(out).encode(), ".json")

    def _tailfade_post(self, path: str, body: dict):
        if path != "call":
            return self._send(404, b'{"error":"unknown tailfade endpoint"}',
                              ".json")
        from engine import gate
        from engine import tailfade as TF
        A = _acct()
        sport = str(body.get("sport") or "")
        if sport not in LIVE_FILES:
            return self._send(400, b'{"error":"unknown sport"}', ".json")
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if gate.enabled() and not self._entitled(conn, who):
                return self._send(402, json.dumps(
                    {"error": "Tail/fade rides on the picks — an active "
                              "subscription is what makes the argument "
                              "fair."}).encode(), ".json")
            try:
                board = json.loads(Path(gate.board_source(
                    LIVE_FILES[sport])).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                board = {}
            code, out = TF.record_call(
                conn, who["id"], board, sport,
                str(body.get("player") or ""), str(body.get("market") or ""),
                str(body.get("stance") or ""))
        finally:
            conn.close()
        return self._send(code, json.dumps(out).encode(), ".json")

    # --- friends: picks sent between accounts -----------------------------
    # engine/social.py holds the two rules (a share is a POINTER carrying
    # only the pick's identity, and friendships form through invite links
    # rather than lookup); these handlers hold the third: every endpoint
    # requires a session, because there is nothing anonymous here to
    # serve. NOT entitlement-gated — no paid content travels (that is the
    # pointer rule doing its work), so a free account can receive a
    # friend's pointer and see the locked state behind it, which is
    # exactly what the same pick's permalink would show them.
    def _alerts_feed(self, conn, who) -> list:
        """The feed this caller may read, and no more of it.

        feed.json is a PAID file — every entry names a pick — so an
        alert is only ever a filter over a board the reader was already
        entitled to. Outside the wall this answers with nothing rather
        than with the locked stub, and the page says why.
        """
        from engine import gate
        path = WEB / "data" / "feed.json"
        if gate.enabled():
            if not self._entitled(conn, who):
                return []
            path = gate.board_source(path)
        try:
            return (json.loads(path.read_text(encoding="utf-8"))
                    or {}).get("events") or []
        except (OSError, ValueError):
            return []

    def _alerts_get(self, path: str):
        from engine import alerts as AL
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path != "me":
                return self._send(404, b'{"error":"unknown alerts endpoint"}',
                                  ".json")
            watches = AL.list_watches(conn, who["id"])
            events = self._alerts_feed(conn, who)
            since = AL.seen_ts(conn, who["id"])
            out = {
                "watches": watches,
                "kinds": list(AL.KINDS),
                "max": AL.MAX_WATCHES,
                "edge_range": [AL.EDGE_MIN, AL.EDGE_MAX],
                # Everything of theirs in the window, and how much of it
                # is new — the page shows the first and badges the second.
                "fired": AL.fired(events, watches),
                "unseen": len(AL.fired(events, watches, since=since)),
                "newest": AL.newest_ts(events),
                "feed_n": len(events),
            }
            return self._send(200, json.dumps(out).encode(), ".json")
        finally:
            conn.close()

    def _alerts_post(self, path: str, body: dict):
        from engine import alerts as AL
        if path not in ("watch", "unwatch", "seen"):
            return self._send(404, b'{"error":"unknown alerts endpoint"}',
                              ".json")
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "watch":
                code, out = AL.add_watch(conn, who["id"], body.get("kind"),
                                         body.get("value"))
            elif path == "unwatch":
                code, out = AL.remove_watch(conn, who["id"], body.get("id"))
            else:
                AL.mark_seen(conn, who["id"], str(body.get("ts") or ""))
                code, out = 200, {"ok": True}
            return self._send(code, json.dumps(out).encode(), ".json")
        finally:
            conn.close()

    def _social_get(self, path: str):
        from engine import social as SOC
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "me":
                out = {"friends": SOC.friends_list(conn, who["id"]),
                       "inbox": SOC.inbox(conn, who["id"]),
                       "sent": SOC.sent(conn, who["id"]),
                       "requests": SOC.requests_in(conn, who["id"]),
                       "threads": SOC.threads(conn, who["id"]),
                       "invite": SOC.invite_get_or_create(conn, who["id"])}
                return self._send(200, json.dumps(out).encode(), ".json")
            return self._send(404, b'{"error":"unknown social endpoint"}',
                              ".json")
        finally:
            conn.close()

    def _social_post(self, path: str, body: dict):
        from engine import social as SOC
        if path not in ("accept", "send", "send-parlay", "remove", "seen",
                        "revoke-invite", "find", "request", "answer-request",
                        "dm", "thread", "nickname",
                        "delete-message", "delete-thread"):
            return self._send(404, b'{"error":"unknown social endpoint"}',
                              ".json")
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "accept":
                code, out = SOC.invite_accept(conn, who["id"],
                                              str(body.get("token") or ""))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "send":
                # The identity fields and the note are the ONLY things
                # read out of the body — a side, line or price sent by a
                # crafted client lands nowhere, because share_pick has no
                # parameter to receive it.
                code, out = SOC.share_pick(
                    conn, who["id"], int(body.get("to") or 0),
                    str(body.get("sport") or ""), str(body.get("date") or ""),
                    str(body.get("player") or ""),
                    str(body.get("market") or ""),
                    str(body.get("note") or ""))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "send-parlay":
                # Legs are rebuilt here key by key — player and market,
                # the identity pair, and nothing else survives the body.
                # A side, a line or a price in a crafted leg lands
                # nowhere; share_parlay's signature is the second lock.
                legs = [{"player": str(l.get("player") or ""),
                         "market": str(l.get("market") or "")}
                        for l in (body.get("legs") or [])
                        if isinstance(l, dict)]
                code, out = SOC.share_parlay(
                    conn, who["id"], int(body.get("to") or 0),
                    str(body.get("sport") or ""), str(body.get("date") or ""),
                    legs, str(body.get("note") or ""))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "find":
                # Display names only — find_users is where the email
                # oracle stays closed; the handler adds nothing to ask.
                out = SOC.find_users(conn, who["id"],
                                     str(body.get("q") or ""))
                return self._send(200, json.dumps({"users": out}).encode(),
                                  ".json")
            if path == "request":
                code, out = SOC.request_send(conn, who["id"],
                                             int(body.get("to") or 0))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "answer-request":
                code, out = SOC.request_answer(
                    conn, who["id"], int(body.get("id") or 0),
                    bool(body.get("accept")))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "remove":
                SOC.friend_remove(conn, who["id"], int(body.get("friend") or 0))
                return self._send(200, b'{"removed":true}', ".json")
            if path == "revoke-invite":
                SOC.invite_revoke(conn, who["id"])
                out = SOC.invite_get_or_create(conn, who["id"])
                return self._send(200, json.dumps(out).encode(), ".json")
            if path == "dm":
                # Body text only — dm_send has no parameter through
                # which a pick field could ride along with the words.
                code, out = SOC.dm_send(conn, who["id"],
                                        int(body.get("to") or 0),
                                        str(body.get("body") or ""))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "thread":
                code, out = SOC.thread(conn, who["id"],
                                       int(body.get("friend") or 0))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "delete-message":
                # Hides ONE item from this viewer's threads. Never the
                # friend's copy — engine/social's deleting section says
                # why that would be a reach into somebody else's account.
                code, out = SOC.delete_item(conn, who["id"],
                                            str(body.get("kind") or ""),
                                            int(body.get("id") or 0))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "delete-thread":
                code, out = SOC.delete_thread(conn, who["id"],
                                              int(body.get("friend") or 0))
                return self._send(code, json.dumps(out).encode(), ".json")
            if path == "nickname":
                # Your private label for a friend — empty clears it. It
                # is stored against YOUR id only and never shown to the
                # friend it names.
                code, out = SOC.nickname_set(conn, who["id"],
                                             int(body.get("friend") or 0),
                                             str(body.get("name") or ""))
                return self._send(code, json.dumps(out).encode(), ".json")
            # "seen", scoped to one conversation when a friend is named.
            friend = body.get("friend")
            SOC.mark_seen(conn, who["id"],
                          int(friend) if friend else None)
            return self._send(200, b'{"seen":true}', ".json")
        finally:
            conn.close()

    # --- the streak game -------------------------------------------------
    # The slate itself is a free static file; these endpoints carry only
    # what is per-account (picks, the fold, names) or cross-account (the
    # leaderboard). Everything is validated against the published slate,
    # never against client-supplied questions — the browser names a qid
    # and a side, and the server decides what those mean.

    def _streak_get(self, path: str):
        S = _streak()
        A = _acct()
        if path == "leaders":
            slate = streak_slate()
            conn = A.connect()
            try:
                S.fold_all(conn, slate)
                board = S.leaders(conn)
                # A COUNT, not a roster — see playing_today's docstring
                # for why the board is empty on day one and why this is
                # the honest thing to show instead.
                tonight = S.playing_today(conn, str(slate.get("date") or ""))
            finally:
                conn.close()
            return self._send(200, json.dumps(
                {"leaders": board, "in_tonight": tonight}).encode(), ".json")
        if path == "me":
            conn = A.connect()
            try:
                who = self._account(conn)
                if not who:
                    return self._send(401, b'{"error":"sign in first"}',
                                      ".json")
                out = S.me(conn, who["id"], streak_slate())
            finally:
                conn.close()
            return self._send(200, json.dumps(out).encode(), ".json")
        return self._send(404, b'{"error":"unknown streak endpoint"}', ".json")

    def _streak_post(self, path: str, body: dict):
        S = _streak()
        A = _acct()
        if path not in ("pick", "name"):
            return self._send(404, b'{"error":"unknown streak endpoint"}',
                              ".json")
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            if path == "pick":
                code, out = S.record_pick(
                    conn, who["id"], streak_slate(),
                    str(body.get("qid") or ""), str(body.get("side") or ""))
            else:
                code, out = S.set_name(conn, who["id"],
                                       str(body.get("name") or ""))
        finally:
            conn.close()
        return self._send(code, json.dumps(out).encode(), ".json")

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

    # --- billing: Stripe holds the card, we hold a status ------------------
    def _entitled(self, conn, who) -> bool:
        """May this caller read a full board?

        THE PAYWALL BEING OFF MEANS EVERYBODY, and that ordering matters:
        the flag is checked before the account is, so a site running
        without a processor behaves exactly as it did before any of this
        was written rather than refusing everyone.
        """
        from engine import billing as BI
        from engine import gate
        from engine import redeem as RD
        if not gate.enabled():
            return True
        if not who:
            return False
        if gate.comped(who.get("email")):
            return True
        # A REDEEMED CODE IS AN ENTITLEMENT, checked before the processor
        # and independent of it. This is what lets the paywall be switched
        # on before Stripe is live: comp addresses and codes are then the
        # two ways in, both under Ethan's hand. Its own try, so that a
        # broken redemption lookup cannot cost a PAYING subscriber their
        # board — the billing check below still runs.
        try:
            RD.init(conn)
            if RD.active(conn, who["id"]):
                return True
        except Exception:                                    # noqa: BLE001
            pass
        try:
            BI.init(conn)
            st = BI.status_for(conn, who["id"])
        except Exception:                                    # noqa: BLE001
            # A billing lookup that breaks must not become a lockout. The
            # failure everybody notices is a paying customer refused; the
            # failure nobody notices is one free read.
            return False
        return bool(st.get("entitled"))

    def _players_search(self, q):
        """Player search across every league, straight off the game logs.

        Ethan, 2026-08-18: "You should be able too look up any player in
        the league too that specific sport." The static board only knows
        tonight's priced players; the history DB knows everyone who has
        appeared in an ingested game. UNGATED on purpose: game logs are
        FACTS, on the same free footing as rosters and injuries
        (engine/statlogs.py's header carries the argument) — the paid
        thing is picks, and none ride here.

        EVERY LEAGUE BY DEFAULT, AND FIGHTERS TOO. Ethan, 2026-08-23:
        "even if im selected on nfl, i shoudl still be able to look up
        mlb or ufc or wnba players." It shipped filtered to whichever tab the visitor was
        on, which made an empty result ambiguous in the worst way — "we
        have nothing on him" and "you are on the wrong tab" looked
        identical, and the second one is not the visitor's mistake to
        make. ``sport`` is now a preference that leads the ranking;
        ``scope=sport`` still pins the search to one league for a caller
        that means it.
        """
        from engine import playersearch, statlogs
        sport = (q.get("sport") or [""])[0].lower()
        term = (q.get("q") or [""])[0][:40]
        if (q.get("scope") or [""])[0].lower() == "sport":
            # Ethan, 2026-09-01, reversing the 08-23 all-league decision:
            # "i wanna be able to search any player only on what sport
            # tabe we are on. if im on mlb then i should only be able to
            # search mlb and so forth." The page sends scope=sport now,
            # so this branch is the search — and the UFC tab's players
            # live in the fighter store, not the history DB.
            if sport == "ufc":
                from engine.ufc import fighters
                hits = fighters.search(term)
            elif sport in statlogs.SPORT_MARKETS:
                hits = statlogs.search(sport, term)
            else:
                return self._send(400, b'{"error":"no log-backed search '
                                       b'for this sport"}', ".json")
        else:
            # playersearch, not statlogs: fighters are not in the history
            # DB and never were, so the league-wide log search could not
            # find one however many leagues it covered. Ethan, an hour
            # after the all-league change: "im not able to search ufc
            # players." Two stores, one answer.
            hits = playersearch.search(term, prefer=sport)
        return self._send(200, json.dumps({"players": hits}).encode(),
                          ".json")

    def _players_logs(self, q):
        """One player's multi-market logs — the searched-up profile's food.

        Same shape the board's ``player_stats`` section ships, so the page
        draws a bench bat with the exact card a priced star gets."""
        from engine import statlogs
        sport = (q.get("sport") or [""])[0].lower()
        player = (q.get("player") or [""])[0][:60]
        if sport not in statlogs.SPORT_MARKETS:
            return self._send(400, b'{"error":"no log-backed search for '
                                   b'this sport"}', ".json")
        stats = statlogs.for_player(sport, player)
        return self._send(200, json.dumps(
            {"player": player, "stats": stats}).encode(), ".json")

    def _players_versus(self, q):
        """A player's history against one opponent — the head-to-head.

        Ethan, 2026-09-01: "the rams take on the 49ers week one and I
        wanna see how Devonte Adam's did the last time the 49ers played
        the rams." Without ``vs`` this returns the opponents he has
        logged games against (the page's picker options — exact stored
        keys, so the join back can never misspell); with ``vs`` it
        returns every stored game against them, one row per game with
        every ingested market. UNGATED like the other log endpoints:
        game logs are FACTS on the free footing of rosters and injuries.
        """
        from engine import statlogs
        sport = (q.get("sport") or [""])[0].lower()
        player = (q.get("player") or [""])[0][:60]
        vs = (q.get("vs") or [""])[0][:60]
        if sport not in statlogs.SPORT_MARKETS:
            return self._send(400, b'{"error":"no log-backed lookup for '
                                   b'this sport"}', ".json")
        out = (statlogs.versus(sport, player, vs) if vs
               else statlogs.opponents_of(sport, player))
        return self._send(200, json.dumps(out or {}).encode(), ".json")

    def _players_fantasy(self, q):
        """The full fantasy dossier — engine/ffprofile.py's page, served.

        NFL-only and ungated for the same reason the log endpoints are:
        season stats, snap shares and schedules are FACTS. The picks
        stay the paid thing."""
        from engine import ffprofile
        player = (q.get("player") or [""])[0][:60]
        return self._send(200, json.dumps(
            ffprofile.profile(player)).encode(), ".json")

    def _serve_board(self, public):
        """The board this CALLER is entitled to, cached and revalidated.

        THE BUG THIS FIXES, proved 2026-08-22 with a signed-in comped
        account: this endpoint served `web/data/<board>.json` to
        everybody, and with QB_PAYWALL on that file is the REDACTED copy —
        `recommendations: []`. So a paying subscriber's page fetched the
        stripped board and drew "No qualifying plays at current numbers",
        which reads as the model finding nothing rather than as the
        paywall taking it away. `live_picks` is not a paid key, so their
        riding bets still showed underneath it, which is exactly what
        Ethan was looking at.

        gate.py has said since it was written that "subscribers get the
        full board from /api/board/<name>" — and nothing in web/js/app.js
        has ever called that endpoint. The page only ever asks here. So
        this is where the entitlement check belongs.

        UNENTITLED CALLERS ARE UNAFFECTED: they get the same redacted file
        they got before, from the same path, with the same locked markers
        the paywall page reads.
        """
        from engine import gate
        body = mtime = etag = None
        if gate.enabled():
            conn = _acct().connect()
            try:
                if self._entitled(conn, self._account(conn)):
                    body, mtime, etag = board_bytes(public.name)
            finally:
                conn.close()
        if body is None:
            body, mtime, etag = file_bytes(public)
        if body is None:
            return self._send(404, b'{"error":"no board"}', ".json")
        if etag and self.headers.get("If-None-Match") == etag:
            return self._send_not_modified(etag, mtime)
        return self._send(200, body, ".json", mtime=mtime,
                          headers=[("ETag", etag)] if etag else None)

    def _api_board(self, name: str):
        """The subscriber's copy of a board, read from outside the web root.

        This endpoint exists because `web/data/*.json` is served off disk by
        Caddy and therefore holds the REDACTED board. Everything paid comes
        through here, where there is a session to check.

        402 rather than 403 for a signed-in account without a
        subscription: the distinction is "pay and this works" versus "you
        may never have this", and the page renders a different thing for
        each.
        """
        # ENTITLEMENT FIRST, THEN THE FILE. This used to read and parse
        # the whole board before asking who was calling, so an
        # unauthenticated request cost a megabyte of disk and CPU to
        # answer with 401. Nothing about that was exploitable — the board
        # was never sent — but it made the cheapest request on the site
        # the most expensive one to refuse, which is the wrong way round
        # for a public endpoint.
        #
        # It also means a stranger can no longer learn which boards exist
        # by watching 404 and 401 differ.
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not self._entitled(conn, who):
                locked = {"error": "This board needs a subscription.",
                          "signed_in": bool(who), "locked": True}
                return self._send(401 if not who else 402,
                                  json.dumps(locked).encode(), ".json")
        finally:
            conn.close()
        body, mtime, etag = board_bytes(name)
        if body is None:
            return self._send(404, b'{"error":"no such board"}', ".json")
        # REVALIDATION, WHICH IS BANDWIDTH RATHER THAN CPU. The page polls
        # this every 30 seconds and the launcher rebuilds every 60, so
        # roughly half of all polls ask for a board the caller already
        # has, and used to be handed the whole thing again. On a board of
        # any size that is the largest recurring cost the site has, and it
        # is paid per subscriber per poll, all day.
        #
        # Done with an ETag the CLIENT sends back rather than by relaxing
        # `Cache-Control: no-store`: the browser cache would work, but it
        # would also mean a subscriber's paid board sitting on disk in
        # their browser, and that is a property this site chose not to
        # have. app.js keeps the tag in memory and hands it back.
        if etag and self.headers.get("If-None-Match") == etag:
            return self._send_not_modified(etag, mtime)
        return self._send(200, body, ".json",
                          headers=[("ETag", etag)] if etag else None)

    def _billing_get(self, path: str):
        from engine import billing as BI
        A = _acct()
        if path != "status":
            return self._send(404, b'{"error":"unknown billing endpoint"}',
                              ".json")
        from engine import gate as GATE_
        conn = A.connect()
        try:
            BI.init(conn)
            who = self._account(conn)
            out = {"configured": BI.configured(), "signed_in": bool(who)}
            # WHICH PLANS CAN ACTUALLY BE SOLD, sent whether or not
            # anybody is signed in, because the plans page renders before
            # sign-in. A plan with no price id configured must not draw a
            # buy button that 502s after the customer has committed.
            out["plans"] = BI.plan_catalogue()
            # THE TRIAL, ADVERTISED TO EVERYONE and granted to fewer. The
            # plans page renders before anybody signs in, so the offer has
            # to be outside the `if who` block; whether THIS account
            # actually gets one is decided at checkout, from the database,
            # and is reported below for the people we can already answer
            # for.
            out["trial_days"] = BI.TRIAL_DAYS
            out["trial_plan"] = BI.TRIAL_PLAN
            # NO PROMO CODES HERE. This endpoint is public — it renders
            # the plans page before anybody signs in — so anything in it
            # is readable by anyone who opens the network tab. A promo
            # code Ethan hands to friends is a secret, and this response
            # was publishing it. Stripe's checkout box is enough: it says
            # "Add promotion code" and names none of them.
            if BI.configured():
                # Test and live are the SAME Stripe account distinguished
                # by a key prefix — unlike Paddle, where the sandbox is a
                # separate account entirely. So "are we live" is a
                # question about the key we are holding.
                try:
                    out["live"] = BI.live_mode(BI.keys()[0])
                except BI.BillingUnavailable:
                    out["live"] = False
            if who:
                # Their OWN address, same-origin, already available from
                # /api/account/me. The plans page shows it so that a
                # signed-in reader who has not subscribed is told they are
                # signed in — landing them on a page headed "Log in" is
                # how this looked when Ethan reported that signing in
                # never says it worked.
                out["email"] = who["email"]
                # Signed in, so we can say rather than advertise: somebody
                # who has subscribed before does not get a second trial,
                # and the plans page should not promise them one.
                out["trial_eligible"] = not BI.has_subscribed_before(
                    conn, who["id"])
                out.update(BI.status_for(conn, who["id"]))
                # Codes ride alongside rather than inside the subscription
                # status: a redeemed code is not a subscription and saying
                # it is would put a status on the page that no processor
                # would recognise if support ever had to look it up.
                from engine import redeem as RD
                RD.init(conn)
                out["codes"] = RD.describe(conn, who["id"])
                if out["codes"]["active"]:
                    out["entitled"] = True
                # AND THE COMP LIST, which this endpoint did not know
                # about. `_entitled` — the method that actually decides
                # whether a full board goes out — checks `gate.comped`
                # first, so a comped address was already being served
                # unredacted data while this endpoint kept answering
                # "entitled: false". The browser believed the endpoint,
                # kept the wall up, and drew a plans page on top of a
                # board the reader was entitled to.
                #
                # Two answers to one question is the bug; this is the
                # second place that question gets asked and both places
                # now agree.
                if GATE_.comped(who.get("email")):
                    out["entitled"] = True
                    out["comped"] = True
                    # And SAY so. `status_for` reads the subscriptions
                    # table, which has no row for a comped address, so its
                    # sentence is "No subscription." — printed in the
                    # entitled style next to a working site. Whatever the
                    # reader concluded from that, it was not the truth.
                    if out.get("status") in (None, "none"):
                        out["note"] = ("Comped account — full access, no "
                                       "card on file.")
                # THE DISCORD INVITE, AND ONLY HERE. Inside the `if who`
                # block and behind the entitlement it has just computed,
                # so it is never in an anonymous response — and never in
                # web/js/app.js, which is a static asset served to
                # everybody. It lives in the environment, so it is not in
                # the repository either and rotating it after a leak is a
                # config line and a restart.
                if out.get("entitled"):
                    from engine import secrets as _s
                    _s.load_local_secrets()
                    invite = os.environ.get("QB_DISCORD_INVITE", "").strip()
                    if invite:
                        out["discord"] = invite
            # THE INSTAGRAM IS NOT THE INVITE and is not gated like one.
            # It is a public page anybody can already find; the Discord
            # welcome cites it because it is where this desk's picks have
            # been posted, and citing it to somebody who has not
            # subscribed is the entire point of a sales page. Outside the
            # `if who` block for that reason.
            from engine import secrets as _s2
            _s2.load_local_secrets()
            gram = os.environ.get("QB_INSTAGRAM", "").strip()
            if gram:
                out["instagram"] = gram
            # Whether the gate is even on. The account page cannot tell
            # "you need to subscribe" from "everything is free right now"
            # without it, and it has been guessing.
            out["paywall"] = GATE_.enabled()
            return self._send(200, json.dumps(out).encode(), ".json")
        finally:
            conn.close()

    def _billing_confirm(self, raw: bytes):
        """"I have just come back from Checkout" — go and ask Stripe.

        THE WEBHOOK IS NOT THE ONLY WAY IN ANY MORE, and it should never
        have been the only one. A webhook is a request from Stripe's
        servers to ours, which means every box in front of this site gets
        an opinion on whether a paying customer gets what they paid for:
        a WAF that decides robots are suspicious, an expired origin
        certificate, a restart at the wrong second. Cloudflare's Bot Fight
        Mode went on over the live site on 2026-08-21 and on the free plan
        it cannot be told to skip a path.

        None of that reaches this endpoint, because this one is a browser
        asking on its own behalf, and the answer comes from a READ of
        Stripe rather than from anything being delivered to us.

        IT IS NOT A WAY IN. The session id in the body grants nothing:
        Stripe must say the session is paid, and the session's
        `client_reference_id` must be the account making the request. A
        session id belonging to somebody else entitles nobody.
        """
        from engine import billing as BI
        A = _acct()
        conn = A.connect()
        try:
            BI.init(conn)
            who = self._account(conn)
            if not who:
                return self._send(401, b'{"error":"sign in first"}', ".json")
            try:
                body = json.loads(raw.decode() or "{}")
            except Exception:                                # noqa: BLE001
                body = {}
            try:
                out = BI.reconcile_session(
                    conn, who["id"], str(body.get("session") or ""))
            except BI.BillingUnavailable as exc:
                # Not an error the customer can act on, and not a reason
                # to lose their place: the webhook may still land.
                return self._send(200, json.dumps(
                    {"entitled": False, "checked": False,
                     "note": str(exc)}).encode(), ".json")
            out["checked"] = True
            return self._send(200, json.dumps(out).encode(), ".json")
        finally:
            conn.close()

    def _billing_redeem(self, raw: bytes):
        """Apply a discount code. Signed-in accounts only.

        The account requirement is not ceremony: a grant has to attach to
        somebody, the one-per-account rule needs an account to be per, and
        the rate limiter needs a subject to count. An anonymous redemption
        is an unlimited redemption.
        """
        from engine import redeem as RD
        A = _acct()
        conn = A.connect()
        try:
            who = self._account(conn)
            if not who:
                return self._send(401,
                    b'{"error":"Sign in first, then redeem your code."}', ".json")
            try:
                body = json.loads(raw.decode() or "{}")
            except Exception:                                # noqa: BLE001
                body = {}
            code = str(body.get("code") or "")
            # The site has two code systems. This endpoint owns the one
            # that grants free months; Stripe owns the one that discounts
            # a subscription. Handing the promo sentences down means a
            # checkout code typed in here is told where it goes instead
            # of being called invalid — and `redeem` still needs no
            # import from the module that moves money.
            from engine import billing as _BI
            try:
                got = RD.redeem(conn, who["id"], code,
                                elsewhere=_BI.promo_misdirect())
            except RD.RedeemError as exc:
                # 200 with an error field, not a 4xx: this is an expected
                # answer to a normal question, and a 400 in the console on
                # every mistyped promo code trains everyone to ignore the
                # console.
                return self._send(200, json.dumps(
                    {"ok": False, "error": str(exc)}).encode(), ".json")
            return self._send(200, json.dumps({
                "ok": True, "code": got["code"], "months": got["months"],
                "granted_to": got["granted_to"],
                "note": f"{got['months']} month(s) of full access added.",
            }).encode(), ".json")
        finally:
            conn.close()

    def _billing_post(self, path: str, raw: bytes):
        from engine import billing as BI
        A = _acct()
        if path == "webhook":
            return self._billing_webhook(raw)
        if path == "redeem":
            return self._billing_redeem(raw)
        if path == "confirm":
            return self._billing_confirm(raw)
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
                    try:
                        body = json.loads(raw.decode() or "{}")
                    except Exception:                        # noqa: BLE001
                        body = {}
                    # NOT DEFAULTED. `price_for` refuses an unknown plan,
                    # and that refusal is the point: substituting the
                    # monthly price for a plan we do not recognise means
                    # charging $25 to somebody who believes they bought a
                    # year. An absent plan is the front end's own default,
                    # which is a different thing from a wrong one.
                    plan = str(body.get("plan") or BI.DEFAULT_PLAN)
                    # DECIDED HERE, FROM THE DATABASE. The browser says
                    # which plan; it does not get a say in whether there
                    # is a trial or how long it runs. A trial length read
                    # off a request body is a free subscription for
                    # anybody who opens the network tab.
                    fresh = not BI.has_subscribed_before(conn, who["id"])
                    trial = BI.trial_days_for(plan, fresh)
                    # ONE PROMO PER ACCOUNT, decided here for the same
                    # reason the trial is: an account that has already
                    # held a subscription is not offered the promo box at
                    # all, so cancelling and re-buying at 75% off is not
                    # a route. Stripe's own first_time_transaction
                    # restriction says the same thing about the CUSTOMER;
                    # this says it about the ACCOUNT, and the two catch
                    # different halves of the same trick.
                    url = BI.start_checkout(
                        who["id"], who["email"],
                        # THE SESSION ID COMES BACK WITH THEM. It grants
                        # nothing — see BI.reconcile_session — it is the
                        # handle we use to ASK Stripe whether this
                        # particular payment happened, so that a webhook
                        # which never arrives cannot cost a customer the
                        # thing they just bought.
                        f"{base}/?paid=1&s={{CHECKOUT_SESSION_ID}}#account",
                        f"{base}/#paywall", plan, trial_days=trial,
                        allow_promo=fresh)
                else:
                    cust = BI.status_for(conn, who["id"]).get("customer_id")
                    if not cust:
                        return self._send(400, json.dumps(
                            {"error": "No subscription to manage yet."}
                        ).encode(), ".json")
                    url = BI.open_portal(cust, f"{base}/#account")
            except BI.BillingUnavailable as exc:
                return self._send(502, json.dumps({"error": str(exc)}).encode(),
                                  ".json")
            return self._send(200, json.dumps({"url": url}).encode(), ".json")
        finally:
            conn.close()

    def _site_base(self) -> str:
        """The address this browser reached us on, for Stripe's return trip.

        Read from the request rather than configured, because this site
        answers on localhost, a LAN address and a tailscale name, and a
        hardcoded one would send two of those three somewhere they cannot
        get back from.

        QB_SITE_URL OVERRIDES IT, and exists for the case the header
        cannot cover: `Host` is whatever the CUSTOMER typed. Somebody who
        reaches the site on a bare IP, or on a hostname that has no TLS
        certificate, gets sent back there after paying — to a browser
        warning, or to nothing. Setting it pins the return trip to the
        one address that is known to work.
        """
        # secrets.local is where QB_SITE_URL is written alongside the
        # Stripe keys, and the loader is a no-op after the first call.
        from engine import secrets as _s
        _s.load_local_secrets()
        pinned = os.environ.get("QB_SITE_URL", "").strip().rstrip("/")
        if pinned:
            return pinned
        host = (self.headers.get("X-Forwarded-Host")
                or self.headers.get("Host") or "127.0.0.1:8000")
        scheme = "https" if self._is_https() else "http"
        return f"{scheme}://{host}"

    def _billing_webhook(self, raw: bytes):
        """Stripe telling us somebody paid. THE ONLY THING THAT GRANTS
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
        A = _acct()
        try:
            _sk, whsec, _price = BI.keys()
        except BI.BillingUnavailable:
            return self._send(503, b'{"error":"billing not configured"}',
                              ".json")
        if not whsec:
            return self._send(503, json.dumps(
                {"error": f"No {BI.ENV_WEBHOOK_SECRET} set, so this endpoint "
                          "cannot tell a real Stripe event from a forged "
                          "one. Refusing rather than trusting it."}).encode(),
                ".json")
        sig = self.headers.get("Stripe-Signature") or ""
        if not BI.verify_signature(raw, sig, whsec):
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
            # Stripe names the event `id`; Paddle named it `event_id`,
            # and this reads both because getting it wrong is silent in
            # the worst direction: already_handled() treats an empty id
            # as "not seen before" and returns False every time, so the
            # replay guard would be switched off while still looking
            # present. A retried subscription.created is then a second
            # grant.
            if BI.already_handled(conn, payload.get("id")
                                  or payload.get("event_id")):
                return self._send(200, b'{"received":true,"duplicate":true}',
                                  ".json")
            event = BI.read_event(payload)
            applied = BI.apply_event(conn, event) if event else False
            # 200 EVEN WHEN WE DID NOTHING. Stripe retries anything that is
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
            means = fantasy_lineup.with_board(means, self._kit_board())
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
                return self._serve_board(live)
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
    def _gated_board(self, path: str):
        """Redact a board on the way out, or None to serve it normally.

        None is the fast path and the common one: the flag is off, the
        file is free by design, or it is already redacted. Only a file
        that genuinely still carries paid rows is parsed and rewritten.

        CACHING IS THE SUBTLE RISK HERE and it is already handled, in two
        places that have to stay consistent. `_send` marks every response
        this app writes `no-store`, so anything that leaves through here
        is never cached by anyone. Caddy separately marks /data/*.json
        `public, max-age=60` — correct only because the files IT serves
        do not vary by who is asking, being the redacted copy. If a future
        change ever makes an on-disk board vary by reader, that Caddy
        header becomes a way to hand a subscriber's copy to the next
        anonymous visitor: the paywall defeated by a cache rather than by
        an attacker.
        """
        from engine import gate
        if not gate.enabled():
            return None
        name = path[len("/data/"):]
        if gate.is_free(name):
            return None
        target = (WEB / path.lstrip("/")).resolve()
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        # Already sealed? Serve the bytes untouched — no rewrite, and the
        # cache header stays cacheable.
        try:
            if not gate._paid_rows(payload, name):
                return None
        except Exception:                                    # noqa: BLE001
            pass
        A = _acct()
        conn = A.connect()
        try:
            if self._entitled(conn, self._account(conn)):
                # A paying reader may have the whole thing — but this
                # response is theirs alone and must never be cached.
                self._send(200, json.dumps(payload).encode(), ".json")
                return True
        finally:
            conn.close()
        self._send(200, json.dumps(gate.redact(payload, name)).encode(), ".json")
        return True

    #: The unsubscribe page. Plain HTML, no app, no script — it has to
    #: work in whatever browser an email link opens, including the
    #: stripped-down one inside a mail client, and it has to work when
    #: the person following it has forgotten they ever had an account.
    _UNSUB_PAGE = """<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>%s — Qellys Book</title>
<style>body{background:#0b0906;color:#f5efe6;font:16px/1.5 system-ui,
-apple-system,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh}
main{max-width:32rem;padding:2rem}h1{font-size:1.4rem;margin:0 0 .6rem}
p{color:#b8ada1}a{color:#e8b64c}</style></head><body><main>
<h1>%s</h1><p>%s</p><p><a href="/">Qellys Book</a></p></main></body></html>"""

    def _unsubscribe(self, query: dict):
        """One click, no sign-in, both digests off.

        AN UNSUBSCRIBE THAT ASKS FOR A PASSWORD IS A SPAM REPORT. The
        token is unguessable, does exactly one thing, and belongs to one
        account — so there is nothing here worth protecting with a login
        and a great deal riding on the click working first time.

        Answers 200 either way, including for a token nobody recognises.
        A page that said "no such subscription" would let anybody probe
        which tokens are live, and it would read as a failure to somebody
        who had simply clicked twice.
        """
        token = (query.get("t") or [""])[0]
        done = False
        try:
            from engine import accounts as A, digest as DG
            conn = A.connect()
            try:
                done = DG.unsubscribe(conn, token)
            finally:
                conn.close()
        except Exception:                                    # noqa: BLE001
            done = False
        title = "Unsubscribed"
        body = ("You will not get the morning card or the nightly recap any "
                "more. Nothing else about your account has changed, and you "
                "can turn them back on any time from the Account page.")
        page = (self._UNSUB_PAGE % (title, title, body)).encode("utf-8")
        # No-store, and noindex in the markup: this URL carries a bearer
        # token and has no business in a cache or a search index.
        self._send(200, page, ".html")
        return done

    def do_POST_unsubscribe(self, query: dict):
        """RFC 8058 one-click, which Gmail and Apple Mail POST to.

        The header on every digest promises this endpoint answers a
        POST. A List-Unsubscribe-Post that 405s is worse than no header
        at all: the client shows the control, the reader presses it, and
        nothing happens.
        """
        return self._unsubscribe(query)

    def _receipts_csv(self):
        """Every settled pick, as a file somebody can open in a spreadsheet.

        Ethan, 2026-08-25: *"Track record page with receipts … no
        cherry-picking. This is your whole sales pitch."*

        NOT GATED, and that is the same decision record.json already
        carries: the record is the evidence the subscription is sold on,
        and a proof nobody can read persuades nobody. Every row here is
        SETTLED — a pick whose game has finished and whose result is
        public. It contains no open position, no line we are currently
        recommending and no unsettled edge, so it gives away nothing
        that is still worth money.

        Built in memory rather than streamed: the journal is thousands
        of rows, not millions, and a half-written download that fails
        mid-stream is worse than a slow one.
        """
        try:
            from engine import ledger as L
            conn = L.connect()
        except Exception:                                    # noqa: BLE001
            return self._send(503, b"receipts unavailable", ".txt")
        try:
            rows = L.receipts(conn)
        except Exception:                                    # noqa: BLE001
            return self._send(503, b"receipts unavailable", ".txt")
        finally:
            conn.close()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(L.RECEIPT_COLUMNS),
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        body = buf.getvalue().encode("utf-8")
        # A filename with the date in it, because a person downloading
        # this twice a month should not end up with receipts(3).csv and
        # no idea which is which.
        stamp = time.strftime("%Y-%m-%d")
        self._send(200, body, ".csv", headers=[
            ("Content-Disposition",
             f'attachment; filename="qellys-receipts-{stamp}.csv"')])

    def do_HEAD(self):
        """Headers only, for anything the static handler would serve.

        THE STATUS PAGE IS THE CALLER. It asks each published board when
        it was last written, and `Last-Modified` is that answer without
        downloading a 2MB board to read one field out of it.

        In production Caddy answers /data/*.json off disk and never
        reaches this code — it speaks HEAD natively. This exists so the
        page behaves the same under `python3 server.py`, where the
        default handler answers HEAD with 501 and the status page would
        be blank on the one machine where it is being developed.

        Static paths only. An API HEAD gets the same 501 it always did,
        because those handlers write bodies and a half-suppressed
        response is a framing bug waiting to happen.
        """
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_error(501, "Unsupported method ('HEAD')")
            return
        if path in ("/", ""):
            path = "/index.html"
        target = (WEB / path.lstrip("/")).resolve()
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        st = target.stat()
        self.send_response(200)
        self.send_header("Content-Type",
                         CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        self.send_header("Cache-Control", "no-store")
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()

    def _entity_page(self, path: str) -> bool:
        """A real address — /mlb, /player/juan-soto, /game/ne-sea-0909.

        Answers with the ORDINARY app document, its preview block swapped
        for this entity's and a `__QB_ROUTE__` hint naming the hash route
        to open. See engine/routes.py for why this is one document rather
        than a landing page that redirects.

        Returns False for anything that is not one of our routes, so the
        static handler still serves the real files and the real 404 —
        swallowing unknown paths here would turn every typo into a soft
        landing on the board, which is the thing a 404 page is for.

        A REAL FILE ALWAYS WINS. `/players` is a route and `/privacy.html`
        is a file; if a page were ever added at a name this table also
        claims, the file is what should be served, because that is what
        every link to it already expects.
        """
        if "." in path.rsplit("/", 1)[-1]:
            return False                       # an asset, not a place
        try:
            route = routes.resolve(path, WEB)
        except Exception:                                    # noqa: BLE001
            # A malformed board must not take the front page down with
            # it: fall through to the static handler, which serves the
            # app at / and the 404 page everywhere else.
            return False
        if route is None:
            return False
        target = (WEB / path.strip("/")).resolve()
        if target.is_relative_to(WEB.resolve()) and target.is_file():
            return False
        index = WEB / "index.html"
        if not index.is_file():
            return False
        try:
            body = routes.document(route, index.read_text(encoding="utf-8"))
        except OSError:
            return False
        self._send(200, body.encode("utf-8"), ".html")
        return True

    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        # Browsers probe /favicon.ico on their own, before they have parsed
        # the <link rel="icon"> that points at our SVG. We only ship the one
        # icon, so hand it back here too — otherwise every single page load
        # logs a 404 that means nothing.
        if path == "/favicon.ico":
            path = "/favicon.svg"
        # The worker names its own cache after the bundle it holds. If
        # the stamp cannot be computed — a shell file removed mid-read, a
        # permissions problem — the raw file is served instead, because a
        # /sw.js that 500s leaves the OLD worker installed and in charge,
        # which is the failure this exists to prevent.
        if path == "/sw.js" and (WEB / "sw.js").is_file():
            try:
                body = sw_body()
            except OSError:
                body = None
            if body is not None:
                self._send(200, body, ".js",
                           mtime=(WEB / "sw.js").stat().st_mtime)
                return
        # THE BACKSTOP, for anything the startup seal did not catch — a
        # board written by a build that ran without QB_PAYWALL in its
        # environment, say, which lands on the public path whole and does
        # not wait for a restart.
        #
        # In production Caddy answers /data/*.json off disk and never
        # reaches this code, which is exactly why the startup seal above
        # is the primary defence rather than this. This covers `python3
        # server.py` with no proxy in front, and it costs a parse only on
        # a paid board while the paywall is on.
        if path.startswith("/data/") and path.endswith(".json"):
            gated = self._gated_board(path)
            if gated is not None:
                return gated
        target = (WEB / path.lstrip("/")).resolve()
        # Prevent path traversal outside the web root. is_relative_to (not a
        # string prefix) so a sibling like web2/ could never slip through.
        if not target.is_relative_to(WEB.resolve()) or not target.is_file():
            # A mistyped page gets the real 404 page (render 23) when it
            # is on disk; an asset miss (a stale precached .js, a missing
            # image) keeps the bare body, because handing a browser a
            # page of HTML where it asked for a script is how a blank
            # screen replaces a clear console error.
            page = WEB / "404.html"
            wants_page = target.suffix in ("", ".html", ".htm")
            if wants_page and page.is_file():
                self._send(404, page.read_bytes(), ".html")
            else:
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

    def _send_not_modified(self, etag: str, mtime: float | None = None):
        """304: the caller's copy is still current.

        NO BODY AND NO CONTENT-LENGTH, which is what 304 means. The
        handler speaks HTTP/1.0 and closes the connection after every
        response, so there is no framing to get wrong here.
        """
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-store")
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        if mtime is not None:
            self.send_header("Last-Modified", formatdate(mtime, usegmt=True))
            self.send_header("Access-Control-Expose-Headers",
                             "Last-Modified, ETag")
        self.end_headers()

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


#: How many requests may be in flight at once. Beyond this the server
#: says 503 and asks for a retry instead of starting another thread.
#:
#: WHY THERE IS A CEILING AT ALL. `ThreadingHTTPServer` starts one thread
#: per connection and never stops. On a 1GB droplet a burst — the site
#: posted to Instagram, a crawler, someone holding refresh — walks the box
#: into swap and then into the OOM killer, and what dies is not "some
#: requests": it is the process, taking every signed-in session with it,
#: and often sshd's ability to get you back in to fix it.
#:
#: A bounded pool converts that into the failure everybody would choose:
#: a few callers get a 503 with a Retry-After, and everyone already being
#: served finishes normally. 64 is generous for this workload — Caddy
#: serves every static file, so the only things reaching Python are API
#: calls, and each is a sqlite read measured in milliseconds.
MAX_INFLIGHT = max(4, int(os.environ.get("QB_MAX_INFLIGHT", "") or 64))

def _busy_response() -> bytes:
    """The 503, assembled so the length is COUNTED rather than typed.

    The first draft typed 78 where the body was 81, and a Content-Length
    three short of the body is a client that reads a truncated JSON
    document and, depending on the client, hangs waiting for the rest.
    A wrong number here would only ever be met under load — which is the
    one time nobody is reading logs.
    """
    body = (b'{"error":"The site is busy for a moment. Try that again in '
            b'a couple of seconds."}')
    head = (b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Retry-After: 2\r\n"
            b"Content-Type: application/json\r\n"
            b"Connection: close\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n")
    return head + body


_BUSY = _busy_response()


class BoundedHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that refuses rather than falls over.

    The semaphore is taken BEFORE the thread is created, which is the
    only place it helps — checking inside the handler means the thread
    already exists and the memory is already spent.

    `daemon_threads` is inherited as True, so a shutdown does not wait on
    in-flight requests. Combined with the ceiling, a restart during a
    burst takes a second rather than a minute.
    """

    #: A listen backlog deep enough that a spike queues in the kernel
    #: instead of being refused at the TCP level, which browsers surface
    #: as "cannot connect" rather than as a retryable error.
    request_queue_size = 128

    #: A SLOT IS A CONNECTION, NOT A REQUEST, and the two are the same
    #: thing here only because `Handler` speaks HTTP/1.0 — the
    #: BaseHTTPRequestHandler default — so every connection closes after
    #: one response.
    #:
    #: Setting `protocol_version = "HTTP/1.1"` on the handler would turn
    #: keep-alive on, and then Caddy's idle upstream connections would sit
    #: in these slots doing nothing. Enough of them and the site refuses
    #: everybody while completely idle, which is a failure that would take
    #: a long evening to understand. tests/test_load_shedding.py fails if
    #: the two are ever changed apart.

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._slots = threading.Semaphore(MAX_INFLIGHT)
        self.shed = 0

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shed += 1
            try:
                request.sendall(_BUSY)
            except Exception:                                # noqa: BLE001
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:                                    # noqa: BLE001
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def seal_on_boot() -> None:
    """Redact every board on the public path, before anything is served.

    CALLED FROM BOTH ENTRYPOINTS, and that is the whole reason it is a
    function. It lived inline in `server.main()` for a day — which is dev
    only. Production runs `launch.py`, which builds its own
    ThreadingHTTPServer around the same Handler and never calls
    `server.main()`, so the seal never fired on the one machine it
    existed for. Found by reading the systemd unit rather than the code.

    WHY IT HAS TO HAPPEN AT BOOT. Redaction happens inside `publish()`,
    so turning QB_PAYWALL on changes what the NEXT build writes and
    touches nothing already on disk. Every board written before the flag
    went on stays whole and public, and in production Caddy serves those
    files straight off disk without the app ever seeing the request —
    there is no later place to catch it. `launch.py --seal` has always
    fixed it, and depending on an operator to remember a command is not a
    paywall. A restart is the one thing that reliably happens on every
    deploy, including the one that turns the flag on.

    NON-FATAL BY DESIGN. A seal that throws must not stop the site
    booting: refusing to start turns a redaction problem into an outage.
    It says so loudly instead, and `--todo` reports the same thing.
    """
    try:
        from engine import gate as _gate
        if not _gate.enabled():
            return
        res = _gate.seal(web_data=WEB / "data", verbose=False)
        n = len(res.get("sealed") or [])
        if n:
            print(f"Paywall ON — sealed {n} board(s) on the public path "
                  "at startup.")
        left = _gate.unsealed(web_data=WEB / "data")
        if left:
            rows = sum(r["rows"] for r in left)
            print(f"  WARNING: {len(left)} board(s) still carry {rows} "
                  "paid row(s) after sealing. Anyone can read them. "
                  "Run: python3 launch.py --seal")
    except Exception as exc:                                 # noqa: BLE001
        print(f"  WARNING: could not seal the public boards at startup: "
              f"{exc}\n  Run `python3 launch.py --seal` and check "
              "`--todo` before letting anyone in.")


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

    seal_on_boot()

    server = BoundedHTTPServer((bind, port), Handler)
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
