"""Where the FITTERS keep the models they have fitted.

`engine.feedstate` closed this door for ``data/feedstate/``. This is the
same door, one directory over, and it was still open — found 2026-08-27
when GitHub Actions went red on three consecutive commits that the local
suite called green.

The cause was exactly what feedstate's docstring warns about, with the
longer fuse it predicts. `engine.cfbtdfit` fitted a temperature for the
college touchdown market and wrote it to ``data/models/calibration.json``.
That file is gitignored — correctly, a fit belongs to the box that
measured it — so it existed on the machine running the suite and not in
CI's fresh clone. The correction LIFTS a modelled probability, which is
what pushed a fixture's quotes over the EV bar, so
`test_td_board.test_cfb_board_prices_quoted_players_with_usage_and_says
_the_rest` asserted picks that only existed because of a file the repo
does not contain.

The suite was green for three commits while the release gate was red, and
the direction is the dangerous one: a local run that passes because the
box is richer than a clone will keep passing right up until it is
deployed somewhere that never fitted anything.

Ten modules keep something under this directory — the calibration store,
the recency dial, the player memory, the loss patterns, the hypothesis
ledger, the preregistrations, the selection fit and the written prose. All
of them now resolve their path through here, and `run_tests.py` points it
at the suite's sandbox. Unset, which is every real run, the answer is the
path these modules always used.

Standard library only.
"""

from __future__ import annotations

import os

#: Overridden by `run_tests.py` so a suite run measures the code and not
#: the machine. Never set this in production.
ENV_VAR = "QB_MODELS_DIR"

DEFAULT_DIR = os.path.join("data", "models")


def directory() -> str:
    """The models directory for this process."""
    return os.environ.get(ENV_VAR) or DEFAULT_DIR


def path(name: str) -> str:
    """``<models dir>/<name>``, as a plain string.

    A string and not a Path because the callers differ — some build a
    `pathlib.Path` from it and some hand it straight to `open` — and a
    resolver that returns the simplest thing is the one nobody has to
    convert back.
    """
    return os.path.join(directory(), name)


__all__ = ["ENV_VAR", "DEFAULT_DIR", "directory", "path"]
