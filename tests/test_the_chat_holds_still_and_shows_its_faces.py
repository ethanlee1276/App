"""The game chat holds still and shows its faces (2026-11-18, step XW).

Ethan, with a screenshot of the NYK at TOR room: "It's glitchy and doesn't
show the reactions." What the audit found, in a phone's browser against the
real server:

  - every three-second ask rewrote the scoreboard, the close button, Who
    wins?, the heat, the tickets and the tabs, whether anything had moved
    or not (the header 15 times in 9.5 s of a quiet room). A tap could land
    on a button swapped out under the thumb, the live dot's pulse began
    again each time, and the logos were drawn again. Each part is now
    written only when what it says has changed (chat.js chatPut), and the
    header's frame once per game;
  - on a phone the four faces sat behind a tap on the message, and nothing
    said so. Each message now keeps a small face at its right (Discord's and
    Slack's add-reaction) that opens them; a mouse keeps them on hover;
  - a phone's tap left :hover stuck on a message, so one put away still
    looked picked: the hover tint is the mouse's only;
  - a message's "now" stayed "now" for as long as the room was open;
  - a send made while the poll's ask was out was dropped, so the message
    took up to a poll to show, and Load earlier did nothing; a face, a vote
    or a play's face the server turned down did nothing at all;
  - every send drew the box again, so a phone's keyboard dropped after each
    message; and an ask that left before a face was changed put the old
    count back for a beat.

    python3 tests/test_the_chat_holds_still_and_shows_its_faces.py
    QB_BROWSER_TESTS=1 python3 tests/test_the_chat_holds_still_and_shows_its_faces.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
CHAT = (ROOT / "web" / "js" / "chat.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "chat.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    i = CHAT.index(f"function {name}(")
    return CHAT[i:CHAT.index("\n}\n", i)]


def test_each_part_is_written_only_when_it_changes():
    put = _fn("chatPut")
    assert "if (!el || el._html === html) return;" in put and "el.innerHTML = html;" in put
    head = _fn("chatDrawHead")
    assert "if (head._frame !== key) {" in head
    assert head.count(".innerHTML =") == 1 and head.index("head.innerHTML = frame;") > head.index("if (head._frame !== key) {"), \
        "the frame (title, close button, marks) only when it changes"
    assert head.index("teamMarkIn(lg, abbr, 26)") < head.index("if (head._frame !== key) {"), \
        "compared whole, so a college logo that comes in late still gets drawn"
    # The fallback badge's gradient is named at random on every draw (visuals.js teamMark).
    assert 'const uid = "tm" + Math.random().toString(36).slice(2, 7);' in (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
    assert 'const key = frame.replace(/(id="|url\\(#)[a-z]{2}[a-z0-9]{0,5}/g, "$1");' in head
    for want in ("chatPut(away, score(lv.away_score));", "chatPut(home, score(lv.home_score));",
                 'chatPut(head.querySelector(".gch-mid"), mid);', 'chatPut(head.querySelector(".gch-here"),'):
        assert want in head, want
    for name in ("chatDrawHeat", "chatDrawTix", "chatDrawPoll", "chatDrawTabs"):
        body = _fn(name)
        assert ".innerHTML =" not in body and ".hidden =" not in body and "chatPut(" in body, name
    pull = _fn("chatPull")
    assert pull.index("chatDrawHead();") < pull.index("chatTimes();"), "the times keep up on every ask"
    times = _fn("chatTimes")
    assert '"#gch-sheet .gch-meta time[data-at]"' in times and "if (t.textContent !== w) t.textContent = w;" in times
    assert '<time data-at="${Number(m.at) || 0}">${chatAgo(m.at)}</time>' in _fn("chatMsgHTML")


def test_the_rules_hold_when_run():
    node = shutil.which("node")
    if not node:
        return
    prog = """
      const src = require('fs').readFileSync(process.argv[1], 'utf8');
      const cut = (a) => { const i = src.indexOf(a); return src.slice(i, src.indexOf('\\n}\\n', i) + 2); };
      eval(cut('function chatPut(') + cut('function chatShow('));
      const chatAgo = eval(src.slice(src.indexOf('const chatAgo = ') + 'const chatAgo = '.length, src.indexOf('};', src.indexOf('const chatAgo = ')) + 1));
      let writes = 0, flips = 0;
      const el = { _v: '', _h: false,
        set innerHTML(v) { writes++; this._v = v; }, get innerHTML() { return this._v; },
        set hidden(v) { flips++; this._h = v; }, get hidden() { return this._h; } };
      chatPut(el, 'a'); chatPut(el, 'a'); chatPut(el, 'b'); chatPut(null, 'c');
      chatShow(el, true); chatShow(el, false); chatShow(el, false); chatShow(el, 0);
      const now = Date.now() / 1000;
      console.log(JSON.stringify([writes, el._v, flips, el._h, chatAgo(now - 40), chatAgo(String(now - 50)), chatAgo(now - 7200)]));
    """
    out = subprocess.run([node, "-e", prog, str(ROOT / "web" / "js" / "chat.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [2, "b", 1, True, "now", "1m", "2h"], out.stdout


def test_a_finished_game_nobody_voted_on_says_nothing_about_the_vote():
    poll = _fn("chatDrawPoll")
    assert "if (!v.open && !total) { chatPut(box, \"\"); chatShow(box, false); return; }" in poll
    assert poll.index("chatPotgHTML(CH.potg)") < poll.index("if (!v.open && !total)"), "the fans' player of the game comes first"


def test_a_phone_has_a_face_to_tap_for_the_four():
    msg = _fn("chatMsgHTML")
    assert ('<button type="button" class="gch-addface" data-gch="faces" data-id="${m.id}" aria-label="React or reply">'
            '${CHAT_SMILE}</button></article>') in msg
    assert "const CHAT_SMILE = `<svg" in CHAT
    click = CHAT[CHAT.index("async function chatClick("):]
    assert 'if (act === "faces") return chatSel(Number(t.dataset.id));' in click
    assert "else if (!msg && CH.sel) chatSel(0);" in click[:1400], "a tap off every message puts the tools away"
    assert 'if (act === "reply") { CH.replyTo = Number(t.dataset.id); chatSel(0);' in click
    assert ".gch-addface { display: none; }" in CSS
    phone = CSS[CSS.index("@media (hover: none), (pointer: coarse) {"):]
    phone = phone[:phone.index("\n}\n")]
    assert ".gch-addface { display: grid;" in phone and "grid-template-columns: 36px minmax(0, 1fr) 30px;" in phone
    assert ".gch-msg.sel .gch-addface { visibility: hidden; }" in phone, "open, the tools sit where the face was"
    # The mouse keeps the four on hover, as before.
    assert "@media (hover: hover) and (pointer: fine) { .gch-msg:hover .gch-tools { display: flex; } }" in CSS


def test_the_hover_tint_is_the_mouse_s_only():
    lines = [ln for ln in CSS.splitlines() if ".gch-msg:hover" in ln or ".gch-msg.cont:hover" in ln]
    assert lines and all(ln.startswith("@media (hover: hover) and (pointer: fine) {") for ln in lines), lines
    assert ".gch-msg.sel { background: var(--fill-hover); }" in CSS


def test_a_send_waits_its_turn_and_keeps_the_box():
    pull = _fn("chatPull")
    assert "while (CH.busy) await new Promise((r) => setTimeout(r, 50));" in pull and "if (CH.busy) return;" not in pull
    assert "if (!CH.busy) await chatPull();" in CHAT[CHAT.index("async function chatTick("):]
    send = CHAT[CHAT.index("async function chatSend(form) {"):]
    send = send[:send.index("\n}\n")]
    assert "const chips = CH.replyTo || CH.bet || CH.betOpen || CH.err;" in send
    assert send.index("if (chips) {") < send.index("chatLetGo(form);") < send.index("await chatPull();")
    sheet = _fn("chatSheet")
    assert 's.addEventListener("mousedown", (e) => { if (e.target.closest(".gch-send")) e.preventDefault(); });' in sheet


def test_a_face_is_shown_or_said_and_never_taken_back_by_a_late_ask():
    click = CHAT[CHAT.index("async function chatClick("):]
    for act in ('"react"', '"play"', '"vote"'):
        i = click.index(f"await chatPost({act},")
        assert click[i:click.index("if (act ===", i)].count("if (out.status !== 200) return chatSay(out.error);") == 1, act
    assert "chatSay(msg) {" in CHAT and 'tfToast(msg || "That didn’t go through — try again.")' in CHAT
    assert "CH.reactedAt.set(id, Date.now());" in click
    assert 'chatPut(msg.querySelector(".gch-faces"), chatFacesIn(m));' in click
    assert 'b.classList.toggle("mine", b.dataset.kind === out.mine)' in click, "the four mark the reader's own face too"
    pull = _fn("chatPull")
    assert "const askedAt = Date.now();" in pull
    assert "if (m && !((CH.reactedAt.get(Number(id)) || 0) > askedAt)) m.reacts = faces;" in pull
    assert "outerHTML = chatFacesHTML" not in CHAT, "a moved face rewrites its row in place"


def test_in_a_browser_on_a_phone_the_room_holds_still_and_its_faces_show():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import time
    import rendercheck
    pbp = {"league": "nba", "event_id": "401", "home": "TOR", "away": "NYK", "generated_at": "2026-11-18T01:20:00Z",
           "live": {"state": "live", "period": "Q2", "clock": "7:16", "away_score": 33, "home_score": 38}, "plays": []}
    by = lambda h, c: {"handle": h, "name": "", "color": c, "team": "", "verified": False, "official": False,  # noqa: E731
                       "founder": False, "following": False, "lv": 3}
    msgs: list = []
    reacts = {"n": 0}

    def room(r):
        if not msgs:
            # "now" for its first few seconds, then "1m" while the room is open.
            msgs.extend([{"id": 1, "at": time.time() - 600, "body": "Brunson cooking", "own": False, "reacts": {"fire": 2},
                          "mine": "", "by": by("sam", 1)},
                         {"id": 2, "at": time.time() - 40, "body": "S*** balls", "own": True, "reacts": {}, "mine": "",
                          "by": by("qellys", 2)}])
        q = r.request.url
        after = int(q.split("after=")[1].split("&")[0]) if "after=" in q else 0
        body = {"room": "nba_401", "t": time.time(), "older": False, "reacts": {}, "plays": {}, "threads": {},
                "mine_plays": {}, "votes": {"home": 0, "away": 0, "mine": "", "open": True}, "here": 2,
                "me": {"signed_in": True, "handle": "qellys", "founder": False},
                "messages": [m for m in msgs if m["id"] > after]}
        r.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def react(r):
        reacts["n"] += 1
        if reacts["n"] == 1:
            return r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "mine": "lol"}))
        r.fulfill(status=429, content_type="application/json", body=json.dumps({"error": "Slow down a little."}))

    def send(r):
        text = json.loads(r.request.post_data or "{}").get("body", "")
        msgs.append({"id": 3, "at": time.time(), "body": text, "own": True, "reacts": {}, "mine": "", "by": by("qellys", 2)})
        r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "id": 3}))
    def until(p, js, timeout=15.0):
        # Asked from outside the page: the site's CSP has no 'unsafe-eval',
        # which wait_for_function needs.
        end = time.time() + timeout
        while time.time() < end:
            if p.evaluate(js):
                return
            p.wait_for_timeout(250)
        raise AssertionError(f"never held: {js}")
    srv, port = rendercheck._serve()
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(args=["--no-sandbox"], executable_path="/opt/pw-browsers/chromium")
            p = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                              service_workers="block").new_page()
            errs = []
            p.on("pageerror", lambda e: errs.append(str(e)))
            p.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb.tour', 'done');"
                              " localStorage.setItem('qb_chat_rules_v1', '1'); } catch (e) {}")
            p.route(lambda u: not u.startswith(f"{base}/"), lambda r: r.abort())
            p.route("**/data/pbp/nba_401.json*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                   body=json.dumps(pbp)))
            p.route("**/api/chat/room*", room)
            p.route("**/api/chat/react", react)
            p.route("**/api/chat/send", send)
            p.goto(f"{base}/index.html?sport=nba#pbp/nba/401", wait_until="load")
            p.wait_for_selector(".gch-entry", timeout=20000)
            p.tap(".gch-entry")
            p.wait_for_selector('#gch-sheet .gch-msg[data-id="2"]', timeout=10000)
            n_faces = p.evaluate("[...document.querySelectorAll('#gch-sheet .gch-addface')]"
                                 ".filter((b) => getComputedStyle(b).display !== 'none' && b.getBoundingClientRect().width > 0).length")
            assert n_faces == 2, ("a face to tap on every message", n_faces)
            assert "🔥" in p.inner_text('#gch-sheet .gch-msg[data-id="1"] .gch-faces'), "a used face shows with its count"
            assert p.inner_text('#gch-sheet .gch-msg[data-id="2"] time') == "now"
            # Two asks of a quiet room: nothing in the header, Who wins? or the tabs is written again.
            p.evaluate("""window.__n = 0; window.__x = document.querySelector('#gch-sheet .gch-x');
              window.__vote = document.querySelector('#gch-sheet .gch-vote');
              const mo = new MutationObserver((l) => { window.__n += l.length; });
              for (const sel of ['.gch-head', '.gch-poll', '.gch-tabs'])
                mo.observe(document.querySelector('#gch-sheet ' + sel), {childList: true, subtree: true, characterData: true, attributes: true});""")
            until(p, "document.querySelector('#gch-sheet .gch-msg[data-id=\"2\"] time').textContent === '1m'")
            assert p.evaluate("window.__n") == 0, ("rewritten while nothing moved", p.evaluate("window.__n"))
            assert p.evaluate("window.__x.isConnected && window.__vote.isConnected"), "the same buttons under the thumb"
            # The face opens the four; one tap puts a face on, shown at once and marked as the reader's.
            p.tap('#gch-sheet .gch-msg[data-id="2"] .gch-addface')
            tools = '#gch-sheet .gch-msg[data-id="2"] .gch-tools'
            assert p.evaluate(f"getComputedStyle(document.querySelector('{tools}')).display") == "flex"
            p.tap(f'{tools} .gch-pk[data-kind="lol"]')
            until(p, "(document.querySelector('#gch-sheet .gch-msg[data-id=\"2\"] .gch-faces') || {}).textContent === '😂1'", 5)
            assert p.evaluate(f"getComputedStyle(document.querySelector('{tools}')).display") == "none", "put away once used"
            assert p.evaluate(f"[...document.querySelectorAll('{tools} .gch-pk.mine')].map((b) => b.dataset.kind)") == ["lol"]
            # A face the server turns down is said, not swallowed.
            p.tap('#gch-sheet .gch-msg[data-id="2"] .gch-addface')
            p.tap(f'{tools} .gch-pk[data-kind="wow"]')
            p.wait_for_selector(".tf-toast", timeout=5000)
            assert "Slow down" in p.inner_text(".tf-toast")
            # A tap off every message puts the tools away.
            p.tap("#gch-sheet .gch-poll-q")
            assert p.evaluate("document.querySelectorAll('#gch-sheet .gch-msg.sel').length") == 0
            # A send keeps the box and its focus (a phone's keyboard stays up) and shows at once.
            p.tap("#gch-sheet .gch-input")
            p.keyboard.type("Brunson for MVP")
            p.evaluate("window.__box = document.querySelector('#gch-sheet .gch-input')")
            p.tap("#gch-sheet .gch-send")
            p.wait_for_selector('#gch-sheet .gch-msg[data-id="3"]', timeout=2500)
            assert p.evaluate("window.__box.isConnected && document.activeElement === window.__box && window.__box.value === ''"), \
                "the same box, still focused, emptied"
            assert not errs, errs
            b.close()
    finally:
        srv.shutdown()


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
