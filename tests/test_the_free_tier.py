"""The free tier: the live games, their chat, the Record and Fantasy for
anyone; the picks for members.

Ethan, 2026-10-25: *"make the website free, but the only free things you
get access to is the record, the live page ... we should not give away any
picks or props ... users can at least use the live feature and the chat
and look at live stats and stuff like that for free without having to pay
for that or having to see a paywall. But obviously live props and stuff
like that, and props and picks and most likely bets and edge bets and all
that stuff should be hidden and not shown for free."* And his four answers
the same day: Fantasy free; a game's page shows its facts free and its
analysis paid; any free account can post in a chat; My Bets free with an
account.

WHAT IS OPENED IS THE PAGE AROUND THE PICKS, NEVER THE PICKS. The boards
a reader without a plan fetches were redacted on disk long before this
(engine/gate), so nothing here makes a pick reachable that was not. What
changed is that the page no longer refuses to draw: the Live tab, a game's
play-by-play and chat, a game's own page, Fantasy and My Bets render with
the app's chrome, and where a paid section would be there is one card
saying what is behind it — with no number from behind it.

AND THE FIRST SCREEN. A stranger lands on sign-up (Real's first screen:
make a username or log in), with one way past it to the free Live tab.

    python3 tests/test_the_free_tier.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate                                       # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text()
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
SERVER = (ROOT / "server.py").read_text()


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _open():
    m = re.search(r"const WALL_OPEN = \[(.*?)\];", APP, re.S)
    return set(re.findall(r'"([a-z]+)"', re.sub(r"//[^\n]*", "", m.group(1))))


def _node(js):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- what opens, and what never does ----------------------------------------
def test_the_free_pages_are_open():
    for page in ("live", "pbp", "game", "record", "fantasy", "mybets", "signup", "account"):
        assert page in _open(), f"{page} is behind the wall"


def test_no_page_that_lists_picks_is_open():
    """The list Ethan named: props, picks, Most Likely, Edge — and every
    other page whose whole content is the model's output."""
    for page in ("recommended", "prop", "props", "edge", "likely", "longshots",
                 "tonight", "scanner", "futures", "ask", "intel", "lab", "bankroll"):
        assert page not in _open(), f"{page} opened with the free tier"


def test_the_paid_boards_are_still_paid():
    """The free tier changed the pages, not the gate: every key a pick
    lives under is still stripped from the public copy."""
    for key in ("recommendations", "most_likely", "likely_board", "pick_of_the_day",
                "game_bets", "long_shots", "matchup_picks", "market_scan"):
        assert key in gate.PAID_KEYS, f"{key} came off the paid list"
    assert "zeno.json" in gate.PAID_FILES
    assert gate.PAID_KEYS_BY_FILE["fantasy.json"] == ("scripts",), \
        "only the fantasy room's opinions opened; the game scripts are sold by name"


# --- the chrome stays, the paid tabs say so ----------------------------------
def test_the_apps_chrome_hides_only_on_the_walls_own_screens():
    m = re.search(r"const WALL_SCREENS = \[([^\]]*)\]", APP)
    assert set(re.findall(r'"([a-z]+)"', m.group(1))) == {"paywall", "checkout", "signup", "reset"}
    assert 'document.body.classList.toggle("on-wall", WALL_SCREENS.includes(name));' in _fn(APP, "_switchViewNow")
    assert "body.walled .sidebar" not in CSS.replace("body.walled.on-wall .sidebar", ""), \
        "a free reader on Live lost the menu"
    assert "body.walled.on-wall .sidebar, body.walled.on-wall .tabbar," in CSS


def test_every_paid_tab_is_marked_locked_and_none_of_the_free_ones():
    body = _fn(APP, "markLockedNav")
    assert '"nav-locked", walled && !WALL_OPEN.includes(b.dataset.view)' in body
    assert ".nav-locked::after" in CSS and "--ic-lock" in CSS
    i = APP.index('document.body.classList.add("walled");')
    assert "markLockedNav();" in APP[i:i + 80], "the wall goes up and the tabs are not marked"


