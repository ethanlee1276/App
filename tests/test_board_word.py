"""Every sport says whether its board is empty, not just whether it built.

Ethan, 2026-08-31: "cfb and wnba are both not showing picks or live
games." Two sports at once, and nothing in the journal to say which of
them had a feed problem, an empty schedule, or a build that ran fine and
found nothing — because four of the five refreshes printed "refreshed"
the moment the build exited 0, whatever it had written.

THE LESSON WAS LEARNED ONCE AND NOT GENERALISED. `refresh_cfb` was
taught in August to tell an unreachable feed and an empty slate apart
from a real refresh, after exactly this happened on college football's
opening Saturday. MLB, NFL, NBA and WNBA kept the old line. So the one
sport that had already burned someone could describe itself and the
other four could not — and one of the four is what broke next.

That is the same shape as the `likely.build` gate: a rule applied on the
path where the bug was found and nowhere else. A fix that lands in one
of five callers is a fix that will be re-earned four more times.

`_board_word` is now the shared answer, and the game count rides on
every line, because a bare "refreshed" is compatible with every failure
below the fetch.

Run directly: `python3 tests/test_board_word.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

import launch


def _src(name="launch.py"):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _board(games):
    path = os.path.join(tempfile.mkdtemp(), "b.json")
    with open(path, "w") as f:
        json.dump({"games": [{"id": i} for i in range(games)]}, f)
    return path


# --- the four cases -------------------------------------------------------
def test_a_board_with_games_says_how_many():
    """A bare "refreshed" is compatible with every failure below the
    fetch. The count is what makes the line worth reading."""
    assert launch._board_word(_board(3), True) == "refreshed · 3 game(s)"


def test_a_board_that_built_cleanly_and_found_nothing_says_so():
    """THE ONE THAT WAS INVISIBLE. Exit 0, file written, no games — and
    four of five sports called that "refreshed"."""
    assert "EMPTY BOARD" in launch._board_word(_board(0), True)


def test_a_missing_board_is_empty_rather_than_a_crash():
    missing = os.path.join(tempfile.mkdtemp(), "nope.json")
    assert "EMPTY BOARD" in launch._board_word(missing, True)


def test_a_failed_build_is_still_unavailable():
    """Distinct from empty: one is a build that did not finish, the
    other is one that finished with nothing. Different fixes."""
    assert launch._board_word(_board(3), False) == "unavailable"


def test_empty_and_unavailable_are_never_the_same_string():
    assert (launch._board_word(_board(0), True)
            != launch._board_word(_board(0), False))


# --- every sport routes through it ----------------------------------------
def _body(fn):
    """One refresh function's source.

    PARSED, NOT SLICED. The first cut of this searched for the sport's
    name in the file and read 200 characters — which for NFL landed on
    its offseason message, three branches away from the line under test.
    Every brittle-anchor bug this session has the same cause.
    """
    import inspect
    return inspect.getsource(getattr(launch, fn))


def test_all_five_refreshes_use_the_shared_helper():
    """The point of the file. Four of five had their own line and the
    fifth had the lesson."""
    for fn in ("refresh_mlb", "refresh_nfl", "refresh_nba",
               "refresh_wnba", "refresh_cfb"):
        assert "_board_word(" in _body(fn), fn


def test_no_slate_refresh_still_prints_a_bare_refreshed():
    """The exact string that lied. If it comes back, so does the bug.

    SCOPED TO THE FIVE GAME-SLATE BOARDS. Rosters, injuries, standings,
    prediction markets and the UFC card still use the plain line and
    should: they carry no `games` array, so a helper that counts games
    would be answering a question they do not have. That is a real
    remaining gap of a different shape, not this one.
    """
    for fn in ("refresh_mlb", "refresh_nfl", "refresh_nba",
               "refresh_wnba", "refresh_cfb"):
        body = _body(fn)
        assert "'refreshed' if ok else" not in body, fn
        assert '"refreshed" if ok else' not in body, fn


def test_cfb_keeps_the_causes_only_it_can_name():
    """Generalising must not delete what the one taught sport knew.
    Unreachable, nothing-to-keep and unreadable are real distinctions
    CFB can detect and the others cannot."""
    src = _src()
    for phrase in ("kept last board (schedule unreachable)",
                   "EMPTY BOARD — schedule unreachable, nothing to keep",
                   "EMPTY BOARD — feed listed games, parser read none"):
        assert phrase in src, phrase


def test_cfb_falls_through_to_the_shared_helper():
    """Its plain branch is the one that used to say "refreshed"."""
    src = _src()
    assert "_board_word(CFB_OUT, ok))" in src


# --- and the helper is where the reasoning lives --------------------------
def test_the_helper_records_why_it_exists():
    doc = launch._board_word.__doc__ or ""
    assert "refreshed" in doc and "empty" in doc.lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
