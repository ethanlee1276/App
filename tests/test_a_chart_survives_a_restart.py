"""A chart survives a restart (step AGJ, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". Every update restarts the server, and a built chart was kept only in its memory: the first
reader of each chart after an update waited for its build (Jahmyr Gibbs's role chart 26.4 s on the live site, Juan
Soto's 32.8 s). Each chart kept is now also written beside the history file (cache/charts/), with his games' stamp
and when it was built (engine/charts._disk_save). One missing from memory is read from there (_disk_load):

  * while his games are the ones it was built from, it answers at once and a new one is built behind it, since an
    update may have changed the code that built it;
  * a box score of his since, and the reader waits for a fresh one, as with a kept answer (step AFQ);
  * a chart of his own games answers so up to a day after it was built; a matchup, which also reads his opponent's
    games, the hour it had;
  * the disk keeps a day and the newest DISK_CAP; a database in memory keeps nothing there; a disk that will not
    take one says so once and the chart answers from memory as before.

Offline. Run directly: `python3 tests/test_a_chart_survives_a_restart.py`
"""
import contextlib
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import charts as CH, db as D  # noqa: E402


def _history():
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    conn = D.connect(path)
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("nfl", 2026, "011", "g11", "Jahmyr Gibbs", "DET", "NYG", "RB", 1, "carries", 15)])
    conn.commit()
    conn.close()
    return d, path


def _restart():
    """What an update does to the kept answers: the memory is gone, the disk is not."""
    with CH._LOCK:
        CH._KEPT.clear()
        CH._BYTES[0] = 0


