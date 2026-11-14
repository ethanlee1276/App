"""The whole pick card opens its pick, not just the player's name (Ethan,
2026-10-28, a screenshot of the Picks page: "you should be able too click
on the whole card not just the players name").

What these hold:

  * the one [data-open] listener opens a Most Likely card's own pick from a
    tap anywhere on the card: the ring, the price, the checks, the empty
    space;
  * a control on the card keeps its own click: Bet it, Why?, Bigger lines
    and any link open what they open and never the pick as well;
  * the name still opens it, once; the card is not made a second tab stop
    (it carries no data-open of its own, so the keyboard net leaves it be);
  * it reads as a door: a pointer over it on a computer.

Run directly: `python3 tests/test_the_whole_pick_card_opens_its_pick.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def test_the_one_listener_opens_a_card_from_anywhere_but_its_controls():
    i = APP.index("/* EVERY [data-open] ROW OPENS, WHEREVER IT IS DRAWN — ONE LISTENER.")
    block = APP[i:APP.index("\n});\n", i) + 4]
    assert block.index("if (row) return openFrom(row.dataset.open);") < block.index('const card = e.target.closest'), \
        "a row opens first"
    assert 'const card = e.target.closest && e.target.closest(".ob-card");' in block
    assert 'e.target.closest("a, button, summary, details, input, select, label")' in block
    assert 'const door = card && !(ctl && card.contains(ctl)) && card.querySelector("[data-open]");' in block
    card = APP[APP.index("function obCardHTML("):]
    card = card[:card.index("\n}\n")]
    assert '<div class="ob-card tier-${escapeAttr(r.tier || "look")}${rank === 1 ? " is-first" : ""}">' in card, \
        "the card carries no door of its own: the keyboard reaches the pick by its name"
    rule = CSS[CSS.index(".ob-card { display: grid;"):]
    assert "cursor: pointer;" in rule[:rule.index("}")]


def _board():
    row = {"player": "Chuba Hubbard", "team": "CAR", "opponent": "GB", "market": "rec", "market_label": "Receptions",
           "side": "over", "line": 1.5, "odds": -225, "book": "DraftKings", "model_prob": 0.68, "hit_prob": 0.68,
           "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": "strong", "bettable": True,
           "confidence": 7.0, "grade": "B", "projection": 3.0, "reasons": ["because"], "recommended": True,
           "since": "2026-10-28T11:08:00Z", "game_date": "2099-01-01", "game": "CAR@GB",
           "checks": {"model": True, "matchup": None, "market": True, "record": True},
           "check_notes": {"model": "our number clears the bar"}, "scout_notes": ["a caution"],
           "bet_links": [["draftkings", "https://sportsbook.draftkings.com/x"]],
           "bigger_lines": [{"line": 2.5, "side": "over", "odds": 140, "prob": 0.45, "worth_at": 122, "book": "DraftKings"}]}
    return {"sport": "nfl", "date": "2099-W01", "recommendations": [row], "most_likely": [row],
            "likely_board": {"rows": [row], "tiers": {"strong": 1}, "lanes": {"prop": 1}},
            "board_shelves": [{"key": "likely", "title": "Most likely", "rows": [row]}],
            "games": [{"home": "GB", "away": "CAR", "date": "2099-01-01", "kickoff": "20:15"}], "player_stats": {}}


def test_in_a_browser_a_tap_anywhere_on_the_card_opens_it_and_its_controls_keep_theirs():
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
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#likely", wait_until="load")
                page.wait_for_selector("#view-likely .ob-card .ob-ring", timeout=20000)
                # Count the opens rather than follow them, so every tap starts on the card.
                page.evaluate("() => { window.__opened = []; window.openFrom = (x) => window.__opened.push(x); }")
                card = "#view-likely .ob-card"
                for name, sel in (("ring", f"{card} .ob-ring"), ("checks", f"{card} .ob-checks"),
                                  ("price", f"{card} .ob-odds > b"), ("name", f"{card} .ob-who b"),
                                  ("bet it", f"{card} .betit"), ("why", f"{card} .td-why > summary"),
                                  ("bigger lines", f"{card} .ob-bigger > summary")):
                    page.evaluate("() => { window.__opened = []; }")
                    loc = page.locator(sel).first
                    loc.scroll_into_view_if_needed()
                    loc.click()
                    page.wait_for_timeout(120)
                    got[name] = page.evaluate("window.__opened.slice()")
                    page.keyboard.press("Escape")
                    page.evaluate("() => document.querySelectorAll('#view-likely .ob-card details[open]').forEach((d) => d.open = false)")
                got["tabindex"] = page.evaluate(f"document.querySelector('{card}').getAttribute('tabindex')")
                got["cursor"] = page.evaluate(f"getComputedStyle(document.querySelector('{card}')).cursor")
                got["errs"] = errs
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    pick = got["name"]
    assert len(pick) == 1 and pick[0].startswith("likely:"), ("the name opens it, once", got)
    for where in ("ring", "checks", "price"):
        assert got[where] == pick, (f"a tap on the {where} opens the pick", got)
    for control in ("bet it", "why", "bigger lines"):
        assert got[control] == [], (f"{control} keeps its own click", got)
    assert got["tabindex"] is None, "no second tab stop"
    assert got["cursor"] == "pointer" and not got["errs"], got


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
