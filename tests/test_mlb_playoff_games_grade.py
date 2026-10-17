"""A playoff game's props grade, off its box score.

The site audit, 2026-09-24, five days before the wild-card round. Every MLB
prop grades from `player_game_logs`, and `ingest.ingest_mlb_date` filled
those from each player's `stats=gameLog` — which statsapi answers with
REGULAR-SEASON games unless it is asked for another game type, and nothing
asked. So from the first playoff game every final would have left its
players with no line; baseball has no absent-player grade
(`ledger.ABSENT_RULE_SPORTS`), so every playoff prop — edge, Most Likely,
the Pick of the Day — would have stayed open for good.

The schedule (finals, the slate) carries every game type already. Now a
final game that the logs did not carry is read off its box score, with the
parser the Live tab's tracked bets already count on; a regular-season date
fetches nothing extra.
"""
import datetime as dt
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ingest, ledger                            # noqa: E402

DAY = (dt.date.today() - dt.timedelta(days=3)).isoformat()      # past the strict window


def _box():
    return {"teams": {
        "home": {"players": {"ID1": {"person": {"fullName": "Aaron Judge"},
                                     "position": {"abbreviation": "RF"},
                                     "stats": {"batting": {"hits": 2, "doubles": 1, "triples": 0,
                                                           "homeRuns": 1, "plateAppearances": 4}}}}},
        "away": {"players": {"ID2": {"person": {"fullName": "Garrett Crochet"},
                                     "position": {"abbreviation": "P"},
                                     "stats": {"pitching": {"strikeOuts": 7, "inningsPitched": "5.2",
                                                            "battersFaced": 22}}}}}}}


def _game(home, away, pk, state="Final", n=1):
    return types.SimpleNamespace(home=home, away=away, game_pk=pk, game_number=n,
                                 sched_state=state, live=None, park="generic", total=8.5,
                                 weather=types.SimpleNamespace(temp_f=70.0, wind_mph=5.0),
                                 pitchers={}, plate_umpire="")


def test_a_final_game_the_logs_missed_is_read_off_its_box():
    fetched = []
    slate = types.SimpleNamespace(games=[_game("NYY", "BOS", 7771), _game("LAD", "SD", 7772, "Live"),
                                         _game("HOU", "SEA", 7773)], props=[])
    covered = [{"period": DAY, "team": "HOU", "player": "X", "market": "hits"}]
    rows = ingest.mlb_box_rows(slate, DAY, covered, fetch=lambda pk: fetched.append(pk) or _box())
    assert fetched == [7771], "only the final game with no lines; never one in play, never one the logs carried"
    got = {(r["player"], r["market"]): r["value"] for r in rows}
    assert got[("Aaron Judge", "total_bases")] == 6.0 and got[("Aaron Judge", "hits")] == 2.0
    assert got[("Aaron Judge", "home_runs")] == 1.0 and got[("Aaron Judge", "pa")] == 4.0
    assert got[("Garrett Crochet", "strikeouts")] == 7.0
    assert got[("Garrett Crochet", "outs")] == 17.0, "5.2 innings is seventeen outs"
    judge = next(r for r in rows if r["player"] == "Aaron Judge")
    assert (judge["team"], judge["opponent"], judge["home"]) == ("NYY", "BOS", 1)
    assert judge["game_id"] == f"Aaron Judge-{DAY}", "the key the game-log path writes"


def test_a_playoff_prop_settles():
    t = Path(tempfile.mkdtemp())
    L, H = ledger.connect(t / "l.db"), db.connect(t / "h.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    slate = types.SimpleNamespace(games=[_game("NYY", "BOS", 7771)], props=[], date=DAY)
    import engine.mlb.sources.statslogs as SL
    saved = (SL.build_live_slate, SL.fetch_boxscore)
    SL.build_live_slate = lambda date, **k: slate
    SL.fetch_boxscore = lambda pk: _box()
    try:
        res = ingest.ingest_mlb_date(H, DAY)
    finally:
        SL.build_live_slate, SL.fetch_boxscore = saved
    assert res["box_rows"] == 6, res
    # The final score arrives from the schedule's results pass (every game type).
    H.execute("UPDATE games SET home_score=5, away_score=3, date=? WHERE sport='mlb' AND period=? "
              "AND game_id='BOS@NYY'", (DAY, DAY))
    H.commit()
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
              "stake_units, stake_dollars, status, category) VALUES "
              "(?, 'mlb', ?, ?, 'Aaron Judge', 'total_bases', 'OVER', 1.5, -150, 1, 10, 'open', 'likely_live')",
              (f"{DAY}T12:00:00", DAY, DAY))
    L.commit()
    assert ledger.settle_from_history(L, H) == 1
    assert L.execute("SELECT status FROM bets").fetchone()[0] == "won"


def test_the_ingest_reads_boxes_and_says_how_many():
    src = Path(ingest.__file__).read_text(encoding="utf-8")
    body = src[src.index("def ingest_mlb_date("):src.index("def ingest_cfb_history(")]
    assert "boxed = mlb_box_rows(slate, date, prows)" in body and 'result["box_rows"] = len(boxed)' in body
    assert body.index("mlb_box_rows(") < body.index("db.upsert_player_logs(")


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
