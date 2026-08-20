"""Three bugs that sat in docs/NEXT.md, and the guard so the list stops going stale.

Ethan, 2026-08-20: "figure out what still needs to be done." `NEXT.md`
had carried three known defects since 2026-08-17 under "found while
fixing the props build, none of them its cause". All three were still
there. Written down is not fixed, and a document is a worse place to keep
a defect than a failing test.

**1. A rate-limited board published EMPTY and reported success.**
`_get_json` turns a 429 into `DataUnavailable`, `_add_prop` caught that
and returned, and `build_live_slate` handed back its games with zero
props. Reproduced below: every game log answering 429 gives games, no
props, no exception — and launch.py records a healthy build over an empty
board. "This is the one on this list that can be silently wrong," said
the note, correctly. A refusal is not an absence; the status is kept now
and an empty board the wire refused raises instead of publishing.

**2. `lineupwatch.py` wrote another module's cache file.** It fetched the
schedule WITHOUT `&hydrate=probablePitcher,venue` and stored it as
`mlb_schedule_{date}.json` — the exact name the builder reads, from a
different URL. `_get_json` keys on the filename and never compares URLs,
so any build inside that 600s TTL got an unhydrated payload: no probable
pitchers, hence no pitcher props at all, and `park="generic"` everywhere.

**3. `mlb_pbp_` was missing from the prune list**, so ~640 KB × ~150
starters a night — roughly 96 MB — accumulated where nothing would ever
delete it. Auditing that turned up more than the one name: `wnba_box_`
was missing while `nba_box_` was present, and every Polymarket prefix and
Rocket Radar's per-mint holder files were absent too.

The third fix is the one that generalises, and `test_every_cache_name_is_classified`
is it. A list somebody must remember to extend is the same failure as a
cache version somebody must remember to bump. Every cache filename in the
source must now be classified as prunable or explicitly kept WITH A
REASON — add a fetch and no classification and the suite fails.

Run directly: `python3 tests/test_cacheclass.py`
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.maintenance import (KEEP_CACHE_PREFIXES,                # noqa: E402
                                PRUNABLE_CACHE_PREFIXES)

ROOT = Path(__file__).resolve().parent.parent

#: Cache filenames are written as f-strings with the key interpolated:
#: `f"mlb_pbp_{game_pk}.json"`. The prefix is everything before the first
#: placeholder — which is exactly what `prune_cache` matches on.
_NAME = re.compile(r'f"([a-z][a-z0-9_]*_)\{')


def _cache_names() -> dict[str, list[str]]:
    """Every cache-file prefix the source writes, and where."""
    out: dict[str, list[str]] = {}
    for path in list((ROOT / "engine").rglob("*.py")) + list(ROOT.glob("*.py")):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in src.splitlines():
            # Only lines that are actually naming a cache file.
            if not re.search(r'(cache_name|CACHE_DIR|fetch_csv|_get_json|'
                             r'fetch_json|cache=)', line):
                continue
            for m in _NAME.finditer(line):
                out.setdefault(m.group(1), []).append(
                    f"{path.relative_to(ROOT)}")
    return out


def _classified(prefix: str) -> bool:
    if any(prefix.startswith(p) or p.startswith(prefix)
           for p in PRUNABLE_CACHE_PREFIXES):
        return True
    return any(prefix.startswith(k) or k.startswith(prefix)
               for k in KEEP_CACHE_PREFIXES)


def test_the_play_by_play_cache_is_prunable_now():
    """The named bug. ~640 KB a game, ~150 starters a night, and nothing
    in the repo would ever have deleted one."""
    assert any(p == "mlb_pbp_" for p in PRUNABLE_CACHE_PREFIXES), \
        "mlb_pbp_ still grows forever"


def test_the_audit_found_more_than_the_one_name():
    """`nba_box_` was in the list and `wnba_box_` was not — the tell that
    the list was assembled by hand rather than derived."""
    for p in ("wnba_box_", "pm_mkt_", "sol_holders_"):
        assert p in PRUNABLE_CACHE_PREFIXES, f"{p} is still unprunable"


def test_paid_and_bulk_caches_are_never_pruned():
    """Two different reasons, both expensive to get wrong: odds requests
    cost real API credits, and the nflverse season files are ~100 MB
    downloads that are bounded anyway — one per season, not one per game."""
    for p in PRUNABLE_CACHE_PREFIXES:
        assert not p.startswith("odds_"), \
            f"{p} would spend paid API credits to refetch"
    for keep in ("odds_", "pbp_", "player_stats_", "depth_charts_"):
        assert keep in KEEP_CACHE_PREFIXES, f"{keep} lost its exemption"
        assert len(KEEP_CACHE_PREFIXES[keep]) > 20, \
            f"{keep} is exempt without saying why"


def test_every_cache_name_is_classified():
    """THE GUARD THAT MAKES THE OTHERS STAY FIXED. A new fetch with no
    classification is a new unbounded cache nobody decided about."""
    unknown = {p: v for p, v in _cache_names().items() if not _classified(p)}
    assert not unknown, (
        "these cache files are neither prunable nor explicitly kept — decide "
        "which, and if kept, say why:\n  "
        + "\n  ".join(f"{p}  ({', '.join(sorted(set(v)))})"
                      for p, v in sorted(unknown.items())))


def test_the_detector_can_fail():
    """A sweep that cannot fail is not a sweep. This is the negative
    control the emoji audit's lesson asks for."""
    assert not _classified("qb_madeup_"), \
        "the classifier accepts a prefix nobody ever listed"
    assert _cache_names(), "the scanner found no cache names at all"


