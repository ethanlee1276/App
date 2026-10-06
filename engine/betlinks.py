"""Bet it: the sportsbook's own bet-slip link on every pick.

Ethan, 2026-10-06: "build the bet it button". A pick on the site names a
book and a price; the button opens that book with that bet already on the
slip, so taking a pick is one tap instead of a search through the book's
menus.

WHERE THE LINKS COME FROM. The Odds API returns them on the same call we
already pay for (`includeLinks=true`; billing is per market per region,
so asking costs no credits): a link on each bookmaker (the game's page),
each market, and each outcome (the bet slip). Some carry a `{state}`
placeholder for the state the reader bets in; it is filled with
QB_BET_STATE (default "mi", Michigan).

WHERE THEY ARE KEPT. Not in the odds cache. Those files are never pruned
(they are paid for), and the links would roughly double them. On every
fresh pull that asked for links, `bank` writes the links to a small
sidecar (data/cache/betlinks_*.json) and hands `oddsapi._request` the
body back WITHOUT them, so the paid cache stays the size it always was.
Sidecars older than three days are deleted here, and they are on the
maintenance prune list as well.

HOW A PICK GETS ITS LINK. `gate.publish` calls `stamp` on the six sports
boards just before writing them. Every pick row that names a book is
matched to the outcome at that book: player, market (main or alternate
ladder), side and line for a prop; team and line for a spread or a
moneyline; the game and the line for a total. A match puts `bet_link`
(and `bet_link_kind` "slip") on the row. No match at the outcome falls
back to that book's page for the game ("page"), which opens the right
game without pretending to have built the slip. No link at all leaves
the row as it was. The field rides inside the paid rows, so the paywall
strips it with them.

Off switch: QB_BET_LINKS=0 stops asking the API for links and stops
stamping.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

PREFIX = "betlinks_"
KEEP_S = 3 * 86400
#: The six sports boards a pick can be on, by published file name.
FILE_SPORT = {"recommendations.json": "nfl", "cfb.json": "cfb", "mlb_recommendations.json": "mlb",
              "nba.json": "nba", "wnba.json": "wnba", "nhl.json": "nhl"}
#: Keys under which no pick lives: skipped by the walk, for speed.
SKIP_KEYS = frozenset({"player_stats", "games", "logs", "all_lines", "recent_values", "comps",
                       "gate_census", "near_miss", "priced_out", "config", "counts", "injured_list"})
GAME_MARKET = {"moneyline": "h2h", "ml": "h2h", "h2h": "h2h", "spread": "spreads", "run_line": "spreads",
               "puck_line": "spreads", "spreads": "spreads", "total": "totals", "totals": "totals"}

_LOCK = threading.Lock()
_MEMO: dict = {}


# ─── switches ──────────────────────────────────────────────────────────────

def enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("QB_BET_LINKS", "1")).strip().lower() not in ("0", "false", "no", "off")


def bet_state(env=None) -> str:
    env = os.environ if env is None else env
    s = re.sub(r"[^a-z]", "", str(env.get("QB_BET_STATE", "mi")).lower())
    return s[:2] if len(s) >= 2 else "mi"


def _cache_dir() -> Path:
    from .sources.fetch import CACHE_DIR
    return CACHE_DIR


# ─── keys ──────────────────────────────────────────────────────────────────

def norm(s) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(str(s or ""))


def point(x) -> str:
    if x is None or x == "":
        return ""
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return ""


def key(book: str, market: str, who: str, side: str, pt: str) -> str:
    return "|".join((book, market, who, side, pt))


def fill_state(url: str, st: str) -> str:
    return str(url).replace("{state}", st).replace("{STATE}", st.upper())


# ─── banking at fetch time ─────────────────────────────────────────────────

def _events(payload) -> list:
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    return [payload] if isinstance(payload, dict) else []


def extract(payload) -> dict:
    """The links in one Odds API payload, per event:
    {event_id: {"t", "home", "away", "slip": {key: url}, "page": {book or book|market: url}}}."""
    out: dict = {}
    for ev in _events(payload):
        eid = str(ev.get("id") or "")
        home, away = str(ev.get("home_team") or ""), str(ev.get("away_team") or "")
        game = f"{norm(away)}@{norm(home)}"
        slip, page = {}, {}
        for bm in ev.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            bk = str(bm.get("key") or "")
            if bm.get("link"):
                page[bk] = str(bm["link"])
            for m in bm.get("markets") or []:
                if not isinstance(m, dict):
                    continue
                mk = str(m.get("key") or "")
                if m.get("link"):
                    page[f"{bk}|{mk}"] = str(m["link"])
                for o in m.get("outcomes") or []:
                    if not isinstance(o, dict) or not o.get("link"):
                        continue
                    if o.get("description"):                # a player prop: description is the player
                        who, side = norm(o["description"]), norm(o.get("name"))
                    elif mk.startswith("totals") or mk.startswith("alternate_totals"):
                        who, side = game, norm(o.get("name"))
                    else:                                   # h2h / spreads: the name is the team
                        who, side = norm(o.get("name")), ""
                    slip[key(bk, mk, who, side, point(o.get("point")))] = str(o["link"])
        if slip or page:
            out[eid] = {"t": str(ev.get("commence_time") or ""), "home": home, "away": away,
                        "slip": slip, "page": page}
    return out


def strip(payload):
    """The payload without its links, which is what the odds cache keeps."""
    for ev in _events(payload):
        for bm in ev.get("bookmakers") or []:
            if not isinstance(bm, dict):
                continue
            bm.pop("link", None)
            for m in bm.get("markets") or []:
                if not isinstance(m, dict):
                    continue
                m.pop("link", None)
                for o in m.get("outcomes") or []:
                    if isinstance(o, dict):
                        o.pop("link", None)
    return payload


def sport_of(cache_name: str) -> str:
    """odds_event_<sport>_<id>_<tag>.json / odds_board_<sport>[_tag].json → sport."""
    parts = Path(cache_name).stem.split("_")
    return parts[2] if len(parts) >= 3 and parts[0] == "odds" and parts[1] in ("event", "board") else ""


def sidecar_name(cache_name: str) -> str:
    return PREFIX + Path(cache_name).name[len("odds_"):]


def bank(body: str, cache_name: str, cache_dir: Path | None = None, now: float | None = None) -> str:
    """Move the links out of a fresh API body into their sidecar; return the body without them.
    Any failure hands the body back untouched: a link is never worth a fetch."""
    try:
        payload = json.loads(body)
    except ValueError:
        return body
    if not sport_of(cache_name):
        return body
    try:
        found = extract(payload)
    except (TypeError, AttributeError, ValueError):
        return body
    if not found:
        return body
    root = Path(cache_dir) if cache_dir else _cache_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        side = root / sidecar_name(cache_name)
        tmp = side.with_name(side.name + ".tmp")
        tmp.write_text(json.dumps({"sport": sport_of(cache_name), "events": found}, separators=(",", ":")))
        os.replace(tmp, side)
        prune(root, now)
    except OSError:
        return body
    return json.dumps(strip(payload), separators=(",", ":"))


def prune(cache_dir: Path | None = None, now: float | None = None) -> int:
    root = Path(cache_dir) if cache_dir else _cache_dir()
    cutoff = (now or time.time()) - KEEP_S
    n = 0
    for f in root.glob(PREFIX + "*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


# ─── reading back ──────────────────────────────────────────────────────────

def load(sport: str, cache_dir: Path | None = None, now: float | None = None) -> dict:
    """Every banked event for this sport from the last three days, newest file winning."""
    root = Path(cache_dir) if cache_dir else _cache_dir()
    cutoff = (now or time.time()) - KEEP_S
    files = []
    for pat in (f"{PREFIX}event_{sport}_*.json", f"{PREFIX}board_{sport}.json", f"{PREFIX}board_{sport}_*.json"):
        for f in root.glob(pat):
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                files.append((st.st_mtime, st.st_size, f))
    events: dict = {}
    with _LOCK:
        for mtime, size, f in sorted(files, key=lambda t: t[0]):
            memo = _MEMO.get(str(f))
            if memo and memo[0] == mtime and memo[1] == size:
                got = memo[2]
            else:
                try:
                    got = (json.loads(f.read_text()) or {}).get("events") or {}
                except (OSError, ValueError):
                    continue
                _MEMO[str(f)] = (mtime, size, got)
            for eid, ev in got.items():
                have = events.setdefault(eid, {"t": ev.get("t"), "home": ev.get("home"), "away": ev.get("away"),
                                               "slip": {}, "page": {}})
                have["slip"].update(ev.get("slip") or {})
                have["page"].update(ev.get("page") or {})
        for k in [k for k in _MEMO if not Path(k).exists()]:
            _MEMO.pop(k, None)
    return events


def _books(title) -> list:
    from .sources.oddsapi import BOOK_TITLES
    t = str(title or "").strip()
    if not t:
        return []
    low = t.lower()
    keys = [k for k, v in BOOK_TITLES.items() if v.lower() == low or k == low]
    return keys or [re.sub(r"[^a-z0-9_]", "", low)]


def _market_keys(sport: str) -> dict:
    """Engine market → every Odds API key that prices it (main line, ladder, Yes/No)."""
    from .sources.oddsapi import SPORT_CONFIG
    cfg = SPORT_CONFIG.get(sport) or {}
    out: dict = {}
    for group in ("markets", "alternates", "scorers"):
        for api_key, eng in (cfg.get(group) or {}).items():
            out.setdefault(str(eng), []).append(api_key)
    return out


def _names_for(team: str, sport: str) -> set:
    """Every normalised name a row's team could appear under in the API."""
    from .sources.oddsapi import SPORT_CONFIG
    t = str(team or "").strip()
    if not t:
        return set()
    names = {norm(t)}
    for full, abbr in ((SPORT_CONFIG.get(sport) or {}).get("teams") or {}).items():
        if str(abbr).upper() == t.upper():
            names.add(norm(full))
    return {n for n in names if n}


