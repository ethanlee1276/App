"""The cheap tier: game lines for the whole slate, in one request.

Ethan, 2026-09-03, on a board eight minutes old carrying prices
fifty-five minutes old: *"These lines along with more are completely
wrong"* — and then *"make sure we are using real numbers and lines for
the sports books. Getting the wrong numbers can fuck our picks bad."*

THE PRICE OF A MONEYLINE WAS THE PRICE OF A PROP BOARD. Game markets
(h2h, spreads, totals) are parsed out of the EVENT-scoped payload the
prop pull buys, which the meter bills per market per region and per
event — eight credits a game. So refreshing one moneyline cost eight
times every game on the slate, the pacer declined it (correctly), and
the board kept prices that aged with the cycle. There was no cheaper
tier to fall back to. There is one: the board endpoint returns the same
three markets for the ENTIRE slate for three credits, and
`test_the_meter_agrees_with_the_constant` below measures both figures
through `_classify` rather than asserting them.

WHAT IT CANNOT DO IS PROPS. Player markets exist only per event, so
nothing at this price refreshes one. That is not a limitation to work
around, it is the shape of the thing: the cheap pull rides ON TOP of
`--cached-odds`, and the two stamp two different clocks. A board whose
spread is four minutes old and whose props are two hours old must not
report one number for both — in either direction. Half these tests are
about that.

Run directly: `python3 tests/test_board_lines.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ODDS_API_KEY", "test-key-not-a-real-one")

from engine.sources import oddsapi                           # noqa: E402
from engine.data_loader import Slate                         # noqa: E402
from engine.models import Game, Weather                      # noqa: E402

BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


# --- fixtures ---------------------------------------------------------------
def _event(home_full, away_full, hml, aml, spread, total,
           commence="2026-09-07T17:00:00Z", books=("draftkings", "pinnacle")):
    def book(k):
        return {"key": k, "title": {"draftkings": "DraftKings",
                                    "pinnacle": "Pinnacle"}.get(k, k),
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": home_full, "price": hml},
                        {"name": away_full, "price": aml}]},
                    {"key": "spreads", "outcomes": [
                        {"name": home_full, "price": -110, "point": spread},
                        {"name": away_full, "price": -110, "point": -spread}]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "price": -105, "point": total},
                        {"name": "Under", "price": -115, "point": total}]}]}
    return {"id": f"e-{home_full}", "home_team": home_full,
            "away_team": away_full, "commence_time": commence,
            "bookmakers": [book(k) for k in books]}


def _game(home, away, kickoff="2026-09-07T17:00:00Z"):
    return Game(home=home, away=away, weather=Weather(), kickoff=kickoff)


def _run(payload, games, props=None, **kw):
    """Call the real function with the network stubbed. Returns
    (result, what the request asked for)."""
    captured = {}
    real = oddsapi.fetch_sport_odds

    def fake(sport, **k):
        captured.update(k)
        captured["sport"] = sport
        return payload, oddsapi.Quota(remaining=4200, used=800)
    oddsapi.fetch_sport_odds = fake
    try:
        slate = Slate(date="2026-W01", teams={}, games=games,
                      props=list(props or []))
        return oddsapi.apply_board_lines_to_slate(slate, sport="nfl", **kw), captured
    finally:
        oddsapi.fetch_sport_odds = real


# --- the economics, measured ------------------------------------------------
def test_the_meter_agrees_with_the_constant():
    """BOARD_ODDS_COST is a claim about what the API bills, and the pacer
    spends real money against it. Measured through `_classify` — the same
    function that bills every other call — rather than asserted, because
    the last time a per-market cost was assumed rather than measured it
    was a 4-8x overspend that burned 19k of a 20k plan in a day (the note
    CREDITS_PER_EVENT carries)."""
    seen = {}
    real = oddsapi._request

    def fake(url, name, ttl=600, cache_only=False):
        seen["url"], seen["name"] = url, name
        return [], oddsapi.Quota()
    oddsapi._request = fake
    try:
        oddsapi.fetch_sport_odds("nfl", api_key="k",
                                 markets=["h2h", "spreads", "totals"],
                                 cache_tag="lines")
    finally:
        oddsapi._request = real
    kind, sport, cost, _detail = oddsapi._classify(seen["url"], seen["name"])
    assert kind == "live_board", f"billed as {kind}, not a board call"
    assert sport == "nfl"
    import launch
    assert cost == launch.BOARD_ODDS_COST, (
        f"the meter bills {cost} and the pacer authorises "
        f"{launch.BOARD_ODDS_COST}")


def test_it_is_cheaper_than_the_pull_it_backs_up():
    """The whole reason this exists. If a board pull ever cost what a
    handful of event pulls cost, the cheap tier would be a fiction and the
    pacer would be declining both."""
    seen = {}
    real = oddsapi._request

    def fake(url, name, ttl=300, cache_only=False):
        seen["url"], seen["name"] = url, name
        return {}, oddsapi.Quota()
    oddsapi._request = fake
    try:
        cfg = oddsapi.SPORT_CONFIG["nfl"]
        mk = (list(cfg["markets"]) + list(cfg.get("scorers") or {})
              + ["h2h", "totals", "spreads"])
        oddsapi.fetch_event_odds("evt1", api_key="k", markets=mk, sport="nfl")
    finally:
        oddsapi._request = real
    _k, _s, per_event, _d = oddsapi._classify(seen["url"], seen["name"])
    import launch
    # One event alone already costs more than the whole board.
    assert per_event > launch.BOARD_ODDS_COST, (
        f"one event costs {per_event}, the whole board "
        f"{launch.BOARD_ODDS_COST} — the cheap tier is not cheap")


def test_the_pacer_is_told_the_price_in_credits_not_in_events():
    """THE UNIT TRAP. `should_refresh`'s first parameter is an EVENT COUNT
    that it multiplies by CREDITS_PER_EVENT (8). A board pull costs three
    credits TOTAL — one request, three markets — so putting 3 in that slot
    meters it at 24: an eightfold over-estimate of the pull that exists
    because it is cheap, which is how a cheap tier gets declined for being
    expensive. `credits` says the real number."""
    from engine.oddsbudget import refresh_credits, CREDITS_PER_EVENT
    import launch
    assert refresh_credits(3) == 3 * CREDITS_PER_EVENT, \
        "the event-count path changed meaning"
    assert refresh_credits(3, launch.BOARD_ODDS_COST) == launch.BOARD_ODDS_COST
    # And the launcher must use that door for this pull.
    i = LAUNCH.index("def refresh_nfl(")
    seg = LAUNCH[i:LAUNCH.index("\ndef ", i + 40)]
    assert "credits=BOARD_ODDS_COST" in seg, \
        "the board pull is priced through the event-count parameter"
    assert "cost=BOARD_ODDS_COST" not in seg, \
        "three credits is being metered as three events"


def test_the_credit_override_reaches_the_daily_cap():
    """The cap is the thing that has been declining these pulls, so the
    honest price has to reach it — not just the cadence above it."""
    import inspect
    from engine import oddsbudget
    src = inspect.getsource(oddsbudget.should_refresh)
    assert src.count("refresh_credits(requests_per_refresh, credits)") == 2, (
        "one of the two per-refresh cost sites still multiplies an event "
        "count by hand")
    assert "credits=credits" in src, "the cadence never sees the override"


def test_on_the_day_that_prompted_this_the_cheap_pull_is_affordable():
    """THE MEASUREMENT, not the intention.

    Reconstructed from the state Ethan was looking at on 2026-09-03: a plan
    down to 5,000 credits, NFL on a half share alongside another live
    slate, a 16-game board. The day's allowance is 40 credits. A prop
    refresh costs 136 — the pacer declines it, correctly, and that is why
    the page carried fifty-five-minute-old prices. The same 40 credits buy
    a dozen game-line refreshes.

    If this ever inverts, the cheap tier has stopped being cheap and the
    board is back on stale numbers with nobody noticing."""
    import datetime as _date
    import json as _json
    import tempfile as _tmp
    import time as _time
    from engine import oddsbudget as ob
    import launch

    day = _date.date(2026, 9, 3)
    now = _time.time()
    st = ob.BudgetState(remaining=5000, used=15000, last_refresh_ts=now - 3600)
    st.sport_last_refresh = {"nfl": now - 3600}
    path = os.path.join(_tmp.mkdtemp(), "budget.json")
    with open(path, "w") as fh:
        _json.dump(st.to_dict(), fh)
    state = ob.load(path)

    games = 16
    allowance = int(ob.daily_allowance(state, day) * 0.5)
    prop = ob.refresh_credits(games + 1)
    board = ob.refresh_credits(games + 1, launch.BOARD_ODDS_COST)
    assert prop > allowance, (
        f"the premise is gone: a prop pull ({prop}) now fits inside the "
        f"day's allowance ({allowance}), so there is nothing to fall back "
        f"from")
    assert board <= allowance, (
        f"the cheap pull ({board}) does not fit in {allowance} either — "
        f"the fallback cannot fire on the day it was built for")
    assert allowance // board >= 6, (
        f"only {allowance // board} game-line refresh(es) a day — not "
        f"enough to keep a moneyline current")
    # And the cadence must actually be reachable, not infinite.
    gap = ob.min_seconds_between(games + 1, state, today=day, share=0.5,
                                 credits=launch.BOARD_ODDS_COST)
    assert gap != float("inf"), "the cheap pull paces to never"
    assert gap <= 2 * 3600, f"a game-line refresh only every {gap / 3600:.1f}h"


def test_it_buys_exactly_the_three_game_markets():
    """The meter bills per market. A fourth market added here is a 33%
    price rise on every refresh, so the list is the cost."""
    _r, asked = _run([], [_game("BUF", "HOU")])
    assert asked.get("markets") == ["h2h", "spreads", "totals"], asked.get("markets")


def test_it_tags_its_cache_so_it_cannot_eat_another_pull():
    """`fetch_sport_odds` keys its cache by SPORT ALONE. livelines already
    stores a one-market h2h payload under the nfl key ("live") and
    prelines a board one ("pre"). Untagged, this would overwrite theirs or
    read theirs back — a payload with no spreads or totals in it — and
    conclude the books had stopped posting them."""
    _r, asked = _run([], [_game("BUF", "HOU")])
    tag = asked.get("cache_tag")
    assert tag, "no cache_tag: this shares a cache file with another pull"
    src = open(os.path.join(ROOT, "engine", "livelines.py"),
               encoding="utf-8").read()
    pre = open(os.path.join(ROOT, "engine", "nfl", "prelines.py"),
               encoding="utf-8").read()
    for other, name in ((src, "livelines"), (pre, "prelines")):
        m = re.search(r'cache_tag="([^"]+)"', other)
        assert m and m.group(1) != tag, f"tag collides with {name}"


# --- what it attaches -------------------------------------------------------
def test_it_prices_the_whole_slate_from_one_request():
    games = [_game("BUF", "HOU"), _game("CHI", "CAR")]
    payload = [_event("Buffalo Bills", "Houston Texans", -108, -102, -1.5, 47.5),
               _event("Chicago Bears", "Carolina Panthers", -154, 135, -3.0, 45.0)]
    r, _ = _run(payload, games)
    assert r.games_priced == 2, r.games_priced
    assert (r.moneylines, r.spreads, r.totals) == (2, 2, 2)
    buf, chi = games
    assert (buf.home_ml, buf.away_ml) == (-108, -102)
    assert (chi.home_ml, chi.away_ml) == (-154, 135)
    assert buf.spread == -1.5 and buf.total == 47.5


def test_a_book_price_marks_the_number_as_the_market_s():
    """`total_measured` / `spread_measured` are the answer to "did a book
    post this", and Game's defaults (44.0 and 0.0) are indistinguishable
    from real numbers without them. A price arriving through this door has
    to set them, or the same three guards go blind again that
    engine/models.py documents at length."""
    g = _game("BUF", "HOU")
    assert not g.total_measured and not g.spread_measured
    r, _ = _run([_event("Buffalo Bills", "Houston Texans", -108, -102, -1.5, 47.5)],
                [g])
    assert r.games_priced == 1
    assert g.total_measured and g.spread_measured
    assert g.total_is_posted and g.spread_is_posted


def test_the_sharp_anchor_rides_along():
    """Pinnacle's own pair is the fair-value anchor the prop path attaches.
    It is in this payload too, and dropping it would quietly make every
    line that arrives cheaply worse than one that arrives expensively."""
    g = _game("BUF", "HOU")
    _run([_event("Buffalo Bills", "Houston Texans", -108, -102, -1.5, 47.5)], [g])
    assert (g.sharp_home_ml, g.sharp_away_ml) == (-108, -102)
    assert g.sharp_total == 47.5
    assert g.sharp_spread == -1.5


def test_it_does_not_touch_a_single_prop():
    """The split this whole design rests on. Player markets do not exist at
    this price, so a prop must come out the far side exactly as the cached
    pull left it — and the freshness stamps downstream are only honest if
    that is true."""
    from engine.models import Prop, SportsbookLine
    # A prop carrying the price the LAST PAID pull attached — the state
    # --cached-odds leaves the board in, which is exactly the state this
    # refresh must not disturb.
    held = SportsbookLine(book="DraftKings", line=241.5,
                          over_odds=-114, under_odds=-106)
    p = Prop(player="Josh Allen", team="BUF", opponent="HOU", position="QB",
             market="pass_yds", logs=[], career_avg=0.0,
             vs_opponent_avg=None, lines=[held])
    before = list(p.lines)
    r, _ = _run([_event("Buffalo Bills", "Houston Texans", -108, -102, -1.5, 47.5)],
                [_game("BUF", "HOU")], props=[p])
    assert r.games_priced == 1, "the fixture did not price, so this proves nothing"
    assert list(p.lines) == before, "the game-lines pull altered a prop"
    assert p.lines[0].over_odds == -114, "the cached prop price was overwritten"


# --- what it drops, and why -------------------------------------------------
def test_the_two_failure_modes_are_named_separately():
    """An unmapped NAME is a stale team table; a mapped pair that is not on
    our slate is a wiring bug. They need opposite fixes, and a board that
    quietly prices 9 of 16 games looks exactly like a light week — the WNBA
    lesson (1 event matched of 4, 761 props reported unpriced, nothing
    anywhere saying three games had simply failed to map)."""
    r, _ = _run([_event("Green Bay Packers", "Minnesota Vikings", -130, 110, -2.0, 42.5),
                 _event("Some Expansion Club", "Denver Broncos", -130, 110, -2.0, 42.5)],
                [_game("BUF", "HOU")])
    reasons = {d["reason"] for d in r.dropped_events}
    assert len(r.dropped_events) == 2, r.dropped_events
    assert any("not in the map" in x for x in reasons), reasons
    assert any("not on our slate" in x for x in reasons), reasons


def test_another_day_s_game_is_not_reported_as_a_fault():
    """The board endpoint has no date filter, so a one-game slate is
    matched against every upcoming fixture. Those are supposed to miss;
    counting them as drops turns a correct result into alarming lines,
    which is how a diagnostic stops being read."""
    r, _ = _run([_event("Green Bay Packers", "Minnesota Vikings", -130, 110,
                        -2.0, 42.5, commence="2026-10-19T17:00:00Z")],
                [_game("BUF", "HOU")])
    assert r.other_day_events == 1, r.other_day_events
    assert not r.dropped_events, r.dropped_events


def test_a_doubleheader_picks_its_leg_by_start_time():
    """Football has none, but this function is sport-agnostic and a
    silently merged doubleheader is a WRONG price rather than a missing
    one — both legs' prices under one line."""
    early = _game("NYY", "BOS", kickoff="2026-07-04T17:05:00Z")
    late = _game("NYY", "BOS", kickoff="2026-07-04T23:10:00Z")
    ev = _event("New York Yankees", "Boston Red Sox", -150, 130, -1.5, 8.5,
                commence="2026-07-04T23:10:00Z")
    real_cfg = oddsapi.SPORT_CONFIG["nfl"]["teams"]
    oddsapi.SPORT_CONFIG["nfl"]["teams"] = dict(
        real_cfg, **{"New York Yankees": "NYY", "Boston Red Sox": "BOS"})
    try:
        r, _ = _run([ev], [early, late])
    finally:
        oddsapi.SPORT_CONFIG["nfl"]["teams"] = real_cfg
    assert r.games_priced == 1
    assert late.home_ml == -150, "the price landed on the wrong leg"
    assert early.home_ml is None or early.home_ml == 0, \
        "the early leg was priced from the late leg's event"


