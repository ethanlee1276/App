"""Ask reads every feed the site publishes, not just the boards.

Ethan, 2026-09-23: "make sure the AI chat is pulling live data and all that
shit that we usually access and have keys for… make sure we're using and
accessing all the data we have access to." Everything the refresher pulls
with the site's keys (the odds feed, CFBD, Kalshi, ESPN) lands on disk, and
before this Ask read only the boards, the injury board, the live scores, the
futures and the record. Each lookup below is one more of those files:

  standings           the league's own table, the playoff seeds, clutch numbers
  roster              the depth chart, who is out, recent signings and trades
  news                headlines, newest first, never the article
  book_report         which book prices sharpest and moves first
  prediction_markets  Kalshi against the books and our model; Polymarket
  market_moves        the live feed: edges appearing and dying, line moves
  our_picks_live      our open bets right now, and our parlays' live chances
  team_efficiency     EPA per play, PROE, pace, with ranks
  fantasy             usage, buy-low and sell-high, waivers, streamers, trends
  live_scores (ufc)   tonight's bouts
  our_picks (top_pick_today), the injury history, a pick's line since it
  opened, the MLB starters, park and umpire, and when every board was built.

Every fixture is built in a temp directory; nothing here reads the box.
"""
import json
import sys
import tempfile
import time
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
AB.PAID_DIR = str(PAID)


def _put(where: Path, name: str, blob: dict) -> None:
    (where / name).write_text(json.dumps(blob))


def _history():
    path = _TMP / "history.db"
    conn = _db.connect(str(path))
    weeks = []
    #            off_epa, def_epa, pass,  rush,  proe,  pace, plays
    for team, (oe, de, pe, re_, proe, pace, plays) in {
            "DET": (0.15, -0.08, 0.25, 0.05, 0.03, 27.0, 66),
            "GB": (0.05, 0.02, 0.10, -0.01, -0.02, 29.5, 62),
            "CHI": (-0.10, 0.10, -0.15, -0.04, 0.06, 26.0, 70)}.items():
        for wk in (1, 2, 3, 4):
            weeks.append(("nfl", 2026, f"{wk:03d}", team, plays, proe, oe, pe, re_, de, pace))
    conn.executemany("INSERT INTO team_weeks (sport, season, period, team, plays, proe, off_epa, pass_epa, "
                     "rush_epa, def_epa, pace) VALUES (?,?,?,?,?,?,?,?,?,?,?)", weeks)
    conn.executemany("INSERT INTO injury_events (sport, player, team, status, posted_at, first_seen, injury, pos) "
                     "VALUES (?,?,?,?,?,?,?,?)",
                     [("nfl", "Sam LaPorta", "DET", "Questionable", "W3-a", "2026-09-20T10:00:00", "back", "TE"),
                      ("nfl", "Sam LaPorta", "DET", "Out", "W2-a", "2026-09-13T10:00:00", "back", "TE"),
                      ("nfl", "Jared Goff", "DET", "Questionable", "W1-a", "2026-09-06T10:00:00", "thumb", "QB")])
    conn.commit()
    conn.close()
    return path


AB.HISTORY_DB = str(_history())

NOW = time.time()
SERIES = [{"ts": NOW - 60 * m, "line": ln, "odds": -110, "book": "FanDuel", "books": 3}
          for m, ln in ((600, 74.5), (540, 75.5), (480, 76.5), (420, 77.5), (360, 78.5), (300, 79.5),
                        (240, 79.5), (180, 80.5), (60, 80.5))]
