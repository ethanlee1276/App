"""Every answer says how long it took and how much of that was its own work (step AFL, 25 November 2026).

Amon-Ra St. Brown's page answered in 4.4 s once and 0.2 s a minute later, and another NFL player's in 2.8 s where
twelve others took 0.2 to 0.6 s. The build loop's settle and chores, the watchers and every reader's request
share the server's one process, and one Python thread runs at a time, so a slow answer is either slow work
or a wait for its turn. Every API answer now carries a Server-Timing line with both: `all`, its milliseconds since
the request was read, and `cpu`, the request thread's own processor time in them. A page or a file has none; a
handler's own parts (the team page's, the player page's) ride on their own line beside it.

Offline. Run directly: `python3 tests/test_every_answer_says_where_its_time_went.py`
"""
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _handler(path, clock=True):
    import server
    h = object.__new__(server.Handler)
    sent = []
    h.send_response = lambda code, *a: sent.append(("status", code))
    h.send_header = lambda k, v: sent.append((k, v))
    h.end_headers = lambda: None

    class _Out:
        def write(self, b):
            sent.append(("body", b))
    h.wfile = _Out()
    h._is_https = lambda: False
    h.path = path
    if clock:
        h._clock = (time.perf_counter() - 0.05, time.thread_time(), time.process_time())
    return h, sent


def _timing(sent):
    return [v for k, v in sent if k == "Server-Timing"]


def test_an_api_answer_says_all_and_cpu():
    h, sent = _handler("/api/players/page?sport=nfl&player=Sam+Hands")
    h._send(200, b"{}", ".json", headers=[("Server-Timing", "kept;dur=0")])
    got = _timing(sent)
    assert got[0] == "kept;dur=0", "the handler's own line first"
    m = re.fullmatch(r"all;dur=(\d+), cpu;dur=(\d+), proc;dur=(\d+)", got[1])
    assert m and int(m.group(1)) >= 50, got
    h, sent = _handler("/api/board/recommendations_picks.json")
    h._send(200, b"{}", ".json")
    assert len(_timing(sent)) == 1 and _timing(sent)[0].startswith("all;dur=")


def test_proc_is_the_whole_process_so_a_wait_behind_other_work_shows():
    """Step AGK: a request that waits while another thread works reads `proc` near `all` and its own `cpu` near 0;
    one that waits on nothing busy (the disk, the network: here a sleep) reads all three apart."""
    import threading
    h, sent = _handler("/api/players/chart?kind=role&sport=nhl&player=Nikita+Kucherov")
    h._clock = (time.perf_counter(), time.thread_time(), time.process_time())
    stop = time.perf_counter() + 0.3
    busy = threading.Thread(target=lambda: [None for _ in iter(lambda: time.perf_counter() < stop, False)])
    busy.start()
    busy.join()
    h._send(200, b"{}", ".json")
    m = re.fullmatch(r"all;dur=(\d+), cpu;dur=(\d+), proc;dur=(\d+)", _timing(sent)[0])
    assert m, _timing(sent)
    all_ms, cpu_ms, proc_ms = (int(x) for x in m.groups())
    assert all_ms >= 280 and proc_ms >= 90 and cpu_ms < 100, (all_ms, cpu_ms, proc_ms)
    h, sent = _handler("/api/players/chart?kind=role&sport=nhl&player=Nikita+Kucherov")
    h._clock = (time.perf_counter(), time.thread_time(), time.process_time())
    time.sleep(0.3)
    h._send(200, b"{}", ".json")
    all_ms, cpu_ms, proc_ms = (int(x) for x in re.fullmatch(r"all;dur=(\d+), cpu;dur=(\d+), proc;dur=(\d+)",
                                                            _timing(sent)[0]).groups())
    assert all_ms >= 280 and proc_ms < 50, (all_ms, cpu_ms, proc_ms)
    # A handler started before this step (two numbers in its clock) says the two it has.
    h, sent = _handler("/api/x")
    h._clock = (time.perf_counter(), time.thread_time())
    h._send(200, b"{}", ".json")
    assert re.fullmatch(r"all;dur=\d+, cpu;dur=\d+", _timing(sent)[0])


def test_a_page_a_file_and_a_handler_with_no_request_say_nothing():
    h, sent = _handler("/index.html")
    h._send(200, b"x", ".html")
    assert not _timing(sent)
    h, sent = _handler("/api/players/page", clock=False)
    h._send(200, b"{}", ".json")
    assert not _timing(sent) and ("body", b"{}") in sent


def test_both_entries_start_the_clock():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    for verb in ("GET", "POST"):
        i = src.index(f"    def do_{verb}(self):\n")
        assert src[i:i + 200].split("\n")[1].strip().startswith(
            "self._clock = (time.perf_counter(), time.thread_time(), time.process_time())"), verb
    assert 'took.append(("build", (time.perf_counter() - t0) * 1000.0))' in src, "the page's own total is its build"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
