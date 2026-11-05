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


def test_a_man_ruled_out_tonight_has_no_seat_and_the_men_who_play_share_his_shots():
    """2026-11-05, measured on the lab's two seasons (docs/NBA_LAB.md, "First
    basket, the men who play"): a candidate sat in 60% of team first baskets,
    and taking the men not in the box out cut the scorer's log loss 9-10%."""
    conn = _history()
    _games(conn)
    data = FB.read(conn, 2026)
    full = {r["player"]: r for r in FB.game_probs(data, "BOS", "NYK")}
    sat = {r["player"]: r for r in FB.game_probs(data, "BOS", "NYK", out={"jayson tatum"})}
    assert "Jayson Tatum" in full and "Jayson Tatum" not in sat
    assert sat["Derrick White"]["share"] == 1.0 and sat["Derrick White"]["prob"] > full["Derrick White"]["prob"]
    assert sat["Jalen Brunson"]["prob"] == full["Jalen Brunson"]["prob"], "the other club is untouched"
    assert abs(sum(r["prob"] for r in sat.values()) - 1.0) < 1e-9
    assert FB.game_probs(data, "BOS", "NYK", out=set()) == FB.game_probs(data, "BOS", "NYK")


def test_a_play_by_play_initial_is_matched_and_a_different_full_name_is_not():
    full, short = FB._sitting({"Jayson Tatum", "Jaylin Williams"})
    assert FB._sits("J. Tatum", full, short), "the play-by-play's own spelling"
    assert FB._sits("Jayson Tatum", full, short)
    assert not FB._sits("Jalen Williams", full, short), "a full name not on the list plays"
    assert FB._sits("J. Williams", full, short), "an initial alone cannot tell them apart: it sits"
    assert not FB._sits("Derrick White", full, short)
    assert FB._sitting(None) == (set(), set())


# --- tonight's five (2026-11-05) -----------------------------------------------------------
BOS_FIVE_BEFORE = ("Jayson Tatum", "Derrick White", "Jaylen Brown", "Jrue Holiday", "Kristaps Porzingis")
BOS_FIVE_LAST = ("Jayson Tatum", "Jaylen Brown", "Jrue Holiday", "Sam Hauser", "Payton Pritchard")
NYK_FIVE = ("Jalen Brunson", "Josh Hart", "Karl-Anthony Towns", "Mikal Bridges", "OG Anunoby")


def _logs(conn, rows):
    conn.execute("CREATE TABLE IF NOT EXISTS player_game_logs (sport TEXT, season INTEGER, period TEXT, "
                 "game_id TEXT, player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, "
                 "market TEXT, value REAL, PRIMARY KEY (sport, season, period, game_id, player, market))")
    for gid, day, player, team, pos in rows:
        conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2026, ?, ?, ?, ?, '', ?, 0, 'min', 30)",
                     (day, gid, player, team, pos))


def _lineup_games(conn):
    """Five BOS-NYK games. BOS start the same five in the first four; in the
    newest, Porzingis misses it, White comes off the bench and Hauser and
    Pritchard start. Tatum takes three opening shots a game, White one in each
    game he started, Hauser one in his start; Brown and Holiday never shoot
    early."""
    logs = []
    for i in range(5):
        gid, day = f"g{i}", f"2026-10-{20 + i:02d}"
        a = 1
        for who, n in (("Jayson Tatum", 3), ("Derrick White", 1 if i < 4 else 0),
                       ("Sam Hauser", 1 if i == 4 else 0)):
            for _ in range(n):
                _shot(conn, gid, a, day, who, "BOS", "NYK", 1, f"11:{50 - a:02d}", 0)
                a += 1
        for who, n in (("Jalen Brunson", 3), ("Josh Hart", 1)):
            for _ in range(n):
                _shot(conn, gid, a, day, who, "NYK", "BOS", 0, f"11:{50 - a:02d}", 0)
                a += 1
        _shot(conn, gid, a, day, "Jayson Tatum", "BOS", "NYK", 1, "10:30", 1)
        five = BOS_FIVE_BEFORE if i < 4 else BOS_FIVE_LAST
        bench = ("Sam Hauser", "Payton Pritchard") if i < 4 else ("Derrick White",)
        logs += [(gid, day, p, "BOS", "S") for p in five] + [(gid, day, p, "BOS", "B") for p in bench]
        logs += [(gid, day, p, "NYK", "S") for p in NYK_FIVE]
    _logs(conn, logs)