def test_cached_with_nothing_on_disk_is_empty_not_an_error():
    """A cache-only call for a payload nobody ever paid for has nothing to
    read. That is the ordinary state before the first pull of a season and
    must not take the build down."""
    real = oddsapi.fetch_sport_odds

    def boom(*a, **k):
        raise oddsapi.OddsAPIError("no cached payload")
    oddsapi.fetch_sport_odds = boom
    try:
        slate = Slate(date="d", teams={}, games=[_game("BUF", "HOU")], props=[])
        r = oddsapi.apply_board_lines_to_slate(slate, sport="nfl",
                                               cache_only=True)
    finally:
        oddsapi.fetch_sport_odds = real
    assert r.games_priced == 0 and r.from_cache


# --- the build ---------------------------------------------------------------
def test_the_build_takes_the_flag_and_runs_it_after_the_cached_prices():
    """Order is the point: --board-odds layers OVER --cached-odds, so the
    cached game prices are overwritten with current ones and the cached
    prop prices are left alone. Running it first would have the cached
    pull put hour-old moneylines back."""
    assert '"--board-odds"' in BUILD, "the flag is gone"
    cached = BUILD.index("if args.odds or args.cached_odds:")
    board = BUILD.index("if args.board_odds:")
    assert board > cached, "the cheap refresh runs before the cached one"
    assert "apply_board_lines_to_slate" in BUILD


