"""The fatigue dimension was computed on every NFL pick and then thrown away.

`python3 doctor.py` reports it in one line:

    always-NULL: rest_days, body_clock — those pipelines are not journaling
    their dimension, so the miner can never convict on it

Two of nine mineable dimensions, permanently empty. The cause was not a
missing calculation. `betting.py` has derived both since the fatigue work
shipped — it hands them straight to `lp_veto` so a convicted short-week
pocket can refuse a matching pick — but nothing ever put them on the
RECORD, so `ledger.log_recommendations`' `r.get("rest_days")` wrote NULL
every time.

That made the rung a closed loop with no input: the miner could REFUSE a
pick on a fatigue pattern and could never CONVICT one, because no settled
bet carried the dimension to learn from. It was applying rules it had no
way to discover.

TWO WRITERS, AND ONLY ONE HAD THE COLUMNS. The prop insert already read
`rest_days`/`body_clock`; the game-bet insert carried no dimension columns
at all. Moneylines, spreads and team totals are exactly where a short week
is most often the story, so half the NFL journal stayed invisible even once
the props started reporting.

DERIVED IN THE PIPELINE, NOT PASSED DOWN FROM THE VETO. A dimension that
only gets journaled when a gate happens to fire is a biased sample of
precisely the thing being measured.

Run directly: `python3 tests/test_fatigue_journaled.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, pipeline                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLATE = os.path.join(ROOT, "data", "sample_slate.json")


def _run():
    return pipeline.run_slate(SLATE)


def _journal(res):
    conn = ledger.connect(":memory:")
    ledger.log_recommendations(conn, res, only_recommended=False)
    return conn


# --- the record carries it ---------------------------------------------------
def test_every_prop_record_has_the_fields():
    """Present on every record, not only where a value exists — a missing
    KEY and a null VALUE are different facts, and only one of them means
    "this spot had no rest data"."""
    recs = _run().get("recommendations") or []
    assert recs
    for r in recs:
        assert "rest_days" in r, r.get("player")
        assert "body_clock" in r, r.get("player")


def test_a_prop_carries_a_real_body_clock():
    recs = _run().get("recommendations") or []
    got = [r for r in recs if r.get("body_clock") is not None]
    assert got, "no prop carries a body clock"


def test_a_sided_game_bet_carries_fatigue():
    """Moneylines, spreads and team totals are about ONE team, so the
    dimension has an unambiguous subject."""
    gb = _run().get("game_bets") or []
    sided = [b for b in gb if (b.get("team") or "").strip()]
    assert sided
    assert all("rest_days" in b and "body_clock" in b for b in sided)
    assert any(b.get("body_clock") is not None for b in sided)


def test_a_game_total_carries_none_because_it_has_no_subject():
    """THE ONE THAT KEEPS THE COLUMN HONEST. A game total is about both
    teams and belongs to neither. Filling it with the home side's rest puts
    two different meanings in one column, and a dimension that means
    different things in different rows is worse than one that is absent —
    the miner would convict on a pocket that does not exist."""
    gb = _run().get("game_bets") or []
    totals = [b for b in gb if b.get("market") == "total"]
    assert totals, "no game totals in the sample slate"
    for b in totals:
        assert b.get("rest_days") is None, b
        assert b.get("body_clock") is None, b


# --- both writers put it in the table ----------------------------------------
def test_a_journaled_prop_stores_the_dimension():
    conn = _journal(_run())
    rows = list(conn.execute(
        "SELECT COUNT(*) FROM bets WHERE market NOT IN "
        "('moneyline','spread','team_total','total') AND body_clock IS NOT NULL"))
    assert rows[0][0] > 0, "props journal no body_clock"


def test_a_journaled_game_bet_stores_the_dimension():
    """The writer that had no dimension columns at all."""
    conn = _journal(_run())
    rows = list(conn.execute(
        "SELECT COUNT(*) FROM bets WHERE market IN "
        "('moneyline','spread','team_total') AND body_clock IS NOT NULL"))
    assert rows[0][0] > 0, "game bets journal no body_clock"


def test_the_game_bet_insert_names_the_columns():
    """A positional INSERT that silently drops the last two values would
    pass the count test above only by accident."""
    import inspect
    src = inspect.getsource(ledger.log_recommendations)
    i = src.index('for r in result.get("game_bets"')
    block = src[i:]
    assert "rest_days, body_clock" in block
    assert 'r.get("rest_days"), r.get("body_clock")' in block


# --- where it is derived -----------------------------------------------------
def test_it_is_derived_in_the_pipeline_not_taken_from_the_veto():
    """`betting.py` computes these for `lp_veto`. Reusing that value would
    tie journaling to whether a gate fired, which biases the sample toward
    the spots the gate looks at."""
    import inspect
    src = inspect.getsource(pipeline)
    assert src.count("from .fatigue import state_for") >= 2, \
        "the pipeline no longer derives fatigue for both record kinds"


def test_a_fatigue_failure_cannot_cost_the_pick():
    """The dimension going missing is recoverable; a lost board is not."""
    import inspect
    src = inspect.getsource(pipeline)
    i = src.index("from .fatigue import state_for")
    assert "except Exception" in src[i:i + 500]


def test_real_schedule_rows_actually_populate_rest_days():
    """The sample slate carries 0/0 rest, which `state_for` reports as None
    — so the sample alone cannot tell "wired up" from "still broken".
    nflverse ships rest precomputed; this checks against it."""
    if not os.path.exists(os.path.join(ROOT, "data", "cache", "games.csv")):
        return
    from engine.fatigue import state_for
    from engine.sources.nflverse import build_games
    games = build_games(2026, 1)
    if not games:
        return
    got = [state_for(g, g.away).get("rest_days") for g in games]
    assert any(v is not None for v in got), got


def test_the_measurement_is_written_where_it_will_be_read():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"),
               encoding="utf-8").read()
    i = src.index("THESE WERE COMPUTED AND THROWN AWAY")
    assert "always-NULL" in src[i:i + 900]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
