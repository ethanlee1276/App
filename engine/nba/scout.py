"""The NBA scout's read: what a basketball person checks before trusting a pick.

Ethan, 2026-11-04: "I don't know much about NBA, so I want to make sure
we're picking the right bets, reading the right scripts, picking the right
models ... so we're winning a lot of bets."

The football scout (engine/scout.py) writes down the spots a football person
hesitates in; this is the same for basketball. The model reads minutes,
rate, defence and shooting and turns them into a number. A person reading
the same pick asks other questions: is this game likely to be over by the
fourth? Is the man whose shots he has been taking back tonight? Did his
minutes just jump? Is he just back from missing games?

THE THRESHOLDS WERE FIXED HERE BEFORE ANY OF THEM WAS MEASURED (2026-11-04),
the repo's rule: never choose a setting because a backtest liked it.

MEASURED THE SAME DAY (docs/NBA_LAB.md, "The scout"), on two full seasons
of box scores — every game a man of 15+ minutes a game played, as a book
settles it — at a half-point line off his last five games: first before any
model (does the flagged side hit less than the same side unflagged?), then
after ours (does it hit less than OUR NUMBER said, against unflagged picks
on that side?). Each flag's verdict is in `VERDICT`:

  * PRICED — a real effect our number now carries, so the card does not
    warn twice: his first games back and a role that just jumped each
    became a measured minutes rule (engine/nba/minutes, `hoops.NBA`); a
    hot three-point run is the shooting regression's (engine/nba/shooting).
  * REFUSED — measured, and not a warning: a starter's over in a projected
    blowout hits more often than our number said, an over on a back-to-back
    as often as any other.
  * WARNING — still goes wrong after everything above, in both seasons:
    an under while a regular teammate sits (3-7% under what we said; the
    low end once the teammate-out minutes are on), an over the night a
    regular returns (2-3%, after the return rule), an over after his
    minutes dropped (4-5%: that rule did not pass its bar, so the card says
    it instead), an under in a game the books expect to be high-scoring
    (2-3%), a man whose games swing widely (about 1%), and a man with under
    five games for his club this season (about 2%, one season measured).
    Only these reach the card, each with what it measured.
  * UNMEASURED — a line well above or below his last five needs the books'
    lines, which the lab's seasons do not have; too rare to read (an over
    in a projected grind: 515 picks in one season, none in the other).

A flag moves no number. The card says it; the record's own correction
(engine/likelycal, by maker and side) is what lowers a chance that keeps
over-claiming.

THE SITUATION a flag reads (``situation()`` builds it; every field may be
missing, and a flag needing a missing field does not fire):

    market, side        the pick ("OVER" / "UNDER")
    line                the number taken
    starter             he started his newest game
    spread              HIS club's spread: negative = favoured by that much
    total               the game total
    rest                tonight's rest label (nba_build.rest_from)
    last5               his average in this market over his newest five games
    cv10                game-to-game spread of his last ten (sd / mean)
    min3, min_prior     his average minutes over his newest three games, and
                        over the seven before them
    games_season        games he has played for his club this season
    missed_last         he did not play his club's previous game
    mate_out            a regular teammate (24+ minutes a game over his last
                        ten) who played lately sits tonight
    mate_back           a regular teammate who missed the club's last two or
                        more games plays tonight
    p3_recent, p3_long, a3_recent
                        his three-point percentage over his last ten games
                        and over his long run, and his attempts over the ten

Standard library only. Pure: no I/O.
"""
from __future__ import annotations

import math

#: Markets a flag reads.
SCORING = {"pts", "fg3m", "pra", "pts_reb", "pts_ast"}
VOLUME = {"pts", "reb", "ast", "fg3m", "pra", "pts_reb", "pts_ast", "reb_ast"}

#: The thresholds, written before any measurement (2026-11-04).
BLOWOUT_SPREAD = 10.0      # a game either side is expected to win by ten or more
FAST_TOTAL = 236.0         # a game the books expect to be high-scoring
SLOW_TOTAL = 214.0         # …or a grind
LINE_STRETCH = 1.15        # line this far above his last-five average
LINE_SHRINK = 0.85         # …or this far below it
ROLE_UP = 1.20             # newest three games' minutes over the seven before
ROLE_DOWN = 0.80
BOOM_BUST_CV = 0.55
THIN_GAMES = 5
HOT_HAND = 0.08            # 3P% over his last ten this far above his long run
HOT_HAND_ATTEMPTS = 25     # …on at least this many threes

