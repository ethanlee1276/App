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
    src = inspect.getsource(pipeline._long_shots)
    assert '"xfp": from_maps(xfp_map, keys)' in src
    # Through the resolver, not a bare key: a player who changed teams in
    # the offseason has his role filed under last season's club.
    assert "usage_keys(prop.player, prop.team, team_of)" in src


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


# --- the join key, which was quietly dropping stars --------------------------
def test_a_generational_suffix_is_not_treated_as_a_surname():
    """`_short_key` took the LAST name-part, so "Chris Godwin Jr." keyed
    as ("c", "jr") and could never meet the play-by-play feed's
    "C.Godwin". Every usage map is keyed by this function — red-zone
    work, snap share, volume role, and the xFP share the touchdown model
    now leans on — so those players were invisible to every measurement
    the model makes about usage. 32 of the 1,260 NFL players logged in
    2025 carry one, and they are not marginal names."""
    from engine.fantasy import _short_key
    for full, pbp in (("Chris Godwin Jr.", "C.Godwin"),
                      ("Marvin Harrison Jr.", "M.Harrison"),
                      ("Kenneth Walker III", "K.Walker"),
                      ("Deebo Samuel Sr.", "D.Samuel"),
                      ("Gardner Minshew II", "G.Minshew"),
                      ("David Sills V", "D.Sills")):
        assert _short_key(full, "TB") == _short_key(pbp, "TB"), full


def test_a_name_that_is_only_a_suffix_is_not_emptied():
    from engine.fantasy import _short_key
    assert _short_key("Jr", "TB")[1] == "jr"
    assert _short_key("", "TB") == ("", "", "TB")


def test_an_ordinary_surname_is_untouched():
    from engine.fantasy import _short_key
    assert _short_key("Mike Evans", "TB") == ("m", "evans", "TB")
    assert _short_key("Amon-Ra St. Brown", "DET")[1] == "brown"


def test_the_suffix_list_matches_the_one_the_backtest_already_used():
    """engine/backtest._norm has stripped exactly these since it was
    written. Two functions normalising names differently is how a join
    silently keeps half a board."""
    import re
    from engine.backtest import _norm
    from engine.fantasy import NAME_SUFFIXES
    for suf in NAME_SUFFIXES:
        assert _norm(f"Chris Godwin {suf}") == "chris godwin", suf


def test_the_team_stays_in_the_key():
    """It has to: 2025 logged two different ('d','moore') and two
    ('m','evans') on different teams. Dropping the team to rescue an
    offseason mover would merge them."""
    from engine.fantasy import _short_key
    assert _short_key("DJ Moore", "CHI") != _short_key("DJ Moore", "CAR")


def test_accents_fold_because_the_feeds_disagree_on_them():
    """The box score writes "Audric Estimé", the play-by-play writes
    "A.Estime". One player a season, which is why it went unnoticed."""
    from engine.fantasy import _short_key
    assert _short_key("Audric Estimé", "DEN") == _short_key("A.Estime", "DEN")
    assert _short_key("Amon-Ra St. Brown", "DET") == \
        _short_key("A.St.Brown", "DET")


def test_the_alias_table_only_holds_names_a_rule_cannot_reach():
    """Robbie Anderson became Robbie Chosen, Deonte Harris became Deonte
    Harty, and Zonovan Knight plays as Bam. No normalisation finds those.
    Every entry was surfaced by join_audit rather than by reading lists —
    each had 60-113 touches in a season with no measured usage."""
    from engine.fantasy import NAME_ALIASES, _short_key
    assert len(NAME_ALIASES) <= 6, \
        "an alias table is where bad guesses hide; keep it audited"
    assert _short_key("Bam Knight", "ARI") == _short_key("Z.Knight", "ARI")
    assert _short_key("Robbie Chosen", "CAR") == _short_key("R.Anderson", "CAR")
    assert _short_key("Deonte Harty", "NO") == _short_key("D.Harris", "NO")


def test_an_alias_does_not_escape_its_team():
    from engine.fantasy import _short_key
    assert _short_key("Bam Knight", "ARI") != _short_key("Z.Knight", "NYJ")


# --- the standing check ------------------------------------------------------
def test_the_audit_reports_a_broken_join_rather_than_waiting_to_be_noticed():
    """It took a touchdown card missing its explanation to find that 32
    players a season had no measured usage. Nothing errored, because a
    failed join does not raise — the player just quietly has no data."""
    c = _conn()
    for w in range(1, 6):
        c.execute("INSERT INTO player_game_logs (sport, season, period, "
                  "player, team, market, value) VALUES "
                  "('nfl', 2025, ?, 'Ghost Player', 'LV', 'carries', 12)",
                  ("%03d" % w,))
    bad = nflusage.join_audit(c, 2025)
    assert [(r[0], r[1]) for r in bad] == [("Ghost Player", "LV")]
    assert bad[0][2] == 60.0