def test_a_paid_tab_still_lands_on_the_plans_and_says_which_it_was():
    """Which tab sent a reader is kept (`_wallFrom`) so the plans can say
    what it holds (js/account.js pwWhyHTML)."""
    sv = _fn(APP, "switchView")
    assert '_wallFrom = wallBlocked(name) ? name : "";' in sv and 'if (_wallFrom) name = "paywall";' in sv
    assert 'if (wallBlocked(name)) { _wallFrom = name; name = "paywall"; dir = 0; }' in _fn(APP, "_switchViewNow")


# --- the lock card -----------------------------------------------------------
def test_the_lock_card_says_what_is_behind_it_and_never_a_number():
    js = f"""
    const icon = () => "";
    {_fn(APP, "escapeHtml")}
    {_fn(APP, "memberLockHTML")}
    console.log(JSON.stringify(memberLockHTML("Our picks", "Members see <every> pick")));
    """
    html = _node(js)
    assert 'href="#paywall"' in html and "See the plans" in html
    assert "&lt;every&gt;" in html, "the lock card draws its words unescaped"


def test_the_live_tab_shows_the_lock_and_never_the_picks():
    """Even if a pick reached the page, the walled Live tab never reads it."""
    data = {"live_picks": [{"player": "Secret Player", "market": "Rush yds", "odds": -110}],
            "live_potd": [{"player": "Pick Of Day Guy"}]}
    js = f"""
    const state = {{ sport: "nfl", view: "live", data: {json.dumps(data)} }};
    const icon = () => "";
    const isWalled = () => true;
    const buzzOnSettle = () => {{ throw new Error("read the picks"); }};
    const _els = {{ "live-picks": {{ innerHTML: "" }} }};
    const document = {{ getElementById: (id) => _els[id] || null }};
    {_fn(APP, "escapeHtml")}
    {_fn(APP, "memberLockHTML")}
    {_fn(APP, "renderLivePicks")}
    renderLivePicks();
    console.log(JSON.stringify(_els["live-picks"].innerHTML));
    """
    html = _node(js)
    assert "member-lock" in html
    assert "Secret Player" not in html and "Pick Of Day Guy" not in html


def test_the_play_by_play_locks_its_picks_rail():
    body = _fn(APP, "pbpPropsHTML")
    head = body[:body.index("pbpOurPicks(")]
    assert "if (isWalled())" in head and "memberLockHTML(" in head, \
        "the play-by-play's picks rail reads the picks before checking the wall"


def test_a_games_page_keeps_its_facts_and_drops_every_paid_section():
    """Ethan's answer: facts free, analysis paid. Every section a pick or
    a reading of the board lives in comes off; the lines, the conditions,
    the team shapes and the pressure pair (standings facts) stay."""
    i = DETAIL.index("if (isWalled()) {\n    host.querySelectorAll(")
    block = DETAIL[i:DETAIL.index("const back = ", i)]
    for sec in ("report", "plan", "scan", "replay", "matchup", "likely", "scripts",
                "bets", "props", "shots"):
        assert f"#gp-sec-{sec}" in block, f"the {sec} section stays on a free game page"
    assert "#gp-lab" in block, "the member-only ideas panel is asked for and refused on a free page"
    assert ".gp-jump" in block, "the jump chips count the picks"
    for fact in ("gp-sec-lines", "gp-sec-shapes", "gp-pressure"):
        assert fact not in block, f"{fact} is a fact and was locked"
    assert 'memberLockHTML("The analysis and every pick on this game"' in block
    # Every section the page can draw is either removed above or named as a
    # fact here, so a new section has to choose.
    drawn = set(re.findall(r'id="(gp-sec-[a-z]+)"', DETAIL))
    known = {f"gp-sec-{s}" for s in ("report", "plan", "scan", "replay", "matchup", "likely",
                                     "scripts", "bets", "props", "shots", "lines", "shapes")}
    assert drawn <= known, f"a new game-page section is unclassified: {sorted(drawn - known)}"


def test_the_ideas_endpoint_answers_members_only():
    body = SERVER[SERVER.index("    def _ideas(self, q):"):SERVER.index("        data = ID.read(sport)")]
    assert "if not self._entitled(aconn, who):" in body


