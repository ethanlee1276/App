"""Savant's pitch-type board is asked for again, and a bad answer never
costs the last good copy.

Found 2026-10-14 beside the barrels and expected-stats fix (step 84):
`savant._arsenal_board` read the cached file whenever one existed and
called `fetch_text` only when there was none. `fetch_text` writes the
file under the same name, so after the first download Savant was never
asked again: every hitter's line against each pitch type (whiff, wOBA,
hard-hit) stayed what it was the day the file landed, all season.

The other two boards were fixed by reading through `fetch_text` always.
This one needed more care, because `fetch_text` writes whatever comes
back over the cached file, and two answers here are worse than the copy
they replace: a page that is not the CSV, and the header with no rows
(what the "ALL" form answers). Either would have cleared every hitter
until a good answer came, or sent the board back a season.

Pinned here, through the real `fetch_text` with Savant faked at urlopen:
  * a file younger than six hours is served without a request;
  * an older one is asked for again, and the new rows are read;
  * an error page or a header-only answer leaves the old rows in place,
    WITH THEIR OLD DOWNLOAD TIME, so the next build asks again;
  * Savant not answering serves the old copy;
  * a cached file that is not the CSV is cleared and fetched again;
  * a finished season is asked for weekly, not every six hours;
  * the barrels and expected-stats boards, refreshing since step 84, and
    the hit page's copies of them, keep their last good copy the same way;
  * the probe prints when each file was fetched.
"""
import io
import os
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.mlb.sources import savant as SV                      # noqa: E402
from engine.sources import fetch                                 # noqa: E402
from engine.sources.fetch import DataUnavailable                 # noqa: E402

HEAD = ('"last_name, first_name","player_id","team_name_alt","pitch_type","pitch_name",'
        '"run_value_per_100","run_value","pitches","pitch_usage","pa","ba","slg","woba",'
        '"whiff_percent","k_percent","put_away","est_ba","est_slg","est_woba","hard_hit_percent"\n')
JUDGE = '"Judge, Aaron",592450,NYY,SL,Slider,1,1,300,20,60,.250,.500,.380,30,25,20,.250,.500,.370,50\n'
SOTO = '"Soto, Juan",665742,NYM,CH,Changeup,1,1,200,15,40,.300,.550,.410,18,15,12,.290,.520,.400,48\n'
# The two boards the home-run model reads (refreshing since step 84), and
# the hit page's copies of them: the same guard covers all four.
BARRELS = ('"last_name, first_name","player_id","attempts","ev95percent","barrels","brl_percent"\n'
           '"Judge, Aaron",592450,450,62.2,90,20.0\n')
EXPECTED = ('"last_name, first_name","player_id","year","pa","bip","ba","est_ba","slg","est_slg",'
            '"woba","est_woba"\n"Judge, Aaron",592450,2026,700,450,.331,.318,.701,.689,.458,.451\n')
YEAR = date.today().year              # the season in play, whatever year the suite runs
HOUR = 3600


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _name(year=YEAR, suffix="_alt"):
    return f"savant_arsenal_batter_{year}{suffix}.csv"


def _seed(d, name, text, age):
    """A cached file downloaded ``age`` seconds ago; returns its mtime."""
    p = Path(d) / name
    p.write_text(text, encoding="utf-8")
    t = time.time() - age
    os.utime(p, (t, t))
    return t


def _run(d, serve, call=lambda: SV.load_arsenal(YEAR, "batter")):
    """``call()`` with the cache in ``d`` and Savant answering ``serve(url)``
    (text, or an exception to raise) through the real fetch_text. Returns
    (the board or the error, the URLs asked)."""
    asked = []

    def urlopen(req, timeout=0, **kw):
        url = getattr(req, "full_url", req)
        asked.append(url)
        out = serve(url)
        if isinstance(out, Exception):
            raise out
        return _Resp(out.encode("utf-8"))
    real = (fetch.CACHE_DIR, SV.CACHE_DIR, fetch.urllib.request.urlopen)
    fetch.CACHE_DIR = SV.CACHE_DIR = Path(d)
    fetch.urllib.request.urlopen = urlopen
    try:
        try:
            return call(), asked
        except DataUnavailable as exc:
            return exc, asked
    finally:
        fetch.CACHE_DIR, SV.CACHE_DIR, fetch.urllib.request.urlopen = real


def _hitters(board):
    return sorted(k for k in board if k != "_season") if isinstance(board, dict) else board


def _file(d, name=None):
    p = Path(d) / (name or _name())
    return p.read_text(encoding="utf-8"), p.stat().st_mtime


def _dir():
    return tempfile.mkdtemp(prefix="arsenal_")


