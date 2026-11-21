"""The owner's desk lists every box command waiting on him, each with a Copy
button.

Ethan, 2026-11-05: "think and add more features for the site and for me."
docs/RUN_NEXT.md is where every command waiting on the box lives, and
reading it meant opening GitHub on a phone, then typing a long line into a
terminal by hand. What this holds:

  * the reader takes each numbered ``##`` section with a command in it, the
    lines inside its code blocks being the commands, in the file's order;
    prose, headings inside a code block and sections with nothing to run
    are left out;
  * the file's "Last updated" date comes along, and a long file is cut at
    the cap while the count still says how many there are;
  * the desk carries it as its own section, so a missing file is that
    card's error and never the desk's;
  * the page draws each section folded (the first open), each command as
    text with a Copy button whose copy is the command itself, quotes
    included; the card says when the list is cut short;
  * a click on Copy writes the command to the clipboard, and a toggle is
    remembered across the minute's redraw;
  * the real file parses, and its commands are the box's own.

Run directly: `python3 tests/test_the_desk_lists_the_waiting_commands.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ownerdesk as OD                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
FENCE = "`" * 3

SAMPLE = f"""# Commands waiting for you

Every command waiting to be run on the box.

Last updated 2026-11-05, after something.

## 1. First: the plan (step JW)

Some words about it.

{FENCE}
cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan --month

grep "two words" /tmp/x.txt
{FENCE}

More words.

{FENCE}bash
bash tools/catchup.sh JW
{FENCE}

## 2. Nothing to run here

Only prose.

## 3. A code block holding a heading

{FENCE}
## not a section
echo three
{FENCE}
"""


def _write(text):
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_each_section_with_a_command_comes_back_with_its_commands_in_order():
    path = _write(SAMPLE)
    try:
        r = OD.run_next(path)
    finally:
        os.unlink(path)
    assert r["n"] == 2 and r["updated"] == "2026-11-05", r
    first, third = r["items"]
    assert first["title"] == "1. First: the plan (step JW)"
    assert first["commands"] == ["cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan --month",
                                 'grep "two words" /tmp/x.txt', "bash tools/catchup.sh JW"], first
    assert third["title"] == "3. A code block holding a heading"
    assert third["commands"] == ["## not a section", "echo three"], "a heading inside a code block is a command line"
    assert not any(i["title"].startswith("2.") for i in r["items"]), "a section with nothing to run is left out"


def test_a_long_file_is_cut_at_the_cap_and_the_count_still_says_how_many():
    body = "Last updated 2026-01-02.\n\n" + "".join(
        f"## {i}. Step {i}\n\n{FENCE}\necho {i}\n{FENCE}\n\n" for i in range(OD.RUN_NEXT_MAX + 5))
    path = _write(body)
    try:
        r = OD.run_next(path)
    finally:
        os.unlink(path)
    assert r["n"] == OD.RUN_NEXT_MAX + 5 and len(r["items"]) == OD.RUN_NEXT_MAX
    assert r["items"][0]["commands"] == ["echo 0"] and r["updated"] == "2026-01-02"


def test_a_file_without_a_date_or_commands_is_an_empty_list():
    path = _write("# Commands waiting for you\n\nNothing today.\n")
    try:
        r = OD.run_next(path)
    finally:
        os.unlink(path)
    assert r == {"items": [], "n": 0, "updated": ""}, r


def test_the_desk_carries_it_and_a_missing_file_is_only_that_cards_error():
    src = READ("engine", "ownerdesk.py")
    assert '"run_next": _section(run_next)' in src, "the desk assembles it through its per-section guard"
    keep = OD.RUN_NEXT_PATH
    OD.RUN_NEXT_PATH = Path(tempfile.mkdtemp()) / "missing.md"
    try:
        got = OD._section(OD.run_next)
    finally:
        OD.RUN_NEXT_PATH = keep
    assert isinstance(got, dict) and got.get("error"), got


def test_the_real_file_parses_and_its_commands_are_the_box_s_own():
    r = OD.run_next()
    assert r["n"] >= 1 and r["updated"], r
    cmds = [c for i in r["items"] for c in i["commands"]]
    assert any("tools/catchup.sh" in c for c in cmds), "the catch-up lines are on the list"
    assert all(i["title"][:1].isdigit() for i in r["items"]), [i["title"] for i in r["items"]][:5]


def _draw(sample, script):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const _handlers = {};
      const document = { addEventListener(kind, fn) { _handlers[kind] = fn; }, querySelectorAll() { return []; } };
      const _clip = [];
      const navigator = { clipboard: { writeText(s) { _clip.push(s); return Promise.resolve(); } } };
    """
    prog = stubs + READ("web", "js", "owner.js") + f"\nconst D = {json.dumps(sample)};\n" + script
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return out.stdout


