"""Betting rules engine.

Applies the discipline rules that keep the model honest: minimum confidence,
suppress props on players with their own injury cloud, and flag when an
alternate line would be materially safer. Returns a decision plus any warnings
so the UI can show why a bet was filtered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Prop, Game
from .betting import Recommendation
from .injuries import player_injury_status


@dataclass
class RuleConfig:
    min_confidence: float = 6.0
    min_edge: float = 0.02
    block_injury_concern: bool = True
    # Never recommend a bet on a game that has already started. Every projection
    # here is a PRE-GAME model: it assumes a full game's worth of opportunity and
    # knows nothing about the current score. A book's in-play price does know, so
    # comparing the two invents enormous phantom edges — e.g. backing a team down
    # three in the bottom of the ninth at +1400 because the pre-game model still
    # thinks they're a coin flip. Until a live model exists, in-play games are
    # shown for their scores but never recommended.
    block_live_games: bool = True
    # Heaviest price worth laying, in American odds. Chalk past this pays too
    # little for the risk, and it's also where the model is least reliable (the
    # far tail of the distribution), so those bets are filtered out.
    max_juice: int = -350


@dataclass
class RuleDecision:
    recommend: bool
    warnings: list[str] = field(default_factory=list)
    #: EVERY condition this pick was held to, passed or failed, with the
    #: threshold and the pick's own value. The warnings above only appear
    #: when a rule FAILS, which meant the site could never say what a pick
    #: had cleared — and on a page about how the model thinks, "no warning"
    #: is not the same sentence as "checked six things and cleared all six".
    #: Absence is not evidence; this is.
    checks: list[dict] = field(default_factory=list)


def condition(key: str, label: str, passed: bool, value: str,
           limit: str = "") -> dict:
    return {"key": key, "label": label, "passed": bool(passed),
            "value": value, "limit": limit}


#: How long after kickoff a game's OWN CLOCK counts it as started, in
#: minutes. Inside this window a pre-game price is being taken in play or
#: after the whistle; past it the row is history — a replay, a backtest, a
#: fixture — and the price ceilings in `oddsapi` (six hours stops a
#: recommendation) already keep a fresh price from existing on a game that
#: old, so in production the far edge of the window is never reached.
IN_PLAY_WINDOW_MIN = 8 * 60


def clock_says_started(date, kickoff, now=None) -> bool:
    """Has this game kicked off by its own schedule, within the window?

    THE SECOND WITNESS. `game_has_started` below read only the live
    overlay, and the NFL launcher never passed `--live` — so on
    2026-09-14 the Broncos-Chiefs slate built at 10:32pm and again at
    10:51pm, in the fourth quarter, with every game "scheduled": the
    board recommended and the journal placed Bo Nix over 217.5 passing
    yards, Evan Engram over 3.5 receptions and a game-total under 48.5
    with 41 points already scored. The scoreboard is now passed, and it
    is still one feed that can 403; the schedule's own kickoff is on the
    game row and needs no network at all.

    A bare "HH:MM" is an Eastern clock joined to the row's date by
    `fatigue.kickoff_instant`; an ISO stamp is read as it is. Anything
    that cannot be joined honestly answers False — a guess here would
    refuse real bets on the strength of a missing field.
    """
    from .fatigue import kickoff_instant
    from .losspatterns import minutes_until
    stamp = str(kickoff or "").strip()
    if not stamp:
        return False
    if len(stamp) <= 5:
        stamp = kickoff_instant(str(date or ""), stamp)
        if not stamp:
            return False
    lead = minutes_until(stamp, now)
    return lead is not None and -IN_PLAY_WINDOW_MIN < lead <= 0


def game_has_started(game, now=None) -> bool:
    """True once a game is live or final — i.e. once a pre-game projection is
    stale and the book is pricing something our model isn't modelling.

    Two witnesses: the live overlay when the build has one, and the
    game's own kickoff clock (`clock_says_started`) when it does not."""
    live = getattr(game, "live", None)
    if live and getattr(live, "state", "") in ("live", "final"):
        return True
    return clock_says_started(getattr(game, "date", ""),
                              getattr(game, "kickoff", ""), now=now)


def apply_rules(
    rec: Recommendation,
    prop: Prop,
    game: Game,
    config: RuleConfig | None = None,
) -> RuleDecision:
    config = config or RuleConfig()
    warnings: list[str] = []
    checks: list[dict] = []
    recommend = True

    if rec.grade == "Pass":
        recommend = False
    checks.append(condition("grade", "Model grade", rec.grade != "Pass",
                         rec.grade, "anything but Pass"))

    started = config.block_live_games and game_has_started(game)
    if started:
        recommend = False
        warnings.append("Game already started — this is a pre-game model and "
                        "cannot price an in-play market")
    checks.append(condition("pregame", "Game not yet started", not started,
                         "started" if started else "not started", "pre-game only"))

    if rec.confidence < config.min_confidence:
        recommend = False
        warnings.append(f"Below confidence threshold ({rec.confidence} < {config.min_confidence})")
    checks.append(condition("confidence", "Confidence",
                         rec.confidence >= config.min_confidence,
                         f"{rec.confidence}/10", f"{config.min_confidence:g} or better"))

    if rec.edge < config.min_edge:
        recommend = False
        warnings.append(f"Edge too small ({rec.edge:+.1%})")
    checks.append(condition("edge", "Edge over the price",
                         rec.edge >= config.min_edge,
                         f"{rec.edge:+.1%}", f"{config.min_edge:+.1%} or better"))

    if rec.odds < config.max_juice:
        recommend = False
        warnings.append(f"Too much juice ({rec.odds:+d}) — pays too little for the risk")
    checks.append(condition("juice", "Price worth laying",
                         rec.odds >= config.max_juice,
                         f"{rec.odds:+d}", f"{config.max_juice:+d} or better"))

    concern = player_injury_status(prop, game.injuries)
    if concern and config.block_injury_concern:
        recommend = False
        warnings.append(f"{prop.player} listed {concern} — hold until inactives confirm status")
    checks.append(condition("health", "No designation on him",
                         not (concern and config.block_injury_concern),
                         concern or "not listed", "not listed"))

    # §7 wind bands: 25+ mph is a hard block on deep-passing markets, not a
    # haircut. Receptions survive (short throws complete in wind); the
    # yardage markets that live on the deep ball do not.
    w = getattr(game, "weather", None)
    deep = prop.market in ("pass_yds", "rec_yds")
    # On the game book's scale the rule was written in (engine/weather.
    # book_wind — a forecast reads on it as it stands, FORECAST_WIND_SCALE).
    from .weather import book_wind
    blown = (w is not None and not w.dome and book_wind(w) >= 25 and deep)
    if blown:
        recommend = False
        warnings.append(f"Wind {book_wind(w):.0f} mph — deep-passing markets "
                        f"are avoided entirely at 25+ (model rule, no exceptions)")
    # Reported only where the rule can bite. A wind check on a rushing prop
    # would read as a condition that was weighed, and it was not.
    if deep:
        checks.append(condition(
            "wind", "Wind under the deep-ball block", not blown,
            "indoors" if (w is not None and w.dome)
            else f"{book_wind(w):.0f} mph" if w is not None else "unknown",
            "under 25 mph"))

    return RuleDecision(recommend=recommend, warnings=warnings, checks=checks)
