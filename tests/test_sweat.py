"""The sweat page's engine: live win probability on the fast clock.

Ethan's roadmap, item 2: "for every journaled bet, show live win
probability updating as the game goes... watching a parlay's % tick up
pitch-by-pitch is the reason people never close FanDuel."

THE MATH ALREADY EXISTED AND RODE THE WRONG CLOCK — engine/livepicks has
computed these numbers since mid-August, inside the 8-minute board
build. engine/sweat.py runs the SAME assembly on live_build's 12-second
clock, banks each pick's probability into a history, and joins open
parlay tickets to their legs' live numbers.

The judgment calls pinned here:

  * HISTORY IS THINNED, NOT RAW. Twelve-second cycles are a thousand
    points of "still 62%" per game; a point earns its place by time
    since the last one or by the size of the jump.
  * A PARLAY LEG IS NOT NECESSARILY A JOURNALED SINGLE. Legs live in
    the parlay ledger, so each becomes a pseudo-bet through the same
    assembly — computed by exactly the machinery a single would get.
  * A MISSING LEG NUMBER KILLS THE JOINT. 62% × nothing is nothing, and
    printing the product of the legs you happened to price is how a
    ticket lies about itself.
  * SETTLED LEGS ARE CERTAINTIES: a won leg multiplies at 1, a lost leg
    at 0 — a dead ticket reads 0%, not "62% pending".

Run directly: `python3 tests/test_sweat.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import sweat                                     # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


# --- history ---------------------------------------------------------------

def _pick(p=0.6, key="Juan Soto|total_bases|main"):
    player, market, cat = key.split("|")
    return {"player": player, "market": market, "category": cat,
            "live_prob": p}


def test_a_point_needs_time_or_a_jump():
    s = sweat.bank_history({}, [_pick(0.60)], "2026-08-24T20:00:00")
    # 12 seconds later, 1 point of drift: not a point.
    s = sweat.bank_history(s, [_pick(0.61)], "2026-08-24T20:00:12")
    assert len(s["Juan Soto|total_bases|main"]["h"]) == 1
    # 12 seconds later, a 5-point jump: a point.
    s = sweat.bank_history(s, [_pick(0.66)], "2026-08-24T20:00:24")
    assert len(s["Juan Soto|total_bases|main"]["h"]) == 2
    # A minute later, flat: still a point — time alone qualifies.
    s = sweat.bank_history(s, [_pick(0.66)], "2026-08-24T20:01:30")
    assert len(s["Juan Soto|total_bases|main"]["h"]) == 3


def test_history_is_capped_and_vanished_picks_are_dropped():
    s = {}
    for i in range(400):
        s = sweat.bank_history(
            s, [_pick(0.5 + (i % 40) / 100)],
            f"2026-08-24T{10 + i // 60:02d}:{i % 60:02d}:00")
    assert len(s["Juan Soto|total_bases|main"]["h"]) <= sweat.HIST_CAP
    s = sweat.bank_history(s, [_pick(0.5, key="Other|hits|main")],
                           "2026-08-24T23:00:00")
    assert "Juan Soto|total_bases|main" not in s, \
        "a settled pick's history lives in the state file forever"


def test_a_pick_with_no_number_keeps_its_place_but_adds_nothing():
    s = sweat.bank_history({}, [_pick(0.6)], "2026-08-24T20:00:00")
    s = sweat.bank_history(s, [_pick(None)], "2026-08-24T20:05:00")
    assert len(s["Juan Soto|total_bases|main"]["h"]) == 1, \
        "a None probability became a history point"


# --- parlays ---------------------------------------------------------------

def _ticket(**over):
    t = {"id": 1, "date": "2026-08-24", "book": "FanDuel", "n_legs": 2,
         "stake_units": 0.5, "quoted_dec": 3.4, "modeled_joint": 0.31,
         "legs": [
             {"player": "Juan Soto", "market": "total_bases", "side": "OVER",
              "line": 1.5, "p_final": 0.58, "status": "open"},
             {"player": "Pete Alonso", "market": "home_runs", "side": "OVER",
              "line": 0.5, "p_final": 0.53, "status": "open"}]}
    t.update(over)
    return t


def _live(player, market, p, side="OVER", line=None):
    return {"player": player, "market": market, "side": side,
            "line": line if line is not None
            else (1.5 if market == "total_bases" else 0.5),
            "live_prob": p, "current": 1.0, "phase": "live"}


def test_the_joint_is_the_product_and_says_so():
    rows = sweat.parlay_rows([_ticket()], [
        _live("Juan Soto", "total_bases", 0.64),
        _live("Pete Alonso", "home_runs", 0.5)])
    t = rows[0]
    assert abs(t["live_joint"] - 0.32) < 1e-9
    assert t["joint_basis"] == "product", \
        "the ticket stopped naming its own approximation"
    assert t["pregame_joint"] == 0.31


def test_a_missing_leg_number_kills_the_joint():
    rows = sweat.parlay_rows([_ticket()], [
        _live("Juan Soto", "total_bases", 0.64)])
    assert rows[0]["live_joint"] is None, \
        "the ticket multiplied only the legs it happened to price"
    assert rows[0]["legs"][1]["live_prob"] is None


def test_settled_legs_are_certainties():
    t = _ticket()
    t["legs"][0]["status"] = "lost"
    rows = sweat.parlay_rows([t], [_live("Pete Alonso", "home_runs", 0.5)])
    assert rows[0]["live_joint"] == 0.0, "a dead ticket is not 50% pending"
    t["legs"][0]["status"] = "won"
    rows = sweat.parlay_rows([t], [_live("Pete Alonso", "home_runs", 0.5)])
    assert rows[0]["live_joint"] == 0.5


def test_a_leg_matches_on_side_and_line_not_just_the_player():
    """Soto OVER 1.5 TB and Soto OVER 2.5 TB are different bets; joining
    on the name alone would hand one leg the other's number."""
    rows = sweat.parlay_rows([_ticket()], [
        _live("Juan Soto", "total_bases", 0.9, line=2.5),
        _live("Pete Alonso", "home_runs", 0.5)])
    assert rows[0]["legs"][0]["live_prob"] is None


