"""The NBA reads ESPN when the league's own feed says no.

Found 2026-10-14 on the box, six days before opening night: the NBA board
read "unreachable" with no games, and the league's CDN answered the box
403 Forbidden for every file and every User-Agent tried —

    403  cdn.nba.com …/staticData/scheduleLeagueV2.json
    403  cdn.nba.com …/liveData/playbyplay/playbyplay_0022501230.json
    200  site.api.espn.com …/basketball/nba/scoreboard

— while ESPN, which the history backfill and the WNBA have ridden all
along, answered 200. Pinned here:

  * the board's schedule (`nba_build`) and the nightly results and the
    settle pass (`maintenance`) read ESPN through `sources/nbaespn`, and
    nothing on those paths imports the CDN's schedule any more;
  * the clubs come out in the league's own codes (GSW, NYK, NOP, SAS, UTA,
    WAS — what the odds, the rosters and the bets use), on the schedule
    and in the stored games and logs, so a moneyline on the Warriors meets
    its game; the WNBA's rows are stored as they always were;
  * the preseason still reaches the build marked, so it is dropped before
    anything is priced.

Fixture payloads; nothing here touches the network.

Run directly: `python3 tests/test_the_nba_reads_espn_when_its_own_feed_says_no.py`
"""
import inspect
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, maintenance                                 # noqa: E402
from engine.sources import espnhoops, nbaespn                      # noqa: E402


def _event(eid, home, away, kind=2, state="post", hs=110, as_=104):
    def side(abbr, where, score):
        return {"homeAway": where, "score": str(score),
                "team": {"abbreviation": abbr, "displayName": abbr + " club"}}
    return {"id": eid, "date": "2026-10-20T23:30Z", "season": {"type": kind},
            "competitions": [{"competitors": [side(home, "home", hs), side(away, "away", as_)],
                              "status": {"type": {"state": state, "completed": state == "post"}}}]}


BOARD = {"events": [_event("401", "GS", "NY"), _event("402", "UTAH", "WSH", state="pre"),
                    _event("403", "SA", "NO", kind=1, state="pre")]}


def _summary(home, away):
    def team(abbr, name):
        return {"team": {"abbreviation": abbr}, "statistics": [{
            "names": ["MIN", "PTS", "REB", "AST", "3PT", "STL", "BLK", "TO"],
            "athletes": [{"athlete": {"displayName": name, "id": "9"}, "starter": True,
                          "stats": ["34", "27", "5", "6", "4-9", "2", "0", "3"]}]}]}
    return {"boxscore": {"players": [team(home, "Home Guard"), team(away, "Away Guard")]}}


class _Feed:
    """ESPN's scoreboard and summary, from the fixtures above."""

    def __init__(self, board):
        self.board, self.old = board, None

    def _box(self, gid, ttl=0, league="wnba"):
        ev = next(e for e in self.board["events"] if e["id"] == gid)
        sides = {c["homeAway"]: c["team"]["abbreviation"] for c in ev["competitions"][0]["competitors"]}
        return _summary(sides["home"], sides["away"])

    def __enter__(self):
        self.old = (espnhoops.fetch_scoreboard, espnhoops.fetch_summary)
        espnhoops.fetch_scoreboard = lambda date, ttl=None, league="wnba": self.board
        espnhoops.fetch_summary = self._box
        return self

    def __exit__(self, *exc):
        espnhoops.fetch_scoreboard, espnhoops.fetch_summary = self.old


def test_the_schedule_carries_the_leagues_own_codes_and_marks_the_preseason():
    with _Feed(BOARD):
        rows = nbaespn.parse_schedule_day(nbaespn.fetch_schedule(), "2026-10-20")
    got = {(g["away"], g["home"]): g for g in rows}
    assert set(got) == {("NYK", "GSW"), ("WAS", "UTA"), ("NOP", "SAS")}, set(got)
    assert got[("NOP", "SAS")]["preseason"] is True
    assert got[("NYK", "GSW")]["preseason"] is False and got[("NYK", "GSW")]["state"] == "final"
    assert got[("WAS", "UTA")]["state"] == "scheduled"