NFL = {
    "sport": "nfl", "date": "2026-W03", "built_at": "2026-09-23T12:00:00",
    "games": [{"home": "NYJ", "away": "DET", "spread": 6.5, "total": 45.5}],
    "recommendations": [
        {"player": "Jahmyr Gibbs", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
         "market_label": "Rushing Yards", "side": "OVER", "line": 80.5, "odds": -112, "book": "FanDuel",
         "hit_prob": 0.57, "edge": 0.05, "recommended": True, "stake_units": 1.0,
         "all_lines": [{"book": "FanDuel", "line": 80.5, "over_odds": -112, "under_odds": -108}],
         "line_series": SERIES}],
    "live_picks": [
        {"player": "Jahmyr Gibbs", "market_label": "Rushing Yards", "side": "OVER", "line": 80.5, "odds": -112,
         "phase": "live", "status": "on_pace", "current": 52, "live_prob": 0.66, "pregame_prob": 0.57,
         "headshot": "https://x/y.png", "game": {"home": "NYJ", "away": "DET", "state": "in"}},
        {"player": "Nobody Known", "status": "unmapped", "phase": "upcoming"}],
    "live_potd": [
        {"player": "Amon-Ra St. Brown", "market_label": "Receptions", "side": "OVER", "line": 6.5, "odds": -120,
         "phase": "live", "status": "hit", "current": 7, "live_prob": 1.0, "pregame_prob": 0.61}],
}
MLB = {
    "sport": "mlb", "generated_at": "2026-09-23T11:30:00",
    "games": [{"home": "NYY", "away": "BOS", "total": 8.5, "home_ml": -150, "away_ml": 130,
               "park_name": "Yankee Stadium", "factors": {"hr": 1.12, "run": 1.04, "k": 0.98},
               "lineups_confirmed": False, "plate_umpire": "Angel Hernandez", "ump_k_factor": 0.95,
               "pitchers": {"home": {"name": "Gerrit Cole", "throws": "R", "xera": 3.21, "k_rate": 0.29},
                            "away": {"name": "Brayan Bello", "throws": "R", "xera": 4.05}},
               "weather": {"dome": False, "temp_f": 71, "wind_mph": 11, "wind_dir": "out", "rain": False}}],
}
BOARDS = {"nfl": NFL, "mlb": MLB}

_put(DATA, "heartbeat.json", {"at": "2026-09-23T12:01:00", "interval_s": 60})
_put(DATA, "standings_nfl.json", {
    "sport": "nfl", "season": 2026, "source": "league", "generated_at": "2026-09-23T06:00:00",
    "order_note": "the league's own records",
    "groups": [
        {"conference": "NFC", "division": "North", "label": "NFC North", "teams": [
            {"rank": 1, "team": "DET", "record": "3-0", "pct": 1.0, "games": 3, "pf_per_game": 31.0,
             "pa_per_game": 20.3, "diff": 32, "home": "2-0", "away": "1-0", "streak_label": "W3",
             "last10_label": "3-0", "results": ["W", "W", "W"]},
            {"rank": 2, "team": "GB", "record": "2-1", "pct": 0.667, "games": 3, "pf_per_game": 24.0,
             "pa_per_game": 22.0, "diff": 6, "home": "1-0", "away": "1-1", "streak_label": "L1",
             "last10_label": "2-1"}]},
        {"conference": "AFC", "division": "East", "label": "AFC East", "teams": [
            {"rank": 1, "team": "BUF", "record": "2-1", "pct": 0.667, "games": 3, "pf_per_game": 28.0,
             "pa_per_game": 19.0, "diff": 27, "home": "2-0", "away": "0-1", "streak_label": "W1",
             "last10_label": "2-1"}]}],
    "projected_seeds": [{"conference": "NFC", "seeds": [{"seed": 1, "team": "DET", "record": "3-0"}]}],
    "bracket": {"started": False},
    "pressure": {"season_used": 2025, "teams": {"DET": {"record": "15-2", "clutch": 0.8, "one_score_games": 5,
                                                        "reliability": 0.9, "fav_games": 12, "comeback": 0.5,
                                                        "dog_games": 2, "choke": 0.1, "games": 17}}}})
_put(DATA, "standings_nba.json", {"groups": [], "note": "Waiting on the 2026-27 season.",
                                  "first_games": "2026-10-20"})
_players = [{"player": f"Depth {i}", "team": "DET", "position": "WR", "depth_pos": "WR", "depth_order": i,
             "status": "Active"} for i in range(1, 30)]
