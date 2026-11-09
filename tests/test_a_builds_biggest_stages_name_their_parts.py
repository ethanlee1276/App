"""A board build's two biggest stages name their parts on the heartbeat
(engine/stageclock.lap, part, parse_parts; engine/pipeline.run_slate;
engine/ideas.attach; launch._parts_of, _note_board).

The NFL build's stage times on 8 November: its pricing stage (run_slate)
ran 37 seconds at 07:57 and 112 at 08:09, and its inventions' readings 33
at 08:25 — and a stage's one number cannot say which of the jobs inside it
took the time. What these hold:

  * a part line names a stage's part and its seconds, read back as
    ``{stage: {part: seconds}}``, a part named twice adding up; a part is
    never counted as a stage, so the stages still add up to the build;
  * nothing prints unless a build started the clock in that process — the
    backtest and the Lab price thousands of slates through run_slate;
  * run_slate says each of its jobs in order, and the board it returns is
    the same with the clock running or not;
  * the readings say each section's seconds and their journals' and write;
  * the matchup scan (11.6 and 13.3 of the pricing stage's seconds at 09:16
    and 09:33) says each table it reads under its own name, so its parts
    are never added into the pricing's, and reads the same with the clock
    running or not;
  * the NFL build's three stages that had no parts — the prices (25 s at
    09:33), the pipeline's stamps (12 s) and the tracker's hooks (15 s) —
    name theirs, each lap under the stage that holds it, so the heartbeat
    files every part under the right stage;
  * a build's parts ride its board's heartbeat entry beside its stages,
    taken once, and a build killed at its limit keeps the parts it printed.

Run directly: `python3 tests/test_a_builds_biggest_stages_name_their_parts.py`
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import launch                                                       # noqa: E402
from engine import stageclock                                       # noqa: E402

RUN_SLATE_PARTS = ["price props", "game bets", "correlations + exposure caps", "long shots + touchdown menu",
                   "matchup scan", "most likely board", "touchdown scenarios", "matchup picks",
                   "census + player stats + shelves + market scan", "incentives + milestones",
                   "playoff picture", "fatigue", "comps", "parlay screen"]
MATCHUP_SCAN_PARTS = ["unit ratings", "season numbers", "red zone", "depth + defenders", "scheme",
                      "charting + tracking", "snaps + weekly usage", "depth mix + pocket", "contact",
                      "headshots", "the games", "touchdown stamps"]
NFL_STAGE_PARTS = {
    "prices + quote journal + line ledger": ["odds onto the slate", "book margins", "quote journal",
                                             "line ledger", "prop tape"],
    "pipeline": ["game plan + avoid warnings", "freshness", "resets + carried", "team logs",
                 "correlations + exposure caps", "drawdown", "line movement stamps", "line tape",
                 "the printout"],
    "tracker + exchange fair + crowd + openers + splits": [
        "odds clocks + calibration + tiers", "live lines", "drive sim", "team shapes", "open-bet tracker",
        "exchange fair", "crowd", "openers", "splits"],
}


class _Stopped:
    """The stage clock as a process that never started it (the backtest)."""

    def __enter__(self):
        self.keep = dict(stageclock._STATE)
        stageclock._STATE.update(t0=None, last=None)

    def __exit__(self, *exc):
        stageclock._STATE.clear()
        stageclock._STATE.update(self.keep)


def test_a_part_reads_back_and_is_never_counted_as_a_stage():
    said = []
    with _Stopped():
        t = stageclock.lap("run_slate", "price props", 0.0, out=said.append, clock=lambda: 5.0)
        stageclock.part("ideas readings", "menu", 1.2, out=said.append)
        assert said == [] and t == 5.0, "silent before a build starts the clock, and still returns now"
        stageclock.start(clock=lambda: 0.0)
        t = stageclock.lap("run_slate", "price props", 0.0, out=said.append, clock=lambda: 12.34)
        t = stageclock.lap("run_slate", "game bets", t, out=said.append, clock=lambda: 13.0)
        stageclock.part("ideas readings", "menu", 1.24, out=said.append)
        stageclock.part("ideas readings", "menu", 0.5, out=said.append)
        stageclock.mark("run_slate", out=said.append, clock=lambda: 20.0)
    assert said[:2] == ["  ⏱ run_slate › price props: 12.3s", "  ⏱ run_slate › game bets: 0.7s"], said
    parts = stageclock.parse_parts(said + ["Analyzed 610 props", "⏱ not › a part"])
    assert parts == {"run_slate": {"price props": 12.3, "game bets": 0.7},
                     "ideas readings": {"menu": 1.7}}, parts
    assert list(parts["run_slate"]) == ["price props", "game bets"], "in the order they printed"
    assert stageclock.parse(said) == {"run_slate": 20}, "a part line is never a stage"
    assert stageclock.parse_parts(["  ⏱ run_slate: 60s (at 120s of 600)"]) == {}, "a stage line is never a part"
    assert stageclock.parse_parts(None) == {}


def test_a_broken_clock_or_printer_never_raises():
    def boom(*a):
        raise RuntimeError("no")
    with _Stopped():
        stageclock.start(clock=lambda: 0.0)
        assert stageclock.lap("s", "p", 3.0, out=boom, clock=lambda: 4.0) == 4.0
        assert stageclock.lap("s", "p", 3.0, out=print, clock=boom) == 3.0
        stageclock.part("s", "p", "not a number", out=boom)
        stageclock.part("s", "p", 1.0, out=boom)


def _run_slate():
    from engine.pipeline import run_slate
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        got = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    return got, buf.getvalue().splitlines()


#: The build's own wall clock, to the second, wherever it lands: a Most
#: Likely pick that has just gone up is stamped `since` now
#: (engine/likely._stamp_hold), so two runs a second apart differed on it
#: about one time in twelve (8 November). The Most Likely turnover's `at`
#: is the same clock: with the gate's other files running beside it the two
#: runs straddled a second (04:48:37 and 04:48:38 on 9 November) and that
#: key was the whole difference. It is the board's only `at`.
WALL_CLOCK_KEYS = {"generated_at", "built_at", "since", "out_at", "at"}


def _same(a, b):
    def clean(d):
        if isinstance(d, dict):
            return {k: clean(v) for k, v in d.items() if k not in WALL_CLOCK_KEYS}
        if isinstance(d, list):
            return [clean(v) for v in d]
        return d
    return clean(json.loads(json.dumps(a, sort_keys=True, default=str))) == \
        clean(json.loads(json.dumps(b, sort_keys=True, default=str)))


def test_run_slate_names_each_of_its_jobs_and_returns_the_same_board():
    with _Stopped():
        quiet, quiet_lines = _run_slate()
        stageclock.start()
        timed, timed_lines = _run_slate()
    assert not stageclock.parse_parts(quiet_lines), "the backtest's run prints no part"
    parts = stageclock.parse_parts(timed_lines)
    assert list(parts) == ["run_slate"], parts
    assert list(parts["run_slate"]) == RUN_SLATE_PARTS, list(parts["run_slate"])
    assert all(v >= 0 for v in parts["run_slate"].values())
    assert _same(quiet, timed), "the clock changes no number on the board"


def test_the_readings_say_each_sections_seconds():
    from engine import ideas
    said = []
    keep = ideas.build
    ideas.build = lambda sport, props, games, board: {
        "sport": sport, "sections": {"menu": {}, "sim": {}}, "errors": {},
        "timings": {"menu": 2.04, "sim": 11.5}}
    out = str(Path(tempfile.mkdtemp()) / "web" / "data" / "nfl.json")
    try:
        with _Stopped():
            stageclock.start()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ideas.attach("nfl", [], [], {}, out=out)
            said = buf.getvalue().splitlines()
    finally:
        ideas.build = keep
    parts = stageclock.parse_parts(said)["ideas readings"]
    assert list(parts) == ["menu", "sim", "journals + write"], parts
    assert parts["menu"] == 2.0 and parts["sim"] == 11.5 and parts["journals + write"] >= 0


def test_the_college_build_names_the_parts_of_its_first_stage():
    """"history + team ratings" ran 38-40 seconds of every Sunday build:
    three feeds, the results store, three rating computations."""
    import re
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    seg = src[src.index("_clock.start()"):src.index('_clock.mark("history + team ratings")')]
    got = re.findall(r'_clock\.lap\("history \+ team ratings", "([^"]+)"', seg)
    assert got == ["teams + re-key", "schedule", "results window", "store results",
                   "closes from the tape", "upcoming + neighbours", "this season's ratings",
                   "every season's ratings", "rating fit"], got


def _scan_once():
    """One matchup scan of one game, its tables stubbed as the scan's own
    test stubs them (tests/test_the_matchup_scan_reads_every_game.py), and
    what it printed."""
    import types
    from engine import gamescan as G
    from engine.sources import nflscheme as N
    import engine.sources.nflverse as NV
    import engine.teamchange as TC
    real = (G.unit_ratings, N.load_pfr_def, G.scheme_tables, NV.load_weekly_stats, NV.load_snap_counts,
            NV.headshot_map, TC.nfl_changes)
    G.unit_ratings = lambda *a, **k: {}
    N.load_pfr_def = lambda season: []
    G.scheme_tables = lambda season: {"season": 2025, "defense": {}, "receivers": {}}
    NV.load_weekly_stats = lambda s: []
    NV.load_snap_counts = lambda s: []
    NV.headshot_map = lambda s: {}
    TC.nfl_changes = lambda *a, **k: {}                 # never the schedule download
    result = {"games": [{"home": "GB", "away": "ATL"}],
              "recommendations": [{"player": "Christian Watson", "team": "GB", "opponent": "ATL",
                                   "position": "WR", "market": "rec_yds", "hit_prob": 0.7, "odds": -150}]}
    slate = types.SimpleNamespace(games=[types.SimpleNamespace(home="GB", away="ATL", injuries=[])])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            n = G.attach_nfl(result, slate, 2026, 3, conn=object())
    finally:
        (G.unit_ratings, N.load_pfr_def, G.scheme_tables, NV.load_weekly_stats, NV.load_snap_counts,
         NV.headshot_map, TC.nfl_changes) = real
    return n, result, buf.getvalue().splitlines()


def test_the_matchup_scan_names_each_table_it_reads_and_reads_the_same():
    with _Stopped():
        n_quiet, quiet, quiet_lines = _scan_once()
        stageclock.start()
        n_timed, timed, timed_lines = _scan_once()
    assert n_quiet == n_timed == 1
    assert not stageclock.parse_parts(quiet_lines), "a scan outside a build prints no part"
    parts = stageclock.parse_parts(timed_lines)
    assert list(parts) == ["matchup scan"], "its own stage: never added into the pricing's parts"
    assert list(parts["matchup scan"]) == MATCHUP_SCAN_PARTS, list(parts["matchup scan"])
    assert not stageclock.parse(timed_lines), "a part is never a stage"
    assert _same(quiet, timed), "the clock changes no read"
    assert [p["player"] for p in timed["scan_reads"]["ATL@GB"]["players"]] == ["Christian Watson"]


def test_the_nfl_builds_unexplained_stages_name_their_parts_under_their_own_marks():
    import re
    src = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    marks = [(m.start(), m.group(1)) for m in re.finditer(r'_mem\("([^"]+)", args\.memtrace\)', src)]
    for stage, want in NFL_STAGE_PARTS.items():
        at = [k for k, (_pos, name) in enumerate(marks) if name == stage]
        assert len(at) == 1, stage
        seg = src[marks[at[0] - 1][0]:marks[at[0]][0]]
        laps = re.findall(r'_lap\("([^"]+)", "([^"]+)"', seg)
        assert {st for st, _p in laps} == {stage}, ("each lap under the stage that holds it", stage, laps)
        assert [p for _st, p in laps] == want, (stage, laps)
    every = re.findall(r'_lap\("([^"]+)", "([^"]+)"', src)
    assert sorted(every) == sorted((st, p) for st, ps in NFL_STAGE_PARTS.items() for p in ps), \
        "no lap outside the three stages"


def test_the_nfl_builds_lap_prints_only_in_a_build_and_never_raises():
    import nfl_build
    with _Stopped():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t = nfl_build._lap("pipeline", "freshness", nfl_build._now())
        assert buf.getvalue() == "" and isinstance(t, float), "nothing outside a build"
        stageclock.start()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            nfl_build._lap("pipeline", "freshness", nfl_build._now() - 1.25)
            nfl_build._lap("pipeline", "freshness", nfl_build._now() - 0.5)
        got = stageclock.parse_parts(buf.getvalue().splitlines())
        assert list(got) == ["pipeline"] and 1.7 <= got["pipeline"]["freshness"] < 3.0, got
        keep = stageclock.lap
        stageclock.lap = None                               # a broken clock
        try:
            assert isinstance(nfl_build._lap("pipeline", "freshness", 0.0), float)
        finally:
            stageclock.lap = keep


def _script(body: str) -> str:
    p = Path(tempfile.mkdtemp()) / "fake_build.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


class _Logs:
    def __enter__(self):
        self.keep = launch.BUILD_LOG_DIR
        launch.BUILD_LOG_DIR = Path(tempfile.mkdtemp())
        return launch.BUILD_LOG_DIR

    def __exit__(self, *exc):
        launch.BUILD_LOG_DIR = self.keep


def test_a_builds_parts_ride_its_board_entry_beside_its_stages_once():
    build = _script("""
        print("  ⏱ run_slate › price props: 31.5s")
        print("  ⏱ run_slate › most likely board: 4.0s")
        print("  ⏱ run_slate: 37s (at 60s of 600)")
        print("  ⏱ ideas readings › sim: 12.2s")
        print("  ⏱ ideas readings: 33s (at 93s of 600)")
    """)
    with _Logs():
        ok, _tail = launch._run_build([build], timeout=60)
        assert ok
        launch._note_board("zz_parts_board", ok)
        rec = launch._BOARD_RUNS["zz_parts_board"]
        assert rec["stages"] == {"run_slate": 37, "ideas readings": 33}, rec
        assert rec["parts"] == {"run_slate": {"price props": 31.5, "most likely board": 4.0},
                                "ideas readings": {"sim": 12.2}}, rec
        launch._note_board("zz_parts_board", True)
        assert "parts" not in launch._BOARD_RUNS["zz_parts_board"], "a refresh with no build wears none"
    launch._BOARD_RUNS.pop("zz_parts_board", None)


def test_a_build_killed_at_its_limit_keeps_the_parts_it_printed():
    build = _script("""
        import sys, time
        print("  ⏱ run_slate › price props: 40.0s", flush=True)
        print("  ⏱ run_slate: 41s (at 41s of 600)", flush=True)
        time.sleep(30)
    """)
    with _Logs():
        ok, _why = launch._run_build([build], timeout=2)
        assert not ok
        launch._note_board("zz_parts_killed", ok)
        rec = launch._BOARD_RUNS["zz_parts_killed"]
        assert rec["parts"] == {"run_slate": {"price props": 40.0}}, rec
        assert "(killed in the next stage)" in rec["stages"]
    launch._BOARD_RUNS.pop("zz_parts_killed", None)


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
