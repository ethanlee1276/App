"""The Lab draws what the replay writes (web/js/more.js, engine/lab.py).

Ethan, 2026-11-14, a screenshot of #lab: "the lab shows this every time u
click on the page. its never worked so we need to dive into that and fix
that." — "Sorry — part of this page failed to draw ... (Cannot read
properties of undefined (reading 'toLocaleString'))".

The members' Lab printed each game-line market's count as
`g.games_priced.toLocaleString()`. engine/lab.game_lines has never written
`games_priced`: it writes `games_quoted`, since 2026-08-28 (9ddb0c19, the
fix that first put game lines on the page at all). From that day every
member's Lab threw on the first league with graded game lines, and the
error took every league's block with it. The page's own test fed it a
fixture spelled the way the PAGE expected, so the suite stayed green
while the page never drew.

These checks hold the page to the writer: the data here is built by the
replay's own code (engine/lab.game_lines over a stubbed replay result,
engine/lab.report_to_dict over a real BacktestReport, engine/lab.cfb_props
over a stubbed runner), then drawn by the members' Lab in Chromium. Every
count on the page goes through `labN`, which prints a dash where the
replay wrote nothing; and one league's block that does not draw costs
that block, never the page.

    python3 tests/test_the_lab_draws_what_the_replay_writes.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_lab_draws_what_the_replay_writes.py
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def _fn(name):
    m = re.search(r"^(async )?function " + name + r"\(", MORE, re.M)
    assert m, name
    return MORE[m.start():MORE.index("\n}\n", m.start()) + 2]


def _game_lines(markets=("spread", "total")):
    """engine/lab.game_lines' own output, over a stubbed replay."""
    from engine import gamebacktest as GB
    from engine import lab as LAB
    real = GB.backtest_game_lines

    def fake(conn, sport, market="total", **_kw):
        if market not in markets:
            raise ValueError("no harvested closing lines for this market — a test")
        # `roi` is the result's own property (net over staked): -0.4%.
        return GB.GameLineBacktest(sport=sport, market=market, games_seen=2412, games_quoted=2345,
                                   unpriced=12, n_bets=312, wins=163, staked=312.0, net=-1.25, mae=10.42)
    GB.backtest_game_lines = fake
    try:
        return LAB.game_lines(None, "mlb", log=lambda *_: None)
    finally:
        GB.backtest_game_lines = real


def _prop_market():
    """engine/lab.report_to_dict over a real BacktestReport, mixed basis."""
    from engine.backtest import BacktestReport, CalibrationBin
    from engine import lab as LAB
    pairs = [(0.55, 1 if i % 3 else 0) for i in range(150)]
    rep = BacktestReport(n=3069, mae=13.04, rmse=26.6, brier=0.2443, ece=0.026,
                         bins=[CalibrationBin(0.4, 0.6, 2800, 0.531, 0.555)],
                         n_bets=352, wins=188, win_rate=0.534, roi=0.1066, net_units=5.25, units_staked=49.3,
                         used_real_lines=277, total_priced=5813, pairs=pairs,
                         segments={"book": {"n_bets": 277, "wins": 140, "win_rate": 0.505, "roi": -0.012, "net": -0.8},
                                   "naive": {"n_bets": 75, "wins": 48, "win_rate": 0.64, "roi": 0.21, "net": 6.05}})
    return LAB.report_to_dict(rep, "pass_yds", "Passing Yards")


def _cfb_props():
    from engine import lab as LAB

    class Rep:
        n, brier, base_rate = 1200, 0.181, 0.24
        pairs = [(0.3, 1), (0.2, 0)] * 600
        bands = {(0.2, 0.4): {"n": 1200, "claimed": 0.25, "landed": 0.24}}
    return LAB.cfb_props(runner=lambda: Rep())


