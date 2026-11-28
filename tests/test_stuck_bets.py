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

    # A REALISTIC day. Storing one player made D_MID a thin day, which the
    # report now (correctly) calls an unfinished ingest rather than a
    # missing player — so the fixture has to look like a real slate for the
    # per-player causes to be the thing under test.
    logs = [{"sport": "mlb", "season": 2026, "period": D_MID, "game_id": "g1",
             "player": f"Filler {i}", "team": "BOS", "opponent": "NYY",
             "position": "S", "home": 1, "market": "hits", "value": 1.0}
            for i in range(150)]
    logs.append({**logs[0], "player": "Real Player", "value": 2.0})
    db.upsert_player_logs(hconn, logs)
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


# --- "player has no log" was two problems wearing one label ----------------
def _day(hconn, date, n_players, extra_names=()):
    rows = [{"sport": "mlb", "season": 2026, "period": date, "game_id": "g",
             "player": f"Filler {i}", "team": "SEA", "opponent": "NYY",
             "position": "S", "home": 1, "market": "hits", "value": 1.0}
            for i in range(n_players)]
    for name in extra_names:
        rows.append({**rows[0], "player": name})
    db.upsert_player_logs(hconn, rows)


def _one_bet(player, date="2026-07-28", market="home_runs"):
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES ('mlb',?,?,?,"
        "'OVER',0.5,400,'C',0.2,2.0,'open','longshot')", (date, player, market))
    lconn.commit()
    return lconn


def test_a_thin_day_is_not_reported_as_a_missing_player():
    """30 bets on one date all saying "player has no log" is not 30 name
    problems — it is one unfinished ingest, and the fixes are opposite."""
    lconn = _one_bet("Cal Raleigh")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-28", 12)
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "day barely ingested"
    assert r["day_players"] == 12


def test_a_full_day_missing_one_player_still_says_so():
    lconn = _one_bet("Cal Raleigh")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-28", 150)
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "player has no log"
    assert r["day_players"] == 150


def test_a_near_miss_name_is_offered_so_the_map_can_be_fixed():
    """The difference between "he did not play" and "we spell him
    differently" is the whole of what to do next."""
    lconn = _one_bet("Jonny Deluca")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-28", 150, extra_names=("Jonathan Deluca",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "player has no log"
    assert r.get("closest") == "jonathan deluca"


def test_names_the_normalizer_already_bridges_are_not_reported_as_missing():
    """Accents and suffixes are handled upstream; re-reporting them here
    would send someone to fix a map that is already right."""
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-28", 150,
         extra_names=("Eugenio Su\u00e1rez", "Luis Robert Jr."))
    for journal_name in ("Eugenio Suarez", "Luis Robert"):
        lconn = _one_bet(journal_name)
        r = ledger.why_open(lconn, hconn, D_NOW)[0]
        assert r["reason"] != "player has no log", journal_name


def test_the_thin_bar_is_named_and_sized_for_a_real_slate():
    assert ledger.THIN_DAY_PLAYERS >= 50


