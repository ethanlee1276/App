"""The store app: the same site, minus what a store reviewer refuses.

Ethan, 2026-10-24: "do both from my call ... we just need it to work with
the app store". The call was the Play build without the sportsbook bet-slip
links, the website keeping them (docs/APP_STORES.md). The read since adds
Apple: 5.3.4 refuses apps that facilitate betting without a licence, and
5.2.1 and 4.1 refuse league logos and player photos used without
permission. So in both store builds (web/js/boot.js QB_STORE_APP):

  - no Bet it and no Tail it sheet: no sportsbook link at all;
  - no league logo and no player photo: the drawn helmet, cap, ball and
    team-colour mark under each one is the art, and anything from another
    host that lands anyway is taken out before it paints;
  - no meme-coin radar and no prediction markets (real-money venues);
  - the Play build sells nothing until the US external-links enrolment is
    on (QB_STORE_CHECKOUT): its paywall is a sign-in page with no price.

The app is told apart by its start address (?app=play), Chrome's
android-app:// referrer, or the iOS shell's user agent; Android's app shares
Chrome's storage, so a remembered "play" counts only in an app window. The
website keeps everything.

Run directly: `python3 tests/test_the_store_app.py` (the browser half with
QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
BOOT, APP, VIS, SOC = READ("web", "js", "boot.js"), app_js(), READ("web", "js", "visuals.js"), READ("web", "js", "social.js")
PHOTO_HOSTS = ("espncdn.com", "cdn.nba.com", "nhle.com", "mlbstatic.com", "static.www.nfl.com")


def _detect(search="", referrer="", ua="Mozilla/5.0", stored=None, standalone=False):
    """Run boot.js in node against a pretend page; (QB_STORE_APP, classes, stored)."""
    js = """
