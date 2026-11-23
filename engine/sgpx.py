"""SGPX: our best picks from different games in one ticket (step ACI, 22 November 2026).

Ethan, 22 November: "I also want to start doing same game parlay X's, as in like we take the top touchdown score for
one game and the top touchdown score for the other game, or like the best picks we have ... Like we could have done
Derrick Henry and Jahmyr Gibbs and St. Brown combined for a parlay today ... We need to do those for player props
and for touchdown props. Like we take the absolute best picks we have for the day and combine them together."

A book's SGPX ticket is several games' same-game parlays in one bet: Gibbs and St. Brown from the Lions' game and
Henry from the Ravens'. Ours:

  * BY KICKOFF SLOT. An NFL game's picks post once both clubs' inactives are in (engine/gameparlays.post_due), so a
    ticket across games can post only once every game on it has. Games that kick off within SLOT_SPAN_MIN of the
    first of them share a slot (a Sunday's 1 PM games; its 4:05 and 4:25 games), and a slot's tickets post once
    every game in it has posted, before the first of them starts. A slot of one game (a Thursday, Sunday or Monday
    night) has none.
  * FROM THE LEGS THE GAMES POSTED, at the chances they posted them: the player-prop tickets from each game's
    posted three-leg and two-leg parlays (its report's own picks, engine/gameparlays.from_report), the touchdown
    tickets from the scorers of its posted touchdown pairs (the ones its research made a case for). The games'
    reports chose the legs; this only combines them, the likeliest first.
  * PRICED AS A BOOK PRICES ONE. Legs from different games are unrelated, so their chances multiply; two legs from
    one game are one same-game piece, their chance and link read as that game's own parlays read them
    (gameparlays.ticket), and a pair that conflicts there makes no ticket here. At most MAX_PER_GAME legs a game,
    at least MIN_GAMES games a ticket. The price to take it at is our fair price and gameparlays.TAKE_EDGE, as
    every parlay's; a book's same-game cut is taken off the same-game pieces only.
  * PER_KIND OF EACH, POSTED ONCE. The likeliest tickets of SIZE legs, each leg on at most MAX_USES of them and no
    two sharing more than MAX_SHARED legs. Once posted, a slot's tickets are kept as posted (``path_for``, beside
    the private board) and never change; the Record grades them at the price each card says to take it at
    (engine/parlayledger.log_sgpx).

THE DAY'S TICKETS TOO (step ACM; Ethan, 22 November: "yes do day-wide SGPX too"). A day of two kickoff windows or
more (a Sunday: its 1 PM games, its 4:05 and 4:25 ones, its night game; Thanksgiving's three) also gets PER_KIND
tickets of each kind whose legs span two windows or more, posted once with the day's first window (every game in
it posted, before its first kickoff) and kept as posted. A later game has not posted by then, so its legs are the
ones it would post as built at that moment (gameparlays.HELD_KEY): picked before its inactives were out, and each
such ticket says so. They are journaled under their own kinds (DAY_SOURCES), so the record says whether those
early legs cost anything.

ONE BOOK FIRST (step ACM). An SGPX is one bet at one sportsbook, so among the tickets a window or a day could post
those one book prices at every leg's number rank first (gameparlays.book_ranker, as each game's own parlays rank),
and the card says the book and its prices (gameparlays.one_book).

COLLEGE FOOTBALL TOO (step ACO, 22 November). Ethan wants every league run the way the NFL runs, and a college
Saturday is the NFL's Sunday many times over: a noon window, a 3:30 one, a night one, a late one. College's games
post their picks 90 minutes before kickoff with no inactives to wait for (gameparlays.POST_WAIT_SPORTS is the
NFL's alone), so a college slot posts once every game in it has reached its post time, and a later game's legs on
a day ticket are the ones it would post as built at that moment: picked before that game posted its own, and each
such ticket and leg says so in those words (EARLY_WORDS). The tickets, their journal kinds, the Record, the Live
tab and Report Picks are the NFL's, unchanged.

Off without a deploy: ``sudo ./deploy/setenv.sh QB_SGPX off``.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import os
from pathlib import Path

SPORTS = ("nfl", "cfb")
KEY = "sgpx"
ENV = "QB_SGPX"
SLOT_SPAN_MIN = 45
SIZE = 3
PER_KIND = 3
MAX_PER_GAME = 2
MIN_GAMES = 2
MAX_USES = 2
MAX_SHARED = 1
#: The likeliest legs of each kind a slot's tickets are made from.
MAX_POOL = 14
KINDS = ("props", "tds")
#: Each kind's journal source (engine/parlayledger.log_sgpx) and its card's name.
SOURCES = {"props": "sgpx_props", "tds": "sgpx_td"}
#: The day's tickets (step ACM), each kind under its own source and name.
DAY_SOURCES = {"props": "sgpx_day_props", "tds": "sgpx_day_td"}
TITLES = {"props": "SGPX parlay", "tds": "SGPX touchdown parlay"}
DAY_TITLES = {"props": "SGPX day parlay", "tds": "SGPX day touchdown parlay"}
#: A window's or a day's opening line names its games up to this many, and counts them past it (step ACO).
LEAD_GAMES = 6
#: A day ticket's legs span this many kickoff windows or more.
DAY_MIN_WINDOWS = 2
HEADS = {"props": "Player props from different games", "tds": "Touchdown scorers from different games"}
KEEP_DAYS = 14
#: A day ticket's leg from a game that had not posted yet, in words (step ACO): an NFL game posts after both clubs'
#: inactives, a college game 90 minutes before kickoff with none to wait for.
EARLY_WORDS = {"nfl": "picked before its inactives"}
EARLY_DEFAULT = "picked before its game posted"
NOTE = ("Each SGPX ticket joins our strongest picks from different games in this kickoff window, the legs each "
        "game's own report posted. Legs from different games are counted as unrelated; two legs from one game are "
        "counted the way that game's own parlays count them. Tracked and graded on the record at the price each "
        "card says to take it at, staked at nothing.")


def early_words(sport: str) -> str:
    """How a day ticket's early leg says why it is early (EARLY_WORDS)."""
    return EARLY_WORDS.get(str(sport or "").lower(), EARLY_DEFAULT)


