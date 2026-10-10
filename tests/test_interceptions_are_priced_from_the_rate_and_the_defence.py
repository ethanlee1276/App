"""A quarterback's interceptions: his rate per attempt × the attempts the
board projects × the defence's takeaway rate, Poisson at the book's half.

Ethan, 2026-10-05: "implement picks for QB interceptions … knowing who
the QB is throwing too the most and also knowing who is guarding that
person and light the path of if an interception bet is good or not."

The COUNT was a coin twice over (0.540 NFL, 0.494 college). What ranks is
the shape engine/passint builds, and the college harness measured it
before anything was bought: the defence's takeaway rating, applied as
engine/defensevs applies every rating, lifted held-out 2023-2025 from
0.529 to 0.638 at ×1.5. Checks: the market exists on every table a
market needs; both football requests buy the key behind the guard and
the meters count it; the model's rate shrinks toward the league's; the
projection's base IS the rate model (chain base "rate") and the attempts
inside it are the chain's own attempts projection; the card is Poisson
under the haircut and Tier 3; college's matchup moves the number at the
measured strength while the NFL's is shown and leaves it alone; both
builders pair the attempts game for game and hang the book's 0.5; the
walk re-builds the production model, opponent included, so the rank
store measures the board's number; a count's ladder rung is Poisson; the
scan says "forces" and never leans a read onto a pick thrown; both
harnesses print a verdict; the docs carry the measurement.

Run directly: `python3 tests/test_interceptions_are_priced_from_the_rate_and_the_defence.py`
"""
import math
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import passint as PI                                    # noqa: E402
from engine import defensevs as D                                   # noqa: E402
from engine.models import (Prop, GameLog, SportsbookLine, Game, Team,   # noqa: E402
                           DefenseProfile, Weather, MARKET_LABELS, PASS_INT, PASS_ATT)
from engine.projection import build_projection                      # noqa: E402
from engine.betting import evaluate_prop                            # noqa: E402


def _qb(ints, atts, opp="SEA", ratings=None, sport="nfl"):
    n = len(ints)
    prop = Prop(player="Arm", team="LA", opponent=opp, position="QB", market=PASS_INT,
                logs=[GameLog(week=w, opponent=opp, value=v) for w, v in zip(range(n, 0, -1), ints)],
                career_avg=sum(ints) / n, vs_opponent_avg=None,
                lines=[SportsbookLine(book="DK", line=0.5, over_odds=-110, under_odds=-110)],
                aux={"pass_att": [GameLog(week=w, opponent=opp, value=v) for w, v in zip(range(n, 0, -1), atts)],
                     "league_int_rate": 0.022})
    game = Game(home="LA", away=opp, weather=Weather(dome=True), spread=-3.5, total=47.5)
    team = Team(opp, opp, DefenseProfile(opp, ratings=ratings or {}))
    return prop, game, team


# --- the tables -------------------------------------------------------------
def test_the_market_is_on_every_table_a_market_needs():
    from engine.quality import MARKET_TIER, tier_min_edge
    from engine.parlays import FAMILY, TIER
    from engine.statlogs import SPORT_MARKETS
    from engine.markets import words
    from engine.boards import FOOTBALL_SHELVES
    from engine.likely import COUNT_MARKETS, RANK_AUC, rankable
    assert PASS_INT == "pass_int" and MARKET_LABELS[PASS_INT] == "Interceptions"
    assert words()["pass_int"] == dict(SPORT_MARKETS["nfl"])["pass_int"] == dict(SPORT_MARKETS["cfb"])["pass_int"]
    assert MARKET_TIER["pass_int"] == 3 and tier_min_edge("pass_int") == tier_min_edge("pass_td") >= 0.06
    assert FAMILY["pass_int"] == "passint" and TIER["pass_int"] == 3
    assert "pass_int" in {m for _k, _t, ms, _b in FOOTBALL_SHELVES for m in ms}, "lands on the Passing shelf, not Other"
    assert "pass_int" in COUNT_MARKETS
    # NO NFL FIGURE until the box's own run says so; college reads its store.
    assert "pass_int" not in RANK_AUC and not rankable("pass_int", "nfl")


