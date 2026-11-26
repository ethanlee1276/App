"""The report says it in a member's words (step AHY, 26 November 2026).

Ethan, 26 November: "i just want the game reports reporting the correct infor and data and using the correct info
and date in the right way and wording everyhting correctly for the user". Read off every league's report the way a
member meets them, what read wrong:

  * the case for a side read "The Packers are without Zach Tom (T), out" ("without" and "out" both) and "without X
    (WR), doubtful" for a player who may yet play; it says the positions as the short version does, a doubtful
    player as doubtful;
  * "the third-fewest rushing yards to running backs on the ground" said it twice, and "touchdowns to running backs
    on the ground" was wrong: the backs' touchdowns count the ones they catch;
  * the call's note read "The chance is the price's, not our team ratings': ... the disagreement has carried
    nothing" and ended without a stop;
  * "so we treat them as out until the props come back" read as the props;
  * "Who can score for Lions", "Lions is without", "Lions's field";
  * Script C read "a close game (21% of the simulated games)" two lines under "45% are decided by 8 points or
    fewer": it counts only the favorite's close wins; each script says its own margin, as the table does;
  * the steps-up lines said "(engine/room)", a file name, and "×1.42" where a reader says "by 42%";
  * three backup lines named one stand-in, and each opposed pair said "the scripts pull apart" again;
  * the injury list said a starting lineman out twice, and a bye and its rest edge were two lines of one fact;
  * hockey's "BOS shoots the 11th-fewest a game" (shots what?), baseball's "rarely strikes out (20.5%)" beside a
    22% league, "Phillies' starter's pitch mix" under a table that names the starter, "Elite CSW%" and "K upside
    capped";
  * a basketball report said whatever key matchup its tape carried, though it named another game's teams.

Offline. Run directly: `python3 tests/test_the_report_says_it_in_a_members_words.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", __import__("tempfile").mkdtemp())

from engine import gamereport as R  # noqa: E402

NAMES = {"DET": "Lions", "GB": "Packers"}


def _ctx(injuries=(), **g):
    base = {"home": "DET", "away": "GB", "date": "2099-11-16", "home_ml": -160, "away_ml": 140,
            "scan": {"injuries": list(injuries)}}
    base.update(g)
    return R.Ctx(base, {}, sport="nfl", names=NAMES)


def _said(sec):
    return [i for b in sec["blocks"] if b.get("type") == "list" for i in b["items"]]


def test_the_case_says_who_is_out_once_and_a_doubtful_player_as_doubtful():
    rows = [{"player": "Zach Tom", "team": "GB", "position": "T", "status": "Out"},
            {"player": "Romeo Doubs", "team": "GB", "position": "WR", "status": "Doubtful"}]
    said = _said(R.sec_verdict(_ctx(rows)))
    line = next(s for s in said if "Zach Tom" in s)
    assert line == "The Packers are without tackle Zach Tom, and wide receiver Romeo Doubs is doubtful.", line
    assert not any(", out" in s or "(T)" in s for s in said), said


def test_the_funnels_say_who_once_and_the_backs_touchdowns_are_all_of_them():
    assert set(R.FUNNEL_TO.values()) == {"running backs", "quarterbacks"}
    assert not any("on the ground" in v or "on the run" in v for v in R.FUNNEL_TO.values())


def test_the_calls_note_is_plain_and_ends_as_a_sentence():
    for note in list(R.VERDICT_NOTE.values()) + [R.VERDICT_NOTE_RATED]:
        assert note.endswith("."), note
        assert "price's" not in note and "carried nothing" not in note, note
    short = R.sec_verdict(R.Ctx({"home": "DET", "away": "GB", "home_ml": -160, "away_ml": 140}, {}, sport="nba",
                                names=NAMES))["blocks"][-1]["text"]
    assert short.endswith("."), short


def test_the_team_has_its_article_and_its_possessive():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    for old in ('_h(f"Who can score for {c.name(off)}")', 'starts for {c.name(t)}', '{c.name(t)} is without',
                "{c.name(c.home)}'s field"):
        assert old not in src, old
    assert 'blocks += [_h(f"Who can score for {team_np(c, off)}"), _claimed_list(scorers)]' in src


def test_each_script_says_its_own_margin_as_the_finished_check_does():
    from engine import reportfacts as F
    hist = [0.20, 0.17, 0.21, 0.20, 0.12, 0.10]
    c = R.Ctx({"home": "DET", "away": "GB", "sim": {"margin_hist": hist}}, {}, sport="nfl", names=NAMES)
    lines = next(b for b in R.script_blocks(c) if b.get("type") == "list")["items"]
    assert lines[0].startswith("Script A, DET by 8 to 14 (17% of the simulated games)"), lines[0]
    assert lines[1].startswith("Script B, GB wins (42% of the simulated games)"), lines[1]
    assert lines[2].startswith("Script C, DET by 1 to 7 (21% of the simulated games)"), lines[2]
    assert lines[3].startswith("Script D, DET by 15 or more (20% of the simulated games)"), lines[3]
    assert F.SCRIPT_SAID == {"A": "the favorite by 8 to 14", "B": "the underdog won", "C": "the favorite by 1 to 7",
                             "D": "the favorite by 15 or more"}, "the same margins after the game"
    assert all(len(x.split(":")[0]) <= 60 for x in lines), "the page still sets each lead-in in bold"


def test_the_steps_up_lines_say_no_file_name_and_say_percents():
    from engine import stepup as S
    assert S.by_words(1.42) == "by 42%" and S.lift_bits({"rec_yds": 1.42, "receptions": 1.32}) == \
        "receiving yards by 42% and catches by 32%"
    for words in S.LIFT_WORDS.values():
        assert "engine/" not in words and " him" not in words and " his " not in words, words
    src = (ROOT / "engine" / "stepup.py").read_text(encoding="utf-8")
    assert "in every number we price on him" not in src and "than his own" not in src


def test_a_tickets_backups_and_pulled_apart_scripts_are_said_once():
    lines = R.backup_lines(["If A is out or that number moves: X over 1.5 (-200, 66%)",
                            "If B is out or that number moves: X over 1.5 (-200, 66%)",
                            "If C is out or that number moves: X over 1.5 (-200, 66%)"], 3)
    assert lines == ["If any leg is out or its number moves: X over 1.5 (-200, 66%)"], lines
    two = R.backup_lines(["If A is out or that number moves: X (+100, 50%)",
                          "If B is out or that number moves: Y (+100, 50%)"], 2)
    assert two == ["If A is out or that number moves: X (+100, 50%)",
                   "If B is out or that number moves: Y (+100, 50%)"], two
    from engine import gameparlays as GP
    legs = [{"player": "Tucker Kraft"}, {"player": "Amon-Ra St. Brown"}, {"player": "Sam LaPorta"}]
    needs = [{"margin": -1, "why_margin": "GB chasing or trading scores — teams throw when behind"},
             {"margin": 1, "why_margin": "DET chasing or trading scores — teams throw when behind"},
             {"margin": 1, "why_margin": "DET chasing or trading scores — teams throw when behind"}]
    assert GP.pulled_apart(legs, needs) == (
        "Tucker Kraft needs GB chasing or trading scores, and Amon-Ra St. Brown and Sam LaPorta need DET chasing or "
        "trading scores: the scripts pull apart, so a close game suits this ticket best")


def test_a_ticket_says_the_scripts_pull_apart_once():
    import copy
    import test_a_game_report_says_what_the_board_posts as T
    with T._Env(QB_PARLAY_POST_LATE="off"):
        _result, rep = T._report()
    sec = next(s for s in rep["sections"] if s["key"] == "parlays")
    tickets = [i for b in sec["blocks"] if b.get("type") == "parlays" for i in b["items"]]
    assert tickets, "the fixture posts tickets"
    for t in tickets:
        assert sum("the scripts pull apart" in c for c in t.get("caveats") or []) <= 1, t["caveats"]
    copy.deepcopy(rep)


def test_the_injury_list_says_a_lineman_once_and_a_bye_is_one_line():
    import test_the_game_report_reads_like_the_research as T
    text = R.to_text(T._report())
    inj = text.split("INJURIES AND AVAILABILITY")[1].split("\n\n")[0]
    assert inj.count("Zach Tom") == 1, inj
    assert "DET comes off a bye: 14 days of rest to GB's 7, and two weeks to prepare" in text
    assert "has the rest edge" not in text


def test_a_clause_keeps_a_place_capitalized_and_a_college_build_has_no_nfl_names():
    c = R.Ctx({"home": "DET", "away": "GB"}, {}, sport="nfl", names=NAMES)
    assert R._clause("Detroit gives up the fourth-most catches to tight ends", R._known_names(c)).startswith("Detroit")
    assert R._clause("Takes 69% of the carries", R._known_names(c)) == "takes 69% of the carries"
    cfb = R.Ctx({"home": "IND", "away": "PUR"}, {}, sport="cfb")
    assert cfb.name("IND") == "IND", "a college code never reads as the Colts"


def test_hockey_and_baseball_say_what_they_count():
    nhl = (ROOT / "engine" / "nhl" / "scan.py").read_text(encoding="utf-8")
    assert "shoots {few} a game" not in nhl and "shoots {_most(shots_rank, 'most')} a game" not in nhl
    mlb = (ROOT / "engine" / "mlb" / "scan.py").read_text(encoding="utf-8")
    assert 'f"{opp} rarely strikes out' not in mlb and "strikes out less than most teams" in mlb
    st = (ROOT / "engine" / "mlb" / "statcast.py").read_text(encoding="utf-8")
    assert 'f"Elite CSW%' not in st and '— K upside capped")' not in st and "of pitches (CSW)" in st
    import test_every_league_gets_a_game_report as L
    rep, _ = L._attach(L._mlb_board(), "mlb")
    assert "Zack Wheeler's pitch mix: four-seamers 45%" in R.to_text(rep)


def test_a_quarterback_is_named_and_a_missing_name_reads_as_the_starter():
    assert R._last_name("Jared Goff") == "Goff" and R._last_name("Michael Penix Jr.") == "Penix"
    assert R._last_name("") == "" and R._last_name("Hendon Hooker III") == "Hooker"
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'last = _last_name(who) or "the starter"' in src


def test_a_basketball_report_says_only_its_own_games_matchups():
    import test_every_college_game_gets_a_report as T
    from engine import leaguereport as L
    board = T._board()
    L.attach(board, "cbb", meta={}, out=None, at="2026-11-24T17:30:00")
    osu = next(r for r in board["game_reports"] if r["home"] == "OSU")
    assert "LAM" not in R.to_text(osu) and "Lamar" not in R.to_text(osu), "another game's edge is never said"
    lam = next(r for r in board["game_reports"] if r["home"] == "LAM")
    assert "Edge LAM: LAM's offensive rebounding (6th)" in R.to_text(lam), "its own still is"


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
