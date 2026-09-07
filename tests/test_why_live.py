"""Accounting for every open bet on the Live tab.

"we are only showing live longshots on the live page and not the actual
recommended player props. why is that"

That is a claim about a difference between two sets, and there is no way to
answer it from the code alone — the answer lives in his journal and his
build, neither of which is in this repo. Guessing at someone's data is how
the WNBA diagnosis went wrong ("never ingested" — it had 151,765 rows).

So `--why-live` prints both sets and the decision made about each row. It
reads the board the site is already serving rather than rebuilding it, so
it costs nothing and describes exactly what is on screen.

The trap this had to avoid: a slate written before the tracker existed has
no live_picks at all, and every row would then get a confident,
individually-plausible explanation for an absence that has exactly one
cause. Five different wrong answers is worse than one right one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def _block():
    i = SRC.index("def why_live(")
    return SRC[i:SRC.index("def _near_dates(")]


# --- the trap ---------------------------------------------------------------
def test_a_slate_built_before_the_tracker_says_so_instead_of_explaining():
    """One cause wearing five different explanations is worse than no
    report at all — every line would look individually reasonable."""
    b = _block()
    assert 'if "live_picks" not in d:' in b
    assert "built before the open-bet tracker" in b


def test_the_guard_checks_for_the_key_not_a_truthy_value():
    """An empty live_picks list is a real answer — "nothing is being
    tracked right now" — and must not be confused with a build that never
    tried."""
    b = _block()
    assert 'if "live_picks" not in d:' in b
    assert 'if not d.get("live_picks")' not in b


def test_a_tracker_error_is_surfaced_rather_than_read_as_zero_bets():
    b = _block()
    assert 'd.get("live_picks_error")' in b


# --- it must agree with the thing it is explaining --------------------------
def test_it_builds_the_index_the_same_way_the_tracker_does():
    """A report that disagrees with the code it describes is worse than
    none. Both key on normalized name + market, and both let the main board
    win a collision."""
    b = _block()
    assert "normalize_name" in b
    assert "idx.setdefault(" in b, "long shots must not overwrite the main board"


def test_it_uses_the_same_neighbouring_day_window_as_the_tracker():
    b = _block()
    assert "_near_dates(date)" in b
    from launch import _near_dates
    assert _near_dates("2026-08-01") == {"2026-07-31", "2026-08-02"}


def test_the_day_window_survives_a_month_boundary():
    from launch import _near_dates
    assert _near_dates("2026-08-31") == {"2026-08-30", "2026-09-01"}
    assert _near_dates("2026-01-01") == {"2025-12-31", "2026-01-02"}


def test_a_non_calendar_date_does_not_crash_the_report():
    """NFL journals weeks like "2026-W1"."""
    from launch import _near_dates
    assert _near_dates("2026-W1") == set()


# --- the question actually asked --------------------------------------------
def test_it_answers_the_player_prop_question_directly():
    """The report exists because of one question. It should end by
    answering that question in a sentence, not leave it to be counted off a
    table."""
    b = _block()
    assert "category 'main'" in b
    assert "main_open" in b and "main_shown" in b


def test_zero_open_props_is_stated_as_a_cause_not_left_blank():
    """The main board journals a prop only when it is recommended AND
    staked above zero. On a thin night that is one or two picks — and an
    empty list then means "there were none", not "they were hidden"."""
    b = _block()
    assert "if main_open == 0:" in b
    assert "RECOMMENDED" in b


def test_buckets_that_are_never_tracked_say_so_rather_than_looking_broken():
    """longshot_watch is a calibration sample of every priced homer on the
    slate — 100+ names. It is excluded on purpose and the report has to
    distinguish that from a failure."""
    b = _block()
    assert "not eligible for the Live tab by design" in b
    assert "bucket is not tracked live" in b


def test_it_never_writes_to_the_journal():
    """A diagnostic that mutates is not a diagnostic. This runs against a
    live journal mid-slate."""
    b = _block()
    for verb in ("INSERT", "UPDATE", "DELETE", "commit()"):
        assert verb not in b, f"why_live performs a {verb}"


def test_it_is_wired_to_a_flag():
    assert 'if "--why-live" in argv:' in SRC
    assert "why_live(who)" in SRC


def test_it_defaults_to_baseball_but_takes_a_sport():
    b = SRC[SRC.index('if "--why-live" in argv:'):][:400]
    assert '"mlb")' in b
    assert "argv[i + 1:]" in b


def test_the_same_player_in_two_buckets_is_two_different_rows():
    """Ethan's journal held Sal Stewart's homer as BOTH a long shot and a
    stale-line flag. Matching on name+market alone reported the excluded
    stale row as "SHOWN — tracking (live)" — a confident wrong line, in the
    report whose entire job is not producing those."""
    b = _block()
    assert "def _key(r):" in b
    assert 'r.get("category", "main")' in b
    # ...and the board index stays a two-part key, because the boards do
    # not have categories.
    assert "idx_key = key[:2]" in b


def test_the_tracker_emits_the_bucket_so_the_report_can_use_it():
    from engine.livepicks import assemble_live_picks
    game = {"home": "PHI", "away": "CHC", "game_number": 1,
            "date": "2026-08-01",
            "live": {"state": "live", "home_score": 1, "away_score": 0}}
    pick = {"player": "A B", "team": "PHI", "opponent": "CHC",
            "market": "home_runs", "market_label": "Home Runs"}
    bet = {"player": "A B", "market": "home_runs", "side": "OVER",
           "line": 0.5, "odds": 400, "stake_units": 0.1,
           "category": "longshot"}
    rows = assemble_live_picks([bet], [], [game], {}, [pick])
    assert rows[0]["category"] == "longshot"


def test_an_unmappable_bet_still_carries_its_bucket():
    """The unmapped path builds its row separately and used to drop every
    field the mapped path added."""
    from engine.livepicks import assemble_live_picks
    bet = {"player": "Nobody", "market": "hits", "side": "OVER", "line": 1.5,
           "odds": -110, "stake_units": 1.0, "category": "loose"}
    rows = assemble_live_picks([bet], [], [], {})
    assert rows[0]["status"] == "unmapped"
    assert rows[0]["category"] == "loose"


def test_a_bet_with_no_bucket_recorded_defaults_to_the_main_board():
    from engine.livepicks import assemble_live_picks
    bet = {"player": "Nobody", "market": "hits", "side": "OVER", "line": 1.5,
           "odds": -110, "stake_units": 1.0}
    rows = assemble_live_picks([bet], [], [], {})
    assert rows[0]["category"] == "main"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
