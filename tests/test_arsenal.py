"""What a pitcher throws, how often, and how much gets missed — §6.

MLB_MODEL §6 parked the arsenal matchup behind "needs pitch-mix +
per-pitch-type hitter data". Half of that was already on disk:
`velocity.py` loads a starter's last five playByPlay payloads to read his
velocity, and those same payloads carry the pitch TYPE and the CALL on
every pitch. The pitcher half is a second read of games the board already
fetched — no new feed, no new request, no credit.

The hitter half genuinely is not here, and `docs/PITCH_LEVEL_SCOPE.md`
now names which of the two costs it is instead of saying "needs data".

Run directly: `python3 tests/test_arsenal.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb import arsenal as ar                          # noqa: E402


def _p(ptype, called, pid=1):
    return {"pitcher_id": pid, "pitch_type": ptype, "called": called}


def test_the_mix_is_the_share_of_what_he_actually_throws():
    rows = [_p("FF", "C")] * 50 + [_p("SL", "B")] * 30 + [_p("CH", "B")] * 20
    m = ar.mix(rows, 1)
    assert m["n"] == 100
    assert m["shares"] == {"FF": 0.5, "SL": 0.3, "CH": 0.2}
    assert list(m["shares"])[0] == "FF", "biggest first"


def test_a_show_me_pitch_does_not_shave_a_point_off_everything_else():
    """One curveball in a start is not part of an arsenal. Shares are over
    the types that CLEARED the floor, so they still sum to 1."""
    rows = [_p("FF", "C")] * 50 + [_p("SL", "B")] * 50 + [_p("CU", "B")]
    m = ar.mix(rows, 1)
    assert "CU" not in m["shares"]
    assert abs(sum(m["shares"].values()) - 1.0) < 1e-9
    # But the raw count is still reported, so "he showed one" is knowable.
    assert m["counts"]["CU"] == 1


def test_whiff_is_per_swing_not_per_pitch():
    """A pitch nobody offers at is a ball. Dividing by every pitch would
    measure how often he is in the zone, not how nasty the pitch is."""
    rows = ([_p("SL", "S")] * 5 + [_p("SL", "F")] * 5
            + [_p("SL", "B")] * 90)          # 90 takes, irrelevant
    w = ar.whiff_by_type(rows, 1)
    assert w["SL"]["swings"] == 10
    assert w["SL"]["whiff_rate"] == 0.5, "5 misses in 10 swings, not in 100"


def test_a_foul_tip_is_contact_not_a_whiff():
    """Counting T as a miss would inflate every splitter in the league."""
    rows = [_p("FS", "T")] * 10
    w = ar.whiff_by_type(rows, 1)
    assert w["FS"]["swings"] == 10 and w["FS"]["whiffs"] == 0
    assert w["FS"]["whiff_rate"] == 0.0


def test_a_rate_off_three_swings_is_not_reported():
    """None means unmeasured; 0.0 means measured and zero."""
    rows = [_p("CU", "S")] * 2 + [_p("CU", "F")]
    w = ar.whiff_by_type(rows, 1)
    assert w["CU"]["swings"] == 3
    assert w["CU"]["whiff_rate"] is None
    assert w["CU"]["whiffs"] == 2       # still counted, just not rated


def test_another_pitchers_work_never_leaks_in():
    rows = [_p("FF", "S", pid=1)] * 20 + [_p("SL", "S", pid=2)] * 20
    assert set(ar.mix(rows, 1)["shares"]) == {"FF"}
    assert set(ar.whiff_by_type(rows, 2)) == {"SL"}


def test_a_shelved_pitch_gets_its_own_flag_not_a_buried_delta():
    """"He shelved the changeup" is a different sentence from "he throws
    it less", and the same tell `velocity.trend_all` reports for speed."""
    prior = {"n": 100, "shares": {"FF": 0.5, "SL": 0.3, "CH": 0.2},
             "whiff": {}}
    latest = {"n": 100, "shares": {"FF": 0.6, "SL": 0.4}, "whiff": {}}
    s = ar.mix_shift([latest, prior, prior, prior])
    assert s["types"]["CH"]["dropped"] is True
    assert s["types"]["FF"]["dropped"] is False
    assert s["types"]["FF"]["delta"] == 0.1


def test_a_new_pitch_is_flagged_rather_than_compared_to_nothing():
    prior = {"n": 100, "shares": {"FF": 1.0}, "whiff": {}}
    latest = {"n": 100, "shares": {"FF": 0.8, "ST": 0.2}, "whiff": {}}
    s = ar.mix_shift([latest, prior, prior])
    assert s["types"]["ST"]["new"] is True
    assert s["types"]["ST"]["delta"] is None, "no baseline to subtract from"


