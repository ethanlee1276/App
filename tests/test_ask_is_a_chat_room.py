"""The Ask page is a chat room.

Ethan, 2026-09-23, a screenshot of the Ask page with the site footer
circled: "Get rid of all this shit down here and make this look more like
an actual ai chat room."

  * THE FOOTER AND THE LEAGUE STRIP LEAVE while Ask is open
    (body.ask-open, toggled on every view switch so they come back the
    moment another page opens) — Ask answers for every league anyway;
  * ONE COLUMN between the top bar and the tab bar: a header, the
    conversation (the only thing that scrolls) and the composer pinned at
    the foot, measured by askRoomSize the way a message thread is;
  * bubbles: the reader's on the right in the brand, Ask's on the left
    beside its avatar; a typing row while it looks things up; a round
    Send button that wakes when something is typed;
  * THE ONE FOOTER LINE THAT MUST STAY rides under the composer: not
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


def test_the_footer_and_the_league_strip_leave_while_ask_is_open():
    assert "body.ask-open .footer, body.ask-open .sportbar { display: none; }" in CSS
    assert "body.ask-open { padding-bottom: 0; }" in CSS, "no band of scroll under the room"
    assert "body.ask-open #view-ask { padding-bottom: 0; }" in CSS
    sw = _fn("_switchViewNow")
    assert 'document.body.classList.toggle("ask-open", name === "ask");' in sw, \
        "toggled on EVERY switch, so the footer comes back on the next page"


def test_one_column_header_conversation_composer():
    r = _fn("renderAsk")
    order = ['<div class="ask-room" id="ask-room">', '<div class="ask-head">', 'class="ask-log" id="ask-log"',
             '<div class="ask-dock">', '<form class="ask-form" id="ask-form">', '<p class="ask-note">']
    at = [r.index(s) for s in order]
    assert at == sorted(at), "header, then the conversation, then the composer"
    assert "<b>Ask Qellys</b><span>Any team, any player, any sport</span>" in r
    assert 'data-ask-reset>New chat</button>' in r, "starting over is the header's button"
    assert 'rows="1"' in r and '<button class="ask-send" type="submit" aria-label="Send" disabled>' in r
    assert "askRoomSize();" in r and "setTimeout(askRoomSize, 400);" in r
    css = CSS[CSS.index(".ask-room {"):]
    assert "display: flex; flex-direction: column;" in css[:200]
    assert re.search(r"\.ask-log \{[^}]*flex: 1; min-height: 0; overflow-y: auto;", CSS), "only the log scrolls"
    assert re.search(r"\.ask-dock \{[^}]*flex-shrink: 0;", CSS), "the composer never scrolls away"
    view = HTML[HTML.index('<section class="view" id="view-ask">'):]
    view = view[:view.index("</section>")]
    assert "section-title" not in view, "the room draws its own header"


def test_the_room_is_measured_clear_of_the_tab_bar_and_the_keyboard():
    size = _fn("askRoomSize")
    assert 'document.querySelector(".tabbar")' in size
    assert '[...tab.querySelectorAll("*")]' in size, "the raised Live button stands proud of the bar"
    assert "window.innerHeight - vv.height > 120" in size, "a keyboard, and the tab bar under it"
    assert "log.scrollTop = log.scrollHeight" in size, "opens on the newest message"
    assert 'window.visualViewport.addEventListener("resize"' in APP
    assert 'window.addEventListener("resize", () => { if (state.view === "ask") askRoomSize(); });' in APP


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


def test_the_empty_room_asks_and_offers_questions_including_one_about_the_past():
    r = _fn("renderAsk")
    assert "<h3>What do you want to know?</h3>" in r
    assert "(a.pick ? ASK_SUGGEST_PICK : ASK_SUGGEST)" in r
    assert "ASK_SUGGEST_PAST[state.sport] || ASK_SUGGEST_PAST.nfl" in r
    past = APP[APP.index("const ASK_SUGGEST_PAST = {"):]
    past = past[:past.index("};")]
    assert set(re.findall(r"(\w+): \"", past)) == {"nfl", "cfb", "mlb", "nba", "wnba"}
    assert '"How have the Lions done against the Packers?"' in past, "his own question, as the NFL example"


def test_the_one_footer_line_that_must_stay_rides_under_the_box():
    r = _fn("renderAsk")
    note = r[r.index('<p class="ask-note">'):]
    note = note[:note.index("</p>")]
    assert "not betting\n        advice" in note or "not betting advice" in note
    assert '<span class="ask-help">21+ · 1-800-GAMBLER</span>' in note
    assert ".ask-help { white-space: nowrap; }" in CSS, "the number never breaks across lines"


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
