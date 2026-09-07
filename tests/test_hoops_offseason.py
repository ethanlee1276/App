""""Offseason" from a single empty day, in a season running into September.

`--boards` on 2026-08-31 — a Sunday in the middle of a WNBA season that
runs into September — showed:

    WNBA  0.1h  0 games  0 recs  offseason

`nba_build` asserted that word whenever today had no games:

    if not games and "status" not in out:
        out.update(status="offseason", ...)

No lookback, no evidence, nothing. A quiet Monday, a bye, an All-Star
break and a finished season all produce zero games, and only the last is
what the word means.

THE SAME CLAIM `cfb_build` MADE, corrected the same day — and this one
was worse. That build at least looked back ten days before asserting it;
this one did not look at all.

The tri-state is the same and for the same reason: "we looked and the
league is dormant" and "we could not look" are different facts, and
publishing OFFSEASON off a fetch we failed to make asserts something
about the league on the strength of our own failure.

Run directly: `python3 tests/test_hoops_offseason.py`
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import nba_build


def _src(name="nba_build.py"):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _args(date="2026-08-31"):
    return types.SimpleNamespace(date=date, league="wnba")


def _lookback(per_day=None, fail_all=False):
    """Run `_recent_slate` against a stand-in schedule feed."""
    # Patched on the SOURCE MODULE, because `_recent_slate` imports the
    # pair per league inside itself — the names do not exist on
    # `nba_build` at all, which is what the first cut of the helper got
    # wrong.
    per_day = per_day or {}
    from engine.sources import wnbaespn as W
    real_fetch, real_parse = W.fetch_schedule, W.parse_schedule_day

    def fake_parse(_sched, date):
        if fail_all:
            raise RuntimeError("feed down")
        return per_day.get(date, [])

    W.fetch_schedule = lambda *a, **k: {}
    W.parse_schedule_day = fake_parse
    try:
        return nba_build._recent_slate(_args(),
                                       types.SimpleNamespace(name="WNBA"))
    finally:
        W.fetch_schedule, W.parse_schedule_day = real_fetch, real_parse


# --- the three answers ----------------------------------------------------
def test_a_running_season_is_found_from_the_days_before():
    found, looked = _lookback({"2026-08-30": [{"home": "SEA"}, {"home": "LA"}]})
    assert looked is True and found == 2


def test_a_genuinely_dormant_league_reports_nothing_found():
    found, looked = _lookback({})
    assert looked is True and found == 0


def test_a_lookback_that_could_not_run_says_so():
    """THE ONE THAT MUST NOT BECOME "OFFSEASON"."""
    found, looked = _lookback(fail_all=True)
    assert looked is False and found == 0


def test_found_nothing_and_could_not_look_are_distinguishable():
    assert _lookback({})[1] is not _lookback(fail_all=True)[1]


def test_a_malformed_date_cannot_look():
    assert nba_build._recent_slate(
        _args("not-a-date"), types.SimpleNamespace(name="WNBA")) == (0, False)


def test_the_helper_imports_the_feed_it_needs():
    """It calls names that live in the league source modules, not on
    `nba_build`. The first cut called them as though they were
    module-level here and would have raised NameError on every empty
    date — the same scoping mistake fixed one file over the same day."""
    import inspect
    src = inspect.getsource(nba_build._recent_slate)
    assert "from engine.sources.wnbaespn import" in src
    assert "from engine.sources.nbadata import" in src


def test_the_window_spans_a_break_rather_than_a_single_day():
    """One day of lookback would call the Tuesday after a quiet Monday
    the offseason. An All-Star break is the longest real gap."""
    assert nba_build.LOOKBACK_DAYS >= 7


def test_it_looks_backward_only():
    import inspect
    src = inspect.getsource(nba_build._recent_slate)
    assert "day - _d.timedelta(days=n)" in src
    assert "day + _d" not in src


# --- and the build uses all three -----------------------------------------
def test_the_build_no_longer_asserts_offseason_from_one_empty_day():
    src = _src()
    assert "recent, looked = _recent_slate(args, tune)" in src


def test_a_quiet_date_inside_a_season_says_so():
    src = _src()
    assert 'status="no games today"' in src
    assert "A quiet date, not" in src


def test_an_unfetchable_lookback_gets_its_own_status():
    src = _src()
    assert 'status="schedule unknown"' in src
    assert "not a claim that" in src


def test_offseason_survives_only_when_the_lookback_earned_it():
    src = _src()
    at = src.index('status="offseason"')
    assert "none in" in src[at:at + 300]


def test_the_three_branches_are_ordered_unknown_first():
    """An unknown must not fall through into either claim about the
    league."""
    src = _src()
    assert src.index("if not looked:") < src.index("elif recent:")
    assert src.index("elif recent:") < src.index('status="offseason"')


# --- the page already has words for the unknown ---------------------------
def test_the_page_can_render_the_unknown_status():
    """Added for CFB the same day; the hoops board emits the same word,
    so the branch is shared rather than duplicated."""
    with open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8") as f:
        assert 'state.data.status === "schedule unknown"' in f.read()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