#: Every flag: (code, the sentence a scout would write). Game script first,
#: then the people around him, then the player himself.
FLAGS = {
    "blowout_over": "an over on a starter in a game expected to be a blowout — starters sit the fourth",
    "fast_under": "an under in a game the books expect to be high-scoring",
    "slow_over": "an over in a game the books expect to be low-scoring",
    "b2b_over": "an over on the second night of a back-to-back",
    "mate_out_under": "an under while a regular teammate sits — his shots and minutes go somewhere",
    "mate_back_over": "an over the night a regular teammate returns — his recent numbers were made without him",
    "role_up_under": "an under on a player whose minutes just went up",
    "role_down_over": "an over on a player whose minutes just went down",
    "back_over": "an over in his first game back after missing time",
    "line_stretch_over": "an over at a line well above his last five games — the book sees something",
    "line_shrink_under": "an under at a line well below his last five games",
    "hot_hand_over": "a scoring over after a hot three-point stretch — shooting runs cool off",
    "boom_bust": "his games swing too widely for a sure thing",
    "thin": "too few games this season to know his role",
}

#: WHAT TWO SEASONS SAID (2026-11-04, docs/NBA_LAB.md "The scout"): each
#: flag's verdict and, for a warning, what it measured after our number as
#: the board now runs it (the rotation's rules on; the teammate-out minutes
#: either way) — flagged picks against unflagged ones on the same side.
VERDICT = {
    "mate_out_under": ("warning", "in two seasons, unders like this hit 3-7% less often than our number "
                                  "said (the low end once the minutes his absence opens are on)"),
    "mate_back_over": ("warning", "in two seasons, overs like this hit 2-3% less often than our number said, "
                                  "even after the minutes the return takes back"),
    "role_down_over": ("warning", "in two seasons, overs like this hit 4-5% less often than our number said: "
                                  "a drop in his minutes mostly holds"),
    "fast_under": ("warning", "in two seasons, unders like this hit 2-3% less often than our number said"),
    "boom_bust": ("warning", "in two seasons, our number ran about 1% hot on men whose games swing like his"),
    "thin": ("warning", "our number ran about 2% hot on men this early in their season (one season measured)"),
    "back_over": ("priced", "his first games back play light — our minutes already take it out"),
    "role_up_under": ("priced", "a jump in his minutes mostly holds — our minutes already read it"),
    "hot_hand_over": ("priced", "a hot shooting run cools — our shooting read already regresses it"),
    "blowout_over": ("refused", "overs like this hit more often than our number said, not less"),
    "b2b_over": ("refused", "overs on a back-to-back hit as often as other overs against our number"),
    "slow_over": ("unmeasured", "too rare in two seasons to read"),
    "line_stretch_over": ("unmeasured", "needs the books' lines, which the measured seasons do not have"),
    "line_shrink_under": ("unmeasured", "needs the books' lines, which the measured seasons do not have"),
}

#: The flags a card shows: the ones still measured to go wrong.
CARD = tuple(c for c in FLAGS if VERDICT.get(c, ("",))[0] == "warning")


def _avg(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _cv(xs):
    xs = [float(x) for x in xs if x is not None]
    if len(xs) < 5:
        return None
    m = sum(xs) / len(xs)
    if m <= 0:
        return None
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) / m


def situation(market: str, side: str, line=None, values=None, minutes=None, starter=None,
              spread=None, total=None, rest=None, games_season=None, missed_last=None,
              mate_out=None, mate_back=None, p3_recent=None, p3_long=None, a3_recent=None) -> dict:
    """The fields a flag reads, from the pick and his history (``values`` and
    ``minutes`` newest first)."""
    vals = list(values or [])
    mins = list(minutes or [])
    return {"market": market, "side": (side or "").upper(), "line": line,
            "starter": starter, "spread": spread, "total": total, "rest": rest,
            "last5": _avg(vals[:5]), "cv10": _cv(vals[:10]),
            "min3": _avg(mins[:3]) if len(mins) >= 6 else None,
            "min_prior": _avg(mins[3:10]) if len(mins) >= 6 else None,
            "games_season": games_season, "missed_last": missed_last,
            "mate_out": mate_out, "mate_back": mate_back,
            "p3_recent": p3_recent, "p3_long": p3_long, "a3_recent": a3_recent}


