"""Tests for measured NFL roles: red-zone usage + snap shares from logs."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.ingest import snap_count_rows
from engine.nflusage import red_zone_usage, snap_shares, build_usage_maps


def _log(player, team, wk, market, value):
    return {"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
            "opponent": "OPP", "position": "", "home": 1,
            "market": market, "value": value}


def _seed(conn):
    rows = []
    for wk in range(1, 7):
        # The goal-line back: 3 inside-5, 5 red-zone carries, 1 rz target.
        rows += [_log("J.Bell", "KC", wk, "i5_car", 3),
                 _log("J.Bell", "KC", wk, "rz_car", 5),
                 _log("J.Bell", "KC", wk, "rz_tgt", 1)]
        # The satellite back on the same team: no goal-line work at all.
        rows += [_log("S.Pace", "KC", wk, "i5_car", 0),
                 _log("S.Pace", "KC", wk, "rz_car", 1),
                 _log("S.Pace", "KC", wk, "rz_tgt", 2)]
        rows += [_log("J.Bell", "KC", wk, "snap_pct" if False else "rz_tgt", 1)]
    db.upsert_player_logs(conn, rows)
    return conn


def test_red_zone_usage_measures_roles_and_team_share():
    conn = db.connect(":memory:")
    _seed(conn)
    rz = red_zone_usage(conn)
    bell = rz[("j", "bell", "KC")]
    pace = rz[("s", "pace", "KC")]
    assert bell.measured and pace.measured
    assert bell.carries_inside_5 == 3.0
    assert bell.carries_inside_10 == 5.0        # rz_car, not just inside-5
    # Team red-zone touches: (5+1) + (1+2) = 9 per week.
    assert abs(bell.rz_touch_share - 6 / 9) < 0.01
    assert abs(pace.rz_touch_share - 3 / 9) < 0.01
    # This is exactly the split the volume proxy could never see: the two
    # backs might have similar total touches, but one owns the goal line.
    assert bell.rz_touch_share > pace.rz_touch_share * 1.5


def test_rz_car_gap_falls_back_to_inside5():
    """Older ingests predate the rz_car market — inside-5 is still a floor,
    never treated as zero red-zone carries."""
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [
        _log("O.School", "SF", wk, m, v)
        for wk in (1, 2) for m, v in (("i5_car", 2), ("rz_tgt", 0))])
    rz = red_zone_usage(conn)
    assert rz[("o", "school", "SF")].carries_inside_10 == 2.0


def test_snap_rows_parse_and_average_recent_weeks():
    raw = [{"player": "Jahmyr Gibbs", "position": "RB", "team": "DET",
            "opponent": "GB", "week": str(wk), "offense_pct": pct}
           for wk, pct in [(1, "0.50"), (2, "0.60"), (3, "0.70"),
                           (4, "0.80"), (5, "0.90"), (6, "1.00")]]
    # A lineman must not enter the map.
    raw.append({"player": "Big Blocker", "position": "T", "team": "DET",
                "opponent": "GB", "week": "6", "offense_pct": "1.0"})
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, snap_count_rows(raw, 2025))
    shares = snap_shares(conn)
    # Last SNAP_WEEKS=5 weeks: mean of .6..1.0 = 0.80 — week 1 aged out.
    # (Keys are the fantasy short key: first INITIAL + last name + team,
    # so full-name snap rows and abbreviated pbp names land together.)
    assert abs(shares[("j", "gibbs", "DET")] - 0.80) < 1e-6
    assert ("b", "blocker", "DET") not in shares


def test_percent_style_snap_values_normalize():
    rows = snap_count_rows([{"player": "A B", "position": "WR", "team": "KC",
                             "opponent": "LV", "week": "3",
                             "offense_pct": "85"}], 2025)
    assert rows[0]["value"] == 0.85


def test_measured_red_zone_changes_the_pick_story():
    """A candidate WITH measured red-zone usage loses the 'inferred' caveat,
    gains full data quality, and shows its snap share; one without keeps
    the proxy disclosure exactly as before."""
    from engine.models import (Game, Team, Prop, GameLog, Weather,
                               DefenseProfile, SportsbookLine, ANYTIME_TD)
    from engine.touchdowns import build_td_longshots, RedZoneUsage

    # Numbers chosen so the model lands NEAR the market (credible, small
    # positive edge) — a huge disagreement is correctly graded Pass and
    # filtered, which is not what this test is about.
    g = Game(home="KC", away="BUF", weather=Weather(dome=True),
             spread=-3.0, total=41.0)
    opp = Team(abbr="BUF", name="Bills",
               defense=DefenseProfile(team="BUF", vs_rb_rush=1.0))

    def cand(name, red_zone=None, snap=None):
        p = Prop(player=name, team="KC", opponent="BUF", position="RB",
                 market=ANYTIME_TD,
                 logs=[GameLog(week=i, opponent="X", value=i % 2)
                       for i in range(1, 7)],
                 career_avg=0.5, vs_opponent_avg=None,
                 lines=[SportsbookLine("DK", 0.5, 120, -145)])
        # PRICED LIKE THE PLAYER IT DESCRIBES. The fixture asked for a
        # goal-line workhorse and then quoted him at +200 — a 33% price
        # against a model that has him at 50%, which is a 17-point
        # disagreement the credibility guard exists to refuse. It
        # graduated before only because the guard sat just far enough
        # away, and the history re-weighting (2026-08-27) moved it over
        # the line and exposed a fixture that was never coherent. A back
        # this good is a short price, so he is quoted like one: +120 is
        # 45%, which the model beats by a believable four points.
        #
        # A bell-cow's share, not a committee back's. POSITION_TYPICAL_SHARE
        # puts a typical starting RB at 0.45, and this fixture is describing
        # the goal-line workhorse its red-zone numbers imply. It read 0.3
        # until 2026-08-27, and passed only because the model then took 60%
        # of its answer from six alternating touchdown games — three TDs in
        # six is a hot streak, not a rate, and the blend was measured and
        # cut to 20%. The fixture now stands on the role it is meant to
        # describe rather than on that over-weighting.
        c = {"prop": p, "game": g, "opponent": opp, "opportunity_share": 0.45,
             "odds": 120, "book": "DK", "under_odds": -145}
        if red_zone is not None:
            c["red_zone"] = red_zone
        if snap is not None:
            c["snap_share"] = snap
        return c

    measured = RedZoneUsage(carries_inside_5=1.0, carries_inside_10=2.0,
                            targets_inside_10=0.5, rz_touch_share=0.30,
                            measured=True)
    # `require_edge=False`: this is about the STORY on the card, not the
    # grade. Since 2026-09-02 the board grades on the §10 0–100 score,
    # and a credible four-point disagreement at +120 is a Pass under
    # Tier 3's 6% bar — the pick is still built, ranked and explained.
    picks = build_td_longshots(
        [cand("Measured Back", measured, snap=0.72), cand("Proxy Back")],
        limit=6, per_game=6, require_edge=False)
    by = {p.player: p for p in picks}
    m = by["Measured Back"]
    assert not any("inferred" in c for c in m.caveats)
    assert any("72% of offensive snaps" in r for r in m.reasons)
    # The identical player WITHOUT measurement keeps the proxy disclosure —
    # and the data-quality discount that (correctly) makes his pick harder
    # to grade. Check the caveat at the probability layer, where it lives.
    from engine.touchdowns import td_probability
    _, info = td_probability(cand("Proxy Back")["prop"], g, opp, 0.3, None)
    assert any("inferred" in c for c in info["caveats"])
    assert info["data_quality"] < 1.0


def test_empty_db_returns_empty_maps():
    conn = db.connect(":memory:")
    maps = build_usage_maps(conn)
    assert maps == {"red_zone": {}, "snap": {}, "volume": {},
                    "xfp": {}, "team_of": {}}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
