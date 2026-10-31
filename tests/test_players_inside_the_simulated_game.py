"""Players inside the simulated game — every prop on a team out of the same simulated games.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 9: the parlay pricer
joins two legs with one number per kind of pair, whoever the players are;
a simulation that plays each throw and carry joins THESE two players.

What these hold: a man's share is his targets over the team's attempts in
the games he played, three games at least, and the passer is the last
game's thrower; a season logged before carries had the market's name
reads its `carries`; inside one simulated game the passer's attempts,
completions and yards are never fewer than his receivers' put together; a
quarterback and the receiver he feeds move together; the copula parameter
is the normal scores' correlation; the shocks and shapes are recovered from
games built with known ones; the four outcomes add to one and the
pricer's number is the one `parlays.relate` gives, shrunk as it shrinks;
the held-out cases skip one man paired with himself and a push; the verdict
is clustered by team-game and wants the pricer beaten in every test season;
and the pick and game pages show the links, labelled. No test touches the
network.

Run directly: `python3 tests/test_players_inside_the_simulated_game.py`
"""
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                       # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine import parlays as P                                  # noqa: E402
from engine import playsim as S                                  # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _game(wr1_tgt=10, wr2=True):
    g = {"Josh Allen": {"pass_att": 34, "pass_cmp": 22, "pass_yds": 250, "rush_att": 4, "rush_yds": 20},
         "Khalil Shakir": {"targets": wr1_tgt, "receptions": 7, "rec_yds": 90},
         "James Cook": {"rush_att": 18, "rush_yds": 80, "targets": 3, "receptions": 2, "rec_yds": 12}}
    if wr2:
        g["Dalton Kincaid"] = {"targets": 6, "receptions": 4, "rec_yds": 45}
    return g


def test_shares_come_from_the_games_he_played():
    games = [(2025, w, _game(wr2=w > 4)) for w in range(1, 9)]
    p = S.profile(games)
    assert p["qb"] == "Josh Allen" and p["pass_att"] == 34 and p["rush_att"] == 22
    assert abs(p["receivers"]["Dalton Kincaid"]["share"] - 6 / 34) < 1e-9, "four games, his share of those four"
    assert abs(p["receivers"]["Khalil Shakir"]["share"] - 10 / 34) < 1e-9
    assert abs(p["rushers"]["James Cook"]["share"] - 18 / 22) < 1e-9
    shrunk = p["receivers"]["Dalton Kincaid"]["catch"]
    assert 4 / 6 > shrunk > S.CATCH_PRIOR[0] or S.CATCH_PRIOR[0] > shrunk > 4 / 6, "pulled toward the league"
    assert S.profile(games[:2]) is None, "two games is too few"
    assert len(S.profile([(2024, w, _game()) for w in range(1, 20)])["receivers"]) == 3
    old = S.team_games([(2024, 1, "BUF", "James Cook", "carries", 18), (2024, 1, "BUF", "Josh Allen", "rush_att", 4),
                        (2024, 1, "BUF", "Josh Allen", "carries", 4)])
    assert old["BUF"][0][2] == {"James Cook": {"rush_att": 18.0}, "Josh Allen": {"rush_att": 4.0}}, \
        "a season logged before carries had their market's name reads as carries"


def test_the_passer_is_never_short_of_his_receivers_and_feeds_his_top_one():
    p = S.profile([(2025, w, _game()) for w in range(1, 9)])
    sim = S.simulate(p, 800, random.Random(4))
    qb = sim["Josh Allen"]
    names = ("Khalil Shakir", "Dalton Kincaid", "James Cook")
    for t in range(800):
        assert qb["pass_cmp"][t] >= sum(sim[n]["receptions"][t] for n in names)
        assert qb["pass_yds"][t] + 1e-9 >= sum(sim[n]["rec_yds"][t] for n in names)
        assert qb["pass_att"][t] >= sum(sim[n]["targets"][t] for n in names)
    assert S.normal_scores_corr(qb["pass_yds"], sim["Khalil Shakir"]["rec_yds"]) > 0.4
    assert abs(sum(sim["James Cook"]["rush_att"]) / 800 - 22 * 18 / 22) < 1.5
    assert 0.0 < S.over_chance(sim["Khalil Shakir"]["receptions"], 6.5) < 1.0
    assert S.over_chance([5, 5, 7, 3], 5) == 0.5, "a push counts half"


def test_the_copula_parameter_is_the_normal_scores_correlation():
    xs = list(range(200))
    assert S.normal_scores_corr(xs, [x * 3 + 1 for x in xs]) == 0.95, "clamped short of one"
    assert S.normal_scores_corr(xs, [-x for x in xs]) == -0.95
    rnd = random.Random(2)
    a, b = [rnd.random() for _ in range(3000)], [rnd.random() for _ in range(3000)]
    assert abs(S.normal_scores_corr(a, b)) < 0.06
    assert S.normal_scores_corr(xs[:10], xs[:10]) is None


