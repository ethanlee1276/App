"""NFL participation: formation, personnel, box and COVERAGE.

NFL_MODEL §6 parked two rows behind "no data exists" — alignment-level
matchups ("needs coverage/alignment data") and coordinator profiles ("no
tendency feed"). Probed 2026-08-09: nflverse publishes
`pbp_participation_{season}.csv` for every season 2016-2025, 49 MB apiece,
carrying `defense_man_zone_type`, `defense_coverage_type`,
`offense_formation`, `offense_personnel`, `defenders_in_box` and
`number_of_pass_rushers`. The claim was wrong.

Run directly: `python3 tests/test_nflpart.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import nflpart as np                        # noqa: E402


def _play(gid, off, mz="", box="", rush="", form="", pers=""):
    return {"nflverse_game_id": gid, "possession_team": off,
            "defense_man_zone_type": mz, "defenders_in_box": box,
            "number_of_pass_rushers": rush, "offense_formation": form,
            "offense_personnel": pers}


#: One week, two games. SF defends NE's snaps in game one; the second game
#: exists purely so a filter bug shows up as league-wide contamination.
ROWS = (
    [_play("2022_01_NE_SF", "NE", "MAN_COVERAGE", "7", "5")] * 3
    + [_play("2022_01_NE_SF", "NE", "ZONE_COVERAGE", "6", "4")] * 7
    + [_play("2022_01_NE_SF", "SF", "ZONE_COVERAGE", "6", "4",
             "SHOTGUN", "1 RB, 1 TE, 3 WR")] * 4
    + [_play("2022_01_NE_SF", "SF", "", "6", "", "I_FORM",
             "2 RB, 2 TE, 1 WR")] * 1
    # A different game entirely: all zone, never defended by SF.
    + [_play("2022_01_BUF_LA", "BUF", "ZONE_COVERAGE", "6", "4")] * 40
)


def test_a_defence_is_read_only_from_its_own_games():
    """THE BUG THIS EXISTS TO CATCH, and it looked right. The first cut
    took every play where the team did not have the ball — which is every
    OTHER game in the league too, so SF, NE and BAL all came back at 28.6%
    man, 71.3% zone, 6.36 in the box on real 2022 data. Three teams
    reading the league average to three decimals is the tell."""
    sf = np.coverage_rates(ROWS, "SF")
    assert sf["n_labelled"] == 10, sf          # NE's 10 labelled snaps only
    assert sf["man_rate"] == 0.3
    assert sf["zone_rate"] == 0.7
    # The 40-play all-zone game must not touch it.
    assert sf["zone_rate"] != np.coverage_rates(ROWS)["zone_rate"]


def test_the_rate_is_over_labelled_plays_not_over_every_snap():
    """Coverage is classified on DROPBACKS: on real 2022 data 18,975 of
    50,150 plays carry a label. Dividing by every play would report every
    defence as playing zone a third of the time, which is a statement
    about run-pass balance wearing a coverage label."""
    ne = np.coverage_rates(ROWS, "NE")         # SF's 5 snaps, 4 labelled
    assert ne["n_labelled"] == 4
    assert ne["zone_rate"] == 1.0              # not 4/5


def test_blitz_is_five_or_more_rushers():
    sf = np.coverage_rates(ROWS, "SF")
    assert sf["n_dropbacks"] == 10 and sf["blitz_rate"] == 0.3


def test_offence_and_defence_read_the_file_from_opposite_sides():
    """`coverage_rates` wants the DEFENDING team and `formation_rates` the
    team with the ball. Passing the same team to both and comparing is a
    mistake that produces plausible nonsense, so it is pinned."""
    f = np.formation_rates(ROWS, "SF")
    assert f["n"] == 5 and f["rates"]["SHOTGUN"] == 0.8
    assert np.formation_rates(ROWS, "NE")["n"] == 0


def test_personnel_groupings_come_back_biggest_first():
    p = np.personnel_rates(ROWS, "SF")
    assert p["n"] == 5
    assert list(p["rates"])[0] == "1 RB, 1 TE, 3 WR"


def test_an_unlabelled_season_reports_none_rather_than_zero():
    """None means "not measured"; 0.0 means "measured, and it is zero".
    A defence that never played man is a real finding and must not read
    the same as a season nobody classified."""
    blank = [_play("2022_01_NE_SF", "NE")] * 5
    c = np.coverage_rates(blank, "SF")
    assert c["man_rate"] is None and c["zone_rate"] is None
    assert c["n_labelled"] == 0


def test_a_malformed_game_id_defends_nobody_instead_of_everybody():
    """The team filter reads the game id. If that id is unparseable the
    safe answer is to drop the play — counting it for every team is how a
    filter bug turns into a league average again."""
    assert np._game_teams({"nflverse_game_id": "garbage"}) == set()
    assert not np._defends({"nflverse_game_id": "", "possession_team": "NE"},
                           "SF")


def test_teams_in_lists_what_the_file_actually_holds():
    assert np.teams_in(ROWS) == ["BUF", "NE", "SF"]


def test_nothing_in_this_module_prices_anything():
    """THE_INFORMATION_TEST: the claimed edge measures AUC 0.479, so a new
    input into the pricing path is the move that finding rules out. This
    is a probe and a tendency, not a grade."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "sources", "nflpart.py"), encoding="utf-8").read()
    for banned in ("edge", "grade", "stake", "hit_prob"):
        assert f"{banned} =" not in src and f"\"{banned}\"" not in src, banned


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
