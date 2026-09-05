"""The profit calendar on the Record page.

Ethan, 2026-09-05: "a profit calendar on record page". A month grid with
the units won or lost each day, green or red by sign and deeper by size,
and a tap on a day for the bets behind it.

Pinned: the day's rows come from the same book and the same stake rule
the curve draws (main + paper, staked), never the Most Likely book; the
endpoint is ungated and validates its date; the grid is Sunday-first
with the right number of blanks; the cell says its units with a true
minus; the month in view defaults to the latest with a bet; an arrow
exists only where there is a month to go to; the day panel is scoped the
way the page is and falls back to the rows the page holds.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger as L                                  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
SERVER = (ROOT / "server.py").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the engine ------------------------------------------------------------------
def _ledger():
    conn = L.connect(":memory:")
    rows = [
        # ts, sport, date, player, market, side, line, odds, status, category, stake, pnl
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "A", "rec_yds", "UNDER", 58.5, -114, "won", "main", 1.02, 0.89),
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "B", "rec_yds", "UNDER", 71.5, -113, "lost", "main", 1.01, -1.01),
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "C", "total", "UNDER", 59.5, -110, "won", "paper", 0.10, 0.09),
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "D", "rec_yds", "OVER", 20.5, -110, "won", "likely", 1.0, 0.91),
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "E", "rec_yds", "OVER", 20.5, -110, "won", "main", 0.0, 0.0),
        ("2026-09-03T20:00:00", "cfb", "2026-09-04", "F", "rec_yds", "OVER", 20.5, -110, "lost", "main", 1.0, -1.0),
        ("2026-09-04T20:00:00", "nfl", "2026-09-05", "G", "rec_yds", "OVER", 20.5, -110, "won", "main", 1.0, 0.91),
        ("2026-09-04T20:00:00", "cfb", "2026-09-05", "H", "rec_yds", "OVER", 20.5, -110, "open", "main", 1.0, None),
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,odds,status,category,"
            "stake_units,pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    return conn


def test_a_days_rows_are_the_curves_own_book_and_stake_rule():
    conn = _ledger()
    got = L.settled_on(conn, "2026-09-05")
    names = [r["player"] for r in got]
    assert names == ["A", "B", "C", "G"], names
    assert "D" not in names, "the Most Likely book never appears in the edge calendar"
    assert "E" not in names, "an unstaked row is not in the curve, so not behind its cell"
    assert "H" not in names, "an open bet is not settled"
    assert "F" not in names, "another day"
    assert got[0]["pnl_units"] == 0.89 and got[1]["status"] == "lost"
    for r in got:
        for k in ("clv", "process", "cause", "market", "side", "line", "odds"):
            assert k in r, k


def test_the_sport_scope_narrows_and_an_empty_day_is_empty():
    conn = _ledger()
    cfb = [r["player"] for r in L.settled_on(conn, "2026-09-05", sport="cfb")]
    assert cfb == ["A", "B", "C"], cfb
    assert [r["player"] for r in L.settled_on(conn, "2026-09-05", sport="nfl")] == ["G"]
    assert L.settled_on(conn, "2026-09-06") == []
    assert L.settled_on(conn, "2026-09-05", categories=("likely",)) and \
        [r["player"] for r in L.settled_on(conn, "2026-09-05", categories=("likely",))] == ["D"], \
        "the book is a parameter, so a likely calendar could be built the same way"


def test_the_curve_and_the_day_agree():
    """The cell's number is the curve's day_u; the rows behind it must sum
    to the same thing, or the calendar contradicts its own tap."""
    conn = _ledger()
    curve = {p["date"]: p for p in L.pnl_curve(conn, sport="cfb")}
    rows = L.settled_on(conn, "2026-09-05", sport="cfb")
    assert abs(curve["2026-09-05"]["day_u"] - sum(r["pnl_units"] for r in rows)) < 1e-9
    assert curve["2026-09-05"]["n"] == len(rows)


# --- the endpoint ------------------------------------------------------------------
def test_the_endpoint_is_routed_validated_and_ungated():
    assert 'if parsed.path in ("/api/record/day", "/api/record/day/"):' in SERVER
    assert "return self._record_day(parse_qs(parsed.query))" in SERVER
    i = SERVER.index("def _record_day(")
    body = SERVER[i:SERVER.index("\n    def ", i + 10)]
    assert 'r"\\d{4}-\\d{2}-\\d{2}"' in body and "400" in body, "a bad date is refused, not queried"
    assert "L.settled_on(conn, date, sport=sport or None)" in body
    assert "_entitled" not in body, "settled rows are the evidence the subscription is sold on"
    assert '"net_units"' in body and '"rows"' in body
    assert "conn.close()" in body


# --- the page ----------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join(_fn(n) for n in ("escapeHtml", "recCalMonths", "recCalU", "recCalMonthHTML", "recCalendarHTML"))
    prog = f"""
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const icon = (n) => `<i data-icon="${{n}}"></i>`;
      let _recCalMonth = null, _recCalDay = null;
      {src}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    env = dict(os.environ, TZ="America/New_York", LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30, env=env)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


CURVE = """[
  {date: "2026-08-30", day_u: 0.91, n: 1, w: 1, l: 0},
  {date: "2026-09-01", day_u: -1.0, n: 1, w: 0, l: 1},
  {date: "2026-09-05", day_u: 2.35, n: 4, w: 3, l: 1},
  {date: "2026-09-12", day_u: -0.2, n: 2, w: 1, l: 1},
  {date: "2026-09-13", day_u: 0, n: 2, w: 1, l: 1},
]"""


