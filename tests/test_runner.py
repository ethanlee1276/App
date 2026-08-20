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
    assert "if r.returncode == 0 and not why and n == 0:" in RUNNER, \
        "the green-zero guard is gone"
    i = RUNNER.index("if r.returncode == 0 and not why and n == 0:")
    block = RUNNER[i:i + 900]
    assert "failed.append(name)" in block, \
        "a countless file is reported but not actually failed"


def test_a_stated_skip_is_still_allowed_through():
    """The guard must not swallow the legitimate case it sits next to.
    `test_venue_ingest.py` bows out when Pillow is absent, says why, and
    has to keep reading as a skip rather than a failure."""
    i = RUNNER.index("if r.returncode == 0 and not why and n == 0:")
    after = RUNNER[i:]
    assert 'skipped.append(name)' in after, "the skip branch is unreachable"
    assert after.index("elif r.returncode == 0:") < after.index(
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

    keep, run_tests.ROOT = run_tests.ROOT, box
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = run_tests._run(dict(os.environ))
    finally:
        run_tests.ROOT = keep
        shutil.rmtree(box, ignore_errors=True)

    text = out.getvalue()
    assert rc == 1, f"a silent file did not fail the run:\n{text}"
    assert "test_silent.py" in text and "ran no tests" in text, text
    # …and the two honest files are untouched by the guard.
    assert "❌ test_counts.py" not in text, text
    assert "⏭️" in text and "test_bows_out.py" in text, \
        f"a stated skip was caught by the guard:\n{text}"


def test_the_summary_line_still_carries_the_count_and_the_skips():
    """That sentence is what the nightly quotes. Both numbers in it have
    to come from the run rather than from a constant."""
    assert 'f"All green: {total} tests across "' in RUNNER
    assert "len(files) - len(skipped)" in RUNNER


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
