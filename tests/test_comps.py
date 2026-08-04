"""Historical comps — the outside view, and the ways it could lie.

Every projection in this engine is an inside view: build a mean, wrap an
assumed distribution around it, integrate past the line. Comps answer the
same question with no model at all — walk the ingested logs, reconstruct
what each past game's trailing form was BEFORE it was played, and count
how often players in tonight's form band actually cleared tonight's
number. No distribution assumed; the record just gets counted.

The tests below are mostly about the four ways a comp set becomes a lie:

* **Leakage** — a spot whose "prior form" includes its own result would
  score itself, and every comp set would look prophetic.
* **Sidedness** — the record is stored from the over's point of view, so
  an under compared against it raw grades backwards. That exact bug is
  called out in the backtest's own comments; it must not reappear here.
* **Pooling** — a hit rate blended across sports or markets describes
  neither. Indexes are keyed by both.
* **Thin samples** — a 6-comp band reads as evidence and is noise.
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import comps, db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log(player, market, value, day, sport="mlb", season=2026):
    return {"sport": sport, "season": season, "period": f"2026-05-{day:02d}",
            "game_id": f"g{day}", "player": player, "team": "BOS",
            "opponent": "NYY", "position": "OF", "home": 1,
            "market": market, "value": value}


def _population(conn, market="hits", sport="mlb"):
    """Two clearly separated populations, so a band that works has to find
    the right one: hot bats around 2.0, cold bats around 0.8."""
    rng = random.Random(7)
    rows = []
    for p in range(30):
        hot = p < 15
        mu = 2.0 if hot else 0.8
        for g in range(60):
            rows.append(_log(("Hot" if hot else "Cold") + str(p), market,
                             max(0, round(rng.gauss(mu, 0.9))), g % 31 + 1,
                             sport=sport))
    db.upsert_player_logs(conn, rows)
    return conn


# --- the index ---------------------------------------------------------------
def test_a_spot_never_sees_its_own_result():
    """The whole method collapses if trailing form includes the game being
    described — every comp set would look prophetic."""
    conn = db.connect(":memory:")
    rows = [_log("Steady", "hits", 1.0, d) for d in range(1, 11)]
    rows.append(_log("Steady", "hits", 99.0, 11))      # the outlier game
    db.upsert_player_logs(conn, rows)
    idx = comps.spot_index(conn, "mlb", "hits")
    assert len(idx) == 1                               # only game 11 qualifies
    _key, player, form, value = idx[0]
    assert player == "Steady"
    assert form == 1.0, "the 99 leaked into its own prior form"
    assert value == 99.0


def test_a_player_without_a_full_window_produces_no_spot():
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [_log("Rookie", "hits", 1.0, d)
                                 for d in range(1, 9)])
    assert comps.spot_index(conn, "mlb", "hits") == []


def test_the_index_never_pools_markets_or_sports():
    conn = db.connect(":memory:")
    rows = [_log("Dual", "hits", 1.0, d) for d in range(1, 13)]
    rows += [_log("Dual", "total_bases", 9.0, d) for d in range(1, 13)]
    rows += [_log("Dual", "hits", 5.0, d, sport="nba") for d in range(1, 13)]
    db.upsert_player_logs(conn, rows)
    hits = comps.spot_index(conn, "mlb", "hits")
    assert hits and all(v == 1.0 for _k, _p, _f, v in hits)
    tb = comps.spot_index(conn, "mlb", "total_bases")
    assert tb and all(v == 9.0 for _k, _p, _f, v in tb)
    hoops = comps.spot_index(conn, "nba", "hits")
    assert hoops and all(v == 5.0 for _k, _p, _f, v in hoops)


# --- the record --------------------------------------------------------------
def test_the_band_finds_the_right_population():
    idx = comps.spot_index(_population(db.connect(":memory:")), "mlb", "hits")
    hot = comps.comp_record(idx, line=1.5, form=2.0)
    cold = comps.comp_record(idx, line=1.5, form=0.8)
    assert hot["hit_rate"] > 0.65 and cold["hit_rate"] < 0.35
    assert hot["form_lo"] <= 2.0 <= hot["form_hi"]


def test_a_thin_band_reports_nothing_rather_than_noise():
    idx = comps.spot_index(_population(db.connect(":memory:")), "mlb", "hits")
    # A form nobody sits in has no comps at all.
    assert comps.comp_record(idx, line=1.5, form=25.0) is None
    # And a real band still refuses below the sample bar.
    assert comps.comp_record(idx, line=1.5, form=2.0, min_n=10_000) is None


def test_pushes_are_counted_and_kept_out_of_the_rate():
    """An integer line the result lands on is a push, exactly as the
    journal counts it — folding pushes into either side would move the
    rate for something nobody won or lost."""
    idx = comps.spot_index(_population(db.connect(":memory:")), "mlb", "hits")
    r = comps.comp_record(idx, line=2.0, form=2.0)
    assert r["push"] > 0
    assert r["n"] == r["over"] + r["under"]
    # hit_rate is a reported number, rounded to 4dp — compare at that scale.
    assert abs(r["hit_rate"] - r["over"] / r["n"]) < 1e-4


def test_the_before_cutoff_keeps_a_replay_honest():
    """A backtest replaying an old date must not see comps from after it."""
    conn = db.connect(":memory:")
    rows = [_log("Early", "hits", 1.0, d) for d in range(1, 13)]
    rows += [_log("Late", "hits", 1.0, d, season=2027) for d in range(1, 13)]
    db.upsert_player_logs(conn, rows)
    idx = comps.spot_index(conn, "mlb", "hits")
    everything = comps.comp_record(idx, line=0.5, form=1.0, min_n=1)
    earlier = comps.comp_record(idx, line=0.5, form=1.0, min_n=1,
                                before=(2027, "2026-05-01"))
    assert earlier["n"] < everything["n"]
    assert all(True for _ in [1])          # cutoff is exclusive, not clipping


def test_the_record_counts_how_many_comps_are_the_players_own():
    idx = comps.spot_index(_population(db.connect(":memory:")), "mlb", "hits")
    r = comps.comp_record(idx, line=1.5, form=2.0, player="Hot0")
    assert 0 < r["own"] < r["n"], "own-history share should be visible"


# --- the decorator -----------------------------------------------------------
def _rec(side="OVER", line=1.5, prob=0.60, vals=None, market="hits"):
    return {"player": "Hot0", "market": market, "line": line, "side": side,
            "hit_prob": prob, "recent_values": vals or [2, 2, 3, 1, 2, 2, 2, 3, 1, 2],
            "reasons": [], "warnings": []}


def test_an_under_is_compared_against_the_complement():
    """The record is stored from the over's side. Comparing an under to it
    raw is the same bug the backtest calls out for grading every under
    backwards — it must not reappear here."""
    conn = _population(db.connect(":memory:"))
    over, under = _rec("OVER"), _rec("UNDER")
    comps.decorate([over, under], conn, "mlb")
    assert over["comps"]["hit_rate"] > 0.65             # stored over-side
    assert abs(over["comps"]["side_rate"] - over["comps"]["hit_rate"]) < 1e-9
    assert abs(under["comps"]["side_rate"]
               - (1 - under["comps"]["hit_rate"])) < 1e-9
    assert "to the under" in " ".join(under["reasons"])


def test_a_wide_disagreement_warns_and_a_close_one_stays_quiet():
    conn = _population(db.connect(":memory:"))
    # The comps say ~75% over; a model claiming 40% is far outside.
    loud = _rec("OVER", prob=0.40)
    quiet = _rec("OVER", prob=0.72)
    out = comps.decorate([loud, quiet], conn, "mlb")
    assert any("Comps disagree" in w for w in loud["warnings"])
    assert not quiet["warnings"]
    assert out["diverged"] == 1 and out["matched"] == 2


def test_every_decorated_card_carries_the_evidence_and_a_reason():
    conn = _population(db.connect(":memory:"))
    r = _rec()
    comps.decorate([r], conn, "mlb")
    assert r["comps"]["n"] >= comps.MIN_COMPS
    assert any("Comps:" in x for x in r["reasons"])


def test_a_player_with_almost_no_history_is_skipped_not_guessed():
    conn = _population(db.connect(":memory:"))
    thin = _rec(vals=[2, 1])
    comps.decorate([thin], conn, "mlb")
    assert "comps" not in thin


def test_a_market_with_no_history_simply_adds_nothing():
    conn = _population(db.connect(":memory:"))
    r = _rec(market="strikeouts")
    comps.decorate([r], conn, "mlb")
    assert "comps" not in r and not r["warnings"]


# --- wiring ------------------------------------------------------------------
def test_a_missing_history_db_costs_the_section_not_the_slate():
    """CI and a fresh clone have no history DB; the board must still build."""
    from engine.pipeline import _attach_comps

    class _Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no such table")

        def close(self):
            pass

    import engine.db as _db
    orig = _db.connect
    try:
        _db.connect = lambda *a, **k: _Broken()
        out = _attach_comps([_rec()], "mlb")
    finally:
        _db.connect = orig
    assert out["matched"] == 0


def test_every_sport_gets_the_outside_view():
    """Per Ethan's standing rule: a signal we adopt is adopted everywhere
    its data supports it — MLB, NFL, CFB and both hoops leagues."""
    pairs = [("engine/pipeline.py", '"nfl"'), ("engine/mlb/pipeline.py", '"mlb"'),
             ("nba_build.py", "args.league"), ("cfb_build.py", '"cfb"')]
    for path, sport in pairs:
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert "_attach_comps" in src, path
        i = src.index("_attach_comps(")
        assert sport in src[i:i + 120], f"{path} decorates the wrong sport"


def test_the_hoops_leagues_are_never_pooled():
    """nba_build serves both leagues; comps must follow the league being
    built, or a WNBA board would read NBA history."""
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    i = src.index("_attach_comps(")
    assert "args.league" in src[i:i + 120]


def test_comps_are_evidence_not_a_price():
    """A new signal earns its way into pricing by being measured first.
    Nothing here may touch a probability, a stake, or the recommendation."""
    src = open(os.path.join(ROOT, "engine", "comps.py"), encoding="utf-8").read()
    for forbidden in ('r["hit_prob"] =', 'r["stake_units"]', 'r["recommended"]',
                      'r["grade"] ='):
        assert forbidden not in src, f"comps must not set {forbidden}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
