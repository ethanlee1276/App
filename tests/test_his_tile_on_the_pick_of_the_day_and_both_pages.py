"""His tile: the chart card's photo on the Pick of the Day, the pick page and
the player page.

Ethan, 2026-10-15, on the three places offered for a player's photo after
every chart got his card: "yes build all three". Pinned here:

  * ONE TILE (app.js `playerTileHTML`): his cut-out headshot on his club's
    colour with its mark faint behind him, asked for at the size the place
    draws it and then whole (visuals.js swapFull), his initials until it
    paints and for good when it never does;
  * THE PICK OF THE DAY wears him when its pick is a player's and his photo
    is on file — top right over the stadium on a wide screen, beside the
    heading and the call on a phone — and the small face beside the bet
    goes; a side, a total or a pick with no photo keeps the art alone;
  * THE PICK PAGE draws him at the head of the card (`betMark(r, 56, 76)`),
    and THE PLAYER PAGE at the head of his profile (`playerTileHTML(r, 72)`);
  * THE STYLES are the site's tokens, colours and motion alike;
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): the real page on a test
    board at 390 and 1280 draws the three tiles with his photo, his initials
    when the photo is missing, no page error and no sideways scroll.

Run directly: `python3 tests/test_his_tile_on_the_pick_of_the_day_and_both_pages.py`
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = app_js()
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d4944415478da63f8cfc0f01f0005000201a6a9b2fd"
                    "0000000049454e44ae426082")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const state = { sport: "nfl" };
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const escapeAttr = escapeHtml;
      const facePreview = (u, px) => (u.includes("cdn.nba") ? u : `${u}?w=${px * 2}`);
      const initials = (n) => n.split(/\\s+/).map((w) => w[0]).join("").toUpperCase();
      const teamPrimaryIn = (lg, a) => (a === "LA" ? "#003594" : "var(--brand)");
      const teamMarkIn = (lg, a, n) => `<mk ${a} ${n}>`;
      const leagueMark = (lg, n) => `<league ${n}>`, teamMark = (a, n) => `<team ${a} ${n}>`;
      const playerAvatar = (p, t, o) => `<avatar ${o.size}>`;
      const TEAM_SIDE_MARKETS = new Set(["moneyline", "spread", "team_total"]);
    """
    prog = f"{stubs}\n{_fn('playerTileHTML')}\n{_fn('betMark')}\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


KYREN = {"player": "Kyren Williams", "team": "LA", "market": "rush_yds",
         "headshot": "https://static.www.nfl.com/image/upload/f_auto,q_auto/league/kyren"}


def test_the_tile_is_his_cut_out_on_his_colour_with_initials_under_it():
    got = _node(f"""
      const k = {json.dumps(KYREN)};
      return {{ tile: playerTileHTML(k, 76), none: playerTileHTML(Object.assign({{}}, k, {{ headshot: "" }}), 76),
               nba: playerTileHTML({{ player: "Jokic", team: "DEN", headshot: "https://cdn.nba.com/h/203999.png" }}, 72),
               solo: playerTileHTML({{ player: "Alex Pereira", team: "" }}, 72) }};""")
    if got is None:
        print("      (skipped: no node)")
        return
    t = got["tile"]
    assert t.startswith('<span class="ptile" aria-hidden="true" style="--pw:76px;--ta:#003594">'), t
    assert "<i><mk LA 61></i>" in t, "his club's mark behind him"
    assert "<b>KW</b>" in t, "his initials under the photo"
    assert f'src="{KYREN["headshot"]}?w=152"' in t and f'data-full="{KYREN["headshot"]}"' in t, "the tile's size, then whole"
    assert 'data-onload="art-on" data-onerr="swapFull"' in t
    assert "<img" not in got["none"] and "<b>KW</b>" in got["none"], "no photo on file: his initials"
    assert "data-full" not in got["nba"], "a photo with one size is asked for once"
    assert "<i>" not in got["solo"] and "--ta:var(--brand)" in got["solo"], "no club: no mark, the site's colour"


def test_a_prop_wears_his_tile_where_the_place_asks_and_a_side_its_mark():
    got = _node(f"""
      const k = {json.dumps(KYREN)};
      return [betMark(k, 56, 76), betMark(k, 30), betMark({{ market: "moneyline", team: "LA", player: "LA" }}, 56, 76),
              betMark({{ market: "total", player: "o47.5" }}, 56, 76)];""")
    if got is None:
        return
    assert got[0].startswith('<span class="ptile"'), "the pick page's head"
    assert got[1] == "<avatar 30>", "a row keeps its face"
    assert got[2] == "<team LA 56>" and got[3] == "<league 56>", "a side or a total keeps its mark"


def test_the_three_places_draw_it():
    pp = APP[APP.index("function renderPropPage("):]
    assert '<div class="card-id">${betMark(r, 56, 76)}' in pp[:pp.index("function ", 30)], "the pick page's head"
    assert "${playerTileHTML(r, 72)}" in _fn("_profileHead"), "the player page's head"
    potd = APP[APP.index("async function renderPickOfTheDay("):]
    potd = potd[:potd.index("\nfunction ", 10)]
    assert 'const tile = isTeam || !pick.headshot ? "" : playerTileHTML(pick, 140);' in potd
    assert '${tile ? "" : `<span class="pick-id">${betMark(pick, 30)}</span>`}' in potd, "one face on the card, not two"
    end = potd.index('<div id="potd-record"')
    assert "${tile}\n    </div>`;" in potd[end:end + 200], "last in the card; the styles place it"
    assert "headshot: pick.headshot," in _fn("potdHeroHTML"), "the deck's row shows his face too"