def _same_team(api_name: str, names: set) -> bool:
    a = norm(api_name)
    return any(a == n or (len(n) >= 4 and (a.startswith(n + " ") or n.startswith(a + " "))) for n in names)


def _row_events(row: dict, sport: str, events: dict) -> tuple:
    """(the events this row's game could be, whether the row's teams picked them out).
    Every event, unmatched, when the row names no team the API knows."""
    home, away = _names_for(row.get("home"), sport), _names_for(row.get("away"), sport)
    if home and away:
        hit = [ev for ev in events.values() if _same_team(ev.get("home"), home) and _same_team(ev.get("away"), away)]
        if hit:
            return hit, True
    team, opp = _names_for(row.get("team"), sport), _names_for(row.get("opponent"), sport)
    if team and opp:
        both = [ev for ev in events.values()
                if {_same_team(ev.get("home"), team), _same_team(ev.get("away"), team)} == {True, False}
                and (_same_team(ev.get("home"), opp) or _same_team(ev.get("away"), opp))]
        if both:
            return both, True
    mine = team | opp
    if mine:
        hit = [ev for ev in events.values() if _same_team(ev.get("home"), mine) or _same_team(ev.get("away"), mine)]
        if hit:
            return hit, True
    return list(events.values()), False


def link_for(row: dict, sport: str, events: dict, mkeys: dict | None = None) -> tuple:
    """(url, kind) for one pick row, or ("", "")."""
    books = _books(row.get("book"))
    if not books or not events:
        return "", ""
    evs, matched = _row_events(row, sport, events)
    market = str(row.get("market") or "").lower()
    pt = point(row.get("line"))
    game_row = (str(row.get("kind") or "") == "game"
                or str(row.get("bet_type") or "").lower() in GAME_MARKET or market in GAME_MARKET)
    tries: list = []                                    # (event, slip key)
    if row.get("player") and market and not game_row:
        mkeys = mkeys if mkeys is not None else _market_keys(sport)
        who, side = norm(row.get("player")), norm(row.get("side"))
        for ev in evs:
            for bk in books:
                for mk in mkeys.get(market, []):
                    for p in (pt, ""):
                        tries.append((ev, key(bk, mk, who, side, p)))
    else:
        mk = GAME_MARKET.get(str(row.get("bet_type") or market).lower())
        if not mk:
            return "", ""
        for ev in evs:
            game = f"{norm(ev.get('away'))}@{norm(ev.get('home'))}"
            for bk in books:
                if mk == "totals":
                    tries.append((ev, key(bk, "totals", game, norm(row.get("side")), pt)))
                    continue
                names = _names_for(row.get("team"), sport)
                for api_team in (ev.get("home"), ev.get("away")):
                    if _same_team(api_team, names):
                        tries.append((ev, key(bk, mk, norm(api_team), "", "" if mk == "h2h" else pt)))
    for ev, k in tries:
        url = (ev.get("slip") or {}).get(k)
        if url:
            return url, "slip"
    # No outcome link: the book's page for the game, but only when the
    # row's own teams picked out exactly one game. A page for the wrong
    # game is worse than no button.
    if matched and len(evs) == 1:
        for bk in books:
            url = (evs[0].get("page") or {}).get(bk)
            if url:
                return url, "page"
    return "", ""


