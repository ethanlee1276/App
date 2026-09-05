"""Where the fitters keep what they measured — and why the suite can't read it.

`run_tests.py` carries the rule in capitals: *"THE SUITE MUST NOT READ THE
BOX IT IS RUNNING ON."* It was written about two secrets leaking in from
`/etc/qellys/env`. The same door was standing open one directory over.

Four modules persist a fit under `data/feedstate/` — the correlation
priors, the CFB team map, the hold watch, and the game-line calibration.
That directory is gitignored, so it exists on the droplet and not in a
fresh clone, and the last of those four sits on the PRICING PATH: the
game-line calibration decides how much of a disagreement with the closing
number a spread keeps, which decides whether it grades Play. A suite that
reads it returns a verdict about the machine.

Run directly: `python3 tests/test_feedstate.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import feedstate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATEFUL = ("corrfit", "cfbteams", "holdwatch", "gamecal",
            "streak", "moments")


def test_the_default_is_the_path_these_modules_always_used():
    keep = os.environ.pop(feedstate.ENV_VAR, None)
    try:
        assert feedstate.directory() == os.path.join("data", "feedstate")
        assert feedstate.path("corr.json") == os.path.join(
            "data", "feedstate", "corr.json")
    finally:
        if keep is not None:
            os.environ[feedstate.ENV_VAR] = keep


def test_the_environment_moves_every_state_file_together():
    keep = os.environ.get(feedstate.ENV_VAR)
    os.environ[feedstate.ENV_VAR] = "/tmp/qb-feedstate-test"
    try:
        assert feedstate.directory() == "/tmp/qb-feedstate-test"
        assert feedstate.path("gamecal.json").startswith(
            "/tmp/qb-feedstate-test")
    finally:
        if keep is None:
            os.environ.pop(feedstate.ENV_VAR, None)
        else:
            os.environ[feedstate.ENV_VAR] = keep


def test_an_empty_override_falls_back_rather_than_writing_to_the_root():
    """``QB_FEEDSTATE_DIR=""`` must not resolve to ``/gamecal.json``."""
    keep = os.environ.get(feedstate.ENV_VAR)
    os.environ[feedstate.ENV_VAR] = ""
    try:
        assert feedstate.directory() == os.path.join("data", "feedstate")
    finally:
        if keep is None:
            os.environ.pop(feedstate.ENV_VAR, None)
        else:
            os.environ[feedstate.ENV_VAR] = keep


def test_no_module_hardcodes_the_feedstate_directory_any_more():
    """The point of one resolver is that the four cannot drift apart.

    A fifth fitter added later with its own `os.path.join("data",
    "feedstate", ...)` would be invisible to the suite's sandbox and would
    reintroduce exactly the failure this file exists to close.
    """
    offenders = []
    for name in os.listdir(os.path.join(ROOT, "engine")):
        if not name.endswith(".py") or name == "feedstate.py":
            continue
        src = open(os.path.join(ROOT, "engine", name), encoding="utf-8").read()
        if re.search(r'["\']data["\']\s*,\s*["\']feedstate["\']', src):
            offenders.append(name)
        elif re.search(r'["\']data/feedstate', src):
            offenders.append(name)
    assert not offenders, (
        f"{offenders} build a feedstate path directly — use "
        f"engine.feedstate.path() so the suite's sandbox reaches it")


def test_every_stateful_module_resolves_through_the_helper():
    for mod in STATEFUL:
        src = open(os.path.join(ROOT, "engine", f"{mod}.py"),
                   encoding="utf-8").read()
        assert "_feedstate.path(" in src, mod
    # engine.feed keeps a whole directory rather than one file.
    src = open(os.path.join(ROOT, "engine", "feed.py"), encoding="utf-8").read()
    assert "_feedstate.directory()" in src


def test_the_suite_runner_sandboxes_the_directory():
    """Pinned in the runner, not just documented in it."""
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    assert feedstate.ENV_VAR in src
    # …and set AFTER the QB_ sweep, or the sweep eats it.
    assert src.index('name.startswith(("STRIPE_"') < src.index(
        f'env["{feedstate.ENV_VAR}"]')


def test_the_calibration_is_inert_without_a_state_file():
    """The property that makes a fresh clone behave like it always did."""
    from engine import gamecal
    keep, keep_cache = gamecal.STATE_PATH, dict(gamecal._cache)
    gamecal.STATE_PATH = "/nonexistent/qb/gamecal.json"
    gamecal._cache.clear()
    try:
        assert gamecal.shrink_for("nfl", "total") is None
        assert gamecal.note_for("nfl", "spread") is None
    finally:
        gamecal.STATE_PATH = keep
        gamecal._cache.clear()
        gamecal._cache.update(keep_cache)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
