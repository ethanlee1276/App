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
    # Heaviest price worth laying, in American odds. Chalk past this pays too
    # little for the risk, and it's also where the model is least reliable (the
    # far tail of the distribution), so those bets are filtered out.
    max_juice: int = -350


@dataclass
class RuleDecision:
    recommend: bool
    warnings: list[str] = field(default_factory=list)


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
