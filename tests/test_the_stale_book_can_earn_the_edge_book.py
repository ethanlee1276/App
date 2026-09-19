"""A shadow book that clears its bar becomes a real one.

Ethan, 2026-09-19: *"us not having any edge bets for cfb in 2 weeks is a
problem so we need to fix that."*

College cannot get them from the model. `engine.gamecal`, fitted on this
box over 2,016 college games, puts the slope of the model's disagreement
with the closing line at **−0.0788** on the moneyline and −0.0367 on the
spread — NEGATIVE, meaning that when the college model disagrees with the
line it has been wrong more often than right. `temper` therefore keeps
0% of every disagreement, every card grades Pass, and the Edge board is
correctly empty. Reopening that path stakes money on a signal measured
to lose, which is the one thing this engine is built not to do.

The stale-line book is the other way up, and it was built for this. It
bets a PRICE DISAGREEMENT — a book pricing a side at least a point below
the field's consensus — not an opinion about who wins. It has journaled
flat 0.1u shadow bets since the season opened so it could earn its way
into the record, and `stale_verdict` has computed the answer on every
export since it was written.

Nothing ever read it. No renderer, no pipeline — its own docstring says
"the pipeline that would act on a promote is a separate change, made
with this number in hand." This is that change, and the bar it acts on
is the one already written: 200 settled flags, a hit rate two standard
errors clear of the break-even OF THE PRICES ACTUALLY TAKEN, and a
positive flat-stake ROI.

Run directly: `python3 tests/test_the_stale_book_can_earn_the_edge_book.py`
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                      # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
_SEQ = [0]


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


def _settled_flags(conn, sport, n, wins, odds=-110):
    """`n` graded stale flags, `wins` of them won, at a real price."""
    for i in range(n):
        _SEQ[0] += 1
        won = i < wins
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
            "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
            "pnl_units) VALUES (?,?,?,'total_bases','OVER',2.5,?,'DK',0.6,0,"
            "0.1,0,'now',?,'stale',?)",
            (sport, "2026-09-01", f"P{_SEQ[0]}", odds,
             "won" if won else "lost",
             0.0909 if won else -0.1))
    conn.commit()


def _slate(sport, n=1):
    """A build payload carrying `n` fresh stale flags."""
    return {"sport": sport, "date": "2026-09-20", "market_scan": {"stale": [
        {"player": f"New{i}", "market": "total_bases", "side": "OVER",
         "line": 2.5, "odds": -110, "book": "DK", "consensus": 0.55,
         "gap_pts": 1.5} for i in range(n)]}}


def _journaled(conn):
    return conn.execute(
        "SELECT category, grade, stake_units FROM bets "
        "WHERE player LIKE 'New%'").fetchall()


# --- the bar decides, and only the bar ---------------------------------
def test_a_book_that_clears_every_guard_is_promoted():
    """200 flags, 62.5% at a 52.4% break-even (z +2.9), ROI positive.

    119 wins is the actual threshold here — 116 reads 58% and z +1.6,
    which the bar rejects, and that is the bar working."""
    c = _conn()
    _settled_flags(c, "cfb", 200, 125)
    v = ledger.stale_verdict(c)["cfb"]
    assert v["verdict"] == "promote", v
    assert ledger.stale_promoted(c, "cfb") is True


def test_a_thin_book_is_not_promoted():
    """College's actual position today: journaling, not yet 200."""
    c = _conn()
    _settled_flags(c, "cfb", 132, 77)
    assert ledger.stale_promoted(c, "cfb") is False
    assert "needs 200" in ledger.stale_verdict(c)["cfb"]["why"]


def test_a_book_that_beats_the_rate_but_not_the_vig_is_not_promoted():
    """The guard that matters most: a flag can beat the break-even and
    still lose money. ROI decides, not the hit rate."""
    c = _conn()
    _settled_flags(c, "cfb", 250, 133)          # 53.2% vs 52.4%
    v = ledger.stale_verdict(c)["cfb"]
    assert v["verdict"] == "hold", v
    assert ledger.stale_promoted(c, "cfb") is False


def test_promotion_is_per_sport():
    """A baseball verdict says nothing about football's flags."""
    c = _conn()
    _settled_flags(c, "mlb", 200, 125)
    _settled_flags(c, "cfb", 40, 30)
    assert ledger.stale_promoted(c, "mlb") is True
    assert ledger.stale_promoted(c, "cfb") is False