def test_the_styles_are_the_sites_tokens():
    i = CSS.index("/* HIS TILE (2026-10-15")
    block = CSS[i:CSS.index("/* Live now:", i)]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block), "tokens only"
    assert "transition: opacity var(--dur-slow) var(--ease-out);" in block, "the motion system's own fade"
    assert "box-shadow: var(--glow-soft);" in block
    for rule in ("position: relative; flex: none; width: var(--pw); aspect-ratio: 4 / 5;", "--grad-ptile: radial-gradient(",
                 "border: var(--hairline) solid", ".ptile.art-on img { opacity: 1; }", ".ptile.art-on b { visibility: hidden; }",
                 "font-size: 30cqi;",
                 ".potd-hero:has(> .ptile) > .ptile { position: absolute; top: 22px; right: 26px;",
                 "@media (max-width: 720px) {",
                 ".potd-hero:has(> .ptile) > .ptile { position: relative; top: auto; right: auto; grid-column: 2; grid-row: 1 / span 2;"):
        assert rule in block, rule


# --- the browser, opt-in --------------------------------------------------------------
def _board(face):
    now = datetime.datetime.now(datetime.timezone.utc)
    today, kick = now.date().isoformat(), (now + datetime.timedelta(hours=6)).isoformat()

    def row(player, team, opp, line, odds, url, prob):
        return {"player": player, "market": "rush_yds", "market_label": "Rushing Yards", "side": "OVER", "line": line,
                "odds": odds, "book": "DraftKings", "team": team, "opponent": opp, "headshot": url, "model_prob": prob,
                "hit_prob": prob, "implied_prob": 0.53, "commence_time": kick, "date": today, "position": "RB",
                "projection": line + 8, "grade": "B+", "confidence": 7.4, "reasons": ["Over this line in four of five."]}
    kyren = row("Kyren Williams", "LA", "BUF", 62.5, -112, face, 0.6)
    cook = row("James Cook", "BUF", "LA", 60.5, -180, "https://faces.test/cook.png", 0.66)
    potd = dict(kyren, fair_prob=0.55, evidence="sharp", price_implied=0.528, payout_units=0.893, ev_units=0.04,
                below_bar="")
    return {"sport": "nfl", "generated_at": now.isoformat(), "board_date": today, "date": today,
            "recommendations": [kyren, cook], "most_likely": [dict(kyren, tier="top"), dict(cook, tier="strong")],
            "pick_of_the_day": {"sport": "nfl", "date": today, "pick": potd, "band": [-125, 100],
                                "verdict": {"call": "bet", "say": "Bet it", "why": ""}},
            "games": [{"home": "LA", "away": "BUF", "date": today, "commence_time": kick}], "player_stats": {}}


def test_in_a_browser_the_three_tiles_draw_his_photo_or_his_initials():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    for face, lit in (("https://faces.test/kyren.png", True), ("https://faces.test/missing.png", False)):
                        body = json.dumps(_board(face))
                        ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                                  has_touch=width < 600, service_workers="block")
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        # Nothing leaves the machine: the page's fonts and logos are refused.
                        page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/")
                                   and "faces.test" not in url, lambda r: r.abort())
                        for pat in ("**/api/recommendations*", "**/data/recommendations*.json*"):
                            page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                        page.route("https://faces.test/**", lambda r: r.fulfill(status=200, content_type="image/png", body=PNG)
                                   if "missing" not in r.request.url else r.fulfill(status=404, body=""))
                        page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                        page.wait_for_selector("#potd-zone .potd-hero > .ptile", timeout=15000)
                        page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                        sel = ".ptile.art-on" if lit else ".ptile:not(.art-on)"
                        page.wait_for_selector(f"#potd-zone {sel}", timeout=5000)
                        assert not page.query_selector("#potd-zone .potd-hero .pick-id"), "one face on the card"
                        box = page.evaluate("(() => { const r = document.querySelector('#potd-zone .ptile').getBoundingClientRect();"
                                            " return [Math.round(r.width), Math.round(r.right)]; })()")
                        assert box[0] == (84 if width < 600 else 140) and box[1] <= width, box
                        if not lit:
                            assert page.evaluate("getComputedStyle(document.querySelector('#potd-zone .ptile b')).visibility") == "visible"
                        pid = page.evaluate("propId(state.data.recommendations[0])")
                        page.evaluate(f"location.hash = '#prop/{pid}'")
                        page.wait_for_selector(f"#prop-body .card-id {sel}", timeout=8000)
                        page.click("[data-player-page]")
                        page.wait_for_selector(f".profile-head {sel}", timeout=8000)
                        assert page.evaluate("document.scrollingElement.scrollWidth") <= width
                        assert not errors, errors
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
