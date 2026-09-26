"""Kalshi and Polymarket on every game, recorded, and measured.

Ethan, 2026-09-26: "we should also look into where we can use pollymarket
and kalshi odds for money lines and other bets since crowd betting is
more accurate ... we can study market swings ... usually a market has
swung a certain way when a large group of people already know the
answer ... we should audit our pollymarket and kalshi predictions."

The audit found Kalshi's price reached only the Pick of the Day, and
Polymarket's game markets were never read. And the Kalshi desk had two
holes:
  * it read the PUBLIC boards, where `game_bets` is stripped, so it has
    had no model number since the paywall went on;
  * it rebuilt the games without their moneylines, so its books-vs-Kalshi
    read never fired.

  * engine/sources/polysports parses a Polymarket game event into its
    moneyline and pins it to one of tonight's games;
  * engine/crowd hangs every venue's home-win chance on the game (never
    our model's — that is the paid card) and records it pregame;
  * engine/crowdfit joins the record to the finals: accuracy per source,
    whether the crowd knows what the books do not, whether swings run on.
"""
import json
import math
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import crowd, crowdfit                                   # noqa: E402
from engine.sources import polysports                                # noqa: E402

GAMES = [{"home": "KC", "away": "BUF", "home_name": "Kansas City Chiefs", "away_name": "Buffalo Bills",
          "date": "2026-09-28", "kickoff": "2026-09-29T00:20:00Z", "home_ml": -150, "away_ml": 130},
         {"home": "NYJ", "away": "MIA", "home_name": "New York Jets", "away_name": "Miami Dolphins",
          "date": "2026-09-28", "kickoff": "2026-09-28T17:00:00Z", "home_ml": 110, "away_ml": -130}]

EVENT = {"slug": "nfl-buf-kc-2026-09-28", "startDate": "2026-09-29T00:20:00Z", "markets": [
    {"slug": "nfl-buf-kc-2026-09-28", "question": "Bills vs. Chiefs", "sportsMarketType": "moneyline",
     "outcomes": "[\"Bills\", \"Chiefs\"]", "outcomePrices": "[\"0.41\", \"0.59\"]",
     "bestBid": 0.40, "bestAsk": 0.42, "liquidity": "25000", "volume24hr": 90000,
     "gameStartTime": "2026-09-29 00:20:00+00"},
    {"slug": "nfl-buf-kc-spread", "question": "Spread: Chiefs (-2.5)", "sportsMarketType": "spreads",
     "outcomes": "[\"Chiefs\", \"Bills\"]", "outcomePrices": "[\"0.5\", \"0.5\"]"},
    {"slug": "nfl-buf-kc-total", "question": "Bills vs. Chiefs: O/U 47.5",
     "outcomes": "[\"Over\", \"Under\"]", "outcomePrices": "[\"0.5\", \"0.5\"]"}]}

KALSHI = [{"ticker": "KXNFLGAME-26SEP28BUFKC-KC", "event_ticker": "KXNFLGAME-26SEP28BUFKC",
           "title": "Kansas City wins", "subtitle": "", "prob": 0.61, "price_basis": "book",
           "spread_cents": 2.0, "volume_24h": 5000.0, "open_interest": 9000.0}]

BETS = [{"bet_type": "moneyline", "home": "KC", "away": "BUF", "pick_is_home": False, "team": "BUF",
         "win_prob": 0.43, "engine_raw_prob": 0.47}]


# --- Polymarket -------------------------------------------------------------------
def test_a_game_event_yields_its_moneyline_only():
    rows = polysports.parse_events([EVENT])
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["teams"] == ["Bills", "Chiefs"] and r["prob"] == 0.41 and r["price_basis"] == "book"
    assert r["spread_cents"] == 2.0 and r["liquidity"] == 25000.0


def test_it_is_pinned_to_one_game_the_right_way_round():
    r = polysports.parse_events([EVENT])[0]
    g, first_home = polysports.match_game(r, GAMES)
    assert g["home"] == "KC" and first_home is False
    assert polysports.p_home(r, first_home) == 0.59
    far = dict(r, start="2026-10-12T00:00:00")
    assert polysports.match_game(far, GAMES) == (None, None), "another week's meeting is another game"
    ohio = {"teams": ["Ohio", "Kent State"], "start": "2026-09-28", "prob": 0.6}
    osu = [{"home": "OSU", "away": "KENT", "home_name": "Ohio State Buckeyes", "away_name": "Kent State Golden Flashes",
            "date": "2026-09-28"}]
    g, _ = polysports.match_game(ohio, osu)
    assert g is not None, "every word of the venue's name is in ours"
    osu2 = [dict(osu[0], home_name="Ohio State Buckeyes"), {"home": "OHIO", "away": "KENT",
            "home_name": "Ohio Bobcats", "away_name": "Kent State Golden Flashes", "date": "2026-09-28"}]
    assert polysports.match_game(ohio, osu2) == (None, None), "two games match: refused, not guessed"


