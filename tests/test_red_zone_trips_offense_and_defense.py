"""Red-zone trips: how often an offence gets in, how often a defence lets
teams in — the touchdown scenarios' fifth reading.

Ethan, 2026-09-25/26: "how often they get to the red zone ... and how the
defenses guards the offense in the red zone." engine/redzone sums every
red-zone target and carry per team-week (the offence) and gives the same
number to the opponent the schedule names (the defence allowed), per
game, before the week being read, 55/45 with last season from two games
on, centred on the league. The scenario scores it 0–2 (TRIPS_REL) and
now needs 6 of 10.

Opponent-adjusted (2026-09-26): Pittsburgh read "allows 4.45 (-50%)"
after holding Atlanta to 0 and New England to 1 — the league's two lowest
red-zone offences. Each game is now moved by the opponent's rate from its
OTHER games, so a defence is credited for beating an offence's level, not
for drawing a bad one.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import redzone as R                                  # noqa: E402
from engine import tdscenarios as S                              # noqa: E402


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, period, player, team, market, value)")
    conn.execute("CREATE TABLE games (sport, season, period, home, away, spread, total)")

    def game(yr, wk, home, away, home_plays, away_plays):
        p = f"{wk:03d}"
        conn.execute("INSERT INTO games VALUES ('nfl', ?, ?, ?, ?, -3, 45)", (yr, p, home, away))
        for team, n in ((home, home_plays), (away, away_plays)):
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl', ?, ?, 'X', ?, 'rz_car', ?)", (yr, p, team, n * 0.6))
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl', ?, ?, 'Y', ?, 'rz_tgt', ?)", (yr, p, team, n * 0.4))

    # 2026: BUF gets in 12 a game; DET lets teams in 12 a game; the others 6.
    game(2026, 1, "BUF", "NYJ", 12, 6)
    game(2026, 1, "DET", "NO", 6, 12)
    game(2026, 2, "BUF", "MIA", 12, 6)
    game(2026, 2, "DET", "CHI", 6, 12)
    game(2026, 3, "BUF", "DET", 99, 99)            # week 3 is the game being read: never counted
    return conn


def test_offence_and_defence_are_read_before_the_week_and_centred():
    r = R.team_rates(_db(), 2026, before_week=3)
    assert r["BUF"]["off"] == 12.0 and r["BUF"]["games"] == 2
    assert r["DET"]["def"] == 12.0, "NO and CHI each ran 12 against Detroit"
    assert r["BUF"]["off_rel"] > 0.3, r["BUF"]
    # The Jets ran 6 against a Buffalo defence that held its other opponent
    # to 6 too: as counted they are below the league, against that defence
    # they are average (opponent-adjusted).
    assert r["NYJ"]["off_raw"] == 6.0 and abs(r["NYJ"]["off_rel"]) < 0.05, r["NYJ"]
    assert r["DET"]["def_rel"] > 0.3 and r["BUF"]["def_rel"] < 0
    assert all(v["off"] != 99 for v in r.values()), "the week being read is never in its own number"


def test_a_defence_is_not_credited_for_drawing_bad_offences():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, period, player, team, market, value)")
    conn.execute("CREATE TABLE games (sport, season, period, home, away)")

    def game(yr, wk, home, away, hp, ap):
        p = f"{wk:03d}"
        conn.execute("INSERT INTO games VALUES ('nfl', ?, ?, ?, ?)", (yr, p, home, away))
        for team, n in ((home, hp), (away, ap)):
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl', ?, ?, 'X', ?, 'rz_car', ?)", (yr, p, team, n))

    # Last season: two weak red-zone offences (ATL, NE: 3 a game) and a
    # league at 9; PIT allowed 9 to the good ones. This season PIT drew
    # both weak offences and held them to their usual 3.
    for wk in range(1, 9):
        game(2025, wk, "ATL", f"A{wk}", 3, 9)
        game(2025, wk, "NE", f"B{wk}", 3, 9)
        game(2025, wk, "PIT", f"C{wk}", 9, 9)
    game(2026, 1, "PIT", "ATL", 9, 3)
    game(2026, 2, "NE", "PIT", 3, 9)
    game(2026, 1, "NE", "D1", 3, 9)
    game(2026, 2, "ATL", "D2", 3, 9)
    game(2026, 1, "D2", "D3", 9, 9)
    game(2026, 2, "D1", "D3", 9, 9)
    r = R.team_rates(conn, 2026, before_week=3)
    pit = r["PIT"]
    assert pit["def_raw"] < 7.0, pit                 # as counted: 3 a game this season
    assert pit["def"] > pit["def_raw"] + 2.0, pit     # against those offences: about average
    assert abs(pit["def_rel"]) < 0.15, pit


def test_the_scenario_scores_trips_as_its_fifth_reading():
    units = {"blend": 0.55, "def": {"passing": {"rank": 27}, "rushing": {"rank": 10}}}
    read = {"player": "Dalton Kincaid", "team": "BUF", "opp": "DET", "pos": "TE", "read": "good",
            "usage": {"tgt_share": 0.20}, "td": {"model_prob": 0.34, "odds": 190, "book": "DK",
                                                 "implied_total": 22.0, "rz_chances": 1.0}}
    # offence 1, defence 2, usage 1, red zone 1 = 5: short of 6 without trips…
    assert S.score(read, units) is None
    s = S.score(read, units, rz_own={"off": 12.0, "off_rel": 0.4}, rz_opp={"def": 12.0, "def_rel": 0.4})
    assert s and s["points"]["trips"] == 2 and s["score"] == 7, s
    assert S.SCENARIO_MIN == 6 and S.TRIPS_REL == (0.15, 0.05)


def test_the_scan_carries_it():
    src = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert "rz_teams = _rz_rates(conn, season, before_week=week)" in src
    assert 'scan["redzone"] = {t: rz_teams[t] for t in (home, away) if t in rz_teams}' in src
    sc = open(os.path.join(ROOT, "engine", "tdscenarios.py"), encoding="utf-8").read()
    assert 'rz_own=rz_by_team.get(x.get("team") or ""), rz_opp=rz_by_team.get(x.get("opp") or "")' in sc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