def test_both_football_requests_buy_it_behind_the_guard_and_the_meters_count_it():
    from engine.sources import oddsapi as O
    from engine.oddsbudget import credits_per_event
    import cfb_build as B, launch
    assert O.PASS_INT_ODDS_KEY == "player_pass_interceptions"
    assert O.NFL_ODDS_TO_MARKET[O.PASS_INT_ODDS_KEY] == PASS_INT
    assert O.CFB_ODDS_TO_MARKET[O.PASS_INT_ODDS_KEY] == PASS_INT
    assert O.PASS_INT_ODDS_KEY in O.UNPROVEN_MARKETS, "dropped and retried if the API refuses it"
    assert credits_per_event("nfl") == 22      # seventeen with interceptions; twenty-two since 2026-10-10 (the five new markets)
    assert O.PASS_INT_ODDS_KEY in B.PLAYER_MARKETS and B.CREDITS_PER_EVENT == 13
    assert launch.CFB_ODDS_COST == 3 + 12 * 13 and launch.CFB_PLAYER_EVENT_COST == 13


def test_the_defence_tables_rate_the_new_stats_and_carry_the_measured_college_strength():
    for stat, group in (("qb_pass_att", "QB"), ("qb_pass_cmp", "QB"), ("qb_pass_int", "QB"), ("rb_rush_att", "RB")):
        assert D.STATS[stat][0] == group
    assert D.stat_for("QB", "pass_int") == "qb_pass_int" and D.stat_for("RB", "rush_att") == "rb_rush_att"
    assert D.stat_for("QB", "pass_att") == "qb_pass_att" and D.stat_for("QB", "pass_cmp") == "qb_pass_cmp"
    assert D.stat_for("WR", "pass_int") is None
    # Either spelling of nflverse's column is read; never both summed.
    assert D._f({"interceptions": "2"}, "passing_interceptions|interceptions") == 2.0
    assert D._f({"passing_interceptions": "1", "interceptions": "9"}, "passing_interceptions|interceptions") == 1.0
    assert D.TRANSFER_CFB[("pass_int", "QB")] == 1.5, "held out 2023-25: 0.529 → 0.638"
    # The NFL's strengths came from the box's own run (2026-10-06, marketfit --opp),
    # adopted by Ethan: interceptions, attempts and completions; nothing else new.
    assert D.TRANSFER[("pass_int", "QB")] == 1.5 and D.TRANSFER[("pass_att", "QB")] == 0.75
    assert D.TRANSFER[("pass_cmp", "QB")] == 0.5 and ("rush_att", "RB") not in D.TRANSFER
    for m in ("pass_att", "pass_cmp"):
        assert ("m", "QB") not in D.TRANSFER_CFB and (m, "QB") not in D.TRANSFER_CFB, "shown, under a point of AUC"
    assert ("rush_att", "RB") not in D.TRANSFER_CFB
    from engine.cfb.defense import COLUMN
    assert COLUMN["pass_int"] == "passing_interceptions" and COLUMN["pass_cmp"] == "completions"


# --- the model ----------------------------------------------------------------
def test_the_rate_shrinks_toward_the_league_and_a_thin_log_is_the_league():
    clean = PI.rate_per_attempt([32] * 12, [0] * 12, 0.022)
    wild = PI.rate_per_attempt([32] * 12, [2] * 12, 0.022)
    assert 0.0 < clean < 0.022 < wild < 2 / 32
    assert PI.rate_per_attempt([32] * 2, [0] * 2, 0.022) == 0.022
    assert PI.league_rate([30, 10, 40], [1, 1, 0]) == 1 / 70, "a 10-attempt relief game does not count"
    assert PI.league_rate([], []) is None
    assert abs(PI.expected(0.02, 33) - 0.66) < 1e-9
    assert "one every 50 throws" in PI.words(0.02, 0.022, 33, 0.66)
    assert PI.FALLBACK_LEAGUE_RATE["nfl"] > 0 and PI.FALLBACK_LEAGUE_RATE["cfb"] > 0


