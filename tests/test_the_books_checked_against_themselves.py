"""Do a book's own numbers add up? The books checked against themselves, and the ideas file that carries it.

Ethan, 2026-10-16: "add everything now. 1-13 and dont stop till everything
is done" — the first invention on the list: a book prices a quarterback's
yards and, separately, every receiver he throws to, and nothing forces the
two to agree.

What these hold: a parent is checked against its parts at ONE book only —
the passer that book prices highest against his own team's receivers (three
or more), a back's rush + rec against his two halves, a team's touchdown
prices against the touchdowns its points imply (both sides of a price
needed, never an assumed hold); the statistic is log(parts / parent);
what normal looks like is fitted (median and MAD, per count of parts) and a
bucket with too few menus has no normal, so nothing is flagged before the
box has measured it; a flag needs |z| ≥ 2 and leans the parent's over and
the parts' unders when the parts run high; the history join reads closes
per book, a man's team and result from the logs dated by the schedule; the
bar is applied on held-out seasons, per side, with the menu (not the leg)
as the unit and each test season on its own; the ideas file builds every
section in its own try, writes privately and atomically, and serves a
pick's or a game's slice; the endpoint asks for a membership; both football
builds write the file; and the pick and game pages draw it, labelled.

Run directly: `python3 tests/test_the_books_checked_against_themselves.py`
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import bookmenu as M                                 # noqa: E402
from engine import db as D                                       # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _l(book, line, o=-110, u=-110):
    return {"book": book, "line": line, "over_odds": o, "under_odds": u}


def _slate():
    props = [
        {"player": "Starter", "team": "KC", "position": "QB", "market": "pass_yds",
         "lines": [_l("dk", 245.5), _l("fd", 250.5)]},
        {"player": "Backup", "team": "KC", "position": "QB", "market": "pass_yds", "lines": [_l("dk", 120.5)]},
        {"player": "WR1", "team": "KC", "position": "WR", "market": "rec_yds", "lines": [_l("dk", 80.5), _l("fd", 70.5)]},
        {"player": "WR2", "team": "KC", "position": "WR", "market": "rec_yds", "lines": [_l("dk", 60.5), _l("fd", 55.5)]},
        {"player": "TE", "team": "KC", "position": "TE", "market": "rec_yds", "lines": [_l("dk", 50.5)]},
        {"player": "RB", "team": "KC", "position": "RB", "market": "rec_yds", "lines": [_l("dk", 20.5)]},
        {"player": "RB", "team": "KC", "position": "RB", "market": "rush_yds", "lines": [_l("dk", 60.5)]},
        {"player": "RB", "team": "KC", "position": "RB", "market": "rush_rec_yds", "lines": [_l("dk", 85.5)]},
    ]
    props += [{"player": f"S{i}", "team": "KC", "position": "WR", "market": "anytime_td",
               "lines": [_l("dk", 0.5, 150 + 40 * i, -190), _l("fd", 0.5, 150 + 40 * i, None)]} for i in range(4)]
    return props, [{"home": "KC", "away": "BUF", "spread": -3.0, "total": 48.5}]


def test_the_arithmetic_takes_no_hold_it_cannot_see():
    fo, fu = M.fair_pair(-110, -110)
    assert abs(fo - 0.5) < 1e-9 and abs(fu - 0.5) < 1e-9
    assert M.fair_pair(-110, None) is None and M.fair_pair(-105, 90) is None, "one side, or a non-price, is no pair"
    lam = M.td_rate(150, -190)
    p = M.fair_pair(150, -190)[0]
    assert abs((1 - math.exp(-lam)) - p) < 1e-9, "the rate whose chance of one or more is the fair Yes"
    assert M.td_rate(150, None) is None
    assert M.team_points(-3.0, 48.5, True) == 25.75 and M.team_points(-3.0, 48.5, False) == 22.75
    assert M.statistic(212.0, 245.5) == math.log(212.0 / 245.5) and M.statistic(0, 245.5) is None


def test_each_book_checks_its_starter_against_his_own_receivers():
    props, games = _slate()
    rows = M.menus(props, games, "nfl", fitted={})
    team = [r for r in rows if r["check"] == "pass_rec"]
    assert [(r["book"], r["parent"]["player"], r["n"]) for r in team] == [("dk", "Starter", 4)], \
        "fd prices only two receivers: under three is not a menu"
    assert team[0]["sum"] == 212.0 and team[0]["game"] == "BUF @ KC"
    assert team[0]["z"] is None and team[0]["lean"] is None, "no fit, no normal, no flag"
    combo = [r for r in rows if r["check"] == "rush_rec"]
    assert len(combo) == 1 and combo[0]["sum"] == 81.0 and combo[0]["parent"]["line"] == 85.5
    td = [r for r in rows if r["check"] == "td_total"]
    assert [r["book"] for r in td] == ["dk"], "fd quotes no No side: its TD prices are not read"
    assert td[0]["points"] == 25.8 and td[0]["n"] == 4
    assert "Starter" in team[0]["players"] and "Backup" not in team[0]["players"]


def test_normal_is_measured_and_a_flag_leans_the_cheap_sides():
    cases = [{"check": "pass_rec", "bucket": "4", "x": -0.1 + 0.01 * ((i % 11) - 5)} for i in range(120)]
    cases += [{"check": "pass_rec", "bucket": "3", "x": 0.0} for _ in range(40)]
    f = M.fit(cases)
    assert set(f["pass_rec"]) == {"4"}, "a bucket under MIN_FIT has no normal"
    assert abs(f["pass_rec"]["4"]["mu"] + 0.1) < 1e-9 and f["pass_rec"]["4"]["n"] == 120
    props, games = _slate()
    rows = M.menus(props, games, "nfl", fitted={"pass_rec": {"4": {"mu": 0.0, "sd": 0.05, "n": 500}}})
    r = [x for x in rows if x["check"] == "pass_rec"][0]
    assert r["z"] < -2 and r["lean"] == "parent under, parts over"
    assert M.summary(rows)["flagged"] == 1 and M.flagged(rows)[0] is r
    assert M._lean(2.5) == "parent over, parts under" and M._lean(1.9) is None


def test_the_bar_is_held_out_per_side_by_menu_and_by_season():
    fitted = {"pass_rec": {"4": {"mu": 0.0, "sd": 0.1, "n": 900}}}
    good, flat = [], []
    for i in range(200):
        season = 2024 + i % 2
        # Parts high (z = +3): the parent's over hits four times in five at a fair 50%.
        good.append({"check": "pass_rec", "bucket": "4", "x": 0.3, "season": season,
                     "parent": {"over": int(i % 5 != 0), "p_over": 0.5},
                     "parts": [{"over": i % 2, "p_over": 0.5}, {"over": 0, "p_over": 0.5}]})
        flat.append({"check": "pass_rec", "bucket": "4", "x": 0.3, "season": season,
                     "parent": {"over": i % 2, "p_over": 0.5}, "parts": []})
    v = M.verdict(M.score(good, fitted))["pass_rec"]
    assert v["parent"]["holds"] and v["parent"]["n"] == 200 and v["parent"]["excess"] == 0.3
    assert set(v["parent"]["by_season"]) == {"2024", "2025"}
    assert v["parts"]["excess"] == 0.25 and v["parts"]["n"] == 200, "a menu's parts average to one number"
    assert not v["parts"]["holds"], "2025's parts did no better than fair: each test season must clear on its own"
    assert not M.verdict(M.score(flat, fitted))["pass_rec"]["parent"]["holds"], "a coin is not a lean"
    quiet = [{**c, "x": 0.05} for c in good]
    assert M.score(quiet, fitted) == {}, "under |z| 2 nothing is scored"
    few = M.verdict(M.score(good[:100], fitted))["pass_rec"]["parent"]
    assert not few["holds"] and few["n"] == 100, "under MIN_CASES the bar is not met"


def test_the_history_join_reads_each_books_close_and_the_mans_own_result():
    conn = D.connect(":memory:")
    date = "2025-10-12"
    rows = []
    def q(player, market, book, line, o=-110, u=-110):
        rows.append({"sport": "nfl", "taken_at": "2025-10-12T16:00:00Z", "event_id": "e1", "home": "KC", "away": "BUF",
                     "player": player, "market": market, "book": book, "line": line, "over_odds": o,
                     "under_odds": u, "commence_time": "2025-10-12T17:00:00Z"})
    q("patrick mahomes", "pass_yds", "dk", 250.5)
    for name, line in (("travis kelce", 60.5), ("rashee rice", 70.5), ("xavier worthy", 45.5)):
        q(name, "rec_yds", "dk", line)
    D.upsert_odds_history(conn, rows)
    logs = [("Patrick Mahomes", "QB", "pass_yds", 301.0), ("Travis Kelce", "TE", "rec_yds", 40.0),
            ("Rashee Rice", "WR", "rec_yds", 90.0), ("Xavier Worthy", "WR", "rec_yds", 45.0)]
    for name, pos, m, v in logs:
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES ('nfl', 2025, '006', 'KC-006', ?, 'KC', 'BUF', ?, 1, ?, ?)",
                     (name, pos, m, v))
    real = M._season_week_dates
    M._season_week_dates = lambda seasons=None: {(2025, 6, "KC"): date, (2025, 6, "BUF"): date}
    try:
        cases = [c for c in M.history_cases(conn, "nfl") if c["check"] == "pass_rec"]
    finally:
        M._season_week_dates = real
    assert len(cases) == 1
    c = cases[0]
    assert c["book"] == "dk" and c["team"] == "KC" and c["season"] == 2025 and c["bucket"] == "3"
    assert abs(c["x"] - math.log(176.5 / 250.5)) < 1e-9
    assert c["parent"] == {"player": "patrick mahomes", "line": 250.5, "over": 1, "p_over": 0.5}
    assert sorted((p["player"], p["over"]) for p in c["parts"]) == [
        ("rashee rice", 1), ("travis kelce", 0), ("xavier worthy", 0)]


def test_the_ideas_file_builds_each_section_alone_and_serves_slices():
    props, games = _slate()
    real = dict(ID.SECTIONS)
    ID.SECTIONS["broken"] = "no_such_module_here"
    try:
        data = ID.build("nfl", props, games, {})
    finally:
        ID.SECTIONS.clear()
        ID.SECTIONS.update(real)
    assert "menu" in data["sections"] and "broken" in data["errors"], "one section's failure is its own"
    d = Path(tempfile.mkdtemp())
    try:
        p = ID.write("nfl", data, where=d)
        assert p.name == "ideas_nfl.json" and not list(d.glob("*.tmp"))
        back = ID.read("nfl", where=d)
        pick = ID.pick_slice(back, "WR1", "rec_yds", "over", 70.5)
        assert [r["check"] for r in pick["sections"]["menu"]["rows"]] == ["pass_rec"]
        game = ID.game_slice(back, "KC", "BUF")
        assert "menu" not in game["sections"], "no flagged menu at the game, nothing to show"
        assert ID.game_slice(back, "BUF", "KC")["sections"] == {}
    finally:
        shutil.rmtree(d)
    from engine import gate
    assert ID.directory() == Path(gate.FULL_DIR), "private: beside the full boards, outside the web root"
    tree = Path(tempfile.mkdtemp())
    try:
        calls = []
        real_j = ID._section_fns
        ID._section_fns = lambda name: (*real_j(name)[:3], lambda sport, sec: calls.append(name))
        try:
            ID.attach("nfl", props, games, {}, out=str(tree / "web" / "data" / "recommendations.json"), quiet=True)
        finally:
            ID._section_fns = real_j
        assert (tree / "data" / "built" / "ideas_nfl.json").exists(), "the file goes beside that build's own board"
        assert calls == [], "a scratch tree keeps nothing in the history database"
    finally:
        shutil.rmtree(tree)


def test_the_endpoint_the_builds_and_the_pages():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/ideas", "/api/ideas/"):' in src
    body = src[src.index("    def _ideas(self, q):"):src.index("    def _players_versus(self, q):")]
    assert "self._entitled(aconn, who)" in body and "401 if not who else 402" in body
    for build, sport in (("nfl_build.py", "nfl"), ("cfb_build.py", "cfb")):
        src_b = (ROOT / build).read_text(encoding="utf-8")
        assert f'_ideas.attach("{sport}",' in src_b and "out=args.out)" in src_b, "beside the build's own board"
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '<div id="pp-lab"></div>' in app and '<div id="gp-lab"></div>' in app
    assert 'X.pickLab(document.getElementById("pp-lab"), state.sport, r)' in app
    assert 'X.gameLab(document.getElementById("gp-lab"), state.sport, g)' in app
    ext = (ROOT / "web" / "js" / "extras.js").read_text(encoding="utf-8")
    assert 's.src = "js/lab.js";' in ext and "pickLab, gameLab, loadLab };" in ext
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    props, games = _slate()
    rows = M.menus(props, games, "nfl", fitted={"pass_rec": {"4": {"mu": 0.0, "sd": 0.05, "n": 500}}})
    slice_ = {"sections": {"menu": M.pick_view({"rows": rows, "summary": M.summary(rows), "verdict": {}, "flag_z": 2},
                                               "WR1", "rec_yds")}}
    held = {"sections": {"menu": {**slice_["sections"]["menu"],
                                  "verdict": {"pass_rec": {"parent": {"holds": True}}}}}}
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{p: L.pickHTML({json.dumps(slice_)}), h: L.pickHTML({json.dumps(held)}),"
              "e: L.pickHTML({sections: {}})}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    got = json.loads(out.stdout)
    assert "Do the books add up?" in got["p"] and "Reading · not measured yet" in got["p"]
    assert "the total under, the pieces over" in got["p"] and 'class="flag"' in got["p"]
    assert "Measured · holds" in got["h"] and got["e"] == ""


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
