"""No player's face is stretched (Ethan, 2026-10-28, a pick page with the
headshot circled: "a lot of the headshots are distorted for all sports").

ESPN's faces (the NBA's, the WNBA's, college's, the UFC's, and the NFL's
whenever nflverse has none) are 1040x760, the older files 350x254: the same
shape, about 1.37 wide for 1 tall. The page asked ESPN's resizer for a
square, and the resizer stretches to the size asked rather than crop, so
every face it served was squeezed to 73% of its width, in every frame.

What these hold:

  * a face is asked for in its own shape, tall enough for its frame at 2x;
    the box's photo check (photocheck.py) asks the same as the page;
  * every frame a face is drawn in crops it (object-fit: cover) rather than
    stretching it;
  * in a browser, with a stand-in for ESPN's resizer that stretches exactly
    as ESPN's does: a round face in the photo is round on the page.

Run directly: `python3 tests/test_no_face_is_stretched.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

VIS = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
CSS_DIR = ROOT / "web" / "css"
FACE = "https://a.espncdn.com/i/headshots/nba/players/full/3907387.png"


def _preview_js():
    a = VIS.index("const ESPN_FACE_ASPECT = ")
    return VIS[a:VIS.index("\n}\n", VIS.index("function espnFacePreview(", a)) + 2]


def test_a_face_is_asked_for_in_its_own_shape_and_the_box_asks_the_same():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no node)")
        return
    sizes = [24, 40, 52, 56, 140, 160]
    prog = _preview_js() + f"\nconsole.log(JSON.stringify({json.dumps(sizes)}.map((px) => espnFacePreview({json.dumps(FACE)}, px))));"
    path = os.path.join(tempfile.mkdtemp(), "f.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    import photocheck as PC
    for px, url in zip(sizes, json.loads(out.stdout)):
        q = parse_qs(urlparse(url).query)
        w, h = int(q["w"][0]), int(q["h"][0])
        assert h == max(48, round(px * 2)), (px, url, "tall enough for its frame at 2x")
        assert abs(w / h - 1040 / 760) < 0.02, (px, url, "the photo's own shape, not a square")
        assert q["img"][0] == "/i/headshots/nba/players/full/3907387.png", url
        assert PC.face_preview(FACE, px) == url, (px, PC.face_preview(FACE, px), url)


def test_every_frame_a_face_is_drawn_in_crops_it():
    rules = {"styles.css": (".avatar-photo {", ".ptile img {", ".inj-face {"),
             "detail.css": (".pbp-face {",), "carrychart.css": (".cc-face img {",), "gamecast.css": (".gc-face img {",),
             "hoopscast.css": (".hc-face img {",), "rinkcast.css": (".rc-face img {",)}
    for name, sels in rules.items():
        css = (CSS_DIR / name).read_text(encoding="utf-8")
        for sel in sels:
            i = css.index(sel)
            assert "object-fit: cover;" in css[i:css.index("}", i)], (name, sel, "a face is cropped, never stretched")


def _photo():
    """A stand-in for one of ESPN's faces: 1040x760, a round red face on
    transparent ground, centred where theirs are."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:                  # the browser test asks for Pillow first
        return None
    im = Image.new("RGBA", (1040, 760), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((370, 120, 670, 420), fill=(255, 0, 0, 255))
    return im


def _resizer(photo):
    """ESPN's combiner as it behaves: the size asked for, stretched to."""
    try:
        from PIL import Image
    except ImportError:                  # the browser test asks for Pillow first
        return None

    def handle(route):
        q = parse_qs(urlparse(route.request.url).query)
        w, h = int(q.get("w", ["1040"])[0]), int(q.get("h", ["760"])[0])
        # Only a face is the photo; a team's logo through the same resizer
        # is nothing, so it cannot land on the face being measured.
        art = photo if "/i/headshots/" in q.get("img", [""])[0] else Image.new("RGBA", photo.size, (0, 0, 0, 0))
        buf = io.BytesIO()
        art.resize((w, h)).save(buf, "PNG")
        route.fulfill(status=200, content_type="image/png", body=buf.getvalue())
    return handle


def _board():
    row = {"player": "Deni Avdija", "team": "POR", "opponent": "LAL", "market": "assists", "market_label": "Assists",
           "side": "over", "line": 5.5, "odds": -150, "book": "DraftKings", "model_prob": 0.66, "hit_prob": 0.66,
           "implied_prob": 0.6, "kind": "prop", "lane": "prop", "tier": "top", "bettable": True, "confidence": 7.0,
           "grade": "B", "projection": 6.8, "reasons": ["because"], "recommended": True, "headshot": FACE,
           "since": "2026-10-28T11:08:00Z", "game_date": "2099-01-01", "game": "POR@LAL",
           "checks": {"model": True, "matchup": True, "market": True, "record": None}}
    return {"sport": "nba", "generated_from": "live", "date": "2099-01-01", "recommendations": [row], "most_likely": [row],
            "likely_board": {"rows": [row], "tiers": {"top": 1}, "lanes": {"prop": 1}},
            "board_shelves": [{"key": "likely", "title": "Most likely", "rows": [row]}],
            "games": [{"home": "LAL", "away": "POR", "date": "2099-01-01", "kickoff": "22:00"}], "player_stats": {}}


def test_in_a_browser_a_round_face_stays_round():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError:
        print("      (skipped: no Playwright or no Pillow)")
        return
    import rendercheck
    body = json.dumps(_board())
    photo = _photo()
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                          has_touch=True, service_workers="block")
                page = ctx.new_page()
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                for pat in ("**/api/recommendations*", "**/api/*/recommendations*", "**/data/recommendations*.json*"):
                    page.route(pat, lambda r: r.fulfill(status=200, content_type="application/json", body=body))
                asked = []
                page.route("https://a.espncdn.com/combiner/i**", lambda r: (asked.append(r.request.url), _resizer(photo)(r)))
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nba#likely", wait_until="load")
                page.wait_for_function("() => [...document.querySelectorAll('#view-likely .ob-face .avatar-photo')]"
                                       ".some((i) => i.complete && i.naturalWidth)", timeout=20000)
                page.wait_for_timeout(300)
                face = page.locator("#view-likely .ob-face .avatar-stack").first
                face.scroll_into_view_if_needed()
                im = Image.open(io.BytesIO(face.screenshot())).convert("RGB")
                pix, (w, h) = im.load(), im.size
                red = [(x, y) for y in range(h) for x in range(w) if pix[x, y][0] > 180 and pix[x, y][1] < 90 and pix[x, y][2] < 90]
                xs, ys = [p[0] for p in red], [p[1] for p in red]
                got = {"asked": asked[:2], "box": (min(xs), min(ys), max(xs), max(ys)) if red else None}
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert got["asked"], "the page asked ESPN's resizer for nothing"
    assert got["box"], got
    x0, y0, x1, y1 = got["box"]
    ratio = (x1 - x0 + 1) / (y1 - y0 + 1)
    assert 0.93 <= ratio <= 1.07, (f"the round face is drawn {ratio:.2f} wide for 1 tall: stretched", got)


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
