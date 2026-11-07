"""nhl_build: tonight's NHL games become a board in the shared schema.

Ethan, 2026-10-03: "We want every single feature we have for NFL and
college football and MLB for NHL as well. Then after that, start working on
the most likely bet model and the edge model for NHL." Ten days of fixture
box scores go through the real ingest (engine/sources/nhldata) into a
scratch history; a priced slate goes through the real build. Checks: every
priced prop carries the fields the shared pages read; the anytime scorer is
a 0.5 line on the yes side; the probable starter gets the saves prop; the
three game lines are priced off real prices; a new league's Edge picks go
on paper; the walk that opens each Most Likely shelf never sees a game
before projecting it; and a measured market reaches the Most Likely list.

Run directly: `python3 tests/test_nhl_board_builds.py`
"""
import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nhl_build as B                                          # noqa: E402
from engine import db, ledger                                  # noqa: E402
from engine.models import SportsbookLine as L                  # noqa: E402
from engine.nhl import backtest as BT                          # noqa: E402
from engine.sources import nhldata as N                        # noqa: E402

PEOPLE = {1: ("Connor", "McDavid", "C"), 2: ("Evan", "Bouchard", "D"), 3: ("Stuart", "Skinner", "G"),
          4: ("Nazem", "Kadri", "C"), 5: ("Dan", "Vladar", "G"), 6: ("Calvin", "Pickard", "G")}
SOG = [4, 5, 3, 6, 4, 2, 5, 4, 3, 5]
GOALS = [1, 0, 1, 1, 0, 0, 2, 0, 1, 0]



def _no_pbp(game_id):
    """No play-by-play in these tests — the network is never touched."""
    raise N.DataUnavailable("no play-by-play in tests")

def _day(i):
    d = (datetime.date(2025, 10, 8) + datetime.timedelta(days=2 * i)).isoformat()
    home_edm = i % 2 == 0
    h, a = ("EDM", "CGY") if home_edm else ("CGY", "EDM")
    edm_g, cgy_g = 3 + (i % 3), 2 + (i % 2)
    day = {"games": [{"id": 2025020000 + i, "gameType": 2, "gameState": "OFF", "startTimeUTC": f"{d}T23:00:00Z",
                      "homeTeam": {"abbrev": h, "score": edm_g if home_edm else cgy_g, "sog": 32},
                      "awayTeam": {"abbrev": a, "score": cgy_g if home_edm else edm_g, "sog": 28},
                      "periodDescriptor": {"periodType": "REG"}}]}
    edm = {"forwards": [{"playerId": 1, "name": {"default": "C. McDavid"}, "position": "C", "goals": GOALS[i],
                         "assists": 1, "points": GOALS[i] + 1, "sog": SOG[i], "hits": 1, "blockedShots": 0,
                         "toi": "21:30"}],
           "defense": [{"playerId": 2, "name": {"default": "E. Bouchard"}, "position": "D", "goals": 0,
                        "assists": 1, "points": 1, "sog": 2, "blockedShots": 2, "toi": "23:00"}],
           "goalies": [{"playerId": 3, "name": {"default": "S. Skinner"}, "saves": 26 + i % 3, "shotsAgainst": 28 + i % 3,
                        "goalsAgainst": cgy_g, "toi": "60:00", "starter": True},
                       {"playerId": 6, "name": {"default": "C. Pickard"}, "toi": "00:00"}]}
    cgy = {"forwards": [{"playerId": 4, "name": {"default": "N. Kadri"}, "position": "C", "goals": i % 2,
                         "assists": 0, "points": i % 2, "sog": 3, "toi": "18:00"}],
           "defense": [],
           "goalies": [{"playerId": 5, "name": {"default": "D. Vladar"}, "saves": 29, "shotsAgainst": 32,
                        "goalsAgainst": edm_g, "toi": "60:00", "starter": True}]}
    box = {"homeTeam": {"abbrev": h}, "awayTeam": {"abbrev": a},
           "playerByGameStats": {"homeTeam": edm if home_edm else cgy, "awayTeam": cgy if home_edm else edm}}
    return d, day, box


def _person(pid):
    f, l, _pos = PEOPLE[int(pid)]
    return {"firstName": {"default": f}, "lastName": {"default": l}, "headshot": f"https://img/{pid}.png"}


