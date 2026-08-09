"""The Correlation Engine (docs/NFL_MODEL.md §9) and the §10 exposure caps.

Correlated bets are one bet wearing two jerseys: the engine must SAY so on
both cards, must reject incoherent pairs outright (QB Under next to his
receiver's Over), and must count correlated stakes together against the
5u-per-game / 15u-per-slate circuit breakers.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def test_the_whole_board_is_scaled_by_ONE_factor():
    """THE PROPERTY THE POLICY EXISTS FOR, and the only one that makes it
    safe without a trustworthy ranking: scaling every stake by the same
    number cannot change ROI, because net and staked move together.

    THIS TEST HAS NOW BEEN REWRITTEN TWICE, which is the honest record of
    how the decision went. It first asserted the survivors summed to
    exactly the cap (proportional per-game scaling). Then it asserted the
    survivors kept full size (trim the weakest). Measured against 888
    settled bets, per-game scaling cost ten points of ROI by reweighting
    the book, and trimming backtested worse still — the 128 bets it keeps
    returned -11.33% while the 443 it drops returned +9.14%.

    So the invariant is neither of those. It is that the RATIOS between
    surviving stakes are exactly the ratios Kelly asked for."""
    rows = [_rec("Big", "KC", "LV", "receptions", "OVER", stake=2.0),
            _rec("Mid", "KC", "LV", "receptions", "OVER", stake=1.0),
            _rec("Small", "BUF", "MIA", "receptions", "OVER", stake=1.0)]
    for i in range(10):                       # push the slate over 15u
        rows.append(_rec(f"F{i}", f"X{i}", f"Y{i}", "receptions", "OVER",
                         stake=2.0))
    before = {r["player"]: r["stake_units"] for r in rows}
    apply_exposure_caps(rows, [])
    kept = {r["player"]: r["stake_units"] for r in rows if r["recommended"]}
    # Recover the factor from any survivor and hold EVERY other survivor
    # to it. Asserting the ratios directly looks equivalent and is weaker:
    # stakes are rounded to 0.01u for display (a bet slip has no fourth
    # decimal), so Big/Mid came back 2.016 rather than 2.0 and the exact
    # comparison failed on the rounding rather than on the property.
    factor = kept["Big"] / before["Big"]
    for name, stake in kept.items():
        assert abs(stake - round(before[name] * factor, 2)) <= 0.005, \
            f"{name} was not scaled by the same factor as the rest"
    assert kept["Mid"] == kept["Small"], "equal stakes came out unequal"


def test_a_stake_scaled_under_the_floor_comes_off_the_board():
    """The 0.047u bet Ethan found. A scale factor and a floor cannot both
    be honoured by arithmetic, so the bets that fall through it are
    dropped — never rounded back up, which would break the cap, and never
    placed, which is what shipped."""
    from engine.staking import MIN_STAKE_UNITS
    rows = [_rec(f"F{i}", f"X{i}", f"Y{i}", "receptions", "OVER", stake=2.0)
            for i in range(10)]
    rows.append(_rec("Tiny", "KC", "LV", "receptions", "OVER", stake=0.1))
    apply_exposure_caps(rows, [])
    tiny = [r for r in rows if r["player"] == "Tiny"][0]
    assert tiny["recommended"] is False, "a sub-floor stake was placed"
    for r in rows:
        if r["recommended"]:
            assert r["stake_units"] >= MIN_STAKE_UNITS, r


def test_a_dropped_bet_leaves_the_board_rather_than_lingering_at_zero():
    """A bet still marked recommended with a zero stake is journaled,
    graded into the win-loss record, and contributes nothing to P&L — it
    moves the record without moving the money. Same treatment as the
    incoherent-pair rejection, which is the other place a bet is taken
    off."""
    rows = [_rec(f"F{i}", f"X{i}", f"Y{i}", "receptions", "OVER", stake=2.0)
            for i in range(10)]
    rows.append(_rec("Tiny", "KC", "LV", "receptions", "OVER", stake=0.1))
    apply_exposure_caps(rows, [])
    for r in rows:
        if not r["recommended"]:
            assert r["stake_units"] == 0.0
            assert r["grade"] == "Pass"
            assert r.get("warnings"), "dropped with no reason given"


def test_the_cap_does_not_sort_on_the_model_grade():
    """DELIBERATE, and the reason this policy was chosen. Whether A+
    outperforms B+ is an open question as of 2026-08-08 — the trim replay
    suggested it may be inverted. A cap rule that reads the grade bets on
    the answer; this one does not have to."""
    src = open(os.path.join(ROOT, "engine", "correlation.py"),
               encoding="utf-8").read()
    i = src.index("def _uniform_factor(")
    body = src[i:src.index("\ndef ", i + 10)]
    # THE DOCSTRING COMES OUT FIRST. That docstring explains at length
    # why the factor must not read the grade — so scanning the raw text
    # for "grade" matched the explanation and failed on the correct file.
    # Same wrong-occurrence trap that has bitten every string-scanning
    # test in this repo; the fix is always to scan the thing meant.
    body = re.sub(r'""".*?"""', "", body, flags=re.S)
    # Not just the helper names — the FIELDS. A mutation that read
    # `r.get("grade")` directly slipped past a check for `_GRADE_RANK`,
    # which guards the spelling of a bug rather than the bug.
    # `sorted(` is deliberately NOT here: the factor sorts two team
    # abbreviations to name a game in a note. Forbidding it would be
    # banning a word rather than a behaviour, and the guard below is
    # about which FIELDS of a bet the factor is allowed to see.
    for token in ("_GRADE_RANK", "quality", "grade", "edge", "_strength"):
        assert token not in body, f"the cap is reading {token} again"


def test_a_slate_inside_its_caps_is_left_completely_alone():
    """The caps are circuit breakers. A quiet night must come out the far
    side byte-identical, or every stake on the board is a cap artefact."""
    rows = [_rec("P1", "KC", "LV", "receptions", "OVER", stake=1.0),
            _rec("P2", "BUF", "MIA", "receptions", "OVER", stake=0.5)]
    before = [dict(r) for r in rows]
    assert apply_exposure_caps(rows, []) == []
    assert rows == before


def test_the_most_binding_cap_is_the_one_that_applies():
    """Game and slate caps are both hard limits; satisfying one is not
    satisfying the other. The factor is the smaller of the two."""
    rows = [_rec(f"P{i}", "KC", "LV", "receptions", "OVER", stake=2.5)
            for i in range(4)]                      # 10u in ONE game
    apply_exposure_caps(rows, [])
    total = sum(r["stake_units"] for r in rows if r["recommended"])
    assert total <= GAME_CAP_U + 0.01, total


def test_slate_cap_counts_game_bets_too():
    recs = [_rec(f"P{i}", t, o, "receptions", "OVER", stake=4.0)
            for i, (t, o) in enumerate([("KC", "LV"), ("BUF", "MIA"),
                                        ("DAL", "NYG"), ("SF", "SEA")])]
    bets = [{"home": "GB", "away": "CHI", "date": "2026-09-13",
             "recommended": True, "stake_units": 4.0}]
    notes = apply_exposure_caps(recs, bets)
    live = ([r for r in recs if r["recommended"]]
            + [b for b in bets if b["recommended"]])
    assert sum(r["stake_units"] for r in live) <= SLATE_CAP_U + 0.01
    assert len(live) == 5, "the slate cap dropped a bet it only had to scale"
    assert notes and "Exposure cap" in notes[0]


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