def test_the_shocks_and_shapes_are_recovered_from_known_games():
    rnd = random.Random(9)
    tg = {}
    for team in range(16):
        games = []
        for season in (2022, 2023):
            for w in range(1, 18):
                v, s = rnd.gauss(0, 0.10), rnd.gauss(0, 0.15)
                pa = max(10, S._count(rnd, 35 * math.exp(v + s)))
                ra = max(5, S._count(rnd, 25 * math.exp(v - s)))
                cmp_ = sum(rnd.random() < 0.64 for _ in range(pa))
                yds = sum(rnd.gammavariate(2.0, 11.0 / 2.0) for _ in range(cmp_))
                rec = {f"R{i}": {"receptions": c, "rec_yds": sum(rnd.gammavariate(2.0, 11.0 / 2.0) for _ in range(c))}
                       for i, c in enumerate([max(1, cmp_ // 3), max(1, cmp_ // 4)])}
                games.append((season, w, {"QB": {"pass_att": pa, "pass_cmp": cmp_, "pass_yds": yds},
                                          "RB": {"rush_att": ra, "rush_yds": ra * 4.3}, **rec}))
        tg[f"T{team}"] = games
    sh = S.fit_shocks(tg, {2022, 2023})
    assert abs(sh["vol_sd"] - 0.10) < 0.04 and abs(sh["script_sd"] - 0.15) < 0.04, sh
    assert sh["eff_sd"] < 0.08, "no passer's-day shock was put in"
    k = S.fit_shapes(tg, {2022, 2023})
    assert abs(k["k_rec"] - 2.0) < 0.4, k
    assert S.fit_shocks({}, {2022}) == S.DEFAULT_SHOCKS


def test_the_four_outcomes_and_the_pricers_number():
    c = S.cells(0.55, 0.5, 0.0)
    assert abs(sum(c) - 1) < 1e-9 and abs(c[0] - 0.275) < 1e-3, "independent: the product"
    assert S.cells(0.55, 0.5, 0.5)[0] > c[0]
    assert S.log_loss((0.4, 0.1, 0.2, 0.3), True, False) == -math.log(0.1)
    qb, wr = {"player": "QB", "team": "BUF", "market": "pass_yds"}, {"player": "WR", "team": "BUF", "market": "rec_yds"}
    rel = P.relate("nfl", {**qb, "side": "over"}, {**wr, "side": "over"})
    assert S.prior_rho("nfl", qb, wr) == (rel.rho if rel.measured else rel.rho * P.RHO_SHRINK)


def test_the_held_out_cases_and_the_clustered_verdict():
    games = [(2025, w, _game()) for w in range(1, 7)]
    tg = {"BUF": games}
    dates = {(2025, w, "BUF"): f"2025-10-{w:02d}" for w in range(1, 7)}
    closes = {"pass_yds": {("josh allen", "2025-10-06"): (240.5, 0.5)},
              "rec_yds": {("khalil shakir", "2025-10-06"): (80.5, 0.5)},
              "receptions": {("khalil shakir", "2025-10-06"): (6.5, 0.5)},
              "rush_yds": {("james cook", "2025-10-06"): (80.0, 0.5)}}
    cases = S.pair_cases(tg, closes, dates, {2025}, trials=200)
    assert len(cases) == 2, "his two legs never pair with each other; a push on 80 is out"
    assert all(c[0] == 2025 and c[1] == "BUF|2025|6" for c in cases)
    rows = []
    for s in (2024, 2025):
        for g in range(200):
            for _ in range(4):
                rows.append((s, f"{s}-{g}", 0.68, 0.70, 0.72))
    v = S.verdict(rows)
    assert v["pairs"] == 1600 and v["vs_pricer"]["games"] == 400 and v["vs_pricer"]["gain"] == 0.02
    assert v["vs_independent"]["gain"] == 0.04 and v["by_season"] == {"2024": 0.02, "2025": 0.02}
    rnd = random.Random(1)
    rows = [(s, k, ll, ll + 0.02 + rnd.gauss(0, 0.05), ll + 0.03) for s, k, ll, _p, _i in rows]
    assert S.verdict(rows)["holds"]
    worse = [(2024 if r[0] == 2024 else 2025, r[1], r[2] + (0.05 if r[0] == 2025 else 0), r[3], r[4]) for r in rows]
    assert not S.verdict(worse)["holds"], "every test season above zero"
    assert not S.verdict(rows[:800])["holds"], "one season is not two"


def test_the_pick_and_game_pages_show_the_links():
    conn = D.connect(":memory:")
    for w in range(1, 9):
        for player, st in _game().items():
            for m, v in st.items():
                conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
                             "VALUES ('nfl', 2026, ?, ?, ?, 'BUF', ?, ?)", (f"{w:03d}", f"g{w}", player, m, v))
    board = {"recommendations": [
        {"player": "Josh Allen", "team": "BUF", "opponent": "MIA", "market": "pass_yds", "line": 245.5},
        {"player": "Khalil Shakir", "team": "BUF", "opponent": "MIA", "market": "rec_yds", "line": 75.5},
        {"player": "James Cook", "team": "BUF", "opponent": "MIA", "market": "rush_yds", "line": 70.5},
        {"player": "Somebody", "team": "BUF", "opponent": "MIA", "market": "anytime_td", "line": 0.5}]}
    sec = S.ideas_section([], [], board, "nfl", conn=conn)
    p = S.pick_view(sec, "Khalil Shakir", "rec_yds")
    assert p["line"] == 75.5 and 0 < p["sim_over"] < 1 and {l["player"] for l in p["links"]} == {"Josh Allen", "James Cook"}
    top = p["links"][0]
    assert top["player"] == "Josh Allen" and top["rho"] > 0.3 and top["their_over_given_his"] > top["their_over"]
    g = S.game_view(sec, "MIA", "BUF")
    assert len(g["pairs"]) == 3 and S.game_view(sec, "NYJ", "NE") is None
    assert S.pick_view(sec, "Somebody", "anytime_td") is None
    assert S.ideas_section([], [], board, "nba", conn=conn) is None
    assert ID.SECTIONS["sim"] == "playsim"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{p: L.pickHTML({json.dumps({'sections': {'sim': p}})}),"
              f" g: L.gameHTML({json.dumps({'sections': {'sim': g}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)
    assert "The same simulated games" in h["p"] and "Josh Allen" in h["p"] and "passing yards" in h["p"]
    assert "Reading · not measured yet" in h["p"] and "nothing on a ticket reads it" in h["p"]
    assert "Where the simulation and the parlay pricer disagree" in h["g"]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