def _waits_for_inactives(sport: str) -> bool:
    """Does this league's game post after its inactives (gameparlays.POST_WAIT_SPORTS)?"""
    from .gameparlays import POST_WAIT_SPORTS
    return str(sport or "").lower() in POST_WAIT_SPORTS


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


def path_for(sport: str, where) -> Path:
    return Path(where) / f"sgpx_{sport}.json"


def _label(x: dict) -> str:
    return f"{x.get('away')}@{x.get('home')}"


def legs_of(x: dict, kind: str, sport: str = "nfl", game: str | None = None) -> list[dict]:
    """One game's posted legs of ``kind`` ("props": its three-leg and two-leg parlays' player props; "tds": its
    touchdown pairs' scorers), each once, each with its game (``sgpx_game``: ``game``, else the entry's own)."""
    from .gameparlays import GAME_LINE_MARKETS, SCORER_MARKETS, _leg_id
    scorer = set(SCORER_MARKETS.get(sport, ()))
    lists = ("threes", "twos") if kind == "props" else ("scorers",)
    seen, out = set(), []
    for k in lists:
        for t in x.get(k) or []:
            for leg in (t.get("legs") or []) if isinstance(t, dict) else []:
                if not isinstance(leg, dict) or leg.get("p") is None or not leg.get("player"):
                    continue
                market = str(leg.get("market") or "")
                if kind == "props" and (leg.get("_game_leg") or market in GAME_LINE_MARKETS or market in scorer):
                    continue
                if kind == "tds" and market not in scorer:
                    continue
                i = _leg_id(leg)
                if i in seen:
                    continue
                seen.add(i)
                out.append(dict(leg, sgpx_game=game or _label(x)))
    return out


