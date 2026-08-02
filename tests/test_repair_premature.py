"""Undoing grades that happened before the game did.

The ingest stored partial stat lines from games in progress (the withholding
guard read a field nobody filled), so the settler graded bets mid-game. That
is fixed forward. This repairs the journals already holding those results.

The stakes are different from every other tool in this repo. Everything else
reports; this WRITES to a betting record. It reopens bets, reverses the
bankroll those bets moved, and deletes stat rows. So:

  * dry by default, and it says so loudly;
  * --apply takes a backup of both databases first and refuses to proceed
    if the backup fails;
  * the audit's burden of proof runs the other way from the settle guard.
    _team_day_unfinished abstains when a team has no game row — which is
    exactly the in-progress case, since only FINAL games get stored, and
    that abstention is the original bug. Here, absent means suspect.

The reversal has three parts and all three are required. Reopening without
reversing the bankroll leaves phantom P&L. Reopening without deleting the
partial rows means the next settle reaches the same verdict from the same
bad data.
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A settled date well OUTSIDE the strict window, computed rather than
#: written down. Inside the window (today and yesterday, which straddle the
#: UTC rollover on a night slate) the audit deliberately flags a missing
#: final on its own, so a hard-coded date would have these fixtures testing
#: one rule this week and the other rule next week.
D = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()


def _fixture():
    """A day that WAS ingested: PHI@CHC finished, KC@DET still playing."""
    tmp = tempfile.mkdtemp()
    h = db.connect(os.path.join(tmp, "h.db"))
    l = ledger.connect(os.path.join(tmp, "l.db"))
    h.execute("INSERT INTO games (sport,season,period,game_id,home,away,"
              "home_score,away_score) VALUES ('mlb',2026,?,?,'PHI','CHC',5,3)",
              (D, "PHI@CHC"))
    for player, team, mkt, val in (("Carter Jensen", "KC", "total_bases", 1.0),
                                   ("Bad Under", "KC", "hits", 0.0),
                                   ("Bryce Harper", "PHI", "total_bases", 3.0)):
        h.execute("INSERT INTO player_game_logs (sport,season,period,game_id,"
                  "player,team,opponent,position,home,market,value) VALUES "
                  "('mlb',2026,?,?,?,?,'X','OF',1,?,?)",
                  (D, f"{player}-{D}", player, team, mkt, val))
    h.commit()
    for player, mkt, side, line, pnl_d in (
            ("Carter Jensen", "total_bases", "OVER", 0.5, 9.0),
            ("Bad Under", "hits", "UNDER", 1.5, 10.0),
            ("Bryce Harper", "total_bases", "OVER", 1.5, 10.0)):
        l.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,"
                  "book,odds,stake_units,stake_dollars,status,category,actual,"
                  "pnl_units,pnl_dollars) VALUES ('2026-08-01T00:00:00','mlb',"
                  "?,?,?,?,?,'FD',-110,0.11,11.0,'won','main',1.0,0.1,?)",
                  (D, player, mkt, side, line, pnl_d))
    l.commit()
    return l, h


# --- the audit --------------------------------------------------------------
def test_it_finds_bets_graded_against_a_game_with_no_final():
    l, h = _fixture()
    rows = ledger.premature_settles(l, h)
    assert {r["player"] for r in rows} == {"Carter Jensen", "Bad Under"}


def test_a_bet_whose_game_did_finish_is_left_alone():
    """The control. Without it, "flag everything" passes the test above."""
    l, h = _fixture()
    assert "Bryce Harper" not in {r["player"]
                                  for r in ledger.premature_settles(l, h)}


def test_a_day_that_was_never_ingested_is_not_evidence_of_anything():
    """A date with no game rows at all may predate the games table, or
    belong to a sport that never stored scores. Without this guard the
    audit flags every settled bet in the journal."""
    tmp = tempfile.mkdtemp()
    h = db.connect(os.path.join(tmp, "h.db"))
    l = ledger.connect(os.path.join(tmp, "l.db"))
    h.execute("INSERT INTO player_game_logs (sport,season,period,game_id,"
              "player,team,opponent,position,home,market,value) VALUES "
              "('mlb',2026,?,?,'Someone','KC','X','OF',1,'hits',1.0)",
              (D, f"Someone-{D}"))
    h.commit()
    l.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
              "odds,stake_units,stake_dollars,status,category,pnl_dollars) "
              "VALUES ('x','mlb',?,'Someone','hits','OVER',0.5,'FD',-110,"
              "0.1,10.0,'won','main',9.0)", (D,))
    l.commit()
    assert ledger.premature_settles(l, h) == []


def test_a_game_that_has_not_started_yet_is_the_loudest_case():
    """The regression Ethan reported: props marked LOST on the Record page
    for games that had not been played.

    A game that has not started produces no games row at all — parse_results
    only writes finals — so the day-was-ingested precondition skipped the
    whole slate, and the audit stayed silent about the one thing it was
    built to find. Today and later, absence of a final is suspect on its
    own; there is no innocent reading of it.
    """
    import datetime
    today = datetime.date.today().isoformat()
    tmp = tempfile.mkdtemp()
    h = db.connect(os.path.join(tmp, "h.db"))
    l = ledger.connect(os.path.join(tmp, "l.db"))
    h.execute("INSERT INTO player_game_logs (sport,season,period,game_id,"
              "player,team,opponent,position,home,market,value) VALUES "
              "('mlb',2026,?,?,'Tonight Guy','KC','X','OF',1,'hits',0.0)",
              (today, f"Tonight Guy-{today}"))
    h.commit()
    l.execute("INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
              "odds,stake_units,stake_dollars,status,category,actual,"
              "pnl_units,pnl_dollars) VALUES ('x','mlb',?,'Tonight Guy',"
              "'hits','OVER',0.5,'FD',-110,0.1,10.0,'lost','main',0.0,"
              "-0.1,-10.0)", (today,))
    l.commit()
    assert [r["player"] for r in ledger.premature_settles(l, h)] == \
        ["Tonight Guy"]


def test_an_open_bet_is_not_a_candidate():
    l, h = _fixture()
    l.execute("UPDATE bets SET status='open'")
    l.commit()
    assert ledger.premature_settles(l, h) == []


def test_the_audit_writes_nothing():
    l, h = _fixture()
    before = (l.execute("SELECT COUNT(*) FROM bets WHERE status='won'").fetchone()[0],
              h.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0],
              ledger.bankroll(l))
    ledger.premature_settles(l, h)
    after = (l.execute("SELECT COUNT(*) FROM bets WHERE status='won'").fetchone()[0],
             h.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0],
             ledger.bankroll(l))
    assert before == after


# --- dry by default ---------------------------------------------------------
def test_a_dry_run_changes_nothing():
    l, h = _fixture()
    plan = ledger.repair_premature(l, h)          # apply defaults to False
    assert plan["applied"] is False
    assert l.execute("SELECT COUNT(*) FROM bets "
                     "WHERE status='won'").fetchone()[0] == 3
    assert h.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == 3


def test_a_dry_run_still_reports_the_bankroll_it_would_move():
    l, h = _fixture()
    plan = ledger.repair_premature(l, h)
    assert plan["dollars_reversed"] == 19.0
    assert plan["bankroll_after"] == plan["bankroll_before"] - 19.0


# --- applying ---------------------------------------------------------------
def test_applying_reopens_only_the_suspect_bets():
    l, h = _fixture()
    ledger.repair_premature(l, h, apply=True)
    rows = {r["player"]: r["status"] for r in
            l.execute("SELECT player, status FROM bets")}
    assert rows == {"Carter Jensen": "open", "Bad Under": "open",
                    "Bryce Harper": "won"}


def test_applying_clears_the_result_fields():
    """A reopened bet carrying its old `actual` would re-settle to the same
    verdict without ever consulting the data again."""
    l, h = _fixture()
    ledger.repair_premature(l, h, apply=True)
    r = l.execute("SELECT actual, pnl_units, pnl_dollars FROM bets "
                  "WHERE player='Bad Under'").fetchone()
    assert r["actual"] is None and r["pnl_dollars"] is None


def test_applying_reverses_the_bankroll():
    """_settle_one ADVANCED the bankroll when it graded these. Reopening
    without reversing leaves phantom P&L that nothing will ever remove."""
    l, h = _fixture()
    before = ledger.bankroll(l)
    ledger.repair_premature(l, h, apply=True)
    assert ledger.bankroll(l) == before - 19.0


def test_applying_deletes_the_partial_rows_that_caused_it():
    """Otherwise the next settle reaches the same verdict from the same bad
    data, and the repair looks like it did nothing."""
    l, h = _fixture()
    ledger.repair_premature(l, h, apply=True)
    left = {r[0] for r in h.execute(
        "SELECT player FROM player_game_logs")}
    assert left == {"Bryce Harper"}


def test_applying_twice_is_a_no_op():
    """The second pass must find nothing — a repair that keeps reversing
    the bankroll every time it runs is worse than the bug."""
    l, h = _fixture()
    ledger.repair_premature(l, h, apply=True)
    after_first = ledger.bankroll(l)
    second = ledger.repair_premature(l, h, apply=True)
    assert second["suspect"] == []
    assert ledger.bankroll(l) == after_first


def test_it_reports_what_it_touched_not_just_a_count():
    """"47 rows repaired" is not something anyone can check afterwards."""
    l, h = _fixture()
    plan = ledger.repair_premature(l, h, apply=True)
    r = plan["suspect"][0]
    for key in ("date", "player", "market", "side", "line", "status",
                "pnl_dollars", "category"):
        assert key in r


# --- the CLI ----------------------------------------------------------------
def test_the_cli_is_dry_unless_apply_is_passed():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def repair_premature_cli(")
    block = src[i:i + 3000]
    assert 'apply = "--apply" in argv' in block
    assert "DRY RUN — nothing was changed." in block


def test_the_cli_backs_up_before_it_writes_and_stops_if_that_fails():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def repair_premature_cli(")
    block = src[i:i + 3000]
    assert "backup = _backup_before_repair()" in block
    b = block.index("backup = _backup_before_repair()")
    assert "if not backup:" in block[b:b + 500]
    assert block.index("if not backup:") < block.index(
        "_led.repair_premature(lconn, hconn, apply=True)")


def test_the_cli_calls_out_the_unders_specifically():
    """An over already past its line graded early but correctly. An under
    graded in the fourth inning is a result that had not happened."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def repair_premature_cli(")
    assert 'str(r["side"]).upper() == "UNDER"' in src[i:i + 3000]


def test_it_is_wired_to_a_flag():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert 'if "--repair-premature" in argv:' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
