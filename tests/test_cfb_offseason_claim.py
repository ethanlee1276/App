"""An empty date is not the offseason, and only one of them is a fact.

Ethan, 2026-08-30, chasing why CFB went dark on the opening Saturday:

    generated_at 2026-08-30T14:55:14  date 2026-08-30
    0 games  0 recs  status: offseason

The build was running fine — the board was minutes old. It had fetched
the schedule, got nothing back for that date, and published
`status: "offseason"` with a note saying the engine "goes live with the
schedule". The day AFTER the college football season opened.

Zero games on a Sunday in week 1 may well be correct. "Offseason" is not
a report of that; it is an INTERPRETATION of it, asserted as a fact, in
the one field a reader checks when a board is empty — and it is the
interpretation that tells them to stop looking until September.

An empty fetch has at least three causes: genuinely no games that day, a
quiet date inside a running season, or a feed that answered with
nothing. The build can separate the first two from data it already pays
for — every successful build fetches RESULT_WINDOW_DAYS of history, so
those days sit in the same 24-hour scoreboard cache.

Run directly: `python3 tests/test_cfb_offseason_claim.py`
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cfb_build                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as fh:
        return fh.read()


def _branch():
    src = _src()
    i = src.index("    if not games:")
    return src[i:src.index("    priced, odds_note", i)]


# --- the two answers ------------------------------------------------------
def test_a_quiet_date_in_a_running_season_is_not_called_the_offseason():
    body = _branch()
    assert 'status="no games today"' in body
    assert "not the offseason" in body
    # And it says what it found, so the claim can be checked rather than
    # trusted: how many games, and when the last one was.
    assert "most recently {last}" in body


def test_a_genuine_offseason_still_says_so():
    """The other direction. A Tuesday in June must not start claiming the
    season is running — that would be the same failure reversed."""
    body = _branch()
    assert 'status="offseason"' in body
    assert "none in the last" in body


def test_the_offseason_claim_now_names_the_evidence_behind_it():
    """It used to assert the offseason from `not games` alone. Now it
    says it also looked back and found nothing, which is a checkable
    statement rather than a conclusion."""
    body = _branch()
    i_recent = body.index("_recent_games(day, lookup)")
    i_off = body.index('status="offseason"')
    assert i_recent < i_off, "the offseason branch must run AFTER the lookback"


# --- the lookback ---------------------------------------------------------
def test_the_lookback_spans_a_bye_week():
    assert cfb_build.NEARBY_DAYS >= 8, cfb_build.NEARBY_DAYS


def test_a_failed_lookback_is_no_longer_reported_as_an_empty_league():
    """SUPERSEDED 2026-08-31, and the old contract is worth stating.

    This test used to assert `got == []` and was named "falls back to the
    old answer not a new wrong one", on the reasoning that a dead feed
    landing on the offseason branch was "exactly where an unknown landed
    before this existed. No new way to be wrong."

    That reasoning was wrong, and Ethan found it from the page: "why does
    it say offseason if cfb started yesterday." Landing an unknown on the
    offseason branch IS a way to be wrong — it publishes a claim about
    college football on the strength of a fetch we could not make. Not a
    NEW way, which is what the old note actually established, and a bug
    that predates a fix is still a bug.

    So the lookback is tri-state now: games, no games, or could not look.
    See tests/test_cfb_offseason_claim2.py for the full shape."""
    def boom(*_a, **_k):
        raise RuntimeError("feed down")

    real = cfb_build.cfbdata.fetch_scoreboard
    cfb_build.cfbdata.fetch_scoreboard = boom
    try:
        got = cfb_build._recent_games(datetime.date(2026, 8, 30), {})
    finally:
        cfb_build.cfbdata.fetch_scoreboard = real
    assert got is None, got


def test_the_lookback_asks_for_the_ten_days_before_the_date_not_after():
    """Forward-looking would call the day before a season opener "running",
    which is not what the word means and is not what an empty board on
    that day should say."""
    # Re-expressed against the per-day fetch `_recent_games` uses now
    # (it stopped calling `load_range`, which hid a failed day). Checking
    # every date rather than the two endpoints is the stronger form of
    # the same contract.
    seen = []

    def spy(date, ttl=None):
        seen.append(date)
        return {"events": []}

    real = cfb_build.cfbdata.fetch_scoreboard
    cfb_build.cfbdata.fetch_scoreboard = spy
    try:
        cfb_build._recent_games(datetime.date(2026, 8, 30), {})
    finally:
        cfb_build.cfbdata.fetch_scoreboard = real
    assert seen, "the lookback asked for nothing"
    assert max(seen) == "2026-08-29", seen        # the day before, not after
    assert min(seen) == "2026-08-20", seen
    assert "2026-08-30" not in seen, "asked about the date itself"
    assert "2026-08-31" not in seen, "asked about the future"


def test_the_lookback_is_cheap_because_the_cache_is_already_warm():
    """Keyless and cached for 24 hours, and every successful build
    already fetches a 14-day results window over the same days. On a true
    offseason date this costs ten requests a day, not ten a cycle."""
    src = _src()
    block = src[src.index("def _recent_games("):]
    block = block[:block.index("\ndef ")]
    # It fetches per day now rather than through `load_range` — that
    # helper swallows a failed day, which is the distinction the tri-state
    # exists to draw. The COST argument is unchanged: the same keyless,
    # 24-hour-cached scoreboard call either way.
    assert "cfbdata.fetch_scoreboard" in block
    assert "cfbdata.load_range" not in block
    assert "NEARBY_DAYS" in block
    # No ttl override: it takes load_range's 24h default deliberately.
    assert "ttl=" not in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
