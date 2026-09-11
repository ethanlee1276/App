"""A bet on a game that was never played can never grade — void it.

Found 2026-08-08. Seventeen MLB picks had been sitting open for twelve days,
each carrying the instruction:

    ↳ CIN has a game on 2026-07-27 with no final score stored, so the repair
      cannot rule out that the bet is about THAT game.
      Ingest the finals: python3 ingest.py mlb --dates 2026-07-27 --refresh

That command cannot work, and the same tool says so four lines later
("MLB day coverage: nothing a re-ingest would fill"). Measured on the real
DB: 2026-07-27 held 12 MLB game rows, 11 with finals, and the twelfth was
CLE @ CIN — the game every one of those seventeen bets is on.

WHY IT CAN NEVER FILL. `parse_results` (engine/mlb/sources/mlbstats.py)
returns completed, SCORED games and nothing else: it skips anything whose
`abstractGameState` is not Final, anything whose `codedGameState` is C, D
or T — cancelled, postponed, suspended — and anything missing a score. It
cannot write a scoreless row. A scoreless row on a past date was written by
the schedule/odds side for a fixture that was then never played, and no
number of re-ingests will give it a score.

`db.coverage_gaps` already reaches this exact conclusion and flags those
days `repairable=False`. The stuck report simply never asked it. The guard
itself was right the whole time — it refuses to grade a bet whose own game
might still be out there — it was the REMEDY that was impossible.

A prop on a postponed game is no action at every book, so the settlement is
a void: zero P&L, and off the open list for good.

Run directly: `python3 tests/test_unplayed.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ledger                                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAST = (dt.date.today() - dt.timedelta(days=12)).isoformat()
PRIOR = (dt.date.today() - dt.timedelta(days=13)).isoformat()
TODAY = dt.date.today().isoformat()


def _bet(conn, date, player, market="home_runs", cat="longshot"):
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " stake_units, status, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (date, "mlb", date, player, market, "over", 0.5, 300, 0.25,
         "open", cat))
    conn.commit()


def _log(hconn, date, player, team, market="home_runs", value=0.0):
    db.upsert_player_logs(hconn, [{
        "sport": "mlb", "season": 2026, "period": date,
        "game_id": f"{team}@X", "player": player, "team": team,
        "opponent": "X", "position": "SS", "home": 1,
        "market": market, "value": value}])


def _world():
    """Ethan's 2026-07-27, in miniature: one unplayed game among scored ones,
    and the player logged on the PREVIOUS day (his last real game), which is
    what made the report call this "logged under the next day"."""
    hconn = db.connect(":memory:")
    lconn = ledger.connect(":memory:")
    db.upsert_games(hconn, [
        {"sport": "mlb", "season": 2026, "period": PAST, "game_id": "CLE@CIN",
         "home": "CIN", "away": "CLE", "home_score": None, "away_score": None},
        {"sport": "mlb", "season": 2026, "period": PAST, "game_id": "NYY@CWS",
         "home": "CWS", "away": "NYY", "home_score": 5, "away_score": 9},
    ])
    _log(hconn, PRIOR, "Elly De La Cruz", "CIN")
    return hconn, lconn


# --- finding them ------------------------------------------------------------
def test_a_bet_on_an_unplayed_game_is_found():
    hconn, lconn = _world()
    _bet(lconn, PAST, "Elly De La Cruz")
    got = ledger.unplayed_bets(lconn, hconn)
    assert len(got) == 1, got
    assert got[0]["team"] == "CIN"
    assert got[0]["finals"] == 0 and got[0]["games"] == 1


def test_a_bet_whose_team_played_is_left_alone():
    """The other eleven games that day were scored. Sweeping in a bet whose
    game finished would void a pick that should have been graded — the one
    outcome worse than leaving it open."""
    hconn, lconn = _world()
    _log(hconn, PAST, "Aaron Judge", "NYY", value=1.0)
    _bet(lconn, PAST, "Aaron Judge")
    got = ledger.unplayed_bets(lconn, hconn)
    assert [r["player"] for r in got] == [], got


def test_tonights_scoreless_game_is_not_a_postponement():
    """A game in progress has no score for an entirely ordinary reason.
    Without the past-date test this would void every live bet on the board
    the moment it ran."""
    hconn, lconn = _world()
    db.upsert_games(hconn, [
        {"sport": "mlb", "season": 2026, "period": TODAY, "game_id": "X@SEA",
         "home": "SEA", "away": "X", "home_score": None, "away_score": None}])
    _log(hconn, TODAY, "Julio Rodriguez", "SEA")
    _bet(lconn, TODAY, "Julio Rodriguez")
    got = ledger.unplayed_bets(lconn, hconn)
    assert [r["player"] for r in got] == [], got


def test_a_past_day_nobody_ingested_is_NOT_treated_as_unplayed():
    """The condition that keeps this rule honest, and the one the first cut
    got wrong.

    "Scoreless row on a past date" alone also describes a day nobody has
    fetched yet — where re-ingesting IS the fix and voiding would throw
    away a bet about to grade. The discriminator is that OTHER games that
    day carry finals, which proves the day was ingested and leaves no
    explanation for the holdout but a fixture that was never played.
    Ethan's 2026-07-27 had 11 of 12 scored; this day has 0 of 1.

    An existing test (test_stuck_bets: an unfinished game on the bet's own
    date) describes exactly this shape and still expects the ingest advice.
    It passed unchanged once the rule was tightened, which is what says the
    tightening was right rather than convenient.
    """
    hconn = db.connect(":memory:")
    lconn = ledger.connect(":memory:")
    db.upsert_games(hconn, [
        {"sport": "mlb", "season": 2026, "period": PAST, "game_id": "CLE@CIN",
         "home": "CIN", "away": "CLE", "home_score": None, "away_score": None}])
    _log(hconn, PRIOR, "Elly De La Cruz", "CIN")
    _bet(lconn, PAST, "Elly De La Cruz")
    assert ledger.unplayed_bets(lconn, hconn) == []


def test_the_clock_is_the_callers_not_the_wall():
    """`why_open` is handed a `today`; this has to use the same one or the
    two disagree about which days are over, and a test's answer changes
    with the date it is run on. The first cut called `date.today()`."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "Elly De La Cruz")
    assert ledger.unplayed_bets(lconn, hconn, today=PAST) == []
    assert len(ledger.unplayed_bets(lconn, hconn, today=TODAY)) == 1


