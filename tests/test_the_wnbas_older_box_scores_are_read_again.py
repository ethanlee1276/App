"""The WNBA's older box scores are read again with every column, by the night (step ABO, 22 November 2026).

Ethan, the Sunday morning: "We want every single sports player pages to match each other ... NFL is kind of like
the one we want to go off of." Every WNBA player page showed four columns (MIN, PTS, REB, AST) where the NBA's
show fifteen: the box-score reader learned steals, blocks and turnovers (13 October) and field goals, free throws
and offensive rebounds (20 October) after the WNBA's season had ended, and RUN_NEXT 00i, the re-read by hand,
was never run. What these hold:

  * the stored WNBA days whose lines carry no steals are found, oldest first (`wnba_days_short`);
  * the night reads them again, a few dozen a night and each twice at most, until none is left, and says how
    many are left (`wnba_box_refill`); a scoreboard that does not answer stops it for the night;
  * the night runs it whatever the month, after the WNBA's own results.

    python3 tests/test_the_wnbas_older_box_scores_are_read_again.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, maintenance as M  # noqa: E402


def _conn():
    return db.connect(Path(tempfile.mkdtemp()) / "history.db")


def _line(day, player, market, value, season=2026, game="g"):
    return {"sport": "wnba", "season": season, "period": day, "game_id": f"{game}{day}", "player": player,
            "team": "LVA", "opponent": "IND", "position": "F", "home": 1, "market": market, "value": value}


def _store(conn, day, markets=("min", "pts", "reb", "ast"), season=2026):
    db.upsert_player_logs(conn, [_line(day, "A'ja Wilson", m, 10.0, season) for m in markets])


def test_the_days_filed_before_every_column_are_found_oldest_first():
    c = _conn()
    _store(c, "2026-07-02")
    _store(c, "2026-06-01")
    _store(c, "2026-07-10", markets=("min", "pts", "reb", "ast", "stl", "blk"))   # read with every column
    _store(c, "2023-07-01", season=2023)                                           # outside the seasons
    db.upsert_player_logs(c, [dict(_line("2026-06-01", "x", "pts", 3.0), sport="nba")])
    assert M.wnba_days_short(c) == ["2026-06-01", "2026-07-02"], M.wnba_days_short(c)
    assert M.wnba_days_short(None) == []


def test_the_night_reads_them_again_until_none_is_left():
    c = _conn()
    for d in ("2026-06-01", "2026-06-03", "2026-06-05"):
        _store(c, d)
    asked, said = [], []

    def ingest(day):
        asked.append(day)
        _store(c, day, markets=("min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga"))
        return {"games": 1, "player_logs": 9, "skipped": []}
    state = {}
    assert M.wnba_box_refill(state, c, ingest, log=said.append, per_night=2) == 2
    assert asked == ["2026-06-01", "2026-06-03"] and said[-1].endswith("2 day(s) read again with every column, 1 left")
    assert M.wnba_box_refill(state, c, ingest, log=said.append, per_night=2) == 1
    assert asked[-1] == "2026-06-05" and said[-1].endswith("none left")
    assert M.wnba_box_refill(state, c, ingest, log=said.append) == 0, "nothing to do once every day has its steals"


def test_a_day_the_feed_cannot_fill_is_read_twice_at_most_and_a_dead_scoreboard_stops_the_night():
    c = _conn()
    _store(c, "2026-06-01")
    _store(c, "2026-06-02")
    tries = []

    def stubborn(day):
        tries.append(day)
        return {"games": 1, "player_logs": 4, "skipped": []}       # read, still no steals
    state = {}
    for _ in range(4):
        M.wnba_box_refill(state, c, stubborn, log=lambda *_: None)
    assert tries.count("2026-06-01") == M.WNBA_REFILL_TRIES == 2
    said = []

    def down(day):
        return {"games": 0, "player_logs": 0, "skipped": [f"wnba scoreboard {day}: refused"]}
    c2 = _conn()
    _store(c2, "2026-06-01")
    _store(c2, "2026-06-02")
    assert M.wnba_box_refill({}, c2, down, log=said.append) == 0
    assert len(said) == 1 and "the rest wait for tomorrow night" in said[0], said


def test_the_night_runs_it():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index("def _run_chores("):]
    assert "wnba_box_refill(state, _hconn, lambda day: _wnba_day(_wrconn, day), log)" in body
    i = body.index("wnba_box_refill(state, _hconn")
    assert body.rindex("if 5 <= today.month <= 10 and _wnba_day is not None:", 0, i) < i, "after the WNBA's results"
    assert "if _wnba_day is not None and _hconn is not None:" in body[i - 400:i], "whatever the month"
    run_next = (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    assert "the night does it since ABO" in run_next


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
