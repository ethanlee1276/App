"""CFBD's school names find every school on the board.

24 November 2026, the college board's new scan census (step ADS): "2026: 108 of 138 schools read". CFBD names a
school the way ESPN's `location` does ("Eastern Michigan"); the board's school map kept ESPN's full name ("Eastern
Michigan Eagles") and its short one ("E Michigan"), and the name matcher only peels words off the name it is given, so
30 schools CFBD rated joined to nothing. Tonight's two games (Kent State at Eastern Michigan, Miami (OH) at Western
Michigan) went unscanned for want of their home sides, and the talent, blue-chip and returning-production priors
(cfb_build `_abbr`) skipped the same schools. The map now keeps the school's own name where neither other name says
it, and the matcher reads it last, never over a name another school answers to, and never where two schools share it.

Offline. Run directly: `python3 tests/test_cfbds_school_names_find_every_school.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import cfbdata as C                            # noqa: E402


def _team(tid, abbr, location, display, short, color="006938"):
    return {"team": {"id": tid, "abbreviation": abbr, "location": location, "displayName": display,
                     "shortDisplayName": short, "color": color, "alternateColor": "ffffff", "logos": [{"href": "x"}]}}


PAYLOAD = {"sports": [{"leagues": [{"teams": [
    _team("2199", "EMU", "Eastern Michigan", "Eastern Michigan Eagles", "E Michigan"),
    _team("2711", "WMU", "Western Michigan", "Western Michigan Broncos", "W Michigan"),
    _team("2309", "KENT", "Kent State", "Kent State Golden Flashes", "Kent State"),
    _team("193", "M-OH", "Miami (OH)", "Miami (OH) RedHawks", "Miami OH"),
    _team("2390", "MIA", "Miami", "Miami Hurricanes", "Miami"),
    # Two schools below Division I that share a place name.
    _team("9001", "WES", "Wesleyan", "Wesleyan Cardinals", "Wesleyan CT"),
    _team("9002", "WESG", "Wesleyan", "Wesleyan Wolves", "Wesleyan GA"),
]}]}]}


def test_the_map_keeps_the_schools_own_name_only_where_it_is_new():
    teams = C.parse_teams(PAYLOAD)
    assert teams["EMU"]["school"] == "Eastern Michigan" and teams["WMU"]["school"] == "Western Michigan"
    assert "school" not in teams["KENT"], "Kent State is already its short name"
    assert "school" not in teams["MIA"] and "school" not in teams["M-OH"], "Miami (OH) is its short name, loosely"


def test_cfbds_names_join_and_nothing_else_moves():
    lookup = C.team_lookup(C.parse_teams(PAYLOAD))
    got = {n: C.resolve_team(n, lookup) for n in
           ("Eastern Michigan", "Western Michigan", "Kent State", "Miami (OH)", "Miami", "Wesleyan",
            "Eastern Michigan Eagles", "Miami (OH) RedHawks", "Miami Hurricanes")}
    assert got == {"Eastern Michigan": "EMU", "Western Michigan": "WMU", "Kent State": "KENT", "Miami (OH)": "M-OH",
                   "Miami": "MIA", "Wesleyan": "", "Eastern Michigan Eagles": "EMU",
                   "Miami (OH) RedHawks": "M-OH", "Miami Hurricanes": "MIA"}, got
    # Before: the map without the school's name, as the board shipped it until step ADV.
    old = C.team_lookup({k: {kk: vv for kk, vv in v.items() if kk != "school"}
                         for k, v in C.parse_teams(PAYLOAD).items()})
    assert C.resolve_team("Eastern Michigan", old) == "" and C.resolve_team("Western Michigan", old) == ""


def test_the_scan_reaches_both_sides():
    from engine import gamescan as S
    lookup = C.team_lookup(C.parse_teams(PAYLOAD))
    seen = []

    def fetch(year):
        return {"Eastern Michigan": {}, "Kent State": {}, "Western Michigan": {}, "Miami (OH)": {}}
    out = {"games": [{"home": "EMU", "away": "KENT"}, {"home": "WMU", "away": "M-OH"}]}
    try:
        S.attach_cfb(out, 2026, lambda s: seen.append(s) or C.resolve_team(s, lookup), fetch=fetch)
    except Exception:                                                  # noqa: BLE001
        pass                     # empty tables rate nobody; the census is written before the ratings
    assert out["scan_census"]["cfbd"]["2026"] == "4 of 4 schools read", out["scan_census"]


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
