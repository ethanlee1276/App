"""A Most Likely board for every sport — earned per market, per box.

Ethan, 2026-08-31: "We should have a most likely page for every sport…
We should dive deeper into getting the most likely page for MLB set up."

The founding rule survives the expansion: a market appears on the
likelihood board only after it has been SHOWN to rank. The NFL's numbers
were hand-measured constants; that cannot scale (the MLB logs never
leave the droplet, so this dev box literally cannot measure them). So
`engine.rankfit` measures walk-forward AUC per (sport, market) on the
box that holds the logs and stores it beside the calibrations, and
`likely.rank_auc` reads the store first. An MLB shelf turns on where the
measurement happened, and nowhere else.

Also fixed in passing and pinned here: the CFB board wore the NFL's
0.721 touchdown AUC — `from_watch` read a flat dict with no idea whose
chain built the row. College's own measured figure is 0.675.

Run directly: `python3 tests/test_mlb_likely.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import boards, likely, rankfit


def _clear_store():
    try:
        os.remove(rankfit.STORE)
    except OSError:
        pass


# --- the AUC itself --------------------------------------------------------
def test_a_perfect_ranking_scores_one_and_a_reversed_one_zero():
    perfect = [(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0)]
    reversed_ = [(p, 1 - o) for p, o in perfect]
    assert rankfit.auc(perfect) == 1.0
    assert rankfit.auc(reversed_) == 0.0


def test_ties_share_credit_and_one_sided_outcomes_refuse():
    assert rankfit.auc([(0.5, 1), (0.5, 0)]) == 0.5
    assert rankfit.auc([(0.5, 1), (0.6, 1)]) is None


# --- the measurement, walked through a stubbed harness ---------------------
def _measure(pairs_by_market, store_path, prior=None):
    from engine import db as _db, logwalk

    class _Rep:
        def __init__(self, pairs):
            self.pairs = pairs

    if prior is not None:
        with open(store_path, "w") as f:
            json.dump(prior, f)
    calls = {}
    saved = (_db.entries_for_market, logwalk.walk)
    _db.entries_for_market = lambda conn, sport, market, **kw: (
        [{"name": "x", "values": [1]}] if market in pairs_by_market else [])
    def fake_walk(sport, entries, market, **kw):
        calls[market] = True
        return _Rep(pairs_by_market[market])
    logwalk.walk = fake_walk
    try:
        lines = rankfit.measure(None, "mlb", log=lambda *_: None,
                                path=store_path)
    finally:
        _db.entries_for_market, logwalk.walk = saved
    return lines, rankfit.load(store_path)


def _good_pairs(auc_high=True, n=3000):
    # Alternate outcomes so the AUC is exactly 1.0 (or 0.5 when mixed).
    out = []
    for i in range(n):
        o = i % 3 == 0
        p = (0.7 if o else 0.3) if auc_high else 0.5
        out.append((p, 1 if o else 0))
    return out


def test_a_big_clean_sample_is_adopted_with_its_auc():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs()}, tmp)
    assert store["mlb:hits"]["auc"] == 1.0
    assert store["mlb:hits"]["n"] == 3000
    assert any("on the board" in ln for ln in lines), lines


def test_an_auc_under_the_floor_is_stored_but_named_off_the_board():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs(auc_high=False)}, tmp)
    assert abs(store["mlb:hits"]["auc"] - 0.5) < 0.01
    assert any("stays off the board" in ln for ln in lines), lines


def test_a_thin_sample_claims_nothing():
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    lines, store = _measure({"hits": _good_pairs(n=500)}, tmp)
    assert "mlb:hits" not in store
    assert any("needs" in ln for ln in lines), lines


def test_a_refit_gone_thin_retires_the_old_measurement():
    """A number measured on data the box no longer holds must not keep
    a shelf open past its evidence."""
    tmp = os.path.join(tempfile.mkdtemp(), "rank_auc.json")
    prior = {"mlb:hits": {"auc": 0.71, "n": 9000, "fitted_at": "2026-07-01"}}
    lines, store = _measure({"hits": _good_pairs(n=100)}, tmp, prior=prior)
    assert "mlb:hits" not in store
    assert any("RETIRED" in ln for ln in lines), lines


# --- likely reads the store, per sport -------------------------------------
def test_an_unmeasured_mlb_market_is_not_rankable():
    _clear_store()
    assert likely.rank_auc("mlb", "hits") is None
    assert not likely.rankable("hits", "mlb")


def test_a_fitted_mlb_market_turns_itself_on():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.71, "n": 9000}})
    try:
        assert likely.rank_auc("mlb", "hits") == 0.71
        assert likely.rankable("hits", "mlb")
        assert not likely.rankable("home_runs", "mlb"), "unmeasured sibling"
    finally:
        _clear_store()


def test_a_fitted_market_under_the_floor_stays_off():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.55, "n": 9000}})
    try:
        assert not likely.rankable("hits", "mlb")
    finally:
        _clear_store()


def test_the_nfl_constants_still_answer_and_cfb_stops_borrowing_them():
    _clear_store()
    assert likely.rank_auc("nfl", "anytime_td") == likely.RANK_AUC["anytime_td"]
    assert likely.rank_auc("cfb", "anytime_td") == likely.CFB_TD_AUC
    assert likely.rank_auc("cfb", "anytime_td") != likely.RANK_AUC["anytime_td"]


def test_a_cfb_watch_row_carries_colleges_own_figure():
    row = likely.from_watch({"player": "A", "team": "UGA",
                             "model_prob": 0.5}, sport="cfb")
    assert row["rank_auc"] == likely.CFB_TD_AUC


# --- the shelves and the build ---------------------------------------------
def test_mlb_has_shelves_and_unlisted_sports_still_do_not():
    shape = boards.shelves("mlb")
    keys = [s["key"] for s in shape]
    assert keys == ["homers", "bats", "arms"], keys
    assert boards.shelves("ufc") == []


def test_mlb_shelf_auc_reads_the_fitted_store():
    _clear_store()
    assert all(s["rank_auc"] is None for s in boards.shelves("mlb"))
    rankfit._save({"mlb:home_runs": {"auc": 0.68, "n": 9000}})
    try:
        homers = boards.shelves("mlb")[0]
        assert homers["rank_auc"] == 0.68
    finally:
        _clear_store()


def test_a_measured_market_flows_through_build_to_the_board():
    _clear_store()
    rankfit._save({"mlb:hits": {"auc": 0.71, "n": 9000}})
    row = {"player": "T Player", "team": "NYY", "market": "hits",
           "market_label": "Hits", "side": "over", "line": 1.5,
           "hit_prob": 0.62, "has_market": True, "odds": -130,
           "book": "fanduel", "implied_prob": 0.58}
    try:
        got = likely.build([row], sport="mlb")
        assert got and got[0]["market"] == "hits"
        assert got[0]["rank_auc"] == 0.71
        assert likely.build([row], sport="nfl") == [], \
            "an MLB measurement must not open the NFL board"
    finally:
        _clear_store()


def test_the_mlb_build_publishes_the_board():
    with open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'result["most_likely"] = _likely_build(' in src
    assert 'sport="mlb"' in src
    assert '_mlboards.shelves(' in src


def test_the_weekly_pass_measures_and_an_empty_store_bootstraps():
    with open(os.path.join(ROOT, "engine", "maintenance.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "_rank_measure(_rkc, _sp, log=log)" in src
    assert "measuring now, not Wednesday" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
