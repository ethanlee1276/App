"""Week 12's prices were on the Week 1 card, wearing the wrong team's name.

Ethan, 2026-09-09, the day the season opened: "i wanna focus on those
moneyline props, they are still showing the wrong lines on the site like
before". `--ml-doctor` put four games side by side with the pull, and
every one of them was an exact price from the SAME PAIR'S REMATCH:

    GB @ MIN   board MIN -220 / GB +200    the Nov 15 MIN @ GB game
    WAS @ PHI  board PHI +121 / WAS -125   the Nov 1  PHI @ WAS game
    DAL @ NYG  board NYG -218 / DAL +180   the Jan 3  NYG @ DAL game
    SF  @ LA   board LA  +120 / SF  -130   the Dec 13 LA  @ SF game

Three of the four show the WRONG TEAM FAVOURED, which is his report from
2026-09-03 word for word: "none of these teams are favored to win on any
sports book."

THREE DEFECTS, and the first is what hid the other two.

  1. `slate_days` read `kickoff`, and an NFL kickoff is a bare Eastern
     clock — "20:20" — with the date two keys away in `date`. Sliced to
     ten characters that is five, so every football game was skipped and
     the set came back EMPTY. `other_day` returns False on an empty set,
     so the day filter was inert on both football paths all season.
  2. The day filter was only consulted for pairs NOT on the slate, which
     is backwards: a pair we DO carry is exactly the one a later fixture
     can be mistaken for.
  3. The lookup is `frozenset((home, away))` — orientation-blind by
     design, because the endpoint's idea of home is not ours to trust —
     and the ASSIGNMENT is positional on both paths. So a rematch does
     not read as a mismatch. It reads as an ordinary price on the wrong
     team.

The endpoint returns every fixture of the season in one payload, so the
September game and the November rematch are both in the file and both
match. The second one wins.

Run directly: `python3 tests/test_rematch_prices.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import oddsapi as O                      # noqa: E402


import json
import tempfile
import time

from engine.models import Game, Weather                      # noqa: E402


class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def _game(kickoff="20:25"):
    """The slate's Week 1 game: Green Bay at Minnesota.

    `kickoff` defaults to the BARE EASTERN CLOCK the NFL schedule
    actually carries — the shape that made `slate_days` return nothing.
    """
    return Game(home="MIN", away="GB", weather=Weather(),
                date="2026-09-13", kickoff=kickoff)


def _ev(home, away, when, home_price, away_price):
    return {"home_team": home, "away_team": away, "commence_time": when,
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": home, "price": home_price},
                                {"name": away, "price": away_price}]}]}]}


WEEK1 = _ev("Minnesota Vikings", "Green Bay Packers",
            "2026-09-13T20:25:00Z", -118, 102)
REMATCH = _ev("Green Bay Packers", "Minnesota Vikings",
              "2026-11-15T18:00:00Z", -220, 200)


def _apply(events, games=None):
    """Run the board-lines path over a payload on disk, no network."""
    slate = _Slate(games if games is not None else [_game()])
    tmp = tempfile.mkdtemp()
    real = O.CACHE_DIR
    O.CACHE_DIR = __import__("pathlib").Path(tmp)
    path = O.CACHE_DIR / "odds_board_nfl_lines.json"
    path.write_text(json.dumps(events))
    old = time.time() - 600
    os.utime(path, (old, old))
    try:
        res = O.apply_board_lines_to_slate(slate, api_key="k", cache_only=True)
    finally:
        O.CACHE_DIR = real
    return res, slate.games[0]


def test_a_football_slate_now_knows_which_days_it_covers():
    """DEFECT 1, and the one that made the rest invisible. An NFL kickoff
    is "20:25" with the date in `date`; read off `kickoff` alone the set
    is empty, and an empty set makes `other_day` answer False for every
    event in the file."""
    days = O.slate_days([_game()])
    assert days, "football slates had no days at all"
    assert "2026-09-13" in days
    # A day either side, because a 4:25pm Eastern kickoff is already
    # tomorrow in UTC.
    assert "2026-09-14" in days and "2026-09-12" in days
    assert "2026-11-15" not in days


def test_a_dated_kickoff_still_wins_where_one_exists():
    """The fallback must not displace a real timestamp — other sports
    carry a full ISO kickoff and their answer should be unchanged."""
    days = O.slate_days([_game(kickoff="2026-09-13T20:25:00Z")])
    assert "2026-09-13" in days and "2026-11-15" not in days


def test_the_day_filter_used_to_be_asked_only_about_pairs_we_lacked():
    """DEFECT 2. The rematch's pair IS on our slate — that is the whole
    problem — so a check that only ran for missing pairs could never
    have caught it."""
    days = O.slate_days([_game()])
    assert O.other_day(REMATCH, days) is True
    assert O.other_day(WEEK1, days) is False


def test_the_rematch_is_not_the_same_meeting():
    """DEFECT 3. Home and away are reversed in the rematch, which is
    exactly why the prices landed on the opposite teams."""
    g = _game()
    assert O.same_meeting("MIN", "GB", g) is True
    assert O.same_meeting("GB", "MIN", g) is False
    assert O.same_meeting("", "", g) is False


def test_the_board_prices_week_one_off_week_one():
    """END TO END on the path Ethan's numbers came through. Both events
    are in the payload exactly as the endpoint returns them, and the
    rematch is listed SECOND so a last-one-wins would take it."""
    res, g = _apply([WEEK1, REMATCH])
    assert (g.home_ml, g.away_ml) == (-118, 102), (g.home_ml, g.away_ml)
    assert res.moneylines == 1


def test_the_rematch_alone_prices_nothing():
    """The refusal has to be a refusal, not a fallback. A payload holding
    only the rematch must leave the game UNPRICED rather than priced
    backwards — no price beats a wrong price, and a real price on the
    wrong team is the worst of the three, because it reads as ordinary."""
    res, g = _apply([REMATCH])
    assert (g.home_ml, g.away_ml) == (0, 0), (g.home_ml, g.away_ml)
    assert res.moneylines == 0


def test_the_refusal_is_counted_rather_than_swallowed():
    """A silent refusal is the same failure with its sign flipped: an
    unpriced board with no reason attached sends the next reader looking
    at the books instead of at us."""
    res, _ = _apply([REMATCH])
    assert res.reversed_events + res.other_day_events == 1, res


def test_a_later_fixture_in_the_same_orientation_is_refused_on_its_date():
    """The mirror of the test below, isolating the OTHER bar. Same home,
    same away, a different week — so the orientation check has nothing to
    say and only the date separates them. This is the shape a baseball
    series has three of, and the shape a season-long football payload has
    whenever the endpoint lists a neutral-site or flexed rematch the same
    way round."""
    later = _ev("Minnesota Vikings", "Green Bay Packers",
                "2026-11-15T18:00:00Z", -220, 200)
    res, g = _apply([later])
    assert (g.home_ml, g.away_ml) == (0, 0), (g.home_ml, g.away_ml)
    assert res.other_day_events == 1, res


def test_the_orientation_bar_holds_when_the_day_filter_cannot():
    """A baseball series runs three games in the SAME orientation on
    three consecutive days, so `slate_days` — which spans a day either
    side — cannot separate them and the orientation check is what is
    left. Here the rematch is moved onto the slate's own weekend to take
    the day filter out of the picture."""
    same_day = _ev("Green Bay Packers", "Minnesota Vikings",
                   "2026-09-13T18:00:00Z", -220, 200)
    res, g = _apply([same_day])
    assert (g.home_ml, g.away_ml) == (0, 0), (g.home_ml, g.away_ml)
    assert res.reversed_events == 1, res


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
