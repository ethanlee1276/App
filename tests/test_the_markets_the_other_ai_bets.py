"""Attempts, completions, carries and a quarterback's rushing: measured,
then priced. Interceptions: measured, and left off.

Ethan, 2026-09-27: "we dont have a market for interceptions, QB over or
under rushing yards, or some other stuff that the ai recommends".

Four separate places had to name each market (tests/test_pass_td_market
is the precedent): the odds request, the slate's position table, the
labels the page and the journal share, and the ranking figure that lets
a row reach the Most Likely board. The figures come from marketfit.py,
walk-forward on the cached 2021-2025 box scores and scored on held-out
2025: pass attempts 0.707, completions 0.696, carries 0.632, a
quarterback's rushing yards 0.616 (level with a back's 0.616 in the same
harness); interceptions 0.540, a coin, so no key, no prop, no figure.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import oddsbudget as B                                   # noqa: E402
from engine.likely import RANK_AUC, rankable                         # noqa: E402
from engine.markets import words                                     # noqa: E402
from engine.models import (MARKET_LABELS, PASS_ATT, PASS_CMP, RUSH_ATT, RUSH_YDS,   # noqa: E402
                           PASS_YDS)
from engine.quality import MARKET_TIER, VOLATILITY                   # noqa: E402
from engine.sources import nflverse as N, oddsapi as O               # noqa: E402
from engine.statlogs import SPORT_MARKETS                            # noqa: E402

NEW = (PASS_ATT, PASS_CMP, RUSH_ATT)


def test_the_book_is_asked_behind_the_guard_and_the_meter_counts_it():
    assert O.NFL_ODDS_TO_MARKET["player_pass_attempts"] == PASS_ATT
    assert O.NFL_ODDS_TO_MARKET["player_pass_completions"] == PASS_CMP
    assert O.NFL_ODDS_TO_MARKET["player_rush_attempts"] == RUSH_ATT
    assert set(O.VOLUME_ODDS_KEYS) <= O.UNPROVEN_MARKETS, "unproven from here, like passing TDs were"
    # The COUNT measured a coin (0.540) and was not bought; the RATE per
    # attempt × projected attempts × the defence's takeaway rate is what
    # went on the request on 2026-10-05 (engine/passint), one more credit.
    assert O.NFL_ODDS_TO_MARKET["player_pass_interceptions"] == "pass_int"
    assert "player_pass_interceptions" in O.UNPROVEN_MARKETS
    cfg = O.SPORT_CONFIG["nfl"]
    assert B.EVENT_CREDITS["nfl"] == len(cfg["markets"]) + len(cfg["scorers"]) + len(cfg["alternates"]) + 3 == 17


def test_the_slate_builds_the_props_a_quarterback_and_a_back_now_hold():
    qb = [m for m, _r in N.POSITION_MARKETS["QB"]]
    assert qb == [PASS_YDS, "pass_td", PASS_ATT, PASS_CMP, "pass_int", RUSH_YDS]
    assert RUSH_ATT in [m for m, _r in N.POSITION_MARKETS["RB"]]
    assert N.is_secondary("QB", RUSH_YDS) and N.SECONDARY_FLOOR[RUSH_YDS] == 8.0, \
        "a pocket passer with five yards a game gets no line nobody hangs"
    assert not N.is_secondary("RB", RUSH_YDS)
    for m in NEW:
        assert m in N.MARKET_COLUMNS
    # A quarterback's relief-appearance rows stay out of every market of his.
    starter = {"position": "QB", "attempts": "31"}
    mop_up = {"position": "QB", "attempts": "4"}
    for m in (PASS_ATT, PASS_CMP, RUSH_YDS):
        assert N.quarterbacked(starter, m) and not N.quarterbacked(mop_up, m)
    assert N.quarterbacked({"position": "RB", "attempts": "0"}, RUSH_YDS)


def test_one_label_on_the_page_the_journal_and_the_chip():
    assert MARKET_LABELS[PASS_ATT] == "Pass Attempts" and MARKET_LABELS[PASS_CMP] == "Completions"
    assert MARKET_LABELS[RUSH_ATT] == "Carries", "the player page already has a Carries chip; one label, one chip"
    w = words()
    for m in NEW:
        assert w[m] == MARKET_LABELS[m]
    chips = dict(SPORT_MARKETS["nfl"])
    assert chips["pass_att"] == "Pass Attempts" and chips["pass_cmp"] == "Completions"
    assert chips["carries"] == MARKET_LABELS[RUSH_ATT]


def test_the_measured_figures_let_them_rank_and_keep_interceptions_off_most_likely():
    """Interceptions are BUILT and PRICED since 2026-10-05 (engine/passint)
    and still carry no NFL ranking figure: the box's own run of
    `marketfit.py --opp` decides that, as it did for the three."""
    assert (RANK_AUC[PASS_ATT], RANK_AUC[PASS_CMP], RANK_AUC[RUSH_ATT]) == (0.707, 0.696, 0.632)
    for m in NEW:
        assert rankable(m, "nfl")
    assert "pass_int" not in RANK_AUC and not rankable("pass_int", "nfl")
    for m in NEW:
        assert MARKET_TIER[m] == 1, "a bet on a role, priced as carefully as catches"
    assert VOLATILITY[PASS_ATT] == "LOW"
    src = open(os.path.join(ROOT, "marketfit.py"), encoding="utf-8").read()
    for line in ("pass_att    QB   0.707", "pass_int    QB   0.540", "rush_yds    QB   0.616"):
        assert line in src, line


def test_the_logs_settle_them_and_the_reads_can_lean_to_them():
    from engine import ingest as I
    assert I.NFL_USAGE_MARKETS["pass_cmp"][0] == "completions" and I.NFL_USAGE_MARKETS["rush_att"] == ("carries",)
    assert "pass_cmp" in I.NFL_QB_ONLY and "rush_att" not in I.NFL_QB_ONLY
    from engine.matchpicks import PROP_MARKETS
    from engine.gameplan import VOLUME_MARKETS
    from engine.boards import FOOTBALL_SHELVES
    assert set(NEW) <= set(PROP_MARKETS) and set(NEW) <= set(VOLUME_MARKETS)
    shelved = {m for _k, _t, ms, _b in FOOTBALL_SHELVES for m in ms}
    assert set(NEW) <= shelved, "a market with no shelf lands on Other"
    scan = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert 'lean = ["pass_yds", "pass_td", "pass_att", "pass_cmp"]' in scan
    assert 'lean = ["rush_yds", "rush_att", "anytime_td"]' in scan


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
