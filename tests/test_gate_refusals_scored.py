"""What happened to the props the Edge board turned DOWN.

Task #164, "rebuild what it selects on", has carried one line since the
selection backtest ran on 2026-09-06:

    STILL UNANSWERABLE FROM THE JOURNAL: whether any ordering would have
    ADMITTED bets the edge gate refused.

That is the question that decides whether the gate is any good, and the
journal cannot answer it by construction: it holds the bets we PLACED,
so `recommended` is True on every row in it. `engine/selectorder.py`
says the same thing in its own docstring — "take the bets we actually
placed and settled".

THE DATA WAS ALREADY THERE. `backtest_from_stats` walks the season
forward, prices every prop from prior weeks only, and settles ALL of
them against the box score. `SettledProp` carries `recommended` beside
the outcome and `BacktestReport.settled` keeps every row. The candidate
surface with outcomes has existed the whole time; nothing ever read the
refused half of it. `n_bets`, `roi` and the rest of the report are
documented "recommended bets only".

So: `from_settled` adapts that surface into the row shape this module
already scores, and `gate_split` scores both arms at a flat 1u.

THE BOOTSTRAP IS NOT THE ONE ABOVE IT, and that is the part worth
getting right. `_boot_roi_diff` resamples ONE pool and re-cuts it,
because the arms it compares are two orderings of the same rows. Here
the arms are different rows — admitted and refused are disjoint — so
each is resampled within itself. Reusing the paired version would have
reported a narrower interval than the truth, which flatters exactly the
kind of result somebody wants to act on.

Run directly: `python3 tests/test_gate_refusals_scored.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import selectorder as S                            # noqa: E402
from engine.backtest import SettledProp                        # noqa: E402


def _sp(actual, line=50.0, odds=-110, recommended=True, basis="book",
        side="OVER", hit_prob=0.55):
    return SettledProp(player="A Man", market="rec_yds", line=line, odds=odds,
                       hit_prob=hit_prob, projection=line, actual=actual,
                       recommended=recommended, basis=basis, side=side)


# --- the adapter ------------------------------------------------------------
def test_the_candidate_surface_becomes_scoreable_rows():
    rows = S.from_settled([_sp(60.0), _sp(40.0, recommended=False)])
    assert [r["status"] for r in rows] == ["won", "lost"]
    assert [r["recommended"] for r in rows] == [True, False]
    assert all(r["basis"] == "book" for r in rows)


def test_an_under_is_scored_on_the_side_it_backed():
    """`SettledProp.outcome` already flips for an UNDER. If the adapter
    read `over_hit` instead, every under would grade backwards — the
    exact bug SettledProp's own comment says it exists to prevent."""
    rows = S.from_settled([_sp(40.0, side="UNDER")])
    assert [r["status"] for r in rows] == ["won"], rows


def test_a_push_is_dropped_rather_than_counted_as_a_loss():
    """A push returns the stake. Scoring it as a loss would bias
    whichever arm happens to hold more of them, and the arms here are
    different populations — so it cannot cancel out the way it would in
    a paired comparison."""
    rows = S.from_settled([_sp(50.0), _sp(60.0)])
    assert len(rows) == 1 and rows[0]["status"] == "won", rows


def test_the_journal_still_reads_as_all_admitted():
    """`usable` defaults `recommended` True, because a journal row is a
    bet we placed. Without that default every existing caller's rows
    would land in the refused arm."""
    rows = S.usable([{"status": "won", "hit_prob": 0.6, "odds": -110}])
    assert rows and rows[0]["recommended"] is True, rows


# --- the split --------------------------------------------------------------
def _arm(n, won, recommended, odds=-110, basis="book"):
    return [_sp(60.0 if i < won else 40.0, odds=odds,
                recommended=recommended, basis=basis) for i in range(n)]


