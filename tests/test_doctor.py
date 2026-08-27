"""The nightly health check.

Nine diagnostics already existed, scattered across launcher flags. Running
all nine by hand every morning is a thing nobody does, so in practice they
were only ever run AFTER something looked broken — the one time a health
check is too late to be a health check.

The property that matters most here is not that any single check is right.
It is that a BROKEN check reports itself as broken. A monitor that goes
quiet when it fails is worse than no monitor, because it converts "I don't
know" into "everything is fine", and that is the state you act on.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doctor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the property the whole thing rests on ----------------------------------
def test_a_check_that_crashes_becomes_a_finding_not_a_silence():
    rep = doctor.Report()

    @doctor._check(rep, "deliberately broken")
    def _():
        raise RuntimeError("boom")

    assert len(rep.checks) == 1
    assert rep.checks[0]["status"] == doctor.FAIL
    assert "boom" in rep.checks[0]["detail"]
    assert rep.verdict == 2


def test_one_broken_check_does_not_stop_the_others():
    rep = doctor.Report()
    doctor._check(rep, "a")(lambda: (_ for _ in ()).throw(ValueError("x")))
    doctor._check(rep, "b")(lambda: rep.add("b", doctor.OK, "fine"))
    assert [c["check"] for c in rep.checks] == ["a", "b"]


def test_the_verdict_is_the_worst_finding_not_the_last_one():
    rep = doctor.Report()
    rep.add("a", doctor.FAIL, "")
    rep.add("b", doctor.OK, "")
    assert rep.verdict == 2
    clean = doctor.Report()
    clean.add("a", doctor.OK, "")
    assert clean.verdict == 0


def test_an_empty_report_is_not_a_pass_by_accident():
    """max() of nothing has to be a decision, not a crash."""
    assert doctor.Report().verdict == 0


# --- the contract an unattended agent depends on ----------------------------
def test_exit_code_distinguishes_clean_from_warn_from_broken():
    """A routine reading this needs three answers, not two: nothing to do,
    something to mention, something to fix."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    assert "sys.exit(main(" in src
    assert "return rep.verdict" in src
    assert doctor._RANK == {"ok": 0, "warn": 1, "fail": 2}


def test_it_actually_runs_and_exits_nonzero_when_something_is_wrong():
    p = subprocess.run([sys.executable, "doctor.py", "--skip-tests"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert p.returncode in (0, 1, 2)
    assert "health check" in p.stdout
    # Every check reported something — a silent check is the bug above.
    for name in ("stuck bets", "site data", "results ingest", "odds budget",
                 "bet journal", "record page", "git"):
        assert name in p.stdout, f"{name} produced no line at all"


def test_json_mode_is_parseable_and_carries_every_check():
    p = subprocess.run([sys.executable, "doctor.py", "--skip-tests", "--json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    d = json.loads(p.stdout)
    assert d["verdict"] in ("ok", "warn", "fail")
    assert len(d["checks"]) == len(doctor.CHECKS) - 1      # minus the tests
    for c in d["checks"]:
        assert set(c) == {"check", "status", "detail", "fix"}


def test_quiet_mode_says_nothing_when_there_is_nothing_to_say():
    """The point of a nightly routine is that a clean night is silent."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index('quiet = "--quiet" in argv')
    block = src[i:i + 700]
    assert 'if not quiet or c["status"] != OK' in block
    assert "if not quiet:" in block, \
        "the header prints even in quiet mode, so a clean run is not silent"


# --- individual checks that are easy to get subtly wrong --------------------
def test_the_ingest_check_does_not_string_compare_football_weeks():
    """NFL stores period as "2026-W1". Comparing that to "2026-08-01" as a
    string is how --stuck once filtered out every football bet."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_ingest_freshness(")
    block = src[i:i + 1600]
    assert "except (ValueError, TypeError):" in block
    assert "continue" in block


def test_the_ingest_check_reads_the_column_that_exists():
    """`games` has `period`, not `date` — and the first version of this
    check asked for `date`, which is exactly the class of bug the
    self-reporting wrapper was built to surface."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_ingest_freshness(")
    block = src[i:i + 1600]
    assert "MAX(period)" in block
    assert "MAX(date)" not in block


def test_the_record_check_counts_the_way_the_page_counts():
    """The page's performance() excludes zero-staked graded rows; the check
    re-counted them raw, read 181 never-were-bets as "the export is behind",
    and prescribed a settle sweep that could re-run forever without
    reconciling anything. One basis: the check asks performance() itself."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_record_page(")
    block = src[i:i + 2200]
    assert 'ledger.performance(c)["settled"]' in block
    assert '"AND category=\'main\'").fetchone()' not in block, \
        "the raw un-predicated count is back"


def test_an_off_season_sport_is_not_reported_as_a_stale_ingest():
    """The NBA is dark June to October. "last final 4 months ago" is the
    calendar, not a broken feed."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_ingest_freshness(")
    block = src[i:i + 1600]
    assert "and since" in block, \
        "nothing checks whether games were actually played since"


def test_rebuilt_data_files_do_not_count_as_uncommitted_work():
    """Every build rewrites web/data — flagging those would make the git
    check fire every single night and train the reader to ignore it."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_git(")
    block = src[i:i + 900]
    assert 'startswith("web/data/")' in block
    assert 'startswith("data/")' in block


def test_a_missing_slate_is_softer_than_a_stale_one():
    """Out of season a sport has no file at all, and that is normal. A file
    that exists but stopped updating means the launcher died."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_slate_freshness(")
    block = src[i:i + 1400]
    assert "WARN if not stale else FAIL" in block


def test_the_slate_window_survives_a_closed_laptop_overnight():
    assert doctor.STALE_SLATE_H >= 6


# --- the machine the check is running ON ------------------------------------
def test_a_machine_with_no_databases_says_so_instead_of_reporting_clean():
    """The databases are gitignored. A fresh clone — CI, a scheduled cloud
    session — has neither, and `connect()` will happily create an empty one.
    Every data check would then report "0 open bets, no problems found",
    which is not a pass: it is a monitor confidently describing a machine it
    cannot see. That is strictly worse than saying nothing."""
    import tempfile
    from engine import db, ledger
    keep = (db.DEFAULT_DB, ledger.DEFAULT_DB)
    tmp = tempfile.mkdtemp()
    try:
        db.DEFAULT_DB = os.path.join(tmp, "h.db")
        ledger.DEFAULT_DB = os.path.join(tmp, "l.db")
        assert doctor.has_history() is False
        assert doctor.has_journal() is False
        rep = doctor.run(skip_tests=True)
        by = {c["check"]: c for c in rep.checks}
        for name in ("stuck bets", "results ingest", "bet journal",
                     "record page"):
            assert "no " in by[name]["detail"] and "machine" in by[name]["detail"], \
                f"{name} reported a verdict on data it does not have"
            assert by[name]["status"] != doctor.OK, \
                f"{name} passed without looking at anything"
    finally:
        db.DEFAULT_DB, ledger.DEFAULT_DB = keep


def test_an_empty_database_file_is_not_mistaken_for_a_real_one():
    """sqlite creates a valid, tiny, empty DB on first connect. Checking
    existence alone would call that "history present"."""
    import tempfile
    from engine import db
    keep = db.DEFAULT_DB
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "h.db")
        db.DEFAULT_DB = p
        # Passed explicitly: connect()'s default argument was bound at import
        # time, so reassigning the module constant does not redirect it.
        db.connect(p)                     # creates the schema, no rows
        assert os.path.exists(p)
        assert doctor.has_history() is False
    finally:
        db.DEFAULT_DB = keep


# --- the launcher wiring ----------------------------------------------------
def _launch():
    return open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def test_the_launcher_runs_the_check_itself_once_a_day():
    """Nobody runs a diagnostic every morning by hand — that is why the nine
    flags this composes were only ever used after something broke."""
    src = _launch()
    fn = src[src.index("def _background_refresher("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "_run_doctor()" in fn


def test_one_bad_cycle_does_not_kill_the_refresher():
    """This thread is the production site's only pulse, and the server
    keeps serving after it dies — so the death is invisible and every
    board just quietly stops moving until the next deploy. Found
    2026-08-18: a nine-day-old "Active" on a man with a broken wrist.
    `_auto_updater` has carried the same guard all along."""
    src = _launch()
    fn = src[src.index("def _background_refresher("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "except Exception" in fn, "one raise ends every refresh for good"
    assert fn.index("try:") < fn.index("refresh_all(quiet=True)"), \
        "the cycle's work must run INSIDE the guard"


def test_the_loop_leaves_a_heartbeat_and_the_check_reads_it():
    """File mtimes cannot separate a failing BUILD (one stale board, the
    rest moving) from a dead LOOP (everything stale, only a restart
    helps). The loop writes its own pulse each cycle — after the guard,
    so a bad cycle still beats — and --check reads it first."""
    src = _launch()
    fn = src[src.index("def _background_refresher("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "_write_heartbeat(interval)" in fn
    assert fn.index("except Exception") < fn.index("_write_heartbeat(interval)")
    i = src.index("Product data (web/data/*.json")
    assert '"heartbeat.json"' in src[i:i + 2200], \
        "--check must read the pulse beside the per-file ages"


def test_the_daily_check_is_silent_when_nothing_is_wrong():
    """A line that says "all clear" every morning trains you to stop
    reading the line."""
    src = _launch()
    i = src.index("def _run_doctor(")
    block = src[i:i + 1800]
    assert 'bad = [c for c in rep.checks if c["status"] != "ok"]' in block
    assert "if bad:" in block


def test_the_suite_ceiling_is_not_shorter_than_the_suite_is_allowed_to_take():
    """THE HEALTH CHECK FAILED ON THE ONE MACHINE IT IS FOR. Ethan ran
    `python3 doctor.py` on the droplet — 1 vCPU, the live site beside it,
    350 test files — and got:

        the check itself failed: TimeoutExpired(['run_tests.py'], 900)
        ↳ this is a bug in doctor.py, not necessarily in the app

    It was. run_tests.py scales its own PER-FILE ceiling by load, up to an
    hour for a single file, on the stated grounds that killing a slow run
    "reports a failure that is really a queue". The doctor then wrapped
    that whole run in fifteen minutes flat, so the two disagreed: the
    suite was allowed to take longer than the doctor was willing to wait.

    The doctor's ceiling has to be at least the per-file one it contains,
    or the containing timeout can fire while a single legal file is still
    running."""
    import run_tests
    idle_file_ceiling = run_tests.FILE_TIMEOUT * 4     # its own hard cap
    assert doctor._suite_timeout() >= run_tests.FILE_TIMEOUT, (
        "the doctor would kill the suite while one file is still inside "
        "its own allowance")
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def _suite_timeout(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "getloadavg" in body and "cpu_count" in body, (
        "the ceiling is fixed again, so a loaded box reports a queue as "
        "a failure")
    assert "5400" in body, "there is no cap, so a hung suite hangs the check"
    assert idle_file_ceiling >= 3600, "run_tests' cap moved; re-check this"


def test_a_suite_that_does_not_finish_is_not_reported_as_a_failure():
    """A red mark for "the box was busy" is how a reader learns to ignore
    red marks. It is a WARN that names the load and points at the flag
    that skips the suite."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_tests(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "except subprocess.TimeoutExpired:" in body, (
        "a timeout still escapes to _check, which files it as a doctor bug")
    j = body.index("except subprocess.TimeoutExpired:")
    arm = body[j:body.index("return", j)]
    # CODE ONLY. The comment in that arm says "NOT a FAIL", which the
    # first cut of this read as the arm filing a FAIL.
    code = "\n".join(l for l in arm.split("\n")
                     if not l.strip().startswith("#"))
    assert "WARN" in code and "FAIL" not in code
    assert "--skip-tests" in arm, "the reader is not told how to get past it"
    assert "getloadavg" in arm, "it does not say what made it slow"


def test_the_daily_check_does_not_run_the_test_suite_in_the_refresh_loop():
    """The suite takes minutes; the refresh cycle is 60 seconds."""
    src = _launch()
    i = src.index("def _run_doctor(")
    assert "skip_tests=True" in src[i:i + 1800]


def test_the_daily_check_throttles_to_one_run_per_calendar_day():
    src = _launch()
    i = src.index("def _run_doctor(")
    block = src[i:i + 1800]
    assert 'state.get("last_doctor_day") == today' in block
    assert 'state["last_doctor_day"] = today' in block


def test_a_broken_health_check_cannot_take_the_site_down():
    src = _launch()
    i = src.index("def _run_doctor(")
    block = src[i:i + 1800]
    assert "except Exception as exc:" in block
    assert "return 0" in block[block.index("except Exception as exc:"):]


def test_it_is_reachable_by_hand_too():
    src = _launch()
    assert 'if "--doctor" in argv:' in src


def test_ci_mode_drops_the_checks_that_need_the_laptop():
    """Six warnings a night that are all correct behaviour is noise, and
    noise teaches you to ignore the run."""
    rep = doctor.run(skip_tests=True, code_only=True)
    names = {c["check"] for c in rep.checks}
    assert names == {"git"}, f"code-only still ran {names - {'git'}}"


def test_ci_mode_still_runs_the_suite_when_asked():
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    assert "if code_only and fn in DATA_CHECKS:" in src
    assert doctor.check_tests not in doctor.DATA_CHECKS, \
        "code-only would skip the test suite, which is the whole point of CI"


def test_the_odds_budget_does_not_report_its_own_default_as_a_reading():
    """load() falls back to ASSUMED_MONTHLY when no state file exists, so a
    fresh clone would report "500 credits left" — the same lie as calling an
    empty journal clean."""
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    i = src.index("def check_odds_budget(")
    block = src[i:i + 900]
    assert "Path(ob.STATE_PATH).exists()" in block


def test_the_workflow_uses_code_only_so_a_red_run_means_something():
    wf = open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"),
              encoding="utf-8").read()
    assert "--code-only" in wf
    assert "python3 run_tests.py" in wf


def test_the_workflow_does_not_quietly_grow_a_dependency():
    """The engine is standard library end to end. A pip install appearing
    here is a fact worth noticing, not papering over."""
    wf = open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"),
              encoding="utf-8").read()
    # Comments stripped: the comment explaining why there is no install step
    # names the thing it is ruling out, and that note is the point.
    steps = "\n".join(l for l in wf.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "pip install" not in steps


def _stdlib(root):
    """Is this import root satisfied by a bare interpreter? 3.10+ can just
    answer; 3.9 (still in the test matrix) has to be asked where the module
    came from, and site-packages is the answer that disqualifies it."""
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return root in names
    import importlib.util
    import sysconfig
    try:
        spec = importlib.util.find_spec(root)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    origin = spec.origin or ""
    if origin in ("built-in", "frozen"):
        return True
    return (origin.startswith(sysconfig.get_paths()["stdlib"])
            and "site-packages" not in origin)


def test_no_test_file_imports_a_third_party_module_unguarded():
    """The sibling test above guards the WORKFLOW against growing a
    dependency, and that turned out to be the wrong half of the door. The
    venue intake tool is the repo's one Pillow user, and its test imported
    PIL at module scope — no pip install anywhere, workflow still clean,
    and the entire suite red on every machine without Pillow, GitHub
    included, from the night the tool landed.

    So state the invariant where it actually bites: a module-scope import
    in tests/ must be standard library or first-party. Anything else has
    to sit inside a try/except that skips the file, which keeps a hand-run
    tool's dependency from becoming the suite's dependency. Imports nested
    in a try or inside a function are not module-scope and pass freely —
    that is the escape hatch, and it is deliberate.
    """
    import ast
    local = {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}
    local |= {d for d in os.listdir(ROOT)
              if os.path.isdir(os.path.join(ROOT, d))
              and not d.startswith(".")}
    bad = []
    for f in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        path = os.path.join(ROOT, "tests", f)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in tree.body:          # top level only: try/def bodies are not
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # A relative import has no module of its own to resolve.
                roots = [node.module.split(".")[0]] if node.level == 0 \
                    and node.module else []
            else:
                continue
            for r in roots:
                if r not in local and not _stdlib(r):
                    bad.append(f"{f}: {r}")
    assert not bad, ("module-scope third-party imports in tests/ — guard "
                     f"them with try/except + a SKIP line: {bad}")


def test_a_skipped_test_file_is_not_reported_as_a_pass():
    """The skip has to be louder than a green zero. run_tests.py prints
    "✅ name  0 tests" for any file that exits clean without running
    anything, which is indistinguishable from a file whose tests all
    vanished — so the runner reads the SKIP line and says so, on the
    per-file row and on the summary line doctor.py reports."""
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    assert 'r"^SKIP (.+)$"' in src, "the runner no longer reads SKIP lines"
    assert "skipped" in src
    # And the file that needs it still says it.
    vi = open(os.path.join(ROOT, "tests", "test_venue_ingest.py"),
              encoding="utf-8").read()
    assert "except ModuleNotFoundError" in vi
    assert 'print("SKIP ' in vi


# --- the tripwires for the August bugs ---------------------------------------
def test_the_new_invariant_checks_are_registered_in_both_lists():
    """A check that exists but is not in CHECKS never runs; one missing
    from DATA_CHECKS turns CI red on machines that have no journal. Both
    registrations, or the tripwire is decoration."""
    for fn in (doctor.check_premature_evidence, doctor.check_parlay_agreement,
               doctor.check_forecast_log, doctor.check_game_calibration,
               doctor.check_fitter_cadence):
        assert fn in doctor.CHECKS, fn.__name__
        assert fn in doctor.DATA_CHECKS, fn.__name__


def test_an_uncalibrated_site_is_warned_about_not_reported_healthy():
    """Every spread and total on the flat 0.5 guess is a finding.

    The guess was unfalsifiable for most of this site's life because no
    closing spread or total was stored anywhere. Now that it is
    measurable, "nothing has ever been measured" must read as a warning
    rather than as silence.
    """
    from engine import gamecal
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    gamecal.STATE_PATH = os.path.join(tempfile.mkdtemp(), "gamecal.json")
    gamecal._cache.clear()
    try:
        rep = doctor.Report()
        doctor.check_game_calibration(rep)
        found = [c for c in rep.checks if c["check"] == "game-line calibration"]
        assert found and found[0]["status"] == doctor.WARN, found
        assert "flat 0.5" in found[0]["detail"]
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


def test_a_measured_zero_is_reported_as_the_headline():
    """"No edge and we know it" and "no edge and we are still betting"
    are different states, and the rung has to distinguish them."""
    from engine import gamecal
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    gamecal.STATE_PATH = os.path.join(tempfile.mkdtemp(), "gamecal.json")
    gamecal._cache.clear()
    try:
        # Every sport fitted, so nothing is left staking on the guess and
        # the measured zero is the only thing left to report. The separate
        # "staking on the unmeasured guess" warning has its own test.
        gamecal._write_state({
            f"{sp}:{m}": {"shrink": 0.0 if sp == "nfl" else 0.3,
                          "slope": 0.006, "se": 0.085, "n": 899,
                          "sport": sp, "market": m, "fit_at": time.time()}
            for sp in ("nfl", "cfb", "mlb")
            for m in ("spread", "total", "moneyline")})
        gamecal._cache.clear()
        rep = doctor.Report()
        doctor.check_game_calibration(rep)
        c = [x for x in rep.checks if x["check"] == "game-line calibration"][0]
        assert c["status"] == doctor.OK, c
        assert "no edge over the close" in c["detail"]
        assert "nfl spread" in c["detail"]
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


def test_a_site_with_history_and_no_deep_fit_is_warned_about():
    """The failure this rung exists for: a sport with the logs to fit,
    and nothing ever fitted, because the schedule stopped reaching the
    fitter and silence looked like nothing to report."""
    from engine import deepfit
    keep_stocked = deepfit.sports_with_history
    keep_isfile = doctor.os.path.isfile
    deepfit.sports_with_history = lambda *a, **k: ["nfl"]
    doctor.os.path.isfile = lambda p: (False if "data/models" in str(p)
                                       else keep_isfile(p))
    try:
        rep = doctor.Report()
        doctor.check_fitter_cadence(rep)
        c = [x for x in rep.checks if x["check"] == "fitter cadence"][0]
        assert c["status"] == doctor.WARN, c
        assert "nothing has ever been fitted" in c["detail"]
    finally:
        deepfit.sports_with_history = keep_stocked
        doctor.os.path.isfile = keep_isfile


def test_no_ingested_history_is_reported_as_a_fact_not_a_fault():
    """A fresh clone has fitted nothing because it has ingested nothing.
    A warning that implies a bug where there is none is how you learn to
    skip warnings."""
    from engine import deepfit
    keep = deepfit.sports_with_history
    deepfit.sports_with_history = lambda *a, **k: []
    try:
        rep = doctor.Report()
        doctor.check_fitter_cadence(rep)
        c = [x for x in rep.checks if x["check"] == "fitter cadence"][0]
        assert c["status"] == doctor.OK, c
        assert "no sport has enough ingested logs" in c["detail"]
    finally:
        deepfit.sports_with_history = keep


def test_the_flow_weights_report_whether_they_are_measured():
    from engine import pmfit
    keep, keep_cache = pmfit.STATE_PATH, dict(pmfit._cache)
    pmfit.STATE_PATH = os.path.join(tempfile.mkdtemp(), "pmfit.json")
    pmfit._cache.clear()
    try:
        rep = doctor.Report()
        doctor.check_fitter_cadence(rep)
        assert "still on the assigned numbers" in rep.checks[0]["detail"]
        pmfit._write_state({"points": {"impact": 50, "niche": 0},
                            "n": 900, "fit_at": time.time()})
        pmfit._cache.clear()
        rep2 = doctor.Report()
        doctor.check_fitter_cadence(rep2)
        d = rep2.checks[0]["detail"]
        assert "measured on 900 resolved flags" in d
        assert "1 signal(s) measured at no edge" in d
    finally:
        pmfit.STATE_PATH = keep
        pmfit._cache.clear()
        pmfit._cache.update(keep_cache)


def test_a_sport_staking_on_the_unmeasured_guess_is_named():
    """The flat 0.5 haircut is defensible where nothing is at risk and is
    a live exposure where money is. On the one sport where that guess was
    ever checked it was roughly sixteen times too generous."""
    from engine import gamecal, probation
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    gamecal.STATE_PATH = os.path.join(tempfile.mkdtemp(), "gamecal.json")
    gamecal._cache.clear()
    try:
        gamecal._write_state({
            f"nfl:{m}": {"shrink": 0.0, "slope": 0.0, "se": 0.05, "n": 899,
                         "sport": "nfl", "market": m, "fit_at": time.time()}
            for m in ("spread", "total", "moneyline")})
        gamecal._cache.clear()
        assert probation.advisories("cfb")      # cfb has no fit
        assert probation.advisories("nfl") == []
        rep = doctor.Report()
        doctor.check_game_calibration(rep)
        c = [x for x in rep.checks if x["check"] == "game-line calibration"][0]
        assert c["status"] == doctor.WARN, c
        assert "cfb" in c["detail"] and "staking on the unmeasured guess" in c["detail"]
        assert "nfl are" not in c["detail"] and "nfl," not in c["detail"]
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


def test_a_stale_calibration_is_warned_about():
    """A fit nobody has refreshed in a season means the nightly settle
    stopped reaching it — which is exactly how the last dead feedback
    loop on this site stayed dead."""
    from engine import gamecal
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    gamecal.STATE_PATH = os.path.join(tempfile.mkdtemp(), "gamecal.json")
    gamecal._cache.clear()
    try:
        old_ts = time.time() - (doctor.GAMECAL_STALE_DAYS + 5) * 86400
        gamecal._write_state({"nfl:total": {
            "shrink": 0.03, "slope": 0.03, "se": 0.11, "n": 899,
            "sport": "nfl", "market": "total", "fit_at": old_ts}})
        gamecal._cache.clear()
        rep = doctor.Report()
        doctor.check_game_calibration(rep)
        c = [x for x in rep.checks if x["check"] == "game-line calibration"][0]
        assert c["status"] == doctor.WARN, c
        assert "days old" in c["detail"]
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


def test_a_settled_game_bet_with_no_final_score_fails_grade_evidence():
    """The fingerprint of the live-score leak: a game bet graded while its
    games row has no final. The parser fix stops new ones; this fires if
    any future feed reintroduces the leak."""
    import tempfile
    from engine import db, ledger

    # Point both connects at throwaway files, run the check, restore.
    tmp = tempfile.mkdtemp()
    lpath, hpath = os.path.join(tmp, "l.db"), os.path.join(tmp, "h.db")
    lc = ledger.connect(lpath)
    lc.execute(
        "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
        "stake_units,stake_dollars,status,category,actual) VALUES "
        "('x','nba','2026-01-15','GSW@LAL','total','OVER',224.5,'DK',-110,"
        "1.0,10.0,'lost','main',97.0)")
    lc.commit()
    db.connect(hpath)                    # empty history: no games row at all

    # connect()'s default path binds at import, so patch the functions —
    # not the constants they were built from.
    orig_lc, orig_hc = ledger.connect, db.connect
    orig_hj, orig_hh = doctor.has_journal, doctor.has_history
    ledger.connect = lambda path=None: orig_lc(lpath)
    db.connect = lambda path=None: orig_hc(hpath)
    doctor.has_journal = doctor.has_history = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_premature_evidence(rep)
    finally:
        ledger.connect, db.connect = orig_lc, orig_hc
        doctor.has_journal, doctor.has_history = orig_hj, orig_hh
    row = next(r for r in rep.checks if r["check"] == "grade evidence")
    assert row["status"] == doctor.FAIL
    assert "no final score" in row["detail"]


def test_grade_evidence_says_which_of_the_two_causes_it_found():
    """Ethan's droplet, 2026-08-23: "11 settled game bet(s) have no final
    score behind them" and nothing else. Eleven is not a diagnosis — the
    two causes need opposite fixes (refetch the day vs fix a team name),
    and the check knows which it is looking at."""
    import tempfile
    from engine import db, ledger

    tmp = tempfile.mkdtemp()
    lpath, hpath = os.path.join(tmp, "l.db"), os.path.join(tmp, "h.db")
    lc = ledger.connect(lpath)
    for date, team in (("2026-01-15", "LAL"), ("2026-01-16", "Lakers")):
        lc.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,stake_units,stake_dollars,status,category,actual) VALUES "
            "('x','nba',?,?,'moneyline','OVER',0.5,'DK',-110,1.0,10.0,"
            "'lost','main',0.0)", (date, team))
    lc.commit()
    hc = db.connect(hpath)
    # 01-16 IS ingested, under the feed's spelling — so that bet's problem
    # is the NAME. 01-15 has nothing at all — that one's problem is the DAY.
    db.upsert_games(hc, [{"sport": "nba", "season": 2026,
                          "period": "2026-01-16", "game_id": "BOS@LAL",
                          "home": "LAL", "away": "BOS",
                          "home_score": 110, "away_score": 99}])

    orig_lc, orig_hc = ledger.connect, db.connect
    orig_hj, orig_hh = doctor.has_journal, doctor.has_history
    ledger.connect = lambda path=None: orig_lc(lpath)
    db.connect = lambda path=None: orig_hc(hpath)
    doctor.has_journal = doctor.has_history = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_premature_evidence(rep)
    finally:
        ledger.connect, db.connect = orig_lc, orig_hc
        doctor.has_journal, doctor.has_history = orig_hj, orig_hh
    row = next(r for r in rep.checks if r["check"] == "grade evidence")
    assert row["status"] == doctor.FAIL
    d = row["detail"]
    assert "2 settled game bet(s)" in d
    assert "1 on dates with no finals stored at all" in d
    assert "1 whose date IS stored but not that team" in d
    # And it names them, so the next run is actionable without a query.
    assert "2026-01-15" in d and "Lakers" in d


