"""The depth charts are parsed once per file, not on every build
(engine/sources/depthcharts._slim_kept, load_depth_charts).

The season's depth-chart file is every team's every position group, every
day since March (492,320 rows and 47 MB in September, longer each day), and
the NFL build streamed it twice on every build to keep the newest three
weeks — its depth-chart stage ran 11 to 14 seconds of every Sunday build on
8 November — though the file is refetched only when its cache expires.
What these hold:

  * the kept rows are exactly what parsing the file gives, in order;
  * a build off the same file does not parse it again;
  * any byte of the file changed — even with the size kept — parses again;
  * a torn copy of the kept rows is parsed again and written whole;
  * the fitters' read of every row (no window) keeps nothing;
  * the loader reaches the kept rows through the fetch layer, as before.

Run directly: `python3 tests/test_the_depth_charts_are_parsed_once_per_file.py`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import depthcharts as D                         # noqa: E402

HEAD = "dt,season,team,player_name,pos_abb,pos_rank,pos_name\n"


def _csv(days=40, teams=("DET", "MIN", "GB"), tweak=""):
    lines = [HEAD]
    for d in range(days):
        day = f"2026-{9 + (d + 1) // 31:02d}-{(d % 30) + 1:02d}T12:00:00Z"
        for t in teams:
            for k, pos in enumerate(("QB", "RB", "WR", "WR", "TE")):
                name = f"{t} {pos} {k}" + (tweak if (d, t, k) == (days - 1, teams[0], 0) else "")
                lines.append(f"{day},2026,{t},{name},{pos},{1 + k % 2},{pos} name\n")
    return "".join(lines)


def _file(text):
    p = Path(tempfile.mkdtemp()) / "depth_charts_2026.csv"
    p.write_text(text, encoding="utf-8")
    return p


class _Counted:
    def __enter__(self):
        self.keep, self.calls = D._slim, []
        calls, keep = self.calls, self.keep
        D._slim = lambda open_rows, keep_days: calls.append(keep_days) or keep(open_rows, keep_days)
        return self.calls

    def __exit__(self, *exc):
        D._slim = self.keep


def test_the_kept_rows_are_what_the_file_parses_to():
    p = _file(_csv())
    want = D._slim(lambda: open(p, encoding="utf-8", newline=""), D.KEEP_DAYS)
    first = D._slim_kept(p, D.KEEP_DAYS)
    again = D._slim_kept(p, D.KEEP_DAYS)
    assert first == want and again == want, "the same rows, in the same order"
    assert list(again[0]) == list(want[0]), "and the same columns in the same order"
    # The newest day in the file is 2026-10-10; three weeks back is 09-19.
    assert want and all(r["dt"][:10] >= "2026-09-19" for r in want), "the window still applies"
    assert min(r["dt"][:10] for r in want) == "2026-09-19" and len(want) < 40 * 15, \
        "and the days before it are left out"


def test_the_same_file_is_not_parsed_again():
    p = _file(_csv())
    with _Counted() as calls:
        D._slim_kept(p, D.KEEP_DAYS)
        D._slim_kept(p, D.KEEP_DAYS)
        D._slim_kept(p, D.KEEP_DAYS)
    assert calls == [D.KEEP_DAYS], f"parsed {len(calls)} times"


def test_a_changed_byte_parses_again_even_at_the_same_size():
    p = _file(_csv(tweak="a"))
    before = D._slim_kept(p, D.KEEP_DAYS)
    size = p.stat().st_size
    p.write_text(_csv(tweak="b"), encoding="utf-8")
    assert p.stat().st_size == size
    with _Counted() as calls:
        after = D._slim_kept(p, D.KEEP_DAYS)
    assert calls == [D.KEEP_DAYS]
    assert after != before and any(r["player_name"].endswith("b") for r in after)


def test_a_torn_copy_is_parsed_again_and_written_whole():
    p = _file(_csv())
    rows = D._slim_kept(p, D.KEEP_DAYS)
    side = p.with_name(f"{p.name}.slim{D.KEEP_DAYS}.json")
    side.write_text('{"key": "x", "rows": [', encoding="utf-8")
    with _Counted() as calls:
        assert D._slim_kept(p, D.KEEP_DAYS) == rows
        assert D._slim_kept(p, D.KEEP_DAYS) == rows
    assert calls == [D.KEEP_DAYS], "parsed once, then kept again"


def test_the_whole_season_read_keeps_nothing():
    p = _file(_csv())
    with _Counted() as calls:
        a = D._slim_kept(p, None)
        b = D._slim_kept(p, None)
    assert a == b and calls == [None, None]
    assert not list(p.parent.glob("*.slim*.json")), "no copy as big as the file"


def test_the_loader_reads_the_kept_rows_through_the_fetch_layer():
    p = _file(_csv())
    keep = (D.CACHE_DIR, D.fetch_text)
    asked = []
    D.CACHE_DIR = p.parent
    D.fetch_text = lambda url, name, *a, **k: asked.append(name) or ""
    try:
        with _Counted() as calls:
            a = D.load_depth_charts(2026)
            b = D.load_depth_charts(2026)
    finally:
        D.CACHE_DIR, D.fetch_text = keep
    assert asked == [p.name, p.name], "every read still asks the fetch layer"
    assert a == b and calls == [D.KEEP_DAYS]


def test_the_nfl_builds_depth_chart_stage_names_its_parts_in_order():
    """5 seconds at 09:02 on 9 November and 14 at 09:24, with the parse
    kept: the stage now says which of its four jobs took them."""
    src = (ROOT / "nfl_build.py").read_text()
    body = src[src.index('_mem("injuries + resets", args.memtrace)'):src.index('_mem("depth charts", args.memtrace)')]
    laps = [f'_lap("depth charts", "{p}", _dt0)' for p in ("load", "injury roles", "qb watch", "team charts")]
    at = [body.index(lp) for lp in laps]
    assert at == sorted(at), at
    assert body.index("load_depth_charts(args.season)") < at[0] < body.index("refine_injury_roles(all_inj")


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
