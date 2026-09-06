"""What `launch.py` accepts on the command line, and what it refuses.

Ethan, 2026-09-06, ran `python3 launch.py --resettle` — a command this
script's OWN parlay report told him to run — and got:

    ⚠️  Port 8000 is already in use — Qellys Book is almost certainly
        already running.

Which is a true sentence about a question nobody asked. Every branch in
`main` is `if "--x" in argv`, so a flag nothing recognises matches
nothing and falls out the bottom of the function, where the web server
lives. The operator reads a port warning and concludes the box is broken.

TWO DEFECTS, AND THE SECOND IS THE ONE WORTH KEEPING. The message
prescribed a flag that does not exist (fixed at its source). But any
typo did the same thing, and always would have — so `main` now refuses a
flag it does not know, by name, with a suggestion.

WHY `KNOWN_FLAGS` IS WRITTEN BY HAND. The obvious implementation derives
it by scanning our own source for `"--x" in argv`. That is wrong in both
directions, which is what these tests pin:

  * `--since` is consumed inside a `for flag in ("--sport", "--since")`
    loop. No regex over the file sees it, so a scan would refuse a
    working command.
  * `--resettle` appeared in a print string. A scan of every `"--x"`
    literal would have ACCEPTED it — the precise bug being fixed.

So the set is explicit, and `test_no_flag_went_unregistered` reads the
source to catch the drift a hand-written list invites: add a flag,
forget to list it, and the suite fails instead of an operator at 1am.

Run directly: `python3 tests/test_known_flags.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _launch_ns():
    """`KNOWN_FLAGS` and `unknown_flags` without importing the world.

    Importing launch.py drags in the whole build. The two objects under
    test are pure, so the block that defines them is executed alone.
    """
    src = _src()
    start = src.index("KNOWN_FLAGS = frozenset({")
    end = src.index("def main() -> None:")
    ns: dict = {}
    exec(compile(src[start:end], "launch.py", "exec"), ns)
    return ns


def _src():
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as fh:
        return fh.read()


def test_the_command_ethan_typed_is_refused_by_name():
    """THE REPORTED BUG. Not 'some unknown flag' — this one."""
    ns = _launch_ns()
    assert ns["unknown_flags"](["--resettle"]) == ["--resettle"]


def test_a_known_flag_is_not_refused():
    ns = _launch_ns()
    assert ns["unknown_flags"](["--settle"]) == []


def test_a_flag_consumed_only_inside_a_loop_is_still_known():
    """`--since` is the reason this set is not a source scan. If someone
    'simplifies' KNOWN_FLAGS into a regex over launch.py, this fails."""
    ns = _launch_ns()
    assert ns["unknown_flags"](["--sport", "nfl", "--since", "2026-08-01"]) == []


def test_values_are_never_judged():
    """A guard that guesses at arguments breaks working commands. A date,
    a sport and a player name are arguments, not flags."""
    ns = _launch_ns()
    assert ns["unknown_flags"](["--settle", "2026-09-05"]) == []
    assert ns["unknown_flags"](["--why-pick", "Bobby Witt Jr."]) == []
    assert ns["unknown_flags"](["8001"]) == []


def test_every_bad_flag_is_named_once_and_in_order():
    """An operator who mistyped two should see both, not the first."""
    ns = _launch_ns()
    assert ns["unknown_flags"](["--settle", "--bogus", "--worse"]) == [
        "--bogus", "--worse"]
    assert ns["unknown_flags"](["--bogus", "--bogus"]) == ["--bogus"]


def test_another_programs_command_line_is_not_judged():
    """`--renders` forwards its whole tail to `rendercheck.main`, which
    has its own `--width` and `--shots`. GUIDE.md documents
    `launch.py --renders --shots out/`, so a guard that judged every
    token would have broken a working, documented command the day it
    shipped — which is a worse bug than the one being fixed.

    Judging stops AT the passthrough flag, not after the next token: a
    passthrough forwards everything, not one argument.
    """
    ns = _launch_ns()
    assert ns["unknown_flags"](["--renders", "--shots", "out/"]) == []
    assert ns["unknown_flags"](["--renders", "--width", "390",
                                "--anything-at-all"]) == []
    # But a bad flag BEFORE it is still ours, and still refused.
    assert ns["unknown_flags"](["--bogus", "--renders", "--shots"]) == [
        "--bogus"]


def test_every_passthrough_flag_is_itself_a_known_flag():
    """A passthrough that main() cannot parse would swallow the whole
    line and then fall through to the server — the original bug wearing
    a bigger hat."""
    ns = _launch_ns()
    assert ns["PASSTHROUGH_FLAGS"] <= ns["KNOWN_FLAGS"]


def test_no_flag_went_unregistered():
    """THE DRIFT GUARD. Every flag the source visibly consumes must be in
    KNOWN_FLAGS, or adding a flag silently makes it unusable.

    Only the shapes a regex can actually see are checked — the loop-driven
    ones cannot be, which is why the set is hand-written and why
    `test_a_flag_consumed_only_inside_a_loop_is_still_known` exists
    beside this.
    """
    src = _src()
    consumed = set()
    for pat in (r'"(--[a-z0-9-]+)"\s+in\s+argv',
                r'argv\.index\(\s*"(--[a-z0-9-]+)"',
                r'a\.startswith\(\s*"(--[a-z0-9-]+)"'):
        consumed |= set(re.findall(pat, src))
    missing = sorted(consumed - _launch_ns()["KNOWN_FLAGS"])
    assert not missing, (
        f"flag(s) parsed by launch.py but not in KNOWN_FLAGS: {missing}. "
        f"Add them, or `python3 launch.py {missing[0]}` refuses a flag "
        f"that works.")


def test_nothing_registered_that_the_source_never_mentions():
    """The other direction. A flag in the set that appears NOWHERE else in
    launch.py is a leftover from something deleted — it would quietly
    accept a flag that does nothing at all.

    THE SET ITSELF IS CUT OUT OF THE SOURCE FIRST. Written the obvious
    way this test cannot fail: KNOWN_FLAGS lives in launch.py, so every
    name in it is trivially "mentioned in launch.py" by its own listing.
    A mutant adding a dead flag survived exactly that way. What has to be
    searched is the rest of the file.
    """
    src, ns = _src(), _launch_ns()
    start = src.index("KNOWN_FLAGS = frozenset({")
    rest = src[:start] + src[src.index("})", start) + 2:]
    orphans = [f for f in sorted(ns["KNOWN_FLAGS"]) if f'"{f}"' not in rest]
    assert not orphans, (
        f"registered but used nowhere in launch.py: {orphans}. Typing one "
        f"is accepted and then does nothing at all.")


def test_main_actually_calls_the_guard_before_anything_else():
    """THE WIRING, WHICH IS THE WHOLE BUG. `unknown_flags` can be perfect
    and the reported failure still happen, because what broke was that
    `main` never asked. Every test above this one calls the helper
    directly and would pass with the guard deleted from `main` — a mutant
    proved it.

    Checked structurally rather than by running `main`: on a mutant where
    the guard is gone, executing it with a bad flag falls through to the
    bottom of the function and starts a web server inside the test suite.
    So the assertion is that the FIRST branch in `main` is the guard, and
    that it returns.
    """
    import ast
    fn = next(n for n in ast.walk(ast.parse(_src()))
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    first_if = next(n for n in fn.body if isinstance(n, ast.If))
    calls = {getattr(c.func, "id", "") for c in ast.walk(first_if.test)
             if isinstance(c, ast.Call)}
    assert "unknown_flags" in calls, (
        "the first branch of main() is no longer the unknown-flag guard — "
        "an unrecognised flag falls through to the server launcher again")
    assert any(isinstance(n, ast.Return) for n in ast.walk(first_if)), (
        "the guard no longer returns, so a refused flag carries on into "
        "the rest of main()")


#: Flags launch.py PRINTS that belong to some other tool. Each is a real
#: command an operator is meant to type — at a different program — so the
#: test below must not read them as our own. Listed with their owner so
#: the next addition is a decision rather than a silent exemption.
FOREIGN_PRINTED_FLAGS = {
    "--bg": "tailscale serve",
    "--budget": "the odds harvester",
    "--cached-odds": "ufc_build.py / the sport builds",
    "--info": "stakecheck",
    "--now": "tools/install-nightly.sh",
    "--odds": "the sport builds",
    "--seasons": "ingest.py",
    "--show": "deploy/setenv.sh",
}


def test_nothing_printed_prescribes_a_flag_we_cannot_parse():
    """THE ORIGINAL LIE, GENERALISED — and the half worth keeping.

    The parlay report told the operator to run a flag that did not exist.
    Pinning that one word would stop that one line coming back and
    nothing else. What actually needs to hold is the rule it broke:
    every flag of OUR shape that launch.py prints must be one launch.py
    can parse, or belong to a named other tool.

    Printed strings only, read through the AST. Comments and docstrings
    are for whoever is reading the code and may discuss a flag that was
    removed; a `print` is an instruction to a human at a terminal.
    """
    import ast
    printed: dict = {}
    for node in ast.walk(ast.parse(_src())):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "print"):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                for f in re.findall(r"--[a-z0-9]+(?:-[a-z0-9]+)*", sub.value):
                    printed.setdefault(f, node.lineno)
    known = _launch_ns()["KNOWN_FLAGS"]
    bad = {f: ln for f, ln in printed.items()
           if f not in known and f not in FOREIGN_PRINTED_FLAGS}
    assert not bad, (
        "launch.py prints flag(s) it cannot parse: "
        + "; ".join(f"{f} (line {ln})" for f, ln in sorted(bad.items()))
        + ". Either add it to KNOWN_FLAGS and implement it, or name the "
          "tool it belongs to in FOREIGN_PRINTED_FLAGS, or stop printing "
          "it — an operator who types it gets the server, not an error.")


def test_the_stale_rows_are_explained_rather_than_falsely_remedied():
    """`--settle` would not have cleared them either: `resettle` skips a
    ticket whose legs have not moved, and `_loss_codes` runs only from
    `_grade_ticket`. Naming a second command would have been the same
    bug with a different word, so the report explains and stops."""
    src = _src()
    at = src.index("CORRELATION_ERROR rows are from before")
    block = src[at:at + 1600]
    assert "nothing re-codes a" in block
    assert "settled history" in block


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
