"""The Lab opens to free accounts, with its public summary only (app.js
WALL_OPEN, more.js labFreeHTML).

Ethan, 2026-11-05, on the list of pages a free account could not open —
About, Methodology, Status, Why Us, Features, the Lab and Alerts: "do all of
them". Six had opened on 2026-10-28; the Lab had stayed a member's because
it read the sealed backtest. What these hold:

  * the Lab is on the free list, and the sealed file stays sealed: the replay
    market by market (its simulated bets, grades and bins) is in
    backtest.json, paid whole (engine/gate PAID_FILES);
  * a reader without a plan gets the replay's public summary, read off the
    free record.json (`replay`, engine/lab.replay_summary: priced, Brier,
    skill, calibration error, basis), and the page's own lock where the rest
    would be, never a number from behind it;
  * the sign-up's table and the plans' line say so, and the Terms' §2 list of
    free features names it, with a dated note that the change only adds;
  * in a browser, a free account lands on the Lab (not the plans), sees each
    sport's summary row and the lock, and nothing from the sealed file.

Run directly: `python3 tests/test_the_lab_opens_to_free_accounts.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate                                          # noqa: E402
from engine import lab as LB                                     # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
TERMS = (ROOT / "web" / "terms.html").read_text(encoding="utf-8")
FLAT = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))  # noqa: E731


def _wall_open() -> set:
    i = APP.index("const WALL_OPEN = ")
    block = re.sub(r"//[^\n]*", "", APP[i:i + 9000])
    return set(re.findall(r'"([a-z]+)"', block[:block.index("]")]))


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


def test_the_lab_is_open_and_its_replay_stays_sealed():
    open_ = _wall_open()
    assert {"lab", "why", "about", "features", "methodology", "status", "alerts"} <= open_
    assert "backtest.json" in gate.PAID_FILES, "the replay market by market stays a member's"
    assert set(LB.SUMMARY_FIELDS) == {"n", "brier", "ece", "skill", "basis"}, \
        "the public summary is calibration numbers only"


def test_a_reader_without_a_plan_gets_the_summary_and_the_lock():
    lab = _fn(MORE, "renderLab")
    free = _fn(MORE, "labFreeHTML")
    who = _fn(MORE, "labWalled")
    assert lab.index("await labWalled()") < lab.index('paidFetch("backtest.json")'), \
        "a reader without a plan is never sent for the sealed file"
    # A link straight to #lab draws before the boot has put the wall up, so
    # the answer is the boot's status when there is one, else the server's.
    assert "isWalled()" in who and "_pwStatus" in who and "await paywallCheck()" in who
    assert "s.paywall && !s.entitled" in who
    assert 'boardFetch("data/record.json"' in free and ".replay" in free
    assert 'memberLockHTML("The replay, market by market, is for members"' in free
    # Nothing in it reads a field the sealed file carries (the lock's own
    # words may name them; the code may not touch them).
    touched = re.findall(r"\.(roi|n_bets|win_rate|bins|segments|markets)\b", free)
    assert not touched, touched


def test_the_plans_the_signup_and_the_terms_say_so():
    rows = ACCOUNT[ACCOUNT.index("const FL_ROWS = ["):ACCOUNT.index("];", ACCOUNT.index("const FL_ROWS = ["))]
    assert '["The Lab — how well each model forecast past games", 1],' in rows
    line = APP[APP.index("const FREE_VS_PLAN = "):APP.index("function freeVsPlanHTML(")]
    assert "the Lab’s " in line and "the Lab market by market" in line
    flat = FLAT(TERMS)
    assert "Last updated 5 November 2026" in TERMS
    note = flat[flat.index("When this version applies."):flat.index("1. Who we are")]
    assert "The change of 5 November 2026 adds the Lab’s summary to the same list" in note
    assert "it too takes nothing away and applies to every account from that day" in note
    sec = flat[flat.index("2. What the Service is"):flat.index("3. No advice")]
    assert ("the Lab’s summary of how well each model forecast past games it never saw (the replay "
            "market by market, with the bets it would have made and their grades, is part of the paid "
            "analysis)") in sec


# --- in a browser ------------------------------------------------------------------
REPLAY = {"nba": {"n": 18420, "brier": 0.2311, "ece": 0.0123, "skill": 0.0412, "basis": "book",
                  "markets": ["Points", "Rebounds"], "carried_from": None},
          "mlb": {"n": 9100, "brier": 0.2401, "ece": 0.02, "skill": -0.004, "basis": "naive",
                  "markets": ["Hits"], "carried_from": None},
          "generated_at": "2026-11-06"}


def _visit() -> dict:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "reader", "color": 1}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": False, "plans": []}
    record = json.dumps({"replay": REPLAY})
    sealed = json.dumps({"generated_at": "2026-11-06T01:00:00", "sports": {"nba": {"props": {"markets": [
        {"market": "pts", "label": "SEALED-MARKET", "n": 9, "roi": 0.5, "n_bets": 4}]}}}})
    ful = lambda b, s=200: (lambda r: r.fulfill(status=s, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, asked = [], []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.on("request", lambda r: asked.append(r.url))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/board/**", ful('{"error":"subscription required"}', 402))
                page.route("**/data/record.json*", ful(record))
                page.route("**/data/backtest.json*", ful(sealed))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#lab", wait_until="load")
                page.wait_for_function("() => !!document.querySelector('#lab-body .member-lock')", timeout=15000)
                got = page.evaluate("""() => ({ view: state.view,
                  walled: document.body.classList.contains('walled'),
                  wall: document.body.classList.contains('on-wall'),
                  text: (document.getElementById('lab-body') || {}).innerText || '',
                  rows: document.querySelectorAll('#lab-body table.lab-free tbody tr').length })""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return {"got": got, "errs": errs, "asked": asked}


def test_in_a_browser_a_free_account_lands_on_the_lab_with_the_summary_and_the_lock():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("  (browser part skipped; QB_BROWSER_TESTS=1 runs it)")
        return
    out = _visit()
    got = out["got"]
    assert got["view"] == "lab" and got["walled"] and not got["wall"], got
    assert got["rows"] == 2, got
    assert "NBA" in got["text"] and "18,420" in got["text"] and "+4.1%" in got["text"], got["text"][:400]
    assert "The replay, market by market, is for members" in got["text"]
    assert "SEALED-MARKET" not in got["text"], "nothing from the sealed file"
    assert not any("backtest.json" in u for u in out["asked"]), "a free reader is never sent for it"
    assert not out["errs"], out["errs"]


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
