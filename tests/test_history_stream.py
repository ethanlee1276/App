"""Loading every sport's snapshot history to keep one day of it.

Found by `nfl_build --memtrace` on the droplet, 2026-09-03, on a machine
with 1 GB:

    stage         rss    peak    left resident    pushed peak
    odds           75    1324             -19          +1147
    pipeline       73    1602              -2           +278

1,425 MB of a 1,602 MB peak, in two stages whose RESIDENT size went down —
allocated and freed, invisible to anything watching RSS, and exactly what
the OOM killer acts on.

Both stages call `todays_rows(load_history())`. `load_history` reads the
whole file with `read_text()` (one string), `.splitlines()` (a second full
copy), then parses every line into a dict and keeps all of them — so that
`todays_rows` can discard everything before local midnight. The build did
it TWICE per run.

The tell had been in the log for weeks and nobody read it as one: an NFL
build printing ten lines of MLB line movement — Kyle Stowers total bases,
Salvador Perez, Chandler Simpson hits. The history it loaded was every
sport's, and the filter came afterwards.

`stream_history` yields one row at a time. `todays_rows` and the other
filters take any iterable, so it drops straight in and only the KEPT rows
are ever held. `load_history` is unchanged for the callers that genuinely
need the whole list — `closing_lines_by_date`, `booksharp.report`,
`stakecheck` — which is why this is a new function rather than a rewrite
of that one.

MEASURED, two fresh processes over a 400,900-row / 65 MB history shaped
like the droplet's (weeks of other days, today's handful at the end):

    load_history      900 rows kept    peak 481 MB
    stream_history    900 rows kept    peak  24 MB

Run directly: `python3 tests/test_history_stream.py`
"""

import datetime as _dt
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.linemoves import (load_history, stream_history,   # noqa: E402
                              todays_rows)