def _pick_like(d: dict) -> bool:
    if not isinstance(d.get("book"), str) or not d.get("book") or d.get("odds") in (None, ""):
        return False
    if d.get("player") and d.get("market") and d.get("side"):
        return True
    return str(d.get("bet_type") or d.get("market") or "").lower() in GAME_MARKET


def _walk(node, out: list, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, dict):
        if _pick_like(node):
            out.append(node)
        for k, v in node.items():
            if k not in SKIP_KEYS and isinstance(v, (dict, list)):
                _walk(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, (dict, list)):
                _walk(v, out, depth + 1)


def stamp(payload, name: str = "", env=None, cache_dir: Path | None = None, now: float | None = None) -> int:
    """Put `bet_link` on every pick row of a sports board that a banked link matches. Returns how many."""
    if not isinstance(payload, dict) or not enabled(env):
        return 0
    sport = FILE_SPORT.get(Path(str(name or "")).name)
    if not sport:
        return 0
    events = load(sport, cache_dir, now)
    if not events:
        return 0
    st, mkeys = bet_state(env), _market_keys(sport)
    rows: list = []
    _walk(payload, rows)
    n = 0
    for row in rows:
        url, kind = link_for(row, sport, events, mkeys)
        if url and url.lower().startswith("https://"):
            row["bet_link"], row["bet_link_kind"] = fill_state(url, st), kind
            n += 1
    return n


