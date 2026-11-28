"""The night keeps the basketball history to its leagues' own games (step ABV, 22 November 2026).

Ethan, the Sunday morning: "We want every single sports player pages to match each other and like have it match
ESPN." The live player pages still counted games no league plays: Caitlin Clark's 2026 season the All-Star Game
("IND/SPO") and exhibitions against "COOP" and Nigeria; A'ja Wilson's every season since 2021 an All-Star side
(USA, WIL, CLA, SPO); Jalen Brunson's 2024-25 and 2023-24 the NBA's (STRIPES, KEN). The writer has refused such
games since 17 November, and the two commands that take out what it stored before (engine/hoopsexhibitions,
engine/hoopspreseason) waited to be typed on the box. What these hold:

  * the night takes out every stored game with a side that is no club of its league, as long as that side has
    only a handful of stored games; a side with more (a club the division tables do not list yet) is said and
    left alone;
  * the night moves each stored season's preseason games to the preseason tables, asking the scoreboard about a
    bounded number of days a night, a season whose every day answered never asked again, one that did not
    answer asked again the next night;
  * both run from the nightly chores, each failure said.

    python3 tests/test_the_night_keeps_the_basketball_history_to_league_games.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import maintenance as M                                    # noqa: E402

PRE = __import__("test_a_preseason_game_is_no_seasons")               # its stored seasons (a sibling test file)


def _add(conn, sport, season, day, gid, home, away):
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                 "VALUES (?,?,?,?,?,?,?,?)", (sport, season, day, gid, home, away, 100, 90))
    for player, team, opp in (("A One", home, away), ("B Two", away, home)):
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (sport, season, day, gid, player, team, opp, "G", int(team == home), "pts", 20))


def _count(conn, sport, gid):
    return (conn.execute("SELECT COUNT(*) FROM games WHERE sport=? AND game_id=?", (sport, gid)).fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport=? AND game_id=?", (sport, gid)).fetchone()[0])


def test_the_all_star_and_exhibition_games_go_and_an_unlisted_club_stays():
    conn = PRE._db()
    _add(conn, "wnba", 2026, "2026-07-25", "as26", "SPO", "COOP")        # the All-Star Game
    _add(conn, "wnba", 2026, "2026-05-02", "ex26", "IND", "NIGER")       # an exhibition
    _add(conn, "nba", 2025, "2025-02-16", "as25", "STRIPES", "KEN")      # the NBA's tournament
    for i in range(M.EXHIBITION_MAX_GAMES + 1):                          # a club engine/divisions does not list yet
        _add(conn, "wnba", 2026, f"2026-06-{10 + i:02d}", f"new{i}", "NEWC", "IND")
    conn.commit()
    said = []
    gone = M.hoops_exhibitions_out(conn, said.append)
    assert gone > 0
    for sport, gid in (("wnba", "as26"), ("wnba", "ex26"), ("nba", "as25")):
        assert _count(conn, sport, gid) == (0, 0), (sport, gid)
    assert _count(conn, "wnba", "new0") == (1, 2), "a side with a club's number of games is left alone"
    assert _count(conn, "wnba", "401700002") == (1, 4), "a league game stays"
    text = " ".join(said)
    assert "NEWC is no WNBA club in engine/divisions" in text and "left alone" in text, said
    assert "All-Star or exhibition game(s) taken out" in text, said
    assert M.hoops_exhibitions_out(conn, said.append) == 0, "and the next look finds none"


def test_the_preseason_moves_a_bounded_number_of_days_a_night_and_a_season_once():
    conn = PRE._db()
    state, asked, said = {}, [], []
    moved = M.hoops_preseason_out(state, conn, said.append, load_for=lambda _lg: PRE._load(asked), per_night=100)
    assert moved == 3, (moved, said)
    assert _count(conn, "nba", "401812684") == (0, 0) and _count(conn, "nba", "401809234") == (1, 4)
    assert _count(conn, "wnba", "401700001") == (0, 0)
    assert conn.execute("SELECT COUNT(*) FROM preseason_games WHERE sport IN ('nba','wnba')").fetchone()[0] == 3
    # The season whose day did not answer (2026-10-22) is asked again; the others never.
    assert 2025 in state["hoops_preseason_done"]["nba"] and 2026 not in state["hoops_preseason_done"]["nba"]
    assert any("unread" in s for s in said), said
    asked.clear()
    M.hoops_preseason_out(state, conn, said.append, load_for=lambda _lg: PRE._load(asked), per_night=100)
    assert asked == ["2026-10-22"], asked
    # A night asks no more than its share; the rest wait.
    state2, asked2 = {}, []
    M.hoops_preseason_out(state2, PRE._db(), said.append, load_for=lambda _lg: PRE._load(asked2), per_night=3)
    assert len(asked2) <= 3 and asked2, asked2


def test_the_nightly_chores_run_both():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("# The basketball history, its leagues' own games only (step ABV)")
    block = src[i:i + 1400]
    assert "hoops_exhibitions_out(_hconn, log)" in block and "hoops_preseason_out(state, _hconn, log)" in block
    assert "HOOPS_CLEAN_EVERY_DAYS * 86400" in block
    assert "⚠️  basketball history: taking out the All-Star and exhibition games failed" in block
    assert "⚠️  basketball history: moving the preseason games out failed" in block
    run_next = (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    assert "the night does it since ABV" in run_next


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
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
