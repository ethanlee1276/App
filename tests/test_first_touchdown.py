"""First touchdown: who scores a game's first touchdown, by our numbers.

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... if we go by the
most likely scorer for each game, it's just going to be the person with the
lowest odds ... We want to be going after what the data and tools that we
have all put together says, not just off of book lines."

engine/firsttd carries the research's model (docs/FIRST_TD_RESEARCH.md):
the team from the lines, the player from two-thirds his share of his team's
carries and targets and one-third its touchdowns. These hold:

  * the lines' sign (the games table's home spread is negative when the
    home team is favoured) and the shares' arithmetic;
  * usage read from player_game_logs, this season and last at half weight,
    his rows for this team only;
  * a pick is our chance clearly above the price — ranked by expected
    return, never by price, one a game, inside the window;
  * grading: the play-by-play's first scorer, an abbreviated name matched
    to the journal's full one, a defence's touchdown losing every bet, a
    game not over left open, and two weeks never sharing a result;
  * the feed asks for the NFL's first-touchdown market and keeps it off
    every anytime reader; the page shows it on the NFL's Long Shots.

Run directly: `python3 tests/test_first_touchdown.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, firsttd as F, ledger                        # noqa: E402
from _app import app_js                                            # noqa: E402

APP = app_js()


def _hist():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    return c


def _log(c, season, period, player, team, **markets):
    for m, v in markets.items():
        c.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES ('nfl',?,?,?,?,?,'OPP','WR',1,?,?)",
                  (season, period, f"{team}-{period}", player, team, m, v))


def test_the_lines_sign_and_the_fit():
    assert abs(F.team_first(0) - 1 / (1 + 2.718281828 ** -F.TEAM_A)) < 1e-6, "a pick'em keeps the home lean"
    fav, dog = F.team_first(-7.0), F.team_first(7.0)
    assert fav > 0.6 and dog < 0.5, (fav, dog)
    assert abs(fav - 1 / (1 + 2.718281828 ** -(F.TEAM_A + F.TEAM_B))) < 1e-6
    assert F.team_first(None) == F.team_first(0)


def test_his_share_is_two_thirds_volume_one_third_touchdowns():
    s = F.shares({"Back": {"touch": 60, "td": 1}, "Wideout": {"touch": 30, "td": 2}, "Tight End": {"touch": 10, "td": 1}})
    assert abs(sum(s.values()) - 1.0) < 1e-9
    assert s["Back"] > s["Wideout"], "volume carries two-thirds of the weight"
    raw_back = F.EPS + F.BLEND["touch"] * 0.6 + F.BLEND["td"] * 0.25
    raw_wr = F.EPS + F.BLEND["touch"] * 0.3 + F.BLEND["td"] * 0.5
    assert abs(s["Back"] / s["Wideout"] - raw_back / raw_wr) < 1e-9
    assert F.shares({}) == {}
    lone = F.shares({"Nobody Yet": {"touch": 0, "td": 0}})
    assert lone == {"Nobody Yet": 1.0}


def test_usage_comes_from_the_logs_this_season_and_last_at_half():
    c = _hist()
    _log(c, 2026, "001", "Josh Jacobs", "GB", carries=20, targets=3, rush_td=1, rec_td=0)
    _log(c, 2026, "002", "Josh Jacobs", "GB", carries=18, targets=2, rush_td=0, rec_td=1)
    _log(c, 2025, "010", "Josh Jacobs", "GB", carries=22, targets=4, rush_td=2, rec_td=0)
    _log(c, 2025, "010", "Josh Jacobs", "LV", carries=99, targets=9, rush_td=9, rec_td=0)   # another team: not his GB volume
    u = F.team_usage(c, "nfl", 2026, "GB")
    assert u["Josh Jacobs"]["touch"] == 20 + 3 + 18 + 2 + 0.5 * (22 + 4)
    assert u["Josh Jacobs"]["td"] == 1 + 1 + 0.5 * 2
    assert u["Josh Jacobs"]["games"] == 2
    before = F.team_usage(c, "nfl", 2026, "GB", before_period="002")
    assert before["Josh Jacobs"]["touch"] == 20 + 3 + 0.5 * 26, "a later week is not read early"


def test_every_chance_in_a_game_adds_to_the_offences_share():
    hu = {"A": {"touch": 50, "td": 2}, "B": {"touch": 50, "td": 2}}
    au = {"C": {"touch": 100, "td": 4}}
    rows = F.game_probs(hu, au, -3.0, "HOM", "AWY")
    assert abs(sum(r["prob"] for r in rows) - F.OFF_SHARE) < 1e-9
    assert rows[0]["player"] == "C" or rows[0]["team"] == "AWY" or rows[0]["prob"] >= rows[-1]["prob"]
    c = next(r for r in rows if r["player"] == "C")
    assert abs(c["prob"] - F.OFF_SHARE * (1 - F.team_first(-3.0))) < 1e-9, "his team's whole share"


def test_a_pick_is_our_chance_above_the_price_not_the_shortest_price():
    rows = [
        # The likeliest scorer at a price that charges for it: no pick.
        {"player": "Bell Cow", "prob": 0.14, "odds": 450, "game": "g1"},
        # A longer price our number likes: the pick.
        {"player": "Volume Wideout", "prob": 0.09, "odds": 1400, "game": "g1"},
        # Above the price but under the floor we will call a pick.
        {"player": "Deep Shot", "prob": 0.03, "odds": 2400, "game": "g2"},
        # Out of the window either side.
        {"player": "Too Short", "prob": 0.30, "odds": 200, "game": "g3"},
        {"player": "Too Long", "prob": 0.06, "odds": 3000, "game": "g3"},
        # A second value pick in g1 loses its seat to the better one.
        {"player": "Also Value", "prob": 0.095, "odds": 1200, "game": "g1"},
    ]
    got = F.pick([dict(r) for r in rows])
    assert [r["player"] for r in got] == ["Volume Wideout"], got
    assert abs(got[0]["ev"] - (0.09 * 15.0 - 1.0)) < 1e-4 and got[0]["implied"] == round(1 / 15.0, 4)
    two = F.pick([dict(r) for r in rows], per_game=2)
    assert [r["player"] for r in two] == ["Volume Wideout", "Also Value"]


def test_the_first_scorer_from_the_plays_and_the_name_match():
    plays = [{"touchdown": "0"}, {"touchdown": "1", "td_team": "MIN", "posteam": "DET", "td_player_name": "B.Murphy",
                                  "pass_touchdown": "0", "rush_touchdown": "0"},
             {"touchdown": "1", "td_team": "DET", "posteam": "DET", "td_player_name": "J.Gibbs", "rush_touchdown": "1"}]
    first = F.first_scorer(plays)
    assert first == {"player": "B.Murphy", "player_id": "", "team": "MIN", "offense": False}, "a pick-six counts"
    assert not F.scored_first("Jahmyr Gibbs", "DET", first)
    assert F.scored_first("Jahmyr Gibbs", "DET", F.first_scorer(plays[2:]))
    assert not F.scored_first("Jahmyr Gibbs", "MIN", F.first_scorer(plays[2:])), "the team is part of the key"
    assert F.first_scorer([{"touchdown": "0"}]) is None and not F.scored_first("Anyone", "DET", None)


def _ledger():
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    return ledger.connect(p)


def _journal(lc, week, rows):
    return ledger.log_longshots(lc, {"sport": "nfl", "date": f"2026-W{week:02d}", "long_shots": rows})


def test_first_touchdown_bets_journal_and_grade_off_the_play_by_play():
    lc = _ledger()
    pick = lambda name, team: {"player": name, "team": team, "market": "first_td", "odds": 1100,  # noqa: E731
                               "book": "DraftKings", "model_prob": 0.09, "edge": 0.01, "grade": "First TD"}
    assert _journal(lc, 8, [pick("Jahmyr Gibbs", "DET"), pick("Justin Jefferson", "MIN")]) == 2
    assert _journal(lc, 9, [pick("Jahmyr Gibbs", "DET")]) == 1
    w8 = [{"season": "2026", "season_type": "REG", "week": "8", "home_team": "DET", "away_team": "MIN",
           "posteam": "DET", "touchdown": "1", "td_team": "DET", "td_player_name": "J.Gibbs", "rush_touchdown": "1"},
          {"season": "2026", "season_type": "REG", "week": "8", "home_team": "DET", "away_team": "MIN",
           "desc": "END GAME"}]
    w9 = [{"season": "2026", "season_type": "REG", "week": "9", "home_team": "GB", "away_team": "DET",
           "posteam": "GB", "touchdown": "1", "td_team": "GB", "td_player_name": "J.Jacobs", "rush_touchdown": "1"}]
    n = F.settle(lc, plays_for=lambda season: iter(w8 + w9))
    assert n == 2, n
    got = {(r["player"], r["date"]): r["status"] for r in lc.execute("SELECT player, date, status FROM bets")}
    assert got[("Jahmyr Gibbs", "2026-W08")] == "won" and got[("Justin Jefferson", "2026-W08")] == "lost"
    assert got[("Jahmyr Gibbs", "2026-W09")] == "open", "no END GAME yet: the week-9 game is not over"
    assert "first_td" in ledger.SETTLEABLE_LONGSHOTS and "first_td" in ledger.LONGSHOT_MARKETS


def test_the_board_joins_quotes_to_our_usage_and_prices_every_player():
    c = _hist()
    for p_, team, car, tgt, td in (("Jahmyr Gibbs", "DET", 15, 4, 1), ("Amon-Ra St. Brown", "DET", 0, 10, 1),
                                   ("Justin Jefferson", "MIN", 0, 11, 1), ("Aaron Jones", "MIN", 16, 3, 0)):
        _log(c, 2026, "007", p_, team, carries=car, targets=tgt, rush_td=td if car else 0, rec_td=0 if car else td)
    quotes = {"amon ra st brown": {"player": "Amon-Ra St. Brown", "home": "DET", "away": "MIN",
                                   "quotes": [{"book": "FanDuel", "yes_odds": 700}]},
              "aaron jones": {"player": "Aaron Jones", "home": "DET", "away": "MIN",
                              "quotes": [{"book": "DraftKings", "yes_odds": 1600}]},
              "nobody known": {"player": "Nobody Known", "home": "DET", "away": "MIN",
                               "quotes": [{"book": "DraftKings", "yes_odds": 5000}]}}
    games = [{"home": "DET", "away": "MIN", "spread": -2.5, "date": "2026-11-01", "kickoff": "13:00"}]
    b = F.board(quotes, games, sport="nfl", conn=c)
    assert b["games"] == 1 and b["quoted"] == 2, b
    names = {r["player"] for r in b["rows"]}
    assert names == {"Amon-Ra St. Brown", "Aaron Jones"}, "a name nobody on either side carries is dropped"
    r = next(x for x in b["rows"] if x["player"] == "Aaron Jones")
    assert r["team"] == "MIN" and r["opponent"] == "DET" and r["market"] == "first_td" and r["odds"] == 1600
    assert r["model_prob"] == r["prob"] and r["implied_prob"] == round(1 / 17, 4)
    assert r["reasons"] and "carries and targets" in r["reasons"][1]
    for p_ in b["picks"]:
        assert p_["grade"] == "First TD" and p_["stake_units"] == 0.1 and p_["edge"] == round(p_["prob"] - p_["implied"], 4)
    assert F.report(b).startswith("  First touchdown: 2 quoted player(s) across 1 game(s)")
    assert F.report({"games": 0}) == "  First touchdown: no first-touchdown prices on this pull"


def test_the_feed_asks_for_it_on_the_nfl_and_keeps_it_from_every_anytime_reader():
    from engine.sources import oddsapi as O
    from engine import oddsbudget as OB
    assert O.SPORT_CONFIG["nfl"]["scorers"]["player_1st_td"] == "first_td"
    assert "player_1st_td" not in O.SCORER_ODDS_TO_MARKET, "the anytime map stays the anytime map"
    assert "player_1st_td" not in O.SPORT_CONFIG["cfb"]["scorers"]
    assert "player_1st_td" in O.UNPROVEN_MARKETS, "rides the drop-and-retry guard"
    assert OB.EVENT_CREDITS["nfl"] == 26
    ev = {"bookmakers": [{"key": "draftkings", "markets": [
        {"key": "player_1st_td", "outcomes": [{"name": "Yes", "description": "Aaron Jones", "price": 1600}]},
        {"key": "player_anytime_td", "outcomes": [{"name": "Yes", "description": "Aaron Jones", "price": 110}]}]}]}
    got = O.parse_event_scorers(ev, O.NFL_SCORER_ODDS_TO_MARKET)
    assert got[("aaron jones", "first_td")][0]["yes_odds"] == 1600
    assert got[("aaron jones", "anytime_td")][0]["yes_odds"] == 110
    assert ("aaron jones", "first_td") not in O.parse_event_scorers(ev), "the default map never sees it"
    assert "first_td" in O.OddsAttachResult.__dataclass_fields__


def test_the_page_shows_it_on_the_nfls_long_shots():
    ls = APP[APP.index("function renderLongShots()"):]
    ls = ls[:ls.index("\n}\n")]
    assert 'const ftd = !!state.data.first_td;' in ls
    assert "first touchdown, our chance against the price" in ls
    assert 'watchlistHTML(watch, false, "first_td")' in ls
    assert "never by the price." in ls and "The likeliest scorer is rarely the pick." in ls
    assert "Who scores first, by our numbers" in APP
    assert 'r.market === "first_td" ? "First-TD share"' in APP
    from engine import gate, markets
    assert "first_td" in gate.PAID_KEYS and markets.label("first_td") == "First Touchdown"


def test_the_research_page_says_where_its_numbers_come_from():
    page = (ROOT / "docs" / "FIRST_TD_RESEARCH.md").read_text(encoding="utf-8")
    assert "python3 tools/first_td_study.py" in page
    for figure in ("58.9%", "57.3%", "0.6654", "0.6550", "2.369", "2.086", "12.9%"):
        assert figure in page, figure
    from tools import first_td_study as S
    assert S.EPS == F.EPS, "the study and the engine share the floor"
    g = S.games_from([
        {"game_id": "g", "season": "2026", "season_type": "REG", "week": "8", "home_team": "DET", "away_team": "MIN",
         "qtr": "1", "kickoff_attempt": "1", "posteam": "MIN", "spread_line": "2.5"},
        {"game_id": "g", "season": "2026", "season_type": "REG", "week": "8", "home_team": "DET", "away_team": "MIN",
         "qtr": "1", "play_type": "pass", "posteam": "MIN", "receiver_player_id": "j1", "receiver_player_name": "J.Jefferson",
         "touchdown": "1", "td_team": "MIN", "td_player_id": "j1", "pass_touchdown": "1"}])
    assert g[0]["receiver"] == "MIN" and g[0]["tds"][0] == {"team": "MIN", "pid": "j1", "offense": True, "qtr": 1}
    assert g[0]["usage"]["j1"]["touch"] == 1


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
