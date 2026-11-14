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


def _box_team(c, team, opp, catches=True):
    """Two college games as ESPN's box score files them: carries for the
    backs and the quarterback, catches (and no targets) for the receivers."""
    for period in ("2026-10-17", "2026-10-24"):
        def put(player, **m):
            for k, v in m.items():
                c.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                          "position, home, market, value) VALUES ('cfb',2026,?,?,?,?,?,'',1,?,?)",
                          (period, f"{team}-{period}", player, team, opp, k, v))
        put(f"{team} Back", carries=18, rush_td=1)
        put(f"{team} Back Two", carries=6, rush_td=0)
        put(f"{team} Quarterback", carries=5, rush_td=0)
        if catches:
            put(f"{team} Wideout", receptions=7, rec_td=1, rec_yds=90)
            put(f"{team} Slot", receptions=5, rec_td=0, rec_yds=55)
            put(f"{team} Third", receptions=3, rec_td=0, rec_yds=30)
            put(f"{team} Tight End", receptions=4, rec_td=1 if period.endswith("24") else 0, rec_yds=40)


def test_a_box_score_receiver_reads_his_catches_when_it_has_no_targets():
    """Ethan's 2026-10-31 paste: Duke's lead back 52% to score the game's
    first touchdown, and every college top three a back or a quarterback."""
    c = _hist()
    _box_team(c, "DUKE", "BC")
    _box_team(c, "BC", "DUKE")
    u = F.team_usage(c, "cfb", 2026, "DUKE")
    assert "DUKE Wideout" in u, "a receiver with catches is a candidate"
    assert abs(u["DUKE Wideout"]["touch"] - 14 / F.CATCH_RATE["cfb"]) < 1e-9, "catches over the catch rate"
    assert u["DUKE Back"]["touch"] == 36, "a back's carries are what they were"
    rows = F.game_probs(u, F.team_usage(c, "cfb", 2026, "BC"), -27.5, "DUKE", "BC", "cfb")
    back = next(r for r in rows if r["player"] == "DUKE Back")
    assert back["prob"] < F.MAX_PROB, back
    assert any(r["player"] == "DUKE Wideout" for r in rows[:4]), "the receivers are back in the top of the list"
    # The read before: the receivers had no volume and fell off the list.
    old = _hist()
    _box_team(old, "DUKE", "BC", catches=False)
    _box_team(old, "BC", "DUKE", catches=False)
    was = F.game_probs(F.team_usage(old, "cfb", 2026, "DUKE"), F.team_usage(old, "cfb", 2026, "BC"),
                       -27.5, "DUKE", "BC", "cfb")
    assert was[0]["player"] == "DUKE Back" and was[0]["prob"] > 0.5, was[0]


def test_a_real_target_count_is_never_replaced():
    c = _hist()
    _log(c, 2026, "001", "Puka Nacua", "LAR", targets=12, receptions=9, rec_td=1)
    assert F.team_usage(c, "nfl", 2026, "LAR")["Puka Nacua"]["touch"] == 12, \
        "targets at or above the catches are the real count"


def test_no_chance_above_the_ceiling_is_a_pick():
    rows = [{"player": "Hole In The Logs", "prob": 0.45, "odds": 300, "game": "A@B"},
            {"player": "Real Read", "prob": 0.20, "odds": 600, "game": "C@D"}]
    assert [r["player"] for r in F.pick([dict(r) for r in rows])] == ["Real Read"]
    b = {"games": 0, "ours_games": 1, "beyond": 1}
    assert "1 player(s) above 30%" in F.report(b)


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


# --- ESPN grades it the night of the game (Ethan, 2026-11-01: "we already are 1/2") ---
def _espn(plays, state="post"):
    return {"header": {"competitions": [{"status": {"type": {"state": state, "completed": state == "post"}}}]},
            "scoringPlays": plays}


def _sp(text, team, kind="Passing Touchdown", abbr="TD", period=1):
    return {"type": {"text": kind}, "scoringType": {"abbreviation": abbr}, "text": text,
            "period": {"number": period}, "team": {"abbreviation": team}}