def test_a_ticket_disagreeing_with_its_legs_fails_parlay_agreement():
    import tempfile
    from engine import ledger, parlayledger

    tmp = tempfile.mkdtemp()
    lpath = os.path.join(tmp, "l.db")
    lc = ledger.connect(lpath)
    parlayledger.ensure_schema(lc)
    lc.execute("INSERT INTO parlays (sport, date, status, parlay_type)"
               " VALUES ('mlb','2026-07-24','lost','A')")
    pid = lc.execute("SELECT id FROM parlays").fetchone()[0]
    lc.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market,"
               " side, line, odds, status) VALUES (?,'1','Beta Guy',"
               "'total_bases','OVER',1.5,-110,'lost')", (pid,))
    # The single healed to won; the ticket still says its leg lost.
    lc.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
               "odds,stake_units,stake_dollars,status,category) VALUES "
               "('x','mlb','2026-07-24','Beta Guy','total_bases','OVER',1.5,"
               "'DK',-110,0.5,5.0,'won','main')")
    lc.commit()

    orig_lc, orig_hj = ledger.connect, doctor.has_journal
    ledger.connect = lambda path=None: orig_lc(lpath)
    doctor.has_journal = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_parlay_agreement(rep)
    finally:
        ledger.connect, doctor.has_journal = orig_lc, orig_hj
    row = next(r for r in rep.checks if r["check"] == "parlay agreement")
    assert row["status"] == doctor.FAIL
    assert "disagree" in row["detail"]


