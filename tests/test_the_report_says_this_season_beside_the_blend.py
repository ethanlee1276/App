"""Where a unit's two-season rank sits far from its rank on this season
alone, the report says both (engine/gamescan.now_said, unit_edges;
engine/gamereport.edge_sentence; engine/gameplan.matchup_lines;
engine/askbot.scan_facts; web/js/detail.js scanEdgeLine).

Ethan, 12 November 2026, the Commanders at the Giants: the report's short
version read "the Giants' run defense (30th), so there is room to run",
and the cards under it, which read this season's yards, did not lean the
backs that way. The 30th is the blend the edges are measured on, still
leaning on last season in November; on this season alone the Giants rank
13th. The tale of the tape already gave both. What these hold:

  * each edge carries both sides' this-season ranks where the scan stamped
    them;
  * a sentence gives this season's rank beside the blend once the two sit
    a quarter of the league apart (eight places at the least), and only
    then;
  * the blend still decides the edge: the same edge, the same verdict;
  * the game plan, Ask and the page's mismatch list say it the same way.

Run directly: `python3 tests/test_the_report_says_this_season_beside_the_blend.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as A                                      # noqa: E402
from engine import gameplan as P                                    # noqa: E402
from engine import gamereport as R                                  # noqa: E402
from engine import gamescan as G                                    # noqa: E402

#: The two units as the board read them that morning: Washington's run
#: game 19th (24th this season), the Giants' run defense 30th (13th).
RATINGS = {"WAS": {"games": 8, "blend": 0.57,
                   "off": {"rushing": {"rank": 19, "now_rank": 24}, "passing": {"rank": 17, "now_rank": 18}}},
           "NYG": {"games": 8, "blend": 0.57,
                   "def": {"rushing": {"rank": 30, "now_rank": 13}, "passing": {"rank": 3, "now_rank": 2}}}}

EDGE = {"unit": "rushing", "off": "WAS", "def": "NYG", "off_rank": 19, "def_rank": 30, "gap": 11,
        "off_now": 24, "def_now": 13}


def _ctx(sport="nfl", **scan):
    game = {"away": "WAS", "home": "NYG", "scan": scan} if scan else {"away": "WAS", "home": "NYG"}
    return R.Ctx(game, {"games": [game]}, names={"WAS": "Commanders", "NYG": "Giants"}, sport=sport)


def test_each_edge_carries_this_seasons_ranks():
    run = next(e for e in G.unit_edges("WAS", "NYG", RATINGS) if e["unit"] == "rushing")
    assert (run["off_rank"], run["def_rank"], run["gap"]) == (19, 30, 11)
    assert (run["off_now"], run["def_now"]) == (24, 13)
    # A rating with no stamp (a blend fully this season's) carries None.
    plain = {"WAS": {"off": {"rushing": {"rank": 19}}}, "NYG": {"def": {"rushing": {"rank": 30}}}}
    run = next(e for e in G.unit_edges("WAS", "NYG", plain) if e["unit"] == "rushing")
    assert run["off_now"] is None and run["def_now"] is None


def test_far_apart_is_said_and_near_is_not():
    assert G.now_said(30, 13) == 13, "17 places apart"
    assert G.now_said(19, 24) is None, "5 places: the blend alone"
    assert G.now_said(30, 22) == 22 and G.now_said(30, 23) is None, "eight places is the line"
    assert G.now_said(30, None) is None and G.now_said(None, 13) is None
    # College: a quarter of 134 teams.
    assert G.now_said(100, 70, 134) is None and G.now_said(100, 60, 134) == 60


def test_the_giants_run_defense_reads_both():
    c = _ctx()
    assert R.edge_sentence(c, EDGE) == (
        "the Commanders' run game (19th in the league) faces the Giants' run defense (30th; 13th this "
        "season alone), so there is room to run for the Commanders")
    assert R.edge_sentence(c, EDGE, first=False) == (
        "the Commanders' run game (19th) faces the Giants' run defense (30th; 13th this season alone), "
        "so there is room to run for the Commanders")
    # Within a quarter of the league, the blend alone, word for word as before.
    near = dict(EDGE, def_now=25)
    assert R.edge_sentence(c, near) == (
        "the Commanders' run game (19th in the league) faces the Giants' run defense (30th), so there is "
        "room to run for the Commanders")
    # An edge built before this carried no season ranks: unchanged.
    old = {k: v for k, v in EDGE.items() if not k.endswith("_now")}
    assert R.edge_sentence(c, old) == R.edge_sentence(c, near)


def test_the_blend_still_decides_and_running_text_reads():
    c = _ctx()
    held = {"unit": "rushing", "off": "WAS", "def": "NYG", "off_rank": 28, "def_rank": 14, "gap": -14,
            "off_now": 12, "def_now": 15}
    assert R.edge_sentence(c, held) == (
        "the Giants' run defense (14th in the league) should hold the Commanders' run game "
        "(28th; 12th this season alone) in check")
    few = {"unit": "explosive", "off": "WAS", "def": "NYG", "off_rank": 30, "def_rank": 5, "gap": -25,
           "off_now": 13, "def_now": 9}
    assert R.edge_sentence(c, few) == (
        "the Giants' defense limits big plays (5th in the league) and the Commanders' offense ranks 30th "
        "(13th this season alone) at making them, so expect few chunk plays from the Commanders")


def test_the_plan_and_ask_say_it_too():
    lines = P.matchup_lines({"edges": [EDGE], "method": {"teams": 32}}, "NYG", "WAS")
    assert lines[0] == ("WAS's rushing offence (19th of 32) against NYG's rushing defence "
                        "(30th; 13th this season alone) — edge WAS."), lines
    facts = A.scan_facts({}, {"scan": {"units": RATINGS, "edges": [EDGE], "method": {"teams": 32}}})
    assert facts["mismatches"] == ["WAS offense rushing 19 vs NYG defense rushing 30 (this season alone 13): "
                                   "edge WAS"], facts["mismatches"]


def test_the_page_says_it_the_same_way():
    src = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "function scanEdgeLine(e, n) {" in src
    assert "const apart = Math.max(8, Math.round((n || 32) * 0.25));" in src
    assert "; ${ordinal(now)} this season alone" in src
    assert "const [who, what] = scanEdgeLine(e, n);" in src


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
