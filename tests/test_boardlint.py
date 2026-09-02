"""The board lint reads a published payload the way a sceptical bettor
reads it, and flags what he would ask about.

Ethan, 2026-09-02: "dive deep into making sure the nfl bets for edge bets
and most likely bets are perfect and following everything we have and
make sense ... Some of them seem weird so I wanna make sure. Especially
the most likely bets." The boards are built on the droplet from feeds
this sandbox cannot reach, so the tool runs there; these pins prove each
check fires on the row shape the pipeline actually publishes.

Run directly: `python3 tests/test_boardlint.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import boardlint as L


def _likely(**kw):
    d = dict(player="Amon-Ra St. Brown", team="DET", opponent="NO", market="receptions",
             market_label="Receptions", side="over", line=5.5, book="FanDuel", odds=-140,
             model_prob=0.66, prob_source="mixture", raw_prob=0.71, implied_prob=0.60,
             projection=6.8, bettable=True, position="WR", usage_role="wr1",
             recent_values=[7, 6, 8, 5, 9, 6], game_script={"archetype": "Shootout", "tilt": 1.04},
             kickoff="2026-09-13T17:00:00+00:00")
    d.update(kw)
    return d


def _prop(**kw):
    d = dict(player="Jared Goff", team="DET", opponent="NO", market="pass_yds",
             side="over", line=249.5, book="DK", odds=-112, hit_prob=0.57, fair_prob=0.52,
             edge=0.05, quality=74, grade="B+", stake_units=0.5, ev_per_unit=0.06,
             projection=262.0, recommended=True, warnings=[], reasons=["Projects 262"],
             has_market=True, game_script={"archetype": "Ground and pound", "tilt": 0.93},
             kickoff="2026-09-13T17:00:00+00:00")
    d.update(kw)
    return d


def _gb(**kw):
    d = dict(matchup="NO @ DET", bet_type="total", pick_label="Over 47.5", line=47.5,
             odds=-110, win_prob=0.55, fair_prob=0.52, edge=0.03, quality=62, grade="Pass",
             stake_units=0.0, ev_per_unit=0.04, credible=True, has_market=True,
             recommended=True, warnings=[], kickoff="2026-09-13T17:00:00+00:00")
    d.update(kw)
    return d


def _flags(items, player):
    for x in items:
        if x["row"].get("player") == player or x["row"].get("matchup") == player:
            return x["flags"]
    raise AssertionError(player)


# --- Most Likely ---------------------------------------------------------------
def test_a_clean_likely_row_carries_no_flag():
    got = L.lint_likely([_likely()], {})
    assert got[0]["flags"] == []


def test_the_injury_hold_is_the_first_thing_asked():
    rows = [_likely(player="Held Man", injury_status="OUT"),
            _likely(player="Page Says", team="NO")]
    got = L.lint_likely(rows, {"page says": "Questionable"})
    assert _flags(got, "Held Man") == ["HELD listed OUT"]
    assert "HELD injuries page says Questionable" in _flags(got, "Page Says")


def test_the_page_rules_are_checked_again_on_the_payload():
    rows = [_likely(player="Chalk", odds=-300),
            _likely(player="Fade", side="under", projection=6.8, line=5.5),
            _likely(player="Runaway", model_prob=0.75, implied_prob=0.55),
            _likely(player="Thin", model_prob=0.25),
            _likely(player="Fine Under", side="under", projection=4.2, line=5.5)]
    got = L.lint_likely(rows, {})
    assert "CHALK -300" in _flags(got, "Chalk")
    # An under is a bet since 2026-09-02 (Ethan: "we have no unders");
    # what the lint asks of one is that the projection sits on its side
    # of the number, the mirror of PROJ<LINE on an over.
    assert any(f.startswith("PROJ>LINE") for f in _flags(got, "Fade")), _flags(got, "Fade")
    assert "UNDER" not in _flags(got, "Fade")
    assert not any(f.startswith("PROJ") for f in _flags(got, "Fine Under")), \
        _flags(got, "Fine Under")
    assert any(f.startswith("GAP") for f in _flags(got, "Runaway"))
    assert any(f.startswith("UNDER-FLOOR") for f in _flags(got, "Thin"))


def test_a_projection_under_the_line_on_an_over_is_a_question():
    got = L.lint_likely([_likely(projection=4.9, line=5.5)], {})
    assert any(f.startswith("PROJ<LINE") for f in got[0]["flags"])


def test_a_history_that_disagrees_with_a_confident_number_is_a_question():
    got = L.lint_likely([_likely(model_prob=0.66, recent_values=[2, 3, 1, 4, 2, 3])], {})
    assert any(f.startswith("HISTORY") for f in got[0]["flags"])
    # a modest number is not held to it
    got = L.lint_likely([_likely(model_prob=0.45, recent_values=[2, 3, 1, 4, 2, 3])], {})
    assert not any(f.startswith("HISTORY") for f in got[0]["flags"])


def test_the_script_against_the_side_and_a_role_misfit_are_named():
    got = L.lint_likely([_likely(game_script={"archetype": "Ground and pound", "tilt": 0.90}),
                         _likely(player="A Quarterback", position="QB", market="receptions")], {})
    assert "SCRIPT against the side" in got[0]["flags"]
    assert "ROLE QB on receptions" in got[1]["flags"]


def test_a_player_twice_on_the_board_is_counted():
    got = L.lint_likely([_likely(), _likely(market="rec_yds", line=60.5, projection=71.0)], {})
    assert "REPEAT x2" in got[0]["flags"] and "REPEAT x2" in got[1]["flags"]


def test_rank_only_and_started_are_shown_not_hidden():
    import datetime as dt
    now = dt.datetime(2026, 9, 13, 18, 0, tzinfo=dt.timezone.utc)
    got = L.lint_likely([_likely(bettable=False)], {}, now)
    assert "RANK-ONLY" in got[0]["flags"] and "STARTED" in got[0]["flags"]


# --- Recommended props -----------------------------------------------------------
def test_a_clean_recommended_prop_carries_only_the_script_question():
    got = L.lint_props([_prop()], {})
    assert got[0]["flags"] == ["SCRIPT against the side"]


def test_only_recommended_props_are_read():
    assert L.lint_props([_prop(recommended=False)], {}) == []


def test_the_doctrine_gates_are_checked_on_the_payload():
    rows = [_prop(player="Warned", warnings=["Jared Goff listed QUESTIONABLE — hold"]),
            _prop(player="Refused", reasons=[L.REFUSAL_REASONS[0]]),
            _prop(player="Under Bar", edge=0.01),
            _prop(player="Wrong Grade", quality=85, grade="B+"),
            _prop(player="Over Ladder", stake_units=1.5, grade="B+"),
            _prop(player="No EV", ev_per_unit=-0.01),
            _prop(player="Proxy", book="proxy", has_market=False),
            _prop(player="Gap", hit_prob=0.70, fair_prob=0.52),
            _prop(player="Wrong Way", side="under", projection=262.0, line=249.5)]
    got = L.lint_props(rows, {})
    assert any(f.startswith("WARNED") for f in _flags(got, "Warned"))
    assert any(f.startswith("REFUSED") for f in _flags(got, "Refused"))
    assert any(f.startswith("BAR") for f in _flags(got, "Under Bar"))
    assert "GRADE B+ on quality 85 (bands say A)" in _flags(got, "Wrong Grade")
    assert any(f.startswith("LADDER 1.5u over the") for f in _flags(got, "Over Ladder")), \
        _flags(got, "Over Ladder")
    assert "EV -0.010" in _flags(got, "No EV")
    assert "PROXY no real price" in _flags(got, "Proxy")
    assert any(f.startswith("GAP") for f in _flags(got, "Gap"))
    assert any(f.startswith("PROJ>LINE") for f in _flags(got, "Wrong Way"))


def test_a_stake_the_price_ladder_itself_set_is_not_a_defect():
    """The false positive that started this. Ethan, 2026-09-02, reading
    a +190 game bet flagged for staking 0.66u: "i dont care about what
    grade it allowed how much money." 0.66u IS what the ladder gives
    +190 — the lint was auditing `quality.STAKE_CAP_U`, the per-grade
    ceiling engine/staking retired in August, and calling the shipped
    rule a defect. A check that flags correct rows teaches a reader to
    ignore the flags."""
    from engine.staking import units_for_price
    for odds in (-200, -110, 100, 190, 400):
        allowed = units_for_price(odds)
        row = _gb(odds=odds, stake_units=allowed, grade="B+", quality=74)
        flags = L.lint_game_bets([row], now=None)[0]["flags"]
        assert not any(f.startswith("LADDER") for f in flags), (odds, flags)
        over = _gb(odds=odds, stake_units=allowed + 0.5, grade="B+", quality=74)
        assert any(f.startswith("LADDER") for f in
                   L.lint_game_bets([over], now=None)[0]["flags"]), odds


def test_both_sides_of_one_player_is_named():
    got = L.lint_props([_prop(), _prop(side="under", projection=240.0)], {})
    assert "BOTH SIDES recommended" in got[0]["flags"]


def _gl(**kw):
    """A likelihood GAME row as likely.from_game_bet builds it."""
    d = dict(kind="game", player="Over 43", pick_label="Over 43", team="", home="CHI",
             away="GB", matchup="GB @ CHI", bet_type="total", market="total",
             market_label="Total", side="Over", line=43.0, book="best", odds=-110,
             model_prob=0.55, implied_prob=0.5, bettable=True, rank_auc=0.497,
             ranked=False, rank_note="Shown as the model’s lean at this number.",
             flipped=False, kickoff="2026-09-13T17:00:00+00:00")
    d.update(kw)
    return d


def test_game_rows_say_what_they_are():
    """Ethan, 2026-09-02: spreads and totals go on the board as leans.
    The lint prints the lean with its figure, names a flipped side, and
    refuses a game row the page could not open."""
    rows = [_gl(),
            _gl(player="DET -3.5", pick_label="DET -3.5", team="DET", bet_type="spread",
                market="spread", side="", line=-3.5, home="DET", away="NO",
                matchup="NO @ DET", rank_auc=0.491, flipped=True),
            _gl(player="GB ML", pick_label="GB ML", team="GB", bet_type="moneyline",
                market="moneyline", side="", line=0.0, ranked=True, rank_note="",
                rank_auc=0.641),
            _gl(player="Under 49", pick_label="Under 49", home="MIN", away="DET",
                matchup="DET @ MIN", side="Under", line=49.0, rank_note=""),
            _gl(player="Over 51", pick_label="Over 51", home="", away="", matchup="")]
    got = L.lint_likely(rows, {})
    assert "LEAN measured 0.50" in _flags(got, "Over 43")
    assert "FLIP" in _flags(got, "DET -3.5") and "LEAN measured 0.49" in _flags(got, "DET -3.5")
    assert not any(f.startswith("LEAN") or f == "FLIP" for f in _flags(got, "GB ML"))
    assert "LEAN without its note" in _flags(got, "Under 49")
    assert any(f.startswith("NO DOOR") for f in _flags(got, "Over 51"))


def test_the_same_total_in_two_games_is_two_bets_not_a_repeat():
    """"Over 43" can be the honest pick in two different games on one
    Sunday; the REPEAT check keys a game row within its matchup."""
    rows = [_gl(), _gl(home="MIN", away="DET", matchup="DET @ MIN")]
    got = L.lint_likely(rows, {})
    assert not any(f.startswith("REPEAT") for x in got for f in x["flags"]), got
    twice = [_gl(), _gl()]
    assert "REPEAT x2" in L.lint_likely(twice, {})[0]["flags"]


# --- Game bets -------------------------------------------------------------------
def test_game_bets_are_held_to_their_own_ceiling():
    rows = [_gb(matchup="Clean", quality=74, grade="B+", stake_units=0.5),
            _gb(matchup="Too High", quality=80, grade="A"),
            _gb(matchup="Not Credible", credible=False, quality=74, grade="B+", stake_units=0.5),
            _gb(matchup="Floor", quality=62, grade="Pass")]
    got = L.lint_game_bets(rows)
    assert _flags(got, "Clean") == []
    assert any(f.startswith("QUALITY 80 above") for f in _flags(got, "Too High"))
    assert any(f.startswith("CREDIBLE") for f in _flags(got, "Not Credible"))
    assert any(f.startswith("GRADE quality 62 under") for f in _flags(got, "Floor"))
    assert L.GAME_BET_QUALITY_MAX == 75.0


# --- the injuries page and the whole payload --------------------------------------
def test_the_injuries_page_is_indexed_by_player_not_active_only():
    d = {"sports": {"nfl": [
        {"player": "A. Player", "status": "Active"},
        {"player": "B Player", "status": "Out"},
        {"player": "C  Player", "status": "Questionable"}]}}
    path = os.path.join(tempfile.mkdtemp(), "inj.json")
    with open(path, "w") as fh:
        json.dump(d, fh)
    idx = L.injury_index(path)
    assert idx == {"b player": "Out", "c player": "Questionable"}
    assert L.injury_index(path + ".missing") == {}


def test_the_whole_payload_renders_and_the_cli_is_read_only():
    payload = {"built_at": "2026-09-13T12:00:00Z",
               "most_likely": [_likely(), _likely(player="Held", injury_status="OUT")],
               "recommendations": [_prop()], "game_bets": [_gb()],
               "likely_census": {"listed OUT — held until inactives confirm": 1}}
    d = tempfile.mkdtemp()
    path = os.path.join(d, "board.json")
    with open(path, "w") as fh:
        json.dump(payload, fh)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = L.main(["--file", path, "--injuries", os.path.join(d, "none.json")])
    out = buf.getvalue()
    assert rc == 0
    assert "MOST LIKELY: 2 rows, 1 flagged" in out
    assert "! HELD listed OUT" in out
    assert "GAME BETS: 1 rows, 1 flagged" in out
    assert "likely board refused: 1 listed OUT" in out
    assert L.main(["--file", path + ".missing"]) == 2
    import inspect
    src = inspect.getsource(L)
    for verb in ("INSERT", "UPDATE", "DELETE", 'open(path, "w")', "json.dump("):
        assert verb not in src, verb


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
