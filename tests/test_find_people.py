"""Find people, and an @ that reaches anybody (engine/socialfeed, engine/
gamechat, js/social.js, js/chat.js; Ethan, 2026-10-28: "There should be a
search tab too look up accounts and shit to add people and see there
profile. It shouldn't be just a link share too find the account" and
"@ any profile in a chat should notify them they were mentioned").

  * THE SEARCH TAB (Instagram's, X's, Real's): Social's second tab, on a
    phone too, where the side rail's box never showed. Anybody by @handle
    or name as you type — handles that start with it first, underscores
    matched as letters — each row opening the profile with Follow and Add
    friend on it, the button saying where the two stand (Requested,
    Accept, Message). Before a name is typed, who to add: who follows you,
    who the people you follow follow, then who is popular. Never yourself,
    never past a block.
  * AN @ ANYWHERE: a post's or a comment's @handle pushes like a game
    chat's does, on unless the account said no; the chat's and Social's @
    suggestions offer anybody's handle, not only the room's.

Run directly: `python3 tests/test_find_people.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import gamechat as GC                            # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import pushalerts as PA                          # noqa: E402
from engine import pushmine as PM                            # noqa: E402
from engine import social as SOC                             # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
FCM = "https://fcm.googleapis.com/fcm/send/"
JS = Path(ROOT, "web", "js", "social.js").read_text(encoding="utf-8")
PEOPLE = (("ethan", "Ethan"), ("sam_k", "Sam King"), ("casey", ""), ("drew_99", "Drew"),
          ("jordan", "Jordan Sams"), ("samuel", ""))


def _db():
    K._cache.clear()
    K._graded.clear()
    K._ready.clear()
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    for m in (SF, GC, SOC, K, PM):
        m.ensure_tables(conn)
    ids = {}
    for handle, name in PEOPLE:
        _, out = A.create_user(conn, f"{handle}@example.com", GOOD, confirmed=True)
        ids[handle] = out["id"]
        assert SF.profile_set(conn, out["id"], handle, "", name=name or None)[0] == 200
    return conn, ids


def _handles(rows):
    return [p["handle"] for p in rows]


def _until(page, js: str, timeout: float = 8.0) -> None:
    """Poll ``js`` until it is true: the site's CSP refuses the string
    eval that Playwright's own wait_for_function runs on the page."""
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate(js):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"never true: {js}")


# --- the box ---------------------------------------------------------------------
def test_a_name_finds_handles_that_start_with_it_first_then_names():
    conn, ids = _db()
    me = ids["ethan"]
    SF.toggle_follow(conn, ids["casey"], "jordan")
    got = SF.people(conn, "sam", me)
    assert _handles(got) == ["sam_k", "samuel", "jordan"], "two handles that start with it, then a name"
    assert _handles(SF.people(conn, "@SAM", me)) == ["sam_k", "samuel", "jordan"], "an @ and any case"
    assert _handles(SF.people(conn, "s", me)) == ["sam_k", "samuel", "jordan"], \
        "one letter: a handle's start or a name's word"
    assert _handles(SF.people(conn, "_9", me)) == ["drew_99"], "an underscore is a letter, not a wildcard"
    assert _handles(SF.people(conn, "%", me)) == [], "nor is a percent sign"
    assert SF.people(conn, "", me) == [] and SF.people(conn, "   ", me) == []
    assert _handles(SF.search(conn, "drew_9", me)["people"]) == ["drew_99"], \
        "the rail's search finds them the same way (it stripped the underscore)"


def test_never_yourself_and_never_past_a_block():
    conn, ids = _db()
    me = ids["ethan"]
    assert SF.people(conn, "ethan", me) == []
    assert _handles(SF.people(conn, "ethan", None)) == ["ethan"], "signed out, anybody is findable"
    SF.toggle_block(conn, me, "sam_k")
    SF.toggle_block(conn, ids["samuel"], "ethan")
    assert _handles(SF.people(conn, "sam", me)) == ["jordan"], "a block either way hides"


