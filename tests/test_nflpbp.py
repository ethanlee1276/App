"""Tests for play-by-play aggregation → xFP, red-zone usage, PROE."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources.nflpbp import (
    aggregate_pbp, xfp_player_rows, team_week_rows, _carry_bucket,
    _target_bucket,
)


def _run(wk, team, rusher, yl, yards, td=0, oe=""):
    return {"week": wk, "posteam": team, "play_type": "run",
            "yardline_100": yl, "yards_gained": yards, "rush_touchdown": td,
            "rusher_player_name": rusher, "pass_oe": oe}


def _pass(wk, team, receiver, yl, air, yards, comp=1, td=0, oe=""):
    return {"week": wk, "posteam": team, "play_type": "pass",
            "yardline_100": yl, "air_yards": air, "yards_gained": yards,
            "complete_pass": comp, "pass_touchdown": td,
            "receiver_player_name": receiver, "pass_oe": oe}


def test_buckets_split_by_field_position():
    assert _carry_bucket(1) == "car_i5"
    assert _carry_bucket(18) == "car_rz"
    assert _carry_bucket(60) == "car_open"
    assert _target_bucket(10, 5) == "tgt_rz"       # red zone wins
    assert _target_bucket(60, 22) == "tgt_deep"
    assert _target_bucket(60, 4) == "tgt_short"


def test_aggregate_values_players_and_proe():
    rows = []
    # 30 inside-5 carries league-wide: half score (avg 3.05 pts each),
    # 30 open-field carries for 5 yards each (0.5 pts each).
    for i in range(30):
        rows.append(_run("3", "KC", "A.Back", 2, 1, td=(i % 2), oe="0.1"))
        rows.append(_run("3", "SF", "B.Back", 50, 5, oe="-0.05"))
    agg = aggregate_pbp(rows)
    assert abs(agg["values"]["car_i5"] - (0.1 * 1 + 3.0)) < 1e-6
    assert abs(agg["values"]["car_open"] - 0.5) < 1e-6
    assert agg["values"]["tgt_rz"] is None          # never sampled
    # Player-week bucket counts.
    assert agg["players"][("A.Back", "KC", 3)]["car_i5"] == 30
    # Team PROE = mean pass_oe over its plays.
    kc = agg["teams"][("KC", 3)]
    assert abs(kc["oe"][0] / kc["oe"][1] - 0.1) < 1e-9

    prow = {(r["player"], r["market"]): r["value"]
            for r in xfp_player_rows(agg, 2025)}
    # A.Back's xFP = 30 inside-5 carries × their league value.
    assert abs(prow[("A.Back", "xfp")] - 30 * agg["values"]["car_i5"]) < 1e-6
    assert prow[("A.Back", "i5_car")] == 30.0
    trow = {r["team"]: r for r in team_week_rows(agg, 2025)}
    assert trow["KC"]["plays"] == 30 and abs(trow["KC"]["proe"] - 0.1) < 1e-6


def test_unpriced_bucket_blocks_xfp_but_not_usage():
    # One deep target league-wide: fewer than 30 samples, so the bucket has
    # no trustworthy value — xFP for its user is withheld, usage still counts.
    agg = aggregate_pbp([_pass("5", "KC", "W.Out", 60, 25, 40)])
    rows = xfp_player_rows(agg, 2025)
    markets = {r["market"] for r in rows if r["player"] == "W.Out"}
    assert "xfp" not in markets
    assert {"rz_tgt", "i5_car", "rz_car"} <= markets


def test_rz_car_counts_every_red_zone_carry():
    """rz_car = all carries inside the 20, the inside-5s included — the
    measured-role feed for the touchdown model."""
    rows = [_run("4", "KC", "A.Back", 3, 2),      # inside 5
            _run("4", "KC", "A.Back", 15, 4),     # red zone
            _run("4", "KC", "A.Back", 55, 6)]     # open field
    prow = {(r["player"], r["market"]): r["value"]
            for r in xfp_player_rows(aggregate_pbp(rows), 2025)}
    assert prow[("A.Back", "rz_car")] == 2.0
    assert prow[("A.Back", "i5_car")] == 1.0


def test_epa_both_sides_and_neutral_pace():
    """EPA aggregates per offense (pass/rush split) AND per defense
    (allowed); pace counts only believable snap gaps in neutral script."""
    rows = []
    secs = 3600.0
    for i in range(24):
        r = _run("3", "KC", "A.Back", 50, 4, oe="0.1")
        r.update(epa="0.25" if i % 2 else "-0.05", defteam="DEN",
                 game_id="G1", wp="0.55", qtr="2",
                 game_seconds_remaining=str(secs))
        rows.append(r)
        secs -= 28.0                                  # 28s between snaps
    # A garbage-time snap: wp outside the window — never counts for pace.
    junk = _run("3", "KC", "A.Back", 50, 4)
    junk.update(epa="1.0", defteam="DEN", game_id="G1", wp="0.95", qtr="4",
                game_seconds_remaining=str(secs))
    rows.append(junk)
    trow = {r["team"]: r for r in team_week_rows(aggregate_pbp(rows), 2025)}
    kc = trow["KC"]
    # 25 plays: 12×0.25 + 12×(-0.05) + 1.0 = 3.4 → /25 = 0.136
    assert abs(kc["off_epa"] - 0.136) < 1e-6
    assert abs(kc["rush_epa"] - 0.136) < 1e-6 and kc["pass_epa"] is None
    assert abs(kc["pace"] - 28.0) < 1e-6              # junk snap excluded
    # Defense: DEN allowed the same EPA KC's offense earned.
    den = trow["DEN"]
    assert abs(den["def_epa"] - 0.136) < 1e-6
    assert den["off_epa"] is None and den["plays"] == 0


def test_team_profiles_average_and_migrate():
    """season_profiles averages team_weeks (min-week gate, form window);
    an OLD pre-EPA team_weeks table gains the new columns on connect."""
    import sqlite3, tempfile
    from pathlib import Path
    from engine import db, teamprofiles
    path = Path(tempfile.mkdtemp()) / "hist.db"
    old = sqlite3.connect(str(path))
    old.execute("CREATE TABLE team_weeks (sport TEXT, season INTEGER, "
                "period TEXT, team TEXT, plays INTEGER, proe REAL, "
                "PRIMARY KEY (sport, season, period, team))")
    old.execute("INSERT INTO team_weeks VALUES ('nfl', 2025, '001', 'KC', 65, 0.05)")
    old.commit(); old.close()

    conn = db.connect(path)                           # migration runs here
    rows = [{"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
             "team": "KC", "plays": 60 + wk, "proe": 0.04,
             "off_epa": 0.10, "pass_epa": 0.15, "rush_epa": 0.02,
             "def_epa": -0.05, "pace": 27.0 + wk}
            for wk in range(2, 7)]
    rows.append({"sport": "nfl", "season": 2025, "period": "001",
                 "team": "DEN", "plays": 55, "proe": -0.02, "off_epa": -0.1,
                 "pass_epa": None, "rush_epa": None, "def_epa": 0.02,
                 "pace": None})
    db.upsert_team_weeks(conn, rows)

    profs = teamprofiles.season_profiles(conn)
    assert "DEN" not in profs                         # 1 week < MIN_WEEKS
    kc = profs["KC"]
    assert kc["weeks"] == 6 and kc["off_epa"] == 0.10
    assert kc["def_epa"] == -0.05
    # Week 1 predates EPA (migrated NULLs) — averaged over present weeks only.
    assert abs(kc["pace"] - (sum(27.0 + w for w in range(2, 7)) / 5)) < 1e-6
    # Form window: last 2 weeks only.
    form = teamprofiles.season_profiles(conn, last_n=2, min_weeks=2)
    assert abs(form["KC"]["pace"] - 32.5) < 1e-6      # weeks 5,6 → 32,33
    base = teamprofiles.league_baseline(profs)
    assert base["off_epa"] == 0.10                    # only KC qualifies


def test_fantasy_prefers_xfp_and_attaches_proe():
    from engine import db
    from engine.fantasy import buy_sell_board, game_scripts, team_proe
    conn = db.connect(":memory:")
    # Usage rows (full names) — heavy volume, modest scoring.
    logs = []
    for wk in range(1, 8):
        for market, val in (("targets", 10.0), ("carries", 0.0),
                            ("fp_ppr", 12.0)):
            logs.append({"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
                         "game_id": f"KC-{wk:03d}", "player": "Wide Out",
                         "team": "KC", "opponent": "LV", "position": "WR",
                         "home": 1, "market": market, "value": val})
        # pbp aggregates under the abbreviated name: xFP says 17/wk.
        logs.append({"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
                     "game_id": f"KC-{wk:03d}", "player": "W.Out",
                     "team": "KC", "opponent": "", "position": "",
                     "home": 1, "market": "xfp", "value": 17.0})
    db.upsert_player_logs(conn, logs)
    bs = buy_sell_board(conn, 2025, min_fit_rows=5)
    row = next(r for r in bs["buy_low"] if r["player"] == "Wide Out")
    # Joined across name styles; expected comes from xFP, not the flat fit.
    assert row["basis"] == "xfp" and row["expected_ppg"] == 17.0

    db.upsert_team_weeks(conn, [
        {"sport": "nfl", "season": 2025, "period": f"{wk:03d}", "team": "KC",
         "plays": 65, "proe": 0.05} for wk in range(1, 6)])
    assert team_proe(conn) == {"KC": 0.05}
    db.upsert_games(conn, [
        {"sport": "nfl", "season": 2026, "period": "001", "game_id": "BUF@KC",
         "home": "KC", "away": "BUF", "home_score": None, "away_score": None,
         "spread": -3.5, "total": 49.0, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": None}])
    s = game_scripts(conn)[0]
    assert s["home_proe"] == 0.05 and s["away_proe"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
