"""Every college football game page has a Matchup scan, as every other league's does.

Ethan, 2026-11-23: "We want all the live pages to match each other ... NFL is kind of like the one we want to go off
of." The NFL's game page opens its facts on the Matchup scan, and so do the NBA's, college basketball's and hockey's
(their tapes). College football's scan ranks units from CFBD's advanced season table (engine/gamescan.attach_cfb),
and on 24 November no college game carried one: Kent State at Eastern Michigan went from the money card straight to
"No prop prices for this game yet". Every college game the CFBD scan leaves bare now carries the tale of the tape from
our own box scores (engine/cfb/scan): points, passing and rushing for and against, yards a carry and a pass,
interceptions, each ranked among the FBS (FBS against FBS only), the points the lines expect, and the key
matchups, drawn in the other tapes' cells (detail.js nbaScanHTML).

Offline. Run directly: `python3 tests/test_every_college_game_page_has_a_matchup_scan.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as DB                                        # noqa: E402
from engine.cfb import scan as S                                   # noqa: E402

TEAMS = ["RUN", "AIR", "WALL", "SIEVE"]


def _league(weeks=10, now_weeks=10):
    """Four FBS schools. RUN runs for 250 yards on 5 a carry, AIR throws for 300 on 10 attempts' worth of 30,
    WALL allows 10 points, SIEVE allows 45. One FCS visitor (FCS1) plays once, scores nothing and must not count."""
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    rounds = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
    pts = {"RUN": 30, "AIR": 28, "WALL": 17, "SIEVE": 24}
    allowed = {"WALL": 10, "SIEVE": 45}
    for season in (2025, 2026):
        for wk in range(weeks if season == 2025 else now_weeks):
            date = (dt.date(season, 9, 1) + dt.timedelta(days=7 * wk)).isoformat()
            for a, b in rounds[wk % 3]:
                home, away = TEAMS[a], TEAMS[b]
                hs = allowed.get(away, pts[home])
                as_ = allowed.get(home, pts[away])
                DB.upsert_games(conn, [{"sport": "cfb", "season": season, "period": date, "date": date,
                                        "game_id": f"{away}@{home}", "home": home, "away": away,
                                        "home_score": hs, "away_score": as_}])
                for team, opp in ((home, away), (away, home)):
                    rows = {"pass_yds": 300.0 if team == "AIR" else 180.0, "pass_att": 30.0, "pass_int": 1.0,
                            "rush_yds": 250.0 if team == "RUN" else 120.0, "carries": 50.0 if team == "RUN" else 40.0}
                    for market, v in rows.items():
                        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, "
                                     "opponent, position, home, market, value) VALUES ('cfb',?,?,?,?,?,?,?,?,?,?)",
                                     (season, date, f"{away}@{home}", f"QB {team}", team, opp, "QB",
                                      int(team == home), market, v))
        DB.upsert_games(conn, [{"sport": "cfb", "season": season, "period": f"{season}-08-25", "date": f"{season}-08-25",
                                "game_id": "FCS1@RUN", "home": "RUN", "away": "FCS1", "home_score": 70, "away_score": 0}])
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "position, home, market, value) VALUES ('cfb',?,?,?,?,?,?,?,?,?,?)",
                     (season, f"{season}-08-25", "FCS1@RUN", "QB RUN", "RUN", "FCS1", "QB", 1, "rush_yds", 600.0))
    conn.commit()
    return conn


def test_each_school_is_ranked_from_its_fbs_games_alone():
    conn = _league()
    prof = S.profiles(conn, 2026, before="2026-12-01")
    teams = prof["teams"]
    assert set(teams) == set(TEAMS) and prof["n"] == 4, "the FCS visitor's day is nobody's number"
    run = teams["RUN"]
    assert round(run["rush_yds"], 1) == 250.0 and round(run["ypc"], 1) == 5.0, run
    assert run["ranks"]["rush_yds"] == 1 and run["ranks"]["ypc"] == 1
    assert teams["AIR"]["ranks"]["pass_yds"] == 1 and round(teams["AIR"]["ypa"], 1) == 10.0
    assert teams["WALL"]["ranks"]["opp_pts"] == 1 and teams["SIEVE"]["ranks"]["opp_pts"] == 4
    assert round(teams["WALL"]["opp_pts"], 1) == 10.0 and round(teams["SIEVE"]["opp_pts"], 1) == 45.0
    # What a school allows is what the other side put up against it: RUN's opponents ran for 120 a game.
    assert round(run["opp_rush_yds"], 1) == 120.0
    assert all(p["season_weight"] == 1.0 for p in teams.values()), "ten games in: this season alone"


def test_last_season_fills_in_until_the_sixth_game_and_the_tape_says_so():
    conn = _league(now_weeks=3)
    prof = S.profiles(conn, 2026, before="2026-12-01")
    run = prof["teams"]["RUN"]
    assert run["games_season"] == 3 and run["season_weight"] == round(3 / S.FULL_GAMES, 3)
    t = S.tape("WALL", "RUN", prof, {"spread": -3.5, "total": 44.5})
    assert t["note"].startswith("Team numbers blend this season with last: RUN 3 FBS games in, 50% this season"), t["note"]


def test_the_tape_reads_as_the_other_leagues_tapes():
    conn = _league()
    prof = S.profiles(conn, 2026, before="2026-12-01")
    t = S.tape("SIEVE", "RUN", prof, {"spread": 3.5, "total": 60.5})
    labels = [r["label"] for r in t["rows"]]
    assert labels[:6] == ["Points a game", "Points allowed a game", "Passing yards a game",
                          "Passing yards allowed a game", "Rushing yards a game", "Rushing yards allowed a game"]
    assert labels[-1] == "Points the lines expect tonight"
    implied = t["rows"][-1]
    assert (implied["a"], implied["h"]) == ("32.0", "28.5"), "the away side's, then the home side's"
    rush = next(r for r in t["rows"] if r["key"] == "rush_yds")
    assert rush["a"] == "250.0" and rush["ar"] == 1
    assert t["teams"] == 4 and "Ranks out of 4 FBS teams" in t["basis"]
    # RUN's running game against SIEVE's defence: the widest gap leads, one edge a side for the run.
    edges = [e["text"] for e in t["edges"]]
    assert any(e.startswith("Edge RUN: RUN's scoring (1st in points a game) against SIEVE's defense (4th") for e in edges), edges
    assert sum("Edge RUN" in e and ("running game" in e or "yards a carry" in e) for e in edges) <= 1
    assert S.tape("XX", "YY", prof) == {}, "neither school rated: no tape"


def test_the_board_hangs_it_where_cfbds_scan_is_missing_and_the_page_draws_it():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    block = src[src.index("# THE TAPE WHERE THAT SCAN HAS NONE"):src.index('_t = _clock.lap("long shots + Most Likely board", "matchup scan", _t)')]
    assert 'if (_gd.get("scan") or {}).get("units")' in block, "CFBD's scan, where there is one, stays first"
    assert '_gd["cfb_tape"] = _tp' in block
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "const t = g && (g.nba_tape || g.cfb_tape);" in det
    assert "g.mlb_tape || g.nhl_tape || g.nba_tape || g.cfb_tape) ? [\"gp-sec-scan\", \"Matchup scan\"]" in det
    assert "matchupScanHTML(g) || mlbScanHTML(g) || nhlScanHTML(g) || nbaScanHTML(g)" in det
    # No player reads ride with the college tape, so its heading promises none.
    assert "— offense against defense${who ? \", and who could shine or struggle\" : \"\"}" in det


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
