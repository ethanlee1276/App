"""Last season's weeks say their season on an NFL card (step AFH, 25 November 2026).

An NFL card names a game by its week, and ten games reach back across the summer: on the live board on 25 November,
191 NFL market logs held a week number twice, this season's week 9 and last season's, with nothing to say which. The
head-to-head already writes an earlier season's week with its year ("’25 Wk 9", js/app.js versus rows). Now:

  * the board's logs mark a game of an earlier NFL season with that season (engine/statlogs, ``season``), and a
    priced card's carried game (engine/pipeline, `prior`) with last season;
  * the card's chart, its log table, the line slider's redraw, the pick page's rows and the fantasy weekly chart all
    say it the head-to-head's way, "’25 Wk 17"; this season's weeks read as before.

The browser half runs with QB_BROWSER_TESTS=1 and /usr/bin/python3.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import db, statlogs  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_the_board_marks_an_earlier_seasons_games():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = [{"sport": "nfl", "season": season, "period": f"{w:03d}", "game_id": f"CAR-{w:03d}", "player": "Chuba Hubbard",
             "team": "CAR", "opponent": "NO", "position": "RB", "home": 1, "market": "carries", "value": 10.0 + w}
            for season, weeks in ((2026, range(1, 6)), (2025, range(14, 19))) for w in weeks]
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    try:
        got = statlogs._query(conn, "nfl", statlogs.SPORT_MARKETS["nfl"], ["Chuba Hubbard"], season=2026)
    finally:
        conn.close()
    logs = got["Chuba Hubbard"]["Carries"]
    assert [(g["week"], g.get("season")) for g in logs] == [(5, None), (4, None), (3, None), (2, None), (1, None),
                                                            (18, 2025), (17, 2025), (16, 2025), (15, 2025), (14, 2025)]
    assert statlogs._season_now("nba") is None
    src = (ROOT / "engine" / "statlogs.py").read_text(encoding="utf-8")
    assert "_query(conn, sport, markets, [player], season=_season_now(sport))" in src
    assert '"season": season,' in src, "the kept read is keyed on the season it marks against"


def test_a_priced_cards_carried_game_says_last_season():
    src = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
    assert ('**({"season": nfl_season_of(_SLATE_DATE.get("date")) - 1}\n'
            '                if sport == "nfl" and getattr(g, "prior", False) else {})}') in src


def test_every_week_label_says_it_the_head_to_heads_way():
    assert "`’${escapeHtml(String(g.season).slice(2))} Wk ${g.week}`" in APP, "the head-to-head's own form"
    word = _fn(APP, "nflWeekWord")
    assert "(season ? `’${String(season).slice(2)} ` : \"\")" in word
    assert "nflWeekWord(l.week, r0.sport, l.season)" in _fn(APP, "historyProfileHTML")
    priced = _fn(APP, "pricedProfileHTML")
    assert priced.count("nflWeekWord(l.week, r.sport || state.sport, l.season)") == 2
    assert "`${nflWeekWord(g.week, \"nfl\", g.season)} ${g.home ? \"vs\" : \"@\"} ${g.opponent}`" in APP
    pp = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
    bars = _fn(pp, "lineAdjBars")
    assert "nflWeekWord(l.week, r.sport, l.season)" in bars and "nflWeekWord(l.week, r.sport || state.sport, l.season)" in bars
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert "`${g.season ? `’${String(g.season).slice(2)} ` : \"\"}Wk ${g.week}`" in detail
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    i = APP.index("const NFL_ROUND = ")
    rounds = APP[i:APP.index(";\n", i) + 2]
    prog = rounds + word + "\nconsole.log(JSON.stringify([nflWeekWord(9, 'nfl'), nflWeekWord(17, 'nfl', 2025), " \
                           "nflWeekWord(19, 'nfl', 2025), nflWeekWord(19, 'nfl')]));"
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    assert got[0] == "Wk 9" and got[1] == "’25 Wk 17", got
    assert got[2] == "’25 " + got[3] and got[3] != "Wk 19", "a playoff round keeps its name, with the year"


def test_in_a_browser_the_history_card_says_last_seasons_weeks():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    ML = __import__("test_a_market_line_can_be_moved")
    board = ML._board()
    board["player_stats"]["Chuba Hubbard"]["Carries"] = (
        [{"week": w, "opponent": "NO", "home": True, "value": v} for w, v in ((3, 12), (2, 9), (1, 15))]
        + [{"week": w, "opponent": "TB", "home": False, "value": v, "season": 2025} for w, v in ((18, 7), (17, 11))])
    body = json.dumps(board)
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("() => typeof openPlayerRoute === 'function' && state.data", timeout=20000)
                page.evaluate("openPlayerRoute('chuba-hubbard', 'Chuba Hubbard')")
                page.wait_for_selector(".plr .profile .form-tiles", timeout=20000)
                page.locator(".plr .prof-tab[data-mkt='Carries']").click()
                page.wait_for_selector(".plr .profile .profile-spark[data-history]", timeout=10000)
                got = page.evaluate("""() => { const c = document.querySelector('.plr .profile');
                    return { rows: [...c.querySelectorAll('.log-table tr')].slice(1).map((tr) => tr.cells[0].textContent),
                      season: [...c.querySelectorAll('.form-tile')].map((t) => t.querySelector('.v').textContent)[4],
                      wide: document.documentElement.scrollWidth - innerWidth }; }""")
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["rows"] == ["Wk 3", "Wk 2", "Wk 1", "’25 Wk 18", "’25 Wk 17"], got
    assert got["season"] == "12", "this season's three games: (12 + 9 + 15) / 3"
    assert got["wide"] <= 0 and not got["errs"], got


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
