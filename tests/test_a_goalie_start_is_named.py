"""Every NHL game side has a starting goalie (2026-11-18, walk 15, step YE).

Connor Hellebuyck's page read GS 0 beside seven games, and Andrei
Vasilevskiy's 351 saves came with six starts: in many stored games neither of
a side's goalies carried the box score's starter flag. The goalie model counts
those flags to name each club's probable starter and backup, so the reader now
names a side's starter by time in net when the box flags none, and
engine/nhlstarts marks the games stored before (nothing without --apply).

    python3 tests/test_a_goalie_start_is_named.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D, nhlstarts                                            # noqa: E402
from engine.sources import nhldata                                               # noqa: E402


def _goalie(pid, name, toi, sa, ga, starter=None):
    g = {"playerId": pid, "name": {"default": name}, "toi": toi, "shotsAgainst": sa, "saves": sa - ga,
         "goalsAgainst": ga, "saveShotsAgainst": f"{sa - ga}/{sa}"}
    if starter is not None:
        g["starter"] = starter
    return g


def _box(home_goalies, away_goalies):
    return {"homeTeam": {"abbrev": "NJD"}, "awayTeam": {"abbrev": "WSH"},
            "playerByGameStats": {"homeTeam": {"forwards": [], "defense": [], "goalies": home_goalies},
                                  "awayTeam": {"forwards": [], "defense": [], "goalies": away_goalies}}}


def _starts(rows):
    return {r["short"]: r["started"] for r in rows if r.get("goalie")}


def test_a_box_that_flags_no_starter_names_the_goalie_longest_in_net():
    rows = nhldata.parse_boxscore(_box([_goalie(1, "C. Hellebuyck", "60:00", 47, 4)],
                                       [_goalie(2, "L. Thompson", "40:00", 20, 4), _goalie(3, "C. Lindgren", "18:30", 9, 1)]))
    got = _starts(rows)
    assert got == {"C. Hellebuyck": 1.0, "L. Thompson": 1.0, "C. Lindgren": 0.0}, got


def test_a_flagged_starter_is_believed_even_when_pulled():
    rows = nhldata.parse_boxscore(_box([_goalie(1, "C. Hellebuyck", "60:00", 30, 2, starter=True)],
                                       [_goalie(2, "L. Thompson", "12:00", 8, 4, starter=True),
                                        _goalie(3, "C. Lindgren", "46:00", 20, 1, starter=False)]))
    got = _starts(rows)
    assert got == {"C. Hellebuyck": 1.0, "L. Thompson": 1.0, "C. Lindgren": 0.0}, got


def _db():
    conn = D.connect(Path(tempfile.mkdtemp()) / "t.db")
    rows = [  # (period, game, player, team, toi, started)
        ("2026-11-14", "g1", "Connor Hellebuyck", "NJD", 60.0, 0.0),
        ("2026-11-14", "g1", "Logan Thompson", "WSH", 58.0, 0.0),
        ("2026-11-14", "g1", "Charlie Lindgren", "WSH", 2.0, 0.0),
        ("2026-11-12", "g2", "Connor Hellebuyck", "NJD", 60.0, 1.0),       # flagged: left alone
        ("2026-11-12", "g2", "Jake Allen", "NJD", 0.0, 0.0),
    ]
    for period, gid, player, team, toi, started in rows:
        for market, value in (("toi", toi), ("started", started), ("saves", 20.0)):
            conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                         "position, home, market, value) VALUES ('nhl', 2026, ?, ?, ?, ?, 'X', 'G', 1, ?, ?)",
                         (period, gid, player, team, market, value))
    conn.commit()
    return conn


def test_the_stored_games_are_found_and_marked_only_with_apply():
    conn = _db()
    rep = nhlstarts.found(conn, 2026)
    assert [(r["game_id"], r["team"], r["player"]) for r in rep["sides"]] == \
        [("g1", "NJD", "Connor Hellebuyck"), ("g1", "WSH", "Logan Thompson")], rep
    started = lambda: dict(conn.execute("SELECT player, SUM(value) FROM player_game_logs WHERE market='started' "  # noqa: E731
                                        "GROUP BY player").fetchall())
    assert started()["Connor Hellebuyck"] == 1.0, "nothing written by finding"
    assert nhlstarts.apply(conn, rep) == 2
    assert started() == {"Connor Hellebuyck": 2.0, "Logan Thompson": 1.0, "Charlie Lindgren": 0.0, "Jake Allen": 0.0}
    assert nhlstarts.found(conn, 2026)["sides"] == [], "run again: nothing left"


def test_the_runbook_names_the_command():
    doc = (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    assert "python3 -m engine.nhlstarts" in doc


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
