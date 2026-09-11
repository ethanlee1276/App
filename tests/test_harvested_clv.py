"""CLV on props ran on free snapshots while the paid closes went unread.

`odds_history` on the droplet, 2026-08-27:

    mlb moneyline 157,488   nfl moneyline 131,840   mlb spread 103,252
    mlb total     103,246   nfl spread     65,920   nfl total    65,920
    mlb total_bases 48,007  mlb hits       15,990

Sixty-four thousand purchased MLB prop closes. And every settled prop bet
in the journal carried no closing price at all, because both places that
write one — the settle path and `repair_closing_odds` — read only
`_snapshot_close_odds`, our own free live pulls. The settle path had the
harvested row in its hand: it took the LINE off it and dropped the PRICE
on the floor.

That matters more than a missing column. CLV is the instrument that
decides whether a model is allowed to keep betting, and on a fixed-line
market (a home run, a touchdown, quoted 0.5 every night) the line cannot
move — the price is the only thing that carries the signal. No price, no
measurement, on exactly the markets where it is the whole measurement.

Both paths now go through `_close_odds_from`, and these tests hold it to
the two rules the snapshot store learned the hard way: the SIDE matters,
and the LINE is part of the key.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger
from engine.sources.oddsapi import normalize_name

F = ledger._close_odds_from


# --- the shared rule ---------------------------------------------------------
def test_the_bets_own_side_is_the_price_it_gets():
    close = {"line": 4.5, "over_odds": -115, "under_odds": -105}
    assert F(close, 4.5, "OVER") == -115
    assert F(close, 4.5, "UNDER") == -105


def test_a_missing_side_defaults_to_the_over_like_the_rest_of_the_ledger():
    close = {"line": 4.5, "over_odds": -115, "under_odds": -105}
    assert F(close, 4.5, None) == -115
    assert F(close, 4.5, "") == -115


def test_a_close_at_another_line_is_a_different_bet_and_yields_nothing():
    """`linemoves.closing_odds_by_date` measured what ignoring this costs:
    an 18-point inversion, concentrated on the bets whose line moved most
    — which is precisely where the information is."""
    close = {"line": 3.5, "over_odds": -115, "under_odds": -105}
    assert F(close, 4.5, "OVER") is None


def test_zero_means_not_quoted_and_never_a_price_of_zero():
    """Many props are Over-only. Reading the absent under as a number is
    how a phantom edge lands on a bet nobody could have placed."""
    close = {"line": 0.5, "over_odds": 550, "under_odds": 0}
    assert F(close, 0.5, "UNDER") is None
    assert F(close, 0.5, "OVER") == 550


def test_an_illegal_american_price_is_refused_on_both_paths():
    """`repair_closing_odds` already applied this floor to the snapshot
    store. It is a rule about PRICES, so it holds wherever one came from."""
    assert F({"line": 1.5, "over_odds": 40}, 1.5, "OVER") is None
    assert F({"line": 1.5, "over_odds": -99}, 1.5, "OVER") is None
    assert F({"line": 1.5, "over_odds": 100}, 1.5, "OVER") == 100


def test_no_harvested_row_is_not_an_error():
    assert F(None, 4.5, "OVER") is None
    assert F({}, 4.5, "OVER") is None


def test_a_bet_with_no_line_takes_the_price_it_finds():
    """A moneyline-shaped prop has no number to compare, and refusing
    every one of them would be the line rule eating its own purpose."""
    assert F({"line": None, "over_odds": -140}, None, "OVER") == -140


def test_junk_in_the_line_column_returns_nothing_rather_than_raising():
    assert F({"line": "n/a", "over_odds": -110}, 4.5, "OVER") is None
    assert F({"line": 4.5, "over_odds": "n/a"}, 4.5, "OVER") is None


# --- the backfill ------------------------------------------------------------
def _fixture():
    tmp = tempfile.mkdtemp()
    hist = db.connect(os.path.join(tmp, "h.db"))
    ledger.DEFAULT_DB = os.path.join(tmp, "l.db")
    return hist, ledger.connect()


def _price(hist, player, market="hits", line=1.5, over=155, under=-190,
           sport="mlb", date="2025-08-01"):
    db.upsert_odds_history(hist, [{
        "sport": sport, "taken_at": f"{date}T23:00:00Z", "event_id": "e1",
        "home": "A", "away": "B", "player": normalize_name(player),
        "market": market, "book": "dk", "line": line,
        "over_odds": over, "under_odds": under}])


def _journal(led, player, side="OVER", line=1.5, odds=150, status="won",
             market="hits", sport="mlb", date="2025-08-01", category="main"):
    led.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,status,"
        "stake_units,category) VALUES (?,?,?,?,?,?,?,?,1.0,?)",
        (sport, date, player, market, side, line, odds, status, category))
    led.commit()


def test_the_backfill_fills_a_settled_bet_from_a_purchased_close():
    saved = ledger.DEFAULT_DB
    try:
        hist, led = _fixture()
        _price(hist, "Aaron Judge")
        _journal(led, "Aaron Judge")
        r = ledger.repair_closing_odds(led, apply=True, hist_conn=hist)
        assert r["filled"] == 1 and r["cleared"] == 0
        got = led.execute("SELECT closing_odds FROM bets").fetchone()[0]
        assert int(got) == 155
    finally:
        ledger.DEFAULT_DB = saved


def test_the_backfill_gives_each_side_its_own_close():
    saved = ledger.DEFAULT_DB
    try:
        hist, led = _fixture()
        _price(hist, "Aaron Judge")
        _journal(led, "Aaron Judge", side="OVER", category="a")
        _journal(led, "Aaron Judge", side="UNDER", odds=-180, status="lost",
                 category="b")
        ledger.repair_closing_odds(led, apply=True, hist_conn=hist)
        got = {r["side"]: int(r["closing_odds"]) for r in
               led.execute("SELECT side, closing_odds FROM bets")}
        assert got == {"OVER": 155, "UNDER": -190}
    finally:
        ledger.DEFAULT_DB = saved


def test_the_backfill_will_not_bank_a_close_from_a_different_line():
    saved = ledger.DEFAULT_DB
    try:
        hist, led = _fixture()
        _price(hist, "Juan Soto", line=1.5)
        _journal(led, "Juan Soto", line=2.5)
        ledger.repair_closing_odds(led, apply=True, hist_conn=hist)
        assert led.execute(
            "SELECT closing_odds FROM bets").fetchone()[0] is None
    finally:
        ledger.DEFAULT_DB = saved


def test_the_name_is_normalised_on_both_sides_of_the_join():
    """The harvest stores 'ronald acuna'; the journal keeps 'Ronald Acuña
    Jr.'. Without folding, every accented name silently fails to join —
    which is a paid-for price that never reaches a bet."""
    saved = ledger.DEFAULT_DB
    try:
        hist, led = _fixture()
        _price(hist, "Ronald Acuña Jr.")
        _journal(led, "Ronald Acuña Jr.")
        ledger.repair_closing_odds(led, apply=True, hist_conn=hist)
        assert int(led.execute(
            "SELECT closing_odds FROM bets").fetchone()[0]) == 155
    finally:
        ledger.DEFAULT_DB = saved


def test_a_market_with_no_harvest_still_falls_through_to_the_snapshots():
    """The free source is a FALLBACK now, not a replacement. Nothing that
    worked before this change may stop working because of it."""
    import inspect
    src = inspect.getsource(ledger.repair_closing_odds)
    assert "_snapshot_close_odds" in src or "snaps" in src
    assert "if want is None:" in src, \
        "the snapshot lookup must run when the harvest has nothing"


def test_the_settle_path_and_the_backfill_share_one_rule():
    """Two copies of the side/line logic is how the first inversion
    survived a fix — it was corrected in one place and not the other."""
    import inspect
    settle = inspect.getsource(ledger.settle_from_history)
    repair = inspect.getsource(ledger.repair_closing_odds)
    assert "_close_odds_from(" in settle
    assert "_close_odds_from(" in repair


def test_the_harvest_reader_survives_a_database_with_no_odds_at_all():
    hist = db.connect(":memory:")
    assert ledger._harvested_closes(hist) == {}


def test_the_harvest_reader_indexes_by_sport_and_market():
    hist = db.connect(":memory:")
    _price(hist, "Aaron Judge", market="hits")
    _price(hist, "Aaron Judge", market="total_bases", line=1.5)
    got = ledger._harvested_closes(hist)
    assert set(got) == {("mlb", "hits"), ("mlb", "total_bases")}
    assert ("aaron judge", "2025-08-01") in got[("mlb", "hits")]


# --- the settle path, end to end ---------------------------------------------
def _settle_fixture(bet_line, close_line, side="UNDER"):
    """One journaled prop, one ingested result, one harvested close."""
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": "2026-07-24",
        "recommendations": [
            {"player": "Aaron Judge", "market": "total_bases", "side": side,
             "line": bet_line, "book": "FanDuel", "odds": -120,
             "projection": 1.4, "hit_prob": 0.6, "edge": 0.08,
             "confidence": 7.5, "grade": "Play", "stake_units": 1.0,
             "recommended": True}]})
    hist = db.connect(":memory:")
    db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "g", "player": "Aaron Judge", "team": "NYY",
         "opponent": "BOS", "position": "RF", "home": 1,
         "market": "total_bases", "value": 1.0}])
    db.upsert_odds_history(hist, [
        {"sport": "mlb", "taken_at": "2026-07-24T23:00:00Z", "event_id": "e",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "total_bases", "book": "DK", "line": close_line,
         "over_odds": -105, "under_odds": -135}])
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    return conn.execute(
        "SELECT * FROM bets WHERE player='Aaron Judge'").fetchone()


def test_settling_banks_the_purchased_closing_price():
    """The whole finding, end to end: the settle path had this row in hand,
    read its line and threw its price away."""
    b = _settle_fixture(bet_line=2.5, close_line=2.5)
    assert b["closing_line"] == 2.5
    assert int(b["closing_odds"]) == -135, \
        "the UNDER bet must bank the UNDER's harvested close"


def test_settling_banks_the_over_price_for_an_over_bet():
    b = _settle_fixture(bet_line=2.5, close_line=2.5, side="OVER")
    assert int(b["closing_odds"]) == -105


def test_settling_refuses_a_price_quoted_at_another_line():
    """The close is real and it is not this bet's close. No number beats a
    wrong one — `_bet_price_clv` cannot tell them apart."""
    b = _settle_fixture(bet_line=2.5, close_line=2.0)
    assert b["closing_line"] == 2.0        # the LINE still joins, as before
    assert b["closing_odds"] is None


def test_the_launcher_hands_the_repair_a_history_connection():
    """`_harvested_closes` will not go looking for a database, so the one
    production caller has to pass one — otherwise the fix is inert on the
    command Ethan actually runs."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "launch.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "repair_closing_odds(conn, apply=apply," in src
    assert "hist_conn=hist_db.connect()" in src


def test_the_repair_refuses_to_open_a_database_of_its_own():
    """The suite must not read the box it runs on. Three doors are
    sandboxed by `run_tests.py`; the history DB is a fourth and still
    open, so this path must never be the one that walks through it."""
    import inspect
    src = inspect.getsource(ledger._harvested_closes)
    assert "if hist_conn is None:" in src
    assert "_hist_db.connect()" not in src
    assert ledger._harvested_closes(None) == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