def test_the_lines_get_their_own_stamp():
    """THE FRESHNESS LIE THIS PREVENTS. On a cycle where only the cheap
    pull was authorised, `priced_at` is hours old and the moneyline is
    minutes old. One number for both overstates the props if it takes the
    newer stamp and understates the lines if it takes the older, and the
    page draws this next to prices people bet."""
    i = BUILD.index('odds_status["priced_at"]')
    seg = BUILD[i:i + 1400]
    assert 'sport_ts("nfl_lines")' in seg, \
        "the lines stamp does not read its own clock"
    assert '"lines_priced_at"' in seg
    # And it must not be written unconditionally: no cheap pull ever made
    # means no second stamp, not a stamp of zero.
    assert "if _lts:" in seg, "an absent lines pull would stamp anyway"


def test_the_stamp_is_only_written_when_a_pull_actually_priced():
    i = BUILD.index("if args.board_odds:")
    seg = BUILD[i:i + 2200]
    assert "if bres.games_priced:" in seg, \
        "a pull that priced nothing would still claim fresh lines"
    j = seg.index("if bres.games_priced:")
    assert 'odds_status["lines_at"]' in seg[j:j + 400]


# --- the launcher ------------------------------------------------------------
def test_the_cheap_pull_is_only_reached_when_the_dear_one_was_declined():
    """It is a FALLBACK, not an addition. Reached from the `elif` branch —
    the one that was previously cached-odds-and-nothing-else — so a cycle
    that already bought the full prop payload (game markets included)
    never pays three credits for numbers it just bought."""
    i = LAUNCH.index("def refresh_nfl(")
    seg = LAUNCH[i:LAUNCH.index("\ndef ", i + 40)]
    lines = seg.splitlines()

    def _at(needle):
        for n, ln in enumerate(lines):
            if needle in ln:
                return n, len(ln) - len(ln.lstrip())
        raise AssertionError(f"{needle} is gone from refresh_nfl")

    dear, _ = _at('args.append("--odds")')
    elif_n, elif_col = _at("elif _with_odds():")
    board, board_col = _at('args.append("--board-odds")')
    assert dear < elif_n < board, "the branch order changed"
    # Nesting, by indentation: the cheap pull has to sit INSIDE the elif
    # body — the branch reached only when the full pull was declined — and
    # deeper still, under its own affordability check.
    assert board_col > elif_col, \
        "--board-odds is not inside the declined branch at all"
    body = lines[elif_n + 1:board]
    assert any("_odds_affordable(" in ln for ln in body), \
        "--board-odds is appended without asking whether it is affordable"
    # Nothing may dedent back to the elif's own level between the two, or
    # the append has left the branch.
    for ln in body:
        if ln.strip() and not ln.lstrip().startswith("#"):
            assert len(ln) - len(ln.lstrip()) > elif_col, \
                f"the branch closed before --board-odds: {ln.strip()[:60]}"