def test_a_dead_venue_costs_its_rows_not_the_build():
    orig = polysports.fetch_events
    polysports.fetch_events = lambda tag, **k: (_ for _ in ()).throw(OSError("blocked"))
    try:
        rows, report = polysports.fetch_sports(["cfb"])
    finally:
        polysports.fetch_events = orig
    assert rows == [] and report == {"cfb": "error"}, "one error, and the aliases are not tried"


# --- the crowd on the game --------------------------------------------------------
def _board():
    return {"games": [dict(g) for g in GAMES], "game_bets": [dict(b) for b in BETS]}


def test_every_venue_hangs_on_the_game_and_our_number_does_not():
    b = _board()
    poly = [dict(r, sport="nfl") for r in polysports.parse_events([EVENT])]
    census = crowd.attach(b, "nfl", KALSHI, poly)
    c = b["games"][0]["crowd"]
    assert c["kalshi"] == 0.61 and c["polymarket"] == 0.59 and c["crowd"] == 0.6
    assert abs(c["books"] - 0.5798) < 0.002 and c["gap_pts"] == round((0.6 - c["books"]) * 100, 1)
    assert "model" not in c and "model_raw" not in c, "the moneyline card is the members'"
    assert "crowd" not in b["games"][1], "a game no venue priced carries nothing"
    assert census == {"games": 2, "kalshi": 1, "polymarket": 1}


def test_a_wide_or_thin_book_is_not_a_price():
    b = _board()
    wide = [dict(KALSHI[0], spread_cents=9.0)]
    thin = [dict(r, sport="nfl", liquidity=50.0, volume_24h=10.0) for r in polysports.parse_events([EVENT])]
    crowd.attach(b, "nfl", wide, thin)
    assert "crowd" not in b["games"][0]


def test_the_record_is_pregame_only_with_our_numbers_beside_it():
    b = _board()
    crowd.attach(b, "nfl", KALSHI, [])
    b["games"][1]["crowd"] = {"kalshi": 0.4}
    conn = sqlite3.connect(":memory:")
    before_mia = 1790000000  # 2026-09-21: neither game has started
    n = crowd.store(conn, "nfl", b["games"], now=before_mia, game_bets=b["game_bets"])
    assert n == 2
    row = conn.execute("SELECT kalshi, books, model, model_raw FROM crowd_snaps WHERE home='KC'").fetchone()
    assert row[0] == 0.61 and row[2] == 0.57 and row[3] == 0.53, "the pick was the away club: turned to home"
    after_nyj = 1790632800   # 2026-09-28 22:00Z: MIA@NYJ under way, KC not
    n = crowd.store(conn, "nfl", b["games"], now=after_nyj, game_bets=b["game_bets"])
    assert n == 1
    b["games"][0]["live"] = {"state": "live"}
    assert crowd.started(b["games"][0])
    football = {"date": "2026-09-28", "kickoff": "20:20"}
    assert not crowd.started(football, now=1790632800) and crowd.started(football, now=1790643600)


def test_the_hook_never_raises_and_says_what_it_did():
    b = _board()
    boom = lambda: (_ for _ in ()).throw(RuntimeError("down"))      # noqa: E731
    line = crowd.attach_to_board(b, "nfl", kalshi_fetch=boom, poly_fetch=boom, record=False)
    assert "Kalshi unavailable" in line and "Polymarket unavailable" in line
    line = crowd.attach_to_board(b, "nfl", kalshi_fetch=lambda: (KALSHI, {}),
                                 poly_fetch=lambda: ([], {"nfl": 0}), record=False)
    assert "Kalshi on 1" in line and b["crowd_census"]["kalshi"] == 1


def test_every_build_calls_the_hook():
    for f, arg in (("nfl_build.py", '(result, "nfl")'), ("mlb_build.py", '(result, "mlb")'),
                   ("cfb_build.py", '(out, "cfb")'), ("nba_build.py", "(out, args.league)")):
        assert f"_crowd.attach_to_board{arg}" in (ROOT / f).read_text(), f


