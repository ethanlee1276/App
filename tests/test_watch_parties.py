"""Watch parties: a private thread inside a game's chat for a group of
friends, by invite link (docs/IDEAS.md, the live game list's eighth; built
2026-10-28, runbook FW).

What these hold:

  * a party is started in a game's room by an account with a username, at
    most three a game each, named by its starter or after them, with an
    invite token; joining by the token is joining once, a party holds fifty,
    and an unknown token is refused;
  * a party's messages are its members' alone: the room's newest page, its
    poll, its older page, its threads and the Live tab's counts all leave
    them out; a member's poll carries them, a stranger's carries nothing of
    them; a stranger cannot post, react or report into one;
  * the room's rules are the party's (the same caps, the same profanity
    check), a reply stays inside it, and leaving takes a member out;
  * parties go with the room's messages after fourteen days, and deleting
    an account takes its memberships and leaves a party it started to its
    friends, with the starter off it; the privacy policy names both tables;
  * the page: a Party tab beside the room's three, an invite link that
    opens the game with the party on, read by the chat itself off the
    address (kept a day for an account made in between), and a message
    sent from the tab goes to the party;
  * and in a browser, an invite link opens the game's chat on the party,
    with its name, its members and its messages, and a message goes to it.

Run directly: `python3 tests/test_watch_parties.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import accounts as A    # noqa: E402
from engine import gamechat as GC   # noqa: E402
from engine import socialfeed as SF  # noqa: E402

GOOD = "correct-horse-battery"
ROOM = "nfl_401873017"
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    SF.ensure_tables(conn)
    GC.ensure_tables(conn)
    ids = []
    for who in ("ethan", "sam", "casey", "drew", "kai"):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
    conn.execute("UPDATE users SET created_at=created_at-?", (2 * 86400,))
    conn.commit()
    for uid, h in zip(ids[:4], ("ethan", "sam", "casey", "drew")):
        SF.profile_set(conn, uid, h, "")
    return conn, ids


def test_a_party_is_started_named_and_capped():
    conn, ids = _db()
    code, out = GC.party_create(conn, ids[4], ROOM, now=1000.0)
    assert code == 409 and out.get("need_handle"), "a username first"
    assert GC.party_create(conn, ids[0], "xfl_1", now=1000.0)[0] == 400
    code, p = GC.party_create(conn, ids[0], ROOM, now=1000.0)
    assert code == 200 and p["name"] == "ethan’s party" and p["members"] == 1 and GC.PARTY_RE.match(p["token"]), p
    code, named = GC.party_create(conn, ids[0], ROOM, "  Sunday   crew ", now=1001.0)
    assert code == 200 and named["name"] == "Sunday crew" and named["token"] != p["token"]
    assert GC.party_create(conn, ids[0], ROOM, "x", now=1002.0)[0] == 200
    code, out = GC.party_create(conn, ids[0], ROOM, "y", now=1003.0)
    assert code == 429 and "3" in out["error"], "three a game"
    assert GC.party_create(conn, ids[0], "nfl_9", "other game", now=1004.0)[0] == 200, "the cap is per game"


def test_an_invite_joins_once_and_a_party_holds_fifty():
    conn, ids = _db()
    _, p = GC.party_create(conn, ids[0], ROOM, now=1000.0)
    assert GC.party_join(conn, ids[1], "nope", now=1001.0)[0] == 404
    assert GC.party_join(conn, ids[1], "short", now=1001.0)[0] == 404
    code, j = GC.party_join(conn, ids[1], p["token"], now=1001.0)
    assert code == 200 and j["id"] == p["id"] and j["members"] == 2 and j["room"] == ROOM
    assert GC.party_join(conn, ids[1], p["token"], now=1002.0)[1]["members"] == 2, "twice is once"
    conn.executemany("INSERT INTO chat_party_members (party_id, user_id, joined_at) VALUES (?,?,?)",
                     [(p["id"], 1000 + i, 1003.0) for i in range(GC.PARTY_MAX - 2)])
    code, out = GC.party_join(conn, ids[2], p["token"], now=1004.0)
    assert code == 409 and "full" in out["error"]
    assert GC.party_join(conn, ids[1], p["token"], now=1005.0)[0] == 200, "a member is never turned away"


def test_a_party_s_messages_are_its_members_alone():
    conn, ids = _db()
    _, p = GC.party_create(conn, ids[0], ROOM, "Sunday crew", now=1000.0)
    GC.party_join(conn, ids[1], p["token"], now=1001.0)
    assert GC.send(conn, ids[2], ROOM, "public hello", now=1002.0)[0] == 200
    code, out = GC.send(conn, ids[2], ROOM, "sneaking in", party=p["id"], now=1006.0)
    assert code == 403, "a stranger cannot post into it"
    assert GC.send(conn, ids[0], ROOM, "party only", party=p["id"], now=1010.0)[0] == 200
    assert GC.send(conn, ids[1], ROOM, "on this play", play="4018730171234", party=p["id"], now=1014.0)[0] == 200
    pid = conn.execute("SELECT id FROM chat_msgs WHERE body='party only'").fetchone()[0]
    # A reply stays in its party; a reply into a party from the room is refused.
    assert GC.send(conn, ids[1], ROOM, "agreed", reply_to=pid, party=p["id"], now=1018.0)[0] == 200
    assert GC.send(conn, ids[1], ROOM, "leak", reply_to=pid, now=1022.0)[0] == 404
    # The room's own reads: none of it.
    for viewer in (ids[0], ids[2], None):
        _c, v = GC.room_view(conn, ROOM, viewer, now=1030.0)
        assert [m["body"] for m in v["messages"]] == ["public hello"], v["messages"]
        assert "4018730171234" not in v["threads"], "a party's thread is not the room's"
    _c, v = GC.room_view(conn, ROOM, ids[2], after=1, now=1030.0)
    assert [m["body"] for m in v["messages"]] == [] or all(m["body"] == "public hello" for m in v["messages"])
    assert GC.counts(conn, [ROOM], now=1030.0)[ROOM]["recent"] == 1, "the Live tab's count is the room's"
    # A member's poll carries the party; a stranger asking for it gets nothing of it.
    _c, mine = GC.room_view(conn, ROOM, ids[1], party=p["id"], now=1030.0)
    assert [x["name"] for x in mine["parties"]] == ["Sunday crew"]
    assert [m["body"] for m in mine["party"]["messages"]] == ["party only", "on this play", "agreed"]
    _c, after = GC.room_view(conn, ROOM, ids[1], party=p["id"], pafter=pid, now=1031.0)
    assert [m["body"] for m in after["party"]["messages"]] == ["on this play", "agreed"]
    _c, theirs = GC.room_view(conn, ROOM, ids[2], party=p["id"], now=1030.0)
    assert "party" not in theirs and theirs["parties"] == []
    _c, anon = GC.room_view(conn, ROOM, None, party=p["id"], now=1030.0)
    assert "party" not in anon and "parties" not in anon
    # Nor can a stranger react to or report a party's message.
    assert GC.react(conn, ids[2], pid, "fire", now=1032.0)[0] == 404
    assert GC.report(conn, ids[2], pid, "spam", now=1032.0)[0] == 404
    assert GC.react(conn, ids[1], pid, "fire", now=1032.0)[0] == 200


def test_the_room_s_rules_hold_in_a_party_and_leaving_takes_you_out():
    conn, ids = _db()
    _, p = GC.party_create(conn, ids[0], ROOM, now=1000.0)
    code, out = GC.send(conn, ids[0], ROOM, "x", party=p["id"], now=1000.5)
    code2, _ = GC.send(conn, ids[0], ROOM, "y", party=p["id"], now=1001.0)
    assert code == 200 and code2 == 429, "one message every few seconds, in a party too"
    code, out = GC.party_create(conn, ids[1], ROOM, "fuck this", now=1002.0)
    assert code == 200 and "fuck" not in out["name"], "a name is masked: every member sees it"
    GC.party_join(conn, ids[2], p["token"], now=1003.0)
    GC.party_leave(conn, ids[2], p["id"])
    assert GC.my_parties(conn, ids[2], ROOM) == []
    assert GC.send(conn, ids[2], ROOM, "still here?", party=p["id"], now=1010.0)[0] == 403


def test_parties_are_swept_and_go_with_an_account_as_the_policy_says():
    conn, ids = _db()
    _, p = GC.party_create(conn, ids[0], ROOM, now=1000.0)
    GC.party_join(conn, ids[1], p["token"], now=1001.0)
    A.delete_user(conn, ids[0])
    row = conn.execute("SELECT user_id FROM chat_parties WHERE id=?", (p["id"],)).fetchone()
    assert row is not None and row[0] == 0, "the party stays for its friends, its starter off it"
    assert [x["id"] for x in GC.my_parties(conn, ids[1], ROOM)] == [p["id"]]
    assert not conn.execute("SELECT 1 FROM chat_party_members WHERE user_id=?", (ids[0],)).fetchone()
    GC._prune(conn, 1000.0 + GC.KEEP_DAYS * 86400 + 10)
    assert not conn.execute("SELECT 1 FROM chat_parties").fetchone()
    assert not conn.execute("SELECT 1 FROM chat_party_members").fetchone()
    privacy = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    assert "<code>chat_parties</code>" in privacy and "<code>chat_party_members</code>" in privacy


def test_the_server_routes_a_party_and_its_poll():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"party", "join", "leave"):' in src
    assert "party=_int(one(\"party\")), pafter=_int(one(\"pafter\")))" in src
    assert "reply_to=_int(body.get(\"reply_to\")) or None, party=_int(body.get(\"party\")))" in src
    for call in ("GC.party_create(conn, uid, room,", "GC.party_join(conn, uid,", "GC.party_leave(conn, uid,"):
        assert call in src, call


def _fn(src, name):
    i = src.index(f"function {name}(")
    if src[i - 6:i] == "async ":
        i -= 6
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_page_has_a_party_tab_and_reads_its_invite():
    assert '["party", CH.party ? `Party · ${CH.party.name}` : "Watch party"]' in CHAT
    mount = _fn(CHAT, "chatMount")
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert ('if (parts[2] === "party" && parts[3]) window._chatWantParty = '
            '{ room: `${parts[0]}_${parts[1]}`, token: parts[3] };') in app, "the router hands the invite over"
    assert "const inv = window._chatWantParty;" in mount and "/^[A-Za-z0-9_-]{8,40}$/.test(inv.token)" in mount
    assert "kept.room === room && Date.now() - kept.at < 86400000" in mount, "an invite waits a day for an account"
    send = _fn(CHAT, "chatSend")
    assert 'const party = CH.tab === "party" && !CH.thread && CH.party ? CH.party.id : 0;' in send
    pull = _fn(CHAT, "chatPull")
    assert 'q.set("party", String(CH.party.id)); if (CH.pLastId) q.set("pafter", String(CH.pLastId));' in pull
    body = _fn(CHAT, "chatPartyHTML")
    assert "chEsc(p.name)" in body and "chEsc(p.members)" in body
    node = shutil.which("node")
    if not node:
        return
    prog = f"""
      const location = {{ origin: "https://qellysbook.com" }};
      const CH = {{ league: "nfl", event: "401" }};
      {_fn(CHAT, "chatPartyLink")}
      console.log(JSON.stringify(chatPartyLink({{ token: "Ab_9-xyz123" }})));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == "https://qellysbook.com/#pbp/nfl/401/party/Ab_9-xyz123"


