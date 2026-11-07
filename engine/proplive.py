"""Live chances for a prop in the middle of a game.

Ethan, 2026-10-12: "live chances for props mid game ... for all sports".

A PROP IN PLAY IS A RACE between what the player has banked and what is
left of the game to bank the rest in. Both halves are already on disk,
free, every cycle: the box score the live loop writes (his number so far)
and the scoreboard's period and clock (how much game is left). This turns
them into the chance the BET wins — over or under, as the ticket says —
without a book's live prop price, which books mostly pull at kickoff and
the Odds API bills per game for (engine/mlb/liveprops says the same).

THE CLOCK SPORTS — football, basketball, hockey:

    remaining production  Y ~ NegBin with mean  mu' * f,  variance  D * mu' * f
        f    the share of regulation still to play (engine/livewp's clock)
        D    the game's variance-to-mean ratio for this market: the
             board's own spread for the player where his row carries one
             (proj_std / sd / the one-SD range proj_low-high), else
             FALLBACK_D
        mu'  the full-game mean that makes the KICKOFF number equal the
             card's own chance at this line

    P(win) = P(banked + Y clears the line on the ticket's side)

A negative binomial with these parameters is a process with independent
increments (a sum of NegBin(r_i, p) with one p is NegBin(sum r_i, p)), so
"mean and variance both shrink in proportion to the game left" is not a
guess about the second half — it is what the distribution does. Counts
too small for a normal (touchdowns, threes, shots, goals) come out right
because it is discrete; D at or under 1 is the Poisson case.

ANCHORED, SO IT STARTS WHERE THE CARD STARTS. mu' is solved so that at
f = 1 and nothing banked, P(over) equals the chance the slip card printed
before kickoff — our number for the leg (Most Likely's tier rate, the
honest-shrunk prop chance, whatever the grader showed), or, for a leg off
our boards, the break-even its own price implies. A live chance that
jumped away from the pregame one at 0:00 would be two models disagreeing
in public; this is the pregame number watched as the game is played.

WHAT IT CANNOT SEE, said plainly because a live percentage reads as
precise whether or not it deserves to:

  * Pace. A receiver with eight targets at the half is treated as if he
    were on his pregame rate for the rest of the game; the update is in
    the banked number, not in the rate. Whether the first half carries
    information about the second beyond that is exactly what the
    measurement (proplivefit) answers, and nothing here assumes it.
  * Benching. A blowout's fourth quarter, foul trouble, an injury
    mid-game. The clock is the game's, not the player's.
  * Overtime. Past regulation the clock has no share left to divide;
    the leg says where it stands and prints no chance (livewp refuses the
    same thing for the same reason).

BASEBALL HAS NO CLOCK, and its live model already exists:
engine/mlb/liveprops, fed by the lineup spot, the inning, the outs and
who is at the plate — the same function the Live tab's tracked bets use.
`mlb_chance` here only gathers those inputs from the slip's live files.

NOT A PRICE. Nothing bets off this and nothing journals it.

Standard library only. Pure functions; no I/O.
"""

from __future__ import annotations

import math

#: The variance-to-mean ratio of a full game, by market, for a row that
#: carries no spread of its own. Typical full-game numbers, not fits: a
#: receiver's ~60 yards with an SD near 30, a scorer's points near 20 with
#: an SD near 6.5, a shot count that is close to Poisson. They set how
#: fast the chance moves with the clock and the banked number; where the
#: chance STARTS is the card's own number (see `anchor`), so a rough D
#: costs shape, never the kickoff value. A market not listed gets no
#: chance at all rather than a borrowed one.
FALLBACK_D = {
    # football
    "pass_yds": 17.0, "rush_yds": 11.0, "rec_yds": 15.0, "rush_rec_yds": 14.0,
    "pass_rush_yds": 16.0, "receptions": 1.0, "pass_att": 1.1, "pass_cmp": 1.2,
    "rush_att": 1.4, "pass_td": 1.0, "pass_int": 1.0, "anytime_td": 1.0,
    "kick_pts": 1.2, "fg_made": 1.0, "tackles_ast": 1.3,
    # basketball
    "pts": 2.1, "reb": 1.1, "ast": 1.15, "fg3m": 1.0, "pra": 2.0,
    "pts_reb": 1.9, "pts_ast": 1.9, "reb_ast": 1.2,
    "stl": 1.0, "blk": 1.2, "tov": 1.0,
    # hockey
    "sog": 1.0, "points": 1.0, "goals": 1.0, "assists": 1.0, "blocks": 1.1,
    "saves": 1.4, "anytime_goal": 1.0,
}

#: The leagues with a regulation clock this can divide (engine/livewp).
CLOCK_LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl")

#: A ratio this close to 1 is Poisson; a negative binomial with a huge r
#: is the same distribution computed the slow way.
POISSON_D = 1.05

