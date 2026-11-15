"""The UFC tab of the Record page reads UFC's own fight picks (2026-11-15).

Ethan sent Record → UFC: the chip said "UFC 43", the verdict said 0-0-0
(0 open, 0 settled), and the week card above it led with NBA rebounds and
NFL tackles — "the ufc record page isn't recording bets and is showing
other sports".

The bets were there: 41 settled and 2 open, journaled under UFC's own book,
category 'ufc' (ledger.ufc_report). The UFC tab read the edge picks, which
UFC never writes to. So (ledger.OWN_BOOK_SPORTS):

  * the UFC scope's headline, verdict, calendar, settled list and calendar
    taps read the 'ufc' book;
  * the all-sports figures still never count it — it stays out of All bets
    until a real sample says it belongs;
  * every other league is unchanged.

    python3 tests/test_the_ufc_tab_reads_its_own_fights.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger as L                                     # noqa: E402
from _app import app_js                                            # noqa: E402

APP = app_js()
_SEQ = [0]


def _conn():
    c = L.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    for cat, status, day, odds, pnl, sport in (
            ("ufc", "won", "2026-11-07", 200, 0.5, "ufc"),
            ("ufc", "lost", "2026-11-07", 150, -0.25, "ufc"),
            ("ufc", "lost", "2026-10-31", 220, -0.2, "ufc"),
            ("ufc", "open", "2026-11-21", 180, 0.0, "ufc"),
            ("main", "won", "2026-11-07", -110, 0.9, "nfl")):
        _SEQ[0] += 1
        c.execute(
            "INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,book,hit_prob,edge,"
            "stake_units,stake_dollars,ts,status,category,pnl_units) VALUES "
            "(?,?,?,?,'moneyline','OVER',0.5,?,'DK',0.4,0,0.25,0,'now',?,?,?)",
            (sport, day, day, f"Fighter {_SEQ[0]}", odds, status, cat, pnl))
    c.commit()
    return c


def test_the_ufc_scope_reads_its_fight_picks():
    r = L.sport_report(_conn(), "ufc")
    o = r["overall"]
    assert (o["settled"], o["open"], o["wins"], o["losses"]) == (3, 1, 1, 2), o
    assert round(o["net_units"], 2) == 0.05
    assert o["label"] == "UFC fight picks · graded in public"
    assert [p["date"] for p in r["curve"]] == ["2026-10-31", "2026-11-07"]
    assert len(r["recent"]) == 3 and all(x["sport"] == "ufc" for x in r["recent"])
    assert r["edge_state"]["open"] == 1 and r["own_book"] == ["ufc"]
    # No pooled block: the page would seat the pooled edge (zero) over it.
    assert "pooled" not in r


def test_every_other_league_reads_as_before_and_all_bets_leaves_ufc_out():
    c = _conn()
    assert L.own_book("nfl") is None and L.edge_books_for("nfl") == L.EDGE_BOOKS
    nfl = L.sport_report(c, "nfl")
    assert nfl["overall"]["settled"] == 1 and "pooled" in nfl
    assert L.performance(c)["settled"] == 1, "the all-sports headline never counts UFC"
    assert L.pooled_report(c)["overall"]["settled"] == 1


def test_the_settled_list_and_the_calendar_taps_page_the_fights():
    c = _conn()
    assert L.settled_page(c, sport="ufc")["total"] == 3
    assert L.settled_page(c)["total"] == 1, "the unscoped list is the headline's rows"
    day = L.settled_on(c, "2026-11-07", sport="ufc", categories=L.edge_books_for("ufc"))
    assert sorted(x["status"] for x in day) == ["lost", "won"]
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    body = src[src.index("    def _record_day("):]
    body = body[:body.index("\n    def ", 10)]
    assert "L.edge_books_for(sport)" in body, "the calendar tap asks the league's own book"


def test_the_page_seats_it_and_names_it():
    # The export builds every league's entry from sport_report.
    led = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert '"by_sport": {sp: {**sport_report(conn, sp, since=since),' in led
    assert '"staked": ({} if own_book(sp) else' in led, "no all-zero staked cut read ahead of it"
    # A record with no pooled block is left as it is (app.js adoptPooledRecord) …
    i = APP.index("function adoptPooledRecord(")
    assert "if (!s || !s.pooled || !s.pooled.overall || s.edge) return s;" in APP[i:i + 400]
    # … its lead carries the book's own name, and a window says it too.
    assert '(ov.label || "Edge picks · graded in public")' in APP
    assert 'String((src.overall || {}).label || "Edge picks").split(" · ")[0]' in APP
    # The tab says once that All bets leaves it out.
    r = APP[APP.index("async function renderRecord("):]
    r = r[:r.index("\n}\n")]
    assert "scoped && src.own_book" in r and "+ ownNote" in r


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=5)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
