"""One record. Ethan, 2026-09-22: "we want both records and all that
shit combined so we can display 1 roi and shit … obv each sport will
have there own page and shit but the most likley and edge record will
be combined."

The edge book (`BOOK`: main, paper, and the staked Most Likely rows)
and the Most Likely paper rows (`likely`) were two headline records on
one page. The ledger now exports the whole journal as one book
(`POOLED_BOOKS`, `pooled_report`), the site seats it where the edge
book sat (`adoptPooledRecord`) so every surface — the verdict, the
deck's ribbon, the sidebar's running ROI, the paywall's proof — reads
one number, and the verdict shows the two books side by side beneath
it. Per sport too. Nothing about grading changes; the paper share is
counted (`PAPER_BOOKS`) and said next to the number.
"""
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
from engine import ledger  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


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


ROWS = [
    # sport, player, category, odds, stake_u, stake_d, status, pnl_u, pnl_d
    ("nfl", "Edge One", "main", -110, 1.0, 10.0, "won", 0.909, 9.09),
    ("nfl", "Paper One", "paper", -110, 1.0, 0.0, "won", 0.909, 0.0),
    ("nfl", "Likely Paper", "likely", -130, 0.1, 0.0, "lost", -0.1, 0.0),
    ("nfl", "Likely Live", "likely_live", -110, 0.25, 2.5, "won", 0.227, 2.27),
    ("mlb", "Likely Paper Two", "likely", 120, 0.1, 0.0, "won", 0.12, 0.0),
    ("nfl", "Long Shot", "longshot", 400, 0.1, 1.0, "won", 0.4, 4.0),
]


def _journal():
    conn = ledger.connect(":memory:")
    day = ledger.RECORD_EPOCH
    for sport, player, cat, odds, su, sd, status, pu, pd in ROWS:
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,book,hit_prob,"
            "stake_units,stake_dollars,status,category,pnl_units,pnl_dollars) VALUES "
            "(?,?,?,'pass_yds','OVER',245.5,?,'DraftKings',0.6,?,?,?,?,?,?)",
            (sport, day, player, odds, su, sd, status, cat, pu, pd))
    conn.commit()
    return conn


def test_the_pooled_book_is_the_edge_book_plus_the_paper_most_likely_rows():
    assert ledger.POOLED_BOOKS == ledger.BOOK + ("likely",)
    assert "likely_live" in ledger.BOOK, "the staked Most Likely rows were already in the edge book"
    assert ledger.PAPER_BOOKS == ("paper", "likely")
    conn = _journal()
    edge = ledger.performance(conn)
    pooled = ledger.pooled_report(conn)["overall"]
    assert edge["settled"] == 3 and pooled["settled"] == 5, "the two paper Most Likely rows join; the long shot does not"
    assert (pooled["wins"], pooled["losses"]) == (4, 1)
    assert abs(pooled["net_units"] - round(0.909 + 0.909 - 0.1 + 0.227 + 0.12, 2)) < 1e-6
    assert abs(pooled["units_staked"] - 2.45) < 1e-6
    assert abs(pooled["roi"] - (0.909 + 0.909 - 0.1 + 0.227 + 0.12) / 2.45) < 1e-6, "one ROI, net over everything staked"
    assert pooled["paper_bets"] == 3 and edge["paper_bets"] == 1, "the paper share counts the paper Most Likely rows"
    assert pooled["money_bets"] == 2, "and the dollar figure still counts only rows with money on them"
    assert abs(pooled["net_dollars"] - 11.36) < 1e-6


def test_the_pooled_curve_and_receipts_carry_the_same_rows():
    conn = _journal()
    edge = ledger.pnl_curve(conn)
    pooled = ledger.pnl_curve(conn, category=ledger.POOLED_BOOKS)
    assert sum(p["n"] for p in edge) == 3 and sum(p["n"] for p in pooled) == 5
    assert abs(pooled[-1]["cum_u"] - ledger.pooled_report(conn)["overall"]["net_units"]) < 1e-6, \
        "the curve ends where the record stands"
    rep = ledger.pooled_report(conn)
    assert {r["player"] for r in rep["recent"]} >= {"Likely Paper", "Edge One", "Likely Live"}
    assert "Long Shot" not in {r["player"] for r in rep["recent"]}
    assert rep["books"] == list(ledger.POOLED_BOOKS)
    both = ledger.EDGE_BOOKS + ledger.LIKELY_BOOKS
    assert ledger.EDGE_BOOKS == ("main", "paper") and set(both) == set(ledger.POOLED_BOOKS) \
        and len(both) == len(set(both)) == len(ledger.POOLED_BOOKS), \
        "the two cards under the number are disjoint and complete"
    likely = ledger.likely_report(conn)
    assert rep["edge"]["settled"] + likely["settled"] == rep["overall"]["settled"] == 5, "edge board + Most Likely = the one number"
    assert abs(rep["edge"]["net_units"] + likely["net_units"] - rep["overall"]["net_units"]) < 0.011
    nfl = ledger.pooled_report(conn, "nfl")["overall"]
    assert nfl["settled"] == 4, "per sport, the same book"