# --- the chat ---------------------------------------------------------------
def test_anyone_reads_a_chat_and_any_account_posts():
    """Ethan's answer: any free account can post. Reading takes nothing."""
    get = SERVER[SERVER.index("    def _chat_get(self"):SERVER.index("    def _chat_post(self")]
    assert "_entitled" not in get, "reading a game's chat asks for a plan"
    post = SERVER[SERVER.index("    def _chat_post(self"):]
    post = post[:post.index("\n    def ")]
    assert "_entitled" not in post, "posting asks for a plan, not an account"
    i = post.index("who = self._account(conn)")
    assert "if not who:" in post[i:i + 80] and "Make a free account to join the chat." in post


# --- the first screen -------------------------------------------------------
def _boot_target(hash_, signed_in=False, seen=False, door=False):
    """The boot's landing rule for a walled reader, run in node against the
    real source: (the hash it sets, the view it switches to). `door` is the
    account wall up for a signed-out reader (app.js acctWallUp)."""
    i = APP.index("const bootTarget = ")
    j = APP.index("// A hash that names a real page must not punch through the wall.", i)
    block = APP[i:j]
    m = re.search(r"const WALL_OPEN = \[(.*?)\];", APP, re.S)
    a = re.search(r"const ACCOUNT_OPEN = \[(.*?)\];", APP, re.S)
    js = f"""
    const WALL_OPEN = [{m.group(1)}];
    const ACCOUNT_OPEN = [{a.group(1)}];
    const location = {{ hash: {json.dumps(hash_)} }};
    const acctSignedIn = () => {json.dumps(signed_in)};
    const welcomeSeen = () => {json.dumps(seen)};
    const door = {json.dumps(door)};
    let kept = null;
    const acctWallTurns = (v) => {{ kept = v; return true; }};
    let went = null;
    const _switchViewNow = (name) => {{ went = name; }};
    {block}
    console.log(JSON.stringify([location.hash, went, kept]));
    """
    return tuple(_node(js))[:2] if not door else tuple(_node(js))


def test_a_stranger_lands_on_sign_up():
    assert _boot_target("") == ("#signup", "signup")
    assert _boot_target("#recommended") == ("#signup", "signup")


def test_someone_who_has_looked_around_or_signed_in_lands_on_live():
    assert _boot_target("", seen=True) == ("#live", "live")
    assert _boot_target("", signed_in=True) == ("#live", "live")


def test_a_link_to_an_open_page_keeps_it():
    for h in ("#record", "#pbp/nfl/401", "#live", "#friend/abc", "#fantasy"):
        assert _boot_target(h)[1] is None, h


def test_a_link_to_a_paid_page_shows_the_plans():
    """What its sender meant to share — for anyone past the first screen.
    A stranger meets the sign-up first, like every stranger."""
    assert _boot_target("#edge", seen=True)[1] == "paywall"
    assert _boot_target("#likely", signed_in=True)[1] == "paywall"
    assert _boot_target("#edge")[1] == "signup"


def test_with_the_account_wall_up_every_closed_link_opens_the_sign_up_and_is_kept():
    """Ethan, 2026-10-25: "people need an account to use the site". Signed
    out with the wall up, a bare visit, a free page and a paid page all open
    the sign-up; the page asked for is kept for after (acctWallTurns). The
    plans, the Record and a reset stay open; a friend's invite keeps its own
    route."""
    assert _boot_target("", door=True) == ("#signup", "signup", None), "a bare visit keeps nothing"
    for h, v in (("#live", "live"), ("#pbp/nfl/401", "pbp"), ("#likely", "likely")):
        assert _boot_target(h, door=True) == ("#signup", "signup", v), h
    for h in ("#record", "#paywall", "#account", "#signup", "#friend/abc"):
        assert _boot_target(h, door=True)[1] is None, h


def test_the_sign_up_screen_leads_with_the_free_account_and_a_way_past_only_without_the_wall():
    body = _fn(ACCOUNT, "signupHTML")
    assert "Create your free account" in body
    assert '${wall ? "" : `<button type="button" class="acct-forgot welcome-skip" data-act="welcomeBrowse">Look around first →</button>`}' in body
    browse = APP[APP.index("window.welcomeBrowse = function"):]
    browse = browse[:browse.index("};")]
    assert "welcomeDone();" in browse and 'location.hash = "#live";' in browse


