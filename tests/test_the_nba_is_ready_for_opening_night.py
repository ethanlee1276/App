"""The NBA, before opening night (the site audit's follow-up, 2026-09-24).

Ethan approved the readiness pass the audit listed as next ("Yeah do 1-4").
Three faults, each able to cost real money or real form on the first night:

1. A player who sat was GRADED, not voided. The NBA's box score lists every
   rostered player, a scratch included, with 0:00 and a row of zeros, so his
   over was graded lost and his under won. The book voids him; the settler
   now does too (Ethan's rule, 2026-09-14: "a scratch is void").
2. The preseason was a game. Neither feed's parser told the preseason apart,
   so early October would have been priced on regular-season minutes and its
   box scores stored as a player's form.
3. Two season labels. The nightly ingest filed a game under its calendar year
   while every query reads the year the season started — from January, every
   new game fell outside the board's `season IN recent_seasons(...)`.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import db, seasons                                    # noqa: E402
from engine.sources import espnhoops, nbadata                     # noqa: E402


def test_zero_minutes_voids_instead_of_grading():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = src.index("ZERO MINUTES IS A SCRATCH, NOT A ZERO")
    block = src[i:i + 1400]
    assert "if actual_minutes is not None and actual_minutes <= 0:" in block
    assert "status='void', pnl_units=0, pnl_dollars=0" in block
    assert block.index("status='void'") < src[i:].index("_settle_one(conn, b, float(row[\"value\"])"), \
        "voided before it can be graded"


def test_a_player_who_sat_is_voided_and_one_who_played_is_graded():
    """The real settler, on a 0:00 line beside a 30-minute one."""
    from engine import ledger
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    D = "2026-03-01"
    for p in ("Scratch Guy", "Played Guy"):
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category) VALUES "
                  "(?, 'nba', ?, '', ?, 'pts', 'OVER', 18.5, -110, 1, 10, 'open', 'main')",
                  (D + "T12:00:00", D, p))
    L.commit()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('nba', 2025, ?, 'NYK@BOS', ?, 'BOS', 'NYK', 110, 100)", (D, D))
    rows = []
    for p, mins, pts in (("Scratch Guy", 0, 0), ("Played Guy", 30, 25)):
        for market, v in (("min", mins), ("pts", pts)):
            rows.append({"sport": "nba", "season": 2025, "period": D, "game_id": f"{p}-{D}",
                         "player": p, "team": "BOS", "opponent": "NYK", "position": "B",
                         "home": 1, "market": market, "value": v})
    db.upsert_player_logs(H, rows)
    H.commit()
    assert ledger.settle_from_history(L, H) == 2
    got = {r["player"]: (r["status"], r["pnl_units"])
           for r in L.execute("SELECT player, status, pnl_units FROM bets")}
    assert got["Scratch Guy"] == ("void", 0.0), got
    assert got["Played Guy"][0] == "won", got


def test_the_preseason_is_known_on_both_feeds():
    assert nbadata.is_preseason("0012600001") and not nbadata.is_preseason("0022600001")
    assert not nbadata.is_preseason("0042500101"), "the playoffs are games"
    sched = {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "0012600011", "gameDateEst": "2026-10-05T00:00:00Z",
         "homeTeam": {"teamTricode": "BOS"}, "awayTeam": {"teamTricode": "NYK"}},
        {"gameId": "0022600011", "gameDateEst": "2026-10-21T00:00:00Z",
         "homeTeam": {"teamTricode": "BOS"}, "awayTeam": {"teamTricode": "NYK"}}]}]}}
    assert [g["preseason"] for g in nbadata.parse_schedule_day(sched, "2026-10-05")] == [True]
    assert [g["preseason"] for g in nbadata.parse_schedule_day(sched, "2026-10-21")] == [False]
    ev = lambda t: {"id": "1", "season": {"type": t}, "competitions": [{"competitors": [  # noqa: E731
        {"homeAway": "home", "team": {"abbreviation": "BOS"}, "score": "100"},
        {"homeAway": "away", "team": {"abbreviation": "NYK"}, "score": "90"}],
        "status": {"type": {"state": "post", "completed": True}}}]}
    got = espnhoops.parse_scoreboard({"events": [ev(1), ev(2)]})
    assert [g["preseason"] for g in got] == [True, False]


def test_the_ingests_and_the_build_leave_the_preseason_out():
    nsrc = (ROOT / "engine" / "sources" / "nbadata.py").read_text(encoding="utf-8")
    i = nsrc.index("def ingest_nba_date(")
    assert 'if g.get("preseason"):' in nsrc[i:i + 900]
    esrc = (ROOT / "engine" / "sources" / "espnhoops.py").read_text(encoding="utf-8")
    i = esrc.index("def ingest_day(")
    assert 'if g.get("preseason"):' in esrc[i:i + 1500]
    build = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'games = [g for g in games if not g.get("preseason")]' in build
    assert 'status="preseason"' in build
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'state.data.status === "preseason"' in app, "an empty October board says why"


def test_the_nightly_files_a_game_under_its_season():
    rows = nbadata.log_rows([{"player": "A", "team": "BOS", "opponent": "NYK", "home": True,
                              "starter": True, "min": 30, "pts": 20, "reb": 5, "ast": 4,
                              "fg3m": 2}], "2027-03-01", "g1")
    assert {r["season"] for r in rows} == {2026}, "March 2027 is the 2026 season"
    nsrc = (ROOT / "engine" / "sources" / "nbadata.py").read_text(encoding="utf-8")
    assert '"season": season_of("nba", date)' in nsrc


def test_the_old_labels_are_found_and_fixed_only_on_apply():
    c = db.connect(":memory:")
    c.execute("INSERT INTO games (sport, season, period, game_id, home, away) "
              "VALUES ('nba', 2027, '2027-03-01', 'A@B', 'B', 'A')")
    for s_ in (2027, 2026):
        c.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, market, value) "
                  "VALUES ('nba', ?, '2027-01-10', 'X-2027-01-10', 'X', 'pts', 20)", (s_,))
    want = {"games": {"wrong": 1, "duplicates": 0}, "player_game_logs": {"wrong": 1, "duplicates": 1}}
    assert seasons.relabel(c, "nba") == want
    assert c.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == 2, "counting changes nothing"
    seasons.relabel(c, "nba", apply=True)
    assert seasons.relabel(c, "nba") == {"games": {"wrong": 0, "duplicates": 0},
                                         "player_game_logs": {"wrong": 0, "duplicates": 0}}
    assert c.execute("SELECT season FROM games").fetchone()[0] == 2026
    assert c.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == 1, "the duplicate went"


def test_the_box_can_count_both_read_only():
    hc = (ROOT / "homecheck.py").read_text(encoding="utf-8")
    i = hc.index("def nba() -> list:")
    body = hc[i:hc.index("\ndef ", i + 10)]
    assert 'seasons.relabel(db.connect(), "nba")' in body and "apply=True" not in body
    assert "actual_minutes <= 0" in body
    runbook = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "python3 homecheck.py nba" in runbook and "relabel nba --apply" in runbook


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