def test_the_grid_is_sunday_first_with_the_right_blanks_and_units():
    got = _node(f"""
      const html = recCalMonthHTML({CURVE}, "2026-09");
      const count = (re) => (html.match(re) || []).length;
      return {{
        heads: count(/class="rc-h"/g), blanks: count(/rc-day blank/g), off: count(/rc-day off/g),
        doors: count(/<button type="button" class="rc-day /g),
        five: (html.match(/class="rc-day pos rc-3" data-date="2026-09-05"[^>]*>5<b>\\+2\\.4<\\/b>/) || [null])[0],
        first: (html.match(/class="rc-day neg rc-2" data-date="2026-09-01"/) || [null])[0],
        twelve: (html.match(/class="rc-day neg rc-1" data-date="2026-09-12"[^>]*>12<b>−0\\.2<\\/b>/) || [null])[0],
        flat: (html.match(/class="rc-day flat rc-1" data-date="2026-09-13"/) || [null])[0],
        foot: (html.match(/<p class="rc-foot">[\\s\\S]*?<\\/p>/) || [""])[0].replace(/\\s+/g, " "),
        aug: recCalMonthHTML({CURVE}, "2026-08").match(/rc-day blank/g).length,
      }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["heads"] == 7
    assert got["blanks"] == 2, "September 1st 2026 is a Tuesday: two blanks after the Sunday head"
    assert got["doors"] == 4 and got["off"] == 26, got
    assert got["five"] and got["first"] and got["twelve"] and got["flat"], got
    # 0-1, 3-1, 1-1, 1-1 across the four days; −1.0 + 2.35 − 0.2 + 0 = +1.15, shown to a tenth.
    assert "<b>September 2026</b> · 4 days bet · <b>5-4</b> · net <b class=\"pos\">+1.2u</b>" in got["foot"], got["foot"]
    assert got["aug"] == 6, "August 1st 2026 is a Saturday"


def test_units_read_with_a_true_minus_and_whole_numbers_past_ten():
    got = _node("""return [recCalU(0.91), recCalU(-1.0), recCalU(0), recCalU(12.34), recCalU(-10), recCalU(null)];""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["+0.9", "−1.0", "0.0", "+12", "−10", "0.0"], got


def test_the_month_in_view_defaults_to_the_latest_and_arrows_only_where_there_is_somewhere_to_go():
    got = _node(f"""
      const months = recCalMonths({CURVE});
      const latest = recCalendarHTML({CURVE});
      _recCalMonth = "2026-08"; const aug = recCalendarHTML({CURVE});
      _recCalMonth = "2025-01"; const unknown = recCalendarHTML({CURVE});
      const one = recCalendarHTML([{{date: "2026-09-05", day_u: 1, n: 1, w: 1, l: 0}}]);
      return {{
        months, none: recCalendarHTML([]), noneNull: recCalendarHTML(null),
        latestMonth: (latest.match(/data-month="([^"]+)"/) || [])[1],
        latestArrows: (latest.match(/aria-label="(Earlier|Later) month"/g) || []),
        augArrows: (aug.match(/aria-label="(Earlier|Later) month"/g) || []),
        augTo: (aug.match(/_recCalSetMonth\\('([^']+)'\\)/) || [])[1],
        unknownMonth: (unknown.match(/data-month="([^"]+)"/) || [])[1],
        oneArrows: (one.match(/ra-ranges/g) || []).length,
        sub: /edge book only/.test(latest), panel: /id="rc-day"/.test(latest),
      }};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["months"] == ["2026-08", "2026-09"]
    assert got["none"] == "" and got["noneNull"] == ""
    assert got["latestMonth"] == "2026-09" and got["latestArrows"] == ['aria-label="Earlier month"']
    assert got["augArrows"] == ['aria-label="Later month"'] and got["augTo"] == "2026-09"
    assert got["unknownMonth"] == "2026-09", "a month the curve does not have falls back to the latest"
    assert got["oneArrows"] == 0, "one month, no arrows — an arrow that goes nowhere is a fake button"
    assert got["sub"] and got["panel"]


def test_the_record_page_draws_it_under_the_curve_and_scopes_the_tap():
    i = APP.index("async function renderRecord()")
    body = APP[i:APP.index("\nfunction _recordRooms(", i)]
    assert "_recCalScope = scope;" in body
    assert "${recAnalytics(src.curve, o, ((d.model_eras || {}).eras) || [])}\n    ${recCalendarHTML(src.curve)}" in body
    assert 'host.querySelectorAll(".rc-day[data-date]")' in body
    assert "recCalDayOpen(el.dataset.date, src.curve, src.recent || [])" in body
    day = _fn("recCalDayOpen")
    assert 'const sport = _recCalScope === "all" ? "" : _recCalScope;' in day
    assert "/api/record/day?date=${encodeURIComponent(date)}&sport=${encodeURIComponent(sport)}" in day
    assert "if (_recCalDay !== date) return;" in day, "a slower fetch never overwrites a later tap"
    assert "rows = (recent || []).filter((b) => b.date === date);" in day, "a static host still shows what it holds"
    assert "rows.map(recSettledRow)" in day, "the same row the receipts draw"
    assert "these are the rows this page already holds" in day
    for sel in (".rc-grid", ".rc-day.pos.rc-3", ".rc-day.neg.rc-1", ".rc-day.open", ".rc-foot", ".rc-dayhead"):
        assert sel in CSS, sel
    assert "min-height: 44px" in CSS[CSS.index(".rc-day {"):CSS.index(".rc-day.blank")], "a thumb-sized cell"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
