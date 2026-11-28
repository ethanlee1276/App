"""A college play counts for the side with the ball (step AHV, 26 November 2026).

The nightly copies count (heartbeat cfb_copies) listed 3,325 college stat rows on 25 November where one player's
game sat under both schools of it: A'Marion Peterson's 8 October game against South Florida, the box score under
UTSA and the play file's row under South Florida. The play file (cfbfastR's player_stats) files a sack, a pass
broken up, an interception and some plain incompletions once, on a row whose ``team`` is the DEFENDING school, and
that row names the other side's passer and receiver: Owen McCown's incompletion to Peterson, both UTSA, says South
Florida. Read as the row says, each opened a line for both under the wrong school, and a stat row's key (game,
player, market) holds no school, so the phantom line and the real one wrote the same row and the last one stood.

Measured on the mirror's files with our own parser, what the table kept: 2026, 8,165 touchdowns of 9,271 and 61,923
pass attempts of 87,963; 2025, 6,090 touchdowns of 6,370 and 73,522 attempts of 95,228; 2023, 8,651 of 8,876 and
72,282 of 80,383. Peterson's game kept 0 touchdowns (he scored 3) and McCown's kept 5 attempts and 0 completions
(31 and 22). What holds now:

  * a play whose named players the season's roster puts with the other school, and none with the row's own,
    counts for that other school (`cfbstats.play_side`), in the stat lines and in the carry, route and passing
    charts alike;
  * a line one ESPN id still splits across both schools of a game is joined into the side he did more on;
    two players of one name (two ids) stay apart;
  * the roster keeps each player's school;
  * the nightly reads the four seasons before this one again with the fix, one a night and the newest first,
    each once, and the heartbeat says which are done (cfb_copies.reread).

    python3 tests/test_a_college_play_counts_for_the_side_with_the_ball.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", __import__("tempfile").mkdtemp())

from engine.sources import cfbstats as C  # noqa: E402

GAMES = {"401862794": {"period": "2026-10-08", "home": "USF", "away": "UTSA", "home_name": "South Florida",
                       "away_name": "UTSA", "points": 0}}
ROSTER = C.parse_rosters([
    {"athlete_id": "4918111", "first_name": "A'Marion", "last_name": "Peterson", "position": "RB", "team": "UTSA"},
    {"athlete_id": "4775136", "first_name": "Owen", "last_name": "McCown", "position": "QB", "team": "UTSA"},
    {"athlete_id": "5000001", "first_name": "Byrum", "last_name": "Brown", "position": "QB",
     "team": "South Florida"},
])


def _play(team="UTSA", opponent="South Florida", **kw):
    row = {"game_id": "401862794", "season": "2026", "week": "6", "team": team, "opponent": opponent,
           "yards_to_goal": "60", "down": "1", "distance": "10"}
    row.update(kw)
    return row


def _plays():
    return [
        _play(rush_player="A'Marion Peterson", rush_player_id="4918111", rush_yds="53",
              touchdown_player="A'Marion Peterson", yards_to_goal="53"),
        _play(incompletion_player="Owen McCown", incompletion_player_id="4775136"),
        _play(incompletion_player="Owen McCown", incompletion_player_id="4775136",
              target_player="A'Marion Peterson", target_player_id="4918111"),
        # The defence's row of a UTSA play: McCown incomplete to Peterson, filed under South Florida.
        _play(team="South Florida", opponent="UTSA", incompletion_player="Owen McCown",
              incompletion_player_id="4775136", target_player="A'Marion Peterson", target_player_id="4918111",
              pass_breakup_player="Somebody", pass_breakup_player_id="9"),
        # South Florida's own play stays South Florida's.
        _play(team="South Florida", opponent="UTSA", incompletion_player="Byrum Brown",
              incompletion_player_id="5000001"),
    ]


def _rows(out, player, market):
    return [(r["team"], r["value"]) for r in out["rows"] if r["player"] == player and r["market"] == market]


def test_the_roster_keeps_his_school():
    assert ROSTER["4918111"] == {"position": "RB", "name": "A'Marion Peterson", "headshot": "", "team": "UTSA"}


def test_a_defence_filed_play_counts_for_the_side_with_the_ball():
    out = C.parse_player_stats(_plays(), 2026, GAMES, ROSTER)
    assert _rows(out, "A'Marion Peterson", "anytime_td") == [("UTSA", 1.0)], out["rows"]
    assert _rows(out, "Owen McCown", "pass_att") == [("UTSA", 3.0)]
    assert _rows(out, "Byrum Brown", "pass_att") == [("USF", 1.0)]
    keys = [(r["game_id"], r["player"], r["market"]) for r in out["rows"]]
    assert len(keys) == len(set(keys)), "one row a key"
    # With no roster to say his school, his one ESPN id joins the line the defence's row split off.
    bare = C.parse_player_stats(_plays(), 2026, GAMES, None)
    assert _rows(bare, "A'Marion Peterson", "anytime_td") == [("UTSA", 1.0)]
    assert _rows(bare, "Owen McCown", "pass_att") == [("UTSA", 3.0)]


def test_a_line_split_by_one_id_is_joined_and_two_names_stay_apart():
    """No roster to say his school: the line one ESPN id splits is joined into the side he did more on."""
    plays = [p for p in _plays() if p.get("team") == "UTSA" or "Byrum" in str(p.get("incompletion_player"))]
    plays.append(_play(team="South Florida", opponent="UTSA", incompletion_player="Owen McCown",
                       incompletion_player_id="4775136"))
    # Two players of one name, one each side, with their own ids.
    plays.append(_play(rush_player="Chris Jones", rush_player_id="111", rush_yds="4"))
    plays.append(_play(team="South Florida", opponent="UTSA", rush_player="Chris Jones", rush_player_id="222",
                       rush_yds="9"))
    out = C.parse_player_stats(plays, 2026, GAMES, None)
    assert _rows(out, "Owen McCown", "pass_att") == [("UTSA", 3.0)], _rows(out, "Owen McCown", "pass_att")
    assert out["skipped"].get("lines under both schools, joined") == 1
    assert sorted(_rows(out, "Chris Jones", "rush_yds")) == [("USF", 9.0), ("UTSA", 4.0)]


def test_the_charts_read_the_same_side():
    from engine.carries import CfbCarries
    from engine.passes import CfbPasses
    from engine.targets import CfbTargets
    for cls in (CfbCarries, CfbTargets, CfbPasses):
        src = (ROOT / "engine" / f"{cls.__module__.split('.')[-1]}.py").read_text(encoding="utf-8")
        assert "CS.play_side(game, r, self.roster)" in src and "CS._side_of(game" not in src, cls
    throws = CfbPasses(2026, GAMES, ROSTER)
    for p in _plays():
        throws.add(p)
    src = (ROOT / "engine" / "sources" / "cfbstats.py").read_text(encoding="utf-8")
    assert "THE FEED FILES SOME PLAYS UNDER THE DEFENCE (step AHV" in src
    assert "side = play_side(game, r, roster)" in src


def test_the_nightly_reads_the_past_seasons_again_one_a_night():
    import datetime as dt
    import json
    import tempfile
    from engine import maintenance as M
    state = Path(tempfile.mkdtemp()) / "cfb_play_side.json"
    day = dt.date(2026, 11, 27)
    stocked = M.CFB_MIN_PLAYER_ROWS
    order = []
    while (got := M.cfb_reread_season(day, stocked, state_path=state)) is not None:
        order.append(got)
        M.cfb_reread_done(got, 1000 + got, state_path=state)
    assert order == [2025, 2024, 2023, 2022], order
    doc = json.loads(state.read_text())
    assert doc["for"] == "play_side" and doc["rows"]["2025"] == 3025
    assert M.cfb_reread_season(day, stocked - 1, state_path=state) is None, "a box still to backfill reads them all"
    state.write_text(json.dumps({"for": "an older parser", "read": [2025, 2024, 2023, 2022]}))
    assert M.cfb_reread_season(day, stocked, state_path=state) == 2025, "a new parser reads them again"
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("seasons = cfb_player_seasons(today, have)")
    body = src[i:i + 1500]
    assert "reread = None if os.environ.get(_ms.ENV_VAR) else cfb_reread_season(today, have)" in body
    assert "seasons = sorted(seasons + [reread])" in body and "cfb_reread_done(reread, got[\"rows\"])" in body
    import launch as L
    real = M.CFB_REREAD_STATE
    try:
        M.CFB_REREAD_STATE = state
        assert L._cfb_copies_public()["reread"]["read"] == [2025, 2024, 2023, 2022]
    finally:
        M.CFB_REREAD_STATE = real


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
