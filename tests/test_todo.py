"""The chore list stops being prose and becomes a query.

Ethan, 2026-08-20: "go through the when home list and all our other todo
lists ... mark off and remove whats complete and figure out what still
needs to be done."

`docs/WHEN_HOME.md` had reached 1,964 lines and **not one item in it
could be verified from anywhere**. The chores run against a database and
a set of model files on Ethan's laptop; a cloud session cannot see them,
and two weeks later neither can he. "Did I run the MLB refit?" is not a
question anybody should answer from memory — it is the same failure as a
cache version that depends on remembering to bump it.

So every item reads the artifact its own chore writes. The tests below
are mostly about the THIRD verdict, because that is the one a checklist
like this gets wrong:

    done        with evidence
    do this     with the command
    can't tell  and why

A tool that reports "all clear" on a machine with no ledger is worse than
one that refuses, and inferring "done" from an absent file is exactly how
it would happen. `test_absence_is_never_read_as_done` is the guard.

The first draft failed its own rule twice, both caught by running it:
it queried a `result` column that does not exist (the table says
`status`), and with zero settled bets it told Ethan to run a refit that
could only decline. Both are pinned below.

Run directly: `python3 tests/test_todo.py`
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import todo                                        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _models(tmp, calibration=None, formfit=None, selection=None):
    d = Path(tmp) / "models"
    d.mkdir(parents=True, exist_ok=True)
    if calibration is not None:
        (d / "calibration.json").write_text(json.dumps(calibration))
    if formfit is not None:
        (d / "formfit.json").write_text(json.dumps(formfit))
    if selection is not None:
        (d / "selection.json").write_text(json.dumps(selection))
    return d


def test_a_dial_adopted_after_its_temperature_is_the_finding():
    """The ordering bug itself: the correction now describes a model that
    moved underneath it."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp,
                    calibration={"nfl:passing_yards": {"fitted_at": "2026-08-13",
                                                       "temperature": 1.2}},
                    formfit={"nfl:passing_yards": {"adopted": True,
                                                   "fitted": "2026-08-14T09:00:00"}})
        rows = {i.name: i for i in todo.learning_items(d)}
    assert rows["NFL"].state == todo.TODO, rows["NFL"].evidence
    assert "--relearn nfl" in rows["NFL"].command
    assert "2026-08-14" in rows["NFL"].evidence and "2026-08-13" in rows["NFL"].evidence


def test_the_right_order_reads_as_done():
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp,
                    calibration={"mlb:hits": {"fitted_at": "2026-08-15"}},
                    formfit={"mlb:hits": {"adopted": True,
                                          "fitted": "2026-08-12T09:00:00"}})
        rows = {i.name: i for i in todo.learning_items(d)}
    assert rows["MLB"].state == todo.DONE, rows["MLB"].evidence


def test_same_day_is_ambiguous_and_says_so():
    """calibrate.py stores a date, formfit.py a datetime. Within one day
    the order genuinely cannot be read, and claiming either answer would
    be inventing one."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp,
                    calibration={"mlb:hits": {"fitted_at": "2026-08-15"}},
                    formfit={"mlb:hits": {"adopted": True,
                                          "fitted": "2026-08-15T23:00:00"}})
        rows = {i.name: i for i in todo.learning_items(d)}
    assert rows["MLB"].state == todo.UNKNOWN, rows["MLB"].evidence
    assert "cannot be read" in rows["MLB"].evidence


def test_an_unadopted_dial_does_not_count():
    """A dial the fit DECLINED changes no number, so it cannot have
    invalidated anything. Counting it would send Ethan to a refit for a
    model that never moved."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp,
                    calibration={"mlb:hits": {"fitted_at": "2026-08-10"}},
                    formfit={"mlb:hits": {"adopted": False,
                                          "fitted": "2026-08-19T09:00:00"}})
        rows = {i.name: i for i in todo.learning_items(d)}
    assert rows["MLB"].state == todo.DONE, rows["MLB"].evidence
    assert "no dial adopted" in rows["MLB"].evidence


def test_absence_is_never_read_as_done():
    """THE RULE THIS TOOL LIVES OR DIES BY. A machine with no model store
    has not finished its chores; it simply cannot answer. Reporting "all
    clear" there is the failure mode that makes a checklist worthless."""
    with tempfile.TemporaryDirectory() as tmp:
        rows = todo.learning_items(Path(tmp) / "nothing")
    assert len(rows) == 1 and rows[0].state == todo.UNKNOWN
    assert "never fitted anything" in rows[0].evidence

    assert todo.data_items(None)[0].state == todo.UNKNOWN
    assert todo.book_items(None)[0].state == todo.UNKNOWN
    with tempfile.TemporaryDirectory() as tmp:
        assert todo.haircut_item(Path(tmp) / "nothing").state == todo.UNKNOWN


