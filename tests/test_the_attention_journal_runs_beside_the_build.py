"""The attention journal runs beside the build, not in its way
(engine/ideas BACKGROUND_JOURNALS, `finish_journals`; nfl_build.py and
cfb_build.py end by waiting for it).

The NFL build at 01:14 on 10 November, the box to itself: 74 seconds, 8.4
of them the attention journal, its whole budget (attention.BUILD_SECONDS)
spent waiting on Wikipedia for views that only the NEXT build reads, the
build waiting with it. What these hold:

  * `attach` starts the attention journal and returns while it is still
    running; the other journals run in line, as before;
  * `finish_journals` waits for it, says its seconds on the stage clock
    under the readings, prints a failure rather than raising, and is a
    no-op with nothing running;
  * the thread is not a daemon, so a build that ends without asking still
    waits for it, and the journal opens its own connection on that thread;
  * both builds end by waiting for it, whatever way `main` ends.

Run directly: `python3 tests/test_the_attention_journal_runs_beside_the_build.py`
"""
import contextlib
import inspect
import io
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import attention, gate, ideas, stageclock      # noqa: E402


class _Board:
    """ideas.attach on a scratch live directory, with stand-in journals."""

    def __init__(self, journals):
        self.journals = journals

    def __enter__(self):
        self.keep = (ideas.build, ideas._section_fns, ideas.directory, gate._full_dir_for,
                     dict(stageclock._STATE))
        where = tempfile.mkdtemp()
        names = list(self.journals)
        ideas.build = lambda sport, props, games, board: {
            "sport": sport, "sections": {n: {} for n in names}, "errors": {},
            "timings": {n: 0.0 for n in names}}
        ideas._section_fns = lambda name: (None, None, None, self.journals.get(name))
        ideas.directory = lambda: Path(where)
        gate._full_dir_for = lambda out: where
        self.out = str(Path(where) / "nfl.json")
        stageclock.start()
        return self

    def __exit__(self, *exc):
        ideas.finish_journals(timeout=5)
        (ideas.build, ideas._section_fns, ideas.directory, gate._full_dir_for, state) = self.keep
        stageclock._STATE.clear()
        stageclock._STATE.update(state)


def test_attach_returns_while_the_attention_journal_is_still_running():
    release, done, inline = threading.Event(), [], []

    def slow(sport, sec):
        release.wait(5)
        done.append(sport)

    with _Board({"attention": slow, "range": lambda s, sec: inline.append(s)}) as b:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            data = ideas.attach("nfl", [], [], {}, out=b.out)
            assert data and inline == ["nfl"], "the other journals run in line, as before"
            assert done == [], "attach waited for the attention journal"
            assert len(ideas._BACKGROUND) == 1 and ideas._BACKGROUND[0].thread.is_alive()
            release.set()
            took = ideas.finish_journals(timeout=5)
        said = buf.getvalue().splitlines()
    assert done == ["nfl"] and set(took) == {"attention"}, (done, took)
    parts = stageclock.parse_parts(said)["ideas readings"]
    assert list(parts)[-1] == "attention journal", parts
    assert "range journal" in parts, "the in-line journal still says its own part"
    assert not ideas._BACKGROUND


def test_a_failing_journal_is_said_and_never_raised():
    def broken(sport, sec):
        raise RuntimeError("Wikipedia said no")

    with _Board({"attention": broken}) as b:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ideas.attach("nfl", [], [], {}, out=b.out)
            took = ideas.finish_journals(timeout=5)
        text = buf.getvalue()
    assert "attention journal: RuntimeError: Wikipedia said no" in text, text
    assert set(took) == {"attention"}
    assert ideas.finish_journals() == {}, "nothing left running: nothing to wait for"


def test_the_thread_is_not_a_daemon_and_the_journal_opens_its_own_connection():
    job = ideas._Journal("attention", lambda s, sec: None, "nfl", {})
    assert job.thread.daemon is False, "a build that ends without asking still waits for it"
    assert ideas.BACKGROUND_JOURNALS == ("attention",)
    src = inspect.getsource(attention.journal)
    assert "own = conn is None" in src and "_db.connect()" in src, "a connection made on its own thread"


def test_both_builds_end_by_waiting_for_the_journals():
    for name in ("nfl_build.py", "cfb_build.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        tail = src[src.index('if __name__ == "__main__":'):]
        assert "try:\n        main()\n    finally:" in tail, name
        assert "finish_journals()" in tail, name


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
