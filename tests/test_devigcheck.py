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
    report_lines, board_state, _sport_of, load, full_copy_of,
    MIN_BOARD, fallback_detail, WHY_TEXT,
)


def _board(sport="nfl", picks=(), watch=()):
    return {"sport": sport, "date": "2026-08-29",
            "generated_at": "2026-08-29T12:00:00Z",
            "long_shots": list(picks), "longshot_watch": list(watch)}


def _row(player="A", odds=300, vig=0.22, source="measured:dk", listed=26):
    return {"player": player, "odds": odds, "vig": vig, "vig_source": source,
            "vig_listed": listed}


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
def test_a_short_reference_board_is_flagged_by_its_SIZE():
    """The failure this exists for, caught by the direct evidence. If the
    feed returns a fraction of a game's scorers the sum comes in low and
    so does the hold — and the board size is the fact, where a small vig
    is only a hint."""
    got = summarise(_board("cfb", picks=[_row(listed=MIN_BOARD - 1)]))
    assert len(got["short"]) == 1
    state, why = verdict(got)
    assert state == "CHECK"
    assert any("SHORT BOARD" in w for w in why)
    assert any("fewer than" in w for w in why)


def test_a_full_board_at_an_ordinary_vig_is_not_flagged():
    """The first live college run flagged a 14.1% board as truncated
    because the floor came from the handbook's 28-50% claim. The fitter
    then measured the NFL market at 16.1% and the live college board at
    14-24%, so both published ranges are high and a floor derived from
    them cries wolf on ordinary boards."""
    got = summarise(_board("cfb", picks=[_row(vig=0.141, listed=26)]))
    assert not got["short"] and not got["suspicious"]
    assert verdict(got)[0] == "READY"


def test_the_vig_floor_still_catches_an_impossible_number():
    """Lowered, not removed: a full-looking board reporting a 1% hold
    means something upstream of the sum is wrong."""
    got = summarise(_board("nfl", picks=[_row(vig=0.01, listed=30)]))
    assert len(got["suspicious"]) == 1
    assert any("upstream" in w for w in verdict(got)[1])


def test_the_alarms_sit_below_what_the_market_was_measured_at():
    """They are truncation alarms, not claims about what the hold should
    be. The NFL market measured 16.1% over 3,890 settled closes and live
    college boards ran 14-24%, so a floor anywhere near those numbers
    flags working boards."""
    assert max(SUSPICIOUS_VIG.values()) < 0.141    # the live college low
    assert SUSPICIOUS_DEFAULT <= min(SUSPICIOUS_VIG.values())
    assert 6 < MIN_BOARD < 20                      # above devig.MIN_PRICED


def test_the_report_prints_the_board_size_distribution():
    """So the provisional MIN_BOARD can be set from what the feed really
    returns rather than from a guess about what books do."""
    b = _board("cfb", picks=[_row(listed=n) for n in (9, 26, 26, 31)])
    text = "\n".join(report_lines(b))
    assert "reference board size" in text
    assert "9 low" in text and "31 high" in text


def test_an_unknown_sport_still_gets_an_alarm():
    got = summarise(_board("kabaddi", picks=[_row(vig=0.01, listed=30)]))
    assert got["floor"] == SUSPICIOUS_DEFAULT
    assert got["suspicious"]


# --- why a board fell back ------------------------------------------------
def test_falling_back_names_the_reason_per_game():
    """"Every row fell back" is a symptom, not a diagnosis. Thin menus, a
    missing game line and a wiring fault look identical from the
    published rows and need three different fixes."""
    b = _board("nfl", picks=[_row(source="assumed", vig=0.06, listed=0)])
    b["td_census"] = {"games": 3, "measured": 0, "no_line": 1,
                      "unmeasurable": 2,
                      "boards": [{"game": "BUF/KC", "book": "draftkings",
                                  "listed": 3, "sum": 0.75, "scorers": 4.6,
                                  "why": "thin"},
                                 {"game": "LA/SF", "book": "draftkings",
                                  "listed": 14, "sum": 3.9, "scorers": 4.4,
                                  "why": "no margin"}]}
    lines = fallback_detail(b)
    assert any("no usable spread and total" in ln for ln in lines)
    assert any("BUF/KC" in ln and WHY_TEXT["thin"] in ln for ln in lines)
    assert any("LA/SF" in ln and WHY_TEXT["no margin"] in ln for ln in lines)
    assert any("BUF/KC" in w for w in verdict(summarise(b))[1])


