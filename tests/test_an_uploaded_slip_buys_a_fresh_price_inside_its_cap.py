"""An uploaded slip buys a fresh price for a leg whose own is old, inside a daily cap.

Ethan, 2026-10-14, "do 1-11", to "A fresh odds pull of a slip's own markets
when our price is old ... so you'd pick a daily cap": yes. The cap starts
small (DEFAULT_DAILY_CAP credits a day) and is set on the box with
QB_SLIP_ODDS_DAILY_CAP.

`engine/slipodds.FreshLive` sees every priced leg once (`grade` calls its
`prepare`), buys one event call per game for just the markets the slip's
legs on that game need, and only for a leg whose game has not started and
whose price is over an hour old or missing. Past the cap, or past the
month's spare credits, or when the call fails, the leg keeps the latest
pull's price and the card says so. Only the upload buys; the Live tab's
tracker and the box's slip watch never do.

NEVER THE BOARD'S BUDGET (Ethan, the same day, on the first build: "make it
so it doesn't run through our budget"). Every call is journalled as
"slip_event" under its league, which the board's daily ceiling skips
(`oddsbudget.SLIP_KINDS`), and an upload spends only what the month can
spare: the ring's balance, less the reserve, less the rest of the month at
the last seven full days' pace (`oddsbudget.spare_credits`). The first
build's check that the ceiling counted these calls was turned round, and
its "near the reserve" case became the spare case (pins changed
2026-10-14, told to Ethan).

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


def _live(age_s=3 * 3600, spent=0, cap=20, spare=10_000, calls=None, fetch=None, **kw):
    calls = calls if calls is not None else _Calls()
    live = SO.FreshLive(_index(age_s), fast_dir=tempfile.mkdtemp(), now=NOW,
                        fetch=fetch or calls.fetch, events=lambda league: EVENTS,
                        spent=lambda: spent, cap=cap, spare=lambda: spare, **kw)
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
                   spent=lambda: 0, cap=20, spare=lambda: 10_000)
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


def test_with_nothing_to_spare_nothing_is_bought():
    live, calls = _live(spare=0)
    leg = _prop()
    live.prepare([leg], {})
    assert calls == [] and live.report["why"] == "spare" and live.report["held"] == 1
    assert live.report["note"] == ("1 leg kept our last pull's price: fresh pulls only use spare "
                                   "odds credits, and this month has none to spare.")
    assert live.prices(leg, None)["books"][0]["book"] == "DraftKings"


def test_the_spare_credits_cover_the_whole_upload_not_each_game_alone():
    """Two games, a credit each, one credit spare: the first game's pull
    is bought and the second is held, never both."""
    live, calls = _live(spare=1)
    kc = _prop()
    gb = _prop(player="Jordan Love", team="GB", opponent="CHI", game="CHI @ GB", market="pass_yds",
               row={"line": 240.5}, line=240.5)
    live.prepare([kc, gb], {})
    assert [c[0] for c in calls] == ["ev-kc"], calls
    assert live.report["held"] == 1 and live.report["why"] == "spare" and live.report["credits"] == 1


# --- spare credits: what the month will not miss -------------------------------------
def _spend_ledger(days: dict, today: _dt.date):
    """A spend ledger: ``{days_ago: [(kind, credits)]}`` before ``today``."""
    from engine import oddsbudget as OB
    p = Path(tempfile.mkdtemp()) / "spend.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for ago, rows in days.items():
            iso = _dt.datetime.combine(today - _dt.timedelta(days=ago), _dt.time(12)).isoformat()
            for kind, credits in rows:
                fh.write(json.dumps({"ts": 0, "iso": iso, "kind": kind, "sport": "nfl",
                                     "credits": credits, "detail": ""}) + "\n")
    OB._TODAY_CACHE.clear()
    return p


def _state(remaining: int):
    from engine import oddsbudget as OB
    p = Path(tempfile.mkdtemp()) / "state.json"
    OB.save(OB.BudgetState(remaining=remaining), p)
    return p


def test_spare_is_the_balance_past_the_reserve_and_the_rest_of_the_month_at_last_weeks_pace():
    from engine import oddsbudget as OB
    today = _dt.date(2026, 10, 14)                         # 18 days left, today counted
    assert OB.days_left_in_month(today) == 18
    week = {ago: [("live_event", 90), (SO.KIND, 10)] for ago in range(1, 8)}
    led, st = _spend_ledger(week, today), _state(5000)
    assert OB.spare_credits(today, path=led, state_path=st) == 5000 - OB.RESERVE - 100 * 18
    # Today's own spend is not the pace (half a day), and a day eight back is past it.
    led = _spend_ledger({**week, 0: [("live_event", 900)], 8: [("live_event", 900)]}, today)
    assert OB.spare_credits(today, path=led, state_path=st) == 5000 - OB.RESERVE - 100 * 18
    # A busier week spares less, and a month that will spend it all spares nothing, never less.
    led = _spend_ledger({ago: [("live_event", 300)] for ago in range(1, 8)}, today)
    assert OB.spare_credits(today, path=led, state_path=st) == 0


def test_spare_errs_toward_nothing():
    from engine import oddsbudget as OB
    today = _dt.date(2026, 10, 14)
    st = _state(5000)
    # No ledger, or one begun today: no pace to judge by.
    assert OB.spare_credits(today, path=Path(tempfile.mkdtemp()) / "none.jsonl", state_path=st) == 0
    assert OB.spare_credits(today, path=_spend_ledger({0: [("live_event", 5)]}, today), state_path=st) == 0
    # Three days on file: their average, not seven days' with four of them called zero.
    led = _spend_ledger({ago: [("live_event", 100)] for ago in (1, 2, 3)}, today)
    assert OB.spare_credits(today, path=led, state_path=st) == 5000 - OB.RESERVE - 100 * 18
    # A quiet day inside the week the ledger covers is a real zero.
    led = _spend_ledger({1: [("live_event", 350)], 7: [("live_event", 350)]}, today)
    assert OB.spare_credits(today, path=led, state_path=st) == 5000 - OB.RESERVE - 100 * 18
    # The slip lane asks nothing of a budget it cannot read.
    old = OB.spare_credits
    OB.spare_credits = lambda *a, **k: 1 / 0
    try:
        assert SO.spare_credits() == 0
    finally:
        OB.spare_credits = old


def test_the_boards_daily_ceiling_never_counts_a_slip_pull():
    """2026-09-10's baseball day (tests/test_harvest_ceiling.py): a
    136-credit ceiling and a six-game board pull. 60 already spent on the
    board leaves room for it; 20 credits of uploads on top would not, if
    the ceiling counted them — and 80 of the board's own still does not."""
    from engine import oddsbudget as OB
    day = _dt.datetime(2026, 9, 10, 17, 27, 48).timestamp()

    def verdict(rows):
        led = Path(tempfile.mkdtemp()) / "spend.jsonl"
        iso = _dt.datetime.fromtimestamp(day).isoformat(timespec="seconds")
        led.write_text("".join(json.dumps({"ts": 0, "iso": iso, "kind": k, "sport": "mlb",
                                           "credits": c, "detail": ""}) + "\n" for k, c in rows),
                       encoding="utf-8")
        st = Path(tempfile.mkdtemp()) / "state.json"
        OB.save(OB.BudgetState(remaining=62092, last_refresh_ts=0.0,
                               last_seen_iso="2026-09-10T17:27:48"), st)
        keep, OB.SPEND_LOG = OB.SPEND_LOG, led
        OB._TODAY_CACHE.clear()
        try:
            return OB.should_refresh(6, now=day, path=st, kickoffs=None, sport="mlb", share=0.093,
                                     credits=6 * OB.credits_per_event("mlb"))
        finally:
            OB.SPEND_LOG = keep
            OB._TODAY_CACHE.clear()

    assert SO.KIND in OB.SLIP_KINDS and not OB.SLIP_KINDS & {"live_event", "live_board", "live_events"}
    cost = 6 * OB.credits_per_event("mlb")
    assert 60 + cost <= 136 < 80 + cost, cost
    ok, why = verdict([("live_event", 60), (SO.KIND, 20)])
    assert ok, why
    ok, why = verdict([("live_event", 80)])
    assert not ok and "budget is spent for this slate" in why, "the ceiling stopped stopping the board"


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
    assert OB.spent_today(time.time(), log, sport="nfl") == 10, "a report of the league's spend counts it"
    assert OB.spent_today(time.time(), log, sport="nfl", exclude=OB.HARVEST_KINDS | OB.SLIP_KINDS) == 8


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
