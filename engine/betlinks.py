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


def _rests(row: dict, sport: str, evs: list, mkeys: dict | None) -> list:
    """[(event, outcome key without the book)] for this bet: every market key
    that prices it (main line, ladder, Yes/No) at its line, on each event it
    could be. Empty for a row this cannot read."""
    market = str(row.get("market") or "").lower()
    pt = point(row.get("line"))
    game_row = (str(row.get("kind") or "") == "game"
                or str(row.get("bet_type") or "").lower() in GAME_MARKET or market in GAME_MARKET)
    out: list = []
    if row.get("player") and market and not game_row:
        mkeys = mkeys if mkeys is not None else _market_keys(sport)
        who, side = norm(row.get("player")), norm(row.get("side"))
        for ev in evs:
            for mk in mkeys.get(market, []):
                for p in (pt, ""):
                    out.append((ev, "|".join((mk, who, side, p))))
        return out
    mk = GAME_MARKET.get(str(row.get("bet_type") or market).lower())
    if not mk:
        return out
    names = _names_for(row.get("team"), sport)
    for ev in evs:
        if mk == "totals":
            game = f"{norm(ev.get('away'))}@{norm(ev.get('home'))}"
            out.append((ev, "|".join(("totals", game, norm(row.get("side")), pt))))
            continue
        for api_team in (ev.get("home"), ev.get("away")):
            if _same_team(api_team, names):
                out.append((ev, "|".join((mk, norm(api_team), "", "" if mk == "h2h" else pt))))
    return out


def _rest_index(ev: dict) -> dict:
    """{outcome key without the book: {book: url}}, built once per event."""
    idx = ev.get("_rest")
    if idx is None:
        idx = {}
        for k, url in (ev.get("slip") or {}).items():
            bk, _, rest = k.partition("|")
            idx.setdefault(rest, {}).setdefault(bk, url)
        ev["_rest"] = idx
    return idx


def _title(bk: str) -> str:
    from .sources.oddsapi import BOOK_TITLES
    return BOOK_TITLES.get(bk, bk)


def _prices(row: dict) -> dict:
    """{book title (lower): this bet's price there} off the row's own ladder."""
    side_key = "under_odds" if str(row.get("side") or "").upper() in ("UNDER", "NO") else "over_odds"
    ln = point(row.get("line"))
    out = {}
    for q in row.get("all_lines") or []:
        if isinstance(q, dict) and point(q.get("line")) == ln and q.get(side_key) not in (None, ""):
            out.setdefault(str(q.get("book") or "").lower(), q.get(side_key))
    if row.get("book") and row.get("odds") not in (None, ""):
        out[str(row["book"]).lower()] = row["odds"]
    return out


def links_for(row: dict, sport: str, events: dict, mkeys: dict | None = None) -> tuple:
    """([[book title, url, price or None], ...], event or None) for one pick.

    EVERY BOOK THAT HAS THIS EXACT BET (Ethan, 2026-10-06: "a box that shows
    all the different sports books and prediction markets we can link that
    bet to, so it doesn't just send someone to one specific sportsbook").
    The pick's own book first, then the best price; Pinnacle (no US
    action) never. The event comes back only when the row's own teams
    picked out exactly one game, for its game-page links."""
    from .sources.oddsapi import SHARP_BOOKS
    if not events:
        return [], None
    evs, matched = _row_events(row, sport, events)
    found: dict = {}
    for ev, rest in _rests(row, sport, evs, mkeys):
        for bk, url in (_rest_index(ev).get(rest) or {}).items():
            if bk not in SHARP_BOOKS and bk not in found:
                found[bk] = url
    prices = _prices(row)
    own = set(_books(row.get("book")))

    def _px(bk):
        v = prices.get(_title(bk).lower())
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    order = sorted(found, key=lambda bk: (bk not in own, -(_px(bk) if _px(bk) is not None else -10**6), _title(bk)))
    slips = [[_title(bk), found[bk], _px(bk)] for bk in order]
    return slips, (evs[0] if matched and len(evs) == 1 else None)


def link_for(row: dict, sport: str, events: dict, mkeys: dict | None = None) -> tuple:
    """(url, kind) — the first link `stamp` would put on this row, or ("", "")."""
    slips, ev = links_for(row, sport, events, mkeys)
    if slips:
        return slips[0][1], "slip"
    if ev is not None:
        for bk in _books(row.get("book")):
            url = (ev.get("page") or {}).get(bk)
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
    from .sources.oddsapi import SHARP_BOOKS
    st, mkeys = bet_state(env), _market_keys(sport)
    eid_of = {id(ev): eid for eid, ev in events.items()}
    rows: list = []
    _walk(payload, rows)
    pages: dict = {}
    n = 0
    ok = lambda u: str(u).lower().startswith("https://")             # noqa: E731
    for row in rows:
        slips, ev = links_for(row, sport, events, mkeys)
        slips = [[t, fill_state(u, st), px] for t, u, px in slips if ok(u)]
        if slips:
            row["bet_links"] = slips[:12]
            row["bet_link"], row["bet_link_kind"] = slips[0][1], "slip"
        if ev is not None:
            eid = eid_of.get(id(ev))
            if eid and eid not in pages:
                pages[eid] = [[_title(bk), fill_state(u, st)] for bk, u in sorted((ev.get("page") or {}).items())
                              if "|" not in bk and bk not in SHARP_BOOKS and ok(u)]
            if eid and pages.get(eid):
                row["bet_ev"] = eid
                if not slips:
                    for bk in _books(row.get("book")):
                        u = (ev.get("page") or {}).get(bk)
                        if u and ok(u):
                            row["bet_link"], row["bet_link_kind"] = fill_state(u, st), "page"
                            break
        if row.get("bet_link") or row.get("bet_ev"):
            n += 1
    if pages:
        # Each game's page at every book, once per board; a row points at
        # its game with `bet_ev` rather than carrying fifteen copies.
        payload["bet_pages"] = {k: v for k, v in pages.items() if v}
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
    # WHERE THE GAPS ARE (Ethan's first run, 2026-10-06: 87 of 1,607 rows
    # had a slip). Which books the API gave slip links for, which books
    # the unlinked rows name, and for a few unlinked rows at a book that
    # does give links, the keys we hold for that player — so a key that
    # does not line up shows itself.
    from collections import Counter
    by_book = Counter(k.split("|", 1)[0] for e in events.values() for k in (e.get("slip") or {}))
    pages = Counter(k for e in events.values() for k in (e.get("page") or {}) if "|" not in k)
    lines.append("  slip links banked, by book: " + (", ".join(f"{b} {n}" for b, n in by_book.most_common()) or "none"))
    lines.append("  game-page links banked, by book: " + (", ".join(f"{b} {n}" for b, n in pages.most_common()) or "none"))
    none = [r for r in rows if not r.get("bet_link")]
    lines.append("  unlinked rows, by the book they name: "
                 + ", ".join(f"{b} {n}" for b, n in Counter(str(r.get("book")) for r in none).most_common(10)))
    shown = 0
    for r in none:
        books = [b for b in _books(r.get("book")) if b in by_book]
        if not books or not r.get("player"):
            continue
        who = norm(r.get("player"))
        held = sorted(k for e in events.values() for k in (e.get("slip") or {})
                      if k.split("|")[0] in books and f"|{who}|" in k)[:4]
        lines.append(f"    unlinked at a linking book: {r.get('book')} · {r.get('player')} {r.get('market')} "
                     f"{r.get('side')} {r.get('line')} — keys held for him: {held or 'none'}")
        shown += 1
        if shown >= 6:
            break
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
