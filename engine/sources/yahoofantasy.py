"""A Yahoo fantasy league, read through OAuth2 — no password, revocable.

Ethan, 2026-08-15, named Yahoo among the platforms he plays in.

WHY THIS ONE IS DIFFERENT FROM THE OTHER TWO. Sleeper is public and ESPN
is public when a league says so; neither needs anything of yours. Yahoo
has no public read at all — but it has the RIGHT kind of private one: a
documented OAuth2 flow where you approve access on Yahoo's own screen,
this app never sees a password, and you can revoke the token from your
Yahoo account page whenever you like. That is the opposite of pasting a
session cookie, and it is why Yahoo is built and a private ESPN league is
not.

WHAT YOU HAVE TO DO ONCE. Register an app at developer.yahoo.com (free),
which gives a client id and a client secret. Put them in `secrets.local`
beside the odds key:

    YAHOO_CLIENT_ID=...
    YAHOO_CLIENT_SECRET=...

Then approve the app once. The token that comes back is stored on this
machine at `data/yahoo_token.json` with owner-only permissions, is never
sent to the browser, and refreshes itself.

THE REDIRECT PROBLEM, AND WHY THE FLOW IS BUILT THE WAY IT IS. Yahoo
wants a redirect URI, and this site is served on a LAN address that has
no public HTTPS name — so the usual web flow does not fit. `oob`
("out of band") is supported for exactly this shape: Yahoo shows you a
code and you paste it back. `authorize_url` defaults to it, and a real
redirect URI can be passed instead if you ever have one.

YAHOO'S JSON IS UNUSUAL AND THE PARSER TREATS IT AS SUCH. Responses nest
lists inside dicts inside lists, with numeric string keys and `count`
fields sprinkled through, and the exact path to a value moves between
endpoints. So nothing here indexes a fixed path — `find_all` walks the
whole structure looking for a key. That is slower and much harder to
break, which is the right trade for a shape nobody here can pin down
against a live response.

AND THE SCORING IS MAPPED BY NAME, NOT BY ID. Yahoo hands back both:
`stat_categories` carries a display name for every stat id, and
`stat_modifiers` carries the points. Mapping "Passing Yards" is something
this file can be sure of; mapping stat id 4 is something it would be
guessing. Anything it cannot place comes back in `unmapped` and reaches
the page, for the same reason it does in the ESPN adapter.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH — probed, and the
proxy returns nothing for fantasysports.yahooapis.com. The pure parts
(the URLs, the request shapes, the walker, the name map) are unit-tested;
the network parts are thin and cache before they parse.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .fetch import CACHE_DIR, DataUnavailable

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
#: Out-of-band: Yahoo shows a code to paste rather than redirecting. The
#: only flow that fits a site served on a LAN address with no public name.
OOB = "oob"
#: Where the token lives. Owner-only, never sent to the browser, never
#: logged. Gitignored with the rest of `data/`.
TOKEN_PATH = Path("data") / "yahoo_token.json"
TTL = 600

#: Yahoo's stat NAMES → the scoring keys `fantasy_lineup` reads. Names
#: rather than ids on purpose — see the module docstring.
#:
#: BOTH SPELLINGS OF EVERY STAT ARE HERE, and that is not belt-and-braces.
#: Yahoo sends two names per stat and they are not the same word: stat 4
#: is `name` "Passing Yards" and `display_name` "Pass Yds". A map holding
#: only the long form matches nothing if the parser happens to read the
#: display name first — which is exactly what the first cut of this file
#: did. Yahoo has also spelled receiving stats as "Reception Yards" for
#: years while everyone else says "Receiving", so both are here too.
#: Matching is case-insensitive and drops punctuation.
STAT_NAMES = {
    "passing yards": "pass_yd", "pass yds": "pass_yd",
    "passing touchdowns": "pass_td", "pass td": "pass_td",
    "interceptions": "pass_int", "int": "pass_int",
    "rushing yards": "rush_yd", "rush yds": "rush_yd",
    "rushing touchdowns": "rush_td", "rush td": "rush_td",
    "reception yards": "rec_yd", "receiving yards": "rec_yd",
    "rec yds": "rec_yd",
    "reception touchdowns": "rec_td", "receiving touchdowns": "rec_td",
    "rec td": "rec_td",
    "receptions": "rec", "rec": "rec",
}
#: Yahoo's `position_type` for stats we knowingly do not project. The
#: lineup model scores offensive components only, so a kicker or team
#: defense rule is not a HOLE in the map — it is a limit we already know
#: about, and lumping the two together would bury a real gap under twenty
#: rules that were never going to be modelled.
UNMODELLED_TYPES = {"K", "DT", "DP"}
#: Yahoo's roster position codes → our slot names. "W/R/T" is Yahoo's
#: flex; "Q/W/R/T" is its superflex.
SLOT_NAMES = {
    "QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DEF",
    "W/R": "WRRB_FLEX", "W/T": "REC_FLEX", "W/R/T": "FLEX",
    "Q/W/R/T": "SUPER_FLEX", "BN": "BN", "IR": "IR",
}


# --- the flow ---------------------------------------------------------------
def credentials() -> tuple[str, str]:
    """``(client_id, client_secret)`` from the environment or secrets.local.

    Raises with the registration URL rather than returning blanks — an
    empty client id produces a Yahoo error page that says nothing about
    what to do next.
    """
    from .. import secrets as _s
    _s.load_local_secrets()
    cid = os.environ.get("YAHOO_CLIENT_ID", "").strip()
    sec = os.environ.get("YAHOO_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise DataUnavailable(
            "No Yahoo app credentials. Register a free app at "
            "developer.yahoo.com (any name, permission 'Fantasy Sports "
            "read'), then put YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in "
            "secrets.local. Nothing else is needed and no password is "
            "ever shared with this app.")
    return cid, sec


def authorize_url(client_id: str, redirect_uri: str = OOB) -> str:
    """The page you approve on. Yahoo's own screen, not ours."""
    q = urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "language": "en-us",
    })
    return f"{AUTH_URL}?{q}"


