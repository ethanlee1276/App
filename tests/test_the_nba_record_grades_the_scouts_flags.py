"""The NBA's graded record grades the scout's flags, the way the NFL's does.

Ethan, 2026-11-04: "I want to make sure we're picking the right bets ... so
we're winning a lot of bets." The NBA's flags reached the cards measured on
two seasons of box scores; the record-learning (engine/likelyctx, run by
engine/boardlearn on every settle pass) now grades them on our own NBA
picks. Checks, one rule each: each settled pick's situation is rebuilt from
the stored games as the board read it (who sat, who came back, rest, his
form, the books' last pre-game spread and total); a night whose box is not
stored says "not known", never "nobody sat"; the record fits every flag a
pick raised and the board applies a proven one on every flag, card or not;
nothing moves without a proven store; the board learning grades the NBA's
flags; the NBA build keeps each game's spread and total.

Run directly: `python3 tests/test_the_nba_record_grades_the_scouts_flags.py`
"""
import itertools
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
os.environ.pop("QB_LIKELY_CAL", None)
os.environ.pop("QB_LIKELY_CTX", None)                   # the stores live in the sandbox above

from engine import db, lineledger                                     # noqa: E402
from engine import ledger as LG                                       # noqa: E402
from engine import likelyctx as C                                     # noqa: E402
from engine.nba import scout as S                                     # noqa: E402
from engine.nba import scoutrecord as R                               # noqa: E402

#: Boston's games: the last two on consecutive nights.
DAYS = ("2026-10-21", "2026-10-23", "2026-10-25", "2026-10-27", "2026-10-29", "2026-10-31",
        "2026-11-02", "2026-11-03")
TONIGHT = DAYS[-1]


def _hist():
    """Boston against New York, eight games. The pick's man plays the first
    six (starting the sixth), misses the seventh, plays tonight; a 30-minute
    regular plays seven and sits tonight; a 28-minute regular plays four,
    misses three, and is back tonight; a bench man plays every game. The
    books' spread and total for tonight, three snapshots — one in play."""
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, logs = [], []

    def log(player, day, minutes, reb=None, stl=None, start=False, season=2026):
        logs.append(("nba", season, day, f"g{day}", player, "BOS", "NYK", "S" if start else "", 1, "min", minutes))
        if reb is not None:
            logs.append(("nba", season, day, f"g{day}", player, "BOS", "NYK", "", 1, "reb", reb))
        if stl is not None:
            logs.append(("nba", season, day, f"g{day}", player, "BOS", "NYK", "", 1, "stl", stl))

    for i, d in enumerate(DAYS):
        games.append(("nba", 2026, d, f"g{d}", "BOS", "NYK", 110, 100, 0.0, None, d))
        if i < 6:
            log("Pick Man", d, 30.0, reb=8.0 + (i % 2), stl=(1.0 if i >= 4 else None), start=(i == 5))
        if i < 7:
            log("Big Man", d, 30.0)
        if i < 4 or i == 7:
            log("Hurt Forward", d, 28.0 if i < 4 else 25.0)
        log("Bench Wing", d, 16.0)
    log("Pick Man", TONIGHT, 31.0, reb=6.0)
    log("Pick Man", "2026-04-10", 34.0, reb=9.0, season=2025)          # last season's last game
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    tip = "2026-11-04T00:30:00Z"
    snaps = [("2026-11-03T15:00:00Z", "spread", -5.5), ("2026-11-03T22:00:00Z", "spread", -6.5),
             ("2026-11-04T01:00:00Z", "spread", -15.5), ("2026-11-03T15:00:00Z", "total", 229.5),
             ("2026-11-03T22:00:00Z", "total", 236.5), ("2026-11-04T01:00:00Z", "total", 250.5)]
    c.executemany("INSERT INTO odds_history (sport, taken_at, event_id, home, away, player, market, book, line, "
                  "over_odds, under_odds, commence_time) VALUES ('nba',?,?,'BOS','NYK',?,?,?,?,-110,-110,?)",
                  [(t, f"{TONIGHT}-NYK@BOS", "BOS" if m == "spread" else "TOTAL", m, "best", v, tip)
                   for t, m, v in snaps]
                  + [("2026-11-03T22:00:00Z", f"{TONIGHT}-NYK@BOS", "BOS", "spread", "Pinnacle", -20.0, tip)])
    c.commit()
    return c


def _pick(**kw):
    return {"player": "Pick Man", "day": TONIGHT, "market": "reb", "side": "UNDER", "line": 7.5, "team": "BOS",
            **kw}