def test_each_row_says_where_the_two_stand():
    conn, ids = _db()
    me = ids["ethan"]
    SF.toggle_follow(conn, me, "sam_k")
    SF.toggle_follow(conn, ids["jordan"], "ethan")
    SOC.request_send(conn, me, ids["drew_99"])
    SOC.request_send(conn, ids["samuel"], me)
    SOC.request_send(conn, me, ids["casey"])
    SOC.request_send(conn, ids["casey"], me)                 # both asked: friends
    rows = {h: SF.people(conn, h, me)[0] for h in ("sam_k", "jordan", "drew_99", "samuel", "casey")}
    assert rows["sam_k"]["following"] is True and rows["sam_k"]["followers"] == 1
    assert rows["jordan"]["follows_you"] is True and rows["jordan"]["following"] is False
    assert rows["drew_99"]["standing"] == "asked"
    assert rows["samuel"]["standing"] == "asked_me"
    assert rows["casey"]["standing"] == "friend"
    assert all(isinstance(p.get("lv"), int) and p.get("cls") for p in rows.values()), \
        "the karma level the chats show beside a name"
    assert all(set(p) >= {"handle", "name", "color", "following", "follows_you", "standing", "followers"}
               for p in rows.values())
    assert not any("email" in json.dumps(p) or "@example.com" in json.dumps(p) for p in rows.values()), \
        "a row is the public profile, nothing past it"
    code, page = SF.profile_page(conn, "samuel", me)
    assert code == 200 and page["profile"]["standing"] == "asked_me" and page["profile"]["friend"] is False
    assert SF.profile_page(conn, "casey", me)[1]["profile"]["friend"] is True


def test_before_a_name_who_to_add_and_why():
    conn, ids = _db()
    me = ids["ethan"]
    SF.toggle_follow(conn, ids["casey"], "ethan")            # follows me
    SF.toggle_follow(conn, me, "jordan")
    SF.toggle_follow(conn, ids["jordan"], "drew_99")         # someone I follow follows them
    got = SF.people_suggest(conn, me)
    assert [(p["handle"], p["why"]) for p in got[:2]] == [
        ("casey", "Follows you"), ("drew_99", "Followed by someone you follow")], got
    assert "jordan" not in _handles(got), "nobody you follow"
    assert "ethan" not in _handles(got), "never yourself"
    assert all(p["why"] == "Popular on Social" for p in got[2:])
    assert set(_handles(SF.people_suggest(conn, None))) == {h for h, _ in PEOPLE}, "signed out: who is popular"


def test_a_profile_says_who_you_follow_that_follows_it():
    """Instagram's and X's "Followed by @a, @b and 3 others you follow": the
    three latest named, the rest counted, never past a block, nothing for
    nobody signed in."""
    conn, ids = _db()
    me = ids["ethan"]
    for h in ("sam_k", "casey", "drew_99", "jordan"):
        SF.toggle_follow(conn, me, h)
        SF.toggle_follow(conn, ids[h], "samuel")
    got = SF.profile_page(conn, "samuel", me)[1]["profile"]["mutual"]
    assert got == {"names": ["jordan", "drew_99", "casey"], "n": 4}, got
    SF.toggle_block(conn, me, "jordan")
    assert SF.profile_page(conn, "samuel", me)[1]["profile"]["mutual"]["n"] == 3
    assert SF.profile_page(conn, "samuel", None)[1]["profile"]["mutual"] == {"names": [], "n": 0}
    assert "function mutualHTML(m)" in JS and "you follow`;" in JS
    assert '${!o.mine && p.mutual && Number(p.mutual.n) ? `<p class="fd-prof-mut">${mutualHTML(p.mutual)}</p>` : ""}' in JS


# --- an @ anywhere -----------------------------------------------------------------
def _phone(conn, uid):
    code, out = PA.subscribe(conn, FCM + str(uid), kind="web", user_id=uid, topics=["bets"])
    assert code == 200, out
    return out["topics"]


def _pushes(conn, uid):
    return [dict(zip(("id", "title", "body", "url"), r)) for r in conn.execute(
        "SELECT id, title, body, url FROM push_mine WHERE user_id=? ORDER BY at", (uid,))]