const store = new Map(%(stored)s);
const cls = new Set();
global.location = { search: %(search)s, href: "https://qellysbook.com/" + %(search)s, origin: "https://qellysbook.com" };
global.document = { referrer: %(referrer)s, documentElement: { classList: { add: (...c) => c.forEach((x) => cls.add(x)) } } };
Object.defineProperty(globalThis, "navigator", { value: { userAgent: %(ua)s }, configurable: true });  // node has its own
global.localStorage = { getItem: (k) => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
global.matchMedia = () => ({ matches: %(standalone)s });
global.window = global;
eval(require("fs").readFileSync(%(path)s, "utf8") + "\\n;global.__got = QB_STORE_APP;");
console.log(JSON.stringify([global.__got, [...cls].filter((c) => c.startsWith("store")).sort(), store.get("qb-store-app") || null]));
""" % {"stored": json.dumps([["qb-store-app", stored]] if stored else []), "search": json.dumps(search),
       "referrer": json.dumps(referrer), "ua": json.dumps(ua), "standalone": "true" if standalone else "false",
       "path": json.dumps(os.path.join(ROOT, "web", "js", "boot.js"))}
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_app_is_told_apart_from_the_website():
    assert _detect("?sport=nfl&app=play", standalone=True) == ["play", ["store-app", "store-nobuy", "store-play"], "play"]
    assert _detect(referrer="android-app://com.qellysbook.app/", standalone=True)[0] == "play"
    assert _detect(ua="Mozilla/5.0 (iPhone) AppleWebKit Mobile QellysApp/1.0 (ios)") == ["ios", ["store-app", "store-ios"], "ios"]
    assert _detect() == ["", [], None], "the website is the website"
    # The Play app shares Chrome's storage: a remembered "play" in a Chrome tab is the website.
    assert _detect(stored="play", standalone=False)[0] == ""
    assert _detect(stored="play", standalone=True)[0] == "play"
    # The iOS shell keeps its own storage, so a remembered "ios" holds.
    assert _detect(stored="ios")[0] == "ios"
    assert _detect("?app=web", stored="play", standalone=True) == ["", [], None], "?app=web forgets it"
    assert _detect("?app=evil", standalone=True)[0] == ""


def test_the_store_app_opens_no_sportsbook():
    at = APP.index("function betItHTML(r, cls) {")
    assert 'if (!r || storeApp()) return "";' in APP[at:at + 200]
    at = SOC.index('if (act === "tail") {')
    body = SOC[at:SOC.index("return;\n    }", SOC.index("betSheetShow(", at))]
    assert body.index("storeApp()") < body.index("betSheetShow("), "the tail is counted, no book opens"


def test_the_store_app_draws_no_league_logo_and_no_photo():
    assert 'if (!key || !abbr || storeArt()) return "";' in VIS, "logoUrl"
    assert "if (storeArt()) opts = { ...opts, headshot: null };" in VIS, "playerAvatar"
    assert 'if (!url || storeArt()) return "";' in VIS, "facePreview"
    assert "const img = key && !storeArt()" in VIS, "leagueMark"
    assert "QB_STORE_APP" in READ("web", "js", "gamecast.js")
    net = BOOT[BOOT.index("The net under the art rule"):]
    assert "MutationObserver" in net and 'attributeFilter: ["src"]' in net and "origin !== location.origin" in net


def test_the_store_app_skips_the_money_pages_and_the_play_build_sells_nothing():
    assert 'const STORE_APP_SKIPS = new Set(["memes", "intel"]);' in APP
    at = APP.index("function switchView(name, push = false) {")
    # (A free account's Home is sent to the free pick first, one line above.)
    assert "STORE_APP_SKIPS.has(name)" in APP[at:at + 320]
    at = APP.index("function _switchViewNow(name, push, dir) {")
    assert 'name === "checkout" && !storeSells()' in APP[at:at + 300]
    assert "var QB_STORE_CHECKOUT = { ios: true, play: false };" in BOOT
    at = APP.index("function storePaywallHTML(rec, status) {")
    body = APP[at:APP.index("\nfunction paywallHTML(", at)]
    for word in ("coStart", "pw-buy", "PLANS", "$", "stripe", "Stripe", "price"):
        assert word not in body.replace("${", ""), word
    assert "if (!storeSells()) return storePaywallHTML(rec, status);" in APP
    twa = json.loads(READ("deploy", "twa", "twa-manifest.json"))
    assert "app=play" in twa["startUrl"]


def _board():
    rows = [{"player": f"Player Name {i}", "team": "CHI", "opponent": "NE", "market": "rec_yds",
             "market_label": "Receiving Yards", "side": "over", "line": 40.5 + i, "odds": -150,
             "book": "draftkings", "book_name": "DraftKings", "model_prob": 0.7 - i * 0.01, "hit_prob": 0.7,
             "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": "top", "bettable": True,
             "confidence": 7.0, "grade": "B", "projection": 50.0, "reasons": ["because"], "recommended": True,
             "headshot": f"https://a.espncdn.com/i/headshots/nfl/players/full/{4000 + i}.png",
             "bet_links": [["DraftKings", "https://sportsbook.draftkings.com/x", -150]]}
            for i in range(8)]
    return {"sport": "nfl", "date": "2099-W01", "recommendations": rows, "most_likely": rows,
            "likely_board": {"rows": rows, "tiers": {"top": 8}, "lanes": {"prop": 8}},
            "games": [{"home": "CHI", "away": "NE", "date": "2099-01-01", "kickoff": "13:00",
                       "spread": -3.5, "total": 44.5}], "player_stats": {}}


def test_in_a_browser_the_app_and_the_website_differ_exactly_so():
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
                for mode in ("web", "play"):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                              has_touch=True, service_workers="block")
                    page = ctx.new_page()
                    asked, errors = [], []
                    page.on("request", lambda r: asked.append(r.url))
                    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                        page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl&app={mode}#likely", wait_until="load")
                    page.wait_for_timeout(1500)
                    seen = {"betit": page.locator(".betit").count(),
                            "foreign_img": page.evaluate("""() => [...document.images].filter((i) => {
                                const s = i.getAttribute('src') || '';
                                return s && !/^(data:|blob:)/.test(s) && new URL(s, location.href).origin !== location.origin;
                              }).length"""),
                            "store": page.evaluate("document.documentElement.className")}
                    page.evaluate("location.hash = '#memes'")
                    page.wait_for_timeout(600)
                    seen["memes_view"] = page.evaluate("(document.querySelector('.view.active') || {}).id || ''")
                    seen["photo_asks"] = [u for u in asked if any(h in u for h in PHOTO_HOSTS)]
                    seen["errors"] = errors
                    got[mode] = seen
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    web, app = got["web"], got["play"]
    assert not web["errors"] and not app["errors"], (web["errors"], app["errors"])
    assert web["betit"] > 0 and web["photo_asks"], ("the website keeps its links and its art", web)
    assert "store-app" not in web["store"] and web["memes_view"] == "view-memes"
    assert app["betit"] == 0, app
    assert app["foreign_img"] == 0 and app["photo_asks"] == [], app["photo_asks"][:5]
    assert "store-app" in app["store"] and "store-nobuy" in app["store"]
    assert app["memes_view"] != "view-memes", app["memes_view"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
