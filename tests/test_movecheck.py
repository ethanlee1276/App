"""A veto with no record of what it vetoed cannot be judged.

`engine/quality.apply_movement` moves a graded pick's score by ±4 points,
±7 on steam, and REJECTS the pick when the drop puts it under 70. Its only
caller's docstring said for months that movement was "purely informational
— it never changes a grade, because we haven't measured its predictive
value on our own picks yet". Both halves were wrong in the same direction:
it does change grades, and the value really is unmeasured.

It was unmeasurable, too — nothing journalled what movement did, so a
rejected pick landed in `loose` reading "quality 66/70", indistinguishable
from a prop that simply graded low. What is pinned here:

  * the stamp is written by the code that applies it, not recomputed,
  * both journal paths persist it,
  * a NULL is "the market never moved", never folded in with a zero,
  * the controls are the UNSTAMPED rows, so nothing may pre-filter them,
  * the bar is fixed in the module, before the first row existed.

Run directly: `python3 tests/test_movecheck.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import movecheck as mc                                          # noqa: E402
from engine import ledger                                       # noqa: E402
from engine.quality import apply_movement                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rows(cat, n, delta, land, tag):
    out = []
    for i in range(n):
        out.append({"category": cat, "hit_prob": 0.58, "move_delta": delta,
                    "move_steam": 0.0,
                    "status": "won" if i < round(n * land) else "lost"})
    return out


# --- the stamp is written where the arithmetic happens -----------------------
def test_apply_movement_records_what_it_applied():
    """Recomputing the delta in the journal would let two copies drift, and
    the column exists precisely so the veto can be checked against
    outcomes. Same discipline as reading the calibration correction in the
    process that priced the pick."""
    rec = {"quality": 80, "grade": "Strong"}
    apply_movement(rec, with_us=False, steam=False)
    assert rec["move_delta"] == -4.0
    assert rec["move_steam"] == 0.0
    assert rec["quality"] == 76

    steam = {"quality": 80, "grade": "Strong"}
    apply_movement(steam, with_us=True, steam=True)
    assert steam["move_delta"] == 7.0 and steam["move_steam"] == 1.0


def test_a_rejection_is_stamped_as_a_rejection():
    """A killed pick lands in `loose` with a quality just under 70 — which
    is exactly how it gets there — and without this flag it reads the same
    as a prop that merely graded low."""
    rec = {"quality": 72, "grade": "Lean"}
    apply_movement(rec, with_us=False, steam=False)
    assert rec["recommended"] is False and rec["grade"] == "Pass"
    assert rec["stake_units"] == 0.0
    assert rec["move_rejected"] is True
    assert rec["move_delta"] == -4.0


def test_a_pick_that_survives_is_not_flagged_rejected():
    rec = {"quality": 90, "grade": "Strong"}
    apply_movement(rec, with_us=False, steam=False)
    assert rec.get("move_rejected") is None
    assert rec["move_delta"] == -4.0        # …but the stamp is still there


def test_an_ungraded_pick_is_left_entirely_alone():
    rec = {"quality": None}
    apply_movement(rec, with_us=False, steam=True)
    assert "move_delta" not in rec


# --- both journal paths persist it -------------------------------------------
def test_the_columns_exist_on_a_fresh_and_a_migrated_ledger():
    conn = ledger.connect(":memory:")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    assert {"move_delta", "move_steam"} <= cols


def test_both_inserts_write_the_stamp():
    """`main` is where a survivor lands and `loose` is where a rejection
    lands. Capturing only one of them answers only half the question, and
    the half it drops is the one that decides whether the veto pays."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    main_ins = src[src.index("INSERT OR IGNORE INTO bets (ts, sport, date, "
                             "player, market, side, line, "):]
    assert "move_delta, move_steam" in main_ins[:1200]
    loose = src[src.index("category='loose'"):]
    assert "move_delta, move_steam" in loose[:1400] or \
        "move_delta" in src[src.index("Journal the props that JUST missed"):
                            src.index("def loose_report")]


def test_near_misses_carries_the_stamp_through():
    """The loose journal can only write what the pipeline hands it."""
    import inspect
    from engine.mlb.pipeline import near_misses
    src = inspect.getsource(near_misses)
    assert '"move_delta": r.get("move_delta")' in src
    assert '"move_rejected"' in src


# --- NULL is a fact, not a missing value -------------------------------------
def test_no_movement_seen_is_its_own_group():
    """"The market never moved on this prop" is a different fact from a
    movement of zero, and a different population from one it moved on.
    Folding them together lets the quiet props dilute the loud ones."""
    rows = (_rows("main", 10, -4.0, 0.4, "a") + _rows("main", 10, 4.0, 0.6, "w")
            + _rows("main", 10, None, 0.5, "n"))
    g = mc.split_by_movement(rows)
    assert len(g["against"]) == 10 and len(g["with"]) == 10
    assert len(g["unseen"]) == 10


