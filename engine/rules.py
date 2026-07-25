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
    recommend = True

    if rec.grade == "Pass":
        recommend = False

    if config.block_live_games and game_has_started(game):
        recommend = False
        warnings.append("Game already started — this is a pre-game model and "
                        "cannot price an in-play market")

    if rec.confidence < config.min_confidence:
        recommend = False
        warnings.append(f"Below confidence threshold ({rec.confidence} < {config.min_confidence})")

    if rec.edge < config.min_edge:
        recommend = False
        warnings.append(f"Edge too small ({rec.edge:+.1%})")

    if rec.odds < config.max_juice:
        recommend = False
        warnings.append(f"Too much juice ({rec.odds:+d}) — pays too little for the risk")

    concern = player_injury_status(prop, game.injuries)
    if concern and config.block_injury_concern:
        recommend = False
        warnings.append(f"{prop.player} listed {concern} — hold until inactives confirm status")

    return RuleDecision(recommend=recommend, warnings=warnings)
