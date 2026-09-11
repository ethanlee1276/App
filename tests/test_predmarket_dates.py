"""130 healthy Kalshi contracts in the doctor's stuck list, and a nightly
sweep walking twelve dead days to find nothing on each.

Ethan's droplet, 2026-08-23. `doctor.py` reported "⚠️ 130 stuck bets", and
`--stuck` showed all 130 were `kalshi_ml` contracts with tickers like
KXNFLGAME-26SEP13DALNYG-DA — September football, journaled in August, for
games that had not been played. Then `--settle all` swept thirteen days
and printed `results: 0 game(s), 0 player log rows` on twelve of them.

Two wrong assumptions, both about the same column:

  * `log_predmarket` stores the day the DESK recommended a contract,
    because the bets table has one date column. For every other bucket
    that IS the slate date. For a prediction market it is a month early,
    so `why_open` aged them from the wrong end and called them overdue.
  * a Kalshi row grades against the exchange's own settlements
    (`resolve_predmarket`), never against ingested game results — so the
    history lookups `why_open` runs can only ever come back empty, and
    "no results ingested" pointed at an ingest that could not have helped.

And one plain bug found on the way: the settlement pull sent only the
first forty open tickers, so with 130 open the other ninety could not
settle no matter what the exchange did.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger
from engine.sources import kalshi as kx

TODAY = "2026-08-23"
JOURNALED = "2026-08-11"


def _journal():
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    return lconn, db.connect(":memory:")


def _pm(lconn, ticker, date=JOURNALED, desk="kalshi_ml"):
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,book,odds,"
        "grade,stake_units,stake_dollars,status,category) VALUES "
        "('kalshi',?,?,?,'YES',52.0,'kalshi',-108,'Desk',0.1,0.0,'open',"
        "'predmarket')", (date, ticker, desk))
    lconn.commit()


def test_event_date_is_read_off_the_ticker():
    assert ledger.predmarket_event_date(
        "KXNFLGAME-26SEP13DALNYG-DA") == "2026-09-13"
    assert ledger.predmarket_event_date("KXHIGHNY-26AUG23-B85") == "2026-08-23"


def test_undated_tickers_say_so_rather_than_guessing():
    # None means UNKNOWN, and every caller has to treat it as unknown.
    # Returning a plausible date here would hide a genuinely stranded row.
    for bad in (None, "", "GARBAGE", "KXNFLGAME-26FEB30XX-DA",
                "KXNFLGAME-26XXX13DAL-DA"):
        assert ledger.predmarket_event_date(bad) is None


def test_a_contract_whose_game_has_not_been_played_is_not_stuck():
    """The 130. Journaled twelve days ago, event three weeks out."""
    lconn, hconn = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")
    assert ledger.why_open(lconn, hconn, TODAY) == []


def test_a_contract_past_its_event_waits_on_the_exchange_not_the_ingest():
    lconn, hconn = _journal()
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")
    rows = ledger.why_open(lconn, hconn, TODAY)
    assert len(rows) == 1
    r = rows[0]
    assert r["reason"] == "waiting on the exchange"
    # Aged from the EVENT, not from the journal entry.
    assert r["age_days"] == 9
    assert r["event_date"] == "2026-08-14"


def test_the_ingest_is_never_blamed_for_a_kalshi_contract():
    """The old diagnosis, and why it was worse than useless: it named a
    command (`ingest.py`) that cannot close one of these rows."""
    lconn, hconn = _journal()
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")
    _pm(lconn, "KXNFLGAME-26AUG15DALNYG-DA")
    reasons = {r["reason"] for r in ledger.why_open(lconn, hconn, TODAY)}
    assert "no results ingested" not in reasons
    assert "game not found" not in reasons


def test_an_undated_contract_still_shows_up():
    lconn, hconn = _journal()
    _pm(lconn, "SOMETHING-WITH-NO-DATE")
    rows = ledger.why_open(lconn, hconn, TODAY)
    assert len(rows) == 1
    assert rows[0]["reason"] == "contract has no dated ticker"


def test_ordinary_bets_are_judged_exactly_as_before():
    """The predmarket branch must not swallow the buckets it sits beside."""
    lconn, hconn = _journal()
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES "
        "('mlb','2026-08-01','Nobody','hits','OVER',1.5,-110,'A',1.0,10.0,"
        "'open','main')")
    lconn.commit()
    rows = ledger.why_open(lconn, hconn, TODAY)
    assert len(rows) == 1 and rows[0]["reason"] == "no results ingested"


def test_a_week_label_is_never_read_as_a_calendar_date():
    """fromisoformat("2026-W1") succeeds on Python >= 3.11 and returns a
    day in the PREVIOUS December. Football has already been aged 215 days
    into the past by that once; a contract journaled under a week label
    must not repeat it."""
    lconn, hconn = _journal()
    _pm(lconn, "SOMETHING-WITH-NO-DATE", date="2026-W1")
    rows = ledger.why_open(lconn, hconn, TODAY)
    assert len(rows) == 1
    assert rows[0]["reason"] == "contract has no dated ticker"
    assert rows[0]["age_days"] == ledger.STUCK_AFTER_DAYS   # not 237


# --- the sweep ------------------------------------------------------------

def test_a_kalshi_only_day_is_never_swept_by_date():
    """`--settle all` re-walking twelve days, nightly, forever.

    A per-date pass ingests that date's results and grades against them.
    No amount of that can settle a contract the exchange settles, so the
    day must not be in the sweep list at all — however old it is."""
    import launch
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")
    days = ledger.open_by_day(lconn, TODAY)
    assert [d["date"] for d in days] == [JOURNALED]
    assert days[0]["gradeable_by_date"] is False
    assert launch._settleable_days(days) == []


def test_a_day_with_a_real_pick_on_it_is_still_swept():
    import launch
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES "
        "('mlb',?,'Nobody','hits','OVER',1.5,-110,'A',1.0,10.0,'open',"
        "'main')", (JOURNALED,))
    lconn.commit()
    days = ledger.open_by_day(lconn, TODAY)
    assert days[0]["gradeable_by_date"] is True
    assert launch._settleable_days(days) == [JOURNALED]


def test_a_future_contract_does_not_make_its_journal_day_stale():
    """`stale` drives the "N finished days still have picks open" warning
    and the doctor's advice. A day is only over for a contract whose
    EVENT is over."""
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")
    assert ledger.open_by_day(lconn, TODAY)[0]["stale"] is False


def test_a_settled_event_still_open_does_make_its_day_stale():
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")
    assert ledger.open_by_day(lconn, TODAY)[0]["stale"] is True


def test_counts_still_carry_every_open_pick():
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")
    _pm(lconn, "KXHIGHNY-26SEP13-B85", desk="kalshi_wx")
    day = ledger.open_by_day(lconn, TODAY)[0]
    assert day["total"] == 2 and day["counts"]["predmarket"] == 2


def test_settleable_days_tolerates_a_caller_built_dict():
    import launch
    assert launch._settleable_days(
        [{"date": "2026-08-01"}, {"date": "2026-W1"}]) == ["2026-08-01"]


# --- --why-open -----------------------------------------------------------

def test_why_open_puts_contracts_in_their_own_bucket():
    """The same misdiagnosis wearing a different tool's clothes: sent
    through the settler's history lookups, 130 healthy contracts came out
    as NO_RESULTS, and the printed advice was "check the feeds"."""
    lconn, hconn = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")
    rep = ledger.explain_open(lconn, hconn, TODAY)
    assert rep["counts"]["exchange"] == 1
    assert rep["counts"]["no_results"] == 0
    assert "exchange" in ledger.OPEN_REASONS
    # Whatever the bucket's wording, it must not send anyone to the ingest.
    assert "ingest" not in ledger.OPEN_REASONS["exchange"].replace(
        "nothing to ingest", "")


def test_why_open_calls_a_future_contract_fresh_and_a_past_one_stale():
    lconn, hconn = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")      # event three weeks out
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")      # event nine days ago
    got = {i["player"]: i["stale"]
           for i in ledger.explain_open(lconn, hconn, TODAY)["buckets"]
           ["exchange"]}
    assert got["KXNFLGAME-26SEP13DALNYG-DA"] is False
    assert got["KXNFLGAME-26AUG14DALNYG-DA"] is True


def test_why_open_still_sorts_ordinary_bets_the_way_it_did():
    lconn, hconn = _journal()
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES "
        "('mlb','2026-08-01','Nobody','hits','OVER',1.5,-110,'A',1.0,10.0,"
        "'open','main')")
    lconn.commit()
    rep = ledger.explain_open(lconn, hconn, TODAY)
    assert rep["counts"]["no_results"] == 1 and rep["counts"]["exchange"] == 0


def test_the_why_open_printer_lists_the_new_bucket():
    """A bucket missing from the print order is 130 bets the report
    silently omits — worse than the wrong diagnosis it replaced."""
    import inspect

    import launch
    src = inspect.getsource(launch.why_open)
    order = src.split("order = [", 1)[1].split("]", 1)[0]
    for key in ledger.OPEN_REASONS:
        assert f'"{key}"' in order, key


# --- the settlement pull --------------------------------------------------

def test_every_open_ticker_is_asked_about_not_the_first_forty():
    """130 open contracts, one request, forty tickers — the other ninety
    could not settle whatever the exchange said."""
    seen, urls = [], []

    def fake_fetch(url, cache_name, ttl=0, **kw):
        urls.append((url, cache_name))
        got = url.split("tickers=", 1)[1].split(",")
        seen.extend(got)
        return '{"markets": [%s]}' % ",".join(
            '{"ticker": "%s", "result": "yes"}' % t for t in got)

    tickers = [f"KXNFLGAME-26SEP{i:02d}AAABBB-DA" for i in range(1, 131)]
    old = kx.fetch_text
    kx.fetch_text = fake_fetch
    try:
        got = kx.fetch_markets_by_tickers(tickers)
    finally:
        kx.fetch_text = old
    assert seen == tickers
    assert len(got) == 130
    # Each batch under its own cache name, or batch two reads batch one's
    # answer back off disk and half the book settles as the wrong market.
    assert len({c for _, c in urls}) == len(urls)


def test_one_bad_batch_does_not_cost_the_others_their_settlements():
    calls = []

    def fake_fetch(url, cache_name, ttl=0, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("connection reset")
        return '{"markets": [{"ticker": "T", "result": "no"}]}'

    old = kx.fetch_text
    kx.fetch_text = fake_fetch
    try:
        got = kx.fetch_markets_by_tickers([f"T{i}" for i in range(80)])
    finally:
        kx.fetch_text = old
    assert len(calls) == 2 and len(got) == 1


def test_a_dead_feed_raises_rather_than_reporting_nothing_settled():
    def fake_fetch(url, cache_name, ttl=0, **kw):
        raise OSError("no route to host")

    old = kx.fetch_text
    kx.fetch_text = fake_fetch
    try:
        kx.fetch_markets_by_tickers(["T1"])
    except OSError:
        pass
    else:
        raise AssertionError("a total feed failure settled silently")
    finally:
        kx.fetch_text = old


def test_the_settlement_pull_skips_games_that_have_not_happened():
    """A market cannot settle before its event. Through an NFL season the
    open book is mostly future contracts, and asking about every one of
    them makes the settlement pull grow with the schedule."""
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26SEP13DALNYG-DA")      # three weeks out
    _pm(lconn, "KXNFLGAME-26AUG14DALNYG-DA")      # played
    assert ledger.open_predmarket_tickers(lconn, TODAY) == [
        "KXNFLGAME-26AUG14DALNYG-DA"]


def test_todays_and_tomorrows_contracts_are_still_asked_about():
    """A day of slack, deliberately: an early settlement or a timezone
    disagreeing about the date costs one batch, and a contract we stop
    asking about is one that never grades."""
    lconn, _ = _journal()
    _pm(lconn, "KXNFLGAME-26AUG23DALNYG-DA")      # today
    _pm(lconn, "KXNFLGAME-26AUG24DALNYG-DA")      # tomorrow
    assert len(ledger.open_predmarket_tickers(lconn, TODAY)) == 2


def test_an_undated_ticker_is_always_asked_about():
    lconn, _ = _journal()
    _pm(lconn, "SOMETHING-WITH-NO-DATE")
    assert ledger.open_predmarket_tickers(lconn, TODAY) == [
        "SOMETHING-WITH-NO-DATE"]


def test_the_stuck_report_names_a_command_that_can_actually_help():
    """The old advice for these rows was `ingest.py`, which can never
    close one. Whatever the tip says now, it must not be that."""
    import inspect

    import launch
    src = inspect.getsource(launch.show_stuck)
    tip = src.split('"waiting on the exchange":', 1)[1].split('",\n', 1)[0]
    assert "ingest.py" not in tip
    assert "pm_build" in tip


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
