"""The NFL buys the alternate ladders for attempts, completions and rush + rec yards.

The Bills @ Rams reports, 2026-10-12: report 1's whole card was alternate
lines on completions, attempts and rush + rec yards, and the site bought
ladders for yards and catches only, so none of those numbers could be
ranked on Most Likely or checked against our model. Ethan, asked whether to
buy them at three more credits an NFL event: "yes". Pinned here, offline:

  * the three `_alternate` keys are on the NFL event call and not on
    college's (a college Saturday is sixty games), and the per-event price
    the pacer meters rose to match what the call asks for;
  * a rung on the new ladders is parsed apart onto `Prop.alt_lines` beside
    the main line, exactly as the yardage ladders are;
  * the Most Likely ladder prices a pass-attempts rung from the projection,
    the same way it prices every other rung;
  * the keys are unproven against the API from here, so a refusal costs one
    call and never the event, and an unnamed refusal drops them with the
    other newest keys.

Run directly: `python3 tests/test_nfl_buys_the_volume_ladders.py`
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa                     # noqa: E402
from engine import oddsbudget as B                           # noqa: E402
from engine import likely                                    # noqa: E402
from engine.statmath import prob_over                        # noqa: E402
from engine.models import (Team, DefenseProfile, Weather, Game, Prop, GameLog,  # noqa: E402
                           SportsbookLine, PASS_ATT, PASS_CMP, RUSH_REC_YDS)
from engine.data_loader import Slate                         # noqa: E402

NEW = ("player_pass_attempts_alternate", "player_pass_completions_alternate",
       "player_rush_reception_yds_alternate")


def _side(name, price, point, who="Josh Allen"):
    return {"name": name, "description": who, "price": price, "point": point}


EVENT = {"id": "e9", "home_team": "Los Angeles Rams", "away_team": "Buffalo Bills", "bookmakers": [
    {"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "player_pass_attempts", "outcomes": [_side("Over", -110, 34.5), _side("Under", -110, 34.5)]},
        {"key": "player_pass_attempts_alternate", "outcomes": [
            _side("Over", -190, 30.5), _side("Under", 155, 30.5),
            _side("Over", 150, 37.5), _side("Under", -185, 37.5)]},
        {"key": "player_pass_completions_alternate", "outcomes": [
            _side("Over", -220, 19.5), _side("Under", 175, 19.5)]},
        {"key": "h2h", "outcomes": [{"name": "Los Angeles Rams", "price": -140},
                                    {"name": "Buffalo Bills", "price": 120}]}]}]}


def _slate():
    teams = {"LA": Team("LA", "LA", DefenseProfile("LA")), "BUF": Team("BUF", "BUF", DefenseProfile("BUF"))}
    game = Game(home="LA", away="BUF", weather=Weather(dome=True), spread=-2.5, total=47.5)
    logs = [GameLog(week=w, opponent="X", value=34) for w in range(1, 6)]
    prop = Prop(player="Josh Allen", team="BUF", opponent="LA", position="QB", market=PASS_ATT,
                logs=logs, career_avg=33, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=33.5)])
    return Slate(date="2026-W06", teams=teams, games=[game], props=[prop])


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.val)

    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def test_the_nfl_asks_for_the_three_ladders_and_college_does_not():
    assert set(NEW) == set(oa.NFL_ALT_ODDS_KEYS)
    assert oa.NFL_ALT_ODDS_KEYS == {"player_pass_attempts_alternate": PASS_ATT,
                                    "player_pass_completions_alternate": PASS_CMP,
                                    "player_rush_reception_yds_alternate": RUSH_REC_YDS}
    nfl = oa.SPORT_CONFIG["nfl"]
    assert set(NEW) <= set(nfl["alternates"]) and set(oa.ALT_ODDS_TO_MARKET) <= set(nfl["alternates"])
    assert not set(NEW) & set(oa.SPORT_CONFIG["cfb"]["alternates"])
    import cfb_build as CB
    assert not set(NEW) & set(CB.PLAYER_MARKETS), "college's request is its own list, and stays four ladders"
    # The price the pacer meters is what the call asks for: one credit per
    # market per region per event — 22 until today, 25 now.
    n = len(nfl["markets"]) + len(nfl["scorers"]) + len(nfl["alternates"]) + 3
    assert n == B.credits_per_event("nfl") == B.EVENT_CREDITS["nfl"] == 25
    asked = {}

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False):
        asked["markets"] = list(markets or [])
        return EVENT, oa.Quota("491", "25")
    slate = _slate()
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: [EVENT]), \
            _Swap(oa, "fetch_event_odds", fake_fetch):
        res = oa.apply_odds_to_slate(slate, api_key="k")
    assert set(NEW) <= set(asked["markets"]) and len(asked["markets"]) == 25, asked
    prop = slate.props[0]
    assert res.matched == 1 and res.alt_matched == 1
    assert [ln.line for ln in prop.lines] == [34.5], "the shopped field stays the main number"
    assert sorted({ln.line for ln in prop.alt_lines}) == [30.5, 37.5], "the ladder rides beside it"


def test_each_ladder_parses_onto_its_own_market():
    alts = oa.parse_event_lines(EVENT, oa.NFL_ALT_ODDS_TO_MARKET)
    assert sorted(ln.line for ln in alts[("josh allen", PASS_ATT)]) == [30.5, 37.5]
    assert [ln.line for ln in alts[("josh allen", PASS_CMP)]] == [19.5]
    main = oa.parse_event_lines(EVENT, oa.SPORT_CONFIG["nfl"]["markets"])
    assert [ln.line for ln in main[("josh allen", PASS_ATT)]] == [34.5], "a rung never lands on the main line"


def test_most_likely_prices_an_attempts_rung_from_the_projection():
    row = {"player": "Josh Allen", "team": "BUF", "opponent": "LA", "market": PASS_ATT,
           "side": "Over", "line": 34.5, "odds": -110, "projection": 33.0, "proj_std": 5.0,
           "alt_lines": [{"book": "DraftKings", "line": 30.5, "over_odds": -190, "under_odds": 155}]}
    got = likely.rungs(row, PASS_ATT, fits={})
    rung = next(c for c in got if c["line"] == 30.5 and c["side"] == "over")
    assert abs(rung["prob"] - prob_over(30.5, 33.0, 5.0)) < 1e-9 and rung["prob"] >= likely.MIN_PROB
    assert rung["odds"] == -190 and rung["book"] == "DraftKings"
    assert likely.rankable(PASS_ATT) and likely.rankable(PASS_CMP) and likely.rankable(RUSH_REC_YDS), \
        "all three were measured to rank before their ladders were bought"


def test_a_refused_ladder_costs_one_call_never_the_event():
    assert set(NEW) <= oa.UNPROVEN_MARKETS and set(NEW) <= oa.NEWEST_ODDS_KEYS
    asked = []

    def fake(url, name, ttl=300, cache_only=False):
        markets = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["markets"][0].split(",")
        asked.append(markets)
        if "player_pass_completions_alternate" in markets:
            raise oa.OddsAPIError("422: invalid market player_pass_completions_alternate")
        return {}, None
    real, oa._request = oa._request, fake
    before = set(oa.REJECTED_MARKETS)
    try:
        oa.fetch_event_odds("evt", api_key="k", sport="nfl",
                            markets=list(oa.SPORT_CONFIG["nfl"]["markets"]) + list(NEW))
    finally:
        oa._request = real
        oa.REJECTED_MARKETS.clear()
        oa.REJECTED_MARKETS.update(before)
    assert len(asked) == 2, asked
    assert "player_pass_completions_alternate" not in asked[1]
    assert {"player_pass_attempts_alternate", "player_rush_reception_yds_alternate", "player_pass_yds"} <= set(asked[1]), \
        "only the named key goes; the other ladders and every main line stay"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
