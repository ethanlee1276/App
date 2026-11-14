"""Eight leagues, one row on a phone (web/css/styles.css, the last block).

Ethan, 2026-11-14, the folded iPhone Duo's league strip circled: "fit this
better". College basketball made the leagues eight, and at 48px a button
the eighth (UFC) wrapped onto a line of its own on every phone — the same
"one alone on a second row" he circled on 2026-09-22 with six. On a phone
the eight share the row in equal eighths now, the crest never wider than
its eighth; the strip still wraps rather than scrolls on anything narrower
than a 320 phone (tests/test_league_strip).

    python3 tests/test_eight_leagues_one_row.py
    QB_BROWSER_TESTS=1 python3 tests/test_eight_leagues_one_row.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CSS = (ROOT / "web" / "css" / "styles.css").read_text()
HTML = (ROOT / "web" / "index.html").read_text()

#: Phone sizes: the folded Duo, iPhones from the SE to the Pro Max, a 360
#: Android, and the 320 phone that is the floor.
SIZES = ((382, 580), (390, 844), (375, 667), (430, 932), (360, 780), (320, 568))


def test_there_are_eight_leagues_on_the_strip():
    leagues = re.findall(r'class="sport-btn[^"]*"[^>]*data-kind="league"|data-kind="league"[^>]*class="sport-btn',
                         HTML)
    assert len(leagues) == 8, len(leagues)


def test_the_phone_rule_shares_the_row_in_eighths():
    assert ".sportbar-in .sport-btn { flex: 1 1 0; min-width: 36px; }" in CSS
    assert ".sportbar-in .sport-btn { padding: 0 1px; }" in CSS
    assert ".sportbar-in .sport-btn .crest { width: min(44px, 100%); aspect-ratio: 1;" in CSS
    # The short screens keep their smaller crest, which fits a 320 phone's
    # 38px eighth (the Duo folded, 2026-10-29).
    assert ".sportbar-in .sport-btn .crest { width: 34px; height: 34px; }" in CSS


def _measure():
    from playwright.sync_api import sync_playwright
    import rendercheck
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for w, h in SIZES:
                    ctx = browser.new_context(viewport={"width": w, "height": h}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');"
                                         "localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html?sport=cbb", wait_until="load")
                    page.wait_for_timeout(1200)
                    got[(w, h)] = page.evaluate("""() => {
                      const bs = [...document.querySelectorAll('.sportbar-in .sport-btn[data-kind="league"]')]
                        .filter((b) => b.offsetParent);
                      const box = (el) => el.getBoundingClientRect();
                      return {n: bs.length, rows: new Set(bs.map((b) => Math.round(box(b).top))).size,
                              w: bs.map((b) => box(b).width), h: bs.map((b) => box(b).height),
                              crest: bs.map((b) => { const c = b.querySelector('.crest'); return c ? box(c).width : 0; }),
                              clipped: bs.filter((b) => b.scrollWidth > b.clientWidth + 1).map((b) => b.dataset.sport),
                              wide: document.documentElement.scrollWidth > innerWidth + 1};
                    }""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, errs


def test_in_a_browser_every_phone_holds_the_eight_on_one_row():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("skip: set QB_BROWSER_TESTS=1")
        return
    got, errs = _measure()
    assert not errs, errs
    for (w, h), g in got.items():
        assert g["n"] == 8, (w, h, g)
        assert g["rows"] == 1, f"{w}x{h}: the leagues wrap to {g['rows']} rows"
        assert not g["clipped"] and not g["wide"], (w, h, g)
        assert min(g["w"]) >= 36, (w, h, g["w"])
        assert max(g["crest"]) <= min(g["w"]), (w, h, g)
        assert min(g["h"]) >= 44, f"{w}x{h}: a league button under the 44px tap size"
        if w >= 375:
            assert min(g["w"]) >= 44, f"{w}x{h}: a league button narrower than the 44px tap size"


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
