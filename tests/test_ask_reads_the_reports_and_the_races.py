"""Ask Qellys reads the game reports, how they did, and the playoff races (POLISH7, 2026-11-17).

Ethan, 2026-11-17: "make sure the ask qellys feature is working correctly and
has access to everything on the site and the game reports and all the data".
What Ask could not reach before this: a game's report unless the question named
a game on the board it was asked from (and then without the call on who wins,
the angles, the red zone or how the game should go); a finished game's report,
its fact check and how each of its picks and parlays did; the reports' own
record; the report picks' and the game parlays' records; and the playoff races.

Guarded here: the call, the angles, the red zone and the script ride with any
named game's report; game_report finds a team's game tonight (its picks and
parlays with it) or else its newest finished one (the final, the fact check,
what it said, each pick and leg won or lost); report_record totals the finished
games; our_record carries the Report book and the game parlays; playoff_race
reads a race as its page draws it; and every new lookup is dispatched and given
its chip.

    python3 tests/test_ask_reads_the_reports_and_the_races.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_ASK_CACHE", str(Path(tempfile.mkdtemp()) / "ask_cache.json"))
os.environ.setdefault("QB_ASK_USAGE", str(Path(tempfile.mkdtemp()) / "ask_usage.json"))

from engine import askbot as AB  # noqa: E402
from engine import reportarchive as RA  # noqa: E402
from engine import reportrecord as RR  # noqa: E402


class _Sibling:
    """A sibling test module's fixtures, loaded when first used (a sibling is not imported at module scope)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


MARKS = _Sibling("test_every_finished_game_marks_its_picks_and_parlays")
RACES = _Sibling("test_the_race_pages")

VERDICT = {"key": "verdict", "blocks": [
    {"type": "winner", "team": "DET", "other": "NE", "name": "Lions", "other_name": "Patriots", "chance": 0.71,
     "word": "likely", "source": "market", "ratings": {"team": "DET", "name": "Lions", "chance": 0.64},
     "sim": {"team": "DET", "chance": 0.68}},
    {"type": "p", "text": "The Lions run on a defense that gives up 5.1 yards a carry."}]}
SECTIONS = [VERDICT,
            {"key": "short", "blocks": [{"type": "p", "text": "Detroit should control it on the ground."}]},
            {"key": "angles", "blocks": [{"type": "list", "items": ["Gibbs gets the goal-line work."]}]},
            {"key": "redzone", "blocks": [{"type": "p", "text": "Inside the 20, Detroit scores touchdowns 68% of the time."}]},
            {"key": "scripts", "blocks": [{"type": "p", "text": "A lead by the half, then the run game."}]}]


def _kept_archive():
    """NE at DET, finished and graded, with the set its report carried; the ledger beside it."""
    where = Path(tempfile.mkdtemp())
    report = {"away": "NE", "home": "DET", "sections": SECTIONS,
              "graded": {"status": "graded", "right": 7, "graded": 10,
                         "groups": [{"key": "matchups", "right": 3, "graded": 4}],
                         "call": {"team": "DET", "right": True},
                         "injuries": {"right": 5, "wrong": 1, "missed_names": ["A Regular"]},
                         "tds": {"n": 4, "scored": 2, "expected": 1.6}}}
    doc = {"sport": "nfl", "date": "2026-11-15", "label": "2026-W11", "away": "NE", "home": "DET", "game": "NE@DET",
           "final": {"away": 10, "home": 35}, "report": report, "results": {}, "parlays": MARKS.KEPT}
    RA.write(RA.path_for(where, "nfl", "2026-11-15", "NE", "DET"), doc)
    RR.refresh(where, "nfl")
    return where


def _with_archive(where, ledger):
    AB._archive_dir = lambda: where
    AB.LEDGER_DB = str(ledger)


