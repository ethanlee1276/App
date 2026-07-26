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


def test_closing_lines_picks_the_last_pregame_number():
    """CLV needs the closing line: the last snapshot before the game starts,
    medianed across books so one outlier can't define the close."""
    import tempfile
    from pathlib import Path
    from engine.linemoves import record_snapshots, load_history, closing_lines
    from engine.models import Prop, SportsbookLine, GameLog, REC_YDS

    tmp = Path(tempfile.mkdtemp()) / "moves.jsonl"

    def prop_at(line, book="DraftKings"):
        return Prop(player="Ja'Marr Chase", team="CIN", opponent="PIT", position="WR",
                    market=REC_YDS, logs=[GameLog(week=1, opponent="X", value=70)],
                    career_avg=70, vs_opponent_avg=None,
                    lines=[SportsbookLine(book, line, -110, -110)])

    record_snapshots([prop_at(68.5)], ts=1000, path=tmp)
    record_snapshots([prop_at(74.5, "DraftKings")], ts=3000, path=tmp)
    record_snapshots([prop_at(75.5, "FanDuel")], ts=3000, path=tmp)
    record_snapshots([prop_at(99.0)], ts=9999, path=tmp)      # post-game, ignore

    rows = load_history(tmp)
    close = closing_lines(rows, before_ts=5000)
    assert close[("Ja'Marr Chase", "rec_yds")] == 75.0        # median of 74.5/75.5
    # Without a cutoff the latest snapshot wins (documents the cutoff's purpose).
    assert closing_lines(rows)[("Ja'Marr Chase", "rec_yds")] == 99.0


def _psnap(ts, book, odds, line=0.5, player="Slugger", market="home_runs"):
    return {"ts": ts, "player": player, "market": market, "book": book,
            "line": line, "over_odds": odds}


def test_price_movement_on_a_static_line():
    """MLB props often sit on a fixed 0.5/1.5 line and move through the
    JUICE — the line never budges, the odds do. That must count as
    movement (it's the only kind HR props ever show)."""
    rows = []
    for book in ("DraftKings", "FanDuel"):
        rows.append(_psnap(NOW - 3000, book, +150))
        rows.append(_psnap(NOW - 600, book, +115))    # over shortening hard
    r = analyze(rows, now=NOW)[0]
    assert r.delta == 0 and r.direction == "up" and r.steam is True
    assert r.open_odds == 150 and r.current_odds == 115
    assert r.prob_delta > 0.05


def test_static_price_and_line_stay_silent():
    rows = [_psnap(NOW - i * 600, "DraftKings", +150) for i in range(5)]
    assert analyze(rows, now=NOW) == []


def test_annotate_stamps_verdict_for_our_side():
    from engine.linemoves import annotate_recommendations

    rows = []
    for book in ("DraftKings", "FanDuel", "BetMGM"):
        rows.append(_snap(NOW - 3000, book, 70.5))
        rows.append(_snap(NOW - 600, book, 72.0))     # line up = toward Over
    reports = analyze(rows, now=NOW)

    over = {"player": "RB One", "market": "rush_yds", "side": "OVER",
            "has_market": True, "reasons": [], "warnings": []}
    under = {"player": "RB One", "market": "rush_yds", "side": "UNDER",
             "has_market": True, "reasons": [], "warnings": []}
    proxy = {"player": "RB One", "market": "rush_yds", "side": "OVER",
             "has_market": False, "reasons": [], "warnings": []}
    unmoved = {"player": "Nobody", "market": "rush_yds", "side": "OVER",
               "has_market": True, "reasons": [], "warnings": []}

    n = annotate_recommendations([over, under, proxy, unmoved], reports)
    assert n == 2
    # Same move, opposite meanings: agreement is a reason, a fade is a warning.
    assert over["line_move"]["verdict"] == "with" and over["line_move"]["steam"]
    assert any("Market moving toward the Over" in r for r in over["reasons"])
    assert under["line_move"]["verdict"] == "against"
    assert any("Market moving against the Under" in w for w in under["warnings"])
    # Proxy lines and unmoved props get no stamp — nothing is fabricated.
    assert "line_move" not in proxy and "line_move" not in unmoved


def test_todays_rows_drops_yesterdays_board():
    """MLB plays daily — yesterday's snapshot of the same player/market must
    never chain onto today's and fabricate movement between two games."""
    from engine.linemoves import todays_rows
    import datetime as dt
    noon = dt.datetime(2026, 7, 26, 12, 0).timestamp()
    rows = [_snap(noon - 20 * 3600, "DraftKings", 70.5),   # yesterday evening
            _snap(noon - 3600, "DraftKings", 72.0),
            _snap(noon - 600, "DraftKings", 72.0)]
    kept = todays_rows(rows, now=noon)
    assert len(kept) == 2
    assert analyze(kept, now=noon) == []                   # today never moved


def test_closing_lines_by_date_takes_each_days_last_snapshot():
    """The journal's free CLV source: each day gets ITS OWN close (the last
    snapshot that day), keyed by normalized player name."""
    import datetime as dt
    from engine.linemoves import closing_lines_by_date
    d1 = dt.datetime(2026, 7, 24, 12, 0).timestamp()
    d2 = dt.datetime(2026, 7, 25, 12, 0).timestamp()
    rows = [_snap(d1, "DraftKings", 70.5, player="RB Oné"),
            _snap(d1 + 7 * 3600, "DraftKings", 72.0, player="RB Oné"),   # day-1 close
            _snap(d2, "DraftKings", 68.5, player="RB Oné")]              # day 2 restarts
    closes = closing_lines_by_date(rows)
    assert closes[("rb one", "rush_yds", "2026-07-24")] == 72.0
    assert closes[("rb one", "rush_yds", "2026-07-25")] == 68.5


def test_annotate_price_move_reads_as_odds():
    from engine.linemoves import annotate_recommendations
    rows = [_psnap(NOW - 3000, "DraftKings", +150),
            _psnap(NOW - 600, "DraftKings", +115),
            _psnap(NOW - 3000, "FanDuel", +150),
            _psnap(NOW - 600, "FanDuel", +115)]
    rec = {"player": "Slugger", "market": "home_runs", "side": "OVER",
           "has_market": True, "reasons": [], "warnings": []}
    assert annotate_recommendations([rec], analyze(rows, now=NOW)) == 1
    assert rec["line_move"]["verdict"] == "with"
    assert any("Over price +150 → +115" in r for r in rec["reasons"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
