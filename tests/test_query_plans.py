"""The joins that read history must stay indexed.

A six-season MLB backfill turned a working build into a 180-second timeout.
Nothing about the queries changed — the tables got 10x bigger and two joins
key on ``(sport, period, ...)``, which is not a prefix of either table's
primary key (those lead with ``season``). SQLite quietly fell back to
matching on ``sport`` alone and re-scanned the whole context table once per
log row. Measured: one platoon-split call went from 1.5 seconds to over ten
minutes.

That failure is invisible in a small test DB — every plan is fast when the
table has forty rows — so these tests read the query PLAN instead of the
clock. If a future schema change drops an index or a query grows a new join
key, the plan degrades to a bare ``sport=?`` search and this fails, on a
tiny fixture, in a second.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.db import connect


def _plan(conn, sql, args=()):
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args)]


def _searches(plan):
    """{table alias: the index terms SQLite matched on}."""
    out = {}
    for line in plan:
        if not line.startswith("SEARCH "):
            continue
        alias = line.split()[1]
        terms = line[line.index("(") + 1:line.rindex(")")] if "(" in line else ""
        out[alias] = terms
    return out


def test_platoon_join_matches_on_the_full_key():
    """`platoon_splits` joins each hitter's log to the opposing starter."""
    conn = connect(":memory:")
    sql = ("SELECT l.player, l.value, s.throws FROM player_game_logs l "
           "JOIN game_starters s ON s.sport=l.sport AND s.period=l.period "
           "  AND s.team=l.opponent "
           "WHERE l.sport='mlb' AND l.market=? AND s.throws IN ('L','R')")
    hits = _searches(_plan(conn, sql, ("total_bases",)))
    assert "s" in hits, "the starters side must be an indexed SEARCH, not a SCAN"
    for col in ("sport", "period", "team"):
        assert col in hits["s"], (
            f"game_starters join fell back to {hits['s']!r} — without {col} "
            f"this re-scans every starter row once per log row")


def test_umpire_join_matches_on_the_full_key():
    """`umpire_profiles` joins ump -> starter -> that starter's K log."""
    conn = connect(":memory:")
    sql = ("SELECT u.umpire, l.value FROM game_umpires u "
           "JOIN game_starters s ON s.sport=u.sport AND s.period=u.period "
           "  AND s.game_id=u.game_id "
           "JOIN player_game_logs l ON l.sport=u.sport AND l.period=u.period "
           "  AND l.player=s.pitcher AND l.market='strikeouts' "
           "WHERE u.sport=? AND u.umpire != ''")
    hits = _searches(_plan(conn, sql, ("mlb",)))
    for alias, need in (("s", ("period", "game_id")),
                        ("l", ("period", "player"))):
        assert alias in hits, f"{alias} must be an indexed SEARCH"
        for col in need:
            assert col in hits[alias], (
                f"{alias} matched only on {hits[alias]!r} — missing {col}")


def test_season_bound_history_read_uses_an_index():
    """The NBA/WNBA live history read, bounded to recent seasons."""
    conn = connect(":memory:")
    sql = ("SELECT player, team, position, period, market, value "
           "FROM player_game_logs WHERE sport=? AND team IN (?,?) "
           "AND season IN (?,?) ORDER BY period DESC")
    hits = _searches(_plan(conn, sql, ("nba", "BOS", "MIA", 2026, 2025)))
    assert hits, "expected an indexed SEARCH, got a full table SCAN"
    assert any("season" in t for t in hits.values()), (
        "the season bound must reach an index — otherwise it filters rows "
        "the query already paid to read")


def test_the_injury_quote_lookup_searches_on_the_time_column():
    """THE THIRTEEN MINUTES. Ethan, 2026-09-19: the first run of
    `homecheck.py data` on the droplet was still going after thirteen
    minutes and had to be killed.

    `odds_history`'s primary key leads (sport, taken_at, ...), and the
    lookup asked for `sport=? AND player=?` — `taken_at` sits between the
    two columns named, so that is not a prefix of the index and SQLite
    scanned the table. Once per injury filing, a few thousand filings,
    over months of quotes.

    This reads `injurylag.QUOTE_SQL` itself rather than a copy, because a
    test that checks a query it wrote proves only that the test is
    indexed."""
    from engine import injurylag
    conn = connect(":memory:")
    hits = _searches(_plan(conn, injurylag.QUOTE_SQL,
                           ("nfl", "2026-09-13 12:00:00",
                            "2026-09-15 12:00:00", "A Back",
                            injurylag.MAX_QUOTES)))
    assert hits, ("odds_history is a full table SCAN — this is the read "
                  "that took thirteen minutes on the droplet")
    terms = hits.get("odds_history", "")
    # BOTH, and the second one is the half-fix that cost another five
    # minutes. Bounding `taken_at` alone lands on the primary key, whose
    # range over (sport, taken_at) is every quote taken for that sport
    # that day — every player, every market, every book — read once per
    # injury filing. `player` is what makes it a handful of rows.
    for col in ("taken_at", "player"):
        assert col in terms, (
            f"matched only on {terms!r} — without {col} this reads far "
            f"more of the table than the filing needs")



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