def _epoch(iso):
    import datetime as dt
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def test_a_first_touchdown_grades_off_espn_once_the_game_is_final():
    lc = _ledger()
    pick = lambda name, team: {"player": name, "team": team, "market": "first_td", "odds": 1800,  # noqa: E731
                               "book": "FanDuel", "model_prob": 0.07, "edge": 0.2, "grade": "First TD"}
    assert _journal(lc, 8, [pick("Malik Washington", "MIA"), pick("Stefon Diggs", "NE"),
                            pick("Jahmyr Gibbs", "DET"), pick("Puka Nacua", "LA")]) == 4
    games = [{"game_id": "401873034", "home": "MIA", "away": "NE", "kickoff": "2026-11-01T18:00Z"},
             {"game_id": "401873030", "home": "DET", "away": "MIN", "kickoff": "2026-11-01T18:00Z"},
             {"game_id": "401873032", "home": "LA", "away": "LAC", "kickoff": "2026-11-02T01:20Z"}]
    summaries = {
        "401873034": _espn([_sp("Jason Sanders 41 Yd Field Goal", "MIA", "Field Goal Good", "FG"),
                            _sp("Malik Washington 5 Yd pass from Tua Tagovailoa (Jason Sanders Kick)", "MIA",
                                period=2)]),
        "401873030": _espn([_sp("Jahmyr Gibbs 3 Yd Run (Jake Bates Kick)", "DET", "Rushing Touchdown")],
                           state="in"),
    }
    asked = []

    def summary(gid):
        asked.append(gid)
        return summaries[gid]
    n = F.settle_espn(lc, week_games=lambda s, w: games if (s, w) == (2026, 8) else [], summary=summary,
                      now=_epoch("2026-11-01T22:00Z"))
    assert n == 2, n
    got = {r["player"]: (r["status"], r["pnl_units"]) for r in lc.execute("SELECT player, status, pnl_units FROM bets")}
    assert got["Malik Washington"] == ("won", 1.8), got["Malik Washington"]
    assert got["Stefon Diggs"][0] == "lost", "the other side scored first"
    assert got["Jahmyr Gibbs"][0] == "open", "the game is still on: ESPN is not final"
    assert got["Puka Nacua"][0] == "open", "the night game has not been on long enough to be over"
    assert "401873032" not in asked, "no summary asked for before a game could have ended"
    assert asked.count("401873034") == 1, "one read a game a pass, however many bets ride on it"


def test_espn_waits_rather_than_guess():
    W = F.espn_verdict
    wash = _sp("Malik Washington 5 Yd pass from Tua Tagovailoa (Kick)", "MIA")
    assert W(_espn([wash]), "Malik Washington", "MIA") == 1.0
    assert W(_espn([wash], state="in"), "Malik Washington", "MIA") is None, "not final"
    assert W(_espn([]), "Malik Washington", "MIA") is None, "ESPN leaves scoring plays off some payloads"
    assert W(_espn([_sp("Jason Sanders 41 Yd Field Goal", "MIA", "Field Goal Good", "FG")]),
             "Malik Washington", "MIA") is None, "field goals only: the file says whether anyone scored one"
    # A pick-six by the other side loses him whoever ran it back, named or not.
    pick6 = _sp("54 Yd Interception Return (Kick)", "NE", "Interception Return Touchdown")
    assert W(_espn([pick6]), "Malik Washington", "MIA") == 0.0
    # His own side's touchdown with no scorer read: he might be the returner, so it waits.
    assert W(_espn([_sp("98 Yd Kickoff Return (Kick)", "MIA", "Kickoff Return Touchdown")]),
             "Malik Washington", "MIA") is None
    # A teammate scored first: lost. ESPN's own codes meet ours (WSH is WAS, LAR is LA).
    assert W(_espn([_sp("De'Von Achane 12 Yd Run (Kick)", "MIA", "Rushing Touchdown")]),
             "Malik Washington", "MIA") == 0.0
    assert W(_espn([_sp("Terry McLaurin 20 Yd pass from Jayden Daniels (Kick)", "WSH")]),
             "Terry McLaurin", "WAS") == 1.0
    assert W(_espn([_sp("Puka Nacua 9 Yd pass from Matthew Stafford (Kick)", "LAR")]), "Puka Nacua", "LA") == 1.0


