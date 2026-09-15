"""The value picks had the same empty page the watch rows had — and no door.

Ethan, 2026-09-10, twice: "when you click on props from the most likely,
it pulls up the search page with the player on there", and then "it's not
showing the last five games. or the shop the price. for the form or how
the line is moving today."

Both were fixed on the WATCH list. The value picks — the scorers the
board actually recommends — are the same defect one list over, and worse,
because they lose the door as well as the page:

    `LongShot.to_dict` published no logs, no form, no book quotes and no
    side or line at all. `propOpenable` opens a card only when it can see
    three games, so a value pick was never a door; `likelyDoor` then fell
    back to `data-player-page` — the search surface Ethan kept landing
    on. `propId` is `player|market|side|line`, so a row naming neither
    could not be addressed anyway, and `quotesForSide` could not tell the
    shop's own answer from an off-the-field price.

Every one of those fields was already on the `Prop` the pick was priced
from. Nothing copied them across — the same shape of miss as `headshot`,
which sat unread on the prop for a fortnight while every card drew the
fallback chip.

ONE SPELLING FOR ONE BET. `longshots.YES_SIDE`/`YES_LINE` now say OVER
0.5 in a single place. Three watch builders were each spelling it
separately and a value pick was not spelling it at all, which is how two
lists end up holding two descriptions of the same wager — and the board's
own dedupe assumes they agree.

The door tests run in node against the real functions, because the
failure was behavioural: source-level pins passed throughout.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import longshots as LS                            # noqa: E402
from engine.models import (Game, Weather, Team, DefenseProfile,   # noqa: E402
                           Prop, SportsbookLine, GameLog, ANYTIME_TD)
from engine.touchdowns import (build_td_longshots, td_watchlist,   # noqa: E402
                               prop_depth)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

#: The six windows `pipeline._rec_to_dict` publishes, which `propFormRows`
#: reads by name.
FORM_KEYS = {"last1", "last3", "last5", "last10", "season",
             "career", "vs_opponent"}


def _bell():
    """A bell cow with a real log and two books on him."""
    return Prop(player="Jahmyr Gibbs", team="DET", opponent="NO",
                position="RB", market=ANYTIME_TD,
                logs=[GameLog(week=w, opponent="CHI", value=float(w % 2))
                      for w in range(8, 0, -1)],
                career_avg=0.0, vs_opponent_avg=None,
                lines=[SportsbookLine(book="DraftKings", line=0.5,
                                      over_odds=210, under_odds=-260),
                       SportsbookLine(book="FanDuel", line=0.5,
                                      over_odds=195, under_odds=-240)])


def _cands(prop, odds=210):
    g = Game(home="DET", away="NO", weather=Weather(dome=True),
             spread=-3.5, total=47.5)
    opp = Team("NO", "NO", DefenseProfile("NO"))
    return [{"prop": prop, "game": g, "opponent": opp,
             "opportunity_share": 0.45, "odds": odds, "book": "DraftKings",
             "under_odds": -260}]


def _pick(prop=None, odds=210):
    prop = prop or _bell()
    picks = build_td_longshots(_cands(prop, odds), require_edge=False)
    assert picks, "the fixture must price"
    return picks[0].to_dict()


# --- the page ---------------------------------------------------------------
def test_a_value_pick_carries_the_four_fields_the_page_draws():
    """`renderPropPage` reads one field per section. Before this a
    recommended scorer published none of them."""
    d = _pick()
    assert len(d["logs"]) == 8, "the game log the chart is drawn from"
    assert d["logs"][0].keys() >= {"week", "opponent", "value", "home"}
    assert set(d["form"]) == FORM_KEYS
    assert [q["book"] for q in d["all_lines"]] == ["DraftKings", "FanDuel"]
    assert d["recent_values"] == [g.value for g in _bell().logs][:12]


def test_the_pick_and_the_watch_row_describe_one_bet_the_same_way():
    """Two lists, one wager. `propId` is built from these four parts, so
    a disagreement here is two rows for one bet."""
    prop = _bell()
    pick = _pick(prop)
    row = td_watchlist(_cands(prop), limit=0)[0]
    for k in ("player", "market", "side", "line"):
        assert pick[k] == row[k], f"{k}: {pick[k]!r} vs {row[k]!r}"


def test_the_side_and_the_line_are_the_ones_the_journal_grades():
    assert (LS.YES_SIDE, LS.YES_LINE) == ("OVER", 0.5)
    assert _pick()["side"] == "OVER" and _pick()["line"] == 0.5


def test_the_other_two_watch_builders_spell_it_from_the_same_place():
    """A source pin, deliberately: the point of the constant is that the
    literal is written once. Three builders each spelling OVER 0.5 by
    hand is how two lists come to describe one bet differently, and the
    college and home-run rows cannot be built here without a database."""
    for rel in ("engine/cfb/tds.py", "engine/mlb/homeruns.py",
                "engine/touchdowns.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert '"side": YES_SIDE, "line": YES_LINE' in src, rel
        assert '"side": "OVER", "line": 0.5' not in src, \
            f"{rel}: the literal is back beside the constant"


def test_a_scorer_with_no_history_publishes_nothing_rather_than_zeroes():
    """A man with no games has no average. A 0.0 in the Last-5 box is a
    claim that he has been held out of the end zone."""
    bare = Prop(player="Camp Body", team="DET", opponent="NO", position="WR",
                market=ANYTIME_TD, logs=[], career_avg=0.0,
                vs_opponent_avg=None, lines=[])
    d = prop_depth(bare)
    assert d["logs"] == [] and d["all_lines"] == [] and d["recent_values"] == []
    assert set(d["form"]) == FORM_KEYS
    assert all(v is None for v in d["form"].values())


def test_the_watch_and_the_picks_read_the_same_helper():
    """They drifted apart once already — the watch was given the page and
    the picks were not."""
    prop = _bell()
    row = td_watchlist(_cands(prop), limit=0)[0]
    pick = _pick(prop)
    for k in ("logs", "form", "all_lines", "recent_values"):
        assert row[k] == pick[k], k


# --- the door ---------------------------------------------------------------
FNS = ("propId", "propOpenable", "findProp", "likelyProp",
       "likelyOpenableProp", "likelyDoor")


def _door(props, row):
    """`likelyDoor(row)` against a board holding exactly `props`."""
    node = shutil.which("node")
    if not node:
        return None
    src = []
    for name in FNS:
        i = APP.index(f"function {name}(")
        src.append(APP[i:APP.index("\n}", i) + 2])
    prog = """
      var escapeAttr = (s) => String(s == null ? "" : s);
      var PROPS = %s;
      var allProps = () => PROPS;
      var slugify = (s) => String(s).toLowerCase().split(" ").join("-");
      var gameBetAttrs = () => " GAME-DOOR";
      %s
      console.log(JSON.stringify(likelyDoor(%s)));
    """ % (json.dumps(props), "\n".join(src), json.dumps(row))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True,
                             timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


#: The likelihood row as `likely.from_watch` writes it — side "yes", no
#: line — for a scorer who is on the VALUE list rather than the watch.
LIKELY_TD = {"kind": "td", "player": "Jahmyr Gibbs", "market": "anytime_td",
             "side": "yes", "line": None, "rung": "main",
             "recent_values": []}


def test_a_recommended_scorer_opens_his_prop_page_not_the_search_page():
    """Ethan's report, in one assertion. The board's own recommendation
    was the row most likely to dump him on the player page, because a
    priced pick carried less than a watched one did."""
    got = _door([_pick()], LIKELY_TD)
    if got is None:
        return
    assert "data-prop=" in got, f"a value pick still opens the player page: {got}"
    assert "Jahmyr Gibbs|anytime_td|OVER|0.5" in got, got
    assert "data-player-page" not in got


def test_a_pick_with_no_history_still_falls_back_rather_than_opening_empty():
    """The fallback is not the bug — opening a page with nothing on it
    would be. A scorer nobody has a game log for has no chart to show."""
    bare = _pick(Prop(player="Camp Body", team="DET", opponent="NO",
                      position="WR", market=ANYTIME_TD, logs=[],
                      career_avg=0.0, vs_opponent_avg=None,
                      lines=[SportsbookLine(book="DraftKings", line=0.5,
                                            over_odds=210, under_odds=-260)]),
                 odds=210)
    got = _door([bare], dict(LIKELY_TD, player="Camp Body"))
    if got is None:
        return
    assert "data-player-page" in got, got


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
