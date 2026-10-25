"""Tomorrow's games are not "priced events that could not be placed" (2026-10-25).

The bug scan, night after night on the NBA: "8 priced event(s) could not be
placed on the slate". The odds endpoint returns every upcoming fixture, and
`slate_days` keeps a day either side of the slate because a 10:30pm Eastern
tip is already tomorrow in UTC — so on a Saturday slate every one of
Sunday's games sat inside the window, was not one of our pairs, and was
reported as a wiring drop. `off_slate_day` asks, of a pair that is NOT on
the slate only, whether its Eastern day is one of the slate's days; a later
day's game is counted with the other days, and a genuine mismatch on the
slate's own day is still a drop.

Run directly: `python3 tests/test_tomorrows_games_are_not_a_dropped_slate.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import oddsapi as O  # noqa: E402

#: A Saturday NBA slate as the CDN dates it: the Eastern day, a UTC kickoff.
SLATE = [{"home": "NYK", "away": "PHI", "date": "2026-10-24", "kickoff": "2026-10-24T23:30:00Z"},
         {"home": "LAL", "away": "GSW", "date": "2026-10-24", "kickoff": "2026-10-25T02:30:00Z"}]


def test_the_eastern_day_of_an_instant():
    assert O._eastern_day("2026-10-25T02:30:00Z") == "2026-10-24", "10:30pm Eastern is still Saturday"
    assert O._eastern_day("2026-10-25T19:00:00Z") == "2026-10-25"
    assert O._eastern_day("") == "" and O._eastern_day("soon") == ""


def test_sundays_game_is_another_day_and_a_saturday_mismatch_is_not():
    sunday = {"home_team": "Boston Celtics", "away_team": "Miami Heat", "commence_time": "2026-10-25T19:00:00Z"}
    late_saturday = {"home_team": "Denver Nuggets", "away_team": "Utah Jazz", "commence_time": "2026-10-25T03:00:00Z"}
    # Both sit inside the padded window the old check used …
    days = O.slate_days(SLATE)
    assert not O.other_day(sunday, days) and not O.other_day(late_saturday, days)
    # … and only Sunday's is another day's game.
    assert O.off_slate_day(sunday, SLATE) is True
    assert O.off_slate_day(late_saturday, SLATE) is False, "a missing pair on the slate's own day is still a drop"


def test_a_slate_with_no_dates_reads_its_kickoffs_in_eastern():
    bare = [{"home": "NYK", "away": "PHI", "kickoff": "2026-10-25T00:00:00Z"}]   # 8pm Saturday Eastern
    assert O.off_slate_day({"commence_time": "2026-10-25T19:00:00Z"}, bare) is True
    assert O.off_slate_day({"commence_time": "2026-10-24T23:00:00Z"}, bare) is False
    assert O.off_slate_day({"commence_time": "2026-10-25T19:00:00Z"}, []) is False, "no slate days, no verdict"


def test_both_paths_ask_before_they_drop():
    src = (ROOT / "engine" / "sources" / "oddsapi.py").read_text(encoding="utf-8")
    assert src.count("off_slate_day(ev, slate.games)") == 2
    assert "if not legs and off_slate_day(ev, slate.games):" in src
    assert "not in slate_pairs and off_slate_day(ev, slate.games):" in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
