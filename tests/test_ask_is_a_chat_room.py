"""The Ask page is a chat room.

Ethan, 2026-09-23, a screenshot of the Ask page with the site footer
circled: "Get rid of all this shit down here and make this look more like
an actual ai chat room."

  * THE FOOTER LEAVES while Ask is open (body.ask-open, toggled on every
    view switch so it comes back the moment another page opens); the
    league row stays as text tabs, as his later render draws it;
  * ONE COLUMN between the top bar and the tab bar: a header, the
    conversation (the only thing that scrolls) and the composer pinned at
    the foot, measured by askRoomSize the way a message thread is;
  * bubbles: the reader's on the right in the brand, Ask's on the left
    beside its avatar; bouncing dots while it thinks, then the answer
    typed out;
  * THE EMPTY ROOM IS HIS RENDER (2026-09-23): the AI pill, "Ask Qellys"
    with Qellys in gold, the robot card, three question cards with icons,
    and the box with a working paperclip and a gold send button;
  * THE ONE FOOTER LINE THAT MUST STAY rides in the intro card: not
    betting advice, 21+, the helpline.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
HTML = (ROOT / "web" / "index.html").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_footer_leaves_and_the_league_row_stays_as_text_tabs():
    """The footer leaves while Ask is open. The league row came back with
    Ethan's render, which draws it: text tabs, the open league underlined in
    gold — on a phone too, instead of the crest carousel."""
    assert "body.ask-open .footer { display: none; }" in CSS
    assert "body.ask-open .sportbar {" not in CSS and "body.ask-open .footer, body.ask-open .sportbar" not in CSS
    assert "body.ask-open { padding-bottom: 0; }" in CSS, "no band of scroll under the room"
    assert "body.ask-open #view-ask { padding-bottom: 0; }" in CSS
    phone = CSS[CSS.index("body.ask-open .footer { display: none; }"):]
    phone = phone[:phone.index("\n}\n")]
    assert "body.ask-open .sportbar-in .sport-btn .crest { display: none; }" in phone
    assert "body.ask-open .sportbar-in .sport-btn.active { color: var(--gold); border-bottom-color: var(--gold); }" in phone
    sw = _fn("_switchViewNow")
    assert 'document.body.classList.toggle("ask-open", name === "ask");' in sw, \
        "toggled on EVERY switch, so the footer comes back on the next page"


def test_one_column_the_conversation_then_the_composer():
    r = _fn("renderAsk")
    order = ['<div class="ask-room${empty ? " is-empty" : ""}" id="ask-room">', 'class="ask-log" id="ask-log"',
             '<div class="ask-dock">', '<form class="ask-form" id="ask-form">']
    at = [r.index(s) for s in order]
    assert at == sorted(at), "the conversation, then the composer"
    assert '${empty ? "" : `<div class="ask-head">${title}' in r, "a conversation folds the title into one line"
    assert 'data-ask-reset>New chat</button>' in r, "starting over is the header's button"
    assert 'rows="1"' in r and '<button class="ask-send" type="submit" aria-label="Send" disabled>' in r
    assert "askRoomSize();" in r and "setTimeout(askRoomSize, 400);" in r
    assert re.search(r"(?m)^\.ask-room \{ display: flex; flex-direction: column;", CSS)
    assert re.search(r"\.ask-log \{[^}]*flex: 1; min-height: 0; overflow-y: auto;", CSS), "only the log scrolls"
    assert re.search(r"\.ask-dock \{[^}]*flex-shrink: 0;[^}]*border-top: var\(--hairline\)", CSS), \
        "the composer never scrolls away, across a hairline"
    view = HTML[HTML.index('<section class="view" id="view-ask">'):]
    view = view[:view.index("</section>")]
    assert "section-title" not in view, "the room draws its own header"


def test_the_room_is_measured_clear_of_the_tab_bar_and_the_keyboard():
    size = _fn("askRoomSize")
    assert 'document.querySelector(".tabbar")' in size
    assert '[...tab.querySelectorAll("*")]' in size, "the raised Live button stands proud of the bar"
    assert 'document.body.classList.contains("ask-typing")) return;' in size, \
        "with a keyboard up, askKeyboard sizes it (tests/test_ask_keyboard.py)"
    assert 'log.scrollTop = el.classList.contains("is-empty") ? 0 : log.scrollHeight;' in size, \
        "a conversation opens on its newest message, the empty room on its title"
    assert 'window.visualViewport.addEventListener("resize"' in APP
    assert 'window.addEventListener("resize", () => { if (state.view === "ask") { askKeyboard(); askRoomSize(); } });' in APP


def test_bubbles_an_avatar_a_typing_row_and_a_send_that_wakes():
    turn = _fn("askTurnHTML")
    assert '<div class="ask-row ${who}">${who === "me" ? "" : ASK_AVA}' in turn, "Ask's turns carry its avatar"
    assert 'src="logo-qb.png"' in APP[APP.index("const ASK_AVA"):][:200]
    assert re.search(r"\.ask-row\.me \{[^}]*justify-content: flex-end;", CSS)
    assert re.search(r"\.ask-turn\.me \{[^}]*background: var\(--brand\); color: var\(--brand-ink\);", CSS)
    assert re.search(r"\.ask-turn\.bot \{[^}]*background: var\(--panel-2\);", CSS)
    r = _fn("renderAsk")
    assert '<span class="ask-dots"' in r and "Looking it up…" in r
    assert "@media (prefers-reduced-motion: no-preference) {\n  .ask-dots i { animation: askDot" in CSS, \
        "the dots only move for readers who allow motion"
    assert "if (send) send.disabled = a.busy || !input.value.trim();" in r
    assert "input.style.height = `${Math.min(input.scrollHeight, 132)}px`;" in r, "the box grows, to five lines"


def test_it_thinks_in_dots_and_then_types_the_answer_out():
    """Ethan, 2026-09-23: "We should add the 3 dots that wiggle when the chat
    bot is thinking and typing too to make it feel more real." """
    r = _fn("renderAsk")
    wait = r[r.index('<div class="ask-turn bot wait">'):]
    wait = wait[:wait.index("</div></div>")]
    assert '<span class="ask-sr">Looking it up…</span>' in wait, "only the dots show; the words are for screen readers"
    assert "askTypeOut();" in r, "every render hands the newest answer to the typist"
    assert re.search(r"\.ask-sr \{[^}]*clip-path: inset\(50%\)", CSS)
    assert re.search(r"@keyframes askDot \{.*translateY\(-5px\)", CSS), "a hop you can see"
    send = _fn("askSend")
    assert "const beat = ASK_THINK_MS - (Date.now() - asked);" in send, "the dots show even for a cached answer"
    assert "if (!turn.error) _askTyping = turn;" in send, "an error is a sentence, not a performance"
    assert send.index("_askTyping = turn") < send.index("a.turns.push(turn)")
    think = int(re.search(r"const ASK_THINK_MS = (\d+);", APP).group(1))
    assert 400 <= think <= 1200, think
    turn = _fn("askTurnHTML")
    assert 'if (t === _askTyping) {' in turn and 'class="ask-turn bot typing" id="ask-typing"' in turn
    typer = _fn("askTypeOut")
    assert 'matchMedia("(prefers-reduced-motion: reduce)").matches) { done(); return; }' in typer
    assert 'log.setAttribute("aria-busy", "true");' in typer and 'log.removeAttribute("aria-busy");' in typer, \
        "a screen reader hears the answer once, whole"
    assert "if (!bub.isConnected || _askTyping !== t) return;" in typer, "a re-render shows it whole instead"
    assert "askSourcesHTML(t)" in typer[typer.index("const done"):typer.index("if (window.matchMedia")], \
        "the source chips arrive when the typing ends"
    assert "ASK_SENTENCE_MS : ASK_WORD_MS" in typer, "a beat longer after each sentence"
    assert "if (low) log.scrollTop = log.scrollHeight;" in typer, "it follows the words unless you scrolled up"
    anim = CSS[CSS.index("@media (prefers-reduced-motion: no-preference) {\n  .ask-dots i"):]
    anim = anim[:anim.index("\n}\n")]
    assert ".ask-turn.typing p:last-child::after { animation: askCaret" in anim, "the caret blinks only with motion allowed"


