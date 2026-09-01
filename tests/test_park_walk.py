"""The context-aware walk — history replayed in its real ballparks.

The finding this closes: the rank store's AUCs did not move after the
MLB handicapping script landed, because the walk replays every
historical game in a NEUTRAL stadium — the venue layer was invisible to
the measurement. The logs already record team, opponent, and home for
every game, park factors are static (nothing the walk sees postdates
the game it predicts), and `parks.park_of_game` has known how to name
the venue since it was written. This wires the three together and adds
`rankfit.context_report` — the A/B that prints neutral vs in-park AUC
per market and WRITES NOTHING: adoption is a decision for whoever reads
the deltas, never a side effect of measuring them.

Run directly: `python3 tests/test_park_walk.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, rankfit


# --- the entries carry where each game happened -----------------------------
def test_entries_carry_team_opponent_and_home_per_game():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    rows = []
    for i in range(10):
        rows.append({"sport": "mlb", "season": 2026,
                     "period": f"2026-06-{i + 1:02d}", "game_id": f"g{i}",
                     "player": "A Hitter", "team": "NYY",
                     "opponent": "BOS", "position": "RF",
                     "home": i % 2, "market": "hits", "value": float(i % 3)})
    db.upsert_player_logs(conn, rows)
    got = db.entries_for_market(conn, "mlb", "hits", min_games=8)
    assert len(got) == 1
    e = got[0]
    assert len(e["teams"]) == len(e["values"]) == 10
    assert e["teams"][0] == "NYY" and e["opps"][0] == "BOS"
    assert e["homes"][:2] == [0, 1]
    conn.close()


# --- the context names the right park ---------------------------------------
def test_home_games_use_the_players_park_and_road_games_the_opponents():
    gfi = rankfit._park_context()
    e = {"teams": ["NYY", "NYY"], "opps": ["BOS", "BOS"], "homes": [1, 0]}
    assert gfi(e, 0).park == "yankee"
    assert gfi(e, 1).park == "fenway"
    assert gfi({"teams": [], "opps": [], "homes": []}, 0).park == "generic"


# --- the walk actually prices the venue -------------------------------------
def test_the_park_reaches_the_walked_probability():
    """Same hitter, same history, same line — Coors vs the neutral
    stadium must produce different home-run probabilities, or the
    context walk is a label with nothing under it."""
    from engine.mlb.backtest import settled_props_from_logs
    from engine.mlb.models import MLBGame

    entry = [{"name": "T Slugger", "spot": 3,
              "values": [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0],
              "dates": [f"2026-06-{d:02d}" for d in range(1, 11)]}]
    neutral, _ = settled_props_from_logs(entry, "home_runs", min_history=8)
    coors, _ = settled_props_from_logs(
        entry, "home_runs", min_history=8,
        game_for_index=lambda e, i: MLBGame(home="COL", away="X",
                                            park="coors"))
    assert len(neutral) == len(coors) == 2
    for n, c in zip(neutral, coors):
        assert c.hit_prob > n.hit_prob, (n.hit_prob, c.hit_prob)


# --- the A/B report ---------------------------------------------------------
def _fake_walk_pair(base_pairs, ctx_pairs):
    from engine import db as _db, logwalk

    class _Rep:
        def __init__(self, pairs):
            self.pairs = pairs

    saved = (_db.entries_for_market, logwalk.walk)
    _db.entries_for_market = lambda conn, sport, market, **kw: [{"name": "x"}]

    def fake_walk(sport, entries, market, **hooks):
        return _Rep(ctx_pairs if hooks.get("game_for_index") else base_pairs)
    logwalk.walk = fake_walk
    return saved


def _pairs(target, n_pos=1000, n_neg=2000):
    """Exact-AUC fixture: the fraction ``target`` of positives sit above
    every negative and the rest below, so AUC == target by construction."""
    k = int(round(target * n_pos))
    return ([(0.3, 0)] * n_neg
            + [(0.6, 1)] * k + [(0.1, 1)] * (n_pos - k))


def test_the_report_prints_both_aucs_and_a_verdict_and_writes_nothing():
    import json
    from engine import db as _db, logwalk
    saved = _fake_walk_pair(_pairs(0.62), _pairs(0.66))
    try:
        lines = rankfit.context_report(None, "mlb", markets=("hits",),
                                       log=lambda *_: None)
    finally:
        _db.entries_for_market, logwalk.walk = saved
    assert len(lines) == 1
    ln = lines[0]
    assert "neutral" in ln and "in-park" in ln
    assert "RANKS BETTER" in ln, ln
    assert not os.path.exists(rankfit.STORE), \
        "the A/B must never write the store — adoption is a decision"


def test_a_worse_context_says_so_and_thin_samples_refuse():
    from engine import db as _db, logwalk
    saved = _fake_walk_pair(_pairs(0.66), _pairs(0.60))
    try:
        lines = rankfit.context_report(None, "mlb", markets=("hits",),
                                       log=lambda *_: None)
    finally:
        _db.entries_for_market, logwalk.walk = saved
    assert "ranks worse" in lines[0]
    saved = _fake_walk_pair(_pairs(0.62, n_pos=80, n_neg=120),
                            _pairs(0.66, n_pos=80, n_neg=120))
    try:
        lines = rankfit.context_report(None, "mlb", markets=("hits",),
                                       log=lambda *_: None)
    finally:
        _db.entries_for_market, logwalk.walk = saved
    assert "too thin" in lines[0]


def test_other_sports_are_told_no_rather_than_walked_wrong():
    lines = rankfit.context_report(None, "nfl", log=lambda *_: None)
    assert "no venue-aware walk" in lines[0]


def test_the_weekly_maintenance_answers_the_ab_by_itself():
    """The one-liner that runs this report was never pasted on the
    droplet, so the park question sat unanswered for a day. The weekly
    pass now prints it beside the rank fits — measured where the logs
    are, with nobody needing to remember a command."""
    src = open(os.path.join(ROOT, "engine", "maintenance.py"),
               encoding="utf-8").read()
    assert "context_report as _rank_ctx" in src
    assert '_rank_ctx(_rkc, "mlb", log=log)' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
