"""Where does a board lose its props? Print the counts, stop guessing.

I told Ethan the WNBA board was empty because the league had never been
ingested. Then he ran the ingest and the database said otherwise: 1,581
games and 151,765 player-log rows across 2021-2026, already there before he
started. The diagnosis was wrong, and it was wrong in a way I could not
have checked from here — the answer lives in his database.

Every prop on these boards comes from one narrow query: this sport, these
teams (tonight's), these seasons. Any one of the three failing gives the
identical symptom — a slate with games on it and nothing to bet — and from
the outside, and from the terminal, the three were indistinguishable.

So `python3 nba_build.py <date> --league wnba --diagnose` prints what
survives each filter. The line that drops to zero is the answer, and it is
a different answer each time:

  * no logs at all               -> run the ingest
  * logs, none in these seasons  -> the ingest and the query disagree about
                                    which year a game belongs to
  * logs, team codes don't match -> the schedule feed and the ingest name
                                    the same clubs differently; re-running
                                    the ingest cannot help
  * everything matches           -> the props exist and are being FILTERED,
                                    which is the gate census's business

Those four need four different responses, and three of them are not "run
the ingest again".
"""

import datetime
import io
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util

from engine import db

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "nba_build_mod", os.path.join(_ROOT, "nba_build.py"))
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

GAMES = [{"home": "LV", "away": "NY", "kickoff": ""},
         {"home": "SEA", "away": "MIN", "kickoff": ""}]


def _logs(teams, season, players=4, games=5):
    out = []
    for t in teams:
        for pi in range(players):
            for gi in range(games):
                d = (datetime.date(2026, 7, 1)
                     + datetime.timedelta(days=gi)).isoformat()
                for m, v in (("min", 28.0), ("pts", 15.0), ("reb", 6.0),
                             ("ast", 4.0), ("fg3m", 1.0)):
                    out.append({"sport": "wnba", "season": season, "period": d,
                                "game_id": f"g{gi}", "player": f"{t} P{pi}",
                                "team": t, "opponent": "XX", "position": "S",
                                "home": 1, "market": m, "value": v})
    return out


def _run(rows, games=GAMES):
    """Run the diagnosis against a synthetic DB and stubbed schedule."""
    import engine.sources.wnbaespn as we
    old_fetch, old_parse, old_conn = (we.fetch_schedule, we.parse_schedule_day,
                                      nb.connect)
    conn = db.connect(":memory:")
    if rows:
        db.upsert_player_logs(conn, rows)
    we.fetch_schedule = lambda ttl=0: {}
    we.parse_schedule_day = lambda s, d: games
    nb.connect = lambda *a, **k: conn
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            nb.diagnose("wnba", "2026-08-01")
    finally:
        we.fetch_schedule, we.parse_schedule_day = old_fetch, old_parse
        nb.connect = old_conn
    return buf.getvalue()


# --- the four different answers ---------------------------------------------
def test_no_logs_at_all_names_the_ingest():
    out = _run([])
    assert "No player logs at all" in out
    assert "python3 ingest.py wnba --seasons 2021-2026" in out


def test_logs_in_the_wrong_season_are_not_reported_as_missing_logs():
    """"Run the ingest" is the wrong advice here — the rows are already
    there, under a year this board does not read."""
    out = _run(_logs(["LV", "NY", "SEA", "MIN"], 2019))
    assert "400 row(s)" in out
    assert "NONE in the seasons this board reads" in out
    assert "No player logs at all" not in out


def test_a_team_code_mismatch_says_re_running_will_not_help():
    """The costliest wrong answer available: a two-hour ingest that changes
    nothing, because the schedule says LV and the logs say LVA."""
    out = _run(_logs(["LVA", "NYL", "SEA", "MIN"], 2026))
    assert "No logs under: LV, NY" in out
    assert "code fix, not an ingest" in out
    assert "nothing you re-run will help" in out


def test_a_partial_match_does_not_also_claim_the_history_is_fine():
    """A report that contradicts itself three lines later is worse than no
    report. My first version printed the ✗ and then the ✓."""
    out = _run(_logs(["LVA", "NYL", "SEA", "MIN"], 2026))
    assert "The history is fine" not in out
    assert "will be missing every player on LV, NY" in out


def test_everything_matching_points_at_the_gates_instead():
    out = _run(_logs(["LV", "NY", "SEA", "MIN"], 2026))
    assert "4 of 4" in out
    assert "The history is fine" in out
    assert "being built and then filtered" in out
    assert "Props buildable" in out


def test_players_present_but_too_new_is_its_own_answer():
    """Two games into a season nobody is projectable yet, and that is not a
    data gap — it is a date."""
    out = _run(_logs(["LV", "NY", "SEA", "MIN"], 2026, games=2))
    assert "none has three games" in out


def test_an_empty_schedule_is_not_reported_as_a_fault():
    out = _run(_logs(["LV", "NY"], 2026), games=[])
    assert "nothing scheduled, so no props is correct" in out


def test_the_counts_are_reported_per_season_not_just_in_total():
    """A single total hides exactly the case that bit us — rows present,
    none of them recent."""
    rows = _logs(["LV", "NY"], 2024) + _logs(["LV", "NY"], 2026)
    out = _run(rows)
    assert "2024:" in out and "2026:" in out


def test_it_is_reachable_from_the_command_line():
    src = open(os.path.join(_ROOT, "nba_build.py"), encoding="utf-8").read()
    assert '"--diagnose"' in src
    assert "diagnose(args.league, args.date)" in src
    # And it must exit before the build: the point is to answer a question
    # in seconds, not to run a slate first.
    i = src.index("diagnose(args.league, args.date)")
    assert "return" in src[i:i + 60]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