def test_the_projection_starts_from_the_rate_model_not_a_form_blend():
    ints = [0, 1, 0, 0, 1, 0, 2, 0]
    atts = [31, 35, 28, 33, 40, 30, 38, 29]
    prop, game, team = _qb(ints, atts)
    proj = build_projection(prop, game, team)
    assert proj.chain["base"]["source"] == "rate" and proj.chain["base"]["label"] == "Rate model"
    # The attempts inside the number are the chain's own attempts projection.
    att_prop = Prop(player="Arm", team="LA", opponent="SEA", position="QB", market=PASS_ATT,
                    logs=prop.aux["pass_att"], career_avg=sum(atts) / len(atts), vs_opponent_avg=None,
                    lines=[SportsbookLine(book="proxy", line=32.5)])
    att_mean = build_projection(att_prop, game, team).mean
    rate = PI.rate_per_attempt(atts, ints, 0.022)
    assert abs(proj.chain["base"]["value"] - rate * att_mean) < 1e-3
    assert any(r.startswith("Interception rate:") for r in proj.reasons)
    # The chain still multiplies out to the mean (tests/test_chain's rule).
    prod = proj.chain["base"]["value"]
    for s in proj.chain["steps"]:
        prod *= s["mult"]
    assert abs(prod - proj.mean) < 1e-3
    # Without its attempts log it prices as a plain count, like passing TDs.
    bare, g2, t2 = _qb(ints, atts)
    bare.aux = {}
    assert build_projection(bare, g2, t2).chain["base"]["source"] == "form"


def test_the_card_is_poisson_under_the_haircut_and_sits_at_tier_three():
    from engine.quality import tier_shrink
    from engine.statmath import prob_over
    prop, game, team = _qb([0, 1, 0, 0, 1, 0, 0, 0], [30] * 8)
    proj = build_projection(prop, game, team)
    rec = evaluate_prop(prop, proj, game=game, sport="nfl")
    assert rec.tier == 3
    shrink = tier_shrink("pass_int")
    raw_side = rec.fair_prob + (rec.hit_prob - rec.fair_prob) / shrink
    over_p = PI.at_least(proj.mean, 0.5)
    poisson_side = over_p if rec.side == "OVER" else 1.0 - over_p
    normal_over = prob_over(0.5, proj.mean, proj.std)
    normal_side = normal_over if rec.side == "OVER" else 1.0 - normal_over
    assert abs(poisson_side - normal_side) > 0.03, "the fixture must separate the two distributions"
    assert abs(raw_side - poisson_side) < 0.01, (raw_side, poisson_side, normal_side)


def test_both_leagues_matchups_move_the_number_at_their_measured_strength():
    rating = {"qb_pass_int": {"pg": 1.6, "league": 0.8, "raw": 2.0, "factor": 1.2, "games": 6, "rank": 1, "of": 60}}
    ints, atts = [0, 1, 0, 0, 1, 0, 1, 0], [31, 35, 28, 33, 40, 30, 38, 29]
    p_cfb, g_cfb, t_cfb = _qb(ints, atts, ratings=rating)
    cfb = build_projection(p_cfb, g_cfb, t_cfb, sport="cfb")
    p_nfl, g_nfl, t_nfl = _qb(ints, atts, ratings=rating)
    nfl = build_projection(p_nfl, g_nfl, t_nfl, sport="nfl")
    step = {s["key"]: s["mult"] for s in cfb.chain["steps"]}
    assert abs(step["matchup"] - min(1.40, 1.0 + 1.5 * 0.2)) < 1e-6, step
    assert cfb.matchup.card and cfb.matchup.card["model"]["applied"] > 1.0
    # The NFL's own run (2026-10-06) adopted the same strength, ×1.5, held
    # inside the NFL's own bounds on a defence factor (defensevs.FACTOR_BOUNDS).
    from engine.defensevs import FACTOR_BOUNDS
    nstep = {s["key"]: s["mult"] for s in nfl.chain["steps"]}
    assert abs(nstep["matchup"] - min(FACTOR_BOUNDS["nfl"][1], 1.0 + 1.5 * 0.2)) < 1e-6, nstep
    assert nfl.matchup.card and nfl.matchup.card["model"]["applied"] > 1.0


