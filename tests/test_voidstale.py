"""Voiding bets the shipping model could not have placed, and the last
game market to get a replay at all.

Ethan, 2026-08-30: "i would say void them, we should only be tracking new
nfl bets that created by the new models we are currently working on."

Twelve NFL game bets sat open from August 8-12 with 7.64 units staked
while `gamebacktest` graded none at all over 1,184 games. They were
priced on the 0.5 market-haircut guess, before `engine.gamecal` had
measured one — and they are identifiable by arithmetic rather than by
date, which is what makes voiding them safe.

Run directly: `python3 tests/test_voidstale.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger as L                              # noqa: E402
from engine.gamebets import MAX_CREDIBLE_EDGE               # noqa: E402


def _ledger(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport TEXT, "
                 "market TEXT, ts TEXT, edge REAL, stake_units REAL, "
                 "grade TEXT, status TEXT, pnl_units REAL, pnl_dollars REAL, "
                 "why_note TEXT)")
    conn.executemany(
        "INSERT INTO bets (sport, market, ts, edge, stake_units, grade, "
        "status) VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


MEASURED = {("nfl", "total"): 0.0296, ("nfl", "spread"): 0.0063,
            ("nfl", "moneyline"): 0.0}


def _patch(monkey):
    from engine import gamecal
    old = gamecal.shrink_for
    gamecal.shrink_for = monkey
    return old


# --- which rows, and why they are identifiable ---------------------------
def test_an_edge_above_the_measured_ceiling_could_not_have_been_priced_today():
    """THE ARITHMETIC THAT MAKES THIS SAFE. `temper` shrinks toward the
    close and the credibility ceiling refuses any raw disagreement over
    MAX_CREDIBLE_EDGE first, so the largest edge that can survive is 0.10
    x shrink. At every measured value that caps a game edge at 0.003 to
    0.009; only the 0.5 fallback reaches 0.05.

    So this reads the EDGE, not the date. A row is voided because the
    model that ships could not produce it — which stays true however the
    timestamps look."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "total", "2026-08-08T13:40:03", 0.0472, 1.0, "Play", "open"),
        ("nfl", "spread", "2026-08-08T13:40:03", 0.0344, 0.79, "Play", "open"),
        # Inside the measured ceiling: this one the model could place.
        ("nfl", "total", "2026-08-29T10:00:00", 0.0020, 0.5, "Play", "open"),
    ])
    old = _patch(lambda s, m: MEASURED.get((s, m)))
    try:
        hit = L.void_unmeasured_game_bets(conn, "nfl", dry_run=True)
    finally:
        gamecal.shrink_for = old
        conn.close()
    assert len(hit) == 2, hit
    assert all(h["edge"] > h["ceiling"] for h in hit)
    assert MAX_CREDIBLE_EDGE * 0.0296 < 0.0472


def test_a_team_total_is_judged_by_the_totals_haircut():
    """`price_team_total` passes market="total" to `temper`, so asking
    gamecal for a "team_total" key returns None. Skipping on that would
    have left three of the twelve standing while their nine siblings were
    voided."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "team_total", "2026-08-11T12:10:27", 0.0348, 0.58, "Play",
         "open"),
    ])
    old = _patch(lambda s, m: MEASURED.get((s, m)))
    try:
        hit = L.void_unmeasured_game_bets(conn, "nfl", dry_run=True)
    finally:
        gamecal.shrink_for = old
        conn.close()
    assert len(hit) == 1 and hit[0]["market"] == "team_total", hit


def test_a_market_still_unmeasured_is_left_alone():
    """Its rows are not evidence of a SUPERSEDED calibration — the
    fallback is still what prices them, so voiding them would be voiding
    the model's current output."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "total", "2026-08-08T00:00:00", 0.0472, 1.0, "Play", "open"),
    ])
    old = _patch(lambda s, m: None)
    try:
        assert L.void_unmeasured_game_bets(conn, "nfl", dry_run=True) == []
    finally:
        gamecal.shrink_for = old
        conn.close()