def test_a_board_with_no_census_reports_no_per_game_detail():
    """Absence of a census is not evidence of anything, and inventing
    reasons for it would be worse than staying quiet."""
    assert fallback_detail(_board("nfl", picks=[_row()])) == []


def test_the_per_game_detail_is_capped_and_says_it_was():
    b = _board("nfl", picks=[_row(source="assumed", vig=0.06, listed=0)])
    b["td_census"] = {"games": 20, "measured": 0, "no_line": 0,
                      "boards": [{"game": f"G{i}", "book": "dk", "listed": 2,
                                  "sum": 0.4, "scorers": 4.0, "why": "thin"}
                                 for i in range(20)]}
    lines = fallback_detail(b)
    assert any("12 more game(s)" in ln for ln in lines)


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


# --- why a board is empty -------------------------------------------------
def test_a_slate_with_no_odds_yet_is_not_reported_as_a_failure():
    """The first live run hit exactly this and read like an alarm. Prop
    menus post Thursday or Friday in college and midweek in the NFL; a
    schedule-only board before then has nothing to de-vig and nothing is
    wrong. Calling that "NO BOARD" alongside a genuine break is how a
    check gets ignored."""
    b = _board()
    b["generated_from"] = "schedule-only"
    b["games"] = [{"home": "KC"}]
    state, why = verdict(summarise(b))
    assert state == "NO ODDS YET"
    assert any("prop menus post" in w for w in why)


# --- the paywall ----------------------------------------------------------
def _tree():
    """A checkout with a paywalled public board and the real one behind."""
    import json
    import os
    import tempfile
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "web", "data"))
    os.makedirs(os.path.join(root, "data", "built"))
    pub = os.path.join(root, "web", "data", "cfb.json")
    full = os.path.join(root, "data", "built", "cfb.json")
    with open(pub, "w") as fh:
        json.dump({"sport": "cfb", "date": "2026-08-29",
                   "generated_at": "x", "locked": {"long_shots": 3},
                   "locked_reason": "subscription"}, fh)
    with open(full, "w") as fh:
        json.dump(_board("cfb", picks=[_row()]), fh)
    return root, pub, full


def test_it_follows_a_paywalled_board_to_the_real_one():
    """The first two live runs learned nothing because they read
    web/data/, which engine/gate strips of every priced row. Pointing at
    the public file is the natural thing to do, so it has to work."""
    root, pub, full = _tree()
    board, read, note = load(pub)
    assert read == full
    assert "paywalled" in note
    assert verdict(summarise(board))[0] == "READY"


def test_an_unlocked_board_is_read_where_it_was_given():
    """Following to the private copy is only for a board that is
    actually redacted — otherwise this would silently analyse a
    different file than the one named."""
    import json
    import os
    root, pub, full = _tree()
    with open(pub, "w") as fh:
        json.dump(_board("cfb", picks=[_row("Public", vig=0.30)]), fh)
    board, read, note = load(pub)
    assert read == pub and not note
    assert board["long_shots"][0]["player"] == "Public"
    assert os.path.isfile(full)          # the other copy exists and was ignored


def test_a_locked_board_with_nothing_behind_it_says_which_file_to_open():
    """Reporting "locked: subscription" reads as a finding about the
    board. It is a finding about which file was opened."""
    import os
    root, pub, full = _tree()
    os.remove(full)
    board, read, note = load(pub)
    assert read == pub
    assert "data/built" in note
    state, why = verdict(summarise(board))
    assert state == "PAYWALLED COPY"
    assert "data/built" in why[0]