def test_each_pick_is_read_as_the_board_read_it_from_the_stored_games():
    data = R.load(_hist(), TONIGHT)
    ctx = R.context(_pick(), data)
    assert ctx["starter"] is True, "he started his newest game"
    assert (ctx["spread"], ctx["total"]) == (-6.5, 236.5), "the last number before the tip, never in play"
    assert data["lines"][("NYK", TONIGHT)]["spread"] == 6.5, "the other club's spread is the home one turned over"
    assert ctx["rest"] == R.rest_label({1, 3, 5}) == "3in4"
    assert ctx["missed_last"] is True, "he missed the club's last game"
    assert ctx["mate_out"] is True, "a 30-minute regular who played the last game sits"
    assert ctx["mate_back"] is True, "a 28-minute regular back from three missed games plays"
    assert ctx["games_season"] == 6, "last season's game counts in his form, not in his season"
    assert ctx["values"][:6] == [9.0, 8.0, 9.0, 8.0, 9.0, 8.0] and ctx["values"][6] == 9.0
    assert ctx["game_id"] == f"{TONIGHT}|NYK@BOS", "both clubs' picks share a game, so a fold keeps it whole"
    steals = R.context(_pick(market="stl"), data)
    assert steals["values"] == [1.0, 1.0], "a count reads only the newest games that stored it"
    assert R.flagged([_pick()], _hist())[0]["flags"] == ["fast_under", "mate_out_under"]
    over = R.flagged([_pick(side="OVER")], _hist())[0]["flags"]
    assert {"b2b_over", "mate_back_over", "back_over"} <= set(over), over


def test_a_night_whose_box_is_not_stored_is_not_known_and_nobody_is_invented():
    data = R.load(_hist(), TONIGHT)
    later = R.context(_pick(day="2026-11-05"), data)
    assert later["mate_out"] is None and later["mate_back"] is None, "not 'nobody sat': not known"
    assert later["spread"] is None and later["total"] is None
    assert R.context(_pick(player="Nobody"), data) is None
    rows = R.flagged([_pick(player="Nobody")], _hist())
    assert rows[0]["ctx"] is None and rows[0]["flags"] == []
    assert R.flagged([], _hist()) == []


def test_the_rebuild_reads_the_schedule_and_the_rotation_as_the_build_does():
    import nba_build as B
    for n in range(7):
        for played in itertools.combinations(range(1, 7), n):
            assert R.rest_label(set(played)) == B.rest_from(set(played)), played
    assert R.NEW_ABSENCE_GAMES == B.NEW_ABSENCE_GAMES
    from engine.hoops import COUNTS, SUMS
    assert R.SUMS == SUMS and R.COUNTS == COUNTS


def _ledger():
    led = LG.connect(Path(tempfile.mkdtemp()) / "ledger.db")
    led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, hit_prob, "
                "status, category) VALUES ('nba',?,?,'Pick Man','BOS','reb','UNDER',7.5,-150,0.66,'won','likely')",
                (TONIGHT, TONIGHT))
    led.commit()
    return led


def test_the_record_learning_reads_the_nbas_own_flags():
    assert "nba" in C.LEARNS and "nba" not in C.SPORTS, "the football read stays football's"
    rows = C.flagged_journal(_ledger(), _hist(), "nba")
    assert [r["flags"] for r in rows] == [["fast_under", "mate_out_under"]]
    assert C.note("mate_out_under", "nba") == S.FLAGS["mate_out_under"]
    assert C.note("shootout_under", "nfl") != "shootout_under", "football's words are football's"
    from engine import boardlearn as B
    e = B.learn_sport(_ledger(), _hist(), "nba", log=lambda *_: None)
    assert e["scout"]["matched"] == 1 and e["scout"]["passed"] is False, e.get("scout")
    src = open(os.path.join(ROOT, "engine", "boardlearn.py"), encoding="utf-8").read()
    assert "likelyctx.LEARNS" in src and "likelyctx.note(f, sport)" in src


def test_a_proven_nba_flag_lowers_its_picks_whether_or_not_the_card_shows_it():
    ctx = R.context(_pick(side="OVER"), R.load(_hist(), TONIGHT))
    row = {"player": "Pick Man", "market": "reb", "side": "OVER", "line": 7.5, "odds": -150, "model_prob": 0.66,
           "scout_ctx": ctx}
    S.annotate([row])
    assert "b2b_over" in row["scout_all"] and "b2b_over" not in row["scout_flags"], "refused: not on the card"
    assert set(row["scout_flags"]) <= set(row["scout_all"])
    assert C.apply([dict(row)], "nba", store={}, history={}) == 0, "no store, nothing moves"
    store = {"nba": {"flags": {"b2b_over": {"k": 0.5, "n": 40, "hit": 0.5, "claimed": 0.66}}}}
    assert C.apply([row], "nba", store=store, history={}) == 1
    q = C.price_chance(-150)
    assert abs(row["model_prob"] - round(q + 0.5 * (0.66 - q), 4)) < 1e-9 and row["model_prob"] < 0.66
    assert S.FLAGS["b2b_over"] in row["ctx_note"] and row["board_raw_prob"] == 0.66
    src = open(os.path.join(ROOT, "engine", "likelyboard.py"), encoding="utf-8").read()
    # The NBA's and college's (2026-11-14), each its own league's verdicts.
    block = src[src.index('if sport in ("nba", "cbb"):'):]
    block = block[:block.index("except Exception")]
    assert block.index("_nsc.annotate(_nrows)") < block.index("_nctx.apply(_nrows, sport)")


