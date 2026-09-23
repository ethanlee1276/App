"""An Ask answer is laid out, not run together.

Ethan, 2026-09-23, a top-ten answer circled on his phone: "Also can we make
the format of the responses better. Everything we ask is all jumbled up in
one paragraph so it makes it hard to read." The page split an answer only
at blank lines, so a ranking written one team to a line arrived as one
run-on block ("1. Bills — 38.5 ppg 2. Panthers — 35.5 ppg 3. …").

Now (web/js/app.js, askBlocks / askBodyHTML / askTypeOut):
  * each line keeps its break;
  * lines starting "1." or "- " are a real numbered or bulleted list, and a
    ranked item keeps its own number, so a tie (4, 4, 4, 7) reads as written;
  * a ranking crammed onto one line is split back into its items;
  * **bold** is bold, a heading is a bold line, and everything else is
    escaped first;
  * the typing animation writes into that same shape and ends identical to
    the answer drawn whole;
  * the prompt asks for exactly this layout.
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

from engine import askbot as AB                                # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
CRAMMED = ("Top NFL offenses by points per game (early, only 2 games each so far):\n\n"
           "1. Bills — 38.5 ppg 2. Panthers — 35.5 ppg 3. Chiefs — 32.0 ppg 4. Bears, Lions, 49ers — 31.0 ppg "
           "(tied) 7. Ravens — 29.0 ppg 8. Cowboys — 28.5 ppg 9. Saints — 27.0 ppg 10. Bengals — 26.5 ppg\n\n"
           "Keep in mind it's only Week 2 data.")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    esc = APP[APP.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fmt = APP[APP.index("const ASK_ITEM"):APP.index("/* UNDER AN ANSWER, TWO LABELLED ROWS")]
    prog = esc + fmt + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _html(text):
    return _node(f"return askBodyHTML({json.dumps(text)});")


def test_his_crammed_top_ten_is_a_numbered_list_with_the_tie_as_written():
    got = _html(CRAMMED)
    if got is None:
        print("  SKIP node not installed")
        return
    assert got.startswith("<p>Top NFL offenses by points per game (early, only 2 games each so far):</p>"
                          '<ol class="ask-list"><li value="1">Bills — 38.5 ppg</li>')
    assert '<li value="4">Bears, Lions, 49ers — 31.0 ppg (tied)</li><li value="7">Ravens — 29.0 ppg</li>' in got
    assert got.count("<li ") == 8 and '<li value="10">Bengals — 26.5 ppg</li></ol>' in got
    assert got.endswith("<p>Keep in mind it&#39;s only Week 2 data.</p>")


def test_lines_lists_and_bold():
    got = _html("The **Bills** lead.\n1. **Bills**: 38.5\n2. Panthers: 35.5\n\n- one\n- two\nplain\nnext")
    if got is None:
        return
    assert got == ('<p>The <strong>Bills</strong> lead.</p>'
                   '<ol class="ask-list"><li value="1"><strong>Bills</strong>: 38.5</li>'
                   '<li value="2">Panthers: 35.5</li></ol>'
                   '<ul class="ask-list"><li>one</li><li>two</li></ul>'
                   '<p>plain<br>next</p>'), "a single line break is kept, not run together"


def test_ordinary_sentences_are_left_alone_and_nothing_else_becomes_markup():
    got = _node("""return [askBodyHTML("Week 1. The Lions won 2. of 3 games."),
                           askBodyHTML("They were 38.5 points a game, 2 games in."),
                           askBodyHTML("## Best bets\\nnone tonight"),
                           askBodyHTML("<img src=x onerror=alert(1)> **half"),
                           askBodyHTML("****\\n\\n  \\n"),
                           askBodyHTML("Their drives went 1. short 2. long 3. short again.")];""")
    if got is None:
        return
    assert got[0] == "<p>Week 1. The Lions won 2. of 3 games.</p>", "two numbers are not a list"
    assert got[1] == "<p>They were 38.5 points a game, 2 games in.</p>"
    assert got[2] == "<p><strong>Best bets</strong><br>none tonight</p>", "a heading is a bold line"
    assert got[3] == "<p>&lt;img src=x onerror=alert(1)&gt; half</p>", "escaped, and a stray ** dropped"
    assert got[4] == "", "nothing to show is nothing"
    assert got[5] == "<p>Their drives went 1. short 2. long 3. short again.</p>", \
        "a crammed list is split only at the start of a line or after a colon or dash"


def test_the_typed_answer_ends_in_the_same_shape():
    turn = APP[APP.index("function askTurnHTML("):]
    turn = turn[:turn.index("\n}\n")]
    assert "askBodyHTML(t.text)" in turn, "a saved or re-rendered answer is laid out"
    typed = APP[APP.index("function askTypeOut("):]
    typed = typed[:typed.index("\n}\n")]
    assert "bub.innerHTML = askBodyHTML(t.text) + askSourcesHTML(t);" in typed, "and it finishes identical"
    assert "askBlocks(t.text)" in typed and 'document.createElement("li")' in typed
    assert "if (row.n) host.value = row.n;" in typed, "a typed ranking keeps its numbers"
    assert 'run.b ? document.createElement("strong")' in typed, "bold is bold as it is typed"
    assert "askParas" not in APP, "the paragraph-only splitter is gone"


def test_the_list_looks_like_one():
    for rule in (".ask-turn .ask-list { margin: 0 0 8px; padding-left: 1.5em; }",
                 ".ask-turn ol.ask-list li::marker { color: var(--brand-2);",
                 ".ask-turn strong { color: var(--text); font-weight: 600; }"):
        assert rule in CSS, rule


def test_the_prompt_asks_for_this_layout():
    system = " ".join(AB.SYSTEM.split())
    for rule in ("Lead with the direct answer in one sentence, on its own line",
                 "a list (a slate, picks, a ranking, facts side by side) goes one item per line",
                 'each line starting "1." when the order means something and "- " when it does not, at most 8',
                 "bold (**...**) only the name or number that answers the question",
                 "no headings and no tables"):
        assert rule in system, rule


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
            traceback.print_exc(limit=2)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
