"""The day's pick is never named off a price past the freshness bar.

Found reviewing the game lines of 2026-10-14 (Ethan: "yes I like that",
to checking today's Pick of the Day code before the first basketball or
hockey pick is recorded; a recorded pick cannot be taken back).

The odds pull dates every game price. Past `oddsapi.MAX_GAME_PRICE_AGE`
(six hours) a game is still SHOWN, marked `price_stale`, and NEVER
RECOMMENDED: the NFL pipeline and the college build both keep that
promise on their cards. `potd.game_lines` read the prices and not the
mark, and the selector itself never asked how old any price was, in any
league: a cached payload up to two days old could have named the day's
pick, the strongest recommendation on the site, and recorded it.

Now the game lines carry `price_age_s` and `price_stale`, and `disqualify`
refuses a stale price by either sign (`potd.STALE_PRICE`), for every
league's rows: the Most Likely game rows carry their price's age too.
And the game lines date a row by the game's own date where the slate game
has one, so a game from another day cannot pass as today's.

Run directly: `python3 tests/test_the_days_pick_never_takes_a_stale_price.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import potd                                       # noqa: E402
from engine.sources import oddsapi                            # noqa: E402

HOURS = 3600.0


class _Game:
    """A slate game as the builds' `_Game` carries one after the odds pull."""

    def __init__(self, home="BOS", away="NYK", **kw):
        self.home, self.away = home, away
        self.kickoff = _kickoff(180)[1]
        self.live = None
        self.spread = self.total = None
        self.home_ml = self.away_ml = 0
        for k, v in kw.items():
            setattr(self, k, v)


def _priced(**kw):
    """Pinnacle has the home side 58% (-150 / +130); DraftKings pays -130:
    a bet on every bar, whatever its age."""
    g = dict(sharp_home_ml=-150, sharp_away_ml=130, home_ml=-130, away_ml=120,
             home_ml_book="DraftKings", away_ml_book="FanDuel")
    g.update(kw)
    return _Game(**g)


def _day():
    return _kickoff(180)[0]


def _named(game, sport="nba"):
    out = {"date": _day(), "most_likely": []}
    potd.attach(out, sport, built_dir=tempfile.mkdtemp(), lines=potd.game_lines([game], _day()))
    return out["pick_of_the_day"]


def test_a_fresh_price_still_names_the_pick():
    card = _named(_priced(price_age_s=300.0, price_stale=False))
    assert card["verdict"]["call"] == "bet" and card["pick"]["team"] == "BOS", card


def test_the_game_lines_carry_the_price_age_and_mark():
    rows = potd.game_lines([_priced(price_age_s=7 * HOURS, price_stale=True)], _day())
    assert rows and all(r["price_age_s"] == 7 * HOURS and r["price_stale"] for r in rows), rows
    fresh = potd.game_lines([_priced()], _day())
    assert all(r["price_age_s"] is None and r["price_stale"] is False for r in fresh), \
        "a game the pull never dated reads as just fetched, as the odds pull reads it"


def test_a_price_marked_stale_never_names_the_pick():
    card = _named(_priced(price_age_s=7 * HOURS, price_stale=True))
    assert card["pick"] is None and card["verdict"]["call"] != "bet", card
    assert card["census"].get(potd.STALE_PRICE) == 2, card["census"]


def test_an_old_price_without_the_mark_is_refused_by_its_age():
    """The Most Likely game rows carry the age and not the mark."""
    over = oddsapi.MAX_GAME_PRICE_AGE + 60
    row = dict(potd.game_lines([_priced()], _day())[0], price_age_s=over, price_stale=False)
    assert potd.disqualify(row) == potd.STALE_PRICE
    assert potd.disqualify(dict(row, price_age_s=oddsapi.MAX_GAME_PRICE_AGE - 60)) == ""
    assert potd.disqualify(dict(row, price_age_s=None)) == ""
    assert potd.disqualify(dict(row, price_age_s="soon")) == "", "an unreadable age is not a stale one"


def test_every_league_is_held_to_it():
    """A Most Likely game row from a board with measured game markets (a
    baseball run line here, since baseball plays every day), sharp-anchored
    and in every band, two days old: refused the same way, and fresh it is
    the pick."""
    d, k = _kickoff(180)
    row = {"kind": "game", "player": "NYY -1.5", "team": "NYY", "opponent": "BOS",
           "home": "NYY", "away": "BOS", "market": "spread", "bet_type": "spread",
           "side": "-1.5", "line": -1.5, "book": "DraftKings", "odds": +105,
           "sharp_anchored": True, "sharp_fair": 0.52, "model_prob": 0.53,
           "implied_prob": 0.488, "rank_auc": 0.7, "bettable": True, "injury_status": "",
           "game_date": d, "kickoff": k, "price_age_s": 47 * HOURS}
    assert potd.disqualify(row) == potd.STALE_PRICE
    got = potd.build([row], "mlb", d)
    assert got["pick"] is None and got["census"] == {potd.STALE_PRICE: 1}, got
    fresh = potd.build([dict(row, price_age_s=600.0)], "mlb", d)
    assert fresh["pick"] is not None and fresh["pick"]["team"] == "NYY", fresh


def test_a_game_from_another_day_is_dated_by_its_own_date():
    tomorrow = _priced(date="2099-01-02")
    rows = potd.game_lines([tomorrow], _day())
    assert {r["game_date"] for r in rows} == {"2099-01-02"}, rows
    assert all(potd.disqualify(r) == "the game is not today" for r in rows)
    assert {r["game_date"] for r in potd.game_lines([_priced()], _day())} == {_day()}, \
        "a slate game with no date of its own is the build's day, as before"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