def _history(old=2000, today=40):
    """A file shaped like the real one: mostly older rows, today's last."""
    now = time.time()
    mid = _dt.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    path = os.path.join(tempfile.mkdtemp(), "line_history.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(old):
            fh.write(json.dumps({"ts": mid - 86400 * (1 + i % 30),
                                 "player": f"Old Guy {i}", "market": "total_bases",
                                 "line": 1.5, "book": "DraftKings"}) + "\n")
        for i in range(today):
            fh.write(json.dumps({"ts": now - 60, "player": f"Today Guy {i}",
                                 "market": "rush_yds", "line": 54.5,
                                 "book": "FanDuel"}) + "\n")
    return path, today


# --- it must keep exactly what the list kept --------------------------------
def test_the_two_readers_agree_row_for_row():
    """A cheaper reader that returns something different is not a fix."""
    path, _ = _history()
    assert list(stream_history(path)) == load_history(path)


def test_todays_rows_is_the_same_either_way():
    path, today = _history()
    a = todays_rows(load_history(path))
    b = todays_rows(stream_history(path))
    assert a == b
    assert len(b) == today, f"{len(b)} of {today} rows survived the day filter"


def test_a_missing_file_yields_nothing_rather_than_raising():
    assert list(stream_history("/nonexistent/line_history.jsonl")) == []
    assert load_history("/nonexistent/line_history.jsonl") == []


def test_a_corrupt_line_is_skipped_not_fatal():
    """Same tolerance the list reader has always had — a half-written last
    line from a killed build must not take the next build down."""
    path, today = _history(old=10, today=3)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"ts": 1, "player": "truncated\n')
        fh.write("\n")
    rows = list(stream_history(path))
    assert len(rows) == 13, len(rows)


def test_it_is_a_generator_and_not_a_list_in_disguise():
    """The whole point is that the file is never held. A `stream_history`
    that built a list first would pass every other test in this file."""
    assert inspect.isgeneratorfunction(stream_history), \
        "stream_history materialises the history it exists to avoid"
    # THE DOCSTRING NAMES read_text() TO EXPLAIN WHY IT IS NOT USED, so a
    # naive substring check matches the prose and fails on correct code.
    # Strip it first — the same rule the source-pinning tests elsewhere in
    # this suite already carry about comments.
    src = inspect.getsource(stream_history)
    body = src.split('"""')[-1]
    assert "read_text()" not in body, "it reads the whole file as one string"
    assert ".splitlines()" not in body, "it makes a second full copy"
    assert "yield" in body


# --- the measurement --------------------------------------------------------
def test_streaming_costs_a_fraction_of_the_peak():
    """THE NUMBER. Two fresh processes, because peak memory is monotonic
    within one — measuring both readers in the same interpreter would let
    the first one's allocation set a floor the second never has to cross,
    and would report a fix that is not there.

    Sized to stay quick in the suite. The droplet's real history is far
    larger and the ratio holds: the list reader's cost scales with the
    FILE, the stream reader's with the rows kept."""
    path, today = _history(old=120000, today=200)
    prog = (
        "import sys\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "from engine.linemoves import load_history, stream_history, todays_rows\n"
        "which, path = sys.argv[1], sys.argv[2]\n"
        "src = load_history(path) if which == 'list' else stream_history(path)\n"
        "kept = todays_rows(src)\n"
        "peak = [int(l.split()[1]) / 1024 for l in open('/proc/self/status')\n"
        "        if l.startswith('VmHWM:')][0]\n"
        "print(f'{len(kept)} {peak:.0f}')\n")

    def run(which):
        r = subprocess.run([sys.executable, "-c", prog, which, path],
                           capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr[-500:]
        kept, peak = r.stdout.split()
        return int(kept), float(peak)

    list_kept, list_peak = run("list")
    str_kept, str_peak = run("stream")
    assert list_kept == str_kept == today, (list_kept, str_kept, today)
    assert str_peak < list_peak * 0.5, (
        f"streaming peaked at {str_peak:.0f} MB against the list reader's "
        f"{list_peak:.0f} MB — it is not actually streaming")


# --- the callers ------------------------------------------------------------
def test_the_filtering_callers_stream():
    """These are the ones that load everything and keep almost none of it.
    nfl_build did it twice a run, which is where the gigabyte went.

    MLB WAS MISSED ON THE FIRST PASS and it is the worst case of the
    three: the sport with the most history — 494,453 harvested odds rows
    on the droplet — and the only one that plays every day, so it rebuilds
    every cycle all year. It was missed because the sweep that found the
    others was piped through `head` and cut at ten lines. Ethan, 2026-09-03:
    "figure out if that issue plauges any other sport and fix it."
    """
    for name, expected in (("nfl_build.py", 2), ("mlb_build.py", 1),
                           ("nba_build.py", 1)):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert src.count("todays_rows(stream_history())") == expected, \
            f"{name} no longer streams its history"
        assert "todays_rows(load_history())" not in src, \
            f"{name} materialises the whole history again"


def test_the_callers_that_need_the_whole_list_still_have_it():
    """`load_history` was kept, not replaced. These read every row and are
    NOT on the per-cycle path — a one-off report or a CLI — so there is no
    case for changing them and every reason not to."""
    for name in ("engine/booksharp.py", "stakecheck.py", "bookcheck.py",
                 "movecheck.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "load_history()" in src, f"{name} lost its full-history read"


def test_the_settle_path_streams_even_though_it_keeps_everything():
    """`engine/ledger.py`'s two snapshot readers run inside
    `settle_from_history`, which every board build calls at the end of
    every cycle — so they ARE on the per-cycle path even though their
    aggregate needs every row.

    Worth about 3 MB, and that is the honest figure: 536 against 533 on a
    400,000-row file. `closing_lines_by_date` groups with
    `grouped.setdefault(key, []).append(r)`, retaining every row, so the
    peak is set while grouping and removing the file-as-a-string
    underneath it does not lower a maximum reached later. Streaming drops
    two full copies and cannot be worse, so it stays — but the number is
    small and this test exists partly to stop anyone reading the change as
    a big one."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert src.count("closing_lines_by_date(stream_history())") == 1
    assert src.count("closing_odds_by_date(stream_history())") == 1
    assert "closing_lines_by_date(load_history())" not in src
    # And the reason the saving is small is recorded where the change is,
    # so nobody re-measures it from scratch to find out.
    i = src.index("closing_lines_by_date(stream_history())")
    assert "3 MB" in src[max(0, i - 1400):i], \
        "the measured saving is no longer written down beside the change"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
