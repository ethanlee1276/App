"""The board that ranks by likelihood, not by edge.

Ethan, 2026-08-30: "we need to focus more on using the data to figure out
who will score each game, not who has the best edge... a separate page
which will be the main page for bets, that will show who we genuinely
think will score or hit the over."

The measurements agree and are not close. The model ranks outcomes and
prices them badly, and those are separate abilities:

    who scores a touchdown    AUC 0.721 (22,099 graded player-weeks)
    who clears their line     0.76 rushing, 0.77 receptions,
                              0.73 receiving, 0.69 passing
    where the market is wrong AUC 0.468 — noise

Long Shots is built on the last one. This board is built on the first
two, which is why it is the main page and that one is the specialist.

Run directly: `python3 tests/test_likely.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K                               # noqa: E402


def _prop(market="rec_yds", prob=0.62, odds=-115, player="A Wideout",
          has_market=True, **kw):
    got = {"player": player, "team": "CIN", "opponent": "CLE",
           "market": market, "market_label": market, "side": "over",
           "line": 45.5, "book": "DK", "odds": odds, "hit_prob": prob,
           "fair_prob": 0.55, "projection": 52.0, "ev_per_unit": 0.03,
           "has_market": has_market, "reasons": ["because"],
           "recent_values": [40, 60, 55], "date": "2026-09-14"}
    got.update(kw)
    return got


def _watch(player="A Back", prob=0.58, odds=-140):
    return {"player": player, "team": "DET", "opponent": "CHI",
            "book": "DK", "odds": odds, "model_prob": prob,
            "implied_prob": 0.55, "ev_per_unit": 0.01,
            "reasons": ["Team implied total 27.5"], "recent_values": [1, 0, 1],
            "game_date": "2026-09-14"}


def _always(_market):
    return True


# --- what may be ranked --------------------------------------------------
def test_only_markets_shown_to_rank_appear_at_all():
    """"We think he will hit" is a claim, and an unmeasured claim on the
    main board is exactly what this product is trying to stop being."""
    for market in ("anytime_td", "receptions", "rush_yds", "rec_yds",
                   "pass_yds"):
        assert K.rankable(market), market
    for market in ("first_td", "longest_reception", "made_up"):
        assert not K.rankable(market), market
    assert K.from_prop(_prop(market="made_up"), _always) is None


def test_the_rank_floor_is_above_a_coin_flip_by_a_margin():
    """0.5 is a coin flip; a board that cannot sort itself has no
    business claiming who will hit."""
    assert K.MIN_RANK_AUC > 0.5
    assert min(K.RANK_AUC.values()) >= K.MIN_RANK_AUC


# --- the distinction the whole page rests on -----------------------------
def test_a_market_can_rank_without_being_bettable():
    """THE POINT, AND IT LOOKS WRONG UNTIL YOU SEE THE TWO TESTS APART.
    `calibrate.is_reliable` shuts rushing yards for BETTING because its
    probability is wrong in ABSOLUTE terms — it cannot be compared to a
    price. Ranking needs it right only in RELATIVE terms. Rushing yards
    rank at 0.7605 while being unbettable, and ordering barely moves when
    the calibration is stripped out entirely (0.7605 against 0.7627 for
    the raw projection), because a monotone error does not reorder a
    list."""
    shut = K.from_prop(_prop(market="rush_yds"),
                       lambda m: m != "rush_yds")
    assert shut is not None, "a shut market must still be rankable"
    assert shut["bettable"] is False
    open_ = K.from_prop(_prop(market="receptions"), _always)
    assert open_["bettable"] is True


def test_the_row_carries_the_measurement_that_justifies_it():
    """A reader should be able to ask "how good is this ordering" and get
    a number rather than a tone of voice."""
    row = K.from_prop(_prop(market="rush_yds"), _always)
    assert row["rank_auc"] == K.RANK_AUC["rush_yds"]


# --- the ordering --------------------------------------------------------
def test_ranked_by_probability_and_by_nothing_else():
    """Sorting by EV, or breaking ties on it, would quietly rebuild the
    edge board under a different name — the exact failure this page
    exists to correct."""
    rows = [_prop(player="Low", prob=0.42, ev_per_unit=0.40),
            _prop(player="High", prob=0.71, ev_per_unit=-0.10),
            _prop(player="Mid", prob=0.55, ev_per_unit=0.20)]
    board = K.build(rows, [], [], sport="nfl")
    assert [r["player"] for r in board] == ["High", "Mid", "Low"], board
    # The juiciest EV on the slate is LAST, which is the whole point.
    assert board[-1]["player"] == "Low"


def test_a_long_shot_pick_and_its_watch_row_are_not_shown_twice():
    board = K.build([], [_watch()], [_watch()], sport="nfl")
    assert len(board) == 1, board


def test_touchdowns_and_yardage_rank_against_each_other():
    """One list, not two stacked. A 71% receiving over outranks a 58%
    scorer and has to say so."""
    board = K.build([_prop(player="Wideout", prob=0.71)],
                    [], [_watch(player="Back", prob=0.58)], sport="nfl")
    assert [r["player"] for r in board] == ["Wideout", "Back"], board


# --- what never reaches it ----------------------------------------------
def test_a_proxy_price_is_not_a_likelihood():
    assert K.from_prop(_prop(has_market=False), _always) is None


def test_a_stale_or_absurd_price_is_refused():
    assert K.from_prop(_prop(odds=9000), _always) is None
    assert K.from_prop(_prop(odds=None), _always) is None


def test_a_coin_flip_is_not_likely_however_it_ranks():
    """The page is called Most Likely. A 31% shot at the top of a thin
    slate is still not something to tell somebody is likely."""
    assert K.from_prop(_prop(prob=0.12), _always) is None
    assert K.MIN_PROB >= 0.30


def test_a_missing_probability_never_becomes_a_zero():
    assert K.from_prop(_prop(prob=None), _always) is None
    board = K.build([], [], [dict(_watch(), model_prob=None)], sport="nfl")
    assert board == []


# --- what the page says about itself -------------------------------------
def test_the_summary_counts_rather_than_asserts():
    board = K.build([_prop(market="rush_yds")], [], [_watch()], sport="nfl")
    got = K.summary(board)
    assert got["rows"] == len(board)
    assert got["bettable"] + got["rank_only"] == got["rows"]
    assert sum(got["by_market"].values()) == got["rows"]


def test_the_board_is_capped_so_it_stays_a_ranking():
    rows = [_prop(player=f"P{i}", prob=0.9 - i / 1000.0) for i in range(200)]
    assert len(K.build(rows, [], [], sport="nfl")) == K.LIMIT


def test_the_page_is_paid_because_it_is_the_product():
    from engine.gate import PAID_KEYS
    assert "most_likely" in PAID_KEYS, \
        "the main board is the thing somebody is paying for"


def test_both_football_boards_publish_it():
    """A sport that published an empty one would read as broken rather
    than as narrow, and college prices touchdowns and nothing else."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "cfb_build.py")).read()
    assert '"most_likely"' in src
    pipe = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "pipeline.py")).read()
    assert '"most_likely"' in pipe


def test_the_second_board_never_costs_the_first_one():
    """It is an additional view of rows that are already published. If it
    cannot be assembled the page renders empty rather than the slate
    failing to build."""
    import inspect
    from engine import pipeline
    src = inspect.getsource(pipeline._likely_board)
    assert "except Exception" in src and "return []" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
