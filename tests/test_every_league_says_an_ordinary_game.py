"""Every league's record says what an ordinary game does (step AIL, 27 November 2026).

The Record grades a read on the player's stat against the average of the player's previous games, and the NFL's
says beside it how often an ordinary game beats that average (42%) or falls short (57%). The other leagues said
nothing, so hockey's fades ("right 47 of 104, 45%") could not be read against anything. engine/basefit measures each
league's ordinary game the same way, weekly, on the history database, and engine/reportrecord says it beside that
league's record. The numbers below are this test's own.

    python3 tests/test_every_league_says_an_ordinary_game.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import basefit as B                                      # noqa: E402
from engine import db                                                # noqa: E402
from engine import reportrecord as RR                                # noqa: E402


def _conn(rows):
    conn = db.connect(":memory:")
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return conn


def _games(sport, player, team, pos, pts, mins, season=2026, stat="pts", vol="min"):
    out = []
    for i, (p, m) in enumerate(zip(pts, mins), 1):
        day = f"2026-11-{i:02d}"
        out += [(sport, season, day, f"g{i}", player, team, "OPP", pos, 1, stat, p),
                (sport, season, day, f"g{i}", player, team, "OPP", pos, 1, vol, m)]
    return out


def test_a_key_player_is_graded_against_the_games_before():
    # Game 3 on: 20 against (10, 30) avg 20 = even; 40 > 20 = over; 10 < 25 = under; 30 > 25 = over.
    rows = _games("nba", "Starter One", "AAA", "G", [10, 30, 20, 40, 10, 30], [30] * 6)
    # A bench player (under 24 minutes) is not a key player, whatever the points.
    rows += _games("nba", "Bench Two", "AAA", "G", [1, 2, 50, 60, 70, 80], [10] * 6)
    old = B.MIN_GAMES
    B.MIN_GAMES = 1
    try:
        m = B.measure(_conn(rows), "nba")
    finally:
        B.MIN_GAMES = old
    assert m["n"] == 4 and m["over"] == 0.5 and m["under"] == 0.25 and m["even"] == 0.25, m
    assert m["seasons"] == "2024–2026", m


def test_hockey_reads_shots_and_leaves_goalies_out():
    rows = _games("nhl", "Shooter", "BBB", "C", [2, 4, 1, 5], [18] * 4, stat="sog", vol="toi")
    rows += _games("nhl", "Keeper", "BBB", "G", [0, 0, 9, 9], [60] * 4, stat="sog", vol="toi")
    old = B.MIN_GAMES
    B.MIN_GAMES = 1
    try:
        m = B.measure(_conn(rows), "nhl")
    finally:
        B.MIN_GAMES = old
    assert m["n"] == 2 and m["under"] == 0.5 and m["over"] == 0.5, m
    assert B.measure(_conn(rows), "nhl") is None, "too few games says nothing"


def test_the_file_and_the_heartbeat_line():
    rows = _games("nba", "Starter One", "AAA", "G", [10, 30, 20, 40, 10, 30], [30] * 6)
    old = B.MIN_GAMES
    B.MIN_GAMES = 1
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "base_rates.json"
            res = B.refresh(_conn(rows), path=path, leagues=["nba", "nhl"])
            saved = json.loads(path.read_text())
    finally:
        B.MIN_GAMES = old
    assert set(saved["leagues"]) == {"nba"} and saved["leagues"]["nba"]["n"] == 4, saved
    assert B.summary_line(res) == "base rates: nba 50.0% over / 25.0% under (4 games, 2024–2026)", B.summary_line(res)
    assert B.summary_line({"leagues": {}}) == "base rates: no league had enough games"


def test_the_record_says_it_beside_every_league():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "base_rates.json"
        path.write_text(json.dumps({"leagues": {"nhl": {"over": 0.38, "under": 0.6, "even": 0.02, "n": 9000,
                                                        "seasons": "2024–2026"}}}))
        old = B.BASE_PATH
        B.BASE_PATH = path
        RR._MEASURED.clear()
        try:
            words = RR.base_words("nhl")
            nfl = RR.base_words("nfl")
            none = RR.base_words("cbb")
        finally:
            B.BASE_PATH = old
            RR._MEASURED.clear()
    assert words == ("For comparison, a key player in an ordinary game beats that average 38% of the time and falls "
                     "short of it 60% (measured over the 2024–2026 seasons)"), words
    assert "42%" in nfl and "57%" in nfl, "the NFL's own measurement stays"
    assert none == "", "a league not measured says nothing"


def test_it_runs_with_the_weekly_refit():
    mt = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = mt[mt.index("def _run_deep_refit("):mt.index("def _continue_deep_refit(")]
    assert '+ _spawn_module("engine.basefit", log)' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
