"""A sport's verdict is its own, or it is worthless.

Ethan's Week 1 priority, 2026-09-06: "confirming NFL can be measured from
its first week ... so by Week 4 you know whether NFL edge is noise
INSTEAD OF INHERITING BASEBALL'S ANSWER."

That is the failure this file exists to prevent, and it is a quiet one.
`stakecheck --info --sport nfl` returning MLB's 931-bet verdict would not
look like a bug. It would look like an answer — a confident AUC on a
sport with four settled bets — and every decision downstream of it would
be made about football using baseball's evidence.

WHY IT MATTERS MOST RIGHT NOW. Football has zero settled bets. Every
measurement this book makes is currently a baseball verdict, and the
whole point of Week 1 is to start replacing that with football's own.
A filter that leaks would mean the replacement never happens and nobody
notices, because the number keeps looking reasonable.

THE OTHER HALF is the empty case. A sport with no settled bets must say
so plainly and exit clean — not crash, and not report a confident figure
computed from nothing. That is NFL's exact state until Wednesday.

Run directly: `python3 tests/test_sport_isolation.py`
"""

import datetime
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                              # noqa: E402

#: Enough MLB rows that a leak is unmistakable in the count.
MLB_N = 120
#: As few NFL rows as a real Week 1 might produce.
NFL_N = 4


def _book():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "l.db")
    l = ledger.connect(db)
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    rows = [(now, "mlb", "2026-08-01", f"P{i}", "hits", "OVER", 0.5, -110,
             0.60 if i % 2 == 0 else 0.40, "won" if i % 2 == 0 else "lost")
            for i in range(MLB_N)]
    rows += [(now, "nfl", "2026-W01", f"N{i}", "rec_yds", "OVER", 50.5, -110,
              0.55, "won") for i in range(NFL_N)]
    l.executemany(
        "INSERT INTO bets (ts,sport,date,player,market,side,line,odds,"
        "hit_prob,status,category,stake_units,stake_dollars) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,'main',1.0,10.0)", rows)
    l.commit()
    return db


def _run(*args):
    r = subprocess.run([sys.executable, "stakecheck.py", *args],
                       capture_output=True, text=True, cwd=ROOT,
                       env={**os.environ})
    return r.returncode, (r.stdout or "")


def test_the_information_test_reports_only_the_sport_asked_for():
    """THE LEAK GUARD. If this fails, football is being told baseball's
    answer and the number looks perfectly ordinary."""
    db = _book()
    _, mlb = _run("--info", "--sport", "mlb", "--db", db)
    _, nfl = _run("--info", "--sport", "nfl", "--db", db)
    assert str(MLB_N) in mlb, mlb[:400]
    assert str(MLB_N) not in nfl, (
        f"the NFL report mentions {MLB_N} — baseball's sample has leaked "
        f"into football's verdict:\n{nfl[:400]}")
    assert str(NFL_N) in nfl, nfl[:400]


def test_clv_reports_only_the_sport_asked_for():
    """Same guard on the other measurement. CLV is the one edge this book
    has actually measured (+2.05% over 931 mostly-baseball bets), which
    makes it the one most tempting to read as football's."""
    db = _book()
    _, mlb = _run("--clv", "--sport", "mlb", "--db", db)
    _, nfl = _run("--clv", "--sport", "nfl", "--db", db)
    assert str(MLB_N) in mlb, mlb[:400]
    assert str(MLB_N) not in nfl, (
        f"the NFL CLV report mentions {MLB_N}:\n{nfl[:400]}")


def test_a_sport_with_nothing_settled_says_so_and_exits_clean():
    """NFL's exact state until Wednesday. It must refuse to answer rather
    than answer from nothing, and it must not crash doing it."""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "empty.db")
    ledger.connect(db)
    code, out = _run("--info", "--sport", "nfl", "--db", db)
    assert code == 0, f"exited {code} on an empty book:\n{out[:400]}"
    assert "0 settled bets" in out, out[:400]
    # It must not print a verdict it cannot support.
    assert "AUC" not in out.split("Too few")[0][-200:], out[:400]


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
