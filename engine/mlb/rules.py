"""MLB betting rules.

Same discipline as the NFL engine, with baseball's own holds:
  * confidence and edge thresholds;
  * **lineup hold** — a hitter prop is suppressed until the player is in a
    posted lineup (the MLB analogue of the NFL injury hold);
  * postponement-risk warnings flow through from the weather engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..rules import RuleConfig, game_has_started
from ..betting import Recommendation
from .models import MLBProp, MLBGame, HITTER_MARKETS
from .projection import MLBProjection


@dataclass
class MLBRuleDecision:
    recommend: bool
    warnings: list[str] = field(default_factory=list)


def apply_mlb_rules(rec: Recommendation, prop: MLBProp, game: MLBGame,
                    proj: MLBProjection,
                    config: RuleConfig | None = None) -> MLBRuleDecision:
    config = config or RuleConfig()
    warnings: list[str] = list(proj.warnings)
    recommend = True

    if rec.grade == "Pass":
        recommend = False
    if config.block_live_games and game_has_started(game):
        recommend = False
        warnings.append("Game already started — this is a pre-game model and "
                        "cannot price an in-play market")
    if rec.confidence < config.min_confidence:
        recommend = False
        warnings.append(f"Below confidence threshold "
                        f"({rec.confidence} < {config.min_confidence})")
    if rec.edge < config.min_edge:
        recommend = False
        warnings.append(f"Edge too small ({rec.edge:+.1%})")

    if rec.odds < config.max_juice:
        recommend = False
        warnings.append(f"Too much juice ({rec.odds:+d}) — pays too little for the risk")

    # Lineup hold: no bet on a hitter who isn't in a confirmed lineup. A
    # PROJECTED lineup (last game's order, used so the board can price the
    # morning board) gives a hitter a real spot — the game-level flag is what
    # says nothing official has posted, so check it too or projected players
    # would sail through to the journal.
    if prop.market in HITTER_MARKETS and (
            prop.lineup_spot == 0 or not game.lineups_confirmed):
        recommend = False
        warnings.append(f"{prop.player} not in a confirmed lineup — "
                        f"hold until the card is posted")

    return MLBRuleDecision(recommend=recommend, warnings=warnings)
