"""tools/fit.sh — the droplet's four jobs, in the order that is correct.

Ethan runs this from a phone console after a deploy. Two things about it
are load-bearing and neither is obvious from reading the file quickly,
so both are pinned here.

Run directly: `python3 tests/test_fit_script.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SRC = open(os.path.join(ROOT, "tools", "fit.sh"), encoding="utf-8").read()


def test_calibration_runs_last():
    """THE ONE THAT MATTERS, and the first cut had it wrong.

    A temperature is fitted against a specific model's claims. Player
    memory changes per-player projections and the recency dial changes
    how the form window is weighted — so both move the claims that
    calibration was fitted to, leaving the correction describing a model
    that no longer exists.

    Not reasoned about: formfit itself printed the reason on the droplet
    on 2026-08-25, at the end of a run where calibration had gone
    second — "Adopted weights change the model — refit its temperature
    next, on the new model".
    """
    order = re.findall(r'run "NFL ([a-z ]+)"', SRC)
    assert order, "the NFL fits are gone from the script"
    assert order[-1] == "probability calibration", \
        f"calibration must run last, on the finished model — got {order}"


def test_the_service_is_restarted_afterwards():
    """Every fitted store is read once per process and cached for its
    lifetime, so a fit that writes a perfect file changes nothing at all
    on a server that is already running. The restart is what makes the
    work count, and putting it in the script is what stops it being
    forgotten at 1am on a phone."""
    assert "systemctl restart qellys" in SRC
    i = SRC.index("systemctl restart qellys")
    assert SRC.index('run "NFL probability calibration"') < i, \
        "the restart happens before the last fit has written"


def test_it_survives_the_console_hanging_up():
    """Closing the browser tab on the droplet console sends SIGHUP to
    everything the shell started. A twenty-minute fit that dies with the
    tab — and does not say so — is worse than one that was never
    started."""
    assert "setsid nohup" in SRC
    assert "--status" in SRC, "no way to ask how far it got"


def test_it_yields_the_core_to_the_site():
    """One vCPU, and the site is serving on it."""
    assert "nice -n 10" in SRC


def test_it_refuses_to_run_twice_at_once():
    assert 'kill -0 "$(cat "$LOCK")"' in SRC


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