#: Chances are clamped here, as livewp clamps its win probability: a live
#: race is never certain until the box score says it is over, and the
#: result field (sliplive) is what reports certainty.
FLOOR, CEIL = 0.001, 0.999

#: A row's range (proj_low / proj_high) is its projection one SD either
#: side — engine/betting.py and engine/mlb/betting.py both write
#: `mean - std` and `mean + std`, the baseball low floored at zero — so
#: the SD is read off the high side, which no floor touches.
RANGE_SDS = 1.0


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default


# ---- the distribution ---------------------------------------------------------
def _pmf_iter(mean: float, disp: float):
    """Yield P(Y = 0), P(Y = 1), … for a count with this mean and
    variance-to-mean ratio: Poisson at D <= POISSON_D, else NegBin."""
    mean = max(0.0, float(mean))
    if mean <= 0.0:
        yield 1.0
        while True:
            yield 0.0
    if disp <= POISSON_D:
        p = math.exp(-mean)
        y = 0
        while True:
            yield p
            y += 1
            p *= mean / y
    q = 1.0 / disp                       # NegBin "success" probability
    r = mean / (disp - 1.0)              # so mean = r(1-q)/q, var = mean / q
    log_p0 = r * math.log(q)
    p = math.exp(log_p0) if log_p0 > -700 else 0.0
    y = 0
    while True:
        yield p
        p *= (y + r) / (y + 1) * (1.0 - q)
        y += 1


def at_least(m: float, mean: float, disp: float) -> float:
    """P(Y >= m) for the count above. m <= 0 is a certainty."""
    if m <= 0:
        return 1.0
    m = int(math.ceil(m))
    below = 0.0
    for y, p in enumerate(_pmf_iter(mean, disp)):
        if y >= m:
            break
        below += p
    return max(0.0, min(1.0, 1.0 - below))


def exactly(k: float, mean: float, disp: float) -> float:
    """P(Y == k) for an integer k >= 0; 0 otherwise."""
    if k < 0 or abs(k - round(k)) > 1e-9:
        return 0.0
    k = int(round(k))
    for y, p in enumerate(_pmf_iter(mean, disp)):
        if y == k:
            return p
    return 0.0                                              # pragma: no cover


def p_over_full(line: float, mean: float, disp: float) -> float:
    """P(a full game clears ``line`` on the over) — strictly more than it."""
    return at_least(math.floor(float(line)) + 1, mean, disp)


def p_win_full(side: str, line: float, mean: float, disp: float) -> float:
    """P(a full game wins the bet on ``side``): over is strictly more than
    the line, under strictly less — on a whole-number line the push is
    neither side's."""
    if str(side or "").lower() in ("over", "yes"):
        return p_over_full(line, mean, disp)
    return max(0.0, 1.0 - at_least(math.ceil(float(line)), mean, disp))


def anchor_side(p_win: float, side: str, line: float, disp: float) -> float | None:
    """The full-game mean at which the bet (side, line) wins with
    ``p_win``. An under wins on fewer than the line, so it is held as
    P(at least ceil(line)) = 1 - p_win, which keeps a whole number's push
    out of both sides."""
    p_win, line = _num(p_win), _num(line)
    if p_win is None or line is None:
        return None
    if str(side or "").lower() in ("over", "yes"):
        return anchor(p_win, line, disp)
    return anchor(1.0 - p_win, math.ceil(line) - 0.5, disp)


def anchor(p_over: float, line: float, disp: float) -> float | None:
    """The full-game mean whose P(over ``line``) is ``p_over``.

    P(over) only rises with the mean, so this is a bisection. A target at
    either edge is held inside it — a 100% card is a claim no
    distribution makes, and the live number should not be the one to
    print it."""
    p_over = _num(p_over)
    line = _num(line)
    if p_over is None or line is None or line < 0:
        return None
    target = min(max(p_over, 0.002), 0.998)
    lo, hi = 1e-6, max(4.0, line * 2.0 + 10.0)
    while p_over_full(line, hi, disp) < target and hi < 1e6:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if p_over_full(line, mid, disp) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def race(side: str, line: float, banked: float, share: float, mean: float,
         disp: float) -> tuple[float, float]:
    """(P(the bet wins), P(it pushes)) with ``banked`` in hand and ``share``
    of the full-game ``mean`` still to come."""
    over = str(side or "").lower() in ("over", "yes")
    need = float(line) - float(banked)
    rest = max(0.0, float(mean) * max(0.0, min(1.0, float(share))))
    p_cross = at_least(math.floor(need) + 1, rest, disp)        # banked + Y > line
    push = exactly(need, rest, disp) if need >= 0 else 0.0     # banked + Y == line
    win = p_cross if over else max(0.0, 1.0 - p_cross - push)
    return win, push


