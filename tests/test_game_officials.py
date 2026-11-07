"""Who refereed each game: read off the summary the basketball ingest already has, kept, never fetched twice.

Ethan, 2026-10-17: "new ways of gathering data". engine/officials keeps the
NBA's and WNBA's crews so a crew's effect can be measured against the
closing total once a season of closes is stored (refcheck.py found none
for the NFL). Pinned here: either spelling of a name is read, a nameless or
repeated entry is skipped, a summary with no officials is an empty answer;
a crew is stored once per game; the backfill reads only the cache and
never fetches; and the ingest stores the crew from the summary it holds.

Offline: a temporary history database and cache folder.

Run directly: `python3 tests/test_game_officials.py`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, officials  # noqa: E402

SUMMARY = {"gameInfo": {"venue": {"fullName": "TD Garden"}, "officials": [
    {"fullName": "Scott Foster", "displayName": "Scott Foster", "position": {"name": "Referee", "displayName": "Crew Chief"}, "order": 1},
    {"displayName": "Tony Brothers", "position": {"name": "Referee"}, "order": 2},
    {"fullName": "", "position": {"name": "Umpire"}},
    {"fullName": "Tony Brothers"},
    {"fullName": "Natalie Sago", "position": "Umpire"}]}}


def test_the_crew_is_read_off_the_summary():
    got = officials.parse(SUMMARY)
    assert [o["name"] for o in got] == ["Scott Foster", "Tony Brothers", "Natalie Sago"]
    assert got[0]["role"] == "Crew Chief" and got[2]["role"] == "Umpire"
    assert officials.parse({"gameInfo": {"venue": {}}}) == [] and officials.parse(None) == []


def test_a_crew_is_stored_once_per_game_and_the_backfill_reads_only_the_cache():
    t = Path(tempfile.mkdtemp())
    H = db.connect(t / "h.db")
    H.executemany("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES ('nba', 2026, ?, ?, ?, 'BOS', 'CHA', 110, 100)",
                  [("2026-10-21", "401", "2026-10-21"), ("2026-10-22", "402", "2026-10-22")])
    H.commit()
    assert officials.store(H, "nba", "401", "2026-10-21", officials.parse(SUMMARY)) == 3
    officials.store(H, "nba", "401", "2026-10-21", officials.parse(SUMMARY))
    assert officials.crew(H, "nba", "401") == ["Scott Foster", "Tony Brothers", "Natalie Sago"]
    cache = t / "cache"
    cache.mkdir()
    (cache / "espn_nba_box_402.json").write_text(json.dumps(SUMMARY))
    r = officials.backfill(H, "nba", cache_dir=cache)
    assert (r["games"], r["todo"], r["not_cached"]) == (1, 1, 0), r
    assert officials.backfill(H, "nba", cache_dir=cache)["todo"] == 0, "a stored crew is not read again"
    assert officials.summary(H, "nba")["games"] == 2


def test_the_ingest_keeps_the_crew_from_the_summary_it_holds():
    src = (ROOT / "engine" / "sources" / "espnhoops.py").read_text(encoding="utf-8")
    i = src.index("summary = fetch_summary(g[\"game_id\"], league=league)")
    block = src[i:i + 900]
    assert "_officials.store(conn, league, g[\"game_id\"], date, _officials.parse(summary))" in block
    assert "officials" in block and "skipped" in block, "a bad crew costs only its own line, never the game"


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