RUN = {"items": [{"title": "1. First: the plan (step JW)",
                  "commands": ["cd /srv/qellys && python3 -m engine.oddsplan --month", 'grep "two words" <x>']},
                 {"title": "2. Then the rest", "commands": ["bash tools/catchup.sh KK"]}],
       "n": 3, "updated": "2026-11-05"}


def _desk(run_next):
    return {"at": time.time(), "now": {"members": 1, "visitors": 0, "pages": 1}, "prefs": {}, "switches": [],
            "notice": {}, "community": {}, "reports": {"open": [], "open_n": 0, "hidden": [], "hidden_n": 0},
            "run_next": run_next}


def test_the_page_draws_each_command_with_a_copy_button():
    html = _draw(_desk(RUN), "process.stdout.write(odRunNextHTML(D.run_next));")
    if html is None:
        return
    for want in ("Commands waiting for you", "the first 2 of 3 from docs/RUN_NEXT.md, last updated 2026-11-05",
                 '<details class="od-run" data-title="1. First: the plan (step JW)" open>',
                 '<details class="od-run" data-title="2. Then the rest">',
                 "<code>cd /srv/qellys &amp;&amp; python3 -m engine.oddsplan --month</code>",
                 'data-od-copy="grep &quot;two words&quot; &lt;x&gt;"', "<code>bash tools/catchup.sh KK</code>",
                 ">Copy</button>"):
        assert want in html, want
    assert html.count('class="od-chip od-copy"') == 3
    assert "<x>" not in html, "a command is text, never markup"


def test_the_card_is_on_the_desk_and_says_so_when_nothing_waits_or_the_file_is_missing():
    out = _draw(_desk(RUN), "process.stdout.write(odHTML(D) + '\\n=====\\n' + odRunNextHTML({items: [], n: 0})"
                " + '\\n=====\\n' + odRunNextHTML({error: 'FileNotFoundError: no file'}));")
    if out is None:
        return
    desk, empty, err = out.split("\n=====\n")
    assert "Commands waiting for you" in desk and "bash tools/catchup.sh KK" in desk
    assert desk.index("Commands waiting for you") < desk.index("Download the numbers"), "beside the morning summary"
    assert "Nothing waiting on the box." in empty
    assert "Could not read this part: FileNotFoundError: no file" in err


def test_a_click_on_copy_writes_the_command_and_a_toggle_is_remembered():
    script = r"""
      const btn = { dataset: { odCopy: 'grep "two words" /tmp/x.txt' }, textContent: "Copy" };
      const target = { closest(sel) { return sel === "[data-od-copy]" ? btn : null; } };
      _handlers.click({ target, preventDefault() {} });
      setTimeout(() => {
        process.stdout.write(JSON.stringify({ clip: _clip, word: btn.textContent }) + "\n");
        // The owner folds the only open one: nothing is open on the page when the toggle lands.
        const shut = { classList: { contains: (c) => c === "od-run" }, open: false, dataset: { title: "1. First: the plan (step JW)" } };
        _handlers.toggle({ target: shut });
        process.stdout.write(odRunNextHTML(D.run_next) + "\n=====\n");
        const open2 = { classList: { contains: (c) => c === "od-run" }, open: true, dataset: { title: "2. Then the rest" } };
        _handlers.toggle({ target: open2 });
        process.stdout.write(odRunNextHTML(D.run_next));
      }, 20);
    """
    out = _draw(_desk(RUN), script)
    if out is None:
        return
    first, rest = out.split("\n", 1)
    folded, html = rest.split("\n=====\n")
    got = json.loads(first)
    assert got["clip"] == ['grep "two words" /tmp/x.txt'] and got["word"] == "Copied", got
    assert " open>" not in folded, "folding the only open one stays folded through the redraw"
    assert '<details class="od-run" data-title="1. First: the plan (step JW)">' in html, "closed stays closed"
    assert '<details class="od-run" data-title="2. Then the rest" open>' in html, "opened stays open"


def test_the_style_reads_the_page_s_own_tokens():
    css = READ("web", "css", "owner.css")
    i = css.index(".od-run {")
    block = css[i:i + 700]
    assert "var(--hairline) solid var(--border-soft)" in block and "var(--lh-tight)" in block
    assert "overflow-wrap: anywhere" in block, "a long command wraps on a phone instead of running off it"


def test_every_fence_stands_on_a_line_of_its_own():
    """A fence with words after it does not close its block on GitHub
    (6 November: RUN_NEXT 0b's "``` Then the read-only check" turned every
    block after it inside out there), though this card's reader took it as
    one. A fence is three backticks and at most a language name."""
    import re
    for name in ("RUN_NEXT.md", "WHEN_YOU_ARE_HOME.md"):
        lines = (ROOT / "docs" / name).read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                assert re.fullmatch(r"\s*```[\w+-]*\s*", line), (name, n, line)


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
