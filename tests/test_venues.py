"""Tests for the venue reference tables (MLB parks, NFL stadiums).

These are hand-entered constants rather than computed values, so the tests
guard the things that actually go wrong with hand-entered constants: a
park quietly missing from the table, a typo'd distance, a stadium whose
data never reaches the page. They deliberately do NOT assert exact
distances — fences move, and a test that pins 333 feet in left at Camden
would fail for a correct edit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.parks import PARKS, get_park, GENERIC_PARK, evaluate_park
from engine.stadiums import STADIUMS, get_stadium, stadium_to_dict


# --- MLB parks --------------------------------------------------------------
def test_every_mlb_team_has_exactly_one_park():
    assert len(PARKS) == 30
    teams = [p.team for p in PARKS.values()]
    assert len(set(teams)) == 30, "a team appears twice or a park has no team"


def test_every_park_carries_full_reference_detail():
    for key, p in PARKS.items():
        assert p.lf_ft and p.cf_ft and p.rf_ft, f"{key} missing dimensions"
        assert p.capacity, f"{key} missing capacity"
        assert p.opened, f"{key} missing opened year"
        assert p.plays, f"{key} missing its character note"


def test_park_dimensions_are_physically_plausible():
    """Catches transposed digits and unit slips, not exact values."""
    for key, p in PARKS.items():
        assert 295 <= p.lf_ft <= 360, f"{key} left field {p.lf_ft}"
        assert 390 <= p.cf_ft <= 425, f"{key} center field {p.cf_ft}"
        assert 295 <= p.rf_ft <= 360, f"{key} right field {p.rf_ft}"
        # Center is always the deepest point down the middle.
        assert p.cf_ft > p.lf_ft and p.cf_ft > p.rf_ft, f"{key} center not deepest"
        assert 3 <= p.lf_wall_ft <= 40, f"{key} left wall {p.lf_wall_ft}"
        assert 3 <= p.rf_wall_ft <= 40, f"{key} right wall {p.rf_wall_ft}"
        assert 1900 < p.opened <= 2030, f"{key} opened {p.opened}"
        assert 10_000 < p.capacity < 60_000, f"{key} capacity {p.capacity}"


def test_the_landmark_walls_are_recorded():
    """The three parks whose wall is the whole story of the park."""
    assert PARKS["fenway"].lf_wall_ft > 30      # Green Monster
    assert PARKS["oracle"].rf_wall_ft > 20      # right-field wall at Oracle
    assert PARKS["pnc"].rf_wall_ft > 15         # Clemente Wall


def test_wall_heights_are_whole_feet_or_close_to_it():
    """The page rounds wall heights to whole feet, because that is how they
    are quoted. A value that rounds badly (37.2 reading as a surveyed
    figure rather than "37 feet 2 inches") is the thing to catch."""
    for key, p in PARKS.items():
        for side, v in (("left", p.lf_wall_ft), ("right", p.rf_wall_ft)):
            assert abs(v - round(v)) in (0.0, 0.5), \
                f"{key} {side} wall {v} — use whole feet or a clean half"


def test_park_names_keep_their_real_spelling():
    """Rogers Centre is Canadian and spelled that way. An over-eager
    find-and-replace on 'centre' renamed the building once already."""
    assert PARKS["rogers"].name == "Rogers Centre"


def test_no_british_spellings_in_reader_facing_text():
    """These strings go straight onto the page for a US audience."""
    british = ("favour", "colour", "centre field", "metre", "behaviour")
    for key, p in PARKS.items():
        low = p.plays.lower()
        for w in british:
            assert w not in low, f"{key} note contains {w!r}"


def test_coors_is_the_only_high_altitude_park():
    high = {k for k, p in PARKS.items() if p.altitude_ft >= 3000}
    assert high == {"coors"}


def test_reference_detail_does_not_reach_the_model():
    """Dimensions are display-only: the multipliers come from the factors
    alone, so two parks with identical factors must price identically no
    matter how differently they are shaped."""
    a = PARKS["fenway"]      # 310 to left, 37-foot wall
    b = PARKS["kauffman"]    # 330 to left, low wall
    assert (a.lf_ft, a.lf_wall_ft) != (b.lf_ft, b.lf_wall_ft)
    same = type(a)(key="x", name="X", team="XXX",
                   hr_factor=a.hr_factor, run_factor=a.run_factor,
                   k_factor=a.k_factor)          # no dimensions at all
    assert evaluate_park(a).multipliers == evaluate_park(same).multipliers


def test_unknown_park_falls_back_without_raising():
    assert get_park("not-a-park") is GENERIC_PARK


# --- NFL stadiums -----------------------------------------------------------
def test_all_32_teams_have_a_stadium():
    assert len(STADIUMS) == 32
    for team, s in STADIUMS.items():
        assert s.name, f"{team} missing stadium name"
        assert s.plays, f"{team} missing its note"
        assert s.team == team


def test_the_two_shared_venues_are_shared():
    """SoFi and MetLife each host two clubs — the same building, so the
    same facts. A divergence here means one got edited and the other
    didn't."""
    for a, b in (("LA", "LAC"), ("NYG", "NYJ")):
        assert STADIUMS[a].name == STADIUMS[b].name
        assert STADIUMS[a].altitude_ft == STADIUMS[b].altitude_ft
        assert STADIUMS[a].roof == STADIUMS[b].roof


def test_denver_is_flagged_as_altitude():
    assert STADIUMS["DEN"].altitude_ft == 5280
    # The page only surfaces an altitude chip above 2000ft; Denver and Las
    # Vegas are the two that clear it.
    high = {k for k, s in STADIUMS.items() if s.altitude_ft >= 2000}
    assert high == {"DEN", "LV"}


def test_roof_and_surface_use_the_expected_vocabulary():
    for team, s in STADIUMS.items():
        assert s.roof in {"outdoors", "dome", "retractable"}, f"{team} roof {s.roof}"
        assert s.surface in {"grass", "turf"}, f"{team} surface {s.surface}"


def test_stadium_to_dict_is_json_safe_and_complete():
    d = stadium_to_dict("GB")
    assert d["name"] == "Lambeau Field"
    assert set(d) == {"team", "name", "roof", "surface", "altitude_ft",
                      "capacity", "opened", "plays"}
    assert all(isinstance(v, (str, int)) for v in d.values())


def test_unknown_team_returns_an_empty_stadium_not_an_error():
    s = get_stadium("XXX")
    assert s.name == ""
    assert stadium_to_dict("XXX")["name"] == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
