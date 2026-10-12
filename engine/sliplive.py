"""The parlay checker's live line: what every book shows for each leg right
now, at the slip's own number, and where the leg's game stands.

Ethan, 2026-10-12: "Obv make sure we are also pulling live line for the
picks that the user puts in the parlay checker".

WHAT "LIVE" MEANS HERE, AND WHAT IT COSTS — nothing new is bought.

* THE PRICE. Every book's quote at the slip's exact number, off the
  private board: each prop row's main line from every book (`all_lines`)
  and the alternate ladders (`alt_lines`), which every public copy and
  Ask's own copy drop (engine/served). That is the latest paid pull, and
  the pacer (engine/oddsbudget) re-prices the NFL through game day — its
  touchpoints, three hours out, at inactives and in the last half hour —
  so the leg says when its price was pulled rather than calling an hour-
  old number "live". A side or a total reads its own game card: the best
  price each side has, the book posting it, the margin taken out.
* THE GAME. State, score and clock from the twelve-second scoreboard
  (`web/data/live_{league}.json`, livescore_build) and each player's line
  from the game's deep file (`web/data/pbp/{league}_{event}.json`), both
  keyless reads the live loop already makes. A leg whose game is over is
  settled off the box score; one in progress says where it stands; an
  over already past its number has won, and an under past it has lost,
  whatever the clock says.

WHAT IT WILL NOT DO is put a number on a prop in the middle of a game. Our
projection assumes a full game; engine/livepicks refuses the same thing
for football for the same reason. A moneyline in play reads the live win
probability the scoreboard already carries (engine/livewp).

Pure assembly over data the caller hands in or files the live loop
writes; the paths are module-level so the suite points them at a temp
directory and never reads the box it runs on.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: Where livescore_build writes the scoreboard and the deep files.
FAST_DIR = ROOT / "web" / "data"
#: The leagues the twelve-second loop covers (livescore_build).
FAST_LEAGUES = ("nfl", "cfb", "nba", "wnba")
#: A scoreboard older than this is a stopped loop, not a quiet night — the
#: launcher rewrites it every three minutes even when nothing is on
#: (engine/livepicks.FAST_FRESH_S, the same bar).
FAST_FRESH_S = 15 * 60
#: Books listed per leg, best price first.
MAX_BOOKS = 8

#: A leg's number in the box score, by our market key: the stats summed.
#: Football reads `nflpreseason.BOX_MARKETS` (carries are rushing
#: attempts); an anytime touchdown counts rushing and receiving scores,
#: which is what the box carries. A market not here gets no progress.
BOX_STAT = {
    "pass_yds": ("pass_yds",), "pass_td": ("pass_td",), "pass_att": ("pass_att",),
    "pass_cmp": ("pass_cmp",), "pass_int": ("pass_int",), "rush_yds": ("rush_yds",),
    "rush_att": ("carries",), "rec_yds": ("rec_yds",), "receptions": ("receptions",),
    "rush_rec_yds": ("rush_yds", "rec_yds"), "pass_rush_yds": ("pass_yds", "rush_yds"),
    "anytime_td": ("rush_td", "rec_td"),
    "pts": ("pts",), "reb": ("reb",), "ast": ("ast",), "fg3m": ("fg3m",),
    "pra": ("pts", "reb", "ast"),
}

GAME_MARKETS = ("moneyline", "spread", "total")
SCORER_MARKETS = ("anytime_td", "anytime_goal")


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default


def _odds(v) -> int:
    o = int(_num(v, 0) or 0)
    return o if 100 <= abs(o) <= 100000 else 0


def _key(name) -> str:
    from .teammates import _norm
    return _norm(name)


def _iso(ts) -> str | None:
    """An epoch stamp as UTC ISO — the page ages it to the second."""
    t = _num(ts)
    if not t or t <= 0:
        return None
    return (_dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat(timespec="seconds")
            .replace("+00:00", "Z"))


def _sharp(book: str) -> bool:
    from .odds import is_sharp_book
    return is_sharp_book(book)


# ---- the price ---------------------------------------------------------------
def quote_index(board: dict) -> dict:
    """``{(player key, market): {"quotes": [(line, book, over, under)],
    "line", "side"}}`` — every book's number on every prop row, main line
    and ladder. Built once per write of a board (askbot.board_at), BEFORE
    Ask's copy drops the ladders; small, because it keeps the numbers and
    nothing else. A scorer row on the touchdown field adds its own quote."""
    out: dict = {}

    def entry(r):
        return out.setdefault((_key(r.get("player")), r.get("market")),
                              {"quotes": {}, "line": _num(r.get("line")),
                               "side": str(r.get("side") or "").lower()})

    for r in (board or {}).get("recommendations") or []:
        if not isinstance(r, dict) or not r.get("player") or not r.get("market"):
            continue
        e = entry(r)
        for q in (r.get("all_lines") or []) + (r.get("alt_lines") or []):
            if not isinstance(q, dict):
                continue
            book, line = str(q.get("book") or ""), _num(q.get("line"))
            if not book or book.lower() == "proxy" or line is None:
                continue
            over, under = _odds(q.get("over_odds")), _odds(q.get("under_odds"))
            if over or under:
                e["quotes"][(book.lower(), line)] = (line, book, over, under)
    for shelf in ("td_field", "longshot_watch", "long_shots"):
        for r in (board or {}).get(shelf) or []:
            if not isinstance(r, dict) or not r.get("player"):
                continue
            r = dict(r, market=r.get("market") or "anytime_td")
            if r["market"] not in SCORER_MARKETS or not _odds(r.get("odds")) or not r.get("book"):
                continue
            e = entry(r)
            e["quotes"].setdefault((str(r["book"]).lower(), 0.5), (0.5, str(r["book"]), _odds(r["odds"]), 0))
    for e in out.values():
        e["quotes"] = list(e["quotes"].values())
    return out


def _board_stamp(board: dict | None, game: bool) -> str | None:
    """When the board's prices were pulled: the props' pull, or the game
    lines' own clock where the build stamped one (nfl_build: the two pulls
    are hours apart on a cheap cycle)."""
    st = (board or {}).get("odds_status") or {}
    ts = (st.get("lines_priced_at") or st.get("priced_at")) if game else st.get("priced_at")
    return _iso(ts)


def _better(a: int, b: int) -> bool:
    """Is American price ``a`` better for the bettor than ``b``?"""
    from .slipgrade import to_decimal
    da, db = to_decimal(a), to_decimal(b)
    return bool(da and db and da > db + 1e-9)


def leg_prices(leg: dict, index: dict | None, board: dict | None = None) -> dict | None:
    """What the books show for this leg right now, at its own number:
    every book's price best first, the best and who has it, the market's
    chance with the margin taken out, where the main line sits now, and
    when it was pulled. None when we hold no price for it."""
    market = leg.get("market")
    if market in GAME_MARKETS:
        return _game_prices(leg, board)
    e = (index or {}).get((_key(leg.get("player")), market))
    if not e:
        return None
    side = leg.get("side")
    under = side in ("under", "no")
    line = 0.5 if market in SCORER_MARKETS else _num(leg.get("line"))
    if line is None:
        return None
    at = [q for q in e["quotes"] if abs(q[0] - line) < 0.01]
    from .odds import devig_two_way
    bettable, fairs = {}, []
    for _line, book, over, und in at:
        mine = und if under else over
        if over and und:
            f_over, f_under = devig_two_way(over, und)
            if 0.0 < f_over < 1.0:
                fairs.append(f_under if under else f_over)
        if mine and not _sharp(book):
            if book not in bettable or _better(mine, bettable[book]):
                bettable[book] = mine
    books = sorted(({"book": b, "odds": o} for b, o in bettable.items()),
                   key=lambda x: (-_decimal(x["odds"]), x["book"]))
    out = {"books": books[:MAX_BOOKS], "n": len(books),
           "fair": round(statistics.median(fairs), 4) if fairs else None,
           "as_of": _board_stamp(board, game=False), "any": bool(e["quotes"])}
    if books:
        out["best"], out["book"] = books[0]["odds"], books[0]["book"]
        yours = _odds(leg.get("odds"))
        if yours:
            out["beats_yours"] = _better(books[0]["odds"], yours)
    main = e.get("line")
    if main is not None and market not in SCORER_MARKETS and abs(main - line) >= 0.01:
        out["main_line"] = main
    return out


def _decimal(odds) -> float:
    from .slipgrade import to_decimal
    return to_decimal(odds) or 0.0


def _game_prices(leg: dict, board: dict | None) -> dict | None:
    """A side or a total off its own game card: the best price the leg's
    side has, the book posting it, and the card's chance with the margin
    out. A card only carries each side's best book (gamebets.attach_books),
    so it lists one."""
    r = leg.get("row") or {}
    if not r:
        return None
    market, team = leg.get("market"), leg.get("team") or ""
    picked = r.get("team") or r.get("pick") or ""
    if market == "total":
        same = str(r.get("side") or "").lower() == leg.get("side")
        odds = r.get("odds") if same else r.get("other_odds")
        book = r.get("over_book") if leg.get("side") == "over" else r.get("under_book")
        book = book or (r.get("book") if same else "")
    elif market == "moneyline":
        home = team == r.get("home")
        odds = r.get("home_odds") if home else r.get("away_odds")
        if not _odds(odds):
            odds = r.get("odds") if picked == team else None
        book = (r.get("home_book") if home else r.get("away_book")) or (r.get("book") if picked == team else "")
        same = picked == team
    else:
        same = picked == team
        odds = r.get("odds") if same else r.get("other_odds")
        book = (r.get("home_book") if team == r.get("home") else r.get("away_book")) or (r.get("book") if same else "")
    fair = _num(r.get("fair_prob"))
    odds = _odds(odds)
    if not odds and fair is None:
        return None
    out = {"books": [{"book": str(book or ""), "odds": odds}] if odds else [], "n": 1 if odds else 0,
           "fair": None if fair is None or r.get("has_market") is False else round(fair if same else 1 - fair, 4),
           "as_of": _board_stamp(board, game=True), "any": bool(odds)}
    if odds:
        out["best"], out["book"] = odds, str(book or "")
        yours = _odds(leg.get("odds"))
        if yours:
            out["beats_yours"] = _better(odds, yours)
    if r.get("price_stale"):
        out["stale"] = True
    return out


# ---- the game ----------------------------------------------------------------
_FILES: dict = {}


def _read(path: Path):
    """A JSON file, parsed once per write of it."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _FILES.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if len(_FILES) > 64:
        _FILES.clear()
    _FILES[str(path)] = (stamp, data)
    return data