_players[:0] = [
    {"player": "Jared Goff", "team": "DET", "position": "QB", "depth_pos": "QB", "depth_order": 1, "number": 16,
     "status": "Active", "age": 31, "college": "California", "unavailable": False},
    {"player": "Kyle Allen", "team": "DET", "position": "QB", "depth_pos": "QB", "depth_order": 2, "number": 8,
     "status": "Active"},
    {"player": "Hendon Hooker", "team": "DET", "position": "QB", "depth_pos": "QB", "depth_order": 3,
     "status": "Active"},
    {"player": "Sam LaPorta", "team": "DET", "position": "TE", "depth_pos": "TE", "depth_order": 1,
     "status": "Out", "injury": "Back", "unavailable": True}]
_put(DATA, "rosters_nfl.json", {"generated_at": "2026-09-23T07:00:00", "teams": {
    "DET": {"players": _players, "count": len(_players)},
    "GB": {"players": [{"player": "Jordan Love", "team": "GB", "position": "QB", "depth_pos": "QB",
                        "depth_order": 1, "status": "Active"}], "count": 1}},
    "transactions": {"moves": [{"player": "Kyle Allen", "from": "BUF", "to": "DET", "date": "2026-09-20"},
                               {"player": "Someone Else", "from": "NE", "to": "MIA", "date": "2026-09-21"}]}})
_put(DATA, "news.json", {"generated_at": "2026-09-23T11:00:00", "sports": {
    "nfl": [{"title": "Lions activate LaPorta from injured list", "link": "https://e/1", "source": "ESPN",
             "published": "2026-09-23T10:00:00", "epoch": 2},
            {"title": "Packers sign veteran kicker", "link": "https://e/2", "source": "ESPN",
             "published": "2026-09-23T09:00:00", "epoch": 1}],
    "nba": [{"title": "Camp opens next week", "link": "https://e/3", "source": "ESPN",
             "published": "2026-09-22T09:00:00", "epoch": 0}]}})
_put(DATA, "bookreport.json", {"generated_at": "2026-09-22T05:00:00", "note": "Measured from our snapshots.",
                               "books": [{"book": "Pinnacle", "n": 400, "mae_pts": 1.1, "lead_rate": 0.42,
                                          "ranked": True},
                                         {"book": "FanDuel", "n": 380, "mae_pts": 2.3, "lead_rate": 0.18,
                                          "ranked": True}],
                               "vs_list": {"measured_sharpest": ["Pinnacle"], "asserted_but_not": ["BetMGM"]}})
_put(DATA, "ufc_live.json", {"status": "live", "event": "UFC Fight Night", "generated_at": "2026-09-23T22:10:00",
                             "bouts": [{"fighters": [{"name": "A One", "winner": False}, {"name": "B Two"}],
                                        "status": {"state": "in", "live": True, "detail": "R2 3:10", "round": 2,
                                                   "clock": "3:10"}},
                                       {"fighters": [{"name": "C Three", "winner": True}, {"name": "D Four"}],
                                        "status": {"state": "post", "live": False, "detail": "KO R1"}}]})
_put(PAID, "kalshi.json", {"generated_at": "2026-09-23T12:00:00", "rows": [
    {"title": "Will Detroit beat New York?", "ticker": "K1", "sport": "nfl", "matchup": "DET@NYJ", "prob": 0.74,
     "spread_cents": 2, "volume_24h": 5200, "book_p": 0.71, "book_gap_pts": 3.0, "model_p": 0.69,
     "edge_pts": -5.0, "rec": True, "rec_side": "NO", "tape": [[1, 0.7]]},
    {"title": "Will Boston beat New York?", "ticker": "K2", "sport": "mlb", "matchup": "BOS@NYY", "prob": 0.44,
     "volume_24h": 900, "model_p": None, "edge_pts": None, "rec": False}]})
_put(PAID, "predmarkets.json", {"generated_at": "2026-09-23T12:00:00", "markets": [
    {"slug": "lions-sb", "question": "Will the Detroit Lions win the Super Bowl?", "yes": 0.12, "vol24": 81000,
     "liquidity": 1, "end_date": "2027-02-14"}]})
