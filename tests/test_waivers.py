"""The waiver board — who just gained a role, and why.

The draft kit is a two-week product; this is the one a manager opens
every Tuesday from September to December. The rules worth pinning are
about HONESTY and about the join, because both failed quietly in the
first cut:

  * IT NEVER CLAIMS AVAILABILITY. The site cannot see your league, so
    "free agent" would be a guess with a number beside it. What it
    measures is role change, which is the half a claim is buying.
  * THE TEAM JOIN IS RESOLVED, NOT ASSUMED. The injury feed writes
    clubs out in full and the usage rows carry abbreviations. Compared
    naively they match nothing — and a vacancy section that never fires
    looks exactly like a quiet week rather than a broken one.
  * SECOND IN LINE INHERITS THE JOB. The beneficiary list is ranked by
    the share he ALREADY holds, not by the size of the name that
    vacated.

Run directly: `python3 tests/test_waivers.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import waivers                                    # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _u(player, team, pos, season, delta, weeks=6, last=None):
    return {"player": player, "team": team, "position": pos,
            "metric": "carry share" if pos == "RB" else "target share",
            "season": season, "l4": season, "last": last if last is not None
            else season + delta, "delta": delta, "fp_pg": 8.0, "weeks": weeks}


USAGE = [
    _u("Backup Back", "KC", "RB", 0.28, 0.06),
    _u("Third Back", "KC", "RB", 0.10, 0.01),
    _u("Star Back", "KC", "RB", 0.55, -0.10),
    _u("Slot Guy", "BUF", "WR", 0.14, 0.10),
    _u("Rookie WR", "BUF", "WR", 0.08, 0.05, weeks=2),
    _u("Left Guard", "BUF", "G", 0.00, 0.09),
]


# --- the team join -----------------------------------------------------------

def test_the_full_club_name_resolves_to_the_usage_abbreviation():
    """The bug the first cut shipped with: the feeds spell teams two
    different ways, so the naive comparison found nothing and the
    section silently never fired."""
    assert waivers.team_key("Kansas City Chiefs") == "KC"
    assert waivers.team_key("KC") == "KC"
    assert waivers.team_key("buffalo bills") == "BUF"


def test_an_unmapped_team_passes_through_rather_than_vanishing():
    assert waivers.team_key("Some Unmapped Club") == "SOME UNMAPPED CLUB"
    assert waivers.team_key("") == ""


def test_a_vacancy_joins_across_the_two_spellings():
    got = waivers.vacancies(
        [{"team": "Kansas City Chiefs", "player": "Star Back",
          "position": "RB", "status": "Out"}], USAGE)
    assert [r["player"] for r in got] == ["Backup Back", "Third Back"], got


# --- the vacancy rules -------------------------------------------------------

def test_the_man_second_in_line_ranks_first():
    got = waivers.vacancies(
        [{"team": "KC", "player": "Star Back", "position": "RB",
          "status": "Out"}], USAGE)
    assert got[0]["player"] == "Backup Back", \
        "the beneficiary list is not ranked by the share he already holds"
    assert got[0]["share"] > got[1]["share"]


def test_the_injured_player_is_never_his_own_beneficiary():
    got = waivers.vacancies(
        [{"team": "KC", "player": "Star Back", "position": "RB",
          "status": "Out"}], USAGE)
    assert "Star Back" not in [r["player"] for r in got]


def test_questionable_is_not_a_vacancy():
    """It resolves to "played" often enough that treating it as a lost
    job would fill the board with jobs nobody lost."""
    assert waivers.vacancies(
        [{"team": "KC", "player": "Star Back", "position": "RB",
          "status": "Questionable"}], USAGE) == []
    assert "QUESTIONABLE" not in waivers.VACATING


def test_out_doubtful_and_ir_all_vacate():
    for status in ("Out", "Doubtful", "IR", "Injured Reserve"):
        got = waivers.vacancies(
            [{"team": "KC", "player": "Star Back", "position": "RB",
              "status": status}], USAGE)
        assert got, f"{status} did not vacate the job"


def test_a_lineman_vacancy_moves_nothing_anyone_can_claim():
    assert waivers.vacancies(
        [{"team": "BUF", "player": "Left Guard", "position": "G",
          "status": "Out"}], USAGE) == []


def test_only_the_same_position_group_inherits():
    got = waivers.vacancies(
        [{"team": "KC", "player": "Star Back", "position": "RB",
          "status": "Out"}], USAGE)
    assert all(r["position"] == "RB" for r in got)
    assert "Slot Guy" not in [r["player"] for r in got], \
        "a Buffalo receiver inherited a Kansas City back's carries"


# --- the rising rules --------------------------------------------------------

def test_rising_reads_share_and_ranks_by_the_jump():
    got = waivers.rising(USAGE)
    assert [r["player"] for r in got] == ["Slot Guy", "Backup Back"], got


def test_a_falling_share_is_not_a_waiver_add():
    assert "Star Back" not in [r["player"] for r in waivers.rising(USAGE)]


def test_a_thin_sample_is_not_a_role_change():
    assert "Rookie WR" not in [r["player"] for r in waivers.rising(USAGE)], \
        "two weeks of data was called a coordinator's decision"


def test_a_lineman_never_reaches_the_board():
    assert "Left Guard" not in [r["player"] for r in waivers.rising(USAGE)]


# --- the honesty rule --------------------------------------------------------

def test_the_board_never_claims_a_player_is_available():
    board = waivers.board(USAGE, [{"team": "KC", "player": "Star Back",
                                   "position": "RB", "status": "Out"}])
    blob = repr(board).lower()
    for word in ("free agent", "unrostered", "available in your league"):
        assert word not in blob, \
            f"the board claims {word!r} — it cannot see the reader's league"
    assert "cannot see your league" in board["note"]
    src = _read("web", "js", "app.js")
    i = src.index("function waiverBoardHTML(w)")
    assert "free agent" not in src[i:i + 2500].lower()


def test_every_row_carries_the_sentence_that_put_it_there():
    board = waivers.board(USAGE, [{"team": "KC", "player": "Star Back",
                                   "position": "RB", "status": "Out"}])
    for r in board["vacancies"] + board["rising"]:
        assert r.get("why"), "a row arrived as a score with no story"
        assert r.get("kind") in ("vacancy", "rising")


def test_a_player_can_earn_both_rows():
    """"He is inheriting a job AND his share was already climbing" is two
    reasons to claim him; collapsing them hides the stronger one."""
    board = waivers.board(USAGE, [{"team": "KC", "player": "Star Back",
                                   "position": "RB", "status": "Out"}])
    assert "Backup Back" in [r["player"] for r in board["vacancies"]]
    assert "Backup Back" in [r["player"] for r in board["rising"]]


def test_empty_inputs_are_an_empty_board_not_a_crash():
    board = waivers.board([], [])
    assert board["vacancies"] == [] and board["rising"] == []
    assert board["note"]


# --- the start/sit half ------------------------------------------------------
# A different question from "who to add": the same player is a different
# play against a shootout than against a team that will run the clock
# out on him. What is pinned here is that the number stays HONEST about
# what it is — a ranking of spots, never a projection of points.

SCRIPTS = [
    {"home": "KC", "away": "BUF", "week": "001",
     "home_implied": 27.5, "away_implied": 24.0,
     "home_proe": 4.0, "away_proe": -3.0},
    {"home": "NYJ", "away": "NE", "week": "001",
     "home_implied": 17.0, "away_implied": 19.5,
     "home_proe": 0.0, "away_proe": 1.0},
    # A LATER week for a team already seen — must never override week 1.
    {"home": "KC", "away": "NE", "week": "002",
     "home_implied": 30.0, "away_implied": 15.0,
     "home_proe": 9.0, "away_proe": 0.0},
]

STREAM_USAGE = [
    {"player": "KC Back", "team": "KC", "position": "RB", "last": 0.60,
     "season": 0.55, "weeks": 6, "fp_pg": 15.0},
    {"player": "KC WR", "team": "KC", "position": "WR", "last": 0.28,
     "season": 0.26, "weeks": 6, "fp_pg": 13.0},
    {"player": "BUF WR", "team": "BUF", "position": "WR", "last": 0.30,
     "season": 0.28, "weeks": 6, "fp_pg": 14.0},
    {"player": "Jets WR", "team": "NYJ", "position": "WR", "last": 0.32,
     "season": 0.30, "weeks": 6, "fp_pg": 10.0},
    {"player": "Bit Part", "team": "KC", "position": "WR", "last": 0.04,
     "season": 0.04, "weeks": 6, "fp_pg": 2.0},
    {"player": "Thin Guy", "team": "KC", "position": "WR", "last": 0.40,
     "season": 0.40, "weeks": 1, "fp_pg": 9.0},
    {"player": "No Game", "team": "ZZZ", "position": "WR", "last": 0.50,
     "season": 0.50, "weeks": 6, "fp_pg": 9.0},
    {"player": "A QB", "team": "KC", "position": "QB", "last": 0.0,
     "season": 0.0, "weeks": 6, "fp_pg": 20.0},
]


def test_the_spot_used_is_the_next_game_not_a_later_one():
    st = waivers.streamers(STREAM_USAGE, SCRIPTS)
    assert st["RB"][0]["implied"] == 27.5,         "a team's week-2 total outranked the game actually being started"


def test_quarterbacks_are_absent_rather_than_scored_at_zero():
    """Every share here is targets or carries, which a QB has neither of
    — so his row would score ~0 and rank last, which reads as an opinion
    about him rather than an absent measurement."""
    st = waivers.streamers(STREAM_USAGE, SCRIPTS)
    assert "QB" not in st
    assert "QB" not in waivers.STREAM_POSITIONS


def test_a_bit_part_in_a_great_spot_is_still_a_bit_part():
    st = waivers.streamers(STREAM_USAGE, SCRIPTS)
    assert "Bit Part" not in [r["player"] for r in st["WR"]]


def test_a_thin_sample_and_a_team_with_no_game_are_both_out():
    st = waivers.streamers(STREAM_USAGE, SCRIPTS)
    names = [r["player"] for r in st["WR"]]
    assert "Thin Guy" not in names, "one week of share was called a role"
    assert "No Game" not in names, "a player with no upcoming game was ranked"


def test_the_pass_lean_tilts_backs_and_catchers_opposite_ways():
    pass_lean = [{"home": "KC", "away": "X", "week": "001",
                  "home_implied": 25.0, "away_implied": 20.0,
                  "home_proe": 8.0, "away_proe": 0.0}]
    run_lean = [{"home": "KC", "away": "X", "week": "001",
                 "home_implied": 25.0, "away_implied": 20.0,
                 "home_proe": -8.0, "away_proe": 0.0}]
    rb = [{"player": "B", "team": "KC", "position": "RB", "last": 0.5,
           "season": 0.5, "weeks": 6}]
    wr = [{"player": "W", "team": "KC", "position": "WR", "last": 0.5,
           "season": 0.5, "weeks": 6}]
    rb_pass = waivers.streamers(rb, pass_lean)["RB"][0]["score"]
    rb_run = waivers.streamers(rb, run_lean)["RB"][0]["score"]
    wr_pass = waivers.streamers(wr, pass_lean)["WR"][0]["score"]
    wr_run = waivers.streamers(wr, run_lean)["WR"][0]["score"]
    assert rb_run > rb_pass, "a run-lean offense did not help its back"
    assert wr_pass > wr_run, "a pass-lean offense did not help its receiver"


def test_a_rounding_artefact_is_not_reported_as_a_pass_lean():
    """PROE reads ~0 before any play-by-play is ingested. Printing
    "-0.0 pass rate over expectation" on every row is noise wearing the
    shape of a measurement."""
    flat = [{"home": "KC", "away": "X", "week": "001", "home_implied": 25.0,
             "away_implied": 20.0, "home_proe": -0.04, "away_proe": 0.0}]
    row = waivers.streamers(
        [{"player": "B", "team": "KC", "position": "RB", "last": 0.5,
          "season": 0.5, "weeks": 6}], flat)["RB"][0]
    assert row["proe"] is None
    assert "expectation" not in row["why"]
    assert row["score"] == round(0.5 * 25.0, 2),         "a rounding artefact moved the arithmetic"


def test_the_panel_says_it_ranks_spots_and_not_points():
    src = _read("web", "js", "app.js")
    i = src.index("function streamerHTML(st)")
    body = src[i:src.index("\nfunction ", i + 10)]
    assert "not a projection of points" in body.lower() \
        or "NOT a projection" in body
    assert "Quarterbacks are absent" in body, \
        "the QB gap is missing rather than named"


# --- the wiring --------------------------------------------------------------

def test_the_build_publishes_it_and_survives_a_missing_injury_file():
    src = _read("fantasy_build.py")
    assert '"waivers": _waiver_board(usage)' in src
    assert '"streamers": waivers.streamers(' in src
    i = src.index("def _waiver_board")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "except (OSError, ValueError)" in body, \
        "an unreadable injury file would take the fantasy build down"
    assert "only the rising-role half" in body, \
        "a half-empty board must say why it is half empty"


def test_the_page_gives_it_a_tab_of_its_own():
    src = _read("web", "js", "app.js")
    assert '["waivers", "Waivers & starts",' in src
    assert "streamerHTML(d.streamers)" in src
    assert "waiverBoardHTML(d.waivers)" in src
    # The Sleeper pulse moved in beside it — same question, other source.
    i = src.index('["waivers", "Waivers & starts",')
    assert "waiverPulseHTML(d.trending)" in src[i:i + 400]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