def test_lineupwatch_no_longer_writes_the_builders_file():
    watch = (ROOT / "lineupwatch.py").read_text(encoding="utf-8")
    assert 'f"mlb_schedule_{date}.json"' not in watch, \
        "lineupwatch is writing the builder's cache file again"
    assert "mlb_watchsched_" in watch, "lineupwatch lost its own cache name"
    # And the builder's own two fetches must still agree with each other,
    # because sharing a name is only safe when the URL is the same.
    hydrated = 0
    for f in ("engine/mlb/sources/mlbstats.py", "engine/mlb/sources/statslogs.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        if 'f"mlb_schedule_{date}.json"' in src:
            assert "hydrate=probablePitcher,venue" in src, \
                f"{f} shares mlb_schedule_ without the hydrate"
            hydrated += 1
    assert hydrated >= 1, "nothing reads mlb_schedule_ any more — check this test"


def test_a_refused_board_raises_instead_of_publishing_empty():
    """The reproduction, with the wire saying 429 to every game log.

    Before: games, zero props, no exception, and a successful build in
    the log. After: it refuses, and the message names the status."""
    from engine.sources.fetch import DataUnavailable
    from engine.mlb.sources import statslogs as sl

    props: list = []
    refusals: list = []

    def throttled(*a, **kw):
        raise DataUnavailable("slow down", status=429)

    orig = sl.fetch_game_log
    sl.fetch_game_log = throttled
    try:
        sl._add_prop(props, 123, "A Hitter", "NYY", "BOS", "1B", sl.HITS,
                     2026, 1, "R", refusals=refusals)
    finally:
        sl.fetch_game_log = orig

    assert not props, "a throttled fetch should still add no prop"
    assert refusals == [("A Hitter", sl.HITS, 429)], \
        f"the refusal was swallowed: {refusals}"


def test_a_player_with_no_log_is_still_just_absent():
    """The other half, and the reason this is not simply 'raise on any
    error'. A rookie with no game log is an ordinary empty answer and
    must not look like an outage."""
    from engine.sources.fetch import DataUnavailable
    from engine.mlb.sources import statslogs as sl

    props: list = []
    refusals: list = []

    def missing(*a, **kw):
        raise DataUnavailable("no such player", status=404)

    orig = sl.fetch_game_log
    sl.fetch_game_log = missing
    try:
        sl._add_prop(props, 123, "A Rookie", "NYY", "BOS", "1B", sl.HITS,
                     2026, 1, "R", refusals=refusals)
    finally:
        sl.fetch_game_log = orig
    assert not props and not refusals, \
        f"a 404 was counted as the wire refusing us: {refusals}"


def test_the_refusal_check_needs_both_halves():
    """It fires only when the board is EMPTY and the wire refused. A
    board that lost three props to a blip and still has two hundred is
    not a refused board, and raising there would take a good slate off
    the site."""
    src = (ROOT / "engine" / "mlb" / "sources" / "statslogs.py").read_text(
        encoding="utf-8")
    assert "if refusals and not props:" in src, \
        "the refusal check no longer requires an empty board"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