_put(PAID, "feed.json", {"generated_at": "2026-09-23T12:02:00", "events": [
    {"id": "e1", "ts": "2026-09-23T12:01:00", "sport": "nfl", "kind": "edge_appeared", "player": "Jahmyr Gibbs",
     "label": "Rushing Yards", "side": "OVER", "line": 80.5, "book": "FanDuel", "odds": -112,
     "digest": {"proj": 88.1}, "_seen": 1, "note": ""},
    {"id": "e2", "ts": "2026-09-23T11:40:00", "sport": "mlb", "kind": "line_move", "player": "Aaron Judge",
     "label": "Total Bases", "side": "OVER", "line": 2.5, "book": "DraftKings", "odds": 120, "from": 1.5, "to": 2.5},
    {"id": "e3", "ts": "2026-09-23T11:00:00", "sport": "mlb", "kind": "released", "n": 14,
     "players": ["Aaron Judge (Hits)", "Juan Soto (Hits)"]}]})
_put(PAID, "sweat.json", {"generated_at": "2026-09-23T20:30:00", "sport": "mlb", "parlays": [
    {"id": "p1", "book": "FanDuel", "n_legs": 2, "stake_units": 0.5, "pregame_joint": 0.3, "live_joint": 0.55,
     "legs": [{"player": "Aaron Judge", "market": "hits", "side": "OVER", "line": 0.5, "status": "won",
               "live_prob": 1.0}]}]})
_put(PAID, "day_top_pick.json", {"generated_at": "2026-09-23T12:00:00Z", "sport": "nfl", "leagues_seen": 4,
                                 "verdict": "top pick: Gibbs over 80.5",
                                 "pick": {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER",
                                          "line": 80.5, "odds": -112, "hit_prob": 0.57, "sport": "nfl"},
                                 "runners_up": [{"player": "Aaron Judge", "market": "hits", "side": "OVER",
                                                 "line": 0.5, "odds": -180, "sport": "mlb"}]})
_put(PAID, "fantasy.json", {"generated_at": "2026-09-23T08:00:00", "season": 2026,
                            "usage": [{"player": "Jahmyr Gibbs", "team": "DET", "position": "RB",
                                       "metric": "carry share", "season": 0.55, "last": 0.61, "delta": 0.06},
                                      {"player": "Jordan Love", "team": "GB", "position": "QB", "metric": "x"}],
                            "buy_sell": {"buy_low": [{"player": "Jayden Reed", "position": "WR", "gap": -4.1}],
                                         "sell_high": [{"player": "Tucker Kraft", "position": "TE", "gap": 5.0}],
                                         "band": 3.0},
                            "trending": {"adds": [{"player": "Rookie Back", "position": "RB", "count": 90000}],
                                         "drops": [], "lookback_hours": 24},
                            "streamers": {"QB": [{"player": "Jordan Love", "opponent": "CHI", "score": 1.2}],
                                          "TE": [{"player": "Sam LaPorta", "score": 0.4}]}})


def _run(name, **args):
    return AB.run_tool(name, args, BOARDS, "nfl", DATA)


def test_the_league_s_own_standings_by_division_with_seeds_and_clutch():
    whole = _run("standings", sport="nfl")
    assert whole["source"] == "the league's own standings" and whole["as_of"] == "2026-09-23T06:00:00"
    assert [g["group"] for g in whole["groups"]] == ["NFC North", "AFC East"]
    det = whole["groups"][0]["teams"][0]
    assert det["team"] == "Detroit Lions" and det["record"] == "3-0" and det["streak_label"] == "W3"
    assert "results" not in det, "the ordering detail stays home"
    assert whole["projected_playoff_seeds"] == [{"conference": "NFC", "seeds": ["1. Detroit Lions 3-0"]}]
    north = _run("standings", sport="nfl", group="NFC North")
    assert [t["team"] for t in north["groups"][0]["teams"]] == ["Detroit Lions", "Green Bay Packers"]
    assert len(north["groups"]) == 1 and "projected_playoff_seeds" not in north
    one = _run("standings", sport="nfl", team="Lions")
    assert [t["team"] for g in one["groups"] for t in g["teams"]] == ["Detroit Lions"]
    assert one["under_pressure"]["clutch"] == 0.8 and one["under_pressure"]["season"] == 2025
    wait = _run("standings", sport="nba")
    assert wait["found"] is False and wait["first_games"] == "2026-10-20" and "Waiting" in wait["note"]


