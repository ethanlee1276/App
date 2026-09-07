"""The Record page's receipts room says each number once.

Ethan, 2026-09-06: "go through every sports record page and make sure
it's good, everything seems cluttered and some of the data seems off."
Rendered over a month of journaled bets, the room summarised one book
three times before any detail: the verdict tiles, then "Records by
book", then a strip of five stat cards of which ROI and Avg CLV were the
verdict's tiles again; the Splits' Market table was the Edge table
again, number for number; two chips on a settled row drew on top of each
other on a phone; "+0.0 CLV" sat on two rows in three; a moneyline row
read "AWAY 0 Moneyline"; and an empty sport said "0 settled pick(s) for
nfl — results this small are mostly luck" under a verdict that had just
said "too early to call".

Run directly: `python3 tests/test_record_declutter.py`
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

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n(function")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_verdict_is_the_one_summary():
    v = _fn("recordVerdictHTML")
    for label in ('tile("record"', 'tile("net"', 'tile("Win rate"', 'tile("CLV"', 'tile("claimed"', 'tile("landed"'):
        assert label in v, label
    assert 'tile("settled"' not in v, "the record tile carries the settled count now"
    assert "at the prices taken" in v and "o.breakeven == null" in v
    assert 'graded ? ((o.win_rate || 0) * 100).toFixed(1) + "%" : "—"' in v, "no 0.0% win rate on nothing graded"
    assert "price ${" in v and "o.price_clv_n" in v, "price CLV rides the CLV tile"
    rr = _fn("renderRecord")
    assert 'stat-cards rec-kpis' not in rr, "the duplicate strip is back"
    assert 'statCardHTML("rising", "ROI"' not in rr and 'statCardHTML("signal", "Avg CLV"' not in rr
    assert '<div class="rec-process-row">' in rr, "the process row stays"
    i = CSS.index(".rv-tiles {")
    assert "repeat(6," in CSS[i:i + 200]


def test_the_small_sample_note_speaks_only_where_the_verdict_does_not():
    rr = _fn("renderRecord")
    assert "const small = o.settled >= (src.min_graded || _recMinGraded) && o.settled < 100" in rr
    assert "${o.settled} settled pick(s)" not in rr, "the note prints a count of picks, plural"
    assert "|| scope.toUpperCase())" in rr, "NFL, not nfl"


def test_the_splits_do_not_redraw_the_edge_table_on_a_sport_scope():
    rr = _fn("renderRecord")
    assert "${recSplitsSection(o, !!scoped)}" in rr
    sp = _fn("recSplitsSection")
    assert 'booksDrawn ? null : o.by_market' in sp
    assert 'cur[0] === "market"' in sp, "the market split is still the only one translated"


def test_the_curve_footer_repeats_the_tiles_only_when_a_window_is_cut():
    ra = _fn("recAnalytics")
    assert 'rk === "all" ? "" : `<p class="ra-line">${range}</p>`' in ra
    assert "staked all-time" in ra


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const icon = (n) => `<i class="ic-${{n}}"></i>`;
      const iconMark = (n) => `<i class="im-${{n}}"></i>`;
      const marketWord = (m) => ({{ hits: "Hits", moneyline: "Moneyline", total: "Game Total" }})[m] || m;
      const american = (o) => o == null ? "—" : (o > 0 ? "+" + o : String(o));
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      {_fn("recSettledRow")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_settled_row_keeps_its_chips_in_one_cell_and_says_only_what_moved():
    got = _node("""
      const base = { date: "2026-09-05", player: "Juan Soto", market: "hits", side: "OVER", line: 1.5, odds: -110, status: "won", pnl_units: 0.91 };
      return {
        flat: recSettledRow({ ...base, clv: 0.0 }),
        tiny: recSettledRow({ ...base, clv: 0.04 }),
        moved: recSettledRow({ ...base, clv: 0.5 }),
        against: recSettledRow({ ...base, clv: -1.0, status: "lost", pnl_units: -1 }),
        noClose: recSettledRow({ ...base, clv: null }),
        lucky: recSettledRow({ ...base, process: "bad", clv: -0.5 }),
        cause: recSettledRow({ ...base, status: "lost", pnl_units: -1, clv: 0.0, cause: "lineup" }),
        ml: recSettledRow({ ...base, market: "moneyline", side: "AWAY", line: 0, player: "KC@LAC", odds: 280 }),
        noLine: recSettledRow({ ...base, market: "total", line: null }),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert "CLV" not in got["flat"] and "CLV" not in got["tiny"], "a close that did not move is not a chip"
    assert "+0.5 CLV" in got["moved"] and "-1.0 CLV" in got["against"]
    assert "no close" in got["noClose"]
    assert "lucky" in got["lucky"]
    assert '<span class="rl-chips"><span class="rl-proc warn"' in got["cause"] and "lineup" in got["cause"]
    for row in got.values():
        assert row.count('class="rl-chips"') == 1, "both chips live in one grid cell"
    assert "AWAY Moneyline" in got["ml"] and " 0 " not in got["ml"]
    assert "OVER Game Total" in got["noLine"]
    assert "OVER 1.5 Hits" in got["moved"]


def test_the_chip_cell_is_laid_out_on_both_widths():
    assert ".rl-chips { display: flex; justify-content: flex-end; gap: 6px; min-width: 0; overflow: hidden; }" in CSS
    i = CSS.index("  .rl-chips { grid-area: proc;")
    assert "flex-wrap: wrap" in CSS[i:i + 160] and "overflow: visible" in CSS[i:i + 160]



def test_an_empty_sport_scope_is_the_empty_state_and_nothing_else():
    """Rendered for the NBA: "Nothing journaled for NBA yet", "Nothing
    tuned for NBA yet", a mining panel counting 461 graded bets of every
    sport, preregistered tests about NFL props, a lab of four zeros."""
    rr = _fn("renderRecord")
    i = rr.index("if (scoped && !o.settled && !o.open) {")
    branch = rr[i:rr.index("bindRecordScopes(host);", i)]
    assert "Nothing journaled for" in branch and "All bets" in branch
    for panel in ("recSelfTuningSection", "recLossPatternsSection", "recPrereg", "recHypothesisLab"):
        assert panel not in branch, f"{panel} is back under the empty state"
    # Two stay, because both draw nothing for a sport they have nothing
    # on, and the night desk can brief a sport before its first settle.
    assert "recRestatedSection(d.restated, scope)" in branch
    assert "recProseSection(d.prose, scope)" in branch
    # The ladder itself is not gone: the learning room still draws it for
    # a sport with a journal.
    rooms = _fn("_recordRooms")
    assert "recLossPatternsSection(d.loss_patterns, scoped ? scope : null)" in rooms


def test_the_calibration_rooms_second_table_is_folded_under_its_heading():
    """"Current model only" drew the whole calibration table, chart and
    scores a second time under the first. The heading stays (it is the
    minor rank the organization test pins); the rows open on a tap."""
    c = _fn("recCalibrationSection")
    assert '<div class="section-title minor">Current model only' in c
    i = c.index('<details class="rec-epoch rec-fold">')
    assert "Open the current model’s own buckets, chart and scores" in c[i:i + 200]
    assert "calBucketRows(era.buckets)" in c[i:] and "calScoreBlock(era)" in c[i:]
    assert ".rec-fold > .card" in CSS


def test_a_thin_book_counts_graded_picks_and_says_so():
    """Beside a 7-8-1 record the header said "15 settled" while the verdict
    said "16 settled". The count is wins plus losses; a push settles but
    does not grade, and the word has to match the count."""
    b = _fn("recBookSections")
    assert "` · ${n} graded — thin sample`" in b
    assert "settled — thin sample" not in b


def test_the_receipts_list_names_its_cap_instead_of_claiming_the_lot():
    """The export carries the most recent RECENT_LIMIT settled picks. The
    button said "Show all 20 settled picks" beside a verdict reading 193
    settled, which is a capped list claiming to be complete."""
    from engine import ledger
    assert ledger.RECENT_LIMIT >= 60
    src = (ROOT / "engine" / "ledger.py").read_text()
    assert '"recent": recent_settled(conn, RECENT_LIMIT, sport=sport, since=since)' in src
    assert '"recent": recent_settled(conn, RECENT_LIMIT, since=since)' in src
    assert "recent_settled(conn, 20," not in src, "the per-sport list was capped at 20"
    rs = _fn("recRecentSection")
    assert "function recRecentSection(recent, settled)" in rs
    assert "const capped = (settled || 0) > recent.length;" in rs
    assert "most recent of ${settled} settled" in rs
    assert "Show ${more} more" in rs and "Show all ${recent.length}" not in rs
    rr = _fn("renderRecord")
    assert "${recRecentSection(src.recent || [], o.settled)}" in rr, \
        "the count must be the verdict's own, or the two can disagree"


def test_the_cap_is_real_and_the_rows_are_the_newest():
    import tempfile
    from engine import ledger
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    rows = [(f"2026-06-{d:02d}", f"P{d}") for d in range(1, 29)]
    conn.executemany(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
        "stake_units, stake_dollars, status, pnl_units, pnl_dollars, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(d + "T12:00:00", "mlb", d, p, "hits", "OVER", 1.5, "DK", -110, 1.0, 10.0,
          "won", 0.91, 9.1, "main") for d, p in rows])
    conn.commit()
    got = ledger.recent_settled(conn, 10, sport="mlb")
    assert len(got) == 10 and got[0]["date"] == "2026-06-28", "newest first"
    report = ledger.sport_report(conn, "mlb")
    assert len(report["recent"]) == 28, "under the cap, every settled pick ships"
    assert report["overall"]["settled"] == 28

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