def _basic(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def token_request(code: str, client_id: str, client_secret: str,
                  redirect_uri: str = OOB) -> tuple[str, dict, bytes]:
    """``(url, headers, body)`` for the code→token exchange. Pure.

    Returned rather than sent so the shape can be tested without a
    network, and so the secret lives in exactly one place that is easy to
    check does not get logged.
    """
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        "code": str(code or "").strip(),
    }).encode()
    return TOKEN_URL, {
        "Authorization": _basic(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
    }, body


def refresh_request(refresh_token: str, client_id: str,
                    client_secret: str,
                    redirect_uri: str = OOB) -> tuple[str, dict, bytes]:
    """``(url, headers, body)`` for a refresh. Same shape, same discipline."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "redirect_uri": redirect_uri,
        "refresh_token": str(refresh_token or "").strip(),
    }).encode()
    return TOKEN_URL, {
        "Authorization": _basic(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
    }, body


def save_token(token: dict, path: str | Path | None = None) -> bool:
    """Store the token owner-only. Never returned to the browser.

    0600 before the write, not after: a token that exists world-readable
    for even a moment on a shared machine has already leaked.
    """
    f = Path(path or TOKEN_PATH)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(token or {}, fh)
        os.chmod(str(f), 0o600)
        return True
    except OSError:
        return False


def load_token(path: str | Path | None = None) -> dict:
    f = Path(path or TOKEN_PATH)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def connected(path: str | Path | None = None) -> bool:
    return bool((load_token(path) or {}).get("refresh_token"))


def _post(url: str, headers: dict, body: bytes, timeout: int = 30) -> dict:
    """POST a form and parse the JSON reply.

    NOTHING FROM `headers` EVER REACHES AN EXCEPTION MESSAGE. The client
    secret lives in the Authorization header, and an error string that
    carried it would end up in a log, a traceback, or a page. Only the
    server's own reply is quoted back.
    """
    req = urllib.request.Request(url, data=body, headers=dict(headers),
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            said = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str(said.get("error_description")
                         or said.get("error") or "")
        except Exception:                            # noqa: BLE001 - best effort
            detail = ""
        hint = ""
        if exc.code in (400, 401):
            hint = (" That is usually a code that was already used or has "
                    "expired — Yahoo's codes are single-use and short-lived, "
                    "so start the approval again — or a client id/secret "
                    "that does not match the app you approved.")
        raise DataUnavailable(
            f"Yahoo refused the token request (HTTP {exc.code})."
            f"{' ' + detail if detail else ''}{hint}", status=exc.code) from exc
    except Exception as exc:                         # noqa: BLE001
        raise DataUnavailable(f"Could not reach Yahoo's token endpoint: "
                              f"{exc}") from exc
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise DataUnavailable("Yahoo's token endpoint did not return JSON; "
                              "nothing was stored.") from exc


def _stamp(token: dict) -> dict:
    """Add an absolute expiry so a stored token can be judged later.

    Yahoo returns `expires_in` seconds, which is meaningless once written
    to disk. The minute of slack is so a token that expires mid-request
    is refreshed before the request rather than after it fails.
    """
    out = dict(token or {})
    try:
        out["expires_at"] = time.time() + float(out.get("expires_in") or 0) - 60
    except (TypeError, ValueError):
        out["expires_at"] = 0.0
    return out


def exchange_code(code: str, redirect_uri: str = OOB,
                  path: str | Path | None = None) -> dict:
    """Trade the pasted approval code for a token and store it.

    Returns only what is safe to show — never the tokens themselves. The
    browser is told THAT it worked, not the secret that makes it work.
    """
    cid, sec = credentials()
    url, headers, body = token_request(code, cid, sec, redirect_uri)
    token = _post(url, headers, body)
    if not token.get("access_token") or not token.get("refresh_token"):
        raise DataUnavailable(
            "Yahoo replied without a token. Nothing was stored. Check the "
            "app's permission includes Fantasy Sports read access.")
    if not save_token(_stamp(token), path):
        raise DataUnavailable(
            f"Got a Yahoo token but could not write {Path(path or TOKEN_PATH)} "
            f"— it is not stored, so nothing is connected.")
    return {"connected": True, "expires_in": int(token.get("expires_in") or 0)}


def access_token(path: str | Path | None = None) -> str:
    """A usable access token, refreshed first if this one has expired."""
    tok = load_token(path)
    if not tok.get("refresh_token"):
        raise DataUnavailable(
            "Yahoo is not connected on this machine. Approve it once from "
            "the Fantasy tab — Yahoo shows a code, you paste it back, and "
            "no password is ever shared with this app.")
    if tok.get("access_token") and float(tok.get("expires_at") or 0) > time.time():
        return str(tok["access_token"])
    cid, sec = credentials()
    url, headers, body = refresh_request(tok["refresh_token"], cid, sec)
    fresh = _post(url, headers, body)
    if not fresh.get("access_token"):
        raise DataUnavailable(
            "Yahoo would not refresh the stored token. If you revoked this "
            "app from your Yahoo account page, approve it again.")
    # Yahoo returns a new refresh token on most refreshes and omits it on
    # some; dropping the old one when it is omitted would disconnect the
    # app on the next expiry for no reason.
    merged = dict(tok)
    merged.update(fresh)
    save_token(_stamp(merged), path)
    return str(fresh["access_token"])


def _cache_name(path: str) -> str:
    return "yahoo_" + re.sub(r"[^A-Za-z0-9]+", "_", str(path))[:80] + ".json"


def api_get(path: str, ttl: int = TTL, token_path: str | Path | None = None,
            timeout: int = 30) -> dict:
    """A read from Yahoo's Fantasy API, cached to disk before it is parsed.

    A 401 means the access token died early; that is retried ONCE with a
    fresh one, and a second 401 is reported rather than looped on.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / _cache_name(path)
    if cache.exists() and (time.time() - cache.stat().st_mtime) < ttl:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            cache.unlink(missing_ok=True)

    url = f"{API_BASE}/{str(path).lstrip('/')}"
    url += ("&" if "?" in url else "?") + "format=json"
    last = None
    for attempt in (1, 2):
        tok = access_token(token_path)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 401 and attempt == 1:
                # Force a refresh on the next pass rather than trusting the
                # stored expiry, which Yahoo has been known to overstate.
                tok_file = load_token(token_path)
                tok_file["expires_at"] = 0.0
                save_token(tok_file, token_path)
                continue
            if exc.code in (401, 403):
                raise DataUnavailable(
                    "Yahoo refused this league for the connected account. "
                    "You can only read leagues you are actually in — check "
                    "the league key, and that it is the same Yahoo account "
                    "you approved.", status=exc.code) from exc
            if exc.code == 404:
                raise DataUnavailable(
                    f"Yahoo has no such resource: {path}. A league key looks "
                    f"like `461.l.1234567`, not a bare number.",
                    status=404) from exc
            raise DataUnavailable(f"Yahoo returned HTTP {exc.code} for "
                                  f"{path}.", status=exc.code) from exc
        except Exception as exc:                     # noqa: BLE001
            last = exc
            if cache.exists():
                try:
                    return json.loads(cache.read_text(encoding="utf-8"))
                except ValueError:
                    pass
            raise DataUnavailable(f"Could not reach Yahoo for {path}: "
                                  f"{exc}") from exc
        text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise DataUnavailable(
                f"Yahoo did not return JSON for {path} — got {len(text)} "
                f"byte(s). Nothing was cached.") from exc
        cache.write_text(text, encoding="utf-8")
        return data
    raise DataUnavailable(f"Yahoo read failed for {path}: {last}")


# --- Yahoo's JSON, walked rather than indexed -------------------------------
def find_all(node, key: str) -> list:
    """Every value stored under ``key`` anywhere in the structure.

    Yahoo nests lists inside dicts inside lists, with numeric string keys
    and `count` fields, and the exact path to a value differs between
    endpoints. Searching is slower and very much harder to break than a
    fixed path, which is the right trade for a shape that cannot be
    pinned down against a live response from here.
    """
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                out.append(v)
            out.extend(find_all(v, key))
    elif isinstance(node, list):
        for v in node:
            out.extend(find_all(v, key))
    return out


def find_first(node, key: str, default=None):
    got = find_all(node, key)
    return got[0] if got else default


def _clean(name: str) -> str:
    return "".join(c for c in str(name or "").lower()
                   if c.isalnum() or c == " ").strip()


def parse_scoring(payload: dict) -> dict:
    """``{"scoring", "unmapped", "not_modelled"}`` from a league's settings.

    Joins `stat_categories` (which names each stat id) to `stat_modifiers`
    (which prices them), then maps by NAME. A stat we cannot place comes
    back in `unmapped` rather than being dropped — a scoring rule silently
    ignored is a lineup silently wrong.

    THREE OUTPUTS, NOT TWO. Kicker and team-defense rules are separated
    from the ones we failed to read. Both are unapplied, but only one is a
    bug: this app does not project kickers, and saying "8 rules could not
    be mapped" when 8 of them are field-goal distances would hide a real
    miss on the ninth.
    """
    names: dict = {}
    for cat in find_all(payload, "stat_categories"):
        for st in find_all(cat, "stat"):
            sid = find_first(st, "stat_id")
            if sid is None:
                continue
            # BOTH names are kept. Yahoo's `name` and `display_name` are
            # different words ("Passing Yards" / "Pass Yds") and which one
            # a league's payload carries is not something this container
            # has been able to confirm against a live response.
            names[str(sid)] = {
                "name": str(find_first(st, "name") or ""),
                "display": str(find_first(st, "display_name") or ""),
                "type": str(find_first(st, "position_type") or "").upper(),
            }
    mods = []
    for mod in find_all(payload, "stat_modifiers"):
        for st in find_all(mod, "stat"):
            sid = find_first(st, "stat_id")
            val = find_first(st, "value")
            if sid is not None and val is not None:
                mods.append((str(sid), val))
    if not mods:
        raise DataUnavailable(
            "Yahoo payload carries no `stat_modifiers` — nothing was "
            "parsed. An empty scoring map would read as a league that "
            "scores nothing and produce a confident lineup of zeros.")
    scoring, unmapped, unmodelled = {}, [], []
    for sid, val in mods:
        try:
            pts = float(val)
        except (TypeError, ValueError):
            continue
        meta = names.get(sid) or {}
        label = meta.get("name") or meta.get("display") or ""
        key = None
        for cand in (meta.get("name"), meta.get("display")):
            key = key or STAT_NAMES.get(_clean(cand))
        row = {"stat_id": sid, "name": label or f"stat {sid}", "points": pts}
        if key:
            scoring[key] = pts
        elif meta.get("type") in UNMODELLED_TYPES:
            unmodelled.append(row)
        elif pts != 0.0:
            unmapped.append(row)
    return {"scoring": scoring, "unmapped": unmapped,
            "not_modelled": unmodelled}


def parse_slots(payload: dict) -> list[str]:
    """Roster positions expanded into the flat list the optimiser reads."""
    out = []
    found = False
    for block in find_all(payload, "roster_positions"):
        for rp in find_all(block, "roster_position"):
            pos = find_first(rp, "position")
            cnt = find_first(rp, "count", 1)
            if not pos:
                continue
            found = True
            slot = SLOT_NAMES.get(str(pos).upper())
            if not slot:
                continue                   # IDP and others we do not model
            try:
                n = int(cnt)
            except (TypeError, ValueError):
                n = 1
            out.extend([slot] * max(0, n))
    if not found:
        raise DataUnavailable(
            "Yahoo payload carries no `roster_positions`; the roster shape "
            "is unknown and guessing it would optimise a lineup for a "
            "league that does not exist.")
    return out


def parse_rosters(payload: dict) -> dict:
    """``{team name: [{player, position}]}`` from a teams+roster payload."""
    out: dict = {}
    teams = find_all(payload, "team")
    if not teams:
        raise DataUnavailable("Yahoo payload carries no `team` — nothing "
                              "was parsed.")
    for t in teams:
        # A team's `name` is a string; a PLAYER's `name` is a dict of
        # first/last/full, and players live inside the same team node. So
        # take the first STRING — `find_first` alone would hand back a dict
        # for any payload that ordered them the other way, and `str()` of
        # that is a team called "{'full': ...}".
        label = next((n for n in find_all(t, "name") if isinstance(n, str)
                      and n.strip()), "")
        if not label:
            continue
        rows = []
        for p in find_all(t, "player"):
            full = find_first(p, "full")
            pos = (find_first(p, "display_position")
                   or find_first(p, "primary_position") or "")
            pos = str(pos).upper().split(",")[0].strip()
            if full and pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
                rows.append({"player": str(full), "position": pos})
        # A team dict appears more than once across a nested payload; the
        # richest copy wins rather than the first, or a roster read from a
        # summary block would overwrite the real one with nothing.
        if str(label) not in out or len(rows) > len(out[str(label)]):
            out[str(label)] = rows
    return out


def my_team(payload: dict) -> str | None:
    """The connected account's own team label, or None.

    Yahoo flags it directly — `is_owned_by_current_login` — which is
    better than anything we could ask the user to type: no id to look up,
    and it cannot select somebody else's roster by accident. None is the
    honest answer when the flag is absent, and None is what stops the desk
    optimising a stranger's team.
    """
    for t in find_all(payload, "team"):
        flag = find_first(t, "is_owned_by_current_login")
        if str(flag) in ("1", "True", "true"):
            label = next((n for n in find_all(t, "name") if isinstance(n, str)
                          and n.strip()), "")
            if label:
                return label
    return None


def my_leagues(game_key: str = "nfl", ttl: int = TTL,
               token_path: str | Path | None = None) -> list[dict]:
    """Every NFL league the connected account is in.

    So the league key never has to be typed. Yahoo's keys look like
    `461.l.1234567` — a number nobody has memorised, and a wrong one is a
    404 rather than an obvious mistake.
    """
    key = re.sub(r"[^a-z0-9._]+", "", str(game_key or "nfl").lower()) or "nfl"
    data = api_get(f"users;use_login=1/games;game_keys={key}/leagues",
                   ttl=ttl, token_path=token_path)
    out, seen = [], set()
    for lg in find_all(data, "league"):
        lk = find_first(lg, "league_key")
        nm = next((n for n in find_all(lg, "name") if isinstance(n, str)
                   and n.strip()), "")
        if not lk or str(lk) in seen:
            continue
        seen.add(str(lk))
        out.append({"league_key": str(lk), "name": nm or str(lk),
                    "season": str(find_first(lg, "season") or "")})
    return out


def league(league_key: str, ttl: int = TTL,
           token_path: str | Path | None = None) -> dict:
    """Everything the league desk needs, in the shared adapter shape.

    Two reads because Yahoo splits them: the settings carry scoring and
    roster slots, the teams/roster endpoint carries who has whom. Matches
    what the Sleeper and ESPN paths already produce — ``{name, slots,
    scoring, rosters, unmapped}`` — so the desk never learns which
    platform it is talking to.
    """
    key = str(league_key or "").strip()
    if not re.fullmatch(r"[0-9]{1,6}\.l\.[0-9]{1,12}", key):
        raise DataUnavailable(
            f"{key or 'that'} is not a Yahoo league key. They look like "
            f"`461.l.1234567` — the number before `.l.` is Yahoo's id for "
            f"the season's game. Connect and the app will list yours.")
    settings = api_get(f"league/{key};out=settings", ttl=ttl,
                       token_path=token_path)
    teams = api_get(f"league/{key}/teams/roster", ttl=min(ttl, 300),
                    token_path=token_path)
    sc = parse_scoring(settings)
    name = next((n for n in find_all(settings, "name") if isinstance(n, str)
                 and n.strip()), "") or f"Yahoo league {key}"
    return {
        "platform": "yahoo",
        "name": name,
        "league_key": key,
        "season": str(find_first(settings, "season") or ""),
        "slots": parse_slots(settings),
        "scoring": sc["scoring"],
        "unmapped": sc["unmapped"],
        "not_modelled": sc["not_modelled"],
        "rosters": parse_rosters(teams),
        "mine": my_team(teams),
    }
