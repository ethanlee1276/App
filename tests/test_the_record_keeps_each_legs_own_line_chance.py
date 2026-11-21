"""The parlay record keeps each leg's own line's chance, and the learned correction moves onto it only
when its record says so (step AAU, 21 November).

Ethan, 2026-11-21: "Do this task here: Journal each parlay leg's own-line fair chance".

A Most Likely pick on a ladder rung carries its own rung's de-vigged chance as `implied_prob` and its main
line's as `fair_prob`; twoleg._fair_of reads `fair_prob` first, so every such leg was journaled with its
main line's chance. The public record's legs read 7 to 10 points under their own prices (the NBA's 53% where
they were priced near 63%), and engine/legfit learned its pull toward the book against that number. Each leg
is now journaled with its own line's chance too (`fair_line`), the record reports it, and each league and
kind's correction anchors on it only when the newest legs that carry both score better against it.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402
from engine import legfit as LF                # noqa: E402
from engine import modelstate                  # noqa: E402
from engine import parlayledger as PL          # noqa: E402

SRC = (ROOT / "engine" / "legfit.py").read_text(encoding="utf-8")


def _ticket(*legs):
    return {"legs": [dict(player=f"P{i}", team="DET", market="receptions", side="Over", line=3.5, pool="likely", **l)
                     for i, l in enumerate(legs)]}


def test_the_journal_keeps_the_legs_own_line_chance_beside_its_old_fair():
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)
    assert "fair_line" in {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    PL.ensure_schema(conn)                                  # a second pass adds nothing and raises nothing
    gp = {"games": [{"game": "NE@DET", "threes": [_ticket(dict(p=0.67, fair=0.50, fair_line=0.674),
                                                          dict(p=0.66, fair=0.61))], "scorers": []}]}
    assert PL.log_game_parlays(conn, gp, "nfl", "2026-W12") == 1
    rows = conn.execute("SELECT fair, fair_line FROM parlay_legs ORDER BY leg_no").fetchall()
    assert rows == [(0.5, 0.674), (0.61, None)], rows
    # The posted leg keeps it, so the journal can (gameparlays.slim keeps LEG_KEYS).
    assert "fair_line" in GP.LEG_KEYS and GP.slim({"p": 0.6, "fair_line": 0.674})["fair_line"] == 0.674


def _graded_journal(rows, source="game_three", sport="nba"):
    """``rows``: (p, fair, fair_line, won), one leg a bet, two a ticket, oldest first."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row                          # as the journal's own connection reads
    PL.ensure_schema(conn)
    for i in range(0, len(rows) - 1, 2):
        # At the start of its game: the record counts the set each report carried then (AT_START).
        cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, status,"
                           " at_start) VALUES (?,?,?,?,2,?,?,'lost',1)",
                           (sport, f"2026-11-{1 + i // 40:02d}", f"k{i}", "same_game", f"A{i}@H{i}", source))
        for j, (p, fair, line, won) in enumerate(rows[i:i + 2]):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, p_final, fair, "
                         "fair_line, status, pool) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (cur.lastrowid, j + 1, f"P{i + j}", "reb", "OVER", 4.5, p, fair, line,
                          "won" if won else "lost", "likely"))
    conn.commit()
    return conn


def test_the_record_reports_each_legs_own_line_where_it_has_it():
    conn = _graded_journal([(0.70, 0.50, 0.66, True), (0.68, 0.52, None, True)])
    rec = PL.game_parlay_record(conn)
    legs = rec["nba"]["three"]["legs"]
    assert legs["once"]["fair"] == round((0.66 + 0.52) / 2, 3), legs


def test_the_correction_reads_the_legs_own_line_only_with_enough_legs_and_a_better_score():
    # Every leg claims 72% and its journal says 50% (its main line's); its own line says 82% or 52%, and it
    # hits that. Only the own line's chance tells the two apart. Hits spread evenly through time.
    won = lambda k, rate: ((k * 37) % 100) < round(rate * 100)          # noqa: E731
    rows = [(0.72, 0.50, 0.82, won(k, 0.82)) if k % 2 else (0.72, 0.50, 0.52, won(k, 0.52)) for k in range(200)]
    fit = LF.fit(_graded_journal(rows), write=False)["fits"]["nba:three"]
    assert fit["anchor"] == "line" and fit["anchor_n"] == 200, fit
    assert fit["anchor_test"][1] < fit["anchor_test"][0] and "scored better" in fit["anchor_why"], fit
    assert fit["fair"] == 0.67, "the fit itself was learned against the own line's chance"
    # Where the journal's chance is the one the hits follow, it stands.
    rows = [(0.72, 0.82, 0.60, won(k, 0.82)) if k % 2 else (0.72, 0.52, 0.60, won(k, 0.52)) for k in range(200)]
    fit = LF.fit(_graded_journal(rows), write=False)["fits"]["nba:three"]
    assert fit["anchor"] == "fair" and "no better" in fit["anchor_why"], fit
    # Too few legs carry their own line's chance: as it was.
    rows = [(0.75, 0.50, 0.65 if k >= 120 else None, won(k, 0.65)) for k in range(160)]
    fit = LF.fit(_graded_journal(rows), write=False)["fits"]["nba:three"]
    assert fit["anchor"] == "fair" and fit["anchor_n"] == 40 and "40 graded, 60 needed" in fit["anchor_why"], fit
    # The journal's own reader skips a leg without one only when asked for the own line's.
    conn = _graded_journal(rows)
    assert len(LF.graded_legs(conn)[("nba", "three")]) == 160
    assert len(LF.graded_legs(conn, own_line=True)[("nba", "three")]) == 40


def test_a_leg_is_pulled_toward_its_own_line_only_under_a_fit_that_reads_it():
    path = modelstate.path(LF.FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    leg = {"player": "A", "p": 0.70, "fair": 0.50, "fair_line": 0.66, "market": "reb"}
    try:
        for anchor, want in (("fair", 0.66), ("line", 0.692)):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"fits": {"nba:three": {"w": 0.2, "fitted": True, "n_all": 100, "anchor": anchor}}}, f)
            os.utime(path, ns=(1, 10 ** 18 - (1 if anchor == "fair" else 2)))
            assert LF.anchor_of("nba", "three") == anchor
            got = LF.apply(dict(leg), "nba", "three")
            assert got["p"] == want, (anchor, got)
            assert LF.census("nba")["three"]["anchor"] == anchor
        # Under a fit that reads the own line, a leg that carries none is read at its journal's chance.
        got = LF.apply({"p": 0.70, "fair": 0.50}, "nba", "three")
        assert got["p"] == 0.66, got
    finally:
        if os.path.exists(path):
            os.remove(path)
    assert LF.anchor_of("nba", "three") == "fair", "no fit on file: the journal's, as it was"


def test_the_heartbeat_says_the_anchor():
    import launch as L
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '("w", "shift", "fitted", "markets", "anchor")' in src
    assert L is not None


def test_the_measurement_is_in_its_words():
    for words in ("NBA's 53% where they were priced near 63%", "scored far better pulled all the way to its own",
                  "so neither league's correction is expected to move"):
        assert words in SRC, words
    assert LF.ANCHORS == ("fair", "line") and LF.ANCHOR_MIN_TEST == 10


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
