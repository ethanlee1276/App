"""The carry projections are graded against what each back carried, every game replayed from the weeks before it.

Ethan, 2026-10-23, after D'Andre Swift carried 22 times on a projection of
15: "yes do the carry projection check". carrycheck.py replays each week
through engine/backtest (the live board's own build, as of that week) and
grades the running backs' carries by projected role, against a plain
last-three average, by the spread before the game and by how it went.

What these hold: the replay hands back every settled prop with its week,
team and position when asked, and nothing when not; the baseline is his
last three games before that week and never that week itself; the spread
and the margin are signed for the team; a role tier is read off the
projection; a table row's bias is carried minus projected and is flagged
only past two standard errors on twenty games; and the report names the
game-flow rows as not knowable before kickoff.

Run directly: `python3 tests/test_the_carries_are_checked_from_the_weeks_before.py`
"""
import inspect
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import carrycheck as C                                             # noqa: E402
from engine import backtest as B                                   # noqa: E402


def test_the_replay_hands_back_its_rows_only_when_asked():
    sig = inspect.signature(B.backtest_from_stats)
    assert sig.parameters["rows_out"].default is None
    src = inspect.getsource(B.backtest_from_stats)
    assert "if rows_out is not None:" in src
    for key in ('"week": w', '"team": rec.get("team", "")', '"position": rec.get("position", "")',
                '"projection": rec["projection"]', '"actual": actuals[key]'):
        assert key in src, key


def test_the_baseline_is_his_last_three_before_the_week():
    stats = [{"player_display_name": "A Back", "week": str(w), "carries": str(c), "season_type": "REG"}
             for w, c in ((1, 10), (2, 20), (3, 30), (4, 40), (6, 60))]
    got = C.last_three(stats)
    assert (("A Back", 1) not in got), "no games before week one"
    assert got[("A Back", 2)] == 10
    assert got[("A Back", 4)] == 20, "weeks 1-3, never week 4 itself"
    assert got[("A Back", 6)] == 30, "his last three games, a bye skipped"
    assert ("A Back", 5) not in got, "no row for a week he did not play"


def test_the_spread_and_the_margin_are_the_teams():
    games = [{"season": "2026", "week": "7", "home_team": "CHI", "away_team": "NE",
              "spread_line": "3", "home_score": "30", "away_score": "24"}]
    got = C.game_lines(games, 2026)
    assert got[("CHI", 7)] == (3.0, 6.0) and got[("NE", 7)] == (-3.0, -6.0)
    unplayed = C.game_lines([dict(games[0], home_score="", away_score="")], 2026)
    assert unplayed[("CHI", 7)] == (3.0, None)
    assert C.game_lines(games, 2025) == {}


def test_a_role_is_read_off_the_projection():
    assert C.tier(15.0) == "lead (14+)" and C.tier(14.0) == "lead (14+)"
    assert C.tier(10.0) == "share (9-14)" and C.tier(8.9) == "change of pace (<9)"


def test_bias_is_carried_minus_projected_and_flagged_only_when_it_stands():
    rows = [{"projection": 15.0, "actual": 22.0}] * 25
    text = C.line("lead", rows)
    assert "+7.0" in text and "<-- off" in text
    few = C.line("lead", rows[:5])
    assert "<-- off" not in few, "five games flag nothing"
    noisy = [{"projection": 10.0, "actual": a} for a in (2, 18) * 15]
    assert "<-- off" not in C.line("share", noisy), "a zero bias is not off, however wide"
    assert C.line("empty", []).split()[-1] == "-"


def test_the_report_says_which_rows_could_have_been_known():
    rows = [{"week": 7, "team": "CHI", "player": "D'Andre Swift", "projection": 15.0, "actual": 22.0,
             "naive": 15.5, "spread": 3.0, "margin": 6.0}]
    text = "\n".join(C.report(rows, "2026"))
    assert "by the spread before the game (could have been known)" in text
    assert "by how the game went (game flow, not knowable before)" in text
    assert "week  7 CHI D'Andre Swift" in text and "carried   22" in text and "(won by 6)" in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
