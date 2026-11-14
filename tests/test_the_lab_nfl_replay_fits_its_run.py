"""The Lab's NFL replay fits inside its run (engine/backtest.backtest_from_stats,
engine/lab.nfl_props).

The live heartbeat, 2026-11-05: the Lab's weekly run "cut_off": true after
99 minutes, its last line "lab: replaying nfl (1 of 6)…", so the page
published nothing, as it has not since 29 September. The NFL's walk
rebuilds a full slate for each of twelve weeks on one niced vCPU. What
these hold:

  * a week the feed has no rows for (not played yet) settles nothing, so
    its slate is never built;
  * with a deadline the walk takes the newest weeks first and stops before
    the next week once the deadline has passed, or once what is left would
    not cover a week at the pace of the last one (2026-11-07) — the first
    week always starts; the report names the weeks it covered and that it
    stopped;
  * each week is built from the weeks before it alone, so the order changes
    no week's answer;
  * without a deadline nothing changes for the other callers (propcal, the
    form checks): the same weeks, oldest first;
  * the Lab's NFL section passes its budget, says which weeks it replayed,
    and the per-week lines reach the log (the line the heartbeat keeps);
  * the closes are read once, inside that budget (2026-11-07: the five
    markets' scans of the history file ran before its clock started), and
    the usage ripple reuses them instead of scanning three of the five
    again; when they cannot be read the ripple reads its own, as before.

Run directly: `python3 tests/test_the_lab_nfl_replay_fits_its_run.py`
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine.pipeline as pl                                    # noqa: E402
import engine.sources.nflverse as nv                            # noqa: E402
from engine import backtest as B                                 # noqa: E402
from engine import lab                                           # noqa: E402


def _stats(weeks):
    return [{"week": str(w), "player_display_name": f"RB {w}", "rushing_yards": "80",
             "passing_yards": "0", "receiving_yards": "0", "receptions": "0"} for w in weeks]


class _Feed:
    """The NFL feed and pipeline, offline: records each slate built and
    costs ``cost`` seconds of a fake clock per slate."""
    def __init__(self, played, cost=0.0, clock=None):
        self.played, self.cost, self.clock, self.built = played, cost, clock, []

    def __enter__(self):
        self.saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
        nv.load_weekly_stats = lambda season: _stats(self.played)

        def build(season, w, upto_week=None, carry=False):
            self.built.append(int(w))
            if self.clock is not None:
                self.clock.t += self.cost
            return {"week": int(w)}
        nv.build_slate = build
        pl.run_slate = lambda slate, config=None, **kw: {"recommendations": [{
            "player": f"RB {slate['week']}", "market": "rush_yds", "line": 70.0, "odds": -110,
            "hit_prob": 0.6, "projection": 82.0, "recommended": True, "stake_units": 1.0}],
            "long_shots": []}
        return self

    def __exit__(self, *exc):
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = self.saved


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _patched_monotonic(clock):
    import time as _t
    real = _t.monotonic
    _t.monotonic = clock
    return real


def test_a_week_not_played_yet_is_never_built():
    with _Feed(played=[6, 7, 8, 9]) as f:
        rep = B.backtest_from_stats(2026, list(range(6, 18)))
    assert f.built == [6, 7, 8, 9], f.built
    assert rep.weeks_covered == [6, 7, 8, 9] and not rep.stopped_early and rep.n == 4


def test_without_a_deadline_the_walk_is_the_same_oldest_first():
    with _Feed(played=list(range(1, 18))) as f:
        rep = B.backtest_from_stats(2025, [6, 7, 8])
    assert f.built == [6, 7, 8] and rep.weeks_covered == [6, 7, 8]


def test_a_deadline_takes_the_newest_weeks_first_and_stops_on_time():
    clock = _Clock()
    real = _patched_monotonic(clock)
    try:
        with _Feed(played=list(range(1, 18)), cost=600.0, clock=clock) as f:
            rep = B.backtest_from_stats(2025, list(range(6, 18)), deadline=clock() + 1500,
                                        newest_first=True)
    finally:
        time.monotonic = real
    # 0 s, 600 s; at 1200 s 300 s are left, under the 600 s a week takes.
    assert f.built == [17, 16], f.built
    assert rep.weeks_covered == [16, 17] and rep.stopped_early, (rep.weeks_covered, rep.stopped_early)
    assert rep.n == 2


def test_a_week_starts_only_with_time_for_one_at_the_last_ones_pace():
    clock = _Clock()
    real = _patched_monotonic(clock)
    logs = []
    try:
        with _Feed(played=list(range(1, 18)), cost=600.0, clock=clock) as f:
            rep = B.backtest_from_stats(2025, list(range(6, 18)), deadline=clock() + 1800,
                                        newest_first=True, log=logs.append)
        # 0 s, 600 s, 1200 s: at 1200 s exactly a week is left, so it starts.
        assert f.built == [17, 16, 15], f.built
        assert any("stopped at the run's time limit: 3 of 12 weeks replayed" in ln for ln in logs), logs
        with _Feed(played=list(range(1, 18)), cost=600.0, clock=clock) as f:
            rep = B.backtest_from_stats(2025, list(range(6, 18)), deadline=clock() + 100,
                                        newest_first=True)
        # The first week has no pace to go by and always starts.
        assert f.built == [17] and rep.weeks_covered == [17] and rep.stopped_early, f.built
    finally:
        time.monotonic = real


def test_the_order_changes_no_weeks_answer():
    with _Feed(played=list(range(1, 18))):
        a = B.backtest_from_stats(2025, [6, 7, 8, 9])
    with _Feed(played=list(range(1, 18))):
        b = B.backtest_from_stats(2025, [6, 7, 8, 9], newest_first=True)
    assert (a.n, a.wins, a.n_bets) == (b.n, b.wins, b.n_bets)


def test_the_labs_nfl_section_passes_its_budget_and_says_which_weeks():
    clock = _Clock()
    real = _patched_monotonic(clock)
    logs = []
    keep = lab.nfl_closes
    lab.nfl_closes = lambda conn, markets=lab.NFL_MARKETS: {}
    try:
        with _Feed(played=list(range(1, 10)), cost=700.0, clock=clock):
            got = lab.nfl_props(season=2026, log=logs.append, conn=object(),
                                budget_s=lab.LAB_NFL_PROPS_BUDGET_S)
    finally:
        time.monotonic = real
        lab.nfl_closes = keep
    m = got["markets"][0]
    # Weeks 9 and 8 (700 s each); 400 s left would not cover week 7.
    assert m["weeks"] == [8, 9] and m["weeks_replayed"] == 2 and m["stopped_early"], m
    assert any("week 9 (1/" in ln for ln in logs), logs[:4]
    assert any("stopped at the run's time limit" in ln for ln in logs), logs
    assert 15 * 60 <= lab.LAB_NFL_PROPS_BUDGET_S <= 40 * 60


def test_the_lab_builds_the_nfl_with_its_budget():
    import inspect
    src = inspect.getsource(lab.build_sport)
    assert "budget_s=cap(LAB_NFL_PROPS_BUDGET_S)" in src


class _Tape:
    """`db.closing_odds_by_date`, offline: one close per market, each read
    costing ``cost`` seconds of the fake clock; ``fail`` raises instead."""
    def __init__(self, clock=None, cost=0.0, fail=False):
        self.clock, self.cost, self.fail, self.reads = clock, cost, fail, []

    def __enter__(self):
        from engine import db
        self.db, self.saved = db, db.closing_odds_by_date

        def read(conn, sport, market):
            self.reads.append((sport, market))
            if self.clock is not None:
                self.clock.t += self.cost
            if self.fail:
                raise RuntimeError("database is locked")
            return {("rb 9", "2026-11-01"): {"line": 70.5, "over_odds": -110,
                                             "under_odds": -110, "book": "pinnacle"}}
        db.closing_odds_by_date = read
        return self

    def __exit__(self, *exc):
        self.db.closing_odds_by_date = self.saved


def test_the_closes_are_read_inside_the_replays_limit_and_handed_on():
    clock = _Clock()
    real = _patched_monotonic(clock)
    seen = {}
    keep = lab.nfl_replay

    def replay(season, weeks, real_lines, log=print, progress=None, deadline=None):
        seen["deadline"], seen["real"] = deadline, real_lines
        return None, 2026, ["2026: nothing settled"]
    lab.nfl_replay = replay
    out: dict = {}
    try:
        with _Tape(clock=clock, cost=60.0) as tape:
            lab.nfl_props(log=lambda *_: None, conn=object(), budget_s=1800, closes_out=out)
    finally:
        time.monotonic = real
        lab.nfl_replay = keep
    assert [m for _s, m in tape.reads] == list(lab.NFL_MARKETS), tape.reads
    # The clock started before the five reads (1000 s), not after them (1300 s).
    assert seen["deadline"] == 1000.0 + 1800, seen["deadline"]
    assert sorted(out) == sorted(lab.NFL_MARKETS), sorted(out)
    assert ("rb 9", "rec_yds", "2026-11-01") in seen["real"]


def _nfl_section(fail=False):
    """build_sport('nfl') offline: the replay and the game lines stubbed,
    the ripple's own entry point recording what it was handed."""
    from engine import ripplefit
    got, logs = {}, []
    keep = (lab.nfl_replay, lab.game_lines, ripplefit.run)
    lab.nfl_replay = lambda *a, **k: (None, 2026, ["2026: nothing settled"])
    lab.game_lines = lambda conn, sport, log=print: {"unavailable": "stubbed"}

    def run(conn, seasons=None, dates=None, closes=None, models_dir=None, log=print):
        got["closes"] = closes
        if closes is None:              # as the real one: it reads its own
            from engine import db
            for m in ripplefit.MARKETS:
                db.closing_odds_by_date(conn, "nfl", m)
        return {"markets": {}}
    ripplefit.run = run
    try:
        with _Tape(fail=fail) as tape:
            blob = lab.build_sport("nfl", object(), log=logs.append)
    finally:
        lab.nfl_replay, lab.game_lines, ripplefit.run = keep
    return blob, got, tape, logs


def test_the_ripple_reuses_the_replays_closes():
    from engine import ripplefit
    blob, got, tape, _logs = _nfl_section()
    assert len(tape.reads) == len(lab.NFL_MARKETS), tape.reads      # five, not eight
    assert set(ripplefit.MARKETS) <= set(got["closes"] or {}), got
    assert blob["ripple"] == {"markets": {}}


def test_when_the_closes_cannot_be_read_the_ripple_reads_its_own():
    from engine import ripplefit
    blob, got, tape, logs = _nfl_section(fail=True)
    assert got["closes"] is None
    assert any("lab: nfl closes unavailable" in ln for ln in logs), logs
    # The replay's first read failed; the ripple tried its own, failed the
    # same way, and the page says so rather than the Lab dying.
    assert tape.reads == [("nfl", lab.NFL_MARKETS[0]), ("nfl", ripplefit.MARKETS[0])], tape.reads
    assert "unavailable" in blob["ripple"] and "database is locked" in blob["ripple"]["unavailable"]


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