def _fresh(doc: dict | None, path: Path, now: float) -> bool:
    try:
        age = now - os.stat(path).st_mtime
    except OSError:
        return False
    return isinstance(doc, dict) and age <= FAST_FRESH_S


def _teams(leg: dict) -> set:
    r = leg.get("row") or {}
    got = {r.get("home"), r.get("away")} - {None, ""}
    if not got:
        got = {leg.get("team") or r.get("team"), leg.get("opponent") or r.get("opponent")} - {None, ""}
    return {str(t) for t in got}


def _clock(live: dict) -> str:
    st = live.get("state")
    if st == "final":
        return "Final"
    if st != "live":
        return ""
    detail = str(live.get("detail") or "").strip()
    if detail:
        return detail
    period, clock = live.get("period"), str(live.get("clock") or "").strip()
    return " ".join(x for x in (f"Q{period}" if period else "", clock) if x)


def live_state(leg: dict, fast_dir=None, now: float | None = None) -> dict | None:
    """Where the leg's game stands, off the live loop's own files: the
    state, the score and the clock; for a prop, his number so far from the
    box score; and the leg's result once it has one — an over past its
    number has won and an under past it has lost, live or final. None when
    the league has no fast loop, the loop has stopped, or the game is not
    on it."""
    league = leg.get("league") or leg.get("sport") or ""
    if league not in FAST_LEAGUES:
        return None
    now = time.time() if now is None else now
    base = Path(fast_dir or FAST_DIR)
    path = base / f"live_{league}.json"
    doc = _read(path)
    if not _fresh(doc, path, now):
        return None
    teams = _teams(leg)
    if not teams:
        return None
    game = None
    for g in doc.get("games") or []:
        sides = {str(g.get("home") or ""), str(g.get("away") or "")}
        if teams <= sides or (len(teams) == 1 and teams & sides):
            game = g
            break
    if game is None:
        return None
    live = game.get("live") or {}
    state = str(live.get("state") or "")
    out = {"state": state, "home": game.get("home"), "away": game.get("away"),
           "home_score": live.get("home_score"), "away_score": live.get("away_score"),
           "clock": _clock(live), "start": live.get("start_time")}
    if state not in ("live", "final"):
        return out
    market = leg.get("market")
    if market in GAME_MARKETS:
        out.update(_game_result(leg, game, live))
        return out
    keys = BOX_STAT.get(market)
    if not keys:
        return out
    deep = _read(base / "pbp" / f"{league}_{game.get('event_id')}.json")
    stats = _player_stats(deep, leg.get("player"))
    if stats is None:
        out["note"] = "not in the box score yet" if state == "live" else "not in the box score"
        return out
    cur = sum(_num(stats.get(k), 0.0) for k in keys)
    out["current"] = round(cur, 1)
    line = 0.5 if market in SCORER_MARKETS else _num(leg.get("line"))
    if line is not None:
        out["result"] = _prop_result(leg.get("side"), line, cur, state)
    return out


