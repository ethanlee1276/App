"""The scout's read: what a football person checks before trusting a pick.

Ethan, 2026-10-03: "think like a human when it comes to making the pick
selections. It's not just us using data to make picks. It's us using data
on top of just general football knowledge and thinking like an actual
human and what could happen."

The model reads form, matchup, weather and injuries and turns them into a
number. A person reading the same pick asks a different kind of question:
does the game script fight this bet? Is the book's line telling me
something his last five games are not? Is he just back from missing time?
Those questions are written down here as FLAGS — each one a situation a
football person would hesitate in, with the thresholds fixed in this file
BEFORE any of them was measured against our record (the repo's rule: never
choose a setting because a backtest liked it).

WHAT A FLAG IS NOT: a verdict. A flag says "this is the kind of spot that
goes wrong", and the graded record decides whether it actually does
(nflaudit.py measures every flag against what we claimed; engine/likelyctx
pulls a flagged pick's chance toward its price only where the record has
proven the flag over-claims, out of sample). Until then a flag is a note on
the card a reader can weigh — the same note the person would write.

THE SITUATION a flag reads (``situation()`` builds it; every field may be
missing and a flag needing a missing field simply does not fire):

    market, side          the pick ("OVER" / "UNDER" / "YES")
    line                  the number taken
    position              QB / RB / WR / TE
    spread                THE TEAM'S spread: negative = favoured by that much
    total                 the game total
    implied               the team's implied points: total/2 − spread/2
    wind, outdoor         mph at kickoff, and whether the roof is open
    weekday               0=Mon … 3=Thu … 6=Sun
    last5                 his average in this market, newest five games
    cv10                  game-to-game spread of his last ten (sd ÷ mean)
    recent3, prior5       his average over the newest three games, and the
                          five before them — the direction of his role
    games_season          games he has played this season
    missed_last           he did not play his team's previous game

Standard library only. Pure: no I/O.
"""
from __future__ import annotations

import math

#: Markets a flag reads, by what moves them.
RUSHING = {"rush_yds", "rush_att"}
PASSING = {"pass_yds", "pass_att", "pass_cmp", "pass_td"}
RECEIVING = {"rec_yds", "receptions"}
VOLUME = RUSHING | PASSING | RECEIVING
YARDAGE = {"rush_yds", "rec_yds", "pass_yds"}
SCORING = {"anytime_td", "pass_td"}

#: The thresholds, written before any measurement (2026-10-03).
SHOOTOUT_TOTAL = 49.0        # a game the books expect to be high-scoring
LOW_TOTAL = 40.0             # a game the books expect to be a grind
BIG_DOG = 7.0                # a team expected to trail all day
BIG_FAV_PASS = 10.0          # a team expected to sit on a lead
BIG_FAV_RUN = 7.0
BLOWOUT = 13.0               # a game expected to be over by the fourth
WIND = 15.0                  # mph: the ball starts to move
LINE_STRETCH = 1.15          # line this far above his last-five average
LINE_SHRINK = 0.85           # …or this far below it
THIN_GAMES = 3
BOOM_BUST_CV = 0.60
LOW_IMPLIED = 18.0           # a team the books expect to score under 18
ROLE_DOWN = 0.75             # newest three at most this share of the five before
ROLE_UP = 1.25

#: Every flag: (code, the sentence a scout would write). The order is the
#: order a reader sees them in — game script first, then the player.
FLAGS = {
    "shootout_under": "an under in a game the books expect to be a shootout",
    "low_total_over": "an over in a game the books expect to be a low-scoring grind",
    "dog_run_over": "a rushing over on a team expected to trail — trailing teams stop running",
    "dog_pass_under": "a passing or receiving under on a team expected to trail — trailing teams throw",
    "fav_pass_over": "a passing over on a big favourite — leads get sat on, starters can sit",
    "fav_run_under": "a rushing under on a big favourite — leads get run out",
    "blowout_over": "an over in a game expected to be decided early — starters can sit in the fourth",
    "wind_pass_over": "a passing or receiving over in strong wind",
    "low_implied_td": "a touchdown on a team expected to score under 18",
    "back_from_absence": "his first game back after missing his team's last game",
    "line_above_form": "the book's line is well above what he has done lately — it may know something",
    "line_below_form": "the book's line is well below what he has done lately — it may know something",
    "role_down_over": "an over while his role has been shrinking",
    "role_up_under": "an under while his role has been growing",
    "thin_sample": "fewer than three games of evidence this season",
    "boom_bust": "a boom-or-bust player — his games swing widely",
    "short_week_over": "an over on a short week (Thursday)",
}


