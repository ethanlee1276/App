"""The thing that counts the tests.

`run_tests.py` is the only place that says whether this project is green,
and it says it in one line: "All green: N tests across M files." Everything
downstream — the nightly, CI, the health check — repeats that sentence
without re-deriving it. So the runner is load-bearing in a way an ordinary
module is not: if it miscounts, nothing else in the project is positioned
to notice.

It was miscounting. The runner reads a file's test count off the file's own
"N tests passed." footer. Fourteen files printed "all good" instead, matched
nothing, scored 0 — and were still drawn ✅ with a 0 beside them. 142 tests
were running and passing while being absent from the headline number.

The miscount was the harmless half. The other half is that a file whose
tests had stopped running ENTIRELY — an import that quietly returns before
the loop, a `__main__` block deleted in a refactor — exits 0, prints
nothing countable, and produces a byte-identical `✅ file  0 tests`. That is
the failure mode run_tests.py's own comment already warned about, one step
further in than the comment reached. Coverage does not announce its own
departure; the runner has to.

Run directly: `python3 tests/test_runner.py`
"""

import contextlib
import io
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()

#: The footer the runner counts. A file that does not print this is
#: invisible to it, however many assertions it makes.
FOOTER = re.compile(r"tests passed")

#: The two files that opt out of counting for a stated reason, and say so
#: on a SKIP line the runner reads.
SKIP_LINE = re.compile(r"^SKIP ", re.M)


def test_every_test_file_prints_a_countable_footer():
    """The invariant, checked against the files themselves rather than
    against a run — a new file adopting the "all good" footer would be
    counted as zero from its very first commit, and nothing about the
    output would look wrong."""
    silent = []
    for name in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        src = open(os.path.join(ROOT, "tests", name), encoding="utf-8").read()
        # Only what the file actually PRINTS counts, so look below the
        # `__main__` line. Two of the fourteen carried "tests passed" in a
        # docstring while printing "all good", and a check that reads the
        # whole file calls those green.
        i = src.find('if __name__ == "__main__":')
        tail = src[i:] if i >= 0 else ""
        if not FOOTER.search(tail) and not SKIP_LINE.search(src):
            silent.append(name)
    assert not silent, (
        "these files print no 'N tests passed.' footer, so run_tests.py "
        f"scores them zero: {', '.join(silent)}")


def test_the_runner_refuses_a_green_zero():
    """The guard itself. A file that exits 0, offers no SKIP reason and
    reports no tests is a failure — not a pass with a 0 in the margin."""
    assert "if code == 0 and not why and n == 0:" in RUNNER, \
        "the green-zero guard is gone"
    i = RUNNER.index("if code == 0 and not why and n == 0:")
    block = RUNNER[i:i + 900]
    assert "failed.append(name)" in block, \
        "a countless file is reported but not actually failed"


def test_a_stated_skip_is_still_allowed_through():
    """The guard must not swallow the legitimate case it sits next to.
    `test_venue_ingest.py` bows out when Pillow is absent, says why, and
    has to keep reading as a skip rather than a failure."""
    i = RUNNER.index("if code == 0 and not why and n == 0:")
    after = RUNNER[i:]
    assert 'skipped.append(name)' in after, "the skip branch is unreachable"
    assert after.index("elif code == 0:") < after.index(
        "skipped.append(name)"), "skips no longer get their own branch"


def test_the_guard_actually_fires_on_a_silent_file():
    """A guard asserted only as a string is a guard nobody has watched
    work. Point the runner at two files of our own — one that counts
    itself, one that exits 0 saying nothing — and check it fails the run
    on the silent one and only the silent one."""
    import run_tests

    box = tempfile.mkdtemp()
    os.mkdir(os.path.join(box, "tests"))

    def write(name, body):
        with open(os.path.join(box, "tests", name), "w",
                  encoding="utf-8") as fh:
            fh.write(body)

    write("test_counts.py", 'print("  ok  x")\nprint("\\n1 tests passed.")\n')
    write("test_silent.py", 'print("nothing to see")\n')
    write("test_bows_out.py", 'print("SKIP no Pillow here")\n')

    # BOTH WAYS ROUND. The runner went parallel on 2026-08-22 and the
    # property that matters is that it did not change its mind about
    # anything: same verdict, same lines, whether the files run one at a
    # time or eight. Running it twice here is the cheapest possible
    # version of that check and it is the one that would catch a result
    # being attributed to the wrong file.
    keep, run_tests.ROOT = run_tests.ROOT, box
    seen = {}
    try:
        for label, argv in (("serial", ["--serial"]), ("parallel", ["-j", "4"])):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = run_tests._run(dict(os.environ), argv)
            seen[label] = (rc, out.getvalue())
    finally:
        run_tests.ROOT = keep
        shutil.rmtree(box, ignore_errors=True)

    for label, (rc, text) in seen.items():
        assert rc == 1, f"[{label}] a silent file did not fail the run:\n{text}"
        assert "test_silent.py" in text and "ran no tests" in text, text
        # …and the two honest files are untouched by the guard.
        assert "❌ test_counts.py" not in text, text
        assert "⏭️" in text and "test_bows_out.py" in text, \
            f"[{label}] a stated skip was caught by the guard:\n{text}"

    # The per-file lines have to be identical and in the same order —
    # only the trailing timing line may differ.
    def lines(text):
        return [l for l in text.splitlines()
                if l.startswith(("  ✅", "  ❌", "  ⏭️", "FAILED:"))]
    assert lines(seen["serial"][1]) == lines(seen["parallel"][1]), (
        "a parallel run reports different results, or reports them in a "
        "different order:\n%r\nvs\n%r"
        % (lines(seen["serial"][1]), lines(seen["parallel"][1])))