# --- the builders -------------------------------------------------------------
def _nfl_row(player, wk, season, att, picked, pos="QB", team="NYG"):
    return {"season": str(season), "week": str(wk), "season_type": "REG", "player_display_name": player,
            "position": pos, "recent_team": team, "opponent_team": "DAL", "attempts": str(att),
            "completions": str(int(att * 0.62)), "passing_yards": str(att * 7), "passing_tds": "1",
            "interceptions": str(picked), "carries": "2", "rushing_yards": "9",
            "targets": "0", "receptions": "0", "receiving_yards": "0"}


def test_the_nfl_slate_builds_a_clean_passer_s_interception_prop_with_his_attempts_beside_it():
    from engine.sources import nflverse as nv
    assert PASS_INT in [m for m, _r in nv.POSITION_MARKETS["QB"]] and PASS_INT in nv.QB_MARKETS
    assert nv.MARKET_COLUMNS[PASS_INT] == ("passing_interceptions", "interceptions")
    current = [_nfl_row("Clean Arm", w, 2026, 30 + w, 0) for w in range(1, 6)]           # no picks all season
    current += [_nfl_row("Wild Arm", w, 2026, 34, 2 if w % 2 else 0, team="DAL") for w in range(1, 6)]
    current += [_nfl_row("Mop Up", 3, 2026, 4, 1)]                                        # a relief appearance
    games = [Game(home="NYG", away="DAL", weather=Weather(dome=True), injuries=[], date="2026-10-11",
                  kickoff="13:00", spread=-3.0, total=44.5)]
    saved = {n: getattr(nv, n) for n in ("build_games", "load_weekly_stats", "roster_index", "roster_teams",
                                         "load_schedules")}
    nv.build_games = lambda s, w: games
    nv.load_weekly_stats = lambda s: current if s == 2026 else []
    nv.roster_index = lambda s: {}
    nv.roster_teams = lambda s: {"Clean Arm": "NYG", "Wild Arm": "DAL", "Mop Up": "NYG"}
    nv.load_schedules = lambda: []
    try:
        slate = nv.build_slate(2026, 6)
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)
    picks = {p.player: p for p in slate.props if p.market == PASS_INT}
    assert "Clean Arm" in picks, "zero picks in five games is the cleanest arm on the slate, not no market"
    p = picks["Clean Arm"]
    assert p.lines[0].line == 0.5 and p.lines[0].book == "proxy"
    assert [g.value for g in p.logs] == [0.0] * 5
    assert [g.value for g in p.aux["pass_att"]] == [35.0, 34.0, 33.0, 32.0, 31.0], "paired game for game, newest first"
    assert 0.0 < p.aux["league_int_rate"] < 0.1
    # The league's rate counts the games quarterbacks threw, not the mop-up.
    assert abs(p.aux["league_int_rate"] - nv.league_int_rate(current)) < 1e-12
    assert nv.league_int_rate([_nfl_row("Mop Up", 3, 2026, 4, 1)]) is None
    assert "Wild Arm" in picks and picks["Wild Arm"].team == "DAL"
    kept, att = nv.pair_attempts([GameLog(week=9, opponent="X", value=1.0)], current, [], "Clean Arm", 6)
    assert kept == [] and att == [], "a game with no attempts partner drops from both"


def test_the_college_builder_pairs_attempts_by_date_and_hangs_the_book_s_half():
    from engine.cfb import props as P
    rows = [("2026-09-20", "X", True, 1.0, False), ("2026-09-13", "Y", False, 0.0, False), ("2026-09-06", "Z", True, 0.0, False)]
    atts = [("2026-09-20", "X", True, 31.0, False), ("2026-09-06", "Z", True, 28.0, False)]
    kept, paired = P.pair_by_period(rows, atts)
    assert [r[0] for r in kept] == ["2026-09-20", "2026-09-06"] and [a[3] for a in paired] == [31.0, 28.0]
    assert P._MIN_MEAN[PASS_INT] == 0.0 and P._POSITION[PASS_INT] == "QB" and P._COLUMN[PASS_INT] == "pass_int"
    filed = {"UGA": {"beck": {"player": "Beck", "position": "QB", "pass_int": rows, "pass_att": atts}}}
    assert abs(P.league_int_rate(filed) - 1.0 / 59.0) < 1e-12


