"""A week label sits at its week on the curve (USEREYES1, 18 November 2026).

The Record page's curve read "2026-08-06 → 2026-W01": eleven NFL rows from
Week 1 that `backfill_game_days` could not place on a game day keep the
week's label (on purpose: a visible week rather than an invisible wrong
Sunday, tests/test_game_day.py), and the curve ordered its days as text,
where "W" outranks every digit, so Week 1's units were drawn after
November's and the curve ended on a label. What these hold:

  * an unplaced week sorts at the Thursday its week opens (the season opens
    the Thursday after Labor Day), and the running total follows that order;
  * the label itself is kept, and every dated day is untouched;
  * the page says a date in words ("Thu, Aug 6") and an unplaced week as a
    week ("NFL week 1"), never "2026-W01".

    python3 tests/test_a_week_label_sits_at_its_week.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                    # noqa: E402


def _db():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))


def _settled(conn, sport, date, player, pnl, game_day=None):
    conn.execute(
        "INSERT INTO bets (sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, pnl_units, pnl_dollars, "
        "category) VALUES (?,?,?,?,'moneyline','OVER',0.5,-110,1.0,10.0,?,?,?, 'main')",
        (sport, date, game_day, player, "won" if pnl > 0 else "lost", pnl, pnl * 10))
    conn.commit()


def test_a_week_label_names_the_thursday_its_week_opens():
    assert ledger.week_label_day("2026-W01") == "2026-09-10"    # Labor Day 2026 is 7 Sept
    assert ledger.week_label_day("2025-W01") == "2025-09-04"    # and 2025's is 1 Sept
    assert ledger.week_label_day("2026-W18") == "2027-01-07"
    for other in ("2026-09-10", "", None, "W01", "2026-W"):
        assert ledger.week_label_day(other) == "", other


def test_an_unplaced_week_is_drawn_at_its_week():
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day=None)
    _settled(conn, "mlb", "2026-09-05", "NYY", 1.0, game_day="2026-09-05")
    _settled(conn, "mlb", "2026-09-12", "BOS", -0.5, game_day="2026-09-12")
    _settled(conn, "nfl", "2026-W11", "KC", -1.0, game_day="2026-11-15")
    rows = ledger.pnl_curve(conn)
    assert [r["date"] for r in rows] == ["2026-09-05", "2026-W01", "2026-09-12", "2026-11-15"], rows
    assert [r["cum_u"] for r in rows] == [1.0, 1.9, 1.4, 0.4], rows


def test_the_page_says_the_day_and_the_week_in_words():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i, j = rec.index("function recDay(s) {"), app.index("function formatGameDate(")
    js = (app[j:app.index("\n}\n", j) + 3] + rec[i:rec.index("\n}\n", i) + 3]
          + "process.stdout.write(JSON.stringify([recDay('2026-08-06'), recDay('2026-W01'), recDay('2026-W12'), recDay('')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60,
                         env={"LANG": "en_US.UTF-8", "TZ": "America/New_York", "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout == '["Thu, Aug 6","NFL week 1","NFL week 12",""]', out.stdout
    for use in ("${recDay(p.date)} · ${p.n} bet", "${escapeHtml(recDay(curve[0].date))} → ${escapeHtml(recDay(last.date))}"):
        assert use in rec, use


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