def test_a_broken_forecast_chain_fails_the_doctor():
    import datetime, tempfile
    from engine import ledger

    tmp = tempfile.mkdtemp()
    lpath = os.path.join(tmp, "l.db")
    lc = ledger.connect(lpath)
    now = datetime.datetime.now().isoformat()
    for i in range(4):
        lc.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,"
                   "book,odds,hit_prob,edge,status) VALUES (?,'mlb',"
                   "'2026-08-02',?,'hits','OVER',0.5,'DK',-110,0.6,0.05,"
                   "'won')", (now, f"P{i}"))
    lc.commit()
    ledger.seal_forecasts(lc)
    lc.execute("UPDATE forecast_log SET hit_prob=0.99 WHERE seq=2")
    lc.commit()

    orig_lc, orig_hj = ledger.connect, doctor.has_journal
    ledger.connect = lambda path=None: orig_lc(lpath)
    doctor.has_journal = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_forecast_log(rep)
    finally:
        ledger.connect, doctor.has_journal = orig_lc, orig_hj
    row = next(r for r in rep.checks if r["check"] == "forecast log")
    assert row["status"] == doctor.FAIL
    assert "BROKEN at #2" in row["detail"]



# --- did the scheduled agents RUN, not just load -----------------------------
def test_the_agent_check_reads_logs_not_launchctl():
    """ETHAN, 2026-08-09. `launchctl list` showed all three agents loaded
    with a last exit status of 0, and `logs/nightly-2026-08-09.log` did
    not exist — the nightly had not run that day at all. Installed,
    healthy-looking and silent is indistinguishable from working, which
    is how "I have to settle by hand every day" went unexplained.

    The LOG is the evidence because the script writes it, while launchd
    writes the status. A plist can be loaded and never fire: the machine
    asleep at the hour, an agent installed after today's slot, or TCC
    refusing the working directory — all three have happened on this
    machine."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("Scheduled agents (did they run")
    body = src[i:i + 2200]
    assert 'glob(f"{stem}-*.log")' in body, "it must read the scripts' own logs"
    assert "launchctl" not in body, (
        "a loaded plist is not a run — that is the exact confusion this "
        "check exists to remove")
    assert "st_mtime" in body, "age comes from the log's own timestamp"


def test_a_never_run_agent_is_not_reported_as_merely_old():
    """No log at all and a stale log are different problems with different
    fixes — one needs a first run, the other needs to know why a schedule
    stopped firing. The two branches say different things."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("Scheduled agents (did they run")
    body = src[i:i + 2200]
    assert "no log has ever been written" in body
    assert "with no run" in body
    assert body.index("no log has ever been written") < body.index("with no run")


def test_the_nightly_runs_every_sports_results_not_just_baseball():
    """ETHAN, 2026-08-09: "is nightly tied into nfl and cfb and nba or just
    mlb — we need it tied in with everything."

    BUILDING always was every sport: `refresh_all` covers mlb, nfl, nba,
    wnba, cfb and ufc, so picks journal for all of them. SETTLING was not.
    `settle_now` ingests through `ingest_for_open_bets`, which pulls MLB,
    NBA and WNBA and nothing else — NFL grades off the nflverse WEEKLY
    stats file and CFB off its own feed, and both live in
    `engine.maintenance.run_if_due`.

    That function had exactly two callers and both needed the SERVER up:
    `_startup_chores` and `_background_refresher`. So an unattended machine
    would journal NFL picks every day of the season and grade none of them
    — bets piling up open while the Record page showed nothing, starting
    the week of Sep 9."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def nightly_run(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "_run_maintenance()" in body, (
        "without the daily chores the unattended nightly settles baseball "
        "and hoops only — NFL and CFB results are never ingested")
    # And BEFORE the settle, or it grades against results that are not
    # there yet and the bets stay open for another day.
    assert body.index("_run_maintenance()") < body.index("settle_now(None)")


def test_the_daily_chores_are_not_reachable_only_through_the_server():
    """The shape of the bug, pinned so it cannot come back: a chore that
    only runs while someone is watching is not automation."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    callers = src.count("_run_maintenance()")
    # def + background refresher + startup chores + nightly
    assert callers >= 4, (
        f"only {callers} references — the nightly path must call it too")


# --- the render sweep, and the checklist's duty to say why it failed --------

def _launch() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return open(os.path.join(root, "launch.py"), encoding="utf-8").read()


def _code_only(src: str) -> str:
    """Source with whole-line `#` comments dropped.

    FOURTH TIME. A guard that greps the file it guards keeps matching the
    comment that explains the very fix — the systemd [Service] header, the
    icons http:// rule, `sudo caddy validate`, and now this. Prose has to
    stay free to quote the wrong thing as the wrong thing; only code is
    the instruction. tests/test_public_server.py does the same job for
    markdown with _shell_blocks().
    """
    return "\n".join(ln for ln in src.splitlines()
                      if not ln.lstrip().startswith("#"))


def test_the_sweep_reports_the_line_that_says_what_broke():
    """It reported the LAST line of node's stderr, and a node crash dump
    ends with its own version banner — so a real failure printed
    "sweep produced no output: ['Node.js v22.22.2']" and threw away the
    message above it. The sweep silently skipped for weeks looking like a
    Node problem, while the actual cause was a browser path.

    A health check that hides why it failed is worse than one that fails
    loudly: it teaches you to scroll past the warning."""
    src = _launch()
    assert "splitlines()[-1:]" not in _code_only(src), \
        "the sweep is back to reporting node's version banner"
    i = src.index("sweep produced no output")
    block = src[max(0, i - 900):i + 300]
    assert "noise" in block and "startswith" in block, \
        "nothing filters the stack frames out of the reported line"


def test_the_sweep_looks_for_a_browser_in_more_than_one_place():
    """Playwright resolves a versioned headless-shell path. A machine with
    Chromium installed elsewhere — this project's own container keeps it
    at /opt/pw-browsers/chromium — fails with "Executable doesn't exist",
    which reads as a broken Playwright install and is a path lookup."""
    src = _launch()
    js = src[src.index("_SWEEP_JS"):]
    assert "CHROMIUM_PATH" in js
    assert "/opt/pw-browsers/chromium" in js, "only one location is tried"
    assert "throw lastErr" in js, \
        "a failure to launch would be swallowed rather than reported"


def test_the_sweep_still_covers_every_page_a_visitor_can_reach():
    """The list is the coverage. Weather and Alerts were both absent once
    and both crashed on load; the account screen is now the page every
    locked board will point at."""
    src = _launch()
    sweep = src[src.index("SWEEP_VIEWS = ["):]
    sweep = sweep[:sweep.index("]\n")]
    for required in ("#recommended", "#record", "#mybets", "#account",
                     "#weather", "#alerts", "#lab", "terms.html",
                     "privacy.html"):
        assert required in sweep, f"the sweep no longer opens {required}"



# --- the blank-brain check --------------------------------------------------

def test_the_checklist_reports_whether_the_model_has_learned_anything():
    """The failure this catches is silent and total.

    data/models/ is gitignored — correctly, they are derived — and
    history.db is too, at 65MB. So a fresh clone, which is exactly what a
    new server is, starts with no fitted models and nothing to refit them
    from. Every correction returns its neutral default and the site looks
    completely normal: the picks still appear, they are simply the
    uncorrected ones.

    Found after the first live deploy, when Ethan noticed player memory
    was nowhere on the site. It was not missing from the code. It was
    missing from the box.
    """
    src = _launch()
    assert "def _learned_model(" in src
    assert "_learned_model(ok, warn, bad)" in src, "defined but never called"
    # Each entry must say what running WITHOUT it costs. A list of absent
    # filenames is not a diagnosis.
    block = src[src.index("LEARNED_STORES = ("):]
    block = block[:block.index("\n)")]
    for store in ("playerfit", "formfit", "calibration", "losspatterns"):
        assert store in block, f"{store} is not on the checklist"
    assert block.count('"') >= 18, "entries are missing their consequences"


def test_the_checklist_points_at_the_fix_rather_than_only_the_fault():
    """A warning with no next step is one people learn to scroll past."""
    src = _launch()
    fn = src[src.index("def _learned_model("):]
    fn = fn[:fn.index("\ndef ")]
    assert "deploy/README.md" in fn or "Seeding" in fn
    seed = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "deploy", "seed.sh")
    assert os.path.exists(seed), "the fix it points at does not exist"
    assert os.access(seed, os.X_OK), "seed.sh is not executable"