def test_the_biggest_move_comes_first():
    prior = {"n": 100, "shares": {"FF": 0.5, "SL": 0.3, "CH": 0.2},
             "whiff": {}}
    latest = {"n": 100, "shares": {"FF": 0.2, "SL": 0.55, "CH": 0.25},
              "whiff": {}}
    s = ar.mix_shift([latest, prior, prior])
    assert list(s["types"])[0] == "FF"


def test_one_start_cannot_be_a_shift():
    s = ar.mix_shift([{"n": 50, "shares": {"FF": 1.0}, "whiff": {}}])
    assert s["enough"] is False and s["types"] == {}


def test_it_reuses_the_starts_velocity_already_loads():
    """The whole reason this is free. A separate fetch would double every
    pitcher's cost on a fifteen-game board."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "mlb", "arsenal.py"), encoding="utf-8").read()
    assert "from .velocity import recent_start_pks" in src
    assert "fetch_playbyplay" in src


def test_nothing_here_prices_anything():
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "mlb", "arsenal.py"), encoding="utf-8").read()
    import re
    for banned in ("hit_prob", "stake", "multiplier"):
        assert not re.search(rf"\b{banned}\b", src), banned
    assert "THE_INFORMATION_TEST" in src


def test_the_newest_start_is_the_one_being_judged():
    """THE BUG ETHAN'S OUTPUT EXPOSED, 2026-08-10.

    `recent_start_pks` returns most-recent-FIRST — `velocity.trend` says
    so in its docstring and reads `history[0]`. This module's first cut
    took `hist[-1]` as the latest and the entries before it as the
    baseline, which compares the OLDEST start against the four newer
    ones. Backwards, and plausible enough to print: on Gerrit Cole it
    reported "SL 18% → 28%, FF 55% → 45%" — he is leaning on the slider —
    when the truth was the reverse, FF 52% → 57% and SL 21% → 17%.

    Nothing in the numbers looks wrong when this is inverted, which is why
    the first three tests here all passed: their fixtures put the odd
    start at whichever end the code happened to read. A directional
    fixture is the only kind that can catch it."""
    newest = {"n": 100, "shares": {"FF": 0.90, "SL": 0.10}, "whiff": {}}
    older = {"n": 100, "shares": {"FF": 0.10, "SL": 0.90}, "whiff": {}}
    s = ar.mix_shift([newest, older, older, older])
    assert s["types"]["FF"]["latest"] == 0.90, "read the wrong end"
    assert s["types"]["FF"]["baseline"] == 0.10
    assert s["types"]["FF"]["delta"] > 0


def test_it_reads_the_same_end_of_the_list_that_velocity_does():
    """One convention across the two modules that share a loader. If they
    disagree, one of them describes a different start from the other while
    both print the same date."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "mlb", "velocity.py"), encoding="utf-8").read()
    assert "history[0]" in src, "velocity's convention moved; recheck this"
    a = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "mlb", "arsenal.py"), encoding="utf-8").read()
    assert "hist[0], hist[1:1 + baseline_starts]" in a


def test_pooling_rescues_the_pitches_one_start_cannot_rate():
    """ETHAN'S COLE RUN: every one of five starts said "under the floor"
    for the slider, curve and change — three quarters of the arsenal
    invisible in a report about the arsenal. A start gives 6-11 swings on
    a secondary and the floor is 10. Nothing about the floor was wrong; it
    was being applied to the wrong unit."""
    start = {"whiff": {"SL": {"swings": 9, "whiffs": 3, "whiff_rate": None}}}
    assert start["whiff"]["SL"]["whiff_rate"] is None
    p = ar.pooled_whiff([start] * 5)
    assert p["SL"]["swings"] == 45
    assert p["SL"]["whiff_rate"] == round(15 / 45, 4)


def test_pooling_still_refuses_a_rate_it_cannot_support():
    """Pooling is not a licence. Five starts of one swing each is five
    swings, and the floor still applies."""
    start = {"whiff": {"KC": {"swings": 1, "whiffs": 1, "whiff_rate": None}}}
    p = ar.pooled_whiff([start] * 5)
    assert p["KC"]["swings"] == 5 and p["KC"]["whiff_rate"] is None


def test_the_pooled_view_does_not_replace_the_per_start_one():
    """Per-start is the only view that can show a pitch getting WORSE;
    pooled is the view that can show what the pitch IS. Both ship."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "launch.py"), encoding="utf-8").read()
    i = src.index("def show_arsenal(")
    body = src[i:i + 3000]
    assert "pooled_whiff" in body and 'st["whiff"].items()' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