def _player_stats(deep, player) -> dict | None:
    """His row of the deep file's box score, by name as the odds feed
    writes names (oddsapi.normalize_name: accents, suffixes, punctuation)."""
    if not isinstance(deep, dict) or not player:
        return None
    from .sources.oddsapi import normalize_name
    want = normalize_name(player)
    for p in deep.get("players") or []:
        if isinstance(p, dict) and normalize_name(p.get("player") or "") == want:
            return p.get("stats") or {}
    return None


def _prop_result(side, line: float, cur: float, state: str) -> str | None:
    over = side in ("over", "yes")
    if cur > line:
        return "won" if over else "lost"      # past the number: settled either way
    if state != "final":
        return None
    if abs(cur - line) < 1e-9:
        return "push"
    return "lost" if over else "won"


def _game_result(leg: dict, game: dict, live: dict) -> dict:
    hs, as_ = _num(live.get("home_score")), _num(live.get("away_score"))
    if hs is None or as_ is None:
        return {}
    market, state = leg.get("market"), live.get("state")
    home = (leg.get("team") or "") == game.get("home")
    out: dict = {}
    if market == "total":
        tot = hs + as_
        out["current"] = tot
        line = _num(leg.get("line"))
        if line is not None:
            out["result"] = _prop_result(leg.get("side"), line, tot, state)
        return out
    margin = (hs - as_) if home else (as_ - hs)
    out["margin"] = margin
    if market == "spread":
        line = _num(leg.get("line"), 0.0)
        cover = margin + line
        out["cover_by"] = cover
        if state == "final":
            out["result"] = "won" if cover > 0 else "lost" if cover < 0 else "push"
        return out
    if state == "final":
        out["result"] = "won" if margin > 0 else "lost" if margin < 0 else "push"
        return out
    wp = live.get("win_prob") or {}
    p = _num(wp.get("home_win_prob"))
    if p is not None:
        out["win_prob"] = round(p if home else 1.0 - p, 4)
    return out


class Live:
    """What the grader asks per leg: ``prices(leg, board)`` and
    ``state(leg)``. The server builds one from the price indexes Ask's
    loader keeps (askbot.prices_at) and the live loop's directory; a test
    builds one from fixtures."""

    def __init__(self, indexes: dict | None = None, fast_dir=None, now: float | None = None):
        self.indexes = indexes or {}
        self.fast_dir = fast_dir
        self.now = now
        # A board with no book's price on any prop (a pull that did not
        # land, a quota spent) says nothing about one prop being taken
        # down; its props get no price line rather than that alarm.
        self.priced = {lg: any(e.get("quotes") for e in (idx or {}).values())
                       for lg, idx in self.indexes.items()}

    def prices(self, leg: dict, board: dict | None = None) -> dict | None:
        league = leg.get("league") or ""
        if leg.get("market") not in GAME_MARKETS and not self.priced.get(league):
            return None
        try:
            return leg_prices(leg, self.indexes.get(league), board)
        except Exception:                                      # noqa: BLE001
            return None

    def state(self, leg: dict) -> dict | None:
        try:
            return live_state(leg, self.fast_dir, self.now)
        except Exception:                                      # noqa: BLE001
            return None
