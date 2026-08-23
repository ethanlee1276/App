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
    i = RUNNER.index("except subprocess.TimeoutExpired")
    assert "code = 1" in RUNNER[i:i + 400], "a timed-out file still passes"


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


def test_the_two_files_that_failed_pass_under_that_environment():
    """The end-to-end version: hand them the box's config and they fail,
    hand them the runner's and they pass. Written this way because the
    check above only reads run_tests.py, and this bug was invisible in
    every file's own source."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        boxenv = os.path.join(td, "env")
        with open(boxenv, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_PRICE_YEARLY=price_pretend\n"
                     "QB_BACKUP_REMOTE=pretend:remote\n")
        dirty = dict(os.environ, QB_ENV_FILE=boxenv)
        clean = dict(os.environ, TMPDIR=td, TEMP=td, TMP=td)
        for name in list(clean):
            if name.startswith(("STRIPE_", "ODDS_API_KEY", "QB_")):
                clean.pop(name)
        clean["QB_ENV_FILE"] = os.path.join(td, "no-such-env")
        for name in ("test_stripe_plans.py", "test_backup_remote.py"):
            f = os.path.join(ROOT, "tests", name)
            bad = subprocess.run([sys.executable, f], capture_output=True,
                                 text=True, env=dirty, timeout=300)
            assert bad.returncode != 0, (
                f"{name} passed with the box's config in scope, so this "
                f"test no longer reproduces the thing it is guarding")
            ok = subprocess.run([sys.executable, f], capture_output=True,
                                text=True, env=clean, timeout=300)
            assert ok.returncode == 0, (
                f"{name} still fails under the runner's environment:\n"
                + ok.stdout[-600:] + ok.stderr[-600:])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