def test_seed_refuses_to_run_on_the_machine_it_would_seed():
    """Both prompts scroll past in one window and the hosts are easy to
    confuse — `ufw`, `journalctl` and `cd ~/App` have all gone to the
    wrong box this week. Run on the server, seed.sh would ssh to itself,
    fail on publickey, and print a permissions error that reads like a
    broken deploy key rather than "wrong machine"."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sh = _code_only(open(os.path.join(root, "deploy", "seed.sh"),
                         encoding="utf-8").read())
    assert "/srv/qellys" in sh, "nothing detects the server"
    guard = sh[sh.index('if [[ -d /srv/qellys'):][:400]
    assert "exit 2" in guard, "it warns but carries on"
    # And the check must come BEFORE anything is stopped or copied.
    assert sh.index("/srv/qellys && ") < sh.index("systemctl stop qellys")


def test_a_seed_that_dies_still_brings_the_app_back():
    """`set -euo pipefail` plus a stop/start pair is a trap.

    Anything failing in between — a dropped rsync, a Ctrl-C, a terminal
    window closed while it was still going — exits with the service
    STOPPED. And it does not look like an outage: Caddy keeps serving the
    static files off disk, so the site stays up and simply stops being
    true. That is the same silence as the stale board, the unfitted model
    and the skipped sweep, arriving by a fourth route.

    Happened for real on 2026-08-16: a terminal was closed mid-seed and
    the droplet served a frozen board for twelve minutes.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sh = open(os.path.join(root, "deploy", "seed.sh"), encoding="utf-8").read()
    assert "trap _restart_guard EXIT INT TERM HUP" in sh, \
        "no trap — a failed seed leaves the app stopped"
    # HUP is the one that matters for a closed terminal, and the one most
    # likely to be dropped from that list as noise.
    trap_line = [ln for ln in sh.splitlines() if ln.startswith("trap ")][0]
    for sig in ("EXIT", "INT", "TERM", "HUP"):
        assert sig in trap_line, f"the trap does not catch {sig}"
    # The guard must be armed AFTER the stop and disarmed AFTER the start,
    # or it either misses the window or fires on a healthy run.
    stop = sh.index("systemctl stop qellys")
    armed = sh.index("QB_APP_STOPPED=1")
    disarmed = sh.index("QB_APP_STOPPED=0        #")
    assert stop < armed < disarmed, "the guard's window is wrong"
    # …and the disarm must come after the start, not before it.
    assert sh.index("systemctl start qellys", stop) < disarmed