def flags(s: dict) -> list[str]:
    """Every flag this situation raises, in FLAGS order — measured or not
    (the lab reads them all; a card shows `card_flags`)."""
    m, side = s.get("market"), s.get("side")
    over, under = side == "OVER", side == "UNDER"
    out = set()
    spread, total = s.get("spread"), s.get("total")
    if over and s.get("starter") and spread is not None and abs(spread) >= BLOWOUT_SPREAD and m in VOLUME:
        out.add("blowout_over")
    if total is not None and m in VOLUME:
        if under and total >= FAST_TOTAL:
            out.add("fast_under")
        if over and total <= SLOW_TOTAL:
            out.add("slow_over")
    if over and s.get("rest") in ("b2b_home", "b2b_road", "b2b_road_30plus", "3in4"):
        out.add("b2b_over")
    if under and s.get("mate_out"):
        out.add("mate_out_under")
    if over and s.get("mate_back"):
        out.add("mate_back_over")
    m3, mp = s.get("min3"), s.get("min_prior")
    if m3 is not None and mp:
        if under and m3 >= ROLE_UP * mp:
            out.add("role_up_under")
        if over and m3 <= ROLE_DOWN * mp:
            out.add("role_down_over")
    if over and s.get("missed_last"):
        out.add("back_over")
    l5, line = s.get("last5"), s.get("line")
    if l5 and line is not None:
        if over and line >= LINE_STRETCH * l5:
            out.add("line_stretch_over")
        if under and line <= LINE_SHRINK * l5:
            out.add("line_shrink_under")
    pr, pl, a3 = s.get("p3_recent"), s.get("p3_long"), s.get("a3_recent")
    if over and m in SCORING and pr is not None and pl is not None and (a3 or 0) >= HOT_HAND_ATTEMPTS \
            and pr >= pl + HOT_HAND:
        out.add("hot_hand_over")
    if (s.get("cv10") or 0) >= BOOM_BUST_CV:
        out.add("boom_bust")
    gs = s.get("games_season")
    if gs is not None and gs < THIN_GAMES:
        out.add("thin")
    return [c for c in FLAGS if c in out]


def card_flags(codes) -> list[str]:
    """The flags a card shows: only those measured to still go wrong."""
    return [c for c in codes if c in CARD]


def notes(codes: list[str]) -> list[str]:
    """The card's sentences: what a scout would write, and what it measured."""
    return [f"{FLAGS[c][0].upper()}{FLAGS[c][1:]}. {VERDICT[c][1][0].upper()}{VERDICT[c][1][1:]}."
            for c in codes if c in FLAGS and c in VERDICT]


def every(ctx: dict | None, market: str, side: str, line=None) -> list[str]:
    """Every flag one pick raises — measured, refused or not — from the
    side-free facts the build put on its row (``scout_ctx``,
    nba_build.scout_context) or the record rebuilt after the game
    (engine/nba/scoutrecord). The card shows `card_flags` of these; the
    record's own correction (engine/likelyctx) reads them all, because the
    graded record may prove a flag two seasons of box scores did not."""
    if not isinstance(ctx, dict) or not market or not side:
        return []
    return flags(situation(market, side, line, ctx.get("values"), ctx.get("minutes"), ctx.get("starter"),
                           ctx.get("spread"), ctx.get("total"), ctx.get("rest"), ctx.get("games_season"),
                           ctx.get("missed_last"), ctx.get("mate_out"), ctx.get("mate_back")))


def read(ctx: dict | None, market: str, side: str, line=None) -> tuple[list, list]:
    """``(card flags, card sentences)`` for one pick, from the side-free facts
    the build put on its row (``scout_ctx``, nba_build.scout_context).
    Empty for a row the build gave none (another league, an old board)."""
    codes = card_flags(every(ctx, market, side, line))
    return codes, notes(codes)


def annotate(rows: list[dict]) -> int:
    """Put ``scout_flags`` and ``scout_notes`` on every row that carries a
    ``scout_ctx``, for the side and line the row itself takes (a Most Likely
    row may take the other side of the Edge card, or a rung of its ladder),
    and ``scout_all``, every flag it raises, for the record's correction
    (engine/likelyctx.apply). Moves no number; returns how many rows carry
    a caution."""
    n = 0
    for r in rows or []:
        if not isinstance(r, dict) or not isinstance(r.get("scout_ctx"), dict):
            continue
        allf = every(r["scout_ctx"], r.get("market") or "", str(r.get("side") or ""), r.get("line"))
        codes = card_flags(allf)
        r["scout_flags"], r["scout_notes"], r["scout_all"] = codes, notes(codes), allf
        n += bool(codes)
    return n
