"""Camp information, measured rather than read about.

§7 calls camp intelligence MMA's signature edge, and the standing answer
here was that no structured feed of camp footage exists — true, but it led
somewhere wrong: that therefore nothing about a fighter's camp is
knowable. Three things are, and the dossier already fetches all of them:
how long since he fought, how often he fights, and where he trains.
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc import camp
from engine.ufc import grade as G

TODAY = "2026-08-01"


def _fighter(name="X", days_out=180, first="2020-01-01", fights=8):
    last = (datetime.date.fromisoformat(TODAY)
            - datetime.timedelta(days=days_out)).isoformat()
    return {"name": name, "last_fight": last, "first_fight": first,
            "fights": fights}


def test_a_normal_camp_cycle_scores_best():
    mid = camp.profile(_fighter(days_out=180), {}, today=TODAY)
    quick = camp.profile(_fighter(days_out=20), {}, today=TODAY)
    rusty = camp.profile(_fighter(days_out=900), {}, today=TODAY)
    assert mid["score"] > quick["score"], "a 20-day turnaround is not a camp"
    assert mid["score"] > rusty["score"]


def test_the_layoff_score_never_improves_as_the_layoff_grows():
    """The bug this pins: averaging layoff with activity was
    non-monotonic, so a fighter three years out who USED to be busy
    outscored one 26 months out who never was. A severe layoff is not
    something an old activity rate rescues.
    """
    prev = None
    for days in (400, 500, 700, 800, 1000, 1200, 1500):
        s = camp.profile(_fighter(days_out=days), {}, today=TODAY)["score"]
        if prev is not None:
            assert s <= prev + 1e-9, (
                f"{days} days out scored better than {prev}")
        prev = s


def test_no_dated_history_means_no_claim():
    p = camp.profile({"name": "Debut"}, {}, today=TODAY)
    assert p["score"] is None
    assert p["layoff_days"] is None


def test_a_gym_change_is_found_by_diffing_our_own_drafts():
    """No news feed, nothing to curate — the same trick that finds NFL
    trades. It needs two drafts to see one, which is why the gym is
    written down on every draft rather than when we want it."""
    tmp = os.path.join(tempfile.mkdtemp(), "gyms.json")
    assert camp.record_gym("A Fighter", "American Top Team",
                           "2026-01-01", tmp)["changed"] is False
    # The same gym seen again is not a move.
    assert camp.record_gym("A Fighter", "American Top Team",
                           "2026-05-01", tmp)["changed"] is False
    moved = camp.record_gym("A Fighter", "City Kickboxing", "2026-07-20", tmp)
    assert moved["changed"] and moved["changed_from"] == "American Top Team"
    st = camp.gym_state("A Fighter", camp.load_gyms(tmp), today=TODAY)
    assert st["gym"] == "City Kickboxing" and st["changed"] is True
    # An old move is history, not news.
    stale = camp.gym_state("A Fighter", camp.load_gyms(tmp), today="2028-01-01")
    assert stale["changed"] is False


def test_an_unknown_gym_costs_nothing():
    """Most payloads name no gym. That must not read as a bad camp."""
    known = camp.profile(_fighter(), {}, today=TODAY)
    assert known["gym"] == "" and known["gym_changed"] is False
    assert known["score"] is not None


# --- how it reaches the grade ----------------------------------------------
def _d(name, **kw):
    d = {"name": name, "division": "heavyweight", "ufc_fights": 12,
         "archetype": "pressure", "red_flags": []}
    d.update(_fighter(name))
    d.update(kw)
    return d


def test_camp_is_scored_off_the_worse_corner():
    """A fight is priced on the pair. A perfect camp opposite a man three
    years out is not an average camp."""
    fresh = _d("Fresh")
    rusty = _d("Rusty")
    rusty.update(_fighter("Rusty", days_out=1200, fights=2))
    both = G.camp_info(None, fresh, _d("Fresh2"), today=TODAY)
    mixed = G.camp_info(None, fresh, rusty, today=TODAY)
    assert mixed["score"] < both["score"]
    assert any("layoff" in w for w in mixed["why"])


def test_the_component_no_longer_waits_on_friday():
    """The whole point: camp is scored with no weigh-in recorded at all."""
    ci = G.camp_info(None, _d("A"), _d("B"), today=TODAY)
    assert ci["score"] is not None, "camp still depends on the scale"
    assert any("weigh-in not recorded" in w for w in ci["why"]), \
        "the missing weigh-in must still be stated, just not fatal"


def test_the_weigh_in_still_adds_when_it_lands():
    made = {"state": "made"}
    before = G.camp_info(None, _d("A"), _d("B"), today=TODAY)["score"]
    after = G.camp_info({"a": made, "b": made}, _d("A"), _d("B"),
                        today=TODAY)["score"]
    assert after > before


def test_the_missing_layer_is_still_named():
    """Camp FOOTAGE has no source and this must not quietly imply it does."""
    ci = G.camp_info(None, _d("A"), _d("B"), today=TODAY)
    assert any("camp-footage" in w for w in ci["why"])


def test_the_dossier_stores_what_the_camp_layer_needs():
    """A drafted dossier without these dates makes camp unmeasurable, and
    the failure would be silent — every fighter scoring None forever."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "sources", "espnmma.py"),
               encoding="utf-8").read()
    for field in ('"last_fight"', '"first_fight"', '"gym"'):
        assert field in src, f"the dossier no longer records {field}"
    drafter = open(os.path.join(root, "ufc_dossiers.py"), encoding="utf-8").read()
    assert "record_gym" in drafter, "gyms are never written down, so a camp "\
        "change can never be detected"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
