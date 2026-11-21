"""A member whose plan ended sees what the picks did since, on the plans page.

The ideas list's win-back (docs/IDEAS.md, 2026-10-26): the lapse card on
the plans page (pwLapseHTML) carries the public record from the day the
plan ended — "Since your plan ended Oct 3 · 23–14 · +6.1u" — off the same
curve the Record page draws, so the two never disagree. What these hold:

  - the numbers are the Record curve's days from the plan's end on, pushes
    counted apart, in Eastern days like the curve;
  - shown win or lose, once five picks have graded; never for a plan that
    has not ended, a reader who still has one, or a curve that is missing;
  - it links to the Record, and a failed card keeps its Update card button.

    python3 tests/test_the_win_back_line.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ACCOUNT = open(os.path.join(ROOT, "web", "js", "account.js"), encoding="utf-8").read()
# Sat 3 Oct 2026, 8:00 PM Eastern.
ENDED = 1791072000


def _fn(name):
    i = ACCOUNT.index(f"function {name}(")
    return ACCOUNT[i:ACCOUNT.index("\n}\n", i) + 3]


def _run(expr):
    js = f"""
    const escapeHtml = (s) => String(s), icon = () => "", tzOpts = (o) => o;
    {_fn("pwSinceHTML")}
    {_fn("pwLapseHTML")}
    console.log(JSON.stringify({expr}));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30,
                         env={**os.environ, "TZ": "America/New_York"})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


CURVE = [
    {"date": "2026-10-02", "w": 9, "l": 1, "n": 10, "day_u": 7.5},      # before: not theirs to miss
    {"date": "2026-10-03", "w": 3, "l": 2, "n": 6, "day_u": 0.8},
    {"date": "2026-10-10", "w": 6, "l": 4, "n": 10, "day_u": 1.4},
    {"date": "2026-10-20", "w": 14, "l": 8, "n": 22, "day_u": 3.9},
]


def test_the_record_since_the_plan_ended():
    out = _run(f"pwSinceHTML({{ curve: {json.dumps(CURVE)} }}, {{ period_end: {ENDED} }})")
    assert '<a class="pw-since" href="#record"><span>Since your plan ended Oct 3</span>' in out
    assert "<b>23–14–1</b>" in out, "the days from the 3rd on, the push counted apart"
    assert '<span class="pos">+6.1u</span>' in out


def test_shown_when_it_lost_too():
    down = [{"date": "2026-10-05", "w": 2, "l": 6, "n": 8, "day_u": -4.25}]
    out = _run(f"pwSinceHTML({{ curve: {json.dumps(down)} }}, {{ period_end: {ENDED} }})")
    assert "<b>2–6</b>" in out and '<span class="neg">−4.3u</span>' in out


def test_not_shown_without_a_real_sample_or_an_ended_plan():
    few = [{"date": "2026-10-05", "w": 2, "l": 2, "n": 4, "day_u": 0.1}]
    assert _run(f"pwSinceHTML({{ curve: {json.dumps(few)} }}, {{ period_end: {ENDED} }})") == ""
    later = int(time.time()) + 86400
    assert _run(f"pwSinceHTML({{ curve: {json.dumps(CURVE)} }}, {{ period_end: {later} }})") == ""
    assert _run(f"pwSinceHTML(null, {{ period_end: {ENDED} }})") == ""
    assert _run(f"pwSinceHTML({{ curve: {json.dumps(CURVE)} }}, {{}})") == ""


def test_it_rides_the_lapse_card_and_nothing_else():
    rec = f"{{ curve: {json.dumps(CURVE)} }}"
    gone = _run(f"pwLapseHTML({{ signed_in: true, entitled: false, status: 'canceled', note: 'Cancelled.', "
                f"period_end: {ENDED} }}, {rec})")
    assert "pw-since" in gone and gone.index("Cancelled.") < gone.index("pw-since")
    card = _run(f"pwLapseHTML({{ signed_in: true, entitled: false, status: 'past_due', note: 'Card declined.', "
                f"period_end: {ENDED} }}, {rec})")
    assert "pw-since" in card and 'data-act="billPortal">Update card</button>' in card
    paying = _run(f"pwLapseHTML({{ signed_in: true, entitled: true, status: 'active', note: 'Active.', "
                  f"period_end: {ENDED} }}, {rec})")
    assert paying == ""
    assert ACCOUNT.count("${pwLapseHTML(status, rec)}") == 2, "the plans page and the store build's both pass the record"


def test_in_a_browser_a_lapsed_member_sees_what_they_missed():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    bill = {"configured": True, "signed_in": True, "email": "you@example.com", "paywall": True, "entitled": False,
            "status": "canceled", "period_end": ENDED, "plan": "monthly", "cancel_at_end": False,
            "note": "Cancelled — access ended 3 Oct 2026.", "trial_eligible": False,
            "plans": [{"id": "monthly", "ready": True}, {"id": "sixmonth", "ready": True}, {"id": "yearly", "ready": True}]}
    rec = {"generated_at": "2026-10-26T09:00:00", "overall": {"settled": 52, "wins": 32, "losses": 15, "pushes": 1},
           "curve": CURVE, "recent": []}
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
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block",
                                          timezone_id="America/New_York")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/data/record.json*", ful(json.dumps(rec)))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#paywall", wait_until="load")
                for _ in range(30):                 # the page's CSP refuses wait_for_function's eval
                    if page.evaluate("!!document.querySelector('.pw-since')"):
                        break
                    page.wait_for_timeout(500)
                got = page.evaluate("""(() => { const a = document.querySelector('.pw-since'); if (!a) return null;
                  const r = a.getBoundingClientRect();
                  return { text: a.textContent.replace(/\\s+/g, ' ').trim(), fits: r.left >= 0 && r.right <= innerWidth,
                           top: r.top < innerHeight }; })()""")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs[:3]
    assert got and got["fits"] and got["top"], got
    assert "Since your plan ended Oct 3" in got["text"] and "23–14–1" in got["text"] and "+6.1u" in got["text"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
