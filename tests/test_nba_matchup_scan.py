"""The NBA matchup scan: offence against defence, key matchups, and a read
on every key player (engine/nba/teams, engine/nba/scan).

Ethan, 2026-10-20: "make sure nba is ready to go. We need most likely and
edge bets being posted and recorded. We also need it too match nfl for like
all features and data ... We need offense vs defense ... We need matchup
details ... We need reports for nba and key matchups and breakout players."

  * every team's offence and defence: points for and against, possessions
    counted the standard way (FGA − OREB + TOV + 0.44 × FTA), pace, the
    ratings per 100 and the four factors, each ranked 1 = best, this season
    blended with last at games / (games + 10);
  * the tale of the tape formatted for the page and the report, and the key
    matchups — an offence near the top against a defence near the bottom;
  * a read on every key player — the defence in his own stats, the game,
    his role (minutes, usage, a teammate's measured absence), rest and the
    blowout — could shine, could struggle, breakout only on a role change;
  * the reads lean Most Likely, decide the one board's matchup check and
    make matchup picks journaled on paper, as the NFL's and MLB's do;
  * the box score keeps the shooting columns that possessions need, and the
    NBA's history reads ESPN's six old club codes as the league's.

Run directly: `python3 tests/test_nba_matchup_scan.py`
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.nba import scan as S, teams as T          # noqa: E402


def _night(day, team, opp, **tot):
    """One team-night as log rows, all of it on one player (sums are sums)."""
    return [(day, team, opp, k, float(v)) for k, v in tot.items()]


def _game(day, a, b, sa, sb):
    return _night(day, a, b, **sa) + _night(day, b, a, **sb)


#: A box line: 100 possessions, 110 points (a 110 rating), 240 team minutes.
BASE = dict(pts=110, reb=44, ast=25, fg3m=12, stl=7, blk=5, tov=14, min=240, fgm=40, fga=88,
            fg3a=34, ftm=18, fta=23, oreb=10)


def _poss(x):
    return x["fga"] - x["oreb"] + x["tov"] + 0.44 * x["fta"]


def test_possessions_pace_and_ratings_are_counted_the_standard_way():
    a = dict(BASE)
    b = dict(BASE, pts=100, fgm=36, fga=90, oreb=12, tov=12, fta=20, ftm=15, fg3m=10, fg3a=36, reb=46, min=265)
    rows = []
    for i in range(3):
        rows += _game(f"2026-01-0{i + 1}", "BOS", "MIA", a, b)
    prof = T.season_profiles(T.team_games(rows))
    bos, mia = prof["BOS"], prof["MIA"]
    game_poss = (_poss(a) + _poss(b)) / 2
    assert abs(bos["poss"] - game_poss) < 1e-9 and abs(mia["poss"] - game_poss) < 1e-9
    assert abs(bos["ortg"] - 100 * 110 / game_poss) < 1e-9, bos["ortg"]
    assert abs(bos["drtg"] - 100 * 100 / game_poss) < 1e-9
    assert abs(bos["net"] - (bos["ortg"] - bos["drtg"])) < 1e-9
    # Pace per 48: BOS's 240 team minutes are a regulation game; MIA's 265
    # are an overtime one, so the same possessions are a slower pace.
    assert abs(bos["pace"] - game_poss) < 1e-9
    assert abs(mia["pace"] - 48 * game_poss / 53) < 1e-9
    assert abs(bos["efg"] - (40 + 6) / 88) < 1e-9 and abs(bos["opp_efg"] - (36 + 5) / 90) < 1e-9
    assert abs(bos["tov_pct"] - 14 / (88 + 0.44 * 23 + 14)) < 1e-9
    assert abs(bos["oreb_pct"] - 10 / (10 + (46 - 12))) < 1e-9
    assert abs(bos["dreb_pct"] - (44 - 10) / ((44 - 10) + 12)) < 1e-9
    assert abs(bos["ftr"] - 23 / 88) < 1e-9 and abs(bos["fg3_pct"] - 12 / 34) < 1e-9
    assert bos["pts"] == 110 and bos["opp_pts"] == 100 and bos["margin"] == 10 and bos["games"] == 3


def _league(n_games=4, shooting=True, codes=("BOS", "MIA", "NYK", "PHI"), day0=1, month="01"):
    """A small league: BOS fast and good, MIA slow and leaky, NYK and PHI
    in between — every team plays every other."""
    style = {"BOS": dict(fga=96, pts=122, tov=11, fg3m=16, fg3a=40),
             "MIA": dict(fga=82, pts=104, tov=17, fg3m=9, fg3a=30),
             "NYK": dict(fga=88, pts=112, tov=14, fg3m=12, fg3a=34),
             "PHI": dict(fga=90, pts=110, tov=13, fg3m=13, fg3a=35)}
    rows, d = [], day0
    for _ in range(n_games):
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                sa, sb = dict(BASE, **style.get(a, {})), dict(BASE, **style.get(b, {}))
                if not shooting:
                    sa = {k: v for k, v in sa.items() if k not in ("fgm", "fga", "fg3a", "ftm", "fta", "oreb")}
                    sb = {k: v for k, v in sb.items() if k not in ("fgm", "fga", "fg3a", "ftm", "fta", "oreb")}
                rows += _game(f"2026-{month}-{d:02d}", a, b, sa, sb)
                d += 1
    return rows


def test_ranks_run_best_first_and_pace_fastest_first():
    prof = T.build([], _league())
    rk = {t: p["ranks"] for t, p in prof["teams"].items()}
    assert rk["BOS"]["pts"] == 1 and rk["MIA"]["pts"] == 4
    assert rk["BOS"]["tov"] == 1 and rk["MIA"]["tov"] == 4, rk     # the fewest turnovers is best
    assert rk["BOS"]["pace"] == 1 and rk["MIA"]["pace"] == 4    # the fastest first
    assert prof["per100"] is True and prof["n"] == 4
    # Points allowed: 1 is the FEWEST allowed.
    allowed = sorted(prof["teams"], key=lambda t: prof["teams"][t]["opp_pts"])
    assert rk[allowed[0]]["opp_pts"] == 1 and rk[allowed[-1]]["opp_pts"] == 4
    assert "pace" in T.PLAIN


def test_this_season_takes_over_from_last_at_games_over_games_plus_ten():
    last = _league(n_games=4, month="03")
    now = _league(n_games=2, month="11")     # 6 games each this season
    prof = T.build(now, last)
    bos = prof["teams"]["BOS"]
    assert bos["games_season"] == 6 and abs(bos["season_weight"] - 6 / 16) < 1e-3, bos["season_weight"]
    p_now = T.season_profiles(T.team_games(now))["BOS"]["pts"]
    p_last = T.season_profiles(T.team_games(last))["BOS"]["pts"]
    assert abs(bos["pts"] - (6 / 16 * p_now + 10 / 16 * p_last)) < 1e-9
    # Two games this season are counted and not rated: last season alone.
    early = T.build(_night("2026-11-01", "BOS", "MIA", **BASE) + _night("2026-11-01", "MIA", "BOS", **BASE), last)
    b = early["teams"]["BOS"]
    assert b["games_season"] == 1 and b["season_weight"] == 0.0 and b["pts"] == p_last
    # The walk-forward: nothing on or after the board's date counts.
    cut = T.build(now, last, before="2026-11-02")
    assert cut["teams"]["BOS"]["games_season"] < 6


def test_without_the_shooting_columns_the_tape_reads_per_game():
    prof = T.build([], _league(shooting=False))
    assert prof["per100"] is False and "ortg" not in prof["teams"]["BOS"]
    tape = S.tape("BOS", "MIA", prof)
    labels = [r["label"] for r in tape["rows"]]
    assert labels == [label for _k, label, _f in S.PER_GAME_ROWS], labels
    assert tape["per100"] is False
    assert all(e["unit"] in ("pts", "opp_pts", "fg3m", "opp_fg3m", "reb", "opp_reb", "tov", "opp_tov", "pace")
               for e in tape["edges"]), tape["edges"]


def test_espn_spellings_count_as_the_league_codes():
    rows = (_night("2026-01-01", "GS", "NY", **BASE) + _night("2026-01-01", "NY", "GS", **BASE)
            + _night("2026-01-03", "GSW", "NYK", **BASE) + _night("2026-01-03", "NYK", "GSW", **BASE))
    nights = T.team_games(rows, "nba")
    assert {k[0] for k in nights} == {"GSW", "NYK"} and nights[("GSW", "2026-01-01")]["opp"] == "NYK"
    # The WNBA's rows are read as stored, as its board reads them.
    assert ("GS", "2026-01-01") in T.team_games(rows, "wnba")


def test_the_tape_formats_rows_the_lines_and_the_key_matchups():
    prof = T.build([], _league())
    g = {"home": "BOS", "away": "MIA", "spread": -9.5, "total": 226.5}
    env = S.environment(g, prof)
    assert env["BOS"]["implied"] == (226.5 + 9.5) / 2 and env["MIA"]["implied"] == (226.5 - 9.5) / 2
    assert env["BOS"]["spread"] == -9.5 and env["MIA"]["spread"] == 9.5
    tape = S.tape("BOS", "MIA", prof, env=env, rest={"MIA": "b2b_home", "BOS": "2plus"})
    labels = [r["label"] for r in tape["rows"]]
    assert labels[:5] == ["Points a game", "Points allowed a game", "Offense: points per 100 possessions",
                          "Defense: points allowed per 100", "Pace: possessions per 48 minutes"], labels
    assert labels[-1] == "Points the lines expect tonight"
    pts = tape["rows"][0]
    assert pts["a"] == f"{prof['teams']['MIA']['pts']:.1f}" and pts["hr"] == 1 and pts["plain"] is False
    efg = next(r for r in tape["rows"] if r["key"] == "efg")
    assert efg["h"].endswith("%")
    assert next(r for r in tape["rows"] if r["key"] == "pace")["plain"] is True
    assert tape["sides"]["MIA"]["rest_word"] == "on the second night of a back-to-back"
    assert tape["sides"]["BOS"]["implied"] == 118.0
    assert tape["teams"] == 4 and tape["per100"] is True
    assert "None of this moves our numbers" in tape["basis"]
    assert tape["note"].startswith("Last season's numbers for both teams"), tape["note"]
    # Key matchups: the best offence against the worst defence reads as an edge.
    texts = [e["text"] for e in tape["edges"]]
    assert any(t.startswith("Edge BOS: BOS's offense (1st in points per 100) against MIA's defense (") for t in texts), texts
    for e in tape["edges"]:
        assert e["tone"] in ("off", "def", "pace") and (e["tone"] == "pace" or e["gap"] >= 2)


def _hist(mins, pts, reb=None, ast=None, fg3m=None, opps=None, starter=True, team="BOS"):
    n = len(mins)
    dates = [f"2026-01-{30 - i:02d}" for i in range(n)]
    h = {"team": team, "starter": starter, "minutes": list(mins), "pts": list(pts),
         "reb": list(reb or [2] * n), "ast": list(ast or [1] * n), "fg3m": list(fg3m or [0] * n),
         "dates": dates, "opps": list(opps or ["NYK"] * n), "by_week": {}}
    for i, d in enumerate(dates):
        h["by_week"][d] = {"min": mins[i], "pts": h["pts"][i], "reb": h["reb"][i], "ast": h["ast"][i]}
    return h


DVP = {"MIA": {"pts": {"pg": 119.4, "league": 113.0, "rank": 2, "of": 30, "games": 9},
               "reb": {"pg": 40.2, "league": 44.0, "rank": 29, "of": 30, "games": 9},
               "ast": {"pg": 29.0, "league": 26.0, "rank": 3, "of": 30, "games": 9}}}


def test_a_read_counts_the_defence_the_game_his_role_rest_and_the_blowout():
    h = _hist(mins=[36] * 5 + [30] * 10, pts=[28] * 15, reb=[9] * 15, ast=[6] * 15)
    env = {"BOS": {"implied": 121.0, "league_pts": 113.0, "pace": None, "league_pace": None, "spread": -4.0}}
    r = S.read_player("Jay Star", h, "BOS", "MIA", dvp=DVP, env=env, rest={"MIA": "3in4", "BOS": "2plus"})
    assert r["pro"] == ["MIA allows the 2nd-most points a game (119.4)",
                        "MIA allows the 3rd-most assists a game (29.0)",
                        "BOS is expected to score 121.0 by the lines — +8.0 on the league's average",
                        "Minutes up 20% over his last five (36.0 a game, 30.0 before)",
                        "MIA is playing a third game in four nights"], r["pro"]
    assert r["con"] == ["MIA allows the 2nd-fewest rebounds a game (40.2)"], r["con"]
    assert r["read"] == "breakout" and r["label"] == "Breakout spot"
    # The read leans what he produces, less the stat the defence argues against.
    assert "pts" in r["lean"] and "ast" in r["lean"] and "reb" not in r["lean"], r["lean"]
    assert "pts_ast" in r["lean"] and "pra" not in r["lean"] and "pts_reb" not in r["lean"], r["lean"]
    assert set(r) >= {"player", "team", "opp", "pos", "read", "label", "pro", "con", "notes", "lean",
                      "headshot", "usage"}
    assert r["usage"]["mpg"] == 33.0 and r["usage"]["min5"] == 36.0
    assert any(n.startswith("28.0 points, 9.0 rebounds, 6.0 assists a game over his last five") for n in r["notes"])


def test_a_breakout_needs_a_role_change():
    flat = _hist(mins=[34] * 15, pts=[28] * 15, reb=[3] * 15, ast=[6] * 15)
    env = {"BOS": {"implied": 121.0, "league_pts": 113.0, "spread": -4.0}}
    r = S.read_player("Jay Star", flat, "BOS", "MIA", dvp=DVP, env=env, rest={"MIA": "b2b_home"})
    assert len(r["pro"]) - len(r["con"]) >= 3 and r["read"] == "good", (r["pro"], r["con"])


def test_a_teammate_out_counts_only_when_the_logs_measured_it():
    h = _hist(mins=[26] * 12, pts=[14] * 12)
    measured = {"BOS": {"out": [("Big Man", 34.0)], "inherit": {
        "player": "Big Man", "enough": True, "n_out": 6,
        "beneficiaries": {"Wing Guy": {"with": 0.12, "without": 0.17, "delta": 0.05, "n_with": 20, "n_without": 6}}}}}
    r = S.read_player("Wing Guy", h, "BOS", "MIA", vacancy=measured)
    assert "In the 6 games Big Man missed, he took 17% of BOS's points (12% with Big Man playing)" in r["pro"]
    thin = {"BOS": {"out": [("Big Man", 34.0)], "inherit": dict(measured["BOS"]["inherit"], enough=False)}}
    r2 = S.read_player("Wing Guy", h, "BOS", "MIA", vacancy=thin)
    assert not r2["pro"] and any(n.startswith("Big Man is out (34 minutes a game)") for n in r2["notes"])
    # Never his own absence.
    r3 = S.read_player("Big Man", h, "BOS", "MIA", vacancy=measured)
    assert not any("Big Man missed" in p for p in r3["pro"])


def test_the_blowout_is_a_starters_worry_and_rest_cuts_both_ways():
    starter = _hist(mins=[34] * 12, pts=[20] * 12)
    bench = _hist(mins=[18] * 12, pts=[8] * 12, starter=False)
    env = {"BOS": {"spread": -12.5}}
    rs = S.read_player("Starter", starter, "BOS", "MIA", env=env, rest={"BOS": "b2b_home", "MIA": "2plus"})
    assert "A 12.5-point spread — a starter's fourth quarter is the first thing a blowout takes" in rs["con"]
    eleven = S.read_player("Starter", starter, "BOS", "MIA", env={"BOS": {"spread": 11.5}})
    assert eleven["con"][0].startswith("An 11.5-point spread"), eleven["con"]
    assert "BOS is on the second night of a back-to-back" in rs["con"]
    rb = S.read_player("Bench", bench, "BOS", "MIA", env=env)
    assert not any("spread" in c for c in rb["con"])
    both = S.read_player("Starter", starter, "BOS", "MIA", rest={"BOS": "b2b_home", "MIA": "3in4"})
    assert not any("back-to-back" in x or "four nights" in x for x in both["pro"] + both["con"]), both


def test_the_scan_rules_out_whom_the_build_rules_out():
    import nba_build
    assert S.OUT == set(nba_build.OUT_STATUSES)


def test_his_own_listing_is_a_note_and_rides_the_read():
    h = _hist(mins=[30] * 12, pts=[18] * 12)
    r = S.read_player("Q Guy", h, "BOS", "MIA", status="questionable")
    assert r["notes"][0] == "Q Guy is listed questionable himself — this read assumes he plays"
    assert r["own_status"] == "QUESTIONABLE"


def test_the_scan_reads_key_players_and_skips_the_ruled_out_and_the_pulled():
    prof = T.build([], _league())
    hist = {"Star": _hist([36] * 12, [30] * 12), "Out Guy": _hist([34] * 12, [22] * 12),
            "Pulled Guy": _hist([30] * 12, [15] * 12), "Deep Bench": _hist([8] * 12, [2] * 12, starter=False),
            "Priced Bench": _hist([9] * 12, [3] * 12, starter=False),
            "Heat Man": _hist([33] * 12, [21] * 12, team="MIA", opps=["BOS"] * 12)}
    out = S.scan([{"home": "BOS", "away": "MIA", "spread": -6.5, "total": 224.0}], hist, prof,
                 dvp=DVP, listed={"Out Guy": {"status": "Out"}}, key_players={"Priced Bench"},
                 out_players={"Pulled Guy"}, faces={"Star": "https://x/star.png"})
    names = [r["player"] for r in out["reads"]["MIA@BOS"]["players"]]
    assert set(names) == {"Star", "Priced Bench", "Heat Man"}, names
    star = next(r for r in out["reads"]["MIA@BOS"]["players"] if r["player"] == "Star")
    assert star["headshot"] == "https://x/star.png" and star["opp"] == "MIA"
    heat = next(r for r in out["reads"]["MIA@BOS"]["players"] if r["player"] == "Heat Man")
    assert any("points a game in his last" in n and "against BOS" in n for n in heat["notes"]), heat["notes"]
    order = [S.LABELS and list(S.LABELS).index(r["read"]) for r in out["reads"]["MIA@BOS"]["players"]]
    assert order == sorted(order)
    assert set(out["tapes"]) == {"MIA@BOS"} and out["tapes"]["MIA@BOS"]["rows"]


def test_reads_lean_most_likely_and_make_matchup_picks():
    from engine.gamescan import leans_from_reads
    from engine import matchpicks as MP
    read = {"player": "Jay Star", "team": "BOS", "opp": "MIA", "read": "good", "label": "Good matchup",
            "lean": ["pts", "pts_ast"], "usage": {"mpg": 34.0}, "pro": ["MIA allows the 2nd-most points"],
            "con": [], "pos": ""}
    leans = leans_from_reads({"MIA@BOS": {"players": [read]}})
    assert leans[("Jay Star", "BOS", "pts")]["side"] == "over" and ("Jay Star", "BOS", "reb") not in leans
    prop = {"player": "Jay Star", "team": "BOS", "opponent": "MIA", "market": "pts", "market_label": "Points",
            "side": "over", "line": 26.5, "hit_prob": 0.61, "odds": -125,
            "all_lines": [{"book": "draftkings", "line": 26.5, "over_odds": -125, "under_odds": 105}]}
    game = {"home": "BOS", "away": "MIA", "kickoff": "2026-10-22T23:30:00Z", "date": "2026-10-22"}
    picks = MP.build([game], {"MIA@BOS": {"players": [read]}}, [], [prop], sport="nba")
    assert len(picks) == 1 and not picks[0]["td"], picks
    p = picks[0]["props"][0]
    assert (p["player"], p["market"], p["side"], p["line"], p["odds"], p["book"]) == \
        ("Jay Star", "pts", "OVER", 26.5, -125, "draftkings")
    assert p["matchup_pick"] is True and p["model_prob"] == 0.61 and p["game"] == "MIA@BOS"
    # A garbage-time role is not a pick, whatever the number says.
    bench = dict(read, usage={"mpg": 14.0})
    assert not MP.build([game], {"MIA@BOS": {"players": [bench]}}, [], [prop], sport="nba")
    assert MP.HOOPS_PROP_MARKETS == ("pts", "reb", "ast", "fg3m", "pra", "pts_reb", "pts_ast", "reb_ast")


def test_the_nba_report_carries_the_tape_the_key_matchups_and_the_breakouts():
    from engine import gamereport as R, leaguereport as L
    prof = T.build([], _league())
    g = {"home": "BOS", "away": "MIA", "date": "2026-10-22", "kickoff": "2026-10-22T23:30:00Z",
         "spread": -9.5, "total": 226.5}
    g["nba_tape"] = S.tape("BOS", "MIA", prof, env=S.environment(g, prof), rest={"MIA": "b2b_home"})
    brk = {"player": "Jay Star", "team": "BOS", "opp": "MIA", "pos": "", "read": "breakout",
           "label": "Breakout spot", "pro": ["Minutes up 20% over his last five", "MIA allows the most points a game (119.4)",
                                             "MIA is on the second night of a back-to-back"], "con": [], "notes": []}
    bad = {"player": "Heat Man", "team": "MIA", "opp": "BOS", "pos": "", "read": "tough", "label": "Tough matchup",
           "pro": [], "con": ["BOS allows the fewest threes a game (10.1)"], "notes": []}
    board = {"date": "2026-10-22", "games": [g], "scan_reads": {"MIA@BOS": {"players": [brk, bad]}}}
    L.attach(board, "nba", meta={})
    rep = board["game_reports"][0]
    keys = [s["key"] for s in rep["sections"]]
    assert keys[:5] == ["short", "facts", "market", "tape", "watch"], keys
    tape = next(s for s in rep["sections"] if s["key"] == "tape")
    table = next(b for b in tape["blocks"] if b["type"] == "table")
    assert table["head"] == ["", "MIA", "BOS"] and table["rows"][0][0] == "Points a game"
    assert table["rows"][0][2].endswith("(1st)"), table["rows"][0]
    text = R.to_text(rep)
    for want in ("KEY MATCHUPS", "Edge BOS: BOS's offense (1st in points per 100) against MIA's defense (",
                 "Breakout watch", "Jay Star", "Could struggle", "Heat Man",
                 "Breakout watch: Jay Star (BOS)", "Could struggle: Heat Man (MIA)",
                 "Key matchup: BOS's offense (1st in points per 100) against MIA's defense ("):
        assert want.lower() in text.lower(), (want, text)
    # Ask reads the same sections a member reads (askbot.LEAGUE_REPORT_KEYS):
    # the tape's rows, its key matchups and the breakout watch.
    from engine import askbot as A
    facts = A.report_facts(board, g)
    assert any(x.startswith("Points a game: ") for x in facts["tape"]), facts["tape"]
    assert any(x.startswith("Edge BOS: ") for x in facts["tape"]), facts["tape"]
    assert any("Jay Star" in x for x in facts["watch"]), facts["watch"]
    # The WNBA reads the same report.
    board2 = {"date": "2026-10-22", "games": [dict(g)], "scan_reads": board["scan_reads"]}
    assert L.attach(board2, "wnba", meta={}).startswith("Game reports: 1 game(s)")


def test_the_build_wires_the_scan_before_most_likely_and_journals_the_matchup_picks():
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    scan = src.index("_nscan.scan(out.get(\"games\") or [], hist, _prof,")
    assert src.index("out[\"recommendations\"] = recs") < scan < src.index("out[\"most_likely\"] = _likely_build(")
    assert "leans=_nba_leans, lean_report=_nba_lean_report)" in src
    assert src.index("_stamp_nba(out[\"scan_reads\"], _nba_lean_report, board=out[\"most_likely\"])") \
        < src.index("print(f\"  {_lb.attach(out, args.league)}\")")
    assert src.index("out[\"matchup_picks\"] = _mp_build(") < src.index("print(f\"  {_lb.attach(out, args.league)}\")")
    assert 'category="matchup_prop", grade_label="Matchup")' in src
    assert "_gd[\"nba_tape\"] = _tp" in src and "dvp=_gr_rt," in src
    from engine import gate, likelyboard
    assert likelyboard.MATCHUP_SOURCE["nba"] == likelyboard.MATCHUP_SOURCE["wnba"] == "scan+model"
    assert "scan_reads" in gate.PAID_KEYS and "matchup_picks" in gate.PAID_KEYS


def test_the_game_page_draws_the_nba_tape_and_its_reads():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    fn = app[app.index("function nbaScanHTML(g) {"):]
    fn = fn[:fn.index("\n}\n")]
    for want in ("g.nba_tape", "t.rows.map(", "tapeTier(r, n)", "t.edges", "scanReadHTML", "d.locked.scan_reads",
                 "t.basis"):
        assert want in fn, want
    assert "matchupScanHTML(g) || mlbScanHTML(g) || nhlScanHTML(g) || nbaScanHTML(g)" in app
    assert "g.mlb_tape || g.nhl_tape || g.nba_tape) ? [\"gp-sec-scan\", \"Matchup scan\"]" in app
    assert "if (u.usg) bits.push(" in app


def test_the_box_score_keeps_the_shooting_columns():
    from engine.sources import espnhoops, nbadata
    rows = espnhoops.parse_summary({"boxscore": {"players": [{"team": {"abbreviation": "BOS"}, "statistics": [{
        "names": ["MIN", "FG", "3PT", "FT", "OREB", "REB", "AST", "TO", "PTS"],
        "athletes": [{"athlete": {"displayName": "A Player"}, "starter": True,
                      "stats": ["34", "9-17", "4-9", "5-6", "2", "8", "6", "3", "27"]}]}]}]}})
    st = rows[0]["stats"]
    assert (st["fgm"], st["fga"], st["fg3m"], st["fg3a"], st["ftm"], st["fta"], st["oreb"]) == (9, 17, 4, 9, 5, 6, 2)
    for k in ("fgm", "fga", "fg3a", "ftm", "fta", "oreb"):
        assert k in nbadata.NBA_MARKETS and k in T.BOX
    box = {"game": {"homeTeam": {"teamTricode": "BOS", "players": [{"name": "A Player", "starter": "1", "statistics": {
        "minutes": "PT34M00.00S", "points": 27, "fieldGoalsMade": 9, "fieldGoalsAttempted": 17,
        "threePointersMade": 4, "threePointersAttempted": 9, "freeThrowsMade": 5, "freeThrowsAttempted": 6,
        "reboundsOffensive": 2, "reboundsTotal": 8}}]}, "awayTeam": {"teamTricode": "MIA", "players": []}}}
    p = nbadata.parse_boxscore(box)[0]
    assert (p["fga"], p["fg3a"], p["fta"], p["oreb"]) == (17, 9, 6, 2)


def test_nba_history_reads_espns_old_club_codes_as_the_leagues():
    import nba_build
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    for day, team, opp in (("2026-03-01", "GS", "NY"), ("2026-03-03", "GS", "SA"), ("2026-11-01", "GSW", "NYK")):
        for m, v in (("min", 34), ("pts", 25)):
            conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2025, ?, ?, 'Steph', ?, ?, 'S', 1, ?, ?)",
                         (day, day, team, opp, m, v))
    hist = nba_build.player_history(conn, {"GSW"}, sport="nba")
    assert hist["Steph"]["team"] == "GSW" and len(hist["Steph"]["minutes"]) == 3, hist
    assert hist["Steph"]["opps"] == ["NYK", "SAS", "NYK"], hist["Steph"]["opps"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
