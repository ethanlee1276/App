"""The Correlation Engine (docs/NFL_MODEL.md §9) and the §10 exposure caps.

Correlated bets are one bet wearing two jerseys: the engine must SAY so on
both cards, must reject incoherent pairs outright (QB Under next to his
receiver's Over), and must count correlated stakes together against the
5u-per-game / 15u-per-slate circuit breakers.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.correlation import (flag_correlations, apply_exposure_caps,
                                GAME_CAP_U, SLATE_CAP_U)


def _rec(player, team, opp, market, side, quality=80, stake=0.5, rec=True):
    return {"player": player, "team": team, "opponent": opp, "market": market,
            "market_label": market, "side": side, "quality": quality,
            "stake_units": stake, "recommended": rec, "game_date": "2026-09-13"}


def test_qb_and_his_receiver_same_side_is_flagged_positive():
    qb = _rec("QB One", "KC", "LV", "pass_yds", "OVER")
    wr = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    out = flag_correlations([qb, wr])
    assert out["pairs_flagged"] == 1 and out["pairs_rejected"] == 0
    assert any("combined exposure" in c for c in qb["correlations"])
    assert any("WR One" in c for c in qb["correlations"])
    assert any("QB One" in c for c in wr["correlations"])
    assert qb["recommended"] and wr["recommended"]


def test_incoherent_pairing_rejects_the_lower_grade():
    # QB Under + his WR Over describe contradictory passing games.
    qb = _rec("QB One", "KC", "LV", "pass_yds", "UNDER", quality=84)
    wr = _rec("WR One", "KC", "LV", "receptions", "OVER", quality=73)
    out = flag_correlations([qb, wr])
    assert out["pairs_rejected"] == 1
    assert wr["recommended"] is False and wr["grade"] == "Pass"
    assert wr["stake_units"] == 0.0
    assert any("Incoherent" in w for w in wr["warnings"])
    assert qb["recommended"] is True          # the higher grade survives


def test_two_receivers_one_ball_is_mildly_negative():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Two", "KC", "LV", "receptions", "OVER")
    flag_correlations([a, b])
    assert any("one ball" in c for c in a["correlations"])
    assert a["recommended"] and b["recommended"]      # flagged, not rejected


def test_cross_team_overs_are_pace_linked():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Away", "LV", "KC", "rec_yds", "OVER")
    flag_correlations([a, b])
    assert any("Pace-linked" in c for c in a["correlations"])


def test_different_games_never_flag():
    a = _rec("WR One", "KC", "LV", "rec_yds", "OVER")
    b = _rec("WR Two", "BUF", "MIA", "rec_yds", "OVER")
    out = flag_correlations([a, b])
    assert out["pairs_flagged"] == 0
    assert "correlations" not in a and "correlations" not in b


def test_a_game_over_its_cap_drops_bets_instead_of_shrinking_them():
    """CHANGED 2026-08-08, and this test changed with it.

    It used to assert the surviving stakes summed to EXACTLY the cap,
    which is what proportional scaling guarantees and is precisely the
    behaviour that had to go. Ethan found the cost of it on the board: a
    +106 winner returned 0.05u because it had been staked 0.047u — below
    `staking.MIN_STAKE_UNITS`, a number the sizing path cannot emit. The
    caps were re-rounding stakes after the floor had been applied.

    The invariant now is an inequality, not an equality: the kept bets fit
    inside the cap AT THE SIZE KELLY ASKED FOR. Hitting the cap exactly is
    not a property worth having if the way you hit it is by making every
    bet the wrong size."""
    rows = [_rec(f"P{i}", "KC", "LV", "receptions", "OVER", stake=2.0)
            for i in range(4)]                    # 8u in one game
    notes = apply_exposure_caps(rows, [])
    kept = [r for r in rows if r["recommended"]]
    assert sum(r["stake_units"] for r in kept) <= GAME_CAP_U
    assert kept, "the cap emptied the game"
    assert all(r["stake_units"] == 2.0 for r in kept), \
        "a surviving bet was resized"
    assert any("Game cap" in n for n in notes)


def test_a_dropped_bet_leaves_the_board_rather_than_lingering_at_zero():
    """A bet still marked recommended with a zero stake is journaled,
    graded into the win-loss record, and contributes nothing to P&L — it
    moves the record without moving the money. Same treatment as the
    incoherent-pair rejection, which is the other place a bet is taken
    off."""
    rows = [_rec(f"P{i}", "KC", "LV", "receptions", "OVER", stake=2.0)
            for i in range(4)]
    apply_exposure_caps(rows, [])
    for r in rows:
        if not r["recommended"]:
            assert r["stake_units"] == 0.0
            assert r["grade"] == "Pass"
            assert r.get("warnings"), "dropped with no reason given"


def test_the_weakest_bets_are_the_ones_dropped():
    """The entire argument for trimming over scaling. If the cap dropped
    arbitrary bets it would be worse than scaling, not better."""
    rows = []
    for i, q in enumerate((9.0, 3.0, 8.0, 4.0)):
        r = _rec(f"P{i}", "KC", "LV", "receptions", "OVER", stake=2.0)
        r["quality"] = q
        rows.append(r)
    apply_exposure_caps(rows, [])
    kept = {r["player"] for r in rows if r["recommended"]}
    assert kept == {"P0", "P2"}, kept


def test_a_slate_inside_its_caps_is_left_completely_alone():
    """The caps are circuit breakers. A quiet night must come out the far
    side byte-identical, or every stake on the board is a cap artefact."""
    rows = [_rec("P1", "KC", "LV", "receptions", "OVER", stake=1.0),
            _rec("P2", "BUF", "MIA", "receptions", "OVER", stake=0.5)]
    before = [dict(r) for r in rows]
    assert apply_exposure_caps(rows, []) == []
    assert rows == before


def test_slate_cap_counts_game_bets_too():
    recs = [_rec(f"P{i}", t, o, "receptions", "OVER", stake=4.0)
            for i, (t, o) in enumerate([("KC", "LV"), ("BUF", "MIA"),
                                        ("DAL", "NYG"), ("SF", "SEA")])]
    bets = [{"home": "GB", "away": "CHI", "date": "2026-09-13",
             "recommended": True, "stake_units": 4.0}]
    notes = apply_exposure_caps(recs, bets)
    live = ([r for r in recs if r["recommended"]]
            + [b for b in bets if b["recommended"]])
    assert sum(r["stake_units"] for r in live) <= SLATE_CAP_U
    assert all(r["stake_units"] == 4.0 for r in live), "a survivor was resized"
    assert any("Slate cap" in n for n in notes)


def test_the_strongest_bet_is_never_dropped_by_a_cap():
    """A cap that can empty the board is a bug wearing a risk control's
    clothes. If one bet alone busts the cap it is clamped to it, not
    deleted."""
    lone = _rec("Solo", "KC", "LV", "receptions", "OVER", stake=40.0)
    apply_exposure_caps([lone], [])
    assert lone["recommended"] is True
    assert lone["stake_units"] == GAME_CAP_U


def test_non_recommended_rows_are_ignored_by_caps():
    rows = [_rec("P1", "KC", "LV", "receptions", "OVER", stake=2.0),
            _rec("P2", "KC", "LV", "receptions", "OVER", stake=9.0, rec=False)]
    notes = apply_exposure_caps(rows, [])
    assert notes == []                     # 2u recommended — no cap tripped
    assert rows[1]["stake_units"] == 9.0   # untouched: it isn't a bet


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
