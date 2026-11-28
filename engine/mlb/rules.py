"""MLB betting rules.

Same discipline as the NFL engine, with baseball's own holds:
  * confidence and edge thresholds;
  * **lineup hold** — a hitter prop is suppressed until the player is in a
    posted lineup (the MLB analogue of the NFL injury hold);
  * postponement-risk warnings flow through from the weather engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..rules import RuleConfig, game_has_started, condition
from ..betting import Recommendation
from .models import MLBProp, MLBGame, HITTER_MARKETS
from .projection import MLBProjection


@dataclass
class MLBRuleDecision:
    recommend: bool
    warnings: list[str] = field(default_factory=list)
    #: Every condition, passed or failed — see engine/rules.RuleDecision
    #: for why the passes matter as much as the failures.
    checks: list[dict] = field(default_factory=list)


def apply_mlb_rules(rec: Recommendation, prop: MLBProp, game: MLBGame,
                    proj: MLBProjection,
                    config: RuleConfig | None = None) -> MLBRuleDecision:
    config = config or RuleConfig()
    warnings: list[str] = list(proj.warnings)
    checks: list[dict] = []
    recommend = True

    if rec.grade == "Pass":
        recommend = False
    checks.append(condition("grade", "Model grade", rec.grade != "Pass",
                         rec.grade, "anything but Pass"))
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
    priced_out = (rec.stake_units or 0) <= 0 and rec.grade != "Pass"
    if priced_out:
        recommend = False
        warnings.append(
            f"Priced out — the read is a {rec.grade}, but at {rec.odds:+d} "
            f"Kelly sizes it at 0.00u: the book's number already matches "
            f"ours. Tracked on paper, never staked.")
    checks.append(condition("kelly", "Worth a stake at this price", not priced_out,
                         f"{(rec.stake_units or 0):.2f}u", "above 0.00u"))

    started = config.block_live_games and game_has_started(game)
    if started:
        recommend = False
        warnings.append("Game already started — this is a pre-game model and "
                        "cannot price an in-play market")
    checks.append(condition("pregame", "Game not yet started", not started,
                         "started" if started else "not started", "pre-game only"))

    if rec.confidence < config.min_confidence:
        recommend = False
        warnings.append(f"Below confidence threshold "
                        f"({rec.confidence} < {config.min_confidence})")
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

    # Lineup hold: no bet on a hitter who isn't in a confirmed lineup. A
    # PROJECTED lineup (last game's order, used so the board can price the
    # morning board) gives a hitter a real spot — the game-level flag is what
    # says nothing official has posted, so check it too or projected players
    # would sail through to the journal.
    if prop.market in HITTER_MARKETS:
        posted = bool(prop.lineup_spot != 0 and game.lineups_confirmed)
        if not posted:
            recommend = False
            warnings.append(f"{prop.player} not in a confirmed lineup — "
                            f"hold until the card is posted")
        # A pitcher prop has no batting order, so the hold is reported only
        # where it applies rather than as a condition nobody weighed.
        checks.append(condition(
            "lineup", "In a posted lineup", posted,
            f"batting {prop.lineup_spot}" if prop.lineup_spot
            else "not in the card", "confirmed card"))

    return MLBRuleDecision(recommend=recommend, warnings=warnings,
                           checks=checks)
