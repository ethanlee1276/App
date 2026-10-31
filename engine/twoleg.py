"""Two-leg parlays — the Parlays page, built from our own picks.

Ethan, 2026-10-31: "for the parlay picks, they will be two-leg parlays and
they will be picked from the most likely bet and the edge bets. And on the
parlay pages, it'll have a section for the edge bet parlays and most likely
bet parlays ... picks that correlate with each other or picks that just make
sense ... one pick on one team, one pick on the other. We can do same-game
parlay X's where it's two picks from different games ... so we can record
that data."

WHAT THE RECORD SAYS ABOUT IT (the public receipts, each day's picks paired
1st+2nd, 3rd+4th by our chance; `backtest` reruns it from the journal). A
two-leg parlay does to the money what its legs already do, about twice:

    Most Likely   singles  →  2-leg parlays
    NFL            −4.4%   →   −8.7%     (34% of parlays hit)
    college        −4.6%   →   −8.1%
    NBA            +4.9%   →  +10.6%     (43% hit)
    MLB            +0.5%   →   +3.4%
    NHL            −1.6%   →   −3.1%

So a parlay of picks that win more than their price pays wins about twice
as fast, and a parlay of picks that pay the juice loses about twice as fast.
That is why a parlay is staked only when BOTH legs are picks the stake rule
already stakes (engine/stakeplan: an Edge pick in a league whose Edge book
is staked and no longer than +130, a Most Likely pick in a league whose
Most Likely book has beaten the price). Every other parlay posts, is
journaled and graded, and is tracked on paper, so the record says how it
would have done.

WHAT IS BUILT, per pool (Edge picks, Most Likely picks), from tonight's
board:

  * SAME-GAME pairs that make sense: one leg on each team of the game, or
    two legs on one team that rise together (engine/parlays.relate, the
    clash taxonomy: a pair it kills or calls a duplicate is never built,
    and a same-team pair needs a positive correlation). The chance both hit
    is the copula's (parlays.joint_two).
  * TWO-GAME pairs ("same-game parlay X" in Ethan's words): two legs from
    different games, whose chances multiply.

A few of each, every leg used once per pool. The Most Likely pool ranks by
the chance both hit; the Edge pool by the expected return at the price, and
only a positive one posts.

THE PRICE, honestly. A parlay is placed at one book. Two legs priced at the
same book pay their prices multiplied; legs whose best prices sit at two
books are graded 3% under the product (TWO_BOOK_CUT), what one book's
slightly worse number costs. A same-game parlay is priced by the book with
its own correlation, which no feed we buy carries, so it is graded at the
product less SGP_CUT — the parlay doctrine's own midpoint
(parlays.BEST_CASE_SGP_TAX / WORST_CASE_SGP_TAX, 4% to 15% for two legs).
The card shows both numbers and says which one the record uses.

Standard library only.
"""
from __future__ import annotations

import re

import itertools

#: The leagues the Parlays page runs for (Ethan: "NBA MLB college football
#: and NFL").
SPORTS = ("nfl", "cfb", "nba", "mlb")
SAME_GAME = "same_game"
TWO_GAME = "two_game"
KIND_WORDS = {SAME_GAME: "Same game", TWO_GAME: "Two games"}
POOLS = ("edge", "likely")
#: How many of each kind a pool posts on one slate. Two, not three: on the
#: public receipts (2026-10-31, tools/parlay_study.py, every graded day since
#: the record's epoch), the third ticket of a day lost units in both pools, and
#: two a day beat three on ROI in both halves of the record (before 10-15: Edge
#: +15.5% against +3.1%, Most Likely +4.3% against -1.8%; from 10-15: +17.6%
#: against +16.6%, +19.7% against +13.4%). The ranking puts the best first, so
#: each extra ticket is a worse one.
PER_KIND = 2
#: A same-team pair has to rise together by at least this much to "make
#: sense"; one leg on each team may be anything short of a fight.
SAME_TEAM_MIN_RHO = 0.10
OPPOSITE_MIN_RHO = -0.05
#: The price cuts (module docstring).
SGP_CUT = 0.095
TWO_BOOK_CUT = 0.03
#: A staked parlay's size, in units.
STAKE_UNITS = 0.5
#: The journal's book for each pool (engine/parlayledger `source`).
SOURCES = {"edge": "two_edge", "likely": "two_likely"}