def test_the_report_names_the_day_the_grader_will_actually_use():
    """A report pointing at a day the settle ignores is worse than silent —
    it sends you to confirm a fix that will not happen."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-26", 300, extra_names=("Cal Raleigh",))
    _day(hconn, "2026-07-28", 368, extra_names=("Cal Raleigh",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["logged_on"] == "2026-07-26", \
        "the report offers the later day while the grader uses the earlier"


def test_a_late_game_filed_on_the_next_date_is_its_own_diagnosis():
    """His 7-27 board: 278 players and 12 games stored, and thirty regulars
    "missing" anyway. A 10pm Pacific first pitch is already tomorrow in UTC,
    so the bet's slate date and the feed's game date can differ by one. That
    is a boundary bug, not a DNP and not a spelling difference, and calling
    it either would send someone to fix the wrong thing."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-28", 368, extra_names=("Cal Raleigh",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "logged under the next day"
    assert r["logged_on"] == "2026-07-28"


def test_a_genuinely_absent_player_is_still_reported_as_absent():
    """The neighbour check must not swallow the real DNPs."""
    lconn = _one_bet("Never Played", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-28", 368)
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "player has no log"
    assert not r.get("logged_on")


def test_the_neighbour_search_only_looks_one_day_each_way():
    """Two days out is a different game, and matching it would grade a bet
    against the wrong night's box score — the worst outcome available."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-30", 300, extra_names=("Cal Raleigh",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "player has no log"


def test_a_week_label_has_no_neighbours_to_search():
    """NFL dates are not days, so date arithmetic on them must not throw."""
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES ('nfl','2026-W1',"
        "'A Receiver','rec_yds','OVER',50.5,-110,'A',1.0,10.0,'open','main')")
    lconn.commit()
    hconn = db.connect(":memory:")
    rows = ledger.why_open(lconn, hconn, D_NOW)
    assert rows and rows[0]["reason"]


# --- the cause, and the repair ----------------------------------------------
def test_a_longshot_is_journaled_under_its_own_games_date():
    """The cause. A 9pm Eastern first pitch is already tomorrow in UTC, so a
    slate stamped off a UTC clock sits a day ahead of the date the box score
    is filed under — and a bet dated one day off its own result can never
    settle. The row already carried game_date; the journal ignored it."""
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_longshots(lconn, {"sport": "mlb", "date": "2026-07-27",
        "long_shots": [{"player": "Cal Raleigh", "market": "home_runs",
                        "odds": 400, "book": "FanDuel",
                        "game_date": "2026-07-26", "model_prob": 0.2}]})
    got = lconn.execute("SELECT date FROM bets").fetchone()[0]
    assert got == "2026-07-26", got


def test_a_row_with_no_game_date_still_uses_the_slate():
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_longshots(lconn, {"sport": "mlb", "date": "2026-07-27",
        "long_shots": [{"player": "No Date", "market": "home_runs",
                        "odds": 400, "book": "FanDuel",
                        "model_prob": 0.2}]})
    assert lconn.execute("SELECT date FROM bets").fetchone()[0] == "2026-07-27"


def _stranded(day="2026-07-27", log_day="2026-07-26", also=()):
    """A bet dated a day off its own stat line — the reported shape."""
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES ('mlb',?,"
        "'Cal Raleigh','home_runs','OVER',0.5,400,'C',0.1,0.0,'open',"
        "'longshot_watch')", (day,))
    lconn.commit()
    hconn = db.connect(":memory:")
    for d in (log_day, *also):
        db.upsert_player_logs(hconn, [{
            "sport": "mlb", "season": 2026, "period": d, "game_id": f"g{d}",
            "player": "Cal Raleigh", "team": "SEA", "opponent": "NYY",
            "position": "S", "home": 1, "market": "home_runs", "value": 1.0}])
        db.upsert_games(hconn, [{
            "sport": "mlb", "season": 2026, "period": d, "game_id": f"g{d}",
            "home": "SEA", "away": "NYY", "home_score": 5, "away_score": 2,
            "spread": 0.0, "total": None, "roof": "open", "surface": "grass",
            "temp": None, "wind": None, "extra": ""}])
    return lconn, hconn


def test_a_bet_stranded_one_day_off_its_result_now_settles():
    """The repair, for the thirty already in the journal."""
    lconn, hconn = _stranded()
    assert ledger.settle_from_history(lconn, hconn) == 1
    row = lconn.execute("SELECT status FROM bets").fetchone()
    assert row[0] == "won"


def test_a_regular_logged_on_both_neighbours_still_grades():
    """My first guard was "exactly one neighbouring day", and it was useless
    for baseball: teams play most days, so any regular is logged on both
    sides of any date. Twenty-four of the reported thirty survived it and
    stayed open. Direction is the discriminator that works."""
    lconn, hconn = _stranded(log_day="2026-07-26", also=("2026-07-28",))
    assert ledger.settle_from_history(lconn, hconn) == 1
    assert lconn.execute("SELECT status FROM bets").fetchone()[0] == "won"


def test_a_log_only_on_the_day_AFTER_is_still_refused():
    """The direction is geography, not preference. Every mechanism that
    produces this drift labels a US evening game with a UTC clock, so a
    drifted bet always sits AHEAD of its result. Nothing explains a bet
    dated BEFORE its own game, and grading one would be inventing a
    reason."""
    lconn, hconn = _stranded(log_day="2026-07-28")
    assert ledger.settle_from_history(lconn, hconn) == 0
    assert lconn.execute("SELECT status FROM bets").fetchone()[0] == "open"


def test_the_fallback_does_not_reach_two_days_out():
    lconn, hconn = _stranded(log_day="2026-07-24")
    assert ledger.settle_from_history(lconn, hconn) == 0


def test_the_bets_own_day_still_wins_when_it_has_the_log():
    """The neighbour search must only run when the bet's own date is empty
    for this player — never in preference to it."""
    lconn, hconn = _stranded(log_day="2026-07-27", also=("2026-07-26",))
    assert ledger.settle_from_history(lconn, hconn) == 1


# --- the repair's refusals are NAMED, not promised away ---------------------
# Seventeen real home-run bets sat on "logged under the next day" while the
# tip said "tell me and I will fix the join" — but the join already had its
# repair, and the seventeen were stuck behind one of its guards. A report
# that promises a fix that shipped weeks ago is worse than no report; each
# row now names the guard that refused and the command that clears it.

def test_a_missing_market_row_on_the_neighbour_day_is_named():
    """He IS logged next door — but without this market's stat row, the
    repair has nothing to grade against. Re-ingesting that day is the fix."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-26", 300, extra_names=("Cal Raleigh",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "logged under the next day"
    assert "no home_runs stat row" in r["repair"]
    assert "--dates 2026-07-26" in r["repair"]


def test_an_unfinished_game_on_the_bets_own_date_is_named():
    """The repair must refuse while the bet could be about its OWN day's
    game — and the report says so, with the date whose finals to ingest."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    db.upsert_player_logs(hconn, [{
        "sport": "mlb", "season": 2026, "period": "2026-07-26",
        "game_id": "gCR", "player": "Cal Raleigh", "team": "SEA",
        "opponent": "NYY", "position": "S", "home": 1,
        "market": "home_runs", "value": 1.0}])
    db.upsert_games(hconn, [{
        "sport": "mlb", "season": 2026, "period": "2026-07-27",
        "game_id": "gO", "home": "SEA", "away": "NYY",
        "home_score": None, "away_score": None, "spread": 0.0,
        "total": None, "roof": "open", "surface": "grass",
        "temp": None, "wind": None, "extra": ""}])
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "logged under the next day"
    assert "no final score" in r["repair"]
    assert "--dates 2026-07-27" in r["repair"]


def test_a_repairable_bet_is_sent_to_the_settle_not_to_me():
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    db.upsert_player_logs(hconn, [{
        "sport": "mlb", "season": 2026, "period": "2026-07-26",
        "game_id": "gCR", "player": "Cal Raleigh", "team": "SEA",
        "opponent": "NYY", "position": "S", "home": 1,
        "market": "home_runs", "value": 1.0}])
    db.upsert_games(hconn, [{
        "sport": "mlb", "season": 2026, "period": "2026-07-26",
        "game_id": "gCR", "home": "SEA", "away": "NYY",
        "home_score": 5, "away_score": 2, "spread": 0.0,
        "total": None, "roof": "open", "surface": "grass",
        "temp": None, "wind": None, "extra": ""}])
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "logged under the next day"
    assert "--settle all" in r["repair"]


def test_a_log_on_the_day_after_is_named_as_the_wrong_direction():
    """The UTC drift only ever pushes a bet AHEAD of its box score. A log
    on the day AFTER means his game on the bet's date was probably never
    stored — a different repair, and the note must not point at the join."""
    lconn = _one_bet("Cal Raleigh", date="2026-07-27")
    hconn = db.connect(":memory:")
    _day(hconn, "2026-07-27", 278)
    _day(hconn, "2026-07-28", 368, extra_names=("Cal Raleigh",))
    r = ledger.why_open(lconn, hconn, D_NOW)[0]
    assert r["reason"] == "logged under the next day"
    assert "day AFTER" in r["repair"]
    assert "--dates 2026-07-27" in r["repair"]


def test_the_stuck_report_prints_the_repair_line():
    launch = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "launch.py"), encoding="utf-8").read()
    fn = launch[launch.index("def show_stuck()"):launch.index("def settle_all()")]
    assert 'r.get("repair")' in fn, "the refusal is computed but never shown"
    assert "Tell me and I will fix the join" not in fn, \
        "the tip still promises a fix that already shipped"


def test_a_scheduled_future_week_is_not_stuck():
    """Seven September W01 game bets landed in the doctor's stuck list in
    August: the week label aged as instantly-stuck, and "n_games > 0 →
    game not found" never checked the bet's OWN game for a FINAL. A
    scheduled week is the calendar working, not a bet stuck — and the
    moment finals land, the same bet reads gradeable now."""
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    hconn = db.connect(":memory:")
    lconn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
        "stake_units,stake_dollars,status,category) VALUES ('nfl',"
        "'2026-W01','ATL@PIT','total','OVER',44.5,-110,'A',1.0,10.0,"
        "'open','main')")
    lconn.commit()
    db.upsert_games(hconn, [
        {"sport": "nfl", "season": 2026, "period": "001",
         "game_id": "ATL@PIT", "home": "PIT", "away": "ATL",
         "home_score": None, "away_score": None, "spread": -3.0,
         "total": 44.5, "roof": "open", "surface": "grass",
         "temp": None, "wind": None, "extra": ""}])
    rows = ledger.why_open(lconn, hconn, today=D_NOW)
    assert rows == [], "a scheduled unplayed week must not read stuck"
    hconn.execute("UPDATE games SET home_score=24, away_score=17")
    rows = ledger.why_open(lconn, hconn, today=D_NOW)
    assert len(rows) == 1 and rows[0]["reason"] == "gradeable now"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
