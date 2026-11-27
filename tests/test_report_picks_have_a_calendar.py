"""The game report picks have a profit calendar of their own (step AIM, 27 November 2026).

Ethan, on the Record page's calendar (its switch read Edge bets / Most Likely): "Also we should have a calander for
game report picks too". The report book (ledger.REPORT_CATEGORY: every pick a game report posts, 0.1 unit each) is
drawn by day the way the Most Likely calendar is (ledger.report_calendar through pnl_curve and edge_state), behind a
third switch, "Report picks", and a tapped day lists that day's report picks (/api/record/day?book=report). What holds:

  * the calendar is the report book by game day and nothing else: no edge bet, no Most Likely pick, no benched
    league on All bets, and a week-keyed football pick sits on its game day;
  * a scope whose reports posted no pick has no calendar, so no switch to an empty one; a scope with picks still
    riding has one, which says so;
  * a tapped day's rows add up to its cell, on a league's scope and on All bets;
  * the page offers the switch only where the scope has the book, keeps a reader's pick where it can, and says
    "picks" for this book.

The players and numbers below are this test's own.

    python3 tests/test_report_picks_have_a_calendar.py
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
sys.path.insert(0, str(ROOT / "tests"))

from engine import ledger as L                                       # noqa: E402
import test_profit_calendar as PC                                    # noqa: E402

ROWS = [
    # ts, sport, date, game_day, player, market, side, line, odds, status, category, stake, pnl
    ("2026-11-20T12:00:00", "nba", "2026-11-20", "2026-11-20", "Alpha", "pts", "OVER", 20.5, -110, "won", "report", 0.1, 0.09),
    ("2026-11-20T12:00:00", "nba", "2026-11-20", "2026-11-20", "Bravo", "pts", "OVER", 18.5, -110, "lost", "report", 0.1, -0.1),
    ("2026-11-21T12:00:00", "nba", "2026-11-21", "2026-11-21", "Cobalt", "reb", "UNDER", 7.5, -125, "won", "report", 0.1, 0.08),
    # A football pick keyed by its week sits on its game day.
    ("2026-11-20T12:00:00", "nfl", "2026-W12", "2026-11-23", "Delta", "rec_yds", "OVER", 40.5, 100, "won", "report", 0.1, 0.1),
    # Another book's rows on the same days: never in the report calendar.
    ("2026-11-20T12:00:00", "nfl", "2026-W12", "2026-11-23", "Echo", "rec_yds", "OVER", 50.5, -110, "won", "main", 1.0, 0.91),
    ("2026-11-20T12:00:00", "nba", "2026-11-20", "2026-11-20", "Foxtrot", "pts", "OVER", 10.5, -110, "won", "likely", 0.1, 0.09),
    # A benched league's report pick: in no scope.
    ("2026-11-20T12:00:00", "wnba", "2026-11-20", "2026-11-20", "Golf", "pts", "OVER", 12.5, -110, "won", "report", 0.1, 0.09),
    # A college pick still riding: its league has a calendar that says so.
    ("2026-11-28T12:00:00", "cfb", "2026-W14", "2026-11-28", "Hotel", "rush_yds", "OVER", 60.5, -110, "open", "report", 0.1, None),
]


def _ledger():
    conn = L.connect(":memory:")
    conn.executemany(
        "INSERT INTO bets (ts,sport,date,game_day,player,market,side,line,odds,status,category,stake_units,pnl_units) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ROWS)
    conn.commit()
    return conn


def test_the_calendar_is_the_report_book_by_game_day():
    conn = _ledger()
    cal = L.report_calendar(conn)
    assert cal["nba"]["days"] == [{"date": "2026-11-20", "day_u": -0.01, "n": 2, "w": 1, "l": 1},
                                  {"date": "2026-11-21", "day_u": 0.08, "n": 1, "w": 1, "l": 0}], cal["nba"]
    assert cal["nfl"]["days"] == [{"date": "2026-11-23", "day_u": 0.1, "n": 1, "w": 1, "l": 0}], \
        "the week-keyed pick on its game day, and the edge bet beside it left out"
    assert cal["cfb"] == {"days": [], "state": {"open": 1, "oldest_open": "2026-11-28", "last_placed": "2026-11-28"}}
    assert "mlb" not in cal and "ufc" not in cal, "no report pick, no calendar"
    assert "wnba" not in cal, "a benched league has no scope"
    assert [(p["date"], p["n"]) for p in cal["all"]["days"]] == [("2026-11-20", 2), ("2026-11-21", 1),
                                                                 ("2026-11-23", 1)], cal["all"]
    # The calendar adds up to the book "The Game Report Picks and Parlays" prints.
    for scope, sport in (("all", None), ("nba", "nba"), ("nfl", "nfl")):
        perf = L.performance(conn, sport, L.REPORT_CATEGORY)
        days = cal[scope]["days"]
        assert perf["settled"] == sum(p["n"] for p in days), scope
        assert abs(perf["net_units"] - sum(p["day_u"] for p in days)) < 0.011, scope
    assert L.REPORT_BOOK == (L.REPORT_CATEGORY,) == ("report",)


def test_a_book_with_no_row_at_all_has_no_calendar():
    conn = L.connect(":memory:")
    assert L.report_calendar(conn) == {}, "nothing posted anywhere: no calendar, not an empty one"
    lk = L.likely_calendar(conn)
    assert set(lk) >= {"all", "nfl", "mlb"}, "the Most Likely calendar keeps a scope per league, as before"


def test_it_rides_the_record_page_only():
    assert "report_calendar" in L.RECORD_PAGE_ONLY, "only the Record page draws a calendar"
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    body = src[src.index("def export_json(conn, path) -> None:"):]
    assert '"report_calendar": report_calendar(conn, since=since),' in body


def test_a_tapped_day_is_its_cell():
    conn = _ledger()
    cal = L.report_calendar(conn)
    for scope, sport in (("nba", "nba"), ("all", None)):
        cell = cal[scope]["days"][0]
        rows = L.settled_on(conn, cell["date"], sport=sport, categories=L.REPORT_BOOK)
        assert [r["player"] for r in rows] == ["Alpha", "Bravo"], (scope, [r["player"] for r in rows])
        assert len(rows) == cell["n"] and abs(sum(r["pnl_units"] for r in rows) - cell["day_u"]) < 1e-9
    nfl = L.settled_on(conn, "2026-11-23", sport="nfl", categories=L.REPORT_BOOK)
    assert [r["player"] for r in nfl] == ["Delta"], "the game day finds the week-keyed pick, never the edge bet"


def test_all_bets_day_leaves_a_benched_league_out_in_every_book():
    """All bets' cells leave a benched league out (pnl_curve), so the rows behind them do too."""
    conn = _ledger()
    conn.execute("INSERT INTO bets (ts,sport,date,game_day,player,market,side,line,odds,status,category,stake_units,"
                 "pnl_units) VALUES ('2026-11-20T12:00:00','wnba','2026-11-20','2026-11-20','India','pts','OVER',9.5,"
                 "-110,'won','main',1.0,0.91)")
    conn.commit()
    edge = L.settled_on(conn, "2026-11-20", categories=L.EDGE_BOOKS)
    assert edge == [], [r["player"] for r in edge]
    assert [r["player"] for r in L.settled_on(conn, "2026-11-20", sport="wnba", categories=L.EDGE_BOOKS)] == ["India"], \
        "a league's own scope still lists its own rows"


