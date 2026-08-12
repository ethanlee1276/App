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


def test_the_daily_check_is_silent_when_nothing_is_wrong():
    """A line that says "all clear" every morning trains you to stop
    reading the line."""
    src = _launch()
    i = src.index("def _run_doctor(")
    block = src[i:i + 1800]
    assert 'bad = [c for c in rep.checks if c["status"] != "ok"]' in block
    assert "if bad:" in block


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
               doctor.check_forecast_log):
        assert fn in doctor.CHECKS, fn.__name__
        assert fn in doctor.DATA_CHECKS, fn.__name__


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
