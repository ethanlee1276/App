"""A player's market line can be moved, and his games are read against it (step AEY, 25 November 2026).

Ethan, 25 November 2026, circling a player page's market chips and writing "Adjust the line": "we should be able
too adjust the lines and numbers with a slide or something so users can see different lines". What this holds:

  * a priced market card with three games or more carries a slider under its chart, at the book's line, one line a
    step through the book's own half (a 0.5 moves through 1.5, 2.5…; a whole line through whole numbers), from a
    step under his lowest game (never under the lowest line a book posts) to a step over his highest;
  * moving it moves the chart's line, each bar's colour and the count under it, the game table's hits and the hit
    rate strip (every game shown, the last 5, the last 10); over or under can be switched; the book's line is one
    tap back;
  * the line moved is kept per player and market, so a redraw draws it where it was left, and a redraw holds off
    a moment while a thumb is on it;
  * the pick block stays the book's line;
  * a market with no book line tonight (the history chips) gets the same slider and draws no line until the reader
    sets one (a line nobody posted is never drawn as a book's); its thumb starts at the line nearest the average,
    and "Clear the line" takes it away again.

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
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(body):
    if not shutil.which("node"):
        return None
    head = ("const _lineAdj = new Map();\nconst lineAdjKey = (r) => `${r.player}|${r.market_label || r.market}`;\n"
            "const lineAdjHit = (v, line, side) => (side === \"UNDER\" ? Number(v) < line : Number(v) > line);\n"
            "const plural = (n, w) => `${n} ${w}${n === 1 ? \"\" : \"s\"}`;\n")
    prog = head + "".join(_fn(n) for n in ("lineAdjVals", "lineAdjRange", "lineAdjState", "lineAdjReadHTML")) + \
        f"\nconsole.log(JSON.stringify((() => {{ {body} }})()));"
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_the_slider_runs_through_the_books_half_from_a_step_under_his_lowest_to_a_step_over_his_highest():
    got = _node("""
      const steals = { line: 0.5, side: "under", logs: [2, 0, 1, 1, 1, 1, 0, 1, 3].map((v) => ({ value: v })) };
      const points = { line: 20.5, logs: [25, 31, 14, 8, 22].map((v) => ({ value: v })) };
      const whole = { line: 6, logs: [4, 7, 9].map((v) => ({ value: v })) };
      return [lineAdjRange(steals), lineAdjRange(points), lineAdjRange(whole), lineAdjState(steals),
              lineAdjReadHTML(points, 20.5, "OVER"), lineAdjReadHTML(steals, 1.5, "UNDER")];""")
    if got is None:
        print("      (skipped: no node)")
        return
    steals, points, whole, state, read_pts, read_stl = got
    assert steals == {"lo": 0.5, "hi": 3.5, "frac": 0.5}, "never under the book's lowest line, a step over his best"
    assert points == {"lo": 7.5, "hi": 31.5, "frac": 0.5}
    assert whole == {"lo": 3, "hi": 9, "frac": 0}, "a whole line through whole numbers"
    assert state == {"line": 0.5, "side": "UNDER"}, "the book's line and side until moved"
    nb = "\u00a0"                          # each part kept whole on a phone
    assert read_pts == f"<b>Over 20.5</b> · 3{nb}of{nb}5{nb}games{nb}(60%)", read_pts
    assert read_stl == f"<b>Under 1.5</b> · 7{nb}of{nb}9{nb}games{nb}(78%) · last{nb}5:{nb}4/5", read_stl


def test_the_card_draws_it_under_its_chart_and_the_redraw_holds_off():
    card = _fn("pricedProfileHTML")
    assert '<div class="profile-spark">${profileBarsHTML(r, at.line, at.side)}</div>\n      ${lineAdjHTML(r)}' in card
    assert "const hit = lineAdjHit(l.value, at.line, at.side);" in card and 'data-v="${escapeAttr(String(l.value))}"' in card
    assert "if (Date.now() - _lineAdjBusy < LINE_ADJ_HOLD_MS" in APP
    for sel in (".line-adj {", ".la-range {", ".la-step {", ".la-sd.on {", ".la-reset[hidden] {"):
        assert sel in CSS, sel
    assert "accent-color: var(--warn)" in CSS, "the thumb is the dashed rule's colour"


def _board():
    vals = [1, 3, 0, 2, 4, 1, 2, 0, 5, 1, 2, 3]
    logs = [{"week": 12 - i, "opponent": "NO", "home": i % 2 == 0, "value": v} for i, v in enumerate(vals)]
    row = {"player": "Chuba Hubbard", "team": "CAR", "opponent": "GB", "market": "rec", "market_label": "Receptions",
           "side": "under", "line": 2.5, "odds": -125, "book": "DraftKings", "model_prob": 0.58, "hit_prob": 0.58,
           "implied_prob": 0.55, "kind": "prop", "lane": "prop", "tier": "strong", "bettable": True,
           "confidence": 6.0, "grade": "B", "projection": 1.9, "edge": 0.03, "reasons": ["because"],
           "recommended": True, "game_date": "2099-01-01", "game": "CAR@GB", "logs": logs, "recent_values": vals,
           "form": {"last1": 1, "last3": 1.3, "last5": 2, "last10": 2, "season": 2}}
    carries = [{"week": 12 - i, "opponent": "NO", "home": i % 2 == 0, "value": v}
               for i, v in enumerate([10, 12, 8, 15, 9])]
    return {"sport": "nfl", "date": "2099-W01", "recommendations": [row], "most_likely": [],
            "games": [{"home": "GB", "away": "CAR", "date": "2099-01-01", "kickoff": "20:15"}],
            "player_stats": {"Chuba Hubbard": {"Carries": carries}}}


def test_in_a_browser_the_line_moves_and_every_reading_moves_with_it():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    body = json.dumps(_board())
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
                page.wait_for_selector(".plr .profile .line-adj .la-range", timeout=20000)

                def read():
                    return page.evaluate("""() => { const c = document.querySelector('.plr .profile');
                        const r = c.querySelector('.la-range');
                        return { value: r.value, min: r.min, max: r.max,
                          read: c.querySelector('.la-read').innerText, cap: c.querySelector('.glbars-cap').innerText,
                          hits: c.querySelectorAll('.log-table td.num.hit').length,
                          good: c.querySelectorAll('.profile-spark rect[fill="var(--good)"]').length,
                          reset: c.querySelector('.la-reset').hidden,
                          on: c.querySelector('.la-sd.on').dataset.side,
                          pick: c.querySelector('.profile-pick .lbl').innerText,
                          wide: document.documentElement.scrollWidth - innerWidth }; }""")
                got["start"] = read()
                page.locator(".plr .profile .la-step[data-d='1']").click()
                got["plus"] = read()
                page.locator(".plr .profile .la-sd[data-side='OVER']").click()
                got["over"] = read()
                page.locator(".plr .profile .la-range").fill("0.5")
                got["slid"] = read()
                # A redraw (the board's minute) draws the card where the reader left it.
                page.evaluate("_lineAdjBusy = 0; renderPlayers()")
                page.wait_for_timeout(300)
                got["redrawn"] = read()
                page.locator(".plr .profile .la-reset").click()
                got["reset"] = read()
                # A market with no book line tonight: the history chip.
                page.locator(".plr .prof-tab[data-mkt='Carries']").click()
                page.wait_for_selector(".plr .profile .line-adj[data-history] .la-range", timeout=10000)
                hist = """() => { const c = document.querySelector('.plr .profile'), cap = c.querySelector('.glbars-cap');
                    return { value: c.querySelector('.la-range').value, cap: cap ? cap.innerText : null,
                      rule: c.querySelectorAll('.profile-spark line').length,
                      read: c.querySelector('.la-read').innerText, hits: c.querySelectorAll('.log-table td.hit').length,
                      reset: c.querySelector('.la-reset').innerText, hidden: c.querySelector('.la-reset').hidden }; }"""
                got["hist"] = page.evaluate(hist)
                page.locator(".plr .profile .la-step[data-d='1']").click()
                got["hist_plus"] = page.evaluate(hist)
                page.locator(".plr .profile .la-reset").click()
                got["hist_clear"] = page.evaluate(hist)
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    s, p, o, sl, rd, rs = (got[k] for k in ("start", "plus", "over", "slid", "redrawn", "reset"))
    assert (s["value"], s["min"], s["max"]) == ("2.5", "0.5", "5.5"), s
    assert s["read"].replace("\u00a0", " ").startswith("Under 2.5 · 8 of 12 games (67%)") and s["cap"] == "8/12 under 2.5", s
    assert s["hits"] == 8 and s["reset"] is True and s["on"] == "UNDER", s
    assert p["value"] == "3.5" and p["cap"] == "10/12 under 3.5" and p["hits"] == 10 and p["reset"] is False, p
    assert o["on"] == "OVER" and o["cap"] == "2/12 over 3.5" and o["hits"] == 2 and o["good"] == 2, o
    assert sl["value"] == "0.5" and sl["cap"] == "10/12 over 0.5" and sl["read"].replace("\u00a0", " ").startswith(
        "Over 0.5 · 10 of 12"), sl
    assert rd["value"] == "0.5" and rd["on"] == "OVER" and rd["cap"] == "10/12 over 0.5", ("kept across a redraw", rd)
    assert rs["value"] == "2.5" and rs["on"] == "UNDER" and rs["cap"] == "8/12 under 2.5" and rs["reset"] is True, rs
    assert "2.5" in s["pick"] and "2.5" in p["pick"], "the pick block stays the book's line"
    assert all(x["wide"] <= 0 for x in (s, p, o, sl, rd, rs)), "no sideways scroll at a phone's width"
    h, hp, hc = got["hist"], got["hist_plus"], got["hist_clear"]
    assert h["value"] == "10.5" and h["cap"] is None and h["rule"] == 0 and h["hits"] == 0, ("no line drawn", h)
    assert h["read"].startswith("No book line tonight") and h["hidden"] is True, h
    assert hp["value"] == "11.5" and hp["cap"] == "2/5 over 11.5" and hp["rule"] == 1 and hp["hits"] == 2, hp
    assert hp["hidden"] is False and hp["reset"] == "Clear the line", hp
    assert hc["cap"] is None and hc["rule"] == 0 and hc["hits"] == 0 and hc["hidden"] is True, ("cleared", hc)
    assert not got["errs"], got["errs"]


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