# --- in a browser (opt-in) ------------------------------------------------------------------
def test_in_a_browser_an_invite_opens_the_party():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    live = {"state": "live", "period": "Q2", "clock": "4:12", "away_score": 7, "home_score": 3}
    pbp = {"league": "nfl", "event_id": "401", "home": "ATL", "away": "SF", "generated_at": "2026-10-25T17:00:00Z",
           "live": live, "plays": [], "drives": []}
    me = {"signed_in": True, "email": "you@example.com", "profile": {"handle": "fan0"}}
    party = {"id": 7, "room": "nfl_401", "name": "Sunday crew", "token": "Ab_9-xyz123", "members": 3}
    person = {"handle": "sam", "display_name": "", "color": "", "fav_team": "", "verified": False, "founder": False}
    pm = [{"id": 51, "at": 1792947600, "body": "who has the dip?", "by": person, "own": False, "reacts": {}, "mine": ""}]
    sent, joined = [], []

    def room(route):
        body = {"room": "nfl_401", "t": 1792947600, "messages": [], "older": False, "reacts": {}, "plays": {},
                "threads": {}, "mine_plays": {}, "votes": {"home": 0, "away": 0, "mine": "", "open": True},
                "vote_path": [], "here": 3, "me": {"signed_in": True, "handle": "fan0", "founder": False},
                "parties": [party]}
        if "party=7" in route.request.url:
            body["party"] = {"id": 7, "messages": pm}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def post(route):
        data = json.loads(route.request.post_data or "{}")
        if route.request.url.endswith("/join"):
            joined.append(data)
            out = party
        else:
            sent.append(data)
            out = {"ok": True, "id": 52}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(out))
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            b = pw.chromium.launch(**kw)
            try:
                p = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  service_workers="block").new_page()
                errs = []
                p.on("pageerror", lambda e: errs.append(str(e)))
                p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');"
                                  " localStorage.setItem('qb_chat_rules_v1', '1'); } catch (e) {}")
                p.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                mk = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))  # noqa: E731
                p.route("**/data/pbp/nfl_401.json*", mk(pbp))
                p.route("**/api/account/me*", mk(me))
                p.route("**/api/chat/room*", room)
                p.route("**/api/chat/join", post)
                p.route("**/api/chat/send", post)
                p.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#pbp/nfl/401/party/Ab_9-xyz123", wait_until="load")
                p.wait_for_selector("#gch-sheet .gch-party-bar", timeout=20000)
                p.wait_for_selector("#gch-sheet .gch-msg", timeout=10000)
                got = p.evaluate("""() => ({
                  tab: document.querySelector('#gch-sheet .gch-tab.on').textContent.trim(),
                  bar: document.querySelector('#gch-sheet .gch-party-bar').textContent.replace(/\\s+/g, ' ').trim(),
                  msgs: [...document.querySelectorAll('#gch-sheet .gch-msg')].map((m) => m.textContent.replace(/\\s+/g, ' ').trim()),
                  hash: location.hash,
                  ph: document.querySelector('#gch-sheet .gch-input').getAttribute('placeholder') })""")
                assert joined == [{"room": "nfl_401", "token": "Ab_9-xyz123"}], joined
                assert got["tab"] == "Party · Sunday crew", got
                assert "Sunday crew" in got["bar"] and "3 in it" in got["bar"] and "Invite" in got["bar"], got
                assert any("who has the dip?" in m for m in got["msgs"]), got
                assert got["hash"] == "#pbp/nfl/401", "the game's own address, the invite used"
                assert got["ph"] == "Message the party", got
                p.fill("#gch-sheet .gch-input", "I do")
                p.click("#gch-sheet .gch-send")
                p.wait_for_timeout(800)
                assert sent and sent[0]["party"] == 7 and sent[0]["body"] == "I do", sent
                assert not errs, errs
            finally:
                b.close()
    finally:
        srv.shutdown()


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
