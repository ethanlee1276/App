"""An uploaded slip buys a fresh price for a leg whose own is old, inside a daily cap.

Ethan, 2026-10-14, "do 1-11", to "A fresh odds pull of a slip's own markets
when our price is old ... so you'd pick a daily cap": yes. The cap starts
small (DEFAULT_DAILY_CAP credits a day) and is set on the box with
QB_SLIP_ODDS_DAILY_CAP.

`engine/slipodds.FreshLive` sees every priced leg once (`grade` calls its
`prepare`), buys one event call per game for just the markets the slip's
legs on that game need, and only for a leg whose game has not started and
whose price is over an hour old or missing. Past the cap, or near the
month's reserve, or when the call fails, the leg keeps the latest pull's
price and the card says so. Every call is journalled as "slip_event" under
its league, where the board's own daily ceiling counts it. Only the upload
buys; the Live tab's tracker and the box's slip watch never do.

Run directly: `python3 tests/test_an_uploaded_slip_buys_a_fresh_price_inside_its_cap.py`
"""

import datetime as _dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import sliplive as SL, slipodds as SO, slipgrade as SG      # noqa: E402

NOW = time.time()


def _iso(ts):
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


EVENTS = [{"id": "ev-kc", "commence_time": _iso(NOW + 3 * 3600),
           "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"},
          {"id": "ev-old", "commence_time": _iso(NOW - 600),
           "home_team": "Denver Broncos", "away_team": "Las Vegas Raiders"},
          {"id": "ev-gb", "commence_time": _iso(NOW + 5 * 3600),
           "home_team": "Green Bay Packers", "away_team": "Chicago Bears"}]


def _prop(**kw):
    """A receiving-yards leg as `price_leg` leaves it, found on the board."""
    leg = {"sport": "nfl", "league": "nfl", "market": "rec_yds", "player": "Travis Kelce",
           "team": "KC", "opponent": "BUF", "game": "BUF @ KC", "side": "over", "line": 52.5,
           "odds": -115, "row": {"line": 52.5}}
    leg.update(kw)
    return leg


def _index(age_s, line=52.5):
    """The board's own price for the prop, pulled ``age_s`` ago."""
    return {"nfl": {(SL._key("Travis Kelce"), "rec_yds"): {
        "quotes": [(line, "DraftKings", -120, -105)], "line": line, "side": "over",
        "as_of": _iso(NOW - age_s)}}}


def _payload(over=-108, under=-118):
    return {"bookmakers": [
        {"key": "pinnacle", "title": "Pinnacle", "markets": [
            {"key": "player_reception_yds", "outcomes": [
                {"name": "Over", "description": "Travis Kelce", "point": 52.5, "price": -110},
                {"name": "Under", "description": "Travis Kelce", "point": 52.5, "price": -110}]},
            {"key": "h2h", "outcomes": [{"name": "Kansas City Chiefs", "price": -150},
                                        {"name": "Buffalo Bills", "price": 130}]}]},
        {"key": "fanduel", "title": "FanDuel", "markets": [
            {"key": "player_reception_yds", "outcomes": [
                {"name": "Over", "description": "Travis Kelce", "point": 52.5, "price": over},
                {"name": "Under", "description": "Travis Kelce", "point": 52.5, "price": under}]},
            {"key": "h2h", "outcomes": [{"name": "Kansas City Chiefs", "price": -140},
                                        {"name": "Buffalo Bills", "price": 120}]}]},
        {"key": "draftkings", "title": "DraftKings", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Kansas City Chiefs", "price": -145},
                                        {"name": "Buffalo Bills", "price": 125}]}]}]}


class _Calls(list):
    def fetch(self, event_id, keys, league):
        self.append((event_id, tuple(keys), league))
        return _payload()


def _live(age_s=3 * 3600, spent=0, cap=20, affordable=True, calls=None, fetch=None, **kw):
    calls = calls if calls is not None else _Calls()
    live = SO.FreshLive(_index(age_s), fast_dir=tempfile.mkdtemp(), now=NOW,
                        fetch=fetch or calls.fetch, events=lambda league: EVENTS,
                        spent=lambda: spent, cap=cap, affordable=lambda cost: affordable, **kw)
    return live, calls