def _tonight():
    return {"games": [{"home": "BUF", "away": "KC", "spread": -2.5, "total": 47.5}],
            "game_reports": [{"away": "KC", "home": "BUF", "sections": [dict(VERDICT, blocks=[dict(
                VERDICT["blocks"][0], team="BUF", other="KC", name="Bills", other_name="Chiefs")])]}],
            "report_bets": [{"player": "James Cook", "market": "rush_yds", "side": "OVER", "line": 64.5,
                             "home": "BUF", "away": "KC", "model_prob": 0.62},
                            {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER", "line": 74.5,
                             "home": "DET", "away": "NE", "model_prob": 0.6}],
            "game_parlays": {"games": [{"home": "BUF", "away": "KC", "threes": [{"legs": [
                {"player": "James Cook", "market": "rush_yds", "side": "OVER", "line": 64.5},
                {"player": "Josh Allen", "market": "pass_yds", "side": "OVER", "line": 240.5},
                {"player": "Travis Kelce", "market": "receptions", "side": "OVER", "line": 4.5}], "joint": 0.21}],
                "scorers": []}]}}


def test_a_named_game_s_report_brings_the_call_the_angles_and_the_red_zone():
    facts = AB.report_facts({"game_reports": [{"away": "NE", "home": "DET", "sections": SECTIONS}]},
                            {"away": "NE", "home": "DET"})
    call = facts["who_we_think_wins"]
    assert call["pick"] == "Lions" and call["over"] == "Patriots" and call["chance"] == 0.71
    assert call["our_ratings_alone"]["chance"] == 0.64 and "unproven" in call["our_ratings_alone"]["note"]
    assert call["our_simulation"] == {"pick": "DET", "chance": 0.68}
    assert call["the_case"] == ["The Lions run on a defense that gives up 5.1 yards a carry."]
    assert facts["angles"] == ["Gibbs gets the goal-line work."]
    assert facts["red_zone"] and facts["how_it_should_go"] and facts["short_version"]


def test_a_long_report_drops_its_least_needed_parts_first():
    long = [dict(s) for s in SECTIONS] + [{"key": "context", "blocks": [{"type": "list", "items": ["x" * 390] * 40}]}]
    facts = AB.report_facts({"game_reports": [{"away": "NE", "home": "DET", "sections": long}]},
                            {"away": "NE", "home": "DET"})
    import json
    assert len(json.dumps(facts, ensure_ascii=False)) <= AB.REPORT_CHARS
    assert "who_we_think_wins" in facts and "short_version" in facts, "the call and the short version stay"


def test_tonight_s_game_report_brings_its_own_picks_and_parlays():
    out = AB.game_report({"nfl": _tonight()}, "Bills", "nfl")
    assert out["status"] == "not finished" and out["league"] == "nfl"
    assert out["game_report"]["who_we_think_wins"]["pick"] == "Bills"
    assert [p["player"] for p in out["report_picks"]] == ["James Cook"], "only this game's picks"
    assert out["report_parlays"][0]["pool"] == "three-leg parlay" and len(out["report_parlays"][0]["legs"]) == 3
    assert AB.game_report({"nfl": _tonight()}, "Chiefs", "nfl", "Bills")["status"] == "not finished"


def test_a_finished_game_s_report_says_how_it_did_and_marks_each_pick_and_leg():
    _with_archive(_kept_archive(), MARKS._journal())
    out = AB.game_report({"nfl": {}}, "Patriots", "nfl")
    assert out["status"] == "finished" and out["date"] == "2026-11-15"
    assert out["final"] == "NE 10, Lions 35" or out["final"].endswith("35")
    did = out["how_the_report_did"]
    assert did["our_call"] == {"pick": "Lions", "right": True, "chance": 0.71}
    assert did["reads_right"] == "7 of 10" and did["reads_right_by_kind"] == {"matchups": "3 of 4"}
    assert did["injury_report_right"] == "5 of 6" and did["regulars_the_injury_report_missed"] == 1
    assert did["touchdowns"].startswith("2 of the 4")
    assert out["what_the_report_said"]["who_we_think_wins"]["pick"] == "Lions"
    picks = {p["bet"]: p for p in out["report_picks"]}
    assert picks["Jahmyr Gibbs over 74.5 Rushing Yards"]["result"] == "won"
    assert picks["Jahmyr Gibbs over 74.5 Rushing Yards"]["finished_with"] == 142
    three = out["report_parlays"][0]
    assert three["ticket"] == "three-leg parlay" and three["result"] == "lost"
    assert [l["result"] for l in three["legs"]] == ["won", "lost", "won"]
    assert out["earlier_versions"] == {"three-leg parlay": "1 of 1 hit"}
    assert AB.game_report({"nfl": {}}, "Packers", "nfl").get("found") is False


