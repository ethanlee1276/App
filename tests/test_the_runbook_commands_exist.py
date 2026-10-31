"""Every command in the runbook is one the CLI it names would accept.

FOUND BY RUNNING IT. Ethan, 2026-09-16, working through seven droplet
blocks: *"two of the doc's commands do not work as written … potd_report
.py --all in ALT does not exist and exits 2 silently … The GATE line
omits backtest.py's required season positional and also exits 2."*

Both were mine, and both were invisible from here: a runbook is prose to
every check this repo runs, so a flag that no parser defines reads
exactly like one that does. The cost lands on whoever pastes it — argparse
exits 2 and prints usage to stderr, which inside a `cd … && python3 …`
one-liner is easy to miss entirely.

THIS IS THE OTHER HALF OF THE DISCOVERABILITY WORK. #77's sweep asked
whether every flag a CLI accepts is documented. This asks whether every
flag the documentation uses is accepted, which is the direction that
wastes somebody's twenty-five minutes.

Deliberately shallow: it reads `add_argument` calls as text rather than
importing the parsers, because importing them pulls in the whole engine
and this has to stay a cheap test. That is enough to catch both defects.

Run through the gate's env.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md")

#: `python3 <script>.py <rest of the line>` inside a fenced block.
_CMD = re.compile(r"python3\s+([A-Za-z_][\w./-]*\.py)((?:\s+[^\n|>]*)?)")


def _commands():
    text = open(DOC).read()
    for m in _CMD.finditer(text):
        script, rest = m.group(1), (m.group(2) or "").strip()
        path = os.path.join(ROOT, script)
        if not os.path.exists(path):
            continue                      # a droplet-only path, not ours
        yield script, path, rest


def _declared_flags(path) -> set:
    """Every long flag the script names, in EITHER CLI style.

    Not just `add_argument`: `launch.py` is a bare-argv CLI with its own
    declared flag list, and reading only argparse calls reported three of
    its real flags as undefined. That is the same mistake made once
    already this session against `tdbook`, so the rule here is the
    permissive one — a flag counts as declared if the script mentions it
    as a string literal at all. A false PASS here costs nothing; a false
    FAIL sends somebody to fix a command that works.
    """
    return set(re.findall(r'["\'](--[\w-]+)["\']', open(path).read()))


def _required_positionals(path) -> list:
    """Positional `add_argument` calls with no `nargs`, in order."""
    out = []
    for m in re.finditer(r'add_argument\(\s*["\']([A-Za-z][\w-]*)["\']([^)]*)',
                         open(path).read()):
        name, tail = m.group(1), m.group(2)
        if "nargs" not in tail:
            out.append(name)
    return out


def _used_flags(rest) -> set:
    return {t.split("=")[0] for t in rest.split() if t.startswith("--")}


# --- the two Ethan tripped over -----------------------------------------------
def test_every_flag_the_runbook_uses_is_one_its_cli_defines():
    bad = []
    for script, path, rest in _commands():
        declared = _declared_flags(path)
        for flag in _used_flags(rest):
            if flag not in declared:
                bad.append(f"{script} {flag}")
    assert not bad, ("the runbook passes flags no parser defines, and argparse "
                     f"exits 2 on each: {sorted(set(bad))}")


def test_every_required_positional_is_supplied():
    """`backtest.py` takes a season. The GATE block did not pass one, so
    the command Ethan pasted exited 2 before it measured anything."""
    bad = []
    for script, path, rest in _commands():
        need = _required_positionals(path)
        if not need:
            continue
        given = [t for t in rest.split() if not t.startswith("-")]
        # Values that belong to a preceding `--flag value` pair are not
        # positionals. Cheap approximation: drop any token whose
        # predecessor is a flag without "=".
        toks, keep = rest.split(), []
        for i, t in enumerate(toks):
            if t.startswith("-"):
                continue
            if i and toks[i - 1].startswith("--") and "=" not in toks[i - 1]:
                continue
            keep.append(t)
        given = keep
        if len(given) < len(need):
            bad.append(f"{script} needs {need}, the doc passes {given or 'none'}")
    assert not bad, bad


# --- and the check itself is not vacuous --------------------------------------
def test_the_runbook_actually_contains_commands_to_check():
    """A regex that silently matches nothing would pass both tests above
    forever."""
    found = list(_commands())
    assert len(found) >= 10, f"only {len(found)} runbook commands matched"
    assert any(_used_flags(rest) for _, _, rest in found), \
        "no command in the runbook passes a flag — the flag test is asleep"


def test_it_only_judges_scripts_that_live_here():
    """The runbook also names droplet-only paths and systemd units. Those
    are out of scope, and pretending otherwise would make this test fail
    on things it cannot see."""
    for script, path, _ in _commands():
        assert os.path.exists(path), script


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
