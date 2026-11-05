"""The site keeps its own record of what broke inside it (engine/bugscan.
record_server, server.Handler._fail, server.BoundedHTTPServer.handle_error).

The bug scan's service section read the journal, and the box's weekly scan
runs as the site's own user, which cannot read it: every scan said "SITE
ERRORS IN THE JOURNAL: not readable here" (the public heartbeat, 5 November).
An error inside the site reached nobody but a person reading the journal
over ssh. What this holds:

  * a request that raised, a failure answered with a 500 and a thread that
    died each leave one line: the exception's type, the place in our own
    code, the kind, and the message with anything quoted, any long number,
    any address and any secret taken out; never the caller's address;
  * the record never raises, ignores a reader closing the page, and keeps
    to its size;
  * the scan groups it (busiest first, with its kinds), counts each distinct
    error as broken and prints it; the owner's desk shows the day's count
    and the commonest, and many in a day go to the owner's phones;
  * a 4xx answer is the reader's mistake, not the site's, and is not kept.

Run directly: `python3 tests/test_the_site_keeps_its_own_error_record.py`
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import bugscan as B                                  # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


class _Log:
    """Point the record at a temporary file for the test."""
    def __enter__(self):
        self.keep = B.SERVER_LOG
        self.path = os.path.join(tempfile.mkdtemp(), "logs", "server_errors.jsonl")
        B.SERVER_LOG = self.path
        return self

    def rows(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                return [json.loads(ln) for ln in fh if ln.strip()]
        except OSError:
            return []

    def __exit__(self, *exc):
        B.SERVER_LOG = self.keep


def _engine_error():
    """An exception raised inside our own code (engine/deepfit)."""
    from engine import deepfit
    try:
        deepfit._write_state("/proc/no-such-dir/state.json", {})
    except OSError as exc:
        return exc
    raise AssertionError("expected an OSError")


def test_a_message_is_kept_without_anything_a_reader_typed():
    got = B.scrub_message("KeyError: 'Their Handle' for 12345678 by someone@example.com via ?token=abc&x=1 \"q\"")
    assert "Their Handle" not in got and "12345678" not in got and "someone@example.com" not in got
    assert "abc" not in got and '"q"' not in got
    assert got.startswith("KeyError: '…' for … by …@… via ?token=…&x=1"), got


def test_each_error_leaves_its_type_our_code_and_its_kind():
    exc = _engine_error()
    with _Log() as log:
        assert B.record_server("request", exc, now=1000) is True
        (row,) = log.rows()
    assert row["kind"] == "request" and row["type"] in ("FileNotFoundError", "PermissionError", "OSError")
    assert row["src"].startswith("engine/deepfit.py:") and row["src"].endswith(" in _write_state"), row
    assert row["at"] == 1000 and "/proc/no-such-dir" not in row["src"]


def test_the_record_never_raises_and_ignores_a_reader_leaving():
    with _Log() as log:
        assert B.record_server("request", None) is False
        assert B.record_server("request", BrokenPipeError()) is False
        assert B.record_server("request", ConnectionResetError()) is False
        B.SERVER_LOG = "/proc/no-such-dir/x.jsonl"
        assert B.record_server("fail", ValueError("x")) is False, "an unwritable log is a False, not a crash"
        B.SERVER_LOG = log.path
        assert log.rows() == []


def test_it_keeps_to_its_size():
    with _Log() as log:
        keep = B.SERVER_LOG_MAX
        B.SERVER_LOG_MAX = 20_000
        try:
            for i in range(3000):
                B.record_server("fail", ValueError(f"row {i}"), now=1000 + i)
        finally:
            B.SERVER_LOG_MAX = keep
        rows = log.rows()
    assert os.path.getsize(log.path) <= 20_000 + 400 and rows, len(rows)
    assert rows[-1]["m"] == "row 2999", "the newest are kept"


def test_the_scan_groups_counts_and_prints_them():
    now = time.time()
    with _Log():
        for i in range(3):
            B.record_server("request", KeyError("a"), now=now - 60 * i)
        B.record_server("thread", KeyError("a"), now=now - 30)
        B.record_server("fail", ValueError("b"), now=now - 10)
        B.record_server("fail", ValueError("old"), now=now - 3 * 86400)
        own = B.server_errors(24, now=now)
        got = B.scan(24, now=now, journal=lambda hours: None)
    assert [(g["type"], g["n"]) for g in own] == [("KeyError", 4), ("ValueError", 1)], own
    assert dict(own[0]["kinds"]) == {"request": 3, "thread": 1}
    assert got["server"] and got["broken"] >= 2
    text = "\n".join(B.report(got))
    assert "ERRORS IN THE SITE'S OWN RECORD: 5 report(s), 2 distinct" in text, text[-600:]
    assert "KeyError: '…'" in text and "request ×3, thread ×1" in text


def test_a_dead_thread_is_recorded_and_the_usual_traceback_still_prints():
    seen = []
    prior_seen = []
    keep_hook, keep_flag = threading.excepthook, list(B._HOOKED)
    threading.excepthook = lambda args: prior_seen.append(args.exc_type)
    B._HOOKED.clear()
    try:
        B.install_thread_hook(record=lambda kind, exc, where: seen.append((kind, type(exc).__name__, where)))
        B.install_thread_hook(record=lambda *a: seen.append("twice"))
        t = threading.Thread(target=lambda: (_ for _ in ()).throw(RuntimeError("boom")), name="board-nba")
        t.start()
        t.join()
    finally:
        threading.excepthook = keep_hook
        B._HOOKED[:] = keep_flag
    assert seen == [("thread", "RuntimeError", "board-nba")], seen
    assert prior_seen == [RuntimeError], "the usual hook still runs"


class _Sent:
    def __init__(self):
        self.sent = []

    def _send(self, status, body, ext):
        self.sent.append(status)


def test_a_500_is_kept_and_a_readers_mistake_is_not():
    import server
    with _Log() as log, redirect_stderr(io.StringIO()):
        h = _Sent()
        server.Handler._fail(h, 500, "The engine could not run that slate.", _engine_error(), "run slate")
        server.Handler._fail(h, 400, "Bad request.", ValueError("their 'input'"), "parse")
        rows = log.rows()
    assert h.sent == [500, 400]
    assert [(r["kind"], r["where"]) for r in rows] == [("fail", "run slate")], rows


def test_a_request_that_raised_is_kept_without_the_callers_address():
    import server
    srv = server.BoundedHTTPServer.__new__(server.BoundedHTTPServer)
    with _Log() as log, redirect_stderr(io.StringIO()) as err:
        try:
            raise _engine_error()
        except OSError:
            srv.handle_error(None, ("203.0.113.9", 51515))
        rows = log.rows()
        raw = open(log.path, encoding="utf-8").read()
    assert len(rows) == 1 and rows[0]["kind"] == "request" and rows[0]["src"].startswith("engine/deepfit.py:")
    assert "203.0.113.9" not in raw, "never the caller"
    assert "Traceback" in err.getvalue(), "the journal still gets socketserver's traceback"
    src = READ("server.py")
    assert "bugscan.install_thread_hook()" in src, "the server installs the thread hook"


def test_the_desk_shows_the_count_and_many_in_a_day_reach_the_owner():
    from engine import ownerdesk as OD, owneralerts as OA
    now = time.time()
    with _Log():
        for i in range(30):
            B.record_server("request", KeyError("a"), now=now - i)
        h = OD.health(now)
    assert h["server_errors"] == 30 and h["server_kinds"] == 1, {k: h.get(k) for k in ("server_errors", "server_kinds")}
    assert h["server_top"][0]["m"] == "KeyError: '…'" and h["server_top"][0]["n"] == 30
    got = [p for p in OA.problems(h, now=now) if p["key"] == "server"]
    assert got and got[0]["title"] == "30 errors inside the site in a day", got
    quiet = dict(h, server_errors=3)
    assert not [p for p in OA.problems(quiet, now=now) if p["key"] == "server"]
    js = READ("web", "js", "owner.js")
    assert '"Server errors, 24 h"' in js and "Inside the site, the commonest:" in js


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