def test_a_posts_and_a_comments_mention_push_unless_the_account_said_no():
    conn, ids = _db()
    me, sam, casey = ids["ethan"], ids["sam_k"], ids["casey"]
    for uid in (sam, casey):
        assert "mentions" in _phone(conn, uid), "on until said no"
    SF.set_mention_alerts(conn, casey, False)
    code, out = SF.create_talk(conn, me, "nfl", "Sunday thoughts", "@sam_k @casey who you got")
    assert code == 200, out
    pid = out["post"]["id"] if "post" in out else out["id"]
    assert _pushes(conn, sam) == [{"id": f"feed:{pid}:0", "title": "@ethan mentioned you in a post",
                                   "body": "Sunday thoughts @sam_k @casey who you got",
                                   "url": f"/#feed/post/{pid}"}], _pushes(conn, sam)
    assert _pushes(conn, casey) == [], "said no: Activity only"
    assert [n["kind"] for n in SF.notifications(conn, casey)["items"]] == ["mention"]
    code, c = SF.add_comment(conn, ids["jordan"], pid, "agree with @sam_k")
    assert code == 200, c
    last = _pushes(conn, sam)[-1]
    assert last["title"] == "@jordan mentioned you in a comment" and last["id"].startswith(f"feed:{pid}:"), last
    # The writer never; a block either way stops it.
    SF.toggle_block(conn, sam, "jordan")
    n = len(_pushes(conn, sam))
    SF.add_comment(conn, ids["jordan"], pid, "@sam_k again")
    assert len(_pushes(conn, sam)) == n
    SF.add_comment(conn, sam, pid, "me, @sam_k")
    assert len(_pushes(conn, sam)) == n


def test_a_friend_request_and_its_yes_reach_the_other_side():
    """An Add friend showed only as a count on the Messages icon: the request
    now lands in the other's Activity, opening Messages, and on their phone;
    its yes on the asker's; a no is never said; the phone once a pair; a
    block stops it."""
    conn, ids = _db()
    me, sam, casey = ids["ethan"], ids["sam_k"], ids["casey"]
    for uid in (me, sam, casey):
        _phone(conn, uid)
    assert SOC.request_send(conn, me, sam)[1]["requested"]
    got = [n for n in SF.notifications(conn, sam)["items"] if n["kind"] == "friend_request"]
    assert [(n["handle"], n["link"]) for n in got] == [("ethan", "#messages")], got
    assert _pushes(conn, sam) == [{"id": f"friend_request:{me}:{sam}", "title": "@ethan wants to be friends",
                                   "body": "Say yes in Messages.", "url": "/#messages"}], _pushes(conn, sam)
    rid = conn.execute("SELECT id FROM friend_requests WHERE to_id=?", (sam,)).fetchone()[0]
    assert SOC.request_answer(conn, sam, rid, True)[1]["accepted"]
    assert [n["kind"] for n in SF.notifications(conn, me)["items"]] == ["friend_accept"]
    assert _pushes(conn, me)[-1]["title"] == "@sam_k said yes: you're friends"
    # A no is never said; asked again, Activity again but the phone once a pair.
    SOC.request_send(conn, casey, me)
    rid = conn.execute("SELECT id FROM friend_requests WHERE to_id=?", (me,)).fetchone()[0]
    SOC.request_answer(conn, me, rid, False)
    assert not [n for n in SF.notifications(conn, casey)["items"] if n["kind"] == "friend_accept"]
    pushed = len(_pushes(conn, me))
    SOC.request_send(conn, casey, me)
    assert len(_pushes(conn, me)) == pushed
    # A block stops it.
    SF.toggle_block(conn, ids["jordan"], "ethan")
    SOC.request_send(conn, me, ids["jordan"])
    assert not [n for n in SF.notifications(conn, ids["jordan"])["items"] if n["kind"] == "friend_request"]
    # No username: named in Activity as Messages names it, "Someone" on a lock screen.
    _, nameless = A.create_user(conn, "nameless@example.com", GOOD, confirmed=True)
    SOC.request_send(conn, nameless["id"], sam)
    row = [n for n in SF.notifications(conn, sam)["items"] if n["kind"] == "friend_request"][0]
    assert row["handle"] == "" and row["snippet"] == SOC.display_name(conn, nameless["id"])
    assert _pushes(conn, sam)[-1]["title"] == "Someone wants to be friends"


