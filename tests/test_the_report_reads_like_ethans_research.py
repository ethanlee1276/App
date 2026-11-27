"""The game report learns from Ethan's own Bears at Lions research (step AIE, 27 November 2026).

Ethan sent the research he bet Thanksgiving on, which won: "U need to be doing shit like this for our game reports ...
learn from these reports and structure better and research better for these games". The report already follows its
outline (the market, who is out and what it changes, the units, who's guarding who, the red zone, the scripts, players
to watch, before kickoff). Two of its pieces it did not have, and now does:

  * the touchdown board as one table: our chance, the fair price, the best price and where, and FanDuel's and
    DraftKings' beside it, which is how it read "Gibbs is −270 at FanDuel and DraftKings, −250 at BetMGM" at a
    glance (the report said each scorer in a sentence with one price);
  * how tickets that share a leg play together: how often all of them cash, how often at least one does, and that
    the shared leg missing loses every one ("Swift is on both tickets, so they win together").

The numbers in these fixtures are the test's own, not a real game's.

Offline. Run directly: `python3 tests/test_the_report_reads_like_ethans_research.py`
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, gamereport as R, gamescan as S          # noqa: E402

QUOTES = [{"book": "FanDuel", "line": 0.5, "over_odds": -270}, {"book": "DraftKings", "line": 0.5, "over_odds": -290},
          {"book": "DraftKings", "line": 0.5, "over_odds": -280}, {"book": "BetMGM", "line": 0.5, "over_odds": -250},
          {"book": "proxy", "line": 0.5, "over_odds": -200}, {"book": "Caesars", "line": 0.5, "over_odds": None}]


def test_every_books_price_is_kept_on_the_scorer():
    assert S.td_books({"all_lines": QUOTES}) == {"FanDuel": -270, "DraftKings": -280, "BetMGM": -250}, \
        "each book once at its better price; a proxy and a book with no price are not books"
    reads = {"CHI@DET": {"players": [{"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB"}]}}
    result = {"longshot_watch": [{"player": "Jahmyr Gibbs", "model_prob": 0.67, "odds": -250, "book": "BetMGM",
                                  "all_lines": QUOTES}]}
    assert S.stamp_touchdowns(reads, result) == 1
    td = reads["CHI@DET"]["players"][0]["td"]
    assert td["books"] == {"FanDuel": -270, "DraftKings": -280, "BetMGM": -250} and td["book"] == "BetMGM", td


def _td(p, odds, book, books=None):
    return {"model_prob": p, "odds": odds, "book": book, **({"books": books} if books else {})}


def _ctx():
    g = {"away": "CHI", "home": "DET", "date": "2026-11-26", "kickoff": "13:00", "spread": 1.5, "total": 55.5}
    reads = [
        {"player": "D'Andre Swift", "team": "CHI", "pos": "RB",
         "td": _td(0.53, -115, "DraftKings", {"FanDuel": -125, "DraftKings": -115})},
        {"player": "Colston Loveland", "team": "CHI", "pos": "TE", "td": _td(0.39, 130, "FanDuel", {"FanDuel": 130})},
        {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB",
         "td": _td(0.67, -250, "BetMGM", {"FanDuel": -270, "DraftKings": -280, "BetMGM": -250})},
        {"player": "Amon-Ra St. Brown", "team": "DET", "pos": "WR",
         "td": _td(0.49, -145, "DraftKings", {"FanDuel": -140, "DraftKings": -145})},
        {"player": "Sam LaPorta", "team": "DET", "pos": "TE", "td": _td(0.28, -290, "FanDuel", {"FanDuel": -290})},
    ]
    return R.Ctx(g, {"games": [g], "scan_reads": {"CHI@DET": {"players": reads}}},
                 names={"CHI": "Bears", "DET": "Lions"}, sport="nfl")


def test_the_touchdown_board_is_one_table_by_our_chance():
    t = R.td_board_table(_ctx())
    assert t["type"] == "table" and t["title"] == "The touchdown board", t
    assert t["head"] == ["Scorer", "Ours", "Fair", "Best price", "FanDuel", "DraftKings"]
    assert t["rows"] == [
        ["Jahmyr Gibbs (DET RB)", "67%", "−203", "−250 BetMGM", "−270", "−280"],
        ["D'Andre Swift (CHI RB)", "53%", "−113", "−115 DraftKings", "−125", "−115"],
        ["Amon-Ra St. Brown (DET WR)", "49%", "+104", "−140 FanDuel", "−140", "−145"],
        ["Colston Loveland (CHI TE)", "39%", "+156", "+130 FanDuel", "+130", "—"],
        ["Sam LaPorta (DET TE)", "28%", "+257", "−290 FanDuel (past −250)", "−290", "—"],
    ], t["rows"]
    assert "Our picks take no price past −250" in t["note"] and "a dash means that book posts no price" in t["note"]
    assert not re.search(r"\b(he|him|his)\b", t["note"]), "the board's note names no one by a pronoun"


def test_the_board_sits_in_the_red_zone_and_needs_two_scorers():
    sec = R.sec_redzone(_ctx())
    assert any(b.get("type") == "table" and b.get("title") == "The touchdown board" for b in sec["blocks"]), sec
    one = _ctx()
    one.result["scan_reads"]["CHI@DET"]["players"] = one.result["scan_reads"]["CHI@DET"]["players"][:1]
    assert R.td_board_table(R.Ctx(one.g, one.result, names={"CHI": "Bears", "DET": "Lions"}, sport="nfl")) is None


def _leg(player, p):
    return {"player": player, "market": "anytime_td", "side": "OVER", "line": 0.5, "p": p}


def test_tickets_that_share_a_leg_say_how_they_play_together():
    gibbs = _leg("Jahmyr Gibbs", 0.67)
    tickets = [{"joint": 0.38, "legs": [gibbs, _leg("D'Andre Swift", 0.55)]},
               {"joint": 0.33, "legs": [gibbs, _leg("Amon-Ra St. Brown", 0.49)]},
               {"joint": 0.20, "legs": [_leg("Colston Loveland", 0.39), _leg("Rome Odunze", 0.30)]}]
    heads = ["Touchdown pair 1", "Touchdown pair 2", "Touchdown pair 3"]
    notes = R.shared_leg_notes(tickets, heads)
    # Given Gibbs scores, pair 1's rest comes in at 0.38/0.67 and pair 2's at 0.33/0.67: both 0.67 x 0.567 x 0.493
    # = 19%; at least one 0.67 x (1 - 0.433 x 0.507) = 52%.
    assert notes == [f"Touchdown pair 1 and Touchdown pair 2 both need {GP.pick_words(gibbs)} (67%): both cash about "
                     f"19% of the time and at least one about 52%, and a game without it loses both"], notes


def test_three_on_one_leg_and_the_cases_the_arithmetic_is_not():
    a = _leg("Jahmyr Gibbs", 0.6)
    three = [{"joint": 0.3, "legs": [a, _leg("B", 0.5)]}, {"joint": 0.3, "legs": [a, _leg("C", 0.5)]},
             {"joint": 0.3, "legs": [a, _leg("D", 0.5)]}]
    got = R.shared_leg_notes(three, ["Pair 1", "Pair 2", "Pair 3"])
    # Given A, each rest at 0.5: all three 0.6 x 0.125 = 7.5%; at least one 0.6 x (1 - 0.125) = 52.5%.
    assert got == [f"Pair 1, Pair 2 and Pair 3 all need {GP.pick_words(a)} (60%): all 3 cash about 8% of the time and "
                   f"at least one about 52%, and a game without it loses every one"], got
    b = _leg("B", 0.5)
    same_two = [{"joint": 0.3, "legs": [a, b, _leg("C", 0.7)]}, {"joint": 0.25, "legs": [a, b, _leg("D", 0.6)]}]
    assert R.shared_leg_notes(same_two, ["T1", "T2"]) == [], "two shared legs: not this arithmetic, so said nothing"
    apart = [{"joint": 0.3, "legs": [a, _leg("B", 0.5)]}, {"joint": 0.3, "legs": [_leg("C", 0.5), _leg("D", 0.6)]}]
    assert R.shared_leg_notes(apart, ["T1", "T2"]) == []
    assert R.shared_leg_notes([], []) == []


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
