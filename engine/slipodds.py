"""A fresh price for an uploaded slip's own legs, when ours is old.

Ethan, 2026-10-14, "do 1-11", to "A fresh odds pull of a slip's own markets
when our price is old ... so you'd pick a daily cap": yes. The cap starts
small and is his to move (QB_SLIP_ODDS_DAILY_CAP on the box).

WHEN. Only on an upload (server `_ask_slip`): the Live tab's minute-by-
minute read of a saved slip and the box's slip watch keep the latest board
pull, as before. Only for a leg whose game has not started, in a league
the odds pull covers, whose price is older than OLD_S or that has no price
of ours at all, and whose game the free events list names.

WHAT. One event call per game, asking for the markets the slip's legs on
that game need and nothing else — the alternate ladder too where the
slip's number is not the main one. The API bills a credit per market per
game, so a four-leg ticket over two games is about three or four. The
prices come back in the shape the card already draws (`sliplive`), each
stamped with the moment it was pulled.

THE BUDGET. The same daily budget the board uses: every call is journalled
under its league (`oddsapi._classify` names it "slip_event"), where the
board's daily ceiling counts it. On top of that, its own cap,
QB_SLIP_ODDS_DAILY_CAP credits a day across every upload (DEFAULT_DAILY_CAP
when unset, 0 turns it off), and never into the month's reserve
(`oddsbudget.RESERVE`). A game it cannot afford keeps the board's price,
and the card says so.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import statistics
import sys
import time

from . import sliplive as SL

#: Credits a day, across every upload, when the box sets no cap.
DEFAULT_DAILY_CAP = 20
CAP_ENV = "QB_SLIP_ODDS_DAILY_CAP"
#: A price older than this is old enough to buy again.
OLD_S = 60 * 60
#: The ledger's name for these calls (`oddsapi._classify`).
KIND = "slip_event"
#: The leagues the odds pull prices. A fight leg reads the UFC card.
LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl")
GAME_KEYS = {"moneyline": "h2h", "spread": "spreads", "total": "totals"}
#: How far ahead an event may be and still be the leg's game.
HORIZON_S = 7 * 86400


def daily_cap() -> int:
    """QB_SLIP_ODDS_DAILY_CAP, or DEFAULT_DAILY_CAP; never below zero."""
    try:
        return max(0, int(os.environ.get(CAP_ENV, DEFAULT_DAILY_CAP)))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP


def spent_today(now: float | None = None, path=None) -> int:
    """Credits the fresh pulls have spent today, off the ledger every paid
    call writes, on the day the board's own ceiling counts."""
    from . import oddsbudget as OB
    return (OB.spent_today(now, path)
            - OB.spent_today(now, path, exclude=frozenset({KIND})))


def odds_keys(league: str, market: str, alternate: bool = False) -> list[str]:
    """The Odds API markets that price our ``market`` in ``league``: the
    main one (or the scorer's), and its ladder when ``alternate``."""
    from .sources.oddsapi import SPORT_CONFIG
    if market in GAME_KEYS:
        return [GAME_KEYS[market]]
    cfg = SPORT_CONFIG.get(league) or {}
    main = [k for k, m in {**(cfg.get("markets") or {}), **(cfg.get("scorers") or {})}.items()
            if m == market]
    ladder = [k for k, m in (cfg.get("alternates") or {}).items() if m == market] if alternate else []
    return main[:1] + ladder[:1]


def _norm(text) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower()).split())


def names_team(token, name, table: dict | None = None) -> bool:
    """Is ``token`` (a board's "KC" or "Ohio State") the feed's ``name``
    ("Kansas City Chiefs", "Ohio State Buckeyes")?"""
    t, n = _norm(token), _norm(name)
    if not t or not n:
        return False
    if str((table or {}).get(name) or "").lower() == str(token).strip().lower():
        return True
    words, mine = n.split(), t.split()
    return t == n or (len(t) >= 4 and words[:len(mine)] == mine)


