"""College grades on ESPN's box score, and its provisional rows never outlive the play file (2026-11-14).

Ethan, answering RUN_NEXT 00e — "grade college on ESPN's box score, the one
the books settle on?" — "1. yes". His cleanup run (engine/cfbdedupe) had found
4,406 box copies in 2026 that differed from the play file's row, some above it
(A'Marion Peterson: 5 carries in the box, 4 in the play file), which no
mid-game copy can be. So (engine/boxsettle.BOX_GRADES):

  * a final box score's numbers are kept (`keep_box_values`, ``box_values``)
    and the play file's rows for the same game take them when it lands
    (`apply_box_values`), so a bet graded on the box score stands;
  * every play-file backfill re-applies them (engine/ingest), so a re-pull
    never puts the play file's number back;
  * a box number the play file has no row for leaves the play file alone;
  * and a game's provisional rows go once its official rows are on file
    whether or not a prop is still open on its day (`provisional_games`) —
    they used to stay beside the official ones once the night's props had
    settled, which is how 130,078 duplicate rows built up.

The NFL keeps grading on nflverse's file.

    python3 tests/test_college_grades_on_the_box_score.py
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as B, db, ledger            # noqa: E402

TODAY = dt.date.today()
DAY = (TODAY - dt.timedelta(days=1)).isoformat()


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _row(game_id, player, team, opp, market, value, period=DAY, home=1, sport="cfb", season=None):
    return {"sport": sport, "season": season or TODAY.year, "period": period, "game_id": game_id,
            "player": player, "team": team, "opponent": opp, "position": "RB", "home": home,
            "market": market, "value": float(value)}


def _box(H):
    """Saturday night: the same-night settle filed the final box score."""
    db.upsert_player_logs(H, [
        _row("401858249-box", "A'Marion Peterson", "MIA", "CLEM", "carries", 5),
        _row("401858249-box", "A'Marion Peterson", "MIA", "CLEM", "rush_yds", 51),
        _row("401858249-box", "Box Only Spelling", "MIA", "CLEM", "rush_yds", 12),
        _row("401858249-box", "Cade Klubnik", "CLEM", "MIA", "pass_yds", 190, home=0)])
    H.commit()


def _play_file(H, carries=4, yds=43, pass_yds=198):
    """Days later: the play file's rows for the same game, keyed by ESPN's number."""
    db.upsert_player_logs(H, [
        _row("401858249", "A'Marion Peterson", "MIA", "CLEM", "carries", carries),
        _row("401858249", "A'Marion Peterson", "MIA", "CLEM", "rush_yds", yds),
        _row("401858249", "Cade Klubnik", "CLEM", "MIA", "pass_yds", pass_yds, home=0),
        _row("401858249", "Other Player", "MIA", "CLEM", "rush_yds", 30)])
    H.commit()


def _logs(H, player, market):
    return [(r[0], r[1]) for r in H.execute(
        "SELECT game_id, value FROM player_game_logs WHERE sport='cfb' AND player=? AND market=? ORDER BY game_id",
        (player, market))]


def test_the_play_file_takes_the_box_scores_numbers_and_the_copies_go_with_no_prop_open():
    L, H = _world()
    _box(H)
    _play_file(H)
    # No prop is open on the day: the copies used to stay forever.
    res = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=lambda lg: [],
                            fetch_summary=lambda lg, eid: {})
    assert res["purged"] == 4, res
    assert res["box_values"] == {"kept": 4, "applied": 3, "unmatched": 1}, res
    assert _logs(H, "A'Marion Peterson", "carries") == [("401858249", 5.0)]
    assert _logs(H, "A'Marion Peterson", "rush_yds") == [("401858249", 51.0)]
    assert _logs(H, "Cade Klubnik", "pass_yds") == [("401858249", 190.0)]
    assert _logs(H, "Other Player", "rush_yds") == [("401858249", 30.0)], "no box number: the play file's stands"
    assert _logs(H, "Box Only Spelling", "rush_yds") == [], "a provisional row never outlives the play file"
    kept = H.execute("SELECT COUNT(*) FROM box_values WHERE sport='cfb'").fetchone()[0]
    assert kept == 4
    # A second pass finds nothing left to do.
    again = B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=lambda lg: [],
                              fetch_summary=lambda lg, eid: {})
    assert again["purged"] == 0 and "box_values" not in again, again


def test_a_backfill_never_puts_the_play_files_number_back():
    L, H = _world()
    _box(H)
    _play_file(H)
    B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=lambda lg: [], fetch_summary=lambda lg, eid: {})
    _play_file(H)                                   # the Monday re-pull writes 4, 43 and 198 again
    assert _logs(H, "A'Marion Peterson", "carries") == [("401858249", 4.0)]
    got = B.apply_box_values(H, "cfb", seasons=[TODAY.year])
    assert got == {"applied": 3, "unmatched": 1}, got
    assert _logs(H, "A'Marion Peterson", "carries") == [("401858249", 5.0)]
    assert _logs(H, "Cade Klubnik", "pass_yds") == [("401858249", 190.0)]
    src = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    body = src[src.index("def ingest_cfb_player_history("):]
    body = body[:body.index("\ndef ", 10)]
    assert body.index("db.upsert_player_logs(conn, out[\"rows\"])") < body.index(
        "boxsettle.apply_box_values(conn, \"cfb\", seasons=[int(season)])"), "after every backfill's write"


def test_a_bet_graded_on_the_box_score_stands_when_the_play_file_lands():
    L, H = _world()
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category) VALUES (?, 'cfb', ?, ?, ?, 'rush_yds', 'OVER', 47.5, -110, 1, 10, "
              "'open', 'main')", (f"{DAY}T12:00:00", DAY, DAY, "A'Marion Peterson"))
    L.commit()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('cfb', ?, ?, '401858249', ?, 'MIA', 'CLEM', 31, 24)", (TODAY.year, DAY, DAY))
    H.commit()
    _box(H)
    assert ledger.settle_from_history(L, H) == 1
    assert L.execute("SELECT status, actual FROM bets").fetchone()["actual"] == 51.0
    _play_file(H)                                   # 43 in the play file: an under
    B.ingest_for_open(L, H, "cfb", log=lambda *a: None, fetch_rows=lambda lg: [], fetch_summary=lambda lg, eid: {})
    ledger.resettle_mismatches(L, H)
    b = L.execute("SELECT status, actual FROM bets").fetchone()
    assert (b["status"], b["actual"]) == ("won", 51.0), dict(b)


def test_the_nfl_keeps_grading_on_its_official_file():
    L, H = _world()
    db.upsert_player_logs(H, [_row("DET-002-box", "Jahmyr Gibbs", "DET", "KC", "rush_yds", 94, sport="nfl",
                                   period="002"),
                              _row("DET-002", "Jahmyr Gibbs", "DET", "KC", "rush_yds", 97, sport="nfl",
                                   period="002")])
    H.commit()
    assert B.keep_box_values(H, "nfl", {"home": "DET", "away": "KC", "period": "002", "season": TODAY.year}) == 0
    assert B.apply_box_values(H, "nfl", seasons=[TODAY.year]) == {"applied": 0, "unmatched": 0}
    assert B.BOX_GRADES == ("cfb",)
    assert B.provisional_games(H, "cfb") == []


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
                traceback.print_exc(limit=5)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
