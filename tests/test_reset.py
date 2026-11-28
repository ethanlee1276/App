"""The reset rule — discarding a sample that describes a dead role.

§5 of the spec is unusually forceful about this, and it is the one
recency instruction that is not a weighting:

    A coordinator change, a new starter, or a traded player *resets the
    sample*. Weight post-change games at nearly 100% and discard the
    stale data entirely, even if the sample is small. Three games in the
    real current role beat twelve games in a role that no longer exists.

Shading is right for a player whose role is stable and whose production
drifts. It is exactly wrong for a receiver traded in week 13: those
eleven games with his old team are not older evidence of the same thing,
they are evidence about a different job, and averaging them in at any
weight imports a number that cannot happen again.

The tests cover the three triggers the data actually supports, the
precedence between them, and the one place this deliberately stops short
of the spec — a post-reset sample of one game is an outlier machine, so
below the floor the logs are kept and the card warns instead.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, reset
from engine.models import GameLog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log(player, team, wk, market="snap_pct", value=0.8, season=2026):
    return {"sport": "nfl", "season": season, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
            "opponent": "OPP", "position": "WR", "home": 1,
            "market": market, "value": value}


def _sched(team, week, coach, season=2026, opp="OPP"):
    return {"season": str(season), "week": str(week), "game_type": "REG",
            "home_team": team, "away_team": opp,
            "home_coach": coach, "away_coach": "Someone Else"}


class _Prop:
    def __init__(self, player, team, weeks):
        self.player, self.team = player, team
        self.logs = [GameLog(week=w, opponent="X", value=50.0 + w)
                     for w in weeks]


class _Slate:
    def __init__(self, props):
        self.props = props


# --- the three triggers ------------------------------------------------------
def test_a_mid_season_coach_change_is_read_off_the_schedule():
    rows = ([_sched("CAR", w, "Frank Reich") for w in range(1, 13)]
            + [_sched("CAR", w, "Chris Tabor") for w in range(13, 18)])
    out = reset.coach_changes(rows, 2026)
    assert out["CAR"] == (13, "Frank Reich", "Chris Tabor")


def test_the_last_coach_change_of_a_season_is_the_one_that_governs():
    rows = ([_sched("XYZ", w, "First") for w in range(1, 6)]
            + [_sched("XYZ", w, "Second") for w in range(6, 12)]
            + [_sched("XYZ", w, "Third") for w in range(12, 18)])
    assert reset.coach_changes(rows, 2026)["XYZ"][0] == 12


def test_a_stable_coach_is_not_a_reset():
    rows = [_sched("KC", w, "Andy Reid") for w in range(1, 18)]
    assert reset.coach_changes(rows, 2026) == {}


def test_a_players_team_change_is_read_off_his_own_logs():
    """Whatever the paperwork said, a player appearing with a new team HAS
    moved — and that is the fact the projection cares about."""
    conn = db.connect(":memory:")
    db.upsert_player_logs(
        conn, [_log("Traded Man", "MIN", w) for w in range(1, 14)]
        + [_log("Traded Man", "PIT", w) for w in range(14, 18)]
        + [_log("Stayed Put", "GB", w) for w in range(1, 18)])
    moves = reset.player_moves(conn, 2026)
    assert moves["Traded Man"] == (14, "MIN", "PIT")
    assert "Stayed Put" not in moves


def test_a_sustained_snap_promotion_is_a_new_starter():
    conn = db.connect(":memory:")
    rows = ([_log("Backup", "NYJ", w, value=0.15) for w in range(1, 9)]
            + [_log("Backup", "NYJ", w, value=0.80) for w in range(9, 15)])
    db.upsert_player_logs(conn, rows)
    week, before, after = reset.role_shifts(conn, 2026)["Backup"]
    assert week == 9 and before < 0.35 and after > 0.55


def test_a_demotion_counts_too():
    conn = db.connect(":memory:")
    rows = ([_log("Benched", "NYJ", w, value=0.85) for w in range(1, 9)]
            + [_log("Benched", "NYJ", w, value=0.10) for w in range(9, 15)])
    db.upsert_player_logs(conn, rows)
    assert reset.role_shifts(conn, 2026)["Benched"][0] == 9


def test_ordinary_snap_noise_is_not_a_role_change():
    """A rotational player having a busy afternoon must not reset a season."""
    conn = db.connect(":memory:")
    import random
    rng = random.Random(3)
    db.upsert_player_logs(conn, [
        _log("Steady", "NYJ", w, value=round(0.60 + rng.uniform(-.08, .08), 2))
        for w in range(1, 16)])
    assert "Steady" not in reset.role_shifts(conn, 2026)


# --- precedence --------------------------------------------------------------
def test_the_latest_reset_wins_and_collapses_the_double_count():
    """A receiver traded in week 13 whose snaps then jumped in week 15 is
    projecting from week 15 — and one move showing up as both a trade and
    a promotion must not count twice."""
    index = {"moves": {"Mover": (13, "MIN", "PIT")},
             "roles": {"Mover": (15, 0.23, 0.62)},
             "coaches": {}}
    week, kind, detail = reset.reset_for(index, "Mover", "PIT")
    assert week == 15 and kind == reset.ROLE
    assert "62%" in detail


def test_a_team_coach_change_reaches_every_player_on_that_team():
    index = {"moves": {}, "roles": {},
             "coaches": {"CAR": (13, "Frank Reich", "Chris Tabor")}}
    hit = reset.reset_for(index, "Any Receiver", "CAR")
    assert hit[0] == 13 and hit[1] == reset.COACH
    assert reset.reset_for(index, "Any Receiver", "KC") is None


def test_a_player_with_no_reset_gets_none():
    assert reset.reset_for({"moves": {}, "roles": {}, "coaches": {}},
                           "Nobody", "KC") is None


# --- the truncation ----------------------------------------------------------
def _conn_with_move(move_week=14):
    conn = db.connect(":memory:")
    db.upsert_player_logs(
        conn, [_log("Traded Man", "MIN", w) for w in range(1, move_week)]
        + [_log("Traded Man", "PIT", w) for w in range(move_week, 18)])
    return conn


def test_the_stale_games_are_actually_discarded():
    slate = _Slate([_Prop("Traded Man", "PIT", list(range(1, 18)))])
    rep = reset.apply_to_slate(slate, _conn_with_move(14), 2026, [])
    kept = slate.props[0].logs
    assert all(g.week >= 14 for g in kept), "a pre-trade game survived"
    assert len(kept) == 4
    e = rep["reset"]["Traded Man"]
    assert e["kind"] == reset.TRADE and e["dropped"] == 13


def test_a_thin_post_reset_sample_is_kept_and_flagged_instead():
    """The one deliberate step short of the spec: 'even if the sample is
    small' is right down to about three games; at one it stops being a
    small sample and becomes an outlier machine."""
    slate = _Slate([_Prop("Traded Man", "PIT", list(range(1, 18)))])
    rep = reset.apply_to_slate(slate, _conn_with_move(17), 2026, [])
    assert len(slate.props[0].logs) == 17, "a one-game sample was trusted"
    assert "Traded Man" not in rep["reset"]
    assert rep["held"]["Traded Man"]["kept"] < reset.MIN_POST_RESET


def test_a_player_without_a_reset_keeps_every_game():
    slate = _Slate([_Prop("Stayed Put", "GB", list(range(1, 18)))])
    rep = reset.apply_to_slate(slate, _conn_with_move(), 2026, [])
    assert len(slate.props[0].logs) == 17
    assert not rep["reset"] and not rep["held"]


def test_a_coach_change_truncates_the_whole_roster():
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [_log("Carolina Guy", "CAR", w)
                                 for w in range(1, 18)])
    sched = ([_sched("CAR", w, "Frank Reich") for w in range(1, 13)]
             + [_sched("CAR", w, "Chris Tabor") for w in range(13, 18)])
    slate = _Slate([_Prop("Carolina Guy", "CAR", list(range(1, 18)))])
    rep = reset.apply_to_slate(slate, conn, 2026, sched)
    assert rep["reset"]["Carolina Guy"]["kind"] == reset.COACH
    assert all(g.week >= 13 for g in slate.props[0].logs)


# --- what the card says ------------------------------------------------------
def test_a_reset_is_explained_and_a_stale_sample_is_warned():
    recs = [{"player": "Traded Man", "reasons": [], "warnings": []},
            {"player": "Thin Sample", "reasons": [], "warnings": []},
            {"player": "Untouched", "reasons": [], "warnings": []}]
    rep = {"reset": {"Traded Man": {"week": 14, "kind": reset.TRADE,
                                    "detail": "joined PIT from MIN",
                                    "kept": 4, "dropped": 13}},
           "held": {"Thin Sample": {"week": 17, "kind": reset.TRADE,
                                    "detail": "joined BUF from NO",
                                    "kept": 1, "dropped": 16}}}
    assert reset.decorate(recs, rep) == 2
    assert "Sample reset" in recs[0]["reasons"][0]
    assert "discarding 13" in recs[0]["reasons"][0]
    assert not recs[0]["warnings"]
    assert "Stale sample" in recs[1]["warnings"][0]
    assert not recs[2]["reasons"] and not recs[2]["warnings"]


def test_the_build_applies_the_rule_before_anything_projects():
    """Truncating after the projection would be theatre — the logs have to
    be cut before build_projection ever reads them."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "reset.apply_to_slate" in src or "_reset.apply_to_slate" in src
    assert src.index("apply_to_slate") < src.index("result = run_slate")
    assert "_reset.decorate" in src


def test_a_missing_history_db_leaves_the_build_standing():
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("apply_to_slate")
    assert "Reset rule skipped" in src[i:i + 1200]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