def _dec(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if -100 < o < 100:
        return None
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / abs(o))


def american(dec: float) -> int:
    """Decimal to American, rounded the way a book prints it; even money is
    -100, as parlays.decimal_to_american spells it."""
    if dec > 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def game_key(leg: dict) -> tuple:
    """(the two teams sorted, the day) — or None's when the leg names no
    game, which is never paired as same-game."""
    a, b = (leg.get("home") or "", leg.get("away") or "") if (leg.get("home") or leg.get("away")) \
        else (leg.get("team") or "", leg.get("opponent") or "")
    if not a or not b:
        return ((), leg.get("game_date") or "")
    return (tuple(sorted((a, b))), leg.get("game_date") or "")


def _started(leg: dict, now=None) -> bool:
    try:
        from .potd import _started as started
        return bool(started(leg, now))
    except Exception:                                         # noqa: BLE001
        return False


# --- the legs -------------------------------------------------------------------
def edge_legs(board: dict, sport: str, now=None) -> list[dict]:
    """The board's Edge picks as legs: recommended, really priced, inside the
    stake rule's price cap, still to play."""
    from .stakeplan import priced_out
    from . import parlays as P
    out = []
    for r in board.get("recommendations") or []:
        if not isinstance(r, dict) or not r.get("recommended") or r.get("has_market") is False:
            continue
        if str(r.get("book") or "").lower() == "proxy" or priced_out("edge", r.get("odds")):
            continue
        out.append(_leg(r, r.get("hit_prob"), "edge"))
    for g in board.get("game_bets") or []:
        if not isinstance(g, dict) or not g.get("recommended") or priced_out("edge", g.get("odds")):
            continue
        out.append(_leg(P.normalize_game_bet(g, sport), g.get("win_prob"), "edge"))
    return [l for l in out if l and not _started(l, now)]


def likely_legs(board: dict, sport: str, now=None) -> list[dict]:
    """The board's Most Likely picks as legs: ranked, bettable, still to play."""
    out = []
    for r in board.get("most_likely") or []:
        if not isinstance(r, dict) or r.get("bettable") is False:
            continue
        out.append(_leg(r, r.get("model_prob"), "likely"))
    return [l for l in out if l and not _started(l, now)]


def _leg(r: dict, p, pool: str) -> dict | None:
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    d = _dec(r.get("odds"))
    if not (0.0 < p < 1.0) or d is None or not r.get("market") or not r.get("player"):
        return None
    return {"player": r.get("player"), "team": r.get("team") or "", "opponent": r.get("opponent") or "",
            "home": r.get("home") or "", "away": r.get("away") or "",
            "market": r.get("market"), "market_label": r.get("market_label") or _market_word(r.get("market")),
            "side": r.get("side") or "", "line": r.get("line"), "odds": int(float(r.get("odds"))),
            "book": r.get("book") or "", "p": round(p, 4), "pool": pool,
            "game_date": r.get("game_date") or r.get("date") or "", "kickoff": r.get("kickoff") or "",
            "headline": r.get("headline") or "", "position": r.get("position") or "",
            "_game_leg": bool(r.get("_game_leg"))}


# --- the pairs ----------------------------------------------------------------------
def _market_word(key) -> str:
    """A market's name in words (engine/markets), for a row that carries no
    label of its own: "pass_yds" is "Passing Yards" on the page."""
    try:
        from . import markets
        return markets.label(str(key or "")) if key else ""
    except Exception:                                         # noqa: BLE001
        return str(key or "")


def plain(mechanism) -> str:
    """The screen's reason for a pair, in the reader's words.

    `parlays.relate` writes its notes for the doctrine's readers and cites
    its sections ("one passing game wearing two jerseys — §4.1's strongest
    usable NFL correlation, and measured at +0.64 on 2,844 of our own
    games"). On the page a section number means nothing, so each citation
    clause goes, from the dash before it to where our own words start
    again (", and measured at ...") or to the end."""
    s = str(mechanism or "")
    i = s.find("§")
    while i >= 0:
        start = max(s.rfind(" — ", 0, i), s.rfind("; ", 0, i))
        start = start if start >= 0 else i
        m = re.search(r",\s*(?:and\s+)?(?=measured)", s[i:])
        s = s[:start] + (" — " + s[i + m.end():] if m else "")
        i = s.find("§")
    return s.strip(" —;,")


