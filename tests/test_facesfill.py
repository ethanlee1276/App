"""The faces backfill (facesfill.py).

Ethan, 2026-08-18, after re-running every ingest: WNBA photos sat at
171/183 before AND after, because ingest skips already-stored days — the
one design decision that makes backfills affordable also makes it
structurally unable to fill a face it missed the first time. This tool
fills from identifiers already in hand instead. What is defended:

  * NFL faces are TAKEN from the roster file, and they land in
    `player_assets` — the table the fantasy profile reads and that no
    NFL path had ever written.
  * Hoops fills ONLY the gap: a photo the box score handed us is a taken
    URL and must never be replaced by a constructed one.
  * MLB constructs from the person_id with the same pattern the prop
    board ships.
  * --dry-run writes nothing; a dead feed is a zero, not a crash.

Run directly: `python3 tests/test_facesfill.py`
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import facesfill
from engine import db


def _conn(td):
    return db.connect(os.path.join(td, "h.db"))


def test_nfl_faces_are_taken_from_the_roster_and_reach_player_assets():
    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        fake = {"P. Mahomes": "https://static.www.nfl.com/x/mahomes.png",
                "No Face": ""}
        with mock.patch("engine.sources.nflverse.headshot_map",
                        return_value=fake):
            n, before, after = facesfill.fill(conn, "nfl")
        assert (n, before, after) == (1, 0, 1), "only players WITH a url"
        row = conn.execute("SELECT headshot FROM player_assets WHERE "
                           "sport='nfl' AND player='P. Mahomes'").fetchone()
        assert row[0] == fake["P. Mahomes"], "the URL is taken verbatim"


def test_nfl_falls_back_a_season_when_this_years_roster_is_not_out():
    calls = []

    def fake_map(year):
        calls.append(year)
        return {} if len(calls) == 1 else {"Vet Guy": "https://x/v.png"}

    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        with mock.patch("engine.sources.nflverse.headshot_map", fake_map):
            n, _, after = facesfill.fill(conn, "nfl")
    assert len(calls) == 2 and calls[1] == calls[0] - 1
    assert n == 1 and after == 1


def test_mlb_faces_are_constructed_from_the_person_id():
    rosters = {"NYY": [{"name": "A. Judge", "person_id": 592450},
                       {"name": "No Id Guy", "person_id": 0}]}
    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        with mock.patch("engine.mlb.sources.mlbstats.fetch_active_rosters",
                        return_value=rosters):
            n, _, after = facesfill.fill(conn, "mlb")
        assert n == 1 and after == 1, "no person_id, no constructed guess"
        row = conn.execute("SELECT headshot, espn_id FROM player_assets "
                           "WHERE sport='mlb'").fetchone()
    assert "592450" in row[0] and row[1] == "592450"


def test_hoops_fills_only_the_gap_and_never_replaces_a_taken_url():
    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        db.upsert_player_assets(conn, [
            {"sport": "wnba", "player": "Has Face", "espn_id": "111",
             "headshot": "https://a.espncdn.com/taken.png", "seen": "d"},
            {"sport": "wnba", "player": "Gap Girl", "espn_id": "222",
             "headshot": "", "seen": "d"},
            {"sport": "wnba", "player": "No Id", "espn_id": "",
             "headshot": "", "seen": "d"},
        ])
        n, before, after = facesfill.fill(conn, "wnba")
        assert (n, before, after) == (1, 1, 2), \
            "one gap fillable; the id-less row cannot be helped"
        rows = dict(conn.execute("SELECT player, headshot FROM player_assets "
                                 "WHERE sport='wnba'").fetchall())
    assert rows["Has Face"] == "https://a.espncdn.com/taken.png", \
        "a taken URL survives the backfill"
    assert rows["Gap Girl"] == facesfill.ESPN_HEADSHOT.format(
        league="wnba", pid="222")
    assert rows["No Id"] == ""


def test_dry_run_counts_and_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        with mock.patch("engine.sources.nflverse.headshot_map",
                        return_value={"A": "https://x/a.png"}):
            n, _, after = facesfill.fill(conn, "nfl", dry_run=True)
        assert n == 1 and after == 0
        assert conn.execute("SELECT COUNT(*) FROM player_assets") \
                   .fetchone()[0] == 0


def test_a_dead_feed_is_a_zero_not_a_crash():
    with tempfile.TemporaryDirectory() as td:
        conn = _conn(td)
        with mock.patch("engine.mlb.sources.mlbstats.fetch_active_rosters",
                        side_effect=RuntimeError("league is down")):
            assert facesfill.fill(conn, "mlb") == (0, 0, 0)
        from engine.sources.fetch import DataUnavailable
        with mock.patch("engine.sources.nflverse.load_rosters",
                        side_effect=DataUnavailable("no file")):
            assert facesfill.fill(conn, "nfl") == (0, 0, 0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
