"""The Lab said no closing lines were stored. There were 17,457.

`lab.game_lines` decided whether a market had anything to show with:

    if not getattr(r, "games_priced", 0):
        continue

`GameLineBacktest` has never had a `games_priced`. The field is
`games_quoted`. The `getattr` default turned that mistake into a silent
zero, so EVERY game-line market was skipped, for every sport, on every
run — and the Lab fell through to "no harvested closing lines stored for
this sport" on a database holding 17,457 MLB closes, 899 replayable NFL
games and 2,055 college ones. An AttributeError would have been loud on
the first run. The default made it invisible for the life of the feature.

Underneath it were two more:

* `backtest_game_lines` read the harvested closes and fell back to the
  schedule only when the harvest was COMPLETELY empty, so one stored row
  for one game hid the schedule's numbers for every other game.
  `engine.gamecal` had the identical bug and the identical fix.
* `schedule_closes` defaults to `require_prices=True`, and college
  football's 3,132 mirror closes carry a line and no price — so the CFB
  game model had thousands of stored closes and no way to be graded
  against a single one.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.cfb import ratings as _cfb          # noqa: F401  (registers cfb)
from engine.gamebacktest import GameLineBacktest, backtest_game_lines


def _games(conn, sport, n, spread=-3.0, total=44.0, with_line=True,
           priced=True):
    """Stored schedule closes. ``priced`` mirrors the real difference
    between the feeds: nflverse ships both prices beside the line in
    ``extra``; the cfbfastR mirror publishes every book's NUMBER and no
    -110s, so its closes arrive with a line and nothing else."""
    import json
    extra = json.dumps({"spread_odds": [-110, -110],
                        "total_odds": [-110, -110]}) if priced else None
    db.upsert_games(conn, [{
        # A DISTINCT DATE PER GAME, so `(period, home, away)` is unique
        # and a count of quoted games is unambiguous.
        "sport": sport, "season": 2025,
        "period": (dt.date(2025, 9, 1) + dt.timedelta(days=i)).isoformat(),
        "game_id": str(i), "home": f"H{i % 6}", "away": f"A{i % 6}",
        "home_score": 27.0 + (i % 7), "away_score": 20.0 + (i % 5),
        "extra": extra,
        "spread": spread if with_line else None,
        "total": total if with_line else None} for i in range(n)])


# --- the field name that hid everything --------------------------------------
def test_the_report_has_no_field_called_games_priced():
    """The name the Lab asked for. If it ever appears, the guard below
    stops meaning anything."""
    import dataclasses
    names = {f.name for f in dataclasses.fields(GameLineBacktest)}
    assert "games_priced" not in names
    assert "games_quoted" in names


def test_the_lab_reads_the_field_by_attribute_not_by_getattr_default():
    """A default is what turned a typo into a silent zero for the life of
    the feature. Attribute access fails loudly on the next rename."""
    import inspect
    from engine import lab
    src = inspect.getsource(lab.game_lines)
    assert "if not r.games_quoted:" in src
    assert 'getattr(r, "games_priced"' not in src
    assert 'getattr(r, "mae"' not in src
    assert 'getattr(r, "refused"' not in src


def test_a_replayable_sport_is_no_longer_reported_as_having_no_closes():
    from engine import lab
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120)
    out = lab.game_lines(conn, "nfl")
    assert "unavailable" not in out, out
    assert out["markets"], "the markets were skipped again"
    assert out["markets"][0]["games_quoted"] > 0


# --- the union ---------------------------------------------------------------
def _key(i):
    """The (period, home, away) `_games` gives game ``i`` — the same key
    both close sources are indexed by."""
    return ((dt.date(2025, 9, 1) + dt.timedelta(days=i)).isoformat(),
            f"H{i % 6}", f"A{i % 6}")


#: A game late enough that both its teams have the 15 prior games
#: `backtest_game_lines` requires before it will quote one.
QUOTED_GAME = 100


def _harvest_one(conn, i=QUOTED_GAME, market="total", line=44.5):
    """One stored book close for game ``i``, in the shape
    `game_line_closes` reads: book "best", both prices present."""
    date, home, away = _key(i)
    db.upsert_odds_history(conn, [{
        "sport": "nfl", "taken_at": f"{date}T23:00:00Z", "event_id": "x",
        "home": home, "away": away, "player": "over", "market": market,
        "book": "best", "line": line,
        "over_odds": -110, "under_odds": -110}])


def test_the_harvested_row_used_by_these_tests_really_does_join():
    """Guard on the fixture itself. The first version of it stored book
    "dk"; `game_line_closes` only reads "best", so the row never joined
    and the shadowing test below passed while proving nothing."""
    from engine.gamebacktest import game_line_closes
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120)
    _harvest_one(conn)
    assert _key(QUOTED_GAME) in game_line_closes(conn, "nfl", "total")


def test_one_harvested_row_does_not_hide_the_whole_schedule():
    """The shadowing bug, exactly: `if not closes` is false as soon as a
    single game has a stored book close, and every other game's schedule
    number then becomes unreachable."""
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120)
    before = backtest_game_lines(conn, "nfl", market="total").games_quoted
    assert before > 5, "premise: the schedule alone quotes many games"
    _harvest_one(conn)
    after = backtest_game_lines(conn, "nfl", market="total").games_quoted
    assert after == before, \
        f"a single harvested row hid the schedule: {before} quoted -> {after}"


def test_a_harvested_close_outranks_the_schedules_for_the_same_game():
    """A stored book close is a real counter's number; the schedule is a
    consensus. Where both exist the book wins."""
    from engine.gamebacktest import schedule_closes, game_line_closes
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120, total=44.0)
    _harvest_one(conn, line=51.5)
    sched = schedule_closes(conn, "nfl", "total", require_prices=False)
    key = _key(QUOTED_GAME)
    assert sched[key][0] == 44.0
    merged = dict(sched)
    merged.update(game_line_closes(conn, "nfl", "total"))
    assert merged[key][0] == 51.5


def test_the_source_names_both_when_both_contributed():
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120)
    assert backtest_game_lines(conn, "nfl", market="total").source == \
        "schedule closes · nflverse closing consensus"
    _harvest_one(conn)
    both = backtest_game_lines(conn, "nfl", market="total").source
    assert both.startswith("real stored closes"), \
        "the harvest leads, because it is the stronger claim"
    assert "nflverse closing consensus" in both, \
        "and the consensus it was topped up from is still named"


def test_the_schedule_feed_is_named_per_sport():
    """"nflverse" was hardcoded into the header. That was right for the
    only sport that had schedule closes, and became a false label the day
    college football's arrived off the cfbfastR mirror — a report that
    misnames its provenance is how an edge over the field gets read as an
    edge over a counter."""
    from engine.gamebacktest import SCHEDULE_FEED
    conn = db.connect(":memory:")
    _games(conn, "cfb", 200, spread=-7.0, total=55.0, priced=False)
    assert SCHEDULE_FEED["cfb"] in \
        backtest_game_lines(conn, "cfb", market="spread").source
    assert "nflverse" not in \
        backtest_game_lines(conn, "cfb", market="spread").source


# --- a close with no price ---------------------------------------------------
def test_a_priceless_close_still_measures_the_line():
    """College football's mirror closes are all priceless. Under the old
    default the CFB game model had 3,132 stored closes and could be
    graded against none of them."""
    conn = db.connect(":memory:")
    _games(conn, "cfb", 200, spread=-7.0, total=55.0,
           priced=False)
    r = backtest_game_lines(conn, "cfb", market="spread")
    assert r.games_quoted > 0
    assert r.unpriced == r.games_quoted, "these closes carry no price"
    assert r.mae > 0, "the line accuracy is the half that needs no price"


def test_a_priceless_close_never_becomes_a_bet():
    """The pricer raises on a None price, and defaulting it to -110 would
    publish an ROI against a number no book ever offered."""
    conn = db.connect(":memory:")
    _games(conn, "cfb", 200, spread=-7.0, total=55.0,
           priced=False)
    r = backtest_game_lines(conn, "cfb", market="spread")
    assert r.n_bets == 0 and r.staked == 0.0 and r.net == 0.0


def test_the_unpriced_count_is_reported_rather_than_implied():
    """A small n_bets could mean 'the model declined' or 'there was no
    price to decline'. Those are different and the reader cannot tell
    them apart from one number."""
    from engine import lab
    conn = db.connect(":memory:")
    _games(conn, "cfb", 200, spread=-7.0, total=55.0,
           priced=False)
    m = lab.game_lines(conn, "cfb")["markets"][0]
    assert m["unpriced"] == m["games_quoted"]
    assert m["n_bets"] == 0


def test_a_priced_close_still_reaches_the_pricer():
    """Admitting priceless closes must cost nothing where prices exist:
    a priced close goes through the card and is never counted unpriced."""
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120)
    r = backtest_game_lines(conn, "nfl", market="total")
    assert r.games_quoted > 0
    assert r.unpriced == 0, "these schedule closes carry prices"
    assert r.refused + r.n_bets == r.games_quoted, \
        "every priced close must reach the pricer and be judged"


def test_a_game_with_no_stored_line_is_not_quoted_at_all():
    conn = db.connect(":memory:")
    _games(conn, "nfl", 120, with_line=False)
    r = backtest_game_lines(conn, "nfl", market="total")
    assert r.games_seen > 0 and r.games_quoted == 0


def test_the_running_team_ratings_still_advance_on_an_unpriced_game():
    """The early-out for a priceless close must not skip the accumulator
    — a season of college games would then never build a rating and
    every later game would fall under `min_team_games`."""
    conn = db.connect(":memory:")
    _games(conn, "cfb", 200, spread=-7.0, total=55.0,
           priced=False)
    r = backtest_game_lines(conn, "cfb", market="spread")
    assert r.games_quoted > 50, \
        "ratings stopped accumulating, so later games were never quoted"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