def price(a: dict, b: dict, kind: str) -> tuple[float, float, str]:
    """(the legs' prices multiplied, the price the record grades at, why)."""
    naive = _dec(a["odds"]) * _dec(b["odds"])
    if kind == SAME_GAME:
        return naive, naive * (1.0 - SGP_CUT), f"same game: the legs' prices less {SGP_CUT:.1%}"
    if (a.get("book") or "").lower() != (b.get("book") or "").lower():
        return naive, naive * (1.0 - TWO_BOOK_CUT), f"two books: the legs' prices less {TWO_BOOK_CUT:.0%}"
    return naive, naive, "one book: the legs' prices multiplied"


def pair(sport: str, a: dict, b: dict) -> dict | None:
    """One candidate parlay, or None when the two legs do not make sense
    together (the same player, a fight, a duplicate, or a same-team pair
    that does not rise together)."""
    from . import parlays as P
    if a["player"] == b["player"]:
        return None
    ka, kb = game_key(a), game_key(b)
    same = bool(ka[0]) and ka == kb
    if same:
        try:
            rel = P.relate(sport, a, b)
        except Exception:                                     # noqa: BLE001
            return None
        if rel.verdict in ("kill", "duplicate"):
            return None
        same_team = bool(a["team"]) and a["team"] == b["team"]
        if same_team and rel.rho < SAME_TEAM_MIN_RHO:
            return None
        if not same_team and rel.rho < OPPOSITE_MIN_RHO:
            return None
        joint = P.joint_two(a["p"], b["p"], max(-0.9, min(0.9, rel.rho)))
        kind, rho = SAME_GAME, round(rel.rho, 3)
        mech = plain(rel.mechanism)
        why = (f"Same game, same team — they rise together: {mech}" if same_team
               else f"Same game, one pick on each team ({a['team']} and {b['team']})"
               + (f": {mech}" if abs(rel.rho) >= 0.10 and mech else ""))
    else:
        joint, kind, rho = a["p"] * b["p"], TWO_GAME, 0.0
        why = "Two games, our picks from each"
    naive, graded, basis = price(a, b, kind)
    return {"kind": kind, "kind_label": KIND_WORDS[kind], "legs": [a, b], "joint": round(joint, 4),
            "independent": round(a["p"] * b["p"], 4), "rho": rho,
            "naive_dec": round(naive, 4), "price_dec": round(graded, 4),
            "price": american(graded), "naive_price": american(naive), "price_basis": basis,
            "ev": round(joint * graded - 1.0, 4), "why": why,
            "kickoff": min(x for x in (a.get("kickoff") or "~", b.get("kickoff") or "~")),
            "game_date": min(a.get("game_date") or "", b.get("game_date") or "") or a.get("game_date") or ""}


def candidates(sport: str, legs: list[dict]) -> list[dict]:
    """Every pair of legs that makes sense, both kinds."""
    out = []
    for a, b in itertools.combinations(legs, 2):
        t = pair(sport, a, b)
        if t is not None:
            out.append(t)
    return out


def choose(tickets: list[dict], pool: str, per_kind: int = PER_KIND) -> list[dict]:
    """A few of each kind, every leg once: the Most Likely pool by the chance
    both hit, the Edge pool by the expected return at the price (positive
    only)."""
    if pool == "edge":
        tickets = [t for t in tickets if t["ev"] > 0]
        key = lambda t: (-t["ev"], -t["joint"])                   # noqa: E731
    else:
        key = lambda t: (-t["joint"], -t["ev"])                   # noqa: E731
    out, used = [], set()
    for kind in (SAME_GAME, TWO_GAME):
        n = 0
        for t in sorted((t for t in tickets if t["kind"] == kind), key=key):
            ids = {_leg_id(l) for l in t["legs"]}
            if ids & used:
                continue
            out.append(t)
            used |= ids
            n += 1
            if n >= per_kind:
                break
    return out


def _leg_id(l: dict) -> tuple:
    return (l.get("player"), l.get("market"), str(l.get("side") or "").upper(), l.get("line"))