def test_settled_rows_are_never_touched():
    """History that already paid out is history. Only OPEN positions."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "total", "2026-08-08T00:00:00", 0.0472, 1.0, "Play", "won"),
        ("nfl", "spread", "2026-08-08T00:00:00", 0.0344, 1.0, "Play", "lost"),
        ("nfl", "total", "2026-08-08T00:00:00", 0.0489, 1.0, "Play", "void"),
    ])
    old = _patch(lambda s, m: MEASURED.get((s, m)))
    try:
        assert L.void_unmeasured_game_bets(conn, "nfl", dry_run=True) == []
    finally:
        gamecal.shrink_for = old
        conn.close()


# --- what voiding actually does ------------------------------------------
def test_the_row_survives_with_a_reason_rather_than_disappearing():
    """VOIDED, NOT DELETED. A record that loses its own history is worse
    than one carrying an explained mistake, and the next person to wonder
    why NFL game bets start in September deserves the answer."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "total", "2026-08-08T13:40:03", 0.0472, 1.0, "Play", "open"),
    ])
    old = _patch(lambda s, m: MEASURED.get((s, m)))
    try:
        L.void_unmeasured_game_bets(conn, "nfl", dry_run=False)
        row = conn.execute("SELECT status, pnl_units, why_note FROM bets"
                           ).fetchone()
    finally:
        gamecal.shrink_for = old
    assert row["status"] == "void"
    assert row["pnl_units"] == 0
    assert "0.5 market-haircut guess" in (row["why_note"] or "")
    conn.close()


def test_a_dry_run_changes_nothing():
    """The default, because this spends somebody's record."""
    from engine import gamecal
    conn = _ledger([
        ("nfl", "total", "2026-08-08T13:40:03", 0.0472, 1.0, "Play", "open"),
    ])
    old = _patch(lambda s, m: MEASURED.get((s, m)))
    try:
        L.void_unmeasured_game_bets(conn, "nfl")
        assert conn.execute("SELECT status FROM bets").fetchone()[0] == "open"
    finally:
        gamecal.shrink_for = old
        conn.close()
    import inspect
    assert "dry_run: bool = True" in inspect.getsource(
        L.void_unmeasured_game_bets)


# --- the last market to be replayed at all -------------------------------
def test_team_totals_now_have_a_backtest():
    """It reached the live board, the journal and the Record with no
    replay of any kind — worse than unmeasured, because it sat beside
    three markets that had one and looked identical."""
    from engine import gamebacktest as G
    assert hasattr(G, "backtest_team_totals")
    src = G.backtest_team_totals.__doc__ or ""
    assert "derived" in src.lower() or "SPLIT" in src


def test_the_team_total_line_is_split_the_way_the_board_splits_it():
    """A book posts a game total and a spread; the board halves them into
    two team numbers, and the replay has to do the same arithmetic or it
    grades a bet nobody made."""
    import inspect
    from engine import gamebacktest as G, pipeline
    replay = inspect.getsource(G.backtest_team_totals)
    live = inspect.getsource(pipeline._game_bets)
    assert "(total_line - spread_line) / 2.0" in replay
    assert "(g.total - g.spread) / 2" in live


def test_a_team_total_settles_on_that_team_s_own_points():
    won, push = G_settle(23.5, "Over", 27.0)
    assert won and not push
    won, push = G_settle(23.5, "Over", 20.0)
    assert not won and not push
    won, push = G_settle(24.0, "Under", 24.0)
    assert push
    won, push = G_settle(23.5, "Under", 20.0)
    assert won and not push


def G_settle(line, side, points):
    from engine.gamebacktest import _settle_team_total
    return _settle_team_total(line, side, points)


def test_the_readiness_table_stops_calling_it_ungraded():
    from engine import nflready as R
    assert R.BACKTESTED["team_total"], "it has a replay now"
    row = R.market_row("nfl", "team_total", None, lookup=lambda s, m: 0.03)
    assert R.verdict_for(row)[0] != "NO BACKTEST"


def test_the_cli_defaults_to_a_dry_run():
    """It spends somebody's record, so the destructive form has to be
    typed out. `--void-dry-run` reports, `--void` applies."""
    import inspect
    from engine import nflready as R
    src = inspect.getsource(R.main)
    assert '"--void" in args' in src
    assert 'apply = "--void" in args' in src
    body = inspect.getsource(R.void_stale)
    assert "dry_run=not apply" in body
    assert "rather than being deleted" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