def test_the_bar_is_the_verdicts_own_and_cannot_be_lowered_here():
    src = (ROOT / "engine" / "ledger.py").read_text()
    body = src[src.index("def stale_promoted("):]
    body = body[:body.index("\ndef ", 10)]
    assert 'v.get("verdict") == "promote"' in body, body
    for knob in ("min_n", "min_z", "MIN_N", "PROMOTE_MIN"):
        assert knob not in body, f"{knob} — the bar is being re-decided here"


def test_an_unreadable_journal_does_not_promote():
    """FAILS CLOSED. Not promoting costs a missed bet; wrongly promoting
    stakes money on an unverified signal."""
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no such table: bets")
    assert ledger.stale_promoted(Broken(), "cfb") is False


# --- what a promoted flag is journaled as ------------------------------
def test_an_unpromoted_flag_is_still_a_shadow_bet():
    c = _conn()
    _settled_flags(c, "cfb", 132, 77)
    assert ledger.log_stale_flags(c, _slate("cfb")) == 1
    row = _journaled(c)[0]
    assert row["category"] == "stale", dict(row)
    assert row["stake_units"] == 0.1, dict(row)


def test_a_promoted_flag_is_journaled_as_an_edge_bet():
    """THE POINT. College gets edge bets the moment its own record says
    the signal pays."""
    c = _conn()
    _settled_flags(c, "cfb", 200, 125)
    assert ledger.log_stale_flags(c, _slate("cfb")) == 1
    row = _journaled(c)[0]
    assert row["category"] == "main", dict(row)
    assert row["stake_units"] == ledger.STALE_PROMOTED_STAKE, dict(row)
    assert row["grade"] == ledger.STALE_PROMOTED_GRADE, dict(row)


def test_a_promoted_flag_reaches_the_headline_record():
    c = _conn()
    _settled_flags(c, "cfb", 200, 125)
    ledger.log_stale_flags(c, _slate("cfb"))
    # `performance` is the headline: category IN ('main','paper') and a
    # stake above zero. An edge bet has to be in it or the promotion did
    # nothing a reader can see.
    assert ledger.performance(c, "cfb")["open"] == 1


def test_a_promoted_flag_is_not_journaled_twice():
    """One bet, one book. In both it would be double-counted by
    `book_records` and would let the sampler go on grading the
    consequences of its own promotion."""
    c = _conn()
    _settled_flags(c, "cfb", 200, 125)
    ledger.log_stale_flags(c, _slate("cfb", n=3))
    rows = _journaled(c)
    assert len(rows) == 3, rows
    assert {r["category"] for r in rows} == {"main"}, [dict(r) for r in rows]


def test_the_flags_that_earned_it_stay_where_they_are():
    """The evidence is not rewritten by the thing it licensed."""
    c = _conn()
    _settled_flags(c, "cfb", 200, 125)
    ledger.log_stale_flags(c, _slate("cfb"))
    n = c.execute("SELECT COUNT(*) FROM bets WHERE category='stale'").fetchone()[0]
    assert n == 200, n


def test_the_promoted_stake_is_flat():
    """The evidence is a FLAT-stake ROI, so the bet it licenses is flat.
    Kelly would size on a win probability the sampler never estimated."""
    src = (ROOT / "engine" / "ledger.py").read_text()
    body = src[src.index("def log_stale_flags("):]
    body = body[:body.index("\ndef ", 10)]
    assert "STALE_PROMOTED_STAKE if promoted else flat_stake" in body, body
    assert "kelly" not in body.lower(), "the promoted stake is being sized"


# --- and the ladder is visible ----------------------------------------
def test_the_record_page_draws_the_ladder():
    """`stale_verdicts` was exported on every build and read by nothing
    — no renderer, no pipeline. A reader could not see college climbing,
    which is why Ethan had to ask why the board was empty."""
    assert "recStaleLadder(d.stale_verdicts, scope)" in APP, \
        "the promotion ladder is published and rendered nowhere again"


def test_the_ladder_names_the_guard_that_is_holding_a_league():
    body = _fn("recStaleLadder")
    assert "v.why" in body, "the ladder shows no reason for a hold"
    assert "break-even" in body and "v.n" in body, body


def test_the_ladder_scopes_to_the_league_in_view():
    body = _fn("recStaleLadder")
    assert 'scope === "all" || sp === scope' in body, body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
