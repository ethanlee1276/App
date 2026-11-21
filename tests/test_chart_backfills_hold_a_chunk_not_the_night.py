"""The baseball and basketball chart backfills hold a few games, never the night.

Ethan, 2026-10-14: "we are no longer showing players. There's no most
likely bets. There's no edge bets. There's no players showing up in the
search page." The page withholds every pick once a board is an hour old,
and search is the app answering — so the box had stopped finishing builds
and stopped answering, and the night's chart reads are where the memory
went. `engine/mlb/charts.ingest_games` read EVERY game of a 400-game
budget into memory before storing one (a parsed play-by-play is about
2 MB), and `engine/nba/shots.ingest_games` did the same with 300 games and
their box scores: each most of a gigabyte, in one child, inside the
1,600 MB the whole service shares with the web server and the builds.

What is pinned, offline:

  * each reads, folds and STORES a chunk before it reads the next, so no
    more than a chunk of games is ever held unread-into-the-table;
  * Python's own allocations while a 40-game run goes through stay near
    one chunk's worth, not forty games';
  * a chunk where nothing could be read ends the run (a host refusing us
    is not asked again forty times) and the rest are left for the next
    run; a chunk with one bad game goes on;
  * the chunk is small.

Run directly: `python3 tests/test_chart_backfills_hold_a_chunk_not_the_night.py`
"""
import importlib.util
import sys
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D  # noqa: E402
from engine.mlb import charts as MC  # noqa: E402
from engine.nba import shots as NS  # noqa: E402


def _fixtures(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MLB = _fixtures("test_mlb_hit_tracker_and_pitch_chart")
NBA = _fixtures("test_a_shot_chart_for_every_nba_player")


def _mlb_games(n):
    return [dict(MLB.GAME, game_pk=1000 + i, date=f"2026-09-{1 + i % 28:02d}") for i in range(n)]


def _nba_games(n):
    return [{"game_id": f"00225{i:05d}", "date": "2025-11-02"} for i in range(1, n + 1)]


def _held(events):
    """The most games read and not yet stored at any moment."""
    held = peak = 0
    for kind, _ in events:
        held += 1 if kind == "read" else -1
        peak = max(peak, held)
    return peak


def test_the_chunk_is_small():
    assert 1 <= MC.CHUNK <= 16 and 1 <= NS.CHUNK <= 16


def test_baseball_stores_each_chunk_before_reading_the_next():
    conn = D.connect(":memory:")
    events = []
    keep = D.upsert_mlb_pitches

    def fetch(pk):
        events.append(("read", pk))
        return MLB.PAYLOAD

    def write(c, rows):
        events.append(("stored", rows[0]["game_pk"] if rows else None))
        return keep(c, rows)
    D.upsert_mlb_pitches = write
    try:
        out = MC.ingest_games(conn, _mlb_games(20), fetch=fetch, workers=1)
    finally:
        D.upsert_mlb_pitches = keep
    assert out["games"] == 20 and out["failed"] == 0
    assert _held(events) == MC.CHUNK, events[:12]
    assert [k for k, _ in events[:MC.CHUNK + 1]] == ["read"] * MC.CHUNK + ["stored"]


def test_basketball_stores_each_chunk_before_reading_the_next():
    conn = D.connect(":memory:")
    events = []
    keep = D.upsert_nba_shots

    def read(gid):
        events.append(("read", gid))
        return NBA._pbp(gid), NBA._box(gid)

    def write(c, rows):
        events.append(("stored", rows[0]["game_id"] if rows else None))
        return keep(c, rows)
    D.upsert_nba_shots = write
    try:
        out = NS.ingest_games(conn, _nba_games(20), read=read, workers=1)
    finally:
        D.upsert_nba_shots = keep
    assert out["games"] == 20 and out["failed"] == 0
    assert _held(events) == NS.CHUNK, events[:12]


def test_a_run_holds_about_a_chunk_of_memory_not_the_whole_budget():
    # Each read hands back its own ~1 MB on top of the play-by-play — what a
    # real parsed feed costs, give or take. Forty games held at once would
    # be forty of them; a chunk at a time is about CHUNK.
    def fetch(pk):
        return dict(MLB.PAYLOAD, pad=[float(pk)] * 125_000)

    def peak_for(chunk):
        conn = D.connect(":memory:")
        tracemalloc.start()
        try:
            out = MC.ingest_games(conn, _mlb_games(40), fetch=fetch, workers=1, chunk=chunk)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert out["games"] == 40
        return peak / 1e6
    chunked, whole = peak_for(MC.CHUNK), peak_for(40)
    assert whole > 30, f"the forty-game read should have cost ~40 MB here, measured {whole:.1f}"
    assert chunked < whole / 2.5, f"a chunk at a time peaked at {chunked:.1f} MB against {whole:.1f} MB"


def test_a_chunk_with_nothing_read_ends_the_run_and_leaves_the_rest():
    conn = D.connect(":memory:")
    asked = []
    out = MC.ingest_games(conn, _mlb_games(30), fetch=lambda pk: asked.append(pk), workers=1)
    assert len(asked) == MC.CHUNK and out["games"] == 0 and out["failed"] == MC.CHUNK
    asked.clear()
    got = NS.ingest_games(D.connect(":memory:"), _nba_games(30),
                          read=lambda gid: asked.append(gid) or (None, None), workers=1)
    assert len(asked) == NS.CHUNK and got["games"] == 0 and got["failed"] == NS.CHUNK


def test_one_bad_game_in_a_chunk_does_not_end_the_run():
    conn = D.connect(":memory:")
    bad = 1003
    out = MC.ingest_games(conn, _mlb_games(20), fetch=lambda pk: None if pk == bad else MLB.PAYLOAD, workers=1)
    assert out["games"] == 19 and out["failed"] == 1


def test_the_season_backfill_counts_the_unread_as_left():
    from engine.mlb.sources import mlbstats

    def sched(start, end):
        return {"dates": [{"games": [{"gamePk": pk, "gameType": "R", "officialDate": "2026-09-01",
                                      "status": {"abstractGameState": "Final", "codedGameState": "F"},
                                      "teams": {"home": {"team": {"id": 147}}, "away": {"team": {"id": 116}}}}
                                     for pk in range(1, 31)]}]}
    keep = mlbstats.fetch_schedule
    mlbstats.fetch_schedule = sched
    try:
        got = MC.backfill(D.connect(":memory:"), 2026, "2026-10-12", budget=30, fetch=lambda pk: None)
    finally:
        mlbstats.fetch_schedule = keep
    assert got["games"] == 0 and got["failed"] == MC.CHUNK and got["left"] == 30 - MC.CHUNK


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
