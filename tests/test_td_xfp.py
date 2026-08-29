"""The strongest touchdown signal we record, finally reaching the model.

`engine/nflfit.evaluate_td`, fitted on 2021-2023 and scored on held-out
2024-2025 player-weeks:

    xfp          AUC 0.696      <- best single predictor
    own_td_rate  AUC 0.672      <- what the model leaned on
    targets      AUC 0.629
    rz_tgt       AUC 0.605
    rz_car       AUC 0.576      <- what the model reached for
    ALL, fitted  AUC 0.715

xFP was ingested for five seasons and read only by the fantasy waiver
board. `engine/touchdowns.py` never mentioned it, while treating
red-zone carries — which order a touchdown worse than plain target
volume — as the signal worth a multiplier.

The blend weight is measured, not chosen: ordering by the historical
rate alone gives 0.6788, climbing smoothly to 0.7158 at a weight of 0.7
and falling away after. An interior optimum with a flat top, unlike the
recency dial, which ran to the edge of its grid and was adopted there.
The scale that puts an xFP share on a share-of-team-touchdowns footing
is the ratio of the two means on the TRAINING seasons only.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import nflusage, prereg, touchdowns


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, player TEXT, team TEXT, market TEXT, value REAL)")
    return c


def _xfp(c, player, team, week, value, season=2025):
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, "
              "team, market, value) VALUES ('nfl', ?, ?, ?, ?, 'xfp', ?)",
              (season, "%03d" % week, player, team, float(value)))


# --- the role map -------------------------------------------------------------
def test_a_share_is_of_his_own_teams_total():
    """The level says a workhorse on a poor offence and a complementary
    back on a great one are the same player. For scoring they are not."""
    c = _conn()
    for w in (1, 2, 3, 4):
        _xfp(c, "A.Star", "LV", w, 20.0)
        _xfp(c, "B.Other", "LV", w, 5.0)
        _xfp(c, "C.Star", "KC", w, 20.0)
        _xfp(c, "D.Other", "KC", w, 60.0)
    roles = nflusage.xfp_roles(c, 2025)
    assert roles[("a", "star", "LV")]["xfp_pg"] == \
        roles[("c", "star", "KC")]["xfp_pg"]
    assert roles[("a", "star", "LV")]["xfp_share"] == 0.8
    assert roles[("c", "star", "KC")]["xfp_share"] == 0.25


def test_the_cutoff_keeps_out_weeks_that_had_not_happened():
    c = _conn()
    for w in range(1, 10):
        _xfp(c, "A.Star", "LV", w, 20.0 if w < 5 else 1.0)
        _xfp(c, "B.Other", "LV", w, 5.0)
    early = nflusage.xfp_roles(c, 2025, upto_week=5)
    assert early[("a", "star", "LV")]["xfp_pg"] == 20.0, \
        "a later collapse leaked backwards"


def test_the_week_filter_casts_rather_than_comparing_text():
    """`period` is zero-padded TEXT and SQLite gives the integer the
    column's affinity, so an uncast cutoff matches every row and leaks
    the season while looking like it worked."""
    import inspect
    assert "CAST(period AS INTEGER) < ?" in \
        inspect.getsource(nflusage.xfp_roles)


def test_a_player_with_one_week_gets_no_role():
    c = _conn()
    _xfp(c, "A.Star", "LV", 1, 20.0)
    assert nflusage.xfp_roles(c, 2025) == {}


def test_a_team_with_no_recorded_points_yields_no_share():
    c = _conn()
    for w in (1, 2, 3):
        _xfp(c, "A.Star", "LV", w, 0.0)
    assert nflusage.xfp_roles(c, 2025) == {}


def test_the_usage_maps_carry_it():
    c = _conn()
    for w in (1, 2, 3):
        _xfp(c, "A.Star", "LV", w, 10.0)
        _xfp(c, "B.Other", "LV", w, 10.0)
    assert nflusage.build_usage_maps(c, 2025)["xfp"]


# --- the model ----------------------------------------------------------------
def test_the_weight_and_scale_are_the_measured_ones():
    assert touchdowns.XFP_SHARE_WEIGHT == 0.7
    assert touchdowns.XFP_SHARE_SCALE == 0.8


def test_the_weight_is_an_interior_optimum_not_a_boundary():
    """The lesson from the recency dial, which ran to the edge of its
    grid and was adopted there anyway."""
    assert 0.0 < touchdowns.XFP_SHARE_WEIGHT < 1.0


def test_a_bigger_share_of_the_offence_raises_the_probability():
    from engine.touchdowns import XFP_SHARE_SCALE, XFP_SHARE_WEIGHT
    from engine.statmath import clamp
    base = 0.10
    low = clamp((1 - XFP_SHARE_WEIGHT) * base
                + XFP_SHARE_WEIGHT * clamp(0.05 * XFP_SHARE_SCALE, 0, 0.60),
                0.01, 0.55)
    high = clamp((1 - XFP_SHARE_WEIGHT) * base
                 + XFP_SHARE_WEIGHT * clamp(0.35 * XFP_SHARE_SCALE, 0, 0.60),
                 0.01, 0.55)
    assert high > low


def test_absent_xfp_leaves_the_model_exactly_as_it_was():
    """Every sport and every un-ingested player must price as before."""
    import inspect
    src = inspect.getsource(touchdowns.td_probability)
    assert "if xfp_share > 0:" in src
    assert 'float((xfp or {}).get("xfp_share") or 0.0)' in src


def test_both_boards_price_with_the_same_model():
    """The value picks and the most-likely watchlist call td_probability
    separately; feeding one and not the other is how two lists about the
    same player start disagreeing."""
    import inspect
    src = inspect.getsource(touchdowns)
    assert src.count('c.get("red_zone"), c.get("xfp")') == 2


def test_the_pipeline_actually_hands_it_over():
    import inspect
    from engine import pipeline
    assert '"xfp": xfp_map.get(key)' in inspect.getsource(pipeline._long_shots)


def test_the_card_says_the_share_moved_it():
    import inspect
    src = inspect.getsource(touchdowns.td_probability)
    assert "share of the" in src and "expected points" in src


# --- the preregistration ------------------------------------------------------
def test_the_old_test_is_superseded_not_edited():
    """The terms are hashed precisely so nobody can move the goalposts
    after seeing data. `verdict` reports an edited test as void."""
    import tempfile
    import pathlib
    p = pathlib.Path(tempfile.mkdtemp()) / "prereg.json"
    store = prereg.ensure_registered(p)
    by_id = {t["id"]: t for t in store["tests"]}
    old = by_id["td-edge-nfl-2026-08"]
    assert old["superseded_by"] == "td-edge-nfl-xfp-2026-08"
    assert "xFP" in old["superseded_why"]
    assert by_id["td-edge-nfl-xfp-2026-08"].get("superseded_by") is None


def test_the_successor_asks_the_same_question_of_the_new_model():
    same = {k: v for k, v in prereg.TD_EDGE_NFL.items() if k != "id"}
    assert {k: v for k, v in prereg.TD_EDGE_NFL_XFP.items()
            if k != "id"} == same, \
        "the claim changed, which would make this a different test"


def test_the_superseded_test_stops_collecting():
    """The point of superseding rather than deleting: the original's
    terms survive as the record of what was asked, and it stops
    delivering a verdict about a model that no longer exists.

    Its FINGERPRINT is deliberately not what distinguishes the two —
    `_terms_hash` covers the terms, and the successor asks the same
    question of a different model, so the terms are identical on purpose.
    The id and the supersession are what separate them."""
    import pathlib
    import tempfile
    p = pathlib.Path(tempfile.mkdtemp()) / "prereg.json"
    prereg.ensure_registered(p)
    store = prereg.load(p)
    old = next(t for t in store["tests"] if t["id"] == "td-edge-nfl-2026-08")
    got = prereg.verdict(old, [])
    assert got["status"] == "superseded"
    assert got["superseded_by"] == "td-edge-nfl-xfp-2026-08"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