# --- the fit ----------------------------------------------------------------------
def _world(n=1500, crowd_skill=0.0, momentum=0.0, seed=7):
    """Games whose truth the books see with noise; Kalshi sees `crowd_skill`
    of the books' miss; a late swing carries `momentum` of what is left."""
    rnd = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    crowd.ensure_tables(conn)
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, home TEXT, away TEXT, "
                 "home_score REAL, away_score REAL, date TEXT)")
    lg = lambda p: math.log(p / (1 - p))                                     # noqa: E731
    sg = lambda z: 1 / (1 + math.exp(-z))                                     # noqa: E731
    for i in range(n):
        truth = rnd.gauss(0, 1.0)
        books = truth + rnd.gauss(0, 0.6)
        kal = books + crowd_skill * (truth - books) + rnd.gauss(0, 0.1)
        y = 1 if rnd.random() < sg(truth) else 0
        early = books - momentum * (truth - books) + rnd.gauss(0, 0.05)
        home, away, day = f"H{i}", f"A{i}", "2026-09-01"
        conn.execute("INSERT INTO games VALUES ('nfl',2026,?,?,?,?,?,?,?)",
                     (day, str(i), home, away, 21 if y else 17, 17 if y else 21, day))
        for ts, b in ((1000, early), (1000 + 7 * 3600, books)):
            conn.execute("INSERT INTO crowd_snaps (sport, date, away, home, bucket_ts, kalshi, books) "
                         "VALUES ('nfl',?,?,?,?,?,?)", (day, away, home, ts, round(sg(kal), 4), round(sg(b), 4)))
    del lg
    return conn


def test_the_fit_finds_a_crowd_that_knows_more_and_calls_it_measured():
    st = crowdfit.run(_world(crowd_skill=0.6), write=False)
    k = st["crowd_vs_books"]["kalshi"]
    assert k["beta"] > 0.3 and k["beta"] / k["se"] > 2, k
    assert k["verdict"].startswith("kalshi knows something the books do not")
    assert st["accuracy"]["kalshi"]["vs_books"]["brier_diff"] < 0, "more accurate than the books"


def test_the_fit_calls_a_copy_of_the_books_nothing():
    st = crowdfit.run(_world(crowd_skill=0.0), write=False)
    k = st["crowd_vs_books"]["kalshi"]
    assert abs(k["beta"]) / k["se"] < 2.5, k


def test_the_fit_finds_a_swing_that_keeps_going():
    st = crowdfit.run(_world(momentum=0.8), write=False)
    s = st["swings"]["books"]
    assert s["beta"] > 0 and s["beta"] / s["se"] > 2 and "keep going" in s["verdict"], s


def test_a_small_record_is_not_enough_games_yet():
    st = crowdfit.run(_world(n=60, crowd_skill=0.9), write=False)
    assert st["crowd_vs_books"]["kalshi"]["verdict"].startswith("not enough games yet (60 of 200)")
    assert "not enough games yet" in crowdfit.report(st)


# --- the desk -----------------------------------------------------------------------
def test_the_desk_reads_the_members_board_with_its_moneylines():
    import pm_build
    tmp = Path(tempfile.mkdtemp())
    web, built = tmp / "web" / "data", tmp / "data" / "built"
    web.mkdir(parents=True); built.mkdir(parents=True)
    game = {"home": "KC", "away": "BUF", "home_ml": -150, "away_ml": 130, "date": "2026-09-28"}
    (web / "recommendations.json").write_text(json.dumps({"games": [game], "game_bets": []}))
    (built / "recommendations.json").write_text(json.dumps({"games": [game], "game_bets": BETS}))
    games, probs = pm_build._tonights_games_and_probs(web)
    assert games["nfl"][0]["home_ml"] == -150 and games["nfl"][0]["away_ml"] == 130
    assert abs(probs[("nfl", "BUF@KC")] - 0.57) < 1e-9, "the model number is on the members' copy only"


def test_the_game_page_draws_the_venues_and_not_our_number():
    app = (ROOT / "web" / "js" / "app.js").read_text()
    i = app.index("function crowdStripHTML(")
    fn = app[i:app.index("\n}\n", i)]
    assert '["kalshi", "Kalshi"], ["polymarket", "Polymarket"], ["books", "Books"]]' in fn
    assert "model" not in fn.split("const cells")[1].split(";")[0]
    assert 'const gpCrowd = isFinal ? "" : crowdStripHTML(g);' in app and "${gpCrowd}" in app


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