def test_the_roster_as_a_depth_chart_and_the_team_a_player_is_on():
    r = _run("roster", team="Lions")
    assert r["team"] == "Detroit Lions" and r["count"] == 33 and r["shown"] == "the top two at each position"
    assert [p["player"] for p in r["players"] if p["position"] == "QB"] == ["Jared Goff", "Kyle Allen"]
    assert r["unavailable"] == ["Sam LaPorta (TE, Out)"]
    assert r["recent_moves"] == [{"player": "Kyle Allen", "from": "BUF", "to": "DET", "date": "2026-09-20"}]
    qbs = _run("roster", team="DET", position="qb")
    assert [p["player"] for p in qbs["players"]] == ["Jared Goff", "Kyle Allen", "Hendon Hooker"], \
        "one position comes whole"
    who = _run("roster", player="Jordan Love")
    assert who["players"][0]["team"] == "Green Bay Packers" and who["players"][0]["position"] == "QB"
    assert _run("roster")["error"]


def test_headlines_newest_first_filtered_and_never_cached():
    n = _run("news", sport="nfl")
    assert [h["title"] for h in n["rows"]] == ["Lions activate LaPorta from injured list", "Packers sign veteran kicker"]
    assert n["headlines_only"] is True and "link" not in n["rows"][0]
    assert [h["title"] for h in _run("news", query="Detroit Lions")["rows"]] == \
        ["Lions activate LaPorta from injured list"], "a word of the name is enough"
    assert len(_run("news")["rows"]) == 3, "every league when none is named"
    assert _run("news", query="Cowboys")["found"] is False
    assert "news" in AB.NO_CACHE_TOOLS


def test_the_book_report_card():
    b = _run("book_report")
    assert b["books"][0] == {"book": "Pinnacle", "early_price_error_pts": 1.1, "moves_first_rate": 0.42,
                             "snapshots": 400, "ranked": True}
    assert b["measured_sharpest"] == ["Pinnacle"] and b["asserted_but_not"] == ["BetMGM"]


def test_kalshi_against_the_books_and_our_model_and_polymarket():
    k = _run("prediction_markets", query="Lions")
    assert k["kalshi"] == [{"title": "Will Detroit beat New York?", "sport": "nfl", "matchup": "DET@NYJ",
                            "kalshi_yes_price": 0.74, "books_chance": 0.71, "kalshi_minus_books_pts": 3.0,
                            "our_model_chance": 0.69, "our_edge_pts": -5.0, "volume_24h": 5200,
                            "spread_cents": 2, "our_side": "NO"}]
    assert k["polymarket"][0]["polymarket_yes_price"] == 0.12
    assert [r["matchup"] for r in _run("prediction_markets", query="BOS")["kalshi"]] == ["BOS@NYY"], \
        "a team code in capitals finds its game"
    assert [r["sport"] for r in _run("prediction_markets", sport="mlb")["kalshi"]] == ["mlb"]
    assert _run("prediction_markets", query="Cowboys")["found"] is False


