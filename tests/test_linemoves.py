"""Tests for line-movement analysis (pure, no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.linemoves import analyze, record_snapshots, load_history
from engine.models import Prop, GameLog, SportsbookLine, RUSH_YDS

NOW = 10_000.0


def _snap(ts, book, line, player="RB One", market="rush_yds"):
    return {"ts": ts, "player": player, "market": market, "book": book,
            "line": line, "over_odds": -110}


def test_steam_when_books_move_together():
    rows = []
    for book in ("DraftKings", "FanDuel", "BetMGM"):
        rows.append(_snap(NOW - 3000, book, 70.5))
        rows.append(_snap(NOW - 600, book, 72.0))
    reports = analyze(rows, now=NOW)
    assert len(reports) == 1
    r = reports[0]
    assert r.open == 70.5 and r.current == 72.0 and r.direction == "up"
    assert r.steam is True


def test_single_book_move_is_not_steam():
    rows = [
        _snap(NOW - 3000, "DraftKings", 70.5), _snap(NOW - 600, "DraftKings", 72.0),
        _snap(NOW - 3000, "FanDuel", 70.5), _snap(NOW - 600, "FanDuel", 70.5),
        _snap(NOW - 3000, "BetMGM", 70.5), _snap(NOW - 600, "BetMGM", 70.5),
    ]
    reports = analyze(rows, now=NOW)
    assert len(reports) == 1
    assert reports[0].steam is False


def test_stale_moves_do_not_steam():
    # Both books moved, but hours ago — outside the steam window.
    rows = []
    for book in ("DraftKings", "FanDuel"):
        rows.append(_snap(NOW - 90_000, book, 70.5))
        rows.append(_snap(NOW - 80_000, book, 72.0))
    reports = analyze(rows, now=NOW, window_s=3600)
    assert reports and reports[0].steam is False
    assert reports[0].delta == 1.5


def test_unmoved_board_is_silent():
    # Cached re-records of an identical board must not fabricate movement.
    rows = [_snap(NOW - i * 600, "DraftKings", 70.5) for i in range(5)]
    assert analyze(rows, now=NOW) == []


def test_down_moves_report_direction():
    rows = [
        _snap(NOW - 3000, "DraftKings", 250.5, player="QB A", market="pass_yds"),
        _snap(NOW - 500, "DraftKings", 244.5, player="QB A", market="pass_yds"),
        _snap(NOW - 3000, "FanDuel", 250.5, player="QB A", market="pass_yds"),
        _snap(NOW - 500, "FanDuel", 245.5, player="QB A", market="pass_yds"),
    ]
    r = analyze(rows, now=NOW)[0]
    assert r.direction == "down" and r.steam is True and r.delta < 0


def test_record_skips_proxy_and_roundtrips(tmp_path=None):
    import tempfile, pathlib
    path = pathlib.Path(tempfile.mkdtemp()) / "hist.jsonl"
    prop = Prop("RB One", "GB", "CHI", "RB", RUSH_YDS,
                [GameLog(1, "X", 80)], 80, None,
                [SportsbookLine("DraftKings", 70.5, -110, -110),
                 SportsbookLine("proxy", 71.5, -110, -110)], "rb1")
    n = record_snapshots([prop], ts=NOW, path=path)
    assert n == 1  # proxy line skipped
    rows = load_history(path)
    assert len(rows) == 1 and rows[0]["book"] == "DraftKings"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
