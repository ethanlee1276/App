"""Every market card on a player page wears the same form tiles (step AFD, 25 November 2026).

A market with a line tonight is drawn by `pricedProfileHTML`, with a row of tiles over its chart (L1, L3, L5, L10,
Season: the averages its build hands over). A market with no line tonight, or a locked board's, is drawn by
`historyProfileHTML` from the player's stored games, and had no tiles at all: tapping from Receptions to Carries on the
same page dropped the row. Ethan, 24 November: "We want every single sports player pages to match each other".

Now one helper (`formTiles`) draws the row on both cards, each number to one decimal (`tileNum`, step AFA). A history
card's L1 to L10 are the averages of its newest one, three, five and ten games (fewer where it has fewer, as the
builds' windows are). Its Season tile reads this season's games among its logs only where the logs reach the season's
start (a week number going up going back, week 1, or a gap of 60 days between games); ten games are not a season, so
otherwise it says "—".

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
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    j = APP.index(";\n", i)
    return APP[i:j + 2]


def test_both_cards_draw_the_row_through_one_helper():
    priced, hist = _fn("pricedProfileHTML"), _fn("historyProfileHTML")
    assert 'const tiles = formTiles([["L1", f.last1], ["L3", f.last3], ["L5", f.last5], ["L10", f.last10], ["Season", f.season]]);' in priced
    assert "${tiles}\n      <div class=\"profile-spark\"" in priced
    assert '${formTiles([["L1", meanOf(vals.slice(0, 1))], ["L3", meanOf(vals.slice(0, 3))], ["L5", meanOf(vals.slice(0, 5))],' in hist
    assert '["L10", meanOf(vals.slice(0, 10))], ["Season", meanOf((logSeason(logs) || []).map((l) => l.value))]])}' in hist
    assert hist.index("formTiles(") < hist.index('class="profile-spark"'), "over the chart, where the priced card has it"


def test_the_windows_and_the_season():
    if not shutil.which("node"):
        print("      (skipped: no node)")
        return
    prog = "\n".join([_const("tileNum"), _const("formTiles"), _const("meanOf"), _fn("logSeason"), r"""
const wk = (ws) => ws.map((w, i) => ({ week: w, value: i + 1 }));
const dt = (ds) => ds.map((d, i) => ({ date: d, value: i + 1 }));
const n = (s) => (s ? s.length : null);
console.log(JSON.stringify({
  mid: n(logSeason(wk([12, 11, 10, 9, 8]))),
  whole: n(logSeason(wk([3, 2, 1]))),
  turn: n(logSeason(wk([2, 1, 18, 17]))),
  dated: n(logSeason(dt(["2026-11-20", "2026-11-15", "2026-04-10", "2026-04-05"]))),
  undated_gap: n(logSeason(dt(["2026-11-20", "2026-11-15", "2026-11-10"]))),
  none: n(logSeason([])),
  mean: [meanOf([]), meanOf([1, 2]), meanOf([10, 12, 8])],
  row: formTiles([["L1", 10], ["L3", 10], ["L5", 10.8], ["L10", 10.8], ["Season", null]]),
}));
"""])
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    assert (got["mid"], got["whole"], got["turn"], got["dated"], got["undated_gap"], got["none"]) == (
        None, 3, 2, 2, None, None), got
    assert got["mean"] == [None, 1.5, 10], got
    assert got["row"].count('class="form-tile"') == 5 and got["row"].startswith('<div class="form-tiles">'), got["row"]
    assert '<div class="k">Season</div><div class="v">—</div>' in got["row"]


def test_in_a_browser_a_history_card_wears_the_priced_cards_row():
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
    body = json.dumps(ML._board())
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
                read = """() => { const c = document.querySelector('.plr .profile');
                    const t = [...c.querySelectorAll('.form-tiles .form-tile')];
                    const box = c.querySelector('.form-tiles').getBoundingClientRect();
                    return { k: t.map((x) => x.querySelector('.k').textContent), v: t.map((x) => x.querySelector('.v').textContent),
                      h: Math.round(box.height), w: Math.round(box.width),
                      above: box.bottom <= c.querySelector('.profile-spark').getBoundingClientRect().top + 1,
                      wide: document.documentElement.scrollWidth - innerWidth }; }"""
                got["priced"] = page.evaluate(read)
                page.locator(".plr .prof-tab[data-mkt='Carries']").click()
                page.wait_for_selector(".plr .profile .profile-spark[data-history]", timeout=10000)
                got["history"] = page.evaluate(read)
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    p, h = got["priced"], got["history"]
    assert p["k"] == h["k"] == ["L1", "L3", "L5", "L10", "Season"], got
    assert p["v"] == ["1", "1.3", "2", "2", "2"], p
    # Carries 10, 12, 8, 15, 9 (weeks 12 to 8): the season does not reach week 1 in five games.
    assert h["v"] == ["10", "10", "10.8", "10.8", "—"], h
    assert (h["h"], h["w"]) == (p["h"], p["w"]) and h["above"] and p["above"], got
    assert h["wide"] <= 0 and not got["errs"], got


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
