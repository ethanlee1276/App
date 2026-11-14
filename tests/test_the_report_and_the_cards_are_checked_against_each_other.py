"""A matchup card that reads against the run or pass edge the game report
names is answered in the report's sentence, and the board's self-check
counts any crossing left unanswered (engine/gamescan.crossing_reads;
engine/gamereport.edge_though, sec_short; engine/boardtruth CROSSED).

Ethan, 12 November 2026, the Commanders at the Giants: the short version
said "the Giants' run defense ranks 30th ... so there is room to run for
the Commanders", and the card under it read "Rachaad White vs NYG's run
defense — UNFAVORABLE". "That doesn't make any sense." The cards were
fixed that day (tests/test_the_matchup_card_agrees_with_the_defence_and_
the_weather.py), and the self-check, counting such crossings from that
afternoon, found 8 on the NFL board. Both sides can be true (the edge is
the two-season unit blend, the card this season's yards, the lines and
the forecast), so the report now says why. What these hold:

  * a back read tough or avoid under a run edge for his side crosses it,
    and so does a quarterback or receiver read good under a pass edge
    against his side; a card that agrees, or reads neutral, does not;
  * only the three edges the short version names, and only the offence the
    edge is about, are read;
  * the report's sentence gives the crossing card's own counted reason
    ("…room to run for the Commanders, though the lines expect the
    Commanders to score only about 18 (the Commanders +4.5)") and records
    which edges it answered;
  * the self-check counts only a crossing the report did not answer, and
    the heartbeat gets the count, never the detail (a card is paid).

Run directly: `python3 tests/test_the_report_and_the_cards_are_checked_against_each_other.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boardtruth as T                                   # noqa: E402
from engine import gamereport as R                                   # noqa: E402
from engine import gamescan as G                                     # noqa: E402

RUN_EDGE = {"unit": "rushing", "off": "WAS", "def": "NYG", "off_rank": 19, "def_rank": 30, "gap": 11}
PASS_EDGE = {"unit": "passing", "off": "WAS", "def": "NYG", "off_rank": 17, "def_rank": 3, "gap": -14}
LOW = "The lines expect WAS to score only about 18 (WAS +4.5)"


def _board(edges, players, reports=None):
    b = {"games": [{"away": "WAS", "home": "NYG", "scan": {"edges": edges}}],
         "scan_reads": {"WAS@NYG": {"players": players}}}
    if reports is not None:
        b["game_reports"] = reports
    return b


def _p(name, pos, read, team="WAS", pro=(), con=(), **usage):
    return {"player": name, "team": team, "pos": pos, "read": read, "pro": list(pro), "con": list(con),
            "usage": usage}


def test_which_cards_cross_an_edge():
    reads = [_p("Rachaad White", "RB", "tough"), _p("Chris Rodriguez", "RB", "good"),
             _p("Terry McLaurin", "WR", "avoid"), _p("Tyrone Tracy", "RB", "avoid", team="NYG")]
    assert [x["player"] for x in G.edge_reads(RUN_EDGE, reads)] == ["Rachaad White", "Chris Rodriguez"]
    assert [x["player"] for x in G.crossing_reads(RUN_EDGE, reads)] == ["Rachaad White"]
    passing = [_p("Terry McLaurin", "WR", "good"), _p("Jayden Daniels", "QB", "avoid"),
               _p("Zach Ertz", "TE", "breakout")]
    assert [x["player"] for x in G.crossing_reads(PASS_EDGE, passing)] == ["Terry McLaurin", "Zach Ertz"]
    assert G.crossing_reads({"unit": "explosive", "off": "WAS", "gap": 9}, reads) == []


def test_an_unanswered_crossing_is_counted():
    rep = T.check(_board([RUN_EDGE], [_p("Rachaad White", "RB", "tough")]))
    assert rep["by_check"] == {"CROSSED": 1}, rep
    assert rep["problems"] == ["CROSSED — Rachaad White (WAS RB): card reads tough, the report gives WAS the "
                               "rushing edge (WAS 19 vs NYG 30) and does not say why"], rep["problems"]
    for read in ("good", "neutral", "breakout"):
        assert T.check(_board([RUN_EDGE], [_p("Rachaad White", "RB", read)]))["count"] == 0, read
    rep = T.check(_board([PASS_EDGE], [_p("Terry McLaurin", "WR", "good"), _p("Jayden Daniels", "QB", "avoid")]))
    assert rep["by_check"] == {"CROSSED": 1}, rep


def test_only_the_named_edges_and_the_offence_they_are_about():
    other = {"unit": "overall", "off": "NYG", "def": "WAS", "off_rank": 9, "def_rank": 30, "gap": 21}
    edges = [other, dict(other, unit="explosive"), dict(other, unit="pressure"), RUN_EDGE]
    assert T.check(_board(edges, [_p("Rachaad White", "RB", "avoid")]))["count"] == 0, "the fourth is not named"
    rep = T.check(_board([RUN_EDGE], [_p("Tyrone Tracy", "RB", "avoid", team="NYG"),
                                       _p("Terry McLaurin", "WR", "avoid")]))
    assert rep["count"] == 0, rep
    assert T.check({"games": [{"away": "WAS", "home": "NYG", "scan": {"edges": [RUN_EDGE]}}]})["count"] == 0
    assert T.check({"games": [{"away": "WAS", "home": "NYG"}]})["checked"] == 0


def _ctx(reads, edges):
    game = {"away": "WAS", "home": "NYG", "spread": -4.5, "total": 40.5,
            "scan": {"edges": edges, "units": {}}}
    board = {"games": [game], "scan_reads": {"WAS@NYG": {"players": reads}}}
    return R.Ctx(game, board, names={"WAS": "Commanders", "NYG": "Giants"}), game, board


def test_the_report_says_why_the_card_crosses_the_edge():
    reads = [_p("Rachaad White", "RB", "tough", con=[LOW], carry_share=0.45),
             _p("Chris Rodriguez", "RB", "tough", con=[LOW], carry_share=0.30)]
    c, _, _ = _ctx(reads, [RUN_EDGE])
    why, players = R.edge_though(c, RUN_EDGE)
    assert why == "the lines expect the Commanders to score only about 18 (the Commanders +4.5)", why
    assert players == ["Rachaad White", "Chris Rodriguez"], "the most-used card first"
    tilt = next(x for x in R.sec_short(c, {})["blocks"][0]["items"] if x.startswith("Where the matchup tilts"))
    assert tilt.rstrip(".").endswith("so there is room to run for the Commanders, though the lines expect the Commanders "
                         "to score only about 18 (the Commanders +4.5)"), tilt
    assert R.sec_short(c, {})["crossed"] == [{"unit": "rushing", "off": "WAS",
                                              "players": ["Rachaad White", "Chris Rodriguez"]}]
    # A pass edge against the side, a receiver read good: his reason, the other way.
    soft = "NYG gives up the 3rd-most receiving yards to wide receivers (190 a game)"
    c, _, _ = _ctx([_p("Terry McLaurin", "WR", "good", pro=[soft], tgt_share=0.24)], [PASS_EDGE])
    tilt = next(x for x in R.sec_short(c, {})["blocks"][0]["items"] if x.startswith("Where the matchup tilts"))
    assert tilt.rstrip(".").endswith("should slow down the Commanders' passing game (17th), though the Giants give up the "
                         "third-most receiving yards to wide receivers (190 a game)"), tilt
    # No crossing, no clause and no record: the sentence as before.
    c, _, _ = _ctx([_p("Rachaad White", "RB", "good")], [RUN_EDGE])
    sec = R.sec_short(c, {})
    assert "crossed" not in sec and ", though" not in " ".join(sec["blocks"][0]["items"])


def test_a_crossing_the_report_answered_is_not_counted():
    reads = [_p("Rachaad White", "RB", "tough", con=[LOW], carry_share=0.45)]
    c, game, board = _ctx(reads, [RUN_EDGE])
    report = {"game": "WAS@NYG", "sections": [R.sec_short(c, {})]}
    assert T.check(_board([RUN_EDGE], reads, reports=[report]))["count"] == 0
    # Another game's answer does not cover this one.
    other = {"game": "DAL@PHI", "sections": [R.sec_short(c, {})]}
    assert T.check(_board([RUN_EDGE], reads, reports=[other]))["by_check"] == {"CROSSED": 1}


def test_the_heartbeat_gets_the_count_never_the_detail():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'return {k: rep.get(k) for k in ("checked", "count", "by_check")}' in src
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
