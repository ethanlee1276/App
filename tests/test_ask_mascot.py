"""Ask Qellys has a face: Ethan's crowned robot, and it moves.

Ethan, 2026-09-23, with two renders of a white-and-gold robot in a QB
crown: "here is renders for the chat bot mascot we should use too. Make
it animated and stuff so the chat feels alive like you're talking to the
actual bot."

  * THE RENDERS SHIP as web/img/ask/: the robot, its head for the avatars
    and the laptop scene for the paywall, each WebP with a JPEG behind it,
    small enough for a phone on a stadium's signal;
  * ITS FACE IS DRAWN, over the screen in the render, so it can move: two
    arcs and a half-moon in the render's glow, on a patch of the screen's
    own black, every face with filter ids of its own;
  * FIVE MOODS on one attribute of the room — idle (blinks, floats),
    listening (looks down at the box you are typing in), thinking (looks
    around, bobs), talking (mouth moving while the answer types out),
    happy (a hop when it finishes) — acted out only by the robots marked
    live (the big one in the empty room and the newest answer's; the
    header's holds still), and by none of them under reduced motion;
  * WHERE IT STANDS: beside the title in the empty room, at the head of a
    conversation, beside the newest answer, and on the paywall.
"""
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
ASK = ROOT / "web" / "img" / "ask"


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def _jpeg_size(path):
    b = path.read_bytes()
    i = 2
    while i < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    raise AssertionError(f"no frame header in {path.name}")


def test_the_renders_ship_small_with_a_jpeg_behind_each():
    for stem in ("qbot", "qbot-head", "qbot-scene", "qbot-scene@640"):
        for ext in ("webp", "jpg"):
            f = ASK / f"{stem}.{ext}"
            assert f.exists(), f
            assert f.stat().st_size < 120_000, f"{f.name} is {f.stat().st_size} bytes"
            if ext == "webp":
                assert f.read_bytes()[8:12] == b"WEBP", f"{f.name} is not a WebP"
    sizes = dict(re.findall(r'(body|head): \[(\d+, \d+)\]', APP[APP.index("const QBOT_SIZE"):][:120]))
    for kind, stem in (("body", "qbot"), ("head", "qbot-head")):
        w, h = _jpeg_size(ASK / f"{stem}.jpg")
        assert f"{w}, {h}" == sizes[kind], f"{stem}.jpg is {w}x{h}; QBOT_SIZE says {sizes[kind]}"
    bw, bh = _jpeg_size(ASK / "qbot.jpg")
    assert abs(bw / bh - 860 / 1480) < 0.005, "the body file is the 860x1480 crop the face is drawn against"
    assert ".qbot-body { width: 118px; aspect-ratio: 860 / 1480;" in CSS
    assert 'const QBOT_BOX = { body: "60 20 860 1480", head: "140 25 760 760" };' in APP
    q = _fn("qbotHTML")
    assert '<source type="image/webp" srcset="img/ask/${file}.webp"><img src="img/ask/${file}.jpg" alt=""' in q
    assert 'aria-hidden="true"' in q, "a face, not content"


def test_the_face_is_drawn_so_it_can_move():
    f = _fn("qbotFace")
    assert "const n = ++_qbotN;" in f and 'id="qbg${n}"' in f and 'id="qbf${n}"' in f, \
        "every face its own filter ids — a shared id would draw every glow from the first face on the page"
    assert 'filter="url(#qbg${n})"' in f and 'filter="url(#qbf${n})"' in f
    assert 'fill="#0A0602" filter="url(#qbf${n})"' in f, "a feathered patch of the screen's own black"
    assert 'transform="rotate(9.7 544 556)"' in f, "tilted the way the render's head is"
    assert f.count('class="qbot-eye"') == 2 and f.count('class="qbot-mouth"') == 1 and 'class="qbot-look"' in f


def test_five_moods_on_one_attribute():
    r = _fn("renderAsk")
    assert 'const mood = a.busy ? "thinking" : _askTyping ? "talking" : "idle";' in r
    assert 'id="ask-room" data-bot="${mood}"' in r
    assert 'askBotState(input.value.trim() ? "listening" : "idle")' in r, "it watches you type"
    typer = _fn("askTypeOut")
    assert 'askBotState("talking");' in typer and 'askBotState("happy");' in typer
    assert 'if (room && room.dataset.bot === "happy") room.dataset.bot = "idle";' in typer
    motion = CSS[CSS.index("@media (prefers-reduced-motion: no-preference) {\n  .qbot.live .qbot-eye"):]
    motion = motion[:motion.index("\n}\n")]
    for rule in (".qbot.live .qbot-eye { animation: qbBlink", ".qbot-body.live { animation: qbFloat",
                 '[data-bot="listening"] .qbot.live .qbot-look { transform:',
                 '[data-bot="thinking"] .qbot.live .qbot-look { animation: qbLook',
                 '[data-bot="talking"] .qbot.live .qbot-mouth { animation: qbTalk',
                 '[data-bot="happy"] .qbot.live { animation: qbHop'):
        assert rule in motion, rule
    for kf in ("qbBlink", "qbFloat", "qbLook", "qbBob", "qbTalk", "qbNod", "qbHop"):
        assert f"@keyframes {kf} " in CSS, kf
    assert "animation: qb" not in CSS.replace(motion, ""), "nothing moves outside the no-preference block"


def test_where_it_stands():
    r = _fn("renderAsk")
    assert '${qbotHTML("body", "ask-hero-bot live")}' in r, "beside the title in the empty room"
    assert 'qbotHTML("head", "ask-head-bot")' in r, "at the head of a conversation"
    assert "ask-head-bot live" not in APP, \
        "and holding still there: only the newest answer's robot moves (Ethan, 2026-09-23)"
    assert "a.turns.map((t, i) => askTurnHTML(t, i === lastBot && !a.busy))" in r, \
        "only the newest answer's robot reacts; older ones hold still"
    assert '<div class="ask-row bot">${askAva(true)}<div class="ask-turn bot wait">' in r, "the one thinking"
    assert "askAva(true)" in _fn("askTurnHTML"), "the one talking"
    pw = _fn("pwAskHTML")
    assert '<picture class="pw-ask-scene">' in pw and 'alt="The Ask Qellys robot at a laptop' in pw
    assert 'srcset="img/ask/qbot-scene@640.webp 640w, img/ask/qbot-scene.webp 960w"' in pw
    assert re.search(r'\.qbot-body img \{ mix-blend-mode: lighten;', CSS), \
        "the render's black melts into the page's instead of drawing a box"
    assert ':root[data-theme="light"] .qbot-body { border-radius: var(--radius-lg); background: #0B0A08; }' in CSS, \
        "on the light theme it stands on a dark card rather than a black smudge"


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
