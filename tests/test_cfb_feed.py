"""The college player-prop feed: what it buys, what it costs, what it says.

Ethan, twice on 2026-09-02: "make sure everything I'm telling you to do
for NFL is also being implemented for college football because I'm still
not seeing any props for college football."

`SPORT_CONFIG["cfb"]` was `markets: {}` — full-game markets only — so no
college player prop was ever requested and there was nothing to price.
That was not an oversight: until `engine/cfb/props.py` there was no
college yardage projection to compare a quote against, and buying a
number you cannot price is paying for nothing.

Now that there is one, the constraint is money. A college Saturday is
sixty games where an NFL Sunday is sixteen, the meter bills per market
per region, and five player markets across sixty games is three hundred
credits a cycle against a plan measured in thousands a month. So the
feed does not widen — the pull picks its games, the pacer says how many,
and the board says what it left out.

Run directly: `python3 tests/test_cfb_feed.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfb_build as B                                        # noqa: E402
from engine.oddsbudget import BudgetState, affordable_events  # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402


# --- what the config now names ----------------------------------------
def test_college_buys_the_same_four_markets_the_nfl_does():
    """Same sport, same Odds API keys. Sharing the dict rather than
    copying it is what stops the two drifting."""
    assert O.SPORT_CONFIG["cfb"]["markets"] is O.ODDS_TO_MARKET
    assert set(O.SPORT_CONFIG["cfb"]["markets"].values()) == \
        {"pass_yds", "rush_yds", "rec_yds", "receptions"}


def test_the_scorer_market_rides_in_the_same_config():
    assert O.SPORT_CONFIG["cfb"]["scorers"] is O.SCORER_ODDS_TO_MARKET


def test_the_team_map_stays_empty_on_purpose():
    """134 schools is the table that rots the moment a conference
    reshuffles; `apply_odds_to_slate` prefers a slate's own team names
    for exactly that reason, and `engine/cfb/props.py` puts them there."""
    assert O.SPORT_CONFIG["cfb"]["teams"] == {}


def test_the_markets_a_college_board_prices_are_the_markets_it_measures():
    from engine import rankfit
    from engine.cfb import props
    assert set(O.SPORT_CONFIG["cfb"]["markets"].values()) == \
        set(rankfit.MARKETS["cfb"]) == set(props.MARKETS)


# --- the cache key that made two market sets collide ------------------
def _url_for(markets, sport="cfb", event="e1"):
    seen = {}

    def fake_request(url, cache_name, ttl=300, cache_only=False):
        seen["url"], seen["name"] = url, cache_name
        return {}, O.Quota()
    real = O._request
    O._request = fake_request
    try:
        O.fetch_event_odds(event, "KEY", markets=markets, sport=sport)
    finally:
        O._request = real
    return seen


def test_two_market_sets_for_one_event_no_longer_share_a_cache_file():
    """THE COLLISION THIS PINS. `_request` caches by filename alone, and
    the name was `odds_event_<id>.json` — no market list in it. A narrow
    request cached under the same key as a wide one serves the narrow
    payload back for the rest of the TTL, and the board concludes the
    books stopped posting markets it never asked for. `fetch_sport_odds`
    has guarded this with `cache_tag` for as long as two callers asked
    it different things; this endpoint had exactly one caller per sport
    until college started buying player props."""
    a = _url_for(["player_anytime_td"])
    b = _url_for(["player_rush_yds", "player_pass_yds"])
    assert a["name"] != b["name"], a["name"]
    assert "e1" in a["name"] and "e1" in b["name"]


def test_the_same_request_still_hits_the_same_cache_file():
    """A digest that changed per call would buy the same event twice."""
    assert _url_for(["player_rush_yds"])["name"] == \
        _url_for(["player_rush_yds"])["name"]
    # …and market ORDER is not a different request.
    assert _url_for(["player_rush_yds", "player_pass_yds"])["name"] == \
        _url_for(["player_pass_yds", "player_rush_yds"])["name"]


def test_two_leagues_never_share_one_event_cache_file():
    assert _url_for(["player_rush_yds"], sport="cfb")["name"] != \
        _url_for(["player_rush_yds"], sport="nfl")["name"]


def test_every_event_call_is_now_billed_to_a_league():
    """`_classify` attributes a credit by scanning the cache name for a
    league token. There was none, so EVERY event-scoped pull ever made —
    every player prop, in every sport — was journaled under sport ""."""
    name = _url_for(["player_rush_yds", "player_pass_yds"])["name"]
    kind, sport, credits, _detail = O._classify(
        "https://x/y?markets=player_rush_yds,player_pass_yds&regions=us", name)
    assert (kind, sport, credits) == ("live_event", "cfb", 2)


# --- what a pull costs, and who decides how much ----------------------
def test_one_call_buys_five_markets_and_is_billed_for_five():
    assert B.CREDITS_PER_EVENT == len(B.PLAYER_MARKETS) == 5
    assert B.PLAYER_MARKETS[0] == "player_anytime_td"
    for key in B.PLAYER_MARKETS[1:]:
        assert key in O.ODDS_TO_MARKET, key


def test_the_authorization_estimate_matches_the_worst_saturday():
    import launch
    assert launch.CFB_ODDS_COST == 3 + B.PLAYER_EVENT_CAP * B.CREDITS_PER_EVENT


def test_a_healthy_plan_affords_games_and_a_spent_one_affords_none():
    assert affordable_events(5, state=BudgetState(remaining=20000)) > 0
    # Below RESERVE there is nothing to spend, whatever the meter says.
    assert affordable_events(5, state=BudgetState(remaining=400)) == 0


def test_the_days_slice_is_split_across_the_pacer_s_own_touchpoints():
    """Four paid pulls a sport a day (7/12/15/18 Eastern). Dividing by
    them is what stops the first pull of the morning spending the day."""
    from engine.oddsbudget import _touchpoints
    st = BudgetState(remaining=20000)
    one = affordable_events(5, state=st, pulls_per_day=1)
    four = affordable_events(5, state=st, pulls_per_day=len(_touchpoints()))
    assert len(_touchpoints()) == 4
    assert four * 4 <= one + 4, (one, four)
    assert affordable_events(5, state=st) == four


def test_a_pricier_pull_buys_fewer_games():
    st = BudgetState(remaining=20000)
    assert affordable_events(1, state=st) > affordable_events(5, state=st)


def test_a_shared_night_halves_the_slice():
    st = BudgetState(remaining=20000)
    assert affordable_events(5, share=0.5, state=st) <= \
        affordable_events(5, share=1.0, state=st)


# --- and the board says what it could not buy -------------------------
def test_the_build_publishes_an_odds_status_the_page_already_renders():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'out["odds_status"] = {' in src
    with open(os.path.join(root, "web", "js", "app.js"), encoding="utf-8") as f:
        app = f.read()
    assert "d.odds_status" in app, "the key nothing reads is not a status"


def test_the_note_names_the_price_and_the_shortfall():
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)
    games, priced = [], {}
    for i in range(6):
        games.append({"game_id": f"g{i}", "home": f"H{i}", "away": f"A{i}",
                      "kickoff": "2026-08-29T20:00Z"})
        priced[f"g{i}"] = {"event_id": f"e{i}", "spread": (-3.0, -110, -110),
                           "total": (50.5, -110, -110)}

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl",
                   cache_only=False):
        return {"bookmakers": []}, O.Quota()
    real = O.fetch_event_odds
    O.fetch_event_odds = fake_fetch
    try:
        _s, _l, note = B.attach_player_quotes(games, priced, cache_only=True,
                                              now=now, cap=2)
    finally:
        O.fetch_event_odds = real
    assert "2 of 6 eligible" in note
    assert f"{B.CREDITS_PER_EVENT} credit(s) each" in note
    assert "4 left unpriced" in note


def test_a_pull_nobody_can_afford_buys_nothing_rather_than_guessing():
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)
    games = [{"game_id": "g0", "home": "H", "away": "A",
              "kickoff": "2026-08-29T20:00Z"}]
    priced = {"g0": {"event_id": "e0"}}
    calls = []

    def fake_fetch(*a, **k):
        calls.append(a)
        return {"bookmakers": []}, O.Quota()
    real = O.fetch_event_odds
    O.fetch_event_odds = fake_fetch
    try:
        scorers, lines, note = B.attach_player_quotes(
            games, priced, cache_only=True, now=now, cap=0)
    finally:
        O.fetch_event_odds = real
    assert calls == [] and scorers == {} and lines == {}
    assert "0 of 1 eligible" in note and "1 left unpriced" in note


def test_an_unmeasured_prop_shelf_explains_itself():
    """`from_prop` refuses an unmeasured market before the census sees
    the row, so the shelf is silently absent — and "we have not measured
    this yet" and "nobody hit the bar tonight" look identical on a page
    while being completely different facts. The sentence MLB and NBA
    publish for the same case."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert '"no market measured to rank yet"' in src
    with open(os.path.join(root, "web", "js", "app.js"), encoding="utf-8") as f:
        app = f.read()
    assert 'c["no market measured to rank yet"]' in app


def test_college_yardage_is_not_wearing_the_nfl_s_measurement():
    """THE FOUNDING RULE, and college has been on the wrong side of it
    once: `likely.CFB_TD_AUC` had to be un-borrowed from the NFL's
    0.721. A box that has not walked college logs must answer None for
    every college yardage market, not the NFL's constant."""
    from engine import likely
    from engine.rankfit import STORE
    if os.path.exists(STORE):            # a box that HAS measured
        return
    for market in ("pass_yds", "rush_yds", "rec_yds", "receptions"):
        assert likely.rank_auc("cfb", market) is None, market
        assert likely.rankable(market, "cfb") is False, market
        assert likely.rank_auc("nfl", market) == likely.RANK_AUC[market]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
