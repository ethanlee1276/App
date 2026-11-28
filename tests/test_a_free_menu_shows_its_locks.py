"""A free account's menu shows its locks (Ethan, 2026-10-28, a screenshot
of the phone's menu sheet signed in on a free account: "on the free
account, we should show all these buttons locked too besides the ones a
free account can access").

The tab bar and the desktop sidebar's page rows already wore a lock on
everything the free tier does not open (app.js markLockedNav, WALL_OPEN).
The phone's menu sheet built its pills from the sidebar's rows and copied
their icon, label and badge, but not the lock; and the sidebar's tools
(Predict, Radar, the Lab, About …) and the board's own tabs (Game Lines)
were never marked at all, though a free account tapping them lands on the
plans. What this file pins:

  * every sidebar entry is marked by the page it opens: a page row by its
    view, a tool by its name, a board tab as the board;
  * the menu sheet's pills copy the lock, drawn at the icon's shoulder as
    the tab bar draws it;
  * in a browser, a free account's sheet locks exactly what WALL_OPEN does
    not open, and a member's locks nothing.

Run directly: `python3 tests/test_a_free_menu_shows_its_locks.py`
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = Path(ROOT, "web", "js", "app.js").read_text(encoding="utf-8")
CSS = Path(ROOT, "web", "css", "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def _wall_open() -> set:
    block = APP[APP.index("const WALL_OPEN = ["):APP.index("];", APP.index("const WALL_OPEN = ["))]
    block = re.sub(r"//[^\n]*", "", block)
    return set(re.findall(r'"([a-z]+)"', block))


def _groups() -> list:
    block = APP[APP.index("const MORE_GROUPS = ["):APP.index("];", APP.index("const MORE_GROUPS = ["))]
    return re.findall(r'"((?:view|sport|subtab):[a-z]+)"', block)


def _view(ref: str) -> str:
    kind, name = ref.split(":")
    return "recommended" if kind == "subtab" else name


def _free_opens(ref: str, open_: set) -> bool:
    """A free account's Home is the free Pick of the Day since 2026-10-30
    (Ethan: "make the picks of the day free"), so the board's own page row
    opens; the board's tabs (Game Lines) still lead to the plans."""
    return ref == "view:recommended" or _view(ref) in open_


def test_every_sidebar_entry_is_marked_by_the_page_it_opens():
    body = _fn("markLockedNav")
    assert """document.querySelectorAll('.nav-btn[data-view],.sport-btn[data-kind="tool"],.sb-subtab')""" in body
    assert '!WALL_OPEN.includes(b.dataset.view || b.dataset.sport || "recommended")' in body
    assert 'walled && b.dataset.view !== "recommended"' in body, "Home is the free pick's door, unlocked"


def test_the_sheet_copies_the_lock_at_the_icons_shoulder():
    assert 'pill.classList.toggle("nav-locked", src.classList.contains("nav-locked"));' in _fn("moreSheetBuild")
    assert ".more-pill.nav-locked { color: var(--text-mute); }" in CSS
    m = re.search(r"\.more-pill\.nav-locked::after \{([^}]*)\}", CSS)
    assert m and "left: 26px" in m.group(1) and "right: auto" in m.group(1), "at the icon's shoulder, as the tab bar"


def test_what_the_free_tier_opens_stays_plain():
    open_ = _wall_open()
    for v in ("live", "fantasy", "mybets", "feed", "zeno", "streak", "tools", "record"):
        assert v in open_, v
    locked = [r for r in _groups() if _view(r) not in open_]
    assert "view:likely" in locked and "subtab:gamebets" in locked and "sport:intel" in locked
    assert not {"sport:fantasy", "sport:mybets", "view:feed", "view:zeno", "view:tools", "view:streak"} & set(locked)


def _sheet(entitled: bool) -> tuple:
    from playwright.sync_api import sync_playwright
    import rendercheck
    who = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "ethan", "color": 1}}
    bill = {"signed_in": True, "email": "you@example.com", "paywall": True, "entitled": entitled, "plans": []}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    errs, rows = [], []
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
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", ful("{}"))
                page.route("**/api/account/**", ful(json.dumps({"sections": {}})))
                page.route("**/api/account/me*", ful(json.dumps(who)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/feed/**", ful(json.dumps({"posts": []})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#live", wait_until="load")
                page.wait_for_timeout(4000)
                page.evaluate("moreSheetOpen(true)")
                page.wait_for_timeout(600)
                rows = page.evaluate("[...document.querySelectorAll('#more-groups .more-pill')]"
                                     ".map((p) => [p.dataset.ref, p.classList.contains('nav-locked')])")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return rows, errs


def test_in_a_browser_a_free_sheet_locks_what_the_free_tier_does_not_open_and_a_members_none():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    open_ = _wall_open()
    rows, errs = _sheet(entitled=False)
    assert not errs, errs
    assert len(rows) >= 20, rows
    wrong = [(ref, locked) for ref, locked in rows if locked != (not _free_opens(ref, open_))]
    assert not wrong, wrong
    assert dict(rows)["sport:fantasy"] is False and dict(rows)["view:likely"] is True
    rows, errs = _sheet(entitled=True)
    assert not errs, errs
    assert rows and not any(locked for _ref, locked in rows), "a member's menu wears no lock"


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
