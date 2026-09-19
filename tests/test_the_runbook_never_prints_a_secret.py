"""No command in the runbook can print a secret as a side effect.

FOUND BY REFUSING TO RUN IT. Ethan, 2026-09-16, working through the
droplet blocks: *"Section 1b's check greps an unanchored TZ, which
matches a promo code and would print all 30 live discount codes. Anchor
it to ^(MALLOC_ARENA_MAX|TZ)=."*

The command was

    tr '\\0' '\\n' < /proc/.../environ | grep -E 'MALLOC|TZ'

and the two letters TZ appear inside a promo code. `QB_PROMOS` lives in
that same environment, so the filter that was there to show two settings
would have dumped every live discount code into a terminal — and into
whatever it was pasted back into.

THE RULE. A process environment holds every secret the service has. Any
command in this file that reads one filters by ANCHORED VARIABLE NAMES —
`^NAME=` — or it is a secret dump with a filter-shaped comment above it.
Substring matching against a bag of secrets is not a filter.

Deliberately narrow: it checks the shape of the filter rather than
trying to guess which variables are secret, because the set of secrets
changes and the shape does not.

Run through the gate's env.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md")

#: Commands that read a process environment, however they reach it.
_ENVIRON = re.compile(r"[^\n]*/proc/[^\n]*environ[^\n]*(?:\n[^\n]*)?")


def _environ_commands():
    """Each runbook line that reads /proc/<pid>/environ, with the line
    after it — the filter is usually on the continuation."""
    text = open(DOC, encoding="utf-8").read()
    return [m.group(0) for m in _ENVIRON.finditer(text)]


# --- the rule -----------------------------------------------------------------
def test_every_environ_read_filters_on_anchored_names():
    bad = []
    for cmd in _environ_commands():
        if "grep" not in cmd and "awk" not in cmd:
            bad.append(f"no filter at all: {cmd.strip()[:90]}")
            continue
        # An anchored name filter looks like ^NAME= or ^(A|B)= .
        if not re.search(r"\^\(?[A-Z_]", cmd):
            bad.append(f"unanchored: {cmd.strip()[:90]}")
    assert not bad, (
        "a runbook command reads the service environment without anchoring "
        "its filter to variable NAMES — that environment holds QB_PROMOS "
        f"and every other secret the service has: {bad}")


def test_the_check_is_not_vacuous():
    """A regex that matched nothing would pass the rule above forever."""
    cmds = _environ_commands()
    assert cmds, "no environ command found — the pattern stopped matching"
    assert any("MALLOC" in c for c in cmds), \
        "the memory-setting check is gone; this test may be reading nothing"


def test_the_unanchored_form_would_be_caught():
    """MUTATION, INLINE. The exact command Ethan refused, checked against
    the rule — so a future edit that reintroduces it fails here rather
    than on his screen."""
    old = "tr '\\0' '\\n' < /proc/1/environ | grep -E 'MALLOC|TZ'"
    assert "grep" in old and not re.search(r"\^\(?[A-Z_]", old), \
        "the rule stopped recognising the shape it was written for"


def test_no_block_echoes_the_promo_variable_by_name():
    """The other way to leak it: printing the variable itself. Reading
    `QB_PROMOS` to check it is SET is fine; printing its value is not,
    and neither is any command that would."""
    text = open(DOC, encoding="utf-8").read()
    for line in text.splitlines():
        if "QB_PROMOS" not in line:
            continue
        low = line.lower()
        assert not any(w in low for w in ("echo $", "printenv qb_promos",
                                          'echo "$')), line
    # …and the literal value never appears in the repo at all.
    assert "QB_PROMOS=" not in text, \
        "a promo value may have been pasted into the runbook"


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
