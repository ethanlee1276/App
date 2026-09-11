"""The three strongest fits on this site had never run for college.

Ethan, 2026-09-04: "do we have all the calibrations and models and
hypothesis and data and ai and all that shit for CFB like we have for
other sports so our edge model an best bet models are elite".

No. `formfit.SPORT_MARKETS` excluded college, and the comment saying why
had gone stale:

    "CFB and UFC are deliberately absent. College is priced at GAME level
     (spread / total / moneyline) and has no player-prop logs to walk...
     listing them here would offer a fit that can never run."

Both halves are false now. College holds 237,242 ingested player-log
rows, and `cfb_build` prices four player markets through
`pipeline.price_props(sport="cfb")` — the same call the NFL board makes.
The premise was overtaken by #60 and the player-props work after it, and
nobody returned to the dict.

THE COST WAS SILENT AND TOTAL. `deepfit.sports_with_history` counts rows
only for sports listed there, so a quarter of a million college rows were
never counted, `refit_sport` was never called, and the recency dial, the
per-player memory and the probability temperatures have never run for
college football. Not declined on the evidence — never offered it.

AND THE EVIDENCE WAS DAMNING. Fitted the day it was listed: three of the
four markets claim SIX TO SEVEN POINTS TOO MUCH, on 16,000 to 24,000
settled predictions each. A college card reading 57% was really about
50%, and the board has priced and recommended on the uncorrected number
for as long as college has had props.

TWO TESTS WERE WRITTEN FOR THIS FILE AND DELETED BEFORE IT SHIPPED,
because `test_preservation` caught them reading machine-local state —
the same class of fault this session spent the morning fixing in
`test_cfbd_empty_cache`, where a test could only pass on a machine with
no internet. The guard was right both times and neither was worth
keeping:

  * one asserted college qualifies for a deep fit by counting rows in
    the live `data/history.db`. `test_deepfit` now asserts the same thing
    against a fixture DB it writes itself, which is the honest form.
  * one asserted the sandbox's fitted temperatures were not committed by
    reading `data/models/calibration.json`. That directory is in
    .gitignore, so the property is guaranteed by construction and the
    test bought nothing but a dependency on the machine.

Satisfying the guard by adding a `tempfile` import it would have skipped
on was available and would have been a lie.

Run directly: `python3 tests/test_cfb_deepfit.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import calibrate                                             # noqa: E402
import formfit                                               # noqa: E402
import playerfit                                             # noqa: E402
from engine import deepfit                                   # noqa: E402

FOUR = ["pass_yds", "rush_yds", "rec_yds", "receptions"]


def test_all_three_deep_fitters_accept_college():
    """One missing dict entry and the sport is not a legal `--sport`
    value, so `refit_sport` shells out and the CLI rejects it."""
    for mod in (formfit, playerfit, calibrate):
        got = mod.SPORT_MARKETS.get("cfb")
        assert got == FOUR, f"{mod.__name__} lists cfb as {got}"


def test_the_markets_listed_are_the_markets_the_board_prices():
    """A fit offered for a market the board never prices is wasted
    minutes on a one-core box; a market priced with no fit is this bug."""
    src = open(os.path.join(ROOT, "engine", "cfb", "props.py"),
               encoding="utf-8").read()
    i = src.index("MARKETS")
    for market in FOUR:
        assert market in src[i:i + 400], \
            f"{market} is fitted but the college slate does not build it"


def test_ufc_stays_out_and_says_why():
    """The original comment was not wrong about everything. UFC has no
    game logs at all, so a fit there could never run — and a dict that
    lists it would spend a weekly slot proving that."""
    for mod in (formfit, playerfit, calibrate):
        assert "ufc" not in mod.SPORT_MARKETS, mod.__name__
    src = open(os.path.join(ROOT, "formfit.py"), encoding="utf-8").read()
    assert "UFC remains deliberately absent" in src


def test_what_the_first_fit_found_is_written_down():
    """A number this large decides whether college props are bettable at
    all, and it is the reason the listing was worth doing. Kept where the
    listing is, so the next person does not re-derive it."""
    src = open(os.path.join(ROOT, "formfit.py"), encoding="utf-8").read()
    for row in ("pass_yds        4,620    0.50   +0.10",
                "rush_yds       16,253    0.48   -0.26",
                "rec_yds        23,681    0.68   -0.26",
                "receptions     21,259    0.40   -0.30"):
        assert row in src, f"the first college fit lost: {row}"
    assert "AT THE GRID EDGE" in src, \
        "the receptions market's unreliability signal is no longer recorded"
    assert "NOT\n    # committed" in src or "are NOT" in src, \
        "the note that these came from this checkout's history is gone"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