def test_the_nightly_stores_the_nbas_games_and_logs_in_the_leagues_codes():
    conn = db.connect(":memory:")
    with _Feed({"events": [_event("401", "GS", "NY")]}):
        res = nbaespn.ingest_day(conn, "2026-10-20")
    assert res["games"] == 1 and res["player_logs"] > 0, res
    g = conn.execute("SELECT home, away, home_score FROM games WHERE sport='nba'").fetchone()
    assert tuple(g) == ("GSW", "NYK", 110)
    teams = {tuple(r) for r in conn.execute(
        "SELECT DISTINCT team, opponent FROM player_game_logs WHERE sport='nba'")}
    assert teams == {("GSW", "NYK"), ("NYK", "GSW")}, teams


def test_the_wnbas_rows_are_stored_as_they_always_were():
    conn = db.connect(":memory:")
    with _Feed({"events": [_event("501", "GS", "NY")]}):
        espnhoops.ingest_day(conn, "2026-07-20", league="wnba")
    assert tuple(conn.execute("SELECT home, away FROM games WHERE sport='wnba'").fetchone()) == ("GS", "NY")


def test_the_rows_already_stored_are_rewritten_once_and_only_when_asked():
    """`nbacodes.py`: a dry run counts, `--apply` rewrites the NBA's six
    ESPN spellings in the history's games and logs, and a second run finds
    nothing; the WNBA's rows and every stat are untouched."""
    import nbacodes
    conn = db.connect(":memory:")
    for sport in ("nba", "wnba"):                           # stored as ESPN spelled them
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, "
                     "away_score) VALUES (?, 2025, '2026-03-01', '401', 'GS', 'NY', 110, 104)", (sport,))
        for team, opp, v in (("GS", "NY", 27.0), ("NY", "GS", 19.0)):
            conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, "
                         "opponent, market, value) VALUES (?, 2025, '2026-03-01', '401', ?, ?, ?, 'pts', ?)",
                         (sport, team + " Guard", team, opp, v))
    conn.commit()
    before = conn.execute("SELECT SUM(value) FROM player_game_logs WHERE sport='nba'").fetchone()[0]
    rows = nbacodes.plan(conn)
    assert {(r[0], r[1], r[2], r[3]) for r in rows} == {
        ("games", "home", "GS", "GSW"), ("games", "away", "NY", "NYK"),
        ("player_game_logs", "team", "GS", "GSW"), ("player_game_logs", "team", "NY", "NYK"),
        ("player_game_logs", "opponent", "GS", "GSW"), ("player_game_logs", "opponent", "NY", "NYK")}
    assert conn.execute("SELECT COUNT(*) FROM games WHERE sport='nba' AND home='GS'").fetchone()[0] == 1
    assert nbacodes.apply(conn, rows) > 0 and nbacodes.plan(conn) == []
    assert tuple(conn.execute("SELECT home, away FROM games WHERE sport='nba'").fetchone()) == ("GSW", "NYK")
    assert tuple(conn.execute("SELECT home, away FROM games WHERE sport='wnba'").fetchone()) == ("GS", "NY")
    assert conn.execute("SELECT SUM(value) FROM player_game_logs WHERE sport='nba'").fetchone()[0] == before
    src = (ROOT / "nbacodes.py").read_text(encoding="utf-8")
    assert "ledger" not in src.split('"""', 2)[2], "the journal is never opened"


def test_every_nba_schedule_and_results_path_reads_espn():
    build = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "from engine.sources.nbadata import" not in build, "the board still asks the CDN for its schedule"
    assert build.count("from engine.sources.nbaespn import") == 3
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "from .sources.nbadata import ingest_nba_date" not in src
    assert "from .sources.nbaespn import ingest_day as nba" in inspect.getsource(maintenance._hoops_ingesters)
    assert "from .sources.nbaespn import ingest_day as ingest_nba_date" in src


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
