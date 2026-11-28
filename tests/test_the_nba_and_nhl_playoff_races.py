"""The NBA's and the NHL's playoff races, played off the season simulation.

Ethan, 2026-11-17, yes to "NHL and NBA playoff race pages? The season
simulation already computes every team's playoff chances, so they can get
brackets like the NFL's: seeds free, chances for members."

Checks, one rule each:
- the simulation plays each league's own format: the NBA's play-in, a fixed
  bracket (1 v 8's winner meets 4 v 5's), the NHL's division bracket with
  the better division winner on the lower wild card, and a series final;
- the field if it ended today is ordered by the leagues' first tiebreakers:
  the NBA's head-to-head among tied clubs, the NHL's points percentage when
  points are level;
- the race's chances are the Futures page's own run, number for number;
- the field and the standings are free, the chances members';
- both writers publish the race beside the board, and Ask reads it;
- the page draws both, the NBA's with its Cup one tap away (browser).

Run directly: `python3 tests/test_the_nba_and_nhl_playoff_races.py`
    QB_BROWSER_TESTS=1 python3 tests/test_the_nba_and_nhl_playoff_races.py
"""
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, gate, seasonrace as SR, standings          # noqa: E402
from engine import futures as F                                   # noqa: E402
from engine import futuresdata as FD                              # noqa: E402
from engine.divisions import MAPS                                 # noqa: E402

RACE = (ROOT / "web" / "js" / "race.js").read_text()
GAMES_DRAWN = {"nba": 21, "nhl": 15}
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _season(sport, n=240, seed=3):
    """A played stretch of `sport`'s season in a real-schema database, and
    the games left."""
    teams = sorted(MAPS[sport])
    rng = random.Random(seed)
    conn = db.connect(":memory:")
    rows = []
    for i in range(n):
        h, a = rng.sample(teams, 2)
        hs, as_ = (3.0, 2.0) if sport == "nhl" else (110.0, 100.0)
        if rng.random() < 0.5:
            hs, as_ = as_, hs
        ex = json.dumps({"type": 2, "ended_in": "OT" if i % 6 == 0 else "REG"}) if sport == "nhl" else None
        rows.append((sport, 2026, f"2026-11-{1 + i % 15:02d}", f"g{i}", h, a, hs, as_, ex))
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, "
                     "away_score, extra) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return conn, [FD.Fixture(*rng.sample(teams, 2)) for _ in range(300)]


def _project(sport, trials=400):
    conn, left = _season(sport)
    real = FD.FIXTURES.get(sport)
    FD.FIXTURES[sport] = lambda _s: left
    try:
        sim = FD.project(conn, sport, season=2026, trials=trials, prices=False)
    finally:
        FD.FIXTURES[sport] = real
    return conn, sim


def _race(sport):
    conn, sim = _project(sport)
    table = standings.compute(conn, sport, season=2026)
    return SR.build(sport, table, standings.season_games(conn, sport, 2026), sim, "2026-11-17"), sim


# --- the simulation plays the leagues' own formats ---------------------------
def test_the_play_in_decides_the_seventh_and_eighth_seeds():
    top = [f"T{i}" for i in range(1, 11)]
    ratings = {t: 0.0 for t in top}
    ratings["T10"] = 99.0                      # the tenth wins every game it plays
    got = F._play_in("nba", top, ratings, random.Random(1))
    assert got[:6] == top[:6] and len(got) == 8
    assert got[7] == "T10", "the 10 seed won both games and is the 8 seed"
    assert got[6] in ("T7", "T8")
    ratings = {t: 0.0 for t in top}
    ratings["T8"] = 99.0
    assert F._play_in("nba", top, ratings, random.Random(1))[6] == "T8", "7 v 8's winner is the 7 seed"


def test_the_bracket_is_fixed_from_the_first_round():
    met = []
    real = F._play_series
    F._play_series = lambda sport, a, b, ratings, n, rng: met.append((a, b)) or a
    try:
        seeds = [f"S{i}" for i in range(1, 9)]
        order = [seeds[i] for i in F.BRACKET_8]
        champ = F._run_fixed("nba", F.SHAPES["nba"], order, {}, random.Random(1), seeds.index)
    finally:
        F._play_series = real
    assert met[:4] == [("S1", "S8"), ("S4", "S5"), ("S2", "S7"), ("S3", "S6")]
    assert met[4:6] == [("S1", "S4"), ("S2", "S3")], "1 v 8's winner meets 4 v 5's, never a reseeded pair"
    assert met[6] == ("S1", "S2") and champ == "S1"