def test_the_box_scores_give_each_club_its_last_starting_five():
    conn = _history()
    _lineup_games(conn)
    lu = FB.lineups(conn, 2026, "2026-10-31")
    assert lu["last_five"]["BOS"] == sorted(FB._norm(p) for p in BOS_FIVE_LAST)
    assert lu["club_last"]["BOS"] == "2026-10-24"
    assert lu["starts"]["BOS"][FB._norm("Jayson Tatum")] == 5.0
    assert lu["starts"]["BOS"][FB._norm("Derrick White")] == 4.0
    assert lu["last_game"]["BOS"][FB._norm("Kristaps Porzingis")] == ("2026-10-23", True)
    assert lu["last_game"]["BOS"][FB._norm("Derrick White")] == ("2026-10-24", False)
    assert FB.lineups(conn, 2026, "2026-10-24")["last_five"]["BOS"] == sorted(FB._norm(p) for p in BOS_FIVE_BEFORE), \
        "nothing on or after tonight is read"
    assert FB.lineups(_history(), 2026, "2026-10-31")["last_five"] == {}, "no logs: the board as built"


def test_tonights_five_shares_the_first_basket_by_opening_shots_per_start():
    """Measured on the lab's two seasons (docs/NBA_LAB.md, "First basket,
    tonight's five"): the scorer's multi-class Brier 0.858 -> 0.827 and
    0.856 -> 0.821, each season's settings fitted on the other."""
    conn = _history()
    _lineup_games(conn)
    data = FB.read(conn, 2026, before="2026-10-31")
    f = FB.five(data, "BOS")
    assert f["five"] == set(BOS_FIVE_LAST), f["five"]
    sh, _f = FB.team_shares(data, "BOS")
    assert abs(sum(sh.values()) - 1.0) < 1e-9
    # A new starter is a starter: Hauser's one opening shot in one start is a
    # league starter's rate, not a twentieth of the club's count.
    assert abs(f["rate"]["Sam Hauser"] - (1 + FB.PRIOR_STARTS * FB.PRIOR_RATE) / (1 + FB.PRIOR_STARTS)) < 1e-9
    assert sh["Sam Hauser"] > 0.15, sh
    # A starter who never shoots early still starts: a seat at the prior.
    assert "Jaylen Brown" in sh and sh["Jaylen Brown"] > 0.1
    # The man sent to the bench keeps BENCH of his rate.
    assert abs(f["w"]["Derrick White"] - FB.BENCH * f["rate"]["Derrick White"]) < 1e-9
    assert sh["Derrick White"] < 0.03 < sh["Payton Pritchard"]
    # The star still leads, and no longer takes three in four.
    assert max(sh, key=sh.get) == "Jayson Tatum" and 0.25 < sh["Jayson Tatum"] < 0.5, sh
    old = FB.shares(FB._as_built(data, "BOS"))
    assert old["Jayson Tatum"] > 0.7 and "Jaylen Brown" not in old and old["Derrick White"] > sh["Derrick White"]
    rows = FB.game_probs(data, "BOS", "NYK")
    assert abs(sum(r["prob"] for r in rows) - 1.0) < 1e-9
    top = rows[0]
    assert top["player"] == "Jayson Tatum" and top["in_five"] is True and top["per_start"] > 1.0