def _teams(leg: dict) -> list[str]:
    out = [str(leg.get(k) or "").strip() for k in ("team", "opponent")]
    game = str(leg.get("game") or "")
    out += [p.strip() for p in re.split(r"\s+(?:@|at|vs\.?|v)\s+", game) if p.strip()]
    seen = []
    for t in out:
        if t and t.lower() not in [s.lower() for s in seen]:
            seen.append(t)
    return seen


def find_event(events, teams: list[str], table: dict | None, now: float) -> dict | None:
    """The one upcoming event both of the leg's teams name (or, knowing one
    team, the one event it names); None when there is none or two."""
    hits = []
    for ev in events or []:
        try:
            start = _dt.datetime.fromisoformat(
                str(ev.get("commence_time") or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if not now < start <= now + HORIZON_S:
            continue
        sides = (ev.get("home_team") or "", ev.get("away_team") or "")
        named = {s for s in sides for t in teams if names_team(t, s, table)}
        if len(named) >= min(2, len(teams)) and named:
            hits.append((start, ev))
    return hits[0][1] if len(hits) == 1 else None


def _iso(ts: float) -> str:
    return (_dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat(timespec="seconds")
            .replace("+00:00", "Z"))


def _age(stamp, now: float) -> float | None:
    try:
        t = _dt.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return now - t.timestamp()


def _title(bm: dict) -> str:
    from .sources.oddsapi import BOOK_TITLES
    key = str(bm.get("key") or "")
    return BOOK_TITLES.get(key, str(bm.get("title") or key))


def prop_prices(leg: dict, payload: dict, league: str, as_of: str) -> dict | None:
    """The slip's prop at every book in the fresh payload, in `sliplive`'s
    shape: each book's main line and ladder for him, scorers at 0.5."""
    from .sources.oddsapi import SPORT_CONFIG
    market, want = leg.get("market"), SL._key(leg.get("player"))
    cfg = SPORT_CONFIG.get(league) or {}
    keys = set(odds_keys(league, market, alternate=True))
    ladders = set(cfg.get("alternates") or {})
    scorer = market in SL.SCORER_MARKETS
    quotes, mains = {}, []
    for bm in (payload or {}).get("bookmakers") or []:
        title = _title(bm)
        for mkt in bm.get("markets") or []:
            if mkt.get("key") not in keys:
                continue
            pairs: dict = {}
            for o in mkt.get("outcomes") or []:
                if SL._key(o.get("description")) != want or o.get("price") is None:
                    continue
                name = str(o.get("name") or "").lower()
                point = 0.5 if scorer else o.get("point")
                if point is None or name not in ("over", "under", "yes", "no"):
                    continue
                pair = pairs.setdefault(float(point), [0, 0])
                pair[0 if name in ("over", "yes") else 1] = int(o["price"])
            for point, (over, under) in pairs.items():
                quotes[(title.lower(), point)] = (point, title, over, under)
                if mkt.get("key") not in ladders:
                    mains.append(point)
    if not quotes:
        return None
    main = statistics.mode(mains) if mains else None
    entry = {"quotes": list(quotes.values()), "line": main, "side": "", "as_of": as_of}
    return SL.leg_prices(leg, {(want, market): entry}, None)


def game_prices(leg: dict, payload: dict, league: str, as_of: str) -> dict | None:
    """The slip's side or total at every book in the fresh payload, in the
    shape `sliplive._game_prices` gives a board's game card: each book's
    price at the slip's number best first, the market's chance with the
    margin out (the sharp book's pair, else the books' median), the other
    side's best price for a hedge."""
    from .odds import devig_two_way, is_sharp_book
    from .sources.oddsapi import SPORT_CONFIG
    market, key = leg.get("market"), GAME_KEYS.get(leg.get("market"))
    table = (SPORT_CONFIG.get(league) or {}).get("teams") or {}
    line = SL._num(leg.get("line"))
    mine, theirs, fairs, sharp = {}, {}, [], None
    for bm in (payload or {}).get("bookmakers") or []:
        title = _title(bm)
        for mkt in bm.get("markets") or []:
            if mkt.get("key") != key:
                continue
            outs = [o for o in mkt.get("outcomes") or [] if o.get("price") is not None]
            if market == "total":
                at = {str(o.get("name") or "").lower(): o for o in outs
                      if line is not None and abs(SL._num(o.get("point"), 1e9) - line) < 0.01}
                me = at.get(leg.get("side"))
                other = at.get("under" if leg.get("side") == "over" else "over")
            else:
                me = next((o for o in outs if names_team(leg.get("team"), o.get("name"), table)
                           and (market == "moneyline" or line is None
                                or abs(SL._num(o.get("point"), 1e9) - line) < 0.01)), None)
                other = next((o for o in outs if me is not None and o is not me
                              and (market == "moneyline" or abs(SL._num(o.get("point"), 1e9)
                                                                + SL._num(me.get("point"), 0)) < 0.01)), None)
            m, t = SL._odds((me or {}).get("price")), SL._odds((other or {}).get("price"))
            if m and t:
                f = devig_two_way(m, t)[0]
                if is_sharp_book(title):
                    sharp = f
                elif 0.0 < f < 1.0:
                    fairs.append(f)
            if is_sharp_book(title):
                continue
            if m and (title not in mine or SL._better(m, mine[title])):
                mine[title] = m
            if t and (title not in theirs or SL._better(t, theirs[title])):
                theirs[title] = t
    if not mine and not theirs:
        return None
    books = sorted(({"book": b, "odds": o} for b, o in mine.items()),
                   key=lambda x: (-SL._decimal(x["odds"]), x["book"]))
    fair = sharp if sharp is not None else (statistics.median(fairs) if fairs else None)
    out = {"books": books[:SL.MAX_BOOKS], "n": len(books),
           "fair": None if fair is None else round(fair, 4), "as_of": as_of, "any": bool(books)}
    if theirs:
        b, o = max(theirs.items(), key=lambda kv: (SL._decimal(kv[1]), kv[0]))
        out["other"] = {"book": b, "odds": o}
    if books:
        out["best"], out["book"] = books[0]["odds"], books[0]["book"]
        yours = SL._odds(leg.get("odds"))
        if yours:
            out["beats_yours"] = SL._better(books[0]["odds"], yours)
    return out


def _events(league: str):
    """The league's upcoming events, off the free list the board's pulls
    keep (`oddsapi.list_events`, cache first)."""
    from .sources import oddsapi
    return oddsapi.list_events(oddsapi.get_api_key(), sport=league, cache_only=True)


def _fetch(event_id: str, keys: list[str], league: str) -> dict:
    """One paid call: these markets on this game, billed and journalled
    under the slip lane. A second upload of the same game inside a minute
    reads the first one's answer for nothing."""
    from .sources import oddsapi
    payload, _quota = oddsapi.fetch_event_odds(event_id, oddsapi.get_api_key(), markets=keys,
                                               sport=league, ttl=60, lane=oddsapi.SLIP_LANE)
    return payload


def _affordable(cost: int) -> bool:
    """Would ``cost`` stay clear of the month's reserve?"""
    from . import oddsbudget as OB
    return OB.pool_remaining() - OB.RESERVE >= cost


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class FreshLive(SL.Live):
    """`sliplive.Live` that buys a fresh price for a leg whose own is old,
    once per upload, inside the cap. ``fetch``, ``events``, ``spent``,
    ``cap`` and ``affordable`` are the paid call, the events list, today's
    spend, the cap and the reserve check — the network and the ledger in
    production, fixtures in a test."""

    def __init__(self, indexes=None, fast_dir=None, now=None, fetch=None, events=None,
                 spent=None, cap=None, affordable=None):
        super().__init__(indexes, fast_dir, now)
        self.fetch = fetch or _fetch
        self.events = events or _events
        self.spent = spent if spent is not None else spent_today
        self.cap = daily_cap() if cap is None else int(cap)
        self.affordable = affordable or _affordable
        self.fresh: dict = {}

    def _wants(self, leg: dict, boards: dict, now: float):
        """``(league, keys, teams)`` when this leg's price is worth buying
        again, else None."""
        league = str(leg.get("league") or leg.get("sport") or "")
        market = leg.get("market")
        if league not in LEAGUES or not (market in GAME_KEYS or odds_keys(league, market)):
            return None
        if (self.state(leg) or {}).get("state") in ("live", "final"):
            return None
        have = super().prices(leg, (boards or {}).get(league))
        age = _age((have or {}).get("as_of"), now)
        if have and have.get("books") and age is not None and age < OLD_S:
            return None
        main = (have or {}).get("main_line")
        if main is None:
            main = SL._num(((leg.get("row") or {}).get("line")))
        alt = (market not in GAME_KEYS and main is not None
               and abs(main - (SL._num(leg.get("line"), main))) >= 0.01)
        return league, odds_keys(league, market, alternate=alt), _teams(leg)

    def prepare(self, legs: list, boards: dict) -> None:
        from .sources.oddsapi import SPORT_CONFIG
        now = self.now or time.time()
        games: dict = {}
        listed: dict = {}
        for leg in legs or []:
            want = self._wants(leg, boards, now)
            if not want:
                continue
            league, keys, teams = want
            try:
                if league not in listed:
                    listed[league] = self.events(league) or []
            except Exception:                                  # noqa: BLE001
                listed[league] = []
            table = (SPORT_CONFIG.get(league) or {}).get("teams") or {}
            ev = find_event(listed[league], teams, table, now)
            if not ev:
                continue
            g = games.setdefault((league, ev.get("id")), {"keys": [], "legs": [], "start": ev.get("commence_time")})
            g["keys"] += [k for k in keys if k not in g["keys"]]
            g["legs"].append(leg)
        if not games:
            return
        spent, cap = self.spent(), self.cap
        stamp = _iso(now)
        got = held = credits = pulled = 0
        why = ""
        for (league, event_id), g in sorted(games.items(), key=lambda kv: str(kv[1]["start"] or "")):
            cost = len(g["keys"])
            if spent + credits + cost > cap:
                held += len(g["legs"])
                why = why or "cap"
                continue
            if not self.affordable(cost):
                held += len(g["legs"])
                why = why or "reserve"
                continue
            try:
                payload = self.fetch(event_id, g["keys"], league)
            except Exception as exc:                           # noqa: BLE001
                sys.stderr.write(f"  slip odds: {league} {event_id}: {type(exc).__name__}: {exc}\n")
                held += len(g["legs"])
                why = why or "error"
                continue
            credits += cost
            pulled += 1
            for leg in g["legs"]:
                make = game_prices if leg.get("market") in GAME_KEYS else prop_prices
                pr = make(leg, payload, league, stamp)
                if pr and pr.get("books"):
                    self.fresh[id(leg)] = dict(pr, fresh=True)
                    got += 1
        sys.stderr.write(f"  slip odds: {got} leg(s) priced fresh on {pulled} game(s), "
                         f"{credits} credit(s) ({spent + credits} of {cap} today)"
                         + (f"; {held} held ({why})" if held else "") + "\n")
        say = {"cap": "today's fresh pulls are used up",
               "reserve": "fresh pulls are paused to keep the month's odds credits",
               "error": "a fresh pull could not be made just now"}.get(why, "")
        note = f"Prices pulled just now for {_plural(got, 'leg')}." if got else ""
        if held:
            note = (note + " " if note else "") + \
                f"{_plural(held, 'leg')} kept our last pull's price: {say}."
        self.report = {"legs": got, "games": pulled, "credits": credits, "held": held,
                       "why": why, "as_of": stamp, "note": note} if (got or held) else None

    def prices(self, leg: dict, board: dict | None = None) -> dict | None:
        got = self.fresh.get(id(leg))
        return got if got is not None else super().prices(leg, board)