def test_the_nhl_bracket_draws_its_division_pairings():
    east = [t for t in sorted(MAPS["nhl"]) if MAPS["nhl"][t][0] == "Eastern"]
    atl = [t for t in east if MAPS["nhl"][t][1] == "Atlantic"]
    met = [t for t in east if MAPS["nhl"][t][1] == "Metropolitan"]
    pts = {t: 0 for t in east}
    for i, t in enumerate(atl):
        pts[t] = 90 - i                        # the Atlantic's winner has the conference's best record
    for i, t in enumerate(met):
        pts[t] = 85 - i
    order = F._nhl_bracket("nhl", east, lambda t: (-pts[t], t))
    a, m = sorted(atl, key=lambda t: -pts[t]), sorted(met, key=lambda t: -pts[t])
    wild = sorted([t for t in east if t not in a[:3] + m[:3]], key=lambda t: -pts[t])[:2]
    assert order == [a[0], wild[1], a[1], a[2], m[0], wild[0], m[1], m[2]], order


def test_a_final_is_a_series_and_the_super_bowl_a_game():
    for sport in ("nba", "nhl", "mlb", "wnba"):
        assert F.SHAPES[sport].final_len == 7, sport
    assert F.SHAPES["nfl"].final_len == 1
    assert not F.SHAPES["nba"].reseed and not F.SHAPES["nhl"].reseed and F.SHAPES["nfl"].reseed
    _, sim = _project("nba", trials=300)
    assert sim["play_in"] == 4
    # Each share is rounded to four places, so thirty of them sum to within 30 x 0.00005.
    tol = len(sim["teams"]) * 5e-5
    assert abs(sum(t["p_playoffs"] for t in sim["teams"]) - 16) <= tol, "eight a conference, every season"
    assert abs(sum(t["p_playin"] for t in sim["teams"]) - 8) <= tol, "four a conference play in"
    assert abs(sum(t["p_title"] for t in sim["teams"]) - 1) <= tol


# --- the field if it ended today ----------------------------------------------
def _nba_row(team, w, l, diff=0):
    return {"team": team, "wins": w, "losses": l, "pct": round(w / (w + l), 4), "diff": diff,
            "record": f"{w}-{l}", "games": w + l}


def test_the_nba_field_seeds_ten_and_breaks_a_tie_head_to_head():
    east = [t for t in sorted(MAPS["nba"]) if MAPS["nba"][t][0] == "East"]
    rows = [_nba_row(t, 15 - i, 5 + i) for i, t in enumerate(east)]
    a, b = rows[2], rows[3]
    a.update(_nba_row(a["team"], 12, 8)), b.update(_nba_row(b["team"], 12, 8))
    games = [{"home": a["team"], "away": b["team"], "home_score": 90.0, "away_score": 100.0}]
    t = SR.nba_today(rows, games, {})["East"]
    seeds = {s["seed"]: s for s in t["seeds"]}
    assert len(seeds) == 10 and seeds[1]["team"] == rows[0]["team"]
    assert seeds[3]["team"] == b["team"] and seeds[4]["team"] == a["team"], "the tie goes to the head-to-head winner"
    assert all(seeds[n]["why"] == "In" for n in range(1, 7)) and all(seeds[n]["why"] == "Play-in" for n in range(7, 11))
    tenth = seeds[10]["team"]
    w10 = next(r for r in rows if r["team"] == tenth)
    first_out = t["hunt"][0]
    r = next(x for x in rows if x["team"] == first_out["team"])
    assert first_out["back"] == ((w10["wins"] - r["wins"]) + (r["losses"] - w10["losses"])) / 2