def _history():
    conn = db.connect(Path(tempfile.mkdtemp()) / "history.db")
    for i in range(10):
        d, day, box = _day(i)
        N.ingest_day(conn, d, fetch_day=lambda _d, day=day: day, fetch_box=lambda _g, box=box: box,
                     fetch_person=_person, fetch_pbp=_no_pbp)
    return conn


TONIGHT = [{"home": "EDM", "away": "CGY", "start": "2025-10-30T23:00:00Z", "type": 2, "final": False}]


def _odds(slate):
    for g in slate.games:
        g.home_ml, g.away_ml = -150, 130
        g.spread, g.spread_home_odds, g.spread_away_odds = -1.5, 165, -195
        g.total, g.total_over_odds, g.total_under_odds = 6.5, -105, -115
    for pr in slate.props:
        if pr.player == "Connor McDavid" and pr.market == "sog":
            pr.lines = [L("DraftKings", 3.5, -120, -105), L("FanDuel", 3.5, -125, 100)]
            pr.alt_lines = [L("DraftKings", 2.5, -230, 175), L("DraftKings", 1.5, -600, 400)]
        elif pr.player == "Connor McDavid" and pr.market == "anytime_goal":
            pr.lines = [L("DraftKings", 0.5, 105, -135)]
        elif pr.player == "Connor McDavid" and pr.market == "points":
            pr.lines = [L("DraftKings", 1.5, 120, -150)]
        elif pr.player == "Stuart Skinner" and pr.market == "saves":
            pr.lines = [L("DraftKings", 26.5, -110, -110)]
    return "fixture odds"


def _board():
    conn = _history()
    out, slate = B.build("2025-10-30", TONIGHT, conn, attach_odds=_odds, injuries={}, starters={}, lines={})
    return out, slate


def test_every_priced_prop_speaks_the_shared_schema():
    out, _ = _board()
    recs = {(r["player"], r["market"]): r for r in out["recommendations"]}
    assert set(recs) == {("Connor McDavid", "sog"), ("Connor McDavid", "anytime_goal"),
                         ("Connor McDavid", "points"), ("Stuart Skinner", "saves")}, set(recs)
    need = {"player", "team", "opponent", "market", "market_label", "side", "line", "odds", "book",
            "hit_prob", "fair_prob", "edge", "projection", "has_market", "all_lines", "rung_probs",
            "recent_values", "headshot", "logs", "reasons", "recommended", "grade", "stake_units"}
    for r in recs.values():
        assert need <= set(r), need - set(r)
        assert 0 < r["hit_prob"] < 1 and r["opponent"] == "CGY" and r["team"] == "EDM"
    sog = recs[("Connor McDavid", "sog")]
    assert sog["headshot"] == "https://img/1.png"
    assert 3.0 < sog["projection"] < 5.5, sog["projection"]
    assert set(sog["rung_probs"]) == {"2.5", "1.5"} and sog["rung_probs"]["1.5"] > sog["rung_probs"]["2.5"]
    assert sog["all_lines"][0]["book"] == "DraftKings" and len(sog["all_lines"]) == 2


def test_the_scorer_is_a_half_goal_line_and_the_starter_gets_saves():
    out, slate = _board()
    goal = next(r for r in out["recommendations"] if r["market"] == "anytime_goal")
    assert goal["line"] == 0.5 and goal["market_label"] == "Anytime Goal"
    saves = [p for p in slate.props if p.market == "saves"]
    assert {p.player for p in saves} == {"Stuart Skinner", "Dan Vladar"}, "starters only, never the backup"


def test_the_three_game_lines_are_priced_off_real_prices():
    out, _ = _board()
    kinds = {b["bet_type"]: b for b in out["game_bets"]}
    assert set(kinds) == {"moneyline", "spread", "total"}, set(kinds)
    for b in kinds.values():
        assert b["has_market"] and 0 < b["win_prob"] < 1 and b["matchup"] == "CGY @ EDM"
    assert abs(kinds["spread"]["line"]) == 1.5 and kinds["total"]["line"] == 6.5
    g = out["games"][0]
    assert g["home_ml"] == -150 and g["total"] == 6.5 and g["live"] is None


