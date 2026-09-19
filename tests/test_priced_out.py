"""Graded A, staked 0.00u — a pick that existed nowhere.

"im confused. we are grading picks as an A but then putting zero units?"

Fair. The grade and the stake measure different things and nothing said so.

The grade is a quality score — edge 40%, pitcher certainty 15%, lineup
certainty 15% — and answers "how much do we trust this read". The stake is
Kelly at the price on offer and answers "is this worth taking". They can
disagree, because the edge bar compares us to the DE-VIGGED fair number
while Kelly compares us to the actual price. A pick can beat fair by 2% and
still lose to the vig.

So "grade A, 0.00u" means: the read is good and the book has already priced
it. There is no bet. Staking it anyway would be knowingly taking a
negative-expectation wager, which is the one thing a betting model must not
do — so this does NOT make them real bets.

What was broken was everything else. Nothing checked the stake before
flagging a pick `recommended`, so the board showed it, the journal skipped
it (stake <= 0), and it landed in no bucket at all: invisible on the Live
tab, absent from the Record, and contradicting the board that displayed it.

Now it is not recommended, and it is paper-tracked in its own bucket at a
flat stake with zero dollars — the empirical answer to "was Kelly right to
refuse?". If the bucket wins at the prices it declined, the sizing is too
strict. If it burns, the refusal was right.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine.mlb.pipeline import _is_priced_out, near_misses, priced_out

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _row(**kw):
    base = {"player": "A Hitter", "market": "total_bases", "side": "OVER",
            "line": 1.5, "odds": -115, "book": "FanDuel", "grade": "A",
            "confidence": 8.1, "edge": 0.041, "stake_units": 0.0,
            "has_market": True, "recommended": False, "tier": 1}
    base.update(kw)
    return base


# --- what counts as priced out ----------------------------------------------
def test_a_graded_pick_with_no_stake_is_priced_out():
    assert _is_priced_out(_row()) is True


def test_a_graded_pick_with_a_real_stake_is_not():
    assert _is_priced_out(_row(stake_units=1.2)) is False


def test_a_pass_is_not_priced_out():
    """A Pass failed the READ. Priced-out passed the read and failed the
    price. Conflating them would put every rejected prop in the bucket."""
    assert _is_priced_out(_row(grade="Pass")) is False


def test_a_proxy_priced_row_never_reaches_the_bucket():
    """Nobody declined a price no book offered, so there is nothing to
    learn from grading against it."""
    assert priced_out([_row(has_market=False)]) == []


# --- it must not be double-counted ------------------------------------------
def test_a_priced_out_pick_is_not_also_a_near_miss():
    """Different populations answering different questions: a near-miss
    fell short of the tier's edge bar, a priced-out pick cleared it and
    lost to the vig. Mixing them blends two unrelated experiments and
    journals the row twice."""
    assert near_misses([_row()]) == []


def test_an_ordinary_near_miss_still_reaches_the_loose_bucket():
    """The control — without it the test above passes for a near_misses()
    that returns nothing at all."""
    rows = near_misses([_row(grade="Pass", stake_units=0.0, edge=0.020,
                             quality=75)])
    assert len(rows) == 1


# --- the board must stop showing them ---------------------------------------
def test_the_rules_refuse_to_recommend_a_pick_kelly_will_not_stake():
    from engine.mlb.rules import apply_mlb_rules
    src = open(os.path.join(ROOT, "engine", "mlb", "rules.py"),
               encoding="utf-8").read()
    assert "(rec.stake_units or 0) <= 0 and rec.grade != \"Pass\"" in src
    assert "Priced out" in src
    assert callable(apply_mlb_rules)


def test_the_warning_explains_itself_rather_than_just_flagging():
    src = open(os.path.join(ROOT, "engine", "mlb", "rules.py"),
               encoding="utf-8").read()
    i = src.index("Priced out")
    assert "Kelly sizes it at 0.00u" in src[i:i + 300]
    assert "never staked" in src[i:i + 400]


# --- the journal bucket -----------------------------------------------------
def test_it_is_journaled_to_its_own_bucket():
    c = _conn()
    n = ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                                  "priced_out": [_row()]})
    assert n == 1
    row = c.execute("SELECT category, stake_units, stake_dollars, status "
                    "FROM bets").fetchone()
    assert row["category"] == "pricedout"
    assert row["status"] == "open"


def test_it_never_carries_dollars():
    """It is a measurement, not a bet. Real exposure here would be the
    model knowingly taking a price it computed as -EV."""
    c = _conn()
    ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                              "priced_out": [_row()]})
    assert c.execute("SELECT stake_dollars FROM bets").fetchone()[0] == 0.0


def test_a_proxy_price_is_not_journaled():
    c = _conn()
    n = ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                                  "priced_out": [_row(book="proxy")]})
    assert n == 0


def test_home_runs_stay_on_their_own_board():
    c = _conn()
    n = ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                                  "priced_out": [_row(market="home_runs")]})
    assert n == 0


def test_it_stays_out_of_the_headline_record():
    """category='main' is the record the Record page scores. A paper
    sampler in there would describe bets nobody placed."""
    c = _conn()
    ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                              "priced_out": [_row()]})
    assert c.execute("SELECT COUNT(*) FROM bets "
                     "WHERE category='main'").fetchone()[0] == 0


def test_the_bucket_has_its_own_scorecard():
    c = _conn()
    ledger.log_priced_out(c, {"sport": "mlb", "date": "2026-08-01",
                              "priced_out": [_row()]})
    rep = ledger.priced_out_report(c)
    assert "recent" in rep


def test_the_build_journals_the_bucket():
    src = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    assert "ledger.log_priced_out(lconn, result)" in src


def test_the_pipeline_emits_the_bucket():
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    assert '"priced_out": priced_out(results),' in src


def test_a_row_that_was_never_sized_is_not_priced_out():
    """"stake_units absent" means the sizer never ran; "stake_units == 0"
    means it ran and refused. The first version conflated them and pulled
    every ordinary near-miss into this bucket — caught by the existing
    near-miss test, not by any of mine."""
    assert _is_priced_out({"grade": "B", "has_market": True}) is False
    assert _is_priced_out({"grade": "B", "stake_units": 0.0}) is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
