"""The feature harness reaches college, on college's own chain.

#71. `engine.tdfeatures` asks "does candidate feature X add anything to
the touchdown model", and it could only ask it of the NFL. The blocker
was small and dull: `cfbtdfit.Sample` carried no player identity — its
slots stopped at the team — and every within-team question is a question
about a person. The name was in scope in `samples` the whole time.

TWO THINGS THIS FILE GUARDS, and they are the two ways the extension
could have produced a confident wrong answer.

ONE: THE RIGHT MODEL. The probability a candidate is scored against has
to come from the chain that ships for that sport. `tdbacktest` replays
`engine.touchdowns`; college ships `engine.cfb.tds`, replayed by
`cfbtdfit`. Running one against the other's logs grades a model nobody
runs — done once on 2026-08-30, and it produced a confident table
showing the college calibration failing badly when on the real chain the
same bands are sound.

TWO: THE RIGHT COLUMNS. The NFL feed logs `targets` and `i5_car`.
College logs neither. Reading the NFL names against college rows does
NOT raise — every lookup returns 0.0, the candidate takes a share of
nothing, and the harness prints a flat AUC as though the feature had
been measured and found small. A negative result indistinguishable from
a wiring fault is worse than no result, so a candidate whose input this
feed does not publish is refused and labelled, never scored on zeros.

THE ANSWER, for the record: none of the candidates add anything in
college either — the same null the NFL returned, from a different model
over different columns, which is worth more than either table alone.

Run directly: `python3 tests/test_cfbfeatures.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import cfbtdfit, tdfeatures as F


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- the blocker ----------------------------------------------------------
def test_a_college_sample_carries_who_it_is():
    """The whole of what kept this NFL-only."""
    assert "player" in cfbtdfit.Sample.__slots__


def test_it_also_carries_the_window_it_was_built_from():
    """A candidate that recomputes its own history is comparing two
    histories and calling the difference a signal."""
    assert "prior_periods" in cfbtdfit.Sample.__slots__


def test_the_sample_defaults_do_not_force_every_caller_to_change():
    s = cfbtdfit.Sample(season=2024, position="RB", share=0.2, td_mean=0.3,
                        games=4, scored=0)
    assert s.player == "" and s.prior_periods == ()


def test_the_builder_fills_them():
    src = _src("engine", "cfbtdfit.py")
    assert "player=player, prior_periods=prior," in src


# --- the right model ------------------------------------------------------
def test_college_rows_come_from_the_college_replay():
    src = _src("engine", "tdfeatures.py")
    at = src.index("def graded_rows(")
    body = src[at:src.index("def evaluate(", at)]
    assert "cfbtdfit.run(conn, collect=rows.append)" in body
    assert 'if (sport or "").lower() == "cfb":' in body


def test_the_nfl_replay_still_refuses_college():
    """The guard that made the wrong answer impossible stays up; this
    extension routes around it rather than removing it."""
    from engine import tdbacktest
    import sqlite3
    try:
        tdbacktest.run(sqlite3.connect(":memory:"), "cfb")
    except Exception as exc:
        assert "cfb" in str(exc).lower() or "nfl" in str(exc).lower(), exc
    else:
        raise AssertionError("tdbacktest.run accepted cfb")


def test_the_college_replay_emits_the_shape_the_harness_reads():
    """Same keys as `tdbacktest.run`'s collect, or the candidates read
    None from every row and report nothing at full confidence."""
    src = _src("engine", "cfbtdfit.py")
    at = src.index("if collect is not None:")
    body = src[at:at + 900]
    for key in ("season", "week", "player", "team", "prob", "scored",
                "opp_share", "rz_share", "prior_weeks"):
        assert f'"{key}"' in body, key


# --- the right columns ----------------------------------------------------
def test_each_sport_declares_its_own_touch_columns():
    assert F.touch_markets("nfl") == ("targets", "carries")
    assert F.touch_markets("cfb") == ("receptions", "carries")


def test_college_has_no_inside_five_column():
    assert F.GOAL_LINE_MARKET["cfb"] is None
    assert F.GOAL_LINE_MARKET["nfl"] == "i5_car"


def test_the_goal_line_candidate_refuses_college_rather_than_zeroing():
    """The trap: `i5_car` against college rows returns 0.0 everywhere,
    so the feature would score a share of nothing and print a flat AUC
    as though it had been tested."""
    ctx = {"goal_line_market": None, "qb_i5": {}, "team_week": {}}
    assert F.quarterback_goal_line({"prior_weeks": ["1"], "season": 2024,
                                    "team": "T"}, ctx) is None


def test_the_goal_line_candidate_still_runs_for_the_nfl():
    ctx = {"goal_line_market": "i5_car",
           "qb_i5": {(2024, "T"): {"1": 3.0}},
           "team_week": {(2024, "1", "T"): {"i5_car": 10.0}}}
    got = F.quarterback_goal_line({"prior_weeks": ["1"], "season": 2024,
                                   "team": "T"}, ctx)
    assert abs(got - 0.3) < 1e-9, got


def test_no_candidate_hardcodes_a_column_name_any_more():
    """The one way this regresses: someone types "targets" back in and
    college silently measures zeros again."""
    src = _src("engine", "tdfeatures.py")
    at = src.index("def usage_trend(")
    body = src[at:src.index("def quarterback_goal_line(", at)]
    assert '"targets"' not in body and '"i5_car"' not in body, body


def test_the_context_is_built_from_the_sports_own_columns():
    src = _src("engine", "tdfeatures.py")
    at = src.index("def context(conn, sport: str)")
    body = src[at:src.index("def graded_rows(", at)]
    assert "touch_markets(sport)" in body
    assert "GOAL_LINE_MARKET.get(sport)" in body


# --- unavailable is not thin ----------------------------------------------
def test_zero_usable_rows_reports_unavailable_not_thin():
    """Opposite meanings. "Thin" says it was measured on too little;
    "unavailable" says it could not be built here at all, and reporting
    both the same way invites reading an untested candidate as tested."""
    got = F.evaluate([{"scored": 0, "prob": 0.2}], lambda r, c: None, {})
    assert got["unavailable"] is True and got["rows"] == 0


def test_a_thin_but_real_sample_is_still_called_thin():
    got = F.evaluate([{"scored": 0, "prob": 0.2}], lambda r, c: 1.0, {})
    assert got.get("thin") is True and got.get("unavailable") is None


def test_the_report_prints_the_two_differently():
    src = _src("engine", "tdfeatures.py")
    assert "not in this feed" in src
    assert "too thin to score" in src


# --- the finding is written down ------------------------------------------
def test_the_college_measurement_is_recorded_beside_the_nfl_one():
    src = _src("engine", "tdfeatures.py")
    assert "29,047 graded" in src
    assert "0.6704" in src and "0.6756" in src


def test_the_docstring_no_longer_claims_the_file_is_nfl_only():
    src = _src("engine", "tdfeatures.py")
    head = src[:src.index('"""', 3)]
    assert "NFL ONLY" not in head
    assert "BOTH SPORTS" in head


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