def report(sport: str = "nfl") -> list[str]:
    """For the box: how many links are banked and how many picks on the board carry one."""
    from . import gate
    events = load(sport)
    slips = sum(len(e.get("slip") or {}) for e in events.values())
    lines = [f"bet links: {sport}: {len(events)} game(s) banked, {slips:,} bet-slip link(s), "
             f"state {bet_state()}, {'on' if enabled() else 'OFF (QB_BET_LINKS=0)'}"]
    fname = next((f for f, s in FILE_SPORT.items() if s == sport), "")
    try:
        board = json.loads(Path(gate.board_source(Path(__file__).resolve().parents[1] / "web" / "data" / fname))
                           .read_text())
    except (OSError, ValueError):
        return lines + ["  no board on disk"]
    rows: list = []
    _walk(board, rows)
    have = [r for r in rows if r.get("bet_link")]
    slip = sum(1 for r in have if r.get("bet_link_kind") == "slip")
    lines.append(f"  board: {len(rows)} pick row(s) naming a book; {slip} with a bet-slip link, "
                 f"{len(have) - slip} with the game's page only, {len(rows) - len(have)} with none")
    for r in [r for r in rows if not r.get("bet_link")][:8]:
        lines.append(f"    none: {r.get('book')} · {r.get('player') or r.get('pick_label')} "
                     f"{r.get('market')} {r.get('side')} {r.get('line')}")
    return lines


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m engine.betlinks")
    ap.add_argument("sport", nargs="?", default="nfl")
    a = ap.parse_args(argv)
    for line in report(a.sport):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
