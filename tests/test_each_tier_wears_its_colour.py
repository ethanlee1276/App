"""Each Most Likely tier wears its colour wherever it is named: Top picks
green, Strong gold, Worth a look sky (Ethan, 2026-10-28, a screenshot of the
Picks page by game with "Strong 5" circled: "with the strong and worth a
look we should colorize them so you kinda know what your looking at quicker
then having too guess what that pick falls under").

What these hold:

  * one colour per tier, set on the element that names the tier (--tier),
    and the ring's and the tier word's colours unchanged: the new places
    read the same colour the ring already wore;
  * the label over a tier's group in the By-game view wears its colour and
    a dot of it; the Best-of-the-slate section titles wear theirs; the tier
    chips wear theirs, and the lit one is tinted with it;
  * every pick card carries a light of its tier from its left edge (the
    night's best pick too, under its gold rim), and a card with no tier
    still has its ground;
  * in a browser, at an iPhone's width and in both themes, the label, the
    chip and the card's light are the colour the card's own tier word is.

Run directly: `python3 tests/test_each_tier_wears_its_colour.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
TIERS = {"top": "var(--good)", "strong": "var(--brand)", "look": "var(--sky)"}


def _rule(start: str) -> str:
    i = CSS.index(start)
    return CSS[i:CSS.index("}", i) + 1]


def test_one_colour_per_tier_the_ring_s_own():
    for tier, colour in TIERS.items():
        assert f".tier-{tier} {{\n  --tier: {colour}; }}" in CSS, tier
    # The ring and the tier word already wore these; the new places match them.
    assert ".ob-ring.tier-top .ob-ring-fg { stroke: var(--good); }" in CSS
    assert ".ob-ring.tier-strong .ob-ring-fg { stroke: var(--brand); }" in CSS
    assert ".ob-ring.tier-look .ob-ring-fg { stroke: var(--sky); }" in CSS


def test_the_labels_the_titles_and_the_chips_wear_it():
    assert "color: var(--tier, var(--text-mute));" in _rule(".mp-tier {")
    dot = _rule('.mp-tier[class*="tier-"]::before {')
    assert "border-radius: 50%;" in dot and "background: var(--tier);" in dot
    assert ".ob-tier .ob-sec-title { color: var(--tier); }" in CSS
    assert ".ob-tier-chip { color: var(--tier, var(--text)); }" in CSS
    lit = _rule(".ob-tier-chip.on {")
    assert "color: var(--tier, var(--brand));" in lit and "var(--tier, var(--brand)) 12%" in lit, lit
    secs = APP[APP.index("function obTierSections("):APP.index("function obByGameHTML(")]
    assert 'class="likely-shelf ob-tier tier-${t}"' in secs
    games = APP[APP.index("function obByGameHTML("):APP.index("function obPicked(")]
    assert '<div class="mp-tier tier-${t}">' in games


def test_every_card_carries_its_tier_s_light():
    card = _rule(".ob-card { display: grid;")
    assert "--grad-tier-light: linear-gradient(90deg, color-mix(in oklab, var(--tier, transparent) 11%, transparent)" in card
    assert "background: var(--grad-tier-light), var(--grad-ob-card);" in card, "a card with no tier keeps its ground"
    first = _rule(".ob-card.is-first::after {")
    assert "background: var(--grad-tier-light), var(--grad-ob-card);" in first, "the best pick's ground covers the card's"


def _board():
    def row(player, market, label, line, tier, prob):
        return {"player": player, "team": "CAR", "opponent": "GB", "market": market, "market_label": label,
                "side": "over", "line": line, "odds": -150, "book": "DraftKings", "model_prob": prob,
                "hit_prob": prob, "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": tier,
                "bettable": True, "confidence": 7.0, "grade": "B", "projection": line + 2, "reasons": ["because"],
                "recommended": True, "since": "2026-10-28T11:08:00Z", "game_date": "2099-01-01", "game": "CAR@GB",
                "checks": {"model": True, "matchup": tier == "top", "market": True, "record": None}}
    rows = [row("Josh Jacobs", "rush_yds", "Rushing Yards", 64.5, "top", 0.66),
            row("Chuba Hubbard", "rec", "Receptions", 1.5, "strong", 0.68),
            row("Jordan Love", "pass_cmp", "Completions", 19.5, "look", 0.61)]
    return {"sport": "nfl", "date": "2099-W01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 1, "strong": 1, "look": 1}, "lanes": {"prop": 3}},
            "board_shelves": [{"key": "likely", "title": "Most likely", "rows": rows}],
            "games": [{"home": "GB", "away": "CAR", "date": "2099-01-01", "kickoff": "20:15"}], "player_stats": {}}


def test_in_a_browser_the_label_the_chip_and_the_card_match_the_tier_word():
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
                for theme in ("dark", "light"):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              service_workers="block", color_scheme=theme)
                    page = ctx.new_page()
                    page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                         f" localStorage.setItem('qb.tour', 'done'); localStorage.setItem('ge-theme', '{theme}'); }} catch (e) {{}}")
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#likely", wait_until="load")
                    page.wait_for_selector('[data-ob-view="game"]', timeout=20000)
                    page.locator('[data-ob-view="game"]').first.click()
                    page.wait_for_selector(".mp-tier.tier-look", timeout=10000)
                    got[theme] = page.evaluate("""() => Object.fromEntries(['top', 'strong', 'look'].map((t) => {
                      const c = (q) => { const e = document.querySelector(q); return e && getComputedStyle(e).color; };
                      const card = document.querySelector(`.ob-card.tier-${t}`);
                      const word = c(`.ob-tierword.tier-${t}`);
                      const [r, g, b] = (word.match(/\\d+/g) || []).map(Number);
                      return [t, { word, label: c(`.mp-tier.tier-${t}`), chip: c(`.ob-tier-chip.tier-${t}`),
                                   dot: getComputedStyle(document.querySelector(`.mp-tier.tier-${t}`), '::before').backgroundColor,
                                   light: getComputedStyle(card).backgroundImage, rgb: [r, g, b] }];
                    }))""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    for theme, tiers in got.items():
        words = {t: v["word"] for t, v in tiers.items()}
        assert len(set(words.values())) == 3, ("three tiers, three colours", theme, words)
        for t, v in tiers.items():
            assert v["label"] == v["word"] == v["chip"] == v["dot"], (theme, t, v)
            assert v["light"].count("linear-gradient") == 2, ("the tier's light over the card's ground", theme, t, v["light"])
        lights = {v["light"] for v in tiers.values()}
        assert len(lights) == 3, ("each tier's card lit in its own colour", theme)


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_by_game_labels_name_their_tiers():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    rows = [{"player": p, "tier": t, "model_prob": .6, "game": "CAR@GB"} for p, t in
            (("A", "look"), ("B", "top"), ("C", "strong"), ("D", "strong"))]
    prog = ("const escapeHtml = (s) => String(s); const escapeAttr = escapeHtml;\n"
            "const teamName = (t) => t; const whenLabel = () => ''; const gameId = () => 'g';\n"
            "const obCardHTML = (r) => `[${r.player}]`;\n"
            "const state = {data: {games: [{away: 'CAR', home: 'GB'}]}};\n"
            + APP[APP.index("const OB_TIERS = ["):APP.index("];", APP.index("const OB_TIERS = [")) + 2] + "\n"
            + _fn("obSorted") + _fn("obByGameHTML")
            + f"\nconsole.log(obByGameHTML({json.dumps(rows)}));")
    path = os.path.join(tempfile.mkdtemp(), "g.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert re.findall(r'class="mp-tier tier-([a-z]+)">([^<]*)<', out.stdout) == [
        ("top", "Top picks "), ("strong", "Strong "), ("look", "Worth a look ")], out.stdout


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
