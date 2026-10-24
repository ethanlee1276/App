"""A player on YOUR synced roster opens, and the keyboard opens him too.

Ethan, 2026-09-09, holding his phone with his own Sleeper roster on it:
*"when you click on a player, it will show you weekly fantasy
projections, and trade targets and if you should bench them for that
week."*

Every other player on the fantasy page was already a door — the kit
board, the calendar cards, the usage rows. The one list that is HIS was
the only place a name did nothing. `renderSleeperPanel`'s `rowHTML`
draws both the roster and the waiver watch, so one door covers both.

THE HALF THAT IS EXECUTED, not read. `role="button"` with `tabindex="0"`
and no key handler is worse than no role at all: it tells a screen reader
the thing is operable and then swallows Enter. The calendar cells have
carried that role since August with only a mouse behind it. So the
delegated keydown is lifted out of app.js and run here against fake
events, because "the string Enter appears in the file" is not the claim
worth pinning — the claim is that Enter on a door fires it and Enter
anywhere else is left alone.

Run directly: `python3 tests/test_roster_door.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _block(needle):
    """The `document.addEventListener("keydown", …)` call containing `needle`.

    Anchored on the handler's own body rather than on the listener head:
    app.js registers ten keydown listeners and the head is not unique,
    which the first draft of this file discovered the slow way.
    """
    assert APP.count(needle) == 1, needle
    head = 'document.addEventListener("keydown"'
    i = APP.rindex(head, 0, APP.index(needle))
    j = APP.index("{", APP.index("=>", i))
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError("unbalanced braces after " + head)


# ---------------------------------------------------------------- the door

def test_the_roster_row_carries_the_door():
    i = APP.index("const rowHTML = (r) => `")
    row = APP[i:APP.index("</div>`;", i)]
    assert 'data-dossier="${escapeAttr(r.name)}"' in row, \
        "the row a manager taps first still opens nothing"
    assert 'role="button"' in row and 'tabindex="0"' in row
    assert "ffrow-door" in row, "no affordance: it does not look tappable"


def test_the_waiver_watch_gets_the_same_door_for_free():
    """One `rowHTML` draws the roster and the waiver watch. Pinning that
    they share it is the point — a second copy is how the two lists start
    behaving differently."""
    i = APP.index("function renderSleeperPanel(")
    body = APP[i:APP.index("\n/* ============", i)]
    assert body.count("const rowHTML = (r) => `") == 1
    assert body.count("waivers.map((u) => rowHTML(") == 1
    assert body.count("myRows.map(rowHTML)") == 1


def test_the_row_is_styled_as_a_door():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".ffrow-door {")
    rule = css[i:i + 400]
    assert "cursor: pointer" in rule
    assert ".ffrow-door:focus-visible" in css, \
        "a keyboard user cannot see where they are"


# ------------------------------------------------- the keyboard, executed

#: A line inside the handler that no mutant of the behaviour under test
#: would touch. Anchoring on the Escape line instead made every Escape
#: mutant unfindable rather than dead, which reads as a pass.
_HEAD = "one behaviour to keep correct instead of two that can drift."


def _run(script):
    src = ("let opened = [], closed = 0;\n"
           "function closeFfDossier() { closed++; }\n"
           "function closePeek() { closed++; }\n"
           "const onKey = "
           + _block(_HEAD).replace('document.addEventListener("keydown", ', "")
                          .rstrip(");").rstrip()
           + ";\n" + script)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


_EVENT = """
function ev(key, matches) {
  const el = matches ? { click: () => opened.push(matches) } : null;
  let prevented = false;
  return { e: { key,
                target: { closest: (sel) => (matches && sel.includes(matches[0]))
                          ? el : null },
                preventDefault: () => { prevented = true; } },
           was: () => prevented };
}
"""


def test_enter_on_a_roster_row_opens_the_player():
    got = _run(_EVENT + """
      const x = ev("Enter", ["data-dossier"]);
      onKey(x.e);
      console.log(JSON.stringify([opened.length, x.was()]));""")
    assert got == [1, True], got


def test_space_opens_it_too_and_does_not_scroll_the_page():
    """Space on a focused button activates it. Without preventDefault it
    also scrolls the list out from under the panel that just opened."""
    got = _run(_EVENT + """
      const x = ev(" ", ["data-dossier"]);
      onKey(x.e);
      console.log(JSON.stringify([opened.length, x.was()]));""")
    assert got == [1, True], got


def test_the_calendar_cells_that_already_claimed_the_role_now_honour_it():
    for attr in ("data-calday", "data-calpick"):
        got = _run(_EVENT + f"""
          const x = ev("Enter", ["{attr}"]);
          onKey(x.e);
          console.log(JSON.stringify(opened.length));""")
        assert got == 1, (attr, got)


def test_enter_anywhere_else_is_left_alone():
    """The handler is on `document`. Swallowing Enter on a text input or
    a real <button> would break every form on the site."""
    got = _run(_EVENT + """
      const x = ev("Enter", null);
      onKey(x.e);
      console.log(JSON.stringify([opened.length, x.was()]));""")
    assert got == [0, False], got


def test_escape_still_closes_and_does_not_open_anything():
    got = _run(_EVENT + """
      const x = ev("Escape", ["data-dossier"]);
      onKey(x.e);
      console.log(JSON.stringify([closed, opened.length]));""")
    assert got[0] == 2, "Escape stopped closing the dossier"
    assert got[1] == 0, "Escape fell through and opened a player"


if __name__ == "__main__":
    if not shutil.which("node"):
        print("SKIP node is not installed; the keyboard half of this file "
              "EXECUTES the handler. `apt install -y nodejs`")
        print("\n0 tests passed.")
        raise SystemExit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
