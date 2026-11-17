"""The report's facts are this season's and right: who is on a reserve list,
whose coverage numbers are whose, which designations are stale, and which
scheme numbers are last season's (2026-11-14).

Ethan, 2026-11-14: "I feel like we're not scouring information week to
week ... we're not pulling the most recent data and information ... it's
not that updated and it's not correct most of the time." What the
Commanders–Giants scan of 12 November held, set against his own reports:

  * Daron Payne, on Washington's injured reserve, named one of its three
    pass rushers, with no status — the weekly injury report never lists a
    man on IR, and the scan read only it;
  * Terry McLaurin, Dyami Brown and Jacory Croskey-Merritt on IR, and the
    report silent about them, where their reports open the personnel section
    on them ("McLaurin, IR — removes the WR1");
  * the Giants' nickel, "Dru Phillips" on the depth chart and "Andru
    Phillips" at PFR, read as never targeted;
  * the coverage table (man and zone, shells, a 30% blitz) last season's,
    said plain beside this season's charting of 40%;
  * and the risk their report named: ESPN's board kept Skattebo and McCarthy
    questionable after the Giants' final report listed only Malik Harrison.

    python3 tests/test_the_report_reads_this_seasons_facts.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamescan as G                     # noqa: E402


def _roster(monkey):
    from engine.sources import nflverse as N
    rows = [{"full_name": "Daron Payne", "team": "WAS", "status": "RES", "status_description_abbr": "R01"},
            {"full_name": "Terry McLaurin", "team": "WAS", "status": "RES", "status_description_abbr": "R01"},
            {"full_name": "Jayden Daniels", "team": "WAS", "status": "ACT", "status_description_abbr": "A01"},
            {"full_name": "Kid Suspended", "team": "WAS", "status": "RES", "status_description_abbr": "R05"}]
    was = N.load_rosters
    N.load_rosters = lambda season: rows
    try:
        return N.reserve_index(2026)
    finally:
        N.load_rosters = was


def test_the_roster_says_who_is_on_a_reserve_list():
    res = _roster(None)
    from engine.sources.oddsapi import normalize_name
    assert res[("WAS", normalize_name("Daron Payne"))] == "on injured reserve"
    assert res[("WAS", normalize_name("Kid Suspended"))] == "suspended"
    assert ("WAS", normalize_name("Jayden Daniels")) not in res, "an active man is on no list"


def test_a_man_on_ir_is_no_pass_rusher_and_is_named_for_what_he_took():
    res = _roster(None)
    defenders = {("WAS", "klavon chaisson"): {"name": "K'Lavon Chaisson", "pressures": 17, "sacks": 3.5},
                 ("WAS", "odafe oweh"): {"name": "Odafe Oweh", "pressures": 12, "sacks": 4.0},
                 ("WAS", "daron payne"): {"name": "Daron Payne", "pressures": 9, "sacks": 1.0},
                 ("WAS", "next man"): {"name": "Next Man", "pressures": 5, "sacks": 0.5}}
    rush = [r["name"] for r in G._pass_rush("WAS", defenders, [], reserve=res)]
    assert rush == ["K'Lavon Chaisson", "Odafe Oweh", "Next Man"], rush
    usage = {("WAS", "terry mclaurin"): {"name": "Terry McLaurin", "position": "WR", "tgt_share": 0.24},
             ("WAS", "jayden daniels"): {"name": "Jayden Daniels", "position": "QB", "tgt_share": 0.0}}
    rows = G.reserve_rows("WAS", res, usage, defenders)
    assert rows[0]["player"] == "Terry McLaurin" and rows[0]["what"] == "24% of the targets"
    assert any(r["player"] == "Daron Payne" and "9 pressures" in r["what"] for r in rows)
    assert G.reserve_rows("WAS", {}, usage, defenders) == [], "no roster read, nothing said"


def test_a_corner_spelled_two_ways_is_one_man():
    defenders = {("NYG", "andru phillips"): {"name": "Andru Phillips", "targets": 31, "rating": 88.0},
                 ("NYG", "deonte banks"): {"name": "Deonte Banks", "targets": 39}}
    assert G._defender_of(defenders, "NYG", "Dru Phillips")["targets"] == 31
    assert G._defender_of(defenders, "NYG", "Deonte Banks")["targets"] == 39
    two = {**defenders, ("NYG", "jalen phillips"): {"name": "Jalen Phillips", "targets": 2}}
    assert G._defender_of(two, "NYG", "Dru Phillips") == {}, "two Phillipses: no guess"


def test_espns_stale_questionable_is_dropped_once_the_club_files():
    from engine.models import Injury
    from engine.sources.injuries import merge_injuries
    weekly = [Injury(player="Malik Harrison", team="NYG", status="QUESTIONABLE", position="LB", role="lb")]
    live = [Injury(player="Cam Skattebo", team="NYG", status="QUESTIONABLE", position="RB", role="rb"),
            Injury(player="Tyrone Tracy", team="NYG", status="IR", position="RB", role="rb"),
            Injury(player="Somebody", team="WAS", status="QUESTIONABLE", position="WR", role="wr")]
    merged, added = merge_injuries(weekly, live)
    who = {i.player: i.status for i in merged}
    assert "Cam Skattebo" not in who, "the Giants filed: ESPN's leftover tag is dropped"
    assert who["Tyrone Tracy"] == "IR", "a reserve move on the live board still lands"
    assert who["Somebody"] == "QUESTIONABLE", "Washington filed nothing: the live board stands"
    assert added == 2


def test_this_seasons_charting_leads_and_last_seasons_shells_say_so():
    from engine import gamereport as GR
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    i = src.index("def sec_identity(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index('f"This season {t} "') < body.index("Last season ({sch_season})"), "this season first"
    assert "this season's coverage numbers come out after the season" in body
    j = src.index("def sec_injuries(")
    assert 'c.scan.get("reserve")' in src[j:j + 2000]
    scan = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert '"reserve": {t: reserve_rows(t, reserve, usage, defenders_now) for t in teams},' in scan
    assert "now = _defender_of(defenders_now, team, name)" in scan
    assert GR is not None


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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
