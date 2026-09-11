""""Offseason" was being published off a lookback that never happened.

Ethan, 2026-08-31: "why does it say offseason if cfb started yesterday."

The board reaches that word two ways, and both have to be true: zero
games on the date, AND nothing found in the ten days before it. The
second is `_recent_games`, and it returned a bare list — so a lookback
that FAILED and a lookback that found a dormant league produced the same
value, and the build called both of them the offseason.

Its own docstring rationalised exactly that: "a fetch that fails is
skipped by `load_range` itself, which means the honest failure mode here
is 'found nothing' — and that lands on the offseason branch, which is
where an unknown belonged." That is not honest. Publishing OFFSEASON off
a failed fetch asserts something about college football on the strength
of our own failure.

AND ON OPENING WEEKEND THERE WAS A SECOND ROUTE TO THE SAME LIE. The
lookback runs through `parse_scoreboard`, the same parser the slate
uses, which discarded every FBS-vs-FCS game until the `_team_key`
fallback landed. Opening weekend is mostly FBS-vs-FCS. So the Saturday
that showed one game had a lookback that found close to none — and a
successful fetch still read as a dormant league.

Both routes are closed: the parser keeps those games now, and a lookback
that could not run answers None rather than [].

Run directly: `python3 tests/test_cfb_offseason_claim2.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import cfb_build
from engine.sources import cfbdata


def _src(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class _Feed:
    """Stands in for ESPN: some days answer, some raise."""

    def __init__(self, per_day, fail_all=False):
        self.per_day, self.fail_all, self.asked = per_day, fail_all, []

    def __call__(self, date, ttl=None):
        self.asked.append(date)
        if self.fail_all:
            raise RuntimeError("unreachable")
        return {"events": self.per_day.get(date, [])}


def _game(home="BAMA", away="UGA"):
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": home,
                                      "displayName": home, "id": "1"}},
        {"homeAway": "away", "team": {"abbreviation": away,
                                      "displayName": away, "id": "2"}}]}]}


def _lookback(feed):
    import datetime
    old = cfbdata.fetch_scoreboard
    cfbdata.fetch_scoreboard = feed
    try:
        return cfb_build._recent_games(datetime.date(2026, 8, 31), {})
    finally:
        cfbdata.fetch_scoreboard = old


# --- the three states -----------------------------------------------------
def test_a_lookback_that_found_games_returns_them():
    got = _lookback(_Feed({"2026-08-29": [_game()]}))
    assert got is not None and len(got) == 1, got


def test_a_lookback_that_ran_and_found_nothing_returns_an_empty_list():
    """A real dormant league. Empty is the right answer here."""
    assert _lookback(_Feed({})) == []


def test_a_lookback_that_could_not_run_returns_none():
    """THE CASE THAT WAS BEING CALLED OFFSEASON."""
    assert _lookback(_Feed({}, fail_all=True)) is None


def test_none_and_empty_are_distinguishable():
    """They were the same value, which is the whole bug."""
    assert _lookback(_Feed({}, fail_all=True)) is not \
        _lookback(_Feed({}))


def test_one_day_answering_is_enough_to_count_as_having_looked():
    """A partial outage is still a look. Only a total one is unknown."""
    feed = _Feed({})
    real = feed.__call__

    def flaky(date, ttl=None):
        if date.endswith("29"):
            return {"events": []}
        raise RuntimeError("down")
    feed.__call__ = flaky
    assert _lookback(flaky) == []


# --- it does not go through the helper that hides the difference ----------
def test_it_fetches_per_day_rather_than_through_load_range():
    """`load_range` swallows a failed day silently, which is exactly the
    distinction being drawn."""
    import inspect
    src = inspect.getsource(cfb_build._recent_games)
    assert "fetch_scoreboard" in src
    assert "load_range" not in src.split('"""')[2]


# --- the build stops asserting a season state it has not earned ----------
def test_there_is_a_status_for_not_knowing():
    src = _src("cfb_build.py")
    assert 'status="schedule unknown"' in src


def test_the_unknown_branch_comes_before_offseason():
    src = _src("cfb_build.py")
    assert src.index("if recent is None:") < src.index('status="offseason"')


def test_the_note_refuses_to_claim_there_is_no_football():
    src = _src("cfb_build.py")
    assert "not a claim that there is no" in src


def test_the_old_rationalisation_is_quoted_and_refuted():
    """The docstring that argued an unknown belonged on the offseason
    branch is still in the file, and should be — a retired mistake kept
    verbatim next to why it was wrong is how this codebase stops making
    it twice. What must not survive is the claim standing alone."""
    src = _src("cfb_build.py")
    at = src.index("where an unknown belonged")
    nearby = src[at:at + 400]
    assert "That is not honest" in nearby, nearby[:200]


# --- and it reaches the reader --------------------------------------------
def test_the_page_has_words_for_it():
    src = _src(os.path.join("web", "js", "app.js"))
    assert 'state.data.status === "schedule unknown"' in src
    assert "can’t tell what’s on today" in src


def test_the_page_does_not_call_it_an_empty_slate():
    src = _src(os.path.join("web", "js", "app.js"))
    at = src.index('"schedule unknown"')
    branch = src[at:src.index('state.data.status === "not built"', at)]
    # Matched on a fragment that does not straddle a line wrap — the
    # full sentence breaks across two lines in the template.
    assert "not a statement that there" in branch
    assert "Nothing is scheduled" not in branch


def test_the_journal_has_a_word_for_it_too():
    src = _src("launch.py")
    assert 'unknown = ok and "schedule unknown" in tail' in src
    assert "season state unknown" in src


def test_it_prints_even_on_a_quiet_cycle():
    """Production is always quiet; a degraded state gated behind
    `not quiet` reports to nobody."""
    src = _src("launch.py")
    assert "or unreadable or unknown:" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