def test_the_live_market_feed_newest_first_and_never_cached():
    m = _run("market_moves")
    assert [e["kind"] for e in m["rows"]] == ["edge_appeared", "line_move", "released"]
    assert m["rows"][0] == {"ts": "2026-09-23T12:01:00", "sport": "nfl", "kind": "edge_appeared",
                            "player": "Jahmyr Gibbs", "label": "Rushing Yards", "side": "OVER", "line": 80.5,
                            "book": "FanDuel", "odds": -112}, "plain facts only: no id, nesting, private or blank"
    assert m["rows"][1]["from"] == 1.5
    assert m["rows"][2]["players"] == ["Aaron Judge (Hits)", "Juan Soto (Hits)"]
    assert [e["kind"] for e in _run("market_moves", sport="mlb", kind="line_move")["rows"]] == ["line_move"]
    assert [e["kind"] for e in _run("market_moves", player="Judge")["rows"]] == ["line_move", "released"]
    assert "market_moves" in AB.NO_CACHE_TOOLS
    AB.CACHE_PATH.unlink(missing_ok=True)
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if calls["n"] % 2:
            blk = types.SimpleNamespace(type="tool_use", id=f"t{calls['n']}", name="market_moves", input={})
            return types.SimpleNamespace(content=[blk], stop_reason="tool_use", usage=None)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Gibbs just cleared.")],
                                     stop_reason="end_turn", usage=None)
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    for _ in range(2):
        out = AB.ask(NFL, "Anything new moving?", client=client, boards=BOARDS,
                     board_name="recommendations.json", data_dir=DATA)
        assert out["cached"] is False and {"label": "Live market feed", "prop": ""} in out["sources"]
    assert calls["n"] == 4, "asked twice, looked up twice"


def test_our_bets_live_with_the_pick_of_the_day_and_the_parlays():
    live = _run("our_picks_live")
    assert [b["player"] for b in live["bets"]] == ["Amon-Ra St. Brown", "Jahmyr Gibbs"], \
        "the day's pick first, the unmapped row dropped"
    assert live["bets"][0]["pick_of_the_day"] is True
    g = live["bets"][1]
    assert g["current"] == 52 and g["live_prob"] == 0.66 and g["pregame_prob"] == 0.57
    assert g["game"] == "DET @ NYJ" and g["game_state"] == "in" and "headshot" not in g
    assert live["parlays"][0]["live_joint"] == 0.55 and live["parlays"][0]["legs"][0]["status"] == "won"
    assert _run("our_picks_live", sport="mlb") == {"parlays": live["parlays"],
                                                   "parlays_as_of": "2026-09-23T20:30:00"}
    assert "our_picks_live" in AB.NO_CACHE_TOOLS


def test_play_by_play_efficiency_ranked_the_right_way_round():
    det = _run("team_efficiency", team="Lions")
    assert det["team"] == "Detroit Lions" and det["weeks"] == 4 and det["teams"] == 3
    assert det["stats"]["off_epa"]["rank"] == 1 and det["stats"]["def_epa"]["rank"] == 1, \
        "the fewest EPA allowed is the best defense"
    assert det["stats"]["pace"]["rank"] == 2, "fewer seconds per snap is faster"
    assert det["stats"]["def_epa"]["league_average"] == round((-0.08 + 0.02 + 0.10) / 3, 4)
    best = _run("team_efficiency", sort="def_epa")
    assert [r["team"] for r in best["rows"]] == ["Detroit Lions", "Green Bay Packers", "Chicago Bears"]
    worst = _run("team_efficiency", sort="def_epa", order="worst")
    assert [r["team"] for r in worst["rows"]][0] == "Chicago Bears" and worst["rows"][0]["rank"] == 3
    style = _run("team_efficiency", sort="proe", order="worst")
    assert style["order"] == "most first" and style["rows"][0]["team"] == "Chicago Bears", \
        "passing more is a style, not a grade: worst does not flip it"
    assert _run("team_efficiency", last_n=2)["window"] == "last 2 weeks"
    assert _run("team_efficiency", season=2019)["found"] is False
    assert _run("team_efficiency", sort="yards")["error"]


def test_the_fantasy_desk():
    use = _run("fantasy", view="usage", player="Gibbs")
    assert use["usage"] == [{"player": "Jahmyr Gibbs", "team": "DET", "position": "RB", "metric": "carry share",
                             "season": 0.55, "last": 0.61, "delta": 0.06}]
    bs = _run("fantasy", view="buy_sell")
    assert bs["buy_low"][0]["player"] == "Jayden Reed" and bs["sell_high"][0]["player"] == "Tucker Kraft"
    assert _run("fantasy", view="trending")["adds"][0]["player"] == "Rookie Back"
    assert list(_run("fantasy", view="streamers", position="TE")) == ["view", "season", "as_of", "TE"]
    assert _run("fantasy", view="moves")["moves"][0]["player"] == "Kyle Allen"
    assert _run("fantasy", view="usage", position="WR")["found"] is False
    assert _run("fantasy", view="dynasty")["error"]