def test_the_endpoint_serves_the_report_book():
    import server
    from engine import ledger as LL
    real = LL.connect
    sent = []
    h = object.__new__(server.Handler)
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, json.loads(body)))
    ready = [_ledger() for _ in range(2)]
    LL.connect = lambda *a, **k: ready.pop(0)
    try:
        h._record_day({"date": ["2026-11-20"], "sport": ["nba"], "book": ["report"]})
        code, got = sent[-1]
        assert code == 200 and got["book"] == "report", got
        assert [r["player"] for r in got["rows"]] == ["Alpha", "Bravo"] and got["net_units"] == -0.01, got
        h._record_day({"date": ["2026-11-20"], "sport": ["nba"], "book": ["edge"]})
        assert [r["player"] for r in sent[-1][1]["rows"]] == [], "the report picks are not edge bets"
    finally:
        LL.connect = real


# --- the page ------------------------------------------------------------------------
REPORT = """{days: [{date: "2026-11-20", day_u: -0.4, n: 30, w: 17, l: 13}, {date: "2026-11-21", day_u: 0.3, n: 12, w: 9, l: 3}],
             state: {open: 12, oldest_open: "2026-11-28", last_placed: "2026-11-29"}}"""
LIKELY = """{days: [{date: "2026-11-20", day_u: 1.8, n: 80, w: 50, l: 30}], state: {}}"""


