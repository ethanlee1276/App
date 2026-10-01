"""A cache file damaged by a full disk heals itself, and a board that skips
its build says why.

Incident 2026-10-01 (a Thursday, game day). The droplet's disk filled
overnight. `fetch_text` wrote every download straight over its cache file,
so the nflverse schedule (`games.csv`) was left cut short. The next
readers trusted it for its whole 12-hour TTL. `_current_nfl_week` found no
upcoming game in the stub and returned None, and `refresh_nfl` kept the
old board without running a build. That took 0.9 seconds, wrote no note,
and the Status page said only "build failed". The NFL board sat ten hours
old on the morning of Thursday Night Football while every other league
rebuilt.

Pinned here:
  * a download is written beside its cache file and swapped in, so a full
    disk leaves the last good copy whole;
  * a schedule that reads as cut short is downloaded again;
  * refresh_nfl re-reads the schedule once before giving up on the week,
    and records why it skipped, which reaches the heartbeat;
  * the Status page shows a failed build's reason on a phone.
"""

import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import fetch, nflverse  # noqa: E402

HEAD = "game_id,season,game_type,week,gameday,away_team,home_team\n"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_full_disk_leaves_the_last_good_copy_whole():
    real_dir, real_open = fetch.CACHE_DIR, fetch.urllib.request.urlopen
    real_write = Path.write_text
    with tempfile.TemporaryDirectory() as d:
        fetch.CACHE_DIR = Path(d)
        good = HEAD + "2026_04_PIT_CLE,2026,REG,4,2026-10-01,PIT,CLE\n"
        (Path(d) / "games.csv").write_text(good)
        os.utime(Path(d) / "games.csv", (0, 0))                 # expired

        def full_disk(self, data, *a, **k):
            # A partial write, then the disk is full: what really happened.
            with open(self, "w", encoding="utf-8") as fh:
                fh.write(data[:10])
            raise OSError(28, "No space left on device")
        fetch.urllib.request.urlopen = lambda *a, **k: _Resp((good + good).encode())
        Path.write_text = full_disk
        try:
            text = fetch.fetch_text("https://example.test/games.csv", "games.csv", ttl=1)
        finally:
            Path.write_text = real_write
            fetch.urllib.request.urlopen = real_open
            fetch.CACHE_DIR = real_dir
        assert text == good + good, "the fresh download is still returned"
        assert (Path(d) / "games.csv").read_text() == good, "the old copy is untouched"
        assert not list(Path(d).glob("*.tmp")), "no half-written file is left behind"


def test_any_cached_csv_cut_mid_line_is_downloaded_again():
    calls = []
    cut = HEAD + "2026_04_PIT_CLE,2026,REG,4,2026-10-01,PI"
    whole = HEAD + "2026_04_PIT_CLE,2026,REG,4,2026-10-01,PIT,CLE\n"
    real = fetch.fetch_text
    fetch.fetch_text = lambda url, name, **kw: calls.append(kw.get("ttl")) or (
        cut if len(calls) == 1 else whole)
    fetch._CSV_REFETCHED.clear()
    try:
        rows = fetch.fetch_csv("https://example.test/x.csv", "x.csv")
        assert rows[-1]["home_team"] == "CLE" and calls == [None, 0], (rows, calls)
        calls.clear()                      # throttled: no second refetch within the hour
        fetch.fetch_text = lambda url, name, **kw: calls.append(kw.get("ttl")) or cut
        assert fetch.fetch_csv("https://example.test/x.csv", "x.csv")[-1]["home_team"] is None
        assert calls == [None]
    finally:
        fetch.fetch_text = real


def test_a_cut_short_schedule_is_downloaded_again():
    calls = []
    whole = [{"season": "2026", "week": "4", "gameday": "2026-10-01", "home_team": "CLE"}]
    cut = [{"season": "2026", "week": "4", "gameday": "2026-10-01", "home_team": None}]
    real = nflverse.fetch_csv

    def fake(url, name, **kw):
        calls.append(kw.get("ttl"))
        return cut if len(calls) == 1 else whole
    nflverse.fetch_csv = fake
    nflverse._SCHEDULE_REFETCHED[0] = False
    try:
        assert nflverse.load_schedules() == whole
        assert calls == [None, 0], calls
        # An empty file is cut short too.
        calls.clear()
        nflverse._SCHEDULE_REFETCHED[0] = False
        nflverse.fetch_csv = lambda url, name, **kw: (calls.append(kw.get("ttl")) or
                                                     ([] if len(calls) == 1 else whole))
        assert nflverse.load_schedules() == whole and calls == [None, 0]
    finally:
        nflverse.fetch_csv = real


def test_a_whole_schedule_is_not_downloaded_again():
    calls = []
    whole = [{"season": "2026", "week": "4", "gameday": "2026-10-01", "home_team": "CLE"}]
    real = nflverse.fetch_csv
    nflverse.fetch_csv = lambda url, name, **kw: calls.append(kw.get("ttl")) or whole
    nflverse._SCHEDULE_REFETCHED[0] = False
    try:
        assert nflverse.load_schedules() == whole and calls == [None]
    finally:
        nflverse.fetch_csv = real


def test_refresh_nfl_rereads_the_schedule_and_says_why_it_skipped():
    import launch
    seen = []
    real_week, real_load = launch._current_nfl_week, nflverse.load_schedules
    launch._current_nfl_week = lambda today=None, rows=None: seen.append(rows) or None
    nflverse.load_schedules = lambda force=False: [{"forced": force}]
    launch._SCHEDULE_RETRY_AT[0] = 0.0
    launch._LAST_BUILD_NOTE[0] = ""
    try:
        assert launch.refresh_nfl(quiet=True) is False
    finally:
        launch._current_nfl_week, nflverse.load_schedules = real_week, real_load
    assert seen == [None, [{"forced": True}]], seen
    assert "no current NFL week" in launch._LAST_BUILD_NOTE[0], launch._LAST_BUILD_NOTE[0]


def test_the_status_page_shows_why_on_a_phone():
    app = (ROOT / "web" / "js" / "app.js").read_text()
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    assert 'class="st-why"' in app
    i = css.index("@media (max-width: 640px) {\n  .cl-row")
    block = css[i:css.index("}\n}", i)]
    assert ".st-why" in block and "display: block" in block.split(".st-why")[1][:120]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fails += 1; print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
