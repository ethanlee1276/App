"""Live fight state, and the body diagram it draws.

The UFC's broadcast graphic is not a damage model — it is a count of
significant strikes landed to each target area, and keeping that straight
is the whole design. "Damage" is a judgement nobody publishes; strikes to
the head is a number somebody counts.

Three things here would look completely normal while being wrong, so each
has a test: the absorbed/landed inversion, a stale count under a LIVE
badge, and an empty diagram standing in for a fight where nothing has
landed.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc import live


def _fighter(name, stats=None, winner=False):
    e = {"athlete": {"displayName": name}, "winner": winner}
    if stats:
        e["statistics"] = [{"name": k, "displayValue": v}
                           for k, v in stats.items()]
    return e


def _comp(state="in", rnd=2, clock="3:12", a_stats=None, b_stats=None,
          div="Lightweight Bout"):
    return {"id": "1", "type": {"text": div},
            "status": {"period": rnd, "displayClock": clock,
                       "type": {"state": state, "shortDetail": "live"}},
            "competitors": [_fighter("Alpha", a_stats),
                            _fighter("Beta", b_stats)]}


def _payload(*comps):
    return {"events": [{"name": "UFC Test", "date": "2026-08-09T23:00Z",
                        "competitions": list(comps)}]}


LIVE_A = {"sigStrHead": "41 of 88", "sigStrBody": "12 of 19",
          "sigStrLeg": "7 of 8", "sigStrLanded": "60 of 115",
          "knockdowns": "1"}
LIVE_B = {"sigStrHead": "19 of 60", "sigStrBody": "22 of 27",
          "sigStrLeg": "14 of 15", "sigStrLanded": "55 of 102"}


# --- the inversion ----------------------------------------------------------
def test_the_diagram_shows_what_a_fighter_absorbed_not_what_he_landed():
    """Getting this backwards inverts the entire picture while looking
    completely normal — the man doing the damage would be shaded as the
    man taking it."""
    b = live.build(_payload(_comp(a_stats=LIVE_A, b_stats=LIVE_B)))["bouts"][0]
    alpha, beta = b["fighters"]
    assert alpha["landed"] == {"head": 41, "body": 12, "leg": 7}
    assert alpha["absorbed"] == {"head": 19, "body": 22, "leg": 14}
    assert beta["absorbed"] == {"head": 41, "body": 12, "leg": 7}
    assert alpha["absorbed_total"] == 55 and beta["absorbed_total"] == 60


def test_a_bout_without_two_corners_absorbs_nothing_rather_than_guessing():
    comp = _comp(a_stats=LIVE_A)
    comp["competitors"] = comp["competitors"][:1]
    f = live.build(_payload(comp))["bouts"][0]["fighters"][0]
    assert f["absorbed"] == {} and f["absorbed_total"] == 0


# --- reading the feed -------------------------------------------------------
def test_landed_is_taken_from_an_x_of_y_string():
    """Strike stats arrive as "12 of 30". Reading the wrong half would
    shade every diagram by attempts."""
    assert live._num("12 of 30") == 12
    assert live._num("12/30") == 12
    assert live._num("41") == 41
    assert live._num("") is None and live._num(None) is None


def test_control_time_survives_as_seconds():
    assert live._num("4:31") == 271


def test_target_labels_are_matched_however_they_are_spelled():
    for spelling in ("sigStrHead", "Significant Strikes Head",
                     "head strikes landed", "HEAD"):
        assert live._match(spelling, live.TARGET_LABELS) == "head"
    for spelling in ("sigStrLeg", "Leg", "significant strikes leg"):
        assert live._match(spelling, live.TARGET_LABELS) == "leg"
    assert live._match("Takedowns Landed", live.TARGET_LABELS) is None


def test_a_more_specific_label_wins_over_a_shorter_one():
    """"head" must not swallow "headStrikesLanded" and lose the count."""
    got = live.parse_fighter_stats(
        {"statistics": [{"name": "headStrikesLanded", "displayValue": "33"}]})
    assert got["targets"] == {"head": 33}


def test_parallel_label_and_value_arrays_are_read_too():
    got = live.parse_fighter_stats(
        {"labels": ["SigStrHead", "SigStrBody", "TDL"],
         "stats": ["9 of 20", "4 of 6", "2"]})
    assert got["targets"] == {"head": 9, "body": 4}
    assert got["totals"]["takedowns"] == 2


def test_a_stats_payload_that_adds_a_column_does_not_shift_every_number():
    """Indexing a fixed position would move every value one to the left,
    silently, while somebody is watching a fight."""
    base = live.parse_fighter_stats(
        {"labels": ["SigStrHead", "SigStrBody"], "stats": ["9", "4"]})
    grown = live.parse_fighter_stats(
        {"labels": ["NewThing", "SigStrHead", "SigStrBody"],
         "stats": ["99", "9", "4"]})
    assert base["targets"] == grown["targets"] == {"head": 9, "body": 4}


# --- what it refuses to do --------------------------------------------------
def test_a_live_bout_with_no_target_data_says_so_instead_of_drawing_zeros():
    """A diagram of zeros looks like a fight where nothing has landed,
    which is a different claim from "we cannot see the numbers"."""
    blob = live.build(_payload(_comp()))
    bout = blob["bouts"][0]
    assert bout["status"]["live"] is True
    assert bout["has_targets"] is False
    assert "not publishing strikes by target" in blob["note"]


def test_no_live_bout_renders_nothing_rather_than_a_placeholder():
    blob = live.build(_payload(_comp(state="post")))
    assert blob["status"] == "card" and blob["live_count"] == 0
    assert "nothing to show between them" in blob["note"]


def test_an_empty_feed_is_reported_not_treated_as_a_quiet_night():
    blob = live.build({"events": []})
    assert blob["status"] == "no_card" and blob["note"]


def test_the_page_is_told_when_to_stop_calling_the_numbers_live():
    """A minute-old count under a green LIVE badge is a lie with a dot on
    it, so the staleness bar travels with the payload."""
    blob = live.build(_payload(_comp(a_stats=LIVE_A, b_stats=LIVE_B)))
    assert blob["stale_after_s"] == live.STALE_S
    js = _read("web", "js", "app.js")
    assert "stale_after_s" in js and "STALLED" in js
    assert "generated_at" in js, "the age is measured from the fetch, not the data"


def test_it_is_never_presented_as_a_betting_signal():
    """The pre-game model refuses live prices by design. A live page is
    something to watch, not something to bet."""
    blob = live.build(_payload(_comp(a_stats=LIVE_A, b_stats=LIVE_B)))
    assert "not a betting signal" in blob["disclaimer"]
    assert "refuses live prices" in blob["disclaimer"]
    # And nothing in the model may read this file.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("model.py", "grade.py", "markets.py"):
        src = open(os.path.join(root, "engine", "ufc", name),
                   encoding="utf-8").read()
        assert "ufc_live" not in src and "from . import live" not in src, \
            f"{name} reads the live feed — that is in-play betting"


# --- the page ---------------------------------------------------------------
def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_figure_is_scaled_to_the_hottest_region_in_the_fight():
    """Share-of-own-total was the first attempt and it was useless: a
    fighter hit evenly in three places scores ~33% everywhere and comes
    out uniformly mid-red, so 41 to the head looked like 7 to the leg."""
    js = _read("web", "js", "app.js")
    fn = js[js.index("function regionFill("):js.index("function fighterPanelHTML(")]
    assert "peak" in fn, "the figure is not normalised across the fight"
    assert "b.fighters.flatMap" in js, "the peak is not taken across both corners"


def test_an_untouched_region_is_flat_not_green():
    """Colour must never read as good news on a page about being hit."""
    js = _read("web", "js", "app.js")
    fn = js[js.index("function regionFill("):js.index("function bodySVG(")]
    assert "var(--panel-3)" in fn
    assert "--good" not in fn and "34, 197" not in fn


def test_the_live_panel_polls_faster_than_the_page_and_stops_on_exit():
    js = _read("web", "js", "app.js")
    assert "_liveTimer" in js and "setInterval" in js
    fn = js[js.index("async function renderUFC() {"):]
    fn = fn[:2000]
    assert 'state.view !== "ufc"' in fn, "it keeps polling a page nobody is on"


def test_the_launcher_backs_off_when_no_fight_is_on():
    """Polling a free feed every 12 seconds around the clock to watch an
    empty octagon is rude and pointless."""
    src = _read("launch.py")
    assert "LIVE_FAST_S" in src and "LIVE_IDLE_S" in src
    assert src[src.index("LIVE_FAST_S = "):].split("\n")[0].endswith("12")
    fn = src[src.index("def _live_ufc_refresher("):src.index("SWEEP_VIEWS")]
    assert 'status") == "live"' in fn, "it never checks whether a bout is on"
    assert "except Exception" in fn, "a feed error would stop the site"


def test_the_probe_is_dispatched():
    assert '"--probe-live" in argv' in _read("launch.py")


def test_the_build_writes_a_payload_that_says_a_failure_was_a_failure():
    """"No fights" and "we could not look" are opposite facts."""
    src = _read("ufc_live_build.py")
    assert '"status": "unavailable"' in src



# --- following through to where the stats actually are ----------------------
def test_stats_are_looked_for_beyond_the_scoreboard():
    """Proved by a probe run mid-card: the scoreboard carries no
    statistics at all — an already-FINISHED bout had no stats block
    either, so it was never "they appear after the fight". They live on
    the fuller records, and this is the same mistake the weigh-in reader
    made and fixed."""
    srcs = live._stat_sources("600", "9001")
    assert len(srcs) >= 3, "only one place is tried"
    labels = [lbl for lbl, _u, _c in srcs]
    assert any("summary" in l for l in labels)
    assert any("core" in l for l in labels)
    for _lbl, url, cache in srcs:
        assert "600" in url or "9001" in url
        assert cache.endswith(".json")


def test_the_walk_finds_stats_however_they_are_nested():
    """A hard-coded path that is right today is a blank body diagram the
    week ESPN moves it, so this walks rather than indexes."""
    buried = {"boxscore": {"players": [{"statistics": [{"athletes": [
        {"athlete": {"displayName": "Deep Guy"},
         "stats": ["21 of 40", "6 of 9"],
         "labels": ["sigStrHead", "sigStrBody"]}]}]}]}}
    hits = live._walk_for_stats(buried)
    assert len(hits) == 1
    assert live.parse_fighter_stats(hits[0])["targets"] == {"head": 21, "body": 6}


def test_the_walk_ignores_objects_with_no_numbers_in_them():
    assert live._walk_for_stats({"athlete": {"displayName": "Nobody"}}) == []
    assert live._walk_for_stats({"a": {"b": {"c": "text"}}}) == []


def test_fetched_stats_are_matched_by_name_not_by_order():
    """The two payloads do not agree on ordering, and putting a fighter's
    numbers on his opponent is the one error here that looks completely
    normal."""
    bout = live.build(_payload(_comp()))["bouts"][0]
    assert bout["has_targets"] is False
    # Deliberately REVERSED relative to the scoreboard's order.
    entries = [
        {"athlete": {"displayName": "Beta"},
         "labels": ["sigStrHead"], "stats": ["5"]},
        {"athlete": {"displayName": "Alpha"},
         "labels": ["sigStrHead"], "stats": ["30"]},
    ]
    assert live._merge_stats(bout, entries) is True
    alpha, beta = bout["fighters"]
    assert alpha["landed"] == {"head": 30}
    assert alpha["absorbed"] == {"head": 5}, "the stats landed on the wrong man"
    assert beta["absorbed"] == {"head": 30}
    assert bout["has_targets"] is True


def test_a_merge_that_matches_nobody_changes_nothing():
    bout = live.build(_payload(_comp()))["bouts"][0]
    assert live._merge_stats(bout, [
        {"athlete": {"displayName": "Somebody Else"},
         "labels": ["sigStrHead"], "stats": ["9"]}]) is False
    assert bout["has_targets"] is False


def test_only_live_bouts_are_followed():
    """A 14-fight card would otherwise be 14 extra requests every twelve
    seconds to re-read numbers that stopped changing hours ago."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "ufc", "live.py"),
               encoding="utf-8").read()
    fn = src[src.index("def refresh("):src.index("def probe(")]
    assert 'if not bout["status"]["live"] or bout["has_targets"]' in fn


def test_the_probe_names_which_source_answered():
    """The point of running it again is finding out WHERE the numbers are,
    so "it worked" is not an answer — which endpoint has to be."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "engine", "ufc", "live.py"),
               encoding="utf-8").read()
    fn = src[src.index("def probe("):]
    assert "_stat_sources(" in fn, "the probe never tries the deeper records"
    assert "reachable, no stats in it" in fn, "a reachable-but-empty source "\
        "must be distinguished from an unreachable one"
    # Matched on a fragment that is contiguous in the SOURCE — the
    # sentence is split across lines by the line length.
    assert "publish live strike-by-target" in fn

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
