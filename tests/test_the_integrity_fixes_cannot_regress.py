"""Named tests for the integrity findings the earlier items did not cover.

Audit 2026-09-30, O14 / B10 / F-14 (roadmap #25). Items 1-5 each shipped a
test that fails on the old code: chain-vs-bets drift and no re-grade off an
in-progress score (test_the_record_leaves_a_trace), the harvested pre-game
cut and the doubleheader's second leg (test_every_close_is_pregame), best-
vs-median CLV and the Brier benchmark (test_clv_compares_like_with_like),
the pooled-record disclosure (test_the_headline_is_the_models_own_book).
What was left:

  * F-14: no test ran a REAL build through `gate.unsealed()` — only
    fixtures went through `gate.publish`, so a build adding a paid key not
    in PAID_KEYS passed every test. The two offline builders now run into
    a temp tree with the paywall on and must leave nothing unsealed, and
    the doctor checks the live tree;
  * B2-1: four de-vig implementations, no equivalence test. They are
    DIFFERENT methods on purpose (multiplicative vs power), so this pins
    how far apart they may drift on a fixed grid rather than pretending
    they agree;
  * A2-2: the no-show sweep reopened EVERY voided desk ticket, including
    the ones `settle_predmarket` had voided on purpose (exchange cancelled,
    or delisted past its event) — a void/reopen ping-pong every cycle.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _build(script, slate, out, paywall):
    env = {**os.environ, "QB_PAYWALL": "1" if paywall else "0"}
    r = subprocess.run([sys.executable, str(ROOT / script), str(slate), "--out", str(out)],
                       env=env, capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]


def test_real_builds_leave_nothing_unsealed_with_the_paywall_on():
    from engine import gate
    tree = Path(tempfile.mkdtemp())
    data = tree / "web" / "data"
    _build("generate.py", ROOT / "data" / "sample_slate.json", data / "recommendations.json", True)
    _build("generate_mlb.py", ROOT / "data" / "mlb_sample_slate.json",
           data / "mlb_recommendations.json", True)
    assert (data / "recommendations.json").exists() and (data / "mlb_recommendations.json").exists()
    assert (tree / "data" / "built" / "recommendations.json").exists(), "the full copy stays off the public path"
    assert gate.unsealed(data) == [], gate.unsealed(data)
    # And the check has teeth: the same builds with the paywall OFF are
    # public boards with paid rows in them.
    open_tree = Path(tempfile.mkdtemp()) / "web" / "data"
    _build("generate.py", ROOT / "data" / "sample_slate.json", open_tree / "recommendations.json", False)
    assert gate.unsealed(open_tree), "unsealed() finds nothing even on an open board"


def test_the_doctor_checks_the_live_tree_when_the_paywall_is_on():
    import doctor
    assert "check_public_boards_sealed" in [f.__name__ for f in doctor.CHECKS]

    tree = Path(tempfile.mkdtemp()) / "web" / "data"
    _build("generate.py", ROOT / "data" / "sample_slate.json", tree / "recommendations.json", False)
    old = os.environ.get("QB_PAYWALL")
    try:
        os.environ["QB_PAYWALL"] = "1"
        rep = doctor.Report()
        doctor.check_public_boards_sealed(rep, web_data=tree)
        assert [c["status"] for c in rep.checks] == [doctor.FAIL], rep.checks
        assert "recommendations.json" in rep.checks[0]["detail"]
        os.environ["QB_PAYWALL"] = "0"
        rep = doctor.Report()
        doctor.check_public_boards_sealed(rep, web_data=tree)
        assert [c["status"] for c in rep.checks] == [doctor.OK], "paywall off: nothing to seal"
    finally:
        if old is None:
            os.environ.pop("QB_PAYWALL", None)
        else:
            os.environ["QB_PAYWALL"] = old


#: Favourites from -110 to -400 at 3, 4.5 and 6% hold: the prices the
#: boards actually quote.
def _grid():
    out = []
    for fav in (-110, -120, -135, -150, -175, -200, -250, -300, -400):
        for vig in (0.03, 0.045, 0.06):
            pf = abs(fav) / (abs(fav) + 100)
            pd = 1 + vig - pf
            dog = int(round(100 * (1 - pd) / pd)) if pd < 0.5 else int(round(-100 * pd / (1 - pd)))
            out.append((fav, dog))
    return out


#: Measured 2026-09-30: the four disagree by at most 2.4 points on this
#: grid (at -400/+285, multiplicative 24.5% vs power 22.1%) and by 0.61
#: points with the favourite at -150 or shorter. A change that widens
#: either is a change to what "fair" means on some board and must be made
#: on purpose.
DEVIG_TOLERANCE_PTS = 2.5
DEVIG_NEAR_EVEN_PTS = 0.75


def test_the_four_devigs_stay_within_a_stated_tolerance():
    from engine import odds
    from engine.nba import prob as nba
    from engine.cfb import pipeline as cfb
    worst = near = 0.0
    for fav, dog in _grid():
        ps = [odds.devig_two_way(dog, fav)[0], nba.devig(dog, fav)[0],
              cfb.devig(dog, fav)[0], nba.devig_power(dog, fav)[0]]
        spread = (max(ps) - min(ps)) * 100
        worst = max(worst, spread)
        if fav >= -150:
            near = max(near, spread)
        assert all(0 < p < 1 for p in ps)
    assert worst <= DEVIG_TOLERANCE_PTS, f"the de-vigs now disagree by {worst:.2f} points"
    assert near <= DEVIG_NEAR_EVEN_PTS, f"near even money they disagree by {near:.2f} points"


def test_a_desk_ticket_voided_on_purpose_stays_void():
    from engine import db as hist_db, ledger as L
    conn = L.connect(Path(tempfile.mkdtemp()) / "l.db")
    for t, note in (("KXNFLGAME-26SEP13DALNYG-NYG", "the exchange cancelled this market"),
                    ("KXNFLGAME-26SEP13PHIWAS-PHI", None)):
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, status, "
                     "category, why_note, stake_units) VALUES ('2026-09-10T00:00:00','nfl','2026-09-10',?,"
                     "'kalshi_ml','YES',50,-100,'void','predmarket',?,0.1)", (t, note))
    conn.commit()
    L.settle_from_history(conn, hist_db.connect(":memory:"))
    got = dict(conn.execute("SELECT player, status FROM bets").fetchall())
    assert got["KXNFLGAME-26SEP13DALNYG-NYG"] == "void", "a deliberate void was reopened"
    assert got["KXNFLGAME-26SEP13PHIWAS-PHI"] == "open", "a no-show sweep's wrong void still heals"
    conn.close()


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