def test_the_empty_room_is_ethans_render():
    """Ethan, 2026-09-23: "Here is a render of what the Qellys chat room
    need[s] to look like." Top to bottom: the AI pill, "Ask Qellys" with
    Qellys in gold, two lines under it, the robot card, three question
    cards with icons side by side, and the box with a paperclip, a divider
    and a gold send button with a paper plane."""
    r = _fn("renderAsk")
    empty = r[r.index('<div class="ask-empty">'):r.index("a.turns.map(askTurnHTML)")]
    order = ["${title}", '<h2 class="ask-title">Ask <em>Qellys</em></h2>',
             "<span>Your AI betting assistant.</span>", '<div class="ask-intro">', 'askIcon("robot", 34)',
             "<b>Ask about any team, player or game.</b>", '<div class="ask-suggest">']
    at = [empty.index(s) for s in order]
    assert at == sorted(at), order
    assert 'const title = `<span class="ask-pill">AI</span>`;' in r
    assert "const sug = a.pick ? ASK_SUGGEST_PICK : ASK_SUGGEST;" in r, "three cards, as drawn"
    assert "ASK_SUGGEST_PAST" not in APP
    assert 'const ASK_SUGGEST_ICONS = ["bars", "doc", "trend"];' in APP
    assert "askIcon(ASK_SUGGEST_ICONS[n % ASK_SUGGEST_ICONS.length], 26)" in empty
    assert re.search(r"\.ask-suggest \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)", CSS), \
        "side by side, a phone included"
    assert re.search(r"\.ask-title-sm em, \.ask-title em \{[^}]*color: var\(--gold\)", CSS), "Qellys in gold"
    assert re.search(r"\.ask-pill \{[^}]*border: var\(--hairline\) solid var\(--gold\); color: var\(--gold\)", CSS)
    assert re.search(r"\.ask-title \{[^}]*font-size: clamp\(var\(--fs-4xl\), 11\.5vw, 60px\)", CSS)
    form = r[r.index('<form class="ask-form" id="ask-form">'):r.index("</form>")]
    assert form.index("data-ask-clip") < form.index("<textarea") < form.index('class="ask-send"'), \
        "paperclip, the box, the send button"
    assert 'askIcon("clip", 22)' in form and 'askIcon("plane", 22)' in form
    assert 'placeholder="Ask about a player, a game or a bet…"' in form
    assert re.search(r"\.ask-clip \{[^}]*border-right: var\(--hairline\) solid var\(--border\)", CSS), "the divider"
    assert re.search(r"\.ask-send \{[^}]*background: var\(--gold\); color: var\(--brand-ink\)", CSS)
    assert ".ask-send:disabled { cursor: default; }" in CSS, "gold even before anything is typed, as drawn"