# --- the pages ------------------------------------------------------------------
def test_the_search_tab_is_second_and_its_page_is_wired():
    nav = JS[JS.index("const NAV = ["):JS.index("];", JS.index("const NAV = ["))]
    assert nav.index('["search", "#feed/search", "search", "Search"]') < nav.index('"following"'), \
        "second, so a phone's row of tabs shows it without a scroll"
    for want in ("function findPageHTML()", "async function findLoad(q)", "function findLive(q)",
                 "function personRowHTML(p)", "function friendBtnHTML(p)", "function inviteCardHTML()",
                 'if (kind === "search") {', 'paint(seq, "search", findPageHTML(), { hero: false });',
                 'if (t.id === "fd-find") findLive(t.value);', 'api(`people?q=${encodeURIComponent(word)}`)',
                 'history.replaceState(history.state, "", `#feed/search'):
        assert want in JS, want
    body = JS[JS.index("function friendBtnHTML(p)"):JS.index("function personRowHTML(p)")]
    for word in ('href="#messages">Message</a>', "disabled>Requested</button>", '"Accept" : "Add friend"'):
        assert word in body, word
    assert "${friendBtnHTML(p)}" in JS[JS.index("function profileHeaderHTML"):], "the profile says the same"
    assert '${route().split("/")[0] === "search" ? ""' in JS, "the rail's box is not twice on the page"
    assert 'go(q ? `search/${encodeURIComponent(q)}` : "search");' in JS
    srv = Path(ROOT, "server.py").read_text(encoding="utf-8")
    assert 'if path == "people":' in srv and "SF.people(conn, q_, uid, n_)" in srv and \
        "SF.people_suggest(conn, uid, n_)" in srv
    acct = Path(ROOT, "web", "js", "account.js").read_text(encoding="utf-8")
    assert 'setItem({ href: "#feed/search", ico: "search", tone: "gold", title: "Find people",' in acct
    css = Path(ROOT, "web", "css", "social.css").read_text(encoding="utf-8")
    for want in (".fd-prow {", ".fd-prow-act {", "@container fd (max-width: 460px)", ".fd-atrow {"):
        assert want in css, want


def test_recent_keeps_the_profiles_opened_from_search_on_the_device():
    for want in ('const FIND_RECENT_KEY = "qb_find_recent";', "function findRecent()", "function findRemember(p, forget)",
                 "(s.suggested ? findRecentHTML() : \"\")", 'data-find="${escapeAttr(p.handle)}"',
                 'const opened = e.target.closest && e.target.closest("a[data-find]");',
                 'if (act === "find-forget" || act === "find-forget-all") {'):
        assert want in JS, want
    body = JS[JS.index("function findRecent()"):JS.index("function findRecentHTML()")]
    assert body.count("try {") == 2 and ".slice(0, 8)" in body, "a device that cannot keep it keeps nothing, eight at most"
    policy = " ".join(Path(ROOT, "web", "privacy.html").read_text(encoding="utf-8").split())
    assert "the profiles you opened from Social’s Search (its Recent list" in policy


def test_activity_words_a_friend_request_and_opens_messages():
    for want in ('friend_request: "wants to be friends"', "friend_accept: \"said yes: you're friends now\"",
                 'const FRIEND_NOTES = ["friend_request", "friend_accept"];', ': fr ? "#messages" :',
                 "<b>Push me mentions, replies and friend requests</b>"):
        assert want in JS, want


def test_the_at_names_reach_past_the_room():
    chat = Path(ROOT, "web", "js", "chat.js").read_text(encoding="utf-8")
    assert "if (out.length < 5 && q) (chatAtFar(q) || []).forEach(add);" in chat
    assert "fetch(`/api/feed/people?q=${encodeURIComponent(q)}&n=5`" in chat
    for want in ("function atDraw(box)", "function atPut(handle)", 'if (act === "at") { atPut(d.handle); return; }',
                 'if (t.id === "fd-comp-text" || /^fd-(cc|rc)-/.test(t.id || "")) atDraw(t);'):
        assert want in JS, want


