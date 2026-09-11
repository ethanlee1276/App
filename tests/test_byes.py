"""The one fact on the draft board.

Ethan, 2026-08-20: "continue on what was still on your list with the bye
week shit and te premium and shit like that."

Everything else in the draft kit is a projection and can be argued with.
The schedule is published, nobody disputes it, and it decides whether the
roster somebody just drafted has three starters missing in week eleven.
Every mock draft simulator worth copying shows it; ours had no idea the
concept existed.

DERIVED, NOT LISTED, which is the whole discipline here. A hard-coded
table of thirty-two bye weeks is a table that is silently wrong the year
the league moves one, and it moves most years. The schedule is already
ingested for everything else, so a bye is the regular-season week a team
appears in neither column — read off the same rows the model grades
itself against.

AND THE REGULAR SEASON IS MEASURED TOO. "Week <= 18" is only true of the
current era: the regular season was seventeen weeks until 2021 and will
change again. A play-off week is one where most of the league is not
playing, which stays true whatever the schedule does, and getting it
wrong turns every eliminated team's January into phantom byes.

Run directly: `python3 tests/test_byes.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import byes, db                                   # noqa: E402


def _conn(rows):
    c = db.connect(":memory:")
    c.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away) "
        "VALUES (?,?,?,?,?,?)", rows)
    return c


def _season(teams, weeks, bye_of):
    """A tidy round-robin: every team plays every week except its bye."""
    rows = []
    gid = 0
    for w in range(1, weeks + 1):
        free = [t for t in teams if bye_of.get(t) != w]
        for i in range(0, len(free) - 1, 2):
            gid += 1
            rows.append(("nfl", 2026, f"{w:03d}", f"g{gid}", free[i], free[i + 1]))
    return rows


TEAMS = [f"T{i:02d}" for i in range(1, 17)]
BYES = {t: 5 + (i % 8) for i, t in enumerate(TEAMS)}


def test_a_bye_is_the_week_a_team_is_not_on_the_schedule():
    c = _conn(_season(TEAMS, 14, BYES))
    got = byes.bye_weeks(c, 2026)
    assert got == BYES, {k: (v, BYES[k]) for k, v in got.items() if BYES[k] != v}


def test_the_play_offs_do_not_hand_out_phantom_byes():
    """Every eliminated team misses every play-off week. Counting those
    would give most of the league a fistful of byes and no team a real
    one — and a wrong bye is worse than a missing one, because a missing
    one shows up as a blank and a wrong one quietly clears a real clash."""
    rows = _season(TEAMS, 14, BYES)
    # Four teams play on into weeks 15-16; the other twelve are done.
    gid = 9000
    for w in (15, 16):
        for i in range(0, 4, 2):
            gid += 1
            rows.append(("nfl", 2026, f"{w:03d}", f"g{gid}", TEAMS[i], TEAMS[i + 1]))
    got = byes.bye_weeks(_conn(rows), 2026)
    assert got == BYES, "a play-off week was counted as part of the season"


def test_a_team_with_a_partial_schedule_is_omitted_not_guessed():
    """Mid-ingest, or a season not yet published in full. Reporting
    nothing for that team is the honest answer."""
    rows = [r for r in _season(TEAMS, 14, BYES)
            if TEAMS[0] not in (r[4], r[5]) or r[2] != "007"]
    got = byes.bye_weeks(_conn(rows), 2026)
    assert TEAMS[0] not in got, "a team missing two weeks was given one of them"
    assert len(got) >= len(TEAMS) - 2, "one gap should not lose the whole league"


def test_a_season_we_do_not_hold_returns_nothing():
    assert byes.bye_weeks(_conn(_season(TEAMS, 14, BYES)), 1999) == {}


def test_the_board_carries_it_and_says_how_many():
    board = [{"player": "A", "team": TEAMS[0]}, {"player": "B", "team": "ZZZ"}]
    n = byes.attach(board, BYES)
    assert n == 1, "attach did not report what it stamped"
    assert board[0]["bye"] == BYES[TEAMS[0]]
    assert "bye" not in board[1], "an unknown team was given a bye anyway"


def test_the_kit_stamps_the_board():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "fantasy_draft.py"),
        encoding="utf-8").read()
    assert "bye_weeks(conn, season)" in src, "the kit no longer reads byes"
    # And receptions, which is what makes a PPR variant arithmetic rather
    # than a guessed catch rate.
    assert '"rec_pg"' in src, "the board dropped receptions again"
    assert 'm.get("receptions"' in src, "receptions are being estimated"


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
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line; "all good" matches nothing and scores the file zero while
    # still drawing it green.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