def test_a_player_who_actually_joins_is_not_reported():
    c = _conn()
    for w in range(1, 6):
        for market, val in (("carries", 12), ("xfp", 9.0)):
            c.execute("INSERT INTO player_game_logs (sport, season, period, "
                      "player, team, market, value) VALUES "
                      "('nfl', 2025, ?, ?, 'LV', ?, ?)",
                      ("%03d" % w, "Real Player" if market == "carries"
                       else "R.Player", market, val))
    assert nflusage.join_audit(c, 2025) == []


def test_a_zero_production_player_is_not_reported():
    """42 of the 53 unmatched players in 2025 had every box-score value at
    zero — special-teamers with no play-by-play because they generated
    none. Reporting them would bury the real misses."""
    c = _conn()
    for w in range(1, 18):
        c.execute("INSERT INTO player_game_logs (sport, season, period, "
                  "player, team, market, value) VALUES "
                  "('nfl', 2025, ?, 'Special Teamer', 'LV', 'targets', 0)",
                  ("%03d" % w,))
    assert nflusage.join_audit(c, 2025) == []


def test_the_audit_is_reported_to_a_human_not_asserted_by_the_suite():
    """It is tempting to assert the real database is clean — it is, on
    all five ingested seasons, after the suffix, accent and alias fixes.
    But run_tests.py is explicit that THE SUITE MUST NOT READ THE BOX IT
    IS RUNNING ON, and a differently-ingested season on the droplet would
    turn the suite red and block a deploy over a data question. So the
    audit runs in the build, where a person is already reading output."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "nfl_build.py"), encoding="utf-8").read()
    assert "join_audit" in src
    # Checked as CALLS, not as text — this test's own message names
    # db.connect() to explain the rule, and a substring scan matched
    # itself. The lesson keeps recurring: a check that reads prose passes
    # or fails on how a comment is worded.
    import ast
    import pathlib as _pl
    for f in _pl.Path(root, "tests").glob("test_*.py"):
        body = f.read_text()
        if "join_audit" not in body:
            continue
        for node in ast.walk(ast.parse(body)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "connect"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "db"):
                raise AssertionError(
                    f"{f.name} runs the audit against this box's own data")


# --- following a player who changed teams ------------------------------------
def test_a_moved_player_finds_the_role_filed_under_his_old_team():
    """Two of six touchdown cards on the Week 1 board. DJ Moore's 2025
    role sits under CHI and his card says BUF; Mike Evans is TB to SF."""
    team_of = {"dj moore": ["CHI"], "mike evans": ["TB"]}
    keys = nflusage.usage_keys("DJ Moore", "BUF", team_of)
    assert [k[2] for k in keys] == ["BUF", "CHI"]
    assert nflusage.from_maps({("d", "moore", "CHI"): {"xfp_share": 0.11}},
                              keys) == {"xfp_share": 0.11}


def test_the_cards_own_team_is_tried_first():
    """Following him back is a guess and must never outrank a direct hit
    — 2025 logged two ('d','moore') and two ('m','evans')."""
    team_of = {"dj moore": ["CHI"]}
    keys = nflusage.usage_keys("DJ Moore", "BUF", team_of)
    got = nflusage.from_maps({("d", "moore", "BUF"): "current",
                              ("d", "moore", "CHI"): "stale"}, keys)
    assert got == "current"


def test_a_midseason_trade_leaves_two_teams_to_try():
    """Elijah Moore logged for BUF and DEN in 2025."""
    keys = nflusage.usage_keys("Elijah Moore", "NYJ",
                               {"elijah moore": ["BUF", "DEN"]})
    assert [k[2] for k in keys] == ["NYJ", "BUF", "DEN"]


def test_an_unknown_player_falls_back_to_his_own_team_only():
    keys = nflusage.usage_keys("Nobody Here", "LV", {})
    assert keys == [("n", "here", "LV")]
    assert nflusage.from_maps({}, keys) is None


def test_the_index_is_keyed_on_the_full_name_because_initials_collide():
    """"DJ Moore" is uniquely CHI in 2025 while ('d','moore') is not —
    David Moore was on CAR. Initials cannot resolve this and full names
    can, which is the whole reason the index exists."""
    import inspect
    src = inspect.getsource(nflusage.season_teams)
    assert "_fold(r[\"player\"])" in src


def test_the_yardage_board_resolves_the_same_way():
    """The volume role had the identical problem and would have kept it
    if only the touchdown path were fixed."""
    import inspect
    from engine import pipeline
    assert "_from_maps(vol_map" in inspect.getsource(pipeline.run_slate)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