def test_the_export_carries_the_pooled_book_beside_the_edge_book_on_every_scope():
    conn = _journal()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "record.json")
        ledger.export_json(conn, path)
        d = json.load(open(path))
    assert d["overall"]["settled"] == 3, "the edge book is still exported where it was"
    assert d["pooled"]["overall"]["settled"] == 5
    assert d["pooled"]["books"] == list(ledger.POOLED_BOOKS)
    assert sum(pt["n"] for pt in d["pooled"]["curve"]) == 5 and sum(pt["n"] for pt in d["curve"]) == 3, \
        "the pooled curve is drawn over the pooled book, the edge curve over the edge book"
    assert {r["player"] for r in d["pooled"]["recent"]} > {r["player"] for r in d["recent"]}
    assert d["by_sport"]["nfl"]["pooled"]["overall"]["settled"] == 4
    assert d["by_sport"]["nfl"]["overall"]["settled"] == 3


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_fn("adoptPooledRecord")}
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


def test_the_site_seats_the_pooled_book_where_the_edge_book_sat():
    got = _node("""
      const file = { overall: { settled: 3, roi: 0.1 }, curve: [1], recent: ["e"],
        pooled: { overall: { settled: 5, roi: 0.2 }, edge: { settled: 2 }, curve: [1, 2], recent: ["e", "l"] },
        by_sport: { nfl: { overall: { settled: 3 }, pooled: { overall: { settled: 4 } } },
                    mlb: { overall: { settled: 0 } } } };
      const rec = adoptPooledRecord(file);
      const twice = adoptPooledRecord(rec);
      const old = adoptPooledRecord({ overall: { settled: 3 } });
      return { top: rec.overall.settled, edge: rec.edge.overall.settled, curve: rec.curve.length, board: rec.edge_board,
               recent: rec.recent, nfl: rec.by_sport.nfl.overall.settled, nflEdge: rec.by_sport.nfl.edge.overall.settled,
               mlb: rec.by_sport.mlb.overall.settled, mlbEdge: !!rec.by_sport.mlb.edge,
               idempotent: twice.edge.overall.settled, oldFile: old.overall.settled, oldEdge: !!old.edge,
               nothing: adoptPooledRecord(null) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["top"] == 5 and got["edge"] == 3, "the pooled book is the record; the edge book keeps its seat"
    assert got["board"] == {"settled": 2}, "and the edge board alone rides beside it for the verdict"
    assert got["curve"] == 2 and got["recent"] == ["e", "l"]
    assert got["nfl"] == 4 and got["nflEdge"] == 3, "per sport too"
    assert got["mlb"] == 0 and got["mlbEdge"] is False, "a scope without a pooled block is untouched"
    assert got["idempotent"] == 3, "adopting twice does not bury the edge book under the pooled one"
    assert got["oldFile"] == 3 and got["oldEdge"] is False, "a file from before this is left as it was"
    assert got["nothing"] is None
    load = _fn("loadRecordOnce")
    assert "adoptPooledRecord(await res.json())" in load, "every surface reading the record file gets the pooled book"
    rr = _fn("renderRecord")
    assert "if (res.ok) d = adoptPooledRecord(await res.json());" in rr, "the Record page reads the file on its own"
    assert 'recordVerdictHTML(src, scope === "all"' in rr and "scoped ? (d.likely_by_sport || {})[scope] : d.likely);" in rr
    assert "recEdgePanel(d.edge_now, d.edge_trend, (d.edge || d).overall)" in rr, "the edge measurement stays over the edge book"


def test_the_verdict_is_one_number_with_the_two_books_beneath_it():
    v = _fn("recordVerdictHTML")
    assert "function recordVerdictHTML(src, scopeLabel, lk)" in v
    assert "const pooled = !!(src && src.edge && src.edge.overall);" in v
    assert "const edge = pooled ? (src.edge_board || src.edge.overall) : o;" in v, \
        "the edge card is the edge board alone, so the two cards add up to the number above them"
    assert "the edge board and the Most Likely board as one book, " in v, "the sub-line says what the number pools"
    assert ": pooled ? verdictBooksHTML(edge, lk, chart, lines)" in v
    assert '<div class="rv-read">${chart}' in v, "an unpooled file still gets the old reading"
    b = _fn("verdictBooksHTML")
    assert '<span class="hd-eyebrow">Edge bets</span>' in b and '<span class="hd-eyebrow">Most likely</span>' in b
    assert "${line(edge)}" in b and '${lk ? line(lk) : "no rows yet"}' in b
    assert "reliabilityDiagram(likelyBuckets)" in b and "predicted: b.claimed, actual: b.actual, n: b.n, ci," in b, \
        "the Most Likely diagram is drawn from its bands, in the edge diagram's shape"
    assert "2 * Math.sqrt(Math.max(0, b.actual * (1 - b.actual)) / b.n)" in b, "the same two-standard-error band"
    assert 'lk && lk.verdict ? `<p>${escapeHtml(String(lk.verdict))}</p>` : ""' in b
    assert ".rv-books { display: grid; gap: 14px; margin-top: 18px; }" in CSS
    assert "@media (min-width: 900px) { .rv-books { grid-template-columns: 1fr 1fr; } }" in CSS
    assert ".rv-book svg { display: block; max-width: 100%; height: auto; margin-bottom: 10px; }" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
