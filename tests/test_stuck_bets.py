"""`--settle all` starting at a date from five days ago, every time.

"when i run the settle all, it starts back at 7-27 then works all the way to
today, is there still props open that was never settled"

Yes — and the sweep could not tell him which. `settle_all` finds every date
with an open pick, re-ingests it, grades what it can and moves on. A bet
that can NEVER grade keeps its date in that list forever, so the sweep
re-does the same work every night, reports nothing settled, and the date
stays. From the outside "still ingesting the backlog" and "these four bets
are permanently stuck" look identical.

`--stuck` names the difference. It writes nothing; it reports which lookup
failed for each open bet whose day is already over, because the four causes
need four different responses and only one of them is "run the settle
again".
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger

D_OLD, D_MID, D_NOW = "2026-07-20", "2026-07-27", "2026-08-01"


def _journal():
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    hconn = db.connect(":memory:")

    def bet(date, player, market, sport="mlb"):
        lconn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
            "stake_units,stake_dollars,status,category) VALUES (?,?,?,?,"
            "'OVER',1.5,-110,'A',1.0,10.0,'open','main')",
            (sport, date, player, market))

    bet(D_MID, "Ghost Player", "hits")       # day ingested, player absent
    bet(D_MID, "Real Player", "hits")        # matches — should have graded
    bet(D_MID, "Real Player", "home_runs")   # player there, market absent
    bet(D_MID, "AWAY@HOME", "total")         # game-level, no game row
    bet(D_OLD, "Nobody", "hits")             # nothing stored for that date
    bet(D_NOW, "Tonight", "hits")            # today — not stuck, still live
    lconn.commit()

    db.upsert_player_logs(hconn, [{
        "sport": "mlb", "season": 2026, "period": D_MID, "game_id": "g1",
        "player": "Real Player", "team": "BOS", "opponent": "NYY",
        "position": "S", "home": 1, "market": "hits", "value": 2.0}])
    return lconn, hconn


def _by_player(rows):
    return {r["player"]: r["reason"] for r in rows}


# --- the four causes --------------------------------------------------------
def test_each_cause_is_named_separately():
    """They need four different responses, and only one is "settle again"."""
    rows = _by_player(ledger.why_open(*_journal(), D_NOW))
    assert rows["Ghost Player"] == "player has no log"
    assert rows["Real Player"] in ("gradeable now", "market not ingested")
    assert rows["Nobody"] == "no results ingested"


def test_a_player_who_played_but_whose_stat_was_never_stored():
    rows = ledger.why_open(*_journal(), D_NOW)
    hr = [r for r in rows if r["market"] == "home_runs"]
    assert hr and hr[0]["reason"] == "market not ingested"


def test_a_bet_that_should_have_graded_says_so_rather_than_hiding():
    """"gradeable now" is the one that means the bug is in the settle path,
    not the data — and it is the one worth escalating."""
    rows = ledger.why_open(*_journal(), D_NOW)
    hits = [r for r in rows
            if r["player"] == "Real Player" and r["market"] == "hits"]
    assert hits and hits[0]["reason"] == "gradeable now"


def test_tonights_open_picks_are_not_called_stuck():
    """A pick from a day still in play is SUPPOSED to be open. Reporting it
    as a fault would bury the real ones."""
    rows = ledger.why_open(*_journal(), D_NOW)
    assert not any(r["date"] == D_NOW for r in rows)


def test_the_age_bar_is_configurable_and_defaults_to_days_not_hours():
    assert ledger.STUCK_AFTER_DAYS >= 1
    lconn, hconn = _journal()
    # A high bar excludes everything recent; a zero bar includes it all.
    assert ledger.why_open(lconn, hconn, D_NOW, older_than=99) == []
    assert len(ledger.why_open(lconn, hconn, D_NOW, older_than=0)) >= 5


def test_it_reports_and_never_writes():
    """Safe to run against a live journal mid-slate."""
    lconn, hconn = _journal()
    before = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='open'"
                           ).fetchone()[0]
    ledger.why_open(lconn, hconn, D_NOW)
    after = lconn.execute("SELECT COUNT(*) FROM bets WHERE status='open'"
                          ).fetchone()[0]
    assert before == after


def test_a_week_labelled_bet_is_judged_on_content_not_on_a_bad_date():
    """NFL journals '2026-W1', which date arithmetic cannot age. It must
    still be examined rather than crashing or being silently dropped."""
    lconn, hconn = _journal()
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES ('nfl','2026-W1',"
        "'A Receiver','rec_yds','OVER',50.5,-110,'A',1.0,10.0,'open','main')")
    lconn.commit()
    rows = ledger.why_open(lconn, hconn, D_NOW)
    assert any(r["player"] == "A Receiver" for r in rows)


# --- the command ------------------------------------------------------------
def test_the_launcher_exposes_it():
    launch = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "launch.py"), encoding="utf-8").read()
    assert '"--stuck" in argv' in launch
    assert "def show_stuck()" in launch


def test_every_reason_the_report_can_print_has_advice():
    """A diagnosis with no next step is half a tool."""
    launch = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "launch.py"), encoding="utf-8").read()
    fn = launch[launch.index("def show_stuck()"):launch.index("def settle_all()")]
    for reason in ("no results ingested", "player has no log",
                   "market not ingested", "game not found", "gradeable now"):
        assert f'"{reason}":' in fn, f"{reason} prints with no advice"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
