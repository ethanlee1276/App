"""The paper book was readable only pooled.

Ethan, 2026-09-10: "and the most likley paper bets for nfl are not showing on
nfl. and the most likley paper bets for mlb ar enot showing on lb and so
forth."

The Record page has a scope per league. The Most Likely paper record — the
board's whole measurement, journaled nightly at zero exposure — was rendered
with `scoped ? "" : recLikelySection(d.likely)`, so pressing any league
button removed the entire section. It was omitted rather than scoped for a
reason: `ledger.likely_report` pooled every sport and there was no per-sport
cut to hand the page.

That is the wrong cut for this bucket in particular, because the standing
order on it is per sport — Ethan, 2026-09-01: "make sure you dont stop
testing each sport until the most likley for eavh sport is making money and
positive roi." A pooled ROI cannot answer that for any league.

So the report takes a sport, and EVERY query in it takes the filter. These
tests check each cut separately, because threading it through some queries
and not others is how a page ends up printing one league's calibration
beside every league's ROI — a failure that reads as a working section.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _journal():
    """A ledger with a likely book in two leagues, deliberately opposite.

    NFL: two winners at a high claim, one open, on rec_yds and moneyline.
    MLB: two losers at a low claim, on hits. So every cut in the report —
    calibration, band, market, sport, game-market, open, receipts, ROI —
    has a different answer for each league and for the pool.
    """
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    rows = [
        ("nfl", "2026-W01", "SEA", "moneyline", 0.80, "won", 0.09),
        ("nfl", "2026-W01", "Sam Darnold", "pass_yds", 0.78, "won", 0.09),
        ("mlb", "2026-09-08", "Aaron Judge", "hits", 0.35, "lost", -0.10),
        ("mlb", "2026-09-08", "NYY", "total", 0.38, "lost", -0.10),
    ]
    for sport, date, player, market, prob, status, pnl in rows:
        conn.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, odds, "
            "hit_prob, stake_units, status, pnl_units, category) "
            "VALUES (?,?,?,?,'OVER',0.5,-110,?,0.10,?,?,'likely')",
            (sport, date, player, market, prob, status, pnl))
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "hit_prob, stake_units, status, category) VALUES "
        "('nfl','2026-W02','NE','moneyline','OVER',0.5,-110,0.6,0.10,"
        "'open','likely')")
    conn.commit()
    return conn


# --- every cut, per league --------------------------------------------------
def test_the_headline_calibration_is_that_leagues_own():
    conn = _journal()
    assert ledger.likely_report(conn)["calibration"]["n"] == 4
    assert ledger.likely_report(conn, sport="nfl")["calibration"]["n"] == 2
    assert ledger.likely_report(conn, sport="mlb")["calibration"]["n"] == 2
    # And it is not merely the count: the pool's claim sits between them.
    nfl = ledger.likely_report(conn, sport="nfl")["calibration"]
    mlb = ledger.likely_report(conn, sport="mlb")["calibration"]
    assert nfl["actual"] == 1.0 and mlb["actual"] == 0.0


def test_the_roi_is_that_leagues_own():
    """The number the standing order is about. Pooled it is the average of
    a league that paid and one that did not, which is true of neither."""
    conn = _journal()
    assert ledger.likely_report(conn, sport="nfl")["roi"] > 0
    assert ledger.likely_report(conn, sport="mlb")["roi"] < 0


def test_the_bands_are_that_leagues_own():
    """NFL's rows claim 0.78-0.80 and MLB's claim 0.35-0.38, so the two
    leagues do not share a single band."""
    conn = _journal()
    nfl = {(b["lo"], b["hi"]) for b in
           ledger.likely_report(conn, sport="nfl")["bands"]}
    mlb = {(b["lo"], b["hi"]) for b in
           ledger.likely_report(conn, sport="mlb")["bands"]}
    assert nfl == {(0.75, 1.01)}
    assert mlb == {(0.30, 0.45)}


def test_the_market_shelves_are_that_leagues_own():
    conn = _journal()
    assert set(ledger.likely_report(conn, sport="nfl")["by_market"]) == \
        {"moneyline", "pass_yds"}
    assert set(ledger.likely_report(conn, sport="mlb")["by_market"]) == \
        {"hits", "total"}


def test_the_per_sport_table_holds_only_that_league():
    """It is inside the scoped report too — a section that says "by sport"
    while showing one league's rows must not list the other."""
    conn = _journal()
    assert set(ledger.likely_report(conn, sport="nfl")["by_sport"]) == {"nfl"}
    assert set(ledger.likely_report(conn)["by_sport"]) == {"mlb", "nfl"}


