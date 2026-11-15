"""The red zone's counts say his season beside his last games (2026-11-15).

Ethan, deciding between the last six games alone and "add season totals":
"add season total beside". Each player's carries and targets inside the 20
were his last six games (engine/nflusage.red_zone_usage, RZ_WEEKS); now the
same four counts over every game he touched the ball this season ride with
them (RedZoneUsage.season_counts → goal_line()["season"], only when the
season is longer than the games counted), and each place that says the
counts says the season beside them: the report's red-zone list, the
likeliest-scorer line, and the pick's own red-zone line (goal_line_text).

    python3 tests/test_the_red_zone_counts_say_the_season_beside.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as R                                   # noqa: E402
from engine.touchdowns import RedZoneUsage                           # noqa: E402


class _Harness:
    """The game report test's own board, imported when a test first needs it
    (never at module scope: test_doctor)."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_the_game_report_reads_like_the_research"), attr)


GR = _Harness()

GIBBS = {"games": 6, "rz_car": 14, "i5_car": 5, "rz_tgt": 2, "i10_tgt": 1,
         "season": {"games": 9, "rz_car": 21, "i5_car": 8, "rz_tgt": 3, "i10_tgt": 1}}


def test_the_play_by_play_reader_counts_his_whole_season_beside_his_last_six():
    from engine import db as D
    from engine import nflusage as U
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    rows = []
    for wk in range(1, 10):
        p = f"{wk:02d}"
        rows += [("nfl", 2026, p, f"g{wk}", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "rz_car", 2 + (wk % 2)),
                 ("nfl", 2026, p, f"g{wk}", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "i5_car", 1),
                 ("nfl", 2026, p, f"g{wk}", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "rz_tgt", 1 if wk <= 3 else 0),
                 ("nfl", 2026, p, f"g{wk}", "Jahmyr Gibbs", "DET", "GB", "RB", 1, "i10_tgt", 0)]
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    got = U.red_zone_usage(conn, 2026)
    rz = next(v for v in got.values())
    assert rz.games == 6
    # Weeks 1-9: rz_car 3,2,3,2,3,2,3,2,3 = 23; i5 9; targets in weeks 1-3.
    assert rz.season_counts == {"games": 9, "rz_car": 23, "i5_car": 9, "rz_tgt": 3, "i10_tgt": 0}, rz.season_counts
    gl = rz.goal_line()
    assert gl["games"] == 6 and gl["season"]["games"] == 9 and gl["season"]["rz_car"] == 23, gl
    text = rz.goal_line_text()
    assert text.endswith("in his last 6 games; 23 carries (9 inside the 5) and 3 targets in his 9 games this season"), text


def test_a_season_no_longer_than_the_games_counted_says_nothing_more():
    rz = RedZoneUsage(carries_inside_10=2.0, carries_inside_5=1.0, measured=True, games=4,
                      season_counts={"games": 4, "rz_car": 8, "i5_car": 4, "rz_tgt": 0, "i10_tgt": 0})
    assert "season" not in rz.goal_line()
    assert "this season" not in rz.goal_line_text()
    assert RedZoneUsage(measured=True, games=3).goal_line().get("season") is None


def _board():
    board = copy.deepcopy(GR._board())
    for r in board["scan_reads"]["GB@DET"]["players"]:
        if r["player"] == "Jahmyr Gibbs":
            r["td"].update(goal_line=copy.deepcopy(GIBBS), rz_share=0.36, odds=-175, model_prob=0.64)
            r["scoring"] = {"go_to": True, "prob": 0.64, "implied": 26.0}
    return board


def test_the_red_zone_list_and_the_scorer_line_say_the_season_beside_the_last_six():
    board = _board()
    rep = R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)
    text = R.to_text(rep)
    assert ("Jahmyr Gibbs (RB): 14 carries (5 inside the 5) and 2 targets (1 inside the 10) in his last 6 games "
            "— 2.7 a game, 36% of DET's; 21 carries (8 inside the 5) and 3 targets (1 inside the 10) in his 9 games "
            "this season. Against GB: about 3.1 this game.") in text, text
    assert ("14 carries (5 inside the 5) and 2 targets (1 inside the 10) inside the 20 in his last 6 games "
            "(21 carries and 3 targets in his 9 games this season), 36% of the Lions' red-zone work") in text, text


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