def _page():
    return {"generated_at": "2026-11-14T00:53:32", "every_days": 7, "min_history": 8,
            "basis_note": "A prop priced against a NAIVE baseline line measures predictive skill.",
            "sports": {
                "mlb": {"props": {"unavailable": "no ingested game logs deep enough"},
                        "game_lines": _game_lines(), "replayed_at": "2026-11-13T20:29:34"},
                "nfl": {"props": {"markets": [_prop_market()], "season": 2026},
                        "game_lines": _game_lines(markets=("spread",)), "replayed_at": "2026-11-13T20:29:45"},
                "cfb": {"props": _cfb_props(), "game_lines": {"unavailable": "no harvested closing lines"},
                        "replayed_at": "2026-11-13T20:29:45"},
                "cbb": {"props": {"unavailable": "no ingested game logs deep enough to replay yet"},
                        "game_lines": {"unavailable": "no scoring baseline registered for 'cbb'"}}}}


def test_the_page_reads_the_count_the_writer_writes():
    written = _game_lines()["markets"][0]
    assert "games_quoted" in written and "games_priced" not in written, written
    table = _fn("labGameTable")
    assert "labN(g.games_quoted)" in table and "g.games_priced" not in MORE, \
        "the page reads the field engine/lab writes"
    # Every field the game-lines row reads, the writer writes.
    read = set(re.findall(r"\bg\.(\w+)", table))
    assert read <= set(written), read - set(written)


def test_no_count_on_the_lab_goes_through_a_bare_tolocalestring():
    lab = "".join(_fn(n) for n in ("labBins", "labPropCard", "labGameTable", "labSportHTML",
                                   "labRippleHTML", "renderLab", "labFreeHTML"))
    bare = re.findall(r"[A-Za-z_]\w*\.\w+\.toLocaleString\(", lab)
    assert not bare, bare
    assert "const labN = (x) => (x == null || !Number.isFinite(Number(x)) ? \"—\"" in MORE


def test_one_leagues_block_that_does_not_draw_costs_that_block():
    r = _fn("renderLab")
    assert "try { return labSportHTML(sport, d); } catch (e) {" in r
    assert "This league’s replay could not be drawn just now" in r


def _draw(page_json):
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                             body="{}"))
                body = json.dumps(page_json)
                page.route("**/api/board/backtest.json", lambda r: r.fulfill(
                    status=200, content_type="application/json", body=body))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                     "localStorage.setItem('qb.tour','done');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#lab", wait_until="load")
                page.wait_for_function("() => (document.getElementById('lab-body') || {}).innerText"
                                       " && document.getElementById('lab-body').innerText.length > 200",
                                       timeout=15000)
                text = page.evaluate("() => document.getElementById('lab-body').innerText")
                # The app's own apology (app.js crashNote), which a caught
                # render error raises as well as an uncaught one.
                banner = page.evaluate("() => { const n = document.querySelector('.crash-note');"
                                       " return n ? n.innerText : ''; }")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return text, errs, banner


def test_in_a_browser_the_members_lab_draws_every_league():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    text, errs, banner = _draw(_page())
    assert not errs, errs
    assert not banner, banner
    assert "undefined" not in text and "NaN" not in text, text[:2000]
    assert "2,345 games graded · MAE 10.42 vs close · 12 of them had no price to bet" in text, text[:3000]
    assert "-0.4% ROI" in text, "the game line's ROI"
    assert "312 bets" in text, "the game line's bets"
    assert "3,069 settled props" in text and "277 bets met a real close" in text, "the NFL's prop card"
    assert "1,200 settled props" in text, "college football's outcomes card"
    # The section titles are upper case by CSS, which innerText keeps.
    assert "not replayed yet" in text.lower() and "no scoring baseline registered for 'cbb'" in text


def test_in_a_browser_a_broken_league_costs_only_its_own_block():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    broken = _page()
    broken["sports"]["nba"] = {"props": {"markets": [None]}, "game_lines": {"unavailable": "x"}}
    text, errs, banner = _draw(broken)
    assert not errs and not banner, (errs, banner)
    assert "This league’s replay could not be drawn just now" in text
    assert "2,345 games graded" in text and "3,069 settled props" in text, "the other leagues still draw"


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
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
