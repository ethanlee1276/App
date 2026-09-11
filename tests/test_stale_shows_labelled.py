"""A dated price goes on the page, labelled — it does not empty the board.

Ethan, 2026-09-08, the night before the Week 1 opener:

    "We have barely any moneylines show and barley and touchdowns shown.
     We need to fix that immediately."

That was this codebase's own six-hour ceiling doing exactly what it had
been written to do, earlier the same day. `MAX_GAME_PRICE_AGE` and
`MAX_PROP_PRICE_AGE` dropped a game's markets and an event's player
markets outright once the payload behind them passed six hours — so on a
box whose odds pull had not run inside that window (a declined budget
cycle, spent credits, the pacer's own gap) EVERY moneyline and EVERY
touchdown quote disappeared at once.

THE MISTAKE WAS COLLAPSING TWO QUESTIONS INTO ONE BAR. "Too old to
stake" and "too old to put on the page" are different, and a price from
this morning is not a WRONG price — it is a real quote that may have
moved, on a card that already carries its own age. Refusing it turned a
labelling problem into an empty board, which is its own way of being
useless and is the thing he is complaining about.

So there are two ceilings now, and this file pins the three states they
create:

  * inside MAX_*_PRICE_AGE — fresh, may be recommended;
  * between that and MAX_*_PRICE_SHOW_AGE — SHOWN, carrying its age,
    marked `price_stale`, and never `recommended`;
  * past the show ceiling — dropped, as before.

The middle state is the whole point: it is what puts moneylines back on
the board without ever presenting a dated number as a current one.

Run directly: `python3 tests/test_stale_shows_labelled.py`
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.models import Game, Weather                         # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402

TEAMS = {"Minnesota Vikings": "MIN", "Green Bay Packers": "GB"}


def _event(eid="e1"):
    return {"id": eid, "home_team": "Minnesota Vikings",
            "away_team": "Green Bay Packers",
            "commence_time": "2026-09-13T20:25:00Z",
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": "Minnesota Vikings", "price": -125},
                                {"name": "Green Bay Packers", "price": 105}]}]}]}


class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def _pull(age_s):
    """Attach the board payload as if the last pull ran `age_s` ago."""
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             kickoff="2026-09-13T20:25:00Z")
    tmp = tempfile.mkdtemp()
    real = oa.CACHE_DIR
    oa.CACHE_DIR = __import__("pathlib").Path(tmp)
    path = oa.CACHE_DIR / "odds_board_nfl_lines.json"
    path.write_text(json.dumps([_event()]))
    old = time.time() - age_s
    os.utime(path, (old, old))
    try:
        res = oa.apply_board_lines_to_slate(_Slate([g]), api_key="k",
                                            cache_only=True)
    finally:
        oa.CACHE_DIR = real
    return g, res


# --- the three states -----------------------------------------------------
def test_a_fresh_price_is_attached_and_not_marked():
    g, res = _pull(600)
    assert res.moneylines == 1, res
    assert (g.home_ml, g.away_ml) == (-125, 105)
    assert g.price_stale is False, "a ten-minute-old pull is not stale"


def test_a_dated_price_is_still_attached_and_marked():
    """THE ONE THAT PUTS THE MONEYLINES BACK. Eight hours is past the
    freshness bar and nowhere near the show ceiling: before this split it
    produced a game with no markets at all."""
    g, res = _pull(8 * 3600)
    assert res.moneylines == 1, "the moneyline vanished — the board is empty again"
    assert (g.home_ml, g.away_ml) == (-125, 105)
    assert g.price_stale is True, g.price_stale
    assert g.price_age_s and g.price_age_s > 6 * 3600
    # …and it is counted, in the SHOWN column rather than the refused
    # one. The build's refusal line reads "kept NO price"; a game priced
    # off an eight-hour payload has a price, so counting it there would
    # have the log deny what is on the board.
    assert res.shown_stale_game_prices == 1, res
    assert res.shown_stale_price_age_s > 6 * 3600, res
    assert res.stale_game_prices == 0, "a shown price was counted as refused"
    assert res.stale_price_age_s == 0.0, \
        "a build that refused nothing reported a refused age"


def test_a_price_past_the_show_ceiling_is_not_counted_as_shown():
    _g, res = _pull(72 * 3600)
    assert res.stale_game_prices == 1, res
    assert res.shown_stale_game_prices == 0, "a refusal was counted as a showing"


def test_a_price_past_the_show_ceiling_is_dropped_as_before():
    g, res = _pull(72 * 3600)
    assert res.moneylines == 0, "a three-day-old price must not be shown"
    assert (g.home_ml, g.away_ml) == (0, 0)
    assert res.stale_game_prices == 1, res


def test_the_two_ceilings_are_ordered_and_the_show_one_is_wider():
    assert oa._max_game_price_show_age() > oa._max_game_price_age()
    assert oa._max_prop_price_show_age() > oa._max_prop_price_age()


def test_showable_and_current_answer_the_two_different_questions():
    hour = 3600.0
    assert oa.price_is_current(2 * hour) and oa.price_is_showable(2 * hour)
    assert not oa.price_is_current(8 * hour), "8h is past the freshness bar"
    assert oa.price_is_showable(8 * hour), "…but must still reach the page"
    assert not oa.price_is_showable(72 * hour)
    # A payload just fetched has no age and is current by construction.
    assert oa.price_is_current(None) and oa.price_is_showable(None)


# --- shown, never recommended ---------------------------------------------
def _card(stale):
    from engine.pipeline import _finish_bet
    from engine.rules import RuleConfig
    # THE BOOK IS PART OF THE FIXTURE, not decoration. A moneyline that
    # cannot name the book posting it is refused outright now
    # (tests/test_game_price_names_its_book.py), so a card without one
    # would fail here for a reason that has nothing to do with age — and
    # this file is about age.
    g = Game(home="MIN", away="GB", weather=Weather(), date="2026-09-13",
             home_ml=-125, away_ml=105, price_age_s=8 * 3600.0,
             home_ml_book="DraftKings", away_ml_book="FanDuel",
             price_stale=stale)
    d = {"bet_type": "moneyline", "market": "moneyline", "team": "MIN",
         "grade": "B", "confidence": 9.0, "edge": 0.08, "odds": -125}
    return _finish_bet(d, g, RuleConfig())


def test_a_stale_priced_card_is_shown_but_never_recommended():
    """Both halves of the promise. The row exists — that is what fixes the
    empty board — and `recommended` is withdrawn, which is what keeps it
    from being a dated number sold as a current one."""
    got = _card(True)
    assert got["price_stale"] is True
    assert got["recommended"] is False, "a stale price was recommended"
    assert any("older than our freshness bar" in w
               for w in got.get("warnings") or []), got.get("warnings")


def test_the_same_card_on_a_fresh_price_is_recommended_normally():
    """So the guard above is the stale flag doing the work, rather than
    the fixture failing some other bar."""
    got = _card(False)
    assert got["price_stale"] is False
    assert got["recommended"] is True, got


# --- and the page says which one it is drawing ----------------------------
def _node(js, *fns):
    import shutil, subprocess
    node = shutil.which("node")
    if not node:
        return None
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    src = []
    for name in fns:
        i = app.index(f"function {name}(")
        src.append(app[i:app.index("\n}", i) + 2])
    prog = """
      var escapeHtml = (s) => String(s == null ? "" : s);
      var escapeAttr = (s) => String(s == null ? "" : s);
      %s
      console.log(JSON.stringify((() => { %s })()));
    """ % ("\n".join(src), js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_chip_says_the_price_may_have_moved():
    got = _node("""
      return { stale: priceAgeChip({ price_age_s: 28800, price_stale: true }),
               fresh: priceAgeChip({ price_age_s: 600, price_stale: false }),
               none:  priceAgeChip({ price_age_s: null, price_stale: true }) };
    """, "priceAgeChip")
    if got is None:
        return
    assert "may have moved" in got["stale"], got["stale"]
    assert "8h ago" in got["stale"], got["stale"]
    # A fresh price says when and nothing more — the warning has to mean
    # something, so it cannot be on every row.
    assert "may have moved" not in got["fresh"], got["fresh"]
    assert "10m ago" in got["fresh"], got["fresh"]
    # No age, no chip, whatever the flag says: a proxy row has no book
    # price to date and must not grow a warning about one.
    assert got["none"] == "", got["none"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
