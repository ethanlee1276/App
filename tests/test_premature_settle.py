"""A bet must not grade while its game is still being played.

"i can confirm that carter jensen prop has not won yet and is still open"

The journal said `won`. The game was in progress. The settler had graded
against a PARTIAL stat line — one total base in the fourth inning, stored
in the history DB as though the day were done.

There is a guard against exactly this, in mlb_rows_from_slate, and it is
well commented: same-date log rows are withheld for teams whose game is not
final, because "one ingested partial row is enough for the settler to grade
tonight's bet mid-game (the premature 'lost' bug)".

It had never fired. Not once.

It reads ``g.live``, which is populated by ``attach_live`` — called only by
mlb_build.py, never by the ingest. So in the ingest ``g.live`` was always
None, the state string was always "", the `if st and st != "final"` was
always False, and teams_in_play was always empty. Every partial line from
every game in progress went into the history DB.

For an OVER already past its line this only looks wrong: it grades early
and correctly. For an UNDER it is money. A hitter sitting on 0 total bases
in the fourth grades the under as WON, and then he doubles.

Two fixes. The state is read from the schedule the builder already fetched
(build_live_slate reads abstractGameState and was throwing it away) rather
than from a field nobody fills. And on TODAY's slate the default flips:
unknown state means in play. Absence of evidence that a game is over is not
evidence that it is over.
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ingest import mlb_rows_from_slate, _game_state
from engine.mlb.data_loader import MLBSlate
from engine.mlb.models import MLBGame, MLBGameLog, MLBProp, TOTAL_BASES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = _dt.date.today().isoformat()
PAST = "2026-06-20"


def _slate(date, state, team="KC"):
    g = MLBGame(home=team, away="DET", park="kauffman", date=date)
    g.sched_state = state
    p = MLBProp(player="Carter Jensen", team=team, opponent="DET",
                position="C", market=TOTAL_BASES,
                logs=[MLBGameLog(game=1, opponent="DET", value=1.0, date=date)],
                career_avg=1.0, vs_pitcher_avg=None, lines=[])
    return MLBSlate(date=date, games=[g], props=[p])


def _same_day_rows(date, state):
    _g, prows = mlb_rows_from_slate(_slate(date, state), date)
    return [r for r in prows if r["period"] == date]


# --- the bug ----------------------------------------------------------------
def test_a_game_in_progress_does_not_store_a_partial_line():
    assert _same_day_rows(TODAY, "live") == []


def test_an_unknown_state_on_todays_slate_is_treated_as_in_play():
    """The actual defect. The old rule required a POSITIVE "not final" to
    withhold, so a game whose state nobody filled in — which was every game
    in the ingest — sailed through."""
    assert _same_day_rows(TODAY, "") == []


def test_a_finished_game_today_still_stores_its_line():
    """The control. Without it the two tests above are satisfied by an
    ingest that stores nothing at all."""
    assert len(_same_day_rows(TODAY, "final")) == 1


def test_a_past_date_with_no_state_still_backfills():
    """Those games are over by definition. Being strict here would withhold
    every row of an ordinary `ingest.py mlb --seasons 2024`."""
    assert len(_same_day_rows(PAST, "")) == 1


def test_older_games_are_never_withheld_even_on_a_live_slate():
    """Only the SAME date is at risk; a player's previous games are done."""
    g = MLBGame(home="KC", away="DET", park="kauffman", date=TODAY)
    g.sched_state = "live"
    p = MLBProp(player="Carter Jensen", team="KC", opponent="DET",
                position="C", market=TOTAL_BASES,
                logs=[MLBGameLog(game=2, opponent="MIN", value=2.0,
                                 date="2026-07-30"),
                      MLBGameLog(game=1, opponent="DET", value=1.0,
                                 date=TODAY)],
                career_avg=1.5, vs_pitcher_avg=None, lines=[])
    _g, prows = mlb_rows_from_slate(MLBSlate(date=TODAY, games=[g], props=[p]),
                                    TODAY)
    assert [r["period"] for r in prows] == ["2026-07-30"]


def test_only_the_playing_teams_are_withheld():
    """One live game must not stop the night's finished games storing."""
    live_g = MLBGame(home="KC", away="DET", park="kauffman", date=TODAY)
    live_g.sched_state = "live"
    done_g = MLBGame(home="PHI", away="CHC", park="citizens", date=TODAY)
    done_g.sched_state = "final"
    props = [
        MLBProp(player="Carter Jensen", team="KC", opponent="DET",
                position="C", market=TOTAL_BASES,
                logs=[MLBGameLog(game=1, opponent="DET", value=1.0,
                                 date=TODAY)],
                career_avg=1.0, vs_pitcher_avg=None, lines=[]),
        MLBProp(player="Bryce Harper", team="PHI", opponent="CHC",
                position="RF", market=TOTAL_BASES,
                logs=[MLBGameLog(game=1, opponent="CHC", value=3.0,
                                 date=TODAY)],
                career_avg=2.0, vs_pitcher_avg=None, lines=[]),
    ]
    _g, prows = mlb_rows_from_slate(
        MLBSlate(date=TODAY, games=[live_g, done_g], props=props), TODAY)
    stored = {r["player"] for r in prows if r["period"] == TODAY}
    assert stored == {"Bryce Harper"}


# --- the state lookup itself ------------------------------------------------
def test_the_live_overlay_still_wins_when_the_site_build_supplied_it():
    class _L:
        state = "live"
    g = MLBGame(home="KC", away="DET", park="kauffman")
    g.sched_state = "final"          # schedule is stale
    g.live = _L()
    assert _game_state(g) == "live"


def test_the_schedule_state_is_used_when_there_is_no_live_overlay():
    g = MLBGame(home="KC", away="DET", park="kauffman")
    g.sched_state = "final"
    assert _game_state(g) == "final"


def test_a_game_with_neither_reports_unknown_not_final():
    """Returning "final" here would re-create the bug in one line."""
    g = MLBGame(home="KC", away="DET", park="kauffman")
    assert _game_state(g) == ""


# --- the builder has to actually stamp it -----------------------------------
def test_the_builder_stamps_the_state_it_already_reads():
    src = open(os.path.join(ROOT, "engine", "mlb", "sources", "statslogs.py"),
               encoding="utf-8").read()
    assert "game.sched_state = str(" in src
    assert "abstractGameState" in src


def test_the_field_is_declared_rather_than_bolted_on():
    from dataclasses import fields
    assert "sched_state" in {f.name for f in fields(MLBGame)}


def test_the_guard_no_longer_depends_on_a_field_the_ingest_never_fills():
    src = open(os.path.join(ROOT, "engine", "ingest.py"), encoding="utf-8").read()
    i = src.index("teams_in_play = set()")
    block = src[i:i + 400]
    assert "_game_state(g)" in block
    assert 'getattr(g.live, "state", "")' not in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
