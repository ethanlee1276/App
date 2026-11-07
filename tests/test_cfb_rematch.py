"""College had the same bug, and was never even asked the question.

The NFL's wrong moneylines on 2026-09-09 came from a season-long odds
payload matching a Week 1 slate game to that pair's REMATCH, keyed on a
`frozenset` that does not care which side is home. Fixed in both of
`oddsapi`'s appliers the same evening.

`cfb_build.attach_odds` calls none of them. It has its own loop, with the
same `frozenset` lookup — and NO DATE CHECK AT ALL, where the NFL path at
least had one (inert, but present). One request returns the WHOLE SEASON,
so a September Saturday could be priced from a December fixture and
nothing in the note would say so.

The collision is rarer in college, and that is worth stating honestly:
most FBS pairs meet once, so the frozenset usually finds the only event
there is. But a conference title game is a rematch of a regular-season
meeting, a bowl can be too, and when it happens the failure is silent in
exactly the way the NFL's was —

    entry["moneyline"] = (mls[home], mls[away])

is written as the EVENT's home and away and read downstream as the SLATE
game's, so a reversed fixture does not read as a mismatch. It reads as an
ordinary price on the wrong team.

Both rules come from `oddsapi` rather than being written a second time
here. `other_day` already carried "ONE DEFINITION, TWO CALLERS" in its
docstring for exactly this reason; this is the third.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cfb_build                                             # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402


def _game(home="BAMA", away="AUB", date="2026-09-12"):
    return {"home": home, "away": away, "date": date,
            "kickoff": f"{date}T23:30:00Z", "game_id": "g1"}


def _ev(home, away, when, home_price, away_price):
    return {"id": "e1", "home_team": home, "away_team": away,
            "commence_time": when,
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": home, "price": home_price},
                                {"name": away, "price": away_price}]}]}]}


LOOKUP = {"alabama": "BAMA", "auburn": "AUB"}


def _attach(events, games=None, monkey=True):
    games = games if games is not None else [_game()]
    real_fetch = O.fetch_sport_odds
    real_age = O.sport_cache_age
    real_resolve = cfb_build.cfbdata.resolve_team
    O.fetch_sport_odds = lambda *a, **k: (events, O.Quota())
    O.sport_cache_age = lambda *a, **k: 600.0
    cfb_build.cfbdata.resolve_team = lambda name, lk: LOOKUP.get(
        str(name).strip().lower())
    try:
        return cfb_build.attach_odds(games, LOOKUP, cache_only=True)
    finally:
        O.fetch_sport_odds = real_fetch
        O.sport_cache_age = real_age
        cfb_build.cfbdata.resolve_team = real_resolve


THIS_WEEK = _ev("Alabama", "Auburn", "2026-09-12T23:30:00Z", -300, 240)
TITLE_GAME = _ev("Auburn", "Alabama", "2026-12-05T20:00:00Z", -140, 120)


def test_this_saturday_is_priced_from_this_saturday():
    """Both fixtures are in the payload, exactly as one request returns
    them, and the rematch is listed SECOND so a last-one-wins would take
    it."""
    priced, note = _attach([THIS_WEEK, TITLE_GAME])
    assert priced["g1"]["moneyline"] == (-300, 240), priced["g1"]["moneyline"]


def test_the_december_fixture_alone_prices_nothing():
    """No price beats a wrong price, and a real price on the wrong team
    is the worst of the three because it reads as ordinary."""
    priced, note = _attach([TITLE_GAME])
    assert priced == {}, priced


def test_the_refusal_is_in_the_note_not_swallowed():
    """This function's own docstring says an unmatched school is counted
    "rather than silently dropped — a board that quietly prices 40 of 60
    games looks exactly like a light Saturday". A fixture refused for
    being another week's is the same kind of fact."""
    _priced, note = _attach([TITLE_GAME])
    assert "another week" in note, note


def test_a_same_week_rematch_is_caught_by_the_orientation_bar():
    """The date cannot separate two fixtures on the same weekend — a
    neutral-site rematch, or a payload that dates one loosely — so the
    orientation check is what is left. Here the reversed fixture kicks
    off on the slate's own day."""
    same_day = _ev("Auburn", "Alabama", "2026-09-12T20:00:00Z", -140, 120)
    priced, note = _attach([same_day])
    assert priced == {}, priced
    assert "the other meeting of the same pair" in note, note


def test_the_rules_are_the_ones_the_nfl_paths_use():
    """Written a second time here, the two football leagues drift apart
    the first time either is corrected — which is how college ended up
    with a bug the NFL had already been fixed for."""
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert "oddsapi.slate_days(games)" in src
    assert "oddsapi.other_day(ev, days)" in src
    assert "oddsapi.same_meeting(home, away, game)" in src


def test_the_shared_rules_read_a_dict_as_well_as_an_object():
    """The NFL slate holds `engine.models.Game` objects and the college
    one holds plain dicts. A rule that only reads attributes is a rule
    college silently does not get."""
    assert "2026-09-12" in O.slate_days([_game()])
    assert O.same_meeting("BAMA", "AUB", _game()) is True
    assert O.same_meeting("AUB", "BAMA", _game()) is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
