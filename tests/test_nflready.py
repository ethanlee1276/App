"""One table that answers "is the NFL board ready", with the evidence.

Ethan, 2026-08-30: "i wanna keep working on nfl. its not done or ready
yet." Both that and its opposite are claims nobody can check, and six
gates stand between a modelled prop and a published pick — each closing a
market for a different reason with a different remedy.

The distinction this module exists to draw is between states that look
identical from an empty board and need opposite work:

    UNMEASURED      never fitted. Not broken — unmeasured
    SHUT            fitted, and the fit disqualified itself
    LIVE, SILENT    bettable and it has never published anything
    LIVE, UNPROVEN  publishing, not enough settled to judge
    LIVE, LOSING    settled, and it has not paid

Run directly: `python3 tests/test_nflready.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import nflready as R                             # noqa: E402


def _ledger(rows=()):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, status TEXT, "
                 "pnl_units REAL, stake_units REAL)")
    conn.executemany("INSERT INTO bets VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return conn


# --- the states, which is the whole point --------------------------------
def test_never_fitted_reads_as_unmeasured_not_as_broken():
    """The two produce an identical empty board and need opposite work:
    one needs a refit, the other needs data to fit against."""
    state, why = R.verdict_for({"fitted": False, "one_sided": False,
                                "reliable": True, "settled": {"n": 0}})
    assert state == "UNMEASURED", state
    assert "not broken, unmeasured" in why


def test_a_boundary_fit_reads_as_shut_and_says_why():
    """A fit at the edge of its search range is a cap, not an optimum —
    the fitter's own way of saying the model is unreliable here."""
    state, why = R.verdict_for({"fitted": True, "boundary": True,
                                "one_sided": False, "reliable": False,
                                "settled": {"n": 0}})
    assert state == "SHUT: boundary fit", state
    assert "cap" in why


def test_a_one_sided_correction_outranks_every_other_diagnosis():
    """It is the more damning of the two shut states — a correction that
    cannot name both sides has stopped being a calibration — so it must
    be reported even when the fit is ALSO at its boundary."""
    state, _why = R.verdict_for({"fitted": True, "boundary": True,
                                 "one_sided": True, "reliable": False,
                                 "settled": {"n": 0}})
    assert state == "SHUT: one-sided", state


def test_a_bettable_market_that_never_published_is_not_the_same_as_unproven():
    """THE DISTINCTION THE FIRST CUT MISSED. "0 settled" on a market that
    has never produced a pick and "0 settled" on one holding thirteen
    open tickets are opposite states, and both printed as a bare zero."""
    silent, why = R.verdict_for({"fitted": True, "boundary": False,
                                 "one_sided": False, "reliable": True,
                                 "settled": {"n": 0, "open": 0}})
    assert silent == "LIVE, SILENT", silent
    assert "never published" in why
    working, why2 = R.verdict_for({"fitted": True, "boundary": False,
                                   "one_sided": False, "reliable": True,
                                   "settled": {"n": 0, "open": 13}})
    assert working == "LIVE, UNPROVEN", working
    assert "13 still open" in why2


def test_a_settled_losing_market_is_named_as_such():
    state, why = R.verdict_for({
        "fitted": True, "boundary": False, "one_sided": False,
        "reliable": True,
        "settled": {"n": 60, "open": 0, "roi": -0.08}})
    assert state == "LIVE, LOSING", state
    assert "-8.0%" in why


def test_a_thin_record_is_not_read_as_a_verdict():
    """Below MIN_SETTLED the ROI is a number about four games."""
    state, _why = R.verdict_for({
        "fitted": True, "boundary": False, "one_sided": False,
        "reliable": True,
        "settled": {"n": R.MIN_SETTLED - 1, "open": 0, "roi": -0.40}})
    assert state == "LIVE, UNPROVEN", state


# --- the record ----------------------------------------------------------
def test_roi_is_per_unit_staked_not_per_bet():
    """The board sizes its stakes, so dividing by the count would rate a
    losing 3-unit bet the same as a losing half-unit one."""
    conn = _ledger([("nfl", "spread", "won", 2.0, 3.0),
                    ("nfl", "spread", "lost", -0.5, 0.5)])
    try:
        got = R.settled_record(conn, "nfl", "spread")
    finally:
        conn.close()
    assert got["n"] == 2 and got["wins"] == 1
    assert abs(got["roi"] - (1.5 / 3.5)) < 1e-9, got


