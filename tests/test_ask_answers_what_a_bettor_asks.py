"""Ask answers what a bettor actually asks.

Ethan, 2026-09-23: "Think of other questions a user would want to ask about
sports and shit and add it. It's a sport betting ai so it should be able to
answer." Each lookup below is a family of those questions, answered from
data the site already holds (engine/askbot.py):

  slate          what is on tonight, at what line, what is the weather
  our_picks      best bets, likeliest, long shots, game lines, parlays, pick of the day
  line_shop      the best price on a pick, and how its line has moved
  prop_hit_rate  how often he has cleared this line — last 5, last 10, season, vs a team
  team_trends    straight up / ATS / over-under: home, away, favorite, underdog
  injuries       is he playing, who is out
  schedule       when they play next, and how the last one went
  live_scores    the score now — never served from the answer cache
  futures        title, conference, division and playoff chances; win totals
  our_record     yesterday, this week, this month, and the settled bets themselves
  odds_calc      payouts, implied chances, parlays and the hold, done exactly

Every fixture is built in a temp directory; nothing here reads the box.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                # noqa: E402
from engine import db as _db                                   # noqa: E402

_TMP = Path(tempfile.mkdtemp())
DATA = _TMP / "web_data"
PAID = _TMP / "paid"
DATA.mkdir()
PAID.mkdir()
AB.CACHE_PATH = _TMP / "ask_cache.json"
AB.USAGE_PATH = _TMP / "ask_usage.json"
AB.UFC_PATH = str(_TMP / "no_fighters.json")
AB.ROSTER_DIR = str(_TMP / "rosters")
AB.PAID_DIR = str(PAID)
os.makedirs(AB.ROSTER_DIR, exist_ok=True)
TODAY = dt.date.today()
AGO = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()    # noqa: E731


def _history():
    path = _TMP / "history.db"
    conn = _db.connect(str(path))
    games = [  # season, week, home, away, home score, away score, HOME spread, total
        (2026, "002", "BUF", "DET", 41, 31, -1.5, 50.5),   # Lions +1.5 dogs away, lose by 10: no cover, over
        (2026, "001", "DET", "NO", 31, 30, -4.5, 47.5),    # Lions -4.5 at home, win by 1: no cover, over
        (2025, "017", "DET", "GB", 31, 24, -6.5, 51.5),    # home favourites, cover, over
        (2025, "012", "CHI", "DET", 23, 17, 3.0, 45.0),    # away favourites, lose, under
        (2025, "009", "GB", "DET", 20, 27, 2.5, 48.5),     # away favourites, cover, under
        (2025, "003", "NYJ", "DET", 13, 30, 7.5, 44.5),    # away favourites, cover, under
    ]
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, spread, total) "
        "VALUES ('nfl',?,?,?,?,?,?,?,?,?)",
        [(s, p, f"{h}{a}{s}{p}", h, a, hs, as_, sp, to) for s, p, h, a, hs, as_, sp, to in games])
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, spread, total, date) "
                 "VALUES ('nfl', 2026, '004', 'GBDET2026004', 'GB', 'DET', 1.5, 49.5, ?)", (AGO(-10),))
    rows = []
    for season, wk, opp, yds in ((2026, "002", "BUF", 45.0), (2026, "001", "NO", 95.0), (2025, "017", "GB", 110.0),
                                 (2025, "012", "CHI", 72.0), (2025, "009", "GB", 85.0), (2025, "003", "NYJ", 140.0)):
        rows.append(dict(sport="nfl", season=season, period=wk, game_id=f"G{season}{wk}", player="Jahmyr Gibbs",
                         team="DET", opponent=opp, position="RB", home=0, market="rush_yds", value=yds))
    _db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


AB.HISTORY_DB = str(_history())

NFL = {
    "sport": "nfl", "date": "2026-W03", "built_at": "2026-09-23T12:00:00",
    "games": [{"home": "NYJ", "away": "DET", "spread": 6.5, "favorite": "DET", "total": 45.5,
               "home_ml": 220, "away_ml": -270, "kickoff": "2026-09-27T17:00:00Z",
               "weather": {"temp_f": 61, "wind_mph": 9}, "stadium": {"plays": "Open-air, swirling."}}],
    "recommendations": [
        {"player": "Jahmyr Gibbs", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
         "market_label": "Rushing Yards", "side": "OVER", "line": 80.5, "odds": -112, "book": "FanDuel",
         "hit_prob": 0.57, "edge": 0.05, "recommended": True, "stake_units": 1.0,
         "all_lines": [{"book": "FanDuel", "line": 80.5, "over_odds": -112, "under_odds": -108},
                       {"book": "DraftKings", "line": 80.5, "over_odds": -105, "under_odds": -115},
                       {"book": "BetMGM", "line": 79.5, "over_odds": -120, "under_odds": 100}],
         "line_move": {"open": 77.5, "current": 80.5, "delta": 3.0, "direction": "up", "steam": True,
                       "verdict": "with", "moved_ago_min": 40, "first_mover": "Pinnacle"}}],
    "most_likely": [{"player": "Amon-Ra St. Brown", "team": "DET", "market": "receptions", "side": "OVER",
                     "line": 4.5, "odds": -190, "model_prob": 0.74},
                    {"player": "Garrett Wilson", "team": "NYJ", "market": "receptions", "side": "OVER",
                     "line": 4.5, "odds": -160, "model_prob": 0.69}],
    "long_shots": [{"player": "Sam LaPorta", "team": "DET", "market": "anytime_td", "odds": 320, "edge": 0.03}],
    "game_bets": [{"matchup": "DET @ NYJ", "pick_label": "Lions -6.5", "market": "spread", "odds": -110,
                   "win_prob": 0.58, "home": "NYJ", "away": "DET", "team": "DET"}],
    "parlays": {"tickets": [{"grade": "play", "likely_case_american": 264, "modeled_joint": 0.29,
                             "legs": [{"player": "Jahmyr Gibbs", "side": "OVER", "line": 80.5,
                                       "market_label": "Rushing Yards", "odds": -112},
                                      {"player": "Amon-Ra St. Brown", "side": "OVER", "line": 4.5,
                                       "market_label": "Receptions", "odds": -190}]}]},
    "pick_of_the_day": {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER", "line": 80.5,
                        "odds": -112, "hit_prob": 0.57},
}
MLB = {
    "sport": "mlb", "date": "2026-09-23", "built_at": "2026-09-23T11:00:00",
    "games": [{"home": "NYY", "away": "BOS", "total": 8.5, "home_ml": -150, "away_ml": 130}],
    "recommendations": [{"player": "Aaron Judge", "team": "NYY", "opponent": "BOS", "market": "hits",
                         "side": "OVER", "line": 0.5, "odds": -180, "hit_prob": 0.7, "edge": 0.08,
                         "recommended": True, "stake_units": 1.0}],
}
BOARDS = {"nfl": NFL, "mlb": MLB}

(DATA / "live_nfl.json").write_text(json.dumps({"generated_at": "2026-09-23T20:00:00Z", "games": [
    {"home": "NYJ", "away": "DET", "home_name": "New York Jets", "away_name": "Detroit Lions",
     "live": {"state": "live", "home_score": 10, "away_score": 14, "period": 3, "clock": "5:12",
              "detail": "3rd 5:12", "win_prob": {"home": 0.31}}}]}))
(DATA / "injuries.json").write_text(json.dumps({"generated_at": "2026-09-23T09:00:00Z", "sports": {"nfl": [
    {"player": "Sam LaPorta", "team": "DET", "status": "Questionable", "injury": "back", "position": "TE"},
    {"player": "Breece Hall", "team": "NYJ", "status": "Out", "injury": "knee", "position": "RB"}]}}))
(DATA / "record.json").write_text(json.dumps({
    "record_epoch": "2026-08-06",
    "pooled": {"overall": {"settled": 60, "wins": 34, "losses": 26, "roi": 0.031, "net_units": 3.2},
               "curve": [{"date": AGO(40), "w": 5, "l": 0, "day_u": 4.5}, {"date": AGO(3), "w": 1, "l": 2, "day_u": -1.1},
                         {"date": AGO(1), "w": 3, "l": 1, "day_u": 1.8}]},
    "by_sport": {"nfl": {"pooled": {"overall": {"settled": 20, "wins": 12, "losses": 8}},
                         "curve": [{"date": AGO(1), "w": 2, "l": 0, "day_u": 1.9}]}}}))
(PAID / "futures_nfl.json").write_text(json.dumps({"season": 2026, "prior_weight": 0.62, "teams": [
    {"team": "BUF", "wins": 2, "losses": 0, "proj_wins": 12.14, "proj_wins_lo": 9.0, "proj_wins_hi": 14.0,
     "p_playoffs": 0.884, "p_division": 0.7, "p_conference": 0.31, "p_title": 0.171},
    {"team": "DET", "wins": 1, "losses": 1, "proj_wins": 10.4, "proj_wins_lo": 8.0, "proj_wins_hi": 13.0,
     "p_playoffs": 0.71, "p_division": 0.44, "p_conference": 0.18, "p_title": 0.09}],
    "season_totals": [{"market": "rush_yds", "label": "Rushing Yards", "players": [
        {"player": "Jahmyr Gibbs", "team": "DET", "banked": 140.0, "mean": 1420.52, "games_left": 15}]}]}))
(PAID / "ufc.json").write_text(json.dumps({"event_date": "UFC 320", "picks": [
    {"fight": "Alex Pereira vs Magomed Ankalaev", "pick": "Alex Pereira", "odds": 110, "model_prob": 0.55,
     "edge": 0.07}], "pass_list": [{"fight": "Two Unpriced vs Fighters", "why": "no price"}]}))


def _ledger():
    from engine import ledger as L
    path = _TMP / "ledger.db"
    conn = L.connect(str(path))
    for player, status, pnl in (("Jahmyr Gibbs", "won", 0.89), ("Sam LaPorta", "lost", -1.0)):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, book, odds, hit_prob, grade, "
                     "stake_units, status, pnl_units, category) VALUES ('nfl', ?, ?, 'rush_yds', 'OVER', 80.5, "
                     "'FanDuel', -112, 0.57, 'A', 1.0, ?, ?, 'main')", (AGO(1), player, status, pnl))
    conn.commit()
    conn.close()
    return path


AB.LEDGER_DB = str(_ledger())


def _run(name, **args):
    return AB.run_tool(name, args, BOARDS, "nfl", DATA)


# --- tonight -----------------------------------------------------------------------------
def test_the_slate_every_league_or_one_with_the_score_when_it_has_started():
    both = _run("slate")
    assert [s["sport"] for s in both["slates"]] == ["nfl", "mlb"], "the open league first, then the rest"
    game = both["slates"][0]["games"][0]
    assert game["game"] == "DET @ NYJ" and game["spread"] == 6.5 and game["total"] == 45.5
    assert game["weather"] == {"temp_f": 61, "wind_mph": 9} and "stadium_note" not in game
    assert game["now"] == {"state": "live", "score": "DET 14, NYJ 10", "period": 3, "clock": "5:12",
                           "detail": "3rd 5:12"}, "a started game carries its score"
    assert [s["sport"] for s in _run("slate", sport="mlb")["slates"]] == ["mlb"]
    ufc = _run("slate", sport="ufc")
    assert ufc["event"] == "UFC 320" and ufc["fights"] == ["Alex Pereira vs Magomed Ankalaev",
                                                         "Two Unpriced vs Fighters"]
    assert _run("slate", sport="nba")["found"] is False


def test_our_picks_by_kind_on_one_board_or_all():
    best = _run("our_picks", kind="best_bets", sport="all")
    assert [(r["league"], r["player"]) for r in best["rows"]] == [("mlb", "Aaron Judge"), ("nfl", "Jahmyr Gibbs")], \
        "every league's staked bets, the biggest edge first"
    likely = _run("our_picks", kind="most_likely")
    assert [r["player"] for r in likely["rows"]] == ["Amon-Ra St. Brown", "Garrett Wilson"]
    assert _run("our_picks", kind="long_shots")["rows"][0]["player"] == "Sam LaPorta"
    assert _run("our_picks", kind="game_lines")["rows"][0]["pick_label"] == "Lions -6.5"
    ticket = _run("our_picks", kind="parlays")["rows"][0]
    assert ticket == {"league": "nfl", "pool": "edge", "grade": "play", "price": 264, "model_chance": 0.29,
                      "legs": ["Jahmyr Gibbs OVER 80.5 Rushing Yards (-112)",
                               "Amon-Ra St. Brown OVER 4.5 Receptions (-190)"]}
    assert _run("our_picks", kind="pick_of_the_day")["rows"][0]["player"] == "Jahmyr Gibbs"
    ufc = _run("our_picks", kind="best_bets", sport="ufc")
    assert ufc["rows"][0]["pick"] == "Alex Pereira" and ufc["rows"][0]["odds"] == 110
    assert _run("our_picks", kind="locks")["error"].startswith("kind is one of")


def test_the_best_price_and_how_the_line_moved():
    shop = _run("line_shop", query="Gibbs")["picks"][0]
    assert shop["pick"] == "Jahmyr Gibbs OVER 80.5 Rushing Yards" and shop["our_price"] == -112
    assert shop["best_price_at_this_line"] == {"book": "DraftKings", "odds": -105}, \
        "the best over at 80.5, not BetMGM's shorter line"
    assert [b["book"] for b in shop["books"]] == ["FanDuel", "DraftKings", "BetMGM"]
    assert shop["line_move"] == {"open": 77.5, "current": 80.5, "delta": 3.0, "direction": "up", "steam": True,
                                 "verdict": "with", "moved_ago_min": 40}
    assert _run("line_shop", query="Nobody")["found"] is False


# --- history, for bettors ------------------------------------------------------------------
def test_how_often_he_goes_over_the_line():
    hr = _run("prop_hit_rate", player="Gibbs", stat="rushing yards")
    assert hr["line"] == 80.5 and hr["tonight"]["odds"] == -112, "no line given: tonight's, from the board"
    assert hr["last_5"] == {"games": 5, "over": 3, "under": 2, "over_hit_rate": 0.6, "average": 81.4}
    assert hr["last_10"]["over"] == 4 and hr["last_10"]["games"] == 6
    assert hr["season_2026"] == {"games": 2, "over": 1, "under": 1, "over_hit_rate": 0.5, "average": 70}
    vs = _run("prop_hit_rate", player="Jahmyr Gibbs", stat="rush_yds", line=100, side="under", opponent="Packers")
    assert vs["against"] == {"opponent": "Packers", "games": 2, "over": 1, "under": 1, "under_hit_rate": 0.5,
                             "average": 97.5}
    assert _run("prop_hit_rate", player="Gibbs", stat="rush_yds", line=85)["last_5"]["push"] == 1, \
        "a push is counted, and out of the rate"
    assert _run("prop_hit_rate", player="Gibbs", stat="sacks", line=1)["error"].startswith("the NFL stats")


def test_betting_splits_home_away_favorite_underdog():
    t = _run("team_trends", team="Lions")
    assert (t["team"], t["season"]) == ("Detroit Lions", 2026)
    s = t["this_season"]
    assert s["overall"] == {"games": 2, "record": "1-1", "ats": "0-2", "over_under": "2 over, 0 under"}
    assert s["home"]["record"] == "1-0" and s["away"]["record"] == "0-1"
    assert s["as_favorite"]["games"] == 1 and s["as_underdog"] == {"games": 1, "record": "0-1", "ats": "0-1",
                                                                 "over_under": "1 over, 0 under"}
    assert t["last_10"] == {"games": 6, "record": "4-2", "ats": "3-3", "over_under": "3 over, 3 under"}
    assert t["every_stored_game"]["away"]["ats"] == "2-2"
    assert _run("team_trends", team="Lions", season=2025)["this_season"]["overall"]["record"] == "3-1"


def test_injuries_a_team_a_player_a_league():
    det = _run("injuries", team="Lions")
    assert [r["player"] for r in det["rows"]] == ["Sam LaPorta"] and det["rows"][0]["status"] == "Questionable"
    assert _run("injuries", player="Breece Hall")["rows"][0]["status"] == "Out"
    assert _run("injuries", sport="nfl")["count"] == 2
    assert _run("injuries", team="Bears")["found"] is False


def test_when_they_play_next():
    s = _run("schedule", team="Lions")
    assert s["team"] == "Detroit Lions" and s["upcoming"][0]["on_tonights_board"] is True
    assert s["upcoming"][0]["game"] == "DET @ NYJ"
    assert s["upcoming"][1] == {"game": "DET @ GB", "when": "2026 week 4", "home_spread": 1.5, "total": 49.5}, \
        "a stored fixture after tonight's"
    assert s["last_game"]["result"] == "L 31-41"


def test_the_score_now_and_it_is_never_cached():
    s = _run("live_scores", team="Lions")
    g = s["scoreboards"][0]["games"][0]
    assert g["score"] == "DET 14, NYJ 10" and g["state"] == "live" and g["home_win_prob"] == 0.31
    assert s["scoreboards"][0]["as_of"] == "2026-09-23T20:00:00Z", "and how old it is"
    assert _run("live_scores", sport="nba")["found"] is False
    AB.CACHE_PATH.unlink(missing_ok=True)
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if calls["n"] % 2:
            blk = types.SimpleNamespace(type="tool_use", id=f"t{calls['n']}", name="live_scores",
                                        input={"team": "Lions"})
            return types.SimpleNamespace(content=[blk], stop_reason="tool_use", usage=None)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Lions up 14-10.")],
                                     stop_reason="end_turn", usage=None)
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    for _ in range(2):
        out = AB.ask(NFL, "What's the score of the Lions game?", client=client, boards=BOARDS,
                     board_name="recommendations.json", data_dir=DATA)
        assert out["cached"] is False
    assert calls["n"] == 4, "asked twice, looked up twice: a score is stale in minutes"


def test_futures_title_and_playoff_chances():
    f = _run("futures", sport="nfl")
    assert [r["team"] for r in f["rows"]] == ["Buffalo Bills", "Detroit Lions"]
    assert f["rows"][0] == {"team": "Buffalo Bills", "record": "2-0", "projected_wins": 12.1,
                            "projected_range": "9-14", "playoffs_chance": 0.884, "division_chance": 0.7,
                            "conference_chance": 0.31, "title_chance": 0.171}
    assert f["share_resting_on_preseason_ratings"] == 0.62
    assert f["season_totals"][0]["projected_leaders"][0] == {"player": "Jahmyr Gibbs", "team": "DET",
                                                            "banked": 140.0, "mean": 1420.5, "games_left": 15}
    assert [r["team"] for r in _run("futures", sport="nfl", team="Lions")["rows"]] == ["Detroit Lions"]
    assert _run("futures", sport="nba")["found"] is False


def test_our_record_by_window_and_the_bets_themselves():
    r = _run("our_record", window="yesterday")
    assert r["yesterday"] == {"wins": 3, "losses": 1, "net_units": 1.8, "days_with_bets": 1}
    assert _run("our_record", window="last_7_days")["last_7_days"]["net_units"] == 0.7
    assert _run("our_record", sport="nfl", window="yesterday")["yesterday"]["wins"] == 2
    assert _run("our_record", window="today")["today"] == "no settled bets in that window"
    bets = _run("our_record", bets=True, window="last_7_days")
    assert bets["settled_bets_matching"] == 2 and {b["status"] for b in bets["settled_bets"]} == {"won", "lost"}
    lost = _run("our_record", result="lost")
    assert [b["player"] for b in lost["settled_bets"]] == ["Sam LaPorta"]


def test_odds_arithmetic_is_done_not_guessed():
    o = _run("odds_calc", odds=["+150"], stake=20)
    assert o["each"][0] == {"odds": "+150", "decimal": 2.5, "implied_chance": 0.4, "profit": 30.0, "payout": 50.0}
    p = _run("odds_calc", odds=["-110", "-110", "-110"])
    assert p["parlay"]["odds"] == "+596" and p["parlay"]["payout"] == 695.79
    two = _run("odds_calc", odds=["-110", "-110"])
    assert two["as_two_sides_of_one_market"] == {"hold": 0.0476, "fair_chances": [0.5, 0.5]}
    assert "as_two_sides_of_one_market" not in _run("odds_calc", odds=["-110", "+150"]), \
        "prices that cannot be one market's two sides get no hold"
    assert _run("odds_calc", odds=["50"])["error"].startswith("50 is not American odds")


def test_every_lookup_is_offered_and_the_prompt_uses_them():
    names = [t["name"] for t in AB.TOOLS]
    for n in ("slate", "our_picks", "line_shop", "prop_hit_rate", "team_trends", "injuries", "schedule",
              "live_scores", "futures", "our_record", "odds_calc"):
        assert n in names, n
    system = " ".join(AB.SYSTEM.split())
    assert "any payout, implied chance, parlay price or hold comes from odds_calc" in system
    assert "scores only from live_scores" in system
    assert "You may explain how betting works in general terms" in system
    assert AB.NO_CACHE_TOOLS >= {"live_scores"}


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
            traceback.print_exc(limit=2)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
