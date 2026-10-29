"""Alerts are asked for after a sign-in, and again only when they mean
something (app.js pushAskArm/pushAskTick, js/account.js pushAskSheet).

Ethan, 2026-10-29: "there needs to be a setting for when you first log
into the app ... it'll prompt you to turn on notifications." What these
hold, from docs/RETENTION.md (Apple: ask in context; the research: a
primer before the system prompt, and fewer, more relevant alerts keep them
on):

  * every way in arms it (email, a password reset, a passkey, a phone
    code), and it shows once the reader lands, wherever the home-screen
    sheet would, after that sheet when both are due;
  * it asks again only beside something an alert would serve: following a
    team, a bet put in My Bets (by hand or Track it in Ask);
  * never on a desktop browser, never once this phone has alerts on or has
    refused them, three times at most, two weeks apart;
  * yes turns on the kinds a new member wants first, for the leagues of
    the teams they follow (or the one they are reading), and says each is
    a switch in Alerts; never a "bet now".

Run directly: `python3 tests/test_alerts_are_asked_for_at_the_right_moment.py`
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ACCT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
ASK = (ROOT / "web" / "js" / "ask.js").read_text(encoding="utf-8")


def _fn(src, head):
    i = src.index(head)
    return src[i:src.index("\n}", i)]


def test_every_way_in_arms_it():
    assert APP.count("    a2hsArm();\n    pushAskArm();\n") == 2, "the email sign-in and the password reset"
    assert 'if (typeof pushAskArm === "function") pushAskArm();' in _fn(ACCT, "const o = await pkOptions(\"login\");"), \
        "a passkey"
    i = ACCT.index('const r = await fetch("/api/account/phone-verify"')
    assert 'if (typeof pushAskArm === "function") pushAskArm();' in ACCT[i:i + 1200], "a phone code"


def test_it_shows_where_the_home_screen_sheet_does_and_after_it():
    assert APP.count("a2hsTick();\n  pushAskTick();") + APP.count("a2hsTick();\n    pushAskTick();") \
        + APP.count("a2hsTick();\n      pushAskTick();") == 3
    assert "pushAskTick();" in _fn(APP, "window.a2hsDismiss = function"), "the alerts sheet waited behind it"
    due = _fn(APP, "function pushAskDue(")
    assert 'document.getElementById("a2hs")' in due, "never on top of the home-screen sheet"


def test_it_asks_again_only_beside_something_an_alert_serves():
    fav = _fn(APP, "function favToggle(")
    assert "if (i < 0) pushAskTick({ team: teamName(abbr) });" in fav, "on a follow, never an unfollow"
    i = APP.index("const bets = mbLoad();\n  bets.push({")
    assert "pushAskTick({ bet: true });" in APP[i:i + 600], "a bet put in My Bets by hand"
    assert 'if (typeof pushAskTick === "function") pushAskTick({ bet: true });' in ASK, "Track it in Ask"


def test_the_rules_it_keeps():
    due = _fn(APP, "function pushAskDue(")
    assert 'k === "native" || (k === "web" && (a2hsMobile() || a2hsInstalled()))' in due, "a phone or the app only"
    assert "(pushSaved() || {}).endpoint" in due, "never once alerts are on"
    assert 'Notification.permission === "denied"' in due, "never once the phone refused"
    assert "(a.n || 0) < 3 && Date.now() - (a.last || 0) > 14 * 864e5" in due, "three asks, two weeks apart"
    sheet = ACCT[ACCT.index("async function pushAskSheet("):]
    assert 'p.receive === "denied"' in sheet, "the iPhone app asks Apple first"
    assert sheet.count("counted();") == 2, "Not now and a refusal are both counted"


def test_yes_turns_on_what_a_new_member_wants_first():
    assert 'const PUSH_ASK_TOPICS = ["posted", "settled", "kickoff", "clutch", "finals", "bets", "watches"];' in ACCT
    lg = _fn(ACCT, "function pushAskLeagues(")
    assert 'split(":")[0]' in lg and "[state.sport]" in lg, "the followed teams' leagues, else the one on screen"
    sheet = ACCT[ACCT.index("async function pushAskSheet("):]
    assert "pushRemember(await pushOn(PUSH_ASK_TOPICS.concat(away), pushAskLeagues()));" in sheet
    # "While you were away" joins them only while the site keeps activity (engine/activity).
    assert 'const away = _pwStatus && _pwStatus.activity_switch ? ["away"] : [];' in sheet
    assert "Never a “bet now”" in sheet and "each kind is a switch in Alerts" in sheet
    on = _fn(APP, "async function pushOn(")
    assert on.count("...lg") == 4, "the leagues travel to the box on both paths"
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")   # the Alerts page, loaded on first use
    assert "pushRemember(await pushOn(" in more, "the Alerts switch keeps what the sheet keeps"


def test_in_a_browser_it_asks_counts_and_waits():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, str(ROOT))                         # rendercheck.py is the repository's own
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    got = {}
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.path.exists("/opt/pw-browsers/chromium"):
            kw["executable_path"] = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**kw)
        try:
            seen = "try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done'); localStorage.setItem('qb.a2hs', 'off'); } catch (e) {}"
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                      service_workers="block")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.add_init_script(seen)
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_timeout(2500)
            page.evaluate("pushAskArm(); pushAskTick();")
            page.wait_for_timeout(1500)
            got["shown"] = page.evaluate("!!document.querySelector('#pushask .a2hs-card')")
            got["text"] = page.evaluate("(document.querySelector('#pushask p') || {}).textContent || ''")
            page.click("#pushask .a2hs-go [data-pa='no']")
            page.wait_for_timeout(200)
            got["gone"] = page.evaluate("!document.getElementById('pushask')")
            got["counted"] = page.evaluate("JSON.parse(localStorage.getItem('qb.pushask')).n")
            got["again_now"] = page.evaluate("pushAskDue()")
            page.evaluate("localStorage.setItem('qb.pushask', JSON.stringify({n: 1, last: Date.now() - 15 * 864e5}))")
            page.evaluate("favToggle('GB', 'nfl')")
            page.wait_for_timeout(1000)
            got["follow"] = page.evaluate("(document.querySelector('#pushask p') || {}).textContent || ''")
            page.evaluate("document.getElementById('pushask') && document.getElementById('pushask').remove()")
            page.evaluate("localStorage.setItem('qb.pushask', JSON.stringify({n: 3, last: 0}))")
            got["after_three"] = page.evaluate("pushAskDue()")
            page.evaluate("localStorage.setItem('qb.pushask', '{}'); localStorage.setItem('qb_push', JSON.stringify({endpoint: 'x', topics: ['posted']}))")
            got["when_on"] = page.evaluate("pushAskDue()")
            got["errors"] = list(errors)
            ctx.close()
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
            page = ctx.new_page()
            page.add_init_script(seen)
            page.goto(origin + "/index.html#recommended", wait_until="load")
            page.wait_for_timeout(2000)
            got["desktop"] = page.evaluate("pushAskDue()")
            ctx.close()
        finally:
            browser.close()
    assert got["shown"] and "Never a “bet now”" in got["text"], got
    assert got["gone"] and got["counted"] == 1 and got["again_now"] is False, got
    assert re.search(r"before every \w+ game", got["follow"]), got["follow"]
    assert got["after_three"] is False and got["when_on"] is False and got["desktop"] is False, got
    assert not got["errors"], got["errors"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
