"""A prop takes its price from its own game, or takes none.

Ethan, 2026-09-15: "we are showing props for players not even on the
team any more. Isaiah pachaceo is on the lions now, not the chiefs."

Two things put him on the Chiefs' board. `nflverse.build_slate.team_of`
read the first stat row of the season before it asked the roster
(tests/test_nflverse.py pins the fix). And `apply_odds_to_slate` keys
its price index by name and market across EVERY event on the pull, so a
man filed under his old team was handed his new team's price: a card
for a game he was not playing in, priced off the game he was. The
index still merges by name — that is right for everyone who is where
the slate says — but `menu` remembers which event priced each key, and
a price from a game the prop's team is not in is now refused, counted
on the result (`wrong_game`), and the prop stays proxy.

Run directly: `python3 tests/test_price_from_own_game.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa                     # noqa: E402
from engine.models import (Team, DefenseProfile, Weather, Game, Prop, GameLog,  # noqa: E402
                           SportsbookLine, RUSH_YDS, ANYTIME_TD)
from engine.data_loader import Slate                         # noqa: E402

NAME = "Isiah Pacheco"


def _book(key, title, rush=(60.5, -110, -110), td=300):
    return {"key": key, "title": title, "markets": [
        {"key": "player_rush_yds", "outcomes": [
            {"name": "Over", "description": NAME, "price": rush[1], "point": rush[0]},
            {"name": "Under", "description": NAME, "price": rush[2], "point": rush[0]}]},
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": NAME, "price": td}]},
        {"key": "h2h", "outcomes": [{"name": "Detroit Lions", "price": -150},
                                    {"name": "Green Bay Packers", "price": 130}]}]}


LIONS_GAME = {"id": "e-det", "home_team": "Detroit Lions", "away_team": "Green Bay Packers",
              "bookmakers": [_book("draftkings", "DraftKings"), _book("fanduel", "FanDuel")]}
CHIEFS_GAME = {"id": "e-kc", "home_team": "Kansas City Chiefs", "away_team": "Denver Broncos",
               "bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": [
                   {"key": "h2h", "outcomes": [{"name": "Kansas City Chiefs", "price": -200},
                                               {"name": "Denver Broncos", "price": 170}]}]}]}


def _slate(team, opponent, market=RUSH_YDS):
    teams = {t: Team(t, t, DefenseProfile(t)) for t in ("KC", "DEN", "DET", "GB")}
    games = [Game(home="KC", away="DEN", weather=Weather(dome=False), spread=-3.5, total=47.0),
             Game(home="DET", away="GB", weather=Weather(dome=True), spread=-2.5, total=49.5)]
    logs = [GameLog(week=w, opponent="X", value=60) for w in range(1, 6)]
    prop = Prop(player=NAME, team=team, opponent=opponent, position="RB",
                market=market, logs=logs, career_avg=58, vs_opponent_avg=None,
                lines=([SportsbookLine(book="proxy", line=55.0)]
                       if market == RUSH_YDS else []),
                usage_role="rb1")
    return Slate(date="2026-W02", teams=teams, games=games, props=[prop])


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val
    def __enter__(self):
        self.old = getattr(self.obj, self.name); setattr(self.obj, self.name, self.val)
    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def _attach(slate):
    events = {"e-det": LIONS_GAME, "e-kc": CHIEFS_GAME}

    def fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False):
        return events[eid], oa.Quota("491", "9")
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: list(events.values())), \
            _Swap(oa, "fetch_event_odds", fetch):
        return oa.apply_odds_to_slate(slate, api_key="k")


def test_a_price_from_another_game_is_refused_and_counted():
    slate = _slate("KC", "DEN")
    res = _attach(slate)
    prop = slate.props[0]
    assert res.wrong_game == 1, res.wrong_game
    assert res.matched == 0
    assert [ln.book for ln in prop.lines] == ["proxy"], "the Lions' price reached the Chiefs' card"
    assert prop.sharp_lines == [] if hasattr(prop, "sharp_lines") else True


def test_the_same_price_attaches_when_he_is_filed_where_the_book_prices_him():
    slate = _slate("DET", "GB")
    res = _attach(slate)
    prop = slate.props[0]
    assert res.wrong_game == 0 and res.matched == 1, (res.wrong_game, res.matched)
    assert sorted(ln.book for ln in prop.lines) == ["DraftKings", "FanDuel"]


def test_a_scorer_quote_from_another_game_is_refused_too():
    slate = _slate("KC", "DEN", market=ANYTIME_TD)
    res = _attach(slate)
    assert res.wrong_game == 1 and res.scorers_matched == 0, (res.wrong_game, res.scorers_matched)
    assert slate.props[0].lines == []
    slate = _slate("DET", "GB", market=ANYTIME_TD)
    res = _attach(slate)
    assert res.wrong_game == 0 and res.scorers_matched == 1, (res.wrong_game, res.scorers_matched)
    assert [ln.over_odds for ln in slate.props[0].lines] == [300, 300]


def test_a_prop_with_no_team_is_never_refused():
    """An MLB slate built from the book's own menu carries no team on
    some props; nothing to check against means nothing refused."""
    class P:
        team = ""
    assert oa._wrong_game(P(), ("DET", "GB")) is False
    class Q:
        team = "KC"
    assert oa._wrong_game(Q(), None) is False
    assert oa._wrong_game(Q(), ("", "")) is False
    assert oa._wrong_game(Q(), ("DET", "GB")) is True
    assert oa._wrong_game(Q(), ("KC", "DEN")) is False


def test_the_build_says_so():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "nfl_build.py")).read()
    assert "if res.wrong_game:" in src and "Refused {res.wrong_game} price(s)" in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