def test_the_game_lines_table_holds_only_that_league():
    """`recLikelyGameLines` renders straight out of this, prefixing each row
    with a league name — so an unfiltered cut here prints "MLB" rows on the
    NFL page."""
    conn = _journal()
    assert set(ledger.likely_report(conn, sport="nfl")["by_sport_market"]) == \
        {"nfl"}
    assert set(ledger.likely_report(conn, sport="mlb")["by_sport_market"]) == \
        {"mlb"}


def test_the_open_count_is_that_leagues_own():
    conn = _journal()
    assert ledger.likely_report(conn, sport="nfl")["open"] == 1
    assert ledger.likely_report(conn, sport="mlb")["open"] == 0
    assert ledger.likely_report(conn)["open"] == 1


def test_the_receipts_are_that_leagues_own():
    conn = _journal()
    for sp in ("nfl", "mlb"):
        got = ledger.likely_report(conn, sport=sp)["recent"]
        assert got and {r["sport"] for r in got} == {sp}


def test_the_report_stamps_the_league_it_filtered_on():
    """The page labels the section off THIS, not off its own scope, so a
    section headed NFL cannot be showing pooled rows."""
    conn = _journal()
    assert ledger.likely_report(conn, sport="nfl")["sport"] == "nfl"
    assert ledger.likely_report(conn)["sport"] == ""


def test_the_verdict_is_computed_on_that_leagues_rows():
    """It refuses below the settle floor, and the count it refuses with has
    to be the league's own or the refusal is about the wrong sample."""
    conn = _journal()
    assert "2 settled" in ledger.likely_report(conn, sport="nfl")["verdict"]
    assert "4 settled" in ledger.likely_report(conn)["verdict"]


# --- the export -------------------------------------------------------------
def test_the_export_carries_a_report_per_league():
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path, encoding="utf-8"))
    assert set(d["likely_by_sport"]) == {"nfl", "mlb"}
    assert d["likely_by_sport"]["nfl"]["calibration"]["n"] == 2
    assert d["likely"]["calibration"]["n"] == 4


def test_a_league_with_nothing_in_this_book_is_omitted_not_emitted_empty():
    """Six empty blobs each carrying their own receipts list is weight in a
    payload every visitor downloads, and the page draws nothing for an
    absent entry anyway."""
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path, encoding="utf-8"))
    for sp in ("cfb", "nba", "wnba", "ufc"):
        assert sp not in d["likely_by_sport"]


# --- the page ---------------------------------------------------------------
def test_the_section_is_no_longer_dropped_on_a_league_scope():
    """The whole report, in one assertion."""
    assert 'scoped ? "" : recLikelySection' not in APP, \
        "pressing a league still removes the Most Likely paper record"
    assert "recLikelySection(scoped ? (d.likely_by_sport || {})[scope]" in APP


def test_the_page_reads_the_scoped_report_and_never_filters_the_pooled_one():
    """Scoping by swapping the SOURCE, which is the rule the rest of this
    page already follows — filtering at each call site is how one panel
    quietly keeps showing the combined number beside a per-sport one."""
    i = APP.index("function recLikelySection(")
    block = APP[i:APP.index("\nfunction ", i + 1)]
    assert 'lk.sport' in block or '(lk || {}).sport' in block, \
        "the section cannot tell which league it is drawing"


def test_the_section_title_names_the_league_it_is_showing():
    i = APP.index("function recLikelySection(")
    block = APP[i:APP.index("\nfunction ", i + 1)]
    title = block[block.index("Most Likely — the paper record"):]
    assert "spName" in title[:200], \
        "a scoped section is headed as though it were the pooled record"


def test_the_game_lines_lede_is_told_which_cut_it_is_describing():
    """It promised "per sport" in prose. On a league's page there is only
    one sport in the table, so that sentence describes a table the reader
    is not looking at."""
    i = APP.index("function recLikelyGameLines(")
    block = APP[i:APP.index("\nfunction ", i + 1)]
    assert block.startswith("function recLikelyGameLines(lk, sp)")
    assert "${sp" in block, "the lede cannot vary with the cut"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