def test_the_one_top_pick_across_every_league():
    t = _run("our_picks", kind="top_pick_today")
    assert t["league"] == "nfl" and t["pick"]["player"] == "Jahmyr Gibbs" and t["leagues_compared"] == 4
    assert t["runners_up"][0]["league"] == "mlb" and t["verdict"] == "top pick: Gibbs over 80.5"


def test_the_ufc_card_live():
    u = _run("live_scores", sport="ufc")["scoreboards"][0]
    assert u["event"] == "UFC Fight Night" and u["as_of"] == "2026-09-23T22:10:00"
    assert u["bouts"][0] == {"bout": "A One vs B Two", "state": "in", "detail": "R2 3:10", "round": 2,
                             "clock": "3:10"}
    assert u["bouts"][1]["winner"] == "C Three"


def test_a_player_s_injury_history_even_off_the_board():
    h = _run("injuries", player="LaPorta")
    assert [d["status"] for d in h["designations_we_have_seen"]] == ["Questionable", "Out"], "newest first"
    assert h["note"] == "not on the injury board now"
    assert _run("injuries", player="Nobody Atall")["found"] is False


def test_a_pick_s_line_since_it_opened():
    tape = _run("line_shop", query="Gibbs")["picks"][0]["line_since_open"]
    assert len(tape) == AB.TAPE_POINTS
    assert tape[0]["line"] == 74.5 and tape[0]["minutes_ago"] == 600, "the open"
    assert tape[-1]["line"] == 80.5 and tape[-1]["minutes_ago"] == 60, "and the now"
    assert "ts" not in tape[0]


def test_an_mlb_game_carries_its_starters_park_and_umpire():
    g = AB.game_facts(MLB, MLB["games"][0])
    assert g["probable_starters"] == {"NYY": {"name": "Gerrit Cole", "throws": "R", "xera": 3.21, "k_rate": 0.29},
                                      "BOS": {"name": "Brayan Bello", "throws": "R", "xera": 4.05}}
    assert g["park"] == "Yankee Stadium" and g["park_factors"] == {"hr": 1.12, "run": 1.04, "k": 0.98}
    assert g["lineups_confirmed"] is False and g["plate_umpire"] == "Angel Hernandez"
    assert g["weather"]["wind_dir"] == "out"
    row = _run("slate", sport="mlb")["slates"][0]["games"][0]
    assert row["probable_starters"]["NYY"]["name"] == "Gerrit Cole", "the first thing a bettor asks"
    assert "park_factors" not in row and "umpire_strikeout_factor" not in row


def test_every_question_says_how_fresh_the_boards_are():
    req = AB.build_request(NFL, "Lions tonight?", data_dir=DATA, boards=BOARDS)
    facts = json.loads(req["messages"][-1]["content"].split("Facts for this question:\n", 1)[1])
    fresh = facts["data_as_of"]
    assert fresh["nfl"] == "2026-09-23T12:00:00" and fresh["mlb"] == "2026-09-23T11:30:00"
    assert fresh["site_refreshed"] == "2026-09-23T12:01:00" and fresh["asked_at"]
    system = " ".join(req["system"][0]["text"].split())
    assert "data_as_of" in system and "news comes only from the news lookup" in system


def test_every_new_lookup_is_offered_answers_and_names_its_source():
    names = {t["name"] for t in AB.TOOLS}
    calls = {"standings": {"sport": "nfl"}, "roster": {"team": "Lions"}, "news": {}, "book_report": {},
             "prediction_markets": {}, "market_moves": {}, "our_picks_live": {}, "team_efficiency": {},
             "fantasy": {"view": "usage"}}
    for name, args in calls.items():
        assert name in names, name
        res = _run(name, **args)
        assert "error" not in res and res.get("found") is not False, (name, res)
        assert AB.tool_source(name, args, res)["label"], name
    assert AB.NO_CACHE_TOOLS == {"live_scores", "market_moves", "news", "our_picks_live", "prediction_markets"}


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
