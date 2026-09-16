"""Where the EV floor should sit is a measurement, not an opinion.

Ethan, 2026-09-16, looking at an MLB card that led with NO BET above a
named bet: *"we need to be confident in our pick, and if that's a good
pick, then we need to say to bet it, not to not bet it."* He chose to
lower the bar. This is the seam that says what to lower it TO.

WHAT IS AND IS NOT OVERRIDABLE. `potd.MIN_EV` stays the shipped bar and
nothing in the product moves it. `shortfall(row, min_ev=...)` is the one
bar a caller may supply, because a floor on HOW MUCH edge is enough is a
product judgement; the other refusals are about whether a number means
anything at all and are not opinions to sweep.

THE FLOOR IS IN `shortfall`, NOT `disqualify` — the first draft of this
put the parameter on `disqualify`, which does not hold the EV check, and
left `shortfall` reading a name that did not exist in its scope. A
latent NameError on the quality path, caught here rather than on the
droplet.

WHAT A SWEEP IS FOR. Lowering the floor buys days with a pick, but fewer
than it looks: the EV bar stops binding and another bar takes over. So
the report counts which bar was binding on the days that still got
nothing, and says out loud that the best cell of seven on one sample is
a bar fitted to noise.

Run through the gate's env.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import potd                                       # noqa: E402
from engine import potdbacktest as B                          # noqa: E402


def _row(sharp_fair, odds=-122):
    """A sharp-witnessed moneyline, priced so `edge` is what we choose."""
    return {"odds": odds, "book": "Novig", "sharp_anchored": True,
            "sharp_fair": sharp_fair, "win_prob": sharp_fair,
            "model_prob": sharp_fair, "market": "moneyline",
            "bet_type": "moneyline", "home": "ARI", "away": "MIA",
            "team": "ARI", "rank_auc": 0.60, "has_market": True}


# --- the seam -----------------------------------------------------------------
def test_the_shipped_floor_is_what_runs_when_nobody_asks():
    """The product's bar is untouched. A sweep is a question asked of the
    selector, never a change to it."""
    row = _row(0.555)                      # ~1% edge, under the 2% bar
    assert potd.shortfall(row) == potd.shortfall(row, None)
    assert "not far enough off the fair" in potd.shortfall(row)


def test_a_supplied_floor_moves_the_bar_that_actually_holds_it():
    row = _row(0.555)
    assert "not far enough off the fair" in potd.shortfall(row, 0.02)
    assert "not far enough off the fair" in potd.shortfall(row, 0.01)
    assert "not far enough off the fair" not in potd.shortfall(row, 0.005)


def test_lowering_the_floor_hands_the_refusal_to_the_next_bar():
    """THE FINDING THIS EXISTS TO SURFACE. Dropping the EV floor does not
    make a row a pick — it makes some OTHER bar the binding one, which is
    why a sweep reports what was binding rather than only the count."""
    row = _row(0.555)
    low = potd.shortfall(row, 0.0)
    assert low, "every bar fell away at once, which is not what should happen"
    assert "not far enough off the fair" not in low, low


def _reason(rows, **kw):
    """Whatever `choose` says stood between these rows and a pick."""
    pick, near, census = potd.choose(rows, **kw)
    if pick:
        return ""
    if census:
        return max(census.items(), key=lambda kv: kv[1])[0]
    return potd.shortfall(near, kw.get("min_ev")) if near else "no rows"


def test_choose_passes_the_floor_down_to_the_bar():
    """`choose` is what the replay calls, so a floor that stopped at its
    signature would sweep nothing and the table would print seven
    identical rows.

    Asked by watching the REASON change rather than a count, because a
    count can stay the same for unrelated reasons. This row carries a
    9.2% edge: at the shipped floor it is refused as too BIG to trust
    (`MAX_EV`), and raising the floor above it flips the refusal to too
    small. Only a threaded `min_ev` can make the same row fail two
    opposite ways."""
    rows = [_row(0.60)]
    assert "too big to trust" in _reason(rows), _reason(rows)
    assert "not far enough off the fair" in _reason(rows, min_ev=0.20), \
        _reason(rows, min_ev=0.20)


def test_no_negative_floor_is_ever_swept():
    """A floor below zero admits a bet the price itself says loses money.
    Today's ARI row was at -0.4%; no sample size makes that a good idea,
    and the sweep must not offer it as an option."""
    assert min(B.SWEEP_FLOORS) >= 0.0, B.SWEEP_FLOORS
    assert potd.MIN_EV in B.SWEEP_FLOORS, \
        "the sweep cannot be read without the shipped bar in it"


# --- the report ---------------------------------------------------------------
def test_a_swept_replay_says_it_was_swept():
    """The `--rank-auc` rule, applied to the floor: a what-if must never
    read as the shipped setting."""
    swept = B.summarize(B.PotdReplay(sport="mlb", min_ev=0.005))
    assert "SWEPT" in swept and "0.5%" in swept
    shipped = B.summarize(B.PotdReplay(sport="mlb"))
    assert "SWEPT" not in shipped
    assert f"{potd.MIN_EV * 100:.1f}%" in shipped


def test_the_sweep_table_reports_more_than_the_roi():
    """Days with a pick, the record, the ROI AND the binding bar. A table
    of ROIs alone invites picking the best cell."""
    real = B.replay_potd
    try:
        def fake(conn, sport="mlb", sharp="Pinnacle", rank_auc=None, min_ev=None):
            r = B.PotdReplay(sport=sport, min_ev=min_ev)
            r.days_seen, r.days_with_pick = 40, 10
            r.n_bets, r.wins, r.staked, r.net = 10, 6, 10.0, 1.2
            r.binding = {"this market’s numbers are not reliable enough": 30}
            return r
        B.replay_potd = fake
        table = B.sweep_ev(None, "mlb")
    finally:
        B.replay_potd = real
    assert "days w/ pick" in table and "ROI" in table
    assert "binding when nothing cleared" in table
    assert "fitted to noise" in table, "the table invites cherry-picking"
    for f in B.SWEEP_FLOORS:
        assert f"{f * 100:.1f}%" in table, f


# --- and the CLI it is reached through ----------------------------------------
def test_help_does_not_crash_on_a_percent_sign():
    """ARGPARSE RUNS HELP THROUGH %-EXPANSION. A bare percent in a help
    string raises ValueError from `--help` itself and takes the WHOLE
    parser's help down, not just that one line — which is exactly what
    adding `--min-ev` did before it was escaped."""
    p = subprocess.run([sys.executable, "potd_backtest.py", "--help"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-600:]
    assert "--sweep-ev" in p.stdout and "--min-ev" in p.stdout
    assert f"{potd.MIN_EV * 100:.1f}%" in p.stdout, \
        "the help does not name the shipped floor it is offering to replace"


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