def test_the_paperclip_attaches_one_of_tonights_picks():
    """A paperclip that attached nothing would be a drawing of a control. It
    attaches one of tonight's props — the attachment a prop page's Ask
    button makes — so the question is asked about that pick."""
    pool = _fn("askAttachable")
    assert "propsRows(state.data).slice(0, 12)" in pool and "id: propId(r)" in pool
    r = _fn("renderAsk")
    assert '<div class="ask-attach" id="ask-attach" role="dialog" aria-label="Attach a pick" hidden></div>' in r
    assert "sheet.innerHTML = askAttachHTML();" in r, "filled when opened: the board may land after the room is drawn"
    assert 'a.pick = b.dataset.askAttach || "";' in r and "askSave(); renderAsk();" in r
    assert 'clip.setAttribute("aria-expanded", open ? "true" : "false");' in r
    att = _fn("askAttachHTML")
    assert "Nothing on tonight’s board to attach yet." in att, "an empty board says so"
    closer = APP[APP.index("/* The attach list closes on a tap anywhere else, or Escape. */"):][:900]
    assert 'document.addEventListener("click"' in closer and 'e.key !== "Escape"' in closer


def test_the_one_footer_line_that_must_stay_rides_in_the_intro_card():
    """The render has nothing under the box, so the line that must stay —
    not betting advice, 21+, the helpline — moved into the robot card."""
    r = _fn("renderAsk")
    intro = r[r.index('<div class="ask-intro">'):r.index('<div class="ask-suggest">')]
    assert '<p class="ask-fine">Not betting advice. <span class="ask-help">21+ · 1-800-GAMBLER</span></p>' in intro
    assert ".ask-help { white-space: nowrap; }" in CSS, "the number never breaks across lines"
    assert 'class="ask-note"' not in APP


if __name__ == "__main__":
    import sys
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