def _until(check, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


class _Builds:
    """A stand-in chart build that counts its builds; a rebuild waits on `gate` when asked to."""
    def __init__(self):
        self.n, self.gate, self.slow = 0, threading.Event(), False

    def __call__(self, conn, kind, sport, player, season=None, opp="", fam=""):
        self.n += 1
        if self.slow:
            self.gate.wait(5)
        return {"player": player, "kind": kind, "games": [{"id": self.n}]}


def _run(test):
    d, path = _history()
    real, builds = CH.answer, _Builds()
    CH.forget()
    CH.answer = builds
    try:
        test(d, path, builds)
    finally:
        builds.gate.set()
        _until(lambda: not CH._BUILDING)
        CH.answer = real
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_after_a_restart_the_kept_chart_answers_at_once_and_is_built_again_behind_it():
    def test(d, path, builds):
        first = CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        files = list((Path(d) / "cache" / "charts").glob("*.gz"))
        assert len(files) == 1 and builds.n == 1, files
        _restart()
        builds.slow = True                               # the build behind is slow; the reader must not wait for it
        took, t0 = [], time.time()
        again = CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs", took=took)
        assert again == first and time.time() - t0 < 1.0, "the one kept on disk, at once"
        assert [p for p, _ in took] == ["disk"], took
        assert _until(lambda: builds.n == 2), "and one build behind it: an update may have changed the code"
        assert CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs") == first, "one build at a time, the kept one meanwhile"
        builds.gate.set()
        assert _until(lambda: not CH._BUILDING)
        assert json.loads(CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs"))["games"] == [{"id": 2}], \
            "the new one replaced it"
        assert builds.n == 2, "kept fresh, it starts no other"
    _run(test)


def test_a_box_score_of_his_since_and_the_reader_waits_for_a_fresh_one():
    def test(d, path, builds):
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        conn = D.connect(path)
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES ('nfl', 2026, '012', 'g12', 'Jahmyr Gibbs', 'DET', 'GB', 'RB', 1, "
                     "'carries', 18)")
        conn.commit()
        conn.close()
        _restart()
        out = json.loads(CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs"))
        assert out["games"] == [{"id": 2}] and builds.n == 2 and not CH._BUILDING, \
            "a game just played is never answered with the chart from before it"
    _run(test)


def _age(d, secs):
    """The kept file rewritten as built `secs` ago."""
    (f,) = (Path(d) / "cache" / "charts").glob("*.gz")
    head, _, body = gzip.decompress(f.read_bytes()).partition(b"\n")
    meta = json.loads(head)
    meta["built"] = time.time() - secs
    f.write_bytes(gzip.compress(json.dumps(meta).encode() + b"\n" + body))
    return meta


def test_his_own_chart_answers_so_for_a_day_and_a_matchup_for_its_hour():
    def test(d, path, builds):
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        _age(d, 20 * 60 * 60)
        _restart()
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        assert _until(lambda: not CH._BUILDING) and builds.n == 2, "twenty hours: at once, built behind"
        _age(d, 25 * 60 * 60)
        _restart()
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        assert builds.n == 3 and not CH._BUILDING, "past the day: the reader waits for a fresh one"
    _run(test)
    key = (str(Path("x") / "history.db"), "matchup", "nfl", "Jahmyr Gibbs", None, "GB", "")
    assert CH._stale_max(key) == CH.ANSWER_STALE_MAX == 60 * 60, "a matchup reads his opponent's games too"
    assert CH._stale_max(("p", "role", "nfl", "Jahmyr Gibbs", None, "", "")) == CH.OWN_STALE_MAX == 24 * 60 * 60


def test_a_file_kept_for_another_chart_is_not_read_as_his():
    def test(d, path, builds):
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        meta = _age(d, 0)
        (f,) = (Path(d) / "cache" / "charts").glob("*.gz")
        head, _, body = gzip.decompress(f.read_bytes()).partition(b"\n")
        meta["key"][2] = "David Montgomery"
        f.write_bytes(gzip.compress(json.dumps(meta).encode() + b"\n" + body))
        _restart()
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        assert builds.n == 2 and not CH._BUILDING, "another key's file: built for the reader"
        f.write_bytes(b"not a kept chart")
        _restart()
        CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
        assert builds.n == 3, "an unreadable one: built for the reader"
    _run(test)


def test_the_disk_keeps_a_day_and_the_newest_few():
    where = Path(tempfile.mkdtemp())
    keep = CH.DISK_CAP
    try:
        CH.DISK_CAP = 3
        now = time.time()
        for i in range(5):
            f = where / f"{i}.gz"
            f.write_bytes(b"x")
            os.utime(f, (now - i * 60, now - i * 60))
        stale = where / "old.gz"
        stale.write_bytes(b"x")
        os.utime(stale, (now - 25 * 60 * 60,) * 2)
        crashed = where / "a.gz.1.2.tmp"
        crashed.write_bytes(b"x")
        os.utime(crashed, (now - 3600,) * 2)
        CH._disk_prune(str(where))
        assert sorted(p.name for p in where.iterdir()) == ["0.gz", "1.gz", "2.gz"]
    finally:
        CH.DISK_CAP = keep
        shutil.rmtree(where, ignore_errors=True)
    assert CH.DISK_CAP == 4000


def test_a_database_in_memory_keeps_nothing_on_disk_and_a_full_disk_says_so_once():
    assert CH._disk_file((":memory:", "role", "nfl", "X", None, "", "")) == ""
    assert CH._disk_file(("", "role", "nfl", "X", None, "", "")) == ""
    d, path = _history()
    real, builds = CH.answer, _Builds()
    CH.forget()
    CH.answer = builds
    CH._DISK_SAID[0] = False
    (Path(d) / "cache").write_text("a file where the folder would go")
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            a = CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs")
            CH.answer_json(path, "role", "nfl", "Amon-Ra St. Brown")
        assert CH.answer_json(path, "role", "nfl", "Jahmyr Gibbs") == a and builds.n == 2, "kept in memory as before"
        assert err.getvalue().count("a chart not kept on disk") == 1, err.getvalue()
    finally:
        CH.answer = real
        CH._DISK_SAID[0] = False
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_the_chart_endpoint_says_when_it_answered_off_the_disk():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    fn = src[src.index("    def _players_chart(self"):src.index("    def _players_fantasy(self")]
    assert "took=took" in fn and 'headers=[("Server-Timing", timing)] if timing else None' in fn
    src = (ROOT / "engine" / "charts.py").read_text(encoding="utf-8")
    assert 'took.append(("disk", (time.perf_counter() - t0) * 1000.0))' in src, "its part: disk;dur=…"


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