def test_the_nhl_field_counts_points_then_points_percentage():
    west = [t for t in sorted(MAPS["nhl"]) if MAPS["nhl"][t][0] == "Western"]
    rows = []
    for i, t in enumerate(west):
        gp = 20
        rows.append({"team": t, "points": 40 - i, "games": gp, "wins": 20 - i // 2, "reg_wins": 15, "diff": 0,
                     "record": "x"})
    cen = [r for r in rows if MAPS["nhl"][r["team"]][1] == "Central"]
    # Two Central clubs level on points: the one with a game in hand ranks first.
    cen[0]["points"] = cen[1]["points"] = 45
    cen[1]["games"] = 19
    t = SR.nhl_today(rows, {})["Western"]
    div = t["divisions"]["Central"]
    assert div[0]["team"] == cen[1]["team"], "level on points, the better points percentage leads"
    assert len(t["wild_cards"]) == 2 and len(t["first_round"]) == 2
    first = t["first_round"][0]
    assert first["games"][0][1] == t["wild_cards"][1]["team"], "the better division winner draws the lower wild card"
    last = t["wild_cards"][1]
    h = t["hunt"][0]
    assert h["back"] == last["points"] - h["points"] and h["in_hand"] == last["games"] - next(
        r for r in rows if r["team"] == h["team"])["games"]


def test_the_race_s_chances_are_the_futures_page_s_own_run():
    for sport in SR.SPORTS:
        out, sim = _race(sport)
        by = {t["team"]: t for t in sim["teams"]}
        assert out["chances"], sport
        for team, ch in out["chances"].items():
            assert ch["playoffs"] == by[team]["p_playoffs"] and ch["title"] == by[team]["p_title"], (sport, team)
        assert out["sims"] == sim["trials"] and out["games_left"] == sim["fixtures_remaining"]
        assert set(out["today"]) == {MAPS[sport][t][0] for t in MAPS[sport]}
    nba, _ = _race("nba")
    assert all("playin" in ch for ch in nba["chances"].values())
    assert [r["seed"] for r in nba["standings"]["East"]] == list(range(1, 16)), "the conference table in seed order"


def test_the_field_is_free_and_the_chances_are_members():
    out, _ = _race("nhl")
    for name in SR.FILES.values():
        assert name in gate.KNOWN_BOARDS and name in gate.MIXED_FILES
        pub = gate.redact(out, name)
        assert pub["today"] == out["today"] and pub["standings"] == out["standings"]
        assert not pub.get("chances"), name


# --- the writers, Ask and the page ---------------------------------------------
def test_both_writers_publish_the_race_beside_the_board():
    import futures_build
    conn, sim = _project("nhl", trials=200)
    d = Path(tempfile.mkdtemp()) / "web" / "data"
    real = futures_build.OUT
    futures_build.OUT = d
    try:
        line = futures_build.publish("nhl", sim, conn)
    finally:
        futures_build.OUT = real
    assert (d / "futures_nhl.json").is_file() and (d / "nhl_race.json").is_file(), line
    assert "NHL playoff race" in line
    launch_src = (ROOT / "launch.py").read_text()
    i = launch_src.index("def _run_futures(")
    assert "futures_build.publish(sport, data, conn)" in launch_src[i:launch_src.index("\ndef ", i + 1)]


def test_ask_reads_the_nhl_race_and_the_nba_s_two():
    from engine import askbot
    nhl, _ = _race("nhl")
    nba, _ = _race("nba")
    d = tempfile.mkdtemp()
    for name, blob in (("nhl_race.json", nhl), ("nba_race.json", nba),
                       ("nba_cup.json", {"today": {"winners": {}}, "chances": {}})):
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(blob, fh)
    old, askbot.PAID_DIR = askbot.PAID_DIR, d
    try:
        h = askbot.playoff_race("nhl")
        b = askbot.playoff_race("nba")
    finally:
        askbot.PAID_DIR = old
    assert h["race"] == "the NHL playoffs" and set(h["today"]) == {"Eastern", "Western"}
    assert h["today"]["Eastern"]["wild_cards"] and h["today"]["Eastern"]["first_round"]
    assert h["best_chances"] and "playoffs" in h["best_chances"][0]
    assert b["race"] == "the NBA playoffs" and "nba_cup" in b, "the NBA answers with both races"
    assert any("(play-in)" in s for s in b["today"]["East"]["seeds"])
    enum = next(t for t in askbot.TOOLS if t["name"] == "playoff_race")["input_schema"]["properties"]["sport"]["enum"]
    assert "nhl" in enum and "nba" in enum


