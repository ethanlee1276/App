"""The preflight that says whether the de-vig ran on the live board.

Unit tests prove the arithmetic; they cannot prove the FEED cooperates.
If the odds feed returns twelve players where the book lists thirty, the
sum comes in low and the hold with it — silently, in the direction that
inflates edge. This module is what catches that, so what it must never
do is report a green light it did not earn.

Run directly: `python3 tests/test_devigcheck.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.devigcheck import (
    SUSPICIOUS_VIG, SUSPICIOUS_DEFAULT, rows_of, summarise, verdict,
    report_lines,
)


def _board(sport="nfl", picks=(), watch=()):
    return {"sport": sport, "date": "2026-08-29",
            "generated_at": "2026-08-29T12:00:00Z",
            "long_shots": list(picks), "longshot_watch": list(watch)}


def _row(player="A", odds=300, vig=0.22, source="measured:dk"):
    return {"player": player, "odds": odds, "vig": vig, "vig_source": source}


# --- what it counts -------------------------------------------------------
def test_the_watch_counts_too_because_it_is_the_wider_sample():
    """The watch takes every quoted scorer at a sane price, so it sees
    more of what the feed returned than the handful of picks that cleared
    the edge bar. Checking only the picks would check the least of it."""
    b = _board(picks=[_row("A")], watch=[_row("B"), _row("C")])
    assert len(rows_of(b)) == 3
    kinds = {r["_kind"] for r in rows_of(b)}
    assert kinds == {"pick", "watch"}


def test_it_separates_the_three_things_that_can_be_true_of_a_price():
    b = _board(picks=[_row(source="measured:dk"),
                      _row(source="two-way", vig=0.0),
                      _row(source="assumed", vig=0.06),
                      _row(source="journal:812", vig=0.11)])
    got = summarise(b)
    assert got["measured"] == 1
    assert got["two_way"] == 1
    # A journalled hold is still a fallback, not a measurement off this
    # game's board — counting it as measured would overstate the wiring.
    assert got["assumed"] == 2
    assert got["unknown"] == 0


def test_a_row_with_no_vig_field_is_unknown_not_assumed():
    """A board built before the field existed proves nothing about
    whether the de-vig is running, and must not be scored as if it
    did."""
    got = summarise(_board(picks=[{"player": "A", "odds": 300}]))
    assert got["unknown"] == 1
    assert got["measured"] == got["assumed"] == got["two_way"] == 0


def test_it_names_the_reference_books_it_saw():
    b = _board(picks=[_row(source="measured:dk"), _row(source="measured:dk"),
                      _row(source="measured:fanduel")])
    assert summarise(b)["books"] == {"dk": 2, "fanduel": 1}


def test_it_reports_the_spread_of_measured_vigs():
    b = _board(picks=[_row(vig=v) for v in (0.18, 0.25, 0.31)])
    got = summarise(b)
    assert (got["vig_min"], got["vig_median"], got["vig_max"]) == (0.18, 0.25, 0.31)


# --- the short-board alarm ------------------------------------------------
def test_an_implausibly_low_measured_vig_is_flagged_as_a_short_board():
    """The failure this exists for. A feed returning half a game's
    scorers produces a real-looking measurement that is far too low, and
    too low is the direction that inflates edge — so a number under what
    the market is known to charge reads as a truncated board, not a
    generous book."""
    got = summarise(_board("nfl", picks=[_row(vig=0.02)]))
    assert len(got["suspicious"]) == 1
    state, why = verdict(got)
    assert state == "CHECK"
    assert any("SHORT BOARD" in w for w in why)


def test_college_carries_a_higher_alarm_than_the_nfl():
    """College holds run wider — the handbook puts them at 28-50% against
    the NFL's 22-35% — so a vig that is merely low for the NFL is
    alarming for CFB."""
    assert SUSPICIOUS_VIG["cfb"] > SUSPICIOUS_VIG["nfl"]
    low = _row(vig=0.12)
    assert not summarise(_board("nfl", picks=[low]))["suspicious"]
    assert summarise(_board("cfb", picks=[low]))["suspicious"]


def test_the_alarms_sit_well_under_the_published_ranges():
    """They are a truncation alarm, not a claim about what the hold
    should be. Setting them inside the handbooks' ranges would assert
    those ranges as fact, which this work has repeatedly found unsafe."""
    assert SUSPICIOUS_VIG["nfl"] < 0.22        # the NFL handbook's floor
    assert SUSPICIOUS_VIG["cfb"] < 0.28        # the CFB handbook's floor
    assert SUSPICIOUS_DEFAULT <= min(SUSPICIOUS_VIG.values())


def test_an_unknown_sport_still_gets_an_alarm():
    got = summarise(_board("kabaddi", picks=[_row(vig=0.01)]))
    assert got["floor"] == SUSPICIOUS_DEFAULT
    assert got["suspicious"]


def test_a_two_way_zero_is_not_mistaken_for_a_short_board():
    """An exact de-vig reports no one-sided overround, and zero is not a
    suspiciously small number there — it is the absence of one."""
    got = summarise(_board(picks=[_row(vig=0.0, source="two-way")]))
    assert not got["suspicious"]
    assert verdict(got)[0] == "READY"


# --- the verdict ----------------------------------------------------------
def test_a_fully_measured_board_is_ready():
    got = summarise(_board(picks=[_row(), _row("B", vig=0.28)]))
    state, why = verdict(got)
    assert state == "READY"
    assert why == ["every priced row got a real de-vig"]


def test_a_board_that_predates_the_field_says_so_rather_than_passing():
    """The most likely way this check gets misread: running it against a
    board built before the deploy. It has to name that, not shrug."""
    state, why = verdict(summarise(_board(picks=[{"player": "A"}])))
    assert state == "NOT WIRED"
    assert any("predates" in w for w in why)


def test_an_empty_board_is_not_a_pass():
    state, why = verdict(summarise(_board()))
    assert state == "NO BOARD"
    assert "READY" not in state


def test_falling_back_is_reported_without_being_called_broken():
    """A thin market legitimately falls back — it is what ran before any
    of this — so it needs a human to look, not an alarm."""
    got = summarise(_board(picks=[_row(source="assumed", vig=0.06)]))
    state, why = verdict(got)
    assert state == "CHECK"
    assert any("fell back" in w for w in why)
    assert not any("SHORT BOARD" in w for w in why)


def test_a_mixed_board_reports_every_reason_not_just_the_first():
    got = summarise(_board("cfb", picks=[
        _row(source="measured:dk", vig=0.02),
        _row(source="assumed", vig=0.06),
        {"player": "C"}]))
    state, why = verdict(got)
    assert state == "CHECK"
    assert len(why) >= 3


# --- the report -----------------------------------------------------------
def test_the_report_prints_the_suspects_by_name():
    b = _board("cfb", picks=[_row("Bad Price", odds=250, vig=0.01)])
    text = "\n".join(report_lines(b))
    assert "Bad Price" in text
    assert "SHORT-BOARD SUSPECTS" in text
    assert "CHECK" in text


def test_the_report_survives_a_row_missing_everything():
    """A malformed row must not crash the preflight — a check that dies
    on bad input is a check that stops running."""
    b = _board(picks=[{}, None, "nonsense"])
    assert report_lines(b)
    assert summarise(b)["unknown"] == 1          # the dict; the rest dropped


def test_the_report_states_the_verdict_last():
    lines = report_lines(_board(picks=[_row()]))
    assert "READY" in lines[-2]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