# --- in a browser -------------------------------------------------------------------
def test_in_a_browser_a_phone_finds_adds_and_opens_a_profile():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    me = {"handle": "ethan", "name": "Ethan", "color": 1}
    suggest = [{"handle": "casey", "name": "Casey", "color": 3, "followers": 4, "why": "Follows you",
                "follows_you": True, "standing": "", "following": False}]
    found = [{"handle": "sam_k", "name": "Sam King", "color": 6, "followers": 2, "standing": "", "following": False},
             {"handle": "samuel", "name": "Samuel", "color": 2, "followers": 0, "standing": "asked_me", "following": False}]
    prof = {"profile": {"handle": "sam_k", "name": "Sam King", "color": 6, "since": 1.7e9, "posts": 0, "tails": 0,
                        "likes": 0, "followers": 2, "following_count": 0, "record": {}, "record30": {},
                        "streak": "", "standing": "asked", "friend": False}, "posts": [], "more": False}
    ful = lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b))  # noqa: E731
    asked = []

    def people(route):
        q = route.request.url.split("q=")[-1].split("&")[0] if "q=" in route.request.url else ""
        body = {"q": q, "people": found} if q else {"q": "", "people": suggest, "suggested": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def friend(route):
        asked.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"requested": True, "already": False}))

    srv, port = rendercheck._serve()
    errs, got = [], {}
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
                page.route("**/api/account/me*", ful(json.dumps({"signed_in": True, "email": "you@example.com",
                                                                  "profile": me})))
                page.route("**/api/feed/me*", ful(json.dumps({"me": me, "signed_in": True, "unseen": 0})))
                page.route("**/api/feed/rail*", ful(json.dumps({"trending": {"picks": [], "active": 0}, "leaders": [],
                                                                "stats": {}, "suggest": [], "tags": []})))
                page.route("**/api/feed/people*", people)
                page.route("**/api/feed/search*", ful(json.dumps({"people": found, "posts": []})))
                page.route("**/api/feed/friend", friend)
                page.route("**/api/feed/profile*", ful(json.dumps(prof)))
                page.route("**/api/social/me*", ful(json.dumps({"invite": {"token": "tok12345"}})))
                page.route("**/api/alerts/**", ful(json.dumps({"players": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html#feed/search", wait_until="load")
                page.wait_for_selector("#fd-find", timeout=15000)
                page.wait_for_timeout(600)
                got["tab"] = page.evaluate("(document.querySelector('.fd-tabs .fd-tab.on') || {}).textContent || ''")
                got["tab_seen"] = page.evaluate("""(() => { const t = document.querySelector('.fd-tabs .fd-tab.on');
                    const r = t && t.getBoundingClientRect(); return !!r && r.right <= innerWidth && r.width > 0; })()""")
                got["suggest"] = page.evaluate("[...document.querySelectorAll('.fd-prow')].map((r) => r.textContent)")
                got["invite"] = page.evaluate("!!document.querySelector('.fd-invite [data-copy-invite]')")
                page.fill("#fd-find", "sam")
                _until(page, "document.querySelectorAll('.fd-prow').length === 2")
                got["hash"] = page.evaluate("location.hash")
                got["accept"] = page.evaluate("[...document.querySelectorAll('.fd-prow [data-fd=\"friend\"]')].map((b) => b.textContent)")
                page.click('.fd-prow [data-fd="friend"][data-handle="sam_k"]')
                _until(page, "[...document.querySelectorAll('.fd-prow button[disabled]')]"
                             ".some((b) => b.textContent === 'Requested')")
                page.click('.fd-prow a[href="#feed/u/sam_k"]')
                page.wait_for_selector(".fd-prof", timeout=8000)
                got["profile"] = page.evaluate("(document.querySelector('.fd-prof-btns') || {}).textContent || ''")
                page.goto(f"http://127.0.0.1:{port}/index.html#feed/search", wait_until="load")
                page.wait_for_selector("#fd-find", timeout=15000)
                _until(page, "document.querySelectorAll('.fd-rchip').length === 1")
                got["recent"] = page.evaluate("[...document.querySelectorAll('.fd-rchip b')].map((b) => b.textContent)")
                page.click('.fd-rchip [data-fd="find-forget"]')
                _until(page, "!document.querySelector('.fd-rchip')")
                got["kept"] = page.evaluate("localStorage.getItem('qb_find_recent')")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert "Search" in got["tab"] and got["tab_seen"], got
    assert len(got["suggest"]) == 1 and "Follows you" in got["suggest"][0], got
    assert got["invite"], "somebody not here yet: the invite link"
    assert got["hash"] == "#feed/search/sam", got
    assert [t.strip() for t in got["accept"]] == ["Add friend", "Accept"], got
    assert asked == [{"handle": "sam_k"}], asked
    assert "Requested" in got["profile"], got
    assert got["recent"] == ["@sam_k"], "opened from Search: under Recent"
    assert got["kept"] == "[]", "forgotten"


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
