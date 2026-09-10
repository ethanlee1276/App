"""The alternate ladders are bought, parsed apart, and carried on the prop.

Ethan, 2026-09-07, after the Most Likely census read 303 prop rows, 215
under the floor, none shown: "i prefer to do whatever gives us props and
picks every single day ready for every game at least 3 hours before."

A main line is hung where the book thinks the coin is fair, so a
calibrated probability at it sits near 50% and a board asking for 55%
at a price no heavier than -250 has nothing to show. The rungs — the
same stat at the other numbers the same books hang — are where a 60-70%
event is actually for sale. Pinned here:

  * the four `_alternate` markets are on the NFL and college event
    calls, and the per-event price the pacer meters rose with them;
  * a rung is parsed with its own map and lands on `Prop.alt_lines`,
    never in `Prop.lines`, so line shopping still shops the main number;
  * the sharp book's rungs ride beside them;
  * on the day the ladders first ship, a cached rebuild falls back to
    the last paid pull's base-market payload instead of a board of
    proxies;
  * the published row carries the ladder.

Run directly: `python3 tests/test_alt_lines.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa                     # noqa: E402
from engine import oddsbudget as B                           # noqa: E402
from engine.models import (Team, DefenseProfile, Weather, Game, Prop, GameLog,  # noqa: E402
                           SportsbookLine, RUSH_YDS, PASS_YDS, REC_YDS, RECEPTIONS)
from engine.data_loader import Slate                         # noqa: E402


def _mk(key, title, main, alts):
    """One bookmaker: a main rush-yards line and a ladder of rungs."""
    return {"key": key, "title": title, "markets": [
        {"key": "player_rush_yds", "outcomes": [
            {"name": "Over", "description": "Josh Jacobs", "price": main[1], "point": main[0]},
            {"name": "Under", "description": "Josh Jacobs", "price": main[2], "point": main[0]}]},
        {"key": "player_rush_yds_alternate", "outcomes": [
            o for pt, ov, un in alts for o in (
                [{"name": "Over", "description": "Josh Jacobs", "price": ov, "point": pt}]
                + ([{"name": "Under", "description": "Josh Jacobs", "price": un, "point": pt}]
                   if un else []))]},
        {"key": "h2h", "outcomes": [{"name": "Green Bay Packers", "price": -150},
                                    {"name": "Chicago Bears", "price": 130}]}]}


EVENT = {"id": "e1", "home_team": "Green Bay Packers", "away_team": "Chicago Bears",
         "bookmakers": [
             _mk("draftkings", "DraftKings", (62.5, -110, -110),
                 [(40.5, -240, 0), (50.5, -160, 0), (75.5, 150, 0)]),
             _mk("fanduel", "FanDuel", (63.5, -105, -115),
                 [(40.5, -230, 180), (50.5, -155, 125)]),
             _mk("pinnacle", "Pinnacle", (62.5, -112, -108),
                 [(50.5, -165, 140)])]}


def test_the_four_ladders_are_on_the_call_and_priced_into_the_pull():
    assert set(oa.ALT_ODDS_TO_MARKET.values()) == {PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS}
    assert all(k.endswith("_alternate") for k in oa.ALT_ODDS_TO_MARKET)
    for sport in ("nfl", "cfb"):
        assert oa.SPORT_CONFIG[sport]["alternates"] is oa.ALT_ODDS_TO_MARKET, sport
    for sport in ("mlb", "nba", "wnba", "ufc"):
        assert not oa.SPORT_CONFIG[sport].get("alternates"), sport
    # 5 props + 1 scorer + 3 game markets + 4 ladders, per event per
    # region. Five since 2026-09-10, when the NFL added
    # `player_pass_tds` (engine/passtd.py); college stayed at four,
    # measured out.
    #
    # DERIVED, NOT REPEATED. The literal 12 was written beside this sum
    # and both had to be edited together, which is one edit too many —
    # the budget's job is to equal what the config asks for, and that is
    # the assertion.
    cfg = oa.SPORT_CONFIG["nfl"]
    n = len(cfg["markets"]) + len(cfg["scorers"]) + len(cfg["alternates"]) + 3
    assert n == B.credits_per_event("nfl") == B.EVENT_CREDITS["nfl"], n
    assert len(cfg["markets"]) == 5, "the NFL should be buying five prop markets"
    # Baseball buys no ladders and keeps the generic price; the cheap
    # lines lane spends the NFL's money at the NFL's price.
    assert B.credits_per_event("mlb") == B.CREDITS_PER_EVENT == 8
    # The lines lane spends the SPORT'S money (`budget_sport`), so it
    # answers the sport's own event price — not a price of its own.
    assert B.credits_per_event("nfl_lines") == B.EVENT_CREDITS["nfl"]
    assert B.credits_per_event(None) == 8
    src = inspect.getsource(oa.apply_odds_to_slate)
    assert "+ list(alt_map)" in src, "the ladders are not on the request"


def test_a_rung_is_parsed_with_its_own_map_and_never_into_the_shopped_field():
    main = oa.parse_event_lines(EVENT)
    alts = oa.parse_event_lines(EVENT, oa.ALT_ODDS_TO_MARKET)
    key = ("josh jacobs", RUSH_YDS)
    # The main parse sees exactly the main lines.
    assert sorted((ln.book, ln.line) for ln in main[key]) == \
        [("DraftKings", 62.5), ("FanDuel", 63.5)]
    # The ladder parse sees the rungs, over-only rungs with 0 for the
    # missing side, never a fabricated under.
    got = sorted((ln.book, ln.line, ln.over_odds, ln.under_odds) for ln in alts[key])
    assert got == [("DraftKings", 40.5, -240, 0), ("DraftKings", 50.5, -160, 0),
                   ("DraftKings", 75.5, 150, 0),
                   ("FanDuel", 40.5, -230, 180), ("FanDuel", 50.5, -155, 125)], got
    # The sharp book's rung, apart.
    sharp = oa.parse_event_sharp_lines(EVENT, oa.ALT_ODDS_TO_MARKET)
    assert [(ln.book, ln.line, ln.over_odds, ln.under_odds) for ln in sharp[key]] == \
        [("Pinnacle", 50.5, -165, 140)]


def _slate():
    teams = {"GB": Team("GB", "GB", DefenseProfile("GB")),
             "CHI": Team("CHI", "CHI", DefenseProfile("CHI"))}
    game = Game(home="GB", away="CHI", weather=Weather(dome=False), spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=70) for w in range(1, 6)]
    prop = Prop(player="Josh Jacobs", team="GB", opponent="CHI", position="RB",
                market=RUSH_YDS, logs=logs, career_avg=68, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=65.0)], usage_role="rb1")
    return Slate(date="2026-W02", teams=teams, games=[game], props=[prop])


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val
    def __enter__(self):
        self.old = getattr(self.obj, self.name); setattr(self.obj, self.name, self.val)
    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def test_the_attach_step_puts_the_ladder_on_the_prop_and_shops_the_main_line():
    asked = {}

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False):
        asked["markets"] = list(markets or [])
        return EVENT, oa.Quota("491", "9")
    slate = _slate()
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: [EVENT]), \
            _Swap(oa, "fetch_event_odds", fake_fetch):
        res = oa.apply_odds_to_slate(slate, api_key="k")
    assert set(oa.ALT_ODDS_TO_MARKET) <= set(asked["markets"]), asked
    prop = slate.props[0]
    assert res.matched == 1 and res.alt_matched == 1 and res.alt_fallback == 0
    # The shopped field is the main number only…
    assert sorted(ln.line for ln in prop.lines) == [62.5, 63.5]
    from engine.odds import best_over_line
    assert best_over_line(prop.lines).line == 62.5
    # …and the ladder is beside it, sharp rungs apart.
    assert sorted({ln.line for ln in prop.alt_lines}) == [40.5, 50.5, 75.5]
    assert all(ln.book != "Pinnacle" for ln in prop.alt_lines)
    assert [(ln.book, ln.line) for ln in prop.alt_sharp_lines] == [("Pinnacle", 50.5)]
    assert [(ln.book, ln.line) for ln in prop.sharp_lines] == [("Pinnacle", 62.5)]


def test_a_cached_rebuild_falls_back_to_the_base_payload_on_deploy_day():
    """The cache file is named by the market list. The first cached
    rebuild after the ladders ship finds nothing under the new name and
    the last paid pull's payload under the old one; it serves that
    rather than a board of proxies."""
    calls = []

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False):
        calls.append((list(markets or []), cache_only))
        if any(m.endswith("_alternate") for m in (markets or [])):
            raise oa.OddsAPIError("no cached payload for that request")
        base = {**EVENT, "bookmakers": [
            {**bm, "markets": [m for m in bm["markets"]
                               if not m["key"].endswith("_alternate")]}
            for bm in EVENT["bookmakers"]]}
        return base, oa.Quota("491", "9")
    slate = _slate()
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: [EVENT]), \
            _Swap(oa, "fetch_event_odds", fake_fetch):
        res = oa.apply_odds_to_slate(slate, api_key="k", cache_only=True)
    assert len(calls) == 2 and calls[1][1] is True
    assert not any(m.endswith("_alternate") for m in calls[1][0])
    assert res.matched == 1 and res.alt_fallback == 1 and res.cache_misses == 0
    assert slate.props[0].lines and slate.props[0].alt_lines == []
    # A LIVE pull never falls back: a failed paid call raises as before.
    def dead(*a, **k):
        raise oa.OddsAPIError("down")
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: [EVENT]), \
            _Swap(oa, "fetch_event_odds", dead):
        try:
            oa.apply_odds_to_slate(_slate(), api_key="k")
        except oa.OddsAPIError:
            pass
        else:
            raise AssertionError("a failed paid pull must still raise")


def test_college_buys_the_same_ladders_and_attaches_them_apart():
    import cfb_build as CB
    from engine.cfb import props as P
    assert [m for m in CB.PLAYER_MARKETS if m.endswith("_alternate")] == list(oa.ALT_ODDS_TO_MARKET)
    assert CB.CREDITS_PER_EVENT == 9
    src = inspect.getsource(CB.attach_player_quotes)
    assert "markets=PLAYER_MARKETS_BASE" in src, "no deploy-day fallback on the college pull"
    assert "parse_event_lines(payload, _alt_map)" in src
    slate = _slate()
    key = ("josh jacobs", RUSH_YDS)
    main = oa.parse_event_lines(EVENT)
    alts = oa.parse_event_lines(EVENT, oa.ALT_ODDS_TO_MARKET)
    alts_sharp = oa.parse_event_sharp_lines(EVENT, oa.ALT_ODDS_TO_MARKET)
    matched, total = P.attach_lines(slate, main, sharp={}, alt=alts, alt_sharp=alts_sharp)
    assert (matched, total) == (1, 1)
    prop = slate.props[0]
    assert sorted(ln.line for ln in prop.lines) == [62.5, 63.5]
    assert sorted({ln.line for ln in prop.alt_lines}) == [40.5, 50.5, 75.5]
    assert [ln.line for ln in prop.alt_sharp_lines] == [50.5]
    # The launcher's Saturday estimate rose with the price.
    import launch
    assert launch.CFB_ODDS_COST == 3 + CB.PLAYER_EVENT_CAP * CB.CREDITS_PER_EVENT == 111
    assert key in alts


def test_the_published_row_carries_the_ladder():
    from engine.pipeline import _rec_to_dict
    from engine.betting import evaluate_prop
    from engine.projection import build_projection
    from engine.rules import apply_rules
    slate = _slate()
    prop = slate.props[0]
    prop.lines = oa.parse_event_lines(EVENT)[("josh jacobs", RUSH_YDS)]
    prop.alt_lines = oa.parse_event_lines(EVENT, oa.ALT_ODDS_TO_MARKET)[("josh jacobs", RUSH_YDS)]
    prop.alt_sharp_lines = oa.parse_event_sharp_lines(EVENT, oa.ALT_ODDS_TO_MARKET)[("josh jacobs", RUSH_YDS)]
    game, opp = slate.game_for(prop), slate.team(prop.opponent)
    proj = build_projection(prop, game, opp)
    rec = evaluate_prop(prop, proj, game=game)
    d = _rec_to_dict(rec, prop, apply_rules(rec, prop, game), proj)
    assert sorted({r["line"] for r in d["alt_lines"]}) == [40.5, 50.5, 75.5]
    assert d["alt_lines"][0].keys() == {"book", "line", "over_odds", "under_odds"}
    assert [(r["book"], r["line"]) for r in d["alt_sharp_lines"]] == [("Pinnacle", 50.5)]
    assert sorted({r["line"] for r in d["all_lines"]}) == [62.5, 63.5]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
