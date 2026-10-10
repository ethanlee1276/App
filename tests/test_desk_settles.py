"""Open desk tickets grade against the exchange, on a clock.

Ethan, 2026-09-14: 103 prediction-market tickets open on the Record page,
the oldest from August. `resolve_predmarket` graded from a {ticker:
result} map and nothing in production ever built one.

Run directly: `python3 tests/test_desk_settles.py`
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                      # noqa: E402

TODAY = "2026-09-15"


def _world():
    L = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    return L


def _ticket(L, ticker, side="YES", line=41.0, date="2026-08-16"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, 'mlb', ?, ?, ?, 'kalshi_ml', ?, ?, -110, 0.1, 0, 'open', 'predmarket')",
        (f"{date}T12:00:00", date, ledger.predmarket_event_date(ticker) or date,
         ticker, side, line))
    L.commit()


def _status(L, ticker):
    r = L.execute("SELECT status, why_note, pnl_units FROM bets WHERE player=?",
                  (ticker,)).fetchone()
    return r[0], r[1], r[2]


def test_finalised_tickets_grade_and_cancelled_ones_void():
    L = _world()
    _ticket(L, "KXMLBGAME-26AUG16NYY-YES", "YES", 41.0)      # won at 41c
    _ticket(L, "KXMLBGAME-26AUG16BOS-NO", "NO", 60.0)        # NO bought, YES result: lost
    _ticket(L, "KXMLBGAME-26AUG16LAD-YES", "YES", 55.0)      # cancelled
    _ticket(L, "KXMLBGAME-26AUG16SEA-YES", "YES", 50.0)      # closed, not yet settled
    asked = []

    def fetch(tickers):
        asked.append(list(tickers))
        return [{"ticker": "KXMLBGAME-26AUG16NYY-YES", "status": "finalized", "result": "yes"},
                {"ticker": "KXMLBGAME-26AUG16BOS-NO", "status": "settled", "result": "yes"},
                {"ticker": "KXMLBGAME-26AUG16LAD-YES", "status": "cancelled", "result": ""},
                {"ticker": "KXMLBGAME-26AUG16SEA-YES", "status": "closed", "result": ""}]
    out = ledger.settle_predmarket(L, fetch=fetch, today=TODAY)
    assert out == {"checked": 4, "settled": 2, "voided": 1, "error": ""}, out
    assert asked == [sorted(["KXMLBGAME-26AUG16NYY-YES", "KXMLBGAME-26AUG16BOS-NO",
                             "KXMLBGAME-26AUG16LAD-YES", "KXMLBGAME-26AUG16SEA-YES"])]
    won = _status(L, "KXMLBGAME-26AUG16NYY-YES")
    assert won[0] == "won" and abs(won[2] - round(0.1 * 0.59 / 0.41, 4)) < 1e-6, won
    assert _status(L, "KXMLBGAME-26AUG16BOS-NO")[0] == "lost"
    cancelled = _status(L, "KXMLBGAME-26AUG16LAD-YES")
    assert cancelled[0] == "void" and "cancelled" in cancelled[1]
    assert _status(L, "KXMLBGAME-26AUG16SEA-YES")[0] == "open", "closed is not settled"


def test_a_contract_the_exchange_no_longer_lists_voids_only_when_long_past():
    L = _world()
    _ticket(L, "KXMLBGAME-26AUG16NYY-YES")                    # a month past
    _ticket(L, "KXMLBGAME-26SEP13KC-YES", date="2026-09-13")  # two days past
    out = ledger.settle_predmarket(L, fetch=lambda t: [], today=TODAY)
    assert out["checked"] == 2 and out["voided"] == 1, out
    old = _status(L, "KXMLBGAME-26AUG16NYY-YES")
    assert old[0] == "void" and "no longer lists" in old[1], old
    assert _status(L, "KXMLBGAME-26SEP13KC-YES")[0] == "open"


def test_a_dropped_batch_is_not_a_delisted_contract():
    """The batch pull keeps going when one batch fails, so a ticker the
    first pull did not return is asked about again on its own. Only a
    pull that answers and still omits it voids; a pull that raises, or
    one that turns out to list it after all, voids nothing."""
    L = _world()
    _ticket(L, "KXMLBGAME-26AUG16NYY-YES")
    calls = []

    def flaky(tickers):
        calls.append(list(tickers))
        if len(calls) == 1:
            return []                              # the batch that dropped it
        raise OSError("second pull failed")
    out = ledger.settle_predmarket(L, fetch=flaky, today=TODAY)
    assert len(calls) == 2 and out["voided"] == 0 and "second pull" in out["error"], (calls, out)
    assert _status(L, "KXMLBGAME-26AUG16NYY-YES")[0] == "open"
    # Listed on the second look (closed, awaiting settlement): still open.
    calls.clear()

    def relists(tickers):
        calls.append(list(tickers))
        return [] if len(calls) == 1 else [
            {"ticker": "KXMLBGAME-26AUG16NYY-YES", "status": "closed", "result": ""}]
    out = ledger.settle_predmarket(L, fetch=relists, today=TODAY)
    assert out["voided"] == 0 and _status(L, "KXMLBGAME-26AUG16NYY-YES")[0] == "open"


def test_a_future_event_is_not_asked_about_and_a_failed_fetch_changes_nothing():
    L = _world()
    _ticket(L, "KXNFLGAME-26SEP20KC-YES", date="2026-09-10")  # event in the future
    _ticket(L, "KXMLBGAME-26AUG16NYY-YES")
    asked = []

    def boom(tickers):
        asked.append(list(tickers))
        raise OSError("exchange down")
    out = ledger.settle_predmarket(L, fetch=boom, today=TODAY)
    assert asked == [["KXMLBGAME-26AUG16NYY-YES"]], asked
    assert out["settled"] == 0 and out["voided"] == 0 and "exchange down" in out["error"]
    assert _status(L, "KXMLBGAME-26AUG16NYY-YES")[0] == "open"
    assert ledger.settle_predmarket(_world(), fetch=boom, today=TODAY)["checked"] == 0


def test_the_intraday_pass_asks_the_exchange_hourly():
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine", "maintenance.py"),
               encoding="utf-8").read()
    body = src[src.index("def settle_open("):]
    assert "ledger.settle_predmarket(lconn)" in body
    assert 'state.get("last_desk_ts")' in body and "DESK_EVERY_S" in body
    assert body.index("settle_from_history(lconn, hconn)") < body.index("settle_predmarket(lconn)")
    from engine import maintenance
    assert maintenance.DESK_EVERY_S == 3600


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
