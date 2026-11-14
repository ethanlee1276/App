"""Look up a team, and how it has actually gone against somebody.

Ethan, 2026-09-09: *"I should be able to search for the Los Angeles Rams,
and look at how they've played against any team in the past. And it
should also show any other data and shit for teams that would be useful
like offense rank and defense rank and past wins and loss and shit like
that."*

Every fixture here is built in memory. The real answer lives in whatever
finals the machine has ingested, and a test that read them would be
asserting facts about this box — the rule
tests/test_backup_remote.py has the long version of.

THE ONE THING MOST WORTH GUARDING is the spread sign. `games.spread` is
the HOME team's number, and every ATS record in the module turns on
that. Getting it backwards is invisible: the page still shows a plausible
cover record, just the other team's. So the fixtures below are built
from cases where the right answer and the wrong answer differ, and
`test_the_dog_that_lost_by_less_than_the_number_covered` is the one that
would catch a flip.

Run directly: `python3 tests/test_teamdex.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, teamdex as T                          # noqa: E402


def _conn(*games):
    """`(season, period, home, away, hs, as_, spread, total)` rows."""
    c = db.connect(":memory:")
    c.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score, spread, total) "
        "VALUES ('nfl',?,?,?,?,?,?,?,?,?)",
        [(s, p, f"{h}{a}{s}{p}", h, a, hs, a_s, sp, to)
         for (s, p, h, a, hs, a_s, sp, to) in games])
    c.commit()
    return c


#: Rams and Seahawks, three meetings, chosen so every ATS and O/U branch
#: has a case whose wrong answer differs from its right one.
_H2H = (
    # Rams away, Seattle laying 2.5, Seattle wins by 4 → Seattle covers.
    (2025, "021", "SEA", "LA", 31, 27, -2.5, 45.5),
    # Rams home, laying 7, win by 3 → Rams win the game, lose the spread.
    (2024, "010", "LA", "SEA", 24, 21, -7.0, 44.0),
    # Rams away as a 10-point dog, lose by 3 → cover. The row that would
    # read backwards if the sign were flipped.
    #
    # THE NUMBER IS -10, and I wrote +10 first. `spread` is the HOME
    # team's line: +10 would make SEATTLE the ten-point dog, at home,
    # which is the opposite fixture and grades the opposite way. The
    # comment above was right and the data under it was wrong — exactly
    # the mistake this test exists to catch, made while writing it.
    (2023, "005", "SEA", "LA", 20, 17, -10.0, 36.5),
)


# ------------------------------------------------------------ the sign

def test_the_dog_that_lost_by_less_than_the_number_covered():
    """The whole file in one row. Losing by 3 as a 10-point underdog is a
    cover, and a flipped sign reports it as a loss against the spread
    while everything else on the page still looks right."""
    c = _conn(*_H2H)
    g = {x["season"]: x for x in
         T.head_to_head(c, "nfl", "LA", "SEA")["games"]}
    assert g[2023]["result"] == "L", "the Rams lost that game"
    assert g[2023]["covered"] is True, "…and covered it"
    assert g[2023]["line"] == 10.0, "away side of a -10 home number"


def test_winning_the_game_and_losing_the_number_are_told_apart():
    c = _conn(*_H2H)
    g = {x["season"]: x for x in
         T.head_to_head(c, "nfl", "LA", "SEA")["games"]}
    assert g[2024]["result"] == "W" and g[2024]["covered"] is False
    assert g[2024]["line"] == -7.0, "home side keeps the stored sign"


def test_a_number_landing_exactly_is_a_push_not_a_win():
    c = _conn((2025, "001", "LA", "SEA", 27, 24, -3.0, 51.0))
    g = T.head_to_head(c, "nfl", "LA", "SEA")["games"][0]
    assert g["covered"] == "push"
    s = T.head_to_head(c, "nfl", "LA", "SEA")["summary"]
    assert (s["ats_w"], s["ats_l"], s["ats_p"]) == (0, 0, 1)


def test_a_total_landing_exactly_is_a_push_too():
    c = _conn((2025, "001", "LA", "SEA", 27, 24, -3.0, 51.0))
    assert T.head_to_head(c, "nfl", "LA", "SEA")["games"][0]["ou"] == "push"


def test_a_game_with_no_line_is_counted_but_not_graded():
    """A final we hold no spread for is still a win or a loss. Scoring it
    as an ATS loss would quietly invent a record."""
    c = _conn((2025, "001", "LA", "SEA", 27, 24, None, None))
    h = T.head_to_head(c, "nfl", "LA", "SEA")
    assert h["games"][0]["covered"] is None and h["games"][0]["ou"] is None
    s = h["summary"]
    assert s["record"] == "1-0"
    assert (s["ats_w"], s["ats_l"], s["ats_p"]) == (0, 0, 0)
    assert (s["over"], s["under"]) == (0, 0)


# --------------------------------------------------------- the head to head

def test_the_summary_is_the_team_you_looked_up_not_the_home_team():
    c = _conn(*_H2H)
    h = T.head_to_head(c, "nfl", "LA", "SEA")
    assert h["summary"]["record"] == "1-2", h["summary"]
    # 27 + 24 + 17 for, 31 + 21 + 20 against.
    assert h["summary"]["pf_per_game"] == 22.7, h["summary"]
    assert h["summary"]["pa_per_game"] == 24.0, h["summary"]
    # …and asked the other way round it is the mirror image, not a
    # second answer.
    back = T.head_to_head(c, "nfl", "SEA", "LA")
    assert back["summary"]["record"] == "2-1"
    assert back["summary"]["pf_per_game"] == h["summary"]["pa_per_game"]


def test_the_meetings_come_back_newest_first():
    c = _conn(*_H2H)
    seasons = [g["season"] for g in
               T.head_to_head(c, "nfl", "LA", "SEA")["games"]]
    assert seasons == [2025, 2024, 2023], seasons


def test_a_matchup_that_never_happened_is_empty_and_not_an_error():
    c = _conn(*_H2H)
    h = T.head_to_head(c, "nfl", "LA", "GB")
    assert h["games"] == [] and h["summary"]["games"] == 0
    assert h["summary"]["record"] == "0-0"


def test_a_scheduled_game_is_not_a_result():
    """A fixture with a line and no score is on the board tonight. Half
    the table would count it as a loss."""
    c = _conn((2025, "001", "LA", "SEA", 27, 24, -3.5, 44.0),
              (2026, "001", "LA", "SEA", None, None, -2.0, 47.0))
    h = T.head_to_head(c, "nfl", "LA", "SEA")
    assert len(h["games"]) == 1 and h["summary"]["record"] == "1-0"


# ------------------------------------------------------------- the ranks

def test_offense_and_defense_are_ranked_within_their_own_season():
    """A rank is meaningless without the field it was taken from, so it
    never travels without one."""
    c = _conn((2025, "001", "LA", "SEA", 40, 10, None, None),
              (2025, "002", "GB", "CHI", 20, 17, None, None),
              (2025, "003", "SEA", "CHI", 13, 10, None, None))
    p = T.profile(c, "nfl", "LA")
    row = p["seasons"][0]
    assert row["season"] == 2025
    assert row["offense_rank"] == 1, row      # 40 a game, best in the set
    assert row["defense_rank"] == 1, row      # 10 allowed, also best
    assert row["teams_ranked"] == 4, row
    assert p["name"] == "Los Angeles Rams"


def test_two_teams_with_the_same_number_share_a_rank():
    """Breaking a tie alphabetically puts a number on the page that means
    nothing — two defences allowing 20.0 are the same defence."""
    c = _conn((2025, "001", "LA", "SEA", 20, 20, None, None),
              (2025, "002", "GB", "CHI", 20, 20, None, None))
    ranks = {t: T.profile(c, "nfl", t)["seasons"][0]["offense_rank"]
             for t in ("LA", "SEA", "GB", "CHI")}
    assert set(ranks.values()) == {1}, ranks


def test_each_season_is_ranked_on_its_own_and_stamped_with_the_year():
    c = _conn((2024, "001", "LA", "SEA", 10, 40, None, None),
              (2025, "001", "LA", "SEA", 40, 10, None, None))
    p = T.profile(c, "nfl", "LA")
    by = {r["season"]: r for r in p["seasons"]}
    assert by[2025]["offense_rank"] == 1 and by[2024]["offense_rank"] == 2
    assert [r["season"] for r in p["seasons"]] == [2025, 2024], "newest first"
    assert p["career"]["record"] == "1-1"


# ---------------------------------------------------------- the opponents

def test_the_picker_only_offers_teams_there_are_games_against():
    """Offering all 32 clubs would advertise pages that open empty."""
    c = _conn((2025, "001", "LA", "SEA", 27, 24, None, None),
              (2024, "001", "SEA", "LA", 20, 17, None, None),
              (2024, "002", "LA", "GB", 30, 20, None, None),
              (2024, "003", "GB", "CHI", 10, 7, None, None))
    got = T.opponents(c, "nfl", "LA")
    assert [o["team"] for o in got] == ["SEA", "GB"], got
    assert got[0]["games"] == 2 and got[1]["games"] == 1
    assert "CHI" not in [o["team"] for o in got]


# ------------------------------------------------------------- the naming

def test_a_full_name_a_nickname_and_an_abbreviation_all_find_the_team():
    pool = ["LA", "LAC", "SEA", "LV"]
    assert T.resolve("Los Angeles Rams", "nfl", pool) == ["LA"]
    assert T.resolve("rams", "nfl", pool) == ["LA"]
    assert T.resolve("la", "nfl", pool)[0] == "LA", "the abbreviation leads"


def test_an_ambiguous_city_offers_both_rather_than_picking_one():
    """Los Angeles is two teams. Choosing for him is the difference
    between a lookup and a guess."""
    got = T.resolve("los angeles", "nfl", ["LA", "LAC", "SEA"])
    assert set(got) == {"LA", "LAC"}, got


def test_a_single_letter_does_not_match_half_the_league():
    assert T.resolve("a", "nfl", ["LA", "LAC", "SEA", "ATL"]) == []
    assert T.resolve("", "nfl", ["LA"]) == []


def test_a_fragment_of_a_word_is_not_a_team():
    """"ram" is not the Rams. Substring matching would make every query a
    prefix of something and the picker useless."""
    assert T.resolve("ram", "nfl", ["LA", "SEA"]) == []


def test_a_team_the_map_has_never_heard_of_is_still_itself():
    """College keys a school we could not resolve as `espn:61`. The page
    shows the id rather than inventing a name for it, and the lookup
    still works on the id."""
    assert T.label("espn:61", "cfb") == "espn:61"
    assert T.resolve("espn:61", "cfb", ["espn:61", "espn:2"]) == ["espn:61"]



def test_the_ats_record_is_the_team_you_asked_about_not_the_home_side():
    """Two away trips where the HOME side covered. The Rams are 0-2
    against the number; a summary that credited whoever covered — rather
    than checking it was the side we are looking at — reads 2-0.

    Deliberately asymmetric. The three-game fixture above happens to
    produce the same TOTALS either way, so it cannot see this at all: it
    has one away cover and one away loss, and swapping them keeps 1-2.
    """
    c = _conn((2025, "001", "SEA", "LA", 31, 20, -2.5, 44.0),
              (2024, "001", "SEA", "LA", 28, 24, -1.5, 44.0))
    s = T.head_to_head(c, "nfl", "LA", "SEA")["summary"]
    assert (s["ats_w"], s["ats_l"]) == (0, 2), s
    back = T.head_to_head(c, "nfl", "SEA", "LA")["summary"]
    assert (back["ats_w"], back["ats_l"]) == (2, 0), back


def test_the_season_row_grades_the_spread_from_the_right_side_too():
    """`profile` walks the same accumulator from both seats in one pass —
    home and away in the same loop — so it is the likeliest place for the
    two to disagree."""
    c = _conn((2025, "001", "SEA", "LA", 31, 20, -2.5, 44.0),
              (2025, "002", "SEA", "LA", 28, 24, -1.5, 44.0))
    la = T.profile(c, "nfl", "LA")["seasons"][0]
    sea = T.profile(c, "nfl", "SEA")["seasons"][0]
    assert (la["ats_w"], la["ats_l"]) == (0, 2), la
    assert (sea["ats_w"], sea["ats_l"]) == (2, 0), sea


def test_a_game_with_only_one_score_recorded_is_not_a_final():
    """Half a scoreline is a data fault, not a result. Reading it as one
    hands somebody a win or a loss out of a missing field — and the
    filter that stops it is a second clause nothing else in this file
    would notice was gone."""
    c = _conn((2025, "001", "LA", "SEA", 27, 24, None, None),
              (2025, "002", "LA", "SEA", 30, None, None, None),
              (2025, "003", "LA", "SEA", None, 14, None, None))
    h = T.head_to_head(c, "nfl", "LA", "SEA")
    assert len(h["games"]) == 1, [g["period"] for g in h["games"]]
    assert h["summary"]["record"] == "1-0"
    assert T.profile(c, "nfl", "LA")["career"]["games"] == 1

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
