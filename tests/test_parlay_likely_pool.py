"""The parlay screen learns to run over the Most Likely board.

Ethan, 2026-09-06: "i want to focus more on the parlay model for the best
bets first then work on the model for parlays for the edge bets ... as
those hit more often and will return more money."

The first half is measured and true — that board hits 62.2% against the
edge board's 48.1%. The second half is the thing this repo keeps
measuring and finding false: hitting more often is not returning more
money, and parlaying roughly doubles whatever the singles ROI already
is. Off their own settled records a 2-leg comes to -5.85% from Most
Likely and -8.80% from the edge board, so his ranking holds and both
signs are negative.

WHAT THIS FILE ACTUALLY GUARDS is the honesty of the split, because the
screen's founding rule is against it. §0: "a leg that would not be a bet
on its own is never a bet inside a parlay" — and a Most Likely row is
NOT a bet. It carries `recommended` False and a zero stake by
construction. So the pool is admitted on a DIFFERENT bar, named in the
code, and its tickets are paper measuring paper: journaled to their own
source, never staked, graduating only the way the board under them
graduates.

The failure this is built to prevent is the two records blending. One
table, one ROI, two boards — the same shape `ledger.BOOK` against
`category='likely'` prevents on the singles side.

Run directly: `python3 tests/test_parlay_likely_pool.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlays as P
from engine import parlayledger as PL


def _row(player="A Wideout", market="receptions", p=0.62, **kw):
    got = {"kind": "prop", "player": player, "team": "DET", "opponent": "CHI",
           "market": market, "market_label": market, "side": "over",
           "line": 4.5, "odds": -115, "model_prob": p, "book": "dk",
           "game_date": "2026-09-13", "ev_per_unit": 0.02}
    got.update(kw)
    return got


def _slate(rows=None):
    return {"most_likely": rows if rows is not None else [_row()],
            "games": [{"home": "DET", "away": "CHI", "date": "2026-09-13",
                       "spread": -3.0, "lineups_confirmed": True}]}


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    return c


def test_each_pool_reads_only_the_board_it_names():
    slate = _slate()
    assert P.screen(slate, "nfl", pool="likely")["eligible_legs"] == 1
    # The edge screen reads `recommendations`, which this slate has none of.
    # A likely row must be invisible to it or the boards have merged.
    assert P.screen(slate, "nfl", pool="edge")["eligible_legs"] == 0


def test_the_adapter_never_writes_on_the_board_row():
    """THE ONE THAT MATTERS MOST. The legs need `recommended` and
    `hit_prob` for the shared gates to read them, and the board's rows
    must not acquire either — a Most Likely row that started reporting
    itself as recommended would knock over every "is this a bet" check
    in the repo at once, including the journal's."""
    slate = _slate()
    before = dict(slate["most_likely"][0])
    P.likely_pool(slate, "nfl")
    assert slate["most_likely"][0] == before, slate["most_likely"][0]
    assert "hit_prob" not in slate["most_likely"][0]
    assert slate["most_likely"][0].get("recommended") is None


def test_a_row_with_no_board_probability_is_not_a_leg():
    legs = P.likely_pool(_slate([_row(), _row(player="Bare", p=None)]), "nfl")
    assert [l["player"] for l in legs] == ["A Wideout"], legs


def test_section_zero_is_answered_rather_than_bypassed():
    """A likely leg clears a different bar and says which. An EDGE leg
    that is not recommended is still refused, in the doc's own words —
    the split must not have loosened the original rule."""
    rules = P.RULES["nfl"]
    likely = dict(_row(), hit_prob=0.62, recommended=True, leg_basis="likely")
    assert P._leg_eligible("nfl", likely, None, rules) == ""
    unrecommended = dict(_row(), hit_prob=0.62, recommended=False)
    why = P._leg_eligible("nfl", unrecommended, None, rules)
    assert "§0" in why and "never a bet inside a parlay" in why, why
    # And a "likely" leg with no board probability cleared no bar at all.
    hollow = {"market": "receptions", "leg_basis": "likely", "recommended": True}
    assert "no bar it can be said to have cleared" in \
        P._leg_eligible("nfl", hollow, None, rules)


def test_an_unknown_pool_is_refused_loudly():
    try:
        P.screen(_slate(), "nfl", pool="everything")
    except ValueError as exc:
        assert "everything" in str(exc)
    else:
        raise AssertionError("an unknown pool screened something")


def test_the_screen_stamps_which_pool_produced_the_payload():
    for pool in P.POOLS:
        assert P.screen(_slate(), "nfl", pool=pool)["pool"] == pool