# --- what a fresh pull asks for ------------------------------------------------------
def test_the_odds_keys_are_the_slips_markets_and_nothing_else():
    assert SO.odds_keys("nfl", "rec_yds") == ["player_reception_yds"]
    assert SO.odds_keys("nfl", "rec_yds", alternate=True) == [
        "player_reception_yds", "player_reception_yds_alternate"]
    assert SO.odds_keys("nfl", "anytime_td") == ["player_anytime_td"]
    assert [SO.odds_keys("nba", m) for m in ("moneyline", "spread", "total")] == [
        ["h2h"], ["spreads"], ["totals"]]
    assert SO.odds_keys("nfl", "win_ko") == [], "a fight market reached the odds pull"


def test_the_leg_finds_its_own_game_and_never_a_started_or_doubtful_one():
    table = {"Kansas City Chiefs": "KC", "Buffalo Bills": "BUF", "Denver Broncos": "DEN"}
    assert SO.find_event(EVENTS, ["KC", "BUF"], table, NOW)["id"] == "ev-kc"
    assert SO.find_event(EVENTS, ["KC"], table, NOW)["id"] == "ev-kc"
    assert SO.find_event(EVENTS, ["DEN"], table, NOW) is None, "a game under way was bought"
    assert SO.find_event(EVENTS + [dict(EVENTS[0], id="ev-kc2")], ["KC"], table, NOW) is None
    assert SO.names_team("Ohio State", "Ohio State Buckeyes")
    assert not SO.names_team("LA", "Los Angeles Rams"), "two letters named a city"


# --- when it buys --------------------------------------------------------------------
def test_an_old_price_is_bought_again_for_just_that_game_and_market():
    live, calls = _live()
    leg = _prop()
    live.prepare([leg], {})
    assert calls == [("ev-kc", ("player_reception_yds",), "nfl")], calls
    pr = live.prices(leg, None)
    assert pr["fresh"] and pr["as_of"] == _iso(NOW), pr
    assert pr["books"][0] == {"book": "FanDuel", "odds": -108}, pr["books"]
    assert all(b["book"] != "Pinnacle" for b in pr["books"]), "the sharp book became a price to take"
    assert live.report["note"] == "Prices pulled just now for 1 leg.", live.report
    assert live.report["credits"] == 1 and live.report["games"] == 1


def test_a_recent_price_is_kept_and_nothing_is_bought():
    live, calls = _live(age_s=10 * 60)
    leg = _prop()
    live.prepare([leg], {})
    assert calls == [] and live.report is None
    assert live.prices(leg, {"odds_status": {}})["books"][0]["book"] == "DraftKings"


def test_two_legs_on_one_game_are_one_call():
    live, calls = _live()
    ml = _prop(market="moneyline", player="", side="team", line=0.0, odds=-135, row={})
    live.prepare([_prop(), ml], {})
    assert calls == [("ev-kc", ("player_reception_yds", "h2h"), "nfl")], calls
    pr = live.prices(ml, None)
    assert pr["books"][0] == {"book": "FanDuel", "odds": -140}, pr
    assert pr["other"] == {"book": "DraftKings", "odds": 125}, pr
    from engine.odds import devig_two_way
    assert pr["fair"] == round(devig_two_way(-150, 130)[0], 4), pr["fair"]   # Pinnacle's pair, margin out
    assert live.report["note"] == "Prices pulled just now for 2 legs."


def test_a_number_off_the_main_line_asks_for_the_ladder_too():
    live, calls = _live()
    live.prepare([_prop(line=60.5)], {})
    assert calls[0][1] == ("player_reception_yds", "player_reception_yds_alternate"), calls


def test_a_started_game_buys_nothing():
    class Started(SO.FreshLive):
        def state(self, leg):
            return {"state": "live"}
    calls = _Calls()
    live = Started(_index(3 * 3600), now=NOW, fetch=calls.fetch, events=lambda lg: EVENTS,
                   spent=lambda: 0, cap=20, affordable=lambda c: True)
    live.prepare([_prop()], {})
    assert calls == [] and live.report is None


# --- the budget ----------------------------------------------------------------------
def test_past_the_cap_the_leg_keeps_its_price_and_the_card_says_so():
    live, calls = _live(spent=20, cap=20)
    leg = _prop()
    live.prepare([leg], {})
    assert calls == [], "the cap was spent past"
    assert live.report["why"] == "cap" and live.report["held"] == 1
    assert live.report["note"] == "1 leg kept our last pull's price: today's fresh pulls are used up."
    assert live.prices(leg, None)["books"][0]["book"] == "DraftKings"


