"""A hundred football bets were journalled as baseball.

Found 2026-09-10 while working out why the Week 1 opener's bets had not
settled. The open journal on the droplet held this:

    mlb   anytime_td   date=2026-W01   x58
    mlb   receptions   date=2026-W01   x27
    mlb   rec_yds      date=2026-W01   x9
    mlb   rush_yds     date=2026-W01   x8
    mlb   pass_yds     date=2026-W01   x5

Five markets, and they are exactly `STALE_SETTLEABLE`'s football half.
Baseball has no `anytime_td` and no week-labelled slate; those are NFL
stale-line flags wearing the wrong league.

THE CAUSE WAS ONE DEFAULT ARGUMENT. `log_stale_flags` read
`result.get("sport", "mlb")`, and `nfl_build` called it with the raw slate
payload — which carries a `date` and no `sport` key at all. The sibling
calls beside it in the same file stamp the sport explicitly and their
comment even names the trap ("log_longshots defaults to 'mlb', and
run_slate's payload carries no sport key to correct it"); this one line
did not.

It could not fail loudly. `_hist_where` turns sport='mlb' plus a week
label into `sport='mlb' AND period='2026-W01'`, no baseball row is ever
filed under an NFL week, and the empty lookup reads as the ordinary
"results are not in yet". So the rows sat open for ever, the shadow
book's NFL verdict measured an empty sample, and the MLB record's open
count carried a hundred football bets.

Two halves here: the writer cannot guess a league any more, and the rows
it already wrote are re-filed on the settle pass.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def _journal():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _scan(market="rec_yds", player="Jaxon Smith-Njigba"):
    return {"market_scan": {"stale": [{
        "player": player, "market": market, "line": 55.5, "odds": -110,
        "book": "fanduel", "gap": 0.08, "model_prob": 0.58}]}}


# --- the writer cannot guess ------------------------------------------------
def test_a_payload_with_no_sport_is_refused_rather_than_filed_under_a_guess():
    """The whole defect in one call. `nfl_build` passed exactly this."""
    conn = _journal()
    try:
        ledger.log_stale_flags(conn, dict(_scan(), date="2026-W01"))
    except ValueError as exc:
        assert "sport" in str(exc)
    else:
        raise AssertionError("a league-less payload still journalled")


def test_the_refusal_happens_before_anything_is_written():
    """A partial write would leave some rows under a guess and refuse the
    rest, which is worse than either outcome on its own."""
    conn = _journal()
    try:
        ledger.log_stale_flags(conn, dict(_scan(), date="2026-W01"))
    except ValueError:
        pass
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0


def test_a_named_league_journals_under_that_league():
    conn = _journal()
    n = ledger.log_stale_flags(
        conn, dict(_scan(), sport="nfl", date="2026-W01"))
    assert n == 1
    row = conn.execute("SELECT sport, date, market FROM bets").fetchone()
    assert (row["sport"], row["date"]) == ("nfl", "2026-W01")


def test_baseball_still_journals_as_baseball():
    """The default was right for MLB by luck, and removing it must not
    take the league it happened to name with it."""
    conn = _journal()
    n = ledger.log_stale_flags(
        conn, dict(_scan(market="hits", player="Aaron Judge"),
                   sport="mlb", date="2026-09-09"))
    assert n == 1
    assert conn.execute("SELECT sport FROM bets").fetchone()["sport"] == "mlb"


# --- every caller names its league ------------------------------------------
def test_both_football_and_baseball_builds_stamp_the_sport():
    """`nfl_build` and `mlb_build` passed the raw payload; the raise above
    can only ever fire on a caller nobody has written yet if they do
    not."""
    for mod, want in (("nfl_build.py", "nfl"), ("mlb_build.py", "mlb"),
                      ("cfb_build.py", "cfb")):
        src = _src(mod)
        i = src.index("log_stale_flags(")
        call = src[i:i + 260]
        assert f'"sport": "{want}"' in call, \
            f"{mod} does not name its league when journalling stale flags"


def test_no_build_hands_the_bare_payload_to_the_flag_journal():
    """The exact line that shipped the bug, in the form it shipped in."""
    for mod in ("nfl_build.py", "mlb_build.py", "cfb_build.py",
                "nba_build.py"):
        assert "log_stale_flags(lconn, result)" not in _src(mod), \
            f"{mod} still passes a payload whose sport is whatever the " \
            f"function decides"


# --- the rows already written -----------------------------------------------
def _stuck(conn, sport, date, market="rec_yds", status="open"):
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, status, category) VALUES (?,?,?,?,'OVER',55.5,-110,"
        "0.10,?,'stale')", (sport, date, "A Player", market, status))
    conn.commit()


def test_a_week_labelled_baseball_bet_is_re_filed_as_football():
    conn = _journal()
    _stuck(conn, "mlb", "2026-W01")
    assert ledger.repair_football_filed_as_baseball(conn) == 1
    assert conn.execute("SELECT sport FROM bets").fetchone()["sport"] == "nfl"


def test_a_real_baseball_bet_is_left_alone():
    """The predicate is the week label, and an MLB slate is a day."""
    conn = _journal()
    _stuck(conn, "mlb", "2026-09-09", market="hits")
    assert ledger.repair_football_filed_as_baseball(conn) == 0
    assert conn.execute("SELECT sport FROM bets").fetchone()["sport"] == "mlb"


def test_a_settled_row_is_left_where_it_is():
    """It already has a verdict and a P&L in a book somebody has read.
    Moving it rewrites two sports' history to fix a label."""
    conn = _journal()
    _stuck(conn, "mlb", "2026-W01", status="won")
    assert ledger.repair_football_filed_as_baseball(conn) == 0
    assert conn.execute("SELECT sport FROM bets").fetchone()["sport"] == "mlb"


def test_it_does_not_touch_another_league():
    conn = _journal()
    _stuck(conn, "cfb", "2026-09-05")
    _stuck(conn, "nfl", "2026-W01")
    assert ledger.repair_football_filed_as_baseball(conn) == 0


def test_it_is_a_no_op_on_a_clean_journal():
    assert ledger.repair_football_filed_as_baseball(_journal()) == 0


def test_the_settle_pass_runs_it_beside_its_hoops_twin():
    """`relabel_cross_league` does this job for the two basketball
    leagues, and for the same reason it runs BEFORE the ingest: the
    ingest picks which sports to fetch from the bets' own labels, so
    re-filing afterwards wastes a pass."""
    src = _src("engine", "maintenance.py")
    i = src.index("def settle_open(")
    block = src[i:src.index("\ndef ", i + 1)]
    assert "repair_football_filed_as_baseball(lconn)" in block
    assert block.index("repair_football_filed_as_baseball") < \
        block.index("ingest_for_open_bets("), \
        "the re-file runs after the ingest that reads the labels"


def test_the_repair_cannot_take_the_whole_settle_pass_down():
    """A maintenance chore must not be able to stop the grade that
    follows it — the rule every other step in this function obeys."""
    src = _src("engine", "maintenance.py")
    i = src.index("repair_football_filed_as_baseball")
    assert "try:" in src[max(0, i - 400):i]
    assert "except Exception as exc:" in src[i:i + 400]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
