"""Where the fitters keep what they have measured.

Four modules persist a measurement between runs — the correlation priors,
the CFB team map, the hold watch and the game-line calibration — and all
four wrote ``data/feedstate/<name>.json`` directly. That directory is
gitignored, which is right (a fit belongs to the box that measured it,
not to the repo) and had one consequence nobody had noticed: the TEST
SUITE reads it.

`run_tests.py` already states the doctrine this exists to enforce —
"THE SUITE MUST NOT READ THE BOX IT IS RUNNING ON" — and gives two
examples of a gate judging the box rather than the code. A pricing path
that consults a state file present on the droplet and absent in a fresh
clone is the same failure with a longer fuse: the game-line calibration
can change whether an NFL spread grades Play, so the same commit could
be green in the container and red in production, or worse, the reverse.

So the location is resolved through the environment, and the suite points
it at its own sandbox. Nothing else changes: unset, which is every real
run, the answer is the path these modules always used.

Standard library only.
"""

from __future__ import annotations

import os

#: Overridden by `run_tests.py` so a suite run measures the code and not
#: the machine. Never set this in production.
ENV_VAR = "QB_FEEDSTATE_DIR"

DEFAULT_DIR = os.path.join("data", "feedstate")


def directory() -> str:
    """The feedstate directory for this process."""
    return os.environ.get(ENV_VAR) or DEFAULT_DIR


def path(name: str) -> str:
    """The full path of one state file, e.g. ``path("corr.json")``."""
    return os.path.join(directory(), name)
