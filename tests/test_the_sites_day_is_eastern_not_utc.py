"""The site's day is the Eastern date, not the UTC one.

The gate at 23:50 on Sunday 8 November: a member who had set a $100 weekly
limit and logged $110 in My Bets saw "This week: $0.00" and no warning. My
Bets dated a new bet with `new Date().toISOString()`, the UTC date, which
turns over at 7pm Eastern (8pm in summer). So the Sunday-evening bets were
filed under Monday and fell out of the Monday-to-Sunday Eastern week the
limit counts (web/js/app.js limitWeek, engine/limits.week_of). The same UTC
date skipped tonight's game on the fantasy desk after 7pm, took "Today" off
the record's day card and cut a day off the countdown to a slate. One helper
(`etToday`) now gives all of them the Eastern date.

Checks: the helper's date at each side of midnight Eastern, in winter and in
summer; every place that meant the site's day asks it; and in a browser with
the clock at Sunday 23:50 Eastern, the two bets are dated Sunday, count in
the week, and cross the limit with its one warning.

Run directly: `python3 tests/test_the_sites_day_is_eastern_not_utc.py`
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
APP = (ROOT / "web" / "js" / "app.js").read_text()
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text()
UTC_TODAY = "new Date().toISOString().slice(0, 10)"


def _fn(src, head):
    """One top-level function's text, to its closing brace (`}` or `};`)."""
    i = src.index(head)
    ends = [j for j in (src.find("\n}\n", i), src.find("\n};\n", i)) if j != -1]
    return src[i:min(ends) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_today_is_the_eastern_date_on_each_side_of_midnight():
    cases = {
        "2026-11-09T04:50:00Z": "2026-11-08",   # Sunday 23:50 EST: still Sunday
        "2026-11-09T05:10:00Z": "2026-11-09",   # 00:10 EST: Monday
        "2026-11-09T00:30:00Z": "2026-11-08",   # 19:30 EST: the hour UTC turns over
        "2026-07-05T03:30:00Z": "2026-07-04",   # 23:30 EDT in summer
        "2026-07-05T04:10:00Z": "2026-07-05",   # 00:10 EDT
        "2026-03-08T06:30:00Z": "2026-03-08",   # 01:30 EST, the night the clocks go forward
    }
    got = _node(_fn(APP, "function etToday(") + f"""
      const cases = {json.dumps(list(cases))};
      const out = {{}};
      for (const c of cases) out[c] = etToday(Date.parse(c));
      out.now = etToday();
      console.log(JSON.stringify(out));""")
    if got is None:
        print("      (skipped: node not installed)")
        return
    for at, day in cases.items():
        assert got[at] == day, (at, got[at], day)
    assert len(got["now"]) == 10 and got["now"][4] == "-", got["now"]


def test_every_place_that_meant_the_sites_day_asks_for_it():
    places = {
        "the bet My Bets logs": _fn(APP, "window.mbAdd = function"),
        "the bets an import brings without a date": _fn(APP, "function mbRowsFromText("),
        "the fantasy desk's next game": _fn(APP, "function _ffPlayerDay("),
        "the record's day card": _fn(APP, "async function renderHomePerf("),
        "the countdown to a slate": _fn(APP, "function renderSlateHorizon("),
        "the date My Bets' form starts on": _fn(ACCOUNT, "function renderMyBets("),
    }
    for what, body in places.items():
        assert "etToday()" in body, f"{what} asks for the site's day"
        assert UTC_TODAY not in body, f"{what} no longer takes the UTC date for today"
    week = _fn(APP, "function limitWeek(")
    assert '"America/New_York"' in week, "the week the bets are counted in is Eastern too"


def test_in_a_browser_a_sunday_night_bet_counts_in_its_week():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    sunday_night = datetime.datetime(2026, 11, 9, 4, 50, tzinfo=datetime.timezone.utc)
    got, errors = {}, []
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            ctx.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');"
                                " localStorage.setItem('qb.a2hs', 'off'); localStorage.setItem('qb.mine', 'no'); } catch (e) {}")
            page = ctx.new_page()
            page.clock.set_fixed_time(sunday_night)
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_timeout(1500)
            got["today"] = page.evaluate("etToday()")
            page.evaluate("window._acctTab = 'settings'; window._setOpen = 'limit'; switchView('account', true);")
            page.wait_for_selector(".set-limit", timeout=8000)
            page.fill(".set-limit", "100")
            page.click("[data-set-limit='save']")
            page.wait_for_timeout(300)
            page.evaluate("switchView('mybets', true)")
            page.wait_for_selector("#mb-stake", timeout=8000)
            got["form_date"] = page.evaluate("(document.getElementById('mb-date') || {}).value || ''")
            for stake, desc in (("60", "Lakers ML"), ("50", "Celtics -3.5")):
                page.fill("#mb-desc", desc)
                page.fill("#mb-stake", stake)
                page.fill("#mb-odds", "-110")
                page.click("[data-act='mbAdd']")
                page.wait_for_timeout(400)
                got.setdefault("toasts", []).append(page.evaluate(
                    "[...document.querySelectorAll('.tf-toast, .toast')].map((t) => t.textContent).join(' | ')"))
            got["dates"] = page.evaluate("mbLoad().map((b) => b.date)")
            got["strip_text"] = page.evaluate("(document.querySelector('.wk-limit') || {}).textContent || ''")
            ctx.close()
        finally:
            browser.close()
    assert got["today"] == "2026-11-08", got
    assert got["form_date"] == "2026-11-08", f"the form starts on Sunday, not UTC's Monday: {got}"
    assert got["dates"] == ["2026-11-08", "2026-11-08"], got
    assert "past the $100" in got["toasts"][1] and "past the" not in got["toasts"][0], got
    assert "$110" in got["strip_text"], got
    assert not errors, errors


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