def slots(games: list) -> list[dict]:
    """The board's games by kickoff slot: [{"key", "label", "start", "games"}], earliest first. A game joins the
    slot of the first game before it that kicks off no more than SLOT_SPAN_MIN earlier."""
    from .gameparlays import _et_clock, game_start
    timed = sorted(((s, x) for x in games if isinstance(x, dict) and (s := game_start(x)) is not None),
                   key=lambda p: p[0])
    out: list = []
    for start, x in timed:
        if out and (start - out[-1]["start"]).total_seconds() <= SLOT_SPAN_MIN * 60:
            out[-1]["games"].append(x)
        else:
            out.append({"start": start, "games": [x]})
    for s in out:
        s["key"] = s["start"].strftime("%Y-%m-%dT%H:%MZ")
        s["label"] = _et_clock(s["start"])
    return out


def ticket(sport: str, legs: list[dict], by_game: dict, memo: dict | None = None) -> dict | None:
    """One SGPX ticket of ``legs`` (each with its ``sgpx_game``), or None: fewer than MIN_GAMES games, more than
    MAX_PER_GAME legs of one game, or a same-game pair that conflicts (gameparlays.ticket). ``by_game``: each
    game's board entry by "AWAY@HOME", for the same-game pieces' links."""
    from . import parlays as P
    from .gameparlays import TAKE_EDGE, _dec, _price_words
    from .gameparlays import ticket as same_game
    from .twoleg import american
    pieces: dict = {}
    for leg in legs:
        pieces.setdefault(leg.get("sgpx_game") or "", []).append(leg)
    if len(pieces) < MIN_GAMES or max(len(v) for v in pieces.values()) > MAX_PER_GAME:
        return None
    joint, links, best = 1.0, [], 1.0
    for game, piece in pieces.items():
        if len(piece) == 1:
            joint *= float(piece[0]["p"])
        else:
            t = same_game(sport, piece, by_game.get(game), memo)
            if not t:
                return None
            joint *= float(t["joint"])
            links += list(t.get("links") or [])
        decs = [_dec(leg.get("odds")) for leg in piece]
        if best is None or not all(decs):
            best = None
            continue
        made = 1.0
        for d in decs:
            made *= d
        # A book's same-game cut, at its kindest, on a same-game piece only (parlays.BEST_CASE_SGP_TAX).
        best *= made * (1.0 - P.BEST_CASE_SGP_TAX.get(len(piece), 0.12)) if len(piece) > 1 else made
    if joint <= 0:
        return None
    indep = 1.0
    for leg in legs:
        indep *= float(leg["p"])
    decs = [_dec(leg.get("odds")) for leg in legs]
    naive = None
    if all(decs):
        naive = 1.0
        for d in decs:
            naive *= d
    fair = 1.0 / joint
    take = fair * (1.0 + TAKE_EDGE)
    caveats = []
    for leg in legs:
        st = str(leg.get("injury_status") or leg.get("own_status") or "").upper()
        if st in ("QUESTIONABLE", "GTD", "DAY-TO-DAY"):
            caveats.append(f"{leg.get('player')} is listed questionable — confirm they play before you bet it")
    held = [leg for leg in legs if leg.get("p_own") is not None]
    if held:
        caveats.append("Each leg counts at the lower of our chance and the book's: " + "; ".join(
            f"{leg.get('player')} {round(100 * float(leg['p']))}% (ours {round(100 * float(leg['p_own']))}%)"
            for leg in held))
    playable = None
    if best is not None:
        playable = best >= take
        if not playable:
            caveats.append(f"At best a book pays about {_price_words(best)} for these legs once it takes its "
                           f"same-game cut, short of the {_price_words(take)} this needs — pass, or play the legs "
                           f"as singles, unless your book pays {_price_words(take)} or better")
    return {"legs": legs, "games": sorted(pieces), "joint": round(joint, 4), "independent": round(indep, 4),
            "fair": american(fair), "fair_words": _price_words(fair),
            "take": american(take), "take_words": _price_words(take),
            "naive": american(naive) if naive else None, "naive_words": _price_words(naive) if naive else "",
            "naive_dec": round(naive, 4) if naive else None, "take_dec": round(take, 4),
            "ev_at_naive": round(joint * naive - 1.0, 4) if naive else None,
            "links": links, "caveats": caveats, "playable": playable, "staked": False, "stake_units": 0.0}