def test_a_week_label_is_skipped_rather_than_crashing():
    """NFL journals under "2026-W1", which has no day to compare."""
    hconn, lconn = _world()
    _bet(lconn, "2026-W1", "Some Player")
    ledger.unplayed_bets(lconn, hconn)      # must not raise


def test_a_player_the_results_never_name_is_not_claimed():
    """No team means no way to know whose game was called off. Silence
    beats a guess that voids a live bet."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "Nobody At All")
    assert ledger.unplayed_bets(lconn, hconn) == []


def test_the_team_is_read_from_the_neighbouring_day():
    """The player has NO row on the bet's own date — that is the whole
    situation, his game was never played — so the team has to come from the
    day beside it or nothing is ever found."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "Elly De La Cruz")
    assert ledger.unplayed_bets(lconn, hconn)[0]["team"] == "CIN"


# --- writing -----------------------------------------------------------------
def test_voiding_settles_at_zero_and_only_the_named_bets():
    hconn, lconn = _world()
    _log(hconn, PAST, "Aaron Judge", "NYY", value=1.0)
    _bet(lconn, PAST, "Elly De La Cruz")
    _bet(lconn, PAST, "Aaron Judge")
    rows = ledger.unplayed_bets(lconn, hconn)
    assert ledger.void_unplayed(lconn, rows) == 1
    st = {r[0]: (r[1], r[2]) for r in lconn.execute(
        "SELECT player, status, pnl_units FROM bets")}
    assert st["Elly De La Cruz"] == ("void", 0)
    assert st["Aaron Judge"][0] == "open"


