"""A board that ships game bets must ship the history they open onto.

Ethan, 2026-08-26: "on nfl im not ablt to click on the game props and it
show me the bar graph and information and shit."

The click was working. What was missing was the DATA behind it. Every
game-bet card on the site is a door onto a chart of that team's last ten
results, and the chart is drawn from one payload key — `team_recent`.
The NFL's full build has attached it since the chart existed; its
schedule-only fallback, which is what the site publishes every day
between the schedule appearing and Week 1 being played, never did. So
for the whole run-up to a season every game bet on the board opened onto
"No recent results for this team yet", with the entire 2025 season sat
in the database one call away.

CFB had the same hole, unnoticed because its season had not started.

THE POINT OF THIS FILE is that neither is a one-line fix. It is a bug
CLASS — a payload that carries the pick and not the evidence — so the
rule is enforced across every build that publishes game bets, and the
next league to grow them fails here before a reader ever finds it.

Run directly: `python3 tests/test_gamebet_history.py`
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.teamlogs import recent_games                       # noqa: E402

#: Every build script that publishes a board.
BUILDS = ("nfl_build.py", "mlb_build.py", "cfb_build.py", "nba_build.py")


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def _ships_game_bets(src: str) -> bool:
    """True when the file puts anything but an empty list in that key.

    ``nba_build.py`` publishes ``"game_bets": []`` and nothing else — the
    league has no game-bet model — so it owes no history. The day it
    grows one, this returns True and the test below starts applying."""
    lines = [ln for ln in src.splitlines() if "game_bets" in ln]
    return any('"game_bets": []' not in ln for ln in lines)


def test_every_board_that_ships_game_bets_ships_their_history():
    missing = []
    for name in BUILDS:
        src = _read(name)
        if not _ships_game_bets(src):
            continue
        if "team_recent" not in src:
            missing.append(name)
    assert not missing, (
        f"{', '.join(missing)} publish game bets with no team_recent — "
        "every one of those cards opens onto an empty chart")


def test_each_of_them_reaches_the_same_place_for_it():
    """One source, not three. `engine/teamlogs.recent_games` is what the
    journal grades game bets against, so a chart drawn from anywhere
    else could disagree with the record on the same game."""
    for name in BUILDS:
        src = _read(name)
        if not _ships_game_bets(src):
            continue
        assert "recent_games" in src, \
            f"{name} builds team history from something other than teamlogs"


def test_a_missing_team_log_costs_the_chart_and_never_the_board():
    for name in BUILDS:
        src = _read(name)
        if "team_recent" not in src:
            continue
        assert src.count("team logs skipped") >= src.count('"team_recent"') - 1, \
            f"{name} attaches team history without a guard around it"


# --- the join, on real column values -----------------------------------------

def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE games (
        sport TEXT, season INTEGER, period TEXT, game_id TEXT,
        home TEXT, away TEXT, home_score REAL, away_score REAL)""")
    return conn


def _game(conn, sport, season, period, home, away, hs, as_):
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, "
                 "away, home_score, away_score) VALUES (?,?,?,?,?,?,?,?)",
                 (sport, season, period, f"{home}{period}", home, away, hs, as_))


def test_cfb_history_joins_on_the_abbreviations_the_board_uses():
    """The CFB board keys teams as UGA and CLEM — in the payload, in the
    game bets, and in the games table. A chart that keyed on school
    names would silently return nothing for every team."""
    conn = _db()
    for i, d in enumerate(("2026-09-05", "2026-09-12", "2026-09-19")):
        _game(conn, "cfb", 2026, d, "UGA", "CLEM", 30 + i, 20)
    conn.commit()
    got = recent_games(conn, "cfb", {"UGA", "CLEM"}, before="2026-09-26",
                       seasons=[2025, 2026])
    assert set(got) == {"UGA", "CLEM"}
    assert len(got["UGA"]) == 3
    assert got["UGA"][0]["margin"] == 12.0, "newest first, from the home side"


def test_the_cfb_window_reaches_back_a_season_so_week_one_has_a_chart():
    """`recent_games` defaults to the season the date falls in, which is
    right in November and empty on the opening Saturday. The NFL board
    already spans seasons (its periods are week numbers, so the date
    filter never bites), and the same card in two leagues should not
    show last season's form in one and a blank panel in the other."""
    conn = _db()
    for i, d in enumerate(("2025-11-01", "2025-11-08", "2025-11-15")):
        _game(conn, "cfb", 2025, d, "UGA", "AUB", 24, 17 + i)
    conn.commit()
    assert not recent_games(conn, "cfb", {"UGA"}, before="2026-08-30",
                            seasons=[2026]), "the one-season window is the bug"
    got = recent_games(conn, "cfb", {"UGA"}, before="2026-08-30",
                       seasons=[2025, 2026])
    assert len(got.get("UGA") or []) == 3
    src = _read("cfb_build.py")
    assert "seasons=[_season - 1, _season]" in src, \
        "the CFB board is back to charting only the season that just started"


def test_tonights_own_result_is_never_in_tonights_chart():
    """The rule `recent_games` exists to keep: a chart that included the
    game being priced would be reporting the answer as the reasoning."""
    conn = _db()
    _game(conn, "cfb", 2026, "2026-09-05", "UGA", "CLEM", 30, 20)
    _game(conn, "cfb", 2026, "2026-09-12", "UGA", "AUB", 31, 20)
    conn.commit()
    got = recent_games(conn, "cfb", {"UGA"}, before="2026-09-12",
                       seasons=[2026])
    assert [g["when"] for g in got["UGA"]] == ["2026-09-05"]


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