def test_near_the_reserve_nothing_is_bought():
    live, calls = _live(affordable=False)
    live.prepare([_prop()], {})
    assert calls == [] and live.report["why"] == "reserve"
    assert "paused to keep the month's odds credits" in live.report["note"]


def test_a_failed_call_keeps_the_last_price():
    def boom(*a):
        raise RuntimeError("quota")
    live, _ = _live(fetch=boom)
    leg = _prop()
    live.prepare([leg], {})
    assert live.report["why"] == "error" and live.prices(leg, None)["books"][0]["book"] == "DraftKings"


def test_the_cap_is_the_boxs_setting_and_small_by_default():
    old = os.environ.pop(SO.CAP_ENV, None)
    try:
        assert SO.daily_cap() == SO.DEFAULT_DAILY_CAP <= 25
        os.environ[SO.CAP_ENV] = "40"
        assert SO.daily_cap() == 40
        os.environ[SO.CAP_ENV] = "0"
        assert SO.daily_cap() == 0
        os.environ[SO.CAP_ENV] = "lots"
        assert SO.daily_cap() == SO.DEFAULT_DAILY_CAP
    finally:
        os.environ.pop(SO.CAP_ENV, None)
        if old is not None:
            os.environ[SO.CAP_ENV] = old


def test_its_calls_are_journalled_as_their_own_kind_under_the_league():
    from engine.sources import oddsapi
    from engine import oddsbudget as OB
    name = oddsapi.event_cache_name("ev-kc", ["player_reception_yds", "h2h"], None, "nfl", oddsapi.SLIP_LANE)
    kind, sport, cost, _ = oddsapi._classify(
        "https://x/v4/sports/americanfootball_nfl/events/ev-kc/odds?markets=player_reception_yds,h2h&regions=us", name)
    assert (kind, sport, cost) == ("slip_event", "nfl", 2)
    assert oddsapi.event_cache_name("ev-kc", ["h2h"], None, "nfl") != oddsapi.event_cache_name(
        "ev-kc", ["h2h"], None, "nfl", oddsapi.SLIP_LANE), "a slip's pull shared the board's cache"
    log = Path(tempfile.mkdtemp()) / "spend.jsonl"
    OB.log_spend("live_event", "nfl", 8, path=log)
    OB.log_spend(SO.KIND, "nfl", 2, path=log)
    OB.log_spend(SO.KIND, "nba", 1, path=log)
    assert SO.spent_today(time.time(), log) == 3
    assert OB.spent_today(time.time(), log, sport="nfl") == 10, "the board's ceiling no longer counts it"


# --- the wiring ----------------------------------------------------------------------
def test_grade_hands_the_legs_over_once_and_carries_the_report():
    class Stub(SL.Live):
        seen = None

        def prepare(self, legs, boards):
            Stub.seen = list(legs)
            self.report = {"note": "Prices pulled just now for 0 legs."}
    card = SG.grade({"legs": []}, {}, live=Stub({}))
    assert Stub.seen == [] and card["fresh"] == {"note": "Prices pulled just now for 0 legs."}
    assert SG.grade({"legs": []}, {}, live=SL.Live({}))["fresh"] is None


def test_only_the_upload_buys():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    i = server.index("def _ask_slip(")
    slip = server[i:server.index("def _ask_track(", i)]
    assert "SO.FreshLive(prices)" in slip
    track = server[server.index("def _ask_track("):]
    track = track[:track.index("\n    def ", 10)]
    assert "FreshLive" not in track, "the Live tab's minute-by-minute read buys prices"
    assert "FreshLive" not in (ROOT / "engine" / "slipwatch.py").read_text(encoding="utf-8")


def test_the_card_says_what_was_pulled():
    js = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
    assert "${freshHTML(s.fresh)}" in js and 'class="pgr-fresh"' in js
    assert ".pgr-fresh" in (ROOT / "web" / "css" / "slip.css").read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = ran = 0
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            try:
                _f(); ran += 1; print(f"  ok  {_n}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {_n}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {_n}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
