"""The likelihood board is offered every quoted scorer, not the page's five.

Ethan, 2026-09-08, the day after the ladder fix put player props back
on the NFL Most Likely board: "Ok it seems like we have player props
just barley any money money lines are touchdown crap so maybe we should
look into that for the NFL most likely bets."

THE TOUCHDOWN HALF. `touchdowns.td_watchlist` defaults to
TD_WATCH_LIMIT — five — because the Long Shots page shows five
most-likely scorers under its value picks. `pipeline._long_shots` fed
that same five to the likelihood board, whose own seating is
`likely.PER_MARKET` (eight) touchdown rows above a 55% floor and under
a -250 price cap. Five offered, one of them the -260 bell cow the cap
refuses, the floor taking its share, and a Sunday with seven backs at
-200 showed three or four of them while the rest were never handed in.

The fix is where the number belongs: the board is offered the WHOLE
ranked menu and applies its own floor, cap and per-market cut; the Long
Shots page takes its five off the top where the payload is assembled.

What this pins, on a slate of eight priced scorers — six at -200 over
the floor, one at -260 past the cap, one at +140 under the floor:

  * `_long_shots` returns all eight, ranked by the shown probability;
  * `run_slate` publishes `longshot_watch` as the first five of that
    list (the page's shelf, unchanged in size and order);
  * the Most Likely board carries the six -200 backs — more rows than
    the page's shelf holds — and the census names the one the cap took.

Run directly: `python3 tests/test_td_watch_feeds_the_board.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import (Game, Weather, Team, DefenseProfile, Prop,   # noqa: E402
                           GameLog, SportsbookLine, ANYTIME_TD, RUSH_YDS,
                           REC_YDS)
from engine.data_loader import Slate                                    # noqa: E402
from engine.pipeline import _long_shots, run_slate                      # noqa: E402
from engine.touchdowns import TD_WATCH_LIMIT                            # noqa: E402
from engine.likely import MIN_PROB, HEAVIEST_PRICE, PER_MARKET          # noqa: E402

#: (price, under price) for each of the eight backs, in slate order.
PRICES = [(-200, 160)] * 6 + [(-260, 200), (140, -170)]


def _slate():
    """Eight games, one bell cow each: half his team's volume (the rush
    line beside a receiver's), a touchdown in every game on file, and a
    real DraftKings scorer price."""
    teams, games, props = {}, [], []
    for i, (over, under) in enumerate(PRICES):
        h, a = f"H{i}", f"A{i}"
        teams[h] = Team(h, h, DefenseProfile(h))
        teams[a] = Team(a, a, DefenseProfile(a))
        games.append(Game(home=h, away=a, weather=Weather(dome=True),
                          spread=-7.5, total=48.5, date="2026-09-13",
                          kickoff="13:00"))
        back, wide = f"Back {i}", f"Wide {i}"
        props.append(Prop(player=back, team=h, opponent=a, position="RB",
                          market=RUSH_YDS,
                          logs=[GameLog(week=w, opponent="X", value=95.0) for w in range(1, 9)],
                          career_avg=90, vs_opponent_avg=None,
                          lines=[SportsbookLine(book="proxy", line=90.5)]))
        props.append(Prop(player=wide, team=h, opponent=a, position="WR",
                          market=REC_YDS,
                          logs=[GameLog(week=w, opponent="X", value=60.0) for w in range(1, 9)],
                          career_avg=60, vs_opponent_avg=None,
                          lines=[SportsbookLine(book="proxy", line=60.5)]))
        props.append(Prop(player=back, team=h, opponent=a, position="RB",
                          market=ANYTIME_TD,
                          logs=[GameLog(week=w, opponent="X", value=1.0) for w in range(1, 9)],
                          career_avg=0, vs_opponent_avg=None,
                          lines=[SportsbookLine(book="DraftKings", line=0.5,
                                                over_odds=over, under_odds=under)]))
    return Slate(date="2026-09-13", teams=teams, games=games, props=props)


def test_the_fixture_is_the_shape_the_complaint_had():
    """Six over the floor and under the cap, one past the cap, one under
    the floor — and more over-the-floor rows than the page's five."""
    _picks, watch = _long_shots(_slate())
    by = {w["player"]: w for w in watch}
    over = [p for p, w in by.items() if w["model_prob"] >= MIN_PROB]
    assert len(over) == 7 and "Back 7" not in over, sorted(over)
    assert by["Back 6"]["odds"] < HEAVIEST_PRICE, "the -260 is the cap's row"
    assert 7 - 1 > TD_WATCH_LIMIT, "the fixture no longer exceeds the page's shelf"
    assert 6 <= PER_MARKET, "the board seats fewer scorers than the fixture offers"


def test_the_menu_handed_to_the_board_is_every_quoted_scorer():
    _picks, watch = _long_shots(_slate())
    assert len(watch) == len(PRICES) > TD_WATCH_LIMIT, [w["player"] for w in watch]
    probs = [w["model_prob"] for w in watch]
    assert probs == sorted(probs, reverse=True), "the menu is not ranked"
    assert watch[0]["player"] == "Back 6", "the heaviest price ranks first"
    assert watch[-1]["player"] == "Back 7", "the plus price ranks last"


def test_the_page_keeps_its_five_and_the_board_seats_six():
    out = run_slate(_slate())
    shelf = out["longshot_watch"]
    assert len(shelf) == TD_WATCH_LIMIT, [w["player"] for w in shelf]
    _picks, watch = _long_shots(_slate())
    assert [w["player"] for w in shelf] == [w["player"] for w in watch[:TD_WATCH_LIMIT]], \
        "the page's shelf is not the top of the same ranked menu"
    td = [r for r in out["most_likely"] if r.get("kind") == "td"]
    assert len(td) == 6 > TD_WATCH_LIMIT, [(r["player"], r["odds"]) for r in td]
    assert {r["player"] for r in td} == {f"Back {i}" for i in range(6)}
    assert all(r["odds"] == -200 and r["model_prob"] >= MIN_PROB for r in td)
    census = out["likely_census"]
    assert census.get(f"heavier than {HEAVIEST_PRICE} — chalk, not a pick") == 1, census


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
