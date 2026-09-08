"""A cached odds payload has a maximum age, and every price says how old it is.

Ethan, 2026-09-08, third report of wrong moneylines in a week: "We need
to find the problem with that because it continues to happen an this
could be our issue with not showing picks and shit bc we are pulling the
wrong lines. Also that can make us give fake and false picks that can
hurt us."

THE PROBLEM, FOUND. `oddsapi._request` with `cache_only` "serves the
cached copy at ANY age and never touches the network" — deliberately,
because on a cycle the budget declines the last paid pull's real prices
beat proxies. Nothing ever bounded "any", and nothing recorded which
payload a given price came off. So:

  * a price pulled four minutes ago and a price pulled last week landed
    in the same field and looked identical to every reader downstream;
  * the board-level `priced_at` stamp dates the last PULL, not the
    payload each game was filled from, and on a cached cycle those are
    hours apart by design;
  * so no fact existed anywhere that could tell an OLD price from a
    WRONG one, which is why the same report came back three times and
    was answered twice with more stamps.

That the screenshots were stale rather than mis-mapped is provable
without the box: every book Ethan can bet is in `DEFAULT_BOOKS`, and
`parse_event_h2h` keeps the BEST price per side across them. A live
payload containing DraftKings at -125 cannot produce -220 for the same
team. The payload was old.

WHAT STALENESS COSTS, measured on this box's 5,241 college games holding
both an opening and a closing moneyline from one book — an opening price
being the extreme case of a stale one:

    median move 0.020 · 90th 0.066 · 99th 0.136
    the open and the close named a DIFFERENT favourite   3.19%
    moved more than ten points of win probability         3.5%

One game in thirty priced off a stale pull shows the wrong side as most
likely. So a payload past `MAX_GAME_PRICE_AGE` prices nothing: the game
keeps no market, the board says "no real book price", and the build says
loudly why. A missing price is a quiet shelf; a wrong price is a bet.

AND THE PROPS, on their own knob. The first cut gated the game markets
and left props dated-but-served, on the argument that gating them the
day before the opener would empty the board on a declined cycle. Ethan
repeated the ask word for word: "this could be our issue with not
showing picks and shit bc we are pulling the wrong lines. Also that can
make us give fake and false picks that can hurt us." A pick is a prop.
A per-event payload past `MAX_PROP_PRICE_AGE` indexes no line, no rung,
no menu entry and no scorer quote, so every prop on that game is
proxy-priced and cannot be a pick; the college quote loop refuses the
same way and says so in its note; every prop row that IS priced carries
the age of the payload behind it.

Run directly: `python3 tests/test_stale_price_ceiling.py`
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.models import Game, Weather                        # noqa: E402
from engine.sources import oddsapi as oa                       # noqa: E402


def _event(home="Minnesota Vikings", away="Green Bay Packers",
           home_ml=-125, away_ml=105, eid="e1"):
    return {"id": eid, "home_team": home, "away_team": away,
            "commence_time": "2026-09-13T20:25:00Z",
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": home, "price": home_ml},
                                {"name": away, "price": away_ml}]}]}]}


class _Slate:
    def __init__(self, games):
        self.games = games
        self.date = "2026-09-13"
        self.props = []


def _slate():
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             kickoff="2026-09-13T20:25:00Z")
    return _Slate([g])


def _with_cache(age_s, body, name="odds_board_nfl_lines.json"):
    """Write a payload into the cache dir with a chosen age, and return a
    restore function. The cache path is module state, so it is swapped
    for a temp directory rather than written into the real one."""
    tmp = tempfile.mkdtemp()
    real = oa.CACHE_DIR
    oa.CACHE_DIR = __import__("pathlib").Path(tmp)
    path = oa.CACHE_DIR / name
    path.write_text(json.dumps(body))
    old = time.time() - age_s
    os.utime(path, (old, old))
    return lambda: setattr(oa, "CACHE_DIR", real)


# --- the ceiling itself --------------------------------------------------------
def test_the_ceiling_is_six_hours_and_the_box_can_widen_it():
    assert oa.MAX_GAME_PRICE_AGE == 6 * 3600
    assert oa._max_game_price_age() == 6 * 3600
    os.environ["QB_MAX_GAME_PRICE_AGE"] = "36000"
    try:
        assert oa._max_game_price_age() == 36000
        assert oa.price_is_current(7 * 3600) is True
    finally:
        del os.environ["QB_MAX_GAME_PRICE_AGE"]
    assert oa.price_is_current(7 * 3600) is False
    assert oa.price_is_current(3 * 3600) is True
    # A payload just fetched has nothing cached to date and is current by
    # construction — the caller is holding the bytes.
    assert oa.price_is_current(None) is True


def test_a_payload_that_was_never_written_has_no_age_rather_than_a_zero():
    restore = _with_cache(60, [])
    try:
        assert oa.sport_cache_age("nfl", "lines") is not None
        assert oa.sport_cache_age("nba", "lines") is None, "a missing file is not fresh"
        assert oa.event_cache_age("nope") is None
    finally:
        restore()


# --- the whole-slate pull ------------------------------------------------------
def test_a_stale_whole_slate_payload_prices_nothing_and_says_so():
    slate = _slate()
    restore = _with_cache(9 * 3600, [_event()])
    try:
        res = oa.apply_board_lines_to_slate(slate, api_key="k", cache_only=True)
    finally:
        restore()
    assert res.stale_game_prices == 1 and res.moneylines == 0, res
    assert res.stale_price_age_s > 8 * 3600
    g = slate.games[0]
    assert g.home_ml == 0 and g.away_ml == 0, "a stale price was attached anyway"


def test_a_fresh_whole_slate_payload_prices_the_game_and_dates_it():
    slate = _slate()
    restore = _with_cache(1800, [_event()])
    try:
        res = oa.apply_board_lines_to_slate(slate, api_key="k", cache_only=True)
    finally:
        restore()
    assert res.moneylines == 1 and res.stale_game_prices == 0, res
    g = slate.games[0]
    assert (g.home_ml, g.away_ml) == (-125, 105)
    assert 1700 < g.price_age_s < 1900 and g.priced_from == "board", g.price_age_s


def test_the_screenshots_price_cannot_come_from_a_live_payload():
    """The proof that those cards were STALE rather than mis-mapped: we
    shop the best price per side across every book we request, and
    DraftKings is one of them. A payload holding DK's -125 can only
    publish -125 or better."""
    assert "draftkings" in oa.DEFAULT_BOOKS
    ev = _event()
    ev["bookmakers"].append(
        {"key": "betmgm", "title": "BetMGM", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Minnesota Vikings", "price": -220},
            {"name": "Green Bay Packers", "price": 200}]}]})
    best = oa.parse_event_h2h(ev, {"Minnesota Vikings": "MIN",
                                   "Green Bay Packers": "GB"})
    assert best["MIN"] == -125, best
    assert best["GB"] == 200, best


# --- the college path ----------------------------------------------------------
def test_college_refuses_a_stale_board_with_a_note_a_reader_can_act_on():
    import cfb_build
    restore = _with_cache(30 * 3600, [], name="odds_board_cfb.json")
    try:
        priced, note = cfb_build.attach_odds([], {}, api_key="k", cache_only=True)
    finally:
        restore()
    assert priced == {} and "stale" in note, note
    assert "30.0h" in note and "6h ceiling" in note, note


# --- the age reaches the card and the row --------------------------------------
def test_the_age_rides_from_the_game_to_the_card_to_the_row():
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    like = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    cfb = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert 'd["price_age_s"] = getattr(g, "price_age_s", None)' in pipe
    assert 'd["priced_from"] = getattr(g, "priced_from", "") or ""' in pipe
    assert '"price_age_s": row.get("price_age_s"),' in like
    assert '"priced_from": "board",' in cfb
    from engine import likely as K
    card = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
                has_market=True, home="MIN", away="GB", team="MIN",
                pick_is_home=True, pick_label="MIN ML", side="", line=0.0,
                matchup="GB @ MIN", win_prob=0.56, fair_prob=0.55, edge=0.01,
                odds=-125, home_odds=-125, away_odds=105, ev_per_unit=0.0,
                confidence=6.0, stake_units=0.0, grade="Pass", credible=True,
                headline="MIN ML", reasons=[], recommended=False, live=False,
                date="2026-09-13", game_spread=-1.5,
                price_age_s=1830.0, priced_from="board")
    row = K.from_game_bet(card, "nfl")
    assert row["price_age_s"] == 1830.0 and row["priced_from"] == "board"


def test_both_builds_report_what_they_refused():
    nfl = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "event_stale_prices=res.stale_game_prices" in nfl
    assert "board_stale_prices=bres.stale_game_prices" in nfl
    assert "game(s) kept NO price" in nfl
    assert "QB_MAX_GAME_PRICE_AGE" in nfl


def test_the_docs_carry_the_root_cause_and_the_measurement():
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert "## 8g. Why the wrong moneylines kept coming back (2026-09-08)" in checks
    assert "QB_MAX_GAME_PRICE_AGE" in checks and "3.19%" in checks
    assert "QB_MAX_PROP_PRICE_AGE" in checks and "event_stale_prop_events" in checks


# --- the props, on their own knob ------------------------------------------------
def test_the_prop_ceiling_is_its_own_knob():
    assert oa.MAX_PROP_PRICE_AGE == 6 * 3600 and oa._max_prop_price_age() == 6 * 3600
    os.environ["QB_MAX_PROP_PRICE_AGE"] = "43200"
    try:
        assert oa._max_prop_price_age() == 43200
        assert oa._max_game_price_age() == 6 * 3600, "the two knobs are one knob"
    finally:
        del os.environ["QB_MAX_PROP_PRICE_AGE"]


def _prop_slate():
    from engine.models import (Team, DefenseProfile, Prop, GameLog,
                               SportsbookLine, PASS_YDS)
    from engine.data_loader import Slate
    teams = {"KC": Team("KC", "KC", DefenseProfile("KC")),
             "BUF": Team("BUF", "BUF", DefenseProfile("BUF"))}
    game = Game(home="KC", away="BUF", weather=Weather(), date="2026-09-13",
                kickoff="2026-09-13T20:25:00Z")
    logs = [GameLog(week=w, opponent="X", value=260) for w in range(1, 6)]
    prop = Prop(player="Josh Allen", team="BUF", opponent="KC", position="QB",
                market=PASS_YDS, logs=logs, career_avg=255, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=250.0)])
    # A second man the payload never prices: his row stays proxy-priced
    # on a game that IS dated, which is the case a stamp that ignores
    # `has_market` gets wrong.
    from engine.models import REC_YDS
    unpriced = Prop(player="Dalton Kincaid", team="BUF", opponent="KC", position="TE",
                    market=REC_YDS,
                    logs=[GameLog(week=w, opponent="X", value=48) for w in range(1, 6)],
                    career_avg=45, vs_opponent_avg=None,
                    lines=[SportsbookLine(book="proxy", line=44.5)])
    return Slate(date="2026-09-13", teams=teams, games=[game], props=[prop, unpriced])


PROP_EVENT = {"id": "e1", "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "commence_time": "2026-09-13T20:25:00Z",
              "bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": [
                  {"key": "h2h", "outcomes": [
                      {"name": "Kansas City Chiefs", "price": -140},
                      {"name": "Buffalo Bills", "price": 120}]},
                  {"key": "player_pass_yds", "outcomes": [
                      {"name": "Over", "description": "Josh Allen", "price": -110,
                       "point": 255.5},
                      {"name": "Under", "description": "Josh Allen", "price": -110,
                       "point": 255.5}]}]}]}


def _attach_event(age_s):
    """Run the per-event attach against PROP_EVENT read at a chosen age,
    with the network and the cache directory out of the picture."""
    real = (oa.list_events, oa.fetch_event_odds, oa.event_cache_age)
    oa.list_events = lambda *a, **k: [dict(PROP_EVENT)]
    oa.fetch_event_odds = lambda *a, **k: (dict(PROP_EVENT), oa.Quota())
    oa.event_cache_age = lambda *a, **k: age_s
    slate = _prop_slate()
    try:
        res = oa.apply_odds_to_slate(slate, api_key="k", cache_only=True)
    finally:
        oa.list_events, oa.fetch_event_odds, oa.event_cache_age = real
    return res, slate


def test_a_stale_event_payload_prices_no_prop_and_no_game():
    res, slate = _attach_event(9 * 3600)
    assert res.stale_prop_events == 1 and res.stale_game_prices == 1, res
    assert res.stale_prop_age_s > 8 * 3600
    assert res.matched == 0, "a stale line was matched to a prop"
    prop = slate.props[0]
    assert all(ln.book == "proxy" for ln in prop.lines), \
        "a stale book line replaced the proxy"
    g = slate.games[0]
    assert g.home_ml == 0 and g.price_age_s is None


def test_a_fresh_event_payload_prices_both_and_dates_the_game():
    res, slate = _attach_event(1800)
    assert res.stale_prop_events == 0 and res.stale_game_prices == 0, res
    assert res.matched == 1, res
    prop = slate.props[0]
    assert any(ln.book != "proxy" and ln.line == 255.5 for ln in prop.lines)
    g = slate.games[0]
    assert (g.home_ml, g.away_ml) == (-140, 120)
    assert g.price_age_s == 1800 and g.priced_from == "event"


def test_the_two_ceilings_are_asked_separately():
    """A box that widens the prop knob keeps the game knob: a nine-hour
    payload can price the props and still not the moneyline."""
    os.environ["QB_MAX_PROP_PRICE_AGE"] = "43200"
    try:
        res, slate = _attach_event(9 * 3600)
    finally:
        del os.environ["QB_MAX_PROP_PRICE_AGE"]
    assert res.matched == 1 and res.stale_prop_events == 0, res
    assert res.stale_game_prices == 1 and slate.games[0].home_ml == 0


def test_a_priced_prop_row_carries_the_payloads_age():
    from engine.pipeline import price_props
    _res, slate = _attach_event(1800)
    rows = price_props(slate, sport="nfl")
    row = next(r for r in rows if r["player"] == "Josh Allen")
    assert row["has_market"] is True
    assert row["price_age_s"] == 1800 and row["priced_from"] == "event", row
    # A proxy-priced row on the SAME dated game has no book price to
    # date: the stamp follows the line, not the game.
    other = next(r for r in rows if r["player"] == "Dalton Kincaid")
    assert other["has_market"] is False and other["price_age_s"] is None, other
    assert other["priced_from"] == ""
    # And on a stale payload nobody is dated, because nobody was priced.
    _res, slate = _attach_event(9 * 3600)
    rows = price_props(slate, sport="nfl")
    row = next(r for r in rows if r["player"] == "Josh Allen")
    assert row["has_market"] is False and row["price_age_s"] is None


def test_college_refuses_stale_player_quotes_and_says_so():
    import datetime as dt
    import cfb_build
    t = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc)
    games = [{"game_id": "g1", "home": "UGA", "away": "CLEM",
              "kickoff": (t + dt.timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
              "home_conference": "SEC", "away_conference": "ACC"}]
    priced = {"g1": {"event_id": "ev1", "spread": (-13.5, -110, -110),
                     "total": (55.5, -110, -110)}}
    payload = {"bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "Nate Frazier", "price": -150},
            {"name": "No", "description": "Nate Frazier", "price": 120}]}]}]}
    real = (oa.fetch_event_odds, oa.event_cache_age)
    oa.fetch_event_odds = lambda *a, **k: (payload, oa.Quota())
    try:
        oa.event_cache_age = lambda *a, **k: 9 * 3600
        scorers, _lines, note, _oldest = cfb_build.attach_player_quotes(
            games, priced, cache_only=True, api_key="k", now=t, cap=5)
        assert scorers == {}, scorers
        assert "kept NO player quotes" in note and "9.0h old" in note, note
        oa.event_cache_age = lambda *a, **k: 1800
        scorers, _lines, note, _oldest = cfb_build.attach_player_quotes(
            games, priced, cache_only=True, api_key="k", now=t, cap=5)
        assert scorers and "kept NO player quotes" not in note, note
    finally:
        oa.fetch_event_odds, oa.event_cache_age = real


def test_the_nfl_build_reports_the_prop_refusals_too():
    nfl = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "event_stale_prop_events=res.stale_prop_events" in nfl
    assert "kept NO player" in nfl and "QB_MAX_PROP_PRICE_AGE" in nfl


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
