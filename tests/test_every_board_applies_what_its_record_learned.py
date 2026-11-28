"""Every board applies what its own record learned, and no learner undoes
a correction nothing applied (2026-11-14).

Ethan, 2026-11-14: "make sure all of our calibrations are working and all
of the learning is working and hypothesis is working and all that stuff for
every single sport? We want to make sure everything is learning and getting
better and selecting better picks".

The audit found two boards pricing with less than the record had learned,
and two learners reading those boards as if they had applied it:

  * THE SELECTION HAIRCUT (engine/selectionfit: what our own settled picks
    landed against what we said) was applied by three pricers only: the
    NFL's and college football's (engine/betting) and MLB's. The basketball
    pipeline (the NBA, the WNBA, college) and the NHL's never applied it,
    and the public record shows what that cost: the NBA's Edge picks claimed
    51.9% and landed 44.9% over 227 settled, the ones claiming 55-60%
    landed 36.7%. Both apply it now, after the side is chosen.
  * ITS REFIT un-shifted every sport's newest rows by the live shift, as if
    each board had applied it: raw basketball and hockey claims were made
    surer than they were said, in their own fits and in the pooled one the
    young sports borrow. A row of theirs before the boards started is raw.
  * THE JOURNAL'S TEMPERATURES (engine/journalfit) un-corrected hockey and
    UFC claims by the stored temperature, though neither pricer ever applied
    one: compounding, night on night. Every row of theirs is raw now.
  * THE LOSS PATTERNS' closed slices (engine/losspatterns) refuse a hockey
    pick that lands in one, as they refuse every other board's.

    python3 tests/test_every_board_applies_what_its_record_learned.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import journalfit as JF                  # noqa: E402
from engine import selectionfit as SF                # noqa: E402

BEFORE, AFTER = "2026-11-14T15:00:00", "2026-11-14T17:00:00"


def _row(sport, p, ts, won=1, **kw):
    return {"sport": sport, "hit_prob": p, "ts": ts, "status": "won" if won else "lost", **kw}


def test_a_late_boards_rows_before_it_applied_the_haircut_are_raw():
    assert SF.LATE_BOARDS_FROM == "2026-11-14T16:00:00"
    assert set(SF.HAIRCUT_FROM) == {"nba", "wnba", "cbb", "nhl"}
    shift, stamp = -0.3, "2026-11-13"
    nba_before = SF._pairs([_row("nba", 0.6, BEFORE)], shift, stamp)
    nba_after = SF._pairs([_row("nba", 0.6, AFTER)], shift, stamp)
    nfl_before = SF._pairs([_row("nfl", 0.6, BEFORE)], shift, stamp)
    assert nba_before == [(0.6, 1)], "the NBA board applied no haircut before: its claim is its own"
    assert nba_after[0][0] > 0.6, "after, it applied the live shift: un-shifted as every board's is"
    assert nfl_before[0][0] > 0.6, "the NFL's board always applied it: unchanged"
    assert SF._pairs([{"hit_prob": 0.6, "ts": BEFORE, "status": "won"}], shift, stamp)[0][0] > 0.6, \
        "a row read without its sport is read as before"


def test_the_refit_reads_basketball_and_hockey_claims_as_they_were_said():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, hit_prob REAL, odds INT, "
                 "status TEXT, ts TEXT, category TEXT)")
    for i in range(40):
        for sport in ("nba", "nhl", "nfl"):
            conn.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?)",
                         (sport, "pts", "OVER", 0.58, -110, "won" if i % 2 else "lost",
                          f"2026-11-14T1{i % 5}:00:00", "main"))
    stored = {"fitted_at": "2026-11-13", "pooled": {"applied": True, "shift": -0.3},
              "sports": {"nfl": {"applied": True, "shift": -0.3}}}
    out = SF.measure(conn, stored, min_settled=10)
    sports = out["sports"]
    # Rows at 10:00-14:00 UTC: before the late boards applied anything.
    assert sports["nba"]["claimed"] == 0.58 and sports["nhl"]["claimed"] == 0.58, sports
    assert sports["nfl"]["claimed"] > 0.58, "the NFL's own claims were shifted, and are un-shifted"


def _store(path, **sports):
    path.write_text(json.dumps({"fitted_at": "2026-11-14", "pooled": {"applied": False, "shift": 0.0, "n": 0},
                                "sports": {s: {"applied": True, "shift": v, "n": 400} for s, v in sports.items()}}))
    SF.reset_cache()


def _with_store(fn, **sports):
    keep = SF.DEFAULT_PATH
    SF.DEFAULT_PATH = Path(tempfile.mkdtemp()) / "selection.json"
    _store(SF.DEFAULT_PATH, **sports)
    try:
        return fn()
    finally:
        SF.DEFAULT_PATH = keep
        SF.reset_cache()


def _hoops_prop(**kw):
    d = {"player": "Guard One", "team": "BOS", "opponent": "NYK", "market": "pts",
         "line": 22.5, "over_odds": 130, "under_odds": -110, "book": "DK",
         "minutes": [32.0] * 15, "values": [23.0] * 15,
         "is_starter": True, "spread": -3.0, "is_favorite": True, "rest": "1day"}
    d.update(kw)
    return d


def test_the_basketball_board_applies_its_leagues_haircut():
    from engine.hoops import CBB, NBA
    from engine.nba.pipeline import evaluate_prop
    plain = evaluate_prop(_hoops_prop(), NBA)
    cut = _with_store(lambda: evaluate_prop(_hoops_prop(), NBA), nba=-0.4)
    assert plain["kind"] != "skip" and cut["kind"] != "skip", (plain, cut)
    assert cut["side"] == plain["side"], "after the side is chosen: never flips one"
    assert cut["p_final"] < plain["p_final"], (plain["p_final"], cut["p_final"])
    assert cut["edge"] < plain["edge"], "the edge, the gate and the stake read the corrected number"
    other = _with_store(lambda: evaluate_prop(_hoops_prop(), CBB), nba=-0.4)
    assert other["p_final"] == evaluate_prop(_hoops_prop(), CBB)["p_final"], \
        "keyed by the league: the NBA's fit never reaches college"
    src = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    i, j = src.index("p_final, clamp_note = humility_clamp("), src.index("fails = approval_gate(")
    assert "apply_haircut(tune.key, p_final)" in src[i:j], "between the clamp and the gate"


def test_the_hockey_board_applies_the_haircut_and_the_loss_patterns():
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    body = src[src.index("def price_prop("):src.index("# --- game lines")]
    i = body.index("edge, side, raw, win, odds, fair, credible = best")
    assert body.index("win, edge = apply_selection(win, edge, SPORT)") > i, "after the side is chosen"
    assert body.index("apply_selection(win, edge, SPORT)") < body.index("ev = expected_value(win, odds)")
    assert body.index("apply_selection(win, edge, SPORT)") < body.index("eh = EH.assess_prop("), \
        "Edge Hunter reads the corrected chance"
    assert "loss_block = _lp_veto(SPORT, prop.market" in body
    assert 'pick = eh["play"] and not loss_block' in body, "a closed slice refuses the pick"


def test_the_journal_never_un_corrects_a_hockey_or_ufc_claim():
    assert JF.UNCORRECTED_BOARDS == frozenset({"nhl", "ufc"})
    entry = {"temperature": 1.8, "intercept": 0.1}
    stamped_hockey = {"sport": "nhl", "cal_temp": 1.8, "cal_bias": 0.1, "ts": AFTER}
    inferred_ufc = {"sport": "ufc", "cal_temp": None, "cal_bias": None, "ts": AFTER}
    assert JF._correction_for(stamped_hockey, entry, "2026-01-01") == (None, "raw"), \
        "the store's hockey temperature was stamped on rows the hockey board never corrected"
    assert JF._correction_for(inferred_ufc, entry, "2026-01-01") == (None, "raw")
    nba = {"sport": "nba", "cal_temp": 1.8, "cal_bias": 0.1, "ts": AFTER}
    assert JF._correction_for(nba, entry, "2026-01-01") == ((1.8, 0.1), "logged"), \
        "a board that applies its temperature is un-corrected exactly as before"


def test_a_hockey_refit_lands_where_its_raw_claims_say():
    import sqlite3
    path = Path(tempfile.mkdtemp()) / "calibration.json"
    path.write_text(json.dumps({"nhl:sog": {"temperature": 0.6, "intercept": 0.0, "samples": 300,
                                            "basis": JF.BASIS, "fitted_at": "2026-11-01"}}))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, player TEXT, side TEXT, hit_prob REAL, "
                 "projection REAL, actual REAL, status TEXT, ts TEXT, cal_temp REAL, cal_bias REAL)")
    for i in range(300):
        conn.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("nhl", "sog", f"P{i}", "OVER", 0.62, 2.5, 3.0, "won" if i % 5 < 3 else "lost",
                      f"2026-11-1{i % 4}T12:00:00", 0.6, 0.0))
    out = JF.fit_temperatures(conn, path=path, dry_run=True)
    row = next(r for r in out["refitted"] if r["key"] == "nhl:sog")
    assert row["provenance"] == {"logged": 0, "stamped": 0, "raw": 300}, row["provenance"]
    # Claimed 62%, landed 60%: a temperature near 1, not the compounding 0.6.
    assert abs(row["temperature"] - 1.0) < 0.35, row


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
