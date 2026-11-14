"""The pitch-type board falls back a season when this one will not download.

The box's MLB build, 2026-09-26: "Pitch mix: 21 starter(s); arsenal
board: 0 hitter(s)". `savant.load_arsenal` fell back to last season only
when this season came back EMPTY; a season that would not download at all
raised straight past last season's good board, and the scan lost every
hitter's pitch-type read. Now a failed download tries the second URL form
(the page's own export), then last season, and raises only when neither
season has the board.

Then the probe on the box: the cached 2026 file was the right header with
NO ROWS. The "pitchType=ALL" form answers with an empty table, and the
August check had read only its first line. Every URL form is now tried
until one has hitters, the page's own export form first.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.mlb.sources import savant as SV                      # noqa: E402
from engine.sources.fetch import DataUnavailable                 # noqa: E402

HEAD = ('"last_name, first_name","player_id","team_name_alt","pitch_type","pitch_name",'
        '"run_value_per_100","run_value","pitches","pitch_usage","pa","ba","slg","woba",'
        '"whiff_percent","k_percent","put_away","est_ba","est_slg","est_woba","hard_hit_percent"\n')
ROW = '"Judge, Aaron",592450,NYY,SL,Slider,1,1,300,20,60,.250,.500,.380,30,25,20,.250,.500,.370,50\n'


def _run(serve):
    """load_arsenal(2026) with fetch_text answering from ``serve(url)``."""
    calls = []

    def fake(url, name, ttl=0, **kw):
        calls.append(url)
        out = serve(url)
        if isinstance(out, Exception):
            raise out
        return out
    old_fetch, old_dir = SV.fetch_text, SV.CACHE_DIR
    SV.fetch_text, SV.CACHE_DIR = fake, Path(tempfile.mkdtemp())
    try:
        try:
            return SV.load_arsenal(2026, "batter"), calls
        except DataUnavailable as exc:
            return exc, calls
    finally:
        SV.fetch_text, SV.CACHE_DIR = old_fetch, old_dir


def test_a_season_that_will_not_download_falls_back_to_last_season():
    board, calls = _run(lambda u: HEAD + ROW if "year=2025" in u else DataUnavailable("403"))
    assert isinstance(board, dict) and board.get("_season") == 2025, board
    assert "SL" in board[next(k for k in board if k != "_season")]
    assert sum("year=2026" in u for u in calls) == len(SV.ARSENAL_FORMS), "every form tried first"


def test_a_header_with_no_rows_tries_the_next_form():
    """The box's exact file: the header, no hitters, from the ALL form."""
    board, calls = _run(lambda u: HEAD + (ROW if "min=q" in u else ""))
    assert isinstance(board, dict) and board.get("_season") == 2026, board
    assert "min=10" in calls[0] and "min=q" in calls[1] and len(calls) == 2, calls


def test_the_pages_export_form_goes_first():
    board, calls = _run(lambda u: HEAD + ROW if "min=10" in u else "<html>maintenance</html>")
    assert isinstance(board, dict) and board.get("_season") == 2026, board
    assert len(calls) == 1 and "pitchType=&" in calls[0], calls
    assert "pitchType=ALL" in SV.ARSENAL_FORMS[-1][1], "the ALL form is the last resort"


def test_every_form_empty_in_both_seasons_is_empty_not_an_error():
    board, calls = _run(lambda u: HEAD)
    assert board == {} and len(calls) == 2 * len(SV.ARSENAL_FORMS), (board, calls)


def test_neither_season_says_why():
    err, _ = _run(lambda u: DataUnavailable("403 Forbidden"))
    assert isinstance(err, DataUnavailable) and "403" in str(err), err


def test_the_probe_reads_the_arsenal_board_too():
    src = open(os.path.join(ROOT, "engine", "mlb", "sources", "savant.py"), encoding="utf-8").read()
    main = src[src.index('if __name__ == "__main__":'):]
    assert '("pitch_arsenal_batter", lambda y: load_arsenal(y, "batter"))' in main


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