def test_the_reports_record_totals_every_finished_game():
    _with_archive(_kept_archive(), MARKS._journal())
    out = AB.report_record("nfl")["leagues"]["nfl"]
    assert out["every_game"]["games"] == 1 and out["every_game"]["call_right"] == "1 of 1"
    assert out["every_game"]["reads_right"] == "7 of 10"
    assert out["newest_games"][0]["our_call"]["pick"] == "Lions"
    assert AB.report_record("nba").get("found") is False


def test_the_record_brings_the_report_book_and_the_game_parlays():
    rec = {"report": {"settled": 12, "wins": 8, "losses": 4, "net_units": 2.6},
           "report_by_sport": {"nfl": {"settled": 5, "wins": 3, "losses": 2, "net_units": 0.4}},
           "game_parlay_record": {"nfl": {"threes": {"graded": 9, "wins": 2, "losses": 7, "net_units": -1.5,
                                                     "one_away": 4, "chance": 0.24,
                                                     "legs": {"graded": 27, "won": 18}}}}}
    out = AB.record_facts(rec)
    assert out["game_report_picks"]["wins"] == 8
    assert out["game_report_parlays"]["nfl"]["three-leg parlay"]["lost_by_one_leg"] == 4
    assert out["game_report_parlays"]["nfl"]["three-leg parlay"]["legs_hit"] == "18 of 27"
    assert AB.record_facts(rec, "nfl")["game_report_picks"]["wins"] == 3
    assert "game_report_parlays" not in AB.record_facts(rec, "nba")


def test_the_playoff_race_is_read_as_its_page_draws_it():
    d = RACES._nfl()
    AB._paid = lambda name, data_dir=None: d if name == "nfl_race.json" else {}
    out = AB.playoff_race("nfl")
    one = d["today"]["AFC"]["seeds"][0]
    assert out["race"] == "the NFL playoffs" and out["today"]["AFC"]["seeds"][0].startswith(f"1. {one['team']}")
    assert len(out["today"]["AFC"]["seeds"]) == 7 and "just_outside" in out["today"]["AFC"]
    lead = [x["playoffs"] for x in out["best_chances"]]
    assert lead == sorted(lead, reverse=True) and len(lead) <= AB.RACE_TEAMS
    if d["swing"]:
        assert out["games_that_swing_it"][0]["moves"]
    team = AB.playoff_race("nfl", one["team"])
    assert list(team["team"].values())[0]["playoffs"] == round(d["chances"][one["team"]]["playoffs"], 3)
    assert AB.playoff_race("cfb").get("found") is False, "a race not built says so"
    assert "error" in AB.playoff_race("mlb")


def test_the_new_lookups_are_dispatched_and_chipped():
    names = [t["name"] for t in AB.TOOLS]
    assert {"game_report", "report_record", "playoff_race"} <= set(names)
    for name in ("game_report", "report_record", "playoff_race"):
        assert AB.run_tool(name, {}, {}).get("error") != f"there is no lookup called {name}"
    assert AB.tool_source("game_report", {}, {"status": "finished", "game": "NE at DET"})["label"] == \
        "NE at DET, the report and how it did"
    assert AB.tool_source("report_record", {}, {"leagues": {}})["label"] == "How our reports did"
    assert AB.tool_source("playoff_race", {}, {"race": "the NFL playoffs"})["label"] == "The race for the NFL playoffs"
    import re
    said = AB.SYSTEM.replace("never he or she", "") + " ".join(t["description"] for t in AB.TOOLS)
    assert not re.findall(r"\b(?:he|his|him)\b", said), "Ask's prompt and lookups are player-neutral"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print()
    print(f"{fails} failed" if fails else f"{ran} tests passed.")
    sys.exit(1 if fails else 0)