def choose(tickets: list[dict], n: int = PER_KIND, rank=None) -> list[dict]:
    """The likeliest ``n``, each leg on at most MAX_USES of them and no two sharing more than MAX_SHARED legs;
    ``rank`` (gameparlays.book_ranker) puts the tickets one book prices whole first."""
    from .gameparlays import _leg_id
    br = rank or (lambda t: 0)
    chosen, ids, uses = [], [], {}
    for t in sorted(tickets, key=lambda t: (br(t), -float(t["joint"]), -(t.get("ev_at_naive") or -9.0),
                                            [str(_leg_id(leg)) for leg in t["legs"]])):
        mine = {_leg_id(leg) for leg in t["legs"]}
        if any(uses.get(i, 0) >= MAX_USES for i in mine) or any(len(mine & o) > MAX_SHARED for o in ids):
            continue
        chosen.append(t)
        ids.append(mine)
        for i in mine:
            uses[i] = uses.get(i, 0) + 1
        if len(chosen) >= n:
            break
    return chosen


def _books(result: dict):
    """(index, carried, rank) for the one-book check (gameparlays.quote_index, carried_picks, book_ranker);
    (None, None, None) when the board has no quotes."""
    try:
        from .gameparlays import book_ranker, carried_picks, quote_index
        index, carried = quote_index(result), carried_picks(result)
        return index, carried, book_ranker(index, carried)
    except Exception:                                        # noqa: BLE001 — no quotes, no rank: our chance alone
        return None, None, None


def _price_books(tickets: list, books) -> None:
    """Each chosen ticket's one book (gameparlays.one_book), where the quotes say."""
    index, carried, _rank = books or (None, None, None)
    if not index:
        return
    from .gameparlays import one_book
    for t in tickets:
        try:
            ob = one_book(t["legs"], index, carried)
        except Exception:                                    # noqa: BLE001
            ob = None
        if ob:
            t["one_book"] = ob


def build_slot(sport: str, s: dict, board_games: list, memo: dict | None = None, books=None) -> dict:
    """A slot's tickets of each kind (KINDS), from its games' posted legs."""
    by_game = {_label(g): g for g in board_games or [] if isinstance(g, dict)}
    memo = {} if memo is None else memo
    rank = (books or (None, None, None))[2]
    out = {"key": s["key"], "label": s["label"], "games": [_label(x) for x in s["games"]]}
    for kind in KINDS:
        pool = [leg for x in s["games"] for leg in legs_of(x, kind, sport)]
        pool = sorted(pool, key=lambda leg: -float(leg["p"]))[:MAX_POOL]
        made = [t for c in itertools.combinations(pool, SIZE) if (t := ticket(sport, list(c), by_game, memo))]
        out[kind] = choose(made, rank=rank)
        _price_books(out[kind], books)
    return out


def _et_day(start) -> str:
    from zoneinfo import ZoneInfo
    return start.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def days(ss: list) -> list:
    """The slots by Eastern day: [{"key": "day:YYYY-MM-DD", "label", "slots", "games", "start"}], a day only where
    it has DAY_MIN_WINDOWS slots or more."""
    by: dict = {}
    for s in ss:
        by.setdefault(_et_day(s["start"]), []).append(s)
    out = []
    for day, mine in sorted(by.items()):
        if len(mine) < DAY_MIN_WINDOWS:
            continue
        first = mine[0]["start"]
        from zoneinfo import ZoneInfo
        out.append({"key": f"day:{day}", "label": first.astimezone(ZoneInfo("America/New_York")).strftime("%A"),
                    "slots": mine, "games": [x for s in mine for x in s["games"]], "start": first})
    return out


