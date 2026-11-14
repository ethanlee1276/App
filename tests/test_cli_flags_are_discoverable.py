"""Every mode flag this repo accepts can be found without reading source.

THE BUG THAT PROMPTED THIS, 2026-09-16. #77 — "does the market shrink
help or hurt the top of the board?" — sat open for weeks reading as
though the measurement still had to be built. It did not: `tdbook
.shrink_report` answered it, `python3 -m engine.tdbook --shrink` ran it,
and that flag was in NO USAGE TEXT. `tdbook`'s help line listed --roi and
--rank and stopped. A flag nobody can find is a flag nobody runs.

The same day turned up `gamerank.measure_market_moneyline`, which had no
CLI path at all, and three guards that could not fire. The pattern is not
missing capability — it is capability nobody can reach.

WHAT THIS ENFORCES, and what it deliberately does not.

  * A MODE flag (`action="store_true"`) must carry `help=`. Those change
    what the tool DOES, so one without a help line is a feature hidden
    inside a file.
  * A bare-argv CLI — one that reads `"--x" in argv` rather than using
    argparse — must print every flag it accepts somewhere in its own
    `__main__` block. argparse writes its own help; these cannot.

NOT ENFORCED: `help=` on value options like `--db`, `--out`, `--sport`.
Those are self-evident from the name, argparse lists them in the usage
line either way, and 127 of them would be churn against no risk. The
failure this file exists for is a MODE nobody knows about.

Run through the gate's env.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules", "tests", "web", "data",
             "venv", ".venv"}


def _sources():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if f.endswith(".py"):
                p = os.path.join(base, f)
                yield (os.path.relpath(p, ROOT),
                       open(p, encoding="utf-8", errors="replace").read())


def test_every_mode_flag_explains_itself():
    """`action="store_true"` with no `help=`. argparse will print the
    flag in the usage line and nothing about what it does, so a reader
    sees a word and has to open the file to learn whether it is the one
    they want."""
    bad = []
    for rel, src in _sources():
        for m in re.finditer(r'add_argument\(\s*("--[a-z0-9-]+")(.*?)\)\s*\n',
                             src, re.S):
            body = m.group(2)
            if "store_true" in body and "help=" not in body:
                bad.append(f"{rel} {m.group(1).strip(chr(34))}")
    assert not bad, (
        "these mode flags carry no help= — each is a feature hidden inside "
        "a file, which is how #77 sat open for weeks:\n  " + "\n  ".join(bad))


def test_a_cli_that_writes_its_own_help_lists_every_flag_it_takes():
    """A bare-argv CLI gets no help from argparse. Whatever it accepts is
    discoverable only if it says so itself — and `tdbook --shrink` is the
    proof that "only if" is load-bearing."""
    bad = []
    for rel, src in _sources():
        if '__name__ == "__main__"' not in src:
            continue
        block = src[src.index('__name__ == "__main__"'):]
        flags = set(re.findall(r'"(--[a-z0-9-]+)" in (?:argv|sys\.argv)',
                               block))
        flags.discard("--help")
        flags.discard("-h")
        if not flags:
            continue                      # argparse, or no flags at all
        printed = " ".join(re.findall(r'print\((.*?)\)\n', block, re.S))
        for flag in sorted(flags):
            if flag not in printed:
                bad.append(f"{rel} {flag}")
    assert not bad, (
        "these bare-argv CLIs accept a flag they never mention:\n  "
        + "\n  ".join(bad))


def test_the_flag_that_started_this_is_still_discoverable():
    """The specific one, by name, so the general rules above cannot be
    satisfied in a way that loses it again."""
    src = open(os.path.join(ROOT, "engine", "tdbook.py"),
               encoding="utf-8").read()
    assert '"--shrink" in argv' in src
    assert "--shrink to ask" in src, "#77's flag is undiscoverable again"


def test_the_rule_is_checkable_at_all():
    """THE GUARD ON THE GUARD. Both tests above pass trivially if the
    scan finds no files — a broken walk, a renamed directory, a bad
    regex. Establish that it is actually reading this repository."""
    rels = [rel for rel, _ in _sources()]
    assert len(rels) > 100, f"the scan found {len(rels)} source files"
    assert "engine/tdbook.py" in rels and "potd_report.py" in rels
    joined = "".join(src for _, src in _sources())
    assert joined.count("add_argument(") > 50, "the scan sees no CLIs at all"


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
