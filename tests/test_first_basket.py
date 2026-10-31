"""First basket is the NBA's Long Shots (engine/firstbasket).

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA ... still not seeing ... first basket scored for NBA
yet ... those bets need to show up on the long shot page."

The model is the box study's (tools/first_basket_study.py, runbook IV): the
team with the first shot scores first 71.9% of the time, the home team 53.8%,
each team's tip history predicts who shoots first, and a player's share of
his team's first-three-minute shots picks the scorer best.

Run directly: `python3 tests/test_first_basket.py`
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import firstbasket as FB, ledger                     # noqa: E402
from engine.sources import oddsapi                               # noqa: E402
from _app import app_js                                          # noqa: E402


def _history():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE nba_shots (game_id TEXT, action INTEGER, season INTEGER, date TEXT, "
                 "person_id INTEGER, player TEXT, team TEXT, opponent TEXT, home INTEGER, period INTEGER, "
                 "clock TEXT, kind TEXT, made INTEGER, shot TEXT, descriptor TEXT, distance REAL, x REAL, "
                 "y REAL, zone TEXT, area TEXT, assist TEXT, blocked INTEGER, quals TEXT, "
                 "PRIMARY KEY (game_id, action))")
    return conn


def _shot(conn, gid, action, date, player, team, opp, home, clock, made, period=1, kind="2pt", season=2026):
    conn.execute("INSERT INTO nba_shots (game_id, action, season, date, player, team, opponent, home, period,"
                 " clock, kind, made) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (gid, action, season, date, player, team, opp, home, period, clock, kind, made))


def _games(conn):
    """Five BOS-NYK games: BOS takes the first shot in four, Tatum takes most
    of BOS's opening shots, Brunson most of NYK's."""
    for i in range(5):
        gid, day = f"g{i}", f"2026-10-{20 + i:02d}"
        first, second = (("BOS", "NYK") if i < 4 else ("NYK", "BOS"))
        a = 1
        for team in (first, second):
            opp = "NYK" if team == "BOS" else "BOS"
            star, role = ("Jayson Tatum", "Derrick White") if team == "BOS" else ("Jalen Brunson", "Josh Hart")
            for who, n in ((star, 3), (role, 1)):
                for _ in range(n):
                    _shot(conn, gid, a, day, who, team, opp, int(team == "BOS"), f"11:{50 - a:02d}", 0)
                    a += 1
        _shot(conn, gid, a, day, "Jayson Tatum", "BOS", "NYK", 1, "10:30", 1)


# --- the model -----------------------------------------------------------------------
def test_the_home_lean_is_what_the_two_measured_rates_imply():
    assert abs(FB.HOME_FIRST_SHOT - 0.587) < 0.001
    assert abs(FB.home_scores_first(FB.HOME_FIRST_SHOT) - FB.HOME_SCORES_FIRST) < 1e-9
    assert abs(FB.home_shoots_first(0.5, 0.5) - FB.HOME_FIRST_SHOT) < 1e-9


def test_a_team_that_wins_the_tip_is_likelier_to_score_first():
    even = FB.home_scores_first(FB.home_shoots_first(0.5, 0.5))
    tips = FB.home_scores_first(FB.home_shoots_first(FB.first_shot_rate(9, 10), FB.first_shot_rate(1, 10)))
    assert tips > even + 0.05 and tips < FB.FIRST_SHOT_SCORES


def test_the_share_is_the_first_three_minutes_with_a_floor():
    s = FB.shares({"A": 6, "B": 2, "C": 0})
    assert abs(sum(s.values()) - 1.0) < 1e-9
    assert s["A"] > s["B"] > s["C"] > 0, "a player with no opening shot is unlikely, never impossible"


def test_the_shots_give_the_tip_record_and_the_openers():
    conn = _history()
    _games(conn)
    data = FB.read(conn, 2026)
    assert data["teams"]["BOS"] == {"first": 4, "games": 5}
    assert data["recent"]["BOS"] == {"Jayson Tatum", "Derrick White"}
    rows = FB.game_probs(data, "BOS", "NYK")
    assert rows[0]["player"] == "Jayson Tatum", rows[:2]
    assert abs(sum(r["prob"] for r in rows) - 1.0) < 1e-9


# --- the board -------------------------------------------------------------------------
def _quote(player, home, away, odds, book="DraftKings"):
    return {"player": player, "home": home, "away": away,
            "quotes": [{"book": book, "yes_odds": odds, "no_odds": None, "player": player}]}


def test_a_price_long_enough_for_our_chance_is_a_pick_and_the_favourite_is_not():
    conn = _history()
    _games(conn)
    games = [{"home": "BOS", "away": "NYK", "date": "2026-10-31", "kickoff": "2026-10-31T23:30:00Z"}]
    quotes = {"a": _quote("Jayson Tatum", "BOS", "NYK", 300),        # our chance ~35%: big value
              "b": _quote("Josh Hart", "BOS", "NYK", 400)}            # a long way under his price
    b = FB.board(quotes, games, conn=conn, date="2026-10-31")
    assert b["games"] == 1 and b["quoted"] == 2
    assert [p["player"] for p in b["picks"]] == ["Jayson Tatum"]
    p = b["picks"][0]
    assert p["market"] == "first_basket" and p["grade"] == "First Basket" and p["stake_units"] == 0.1
    assert p["ev"] >= FB.MIN_EV and FB.FIRST_BASKET_ODDS[0] <= p["odds"] <= FB.FIRST_BASKET_ODDS[1]


def test_a_game_with_no_price_shows_our_first_scorers_and_the_price_that_would_make_a_pick():
    conn = _history()
    _games(conn)
    games = [{"home": "BOS", "away": "NYK", "date": "2026-10-31", "kickoff": "2026-10-31T23:30:00Z"}]
    b = FB.board({}, games, conn=conn, date="2026-10-31", why="")
    assert b["picks"] == [] and b["rows"] == [] and b["ours_games"] == 1
    assert len(b["ours"]) == FB.OURS_PER_GAME and b["ours"][0]["player"] == "Jayson Tatum"
    top = b["ours"][0]
    assert top["priced"] is False and top["need_odds"] >= FB.FIRST_BASKET_ODDS[0]
    assert b["why"] == FB.WHY_LATER
    assert FB.why_empty("the pacer held the pull: budget") == FB.WHY_BUDGET


# --- grading ----------------------------------------------------------------------------
def test_the_first_points_grade_it_free_throws_included():
    h = _history()
    _shot(h, "x1", 1, "2026-10-31", "Jalen Brunson", "NYK", "BOS", 0, "11:40", 0)
    _shot(h, "x1", 2, "2026-10-31", "Jayson Tatum", "BOS", "NYK", 1, "11:20", 1, kind="ft")
    _shot(h, "x1", 3, "2026-10-31", "Jalen Brunson", "NYK", "BOS", 0, "11:00", 1)
    assert FB.first_scorer(h, "NYK", "2026-10-31") == {"player": "Jayson Tatum", "team": "BOS"}
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    for who, team in (("Jayson Tatum", "BOS"), ("Jalen Brunson", "NYK")):
        lconn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, hit_prob,"
                      " grade, stake_units, stake_dollars, status, category, team, game_day)"
                      " VALUES ('t','nba','2026-10-31',?,'first_basket','OVER',0.5,'DK',400,0.3,"
                      "'First Basket',0.1,0,'open','longshot',?,'2026-10-31')", (who, team))
    lconn.commit()
    assert FB.settle(lconn, h) == 2
    got = dict(lconn.execute("SELECT player, status FROM bets").fetchall())
    assert got == {"Jayson Tatum": "won", "Jalen Brunson": "lost"}, got


def test_an_unplayed_game_waits():
    h = _history()
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    lconn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, hit_prob,"
                  " grade, stake_units, stake_dollars, status, category, team)"
                  " VALUES ('t','nba','2026-11-01','A','first_basket','OVER',0.5,'DK',400,0.3,"
                  "'First Basket',0.1,0,'open','longshot','BOS')")
    lconn.commit()
    assert FB.settle(lconn, h) == 0
    assert lconn.execute("SELECT status FROM bets").fetchone()[0] == "open"


# --- the wiring --------------------------------------------------------------------------
def test_the_nba_pull_buys_the_market_and_keeps_it_apart():
    cfg = oddsapi.SPORT_CONFIG["nba"]
    assert cfg["scorers"] == {"player_first_basket": "first_basket"}
    assert "player_first_basket" in oddsapi.UNPROVEN_MARKETS, "a refusal drops it and retries"
    assert "player_first_basket" not in oddsapi.SPORT_CONFIG["wnba"].get("scorers", {})
    from engine import oddsbudget
    assert oddsbudget.EVENT_CREDITS["nba"] == 20
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"), encoding="utf-8").read()
    assert 'keep = result.first_td if k[1] == "first_td" else result.first_basket' in src


def test_the_journal_and_the_record_know_the_market():
    assert "first_basket" in ledger.LONGSHOT_MARKETS and "first_basket" in ledger.SETTLEABLE_LONGSHOTS
    from engine import gate, markets
    assert "first_basket" in gate.paid_keys_for("nba.json")
    assert markets.words().get("first_basket") == "First Basket"
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert "n_fb = _fb.settle(lconn, hconn)" in src


def test_the_nba_build_makes_the_board_and_journals_its_picks():
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert 'first_basket_quotes = getattr(res, "first_basket", None) or {}' in src
    assert 'out["first_basket"] = _fb' in src and 'out["long_shots"] = _fb["picks"]' in src
    assert "_ls_n = ledger.log_longshots(lconn," in src


def test_the_long_shots_page_opens_for_the_nba_and_reads_either_board():
    app = app_js()
    assert '  nba: ["weather"],' in app, "Long Shots is no longer hidden for the NBA"
    i = app.index("function firstScorer(d)")
    body = app[i:app.index("\n}", i)]
    assert "d.first_basket ?" in body and "d.first_td ?" in body
    assert "firstOursHTML(fs.b.ours)" in app
    assert 'r.market === "first_basket" ? "First-basket share"' in app


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    print(f"{ran} passed, {fails} failed")
    sys.exit(1 if fails else 0)