def test_the_nba_board_applies_a_proven_flag_inside_its_own_build():
    # The board's NBA block swallows its errors so a scout can never take
    # the board down; this is the check that the correction really runs there.
    from engine import likely as L
    from engine import likelyboard as LB
    ctx = {"starter": True, "spread": -3.0, "total": 230.0, "rest": "b2b_home", "values": [6, 7, 5, 6, 7, 6],
           "minutes": [30.0] * 10, "games_season": 8, "missed_last": False, "mate_out": False, "mate_back": False}
    games = [{"home": "BOS", "away": "NYK", "date": "2099-11-04", "kickoff": "2099-11-05T00:00Z", "live": None}]
    rows = []
    for i, (mk, side) in enumerate((("reb", "OVER"), ("ast", "UNDER"))):
        rec = {"player": f"Player {i}", "team": "BOS", "opponent": "NYK", "market": mk, "market_label": mk,
               "side": side, "line": 5.5, "odds": -140, "book": "DraftKings", "hit_prob": 0.64, "fair_prob": 0.58,
               "projection": 6.0, "reasons": ["because"], "recent_values": [6, 7, 5, 6], "injury_status": "",
               "scout_ctx": ctx}
        rows.append(L._row_from(rec, mk, "nba", lambda m: True, 0.64, shown=0.64, source="model"))
    result = {"most_likely": rows, "games": games, "recommendations": [], "scan_reads": {}}
    C.save({"sport": "nba", "flags": {}, "held_out": {"n": 0}, "fitted_at": "2026-11-04T00:00:00"})
    quiet = {r["player"]: r for r in LB.build(result, record={}, sport="nba", band_verdict=None)["rows"]}
    assert quiet["Player 0"]["model_prob"] == 0.64 and not quiet["Player 0"].get("ctx_note"), "no proof, no move"
    C.save({"sport": "nba", "flags": {"b2b_over": {"k": 0.5, "n": 40, "hit": 0.5, "claimed": 0.66}},
            "held_out": {"n": 400}, "fitted_at": "2026-11-04T00:00:00"})
    try:
        got = {r["player"]: r for r in LB.build(result, record={}, sport="nba", band_verdict=None)["rows"]}
    finally:
        C.save({"sport": "nba", "flags": {}, "held_out": {"n": 0}, "fitted_at": "2026-11-04T00:00:00"})
    over, under = got["Player 0"], got["Player 1"]
    assert over["scout_all"] == ["b2b_over"] and over["model_prob"] < 0.64 and over["ctx_raw_prob"] == 0.64
    assert S.FLAGS["b2b_over"] in over["ctx_note"]
    assert under["model_prob"] == 0.64 and not under.get("ctx_note"), "an under on a back-to-back raises nothing"


def test_the_nba_build_keeps_each_games_spread_and_total():
    game = {"home": "BOS", "away": "NYK", "date": TONIGHT, "kickoff": "2026-11-04T00:30Z",
            "spread": -6.5, "total": 236.5, "home_ml": 0, "away_ml": 0}
    rows = lineledger.rows_for_games("nba", [game])
    assert {r["market"] for r in rows} == {"spread", "total"}
    assert {r["event_id"] for r in rows} == {f"{TONIGHT}-NYK@BOS"}, "the game's day is in the key"
    assert all(r["commence_time"] == "2026-11-04T00:30:00Z" for r in rows), "the cut for in-play numbers"
    import datetime as dt
    h = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    before_tip = dt.datetime(2026, 11, 3, 22, 0, tzinfo=dt.timezone.utc)
    assert lineledger.record(h, "nba", [game], now=before_tip) == 2
    in_play = dict(game, spread=-15.5, total=None)
    assert lineledger.record(h, "nba", [in_play], now=before_tip + dt.timedelta(hours=3)) == 1
    got = R.load(h, TONIGHT)["lines"]
    assert got[("BOS", TONIGHT)] == {"spread": -6.5, "total": 236.5} and got[("NYK", TONIGHT)]["spread"] == 6.5
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert "_lineledger.record_note(conn, args.league" in src and '"date": args.date' in src


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
