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


def game_has_started(game) -> bool:
    """True once a game is live or final — i.e. once a pre-game projection is
    stale and the book is pricing something our model isn't modelling."""
    live = getattr(game, "live", None)
    return bool(live and getattr(live, "state", "") in ("live", "final"))


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
    blown = (w is not None and not w.dome and (w.wind_mph or 0) >= 25 and deep)
    if blown:
        recommend = False
        warnings.append(f"Wind {w.wind_mph:.0f} mph — deep-passing markets "
                        f"are avoided entirely at 25+ (model rule, no exceptions)")
    # Reported only where the rule can bite. A wind check on a rushing prop
    # would read as a condition that was weighed, and it was not.
    if deep:
        checks.append(condition(
            "wind", "Wind under the deep-ball block", not blown,
            "indoors" if (w is not None and w.dome)
            else f"{(w.wind_mph or 0):.0f} mph" if w is not None else "unknown",
            "under 25 mph"))

    return RuleDecision(recommend=recommend, warnings=warnings, checks=checks)