def test_the_private_copy_is_resolved_relative_to_its_own_checkout():
    """`gate.publish` writes it root-relative for a reason: a run against
    a tree that is not this one must read ITS boards, not this machine's."""
    root, pub, full = _tree()
    assert str(full_copy_of(pub)) == full
    assert str(full_copy_of(pub)).startswith(root)


def test_a_pull_that_never_happened_is_told_apart_from_one_that_found_nothing():
    """Four different things produce an empty touchdown board and they
    need four different answers — the fix is in a different place for
    each."""
    b = _board("cfb")
    b["games"] = [{"home": "a"}]
    b["td_census"] = {"games_quoted": 0, "quoted_players": 0,
                      "quotes_note": "TD quotes: 0 of 0 eligible"}
    assert board_state(b)[0] == "NO SCORER PULL"
    b["td_census"] = {"games_quoted": 3, "quoted_players": 0,
                      "quotes_note": "TD quotes: 3 of 8 eligible"}
    assert board_state(b)[0] == "NO SCORER PULL"
    b["td_census"] = {"games_quoted": 3, "quoted_players": 54,
                      "no_usage": 40, "outside_window": 14,
                      "usage_season": 2025}
    state, why = board_state(b)
    assert state == "PRICED, NONE KEPT"
    assert "40 had no usage logs" in why
    assert "14 sat outside the odds window" in why


def test_without_a_census_it_says_to_rebuild_rather_than_guessing():
    b = _board("cfb")
    b["games"] = [{"home": "a"}]
    state, why = board_state(b)
    assert state == "NO TD MARKET"
    assert "Rebuild" in why


def test_an_empty_board_is_never_a_pass():
    for b in (_board(), dict(_board(), games=[{"home": "a"}])):
        state, _ = verdict(summarise(b))
        assert state != "READY"


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
def test_the_report_prints_the_suspects_by_name_and_by_bucket():
    """Two different problems, listed separately: a board we only saw
    part of, and a full board reporting an impossible number. Lumping
    them together sends the reader to the wrong fix."""
    b = _board("cfb", picks=[_row("Short Board", odds=250, listed=4),
                             _row("Bad Number", odds=250, vig=0.01,
                                  listed=30)])
    text = "\n".join(report_lines(b))
    assert "Short Board" in text and "SHORT BOARDS" in text
    assert "Bad Number" in text and "IMPLAUSIBLE VIG" in text
    assert "listed   4" in text
    assert "CHECK" in text


def test_the_report_survives_a_row_missing_everything():
    """A malformed row must not crash the preflight — a check that dies
    on bad input is a check that stops running."""
    b = _board(picks=[{}, None, "nonsense"])
    assert report_lines(b)
    assert summarise(b)["unknown"] == 1          # the dict; the rest dropped


# --- reading a board that was not built for this check --------------------
def test_it_finds_the_build_time_whatever_the_board_calls_it():
    """The NFL payload stamps `built_at` and the others `generated_at`.
    Printing "?" for a board that plainly says when it was built is the
    check looking broken instead of the board."""
    b = _board(picks=[_row()])
    b.pop("generated_at")
    b["built_at"] = "2026-08-29T13:40:00"
    assert summarise(b)["generated_at"] == "2026-08-29T13:40:00"


def test_it_infers_the_sport_when_the_board_does_not_carry_one():
    """The NFL payload has no `sport` key, and without it the alarm floor
    would silently fall back to the default rather than the NFL's."""
    assert _sport_of({"date": "2026-W01"}) == "nfl"
    assert _sport_of({"sport": "cfb", "date": "2026-08-29"}) == "cfb"
    assert _sport_of({"date": "2026-08-29"}) == ""
    got = summarise({"date": "2026-W01", "long_shots": [_row(vig=0.12)],
                     "longshot_watch": []})
    assert got["sport"] == "nfl"
    assert got["floor"] == SUSPICIOUS_VIG["nfl"]


def test_the_report_states_the_verdict_last():
    lines = report_lines(_board(picks=[_row()]))
    assert "READY" in lines[-2]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
