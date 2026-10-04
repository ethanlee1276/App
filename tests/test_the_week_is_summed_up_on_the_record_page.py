"""The Record page leads with the last seven days, each book on its own.

Ethan, 2026-10-04: "do all of it" — the weekly recap. engine/recap reads
the journal's settled picks from the last seven Eastern days, per published
book, and the export carries it as weekly_recap for the Record page's
"This week" card. Checks: the window is seven days by game day; voids and
open picks stay out; the books never pool; the best hit is the longest
price that won and the toughest miss the highest claim that lost; the
export carries it; the card draws it and draws nothing for an empty week.

Run directly: `python3 tests/test_the_week_is_summed_up_on_the_record_page.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger, recap                                    # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
NOW = dt.datetime(2026, 10, 5, 3, 0)          # 11 pm Sunday, Eastern
_SEQ = [0]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


def _bet(conn, category, status, day, odds=-120, prob=0.6, pnl=0.0, sport="nfl"):
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,book,hit_prob,edge,"
        "stake_units,stake_dollars,ts,status,category,pnl_units) VALUES "
        "(?,?,?,?,'anytime_td','OVER',0.5,?,'DK',?,0,1,0,'now',?,?,?)",
        (sport, day, day, f"P{_SEQ[0]}", odds, prob, status, category, pnl))
    conn.commit()


def _book(out, name):
    return next((b for b in out["books"] if b["book"] == name), None)


def test_the_window_is_the_last_seven_eastern_days():
    c = _conn()
    _bet(c, "likely_live", "won", "2026-10-04", pnl=0.8)
    _bet(c, "likely_live", "won", "2026-09-28", pnl=0.8)
    _bet(c, "likely_live", "lost", "2026-09-27", pnl=-1)      # eight days back: out
    out = recap.recap(c, now=NOW)
    assert (out["from"], out["to"]) == ("2026-09-28", "2026-10-04")
    b = _book(out, "Most Likely")
    assert (b["w"], b["l"], b["p"]) == (2, 0, 0) and b["units"] == 1.6


def test_voids_and_open_picks_stay_out():
    c = _conn()
    _bet(c, "likely_live", "void", "2026-10-04")
    _bet(c, "likely_live", "pending", "2026-10-04")
    assert recap.recap(c, now=NOW)["books"] == []


def test_the_books_never_pool():
    c = _conn()
    _bet(c, "likely_live", "won", "2026-10-03", pnl=0.8)
    _bet(c, "board", "lost", "2026-10-03", pnl=-1)
    _bet(c, "main", "push", "2026-10-03")
    _bet(c, "stale", "won", "2026-10-03", pnl=1)              # a sampler: not a published book
    out = recap.recap(c, now=NOW)
    assert [b["book"] for b in out["books"]] == ["Most Likely", "The one board", "Edge picks"]
    assert (_book(out, "The one board")["w"], _book(out, "The one board")["l"]) == (0, 1)
    assert _book(out, "Edge picks")["hit"] is None            # a push alone decides nothing


def test_the_best_hit_and_the_toughest_miss():
    c = _conn()
    _bet(c, "likely_live", "won", "2026-10-04", odds=-150, prob=0.62)
    _bet(c, "likely_live", "won", "2026-10-04", odds=135, prob=0.45)
    _bet(c, "likely_live", "lost", "2026-10-04", odds=-200, prob=0.70)
    _bet(c, "likely_live", "lost", "2026-10-04", odds=110, prob=0.50)
    b = _book(recap.recap(c, now=NOW), "Most Likely")
    assert b["best"]["odds"] == 135 and b["worst"]["claim"] == 0.7
    assert b["hit"] == 0.5 and b["claimed"] == round((0.62 + 0.45 + 0.70 + 0.50) / 4, 3)
    assert b["by_sport"] == {"nfl": {"w": 2, "l": 2}}


def test_the_export_carries_it():
    assert '"weekly_recap": _recap_or_empty(conn)' in (ROOT / "engine" / "ledger.py").read_text()
    assert ledger._recap_or_empty(_conn())["books"] == []


def test_the_card_draws_it_and_nothing_for_an_empty_week():
    i = APP.index("function weekRecapHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert 'if (!books.length) return "";' in fn
    for want in ("Best hit", "Toughest miss", "we said", "the price said"):
        assert want in fn, want
    r = APP[APP.index("async function renderRecord("):]
    assert "weekRecapHTML(d.weekly_recap)" in r[:r.index("\n}\n")]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