# --- the assembly's exports ------------------------------------------------

def test_the_rows_carry_the_sentence_ingredients():
    src = open(os.path.join(ROOT, "engine", "livepicks.py"),
               encoding="utf-8").read()
    for key in ('"opp_left"', '"opp_unit"', '"still_in"', '"pregame_prob"'):
        assert key in src, f"livepicks rows lost {key}"
    assert 'b.get("hit_prob")' in src, \
        "the pregame baseline no longer comes off the journal row"
    mb = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    assert "category, hit_prob" in mb, \
        "mlb_build's open-bet query stopped selecting hit_prob"


def test_parlay_legs_go_through_the_same_assembly():
    src = open(os.path.join(ROOT, "engine", "sweat.py"),
               encoding="utf-8").read()
    assert '"category": "parlay"' in src
    i = src.index("leg_rows = assemble_live_picks")
    assert i > 0, "legs are joined against journaled picks only again"


# --- the wire --------------------------------------------------------------

def test_the_sweat_is_a_paid_board():
    from engine import gate
    assert "sweat.json" in gate.PAID_FILES
    assert "sweat.json" in gate.KNOWN_BOARDS


def test_it_rides_the_fast_clock_and_cannot_break_the_scores():
    src = open(os.path.join(ROOT, "live_build.py"), encoding="utf-8").read()
    i = src.index("sweat.build")
    seg = src[max(0, i - 600):i]
    assert "except Exception" in src[i:i + 300] or "try:" in seg, \
        "a sweat failure takes the scoreboard down with it"
    assert src.index('print(f"live scores:') < i, \
        "the sweat runs before the scores are written"


def test_the_zone_leads_the_live_view():
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    i = html.index('id="live-board"')
    j = html.index('id="sweat-zone"')
    k = html.index('id="live-picks"')
    assert i < j < k, "the sweat zone moved out of its slot"
    fn = APP[APP.index("async function renderSweatZone("):]
    fn = fn[:fn.index("\nasync function ")]
    assert "180000" in fn, \
        "a stale sweat file would render as live numbers"
    assert "d.locked" in fn
    assert "joined as a product" in fn, "the honesty note left the ticket"
    assert 'r.still_in === false' in fn, \
        "a pulled pitcher's certainty lost its sentence"


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