def test_the_nhl_opens_its_futures_and_race_tabs_and_the_page_knows_both_races():
    i = APP.index("  nhl: [")
    hidden = APP[i:APP.index("]", i)]
    assert '"futures"' not in hidden and '"race"' not in hidden, hidden
    assert 'nhl: "nhl_race.json"' in RACE
    assert 'file: "nba_race.json"' in RACE and 'file: "nba_cup.json"' in RACE


def _render(fn, sport, payload):
    js = f"""
    const state = {{ sport: "{sport}", view: "race" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const teamMarkIn = (sp, t) => `<i data-mark="${{t}}"></i>`;
    const teamNameIn = (sp, t) => t;
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const formatGameDate = (s) => s;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    const settings = () => ({{ teams: [] }});
    const isFavTeam = () => false;
    {RACE}
    console.log(JSON.stringify({fn}("{sport}", {json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-"], input=js, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_each_field_as_a_bracket_and_locks_only_the_chances():
    for sport in SR.SPORTS:
        out, _ = _race(sport)
        html = _render("seasonRaceHTML", sport, out)
        # The NBA: a conference's three play-in games, four in the first round, two semifinals and its
        # final, and the Finals: 21. The NHL: four, two and one a conference, and the Cup Final: 15.
        assert len(re.findall(r'class="rc-bk-game[ "]', html)) == GAMES_DRAWN[sport], sport
        assert "If the season ended today" in html and "member-lock" not in html
        locked = _render("seasonRaceHTML", sport, gate.redact(out, SR.FILES[sport]))
        assert "member-lock" in locked and "If the season ended today" in locked, sport
    nba = _render("seasonRaceHTML", "nba", _race("nba")[0])
    assert "Play-in" in nba and "For the 8 seed" in nba and "NBA Finals" in nba
    nhl = _render("seasonRaceHTML", "nhl", _race("nhl")[0])
    assert "Stanley Cup Final" in nhl and "WC" in nhl


def test_in_a_browser_both_races_draw_and_the_nba_switches_to_its_cup():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    from playwright.sync_api import sync_playwright
    import rendercheck
    nhl, nba = _race("nhl")[0], _race("nba")[0]
    cup = {"today": {"winners": {}, "wildcards": {}}, "groups": {}, "chances": {}, "sims": 0}
    files = {"nhl_race.json": nhl, "nba_race.json": nba, "nba_cup.json": cup}
    srv, port = rendercheck._serve()
    errs, got = [], {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for sport in ("nhl", "nba"):
                    for width in (390, 1366):
                        ctx = browser.new_context(viewport={"width": width, "height": 900}, service_workers="block")
                        page = ctx.new_page()
                        page.on("pageerror", lambda e: errs.append(str(e)))
                        page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                        page.route("**/api/**", lambda r, *_: r.fulfill(status=200, content_type="application/json", body="{}"))
                        for name, blob in files.items():
                            body = json.dumps(blob)
                            for pat in (f"**/api/board/{name}", f"**/data/{name}"):
                                page.route(pat, lambda r, *_, b=body: r.fulfill(status=200, content_type="application/json", body=b))
                        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                        page.goto(f"http://127.0.0.1:{port}/index.html?sport={sport}#race", wait_until="load")
                        if sport == "nba":
                            page.wait_for_selector("#race-body [data-rc-mode]", timeout=15000)
                            page.click('#race-body [data-rc-mode="playoffs"]')
                        page.wait_for_selector("#race-body .rc-bk-game", timeout=15000)
                        got[(sport, width)] = page.evaluate("""() => ({
                          games: document.querySelectorAll('#race-body .rc-bk-game').length,
                          wide: document.documentElement.scrollWidth > window.innerWidth + 1,
                          title: (document.getElementById('race-title') || {}).textContent || ''})""")
                        if sport == "nba":
                            page.click('#race-body [data-rc-mode="cup"]')
                            page.wait_for_function("() => (document.getElementById('race-title') || {}).textContent.includes('NBA Cup')")
                            got[("cup", width)] = page.evaluate(
                                "() => document.querySelector('#race-body [data-rc-mode=\"cup\"]').getAttribute('aria-selected')")
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    for (sport, width), g in got.items():
        if sport == "cup":
            assert g == "true", width
            continue
        assert g["games"] == GAMES_DRAWN[sport], (sport, width, g)
        assert not g["wide"], f"{sport} at {width}px: the page scrolls sideways"
        assert ("NHL playoff race" if sport == "nhl" else "NBA playoff race") in g["title"], g


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