def test_a_hung_file_fails_itself_rather_than_the_whole_run():
    """Serially, a file that never returns stalled everything with
    nothing to say. In parallel it would hold a worker for ever and the
    run would end looking merely slow."""
    assert "FILE_TIMEOUT" in RUNNER
    assert "TimeoutExpired" in RUNNER
    # THE HANDLER, not a 400-character window after it. That window
    # broke on 2026-08-23 when the handler grew a diagnosis, and the
    # behaviour it checks — a timed-out file exits non-zero — had not
    # moved at all. Ninth fixed-width slice in this suite to fail for
    # that reason this week.
    i = RUNNER.index("except subprocess.TimeoutExpired")
    handler = RUNNER[i:RUNNER.index("\n    return name, code", i)]
    assert "code = 1" in handler, "a timed-out file still passes"


def test_the_worker_count_can_be_pinned():
    """The droplet has one vCPU and a gigabyte. Whoever is standing in
    front of it needs to be able to say how many at a time, and to turn
    it off entirely."""
    import run_tests
    assert run_tests._workers(["--serial"]) == 1
    assert run_tests._workers(["-j", "3"]) == 3
    assert run_tests._workers(["-j5"]) == 5
    assert run_tests._workers([]) >= 2
    assert run_tests._workers([]) <= 8, (
        "each worker can spawn a server of its own and the box has 1GB")


def test_the_summary_line_still_carries_the_count_and_the_skips():
    """That sentence is what the nightly quotes. Both numbers in it have
    to come from the run rather than from a constant."""
    assert 'f"All green: {total} tests across "' in RUNNER
    assert "len(files) - len(skipped)" in RUNNER


def test_the_run_gets_a_clean_environment_not_the_boxs():
    """REPRODUCED FROM THE DROPLET, 2026-08-23. Two files failed there
    and nowhere else, and both for the same reason: the code under test
    reads /etc/qellys/env, so the production config was in scope.

      test_stripe_plans  pops STRIPE_PRICE_YEARLY and asks billing to
                         refuse. billing._env() -> load_local_secrets()
                         read the file and put it straight back, so the
                         pop was undone by the call under test.
      test_backup_remote runs `backup.sh --check` with no remote and
                         expects failure; the script read the same file
                         and found the real rclone destination.

    The dangerous direction is not the false failure. It is that a suite
    inheriting a live STRIPE_SECRET_KEY is one careless test away from
    touching a real account.
    """
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    body = src[src.index("def main("):]
    body = body[:body.index("\ndef ")]
    assert 'startswith(("STRIPE_", "ODDS_API_KEY", "QB_"))' in body, (
        "the run inherits the box's secrets")
    assert 'env["QB_ENV_FILE"]' in body, (
        "nothing points the secrets loader away from /etc/qellys/env")
    # Order matters and is easy to get backwards: the sweep drops every
    # QB_* name, so setting QB_ENV_FILE before it would be pointless.
    assert body.index("env.pop(name)") < body.index('env["QB_ENV_FILE"]'), (
        "QB_ENV_FILE is set before the sweep that removes it")


def test_the_secrets_leak_the_clean_environment_closes():
    """THE MECHANISM, not another file's behaviour.

    This used to run test_stripe_plans.py and test_backup_remote.py under
    both environments and assert each FAILED with the box's config in
    scope. That is a test asserting a bug still exists, and it broke the
    moment somebody fixed one of them properly: 4c7ae48 gave
    test_backup_remote a tree of its own, so it stopped caring about the
    box, and this file went red for a repair.

    The thing worth guarding is the leak itself — that engine.secrets
    reads /etc/qellys/env into os.environ, so a value a test popped comes
    straight back — and that pointing QB_ENV_FILE elsewhere closes it.
    Checked directly, with no other test file involved.
    """
    import subprocess
    import tempfile

    probe = (
        "import os, sys; sys.path.insert(0, %r)\n"
        "from engine import secrets\n"
        "secrets.load_local_secrets()\n"
        "print(os.environ.get('STRIPE_PRICE_YEARLY', 'ABSENT'))\n" % (ROOT,))

    with tempfile.TemporaryDirectory() as td:
        boxenv = os.path.join(td, "env")
        with open(boxenv, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_PRICE_YEARLY=price_pretend\n")

        def run(env_file):
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("STRIPE_", "QB_"))}
            env["QB_ENV_FILE"] = env_file
            return subprocess.run([sys.executable, "-c", probe], env=env,
                                  capture_output=True, text=True,
                                  timeout=60).stdout.strip()

        assert run(boxenv) == "price_pretend", (
            "the loader no longer reads QB_ENV_FILE, so this test is not "
            "reproducing the leak it guards")
        assert run(os.path.join(td, "no-such-env")) == "ABSENT", (
            "pointing QB_ENV_FILE at nothing still leaked the box's config "
            "into the run")