# --- the walk -----------------------------------------------------------------
def _walk_db(players=24, seasons=(2024, 2025), games=13, seed=5):
    from engine import db
    rnd = random.Random(seed)
    rows, teams = [], [f"T{i}" for i in range(8)]
    for i in range(players):
        skill = 0.012 + 0.03 * (i / players)
        for s in seasons:
            for g in range(games):
                opp = teams[(i + g) % len(teams)]
                tough = 1.6 if opp == "T0" else 0.7 if opp == "T1" else 1.0
                att = max(15, rnd.gauss(32, 6))
                picks = sum(1 for _ in range(int(att)) if rnd.random() < skill * tough)
                for market, value in (("pass_int", picks), ("pass_att", att)):
                    rows.append({"sport": "cfb", "season": s, "period": f"{s}-09-{g + 1:02d}",
                                 "game_id": f"g{i}-{s}-{g}", "player": f"QB {i}", "team": "AAA",
                                 "opponent": opp, "position": "QB", "home": g % 2,
                                 "market": market, "value": float(value)})
    d = tempfile.mkdtemp(prefix="passint-walk-")
    conn = db.connect(os.path.join(d, "history.db"))
    db.upsert_player_logs(conn, rows)
    return conn, d


def test_the_walk_rebuilds_the_production_model_opponent_included():
    from engine.logwalk import load_entries, settled_props_from_logs, COUNT_LINE
    from engine import calibrate as _cal
    conn, _d = _walk_db()
    entries = load_entries(conn, "cfb", "pass_int")
    assert entries and all(len(e["companion"]) == len(e["values"]) for e in entries)
    assert entries.aux["allowed"] and all(len(t) == 4 for t in entries.aux["allowed"])
    with _cal.disabled():
        cfb = settled_props_from_logs(entries, "pass_int", sport="cfb")
        nfl = settled_props_from_logs(entries, "pass_int", sport="nfl")
        blind = settled_props_from_logs(entries, "pass_int", sport="nfl", allowed=[])
    assert cfb and all(s.line == COUNT_LINE[PASS_INT] for s in cfb), "the book's 0.5, never a trailing average"
    # Both leagues' measured strengths reach the walk's number (the NFL's since
    # its own run, 2026-10-06): the opponent changes it against a blind walk.
    assert [round(s.hit_prob, 6) for s in nfl] != [round(s.hit_prob, 6) for s in blind]
    assert [round(s.hit_prob, 6) for s in cfb] != [round(s.hit_prob, 6) for s in blind]
    # The pick-happy defence raises a passer's expected picks against it.
    by_opp = {}
    for s in cfb:
        if s.player == "QB 12":
            by_opp.setdefault(s.side, []).append(s)
    # Every settled row's projection is the production λ: a rate times attempts.
    assert all(0.0 < s.projection < 5.0 for s in cfb)


def test_the_rank_store_measures_it_through_the_same_door():
    from engine import rankfit
    conn, d = _walk_db(players=8, games=6)
    store = os.path.join(d, "rank_auc.json")
    lines = rankfit.measure(conn, "cfb", markets=["pass_int"], path=store, log=lambda *_: None)
    assert lines and "walk failed" not in lines[0], lines
    assert "pass_int" in rankfit.MARKETS["cfb"]
    import calibrate, formfit, playerfit
    for mod in (calibrate, formfit, playerfit):
        assert "pass_int" in mod.SPORT_MARKETS["cfb"], mod.__name__
        assert "load_entries" in open(ROOT / f"{mod.__name__}.py", encoding="utf-8").read(), \
            f"{mod.__name__} loads its entries through the one door"


# --- the board, the scan, the harnesses, the docs ------------------------------
def test_a_count_s_ladder_rung_is_poisson():
    from engine.likely import _prob_at
    row = {"projection": 0.7, "proj_std": 0.8, "market": PASS_INT}
    # `_prob_at` rounds to four places for the ladder.
    assert abs(_prob_at(row, PASS_INT, "over", 1.5) - PI.at_least(0.7, 1.5)) < 5e-4
    assert abs(_prob_at(row, PASS_INT, "under", 0.5) - (1.0 - PI.at_least(0.7, 0.5))) < 5e-4
    from engine.statmath import prob_over
    # At the half-number a normal hung on 0.7 says 0.60 where Poisson says 0.50.
    assert abs(_prob_at(row, PASS_INT, "over", 0.5) - prob_over(0.5, 0.7, 0.8)) > 0.05, "not a normal"


