"""A WNBA bet filed under 'nba' can never be graded.

The doctor's real output: seventeen "no results ingested" picks dated
2026-07-31, sport nba — Caitlin Clark, Sophie Cunningham, Kelsey Mitchell.
The NBA does not play games in July. The build that wrote them runs as BOTH
leagues, journaled every pick as ``{"sport": "nba"}``, and then swept the
journal with ``sport=args.league`` — so a WNBA pick was filed where no WNBA
ingest could ever reach it, and "ingest wnba" (the tip the report gave)
could never have fixed it.

Two halves: the build now journals under the league it ran as, and the
settle passes re-file the rows the old build already wrote — strictly, only
when the player appears in exactly ONE league's game logs, because flipping
on a guess just moves the bet from one wrong place to another.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def _journal(sport="nba", player="Caitlin Clark", status="open"):
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES (?,?,?,?,"
        "'OVER',18.5,-110,'Play',0.5,5.0,?,'main')",
        (sport, "2026-07-31", player, "pts", status))
    lconn.commit()
    return lconn


def _wnba_history(player="Caitlin Clark", period="2026-07-31",
                  with_final=True):
    hconn = db.connect(":memory:")
    db.upsert_player_logs(hconn, [{
        "sport": "wnba", "season": 2026, "period": period, "game_id": "gW",
        "player": player, "team": "IND", "opponent": "NYL", "position": "G",
        "home": 1, "market": "pts", "value": 24.0}])
    if with_final:
        db.upsert_games(hconn, [{
            "sport": "wnba", "season": 2026, "period": period,
            "game_id": "gW", "home": "IND", "away": "NYL",
            "home_score": 88, "away_score": 80, "spread": 0.0,
            "total": None, "roof": "dome", "surface": "court",
            "temp": None, "wind": None, "extra": ""}])
    return hconn


# --- the source of the rows: the build ---------------------------------------
def test_the_build_journals_under_the_league_it_ran_as():
    src = _read("nba_build.py")
    assert '{"sport": args.league, "date": args.date' in src
    assert '{"sport": "nba", "date": args.date' not in src, \
        "the journal label is hardcoded while the settle reads args.league"


# --- the repair for the rows already written ---------------------------------
def test_a_wnba_bet_filed_under_nba_is_refiled():
    lconn = _journal(sport="nba")
    hconn = _wnba_history()
    assert ledger.relabel_cross_league(lconn, hconn) == 1
    assert lconn.execute("SELECT sport FROM bets").fetchone()[0] == "wnba"


def test_the_flip_works_in_both_directions():
    lconn = _journal(sport="wnba", player="Jayson Tatum")
    hconn = db.connect(":memory:")
    db.upsert_player_logs(hconn, [{
        "sport": "nba", "season": 2026, "period": "2026-01-15",
        "game_id": "gN", "player": "Jayson Tatum", "team": "BOS",
        "opponent": "NYK", "position": "F", "home": 1,
        "market": "pts", "value": 30.0}])
    assert ledger.relabel_cross_league(lconn, hconn) == 1
    assert lconn.execute("SELECT sport FROM bets").fetchone()[0] == "nba"


def test_a_name_in_both_leagues_is_left_alone():
    """Flipping on a guess moves the bet from one wrong place to another."""
    lconn = _journal(sport="nba", player="Both Leagues")
    hconn = _wnba_history(player="Both Leagues")
    db.upsert_player_logs(hconn, [{
        "sport": "nba", "season": 2026, "period": "2026-01-15",
        "game_id": "gN", "player": "Both Leagues", "team": "BOS",
        "opponent": "NYK", "position": "F", "home": 1,
        "market": "pts", "value": 12.0}])
    assert ledger.relabel_cross_league(lconn, hconn) == 0
    assert lconn.execute("SELECT sport FROM bets").fetchone()[0] == "nba"


def test_a_name_in_neither_league_is_left_alone():
    lconn = _journal(sport="nba", player="Nobody Logged")
    hconn = db.connect(":memory:")
    assert ledger.relabel_cross_league(lconn, hconn) == 0


def test_a_settled_bet_keeps_its_label():
    """History is history — only OPEN bets re-file."""
    lconn = _journal(sport="nba", status="won")
    hconn = _wnba_history()
    assert ledger.relabel_cross_league(lconn, hconn) == 0
    assert lconn.execute("SELECT sport FROM bets").fetchone()[0] == "nba"


def test_a_refiled_bet_then_settles_end_to_end():
    """The whole point: relabel, then the ordinary sweep grades it."""
    lconn = _journal(sport="nba")
    hconn = _wnba_history()
    ledger.relabel_cross_league(lconn, hconn)
    assert ledger.settle_from_history(lconn, hconn) == 1
    row = lconn.execute("SELECT sport, status FROM bets").fetchone()
    assert (row[0], row[1]) == ("wnba", "won")


# --- the wiring: both settle passes, and BEFORE the ingest -------------------
def test_the_manual_settle_refiles_before_it_ingests():
    """The ingest decides which sports to fetch from the bets' own labels —
    relabeling after it wastes a pass on the exact rows being repaired."""
    src = _read("launch.py")
    fn = src[src.index("def settle_now("):src.index("def _tailscale_ip(")]
    assert "relabel_cross_league" in fn
    assert fn.index("relabel_cross_league") < fn.index(
        "ingest_for_open_bets"), "relabel runs after the ingest chose sports"


def test_the_nightly_settle_refiles_before_it_ingests():
    src = _read(os.path.join("engine", "maintenance.py"))
    fn = src[src.index("def settle_open("):src.index("def run_if_due(")]
    assert "relabel_cross_league" in fn
    assert fn.index("relabel_cross_league") < fn.index(
        "ingest_for_open_bets(lconn, hconn"), \
        "relabel runs after the ingest chose sports"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