def build_day(sport: str, d: dict, result: dict, memo: dict | None = None, books=None) -> dict:
    """A day's tickets of each kind: legs across DAY_MIN_WINDOWS windows or more, the first window's posted legs
    and each later game's as built (gameparlays.HELD_KEY) or as posted; a later game's legs are marked
    ``sgpx_early`` and the ticket says it."""
    from .gameparlays import HELD_KEY
    by_game = {_label(g): g for g in result.get("games") or [] if isinstance(g, dict)}
    held = result.get(HELD_KEY) if isinstance(result.get(HELD_KEY), dict) else {}
    window = {_label(x): i for i, s in enumerate(d["slots"]) for x in s["games"]}
    memo = {} if memo is None else memo
    rank = (books or (None, None, None))[2]
    out = {"key": d["key"], "label": d["label"], "games": [_label(x) for x in d["games"]], "day": True,
           # Whether a later game's legs were picked before its inactives (the NFL) or before it posted (step ACO).
           **({} if _waits_for_inactives(sport) else {"inactives": False})}
    for kind in KINDS:
        pool = []
        for x in d["games"]:
            game = _label(x)
            src = x if _posted(x) else (held.get(game) or {})
            for leg in legs_of(src, kind, sport, game=game):
                if window.get(game, 0) > 0:
                    leg["sgpx_early"] = not _posted(x)
                    if leg["sgpx_early"]:
                        leg["sgpx_early_words"] = early_words(sport)
                pool.append(leg)
        pool = sorted(pool, key=lambda leg: -float(leg["p"]))[:MAX_POOL]
        made = []
        for c in itertools.combinations(pool, SIZE):
            if len({window.get(leg["sgpx_game"], 0) for leg in c}) < DAY_MIN_WINDOWS:
                continue
            t = ticket(sport, list(c), by_game, memo)
            if t:
                early = sorted({leg["sgpx_game"] for leg in t["legs"] if leg.get("sgpx_early")})
                if early:
                    later = (f"{'that game starts' if len(early) == 1 else 'those games start'} later in the day, "
                             f"and a leg on a player who sits is void")
                    t["caveats"].insert(0, (f"Picked before the inactives of {', '.join(early)}: {later}"
                                            if _waits_for_inactives(sport) else
                                            f"Picked before {', '.join(early)} posted "
                                            f"{'its' if len(early) == 1 else 'their'} own picks: {later}"))
                made.append(t)
        out[kind] = choose(made, rank=rank)
        _price_books(out[kind], books)
    return out


def _posted(x: dict) -> bool:
    """A game that posted its picks: no post time still ahead of it (gameparlays.hold_until_post)."""
    return not x.get("post_at")


def _started(s: dict, now) -> bool:
    return now >= s["start"] or any(x.get("kept") for x in s["games"])


def read_kept(path) -> dict:
    """The slots posted so far, by slot key; {} when none or the file cannot be read."""
    try:
        kept = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return kept.get("slots") or {} if isinstance(kept, dict) else {}


