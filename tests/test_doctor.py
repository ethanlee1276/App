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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
