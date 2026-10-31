"""An account to use the site, the paid side shown before it, and the ways
from the free site into the paid one.

Ethan, 2026-10-25, the Live tab open on his phone: "there should be an
option on this screen to make an account bc people need an account to use
the site ... Look at the Real app and how they make u create an account on
the first screen", "make sure there's [a way] to get into the paid site from
this free version", and then: "go deeper on the free paid wall for when u
sign into the site or first get onto the site. look at other apps ... we
can show our paid features on the sign up site". What these hold:

  - the account wall is one switch on the box (engine/gate.account_wall):
    on with the paywall unless QB_ACCOUNT_WALL says otherwise, and both the
    billing status and /api/account/me carry it;
  - signed out with it up, every page but the plans, the Record, sign-in,
    sign-up, a reset and checkout opens the sign-up, and the page asked for
    is kept in the tab and opened once the account exists;
  - the sign-up shows the members' side from /api/firstlook alone —
    tonight's counts, last night, the record and the newest graded pick
    whatever it did — and no number is written into the page;
  - a plan tapped before the account goes to checkout after it; a new
    account meets the offer once, after its teams, with "continue free";
  - "Get picks" in the top bar, a members strip on Live, and a locked tab
    that says what it holds on the plans it opens.

    python3 tests/test_an_account_to_use_the_site.py
    (the browser half with QB_BROWSER_TESTS=1 and Playwright)
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ.setdefault("QB_ACCOUNTS_DB", os.path.join(_DIR, "accounts.db"))

APP = (ROOT / "web" / "js" / "app.js").read_text()
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text()
CHAT = (ROOT / "web" / "js" / "chat.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
SERVER = (ROOT / "server.py").read_text()


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _node(js):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the switch ---------------------------------------------------------------
def test_the_wall_stands_with_the_paywall_unless_the_box_says_otherwise():
    from engine import gate
    keep = {k: os.environ.pop(k, None) for k in ("QB_PAYWALL", "QB_ACCOUNT_WALL")}
    try:
        assert gate.account_wall() is False, "everything free, nothing asked"
        os.environ["QB_PAYWALL"] = "1"
        assert gate.account_wall() is True, "the paywall up brings the account wall"
        os.environ["QB_ACCOUNT_WALL"] = "0"
        assert gate.account_wall() is False, "one line on the box takes it down"
        os.environ.pop("QB_PAYWALL")
        os.environ["QB_ACCOUNT_WALL"] = "1"
        assert gate.account_wall() is True, "and puts it up with the paywall off"
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_both_answers_the_page_asks_carry_it():
    bill = SERVER[SERVER.index("    def _billing_get(self"):SERVER.index("    def _billing_confirm(self")]
    assert 'out["account_wall"] = GATE_.account_wall()' in bill
    me = SERVER[SERVER.index("    def _account_get(self"):]
    assert '"account_wall": __import__("engine.gate", fromlist=["x"]).account_wall()' in me[:2400]


# --- what the first screen shows of the paid side --------------------------------
def _ledger(rows):
    from engine import ledger as L
    conn = L.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))
    for r in rows:
        conn.execute("INSERT INTO bets (date, sport, player, market, side, line, odds, book, status, pnl_units, "
                     "hit_prob, stake_units, category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    return conn


def test_the_sample_is_the_newest_graded_pick_whatever_it_did():
    from engine import firstlook, ledger as L
    book = sorted(L.POOLED_BOOKS)[0] if isinstance(L.POOLED_BOOKS, (set, frozenset)) else L.POOLED_BOOKS[0]
    cat = book if isinstance(book, str) else book[0]
    conn = _ledger([
        ("2026-10-20", "nba", "Older Win", "points", "OVER", 20.5, -110, "fanduel", "won", 0.9, 0.6, 1.0, cat),
        ("2026-10-24", "nba", "Newest Loss", "rebounds", "OVER", 8.5, 105, "draftkings", "lost", -1.0, 0.55, 1.0, cat),
        ("2026-10-25", "nba", "Still Open", "assists", "OVER", 6.5, -120, "fanduel", "open", 0.0, 0.62, 1.0, cat),
    ])
    try:
        last = firstlook.last_graded(conn)
        assert last and last["player"] == "Newest Loss" and last["status"] == "lost", last
        assert set(last) == set(firstlook.LAST_FIELDS), "only the Record's own fields"
    finally:
        conn.close()
    empty = _ledger([])
    try:
        assert firstlook.last_graded(empty) is None
    finally:
        empty.close()


def test_the_feed_is_the_widgets_own_numbers_plus_that_row():
    from engine import firstlook
    conn = _ledger([])
    try:
        out = firstlook.build(Path(tempfile.mkdtemp()), conn=conn)
    finally:
        conn.close()
    # And `proof` (2026-10-26): real counts of who is here, or None under their floors.
    assert set(out) == {"record", "last_night", "tonight", "updated", "last", "proof"}, out
    src = (ROOT / "engine" / "firstlook.py").read_text()
    assert "widgetfeed.build(web, today)" in src, "the counts are the widget's — a count, never a pick"


def test_the_endpoint_is_public_and_kept_a_minute():
    assert 'if parsed.path in ("/api/firstlook", "/api/firstlook/"):' in SERVER
    fn = SERVER[SERVER.index("    def _firstlook(self"):SERVER.index("    def _record_lab(self")]
    assert "_account" not in fn and "_entitled" not in fn, "nothing in it is anyone's"
    assert "now - _FIRSTLOOK.get(\"at\", 0) > FIRSTLOOK_TTL_S" in fn and "FIRSTLOOK_TTL_S = 60" in SERVER


# --- the wall in the page ----------------------------------------------------------
def _open(name):
    m = re.search(rf"const {name} = \[(.*?)\];", APP, re.S)
    return set(re.findall(r'"([a-z]+)"', re.sub(r"//[^\n]*", "", m.group(1))))


def test_without_an_account_only_the_door_pages_open():
    assert _open("ACCOUNT_OPEN") == {"signup", "account", "reset", "paywall", "checkout", "record"}
    sw = _fn(APP, "_switchViewNow")
    assert sw.index('if (acctWallTurns(name)) { name = "signup"; dir = 0; }') \
        < sw.index('document.body.classList.toggle("on-wall", WALL_SCREENS.includes(name));'), \
        "the sign-up wears its own masthead"


def _turns(hash_, name, wall=True, signed=False, pre=None):
    open_list = re.search(r"const ACCOUNT_OPEN = \[(.*?)\];", APP, re.S).group(1)
    js = f"""
    const store = {json.dumps({"qb_wall_back": pre} if pre else {})};
    const sessionStorage = {{ getItem: (k) => store[k] || null, setItem: (k, v) => {{ store[k] = String(v); }},
                              removeItem: (k) => {{ delete store[k]; }} }};
    const location = {{ hash: {json.dumps(hash_)} }};
    let _pwStatus = {{ account_wall: {json.dumps(wall)} }};
    const acctSignedIn = () => {json.dumps(signed)};
    const ACCOUNT_OPEN = [{open_list}];
    {APP[APP.index("const acctWallUp = "):APP.index("let _wallFrom = ")]}
    const turned = acctWallTurns({json.dumps(name)});
    console.log(JSON.stringify([turned, store.qb_wall_back || null, takeWallBack(), store.qb_wall_back || null]));
    """
    return _node(js)


def test_a_refused_page_is_kept_once_for_after_the_account():
    assert _turns("#pbp/nfl/401", "pbp") == [True, "#pbp/nfl/401", "#pbp/nfl/401", None], "the whole link, read once"
    assert _turns("#record", "live") == [True, "#live", "#live", None], "a tab tapped elsewhere keeps its own name"
    js_keep = _turns("#signup", "pbp", pre="#pbp/nfl/401")
    assert js_keep[1] == "#pbp/nfl/401", "a room switched to after the boot does not shorten the kept link"
    assert _turns("#record", "record")[0] is False
    assert _turns("#live", "live", wall=False)[0] is False, "the switch off"
    assert _turns("#live", "live", signed=True)[0] is False, "an account in"


def test_after_the_account_the_kept_page_opens():
    land = _fn(APP, "acctLandAfterAuth")
    i = land.index("const back = takeWallBack();")
    assert land.index("if (!_pwStatus) {") < i, "a status that failed to arrive keeps the page for the next try"
    # What brought them here (whyLand, docs/IDEAS.md round three) comes after the kept page.
    assert '(_pendingPlanPeek() ? "#paywall" : back || whyLand(1) || "#live") : back || whyLand() || dcFirstStop();' in land
    assert land.count("if (back) location.hash = back;") == 2


def test_the_boot_raises_it_whether_or_not_the_paywall_is_up():
    i = APP.index("const door = acctWallUp();")
    block = APP[i:APP.index('addEventListener("hashchange"', i)]
    assert "if (!walled && !door) return;" in block
    assert 'if (!ACCOUNT_OPEN.includes(bootTarget) && bootTarget !== "friend") {' in block


# --- the first screen ----------------------------------------------------------------
def test_the_sign_up_shows_the_members_side_from_the_feed_alone():
    body = _fn(ACCOUNT, "signupHTML")
    order = [body.index(m) for m in ('<header class="fsu-top">', '<div class="fl-host">${flTonightHTML(_fl)}</div>',
                                     '<div class="card acct-card" id="su-form">',
                                     '<div class="fl-more">${flMembersHTML(_fl, _pwStatus)}</div>',
                                     '<ul class="acct-promises">')]
    assert order == sorted(order), "the brand, tonight, the form, then the members' side"
    assert 'fetch("/api/firstlook"' in _fn(ACCOUNT, "flGet")
    for name in ("flTonightHTML", "flLastHTML", "flRecordHTML", "flMembersHTML", "psTonightHTML"):
        f = _fn(ACCOUNT, name).replace("${", "")
        assert not re.search(r"\b\d{2,}\s*(picks?|–\d)", f), f"a count written into {name}"
    assert "flPaint(host);" in _fn(ACCOUNT, "renderSignup")
    assert "introDone(); host.innerHTML = signupHTML(); host.scrollTop = 0; flPaint(host);" in _fn(ACCOUNT, "introBind")


def test_the_sample_says_won_or_lost_as_it_happened():
    js = f"""
    const escapeHtml = (s) => String(s); const marketWord = (m) => m; const american = (o) => String(o);
    {_fn(ACCOUNT, "flLastHTML")}
    const row = (status, pnl) => ({{ player: "P", sport: "nba", date: "2026-10-24", market: "points", side: "OVER",
                                     line: 20.5, odds: -110, status, pnl_units: pnl, hit_prob: 0.6 }});
    console.log(JSON.stringify([flLastHTML({{ last: row("lost", -1) }}), flLastHTML({{ last: row("won", 0.91) }}),
                                flLastHTML({{ last: null }})]));
    """
    lost, won, none = _node(js)
    assert 'class="fl-pick lost"' in lost and "Lost −1.00u" in lost
    assert 'class="fl-pick won"' in won and "Won +0.91u" in won
    assert none == "", "no graded pick, no sample"


def test_the_free_lines_are_free_pages_and_the_member_lines_are_sold():
    rows = ACCOUNT[ACCOUNT.index("const FL_ROWS = ["):ACCOUNT.index("];", ACCOUNT.index("const FL_ROWS = ["))]
    # Seven free since 2026-10-30: the Pick of the Day joined them.
    assert rows.count(", 1],") == 7 and rows.count(", 0],") == 6
    assert '["The Pick of the Day, every league, with its record", 1]' in rows
    assert "Ask Qellys" in rows and "Zeno’s bets" in rows and "The members’ Discord" in rows


def test_a_plan_tapped_before_the_account_goes_to_checkout_after_it():
    js = ACCOUNT[ACCOUNT.index('if (typeof window !== "undefined" && !window._flBound) {'):]
    js = js[:js.index("\n}\n")]
    assert "rememberPendingPlan(pl.id);" in js and "if (acctSignedIn()) return window.coStart({ dataset: { plan: pl.id } });" in js
    plans = _fn(ACCOUNT, "flPlansHTML")
    assert "if (!storeSells())" in plans and "Members sign in with their account" in plans, "a build that sells names no price"


def test_the_trial_is_laid_out_day_by_day_only_when_this_reader_can_have_it():
    js = f"""
    const escapeHtml = (s) => String(s); const storeSells = () => true;
    const PLANS = [{{ id: "monthly", name: "Monthly", price: 25, per: "month", months: 1 }}];
    {_fn(ACCOUNT, "flTrialHTML")}
    console.log(JSON.stringify([flTrialHTML({{ trial_days: 3, trial_plan: "monthly" }}),
      flTrialHTML({{ trial_days: 3, trial_plan: "monthly", trial_eligible: false }}), flTrialHTML({{ trial_days: 0 }})]))
    """
    on, used, none = _node(js)
    assert "<b>Today</b>" in on and "<b>Day 3</b>" in on and "<b>Day 4</b>" in on and "$25 a month begins" in on
    assert used == "" and none == ""


def test_a_new_account_meets_the_offer_once_after_its_teams():
    assert "done: () => planStep(done) };" in _fn(ACCOUNT, "followStep")
    step = _fn(ACCOUNT, "planStep")
    assert 'if (!host || state.view !== "signup" || !storeSells() || _pendingPlanPeek()) return done();' in step
    assert "walled = await paywallCheck(1);" in step and "if (!walled) return done();" in step
    html = _fn(ACCOUNT, "planStepHTML")
    assert 'data-ps="free">Continue with the free account</button>' in html, "free is a full button"
    pick = _fn(ACCOUNT, "planPick")
    assert 'if (choice !== "free") rememberPendingPlan(choice);' in pick and "_planDone = null;" in pick


def test_with_the_wall_up_the_sign_up_has_no_way_past():
    js = f"""
    let _acctUser = null, _pwStatus = {{ account_wall: true }}, _acctNote = "", _fl = null, _suNote = "";
    const escapeHtml = (s) => String(s), escapeAttr = escapeHtml, icon = () => "", iconMark = () => "";
    const brandMarkHTML = () => "", phoneDoorHTML = () => "", referralTyped = () => "", storeSells = () => true;
    const acctFieldsHTML = (m, extra) => extra, flTonightHTML = () => "", flMembersHTML = () => "", flProofHTML = () => "";
    const suWhyHTML = () => "";
    const sessionStorage = {{ getItem: () => "#pbp/nfl/1" }}; const WALL_OPEN = ["pbp"]; const PLANS = [{{}}];
    {_fn(ACCOUNT, "wallWhyLine")}
    {_fn(ACCOUNT, "signupHTML")}
    const up = signupHTML(); _pwStatus = {{ account_wall: false }};
    console.log(JSON.stringify([up, signupHTML()]));
    """
    up, down = _node(js)
    assert "Look around first" not in up and "Look around first" in down
    assert "the game you were sent opens" in up, "a shared game says it is waiting"
    assert 'data-act="acctGoLogin">Log in</button>' in up.split('<div class="welcome-hero">')[0], "Log in at the top"


# --- the ways in from the free site ---------------------------------------------------
def test_get_picks_in_the_top_bar_for_a_reader_without_a_plan():
    assert re.search(r'<a class="nav-up" id="nav-up" href="#paywall" hidden>', HTML)
    lock = _fn(APP, "markLockedNav")
    assert 'if (up) up.hidden = !walled || !storeSells();' in lock


def test_a_locked_tab_says_on_the_plans_what_it_holds():
    why = _fn(ACCOUNT, "pwWhyHTML")
    assert 'typeof _wallFrom === "string" ? _wallFrom : ""' in why
    assert "${pwWhyHTML()}" in _fn(ACCOUNT, "paywallHTML")
    table = ACCOUNT[ACCOUNT.index("const PW_WHY = {"):ACCOUNT.index("};", ACCOUNT.index("const PW_WHY = {"))]
    for tab in ("recommended:", "likely:", "ask:"):
        assert tab in table, tab


def test_live_carries_the_members_strip_with_a_count_and_never_a_pick():
    load = CHAT[CHAT.index("async function lvmLoad("):CHAT.index("function lvmHTML(")]
    assert "isWalled()" in load and "storeSells()" in load and "Date.now() - _lvmAt < 300000" in load
    assert 'fetch("/api/firstlook"' in load
    html = _fn(CHAT, "lvmHTML")
    assert 'href="#paywall"' in html and "x.picks" in html and "player" not in html
    mount = CHAT[CHAT.index("async function yourPlayersMount("):CHAT.index("let _lvmLast = ")]
    assert "host.innerHTML = _lvmLast + _ypLast;" in mount


# --- in a browser --------------------------------------------------------------------
def test_in_a_browser_a_stranger_signs_up_first_and_keeps_the_link():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    plans = [{"id": "monthly", "ready": True}, {"id": "sixmonth", "ready": True}, {"id": "yearly", "ready": True}]
    bill = {"configured": True, "signed_in": False, "plans": plans, "trial_days": 3, "trial_plan": "monthly",
            "paywall": True, "account_wall": True}
    me = {"signed_in": False, "account_wall": True}
    fl = {"record": {"w": 40, "l": 30, "p": 1, "units": 3.5, "roi": 2.0},
          "last_night": {"date": "2026-10-24", "w": 3, "l": 2, "p": 0, "units": 0.8},
          "tonight": [{"league": "NFL", "sport": "nfl", "picks": 5}], "updated": "x",
          "last": {"date": "2026-10-24", "sport": "nfl", "player": "Sample Player", "market": "rec yds", "side": "OVER",
                   "line": 60.5, "odds": -110, "book": "fanduel", "status": "lost", "pnl_units": -1.0, "hit_prob": 0.58}}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
                ctx.add_init_script("try { localStorage.setItem('qb_intro_v1', '1'); } catch (e) {}")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/billing/status*", ful(json.dumps(bill)))
                page.route("**/api/account/me*", ful(json.dumps(me)))
                page.route("**/api/firstlook*", ful(json.dumps(fl)))
                page.goto(f"http://127.0.0.1:{port}/#pbp/nfl/401", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                got["shared"] = page.evaluate("""() => ({ view: state.view, kept: sessionStorage.getItem('qb_wall_back'),
                  why: (document.querySelector('.fsu-why') || {}).textContent || '',
                  tonight: (document.querySelector('.fl-tonight-h b') || {}).textContent || '',
                  sample: (document.querySelector('.fl-pick') || {}).className || '',
                  skip: !!document.querySelector('.welcome-skip') })""")
                page.click("[data-flplan='yearly']", force=True)
                page.wait_for_timeout(500)
                got["plan"] = page.evaluate("localStorage.getItem('qb_pending_plan')")
                page.goto(f"http://127.0.0.1:{port}/#record", wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                got["record"] = page.evaluate("state.view")
                got["errors"] = errs
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    s = got["shared"]
    assert s["view"] == "signup" and s["kept"] == "#pbp/nfl/401", s
    assert "the game you were sent opens" in s["why"] and "5 picks posted today" in s["tonight"], s
    assert "lost" in s["sample"] and not s["skip"], s
    assert got["plan"] == "yearly", got
    assert got["record"] == "record", "the Record stays open without an account"
    assert not got["errors"], got["errors"]


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