# --- the stake ------------------------------------------------------------------------
def staked(sport: str, t: dict, plan: dict | None) -> bool:
    """Both legs are picks the stake rule stakes (module docstring)."""
    from . import stakeplan
    p = plan or {}
    for l in t["legs"]:
        if l["pool"] == "edge":
            if not stakeplan.edge_staked(sport, _plan=p) or stakeplan.priced_out("edge", l["odds"]):
                return False
        elif not stakeplan.likely_staked(sport, _plan=p):
            return False
    return True


# --- the board -----------------------------------------------------------------------------
def build(board: dict, sport: str, plan: dict | None = None, now=None,
          drawdown: bool = False) -> dict:
    """{"sport", "date", "edge": {...}, "likely": {...}} — each pool's
    tickets with the counts behind them. Never raises: a pool that fails says
    so in its own `note`.

    ``drawdown``: the singles' drawdown breaker is on (parlays.bankroll_state).
    The doctrine's §10.2 holds here as it held for the screen: "when stakes
    are halved, parlays go to zero — not half." Every ticket is tracked, and
    the board says why."""
    sp = str(sport or "").lower()
    if plan is None:
        try:
            from . import ledger as L
            plan = L.stake_plan()
        except Exception:                                     # noqa: BLE001
            plan = {}
    out = {"sport": sp, "date": board.get("date") or "", "stake_units": STAKE_UNITS,
           "sgp_cut": SGP_CUT, "two_book_cut": TWO_BOOK_CUT, "drawdown": bool(drawdown)}
    if drawdown:
        out["note"] = ("The drawdown breaker is on: every parlay is tracked, none staked, "
                       "until the singles' stakes are whole again.")
    for pool, get in (("edge", edge_legs), ("likely", likely_legs)):
        try:
            legs = get(board, sp, now)
            cands = candidates(sp, legs)
            tickets = choose(cands, pool)
            for t in tickets:
                t["staked"] = (not drawdown) and staked(sp, t, plan)
                t["stake_units"] = STAKE_UNITS if t["staked"] else 0.0
            out[pool] = {"tickets": tickets, "legs": len(legs), "considered": len(cands),
                         "same_game": sum(1 for t in tickets if t["kind"] == SAME_GAME),
                         "two_game": sum(1 for t in tickets if t["kind"] == TWO_GAME)}
        except Exception as exc:                              # noqa: BLE001
            out[pool] = {"tickets": [], "legs": 0, "considered": 0, "same_game": 0, "two_game": 0,
                         "note": f"the {pool} parlays did not build: {exc}"}
    return out


def attach(board: dict, sport: str, plan: dict | None = None, drawdown: bool = False) -> dict:
    """Hang tonight's two-leg parlays on the board as `two_leg` (the leagues
    in SPORTS). Never raises."""
    if str(sport or "").lower() in SPORTS:
        try:
            board["two_leg"] = build(board, sport, plan, drawdown=drawdown)
        except Exception as exc:                              # noqa: BLE001
            board["two_leg"] = {"sport": sport, "edge": {"tickets": []}, "likely": {"tickets": []},
                                "note": f"the parlays did not build: {exc}"}
    return board


def report(b: dict) -> str:
    """The build log's line."""
    if not isinstance(b, dict) or "edge" not in b:
        return "  Two-leg parlays: not built"
    parts = []
    for pool, word in (("edge", "Edge"), ("likely", "Most Likely")):
        x = b.get(pool) or {}
        parts.append(f"{word} {x.get('same_game', 0)} same-game + {x.get('two_game', 0)} two-game "
                     f"from {x.get('legs', 0)} legs")
    return "  Two-leg parlays: " + "; ".join(parts) + ("; drawdown: all tracked" if b.get("drawdown") else "")


# --- what it would have done: the journal, paired the same way ----------------------------
BACKTEST_CATS = {"edge": ("main", "paper"), "likely": ("likely", "likely_live", "board")}


def _grade(t: dict) -> float | None:
    """One parlay's return on one unit, from its legs' results, or None when
    it voids (a book drops a pushed leg; one leg left is no parlay)."""
    a, b = t["legs"]
    if "lost" in (a["status"], b["status"]):
        return -1.0
    live = [l for l in (a, b) if l["status"] == "won"]
    if len(live) == 2:
        return t["price_dec"] - 1.0
    return None


