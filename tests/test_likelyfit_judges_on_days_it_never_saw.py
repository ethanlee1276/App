"""likelyfit.py: which Most Likely picks to stop taking, judged out of sample.

Ethan, 2026-10-02: "I feel like we have collected enough data for our
most likely bets too make the models better". The record says the number
is honest and the price is the problem, so the study tries selection
rules — chosen on the earlier days, scored on later days they never saw.
These tests plant a real pattern and check it is found, check pure noise
passes nothing, and check the ledger is never written.

Run directly: `python3 tests/test_likelyfit_judges_on_days_it_never_saw.py`
"""
import datetime as dt
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import likelyfit as LF                                           # noqa: E402
from engine import ledger                                        # noqa: E402

_INS = ("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, edge, grade, "
        "stake_units, stake_dollars, status, category, pnl_units) VALUES ('t',?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,0)")


def _ledger(path, planted: bool, seed=1, days=60, per_day=12):
    conn = ledger.connect(path)
    rng = random.Random(seed)
    start = dt.date(2026, 8, 1)
    for d in range(days):
        day = (start + dt.timedelta(days=d)).isoformat()
        for i in range(per_day):
            heavy = i % 2 == 0
            odds = -300 if heavy else -130
            # Planted: the heavy favourites hit 62%, far under the 75% their
            # price needs; the short ones hit 62% at a price needing 56.5%.
            # Unplanted: every pick hits at exactly its own break-even.
            p = 0.62 if planted else (0.75 if heavy else 0.565)
            won = rng.random() < p
            conn.execute(_INS, ("mlb", day, day, f"P{d}-{i}", "hits", "OVER", 0.5, odds, 0.66, 0.02,
                                "Likely", 0.1, "won" if won else "lost", "likely"))
    conn.commit()
    conn.close()


def _run(planted, seed=1):
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    _ledger(p, planted, seed)
    rows = LF.load(LF._ro(p), "mlb")
    return LF.study(rows), p


def test_a_real_pattern_is_found_on_the_days_that_chose_nothing():
    res, _ = _run(planted=True)
    cap = next(r for r in res["rules"] if r["rule"] == "price_cap")
    assert cap["verdict"] == "PASSES", cap
    assert "heavier than -250" in cap["setting"] or "heavier than -200" in cap["setting"] \
        or "heavier than -175" in cap["setting"] or "heavier than -150" in cap["setting"], cap
    assert cap["test_roi"] > cap["test_all_roi"]


def test_noise_passes_nothing():
    for seed in (2, 3, 4, 5, 6):
        res, _ = _run(planted=False, seed=seed)
        passed = [r["rule"] for r in res["rules"] if r.get("verdict") == "PASSES"]
        assert passed == [], (seed, passed)


def test_the_split_is_by_date_and_the_later_days_are_never_chosen_on():
    res, _ = _run(planted=True)
    assert res["train_days"][1] < res["test_days"][0]
    assert res["train"] + res["test"] == res["n"]


def test_a_thin_book_refuses_to_judge():
    rows = [{"ret": 0.5, "day": f"2026-09-{d:02d}", "odds": -110, "hit_prob": 0.6, "edge": 0.01,
             "fair_consensus": None, "side": "OVER", "lead_min": None, "grade": "", "sport": "nfl",
             "market": "rec_yds"} for d in range(1, 30)]
    res = LF.study(rows)
    assert res["rules"] == [] and "needed before a rule can be judged" in res["note"]


def test_the_ledger_is_never_written():
    _, p = _run(planted=True)
    before = p.read_bytes()
    LF.main(["--db", str(p)])
    assert p.read_bytes() == before


def test_the_bar_is_written_down_before_the_run():
    src = " ".join((ROOT / "likelyfit.py").read_text().split())
    assert "THE BAR, WRITTEN BEFORE ANY RUN" in src
    assert "two runs at least two weeks apart" in src
    assert LF.MIN_TEST_KEPT == 40 and LF.TRAIN_SHARE == 0.60


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