def test_the_switch_has_a_third_book():
    got = PC._node(f"""
      const src = {{curve: {PC.CURVE}, edge_state: {{}}}};
      const R = {REPORT}, M = {LIKELY};
      const chips = (h) => [...h.matchAll(/data-arg="(edge|likely|report)" aria-pressed="(true|false)">([^<]+)</g)]
        .map((m) => [m[1], m[2], m[3]]);
      const sub = (h) => ((h.match(/<span class="sub">([^<]*)<\\/span>/) || [])[1] || "").replace(/\\s+/g, " ");
      const foot = (h) => ((h.match(/<p class="rc-foot">([\\s\\S]*?)<\\/p>/) || [])[1] || "").replace(/\\s+/g, " ");
      const realDate = Date; Date = class extends realDate {{ constructor(...a) {{ super(...(a.length ? a : [2026, 10, 27])); }} }};
      _recCalBook = null;
      const unchosen = recCalendarsHTML(src, M, R);
      _recCalBook = "report";
      const report = recCalendarsHTML(src, M, R);
      const noReport = recCalendarsHTML(src, M, undefined);
      const reportOnly = recCalendarsHTML(src, undefined, R);
      const noneButReport = recCalendarsHTML({{curve: []}}, {{days: [], state: {{}}}}, R);
      Date = class extends realDate {{ constructor(...a) {{ super(...(a.length ? a : [2026, 11, 1])); }} }};
      const december = recCalendarsHTML(src, M, R);
      Date = realDate;
      _recCalBook = null;
      const opensOnReport = recCalBookIn({{curve: []}}, {{days: [], state: {{}}}}, R);
      return {{unchosen: chips(unchosen), report: chips(report), reportSub: sub(report), reportMonth:
                 (report.match(/data-month="([^"]+)"/) || [])[1], noReport: chips(noReport), reportOnly: chips(reportOnly),
               noneButReport: chips(noneButReport), december: foot(december), opensOnReport,
               words: recCalBook("report")}};""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["unchosen"] == [["edge", "true", "Edge bets"], ["likely", "false", "Most Likely"],
                               ["report", "false", "Report picks"]], got["unchosen"]
    assert got["report"][2] == ["report", "true", "Report picks"], got["report"]
    assert got["reportSub"] == ("— units by day, every pick our game reports posted, 0.1 unit each; tap a day for its "
                                "picks"), got["reportSub"]
    assert got["reportMonth"] == "2026-11"
    assert got["noReport"] == [["edge", "true", "Edge bets"], ["likely", "false", "Most Likely"]], \
        "a scope with no report pick has no switch to one, and a reader's pick falls back to the first book with days"
    assert got["reportOnly"] == [["edge", "false", "Edge bets"], ["report", "true", "Report picks"]], got["reportOnly"]
    assert got["noneButReport"][2] == ["report", "true", "Report picks"], got["noneButReport"]
    assert got["december"] == ("<b>December 2026</b> · No report pick has settled in December yet. 12 are still "
                               "waiting on a result, the oldest from Nov 28."), got["december"]
    assert got["opensOnReport"] == "report", "unchosen, the calendar opens on the book with days"
    assert got["words"] == {"word": "Report picks", "sub": "every pick our game reports posted, 0.1 unit each",
                            "one": "report pick", "tap": "picks"}, got["words"]


def test_a_tapped_report_day_says_picks():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    src = "\n".join(PC._fn(n) for n in ("escapeHtml", "recCalBook", "recCalU", "recCalDayBodyHTML"))
    prog = f"""
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const panelEmpty = (t) => `<p class="empty">${{t}}</p>`;
      const recSettledRow = (r) => `<div>${{r.player}}</div>`;
      const recLg = (s) => String(s || "").toUpperCase();
      const marketWord = (m) => m;
      const REC_DAY_OPEN_MAX = 6;
      {src}
      const rows = Array.from({{length: 7}}, (_, i) => ({{player: "P" + i, sport: "nba", market: "pts",
        status: i % 2 ? "lost" : "won", pnl_units: i % 2 ? -0.1 : 0.09}}));
      console.log(JSON.stringify({{none: recCalDayBodyHTML([], "report"), noneEdge: recCalDayBodyHTML([], "edge"),
                                   many: recCalDayBodyHTML(rows, "report")}}));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip())
    assert got["none"] == '<p class="empty">No settled picks on this day in this scope.</p>', got["none"]
    assert got["noneEdge"] == '<p class="empty">No settled bets on this day in this scope.</p>', "the edge book as before"
    assert "Show the day’s 7 picks" in got["many"] and "Hide the picks" in got["many"], got["many"]


def test_the_page_hands_the_calendar_the_report_book():
    app = PC.APP
    i = app.index("async function renderRecord()")
    body = app[i:app.index("\nfunction _recordRooms(", i)]
    assert "const reportCal = (d.report_calendar || {})[scope];" in body
    assert "const calCurve = recCalBooks(src, likelyCal, reportCal)[calBook][0];" in body
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert '_recCalBook = ["likely", "report"].includes(b) ? b : "edge";' in rec, "the switch keeps the third book"
    day = PC._fn("recCalDayOpen")
    assert "Loading the day’s ${recCalBook(book).tap}…" in day


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