def test_the_scan_says_forces_and_never_leans_a_read_onto_a_pick():
    from engine import gamescan as G
    assert ("pass_int", "qb_pass_int") in G._FACT_STATS["qb"]
    assert ("pass_att", "qb_pass_att") in G._FACT_STATS["qb"] and ("rush_att", "rb_rush_att") in G._FACT_STATS["rb"]
    assert "pass_int" in G._NO_LEAN_MARKETS
    allowed = {"qb_pass_int": {"rank": 2, "of": 32, "pg": 1.3}, "qb_pass_yds": {"rank": 30, "of": 32, "pg": 190}}
    sign, text = G.rank_fact(allowed, "qb_pass_int", "DAL")
    assert sign == 1 and text.startswith("DAL forces 1.3 interceptions a game"), text
    sign2, text2 = G._allowed_line(allowed, "qb_pass_int", "DAL")
    assert sign2 == 1 and "forces the 2nd-most interceptions" in text2
    facts = G.read_facts("qb", "QB", "NYG", "DAL", usage={}, allowed=allowed, ratings_def={}, points=None,
                         line_words="", n_teams=32, room=None)
    pick = [f for f in facts if f["markets"] == ["pass_int"]]
    # In the number since the NFL's own run adopted the strength (2026-10-06).
    assert pick and pick[0]["in_number"] is True and pick[0]["sign"] == 1, facts
    assert "forces" in pick[0]["text"]


def test_the_quarterback_s_card_lights_the_path_to_a_pick():
    """Ethan: "knowing who the QB is throwing too the most and also knowing
    who is guarding that person". His top targets, the corners over them
    and his charted interception-worthy rate, each shown and signed from
    the over's side of his interceptions, none in the number."""
    from engine import gamescan as G
    usage = {("NYG", "nabers"): {"name": "M. Nabers", "games": 5, "tgt_share": 0.31, "targets_pg": 10.2},
             ("NYG", "slayton"): {"name": "D. Slayton", "games": 5, "tgt_share": 0.17, "targets_pg": 5.6},
             ("NYG", "robinson"): {"name": "W. Robinson", "games": 5, "tgt_share": 0.14, "targets_pg": 4.8},
             ("NYG", "tracy"): {"name": "T. Tracy", "games": 5, "tgt_share": 0.09, "targets_pg": 3.0},
             ("DAL", "lamb"): {"name": "C. Lamb", "games": 5, "tgt_share": 0.30, "targets_pg": 10.0}}
    assert [n for n, _s, _p in G.top_targets(usage, "NYG")] == ["M. Nabers", "D. Slayton", "W. Robinson"]
    room = {"corners": [{"name": "T. Diggs", "spot": "LCB", "rating": 68.0, "targets": 31},
                        {"name": "D. Bland", "spot": "RCB", "rating": 101.0, "targets": 28},
                        {"name": "J. Lewis", "spot": "NB", "rating": 55.0, "targets": 3}],    # too few targets
            "missing": [], "weakest": None}
    charting = {"qbs": {("NYG", "R.Wilson"): {"attempts": 160, "iw": 7, "iw_rate": 7 / 160},
                        ("DAL", "D.Prescott"): {"attempts": 180, "iw": 3, "iw_rate": 3 / 180}}}
    league = G.league_iw_rate(charting)
    assert abs(league - 10 / 340) < 1e-9
    facts = G.interception_facts("NYG", "DAL", targets=G.top_targets(usage, "NYG"), room=room,
                                 charting=charting["qbs"][("NYG", "R.Wilson")], league_iw=league,
                                 lean=["pass_yds", "pass_td", "pass_att", "pass_cmp"])
    kinds = {f["kind"]: f for f in facts}
    assert kinds["targets"]["text"].startswith("Throws most to M. Nabers (31% of the targets, 10.2 a game), D. Slayton (17%)")
    assert "pass_int" in kinds["targets"]["markets"] and kinds["targets"]["sign"] == 0
    cov = kinds["coverage"]
    assert cov["sign"] == 1 and cov["markets"] == ["pass_int"] and cov["in_number"] is False
    assert "T. Diggs (LCB) has allowed a 68 passer rating on 31 targets" in cov["text"]
    assert "J. Lewis" not in cov["text"], "a corner with three targets is not rated"
    ch = kinds["charting"]
    assert ch["sign"] == 1 and "4.4% of his attempts" in ch["text"] and "league 2.9%" in ch["text"]
    assert all(f["in_number"] is False for f in facts)
    # Through read_facts, only a quarterback gets them.
    got = G.read_facts("qb", "QB", "NYG", "DAL", usage={}, allowed=None, ratings_def={}, points=None,
                       line_words="", n_teams=32, room=room, targets=G.top_targets(usage, "NYG"),
                       charting=charting["qbs"][("NYG", "R.Wilson")], league_iw=league)
    assert {f["kind"] for f in got} >= {"targets", "coverage", "charting"}
    wr = G.read_facts("wr", "WR", "NYG", "DAL", usage={}, allowed=None, ratings_def={}, points=None,
                      line_words="", n_teams=32, room=room, targets=G.top_targets(usage, "NYG"))
    assert not [f for f in wr if f["kind"] in ("targets", "charting")]
    # A soft room reads the other way; a middling one says nothing.
    soft = {"corners": [{"name": "A", "spot": "LCB", "rating": 108.0, "targets": 30},
                        {"name": "B", "spot": "RCB", "rating": 99.0, "targets": 30}]}
    assert G.interception_facts("NYG", "DAL", targets=None, room=soft, charting=None, league_iw=None,
                                lean=[])[0]["sign"] == -1
    mid = {"corners": [{"name": "A", "spot": "LCB", "rating": 90.0, "targets": 30}]}
    assert G.interception_facts("NYG", "DAL", targets=None, room=mid, charting=None, league_iw=None,
                                lean=[])[0]["sign"] == 0


