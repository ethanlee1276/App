"""A local import shadowed a module function and froze the college board.

THE CRASH, from the droplet's journal, every cycle for most of a day:

    build failed: cfb_build.py 2026-08-30 — exit 1: UnboundLocalError:
    cannot access local variable '_recent_games' where it is not
    associated with a value

`cfb_build.main()` calls the module-level `_recent_games(day, lookup)`
on its no-games branch.175 lines LATER, the same function did:

    from engine.teamlogs import recent_games as _recent_games

Python binds a name for the WHOLE function body wherever it is assigned,
and `import ... as` is an assignment. So that line made every earlier
reference an unbound local, and `main()` died before it could write —
which is why the board sat frozen with a status word that had aged into
a fossil. Not a feed, not a timeout, not the offseason logic. All three
of those were things I proposed before this line existed to be read.

WHY THE SUITE DID NOT CATCH IT, and this is the part worth keeping.
`tests/test_cfb_offseason_claim.py` exercises `_recent_games` by calling
`cfb_build._recent_games(...)` — the MODULE-LEVEL function, where there
is no shadow. And the tests written for the branch around it assert on
SOURCE TEXT: that a status string exists, that one branch precedes
another. Every one passed against code that could not run. A test that
reads a function's source is not a test that the function executes.

So this file does not read source text. It walks the AST of every module
and finds the one shape that produces this crash: a name READ in a
function before it is BOUND in that same function, where a module-level
function of that name exists to be shadowed. Shadowing alone is fine and
seven other sites do it harmlessly; reading before binding is the bug.

Run directly: `python3 tests/test_shadowed_locals.py`
"""

import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shadowed_reads(source: str):
    """`[(function, name, read_line, bind_line)]` — the crash shape.

    A module-level function's name, read inside some function BEFORE
    that function binds the same name. Binding it first is legal and
    common (a local alias for a helper); reading first is an
    UnboundLocalError waiting for the branch that reaches it.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    top = {n.name for n in tree.body
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    found = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        binds, reads = {}, {}
        for node in ast.walk(fn):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    nm = a.asname or a.name.split(".")[0]
                    binds[nm] = min(binds.get(nm, 1 << 30), node.lineno)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        binds[t.id] = min(binds.get(t.id, 1 << 30), t.lineno)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                reads[node.id] = min(reads.get(node.id, 1 << 30), node.lineno)
        for nm in (set(binds) & top) - {fn.name}:
            if nm in reads and reads[nm] < binds[nm]:
                found.append((fn.name, nm, reads[nm], binds[nm]))
    return found


def _files():
    return (sorted(glob.glob(os.path.join(ROOT, "*.py")))
            + sorted(glob.glob(os.path.join(ROOT, "engine", "**", "*.py"),
                               recursive=True)))


# --- the detector works ---------------------------------------------------
def test_it_finds_the_shape_that_crashed():
    """The bug, reduced. `helper` is read at the top and rebound at the
    bottom, so the read is an unbound local."""
    bad = ("def helper():\n    return 1\n"
           "def main():\n"
           "    x = helper()\n"
           "    from somewhere import helper\n"
           "    return x, helper\n")
    got = _shadowed_reads(bad)
    assert got and got[0][1] == "helper", got


def test_the_reduced_case_really_does_raise():
    """Guards the guard: proves the shape is fatal, not stylistic."""
    ns = {}
    exec("def helper():\n    return 1\n"
         "def main():\n"
         "    x = helper()\n"
         "    helper = 2\n"
         "    return x\n", ns)
    try:
        ns["main"]()
    except UnboundLocalError:
        return
    raise AssertionError("expected UnboundLocalError")


def test_binding_before_reading_is_not_flagged():
    """Seven sites in this codebase alias a module function locally and
    are perfectly fine. Flagging them would make this file noise."""
    ok = ("def helper():\n    return 1\n"
          "def main():\n"
          "    from somewhere import helper\n"
          "    return helper()\n")
    assert _shadowed_reads(ok) == []


def test_a_plain_call_with_no_shadow_is_not_flagged():
    ok = ("def helper():\n    return 1\n"
          "def main():\n    return helper()\n")
    assert _shadowed_reads(ok) == []


def test_a_functions_own_name_is_not_a_shadow():
    """Recursion rebinding nothing."""
    ok = ("def main():\n    return main\n")
    assert _shadowed_reads(ok) == []


# --- and the codebase is clean --------------------------------------------
def test_no_module_reads_a_function_it_later_rebinds():
    """THE GUARD. This is the check that would have caught the college
    board's crash before it shipped, and it costs one AST walk."""
    bad = []
    for path in _files():
        with open(path, encoding="utf-8") as f:
            for fn, nm, read, bind in _shadowed_reads(f.read()):
                bad.append(f"{os.path.relpath(path, ROOT)}:{fn}() reads "
                           f"{nm}() at line {read}, rebinds it at {bind}")
    assert not bad, "\n".join(bad)


def test_the_specific_alias_that_broke_it_is_gone():
    """Named explicitly so a reader of this file learns the case."""
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert "import recent_games as _recent_games" not in src
    assert "import recent_games as _tl_recent_games" in src


def test_the_module_level_helper_is_still_there_and_still_called():
    import cfb_build
    assert callable(cfb_build._recent_games)
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as f:
        assert "recent = _recent_games(day, lookup)" in f.read()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
