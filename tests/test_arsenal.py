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


# --- §6's matchup: the hitter half, confirmed live 2026-08-10 ----------------
_B = {"FF": {"pa": 300, "whiff_pct": 0.18, "est_woba": 0.380, "usage": 0.55},
      "SL": {"pa": 120, "whiff_pct": 0.40, "est_woba": 0.250, "usage": 0.30},
      "CH": {"pa": 60, "whiff_pct": 0.28, "est_woba": 0.300, "usage": 0.15}}


def test_the_same_hitter_reads_differently_against_two_arsenals():
    """THE WHOLE POINT IS THE DIFFERENCE, NOT THE LEVEL. A hitter who
    whiffs at 40% against sliders is not a problem until he faces someone
    who throws 45% sliders; against a fastball-first starter that weakness
    never comes up. The league knows he whiffs at sliders — the price
    contains it. What the price may not contain is tonight's mix."""
    hot = ar.matchup({"SL": 0.45, "FF": 0.40, "CH": 0.15}, _B)
    cold = ar.matchup({"FF": 0.70, "SL": 0.15, "CH": 0.15}, _B)
    assert hot["whiff_delta"] > 0 and cold["whiff_delta"] < 0
    assert hot["whiff_baseline"] == cold["whiff_baseline"], (
        "the baseline is the hitter's own, and must not move with the "
        "opponent")
    assert hot["xwoba_delta"] < 0 < cold["xwoba_delta"]


def test_a_pitch_he_has_barely_faced_is_dropped_not_trusted():
    """Savant publishes rows down to a handful of PA, and a .600 wOBA on
    nine of them is a rounding artefact."""
    thin = dict(_B, FS={"pa": 6, "whiff_pct": 0.55, "est_woba": 0.150,
                        "usage": 0.02})
    m = ar.matchup({"FS": 0.30, "FF": 0.70}, thin)
    assert "FS" not in m["types"]
    assert m["coverage"] == 0.70


def test_coverage_is_reported_and_gates_the_verdict():
    """A re-weighting over 60% of the arsenal is a different claim from
    one over 95%. If the pitcher throws a splitter this hitter has never
    seen, that share is unmeasured and the report says so."""
    m = ar.matchup({"FF": 0.40, "XX": 0.60}, _B)
    assert m["coverage"] == 0.40
    assert m["enough"] is False
    assert ar.matchup({"FF": 0.70, "SL": 0.30}, _B)["enough"] is True


def test_a_hitter_we_hold_nothing_for_returns_none_not_zero():
    """None is "not measured"; 0.0 would read as "no edge either way"."""
    m = ar.matchup({"FF": 1.0}, {})
    assert m["whiff_vs_mix"] is None and m["whiff_delta"] is None
    assert m["enough"] is False


def test_the_savant_board_keeps_every_pitch_type_per_player():
    """This is the only Savant board here with SEVERAL rows per person.
    Parsing it like the others would keep whichever pitch type came last.
    Header verified live 2026-08-10."""
    from engine.mlb.sources.savant import parse_arsenal, _read_csv_text
    text = ('\ufeff"last_name, first_name","player_id","team_name_alt",'
            '"pitch_type","pitch_name","run_value_per_100","run_value",'
            '"pitches","pitch_usage","pa","ba","slg","woba","whiff_percent",'
            '"k_percent","put_away","est_ba","est_slg","est_woba",'
            '"hard_hit_percent"\n'
            '"Judge, Aaron","592450","NYY","FF","4-Seamer","2.1","14","900",'
            '"48.5","250","0.310","0.700","0.460","22.5","24.0","18.0",'
            '"0.300","0.680","0.450","55.0"\n'
            '"Judge, Aaron","592450","NYY","SL","Slider","-1.4","-9","400",'
            '"21.0","110","0.210","0.400","0.300","38.2","31.0","24.0",'
            '"0.220","0.410","0.310","41.0"\n')
    d = parse_arsenal(_read_csv_text(text))
    assert set(d["aaron judge"]) == {"FF", "SL"}, "one type overwrote another"
    assert d["aaron judge"]["SL"]["whiff_pct"] == 0.382
    assert d["aaron judge"]["FF"]["usage"] == 0.485


def test_a_poisoned_cache_is_not_served_as_an_empty_season():
    """ETHAN, 2026-08-10: "No arsenal line for 'Aaron Judge' in 2026. The
    board holds 0 hitters."

    `fetch_text` writes whatever the server returns and serves it back for
    the whole TTL — an empty body, a maintenance page, an HTML redirect.
    One bad response poisons six hours and the only symptom is a board
    with nothing in it, which is indistinguishable from a season Savant
    has not populated. The header check is what separates them."""
    from engine.mlb.sources.savant import _looks_like_arsenal as ok
    assert ok('"last_name, first_name","pitch_type","whiff_percent"')
    assert not ok("<!DOCTYPE html><html><head><title>Error</title>")
    assert not ok("")
    # A CSV that is real but a DIFFERENT board must also be refused.
    assert not ok('"last_name, first_name","player_id","barrel_batted_rate"')


def test_an_empty_season_falls_back_and_says_which_year_it_used():
    """A hitter's profile from last season is real information; an empty
    dict is not. But the caller must be told, or a stale reading gets
    passed off as current."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "mlb", "sources", "savant.py"), encoding="utf-8").read()
    i = src.index("def load_arsenal(")
    body = src[i:i + 2200]
    assert 'board["_season"] = year' in body, "the year used must come back"
    assert "load_arsenal(year - 1" in body
    assert "fallback=False" in body, "the fallback must not recurse forever"


def test_the_probe_distinguishes_three_different_failures():
    """"0 hitters" was three problems in one sentence: the season is not
    published, the fetch returned something that was not the CSV, or this
    hitter is missing from a board that is otherwise full."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "launch.py"), encoding="utf-8").read()
    i = src.index("def show_matchup(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "came back EMPTY" in body
    assert "Closest names we hold" in body
    assert "last season's hitter, not" in body


def test_the_pitcher_and_the_hitter_are_read_on_different_clocks():
    """ETHAN, 2026-08-10: `--matchup 543037 "Aaron Judge" 2025` →
    "No starts parsed for 543037 in 2025."

    He asked for the 2025 SAVANT BOARD, which is the year his curl proved
    has data. The season argument dragged the PITCHER lookup back to 2025
    with it, where Cole has no cached starts, and the report answered a
    question nobody asked.

    A pitcher's arsenal is inherently a NOW question — what is he throwing
    lately. The batter board is a season aggregate. One parameter cannot
    mean both."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "launch.py"), encoding="utf-8").read()
    i = src.index("def show_matchup(")
    # To the END of the function, not a guessed character count. A fixed
    # window silently stops asserting the moment the function grows past
    # it — this test failed on its first run for exactly that reason, and
    # a guard that quietly narrows is worse than no guard.
    body = src[i:src.index("\ndef ", i + 10)]
    # The board takes the argument; the pitcher takes the current year.
    assert "load_arsenal(season," in body
    assert "for yr in (now, now - 1):" in body
    assert "_ar.history(int(person_id), yr)" in body
    # And the header must say which year each half came from, or a
    # cross-season reading looks like a same-season one.
    assert "hitter board {used}" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