def test_nothing_to_fit_is_not_a_chore():
    """Caught by running it: with no settled bets the guard fell through
    and told Ethan to run a refit that could only decline."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp, selection={"fitted_at": "2026-08-12",
                                    "pooled": {"n": 0}})
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE bets (status TEXT)")
        item = todo.haircut_item(d, conn)
        conn.close()
    assert item.state == todo.DONE, item.evidence
    assert "nothing to fit" in item.evidence


def test_a_book_that_has_moved_a_long_way_reopens_the_fit():
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp, selection={"fitted_at": "2026-08-12",
                                    "pooled": {"n": 100}})
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE bets (status TEXT)")
        conn.executemany("INSERT INTO bets VALUES (?)", [("won",)] * 400)
        item = todo.haircut_item(d, conn)
        conn.close()
    assert item.state == todo.TODO, item.evidence
    assert "--haircut" in item.command


def test_a_book_that_has_barely_moved_does_not():
    """Re-fitting one parameter on 5% more rows moves it inside its own
    noise, so the answer would be the same answer."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _models(tmp, selection={"fitted_at": "2026-08-12",
                                    "pooled": {"n": 400}})
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE bets (status TEXT)")
        conn.executemany("INSERT INTO bets VALUES (?)", [("won",)] * 420)
        item = todo.haircut_item(d, conn)
        conn.close()
    assert item.state == todo.DONE, item.evidence


def test_the_queries_match_the_schema_that_exists():
    """The first draft asked for a `result` column. The table calls it
    `status`, so every book check answered "can't tell" with a SQL error
    inside it — which the three-verdict design made survivable and
    visible, but is still wrong. Run against the REAL schema."""
    from engine import ledger
    with tempfile.TemporaryDirectory() as tmp:
        conn = ledger.connect(Path(tmp) / "l.db")
        rows = todo.book_items(conn, None, "2026-08-20")
        conn.close()
    assert rows, "no book items produced"
    for r in rows:
        assert "no such column" not in r.evidence, r.evidence
        assert "could not read" not in r.evidence, r.evidence


def test_an_open_pick_on_a_past_day_is_the_settle_chore():
    from engine import ledger
    with tempfile.TemporaryDirectory() as tmp:
        conn = ledger.connect(Path(tmp) / "l.db")
        conn.execute("INSERT INTO bets (sport, date, player, market, status) "
                     "VALUES ('mlb','2026-08-01','A','hits','open')")
        rows = {r.name: r for r in todo.book_items(conn, None, "2026-08-20")}
        conn.close()
    r = rows["open picks on past days"]
    assert r.state == todo.TODO and "--settle all" in r.command, r.evidence


def test_the_backup_destination_is_reported_missing():
    """It is unset today, and the failure it does not survive is the one
    it exists for."""
    item = {i.name: i for i in todo.config_items({})}["QB_BACKUP_REMOTE"]
    assert item.state == todo.TODO
    assert "same disk" in item.evidence
    ok = {i.name: i for i in todo.config_items(
        {"QB_BACKUP_REMOTE": "b2://x"})}["QB_BACKUP_REMOTE"]
    assert ok.state == todo.DONE


def test_a_paywall_with_no_comped_address_locks_ethan_out():
    """The specific foot-gun named in docs/NEXT.md, in the order it
    fires: the first thing an un-comped paywall does is lock out its own
    owner."""
    item = {i.name: i for i in todo.config_items({"QB_PAYWALL": "1"})}["paywall"]
    assert item.state == todo.TODO
    assert "lock you out" in item.evidence
    fine = {i.name: i for i in todo.config_items(
        {"QB_PAYWALL": "1", "QB_COMP_EMAILS": "a@b.c"})}["paywall"]
    assert fine.state == todo.DONE


def test_every_todo_carries_a_command_or_a_reason():
    """A chore with no next action is a worry, not a task. The only ones
    allowed to skip the command are those whose next action is a decision
    (a backup destination has to be chosen before it can be typed)."""
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE bets (status TEXT, date TEXT)")
        items = todo.collect(models=Path(tmp) / "none", conn=None,
                             ledger_conn=conn, env={})
        conn.close()
    for i in items:
        if i.state == todo.TODO and not i.command:
            assert len(i.evidence) > 60, \
                f"{i.name} says to do something without saying what: {i.evidence}"


def test_the_report_renders_and_counts_what_it_shows():
    with tempfile.TemporaryDirectory() as tmp:
        items = todo.collect(models=Path(tmp) / "none", conn=None,
                             ledger_conn=None, env={})
    text = todo.render(items)
    n_todo = sum(1 for i in items if i.state == todo.TODO)
    assert f"{n_todo} thing(s) to do" in text
    assert "docs/WHEN_HOME.md" in text, \
        "the report must point at where the judgement calls live"
    for i in items:
        assert i.name in text, f"{i.name} was collected and not rendered"


def test_the_launcher_exposes_it():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"--todo" in argv' in src, "--todo is not wired into the launcher"


def test_every_item_lands_in_a_group_that_renders():
    """An Item whose group is not in GROUPS is dropped by `render` without
    a word. That is exactly what happened to the legal-pages check on its
    first run: it was written, it was collected, and it appeared nowhere,
    which is the worst possible outcome for a reminder."""
    from engine import todo as T
    known = {k for k, _ in T.GROUPS}
    items = T.collect()
    assert items
    for i in items:
        assert i.group in known, (
            "%r is in group %r, which render() does not print — the item "
            "exists and nobody will ever see it" % (i.name, i.group))
    text = T.render(items)
    for i in items:
        assert i.name in text, "%r never reaches the report" % i.name


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
