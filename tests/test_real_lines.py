"""Every number on an NFL card has to have come from somewhere real.

Ethan, 2026-09-03: *"make sure we are using real numbers and lines for
the sports books. Getting the wrong numbers can fuck our picks bad."*

THE DEFAULTS WERE NOT SENTINELS, and that is the whole finding.
`Game.total` defaults to 44.0 and `Game.spread` to 0.0. Both are values a
real NFL market holds — 44 is a mid-range total, 0 is a pick'em — so
nothing downstream could tell a posted number from a missing one.

nflverse is where they come from, and it fills `total_line` and
`spread_line` only AFTER a game is played, exactly as it does temp and
wind. So every game on a FORWARD board — the board people bet — arrived
carrying two placeholders that looked like quotes.

    a forward game, no posted lines:  total=44.0  spread=0.0
      team_implied_total -> MIN 22.0 pts, GB 22.0 pts    both fabricated
    a game a book has posted:         total=49.5  spread=-6.5
      team_implied_total -> DET 28.0 pts, NO 21.5 pts    real

THREE GUARDS WERE WRITTEN TO ASK "did a book post this" AND COULD NOT:

  pipeline._td_board    `if not g.total` — 44.0 is truthy, so the "no
                        line" branch never fired. The touchdown board
                        priced every unposted game off 22.0 points a
                        side, and its own census bucket read zero.
  matchup               `if coef and game.total` — same test. With
                        TOTAL_BASELINE at 44.6 the fabricated 44.0 is
                        not even neutral: x1.006 on every rushing
                        projection, silently, under the 2% threshold
                        that would have printed a reason.
  pipeline team totals  gated on the TOTAL's two prices while splitting
                        the line by the SPREAD. Its own comment says
                        "the total and the spread"; it tested one. An
                        unposted spread splits a real total 50/50 and
                        publishes symmetric team totals on a game with a
                        touchdown favourite.

This is `Weather.measured` again, on the game lines — the same source,
the same after-the-fact fill, the same defaults posing as facts. The
defaults stay, because the arithmetic paths need a number; the flag is
what stops them being read as the market's opinion.

Run directly: `python3 tests/test_real_lines.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import Game, Weather                       # noqa: E402
from engine.touchdowns import team_implied_total              # noqa: E402


def _forward():
    """A game as a forward board has it: scheduled, nothing posted."""
    return Game(home="MIN", away="GB", weather=Weather())


def _posted():
    return Game(home="DET", away="NO", weather=Weather(), total=49.5,
                spread=-6.5, total_measured=True, spread_measured=True)


# --- the defaults are not sentinels ---------------------------------------
def test_an_unposted_game_is_marked_unmeasured():
    g = _forward()
    assert g.total == 44.0 and g.spread == 0.0, "the defaults moved"
    assert g.total_measured is False, "an unposted total claims to be measured"
    assert g.spread_measured is False


def test_truthiness_cannot_tell_the_two_apart_which_is_the_point():
    """The test every old guard used, shown failing on purpose. If this
    ever starts passing, the defaults became sentinels and the flag
    could be retired — until then it is load-bearing."""
    g = _forward()
    assert bool(g.total) is True, \
        "44.0 is falsy now; the guards that read `not g.total` may be fine"
    assert bool(g.spread) is False, \
        "0.0 spread reads truthy; a pick'em would no longer be skipped"


def test_the_implied_totals_off_an_unposted_game_are_symmetric_and_fake():
    """22.0 and 22.0 — the shape a fabricated 44.0/0.0 always produces,
    and what the touchdown board was pricing against."""
    g = _forward()
    assert team_implied_total(g, "MIN") == team_implied_total(g, "GB") == 22.0


def test_a_posted_game_gives_the_favourite_the_points():
    g = _posted()
    home, away = team_implied_total(g, "DET"), team_implied_total(g, "NO")
    assert home > away, "the spread is not reaching the implied totals"
    assert abs((home + away) - g.total) < 1e-9, "the split does not close"


# --- the three guards ------------------------------------------------------
def _fn(path, name):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    i = src.index(name)
    return src[i:i + 900]


def test_the_touchdown_board_asks_whether_a_book_posted_the_total():
    seg = _fn("engine/pipeline.py", 'note["no_line"] += 1')
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    i = src.index('note["no_line"] += 1')
    before = src[max(0, i - 400):i]
    assert "total_is_posted" in before, \
        "the touchdown board still gates on a number that is never zero"


def test_the_pace_adjustment_asks_the_same_question():
    src = open(os.path.join(ROOT, "engine", "matchup.py"), encoding="utf-8").read()
    i = src.index("TOTAL_CLAMP)")
    before = src[max(0, i - 500):i]
    assert "total_is_posted" in before, \
        "a fabricated total still moves every rushing projection"


def test_team_totals_need_the_spread_they_are_split_by():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    i = src.index("_half((g.total - g.spread)")
    before = src[max(0, i - 700):i]
    assert "spread_is_posted" in before, \
        "team totals are still split by a spread nobody posted"


def test_a_pickem_spread_is_a_real_line_and_is_not_skipped():
    """`g.spread and ...` dropped every pick'em along with every missing
    spread. They are not the same thing and the NFL posts plenty of the
    former."""
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    i = src.index("g.spread_home_odds and g.spread_away_odds")
    seg = src[max(0, i - 300):i + 60]
    assert "spread_is_posted" in seg, seg[-200:]


# --- the sources say which it is ------------------------------------------
def test_the_schedule_records_presence_rather_than_swallowing_it():
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"),
               encoding="utf-8").read()
    assert "total_measured=_has(r, \"total_line\")" in src
    assert "spread_measured=_has(r, \"spread_line\")" in src
    assert "def _has(" in src, "the presence test is gone"


def test_a_book_price_marks_the_number_measured():
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    i = src.index("game.total, game.total_over_odds, game.total_under_odds = tot")
    assert "total_measured = True" in src[i:i + 200]
    j = src.index("game.spread, game.spread_home_odds, game.spread_away_odds = sp")
    assert "spread_measured = True" in src[j:j + 200]


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