def test_it_paces_on_its_own_clock():
    """Sharing "nfl" would have the two tiers starve each other in both
    directions: a three-credit pull resetting the clock a 128-credit pull
    waits on, and MIN_REFRESH_GAP after a prop pull blocking the lines
    too. The credit budget stays shared — it is one plan."""
    import launch
    assert launch.LINES_CLOCK != "nfl", "the two tiers share a pacing clock"
    i = LAUNCH.index("def refresh_nfl(")
    seg = LAUNCH[i:LAUNCH.index("def ", i + 40)]
    assert "sport=LINES_CLOCK" in seg and "credits=BOARD_ODDS_COST" in seg


def test_a_pull_that_never_landed_does_not_burn_its_clock():
    """The same rule the prop pull learned: authorization is not a pull.
    Stamping at authorization time meant a network blip silently stranded
    the board on stale prices until the next window."""
    i = LAUNCH.index("def refresh_nfl(")
    seg = LAUNCH[i:LAUNCH.index("def ", i + 40)]
    assert "_finish_paid_pull(lines_spend" in seg, \
        "the cheap pull never confirms it landed"
    assert "lines_before = _paid_pull_baseline()" in seg


# --- the page ----------------------------------------------------------------
def test_the_page_shows_the_second_clock_only_when_it_is_newer():
    """Two timestamps that agree are one fact printed twice. The second
    line earns its place only on the cycles where the lines really are
    fresher than the props."""
    i = APP.index("function oddsClockHTML(")
    seg = APP[i:i + 2500]
    assert "os.lines_priced_at" in seg, "the page ignores the lines stamp"
    assert "> (os.priced_at || 0)" in seg, \
        "the second stamp prints even when it is not newer"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
