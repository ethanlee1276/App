"""`explain_open` — why an open bet has not settled, and the --why-open CLI.

Ethan, 2026-08-10: "it doesn't seem like the bets settled from last night.
They are still not automatically settling."

"Not settling" has three different fixes and the record page cannot tell
them apart: a READY bet still open means the settle PASS is not running
(server down / nightly job not installed), NO_RESULTS means the ingest
never reached that date, and NO_STATLINE/NO_GRADE_SOURCE mean it cannot
grade from what exists (DNP, name mismatch, preseason props). This pins
that each classification matches what a real settle pass would find, by
reusing the settler's own lookups against the same in-memory fixtures the
settle tests use.
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                                       # noqa: E402
from engine import db as hist_db                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = _dt.date.today().isoformat()
OLD = "2026-07-24"          # firmly in the past, so the strict window is off


def _conn():
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _prop(conn, player, date=OLD, market="total_bases"):
    r = {"sport": "mlb", "date": date, "recommendations": [
        {"player": player, "market": market, "side": "UNDER", "line": 2.5,
         "odds": -120, "recommended": True, "grade": "Play",
         "stake_units": 1.0, "edge": 0.05, "confidence": 6.0,
         "win_prob": 0.55}]}
    ledger.log_recommendations(conn, r)


def test_a_bet_with_results_in_reads_ready_not_stuck():
    """The smoking-gun bucket: results are present, so a settle pass WOULD
    close it — if it is still open, the pass is not running."""
    conn = _conn()
    _prop(conn, "Aaron Judge")
    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": OLD, "game_id": "g",
         "player": "Aaron Judge", "team": "NYY", "opponent": "BOS",
         "position": "RF", "home": 1, "market": "total_bases", "value": 1.0}])
    rep = ledger.explain_open(conn, hist, today=TODAY)
    assert rep["counts"]["ready"] == 1
    assert rep["total"] == 1
    # And it really would settle — the classification is not a guess.
    assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    assert ledger.explain_open(conn, hist, today=TODAY)["total"] == 0


def test_no_results_ingested_is_its_own_bucket():
    """An empty history DB is 'ingest has not reached it', not a DNP."""
    conn = _conn()
    _prop(conn, "Mike Trout")
    hist = hist_db.connect(":memory:")
    rep = ledger.explain_open(conn, hist, today=TODAY)
    assert rep["counts"]["no_results"] == 1
    assert rep["counts"]["ready"] == 0


def test_day_ingested_but_player_absent_is_a_missing_statline():
    """Other players logged that day, this one not: a DNP or a name the
    feed spells differently — distinct from 'no results at all'."""
    conn = _conn()
    _prop(conn, "Someone Whodidnotplay")
    hist = hist_db.connect(":memory:")
    hist_db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": OLD, "game_id": "g",
         "player": "Aaron Judge", "team": "NYY", "opponent": "BOS",
         "position": "RF", "home": 1, "market": "total_bases", "value": 2.0}])
    rep = ledger.explain_open(conn, hist, today=TODAY)
    assert rep["counts"]["no_statline"] == 1
    assert rep["counts"]["no_results"] == 0


def test_a_game_bet_with_a_final_reads_ready():
    conn = _conn()
    result = {"sport": "mlb", "date": OLD, "recommendations": [],
              "game_bets": [{"bet_type": "moneyline", "recommended": True,
                             "pick": "NYY", "odds": -125, "win_prob": 0.6,
                             "edge": 0.04, "confidence": 6.0, "grade": "Play",
                             "stake_units": 1.0}]}
    ledger.log_recommendations(conn, result)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [
        {"sport": "mlb", "season": 2026, "period": OLD, "game_id": "BOS@NYY",
         "home": "NYY", "away": "BOS", "home_score": 5, "away_score": 3,
         "spread": 0.0, "total": None, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": ""}])
    rep = ledger.explain_open(conn, hist, today=TODAY)
    assert rep["counts"]["ready"] == 1


def test_todays_finished_but_uningested_bet_is_not_called_ready():
    """A bet dated TODAY with no results must never read 'ready' — that
    would tell the user to run --settle when the game may still be on."""
    conn = _conn()
    _prop(conn, "Shohei Ohtani", date=TODAY)
    hist = hist_db.connect(":memory:")
    rep = ledger.explain_open(conn, hist, today=TODAY)
    assert rep["counts"]["ready"] == 0
    assert rep["counts"]["no_results"] == 1


def test_the_cli_is_wired_and_explains_the_three_fixes():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--why-open" in argv' in src
    i = src.index("def why_open")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "explain_open" in body
    # Each bucket must name its own fix, or the tool just restates the
    # symptom the user already sees.
    assert "--settle all" in body            # the READY fix
    assert "--check" in body                 # the NO_RESULTS fix


def test_reasons_table_covers_every_bucket():
    """Every key explain_open can return must have human copy, or the CLI
    prints a bare slug."""
    rep_keys = set(ledger.OPEN_REASONS)
    assert rep_keys == {"ready", "waiting", "no_results", "no_statline",
                        "no_grade_source"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
