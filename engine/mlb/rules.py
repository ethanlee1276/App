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
    # Kelly sizing it at zero means that AT THIS PRICE, with our own
    # probability, the bet is negative expectation. The grade and the stake
    # measure different things — the grade is how much we trust the read
    # (edge 40%, pitcher certainty 15%, lineup certainty 15%...), the stake
    # is whether the price is worth taking — and they can disagree, because
    # the edge bar compares us to the DE-VIGGED fair number while Kelly
    # compares us to the price actually on offer. A pick can beat fair by
    # 2% and still lose to the vig.
    #
    # Nothing checked this, so such a pick was flagged recommended, shown on
    # the board, and then skipped by the journal — landing in no bucket at
    # all. The board said "pick" and every other surface disagreed. A pick
    # we would not stake is not a pick; it is paper-tracked instead (see
    # ledger.log_priced_out).
    if (rec.stake_units or 0) <= 0 and rec.grade != "Pass":
        recommend = False
        warnings.append(
            f"Priced out — the read is a {rec.grade}, but at {rec.odds:+d} "
            f"Kelly sizes it at 0.00u: the book's number already matches "
            f"ours. Tracked on paper, never staked.")
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
