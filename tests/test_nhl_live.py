"""NHL live: the fast scoreboard, a hockey win probability, and the live
line on its own lane — behind football.

Ethan, 2026-10-03: "do all of them" (live lines among them), and "NFL is
still also the most important sport to pull ads and ship for ... make sure
NHL is behind all that ... budget our credits." Checks, one rule each: a
hockey game's chance is two Poisson counts on the clock left, never the
football margin model; the feed's period LABEL ("Q2", "P2") is read for its
number — the fast football win probability never appeared because int()
refused "Q2"; ESPN's hockey abbreviations land on the league's own; the
hockey live-line pull has its own clock, spends the NHL's own money, and
never runs while an NFL or college game is live; the board charts from the
history for free.

Run directly: `python3 tests/test_nhl_live.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import livewp as W                                  # noqa: E402
from engine.sources import livescores as L                      # noqa: E402


def test_a_hockey_chance_is_two_poisson_counts_on_the_clock():
    start = W.hockey_win_prob(0, 3600)
    assert 0.5 < start < 0.56, "home ice is a small edge, and a tie at the horn is a coin flip past it"
    up_late = W.hockey_win_prob(1, 120)
    up_early = W.hockey_win_prob(1, 3000)
    assert up_late > 0.85 > up_early > 0.6
    assert W.hockey_win_prob(0, 0) == W.NHL_OT_HOME, "tied at the horn goes to overtime"
    r = W.reading("nhl", "EDM", "CGY", 1, 90)
    assert r["basis"].startswith("score and clock against the league") and r["possession_blind"]
    assert "pulls its goalie" in r["caveat"]


def test_the_period_label_is_read_for_its_number():
    assert W.seconds_left("nhl", "P2", "10:00") == 600 + 1200
    assert W.seconds_left("nhl", "P4", "3:00") is None, "overtime is not regulation"
    assert W.seconds_left("nfl", "Q2", "7:30") == 2250, "the football fast file's own label"
    assert W.seconds_left("nfl", 2, "7:30") == 2250


def test_espn_hockey_abbreviations_land_on_the_leagues_own():
    assert L._side_key({"displayName": "Tampa Bay Lightning", "abbreviation": "TB"}, "nhl") == "TBL"
    assert L._side_key({"displayName": "Nowhere Name", "abbreviation": "NJ"}, "nhl") == "NJD"
    assert "hockey/nhl/scoreboard" in L.ESPN_SCOREBOARD["nhl"]


def test_the_hockey_live_line_has_its_own_lane_behind_football():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert 'NHL_LINES_CLOCK = "nhl_lines"' in src
    i = src.index("def refresh_nhl(")
    body = src[i:i + 2500]
    assert "not _football_live()" in body and "sport=NHL_LINES_CLOCK" in body
    assert '"nfl", "cfb", "nba", "wnba", "nhl"' in src, "the fast scoreboard loop reads hockey"
    from engine.oddsbudget import budget_sport
    assert budget_sport("nhl_lines") == "nhl", "the NHL's own money"
    b = open(os.path.join(ROOT, "nhl_build.py"), encoding="utf-8").read()
    assert '"--live-lines"' in b and "_ll.attach(out.get(\"games\")" in b
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert 'nhl: "data/live_nhl.json"' in js


def test_football_live_reads_both_football_boards():
    import json
    import tempfile
    import launch
    d = tempfile.mkdtemp()
    nfl, cfb = os.path.join(d, "nfl.json"), os.path.join(d, "cfb.json")
    json.dump({"games": [{"live": {"state": "final"}}]}, open(nfl, "w"))
    json.dump({"games": [{"live": {"state": "live"}}]}, open(cfb, "w"))
    old = launch.NFL_OUT, launch.CFB_OUT
    launch.NFL_OUT, launch.CFB_OUT = nfl, cfb
    try:
        assert launch._football_live() is True
        json.dump({"games": []}, open(cfb, "w"))
        assert launch._football_live() is False
    finally:
        launch.NFL_OUT, launch.CFB_OUT = old


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
