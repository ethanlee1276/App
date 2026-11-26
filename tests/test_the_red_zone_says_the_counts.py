"""The game report's red zone says the counts, not "by our numbers" (2026-11-15).

Ethan, circling "Who gets NE's chances inside the 20: Rhamondre Stevenson
(about 2), Corey Kiner (about 1.5), Mack Hollins (about 1.1) — carries and
targets a game there, by our numbers": "I feel like we should be going of the
actual factual numbers and not 'our numbers'. The point is so the user knows
how many redzone touches and targets each player gets and how many they
should get based off the match up for the game and offense and defense".

What these hold (engine/gamereport.sec_redzone, rz_usage_lines):

  * each player's carries and targets inside the 20 in the last games, from
    the play-by-play (inside the 5 and the 10 said where he has them), a game,
    and his share of his team's — the touchdown row carries the counts
    (`goal_line`) and the share (`rz_share`) to the read (engine/gamescan);
  * what that comes to against this defense: his rate times how many plays
    inside the 20 the defense allows against an average one;
  * the team's line says this game's plays the same way;
  * a touchdown chance's line no longer prints the estimated share (the counts
    say the real one), and the touchdown rule still reads the board's share.

    python3 tests/test_the_red_zone_says_the_counts.py
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402


class _Harness:
    """The game report test's own board, imported when a test first needs it
    (never at module scope: test_doctor)."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_the_game_report_reads_like_the_research"), attr)


GR = _Harness()

GIBBS = {"games": 6, "rz_car": 14, "i5_car": 5, "rz_tgt": 2, "i10_tgt": 1}
ST_BROWN = {"games": 6, "rz_car": 0, "i5_car": 0, "rz_tgt": 7, "i10_tgt": 3}


def _board():
    board = copy.deepcopy(GR._board())
    for r in board["scan_reads"]["GB@DET"]["players"]:
        if r["player"] == "Jahmyr Gibbs":
            r["td"].update(goal_line=dict(GIBBS), rz_share=0.36)
        elif r["player"] == "Amon-Ra St. Brown":
            r["td"].update(goal_line=dict(ST_BROWN), rz_share=0.18)
    return board


def _redzone(rep):
    sec = next(s for s in rep["sections"] if s["key"] == "redzone")
    out = []
    for b in sec["blocks"]:
        out.append(("h", b.get("text") or "") if b["type"] == "h" else ("list", [
            it if isinstance(it, str) else it.get("text") for it in b.get("items") or []]))
    return out


def test_each_player_says_his_counts_his_rate_his_share_and_this_game():
    board = _board()
    rep = R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)
    blocks = _redzone(rep)
    heads = [t for k, t in blocks if k == "h"]
    assert "Who gets the ball inside the 20 for the Lions" in heads, heads
    lines = blocks[heads and [t for k, t in blocks].index("Who gets the ball inside the 20 for the Lions") + 1][1]
    # GB allows 15% more plays inside the 20 than an average defense: x1.15.
    assert lines == [
        "Jahmyr Gibbs (RB): 14 carries (5 inside the 5) and 2 targets (1 inside the 10) in the last 6 games "
        "— 2.7 a game, 36% of DET's. Against GB: about 3.1 this game.",
        "Amon-Ra St. Brown (WR): 7 targets (3 inside the 10) in the last 6 games — 1.2 a game, 18% of DET's. "
        "Against GB: about 1.3 this game.",
    ], lines
    # The counts come before who can score, for each team.
    order = [t for k, t in blocks if k == "h"]
    assert order.index("Who gets the ball inside the 20 for the Lions") < order.index("Who can score for the Lions")
    text = R.to_text(rep)
    assert "by our numbers" not in text
    assert "DET runs about 12 plays a game inside the opponent's 20" in text and "This game: about 13.8 for DET." in text


def test_a_players_touchdown_line_leaves_the_share_to_the_counts():
    board = _board()
    rep = R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)
    text = R.to_text(rep)
    # The rank and the number (step AHO).
    assert ("Jahmyr Gibbs (RB): 43% to score, at +333; GB allows the second-most touchdowns to running backs "
            "(1.7 a game); the touchdown matchup backs it") in text
    assert "of DET's red-zone chances" not in text


def test_no_counts_no_list_and_the_old_words_are_gone():
    rep = GR._report()
    heads = [t for k, t in _redzone(rep) if k == "h"]
    assert not [h for h in heads if h.startswith("Who gets the ball inside the 20")], heads
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "carries and targets a game there, by our numbers" not in src.replace(
        'circling "carries and targets a game there, by our numbers"', "")


def test_the_factor_is_the_defenses_red_zone_plays_against_average_and_bounded():
    assert R.rz_factor(-0.15) == 0.85 and R.rz_factor(0.06) == 1.06
    assert R.rz_factor(-0.9) == 0.6 and R.rz_factor(0.9) == 1.4
    assert R.rz_factor(None) is None


def test_the_counts_and_the_share_ride_the_touchdown_row_to_the_read():
    td_src = (ROOT / "engine" / "touchdowns.py").read_text(encoding="utf-8")
    assert '"rz_share": round(rz.rz_touch_share, 3) if rz.measured and rz.rz_touch_share else None,' in td_src
    assert '"rz_share": info.get("rz_share"),' in td_src
    scan_src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert '"goal_line": r.get("goal_line"), "rz_share": r.get("rz_share"),' in scan_src
    from engine import gamescan as GS
    result = {"longshot_watch": [{"player": "Jahmyr Gibbs", "model_prob": 0.43, "odds": 333,
                                  "goal_line": dict(GIBBS), "rz_share": 0.36, "rz_chances": 2.4}]}
    reads = {"GB@DET": {"players": [{"player": "Jahmyr Gibbs", "team": "DET"}]}}
    assert GS.stamp_touchdowns(reads, result) == 1
    td = reads["GB@DET"]["players"][0].get("td") or {}
    assert td.get("goal_line") == GIBBS and td.get("rz_share") == 0.36, td


def test_the_heartbeat_counts_the_reports_that_say_the_counts():
    """The reports are a paid key: the heartbeat is where a live check sees
    their red zones say the counts (launch._board_counts)."""
    import json
    import os
    import tempfile
    import launch as L
    board = _board()
    rep = R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump({"game_reports": [rep, GR._report()], "most_likely": [], "game_bets": []}, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["reports"], got["rz_count_lists"], got["rz_count_players"]) == (2, 1, 2), got


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