def backtest(conn, since: str | None = None, games: dict | None = None,
             per_kind: int = PER_KIND, until: str | None = None) -> dict:
    """Every graded day of the headline record, paired the way tonight's
    board is (`candidates` → `choose`), and graded off the legs' results.

    ``games`` is {(sport, day, team): opponent} for telling one game's two
    sides from two games; without it only same-team pairs count as one game
    and every other pair is two games. ``until`` (a day, exclusive) ends the
    window, for the study's halves. Returns {"rows": [{sport, pool, kind,
    parlays, won, win_rate, units, roi, singles_roi}], "per_kind", "since",
    "until", "rule"}."""
    from . import ledger as L
    since = since or getattr(L, "RECORD_EPOCH", None)
    q = (f"SELECT sport, {L.day_expr()} AS day, date, category, player, team, market, side, line, odds, "
         "book, hit_prob, status FROM bets WHERE status IN ('won','lost','push') AND stake_units > 0 "
         "AND hit_prob IS NOT NULL")
    args: list = []
    if since:
        q += f" AND {L.day_expr()} >= ?"
        args.append(since)
    if until:
        q += f" AND {L.day_expr()} < ?"
        args.append(until)
    seen, groups = set(), {}
    for r in conn.execute(q, args):
        r = dict(r)
        sp = str(r["sport"] or "").lower()
        if sp not in SPORTS or L.is_benched(sp):
            continue
        pool = next((p for p, cats in BACKTEST_CATS.items() if r["category"] in cats), None)
        if pool is None:
            continue
        k = (pool, sp, r["date"], r["player"], r["market"], str(r["side"] or "").upper(), r["line"])
        if k in seen:
            continue
        seen.add(k)
        team = r.get("team") or ""
        opp = (games or {}).get((sp, r["day"], team), "")
        leg = _leg({**r, "opponent": opp, "game_date": r["day"]}, r["hit_prob"], pool)
        if leg is None:
            continue
        leg["status"] = r["status"]
        if not team:
            leg["opponent"] = ""                     # no team: never a same-game leg
        elif not opp:
            leg["opponent"] = f"?{team}"             # a team with no schedule: its own game
        groups.setdefault((sp, r["day"], pool), []).append(leg)
    agg: dict = {}
    for (sp, _day, pool), legs in groups.items():
        for t in choose(candidates(sp, legs), pool, per_kind):
            ret = _grade(t)
            if ret is None:
                continue
            for key in ((sp, pool, t["kind"]), (sp, pool, "all"), ("all", pool, "all")):
                c = agg.setdefault(key, {"parlays": 0, "won": 0, "units": 0.0, "singles": 0.0, "legs": 0})
                c["parlays"] += 1
                c["won"] += ret > 0
                c["units"] += ret
                for l in t["legs"]:
                    if l["status"] == "won":
                        c["singles"] += _dec(l["odds"]) - 1.0
                    elif l["status"] == "lost":
                        c["singles"] -= 1.0
                    c["legs"] += 1 if l["status"] in ("won", "lost") else 0
    rows = []
    for (sp, pool, kind), c in sorted(agg.items()):
        rows.append({"sport": sp, "pool": pool, "kind": kind, "parlays": c["parlays"],
                     "won": c["won"], "win_rate": round(c["won"] / c["parlays"], 4),
                     "units": round(c["units"], 2), "roi": round(c["units"] / c["parlays"], 4),
                     "singles_roi": round(c["singles"] / c["legs"], 4) if c["legs"] else None})
    return {"rows": rows, "per_kind": per_kind, "since": since, "until": until,
            "rule": ("Each day's graded picks paired the way tonight's board is: same-game pairs that "
                     "make sense and two-game pairs, a few of each, every pick once; graded off the "
                     "picks' own results at the parlay's price, one unit each.")}


def schedule(hconn, since: str | None = None) -> dict:
    """{(sport, day, team): opponent} from the history database's games, for
    `backtest`. Empty when it cannot be read."""
    out: dict = {}
    if hconn is None:
        return out
    try:
        q = "SELECT sport, date, home, away FROM games WHERE sport IN (%s)" % ",".join("?" * len(SPORTS))
        args = list(SPORTS)
        if since:
            q += " AND date >= ?"
            args.append(since)
        for sp, day, home, away in hconn.execute(q, args):
            d = str(day or "")[:10]
            out[(sp, d, home)] = away
            out[(sp, d, away)] = home
    except Exception:                                         # noqa: BLE001
        return {}
    return out