def test_a_returning_starter_joins_the_five_only_when_priced_with_his_club():
    conn = _history()
    _lineup_games(conn)
    data = FB.read(conn, 2026, before="2026-10-31")
    assert "Kristaps Porzingis" not in FB.candidates(data, "BOS"), "nothing says he plays tonight"
    back = FB.five(data, "BOS", plays={"Kristaps Porzingis": "BOS", "Jayson Tatum": "BOS"})
    assert "Kristaps Porzingis" in back["five"] and len(back["five"]) == 6
    moved = FB.five(data, "BOS", plays={"Kristaps Porzingis": "DAL", "Payton Pritchard": "DAL"})
    assert "Kristaps Porzingis" not in moved["w"] and "Payton Pritchard" not in moved["w"], \
        "a man priced with another club tonight is no candidate here"
    assert "Derrick White" in moved["five"], "the five is filled from the busiest candidates"


def test_a_starter_ruled_out_leaves_the_five_and_the_busiest_candidate_fills_it():
    conn = _history()
    _lineup_games(conn)
    data = FB.read(conn, 2026, before="2026-10-31")
    f = FB.five(data, "BOS", out={"jaylen brown"})
    assert "Jaylen Brown" not in f["w"]
    assert f["five"] == {"Jayson Tatum", "Jrue Holiday", "Sam Hauser", "Payton Pritchard", "Derrick White"}
    assert FB.five(data, "NYK")["five"] == set(NYK_FIVE)
    assert FB.five(FB.read(_history(), 2026), "BOS") is None, "no box scores: the board as built"


def test_a_pick_on_tonights_five_says_so():
    conn = _history()
    _lineup_games(conn)
    games = [{"home": "BOS", "away": "NYK", "date": "2026-10-31", "kickoff": "2026-10-31T23:30:00Z"}]
    quotes = {"a": _quote("Sam Hauser", "BOS", "NYK", 1600)}
    b = FB.board(quotes, games, conn=conn, date="2026-10-31")
    row = b["rows"][0]
    assert row["player"] == "Sam Hauser" and "likely starting five tonight" in row["reasons"][1], row["reasons"]
    assert [p["player"] for p in b["picks"]] == ["Sam Hauser"], "his starter's chance against a bench man's price"
    bench = FB.board({"a": _quote("Derrick White", "BOS", "NYK", 1600)}, games, conn=conn, date="2026-10-31")
    assert "not in BOS's likely starting five" in bench["rows"][0]["reasons"][1]
    assert bench["picks"] == []


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
    # The box, 2026-10-31: no NBA prices bought all day, and the board said
    # they post closer to tip-off.
    assert FB.why_empty("matched 0 props across 0 events (cached)") == FB.WHY_BUDGET
    assert FB.why_empty("no odds requested — engine ran with no bettable prices") == FB.WHY_BUDGET
    assert FB.why_empty("matched 412 props across 7 events") == FB.WHY_LATER, \
        "props bought and no first-basket price yet: it posts later"


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


def test_a_price_on_a_man_ruled_out_is_never_a_pick():
    conn = _history()
    _games(conn)
    games = [{"home": "BOS", "away": "NYK", "date": "2026-10-31", "kickoff": "2026-10-31T23:30:00Z"}]
    quotes = {"a": _quote("Jayson Tatum", "BOS", "NYK", 300), "b": _quote("Derrick White", "BOS", "NYK", 400)}
    b = FB.board(quotes, games, conn=conn, date="2026-10-31", out={"jayson tatum"})
    assert [r["player"] for r in b["rows"]] == ["Derrick White"], b["rows"]
    assert all(p["player"] != "Jayson Tatum" for p in b["picks"])
    ours = FB.board({}, games, conn=conn, date="2026-10-31", out={"jayson tatum"})["ours"]
    assert "Jayson Tatum" not in {r["player"] for r in ours}


def test_the_nba_build_makes_the_board_and_journals_its_picks():
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert "why=odds_note, out=_fb_out," in src, "the build hands the board tonight's ruled-out men"
    assert "plays={pp.player: pp.team for pp in slate.props if pp.team})" in src, \
        "and the men it prices tonight, by club (a returning starter's confirmation)"
    assert "in OUT_STATUSES}" in src[src.index("_fb_out = "):src.index("_fb_out = ") + 300]
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
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
