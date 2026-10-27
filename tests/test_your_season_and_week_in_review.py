"""Your league's season: playoff odds, power rankings, last week in review.

Ethan, 2026-10-27: "look at other apps, look at other examples … add more
features and what our fantasy room should actually be doing". The big apps
show a linked league's playoff odds, power rankings and a weekly recap; the
desk showed the standings and this week's game (docs/FANTASY.md, items 5
and 8).

What these hold: every simulated season sends exactly the league's
playoff_teams to the playoffs and one team to first place, so the odds add
up; a team that has clinched is in and one that is out is out; a median
league plays the median every week; your paths add up to every season
played; all-play counts every pairing; luck is wins above the all-play
rate; a bye zeroes its players; the review's awards come from the box, a
box with no player points wins none, and your costliest call says when it
cost the game; the endpoint reads Sleeper (faked here, no network) and
answers with all of it; the desk draws it after it paints, Sleeper only.

Run directly: `python3 tests/test_your_season_and_week_in_review.py`
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fantasy_season as S                           # noqa: E402

WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "fantasy.css").read_text(encoding="utf-8")

FOUR = {1: {"wins": 5, "losses": 3, "pf": 900.0}, 2: {"wins": 4, "losses": 4, "pf": 880.0},
        3: {"wins": 4, "losses": 4, "pf": 820.0}, 4: {"wins": 3, "losses": 5, "pf": 800.0}}
SCHED = {9: [(1, 2), (3, 4)], 10: [(1, 3), (2, 4)], 11: [(1, 4), (2, 3)]}
EVEN = {w: {r: (100.0, 20.0) for r in FOUR} for w in SCHED}


# --- the odds ----------------------------------------------------------------------------------

def test_the_odds_add_up_to_the_playoff_places():
    out = S.simulate(FOUR, SCHED, EVEN, playoff_teams=2, seed=3, me=2)
    t = out["teams"]
    assert abs(sum(x["playoff"] for x in t.values()) - 2) < 0.01, "two teams go every season"
    assert abs(sum(x["first"] for x in t.values()) - 1) < 0.01, "one first place every season"
    assert t[1]["playoff"] > t[4]["playoff"], "a win ahead is worth something"
    assert all(abs(x["wins"] + x["losses"] - 11) < 0.01 for x in t.values()), "eight played, three to play"
    assert out == S.simulate(FOUR, SCHED, EVEN, playoff_teams=2, seed=3, me=2), "the same seed, the same odds"


def test_clinched_is_in_and_eliminated_is_out():
    teams = {1: {"wins": 11, "losses": 0, "pf": 1300.0}, 2: {"wins": 0, "losses": 11, "pf": 700.0},
             3: {"wins": 6, "losses": 5, "pf": 1000.0}, 4: {"wins": 5, "losses": 6, "pf": 990.0}}
    out = S.simulate(teams, {12: [(1, 2), (3, 4)]}, {12: {r: (100.0, 20.0) for r in teams}}, playoff_teams=2, seed=1)
    assert out["teams"][1]["playoff"] == 1.0 and out["teams"][1]["first"] == 1.0
    assert out["teams"][2]["playoff"] == 0.0


def test_a_median_league_plays_the_median_every_week():
    out = S.simulate(FOUR, SCHED, EVEN, playoff_teams=2, seed=3, me=2, median=True)
    assert out["games_left"] == 6, "three games and three medians"
    assert all(abs(x["wins"] + x["losses"] - 14) < 0.01 for x in out["teams"].values())


def test_your_paths_add_up_and_more_wins_never_hurt():
    out = S.simulate(FOUR, SCHED, EVEN, playoff_teams=2, seed=5, me=2, sims=4000)
    paths = out["paths"]
    assert [p["wins"] for p in paths] == [3, 2, 1, 0] and all(p["of"] == 3 for p in paths)
    assert abs(sum(p["share"] for p in paths) - 1) < 0.01
    chances = [p["playoff"] for p in paths]
    assert chances == sorted(chances, reverse=True), chances


def test_a_strong_team_is_likelier_than_its_record_alone():
    strong = {w: {**EVEN[w], 4: (130.0, 20.0)} for w in SCHED}
    weak = S.simulate(FOUR, SCHED, EVEN, playoff_teams=2, seed=3)["teams"][4]["playoff"]
    good = S.simulate(FOUR, SCHED, strong, playoff_teams=2, seed=3)["teams"][4]["playoff"]
    assert good > weak + 0.05, (weak, good)


def test_the_schedule_is_the_league_s_own_pairings():
    rows = [{"roster_id": 1, "matchup_id": 7}, {"roster_id": 2, "matchup_id": 7},
            {"roster_id": 3, "matchup_id": 8}, {"roster_id": 4, "matchup_id": 8},
            {"roster_id": 5, "matchup_id": None}, {"roster_id": 6, "matchup_id": 9}]
    assert S.schedule_from(rows) == [(1, 2), (3, 4)], "no game for a bye or a lone row"


def test_a_bye_zeroes_its_players_and_no_spread_still_swings():
    rows = {1: [{"player": "QB A", "position": "QB"}, {"player": "WR A", "position": "WR"}]}
    means = {"QB A": {"position": "QB", "fp_ppr": 20.0, "_sd": 6.0}, "WR A": {"position": "WR", "fp_ppr": 12.0}}
    slots = ["QB", "WR"]
    full = S.strengths(rows, slots, {}, means)[1]
    off = S.strengths(rows, slots, {}, means, off={"BUF"}, team_of={"QB A": "BUF"})[1]
    assert full[0] == 32.0 and off[0] == 12.0
    assert full[1] == S.MIN_TEAM_SD, "6.0 measured on one starter is less than a lineup swings"
    assert means["QB A"]["fp_ppr"] == 20.0, "the caller's means are not touched"


# --- power ---------------------------------------------------------------------------------

def test_all_play_counts_every_pairing_and_skips_an_empty_week():
    ap = S.all_play({1: {1: 100, 2: 90, 3: 80, 4: 70}, 2: {1: 60, 2: 90, 3: 80, 4: 80}, 3: {1: 0, 2: 0, 3: 0, 4: 0}})
    assert ap[1] == {"w": 3, "l": 3, "t": 0} and ap[2] == {"w": 5, "l": 1, "t": 0}
    assert ap[3] == {"w": 2, "l": 3, "t": 1} and ap[4] == {"w": 1, "l": 4, "t": 1}


def test_power_is_strength_and_luck_is_wins_above_all_play():
    teams = {1: {"wins": 6, "losses": 2}, 2: {"wins": 2, "losses": 6}}
    ap = {1: {"w": 4, "l": 4, "t": 0}, 2: {"w": 6, "l": 2, "t": 0}}
    rows = S.power(teams, {1: (90.0, 20.0), 2: (120.0, 20.0)}, ap)
    assert [r["roster_id"] for r in rows] == [2, 1] and rows[0]["power"] == 1
    by = {r["roster_id"]: r for r in rows}
    assert by[1]["luck"] == 2.0 and by[2]["luck"] == -4.0, "6 wins on a .500 all-play is two lucky ones"
    assert S.power({3: {"wins": 0, "losses": 0}}, {}, {})[0]["luck"] is None, "no games, no luck"


# --- the week in review --------------------------------------------------------------------

PLAYERS = {"1": ("QB Me", "QB"), "2": ("RB Me", "RB"), "3": ("RB Bench", "RB"), "4": ("WR Me", "WR"),
           "5": ("WR Bench", "WR"), "11": ("QB Them", "QB"), "12": ("RB Them", "RB"), "13": ("WR Them", "WR")}
WHO = lambda pid: PLAYERS.get(str(pid), (None, ""))     # noqa: E731
SLOTS = ["QB", "RB", "WR"]


def _box(me_pts, them_pts, extra=()):
    return [{"roster_id": 1, "matchup_id": 1, "points": me_pts["1"] + me_pts["2"] + me_pts["4"],
             "starters": ["1", "2", "4"], "players": ["1", "2", "3", "4", "5"], "players_points": me_pts},
            {"roster_id": 2, "matchup_id": 1, "points": sum(them_pts.values()), "starters": ["11", "12", "13"],
             "players": ["11", "12", "13"], "players_points": them_pts}, *extra]


def test_the_review_reads_the_box_and_names_the_costly_call():
    me = {"1": 20.0, "2": 4.0, "3": 19.0, "4": 15.0, "5": 9.0}
    them = {"11": 22.0, "12": 12.0, "13": 10.0}
    got = S.review(_box(me, them), WHO, SLOTS, {1: "Me", 2: "Them"}, me=1)
    mine = got["me"]
    assert (mine["points"], mine["best"], mine["left"]) == (39.0, 54.0, 15.0)
    assert mine["result"] == "L" and mine["opponent"] == "Them" and mine["opp_points"] == 44.0
    assert mine["worst_call"] == {"started": "RB Me", "started_pts": 4.0, "benched": "RB Bench", "benched_pts": 19.0,
                                  "diff": 15.0, "would_have_won": True}
    assert mine["best_call"] == {"started": "WR Me", "started_pts": 15.0, "benched": "WR Bench", "benched_pts": 9.0,
                                 "diff": 6.0}
    awards = {a["key"]: a["text"] for a in got["awards"]}
    assert awards["top"] == "Them, 44.0" and awards["low"] == "Me, 39.0"
    assert awards["unlucky"] == "Me scored 39.0 and lost" and awards["close"] == "Them over Me by 5.0"
    assert awards["sharp"] == "Them set the best lineup it could" and awards["bench"] == "Me, 15.0"
    assert awards["mvp"] == "QB Them, 22.0 for Them" and awards["pine"] == "RB Bench, 19.0 on Me's bench"


def test_a_box_without_player_points_wins_nothing():
    me = {"1": 20.0, "2": 4.0, "3": 19.0, "4": 15.0, "5": 9.0}
    them = {"11": 22.0, "12": 12.0, "13": 10.0}
    ghost = [{"roster_id": 3, "matchup_id": 2, "points": 90.0, "starters": [], "players": [], "players_points": {}},
             {"roster_id": 4, "matchup_id": 2, "points": 80.0, "starters": [], "players": [], "players_points": None}]
    got = S.review(_box(me, them, ghost), WHO, SLOTS, {1: "Me", 2: "Them", 3: "Ghost", 4: "Shade"}, me=1)
    awards = {a["key"]: a["text"] for a in got["awards"]}
    assert awards["sharp"] == "Them set the best lineup it could", "Ghost has no box to be sharp with"
    assert awards["top"] == "Ghost, 90.0", "a score is still a score"
    assert {t["team"]: t["left"] for t in got["teams"]}["Ghost"] is None


def test_no_review_before_a_week_is_played():
    assert S.review([], WHO, SLOTS, {}) is None
    assert S.review([{"roster_id": 1, "matchup_id": 1, "points": 0}], WHO, SLOTS, {}) is None


# --- the endpoint --------------------------------------------------------------------------

def _sleeper():
    players = {}
    rosters = []
    for rid in range(1, 5):
        pids = [f"{rid}{k}" for k in range(5)]
        for k, pid in enumerate(pids):
            players[pid] = {"first_name": f"T{rid}", "last_name": f"P{k}",
                            "position": ["QB", "RB", "RB", "WR", "WR"][k], "team": "BUF"}
        rosters.append({"roster_id": rid, "owner_id": f"u{rid}", "players": pids, "starters": pids[:4],
                        "settings": {"wins": [6, 4, 4, 2][rid - 1], "losses": [2, 4, 4, 6][rid - 1],
                                     "fpts": [900, 850, 800, 700][rid - 1], "fpts_decimal": 50}})
    out = {"league/77": {"name": "Test League", "scoring_settings": {},
                         "roster_positions": ["QB", "RB", "WR", "FLEX", "BN"],
                         "settings": {"leg": 9, "playoff_week_start": 12, "playoff_teams": 2}},
           "league/77/rosters": rosters, "players/nfl": players, "state/nfl": {"week": 9},
           "league/77/users": [{"user_id": f"u{r}", "display_name": f"Owner {r}"} for r in range(1, 5)]}
    for w in range(1, 12):
        pairs = [(1, 2), (3, 4)] if w % 2 else [(1, 3), (2, 4)]
        rows = []
        for mid, (a, b) in enumerate(pairs, 1):
            for rid in (a, b):
                pids = [f"{rid}{k}" for k in range(5)]
                pts = {p: float(10 + rid + k) for k, p in enumerate(pids)} if w < 9 else {}
                rows.append({"roster_id": rid, "matchup_id": mid, "starters": pids[:4], "players": pids,
                             "players_points": pts, "points": sum(list(pts.values())[:4]) if pts else 0})
        out[f"league/77/matchups/{w}"] = rows
    return out


def test_the_season_endpoint_answers_from_the_league():
    import server
    from engine import db as D
    from engine.sources import fetch as F
    fix = _sleeper()
    tmp = Path(tempfile.mkdtemp())
    real_connect, real_fetch = D.connect, F.fetch_text
    logs = []
    for rid in range(1, 5):
        for k in range(5):
            for wk in range(1, 5):
                logs.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "game_id": f"g{rid}{k}{wk}",
                             "player": f"T{rid} P{k}", "team": "BUF", "opponent": "MIA",
                             "position": ["QB", "RB", "RB", "WR", "WR"][k], "home": 1, "market": "fp_ppr",
                             "value": 8.0 + 3 * (5 - rid) + k + wk})
    conn = real_connect(str(tmp / "h.db"))
    D.upsert_player_logs(conn, logs)
    conn.close()
    D.connect = lambda *a, **k: real_connect(str(tmp / "h.db"))
    F.fetch_text = lambda url, cache, ttl=0, **kw: json.dumps(fix[url[len(server.SLEEPER_BASE):]])
    sent = []
    try:
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._fail = lambda code, msg, exc, where: sent.append((code, {"error": msg}))
        h._kit_board = lambda: {}
        h._fantasy_week = lambda: ({}, {"state": "none"})
        h._league_season({"league": ["77"], "user": ["u1"]})
        h._league_season({"league": ["not-a-league"]})
    finally:
        D.connect, F.fetch_text = real_connect, real_fetch
        shutil.rmtree(tmp, ignore_errors=True)
    code, out = sent[0]
    assert code == 200, out
    assert out["week"] == 9 and out["last_regular_week"] == 11 and out["playoff_teams"] == 2 and out["me"] == 1
    teams = {t["roster_id"]: t for t in out["teams"]}
    assert teams[1]["me"] and teams[1]["team"] == "Owner 1" and teams[1]["pf"] == 900.5
    assert abs(sum(t["odds"]["playoff"] for t in out["teams"]) - 2) < 0.01
    assert teams[1]["odds"]["playoff"] > teams[4]["odds"]["playoff"]
    assert [t["roster_id"] for t in out["teams"]][0] == 1, "the best roster ranks first"
    assert sum(teams[1]["all_play"].values()) == 8 * 3, "eight weeks, three others each"
    assert out["games_left"] == 3 and abs(sum(p["share"] for p in out["paths"]) - 1) < 0.01
    assert out["review_week"] == 8 and out["review"]["me"]["result"] in ("W", "L", "T")
    assert {a["key"] for a in out["review"]["awards"]} >= {"top", "low", "blowout", "mvp"}
    assert sent[1][0] == 400
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/leagueseason"' in src


# --- the page ------------------------------------------------------------------------------

def _fn(name):
    i = WEEK_JS.index(f"function {name}(")
    i = WEEK_JS.rindex("\n", 0, i) + 1
    return WEEK_JS[i:WEEK_JS.index("\n  }\n", i) + 4]


def test_the_desk_draws_it_after_it_paints_sleeper_only():
    paint = APP_JS[APP_JS.index("async function renderLeagueDesk("):]
    assert "ffStandingsHTML(d) + `<div id=\"ffs\"></div>` + ffTeamsHTML(d)" in paint
    assert "W.season(host, leagueId, userId, platform)" in paint
    body = _fn("season")
    assert "(platform && platform !== \"sleeper\")" in body, "ESPN and Yahoo have no public schedule read here"
    assert "fetch(`/api/leagueseason?league=" in body and "if (box.isConnected)" in body
    assert "season" in WEEK_JS[WEEK_JS.index("window.QBWeek = {"):]


def test_every_class_it_draws_is_styled():
    drawn = set(re.findall(r"\b(ff[sr]-[a-z-]+)", WEEK_JS))
    styled = set(re.findall(r"\.(ff[sr]-[a-z-]+)", CSS))
    assert drawn and drawn <= styled, sorted(drawn - styled)


def test_paths_that_land_alike_are_one_line_in_node():
    if not shutil.which("node"):
        return
    i = WEEK_JS.index("  const pct = ")
    harness = (WEEK_JS[i:WEEK_JS.index("\n", i)] + "\n"
               "const rec = (w, l, t) => `${w}–${l}${t ? `–${t}` : ''}`;\n" + _fn("seasonPaths")
               + "\nconst P = (w, p, s) => ({ wins: w, of: 4, playoff: p, share: s });"
               "process.stdout.write(JSON.stringify([seasonPaths({ paths: [P(4, 1, .1), P(3, .999, .3), P(2, .7, .3),"
               " P(1, .002, .2), P(0, 0, .1)] }), seasonPaths({ paths: [P(4, .9, .5), P(3, .4, .005)] })]));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = json.loads(out.stdout)
    assert got[0] == [{"text": "3–1 or better", "label": ">99%"}, {"text": "2–2", "label": "70%"},
                      {"text": "1–3 or worse", "label": "<1%"}], got[0]
    assert got[1] == [{"text": "4–0", "label": "90%"}], "a path under one season in a hundred is not shown"


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
