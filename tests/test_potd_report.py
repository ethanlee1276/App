"""The funnel a person can actually run on the box.

Ethan, 2026-09-15: "I wanna make sure we access all the data we can and
all the tools we can to dish out the best picks of the day possible."

THE QUESTION NO TEST CAN ANSWER is whether a real Tuesday board carries
anything for the selector's rules to bite on. The suite proves the rules
are obeyed; `potd_report.py` is how a person finds out whether the POOL
is wrong — "68 rows considered, 61 outside the band, 0 picks" is not a
bug report, it is the name of the gate to argue with.

What is guarded here is that the tool stays honest about three things: it
never writes, it never invents a pick, and an absent board reads as an
absent board rather than as an empty day.

Run directly: `python3 tests/test_potd_report.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import potd_report as R                                       # noqa: E402
from engine import potd                                       # noqa: E402

ET = ZoneInfo("America/New_York")


def _row(**kw):
    """A board row three hours from kickoff that clears every bar."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=180)
    r = {"kind": "prop", "player": "A Player", "team": "AAA",
         "opponent": "BBB", "market": "receptions",
         "market_label": "Receptions", "side": "over", "line": 3.5,
         "book": "DraftKings", "odds": -110, "sharp_anchored": True,
         "sharp_fair": 0.60, "model_prob": 0.58, "implied_prob": 0.5238,
         "rank_auc": 0.71, "bettable": True, "injury_status": "",
         "game_date": t.strftime("%Y-%m-%d"), "kickoff": t.strftime("%H:%M")}
    r.update(kw)
    return r


def _board(rows):
    return {"built_at": "2026-09-15T12:00:00", "most_likely": rows}


def _in_tmp(files: dict):
    """A throwaway data dir. NEVER the box's own `web/data` — a test that
    reads the machine it runs on passes or fails on what happened to be
    built there this morning, which is the house rule this obeys."""
    d = tempfile.mkdtemp(prefix="potd-report-")
    for name, payload in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return d


# --- it reports what the selector actually did -------------------------------
def test_the_pick_and_the_gates_both_appear():
    out = R.report(_board([_row(player="Good"), _row(odds=-400)]), "nfl")
    assert "PICK" in out and "Good" in out, out
    assert "the payout is outside the even-money band" in out, out
    assert "2 row(s) considered" in out, out


def test_a_day_with_no_pick_names_the_binding_gate_rather_than_shrugging():
    """The whole reason the tool exists. A blank day must say which bar
    it was, or the next hour is spent guessing at it."""
    out = R.report(_board([_row(sharp_fair=0.53)]), "nfl")
    assert "no pick" in out, out
    assert "not far enough off the fair" in out, out
    assert "shown, not recorded" in out, out


def test_an_empty_board_says_the_pool_was_empty_not_that_the_day_was_quiet():
    out = R.report(_board([]), "nfl")
    assert "no Most Likely rows at all" in out, out
    assert "PICK" not in out, out


def test_a_board_it_cannot_read_says_so_and_does_not_pretend():
    out = R.report({"_error": "JSONDecodeError: line 1"}, "nfl")
    assert "could not read the board" in out, out
    assert "JSONDecodeError" in out, out


def test_the_near_misses_carry_the_reason_each_one_missed_by():
    rows = [_row(player="Thin", sharp_fair=0.53),
            _row(player="Flip", rank_auc=0.49),
            _row(player="Ours", sharp_anchored=False, sharp_fair=None,
                 model_prob=0.70)]
    out = R.report(_board(rows), "nfl", rows_shown=5)
    for who, why in (("Thin", "not far enough off the fair"),
                     ("Flip", "ranks no better than a coin flip"),
                     ("Ours", "only our own model disputes this price")):
        assert who in out and why in out, (who, out)


def test_a_reserve_candidate_is_labelled_where_it_is_printed():
    """It can be the pick now (engine/potd.shortfall), so a reader of
    this tool has to be able to see that that is what happened."""
    out = R.report(_board([_row(reserve=True, sharp_fair=0.62, odds=100)]), "nfl")
    assert "[reserve]" in out, out


def test_the_line_names_the_witness_and_never_only_a_number():
    """"60%" means a different thing from a sharp book than from us, and
    a report that prints the number alone is the failure this whole
    rebuild was about."""
    out = R.report(_board([_row()]), "nfl")
    assert "sharp fair" in out, out
    out2 = R.report(_board([_row(sharp_anchored=False, sharp_fair=None,
                                 prob_source="market", implied_prob=0.56)]), "nfl")
    assert "market fair" in out2, out2


# --- and it is safe to point at the production box ---------------------------
def test_a_missing_league_is_skipped_and_a_missing_everything_explains():
    d = _in_tmp({})
    assert R.main(["nfl", "--dir", d]) == 1, "nothing found is a non-zero exit"
    d2 = _in_tmp({"nfl_picks.json": _board([_row()])})
    assert R.main(["nfl", "--dir", d2]) == 0
    # A league simply out of season is not an error beside one in season.
    assert R.main(["nfl", "wnba", "--dir", d2]) == 0


def test_the_tool_writes_nothing():
    """Read-only is the claim that lets this run on the droplet mid-cycle,
    so it is asserted rather than trusted: the data dir is byte-identical
    after a full run."""
    d = _in_tmp({"nfl_picks.json": _board([_row(), _row(odds=-400)])})
    before = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    R.main(["nfl", "--dir", d])
    after = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    assert before == after, "the report modified the board it was reading"
    assert sorted(before) == sorted(after), "the report added or removed a file"


def test_the_header_quotes_the_band_from_the_engine_not_from_a_copy():
    """A tool printing its own idea of the band would tell a reader the
    selector is doing something it is not."""
    out = R.report(_board([_row()]), "nfl")
    assert f"{potd.MIN_ODDS:+d}" in out and f"{potd.MAX_ODDS:+d}" in out, out
    assert f"{potd.MIN_EV:.0%}" in out, out


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