def test_the_routine_seed_cannot_erase_the_live_journal():
    """The footgun in the first version of this script.

    The full seed sends ledger.db, which is right exactly once — when a
    new box has journaled nothing. After that the SERVER owns the record:
    it is the machine running launch.py against live slates, so every
    pick the public Record shows was written there. Re-running the full
    seed a month later would erase all of it, and that is the one loss no
    backup schedule makes painless, because it is a deliberate overwrite
    rather than a fault.

    --models-only is what a refit actually needs: the fitters require the
    65MB history.db so they run on the Mac, and only their output has to
    travel.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sh = open(os.path.join(root, "deploy", "seed.sh"), encoding="utf-8").read()
    assert "--models-only" in sh
    # The ledger must be sent ONLY inside the full-mode branch.
    guarded = sh[sh.index('if [[ "$MODE" == "full" ]]'):]
    guarded = guarded[:guarded.index("\nfi\n")]
    assert "data/ledger.db" in guarded, \
        "the ledger is sent outside the full-mode guard"
    assert sh.count("data/ledger.db") == guarded.count("data/ledger.db") + \
        sh[:sh.index('if [[ "$MODE" == "full" ]]')].count("data/ledger.db"), \
        "a second unguarded ledger send exists"
    # …and models-only must not be gated behind the typed confirmation,
    # or the safe path is the annoying one and nobody uses it.
    assert 'if [[ "$MODE" == "models" ]]; then' in sh


def test_seeding_a_box_stops_the_app_before_it_overwrites_the_database():
    """rsync onto a live SQLite file is a torn copy, and the file in
    question is the public record."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # _code_only, for the fifth time this session: the comment explaining
    # the restart guard says "a dropped rsync", and a bare index() found
    # THAT — before the stop — and reported that the script copies over a
    # running app. Prose has to stay free to name the thing it is about.
    sh = _code_only(open(os.path.join(root, "deploy", "seed.sh"),
                         encoding="utf-8").read())
    stop = sh.index("systemctl stop qellys")
    assert stop < sh.index("rsync"), "it copies over a running app"
    assert "systemctl start qellys" in sh, "it never starts the app again"
    # And it must not do any of this without being asked twice.
    assert "read -r -p" in sh, "no confirmation before replacing the journal"
    assert "chown -R qellys:qellys" in sh, \
        "the app cannot write files root has just delivered"


def test_the_backup_line_reports_an_AGE_not_just_a_filename():
    """It used to print a green tick and a filename, so a nine-week-old
    archive and this morning's read identically unless you date-parsed
    the name in your head.

    The weekly backup runs INSIDE the refresh loop, and that loop dying
    silently has actually happened here (nine days, 2026-08-10). When it
    dies the backups stop with it — which is the moment this line most
    needs to be loud, and was quietest."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index('backups = sorted((ROOT / "data" / "backups")')
    seg = src[i:i + 1800]
    assert "BACKUP_EVERY_DAYS" in seg, "the cadence must come from the source"
    assert "days old" in seg and "DAYS old" in seg, "no age is printed"
    # Three outcomes, and the worst one names the actual cause.
    assert "2 * _every" in seg, "no hard failure band"
    assert "refresh loop is not running" in seg
    assert "systemctl status qellys" in seg, "a diagnosis with no next step"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
