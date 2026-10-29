"""The free side opens the pages that sell the plan, and Alerts (Ethan,
2026-10-28, asked whether About, Methodology, Status, Why Us, Features, the
Lab and Alerts should open for free accounts: "whatever you think makes the
most sense with that").

  * Why Us, About, Features and Methodology are the case for paying, and
    Status says whether the boards are current. None shows a pick, price or
    bet, and none reads a paid file: they open for everybody without a plan.
  * Alerts opens too: a free account's own switches (kickoff, big moments,
    final scores) and its watches live there, and the server hands it no
    pick on that page. What is a member's there says so, once.
  * The Lab stays a member's: it reads the paid backtest, so for a free
    account it would be an empty page.

Run directly: `python3 tests/test_the_free_side_opens_its_reference_pages.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
OPENED = ("why", "about", "features", "methodology", "status", "alerts")


def _list(name: str) -> set:
    i = APP.index(f"const {name} = ")
    block = re.sub(r"//[^\n]*", "", APP[i:i + 8000])          # its comments hold semicolons and brackets
    return set(re.findall(r'"([a-z]+)"', block[:block.index("]")]))


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


def test_the_six_open_and_the_lab_does_not():
    open_ = _list("WALL_OPEN")
    assert set(OPENED) <= open_, set(OPENED) - open_
    assert "lab" not in open_, "the Lab reads the paid backtest"
    assert set(OPENED) - {"alerts"} <= _list("QUIET_FOOTER_VIEWS") and "QUIET_FOOTER_VIEWS = new Set(" in APP, \
        "the reference pages show no pick, price or bet"


def test_what_each_page_reads_is_free():
    from engine import gate
    assert "record.json" in gate.FREE_FILES and "heartbeat.json" in gate.FREE_FILES
    assert 'boardFetch("data/record.json"' in _fn(APP, "renderWhy")
    # The Methodology page moved to more.js on 2026-10-29 (the first visit's
    # budget); it reads the same free record from there.
    assert "const rec = await loadRecordOnce();" in _fn(MORE, "renderMethodology")
    status = MORE[MORE.index("async function renderStatus("):]
    assert 'boardFetch("data/heartbeat.json"' in status[:status.index("\n}\n")]
    for name in ("renderAbout", "renderFeatures"):
        body = MORE[MORE.index(f"function {name}("):]
        body = body[:body.index("\n}\n")]
        assert "paidFetch(" not in body and "fetch(" not in body.replace("boardFetch(", ""), name
    lab = MORE[MORE.index("async function renderLab("):]
    assert 'paidFetch("backtest.json")' in lab[:lab.index("\n}\n")], "why the Lab stays a member's"


def test_alerts_gives_a_free_account_its_own_and_no_pick():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    feed = srv[srv.index("def _alerts_feed("):]
    feed = feed[:feed.index("\n    def ")]
    assert "if not (self._entitled(conn, who) if paid is None else paid):\n                return []" in feed
    watch = _fn(APP, "renderWatchZone")
    assert "const free = isWalled();" in watch
    assert '${free ? "" : `<option value="edge">Edge at least</option>`}' in watch, "an edge size is a member's"
    assert "the site cannot reach your lock screen" not in APP, "it can: the switches above"
    assert '${isWalled() ? "player or a team" : "player, a team, or an edge size"}' in _fn(APP, "watchChipsHTML")
    alerts = _fn(MORE, "renderAlerts")              # the Alerts page loads on first use
    assert 'isWalled() ? sections.join("") + memberLockHTML("Line moves and the desk are for members",' in alerts
    rows = ACCOUNT[ACCOUNT.index("const FL_ROWS = ["):ACCOUNT.index("];", ACCOUNT.index("const FL_ROWS = ["))]
    assert '["Alerts for your teams: kickoff, big moments, final scores", 1],' in rows
    assert '["Game reports, matchups, line moves and pick alerts", 0],' in rows


# --- in a browser ----------------------------------------------------------------
def _visit(entitled: bool, views) -> dict:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": entitled, "plans": []}
    me = {"watches": [], "kinds": ["player", "team", "edge", "price"], "max": 25, "edge_range": [1, 30],
          "fired": [], "unseen": 0, "newest": "", "feed_n": 0}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    got, errs = {}, []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                for view in views:
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                              is_mobile=True, has_touch=True)
                    page = ctx.new_page()
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/api/**", ful("{}"))
                    page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                    page.route("**/api/account/me*", ful(json.dumps(who)))
                    page.route("**/api/billing/status*", ful(json.dumps(bill)))
                    page.route("**/api/alerts/me*", ful(json.dumps(me)))
                    page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                    page.goto(f"http://127.0.0.1:{port}/index.html#{view}", wait_until="load")
                    page.wait_for_timeout(3000)
                    got[view] = page.evaluate("""() => ({ hash: location.hash,
                      edge: !!document.querySelector('#al-kind option[value="edge"]'),
                      lock: !!document.querySelector('#alerts-body .member-lock'),
                      locked: [...document.querySelectorAll('.sport-btn[data-kind="tool"].nav-locked')].map((b) => b.dataset.sport) })""")
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return {"views": got, "errs": errs}


def test_in_a_browser_a_free_account_opens_them_and_the_lab_asks_for_a_plan():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    free = _visit(False, OPENED + ("lab",))
    assert not free["errs"], free["errs"]
    for v in OPENED:
        assert free["views"][v]["hash"] == f"#{v}", (v, free["views"][v])
    assert free["views"]["lab"]["hash"] == "#paywall", free["views"]["lab"]
    a = free["views"]["alerts"]
    assert not a["edge"] and a["lock"], a
    locked = set(a["locked"])
    assert "lab" in locked and not locked & set(OPENED), locked
    member = _visit(True, ("alerts",))
    m = member["views"]["alerts"]
    assert m["edge"] and not m["lock"] and not m["locked"], m


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
