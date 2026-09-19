"""One canonical team per program — the realignment-era name map.

CFB readiness audit, 2026-09-02 (Phase 1): a name collision that merges
two programs is a P0. The book quotes "Miami Hurricanes" and "Miami (OH)
RedHawks"; ESPN's teams feed carries both Miamis. These are the spellings
The Odds API actually uses, resolved through the same `team_lookup` +
`resolve_team` the build joins prices with.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbdata as C


def _teams():
    """ESPN-shaped: displayName / shortDisplayName / abbreviation."""
    rows = [
        ("MIA", "Miami Hurricanes", "Miami", "2390"),
        ("M-OH", "Miami (OH) RedHawks", "Miami (OH)", "193"),
        ("MISS", "Ole Miss Rebels", "Ole Miss", "145"),
        ("MSST", "Mississippi State Bulldogs", "Mississippi State", "344"),
        ("HAW", "Hawai'i Rainbow Warriors", "Hawai'i", "62"),
        ("SJSU", "San José State Spartans", "San José State", "23"),
        ("UTSA", "UTSA Roadrunners", "UTSA", "2636"),
        ("TA&M", "Texas A&M Aggies", "Texas A&M", "245"),
        ("ULL", "Louisiana Ragin' Cajuns", "Louisiana", "309"),
        ("ULM", "UL Monroe Warhawks", "UL Monroe", "2433"),
        ("APP", "App State Mountaineers", "App State", "2026"),
        ("USC", "USC Trojans", "USC", "30"),
        ("SC", "South Carolina Gamecocks", "South Carolina", "2579"),
    ]
    payload = {"sports": [{"leagues": [{"teams": [
        {"team": {"abbreviation": a, "displayName": n, "shortDisplayName": s,
                  "id": i}} for a, n, s, i in rows]}]}]}
    return C.parse_teams(payload)


def test_both_miamis_resolve_to_their_own_program():
    look = C.team_lookup(_teams())
    assert C.resolve_team("Miami Hurricanes", look) == "MIA"
    assert C.resolve_team("Miami (OH) RedHawks", look) == "M-OH"
    assert C.resolve_team("Miami (OH)", look) == "M-OH"
    assert C.resolve_team("Miami FL", look) != "M-OH"
    assert C.resolve_team("Miami OH", look) == "M-OH"


def test_the_odds_api_spellings_all_land_on_one_canonical_team():
    look = C.team_lookup(_teams())
    for quoted, abbr in (
            ("Ole Miss Rebels", "MISS"), ("Mississippi State Bulldogs", "MSST"),
            ("Hawaii Rainbow Warriors", "HAW"), ("San Jose State Spartans", "SJSU"),
            ("UTSA Roadrunners", "UTSA"), ("Texas A&M Aggies", "TA&M"),
            ("Texas A M Aggies", "TA&M"), ("Louisiana Ragin' Cajuns", "ULL"),
            ("UL Monroe Warhawks", "ULM"), ("App State Mountaineers", "APP"),
            ("USC Trojans", "USC"), ("South Carolina Gamecocks", "SC")):
        assert C.resolve_team(quoted, look) == abbr, (quoted, C.resolve_team(quoted, look))


def test_an_unknown_school_is_a_counted_miss_not_a_guess():
    look = C.team_lookup(_teams())
    assert C.resolve_team("Montana State Bobcats", look) == ""
    assert C.resolve_team("", look) == ""


def test_the_2026_schedule_carries_no_two_programs_under_one_key():
    """Every FBS name in the 2026 cfbfastR schedule produces a distinct key
    — the join that would merge two schools is impossible on this
    season's names. Read from the cached copy when present; the network
    copy is the audit's, not the suite's."""
    import csv
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "data", "cache", "cfb_schedules_2025.csv")
    if not os.path.exists(path):
        return
    names = set()
    for r in csv.DictReader(open(path, encoding="utf-8")):
        for side in ("home", "away"):
            if r.get(f"{side}_division") == "fbs":
                names.add(r[f"{side}_team"])
    keys = {}
    for n in names:
        keys.setdefault(C.name_key(n), []).append(n)
    dups = {k: v for k, v in keys.items() if len(v) > 1}
    assert not dups, dups


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