def test_a_timeout_says_where_it_hung():
    """Three timeouts on the droplet reported nothing but the words
    TIMED OUT, and each one cost an afternoon of guessing which test was
    stuck. The runner was already capturing the partial stdout — Python
    just buffers stdout when it is not a tty, so every `ok <name>` the
    file had printed sat in an 8KB buffer and died with the process.

    `-u` on the child is the whole fix. The partial output survives the
    kill, and the last line names the test that finished before the one
    that hung."""
    import subprocess
    import tempfile
    import textwrap

    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    assert '"-u", path' in src, (
        "the child buffers its output, so a killed file reports nothing")

    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "test_hangs.py")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent("""
                import time
                def test_aaa(): pass
                def test_bbb_hangs(): time.sleep(120)
                if __name__ == "__main__":
                    for k, v in sorted(globals().items()):
                        if k.startswith("test_"):
                            v(); print("  ok  " + k)
            """))
        import run_tests
        was = run_tests.FILE_TIMEOUT
        run_tests.FILE_TIMEOUT = 3
        try:
            _, code, _, err, _ = run_tests._run_one(f, dict(os.environ))
        finally:
            run_tests.FILE_TIMEOUT = was
    assert code != 0
    assert "TIMED OUT" in err
    assert "test_aaa" in err, (
        "the timeout does not name the last test that finished:\n" + err)


def test_a_file_that_hangs_before_its_first_test_says_so_too():
    """"It printed nothing" and "it printed three oks" are different
    diagnoses — the first is an import or module-level work, and looking
    for a slow test would be looking in the wrong place entirely."""
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    body = src[src.index("def _run_one("):]
    body = body[:body.index("\ndef ")]
    assert "printed nothing at all" in body
    assert "an import, or module-level work" in body


def test_the_run_yields_the_cpu_to_the_live_site():
    """The suite runs ON the droplet, DURING a deploy, while the site is
    serving — and the droplet has one core. For ten minutes ~340 test
    processes competed on equal terms with the refresher and with Caddy
    answering subscribers.

    That is backwards twice: somebody is READING the site, and a heavy
    test file killed for losing the race reports a failure that is really
    a queue. test_ledger has failed three deploys running that way while
    passing in nine seconds anywhere else."""
    import run_tests
    cmd = run_tests._child("tests/test_db.py")
    assert "-u" in cmd, "the child still buffers its output"
    if run_tests._NICE:
        assert cmd[0] == run_tests._NICE and "10" in cmd, cmd
    else:
        assert cmd[0] == sys.executable, "no nice, so run it plainly"


def test_the_per_file_ceiling_follows_how_busy_the_box_is():
    """A fixed 900s was chosen when this ran serially on an idle machine.
    Measured contention, not a guessed constant: load over CPU count IS
    the queue. Floored so an idle box keeps the old number, capped so a
    genuinely hung file still dies inside the hour."""
    import run_tests
    real_load, real_cpu = os.getloadavg, os.cpu_count
    try:
        os.getloadavg = lambda: (0.2, 0.2, 0.2)
        os.cpu_count = lambda: 8
        assert run_tests._timeout() == run_tests.FILE_TIMEOUT, (
            "an idle box should keep the plain ceiling")
        os.getloadavg = lambda: (3.0, 3.0, 3.0)
        os.cpu_count = lambda: 1
        busy = run_tests._timeout()
        assert busy > run_tests.FILE_TIMEOUT, "a loaded box gets no more time"
        os.getloadavg = lambda: (200.0, 200.0, 200.0)
        assert run_tests._timeout() <= run_tests.FILE_TIMEOUT * 4, (
            "a hung file could outlive the deploy")
    finally:
        os.getloadavg, os.cpu_count = real_load, real_cpu


def test_a_timeout_reports_the_load_it_was_fighting():
    """"Timed out at 900s" and "timed out at 900s with a load of 14 on
    one cpu" are different findings, and only the second one points at
    the box instead of at the code."""
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    body = src[src.index("def _run_one("):]
    body = body[:body.index("\ndef ")]
    assert "getloadavg" in body and "cpu(s)" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
