"""`python3 -m engine.lab` printed nothing, twice, and that was the point.

The Lab existed only as a nightly side effect: `run_if_due` builds the
JSON and writes it through the paywall gate. `engine/lab.py` had no
`__main__`, so running the module directly did exactly nothing — no
output, no error, exit 0. Ethan ran it twice after a four-thousand-credit
harvest and saw a blank line both times.

The other half of the same problem was the season. `nfl_season_of` is
right about what it answers — on 2026-08-27 the 2026 season IS the
current one — and wrong as a backtest default, because that season has
not been played. A Lab run in August was guaranteed to replay an empty
season and report "unavailable" while a database full of 2025 closing
prices went unread.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import lab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- which season gets replayed ---------------------------------------------
def test_an_explicit_season_is_honoured_exactly():
    """A caller naming 2023 means 2023 and must not silently get 2022."""
    assert lab._seasons_to_try(2023) == [2023]
    assert lab._seasons_to_try(2025) == [2025]


def test_the_default_falls_back_one_season_and_no_further():
    """An offseason run wants last season. So does a run in week 2 — six
    weeks of priors do not exist yet. Both are "the current season
    produced nothing", so both are the same fallback. Two is enough:
    reaching further back would quietly replay a season nobody asked
    about."""
    got = lab._seasons_to_try(None)
    assert len(got) == 2
    assert got[1] == got[0] - 1


def test_the_two_callers_share_one_fallback():
    """The `--bets` path reimplemented the season loop and left out the
    `DataUnavailable` arm, so it crashed on an unplayed 2026 instead of
    falling back to 2025 — the exact failure the fallback exists to
    prevent, in a copy of the fallback. One implementation now."""
    import inspect
    assert "nfl_replay(" in inspect.getsource(lab.nfl_props)
    assert "nfl_replay(" in inspect.getsource(lab.main)
    body = inspect.getsource(lab.main)
    assert "backtest_from_stats(" not in body, \
        "main is replaying on its own again"


def test_the_shared_fallback_survives_an_unplayed_season():
    """The crash, reproduced: the newest season 404s and the replay has to
    keep going rather than raise."""
    from engine.sources.fetch import DataUnavailable
    from engine import backtest as B
    saved = B.backtest_from_stats
    calls = []

    def fake(season, weeks, **kw):
        calls.append(season)
        if season == max(lab._seasons_to_try(None)):
            raise DataUnavailable(f"nflverse has nothing for {season}")
        class _R:
            n = 5
            longshots = None
        return _R()
    try:
        B.backtest_from_stats = fake
        rep, season, tried = lab.nfl_replay(None, [6, 7], {}, log=lambda *a: None)
    finally:
        B.backtest_from_stats = saved
    assert rep is not None, "the unplayed season took the whole run down"
    assert season == max(lab._seasons_to_try(None)) - 1
    assert any("nflverse has nothing" in t for t in tried)


def test_the_fallback_is_driven_by_an_empty_result_not_by_the_calendar():
    """A season with a stats file but no settled props in the window has
    to fall through too — a 404 is not the only way to have nothing."""
    import inspect
    src = inspect.getsource(lab.nfl_replay)
    assert "for candidate in _seasons_to_try(season)" in src
    assert "if rep.n:" in src, \
        "an empty replay must fall through, not be reported as the answer"
    assert "if rep is None:" in inspect.getsource(lab.nfl_props)


def test_every_season_tried_is_named_when_none_of_them_worked():
    """"unavailable" with no reason is how a data gap gets mistaken for a
    model that found nothing."""
    import inspect
    assert 'tried.append' in inspect.getsource(lab.nfl_replay)
    assert '"; ".join(tried)' in inspect.getsource(lab.nfl_props)
    assert '"; ".join(tried)' in inspect.getsource(lab.main), \
        "the --bets path must name the seasons it could not reach too"


# --- the printer -------------------------------------------------------------
def _market(**over):
    m = {"market": "receptions", "label": "Receptions", "n": 300,
         "basis": "mixed", "used_real_lines": 120, "total_priced": 300,
         "n_bets": 100, "win_rate": 0.55, "roi": 0.03, "segments": {}}
    m.update(over)
    return m


def _capture(m):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab._print_market(m)
    return buf.getvalue()


def test_the_basis_leads_because_it_decides_what_the_numbers_mean():
    """"book" is a claim about beating a market; "naive" is a claim about
    the projection and nothing else. A win rate printed without it is a
    number whose meaning the reader has to guess."""
    out = _capture(_market())
    assert "basis mixed" in out
    assert "120/300 priced on real closes" in out


def test_both_segments_are_printed_apart():
    out = _capture(_market(segments={
        "book": {"n_bets": 40, "win_rate": 0.6, "roi": 0.08, "grades": {}},
        "naive": {"n_bets": 60, "win_rate": 0.51, "roi": -0.01,
                  "grades": {}}}))
    assert "vs the book" in out and "60.0%" in out
    assert "vs a proxy" in out and "51.0%" in out


def test_the_grade_ladder_prints_inside_its_basis():
    """The question the harvest was bought to answer lives here and
    nowhere else: does the top band earn its billing against a real
    book."""
    out = _capture(_market(segments={"book": {
        "n_bets": 100, "win_rate": 0.55, "roi": 0.02,
        "grades": {"A": {"n_bets": 30, "win_rate": 0.40, "roi": -0.12},
                   "B+": {"n_bets": 70, "win_rate": 0.61, "roi": 0.09}}}}))
    assert "A " in out and "40.0%" in out
    assert "B+" in out and "61.0%" in out


def test_an_empty_band_is_not_printed_as_a_zero():
    out = _capture(_market(segments={"book": {
        "n_bets": 10, "win_rate": 0.5, "roi": 0.0,
        "grades": {"A+": {"n_bets": 0, "win_rate": None, "roi": None}}}}))
    assert "A+" not in out


def test_a_missing_number_prints_as_a_dash_rather_than_zero_percent():
    assert lab._pct(None) == "—"
    assert lab._pct(0.0) == "0.0%"


def test_a_market_with_no_bets_still_reports_what_it_settled():
    out = _capture(_market(n_bets=0, segments={}))
    assert "300 settled" in out


# --- the command line --------------------------------------------------------
def test_the_module_is_runnable_at_all():
    """The whole point. It had no __main__ and printed nothing, twice."""
    with open(os.path.join(ROOT, "engine", "lab.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert 'if __name__ == "__main__":' in src
    assert "_sys.exit(main())" in src


def test_the_help_names_the_flags_that_matter():
    out = subprocess.run([sys.executable, "-m", "engine.lab", "--help"],
                         capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    for flag in ("--sport", "--season", "--json"):
        assert flag in out.stdout, flag


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
