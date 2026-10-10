"""`--why-many`: is tonight's board unusually big, or does it just feel that way?

Ethan opened the MLB page and saw 21 recommended props against a remembered
norm of "about four a night". The right first move is not to reason about
the gates — it is to check whether 21 is actually unusual, and "about four"
is a memory rather than a baseline.

So this measures the nightly count from the journal itself. If the trailing
median really is 4, a 21 is a 5x night and worth explaining. If the journal
says nights range 2-20, then 21 is the top of a normal spread and there is
nothing to fix.

The gate that swings an MLB count hardest is the lineup hold — hitter props
are blocked until the card is posted (engine/mlb/rules.py), so the board is
quiet in the morning and fills in the moment lineups drop. A count taken at
11am and a count taken at 6pm are not the same measurement, which is the
first thing to rule out before suspecting the model.
"""

import datetime as dt
import io
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launch
from engine import ledger


def _journal(counts, sport="mlb"):
    """A throwaway ledger with a given picks-per-night rhythm."""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "ledger.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(ledger.SCHEMA)
    for i, n in enumerate(counts):
        d = (dt.date(2026, 7, 30) - dt.timedelta(days=i)).isoformat()
        for j in range(n):
            conn.execute(
                "INSERT INTO bets (sport,date,player,market,category,odds,edge,"
                "confidence,grade,stake_units) VALUES (?,?,?,?,'main',-110,"
                ".04,7,'B',.2)", (sport, d, f"P{j}", f"m{j}"))
    conn.commit()
    conn.close()
    return db


def _board(n_rec, n_priced=40, opponent="MIL", market="Total Bases"):
    rows = []
    for i in range(n_priced):
        rows.append({
            "player": f"Player {i}", "market": "total_bases",
            "market_label": market, "opponent": opponent if i % 3 else "SD",
            "edge": 0.05, "confidence": 7.5, "grade": "B",
            "stake_units": 0.25, "recommended": i < n_rec,
        })
    return {"date": "2026-08-02", "recommendations": rows}


def _run(board, db, **kw):
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "web", "data"), exist_ok=True)
    with open(os.path.join(tmp, "web", "data", "mlb_recommendations.json"),
              "w", encoding="utf-8") as fh:
        json.dump(board, fh)
    # Patch connect() itself, not ledger.DEFAULT_DB. `connect(path=DEFAULT_DB)`
    # binds that default at DEFINITION time, so reassigning the module
    # attribute afterwards changes nothing — the first version of this helper
    # did exactly that and every test silently read the real ledger (empty
    # here), so they were asserting against the no-journal branch while
    # claiming to test the baseline one.
    old_root, old_connect = launch.ROOT, ledger.connect
    launch.ROOT = __import__("pathlib").Path(tmp)
    ledger.connect = lambda *a, **k: old_connect(db)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            launch.why_many("mlb", **kw)
    finally:
        launch.ROOT, ledger.connect = old_root, old_connect
    return buf.getvalue()


def test_it_reports_the_measured_median_not_a_remembered_one():
    """The whole point. "About four a night" has to become a number read
    off the journal before tonight can be called unusual."""
    out = _run(_board(21), _journal([4, 3, 5, 4, 6, 3, 4, 5, 2, 4] * 2))
    assert "median 4" in out, out
    assert "21 recommended" in out
    assert "5.2x the median night" in out or "5.3x" in out, out


def test_a_big_night_inside_a_wide_spread_is_not_flagged_as_a_multiple():
    """The negative control, and the reason the baseline is measured rather
    than assumed: if nights genuinely range 2-20, a 21 is the top of a
    normal spread and the ratio should say so instead of alarming."""
    out = _run(_board(21), _journal([2, 18, 5, 20, 3, 16, 4, 19, 6, 17]))
    assert "min 2" in out and "max 20" in out, out
    # median of that spread is ~16, so tonight is ~1.3x — not a 5x story.
    assert "5." not in out.split("x the median night")[0][-6:], out


def test_no_journal_says_so_rather_than_inventing_a_baseline():
    """A fresh clone has no ledger. Printing "0x the median" or silently
    skipping the comparison would both imply a judgement the data cannot
    support."""
    out = _run(_board(21), _journal([]))
    assert "no baseline to compare against" in out
    assert "cannot be called unusual" in out


def test_it_names_concentration_because_that_is_a_different_problem():
    """A board that is big because ONE matchup produced fourteen picks is
    not the same as a board that is big because the slate is big. The first
    is correlated exposure wearing the costume of diversification."""
    out = _run(_board(15, opponent="MIL"), _journal([4] * 10))
    assert "come from one matchup" in out, out
    assert "Correlated exposure" in out


def test_a_spread_out_board_is_not_flagged_for_concentration():
    board = _board(12)
    for i, r in enumerate(board["recommendations"]):
        r["opponent"] = f"T{i}"          # every pick a different matchup
    out = _run(board, _journal([4] * 10))
    assert "come from one matchup" not in out, out


def test_it_reports_the_shape_of_what_cleared():
    """A count alone does not say whether the gates held. Edge and
    confidence spreads do: twenty picks all sitting a hair over the bar is
    a different story from twenty comfortably clear of it."""
    out = _run(_board(21), _journal([4] * 10))
    for label in ("edge", "confidence", "exposure", "markets", "grades"):
        assert label in out, f"{label} missing from the summary"


def test_an_empty_board_points_at_the_other_tool():
    out = _run(_board(0), _journal([4] * 10))
    assert "--why-empty" in out


def test_the_flag_is_wired_into_the_cli():
    src = open(os.path.join(os.path.dirname(__file__), "..", "launch.py"),
               encoding="utf-8").read()
    assert '"--why-many" in argv' in src
    assert "why_many(sp)" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