# ---- the inputs ---------------------------------------------------------------
def row_dispersion(row: dict | None) -> float | None:
    """The full game's variance-to-mean off the row's OWN spread, or None
    when it carries none.

    Read in the order the boards write it: `proj_std` (the NFL and college
    pipeline), `sd` (hockey), then the range `proj_low` / `proj_high` (the
    shared Recommendation and baseball's), one SD either side of
    `projection`. A spread the row carries but that is nonsense (an SD of
    zero, a range upside down) is no spread."""
    r = row or {}
    mu = _num(r.get("projection"))
    sd = _num(r.get("proj_std")) or _num(r.get("sd"))
    if not sd:
        lo, hi = _num(r.get("proj_low")), _num(r.get("proj_high"))
        if hi is not None and mu is not None and hi > mu:
            sd = (hi - mu) / RANGE_SDS
        elif lo is not None and hi is not None and hi > lo:
            sd = (hi - lo) / (2.0 * RANGE_SDS)
    if mu and mu > 0 and sd and sd > 0:
        return max(1.0, (sd * sd) / mu)
    return None


def dispersion(row: dict | None, market: str) -> float | None:
    """The full game's variance-to-mean for this player and market: the
    row's own spread where it carries one, else FALLBACK_D, else None."""
    d = row_dispersion(row)
    return d if d is not None else FALLBACK_D.get(market)


def share_left(league: str, live: dict | None) -> float | None:
    """The share of regulation still to play, off the scoreboard's own
    period and clock (engine/livewp.seconds_left). None in overtime, on a
    clock that will not parse, and for a league with no clock."""
    lg = str(league or "").lower()
    if lg not in CLOCK_LEAGUES or not isinstance(live, dict):
        return None
    from . import livewp
    left = livewp.seconds_left(lg, live.get("period"), live.get("clock"))
    total = livewp.REGULATION_S.get(lg)
    if left is None or not total:
        return None
    return max(0.0, min(1.0, float(left) / float(total)))


def pregame_win(leg: dict) -> tuple[float | None, str]:
    """(the leg's pregame chance for its own side, where it came from):
    the card's own number when it is ours, else the break-even its price
    implies — the number the ticket's chance already used for it."""
    p = _num(leg.get("prob"))
    if p is not None:
        return p, "ours"
    p = _num(leg.get("needs"))
    return (p, "price") if p is not None else (None, "")


def clock_chance(leg: dict, row: dict | None = None) -> dict | None:
    """The live chance for a prop in a clock sport, from the leg's live
    state (engine/sliplive: `share_left`, `current`) and its pregame
    number. None whenever an input is missing — no clock, no banked
    number, no pregame chance, a market with no dispersion — because
    each of those is a reason the number would be made up."""
    live = leg.get("live") or {}
    if live.get("state") != "live" or live.get("result"):
        return None
    market, side = leg.get("market"), str(leg.get("side") or "").lower()
    share = _num(live.get("share_left"))
    banked = _num(live.get("current"))
    line = 0.5 if market in ("anytime_td", "anytime_goal") else _num(leg.get("line"))
    if share is None or banked is None or line is None or side not in ("over", "under", "yes", "no"):
        return None
    if share <= 0.0:
        # Regulation is over and the game is not: overtime may add to it,
        # and this model has no share of an overtime to divide.
        return None
    disp = dispersion(row if row is not None else leg.get("row"), market)
    p_win, source = pregame_win(leg)
    if disp is None or p_win is None:
        return None
    mean = anchor_side(p_win, side, line, disp)
    if mean is None:
        return None
    win, push = race(side, line, banked, share, mean, disp)
    return {"p": round(min(CEIL, max(FLOOR, win)), 4),
            "push": round(push, 4) if push >= 0.0005 else 0.0,
            "share_left": round(share, 3), "from": source, "model": "clock",
            "expected": round(banked + mean * share, 1)}


# ---- baseball ----------------------------------------------------------------
#: The MLB markets engine/mlb/liveprops prices, by the box key that banks
#: them. "outs" (a pitcher's outs recorded) is not among them: liveprops
#: has no model for it, so it shows his number and no chance.
MLB_HITTER = ("hits", "total_bases", "home_runs")
MLB_PITCHER = ("strikeouts",)


def mlb_inning(period: str, outs) -> tuple[int, str, int] | None:
    """(inning, "Top"/"Bottom", outs) off the fast file's period —
    "Top 5th", "Bottom 9th", "Middle 3rd", "End 7th". Middle is the
    bottom about to start and End the next top, both with nobody out."""
    words = str(period or "").split()
    if len(words) < 2:
        return None
    digits = "".join(ch for ch in words[1] if ch.isdigit())
    if not digits:
        return None
    inning = int(digits)
    half = words[0].lower()
    o = int(_num(outs, 0) or 0)
    if half.startswith("top"):
        return inning, "Top", o
    if half.startswith("bot"):
        return inning, "Bottom", o
    if half.startswith("mid"):
        return inning, "Bottom", 0
    if half.startswith("end"):
        return inning + 1, "Top", 0
    return None