def test_the_controls_are_not_pre_filtered_to_stamped_rows():
    """The bug the first cut shipped. The comparison groups ARE the
    unstamped rows, so filtering to stamped ones first empties every
    control and the script reports 'not enough on one side' against a
    journal that has plenty — the quietest way for a diagnostic to be
    wrong."""
    src = open(os.path.join(ROOT, "movecheck.py"), encoding="utf-8").read()
    body = src[src.index("def report("):]
    assert 'main = [r for r in rows if' in body
    assert 'loose = [r for r in rows if' in body
    assert 'main = [r for r in stamped' not in body


# --- the verdict -------------------------------------------------------------
def test_an_empty_journal_says_there_is_nothing_to_measure():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mc.report(ledger.connect(":memory:"), "mlb")
    out = buf.getvalue()
    assert "NOTHING TO MEASURE YET" in out
    assert "real answer, not a bug" in out
    assert "VERDICT" not in out          # and it does not pretend to one


def test_a_veto_that_kills_winners_is_called_out():
    """The outcome that matters. If the picks movement killed landed BETTER
    than the near-misses it spared, it has been removing the good half of a
    marginal bucket."""
    killed = _rows("loose", 90, -4.0, 0.70, "k")
    spared = _rows("loose", 160, None, 0.42, "s")
    c = mc.compare(killed, spared)
    assert c["ok"] and c["diff"] >= mc.KEEP_VETO_PTS and c["z"] >= 2.0


def test_a_veto_that_kills_losers_is_credited():
    killed = _rows("loose", 120, -4.0, 0.30, "k")
    spared = _rows("loose", 160, None, 0.60, "s")
    c = mc.compare(killed, spared)
    assert c["ok"] and c["diff"] <= -mc.KEEP_VETO_PTS and c["z"] <= -2.0


def test_a_thin_side_refuses_to_compare():
    c = mc.compare(_rows("loose", 5, -4.0, 0.2, "k"),
                   _rows("loose", 160, None, 0.6, "s"))
    assert c["ok"] is False


def test_the_bar_is_a_module_constant_fixed_before_the_data():
    """A threshold chosen after seeing the answer is not a threshold. This
    one was written down while every row in the journal still read NULL."""
    src = open(os.path.join(ROOT, "movecheck.py"), encoding="utf-8").read()
    verdict = src[src.index("print(\"VERDICT\")"):]
    assert "KEEP_VETO_PTS" in verdict
    assert "0.05" not in verdict


def test_it_writes_nothing():
    src = open(os.path.join(ROOT, "movecheck.py"), encoding="utf-8").read()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "commit()",
                      "write_text"):
        assert forbidden not in src, forbidden


def test_the_report_says_whether_movement_can_be_SEEN_not_just_counted():
    """Ethan's first real run: "3,366 settled mlb bets, 14 carrying a
    movement stamp". The natural reading is "wait for more bets", and it
    is usually wrong.

    A stamp needs `analyze` to have SEEN the prop move, which needs two
    snapshots of the same (player, market, book) with different numbers.
    A prop pulled once a day is invisible to this instrument forever,
    however much it moved in between — so the binding constraint is the
    PULL CADENCE, and more settled bets cannot fix it."""
    import contextlib
    import io
    import json
    import tempfile
    from pathlib import Path
    from engine import linemoves
    ts = 1_700_000_000
    rows = [
        # one series seen twice — observable
        {"player": "A", "market": "hits", "book": "FanDuel", "ts": ts,
         "line": 1.5, "over_odds": -110},
        {"player": "A", "market": "hits", "book": "FanDuel", "ts": ts + 600,
         "line": 1.5, "over_odds": -140},
        # three series seen once — invisible, whatever they did
        {"player": "B", "market": "hits", "book": "FanDuel", "ts": ts,
         "line": 1.5, "over_odds": -110},
        {"player": "C", "market": "hits", "book": "FanDuel", "ts": ts,
         "line": 1.5, "over_odds": -110},
        {"player": "D", "market": "hits", "book": "FanDuel", "ts": ts,
         "line": 1.5, "over_odds": -110},
    ]
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    orig = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = Path(path)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mc._snapshot_depth()
    finally:
        linemoves.HISTORY_PATH = orig
        os.unlink(path)
    out = buf.getvalue()
    assert "1 of 4" in out, out
    assert "3 were pulled once" in out or "other 3" in out, out
    # More invisible than visible: it must name cadence as the blocker
    # rather than let "wait for more bets" stand.
    assert "CADENCE IS THE BINDING CONSTRAINT" in out
    assert "pre-kickoff" in out


def test_snapshot_depth_is_silent_with_no_history_rather_than_crashing():
    """It runs at the top of every report, so it must never be the reason
    the report does not print."""
    import contextlib
    import io
    import tempfile
    from pathlib import Path
    from engine import linemoves
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    orig = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = Path(path)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mc._snapshot_depth()
    finally:
        linemoves.HISTORY_PATH = orig
        os.unlink(path)
    assert buf.getvalue() == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