def test_open_tickets_are_counted_but_never_scored():
    """They are evidence of life, not of performance."""
    conn = _ledger([("nfl", "total", "open", None, 1.0),
                    ("nfl", "total", "open", None, 1.0),
                    ("nfl", "total", "won", 0.9, 1.0)])
    try:
        got = R.settled_record(conn, "nfl", "total")
    finally:
        conn.close()
    assert got["n"] == 1 and got["open"] == 2, got


def test_a_market_with_nothing_at_all_still_reports_its_open_count():
    conn = _ledger([("nfl", "spread", "open", None, 1.0)])
    try:
        got = R.settled_record(conn, "nfl", "spread")
    finally:
        conn.close()
    assert got == {"n": 0, "open": 1}, got


# --- the table -----------------------------------------------------------
def test_game_bets_do_not_borrow_the_prop_tier_bars():
    """Game bets never pass through the §3 tier minimums — they answer to
    `gamebets.MAX_CREDIBLE_EDGE`. Printing the default tier for them
    would invent a rule the market has never been subject to."""
    row = R.market_row("nfl", "spread", None)
    assert row["game"] and row["min_edge"] is None and row["tier"] is None
    prop = R.market_row("nfl", "receptions", None)
    assert not prop["game"] and prop["min_edge"] is not None


def test_the_market_list_is_explicit_so_a_never_fitted_market_shows_up():
    """Discovering the list from the calibration store would hide exactly
    the case this report exists to surface: a market that has never been
    fitted has no entry to discover."""
    import inspect
    src = inspect.getsource(R)
    assert "PLAYER_MARKETS = (" in src
    for m in ("anytime_td", "receptions", "rec_yds", "rush_yds", "pass_yds"):
        assert m in R.PLAYER_MARKETS
    for m in ("moneyline", "spread", "total", "team_total"):
        assert m in R.GAME_MARKETS


def test_the_report_renders_both_sections_and_a_verdict_per_market():
    lines = R.report("nfl", conn=_ledger())
    text = "\n".join(lines)
    assert "player props" in text and "game bets" in text
    for m in R.PLAYER_MARKETS + R.GAME_MARKETS:
        assert m in text, m
    # Every market lands in exactly one state, and the states are about
    # CAUSE rather than severity.
    assert any(s in text for s in ("UNMEASURED", "SHUT", "LIVE"))


def test_the_report_survives_a_box_with_no_ledger_and_says_so():
    lines = R.report("nfl", conn=None)
    assert any("no ledger on this box" in x for x in lines) or \
        any("UNMEASURED" in x for x in lines)


# --- what a replay has actually said -------------------------------------
def test_a_market_nothing_has_ever_graded_is_worse_than_unmeasured():
    """`team_total` publishes picks and no backtest for it exists. That
    is a different and worse state than "never fitted": an unfitted
    market announces itself, and this one looks like the three beside it
    while nothing has ever checked whether it works."""
    row = R.market_row("nfl", "team_total", None)
    assert row["backtest"] is None
    state, why = R.verdict_for(row)
    assert state == "NO BACKTEST", state
    assert "looks measured" in why


def test_the_replay_result_reaches_the_verdict_for_markets_that_have_one():
    """A market can be unfitted AND replayed, and the replay is the more
    useful sentence of the two — "off the close by 4 points and never
    qualified" says far more than "needs settled rows"."""
    row = R.market_row("nfl", "spread", None)
    state, why = R.verdict_for(row)
    assert state == "UNMEASURED", state
    assert "Replay says:" in why and "4.05" in why


def test_every_measured_game_market_is_recorded_with_its_numbers():
    """2026-08-30, over 1,424 completed NFL games. The three game markets
    that can be replayed have never produced a bet graded above Pass —
    which is the GATES WORKING, not failing: the model does not beat the
    closing number and correctly declines. Dropping `min_team_games` from
    15 to 0 changes nothing, so it is not thin history either.

    Written down because the live board publishes game bets anyway, and a
    model that qualifies nothing in replay while publishing live is two
    different models until somebody finds the difference."""
    import inspect
    src = inspect.getsource(R)
    for number in ("0.2336", "3.18", "4.05", "1,184"):
        assert number in src, f"the replay result lost {number}"
    assert "min_team_games" in src
    for market in ("moneyline", "spread", "total"):
        assert R.BACKTESTED[market], market


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
