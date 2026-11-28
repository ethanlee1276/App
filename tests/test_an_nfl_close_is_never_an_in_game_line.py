"""An NFL closing line is a pregame line, never one taken during the game.

Ethan's box run of closecheck.py, 2026-09-29: the one board's picks that
"lost the close" went 9-67, and the list said why — the closes were
in-game lines. AJ Barner receiving yards under 19.5 "closed" at 69.5 and
he finished with 69; Noah Fant 12.5 → 33.5, final 33; Joe Burrow passing
yards 255.5 → 349.5; Saquon Barkley receiving yards 7.5 → 79.5. A line
that tracks the box score as the game runs will always say the losing
side "lost the close".

The mechanism: the pregame cut (`linemoves._pregame_only`) needs each
snapshot stamped with its game's start, and `start_epoch` refuses a bare
clock — rightly, in general. An NFL game's kickoff IS a bare clock
(nflverse's `gametime`, "20:15", US Eastern), so no NFL snapshot was ever
stamped, the cut never ran, and every in-game re-price on a staggered
Sunday was eligible to be the close. The odds adapter now names the NFL
clock's zone, and the recorder stamps with it.

Fixture slate and a temp history file — never the box's.

Run directly: `python3 tests/test_an_nfl_close_is_never_an_in_game_line.py`
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import linemoves as LM                                   # noqa: E402

KICK = LM.start_epoch("20:15", "2026-09-28", "America/New_York")     # 00:15 UTC Sep 29


def _slate():
    game = NS(home="CHI", away="PHI", date="2026-09-28", kickoff="20:15")
    prop = NS(player="Colston Loveland", market="rec_yds", team="CHI", opponent="PHI",
              lines=[NS(book="fanduel", line=29.5, over_odds=-115, under_odds=-105)])
    slate = NS(props=[prop], game_for=lambda p: game)
    return slate, prop


def test_a_bare_nfl_clock_becomes_an_instant_only_with_its_zone():
    assert KICK == 1790640900.0                 # 2026-09-29 00:15:00 UTC
    assert LM.start_epoch("20:15") is None
    assert LM.start_epoch("20:15", "2026-09-28") is None, "no zone, no guess"
    assert LM.start_epoch("13:00", "2026-09-27", "America/New_York") == 1790528400.0   # 17:00 UTC
    assert LM.start_epoch("2026-09-28T23:10:00Z") == 1790637000.0       # full stamps unchanged
    assert LM.start_epoch("TBD", "2026-09-28", "America/New_York") is None


def test_the_recorder_stamps_an_nfl_snapshot_when_told_the_zone():
    slate, prop = _slate()
    path = Path(tempfile.mkdtemp()) / "hist.jsonl"
    LM.record_snapshots(slate.props, ts=KICK - 3600, path=path, slate=slate,
                        clock_tz="America/New_York")
    LM.record_snapshots(slate.props, ts=KICK - 3600, path=path, slate=slate)   # no zone
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert rows[0]["start_ts"] == KICK
    assert "start_ts" not in rows[1], "without a zone the recorder still refuses to guess"


def test_the_in_game_line_is_not_the_close():
    slate, prop = _slate()
    path = Path(tempfile.mkdtemp()) / "hist.jsonl"
    # 7 PM ET, pregame: 29.5. Then 10:30 PM ET, the second half: 59.5.
    LM.record_snapshots(slate.props, ts=KICK - 4500, path=path, slate=slate,
                        clock_tz="America/New_York")
    prop.lines[0].line = 59.5
    LM.record_snapshots(slate.props, ts=KICK + 8100, path=path, slate=slate,
                        clock_tz="America/New_York")
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    closes = LM.closing_lines_by_date(rows)
    got = {k: v for k, v in closes.items() if k[1] == "rec_yds"}
    assert list(got.values()) == [29.5], got


def test_the_odds_adapter_names_the_nfl_clock():
    src = (ROOT / "engine" / "sources" / "oddsapi.py").read_text()
    assert ('record_snapshots(slate.props, slate=slate,\n'
            '                         clock_tz="America/New_York" if sport == "nfl" else None)') in src


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
