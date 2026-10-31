"""The NFL Most Likely board, tightened from its own graded record.

Ethan, 2026-10-31: "our NFL most likely bets are not doing well. So we need
to tighten that up ... we have so much bets and data behind us that we have
made and won and lost to where we can adjust our filters."

What the record said (record.json that day): 1,479 settled list picks, 61.3%
won where the average price (-172) needed 63.2%. The chance was honest; the
loss sat in the 45-60% band (662 picks, -6.8%) and in unders the scout
cautions against (dog_pass_under 39% hit where we said 62%, and four more).
What these hold:

  * the list asks 60% of an NFL prop or game line (engine/likely
    LANE_MIN_PROB); a touchdown keeps the shared bar; other leagues are
    untouched; QB_NFL_TIGHT=off puts everything back;
  * a row under the bar can still fill a thin shelf as a reserve row —
    labelled, never staked — so the page is never blank;
  * the board holds an NFL prop under 60% after its corrections, and an
    under carrying one of the five cautions, but never a posted pick;
  * a pick the board held that way is taken off the list too, so the
    staked book cannot journal what the board refused;
  * the box's audits ask the new questions: the game's weekday and how
    long before kickoff each pick was taken (lossaudit), and two rules
    tried on days they never saw (likelyfit day_cut and maker).

Run directly: `python3 tests/test_the_nfl_board_is_tightened.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _slate_clock import kickoff as _kickoff                     # noqa: E402

from engine import likely, likelyboard as B                       # noqa: E402


class _Env:
    """QB_NFL_TIGHT set for the block, restored after."""
    def __init__(self, value):
        self.value, self.keep = value, None

    def __enter__(self):
        self.keep = os.environ.get(likely.TIGHT_ENV)
        if self.value is None:
            os.environ.pop(likely.TIGHT_ENV, None)
        else:
            os.environ[likely.TIGHT_ENV] = self.value

    def __exit__(self, *exc):
        if self.keep is None:
            os.environ.pop(likely.TIGHT_ENV, None)
        else:
            os.environ[likely.TIGHT_ENV] = self.keep


def _card(i, prob):
    d, k = _kickoff(180)
    return {"bet_type": "moneyline", "matchup": f"A{i} @ B{i}", "home": f"B{i}", "away": f"A{i}",
            "team": f"B{i}", "win_prob": prob, "fair_prob": prob - 0.02, "odds": -150,
            "has_market": True, "book": "DraftKings", "game_date": d, "kickoff": k}


def _games(board):
    return {r["team"]: r for r in board if r.get("kind") == "game"}


def test_the_nfl_bar_is_sixty_for_props_and_game_lines_only():
    with _Env(None):
        assert likely.lane_floors("nfl") == {"prop": 0.60, "game": 0.60}
        assert likely.lane_floors("cfb") == {} and likely.lane_floors("mlb") == {}
        assert "td" not in likely.lane_floors("nfl"), "a scorer keeps the shared bar"
    with _Env("off"):
        assert likely.lane_floors("nfl") == {} and not likely.tightened("nfl")
    assert likely.MIN_PROB == 0.55, "the shared bar itself does not move"


def test_a_58_percent_nfl_moneyline_is_no_longer_a_pick():
    # A game row shows the market's fair chance (the card's fair_prob): 66%
    # and 58% here.
    cards = [_card(1, 0.68), _card(2, 0.60)]
    with _Env(None):
        on = _games(likely.build([], [], [], sport="nfl", game_bets=cards))
    with _Env("off"):
        off = _games(likely.build([], [], [], sport="nfl", game_bets=cards))
    assert "B1" in on and not on["B1"].get("reserve"), on.keys()
    # Under the bar it is not a pick; it may still fill the thin shelf as a
    # labelled reserve row, which is never staked.
    assert "B2" not in on or on["B2"].get("reserve"), on.get("B2")
    assert "B2" in off and not off["B2"].get("reserve"), "QB_NFL_TIGHT=off puts it back"


def test_college_keeps_the_shared_bar():
    cards = [_card(1, 0.68), _card(2, 0.60)]
    with _Env(None):
        got = _games(likely.build([], [], [], sport="cfb", game_bets=cards))
    assert "B2" in got and not got["B2"].get("reserve")


# --- the board ------------------------------------------------------------------
GAME = {"home": "DET", "away": "NYJ", "spread": -9.5, "total": 44.5,
        "scan": {"units": {}, "redzone": {}}}


def _result(rows):
    return {"games": [GAME], "recommendations": [], "scan_reads": {},
            "most_likely": rows, "matchup_picks": [], "td_scenarios": []}


def _prop(player, prob, side="OVER", market="rec_yds", **kw):
    return {"kind": "prop", "player": player, "team": "NYJ", "opponent": "DET", "market": market,
            "side": side, "line": 45.5, "odds": -130, "model_prob": prob, "implied_prob": prob - 0.02,
            **kw}


def test_the_board_holds_a_prop_under_sixty_and_says_why():
    rows = [_prop("A Sixty", 0.63), _prop("B Fifty-seven", 0.57)]
    with _Env(None):
        b = B.build(_result([dict(r) for r in rows]), record={}, sport="nfl", tiers_seen={})
    on = {r["player"] for r in b["rows"]}
    held = {r["player"]: r for r in b["held"]}
    assert "A Sixty" in on and "B Fifty-seven" in held, (on, list(held))
    assert held["B Fifty-seven"]["tight_hold"] is True
    assert "the NFL board asks 60% of a prop or a game line" in held["B Fifty-seven"]["held_note"]
    with _Env("off"):
        b = B.build(_result([dict(r) for r in rows]), record={}, sport="nfl", tiers_seen={})
    assert "B Fifty-seven" in {r["player"] for r in b["rows"]}, "off: the old board"
    b = B.build(_result([dict(r) for r in rows]), record={}, sport="cfb", tiers_seen={})
    assert "B Fifty-seven" in {r["player"] for r in b["rows"]}, "college is not tightened"


def test_an_under_the_scout_cautions_against_comes_off():
    r = _prop("C Under", 0.66, side="UNDER", scout_flags=["dog_pass_under"])
    assert B.tightened_reason(r, "nfl").startswith("held back: a passing or receiving under on a team "
                                                   "expected to trail")
    assert B.tightened_reason(dict(r, side="OVER"), "nfl") is None, "the caution is about unders"
    assert B.tightened_reason(dict(r, scout_flags=["boom_bust"]), "nfl") is None, "only the five"
    assert B.tightened_reason(dict(r, locked=True), "nfl") is None, "a posted pick keeps its seat"
    assert B.tightened_reason(dict(r, reserve=True), "nfl") is None
    assert B.tightened_reason(r, "cfb") is None
    td = {"kind": "td", "player": "D Scorer", "market": "anytime_td", "side": "YES", "model_prob": 0.45}
    assert B.tightened_reason(td, "nfl") is None, "a touchdown keeps its own bar"
    assert set(B.NFL_UNDER_CAUTIONS) == {"dog_pass_under", "long_trip_under", "body_clock_under",
                                         "new_coach_under", "shootout_under"}
    from engine import scout
    assert all(c in scout.FLAGS for c in B.NFL_UNDER_CAUTIONS), "every one a flag the scout raises"


def test_a_tight_ends_under_comes_off():
    """nflaudit on the box (Ethan's paste, 2026-10-31): tight-end unders hit
    48% where we said 60% over 100 picks, short in both halves — the one
    position and side marked HOLDS. Overs, other positions, touchdowns,
    posted picks and college are untouched."""
    te = _prop("G Tight End", 0.66, side="UNDER", position="TE", market="receptions")
    assert B.tightened_reason(te, "nfl").startswith("held back: a tight end's under")
    assert "48% where we said 60%" in B.tightened_reason(te, "nfl")
    assert B.tightened_reason(dict(te, position="te"), "nfl"), "any case"
    assert B.tightened_reason(dict(te, side="OVER"), "nfl") is None, "a tight end's over stays"
    assert B.tightened_reason(dict(te, position="WR"), "nfl") is None, "a receiver's under stays"
    assert B.tightened_reason(dict(te, locked=True), "nfl") is None, "a posted pick keeps its seat"
    assert B.tightened_reason(te, "cfb") is None, "college is not tightened"
    with _Env("off"):
        assert B.tightened_reason(te, "nfl") is None, "QB_NFL_TIGHT=off puts it back"
    assert set(B.NFL_UNDER_POSITIONS) == {"TE"}


def test_the_board_finds_a_tight_end_from_the_props_when_the_row_has_no_position():
    # On the favourite, so no scout caution reaches it first.
    row = _prop("H Kincaid", 0.64, side="UNDER", market="rec_yds", team="DET", opponent="NYJ")
    result = _result([row])
    result["recommendations"] = [{"player": "H Kincaid", "position": "TE", "market": "rec_yds"}]
    with _Env(None):
        b = B.build(result, record={}, sport="nfl", tiers_seen={})
    held = {r["player"]: r for r in b["held"]}
    assert "H Kincaid" in held and held["H Kincaid"]["tight_hold"], [r["player"] for r in b["rows"]]
    assert "tight end's under" in held["H Kincaid"]["held_note"]


def test_the_matchup_read_no_longer_rescues_an_nfl_prop_under_sixty():
    """The 10-07 rule kept a pick the record pulled under 50% when the
    matchup read backed it. On the tightened NFL board the bar is 60% and
    nothing rescues a prop under it: the graded board's Top picks — the
    tier the matchup read backs — went 97-66 for −9.6%, the worst tier."""
    backed = _prop("F Backed", 0.47, cal_note="picks like this over-claim")
    assert B.held_reason(backed, {"matchup": True}) is None, "the old rule keeps it"
    assert B.tightened_reason(backed, "nfl").startswith("held back: our chance is 47%")


def test_a_pick_the_board_held_is_not_on_the_list_to_be_staked():
    keep, cut = _prop("A Sixty", 0.63), _prop("B Fifty-seven", 0.57)
    posted = _prop("E Posted", 0.56, locked=True)
    result = _result([keep, cut, posted])
    with _Env(None):
        result["likely_board"] = B.build(result, record={}, sport="nfl", tiers_seen={})
        B.harmonize(result)
    names = [r["player"] for r in result["most_likely"]]
    assert names == ["A Sixty", "E Posted"], names
    assert result["likely_board"]["tightened_off_list"] == 1


def test_the_audits_ask_the_sunday_question():
    import lossaudit as LA
    assert LA.game_weekday({"game_day": "2026-10-25"}) == "Sunday"
    assert LA.game_weekday({"game_day": None}) == "(no game day)"
    assert LA.taken_before({"lead_min": 45}) == "under 90 minutes (inactives out)"
    assert LA.taken_before({"lead_min": 300}) == "3 to 8 hours"
    assert LA.taken_before({"lead_min": None}) == "(not stamped)"
    assert "game_day" in LA.COLUMNS and "lead_min" in LA.COLUMNS
    import likelyfit as LF
    assert "day_cut" in LF.WORDS and "maker" in LF.WORDS and LF.DAY_CUT_MIN_DAYS == 10


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