def test_a_file_younger_than_six_hours_is_served_without_asking():
    d = _dir()
    try:
        t = _seed(d, _name(), HEAD + JUDGE, 1 * HOUR)
        board, asked = _run(d, lambda u: HEAD + SOTO)
        assert asked == [], asked
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR, board
        assert abs(_file(d)[1] - t) < 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_an_older_file_is_asked_for_again_and_the_new_rows_are_read():
    """The bug: this file was read forever after its first download."""
    d = _dir()
    try:
        _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        board, asked = _run(d, lambda u: HEAD + SOTO)
        assert len(asked) == 1 and "min=10" in asked[0], asked
        assert _hitters(board) == ["juan soto"], board
        text, mtime = _file(d)
        assert text == HEAD + SOTO and time.time() - mtime < 60, "the new copy is kept, dated now"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_an_error_page_never_costs_the_last_good_copy():
    d = _dir()
    try:
        t = _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        board, asked = _run(d, lambda u: "<html><body>Savant is down for maintenance</body></html>")
        assert len(asked) == 1, "the old copy has hitters: no other form, no other season"
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR, board
        text, mtime = _file(d)
        assert text == HEAD + JUDGE, "the error page did not replace the board"
        assert abs(mtime - t) < 1, "the old copy keeps its own download time"
        assert not list(Path(d).glob("*.tmp")), "nothing half-written is left behind"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_header_with_no_rows_never_costs_the_last_good_copy():
    """What the "ALL" form answers; a refresh that got it used to mean
    every hitter gone, or last season's board in place of this one."""
    d = _dir()
    try:
        t = _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        board, asked = _run(d, lambda u: HEAD)
        assert len(asked) == 1, asked
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR, board
        text, mtime = _file(d)
        assert text == HEAD + JUDGE and abs(mtime - t) < 1, "the old rows, dated as they were"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_copy_kept_is_asked_for_again_on_the_next_build():
    """Its age stays true, so a bad answer costs one request a build, not
    six hours of an old board; the next good answer replaces it."""
    d = _dir()
    try:
        _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        _run(d, lambda u: "<html>busy</html>")
        board, asked = _run(d, lambda u: HEAD + SOTO)
        assert len(asked) == 1, "asked again at once"
        assert _hitters(board) == ["juan soto"], board
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_savant_not_answering_serves_the_old_copy():
    d = _dir()
    try:
        t = _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        board, asked = _run(d, lambda u: OSError("connection refused"))
        assert len(asked) == 1, asked
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR, board
        text, mtime = _file(d)
        assert text == HEAD + JUDGE and abs(mtime - t) < 1, "the old copy, untouched"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_cached_file_that_is_not_the_csv_is_cleared_and_fetched_again():
    """Even inside the six hours: a poisoned copy is worse than none."""
    d = _dir()
    try:
        _seed(d, _name(), "<html>maintenance</html>", 1 * HOUR)
        board, asked = _run(d, lambda u: HEAD + JUDGE)
        assert len(asked) == 1, asked
        assert _hitters(board) == ["aaron judge"], board
        assert _file(d)[0] == HEAD + JUDGE
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_header_only_file_with_no_good_copy_still_moves_to_the_next_form():
    """The box's ALL-form file of 2026-09-26, older than the TTL: no rows
    to keep, so the answer is read and the next form is tried, as before."""
    d = _dir()
    try:
        _seed(d, _name(), HEAD, 7 * HOUR)
        board, asked = _run(d, lambda u: HEAD + (JUDGE if "min=q" in u else ""))
        assert [("min=10" in u, "min=q" in u) for u in asked] == [(True, False), (False, True)], asked
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR, board
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_finished_season_is_asked_for_weekly_not_every_six_hours():
    past = YEAR - 1
    assert SV._arsenal_ttl(YEAR) == SV.ARSENAL_TTL == 6 * HOUR
    assert SV._arsenal_ttl(past) == SV.PAST_SEASON_TTL == 7 * 24 * HOUR
    d = _dir()
    try:
        _seed(d, _name(past), HEAD + JUDGE, 2 * 24 * HOUR)
        board, asked = _run(d, lambda u: HEAD + SOTO, call=lambda: SV._arsenal_board(past, "batter"))
        assert asked == [] and _hitters(board) == ["aaron judge"], (asked, board)
        _seed(d, _name(past), HEAD + JUDGE, 8 * 24 * HOUR)
        board, asked = _run(d, lambda u: HEAD + SOTO, call=lambda: SV._arsenal_board(past, "batter"))
        assert len(asked) == 1 and f"year={past}" in asked[0] and _hitters(board) == ["juan soto"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_last_seasons_fallback_reads_through_the_same_door():
    """This season will not download and has no copy; last season's file,
    two days old, is served without a request."""
    d = _dir()
    try:
        _seed(d, _name(YEAR - 1), HEAD + JUDGE, 2 * 24 * HOUR)
        board, asked = _run(d, lambda u: OSError("connection refused"))
        assert all(f"year={YEAR}" in u for u in asked) and len(asked) == len(SV.ARSENAL_FORMS), asked
        assert _hitters(board) == ["aaron judge"] and board["_season"] == YEAR - 1, board
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_home_run_models_two_boards_keep_their_last_good_copy_too():
    """Barrels and expected stats have refreshed every six hours since
    step 84, through the same `fetch_text`: an error page or an empty
    body there used to read as a season with no hitters for six hours."""
    d = _dir()
    try:
        nb, ne = f"savant_barrels_batter_{YEAR}.csv", f"savant_expected_batter_{YEAR}.csv"
        tb, te = _seed(d, nb, BARRELS, 7 * HOUR), _seed(d, ne, EXPECTED, 7 * HOUR)
        brl, asked = _run(d, lambda u: "<html>busy</html>", call=lambda: SV.load_barrels(YEAR))
        exp, asked2 = _run(d, lambda u: "", call=lambda: SV.load_expected_stats(YEAR))
        assert len(asked) == len(asked2) == 1, (asked, asked2)
        assert brl["aaron judge"]["barrel_pct"] == 0.2 and exp["aaron judge"].xslg == 0.689
        for name, text, t in ((nb, BARRELS, tb), (ne, EXPECTED, te)):
            now_text, mtime = _file(d, name)
            assert now_text == text and abs(mtime - t) < 1, name
        brl, asked = _run(d, lambda u: BARRELS.replace(",20.0", ",25.0"), call=lambda: SV.load_barrels(YEAR))
        assert len(asked) == 1 and brl["aaron judge"]["barrel_pct"] == 0.25, "a good answer still lands"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_an_answer_the_csv_reader_cannot_read_is_no_answer():
    """One line past the CSV reader's 128 KB field limit (a minified error
    page can be one) used to raise out of the loader, taking the expected
    board and the barrels with it for that build."""
    huge = "<html>" + "x" * 200_000 + "</html>"
    d = _dir()
    try:
        nb = f"savant_barrels_batter_{YEAR}.csv"
        tb, ta = _seed(d, nb, BARRELS, 7 * HOUR), _seed(d, _name(), HEAD + JUDGE, 7 * HOUR)
        brl, _ = _run(d, lambda u: huge, call=lambda: SV.load_barrels(YEAR))
        assert brl["aaron judge"]["barrel_pct"] == 0.2 and _file(d, nb)[0] == BARRELS
        board, _ = _run(d, lambda u: HEAD + '"' + "x" * 200_000 + '"\n')
        assert _hitters(board) == ["aaron judge"] and _file(d)[0] == HEAD + JUDGE, board
        assert abs(_file(d, nb)[1] - tb) < 1 and abs(_file(d)[1] - ta) < 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_hit_pages_copies_keep_their_last_good_copy_too():
    d = _dir()
    try:
        ne, nb = SV.page_names(YEAR)
        te, tb = _seed(d, ne, EXPECTED, 21 * HOUR), _seed(d, nb, BARRELS, 21 * HOUR)
        got, asked = _run(d, lambda u: (EXPECTED.splitlines()[0] + "\n") if "expected" in u
                          else "<html>maintenance</html>", call=lambda: SV.fetch_page_boards(YEAR))
        assert len(asked) == 2 and got == {"expected": 1, "barrels": 1}, (asked, got)
        for name, text, t in ((ne, EXPECTED, te), (nb, BARRELS, tb)):
            now_text, mtime = _file(d, name)
            assert now_text == text and abs(mtime - t) < 1, "the page's as-of date stays the data's own"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_probe_prints_when_each_file_was_fetched():
    d = _dir()
    real = SV.CACHE_DIR
    try:
        now = time.time()
        _seed(d, _name(), HEAD + JUDGE + SOTO, 3 * HOUR)
        _seed(d, _name(suffix=""), HEAD, 30 * HOUR)
        SV.CACHE_DIR = Path(d)
        lines = SV.cache_report(YEAR, now=now)
    finally:
        SV.CACHE_DIR = real
        shutil.rmtree(d, ignore_errors=True)
    assert len(lines) == 2, lines
    alt = next(x for x in lines if x.startswith(_name()))
    assert "2 row(s), fetched " in alt and "(3.0 h ago)" in alt and "pitch_type" in alt, alt
    old = next(x for x in lines if x.startswith(_name(suffix="")))
    assert "0 row(s)" in old and "(30.0 h ago)" in old, old
    src = open(os.path.join(ROOT, "engine", "mlb", "sources", "savant.py"), encoding="utf-8").read()
    assert "for line in cache_report(year):" in src[src.index('if __name__ == "__main__":'):]


def test_the_loader_no_longer_reads_the_file_behind_fetch_texts_back():
    src = open(os.path.join(ROOT, "engine", "mlb", "sources", "savant.py"), encoding="utf-8").read()
    i = src.index("def _arsenal_board(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "fetch_text(url, name, ttl=ttl)" in body
    assert "local.read_text" not in body and "if text is None" not in body, \
        "the cached file is read through fetch_text, which asks again past the TTL"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
