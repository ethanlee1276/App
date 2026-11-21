"""A player's birthday on his game, as Real shows it.

Ethan, 2026-10-25, on Real: "It has live injuries. It shows players'
birthdays and stuff like that." The birth date rides in on each league's
own roster feed (Sleeper's `birth_date` for the NFL, ESPN's `dateOfBirth`
for the NBA and WNBA, the NHL's `birthDate`, MLB's hydrated person), onto
the published roster file; the live builders read that file once per
change and put the day's birthdays on each game (engine/rosters
.attach_birthdays), the game's own day in US Eastern time.

    python3 tests/test_birthdays_on_the_game.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import rosters as R                                 # noqa: E402

ROSTER = {"teams": {
    "CIN": {"players": [{"player": "Ja'Marr Chase", "born": "2000-03-01"},
                        {"player": "Old Hand", "born": "1990-03-01"},
                        {"player": "No Date", "born": ""}]},
    "PIT": {"players": [{"player": "Somebody", "born": "1998-07-04"}]}}}


def test_a_birth_date_is_kept_only_when_it_is_one():
    assert R._born("2000-03-01T08:00Z") == "2000-03-01"
    for bad in ("", None, "March 1", "2000/03/01"):
        assert R._born(bad) == "", bad


def test_the_birthdays_on_a_day_oldest_first_with_the_age_they_turn():
    got = R.birthdays(ROSTER, ["PIT", "CIN"], "2026-03-01")
    assert got == [{"player": "Old Hand", "team": "CIN", "age": 36},
                   {"player": "Ja'Marr Chase", "team": "CIN", "age": 26}]
    assert R.birthdays(ROSTER, ["CIN"], "2026-03-02") == []
    assert R.birthdays(ROSTER, ["CIN"], "") == []


def test_each_roster_source_carries_the_date():
    row = R._player_row({"full_name": "Ja'Marr Chase", "team": "CIN", "position": "WR",
                         "active": True, "birth_date": "2000-03-01"})
    assert row and row["born"] == "2000-03-01"
    feed = R.feed_rosters("nhl", {"PIT": [{"player": "Sidney Crosby", "position": "C", "born": "1987-08-07"}]})
    assert feed["teams"]["PIT"]["players"][0]["born"] == "1987-08-07"
    mlb = R.mlb_feed_rosters({"NYM": [{"name": "Pete Alonso", "position": "1B", "born": "1994-12-07"}]})
    assert mlb["teams"]["NYM"]["players"][0]["born"] == "1994-12-07"
    src = (ROOT / "engine" / "sources" / "espnrosters.py").read_text()
    assert '"born": str(a.get("dateOfBirth") or "")[:10]' in src
    mlbsrc = (ROOT / "engine" / "mlb" / "sources" / "mlbstats.py").read_text()
    assert '"born": str(person.get("birthDate") or "")[:10]' in mlbsrc


def test_a_game_gets_the_birthdays_of_its_own_day_in_eastern_time():
    """A 10:30pm Eastern game starts after midnight UTC; its birthdays are
    the Eastern day's, the one the broadcast calls it."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "rosters_nfl.json").write_text(json.dumps(ROSTER))
        games = [{"home": "CIN", "away": "PIT", "live": {"start_time": "2026-03-02T03:30:00Z"}},
                 {"home": "CIN", "away": "PIT", "live": {"start_time": "2026-03-02T18:00:00Z"}},
                 {"home": "CIN", "away": "PIT", "live": {"start_time": ""}}]
        assert R.attach_birthdays(games, "nfl", d) == 1
        assert [b["player"] for b in games[0]["birthdays"]] == ["Old Hand", "Ja'Marr Chase"]
        assert "birthdays" not in games[1] and "birthdays" not in games[2]
        assert R.attach_birthdays(games, "nba", d) == 0, "no roster file is no line, not an error"


def test_the_builders_put_them_on_the_game_and_its_page():
    ls = (ROOT / "livescore_build.py").read_text()
    i = ls.index("attach_birthdays(games, league,")
    assert i < ls.index("out[\"plays_note\"] = attach_plays(games, league", i), "the deep files are written after"
    assert 'doc["birthdays"] = list(g["birthdays"])' in ls
    lb = (ROOT / "live_build.py").read_text()
    assert 'attach_birthdays(games, "mlb",' in lb and '"birthdays": list(g["birthdays"])' in lb
    detail = (ROOT / "web" / "js" / "detail.js").read_text()
    assert "${pbpBirthdaysHTML(d)}" in detail
    fn = detail[detail.index("function pbpBirthdaysHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "escapeHtml(x.player)" in fn and "turns ${Number(x.age)}" in fn and 'if (!b.length) return "";' in fn


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
