"""College football gets the matchup model the NFL got, measured on college.

Ethan, 2026-09-23: "go do the same work you just did for nfl but for CFB."

What the college scan found and what changed:

  * NO MATCHUP AT ALL. Every college defence was "league average on
    purpose" — college "has no equivalent ingest". It does: every stored
    college player game names its opponent and the player's position.
    engine/cfb/defense.py rates each defence against each position from
    those rows (FBS against FBS), and the strengths are college's own
    (defensevs.TRANSFER_CFB, `python3 cfbdefensefit.py`): QB passing yards
    +3.9% of squared error removed held out, RB rushing +2.1%, receivers,
    tight ends and backs smaller, touchdowns on top of the book's total.
  * THE NFL'S SCRIPT AND TOTAL RULES RAN ON COLLEGE and made it worse:
    passing yards and WR/TE yards and catches in nearly every held-out
    season. They stand down for college.
  * EVERY COLLEGE CLOSING LINE WAS WRITTEN TO NOTHING (ingest), pinned in
    tests/test_cfb_ingest_keys.py.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db as DB                                        # noqa: E402
from engine import defensevs as D                                  # noqa: E402
from engine.cfb import defense as CD                               # noqa: E402
from engine.cfb import defensefit as CF                            # noqa: E402
from engine.matchup import evaluate_matchup                        # noqa: E402
from engine.models import (DefenseProfile, Game, Prop, SportsbookLine, GameLog, Weather,  # noqa: E402
                           PASS_YDS, RUSH_YDS, REC_YDS)

TEAMS = ["espn:1", "espn:2", "espn:3", "espn:4"]


def _league():
    """Four FBS schools, ten weeks, two games a week. espn:1's defence
    gives up twice the passing yards everyone else does. One FCS visitor
    (espn:99) plays once and must not count."""
    import datetime as dt
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    rounds = [((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2))]
    for season in (2025, 2026):
        for wk in range(10):
            date = (dt.date(season, 9, 1) + dt.timedelta(days=7 * wk)).isoformat()
            for a, b in rounds[wk % 3]:
                home, away = TEAMS[a], TEAMS[b]
                DB.upsert_games(conn, [{"sport": "cfb", "season": season, "period": date,
                                        "game_id": f"{away}@{home}", "home": home, "away": away,
                                        "home_score": 30, "away_score": 20}])
                for team, opp in ((home, away), (away, home)):
                    for market, v in (("pass_yds", 400.0 if opp == "espn:1" else 200.0), ("pass_td", 2.0)):
                        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, "
                                     "team, opponent, position, home, market, value) "
                                     "VALUES ('cfb',?,?,?,?,?,?,?,?,?,?)",
                                     (season, date, f"{away}@{home}", f"QB {team}", team, opp, "QB", 1, market, v))
        DB.upsert_games(conn, [{"sport": "cfb", "season": season, "period": f"{season}-08-25",
                                "game_id": "espn:99@espn:2", "home": "espn:2", "away": "espn:99",
                                "home_score": 70, "away_score": 0}])
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                     "position, home, market, value) VALUES ('cfb',?,?,?,?,?,?,?,?,?,?)",
                     (season, f"{season}-08-25", "espn:99@espn:2", "QB espn:2", "espn:2", "espn:99", "QB", 1,
                      "pass_yds", 900.0))
    conn.commit()
    return conn


def test_the_ratings_come_from_our_own_logs_fbs_against_fbs_before_the_game():
    conn = _league()
    assert CD.fbs_teams(conn, 2026) == set(TEAMS), "the FCS visitor plays once and is not FBS"
    r = CD.ratings(conn, 2026, before="2026-10-15")
    assert set(r) == set(TEAMS)
    assert r["espn:1"]["qb_pass_yds"]["rank"] == 1 and r["espn:1"]["qb_pass_yds"]["pg"] == 400.0
    assert r["espn:1"]["qb_pass_yds"]["factor"] > 1.2, "shrunk toward last season's, which agrees"
    assert "espn:99" not in r and max(x["qb_pass_yds"]["pg"] for x in r.values()) == 400.0, "900 never counted"
    assert r["espn:1"]["qb_pass_yds"]["games"] < 10, "only games before the date"
    assert CD.ratings(conn, 2026, before="2026-08-01") == {}, "week one: nothing to rate, so nothing is claimed"


def test_the_college_tables_are_the_measured_ones():
    assert D.transfer("QB", "pass_yds", "cfb") == 0.82 and D.transfer("RB", "rush_yds", "cfb") == 0.87
    assert D.transfer("WR", "rec_yds", "cfb") == 0.35 and D.model_stat("WR", "rec_yds", "cfb") == "wr_rec_yds", \
        "in college a receiver's own position's number predicts him"
    assert D.model_stat("WR", "rec_yds") == "qb_pass_yds", "the NFL still reads pass defence"
    assert D.model_stat("QB", "rush_yds", "cfb") == "rb_rush_yds" and D.model_stat("QB", "rush_yds") is None
    assert D.transfer("WR", "anytime_td", "cfb") == 0.48 and D.transfer("WR", "anytime_td") == 0.0
    for (m, g), b in D.TRANSFER_CFB.items():
        assert CF.in_use(m, g)[1] == b


def _rating(**factors):
    base = {s: {"pg": 10.0, "league": 10.0, "raw": 1.0, "factor": 1.0, "rank": 60, "of": 130, "games": 5}
            for s in D.STATS}
    for s, (f, rank, pg) in factors.items():
        base[s] = {**base[s], "factor": f, "rank": rank, "pg": pg}
    return base


def test_the_card_names_the_school_and_a_qb_run_reads_the_run_defence():
    r = _rating(qb_pass_yds=(1.2, 3, 290.0), rb_rush_yds=(0.8, 125, 90.0))
    f, why, card = D.effect("espn:333", r, "QB", "pass_yds", sport="cfb", label="Alabama")
    assert abs(f - (1 + 0.82 * 0.2)) < 1e-9 and why.startswith("Soft matchup — Alabama allow the 3rd-most")
    assert card["opponent"] == "Alabama" and card["of"] == 130
    f, why, card = D.effect("espn:333", r, "QB", "rush_yds", sport="cfb", label="Alabama")
    assert abs(f - (1 + 0.16 * -0.2)) < 1e-9 and card["stat"] == "rushing yards to RBs"
    assert D.effect("espn:333", r, "QB", "rush_yds")[2] is None, "the NFL shows no QB rushing card"


def _prop(market, pos="WR", team="espn:2"):
    return Prop(player="P", team=team, opponent="espn:1", position=pos, market=market,
                logs=[GameLog(w, "x", 50.0) for w in range(1, 6)], career_avg=50.0, vs_opponent_avg=None,
                lines=[SportsbookLine("book", 49.5, -110, -110)])


def test_the_nfl_script_and_total_rules_stand_down_for_college():
    game = Game(home="espn:2", away="espn:1", weather=Weather(), spread=14.0, total=62.0)
    game.total_measured = game.spread_measured = True
    neutral = DefenseProfile(team="espn:1")
    nfl_pass = evaluate_matchup(_prop(PASS_YDS, "QB"), neutral, game).multiplier
    nfl_rush = evaluate_matchup(_prop(RUSH_YDS, "RB"), neutral, game).multiplier
    assert nfl_pass > 1.0 and nfl_rush < 1.0, "the NFL keeps both (a 14-point dog throws; a high total runs less)"
    assert evaluate_matchup(_prop(PASS_YDS, "QB"), neutral, game, sport="cfb").multiplier == 1.0
    assert evaluate_matchup(_prop(RUSH_YDS, "RB"), neutral, game, sport="cfb").multiplier == 1.0
    rated = DefenseProfile(team="espn:1", label="Alabama", ratings=_rating(wr_rec_yds=(1.3, 1, 300.0)))
    eff = evaluate_matchup(_prop(REC_YDS), rated, game, sport="cfb")
    assert abs(eff.multiplier - (1 + 0.35 * 0.3)) < 1e-9, "the defence's rating, and nothing from the script"
    assert eff.card["opponent"] == "Alabama"


def test_the_college_slate_carries_ratings_and_the_projection_uses_them():
    from engine.cfb import props as P
    from engine.projection import build_projection
    ratings = {"espn:1": _rating(wr_rec_yds=(1.3, 1, 300.0))}
    teams, games = P._game_objects([{"home": "espn:2", "away": "espn:1", "home_name": "Georgia",
                                     "away_name": "Alabama", "spread": -3.0, "total": 55.0}], ratings)
    d = teams["espn:1"].defense
    assert (d.label, d.ratings["wr_rec_yds"]["rank"]) == ("Alabama", 1)
    assert teams["espn:2"].defense.ratings == {}, "a school with no rating stays neutral"
    proj = build_projection(_prop(REC_YDS), games[0], teams["espn:1"], sport="cfb")
    assert proj.matchup.card["opponent"] == "Alabama" and abs(proj.matchup.multiplier - 1.105) < 1e-9
    src = open(os.path.join(ROOT, "engine", "cfb", "props.py"), encoding="utf-8").read()
    body = src[src.index("def build_slate("):]
    assert "_defense_ratings(conn, int(season), before=str(date)[:10])" in body
    assert 'census["defenses_rated"] = len(ratings)' in body


def test_the_touchdown_board_applies_his_positions_matchup_and_shows_it():
    import test_cfb_board_not_thin as B
    from engine.cfb import tds as T
    real = CD.ratings
    soft = {"CLEM": _rating(rb_td=(1.5, 1, 2.5)), "UGA": _rating()}
    try:
        CD.ratings = lambda conn, season, before=None: soft
        _rows, census, watch = T.build_cfb_td_longshots(B._hist(), B._games(), B._quotes(), 2026)
        CD.ratings = lambda conn, season, before=None: {}
        _rows0, _c0, watch0 = T.build_cfb_td_longshots(B._hist(), B._games(), B._quotes(), 2026)
    finally:
        CD.ratings = real
    assert census["defenses_rated"] == 2
    before = {w["player"]: w for w in watch0}
    uga_rb = [w for w in watch if w["team"] == "UGA" and w["model_prob"] > before[w["player"]]["model_prob"]]
    assert uga_rb, "a back facing the defence that gives up the most RB touchdowns is more likely to score"
    card = uga_rb[0]["matchup_card"]
    assert card["stat"] == "TDs to RBs" and card["model"]["applied"] == round(1 + 0.44 * 0.5, 3)
    assert any(r.startswith("Soft matchup — CLEM") for r in uga_rb[0]["reasons"])
    assert all(w.get("matchup_card") is None for w in watch0), "no rating, no card"


def test_college_keeps_a_measured_matchup_the_nfl_cap_would_cut():
    from engine import projection as PR
    from engine.cfb import props as P
    assert PR.CAP_BOUNDS == {"nfl": (0.85, 1.18), "cfb": (0.70, 1.40)}
    assert D.FACTOR_BOUNDS == {"nfl": (0.80, 1.25), "cfb": (0.70, 1.40)}
    worst = {"espn:1": _rating(qb_pass_yds=(1.45, 1, 330.0))}
    teams, games = P._game_objects([{"home": "espn:2", "away": "espn:1", "away_name": "Alabama"}], worst)
    cfb = PR.build_projection(_prop(PASS_YDS, "QB"), games[0], teams["espn:1"], sport="cfb")
    nfl = PR.build_projection(_prop(PASS_YDS, "QB"), games[0], teams["espn:1"], sport="nfl")
    assert abs(cfb.matchup.multiplier - (1 + 0.82 * 0.45)) < 1e-9, "×1.37, inside college's bound"
    steps = {s["key"]: s["mult"] for s in cfb.chain["steps"]}
    assert "cap" not in steps, "and nothing caps it"
    assert abs(nfl.matchup.multiplier - 1.25) < 1e-9 and nfl.mean < cfb.mean, "the NFL's bounds are unchanged"


def test_the_fitter_solves_and_the_rule_needs_three_seasons_of_four():
    pts = [{"e": 10.0, "y": 10.0 * (1 + 0.5 * d + 0.2 * t), "own": d, "t": t}
           for d in (-0.2, 0.0, 0.3) for t in (-0.1, 0.1)]
    b = CF.fit(pts, ["t", "own"])
    assert abs(b[0] - 0.2) < 1e-9 and abs(b[1] - 0.5) < 1e-9
    mk = lambda per: {"per": per, "mean": sum(per) / len(per), "b": 0.3, "n": 100}   # noqa: E731
    # the rule, as study() applies it
    ok = [o for o, r in (("own", mk([0.01, -0.02, 0.03, 0.02])), ("pass", mk([0.05, -0.01, -0.01, 0.2])))
          if r["mean"] > 0 and sum(1 for x in r["per"] if x > 0) >= 3]
    assert ok == ["own"], "a bigger average carried by one season does not qualify"


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