def test_the_two_records_cannot_blend():
    """One table, two boards. A blended ROI answers a question nobody
    asked — the failure `ledger.BOOK` prevents on the singles side."""
    c = _conn()
    for src, pnl in (("edge", -1.0), ("likely", 3.0)):
        c.execute("INSERT INTO parlays (ts,sport,date,legs_key,n_legs,status,"
                  "pnl_units,notional_units,source) VALUES "
                  "('t','nfl','2026-09-13',?,2,'lost',?,1.0,?)",
                  (f"k-{src}", pnl, src))
    c.commit()
    assert PL.report(c, "edge")["graded"] == 1
    assert PL.report(c, "likely")["graded"] == 1
    assert PL.report(c, "edge")["net_units"] == -1.0
    assert PL.report(c, "likely")["net_units"] == 3.0


def test_a_ticket_written_before_the_column_existed_is_edge():
    """Every row in the journal today came from the edge board. Calling
    that unknown would file the entire existing record under "not
    sure"."""
    c = _conn()
    c.execute("INSERT INTO parlays (ts,sport,date,legs_key,n_legs,status,"
              "pnl_units,notional_units) VALUES "
              "('t','mlb','2026-08-01','old',2,'lost',-1.0,1.0)")
    c.execute("UPDATE parlays SET source=NULL")
    c.commit()
    assert PL.report(c, "edge")["graded"] == 1, "a legacy row went missing"
    assert PL.report(c, "likely")["graded"] == 0


def test_the_journal_reads_the_pool_off_the_payload_not_off_a_caller():
    """`screen` stamps `pool` on what it returns, so the record cannot
    disagree with the screen that produced it. A caller passing the wrong
    argument is exactly the kind of drift a stamped payload rules out."""
    src = (ROOT / "engine" / "parlayledger.py").read_text()
    assert 'board.get("pool") or "edge"' in src, src[:0]
    assert "def log_board(conn, board: dict" in src


# --- the wiring -----------------------------------------------------------
def test_attach_hangs_both_pools_on_the_slate():
    slate = _slate([_row("A Wideout", "receptions", 0.64),
                    _row("A QB", "pass_yds", 0.61, line=245.5)])
    slate.update(recommendations=[], game_bets=[])
    P.attach(slate, "nfl")
    assert slate["parlays"]["pool"] == "edge"
    assert slate["likely_parlays"]["pool"] == "likely"
    assert slate["likely_parlays"]["eligible_legs"] == 2
    # receptions is Tier 1, so §4's anchor rule is satisfiable here and the
    # pair actually reaches a ticket rather than dying at the door.
    assert slate["likely_parlays"]["tickets"], slate["likely_parlays"]["killed"]


def test_one_pool_failing_does_not_blank_the_other():
    """ONE TRY EACH. A single guard around both would let the new screen
    take down the working one — exactly the shape `attach`'s "never
    raises" promise exists to prevent, one level in."""
    slate = _slate()
    slate.update(recommendations=[], game_bets=[])
    real = P.screen
    calls = []

    def boom(sl, sport, **kw):
        calls.append(kw.get("pool"))
        if kw.get("pool") == "likely":
            raise RuntimeError("the likely screen fell over")
        return real(sl, sport, **kw)

    P.screen = boom
    try:
        P.attach(slate, "nfl")
    finally:
        P.screen = real
    assert calls == ["edge", "likely"], calls
    assert slate["parlays"]["pool"] == "edge", "a working pool was blanked"
    assert "fell over" in " ".join(slate["likely_parlays"]["notes"])
    assert slate["likely_parlays"]["tickets"] == []


def test_the_new_payload_is_paid_like_the_board_it_screens():
    """`most_likely` and `parlays` are both paid. A screen over one,
    published under a key nobody added to the list, hands a paid board's
    rows back for free in ticket form — the fourth time this file has
    been taught that a new VIEW of a paid board is a new KEY."""
    from engine import gate
    pub = gate.redact({"parlays": {"tickets": [1]},
                       "likely_parlays": {"tickets": [1]},
                       "most_likely": [1]}, "recommendations.json")
    for key in ("parlays", "likely_parlays", "most_likely"):
        assert not pub.get(key), f"{key} survived the public copy"


def test_the_journal_reads_both_keys():
    """A board built, shown and never graded is the failure the paywall
    comment in `journal_built_boards` already records once."""
    src = (ROOT / "engine" / "parlayledger.py").read_text()
    i = src.index("def journal_built_boards")
    nxt = src.find("\ndef ", i + 10)
    body = src[i:] if nxt == -1 else src[i:nxt]   # it is the last function
    assert 'for key in ("parlays", "likely_parlays")' in body, body[:0]
    assert 'board.get(key)' in body


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