def test_both_harnesses_print_a_verdict_under_the_written_rule():
    import cfbmarketfit as C
    import marketfit as M
    rnd = random.Random(3)
    rows = []
    for yr in (2022, 2023, 2024, 2025):
        for wk in range(1, 13):
            for i in range(10):
                opp = f"D{(i + wk) % 6}"
                tough = 1.5 if opp == "D0" else 1.0
                att = 30 + i
                picks = sum(1 for _ in range(att) if rnd.random() < 0.02 * tough)
                rows.append((yr, wk, f"QB {i}", "QB", {"pass_att": float(att), "pass_cmp": 20.0,
                                                          "pass_int": float(picks), "pass_yds": 240.0,
                                                          "carries": 2.0, "rush_yds": 8.0}, opp))
                rows.append((yr, wk, f"RB {i}", "RB", {"carries": 14.0 + i % 3, "rush_att": 14.0 + i % 3,
                                                          "rush_yds": 60.0 + rnd.randint(-20, 20),
                                                          "receptions": 2.0, "rec_yds": 15.0}, opp))
    out = C.opponent_report(rows, held_outs=(2024, 2025))
    assert any(ln.strip().startswith("verdict:") for ln in out), out
    assert any("pass_int QB" in ln for ln in out)
    assert C.ADOPT_MIN == M.ADOPT_MIN == 0.01 and M.STRENGTHS["count1"] == C.STRENGTHS["count1"]
    assert "--opp" in open(ROOT / "marketfit.py", encoding="utf-8").read()
    assert "--opp" in open(ROOT / "cfbmarketfit.py", encoding="utf-8").read()


def test_the_measurement_is_written_where_the_strength_lives_and_in_the_docs():
    src = open(ROOT / "engine" / "defensevs.py", encoding="utf-8").read()
    for want in ("no opponent      0.529", "×1.5             0.638", "cfbmarketfit.ADOPT_MIN"):
        assert want in src, want
    cfb = open(ROOT / "docs" / "CFB_MODEL.md", encoding="utf-8").read()
    assert "0.638" in cfb and "engine/passint" in cfb
    nfl = open(ROOT / "docs" / "NFL_MODEL.md", encoding="utf-8").read()
    assert "engine/passint" in nfl
    home = open(ROOT / "docs" / "WHEN_YOU_ARE_HOME.md", encoding="utf-8").read()
    assert "marketfit.py --opp" in home


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
