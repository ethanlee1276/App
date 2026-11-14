"""The already-stored skip bought no touchdowns and said it succeeded.

Ethan harvested NFL `receptions` for twelve Sundays, then re-ran the same
Sundays asking for `receptions,anytime_td`. The output:

    2025-09-07: 30 events → 0 price rows
    2025-09-14: 31 events → 0 price rows
    ...
    Harvested 836 price rows in 113 API call(s), skipped 105 already stored.
    Credits spent this run: ~80

Eighty credits, and not one touchdown price on any day that already had
receptions. `db.have_odds_snapshot` asks "have we been here before",
keyed on (sport, event_id, taken_at) with no notion of market — so every
event the receptions run had stored was skipped, and the market that had
never been bought was never bought.

The guard was right about what it measured. A past price IS immutable and
re-buying it IS a waste. It simply could not tell "we have this day" from
"we have this day's touchdowns", and answering the second question with
the first made a run that spent credits, stored nothing, and exited
looking successful.

Coverage is now checked per DAY rather than per event, and that is
deliberate: a book quotes receptions on most games and not all of them,
so an event with no receptions row may never have been offered one.
Asking per event would re-buy those events on every future run forever.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.sources import oddshistory as oh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "2025-09-07T17:00:00Z"


def _row(event, market, player="p", taken=STAMP):
    return {"sport": "nfl", "taken_at": taken, "event_id": event,
            "home": "CIN", "away": "BAL", "player": player, "market": market,
            "book": "dk", "line": 4.5, "over_odds": -110, "under_odds": -110}


def _harvested(conn, market, events=13):
    db.upsert_odds_history(conn, [
        _row(f"e{i}", market, f"p{i}") for i in range(events)])


def _want(*names):
    readable = oh.parse_map("nfl")
    keys = oh.resolve_market_keys("nfl", list(names))
    return {readable[k] for k in keys if k in readable}


# --- what a snapshot holds ---------------------------------------------------
def test_a_fresh_snapshot_holds_nothing():
    assert db.markets_at_snapshot(db.connect(":memory:"), "nfl", STAMP) == set()


def test_the_markets_of_a_day_are_pooled_across_its_events():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [_row("e1", "receptions"),
                                  _row("e2", "anytime_td")])
    assert db.markets_at_snapshot(conn, "nfl", STAMP) == {"receptions",
                                                          "anytime_td"}


def test_another_days_markets_do_not_count_as_this_days():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        _row("e1", "receptions"),
        _row("e2", "anytime_td", taken="2025-09-14T17:00:00Z")])
    assert db.markets_at_snapshot(conn, "nfl", STAMP) == {"receptions"}


def test_another_sports_markets_do_not_count_either():
    conn = db.connect(":memory:")
    row = _row("e1", "hits")
    row["sport"] = "mlb"
    db.upsert_odds_history(conn, [row, _row("e2", "receptions")])
    assert db.markets_at_snapshot(conn, "nfl", STAMP) == {"receptions"}


# --- the decision the harvester makes ---------------------------------------
def test_re_asking_for_a_market_already_bought_is_still_skipped():
    """The guard's original job, which must survive the fix: a past price
    is immutable and paying for it twice is pure waste."""
    conn = db.connect(":memory:")
    _harvested(conn, "receptions")
    stored = db.markets_at_snapshot(conn, "nfl", STAMP)
    assert _want("receptions") <= stored


def test_asking_for_a_market_never_bought_stands_the_skip_down():
    """Ethan's case exactly. The day has receptions; it has no touchdowns;
    the touchdowns must be bought."""
    conn = db.connect(":memory:")
    _harvested(conn, "receptions")
    stored = db.markets_at_snapshot(conn, "nfl", STAMP)
    assert not (_want("receptions", "anytime_td") <= stored)
    assert db.have_odds_snapshot(conn, "nfl", "e0", STAMP), \
        "the event IS stored — which is exactly why the old check skipped it"


def test_once_both_markets_are_stored_the_day_is_covered_again():
    """And the run after the fix must not re-spend."""
    conn = db.connect(":memory:")
    _harvested(conn, "receptions")
    _harvested(conn, "anytime_td")
    stored = db.markets_at_snapshot(conn, "nfl", STAMP)
    assert _want("receptions", "anytime_td") <= stored


def test_an_event_a_book_never_quoted_does_not_reopen_the_whole_day():
    """Coverage is per DAY on purpose. A book quotes receptions on most
    games and not all of them; asking per event would re-buy the
    unquoted ones on every run forever."""
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [_row("e1", "receptions"),
                                  _row("e1", "anytime_td"),
                                  _row("e2", "anytime_td")])   # no receptions
    stored = db.markets_at_snapshot(conn, "nfl", STAMP)
    assert _want("receptions", "anytime_td") <= stored


# --- the wiring --------------------------------------------------------------
def test_the_harvester_translates_api_keys_to_the_names_it_stores():
    """`--markets anytime_td` becomes `player_anytime_td` on the request
    and is stored as `anytime_td`. Comparing the request form against the
    stored form would find nothing covered, ever, and re-buy everything."""
    with open(os.path.join(ROOT, "harvest_odds.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "readable = oh.parse_map(args.sport)" in src
    assert "want_markets = {readable[k] for k in market_keys" in src


def test_the_skip_consults_the_day_before_it_fires():
    with open(os.path.join(ROOT, "harvest_odds.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "day_covered and _db.have_odds_snapshot(" in src, \
        "the market-blind skip must not be reachable on its own"
    assert "want_markets <= _db.markets_at_snapshot(" in src


def test_a_full_market_harvest_keeps_the_old_behaviour():
    """No --markets means everything, and then 'we have been here' really
    does mean 'we have what we came for'."""
    with open(os.path.join(ROOT, "harvest_odds.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "day_covered = True" in src, \
        "an unrestricted harvest must default to covered, not to re-buying"


def test_the_script_still_runs():
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "harvest_odds.py"), "nfl",
         "--from", "2025-09-07", "--to", "2025-09-28", "--markets",
         "receptions,anytime_td", "--weekdays", "sun", "--dry-run"],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "player_receptions" in out.stdout
    assert "player_anytime_td" in out.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