def test_the_record_page_names_each_long_shot_and_lines_up_each_kind():
    """Every settled long shot read "HR" (`b.market_label || "HR"`, a field
    the export never sends), anytime touchdowns included; and the first
    scorers' week sat pooled under 395 graded home runs."""
    import shutil
    import subprocess
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    i, j = js.index("const LS_MARKET_ORDER"), js.index("function recLongshotSection(ls)")
    body = js[j:js.index("\n}\n", j)]
    assert 'marketWord(b.market || "home_runs")' in body and 'market_label || "HR"' not in body
    assert "recLongshotMarkets(ls.by_market)" in body and "first touchdowns and first baskets" in body
    if not shutil.which("node"):
        return
    harness = js[i:j] + """
const marketWord = (k) => ({first_td: "First Touchdown", first_basket: "First Basket",
  anytime_td: "Anytime TD", home_runs: "Home Runs"})[k] || k;
const escapeHtml = (s) => String(s);
const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
process.stdout.write(recLongshotMarkets({home_runs: {w: 58, l: 337, net_u: -5.06},
  first_basket: {w: 0, l: 4, net_u: -0.4}, first_td: {w: 1, l: 1, net_u: 1.7}}) + "|" +
  recLongshotMarkets({home_runs: {w: 1, l: 2, net_u: -0.1}}));
"""
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    many, one = out.stdout.split("|")
    flat = " ".join(many.split())
    assert flat.index("First Touchdown 1-1") < flat.index("First Basket 0-4") < flat.index("Home Runs 58-337"), flat
    assert '<b class="pos">+1.70u</b>' in flat and '<b class="neg">-5.06u</b>' in flat
    assert one == "", "one kind alone is the tiles' own record: no second line"


def test_the_settle_pass_asks_espn_first_and_the_file_after():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("n_ftd += _ftd.settle_espn(lconn)")
    assert i < src.index("n_ftd += _ftd.settle(lconn)", i), "ESPN first, the overnight file as the backstop"
    assert "first-touchdown ESPN grade skipped" in src, "an ESPN failure never stops the file's grade"


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
    assert all(r["priced"] for r in b["rows"]) and b["ours"] == [], "a priced game shows its prices"


def test_a_game_with_no_price_shows_our_first_scorers_and_the_price_that_would_make_a_pick():
    """Ethan, 2026-10-31: "still not seeing first touchdown bets". A game whose
    prices are not on file still shows who scores first by our numbers, each
    with the shortest price that would make him a pick — never a pick itself."""
    c = _hist()
    for p_, team, car, tgt, td in (("Jahmyr Gibbs", "DET", 15, 4, 1), ("Amon-Ra St. Brown", "DET", 0, 10, 1),
                                   ("Justin Jefferson", "MIN", 0, 11, 1), ("Aaron Jones", "MIN", 16, 3, 0)):
        _log(c, 2026, "007", p_, team, carries=car, targets=tgt, rush_td=td if car else 0, rec_td=0 if car else td)
    games = [{"home": "DET", "away": "MIN", "spread": -2.5, "date": "2026-11-01", "kickoff": "13:00"}]
    b = F.board({}, games, sport="nfl", conn=c, why="player quotes: 0 of 1 eligible game(s) pulled · "
                "1 left unpriced — the pull is capped at 0 game(s) by attention tier (budget pacing)")
    assert b["rows"] == [] and b["picks"] == [] and b["ours_games"] == 1
    assert len(b["ours"]) == F.OURS_PER_GAME and all(r["priced"] is False for r in b["ours"])
    top = b["ours"][0]
    assert top["need_odds"] is None or F.FIRST_TD_ODDS[0] <= top["need_odds"] <= F.FIRST_TD_ODDS[1]
    assert top["fair_odds"] > 0 and b["why"] == F.WHY_BUDGET, "the budget held it, said in a reader's words"
    assert F.why_empty("") == F.WHY_LATER
    assert "our top first scorers shown unpriced for 1 game(s)" in F.report(b)


def test_the_price_that_makes_a_pick_is_ten_percent_over_our_chance():
    assert F.need_odds(0.10) == 1000, "1.10 / 0.10 = 11.0 decimal = +1000"
    assert F.need_odds(0.30) == 267 and F.need_odds(0.50) == 250, "never shorter than the window's floor"
    assert F.need_odds(0.03) is None and F.need_odds(0.042) is None, "nothing in the window makes him one"
    assert F.fair_odds(0.2) == 400 and F.fair_odds(0) is None


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
    # One renderer for every first-scorer league since 2026-10-31 (the NBA's
    # first basket rides it too): firstScorer() says which board and its word.
    assert "const fs = firstScorer(state.data);" in ls and "const ftd = !!fs;" in ls
    assert "`— ${fs.what}, our chance against the price`" in ls
    assert 'what: "first touchdown"' in APP
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