def write_kept(path, kept: dict, now) -> None:
    """The posted slots, those older than KEEP_DAYS dropped. Never raises."""
    cut = (now - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"slots": {k: v for k, v in kept.items()
                                             if (k[4:14] if k.startswith("day:") else k[:10]) >= cut}}),
                       encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def attach(result: dict, sport: str, out=None, now=None) -> str:
    """``result["sgpx"]``: {"sport", "slots": [...], "note"} for each kickoff slot of the board's game parlays
    (engine/gameparlays) of MIN_GAMES games or more still to start: its posted tickets, kept as posted; or, before
    every game in it has posted, when they post (``post_note``). ``out`` is the board's public path: the posted
    slots are kept beside its private copy, and with no ``out`` nothing is kept. A line for the build log; never
    raises."""
    sp = str(sport or "").lower()
    if sp not in SPORTS or not on():
        result.pop(KEY, None)
        return ""
    try:
        gp = result.get("game_parlays") if isinstance(result.get("game_parlays"), dict) else {}
        games = [x for x in gp.get("games") or [] if isinstance(x, dict) and x.get("home") and x.get("away")]
        now = now or dt.datetime.now(dt.timezone.utc)
        path = None
        if out:
            from .gate import _full_dir_for
            path = path_for(sp, _full_dir_for(out))
        kept = read_kept(path) if path else {}
        memo: dict = {}
        books = _books(result)
        entries, made = [], 0
        ss = slots(games)
        # THE DAY'S TICKETS (step ACM), first: they post with the day's first window.
        for d in days(ss):
            if d["key"] in kept:
                entries.append(dict(kept[d["key"]], posted=True))
                continue
            first = d["slots"][0]
            if _started(first, now):
                continue
            if not all(_posted(x) for x in first["games"]):
                entries.append({"key": d["key"], "label": d["label"], "games": [_label(x) for x in d["games"]],
                                "day": True,
                                "post_note": (f"{d['label']}'s SGPX day parlays post once the games kicking off at "
                                              f"{first['label']} have posted their own picks, before the first of "
                                              f"them starts")})
                continue
            e = build_day(sp, d, result, memo, books)
            if any(e.get(k) for k in KINDS):
                e["posted_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                kept[d["key"]] = e
                made += 1
            entries.append(dict(e, posted=True))
        for s in ss:
            if s["key"] in kept:
                entries.append(dict(kept[s["key"]], posted=True))
                continue
            if len(s["games"]) < MIN_GAMES or _started(s, now):
                continue
            if not all(_posted(x) for x in s["games"]):
                entries.append({"key": s["key"], "label": s["label"], "games": [_label(x) for x in s["games"]],
                                "post_note": (f"These SGPX parlays post once all {len(s['games'])} games kicking "
                                              f"off at {s['label']} have posted their own picks, "
                                              + ("after their inactives, " if _waits_for_inactives(sp) else "")
                                              + "and before the first of them starts")})
                continue
            e = build_slot(sp, s, result.get("games") or [], memo, books)
            if any(e.get(k) for k in KINDS):
                e["posted_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                kept[s["key"]] = e
                made += 1
            entries.append(dict(e, posted=True))
        if made and path:
            write_kept(path, kept, now)
        # Each slot as a report draws it (`section`), for the Report Picks page's SGPX tab.
        for e in entries:
            sec = section([e])
            if sec:
                e["blocks"] = sec["blocks"]
        result[KEY] = {"sport": sp, "slots": entries, "note": NOTE, "early_words": early_words(sp)}
        n = {k: sum(len(e.get(k) or []) for e in entries) for k in KINDS}
        return (f"SGPX parlays: {n['props']} player-prop and {n['tds']} touchdown ticket(s) across "
                f"{sum(1 for e in entries if e.get('posted') and not e.get('day'))} kickoff slot(s)"
                + (" and the day" if any(e.get("posted") and e.get("day") for e in entries) else "")
                + (f", {made} posted now" if made else "")
                + (f", {sum(1 for e in entries if e.get('post_note'))} waiting" if any(e.get('post_note')
                                                                                      for e in entries) else ""))
    except Exception as exc:                                 # noqa: BLE001
        result[KEY] = {"sport": sp, "slots": [], "note": f"the SGPX parlays did not build: {exc}"}
        return f"⚠️  SGPX parlays skipped ({type(exc).__name__}: {exc})"
    finally:
        # The held games' legs are this build's working state (gameparlays.HELD_KEY), never the board's.
        from .gameparlays import HELD_KEY
        result.pop(HELD_KEY, None)


def card(t: dict, n: int, kind: str, day: bool = False) -> dict:
    """One SGPX ticket as a report and the Report Picks page draw it, the way a game's own parlay card reads
    (gameparlays.card): its name (a day ticket's, ``day``), its chance and prices, the one book that has every
    leg, and each leg in words with its game."""
    from .gameparlays import _odds_words, pick_words
    joint = float(t.get("joint") or 0)
    price = f"{joint:.0%} by our numbers · fair {t.get('fair_words')} · take it at {t.get('take_words')} or better"
    if t.get("naive_words"):
        price += f" · the legs' own prices multiplied pay {t['naive_words']}"
    legs = [{"pick": pick_words(leg), "game": leg.get("sgpx_game") or "", "player": leg.get("player"),
             **({"early": leg.get("sgpx_early_words") or EARLY_WORDS["nfl"]} if leg.get("sgpx_early") else {}),
             "team": leg.get("team"),
             "price": " ".join(x for x in (_odds_words(leg.get("odds")), leg.get("book") or "") if x),
             "chance": round(float(leg.get("p") or 0), 4), "why": list(leg.get("why") or []),
             **({"headshot": leg["headshot"]} if leg.get("headshot") else {})}
            for leg in t.get("legs") or []]
    ob = t.get("one_book") or {}
    return {"title": f"{(DAY_TITLES if day else TITLES).get(kind, 'SGPX parlay')} {n}", "price_line": price,
            "legs": legs,
            **({"one_book": ob["words"]} if ob.get("words") else {}), **({"one_book_gone": True} if ob.get("gone") else {}),
            "games": list(t.get("games") or []), "links": list(t.get("links") or []),
            "caveats": list(t.get("caveats") or []), "joint": joint, "fair": t.get("fair"),
            "take": t.get("take"), "take_dec": t.get("take_dec"), "bet_legs": list(t.get("legs") or [])}


def for_game(result: dict, game: str) -> list:
    """Every entry of ``result["sgpx"]`` a game ("AWAY@HOME") is in: its day's, then its window's."""
    sg = result.get(KEY) if isinstance(result.get(KEY), dict) else {}
    return [e for e in sg.get("slots") or [] if isinstance(e, dict) and game in (e.get("games") or [])]


def _entry_blocks(entry: dict) -> list:
    """One entry's blocks: when it posts, or its tickets of each kind under a line that says whose they are."""
    day = bool(entry.get("day"))
    if entry.get("post_note"):
        return [{"type": "p", "text": entry["post_note"] + "."}]
    blocks = []
    for kind in KINDS:
        cards = [card(t, i, kind, day) for i, t in enumerate(entry.get(kind) or [], 1)]
        if cards:
            blocks += [{"type": "h", "text": (f"{entry.get('label')}'s games: " if day else "") + HEADS[kind]},
                       {"type": "parlays", "kind": "sgpx", "items": cards}]
    if not blocks:
        return []
    # The games by name while they fit on a line; a college Saturday's dozens by their count (step ACO).
    gs = list(entry.get("games") or [])
    others = ", ".join(gs) if len(gs) <= LEAD_GAMES else f"{len(gs)} games"
    lead = (f"Our strongest picks across {entry.get('label')}'s kickoff windows ({others}), combined; posted "
            f"with the first of them, so a later game's legs were "
            + ("picked before its inactives were out." if entry.get("inactives", True)
               else "picked before that game posted its own.")
            if day else f"Our strongest picks from the games kicking off at {entry.get('label')} ({others}), "
                        f"combined across games.")
    return [{"type": "p", "text": lead}] + blocks


def section(entries) -> dict | None:
    """A game report's "SGPX parlays" section: each entry it is in (`for_game`), the day's first, each with its
    posted tickets or when they post. None for a game in none."""
    if isinstance(entries, dict):
        entries = [entries]
    blocks = []
    for e in entries or []:
        if isinstance(e, dict):
            blocks += _entry_blocks(e)
    if not blocks:
        return None
    if any(b.get("type") == "parlays" for b in blocks):
        blocks.append({"type": "note", "text": NOTE})
    return {"key": KEY, "title": "SGPX parlays", "blocks": blocks}
