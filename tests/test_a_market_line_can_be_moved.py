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
  * it lives in the player page's own file (js/playerpage.js, css/playerpage.css), loaded when a player's page
    opens: app.js draws each card at the book's line as it always did and marks the chart, so a first visit
    downloads none of it (tests/test_the_first_paint_has_a_budget.py);
  * the pick block stays the book's line;
  * a market with no book line tonight (the history chips) gets the same slider and draws no line until the reader
    sets one (a line nobody posted is never drawn as a book's); its thumb starts at the line nearest the average,
    and "Clear the line" takes it away again;
  * a priced card moved off the book's number says what the books pay at the new one, in the parlay checker's words
    ("Now FanDuel −250 · BetMGM −270 · 4 books · 70% with the margin out"), read once per card from
    /api/lines/ladder (engine/sliplive.ladder_prices) behind the membership; a number no book prices says so, and
    nothing of ours is said at another number.

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
PP = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")


def _fn(name, src=None):
    src = PP if src is None else src
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(body):
    if not shutil.which("node"):
        return None
    head = ("const _lineAdj = new Map();\nconst lineAdjKey = (r) => `${r.player}|${r.market_label || r.market}`;\n"
            "const lineAdjHit = (v, line, side) => (side === \"UNDER\" ? Number(v) < line : Number(v) > line);\n"
            "const plural = (n, w) => `${n} ${w}${n === 1 ? \"\" : \"s\"}`;\n")
    prog = head + "".join(_fn(n) for n in ("lineAdjBook", "lineAdjVals", "lineAdjRange", "lineAdjState",
                                           "lineAdjReadHTML")) + \
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
      const kept = { player: "P", market_label: "Receptions", line: 3, side: "over", logs: whole.logs };
      _lineAdj.set(lineAdjKey(kept), { line: 3.5, side: "UNDER" });
      const offGrid = lineAdjState(kept);
      _lineAdj.set(lineAdjKey(kept), { line: 5, side: "UNDER" });
      return [lineAdjRange(steals), lineAdjRange(points), lineAdjRange(whole), lineAdjState(steals),
              lineAdjReadHTML(points, 20.5, "OVER"), lineAdjReadHTML(steals, 1.5, "UNDER"), offGrid,
              lineAdjState(kept)];""")
    if got is None:
        print("      (skipped: no node)")
        return
    steals, points, whole, state, read_pts, read_stl, off_grid, on_grid = got
    assert off_grid == {"line": 3, "side": "OVER"}, ("the book moved to a whole number: its line again", off_grid)
    assert on_grid == {"line": 5, "side": "UNDER"}, on_grid
    assert steals == {"lo": 0.5, "hi": 3.5, "frac": 0.5}, "never under the book's lowest line, a step over his best"
    assert points == {"lo": 7.5, "hi": 31.5, "frac": 0.5}
    assert whole == {"lo": 3, "hi": 9, "frac": 0}, "a whole line through whole numbers"
    assert state == {"line": 0.5, "side": "UNDER"}, "the book's line and side until moved"
    nb = "\u00a0"                          # each part kept whole on a phone
    assert read_pts == f"<b>Over 20.5</b> · 3{nb}of{nb}5{nb}games{nb}(60%)", read_pts
    assert read_stl == f"<b>Under 1.5</b> · 7{nb}of{nb}9{nb}games{nb}(78%) · last{nb}5:{nb}4/5", read_stl


def test_the_card_draws_it_under_its_chart_and_the_redraw_holds_off():
    card, hist = _fn("pricedProfileHTML", APP), _fn("historyProfileHTML", APP)
    assert '<div class="profile-spark" data-player="${escapeAttr(r.player || "")}" data-mkt="${escapeAttr(r.market_label || "")}">' in card
    assert "line: r.line, side: r.side, fit: true" in card, "app.js draws the book's line, as it always did"
    assert 'data-mkt="${escapeAttr(label)}" data-history="1">' in hist and "line:" not in hist.split("gamelogBars")[1].split("})")[0]
    # Only this player's slider holds the redraw: a tap to another player inside the four seconds still opens him.
    assert ('if (Date.now() - (window._lineAdjBusy || 0) < 4000\n        && [...host.querySelectorAll(".line-adj")]'
            '.some((b) => b.dataset.player === own)) return;') in APP
    assert 'if (typeof lineAdjFill === "function") lineAdjFill(fresh);' in APP, "a chip switch gets its slider back"
    rest = APP.replace("window._lineAdjBusy", "").replace("lineAdjFill", "").replace("js/playerpage.js lineAdjSet", "")
    assert "lineAdj" not in rest, "nothing else on the boot path"
    markets = _fn("plrMarkets")
    assert "tonight.replaceChildren(kept);\n  lineAdjFill(tonight);" in markets
    fill = _fn("lineAdjFill")
    assert 'spark.insertAdjacentHTML("afterend", html);' in fill and "lineAdjDraw(spark.nextElementSibling" in fill
    bars = _fn("lineAdjBars")
    assert "nflWeekWord(l.week, r.sport || state.sport)" in bars and "nflWeekWord(l.week, r.sport) :" in bars
    assert "teamPrimaryIn(r.sport, r.team) : teamPrimary(r.team)" in bars, "each card's own colour, as app.js drew it"
    for sel in (".line-adj {", ".la-range {", ".la-step {", ".la-sd.on {", ".la-reset[hidden] {", ".la-price {"):
        assert sel in CSS, sel
    assert "accent-color: var(--warn)" in CSS, "the thumb is the dashed rule's colour"
    styles = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".line-adj" not in styles and ".la-" not in styles, "the slider's styles load with its page"


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


def _ladder():
    """What /api/lines/ladder answers for the card (engine/sliplive.ladder_prices' shape)."""
    def side(books, fair):
        return {"books": [{"book": b, "odds": o} for b, o in books], "n": len(books), "fair": fair,
                "best": books[0][1], "book": books[0][0]}
    return {"player": "Chuba Hubbard", "market": "rec", "line": 2.5, "side": "under", "lines": [
        {"line": 0.5, "over": side([("DraftKings", -1200)], 0.94)},
        {"line": 2.5, "over": side([("FanDuel", 105), ("DraftKings", 100)], 0.47),
         "under": side([("DraftKings", -125)], 0.53)},
        {"line": 3.5, "under": side([("FanDuel", -250), ("BetMGM", -270), ("Caesars", -275), ("DraftKings", -280)], 0.70)}]}


def test_the_books_prices_at_every_number_are_the_parlay_checkers_reading():
    from engine import sliplive as SL
    row = {"player": "Chuba Hubbard", "market": "rec", "line": 2.5, "side": "under",
           "all_lines": [{"book": "DraftKings", "line": 2.5, "over_odds": 100, "under_odds": -125},
                         {"book": "FanDuel", "line": 2.5, "over_odds": 105, "under_odds": -135},
                         {"book": "Pinnacle", "line": 2.5, "over_odds": 110, "under_odds": -130}],
           "alt_lines": [{"book": "FanDuel", "line": 3.5, "under_odds": -250},
                         {"book": "DraftKings", "line": 3.5, "over_odds": 230, "under_odds": -280},
                         {"book": "DraftKings", "line": 0.5, "over_odds": -1200}]}
    board = {"recommendations": [row], "odds_status": {"priced_at": 1764036000}}
    index = SL.quote_index(board)
    got = SL.ladder_prices(index, board, "Chuba Hubbard", "rec", 0.5, 5.5)
    assert got["line"] == 2.5 and got["side"] == "under" and got["as_of"], got
    by = {x["line"]: x for x in got["lines"]}
    assert sorted(by) == [0.5, 2.5, 3.5], "a number no book prices is left out"
    assert [b["book"] for b in by[2.5]["over"]["books"]] == ["FanDuel", "DraftKings"], "best first, the sharp book never"
    assert by[2.5]["under"]["best"] == -125 and by[2.5]["under"]["book"] == "DraftKings"
    assert 0.5 < by[2.5]["under"]["fair"] < 0.6, "the margin out, the sharp book's pair among the books'"
    assert by[3.5]["under"]["book"] == "FanDuel" and by[3.5]["under"]["n"] == 2 and "over" in by[3.5]
    assert "under" not in by[0.5] and by[0.5]["over"]["fair"] is None, "one side hung: no margin to take out"
    assert SL.ladder_prices(index, board, "Chuba Hubbard", "rec", 0.5, 0.5 + SL.LADDER_MAX) is None
    assert SL.ladder_prices(index, board, "Chuba Hubbard", "rec", 3.5, 2.5) is None
    assert SL.ladder_prices(index, board, "Chuba Hubbard", "rec", -1.5, 2.5) is None
    assert SL.ladder_prices(index, board, "Somebody Else", "rec", 0.5, 5.5) is None
    assert SL.ladder_prices(index, board, "Chuba Hubbard", "spread", 0.5, 5.5) is None


def test_the_endpoint_reads_the_private_board_for_a_member():
    import server
    from engine import askbot as AB
    from engine import gate as GATE_
    row = {"player": "Chuba Hubbard", "market": "rec", "line": 2.5, "side": "under",
           "all_lines": [{"book": "DraftKings", "line": 2.5, "over_odds": 100, "under_odds": -125}],
           "alt_lines": [{"book": "FanDuel", "line": 3.5, "under_odds": -250}]}
    boards = Path(tempfile.mkdtemp())
    (boards / "recommendations.json").write_text(json.dumps({"sport": "nfl", "recommendations": [row]}))

    class _Conn:
        def close(self):
            pass

    def handler(entitled=True, who=None):
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._account = lambda conn: who if who is not None else {"id": 7}
        h._entitled = lambda conn, w: entitled
        return h, sent
    saved = (server._acct, GATE_.full_board_file)
    server._acct = lambda: type("A", (), {"connect": staticmethod(lambda: _Conn())})()
    GATE_.full_board_file = lambda name: (boards / name) if name == AB.BOARD_FILES["nfl"] else None
    try:
        q = {"sport": ["nfl"], "player": ["Chuba Hubbard"], "market": ["rec"], "lo": ["0.5"], "hi": ["5.5"]}
        h, sent = handler()
        h._lines_ladder(q)
        code, out = sent[-1]
        assert code == 200 and [x["line"] for x in out["lines"]] == [2.5, 3.5], (code, out)
        assert out["lines"][1]["under"]["book"] == "FanDuel" and out["lines"][1]["under"]["best"] == -250
        h._lines_ladder(dict(q, player=["Nobody Here"]))
        assert sent[-1] == (200, {"player": "Nobody Here", "market": "rec", "lines": [], "none": True}), sent[-1]
        h._lines_ladder(dict(q, lo=["x"]))
        assert sent[-1][0] == 400
        h._lines_ladder(dict(q, sport=["xfl"]))
        assert sent[-1][0] == 400
        out_of, sent2 = handler(entitled=False, who={})
        out_of._lines_ladder(q)
        assert sent2[-1][0] == 401 and sent2[-1][1]["locked"] is True
        lapsed, sent3 = handler(entitled=False, who={"id": 9})
        lapsed._lines_ladder(q)
        assert sent3[-1][0] == 402
    finally:
        server._acct, GATE_.full_board_file = saved


def test_the_prices_ask_for_a_membership_before_a_board_is_read():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/lines/ladder"' in srv
    i = srv.index("def _lines_ladder(")
    body = srv[i:srv.index("\n    def ", i + 10)]
    assert "if not self._entitled(aconn, who):" in body and "401 if not who else 402" in body
    assert body.index("_entitled") < body.index("AB.board_at("), "who is asking, before anything is read"
    assert "SL.ladder_prices(" in body and "AB.prices_at(path)" in body
    fn = PP[PP.index("function lineAdjPriceHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "with the margin out" in fn and "No book has a price at exactly" in fn and "#paywall" in fn
    assert "_prob" not in fn and "our chance" not in fn.lower(), "nothing of ours at another number"


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
                asked = []

                def ladder(route):
                    asked.append(route.request.url)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(_ladder()))
                page.route("**/api/lines/ladder*", ladder)
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
                          price: c.querySelector('.la-price').hidden ? null : c.querySelector('.la-price').innerText,
                          wide: document.documentElement.scrollWidth - innerWidth }; }""")
                got["start"] = read()
                page.locator(".plr .profile .la-step[data-d='1']").click()
                page.wait_for_function("() => !document.querySelector('.plr .profile .la-price').hidden", timeout=10000)
                got["plus"] = read()
                page.locator(".plr .profile .la-sd[data-side='OVER']").click()
                got["over"] = read()
                page.locator(".plr .profile .la-range").fill("0.5")
                got["slid"] = read()
                # A redraw (the board's minute) draws the card where the reader left it.
                page.evaluate("window._lineAdjBusy = 0; renderPlayers()")
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
                got["hist_price"] = page.evaluate("() => document.querySelectorAll('.plr .profile .la-price').length")
                got["asked"] = list(asked)
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
    # The books' prices at the moved number, in the parlay checker's words; none at the book's own number.
    assert s["price"] is None and rs["price"] is None, (s["price"], rs["price"])
    assert p["price"] == "Now FanDuel \u2212250 · BetMGM \u2212270 · Caesars \u2212275 · 4 books · 70% with the margin out", p["price"]
    assert o["price"] == "No book has a price at exactly over 3.5.", o["price"]
    assert sl["price"] == "Now DraftKings \u22121200 · 94% with the margin out", sl["price"]
    assert rd["price"] == sl["price"], ("said again after a redraw", rd["price"])
    assert len(got["asked"]) == 1, ("asked once for the card", got["asked"])
    assert "sport=nfl" in got["asked"][0] and "player=Chuba%20Hubbard" in got["asked"][0] \
        and "market=rec" in got["asked"][0] and "lo=0.5" in got["asked"][0] and "hi=5.5" in got["asked"][0], got["asked"]
    assert got["hist_price"] == 0, "a market with no book line asks no book"
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
