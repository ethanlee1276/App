"""Every settled bet in the headline record, filterable, a page at a time.

Ethan's product audit, 2026-09-23, item 17: the Record as "a financial
terminal" — every bet, with the model's number, the price, the close
and the CLV on each row, filterable. The record file ships the most
recent RECENT_LIMIT settled bets; /api/record/bets (ledger.settled_page)
serves the rest, fifty at a time.

What this file holds:

  * THE SAME ROWS AS THE HEADLINE. With no filter the list's total IS
    the headline's settled count — the pooled books, staked, on or after
    the epoch, benched leagues out. A list that disagreed with the number
    above it would be the cherry-picking the page exists to disprove.
  * THE WINDOW IS THE CALENDAR DAY, the one the running P&L buckets on,
    so the chart and the list agree about which days are in.
  * EVERY PARAMETER HAS A CLOSED SHAPE before it reaches SQL.
  * THE PAGE SAYS WHICH LIST IT HAS: the journal's true count, or — on a
    host with no API — the shipped recent rows, called that.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server                                                  # noqa: E402
from engine import ledger                                      # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
SERVER = (ROOT / "server.py").read_text()
TODAY = dt.date.today()
EPOCH = dt.date.fromisoformat(ledger.RECORD_EPOCH)


def _ago(n):
    return (TODAY - dt.timedelta(days=n)).isoformat()


def _journal(path=":memory:"):
    conn = ledger.connect(path)

    def bet(day, player, market="hits", status="won", category="main", sport="mlb",
            stake=1.0, date=None, prob=0.6, close=None):
        conn.execute(
            "INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,book,hit_prob,"
            "stake_units,stake_dollars,status,category,pnl_units,closing_odds) VALUES "
            "(?,?,?,?,?,'OVER',1.5,-110,'DraftKings',?,?,10.0,?,?,?,?)",
            (sport, date or day, day, player, market, prob, stake, status, category,
             0.91 if status == "won" else (-1.0 if status == "lost" else 0.0), close))

    bet(_ago(2), "Recent Prop", prob=0.64, close=-125)
    bet(_ago(3), "Recent Line", market="total", status="lost")
    bet(_ago(4), "Paper Likely", category="likely")                  # pooled
    bet(_ago(5), "Staked Likely", market="spread", category="likely_live")
    bet(_ago(6), "Paper Edge", category="paper", status="push")
    bet(_ago(3), "Long Shot", category="longshot")                   # never pooled
    bet(_ago(3), "Unstaked", stake=0.0)                              # a 0.00u grading bug row
    bet(_ago(3), "Benched", sport="wnba")                            # benched, out of the unscoped list
    bet(_ago(40), "Older Prop", status="lost")
    bet((EPOCH - dt.timedelta(days=3)).isoformat(), "Before The Record")
    # An NFL row keyed by a WEEK LABEL, with its calendar day in game_day.
    bet(_ago(2), "Week Label", sport="nfl", market="moneyline", date="2026-W40")
    # …and an older one: a week label sorts above every ISO date, so only
    # the calendar day can put this row outside a thirty-day window.
    bet(_ago(40), "Old Week", sport="nfl", market="moneyline", date="2026-W33")
    conn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,book,stake_units,"
                 "status,category) VALUES ('mlb',?,'Still Open','hits','OVER',1.5,-110,'DK',1.0,"
                 "'open','main')", (_ago(1),))
    conn.commit()
    return conn


def _names(page):
    return [r["player"] for r in page["rows"]]


def test_with_no_filter_the_list_is_the_headline():
    conn = _journal()
    page = ledger.settled_page(conn)
    head = ledger.performance(conn, category=ledger.POOLED_BOOKS, since=ledger.RECORD_EPOCH)
    assert page["total"] == head["settled"] == 8, (page["total"], head["settled"], _names(page))
    names = set(_names(page))
    for out in ("Long Shot", "Unstaked", "Benched", "Before The Record", "Still Open"):
        assert out not in names, out
    assert {"Paper Likely", "Staked Likely", "Paper Edge"} <= names, "the pooled books, every one"
    assert _names(page)[0] == "Week Label" or page["rows"][0]["date"] >= page["rows"][1]["date"]


def test_the_filters_cut_props_lines_result_sport_and_window():
    conn = _journal()
    props = set(_names(ledger.settled_page(conn, kind="props")))
    lines = set(_names(ledger.settled_page(conn, kind="lines")))
    assert lines == {"Recent Line", "Staked Likely", "Week Label", "Old Week"}, lines
    assert props == {"Recent Prop", "Paper Likely", "Paper Edge", "Older Prop"}, props
    assert set(_names(ledger.settled_page(conn, result="lost"))) == {"Recent Line", "Older Prop"}
    assert _names(ledger.settled_page(conn, sport="nfl")) == ["Week Label", "Old Week"]
    assert _names(ledger.settled_page(conn, sport="wnba")) == ["Benched"], "a scoped read still answers"
    month = set(_names(ledger.settled_page(conn, since=_ago(30))))
    assert "Older Prop" not in month and "Old Week" not in month and "Week Label" in month, \
        "the window reads the calendar day — a week label is not a day"
    early = ledger.settled_page(conn, since=(EPOCH - dt.timedelta(days=30)).isoformat())
    assert early["total"] == 8, "a window never reaches back past the record's start"


def test_each_row_carries_the_terminals_columns():
    conn = _journal()
    row = next(r for r in ledger.settled_page(conn)["rows"] if r["player"] == "Recent Prop")
    for k in ("day", "date", "sport", "market", "side", "line", "odds", "book", "hit_prob",
              "closing_odds", "clv", "process", "status", "pnl_units", "cause"):
        assert k in row, k
    assert row["hit_prob"] == 0.64 and row["closing_odds"] == -125 and row["day"] == _ago(2)


def test_the_pages_are_fifty_newest_first_and_count_them_all():
    conn = ledger.connect(":memory:")
    for i in range(120):
        conn.execute(
            "INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,stake_units,"
            "status,category,pnl_units) VALUES ('mlb',?,?,?,'hits','OVER',1.5,-110,1.0,'won','main',0.91)",
            (_ago(1 + i % 30), _ago(1 + i % 30), f"P{i}"))
    conn.commit()
    first = ledger.settled_page(conn)
    last = ledger.settled_page(conn, offset=100)
    assert ledger.SETTLED_PAGE_SIZE == 50
    assert first["total"] == last["total"] == 120
    assert len(first["rows"]) == 50 and len(last["rows"]) == 20
    days = [r["date"] for r in first["rows"]]
    assert days == sorted(days, reverse=True), "newest first"
    seen = set()
    for off in (0, 50, 100):
        seen |= set(_names(ledger.settled_page(conn, offset=off)))
    assert len(seen) == 120, "every bet reachable, none twice"


def _handler():
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
    return h, sent


def test_the_endpoint_answers_from_the_journal_and_refuses_what_it_cannot_read():
    path = os.path.join(tempfile.mkdtemp(), "ledger.db")
    _journal(path).close()
    saved = ledger.DEFAULT_DB
    ledger.DEFAULT_DB = Path(path)
    try:
        h, sent = _handler()
        h._record_bets({"kind": ["lines"], "result": ["won"]})
        code, out = sent[-1]
        assert code == 200 and out["total"] == 3 and \
            {r["player"] for r in out["rows"]} == {"Staked Likely", "Week Label", "Old Week"}
        h._record_bets({"sport": ["nfl"], "since": [_ago(30)], "offset": ["0"]})
        assert sent[-1][0] == 200 and sent[-1][1]["total"] == 1
        for bad in ({"kind": ["parlays"]}, {"result": ["win"]}, {"since": ["last month"]},
                    {"sport": ["n; drop"]}, {"offset": ["-1"]}, {"offset": ["x"]},
                    {"offset": ["999999"]}):
            h._record_bets(bad)
            assert sent[-1][0] == 400, bad
    finally:
        ledger.DEFAULT_DB = saved
    assert 'if parsed.path in ("/api/record/bets", "/api/record/bets/"):' in SERVER
    assert "return self._record_bets(parse_qs(parsed.query))" in SERVER


# --- the page ----------------------------------------------------------------
def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const TEAM_SIDE_MARKETS = new Set(["moneyline", "spread", "team_total"]);
      let _recBetKind = "", _recBetResult = "", _recAllPicks = false;
      let _recBetsCtx = {{ recent: new Array(60).fill({{}}) }};
      const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
      const panelEmpty = (t) => `<empty>${{t}}</empty>`;
      const recSettledRow = (b) => `<row>${{b.player}}</row>`;
      {_fn("recBetKind")}
      {_fn("recBetsQuery")}
      {_fn("recBetsURL")}
      {_fn("recBetsLocal")}
      {_fn("recBetsBarHTML")}
      {_fn("recBetsListHTML")}
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


def test_the_page_asks_for_exactly_the_filters_in_view():
    got = _node("""
      const all = recBetsURL(recBetsQuery("all", ""), 0);
      _recBetKind = "props"; _recBetResult = "lost";
      const q = recBetsQuery("nfl", "2026-08-24");
      return { all, q, url: recBetsURL(q, 50), intel: recBetsQuery("intel", "").sport,
               kinds: ["moneyline", "spread", "total", "team_total", "hits", "anytime_td"].map(recBetKind) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["all"] == "/api/record/bets", "no filter, no query string"
    assert got["q"] == {"sport": "nfl", "kind": "props", "result": "lost", "since": "2026-08-24"}
    assert got["url"] == "/api/record/bets?sport=nfl&kind=props&result=lost&since=2026-08-24&offset=50"
    assert got["intel"] == ""
    assert got["kinds"] == ["lines", "lines", "lines", "lines", "props", "props"], \
        "the engine's GAME_MARKETS, from the page's own set plus total"
    assert set(ledger.GAME_MARKETS) == {"moneyline", "spread", "total", "team_total"}


def test_without_the_api_the_shipped_rows_are_filtered_and_called_recent():
    got = _node("""
      const recent = [
        { player: "A", market: "hits", status: "won", date: "2026-09-20" },
        { player: "B", market: "total", status: "lost", date: "2026-09-19", day: "2026-09-19" },
        { player: "C", market: "spread", status: "won", date: "2026-W40", day: "2026-09-01" }];
      _recBetKind = "lines";
      const lines = recBetsLocal(recent, recBetsQuery("all", "")).map((b) => b.player);
      const dayed = recBetsLocal(recent, recBetsQuery("all", "2026-09-10")).map((b) => b.player);
      const st = { rows: recBetsLocal(recent, recBetsQuery("all", "")), remote: false, total: null };
      const local = recBetsListHTML(st, 400, recBetsQuery("all", ""));
      _recBetKind = "";
      const none = recBetsListHTML({ rows: [], remote: false }, 0, recBetsQuery("all", ""));
      return { lines, dayed, local, none };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["lines"] == ["B", "C"]
    assert got["dayed"] == ["B"], "the calendar day, not the week label"
    assert got["local"]["line"].endswith(" · of the 60 most recent settled"), got["local"]["line"]
    assert "<row>B</row><row>C</row>" in got["local"]["list"]
    assert "<empty>Nothing settled yet.</empty>" in got["none"]["list"]


def test_with_the_api_the_list_counts_the_whole_record_and_pages_on():
    got = _node("""
      _recBetResult = "won";
      const rows = new Array(50).fill(0).map((_, i) => ({ player: "P" + i }));
      const dozen = recBetsListHTML({ rows, total: 173, remote: true }, 400, recBetsQuery("all", ""));
      _recAllPicks = true;
      const page = recBetsListHTML({ rows, total: 173, remote: true }, 400, recBetsQuery("all", ""));
      const last = recBetsListHTML({ rows, total: 80, remote: true }, 400, recBetsQuery("all", ""));
      const done = recBetsListHTML({ rows: rows.slice(0, 3), total: 3, remote: true }, 400, recBetsQuery("all", ""));
      const empty = recBetsListHTML({ rows: [], total: 0, remote: true }, 400, recBetsQuery("all", ""));
      return { dozen, page, last, done, empty, bar: recBetsBarHTML(recBetsQuery("all", "")) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["page"]["line"].endswith("· 173 settled bets match"), got["page"]["line"]
    assert got["dozen"]["list"].count("<row>") == 12, "a dozen first, as the list always opened"
    assert 'data-act="recShowPicks">Show 38 more<' in got["dozen"]["list"], "then what is already here"
    assert got["page"]["list"].count("<row>") == 50
    assert "data-bets-more" in got["page"]["list"] and "Show 50 more" in got["page"]["list"] \
        and "of 123" in got["page"]["list"], "then the journal's next fifty"
    assert "Show 30 more</button>" in got["last"]["list"] and " of " not in got["last"]["list"], \
        "the last page does not count itself twice"
    assert "data-bets-more" not in got["done"]["list"], "nothing left, no button"
    assert "<empty>No settled bets match these filters.</empty>" in got["empty"]["list"]
    chips = re.findall(r'data-bf="(\w+)" data-v="(\w*)" aria-pressed="(true|false)">([^<]+)<', got["bar"])
    assert chips == [("kind", "", "true", "All bets"), ("kind", "props", "false", "Props"),
                     ("kind", "lines", "false", "Game lines"), ("result", "", "false", "Any result"),
                     ("result", "won", "true", "Won"), ("result", "lost", "false", "Lost")], chips


def test_the_record_page_mounts_the_list_and_each_row_says_model_and_close():
    rr = _fn("renderRecord")
    assert "recBetsMount(host, src.recent || [], o.settled, scope, from);" in rr, \
        "the scope and the window in view"
    rs = _fn("recRecentSection")
    assert 'id="rec-bets-sub"' in rs and '<div id="rec-bets-bar"></div>' in rs \
        and '<div class="card rec-list" id="rec-bets">' in rs
    mount = _fn("recBetsMount")
    assert "if (fresh) recBetsFetch(host, 0);" in mount, "one ask per new filter"
    fetch_ = _fn("recBetsFetch")
    assert "if (_recBets.key !== key) return;" in fetch_, "a slow answer never paints over a newer filter"
    row = _fn("recSettledRow")
    assert "b.hit_prob != null ? ` · model ${(Number(b.hit_prob) * 100).toFixed(0)}%` : \"\"" in row
    assert "b.closing_odds != null ? ` · closed ${escapeHtml(oddsTxt(b.closing_odds))}` : \"\"" in row, \
        "the close through the one price formatter"
    assert "the settled bets are the last ${winDays} days" in rr, "the window note names the list too"
    assert ".rec-bets-bar {" in CSS and ".rec-bf.active {" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
