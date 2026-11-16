"""College basketball's Parlays page builds, and every ticket is tracked.

Ethan, 2026-11-13: every NBA tool on college. The app showed college a
Parlays tab ("the two-leg builder pairs its Edge and Most Likely picks"),
but the builder ran only for the four leagues Ethan named on 2026-10-31
(engine/twoleg.SPORTS), so college's page could only ever say "No parlays
on this board yet: they build with the board". It builds for college now:

  * from college's own Edge and Most Likely picks, same-game and two-game;
  * the same-game link reads the published priors (two overs in one game
    share its pace, +0.10; two unders are killed), never another league's
    measurement, until college's own games measure one;
  * PROBATION, ENFORCED: college's singles are graded and never staked
    (engine/probation), so a parlay of them is tracked, never staked. The
    stake rule reads the league's record, which knows nothing of probation
    (an Edge book with no record reads as staked), so the board's own flag
    decides, for any league on probation, and the page says why.

THE PAGE AND THE BOARD HOOK RETIRED 2026-11-16 (Ethan, circling Parlays in
the menu: "get rid of these parlays and the parlay page for all sports since
we have replaced it with the game report picks and parlays"). engine/twoleg
still builds college's tickets when asked, and the record still reads the
ones it made; no board asks any more.

Run directly: `python3 tests/test_college_parlays_build_and_stay_tracked.py`
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import parlayledger, twoleg as T             # noqa: E402

DAY = "2099-11-14"


def _prop(player, team, opp, market, side, line, odds, p, **kw):
    return {"player": player, "team": team, "opponent": opp, "market": market, "side": side, "line": line,
            "odds": odds, "book": "DraftKings", "hit_prob": p, "model_prob": p, "recommended": True,
            "has_market": True, "game_date": DAY, "kickoff": f"{DAY}T23:00:00Z", **kw}


def _board(probation=True):
    return {"date": DAY, "probation": probation,
            "recommendations": [_prop("Cooper Flagg", "DUKE", "UNC", "pts", "OVER", 19.5, -110, 0.58),
                                _prop("Kon Knueppel", "DUKE", "UNC", "fg3m", "OVER", 2.5, -105, 0.57),
                                _prop("RJ Davis", "UNC", "DUKE", "pts", "UNDER", 17.5, -110, 0.57),
                                _prop("Mark Sears", "BAMA", "AUB", "ast", "OVER", 3.5, 105, 0.53)],
            "most_likely": [_prop("Cooper Flagg", "DUKE", "UNC", "reb", "OVER", 5.5, -250, 0.80),
                            _prop("RJ Davis", "UNC", "DUKE", "pts", "OVER", 11.5, -300, 0.81),
                            _prop("Johni Broome", "AUB", "BAMA", "reb", "OVER", 7.5, -220, 0.78)]}


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_college_is_one_of_the_parlay_leagues_and_its_journal_reads_its_board():
    assert "cbb" in T.SPORTS and not {"nhl", "wnba", "ufc"} & set(T.SPORTS)
    app = _read("web", "js", "app.js")
    assert 'cbb: ["longshots", "weather"],' in app, "college's tabs (Report Picks among them) show"
    assert parlayledger.BOARD_FILES["cbb"] == "web/data/cbb.json", "the journal reads college's board"


def test_a_college_board_builds_both_pools_on_the_published_priors():
    b = T.build(_board(), "cbb", plan={})
    edge, likely = b["edge"], b["likely"]
    assert edge["same_game"] == 1 and edge["two_game"] == 1, edge
    assert likely["same_game"] == 1, likely
    sg = next(t for t in edge["tickets"] if t["kind"] == T.SAME_GAME)
    assert sg["rho"] == 0.1 and "measured at" not in sg["why"], "a prior, said as one: never a borrowed sample"
    assert {l["team"] for l in sg["legs"]} == {"DUKE"}, "two overs on one team share its pace"
    two_unders = [_prop("A", "DUKE", "UNC", "pts", "UNDER", 15.5, -110, 0.58),
                  _prop("B", "DUKE", "UNC", "reb", "UNDER", 6.5, -110, 0.58)]
    assert T.candidates("cbb", [T._leg(r, r["hit_prob"], "edge") for r in two_unders]) == [], \
        "two unders in one game share its pace the wrong way"


def test_a_board_on_probation_tracks_every_parlay_and_says_why():
    b = T.build(_board(), "cbb", plan={})
    tickets = [t for p in T.POOLS for t in b[p]["tickets"]]
    assert tickets and not any(t["staked"] or t["stake_units"] for t in tickets)
    assert b["probation"] is True and "probation" in b["note"] and "tracked" in b["note"]
    assert T.report(b).endswith("; probation: all tracked")
    # The control: the same legs on a board off probation stake the Edge
    # two-game pair, as the stake rule says (an Edge book with no record
    # reads as staked) — so it is the board's flag that held it back.
    off = T.build(_board(probation=False), "nba", plan={})
    assert any(t["staked"] for t in off["edge"]["tickets"] if t["kind"] == T.TWO_GAME)
    assert "note" not in off and off["probation"] is False


def test_the_board_hook_hangs_no_two_leg_tickets_since_they_retired():
    """The builder still answers when asked (the tests above); the board's
    hook no longer asks, so no board carries `two_leg` and the page that
    drew them is gone."""
    from engine import parlays as P
    board = _board()
    P.attach(board, "cbb", state="normal")
    assert "two_leg" not in board, board.get("two_leg")
    built = T.attach(_board(), "cbb", plan={})
    assert built["two_leg"]["sport"] == "cbb" and built["two_leg"]["edge"]["tickets"]
    assert "function renderParlayPage(" not in _read("web", "js", "app.js")


def test_the_record_page_orders_college_with_the_parlay_leagues():
    rec = _read("web", "js", "record.js")
    assert 'const TL_SPORT_ORDER = ["all", "nfl", "cfb", "nba", "cbb", "mlb"];' in rec, \
        "a college row sorts beside the others, never above the all-leagues row"
    assert '"All leagues"' in rec and '"All four"' not in rec, "five leagues now, and a word that keeps"


def test_a_college_card_badges_its_school_by_espns_id():
    """ESPN keys college logos by school id (engine/cbbteams cards carry
    it); the Most Likely card's badge asked for the abbreviation, which
    names no logo, so the badge removed itself on every college card."""
    app = _read("web", "js", "app.js")
    assert "logoUrl(team(r.team, teamsForSport(state.sport)).id || r.team, state.sport, 20)" in app
    import re
    for f in ("teams.js", "teams_nba.js", "teams_wnba.js", "teams_nhl.js", "teams_mlb.js"):
        assert not re.search(r'\bid\s*:|"id"\s*:', _read("web", "js", f)), \
            f"{f}: a pro league's colours never carry an id, so its badge keeps its abbreviation"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