def test_the_count_is_rows_actually_written():
    """`conn.total_changes` is cumulative for the connection, so testing it
    per row counts every write the connection has ever made and reports a
    success for each. The first cut did exactly that."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "Elly De La Cruz")
    rows = ledger.unplayed_bets(lconn, hconn)
    assert ledger.void_unplayed(lconn, rows) == 1
    # Already void — a second pass writes nothing and must say so.
    assert ledger.void_unplayed(lconn, rows) == 0


def test_it_is_idempotent():
    hconn, lconn = _world()
    _bet(lconn, PAST, "Elly De La Cruz")
    ledger.void_unplayed(lconn, ledger.unplayed_bets(lconn, hconn))
    assert ledger.unplayed_bets(lconn, hconn) == []


def test_voiding_nothing_is_allowed():
    _, lconn = _world()
    assert ledger.void_unplayed(lconn, []) == 0


# --- the message that sent him nowhere ---------------------------------------
def test_the_repair_note_stops_prescribing_an_impossible_ingest():
    hconn, lconn = _world()
    row = list(hconn.execute(
        "SELECT * FROM player_game_logs WHERE period=?", (PRIOR,)))[0]
    b = {"sport": "mlb", "date": PAST, "player": "Elly De La Cruz",
         "market": "home_runs"}

    class _B(dict):
        def keys(self):
            return super().keys()

    assert ledger.never_resolving_game(hconn, _B(b), row) is True
    note = ledger._date_shift_repair_note(hconn, _B(b), PRIOR)
    assert "--refresh" not in note, note
    assert "never will" in note or "cannot fill" in note, note
    assert "void" in note.lower(), note


def test_a_game_still_to_be_ingested_keeps_the_ingest_advice():
    """The original message is RIGHT when the day genuinely has not been
    fetched yet. The fix must not throw that away — only stop using it for
    a fixture that was never played."""
    hconn, lconn = _world()
    db.upsert_games(hconn, [
        {"sport": "mlb", "season": 2026, "period": TODAY, "game_id": "X@CIN",
         "home": "CIN", "away": "X", "home_score": None, "away_score": None}])
    row = list(hconn.execute(
        "SELECT * FROM player_game_logs WHERE period=?", (PRIOR,)))[0]
    assert ledger.never_resolving_game(
        hconn, {"sport": "mlb", "date": TODAY}, row) is False


def test_the_measurement_is_written_where_it_will_be_read():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    i = src.index("def never_resolving_game")
    doc = src[i:i + 2200]
    assert "coverage_gaps" in doc
    assert "postponed" in doc


def test_the_cli_defaults_to_a_dry_run():
    """This writes a settlement the Record page and every learning rung
    read as fact. It must show the list before it writes."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--void-unplayed" in argv' in src
    i = src.index("def show_unplayed(")
    block = src[i:i + 2400]
    assert "apply: bool = False" in block
    assert "Nothing was written" in block
    assert "--apply" in block


# --- game-level bets, which had no team at all -------------------------------
def test_a_moneyline_on_an_unplayed_game_is_found():
    """THE DOCTOR'S "game not found" BUCKET, and why it never cleared.

    `_bet_team` resolves a team by looking the bet's `player` up in
    `player_game_logs`, which is right for a prop and cannot work for a
    game bet: `player` there is not a person. Moneyline, spread and
    team_total store the TEAM in that column. So the lookup returned None,
    `unplayed_bets` skipped the row, and a moneyline on a postponed
    fixture could not be voided by the tool built to void bets on
    postponed fixtures.

    Six were open on 2026-08-09 carrying `--settle all` as the advice.
    Settling can never help: the game was not played, so no re-ingest will
    produce the score the settler waits for."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "CIN", market="moneyline", cat="main")
    got = ledger.unplayed_bets(lconn, hconn)
    assert len(got) == 1, got
    assert got[0]["team"] == "CIN"
    assert got[0]["market"] == "moneyline"


def test_a_total_is_found_through_its_matchup_key():
    """`total` stores the matchup key `AWAY@HOME`, not a team. Either half
    is enough — `never_resolving_game` asks whether that team has a
    scoreless row on that date, and both halves of a postponed game do."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "CLE@CIN", market="total", cat="main")
    got = ledger.unplayed_bets(lconn, hconn)
    assert len(got) == 1, got
    assert got[0]["team"] == "CIN"


def test_a_doubleheader_suffix_is_not_read_as_part_of_the_team_name():
    """`CLE@CIN-G2` is one game, not a team called `CIN-G2`."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "CLE@CIN-G2", market="total", cat="main")
    assert len(ledger.unplayed_bets(lconn, hconn)) == 1


def test_a_game_bet_whose_game_was_played_is_left_alone():
    """The narrowness is the safety. A team with a FINAL on its date is
    not an unplayed fixture, and voiding it would erase a real result."""
    hconn, lconn = _world()
    _bet(lconn, PAST, "CWS", market="moneyline", cat="main")
    assert ledger.unplayed_bets(lconn, hconn) == []


def test_a_game_bet_is_voided_with_zero_pnl_like_any_other():
    hconn, lconn = _world()
    _bet(lconn, PAST, "CIN", market="spread", cat="main")
    rows = ledger.unplayed_bets(lconn, hconn)
    assert ledger.void_unplayed(lconn, rows) == 1
    r = lconn.execute("SELECT status, pnl_units FROM bets").fetchone()
    assert r[0] == "void" and (r[1] or 0) == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
