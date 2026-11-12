"""The board's self-check counts a game report that gives a side the run or
pass edge while a matchup card on that offence reads the other way
(engine/boardtruth CROSSED).

Ethan, 12 November 2026, the Commanders at the Giants: the short version
said "the Giants' run defense ranks 30th ... so there is room to run for
the Commanders", and the card under it read "Rachaad White vs NYG's run
defense — UNFAVORABLE". "That doesn't make any sense." The cards were
fixed that day (tests/test_the_matchup_card_agrees_with_the_defence_and_
the_weather.py); this makes the next crossing a number on the heartbeat
the build counts, not a screenshot. What these hold:

  * a back read tough or avoid under "room to run" for his side is
    CROSSED, and so is a receiver read good under "should slow down" his
    passing game;
  * a card that agrees, or reads neutral, is not;
  * only the three edges the short version names, and only the offence the
    edge is about, are read;
  * the heartbeat gets the count, never the detail (a card is paid).

Run directly: `python3 tests/test_the_report_and_the_cards_are_checked_against_each_other.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boardtruth as T                                   # noqa: E402

RUN_EDGE = {"unit": "rushing", "off": "WAS", "def": "NYG", "off_rank": 19, "def_rank": 30, "gap": 11}
PASS_EDGE = {"unit": "passing", "off": "WAS", "def": "NYG", "off_rank": 17, "def_rank": 3, "gap": -14}


def _board(edges, players):
    return {"games": [{"away": "WAS", "home": "NYG", "scan": {"edges": edges}}],
            "scan_reads": {"WAS@NYG": {"players": players}}}


def _p(name, pos, read, team="WAS"):
    return {"player": name, "team": team, "pos": pos, "read": read, "pro": [], "con": []}


def test_the_screenshot_is_a_crossing():
    rep = T.check(_board([RUN_EDGE], [_p("Rachaad White", "RB", "tough")]))
    assert rep["by_check"] == {"CROSSED": 1}, rep
    assert rep["problems"] == ["CROSSED — Rachaad White (WAS RB): card reads tough, the report gives WAS the "
                               "rushing edge (WAS 19 vs NYG 30)"], rep["problems"]
    # The fixed card (rain, favorable) and a neutral one cross nothing.
    for read in ("good", "neutral", "breakout"):
        assert T.check(_board([RUN_EDGE], [_p("Rachaad White", "RB", read)]))["count"] == 0, read


def test_a_receiver_up_under_a_stingy_pass_defense_is_a_crossing():
    rep = T.check(_board([PASS_EDGE], [_p("Terry McLaurin", "WR", "good"), _p("Jayden Daniels", "QB", "avoid"),
                                       _p("Zach Ertz", "TE", "tough")]))
    assert rep["by_check"] == {"CROSSED": 1}, rep
    assert rep["problems"][0].startswith("CROSSED — Terry McLaurin (WAS WR): card reads good, the report gives "
                                         "NYG the passing edge"), rep["problems"]


def test_only_the_named_edges_and_the_offence_they_are_about():
    other = {"unit": "overall", "off": "NYG", "def": "WAS", "off_rank": 9, "def_rank": 30, "gap": 21}
    # The edge the short version does not name (fourth) is not read.
    edges = [other, dict(other, unit="explosive"), dict(other, unit="pressure"), RUN_EDGE]
    assert T.check(_board(edges, [_p("Rachaad White", "RB", "avoid")]))["count"] == 0
    # The Giants' own back is not read against the Commanders' run edge,
    # and a receiver is not read against a run edge.
    rep = T.check(_board([RUN_EDGE], [_p("Tyrone Tracy", "RB", "avoid", team="NYG"),
                                       _p("Terry McLaurin", "WR", "avoid")]))
    assert rep["count"] == 0, rep
    # A game with no reads (or no scan) checks nothing.
    assert T.check({"games": [{"away": "WAS", "home": "NYG", "scan": {"edges": [RUN_EDGE]}}]})["count"] == 0
    assert T.check({"games": [{"away": "WAS", "home": "NYG"}]})["checked"] == 0


def test_the_heartbeat_gets_the_count_never_the_detail():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'return {k: rep.get(k) for k in ("checked", "count", "by_check")}' in src
    # The Status page names it in words.
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    words = more[more.index("const TRUTH_WORDS"):more.index("function truthRowHTML")]
    assert '"CROSSED": "report and a matchup card point opposite ways"' in words


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
