"""The per-market calibration sweep has to say what it is missing.

Running `mlb_calibration.py` on a DB with no MLB logs printed:

    Total Bases    —   (no rows — try a wider --min-history)
    Hits           —   (no rows — try a wider --min-history)
    Home Runs      —   (no rows — try a wider --min-history)
    Strikeouts     —   (no rows — try a wider --min-history)

There were no MLB logs at all. --min-history was never the problem, and
widening it forever would not have produced a row. A confident wrong
reason is worse than no reason: it sends you tuning a knob that was never
connected to anything.

Three states have to read differently, because each needs a different fix:

  no MLB logs at all        → ingest
  logs, but none for market → that market was never stored
  logs for the market, thin → lower --min-history

And separately: no harvested odds makes the ROI column meaningless, but
leaves ECE and Brier fully valid — they grade against OUTCOMES, not lines.
Conflating those would make someone harvest odds (which costs real credits)
to answer a question the data already answers.
"""

import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_with(hits_players=0, hr_rows=0):
    from engine import db
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    random.seed(11)
    for p in range(hits_players):
        for g in range(20):
            conn.execute(
                "INSERT INTO player_game_logs (sport,season,period,game_id,"
                "player,team,opponent,position,home,market,value) VALUES "
                "('mlb',2026,?,?,?,'PHI','CHC','OF',1,'hits',?)",
                (f"2026-06-{g + 1:02d}", f"g{p}-{g}", f"Hitter {p}",
                 float(random.randint(0, 3))))
    for g in range(hr_rows):
        conn.execute(
            "INSERT INTO player_game_logs (sport,season,period,game_id,"
            "player,team,opponent,position,home,market,value) VALUES "
            "('mlb',2026,?,?,'Slugger','PHI','CHC','OF',1,'home_runs',?)",
            (f"2026-06-{g + 1:02d}", f"hr{g}", float(g % 2)))
    conn.commit()
    return path


def _run(path, *extra):
    p = subprocess.run([sys.executable, "mlb_calibration.py", "--db", path,
                        *extra], cwd=ROOT, capture_output=True, text=True,
                       timeout=600)
    assert p.returncode == 0, p.stderr[-500:]
    return p.stdout


# --- the three empty states read differently --------------------------------
def test_an_empty_db_says_ingest_rather_than_blaming_min_history():
    out = _run(_db_with())
    assert "No MLB player game logs" in out
    assert "ingest.py mlb" in out
    assert "min-history" not in out, \
        "still blaming a knob that cannot fix an empty database"


def test_a_market_that_was_never_stored_says_so():
    out = _run(_db_with(hits_players=40), "--naive")
    assert "(no total bases rows stored at all)" in out
    assert "(no strikeouts rows stored at all)" in out


def test_a_market_with_rows_but_too_few_priors_names_the_knob_and_a_value():
    """This is the ONE case where --min-history is the answer, so it is the
    one case that should say so — and it should say what to set it to."""
    out = _run(_db_with(hits_players=40, hr_rows=3), "--naive")
    assert "3 row(s) stored, none with 7+ prior games" in out
    assert "--min-history 3" in out


def test_a_market_with_enough_data_actually_reports():
    """The positive control. Without it, the three tests above only prove
    the sweep can print excuses."""
    out = _run(_db_with(hits_players=40), "--naive")
    line = next(l for l in out.splitlines() if l.startswith("Hits"))
    assert "—" not in line, f"Hits produced no numbers: {line}"
    parts = line.split()
    assert int(parts[1]) > 100, f"suspiciously few props: {line}"


# --- odds coverage is a separate axis ---------------------------------------
def test_missing_odds_does_not_invalidate_the_calibration_numbers():
    """ECE and Brier grade against outcomes. Letting someone believe they
    need harvested odds to read them would cost real credits to answer a
    question the data already answers."""
    out = _run(_db_with(hits_players=40))
    assert "No harvested odds" in out
    assert "ECE and Brier are unaffected" in out
    assert "grade against OUTCOMES, not lines" in out


def test_the_run_states_what_it_is_working_from():
    out = _run(_db_with(hits_players=40), "--naive")
    assert "MLB log row(s)" in out
    assert "harvested book line(s)" in out


def test_the_stock_check_counts_rather_than_assumes():
    src = open(os.path.join(ROOT, "mlb_calibration.py"), encoding="utf-8").read()
    i = src.index("def _stock(")
    block = src[i:i + 900]
    assert "SELECT COUNT(*) FROM player_game_logs" in block
    assert "GROUP BY market" in block
    # A DB without the odds table must not take the run down.
    assert "except Exception:" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
