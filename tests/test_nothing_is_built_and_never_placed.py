"""A value computed and thrown away is the bug this repo keeps finding.

It has a shape, and the shape repeats: something real is worked out —
a list, a reason, a report, a census — and then never reaches the page,
the log or the caller. It costs nothing visible, so nothing catches it,
and the thing it was supposed to explain goes on being unexplained.

The register, from this repo's own history:

  #213  the sharp-book list check, computed and never shown
  #222  a model board that fails to load, still silent
  2026-09-16  match reasons printed under the wrong census heading
  2026-09-16  `_write_day_top_pick` swallowing a missing board with a
              bare `continue`, so a dropped league left no trace
  2026-09-18  `exchangefair.attach_to_board` taking `(markets, meta)`
              from `fetch_sports_markets` and never reading `meta` — the
              per-series report that is the only thing separating "the
              exchange lists nothing" from "the feed is down" from "our
              tickers are wrong". A total outage read as a naming bug.
  2026-09-18  `mockDraftHTML` building two whole lists per render, left
              over from the three-column redesign, into strings nobody
              placed.

This file is the mechanical half of catching it: a local that is bound
and never read again. That does not find every instance — a value that
IS read but read into nothing still passes — but it finds this one, and
it would have found the exchange report on the day it was written.

THE ALLOWLIST IS THE POINT OF THE DESIGN. Some bindings are honestly
unread: a tuple unpack that wants one field, a call kept for the
exception it raises. Those are listed here by name with the reason, so
adding one is a deliberate act with a sentence attached rather than a
silent pass.

Run directly: `python3 tests/test_nothing_is_built_and_never_placed.py`
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Python bindings that are deliberately never read, and why.
#:
#: A LEADING UNDERSCORE ALREADY SAYS "UNUSED" and is skipped without an
#: entry; this list is for the ones that cannot be renamed, or where the
#: name is load-bearing documentation of what the slot holds.
PY_ALLOWED = {
    # Tuple unpacks that want the tempered figure, not the raw one.
    ("engine/betting.py", "evaluate_prop", "edge_raw"):
        "pick_side's raw edge; temper_edge recomputes it two lines down",
    ("engine/mlb/betting.py", "evaluate_mlb_prop", "edge_raw"):
        "pick_side's raw edge; temper_edge recomputes it two lines down",
}

#: JavaScript locals in app.js that are declared and never read.
#: Empty, and meant to stay that way — every entry is a render doing
#: work it throws away.
JS_ALLOWED: dict = {}


def _py_unread():
    out = []
    files = sorted(list((ROOT / "engine").rglob("*.py"))
                   + list(ROOT.glob("*.py")))
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assigned, read = {}, set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Store):
                        assigned.setdefault(node.id, node.lineno)
                    else:
                        read.add(node.id)
                elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    read.add(node.target.id)
                elif isinstance(node, (ast.Global, ast.Nonlocal)):
                    read.update(node.names)
            for var, lineno in assigned.items():
                if var.startswith("_") or var in read:
                    continue
                out.append((rel, fn.name, var, lineno))
    return out


def _js_unread():
    """Locals declared with const/let inside a top-level function in
    app.js and never named again in that function."""
    src = (ROOT / "web" / "js" / "app.js").read_text()
    lines = src.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^(?:async )?function (\w+)\(", lines[i])
        if m:
            j = i + 1
            while j < len(lines) and lines[j] != "}":
                j += 1
            body = lines[i:j + 1]
            text = "\n".join(body)
            for k, ln in enumerate(body):
                d = re.match(r"^\s{2,}(?:const|let) (\w+) = ", ln)
                if not d or d.group(1).startswith("_"):
                    continue
                var = d.group(1)
                if len(re.findall(r"\b" + re.escape(var) + r"\b", text)) == 1:
                    out.append((m.group(1), var, i + k + 1))
            i = j
        i += 1
    return out


# --- the sweep ---------------------------------------------------------------
def test_no_python_value_is_computed_and_never_read():
    bad = [(f, fn, v, ln) for f, fn, v, ln in _py_unread()
           if (f, fn, v) not in PY_ALLOWED]
    assert not bad, (
        "these are bound and never read again — either the work they do is "
        "meant to reach something and does not, or the name should start "
        "with an underscore to say it is a discarded slot:\n  "
        + "\n  ".join(f"{f}:{ln} {fn}() `{v}`" for f, fn, v, ln in bad))


def test_no_render_in_app_js_builds_a_string_it_never_places():
    bad = [(fn, v, ln) for fn, v, ln in _js_unread()
           if (fn, v) not in JS_ALLOWED]
    assert not bad, (
        "declared and never read — a render doing work it throws away:\n  "
        + "\n  ".join(f"app.js:{ln} {fn}() `{v}`" for fn, v, ln in bad))


# --- the allowlist is not a place to hide things -----------------------------
def test_every_allowance_names_a_real_binding():
    """An entry whose code has moved on is an allowance protecting
    nothing, and the next real instance in that function slips under it."""
    live = {(f, fn, v) for f, fn, v, _ in _py_unread()}
    stale = [k for k in PY_ALLOWED if k not in live]
    assert not stale, (
        f"these allowances no longer match any binding — delete them, or "
        f"the next unread value in that function passes silently: {stale}")


def test_every_allowance_carries_a_reason():
    empty = [k for k, why in PY_ALLOWED.items() if not str(why).strip()]
    assert not empty, f"allowed with no reason given: {empty}"


def test_the_javascript_allowlist_is_empty():
    """Not a rule about JavaScript — a statement about this codebase.
    Every instance found in app.js so far has been a real discard, and an
    entry here should have to argue with this sentence first."""
    assert not JS_ALLOWED, (
        "something was added to JS_ALLOWED. Every app.js instance found so "
        "far was a render doing work nobody read; say why this one is not.")


# --- the two that started it stay dead ---------------------------------------
def test_the_exchange_report_reaches_the_board():
    """The 2026-09-18 find. `fetch_sports_markets` returns a per-series
    report whose docstring says it exists to distinguish "wrong name"
    from "feed down"; `attach_to_board` dropped it, so an exchange that
    was entirely unreachable was reported as a matching failure."""
    src = (ROOT / "engine" / "exchangefair.py").read_text()
    i = src.index("def attach_to_board")
    body = src[i:]
    assert 'result["exchange_series"]' in body, \
        "the per-series report is fetched and never published"
    assert "THE FEED IS DOWN" in body, \
        "a total outage is not named; it reads as a matching problem"


def test_the_mock_draft_does_not_rebuild_the_lists_it_replaced():
    src = (ROOT / "web" / "js" / "app.js").read_text()
    i = src.index("function mockDraftHTML")
    body = src[i:i + 9000]
    assert "const avail = sheet.slice(0, 12)" not in body, \
        "the pre-redesign available list is being built again"
    assert "const recent = m.log.slice(-m.teams)" not in body, \
        "the pre-redesign recent list is being built again"
    # And the lists that DID replace them are still placed.
    assert "poolList" in body and "boardList" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
