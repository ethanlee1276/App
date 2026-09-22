"""v5 motion: the numbers count up, the dot pings, the live redraw is still.

Ethan, 2026-09-22: "I feel like we could be using more animations and
more design features … feel like a real sportsbook app made by a real
company." Four things, all inside the motion system (tests/test_motion.py:
tokened durations and curves, zeroed under reduced motion), and none of
them invented: every one moves a number the board already holds.

- A ribbon's ring label and headline number count up to themselves
  (countAt, countNumbers): once per element, ending byte for byte on the
  final text, the same decimals and thousands commas on the way.
- The live dot pings — the one perpetual animation §3.4 permits, which
  the NEW LOOK had left as a square that never moved. A held game's dot
  has stopped, and so has its ping.
- The form dots pop in, newest first; the ribbons rise with the rows.
- The live clock's redraw of the home deck is STILL: the riding rows and
  the strip refilled in place, no skeleton, no entrance, the record and
  Zeno left alone. Before this the whole deck re-landed every 20 seconds
  of a live night — a page that flickers is the opposite of a book.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("COUNT_NUM")}
      {_fn("countAt")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_count_at_scales_the_first_number_and_keeps_everything_around_it():
    got = _node("""
      return {
        zero: countAt("+14.6% ROI", 0), one: countAt("+14.6% ROI", 1), past: countAt("+14.6% ROI", 2),
        half: countAt("57%", .5), money: countAt("+$1,234", .5), minus: countAt("\\u22123.2u", 0),
        units: countAt("+6.4u", 0), none: countAt("no number here", .3), nan: countAt("+14.6% ROI", NaN),
        big: countAt("$12,345.60 risked", .999) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["zero"] == "+0.0% ROI", "the sign, the unit and the word stay; only the number moves"
    assert got["one"] == "+14.6% ROI" and got["past"] == "+14.6% ROI", "at the end it IS the final text"
    assert got["half"] == "50%", "an ease-out cube: 57 × (1 − .5³) = 49.9 → 50"
    assert got["money"] == "+$1,080", "1234 × (1 − .5³) = 1079.75, and the comma comes with it"
    assert got["minus"] == "−0.0u", "the typographic minus is a prefix, not part of the number"
    assert got["units"] == "+0.0u", "one decimal in, one decimal out"
    assert got["none"] == "no number here"
    assert got["nan"] == "+14.6% ROI", "a broken clock shows the number"
    assert got["big"].startswith("$12,3") and got["big"].endswith(" risked") and got["big"].count(",") == 1, \
        "the thousands comma is kept where the text had one"


def test_the_ribbon_hands_its_two_numbers_to_the_counter():
    rec = _fn("recordRibbonsHTML")
    assert '<i data-count>${pc}%</i>' in rec, "the ring's label counts"
    assert '<b style="color:${color}" data-count>${big}</b>' in rec, "the headline number counts"
    sweep = _fn("sweepRings")
    assert "countNumbers(host);" in sweep, "wherever a ring sweeps, its numbers count"
    body = _fn("countNumbers")
    assert '"(prefers-reduced-motion: reduce)").matches) return;' in body, "reduced motion: the number is simply there"
    assert 'querySelectorAll("[data-count]:not([data-counted])")' in body and 'el.dataset.counted = "1";' in body, \
        "once per element"
    assert 'getPropertyValue("--dur-slow")' in body and "COUNT_STEPS_OF_SLOW" in body, "the duration comes from the ladder"
    assert "setTimeout(() => { el.textContent = final; }, dur + 120);" in body, "a throttled tab still ends on the number"
    assert "el.textContent = countAt(final, 0);" in body, "the first paint is zero, or there is nothing to count from"
    assert ".hd-big, .hd-ring i { font-variant-numeric: tabular-nums; }" in CSS, "a counting number holds its width"
    assert ".hd-big b { white-space: nowrap; }" in CSS


def test_the_live_dot_pings_and_a_paused_one_does_not():
    i = DECLS.index(".live-dot {")
    rule = DECLS[i:DECLS.index("}", i)]
    assert "position: relative;" in rule and "animation: livePulse 1.4s var(--ease-out) infinite;" in rule, rule
    assert '.live-dot::after { content: ""; position: absolute; inset: 0; border-radius: inherit; background: inherit;' in CSS
    assert "animation: livePing 1.4s var(--ease-out) infinite; }" in CSS
    ping = DECLS[DECLS.index("@keyframes livePing"):]
    ping = ping[:ping.index("}", ping.index("to {")) + 1]
    assert "transform: scale(3); opacity: 0;" in ping and "box-shadow" not in ping and "border" not in ping, \
        "a ping is a copy of the dot leaving it — no glow, no ring"
    pulse = DECLS[DECLS.index("@keyframes livePulse"):]
    pulse = pulse[:pulse.index("\n}") + 2]
    assert "opacity: .45;" in pulse and "box-shadow" not in pulse, "the dot breathes; the NEW LOOK's zeroed glow is gone"
    assert ".live-dot.paused::after { display: none; }" in CSS, "a held game's ping has stopped with its dot"
    assert "@media (prefers-reduced-motion: reduce) { .live-dot, .live-dot::after { animation: none; } .live-dot::after { display: none; } }" in CSS


def test_the_form_dots_pop_and_the_ribbons_rise():
    assert ".hd-ribbon { animation: rise var(--dur-slow) var(--ease-out) both; }" in CSS
    assert ".hd-ribbon + .hd-ribbon { animation-delay: calc(var(--dur-fast) * .6); }" in CSS, "the second a beat behind"
    assert "@keyframes popIn { from { opacity: 0; transform: scale(.4); } to { opacity: 1; transform: none; } }" in CSS
    assert ".hd-form i { animation: popIn var(--dur-base) var(--ease-out) both; animation-delay: var(--dur-slow); }" in CSS, \
        "the dots wait for the ring's sweep"
    for n, k in ((2, ".5"), (3, "1"), (4, "1.5"), (5, "2")):
        assert f".hd-form i:nth-child({n}) {{ animation-delay: calc(var(--dur-slow) + var(--dur-fast) * {k}); }}" in CSS, n
    # every duration on these lines is a token (tests/test_motion.py covers transitions; this covers the animations)
    for line in CSS.splitlines():
        if "animation:" in line and ("popIn" in line or "rise var" in line):
            assert not re.search(r"animation:[^;]*\b\d+m?s\b", line), line


def test_the_live_clock_redraws_the_deck_in_place():
    deck = _fn("renderHomeDeck")
    assert "const still = !!(opts && opts.still);" in deck
    assert 'host.classList.toggle("hd-still", still);' in deck
    assert "if (!still) { deckSkeleton(host); deckAdopt(host); placeSlip(); }" in deck, "no skeleton over a live page"
    i = deck.index('deckFill(host, "riding", deckRidingHTML(riding));')
    j = deck.index("if (still) {")
    assert i < j, "the riding rows refill either way — a bet's state moves with the score"
    assert 'if (still) {\n    deckFill(host, "live", await deckLiveHTML(riding, rows));\n  } else {' in deck
    assert 'deckFill(host, "record", rest.record);' in deck[j:], "the record is rebuilt only on a full render"
    assert 'if (!still) host.querySelectorAll(".zeno-copy")' in deck, "no second listener on a button that stayed"
    assert "if (!still) {\n    sweepRings(host);" in deck, "a still redraw sweeps and counts nothing"
    arm = _fn("armDeckLive")
    assert "if (now !== _deckStamp) { renderHomeDeck({ still: true }); return; }" in arm
    assert ".hd-still .hd-row, .hd-still .hd-ribbon, .hd-still .hd-form i { animation: none; }" in CSS
    # a visit is the full render
    rec = _fn("renderRecommended")
    assert "renderHomeDeck();" in rec


def test_the_rows_and_game_cards_answer_a_press():
    press = DECLS[DECLS.index(".btn:active, .chip[role=\"button\"]:active"):]
    press = press[:press.index("}")]
    assert ".ml-row:active, .hd-game:active" in press
    trans = DECLS[DECLS.index(".btn, .sport-btn, .nav-btn, .mbc-chip"):]
    trans = trans[:trans.index("{")]
    assert ".ml-row, .hd-game" in trans, "and they ease back"
    rm = DECLS[DECLS.index("@media (prefers-reduced-motion: reduce) {", DECLS.index("main { view-transition-name: page; }")):]
    assert ".ml-row:active, .hd-game:active { transform: none; }" in rm[:1000], "reduced motion lets go of the press"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
