"""The game chat, out of the corner and rebuilt (js/chat.js, css/chat.css).

Ethan, 2026-10-25: "I feel like it's hidden in the corner of the live page,
so it's hard to see ... and then also make the actual chat look better,
like it's very buggy and weird looking ... look at other websites and how
chats work." What these hold:

  - every game page leaves a slot under its scoreboard (the shared page,
    basketball's and hockey's own), filled with the chat's card on every
    draw: who is watching, the last messages, the split, Join;
  - on a phone the way in is a bar across the bottom with the newest
    message, not a pill in a corner, and it steps aside while the card is
    on screen;
  - on a computer the room docks under the site's bar, and the page moves
    over only where its layout still fits;
  - a message carries the faces somebody used and no others; its tools are
    on hover or a tap; one author's run inside three minutes is one block.

    python3 tests/test_the_chat_is_easy_to_find_and_reads_like_a_chat.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = lambda n: (ROOT / "web" / "js" / n).read_text()            # noqa: E731
CHAT, CSS = JS("chat.js"), (ROOT / "web" / "css" / "chat.css").read_text()


def test_every_game_page_leaves_the_card_a_slot_under_the_scoreboard():
    det = JS("detail.js")
    hero = det[det.index("${pbpBoardHTML(d, league, lv)}"):]
    assert '<div class="gch-entry-slot"></div>' in hero[:hero.index('<div class="card pbp-parkcard">')]
    # Every game being watched; an old game's page has no room and no slot
    # (2026-10-30, engine/gamearchive; tests/test_every_game_has_a_page.py).
    assert '${scoreboardHTML(d, league, k)}${d.archive ? "" : `<div class="gch-entry-slot"></div>`}' in JS("hoopscast.js")
    assert '${scoreboardHTML(d, k)}<div class="gch-entry-slot"></div>' in JS("rinkcast.js")
    wire = det[det.index("  const wire = () => {"):]
    assert 'if (typeof chatEntryPaint === "function") chatEntryPaint();' in wire[:400], \
        "filled on every draw, whichever layout drew it (the arenas call the same wire)"


def test_the_card_and_the_bar_say_who_is_here_and_what_was_said():
    fn = CHAT[CHAT.index("function chatEntryPaint("):]
    fn = fn[:fn.index("\n}\n")]
    # Held back with the page while "Watching on TV" is on (chatReady).
    assert "CH.msgs.filter((m) => m.body && chatReady(m)).slice(-3)" in fn and "watching" in fn and "Join</span>" in fn
    assert "chEsc(String(m.body).slice(0, 90))" in fn and "chEsc((m.by || {}).handle" in fn
    assert 'document.body.classList.toggle("gch-card-in"' in fn
    fab = CHAT[CHAT.index("function chatFab("):CHAT.index("function chatEntryPaint(")]
    assert "chatEntryPaint();" in fab and "gch-fab-last" in fab and "chEsc(String(last.body).slice(0, 80))" in fab
    assert "body.gch-card-in .gch-fab { display: none; }" in CSS.replace(".gch-fab[hidden], ", "")
    phone = CSS[CSS.index("@media (max-width: 760px) {\n  .gch-fab {"):]
    assert "left: 10px; right: 10px; width: auto;" in phone[:200], "a bar across, not a pill in the corner"


def test_the_card_is_one_button_kept_across_redraws():
    """2026-10-26 (Ethan: the chat's buttons "glitch out"): the card was
    rebuilt on every redraw and every poll, about every two seconds, so a
    tap mid-rebuild hit a button that was gone. One button now lives for the
    visit, moved into each new slot, its words rewritten only when they
    change; the bar is rewritten only when it changes too."""
    fn = CHAT[CHAT.index("function chatEntryPaint("):]
    fn = fn[:fn.index("\n}\n")]
    assert "if (!CH.card) {" in fn and 'CH.card.addEventListener("click", () => chatOpen({}));' in fn
    assert "if (CH.cardHTML !== html) { CH.cardHTML = html; CH.card.innerHTML = html; }" in fn
    assert "if (CH.card.parentNode !== slot) slot.replaceChildren(CH.card);" in fn
    assert "slot.innerHTML" not in fn, "the card is never rebuilt from a string"
    fab = CHAT[CHAT.index("function chatFab("):CHAT.index("function chatEntryPaint(")]
    assert "if (f._html !== html) { f._html = html; f.innerHTML = html; }" in fab


def test_on_a_computer_the_room_docks_under_the_header():
    assert ".gch-sheet { inset: var(--topbar-h) 0 0 auto;" in CSS
    assert "@media (min-width: 1440px) { body.gch-on { padding-right: 400px; } }" in CSS


def test_faces_only_when_used_tools_on_hover_or_tap_and_runs_grouped():
    faces = CHAT[CHAT.index("function chatFacesHTML("):CHAT.index("const chatPickHTML")]
    assert "CHAT_FACES.filter(([k]) => (faces[k] || 0) > 0)" in faces
    msg = CHAT[CHAT.index("function chatMsgHTML(m, prev) {"):CHAT.index("function chatMenuHTML(")]
    assert '<div class="gch-tools">${chatPickHTML(m)}' in msg and 'data-gch="reply"' in msg
    assert '@media (hover: hover) and (pointer: fine) { .gch-msg:hover .gch-tools { display: flex; } }' in CSS
    assert ".gch-msg.sel .gch-tools { display: flex; }" in CSS
    click = CHAT[CHAT.index("async function chatClick("):]
    assert "chatSel(Number(msg.dataset.id))" in click[:900]
    assert "rows.map((m, i) => chatMsgHTML(m, rows[i - 1]))" in CHAT
    node = subprocess.run(["node", "-e", """
      const src = require('fs').readFileSync(process.argv[1], 'utf8');
      const CH = { thread: "" };
      const s = src.slice(src.indexOf('const chatJoins'), src.indexOf('const chatClock'));
      const chatJoins = eval(s.replace('const chatJoins = ', '').replace(/;\\s*$/, ''));
      const a = { by: { handle: 'x' }, at: 100 }, b = { by: { handle: 'x' }, at: 150 }, c = { by: { handle: 'y' }, at: 160 };
      const r = { by: { handle: 'x' }, at: 170, reply_to: 3 }, late = { by: { handle: 'x' }, at: 500 };
      console.log(JSON.stringify([chatJoins(b, a), chatJoins(c, b), chatJoins(r, a), chatJoins(late, a), chatJoins(a, null)]));
    """, str(ROOT / "web" / "js" / "chat.js")], capture_output=True, text=True)
    if node.returncode == 127 or "not found" in node.stderr:
        return
    assert node.returncode == 0, node.stderr
    assert json.loads(node.stdout) == [True, False, False, False, False]


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
