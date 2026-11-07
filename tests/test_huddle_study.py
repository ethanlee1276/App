"""The huddle study's arithmetic (tools/huddle_study.py, docs/HUDDLE_RESEARCH.md).

Ethan, 2026-10-31: "maybe they can't hear or pick up the call, and that can
cause confusion ... see if that factors into anything." The page's numbers
come from tools/huddle_study.py run over nflverse play-by-play; these check
its rules on plays made up for the purpose: what a normal game situation
is, which flags count as the offense's own before the snap, the home and
road rates, and the no-huddle gap inside one team, down and distance.

Run directly: `python3 tests/test_huddle_study.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import huddle_study as H                           # noqa: E402


def _row(**kw):
    base = {"season": 2025, "season_type": "REG", "game_id": "g1", "fixed_drive": "1", "week": "1",
            "posteam": "BUF", "defteam": "MIA", "home_team": "BUF", "away_team": "MIA",
            "play_type": "pass", "down": "1", "ydstogo": "10", "epa": "0.0", "success": "0",
            "qtr": "1", "wp": "0.5", "half_seconds_remaining": "900", "no_huddle": "0"}
    base.update(kw)
    return base


def test_a_normal_game_situation():
    assert H.neutral(_row())
    assert not H.neutral(_row(qtr="4")), "the fourth quarter is the clock's"
    assert not H.neutral(_row(wp="0.9")) and not H.neutral(_row(wp="0.1"))
    assert not H.neutral(_row(half_seconds_remaining="100")), "a half's last two minutes"
    assert not H.neutral(_row(wp="NA"))


def test_only_the_offenses_own_flags_before_the_snap_count():
    fs = _row(play_type="no_play", penalty="1", penalty_type="False Start", penalty_team="BUF")
    assert H.presnap_error(fs) == "False Start"
    assert H.presnap_error(_row(play_type="no_play", penalty="1", penalty_type="Delay of Game",
                                penalty_team="BUF")) == "Delay of Game"
    assert H.presnap_error(_row(penalty="1", penalty_type="Defensive Offside", penalty_team="MIA")) == ""
    assert H.presnap_error(_row(penalty="1", penalty_type="False Start", penalty_team="MIA")) == "", \
        "a flag on the other side is not this offense's"
    assert H.presnap_error(_row(penalty="1", penalty_type="Too Many Men on Field", penalty_team="BUF")) == "", \
        "the unlabelled too-many-men can be the defence's"
    assert H.presnap_error(_row(penalty="1", penalty_type="Holding", penalty_team="BUF")) == ""


def test_home_and_road_rates_per_hundred_snaps():
    rows = [
        _row(),
        _row(play_type="no_play", penalty="1", penalty_type="False Start", penalty_team="BUF"),
        _row(posteam="MIA", defteam="BUF"),
        _row(posteam="MIA", defteam="BUF", play_type="run"),
        _row(posteam="MIA", defteam="BUF", play_type="no_play", penalty="1",
             penalty_type="Delay of Game", penalty_team="MIA"),
        _row(posteam="MIA", defteam="BUF", aborted_play="1"),
        _row(play_type="no_play", timeout="1", timeout_team="BUF"),
        _row(play_type="no_play", timeout="1", timeout_team="BUF", half_seconds_remaining="60"),
    ]
    op = H.operation(rows)
    assert op["snaps"] == {True: 4, False: 4}, op["snaps"]
    assert op["kinds"]["False Start"] == {True: 25.0, False: 0.0}
    assert op["kinds"]["Delay of Game"] == {True: 0.0, False: 25.0}
    assert op["kinds"]["all"] == {True: 25.0, False: 25.0}
    assert op["timeouts"] == {True: 25.0, False: 0.0}, "the late-half timeout is the clock's"
    assert op["botched"] == {True: 0.0, False: 25.0}


def test_the_no_huddle_gap_inside_one_team_down_and_distance():
    rows = []
    for i in range(3):
        rows.append(_row(no_huddle="1", epa="0.30", success="1", fixed_drive=f"d{i}"))
        rows.append(_row(no_huddle="0", epa="0.00", fixed_drive=f"d{i}"))
    # Another team's huddled plays in a different cell move nothing.
    rows += [_row(posteam="NYJ", down="2", epa="-1.0", fixed_drive="x")]
    out = H.no_huddle(rows)
    assert abs(out["within"] - 0.30) < 1e-9, out["within"]
    assert out["all"]["nh_n"] == 3 and out["all"]["hu_n"] == 4
    assert abs(out["all"]["nh_succ"] - 1.0) < 1e-9


def test_the_page_says_where_its_numbers_come_from():
    page = (ROOT / "docs" / "HUDDLE_RESEARCH.md").read_text(encoding="utf-8")
    assert "python3 tools/huddle_study.py" in page
    assert "0 on every play" in page, "the play clock's absence is said, not glossed"
    src = (ROOT / "tools" / "huddle_study.py").read_text(encoding="utf-8")
    assert "Offensive Too Many Men on Field" in src and '"Too Many Men on Field"' not in src


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
