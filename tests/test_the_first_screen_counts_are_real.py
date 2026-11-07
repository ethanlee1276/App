"""The first screen says how many are here — real counts, or nothing.

The ideas list's "true social proof" (2026-10-26): under the first screen's
promise, "214 accounts made this week · 37 in game rooms right now". What
these hold (engine/firstlook proof, engine/gamechat here_total, account.js
flProofHTML):

  - the week is the accounts table's own count of the last seven days, the
    rooms the chat's own "here" pages, each page once however many rooms;
  - under its floor a count is left out, and with neither there is no line;
  - a read never creates the accounts file;
  - the page prints exactly what the server sent, never rounded up.

    python3 tests/test_the_first_screen_counts_are_real.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A          # noqa: E402
from engine import firstlook as FL        # noqa: E402
from engine import gamechat as GC         # noqa: E402

ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()
NOW = 1793030400.0


def _users(conn, ages):
    for i, age in enumerate(ages):
        conn.execute("INSERT INTO users (email, verifier, created_at, age_confirmed, terms_accepted_at) "
                     "VALUES (?, 'x', ?, 1, ?)", (f"u{i}@example.com", NOW - age, NOW - age))
    conn.commit()


def _rooms(pages):
    with GC._HERE_LOCK:
        was = {k: dict(v) for k, v in GC._HERE.items()}
        GC._HERE.clear()
        for room, keys in pages.items():
            GC._HERE[room] = {k: NOW - 5 for k in keys}
    return was


def _restore(was):
    with GC._HERE_LOCK:
        GC._HERE.clear()
        GC._HERE.update(was)


def test_the_week_is_the_accounts_tables_own_count():
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        _users(conn, [3600 * h for h in range(30)] + [8 * 86400] * 5)
        was = _rooms({})
        try:
            assert FL.proof(NOW, conn) == {"week": 30}
        finally:
            _restore(was)
        conn.close()


def test_under_its_floor_a_count_is_left_out():
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        _users(conn, [3600] * (FL.WEEK_MIN - 1))
        was = _rooms({"nfl_1": [f"a{i}" for i in range(FL.ROOMS_MIN - 1)]})
        try:
            assert FL.proof(NOW, conn) is None
        finally:
            _restore(was)
        conn.close()


def test_a_page_in_two_rooms_counts_once_and_a_gone_one_not_at_all():
    pages = {"nfl_1": [f"a{i}" for i in range(8)], "nba_2": [f"a{i}" for i in range(4, 12)]}
    was = _rooms(pages)
    try:
        with GC._HERE_LOCK:
            GC._HERE["nhl_3"] = {"gone": NOW - GC.HERE_S - 1}
        assert GC.here_total(NOW) == 12
        with tempfile.TemporaryDirectory() as d:
            conn = A.connect(Path(d) / "a.db")
            assert FL.proof(NOW, conn) == {"rooms": 12}
            conn.close()
    finally:
        _restore(was)


def test_a_read_never_creates_the_accounts_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "none.db"
        was_path = A.DB_PATH
        A.DB_PATH = path
        try:
            FL.proof(NOW)
        finally:
            A.DB_PATH = was_path
        assert not path.exists()


def test_the_build_carries_it():
    src = open(os.path.join(ROOT, "engine", "firstlook.py"), encoding="utf-8").read()
    assert 'out["proof"] = proof()' in src


def _paint(proof):
    i = ACCOUNT.index("function flProofHTML(")
    fn = ACCOUNT[i:ACCOUNT.index("\n}\n", i) + 3]
    js = f"{fn}\nconsole.log(JSON.stringify(flProofHTML({json.dumps({'proof': proof})})));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_prints_what_was_sent():
    out = _paint({"week": 1204, "rooms": 37})
    assert "<b>1,204</b> accounts made this week" in out and "<b>37</b> in game rooms right now" in out
    assert _paint({"rooms": 12}).count("<span>") == 1
    assert _paint(None) == "" and _paint({}) == ""
    assert "<b>12</b>" in _paint({"rooms": 12.9}), "never rounded up"


def test_in_a_browser_the_counts_sit_under_the_promise():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    bill = {"configured": True, "signed_in": False, "plans": [{"id": "monthly", "ready": True}], "trial_days": 3,
            "trial_plan": "monthly", "paywall": True, "account_wall": True}
    fl = {"tonight": [], "proof": {"week": 214, "rooms": 37}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, got = [], None
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/account/me*", ful(json.dumps({"signed_in": False, "account_wall": True})))
                page.route("**/api/firstlook*", ful(json.dumps(fl)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/#signup", wait_until="domcontentloaded")
                for _ in range(30):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.fl-proof')"):
                        break
                    page.wait_for_timeout(500)
                got = page.evaluate("""(() => { const p = document.querySelector('.fl-proof'); if (!p) return null;
                  const r = p.getBoundingClientRect(), s = document.querySelector('.fsu-sub').getBoundingClientRect();
                  return { text: p.textContent.replace(/\\s+/g, ' ').trim(), under: r.top >= s.bottom,
                           seen: r.bottom <= innerHeight, fits: r.left >= 0 && r.right <= innerWidth }; })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got and got["under"] and got["seen"] and got["fits"], got
    assert "214 accounts made this week" in got["text"] and "37 in game rooms right now" in got["text"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