def test_a_gate_whose_refusals_lose_earns_its_place():
    settled = _arm(80, 60, True) + _arm(80, 20, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    assert res["enough"], res
    assert res["admitted"]["bets"] == 80 and res["refused"]["bets"] == 80
    assert res["admitted"]["roi"] > res["refused"]["roi"], res
    assert res["diff"]["admitted-refused"]["lo"] > 0, res["diff"]
    assert "earns its place" in S.gate_reading(res), S.gate_reading(res)


def test_a_gate_whose_refusals_win_is_reported_as_costing_money():
    """THE FINDING THIS EXISTS TO CATCH. If the board would have done
    better taking what it turned down, nothing in the journal would ever
    say so."""
    settled = _arm(80, 20, True) + _arm(80, 60, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    assert res["diff"]["admitted-refused"]["hi"] < 0, res["diff"]
    say = S.gate_reading(res)
    assert "COSTING money" in say, say
    assert "worth more than what it takes" in say, say


def test_two_arms_that_ran_the_same_read_as_unproven():
    settled = _arm(80, 40, True) + _arm(80, 40, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    d = res["diff"]["admitted-refused"]
    assert d["lo"] <= 0 <= d["hi"], d
    assert "unproven either way" in S.gate_reading(res), S.gate_reading(res)


# --- the bars that keep it honest -------------------------------------------
def test_a_thin_arm_reports_how_thin_rather_than_a_number():
    settled = _arm(80, 40, True) + _arm(5, 3, False)
    res = S.gate_split(S.from_settled(settled), reps=100)
    assert not res["enough"], res
    assert res["admitted"] is None and res["refused"] is None
    assert "5 refused" in res["note"], res["note"]
    assert S.gate_reading(res) == res["note"]


def test_proxy_priced_rows_are_left_out_by_default():
    """A `naive` row was priced against the recent-form proxy at a
    synthetic -110, so beating it is the model scored against itself.
    `BacktestReport` segments on the same distinction."""
    settled = _arm(80, 60, True) + _arm(80, 20, False, basis="naive")
    res = S.gate_split(S.from_settled(settled), reps=100)
    assert res["n_refused"] == 0, res
    assert not res["enough"], res


def test_pooling_the_proxy_rows_says_the_number_is_not_market_relative():
    settled = _arm(80, 60, True, basis="naive") + _arm(80, 20, False, basis="naive")
    res = S.gate_split(S.from_settled(settled), basis="naive", reps=300)
    assert res["enough"], res
    assert "not a claim about beating a market" in S.gate_reading(res)


def test_the_bootstrap_is_two_sample_not_the_paired_one():
    """Read off the function, because the failure is invisible in the
    output: a paired interval on unpaired arms is simply narrower than
    the truth."""
    import inspect
    src = inspect.getsource(S.gate_split)
    assert "_boot_two_sample" in src, src[:200]
    assert "_boot_roi_diff" not in src, "the paired bootstrap is back"
    two = inspect.getsource(S._boot_two_sample)
    assert "_top(" not in two, "the two-sample bootstrap is re-cutting a slice"


def test_the_two_arms_never_share_a_row():
    """Disjoint by construction — the whole basis for reading the
    difference as the gate's doing."""
    settled = _arm(70, 35, True) + _arm(70, 35, False)
    rows = S.from_settled(settled)
    pool = S.usable(rows)
    took = [r for r in pool if r["recommended"]]
    left = [r for r in pool if not r["recommended"]]
    assert len(took) + len(left) == len(pool)
    assert len(took) == 70 and len(left) == 70


# --- WHICH refusal is costing ------------------------------------------------
def _refused(why, n, won):
    """`n` refused rows carrying reason `why`, `won` of them winners at
    -110 — so a reason with more than 52.4% winners is one the gate was
    wrong to refuse."""
    return [{"status": "won" if i < won else "lost", "hit_prob": 0.55,
             "odds": -110, "stake_units": 1.0, "market": "hits",
             "recommended": False, "basis": "book", "refusal": why}
            for i in range(n)]


def test_the_refused_arm_splits_by_the_bar_that_refused_it():
    """THE FOLLOW-UP `gate_split`'s OWN DOCSTRING NAMED AND COULD NOT
    ASK: "which refusal did it — this function does not know, and saying
    which would need the refusal REASON on the row, which SettledProp
    does not carry." It carries it now."""
    from engine.selectorder import by_refusal
    # THE LOSING REASON IS INSERTED FIRST, deliberately. Python dicts
    # keep insertion order, so a fixture listing the winner first passes
    # whether or not anything sorts — and did, until a mutant that
    # deleted the sort survived this test.
    rows = _refused("no credible edge", 40, 10) + \
        _refused("the price looks off", 40, 30)
    got = by_refusal(rows)
    assert len(got) == 2, got
    # Best first, so the bar the gate was most wrong to apply leads.
    assert got[0]["refusal"] == "the price looks off", got
    assert got[0]["roi"] > 0 and got[1]["roi"] < 0, got
    assert got[0]["n"] == 40 and got[1]["n"] == 40


def test_a_thin_reason_is_pooled_rather_than_quoted():
    """Many small slices of one sample: the smallest always looks the
    most extreme. A reason under the floor is pooled and the reader is
    told how much is being withheld."""
    from engine.selectorder import by_refusal, refusal_lines
    rows = _refused("a common bar", 40, 30) + _refused("a rare bar", 3, 3)
    got = by_refusal(rows, min_n=20)
    assert len(got) == 2, got
    assert got[-1].get("thin") is True, got
    assert got[-1]["n"] == 3
    assert "pooled" in got[-1]["refusal"]
    out = "\n".join(refusal_lines(got))
    assert "a rare bar" not in out, "a 3-row slice was quoted as a finding"


def test_the_reading_refuses_to_call_it_a_verdict():
    """Acting on the worst line is choosing a threshold on the rows that
    suggested it — engine/prereg.py, the discipline #164 opens with."""
    from engine.selectorder import by_refusal, refusal_lines
    out = "\n".join(refusal_lines(by_refusal(
        _refused("a bar", 40, 30))))
    assert "LEAD, NOT A VERDICT" in out, out
    assert "prereg" in out, out


def test_an_admitted_row_is_never_in_the_split():
    from engine.selectorder import by_refusal
    rows = _refused("a bar", 40, 30)
    for r in rows[:10]:
        r["recommended"] = True
        r["refusal"] = ""
    got = by_refusal(rows, min_n=1)
    assert sum(g["n"] for g in got) == 30, got


def test_a_settled_prop_carries_the_reason_off_the_card():
    """Read from the card's own sentences, not re-derived — a second
    definition of the gate would drift from the one the reader saw."""
    from engine.backtest import refusal_of
    assert refusal_of({"recommended": True, "warnings": ["x"]}) == ""
    assert refusal_of({"recommended": False,
                       "warnings": ["the price looks off"]}) == \
        "the price looks off"
    # A refused rec with nothing to say is LABELLED, not silently
    # bucketed with a named reason.
    assert refusal_of({"recommended": False}) == "refused, reason not recorded"


def test_the_reason_survives_the_trip_to_the_scorer():
    """`usable` rebuilds every row, and dropping the field there made the
    split read "reason not recorded" on every row — a lost field looking
    exactly like a data gap."""
    from engine.selectorder import usable
    got = usable(_refused("a named bar", 1, 1))
    assert got[0]["refusal"] == "a named bar", got


# --- the CLI reads it -------------------------------------------------------
def test_the_backtest_cli_can_print_it():
    src = open(os.path.join(ROOT, "backtest.py"), encoding="utf-8").read()
    assert '"--gate"' in src, "the flag is gone"
    assert "def gate_report(" in src
    # NAMED, NOT SPELLED AS ONE IMPORT LINE. Asserting the exact import
    # statement broke the moment `by_refusal` joined it — for a reason
    # that has nothing to do with whether the CLI reads the split. What
    # matters is that each function is reached.
    for fn in ("from_settled", "gate_split", "gate_reading"):
        assert fn in src, f"the CLI no longer calls {fn}"
    assert "report.settled" in src, "the CLI is not reading the candidate surface"
    # AND IT CAN FILL THE BOOK-PRICED ARM. Without harvested closes every
    # row is basis=naive and `--gate` has nothing market-relative to read
    # — which is what the first live run of this did, silently.
    assert "by_refusal" in src and "refusal_lines" in src, \
        "the CLI prints whether the gate costs money and never which bar"
    assert '"--real-lines"' in src, "the join that makes --gate mean anything is gone"
    assert "nfl_real_lines" in src
    # THE VALUE REACHES THE REPLAY, not just the flag reaching argparse.
    # Written after a mutant that deleted `real_lines=real` from the call
    # survived every other assertion here: the flag would still parse,
    # the closes would still be read and counted on screen, and every row
    # would still come back proxy-priced.
    assert "real_lines=real)" in src, \
        "the harvested closes are built and then not passed to the replay"


def test_the_header_names_the_basis_it_actually_read():
    """It said "priced against a real book line" whatever basis was
    asked for, so the proxy run announced 2,529 book-priced rows it did
    not have. A false sentence over a true table is the shape of every
    wrong number this repo has had to chase."""
    src = open(os.path.join(ROOT, "backtest.py"), encoding="utf-8").read()
    i = src.index("def gate_report(")
    body = src[i:src.index("\nif __name__", i)] if "\nif __name__" in src[i:] else src[i:]
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "recent-form proxy at a synthetic -110" in code, code[:300]
    assert "real harvested book line" in code, code[:300]
    # The claim must be conditional on the basis, never unconditional.
    assert 'res["basis"] == "book"' in code, code[:300]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
