"""Catch a fixed-size test window BEFORE it fails on correct code.

Dozens of assertions here scope a search with a character count:

    i = APP.index("function gameBetCard(")
    assert "gameBetAttrs(r)" in APP[i:i + 3000]

The count is a guess about how long a function will stay. Three times in
two weeks a guess expired and the suite went red on correct code — the
2026-08-17 chart pass, an 08-26 storage slice, and the 08-27 not-staked
chip. Each time the fix was a bigger number, which resets the clock and
teaches the next reader that red means "re-anchor" rather than
"investigate". A safety net you have learned to overrule is the
expensive failure, not the wasted minutes.

`tests/_windows.py` fixes the ones whose scope is really a block. This
catches the rest, and it is the durable half: it measures how much room
each window has LEFT and fails while there is still time to widen or
convert it deliberately — with a message saying which, rather than a
mystery assertion error inside an unrelated test.

Only the two-line shape above is measurable, so this does not see every
window. It sees the ones that have historically broken.

Run directly: `python3 tests/test_window_slack.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _windows  # noqa: E402  (path set above)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The globals tests slice, and the file each one holds.
SOURCES = {"APP": "web/js/app.js", "HTML": "web/index.html",
           "INDEX": "web/index.html", "CSS": "web/css/styles.css",
           "SW": "web/sw.js"}

#: Below this much room left, a window is one ordinary edit from failing.
#: Not a style rule — a countdown. 150 characters is about three lines of
#: the code these windows point into.
MIN_SLACK = 150

#: …except where the window is deliberately small. A CSS rule block is
#: genuinely eighty characters long, and a window sized to it has little
#: slack by design and is not at risk from a change somewhere else.
SMALL_WINDOW = 200

_ASSIGN = re.compile(r'(\w+)\s*=\s*([A-Z_]+)\.index\(("(?:[^"\\]|\\.)*"'
                     r"|'(?:[^'\\]|\\.)*')\)")


def _body(name):
    path = os.path.join(ROOT, SOURCES[name])
    if not os.path.isfile(path):
        return None
    return open(path, encoding="utf-8").read()


def _unquote(lit):
    try:
        return lit[1:-1].encode().decode("unicode_escape")
    except UnicodeDecodeError:
        return None


def measure() -> list[dict]:
    """Every measurable window, with how much room it has left."""
    bodies = {k: _body(k) for k in SOURCES}
    out = []
    for fn in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if not (fn.startswith("test_") and fn.endswith(".py")):
            continue
        if fn == os.path.basename(__file__):
            # This file QUOTES the shape it measures, in its own
            # docstring, as the example of what goes wrong. Scanning
            # itself would report the illustration as a finding — which
            # it did on the first run, and which is at least proof the
            # matcher works.
            continue
        lines = open(os.path.join(ROOT, "tests", fn),
                     encoding="utf-8").read().splitlines()
        for idx, line in enumerate(lines):
            m = _ASSIGN.search(line)
            if not m:
                continue
            var, gvar, anchor_lit = m.group(1), m.group(2), m.group(3)
            body = bodies.get(gvar)
            anchor = _unquote(anchor_lit) if body else None
            if not anchor:
                continue
            window = re.compile(
                r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\s+in\s+'
                + re.escape(gvar) + r'\[' + re.escape(var) + r'\s*:\s*'
                + re.escape(var) + r'\s*\+\s*(\d+)\]')
            for look in lines[idx + 1:idx + 6]:
                w = window.search(look)
                if not w:
                    continue
                needle = _unquote(w.group(1))
                if needle is None:
                    break
                size = int(w.group(2))
                try:
                    at = body.index(anchor)
                    where = body.index(needle, at) - at
                except ValueError:
                    break
                out.append({"file": fn, "line": idx + 1, "size": size,
                            "needed": where, "slack": size - where,
                            "anchor": anchor})
                break
    return out


def test_the_analyzer_finds_the_windows_it_is_meant_to():
    """A measurer that silently matched nothing would pass forever."""
    rows = measure()
    assert len(rows) >= 20, f"only found {len(rows)} windows — regex drifted?"


def test_no_window_is_nearly_full():
    """The countdown. A window this close is one ordinary edit from a
    red suite on correct code."""
    tight = [r for r in measure()
             if r["slack"] < MIN_SLACK and r["size"] > SMALL_WINDOW]
    assert not tight, (
        "these fixed-size windows are nearly full and will fail on correct "
        "code soon — slice to the block with tests/_windows.py instead of "
        "widening the number:\n" + "\n".join(
            f"  {r['file']}:{r['line']}  window {r['size']}, needs "
            f"{r['needed']}, {r['slack']} left  ({r['anchor'][:40]!r})"
            for r in sorted(tight, key=lambda r: r["slack"])))


def test_every_window_actually_contains_what_it_asserts():
    """A window whose needle sits PAST it is already broken; this names
    it as a window problem rather than letting it surface as a mystery
    assertion error inside an unrelated test."""
    past = [r for r in measure() if r["slack"] < 0]
    assert not past, "\n".join(
        f"  {r['file']}:{r['line']} needs {r['needed']}, window is {r['size']}"
        for r in past)


# --- the helper the fix uses --------------------------------------------------
def test_block_stops_at_the_matching_brace_not_the_first_one():
    src = "fn a() {\n  if (x) { y(); }\n  z();\n}\nfn b() {}"
    got = _windows.block(src, "fn a()")
    assert got.endswith("z();\n}")
    assert "fn b" not in got


def test_block_finds_a_css_rule():
    src = ".a { color: red; }\n.b { color: blue; }"
    assert _windows.block(src, ".b {") == ".b { color: blue; }"


def test_block_raises_on_a_missing_anchor():
    """The same failure a bare .index() gives — and it IS a real finding:
    the anchor moved."""
    try:
        _windows.block("nothing here", "function gone(")
    except ValueError:
        return
    raise AssertionError("a missing anchor must not slice silently")


def test_an_unclosed_block_returns_the_rest_rather_than_raising():
    assert _windows.block("fn a() { x();", "fn a()").endswith("x();")


def test_function_skips_a_destructured_parameter_list():
    """The bug this helper hit on its first real use. `function
    liveCardHTML({ sport, g, bets })` opens a brace in its PARAMETERS,
    so taking the first `{` after the name slices forty characters and
    stops before the body starts."""
    src = "function f({ a, b }) {\n  body();\n}\nfunction g() {}"
    got = _windows.function(src, "function f(")
    assert "body();" in got
    assert "function g" not in got
    # …and the naive version really does get it wrong, which is why the
    # helper has two entry points rather than one.
    assert "body();" not in _windows.block(src, "function f(")


def test_function_handles_a_default_value_containing_braces():
    src = "function f(opts = { x: 1 }) {\n  body();\n}\n"
    assert "body();" in _windows.function(src, "function f(")


def test_function_falls_back_when_there_is_no_parameter_list():
    src = "const f = {\n  body: 1,\n};\n"
    assert "body" in _windows.function(src, "const f =")


def test_until_falls_back_to_the_rest_of_the_file():
    src = "## one\nbody\n"
    assert _windows.until(src, "## one", "## two") == src


def test_lines_after_counts_lines_not_characters():
    src = "anchor\nb\nc\nd\n"
    assert _windows.lines_after(src, "anchor", 2) == "anchor\nb\nc"


def test_the_helper_is_not_collected_as_a_test():
    """`run_tests.py` globs test_*.py — a helper named otherwise stays a
    helper."""
    assert not os.path.basename(_windows.__file__).startswith("test_")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