def test_a_new_league_journals_on_paper():
    assert ledger.book_for("nhl", False) == "paper"
    assert ledger.book_for("nfl", False) == "main", "nobody else moves"
    conn = ledger.connect(":memory:")
    rec = {"player": "Connor McDavid", "market": "sog", "side": "OVER", "line": 3.5, "book": "DraftKings",
           "odds": -120, "projection": 4.1, "hit_prob": 0.6, "edge": 0.05, "confidence": 8.0,
           "grade": "Play", "stake_units": 0.5, "recommended": True, "team": "EDM", "opponent": "CGY"}
    assert ledger.log_recommendations(conn, {"sport": "nhl", "date": "2030-10-30", "recommendations": [rec]}) == 1
    assert conn.execute("SELECT category FROM bets").fetchone()[0] == "paper"


def test_opening_night_keeps_last_seasons_players_and_drops_the_gone():
    """Every player's last game is months old on opening night; counted in
    days, the whole league would vanish. Counted in his team's games, a
    regular stays and a man who missed the team's last ten does not."""
    conn = _history()
    players = B.M.player_games(conn)
    players["Gone Guy"] = {"team": "EDM", "position": "C",
                           "games": [{"date": "2025-04-10", "team": "EDM", "toi": 15.0, "sog": 2.0}]}
    live = B.current_players(players, "2026-10-08")
    assert "Connor McDavid" in live and "Stuart Skinner" in live
    assert "Gone Guy" not in live, "missed his team's last ten games"
    slate = B.build_slate([{"home": "EDM", "away": "CGY", "start": ""}], players, "2026-10-08")
    assert any(p.player == "Connor McDavid" for p in slate.props)
    assert not any(p.player == "Gone Guy" for p in slate.props)


def test_a_traded_player_moves_with_the_roster_and_a_released_one_leaves():
    conn = _history()
    players = B.M.player_games(conn)
    live = B.current_players(players, "2026-10-08", rosters={"Connor McDavid": "CGY", "Stuart Skinner": "EDM",
                                                            "Nazem Kadri": "CGY", "Dan Vladar": "CGY"})
    assert live["Connor McDavid"]["team"] == "CGY" and live["Connor McDavid"]["traded_from"] == "EDM"
    assert "Evan Bouchard" not in live, "on no current roster of a club whose roster was read"
    assert B.current_players(players, "2026-10-08", rosters={})["Evan Bouchard"], "no rosters, no change"


def test_the_walk_never_sees_a_game_before_projecting_it():
    conn = _history()
    rows = BT.settled(conn, "sog")
    mc = [s for s in rows if s.player == "Connor McDavid"]
    assert len(mc) == 10 - BT.MIN_HISTORY, len(mc)
    assert [s.actual for s in mc] == [float(v) for v in SOG[BT.MIN_HISTORY:]]
    # Game 6's projection moves only with games 1-5: change game 7 onwards
    # and the first projection must not move.
    players = BT._all_games(conn)
    first = BT.settled(conn, "sog", players=players)[0].projection
    for g in players["Connor McDavid"]["games"][BT.MIN_HISTORY + 1:]:
        g["sog"] = 40.0
    assert BT.settled(conn, "sog", players=players)[0].projection == first
    saves = BT.settled(conn, "saves")
    assert saves and all(s.player in ("Stuart Skinner", "Dan Vladar") for s in saves)


def test_rankfit_walks_hockey_with_its_own_model():
    from engine import rankfit, seasons
    conn = _history()
    path = Path(tempfile.mkdtemp()) / "rank.json"
    real = seasons.recent_seasons
    seasons.recent_seasons = lambda sport, date, back=1: [2025]   # the fixture's season, whatever today is
    try:
        lines = rankfit.measure(conn, "nhl", markets=("sog", "anytime_goal"), log=lambda *_: None, path=path)
    finally:
        seasons.recent_seasons = real
    assert all("pairs — needs" in ln for ln in lines), lines


def test_a_measured_market_reaches_most_likely():
    from engine import likely, rankfit
    out, _ = _board()
    real = rankfit.rank_auc
    rankfit.rank_auc = lambda sport, market, store=None: 0.70 if sport == "nhl" else real(sport, market, store)
    try:
        census: dict = {}
        rows = likely.build(out["recommendations"], sport="nhl", census=census)
    finally:
        rankfit.rank_auc = real
    main = [r for r in rows if not r.get("reserve")]
    assert main, census
    assert all(r["model_prob"] >= likely.MIN_PROB for r in main), [r["model_prob"] for r in main]
    sog = next(r for r in main if r["market"] == "sog")
    assert sog["rung"] == "alt" and sog["line"] == 2.5, "the ladder carries the likely number"
    assert all(r["model_prob"] >= likely.RESERVE_MIN_PROB for r in rows)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