def mlb_means(board: dict | None, player: str) -> dict:
    """{market: tonight's projection} for one player off the MLB board's
    own rows — the same means that priced the bet, which is the whole
    reason liveprops takes its rates from them."""
    from .sources.oddsapi import normalize_name
    want = normalize_name(player or "")
    out: dict = {}
    for r in (board or {}).get("recommendations") or []:
        if isinstance(r, dict) and normalize_name(r.get("player") or "") == want:
            mu = _num(r.get("projection"))
            if mu is not None and r.get("market") and r["market"] not in out:
                out[r["market"]] = mu
    return out


def mlb_chance(leg: dict, board: dict | None) -> dict | None:
    """The live chance for an MLB prop, through engine/mlb/liveprops, from
    the situation the slip's live state carries (sliplive: inning text,
    outs, his lineup spot, the batter at the plate, whether a pitcher is
    still on the mound). None when liveprops would refuse — no spot, no
    batter up, total bases without the hits and home-run means beside it.
    """
    live = leg.get("live") or {}
    if live.get("state") != "live" or live.get("result"):
        return None
    sit = live.get("situation") or {}
    inn = mlb_inning(live.get("period"), sit.get("outs"))
    banked = _num(live.get("current"))
    market, line = leg.get("market"), _num(leg.get("line"))
    if inn is None or banked is None or line is None:
        return None
    from .mlb import liveprops as lp
    inning, half, outs = inn
    side = "UNDER" if str(leg.get("side") or "").lower() == "under" else "OVER"
    is_home = bool(sit.get("is_home"))
    hs, as_ = live.get("home_score"), live.get("away_score")
    means = mlb_means(board, leg.get("player"))
    if market in MLB_PITCHER:
        still_in = bool(sit.get("on_mound"))
        opp_outs = lp.outs_left(inning, half, outs, is_home=not is_home,
                                home_score=hs, away_score=as_)
        left = lp.bf_left(opp_outs, _num(sit.get("bf"), 0.0) or 0.0) if still_in else 0.0
        mean = means.get("strikeouts")
        if mean is None:
            return None
        p = lp.pitcher_probability(float(mean) / lp.STARTER_BF, line, side, banked, left)
        unit, n = "batters", left
    elif market in MLB_HITTER:
        spot, up = sit.get("spot"), sit.get("batter_spot")
        if not spot or not up:
            return None
        rates = lp.rates_for(market, means, int(spot))
        if rates is None:
            return None
        team_outs = lp.outs_left(inning, half, outs, is_home, hs, as_)
        n = lp.remaining_pa(int(spot), int(up), team_outs)
        p = lp.hitter_probability(rates, market, line, side, banked, n)
        unit = "plate appearances"
    else:
        return None
    if p is None:
        return None
    return {"p": round(min(CEIL, max(FLOOR, float(p))), 4), "push": 0.0,
            "from": "ours", "model": "mlb", "left": round(float(n), 1), "left_unit": unit}


def leg_chance(leg: dict, boards: dict | None = None) -> dict | None:
    """The live chance for one slip leg, whichever model its sport has:
    the clock for football, basketball and hockey, liveprops for baseball.
    A side or a total reads the scoreboard's win probability elsewhere
    (sliplive); this is for player props."""
    league = str(leg.get("league") or leg.get("sport") or "").lower()
    if leg.get("market") in ("moneyline", "spread", "total"):
        return None
    try:
        if league == "mlb":
            return mlb_chance(leg, (boards or {}).get("mlb"))
        if league in CLOCK_LEAGUES:
            # The spread is the player's, not the shelf's: a leg seated on
            # Most Likely carries the seat's chance and no spread, and the
            # main board's row for him carries the projection's.
            row = leg.get("row")
            if row_dispersion(row) is None:
                main = _rec_row((boards or {}).get(league), leg)
                if row_dispersion(main) is not None:
                    row = main
            return clock_chance(leg, row)
    except Exception:                                      # noqa: BLE001
        return None
    return None


def _rec_row(board: dict | None, leg: dict) -> dict | None:
    """The player's main-board row for this market — the one that carries
    the projection's spread — when the leg was found on a shelf that does
    not (a Most Likely seat, a scorer field)."""
    from .sources.oddsapi import normalize_name
    want = normalize_name(leg.get("player") or "")
    for r in (board or {}).get("recommendations") or []:
        if (isinstance(r, dict) and r.get("market") == leg.get("market")
                and normalize_name(r.get("player") or "") == want):
            return r
    return None