def test_reals_first_screens_come_before_the_form_once():
    """Ethan's screenshot of Real's first screen: "This is a play", a card,
    "Every big moment in a game becomes one of these", four bars and
    Continue. Four steps, a way past on each, and the form after."""
    steps = ACCOUNT[ACCOUNT.index("function introSteps("):ACCOUNT.index("function introHTML(")]
    for lead in ("This is a play", "Every play has its own thread", "Every game has a room",
                 "Every pick, graded in public"):
        assert lead in steps, lead
    html = _fn(ACCOUNT, "introHTML")
    assert 'data-intro="${last ? "done" : "next"}"' in html and "Create your free account" in html
    assert 'data-act="acctGoLogin"' in html and 'data-intro="skip"' in html
    assert '${i < 3 ? "Example" : ""}' in html, "the example cards say they are examples"
    render = ACCOUNT[ACCOUNT.index("async function renderSignup("):]
    render = render[:render.index("\n}\n")]
    # …unless a plan is already chosen: a buyer goes straight to the form.
    assert render.index("if (!introSeen() && !_pendingPlanPeek())") < render.index("host.innerHTML = signupHTML();")
    bind = _fn(ACCOUNT, "introBind")
    assert "introDone(); host.innerHTML = signupHTML();" in bind, "skip and the last step land on the form for good"


def test_the_records_numbers_on_the_welcome_are_the_records_own():
    """No invented proof: the last step's numbers are read off the public
    Record file, and with no file it says "The Record" and no number."""
    steps = ACCOUNT[ACCOUNT.index("function introSteps("):ACCOUNT.index("function introHTML(")]
    assert "((_introRecord || {}).all_time || {}).overall" in steps
    assert 'fetch("data/record_head.json"' in ACCOUNT
    assert '<div class="wi-record" aria-hidden="true"><b>The Record</b></div>' in steps
    import re as _re
    assert not _re.search(r"\b\d{3,},?\d*–\d", steps.replace("${", "")), "a won-lost written into the code"


def test_a_new_account_picks_its_teams_and_players_next():
    """Ethan, 2026-10-25: after making an account on Real "you're allowed to
    select your favorite players ... and teams you want to follow ... so
    you can get notifications about your favorite players' props being
    posted". Sign-up goes through followStep before it lands; every team
    and player becomes a watch (engine/alerts), which is what the Alerts
    page and the phone already read."""
    app_auth = APP[APP.index("window.acctAuth = async function"):]
    app_auth = app_auth[:app_auth.index("\n};\n")]
    assert 'if (mode === "signup" && window.followStep) return followStep(() => acctLandAfterAuth(say));' in app_auth
    save = ACCOUNT[ACCOUNT.index("async function followSave("):]
    save = save[:save.index("\n}\n")]
    assert 'fetch("/api/alerts/watch"' in save and 'setSetting("teams"' in save
    assert '{ kind: "team", value: t.split(":")[1] }' in save and '{ kind: "player", value: p.name }' in save
    from engine import alerts
    assert f"const FOLLOW_MAX = {alerts.MAX_WATCHES};" in ACCOUNT, "the picker's cap and the watches' cap disagree"
    step = _fn(ACCOUNT, "followStep")
    assert 'state.view !== "signup") return done();' in step, "off the sign-up page it lands as before"


def test_a_username_is_checked_before_the_account_exists():
    """Real asks for the username first, so a taken or rude one has to be
    refused before the account is made, not after."""
    i = SERVER.index("hc, why = SF.handle_problem(conn, handle)")
    j = SERVER.index("create_user(", i - 2000)
    assert i < j, "the account is created before its username is checked"


def test_every_wall_screen_prints_the_helpline_the_footer_would_have():
    """The wall's own screens hide the site footer (body.walled.on-wall),
    so each prints its responsible-gambling line itself."""
    line = "21+ · Not betting advice · Gambling problem? Call <b>1-800-GAMBLER</b>"
    assert line in _fn(ACCOUNT, "signupHTML")
    assert line in _fn(APP, "resetHTML")


def test_the_way_back_from_the_plans_leads_to_live():
    html = (ROOT / "web" / "index.html").read_text()
    assert re.search(r'id="wall-back" href="#live"', html)


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