def team_spread(game_spread, home: bool | None):
    """The team's own spread from the stored HOME spread (negative = home
    favoured): the home side's number, or its negative for the away side."""
    if game_spread is None or home is None:
        return None
    s = float(game_spread)
    return s if home else -s


def implied_points(total, spread):
    """total/2 − spread/2: a 7-point favourite in a 47 game is 27."""
    if total is None or spread is None:
        return None
    return float(total) / 2.0 - float(spread) / 2.0


def _avg(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _cv(xs):
    xs = [float(x) for x in xs if x is not None]
    if len(xs) < 4:
        return None
    m = sum(xs) / len(xs)
    if m <= 0:
        return None
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    return sd / m


def situation(market: str, side: str, line=None, position: str = "", values=None,
              game_spread=None, home: bool | None = None, total=None, wind=None, outdoor=None,
              weekday=None, games_season=None, missed_last=None) -> dict:
    """The situation from the pick and its game. ``values`` = his results in
    this market, NEWEST FIRST (the shape every row and the history carry)."""
    vals = [v for v in (values or []) if v is not None]
    sp = team_spread(game_spread, home)
    return {"market": market, "side": str(side or "").upper(), "line": line,
            "position": str(position or "").upper(), "spread": sp, "total": total,
            "implied": implied_points(total, sp), "wind": wind, "outdoor": outdoor,
            "weekday": weekday, "last5": _avg(vals[:5]), "cv10": _cv(vals[:10]),
            "recent3": _avg(vals[:3]) if len(vals) >= 3 else None,
            "prior5": _avg(vals[3:8]) if len(vals) >= 6 else None,
            "games_season": games_season if games_season is not None else len(vals),
            "missed_last": missed_last}


def flags(s: dict) -> list[str]:
    """The flag codes this situation raises, in FLAGS order."""
    m, side = s.get("market") or "", s.get("side") or ""
    over = side in ("OVER", "YES")
    under = side == "UNDER"
    sp, tot, imp = s.get("spread"), s.get("total"), s.get("implied")
    line, l5 = s.get("line"), s.get("last5")
    out = set()
    if tot is not None:
        if under and m in VOLUME and tot >= SHOOTOUT_TOTAL:
            out.add("shootout_under")
        if over and tot <= LOW_TOTAL:
            out.add("low_total_over")
    if sp is not None:
        if over and m in RUSHING and sp >= BIG_DOG:
            out.add("dog_run_over")
        if under and m in (PASSING | RECEIVING) and sp >= BIG_DOG:
            out.add("dog_pass_under")
        if over and m in PASSING and sp <= -BIG_FAV_PASS:
            out.add("fav_pass_over")
        if under and m in RUSHING and sp <= -BIG_FAV_RUN:
            out.add("fav_run_under")
        if over and m in VOLUME and abs(sp) >= BLOWOUT:
            out.add("blowout_over")
    wind = s.get("wind")
    if over and m in (PASSING | RECEIVING) and wind is not None and s.get("outdoor") is not False \
            and float(wind) >= WIND:
        out.add("wind_pass_over")
    if over and m in SCORING and imp is not None and imp <= LOW_IMPLIED:
        out.add("low_implied_td")
    if s.get("missed_last"):
        out.add("back_from_absence")
    if line is not None and l5 and m in VOLUME:
        if over and float(line) >= LINE_STRETCH * l5:
            out.add("line_above_form")
        if under and float(line) <= LINE_SHRINK * l5:
            out.add("line_below_form")
    r3, p5 = s.get("recent3"), s.get("prior5")
    if r3 is not None and p5 and m in VOLUME:
        if over and r3 <= ROLE_DOWN * p5:
            out.add("role_down_over")
        if under and r3 >= ROLE_UP * p5:
            out.add("role_up_under")
    gs = s.get("games_season")
    if gs is not None and gs < THIN_GAMES:
        out.add("thin_sample")
    cv = s.get("cv10")
    if cv is not None and m in YARDAGE and cv >= BOOM_BUST_CV:
        out.add("boom_bust")
    if over and s.get("weekday") == 3:
        out.add("short_week_over")
    return [f for f in FLAGS if f in out]


def notes(codes: list[str]) -> list[str]:
    """The sentences for a list of flag codes."""
    return [FLAGS[c] for c in codes if c in FLAGS]
