"""Target share, air-yards share and WOPR are scanned against the close.

Ethan, 2026-09-07, on the data a winning model needs: "Player usage data
for props. NFL routes, target share and air yards from Next Gen Stats and
play-by-play, where the model uses snap counts and weekly totals today."

Targets and air yards were already stored per player per week and
already scanned as raw counts. A count is half a signal: eight targets
on a team that threw twenty is a featured role and eight on a team that
threw forty is not, and the book prices the role. This adds the SHARE of
the team's week, and the weighted blend the fantasy literature calls
WOPR, to `formbook.signal_scan` — signals only, scored by AUC against
whether the game beat the closing number, which is the plan's own rule
for how an input earns a place. Routes are not here: no free feed
carries them.

Run directly: `python3 tests/test_usage_shares.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import formbook as F                             # noqa: E402
from engine.backtest import _norm                            # noqa: E402

WEEKS = 14


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, "
              "game_id TEXT, player TEXT, team TEXT, opponent TEXT, position TEXT, "
              "home INTEGER, market TEXT, value REAL)")
    c.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, event_id TEXT, "
              "home TEXT, away TEXT, player TEXT, market TEXT, book TEXT, line REAL, "
              "over_odds INTEGER, under_odds INTEGER)")
    return c


def _log(c, player, team, week, market, value):
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, team, "
              "opponent, market, value) VALUES ('nfl', 2025, ?, ?, ?, 'DEN', ?, ?)",
              ("%03d" % week, player, team, market, float(value)))


def _close(c, player, week, line=50.0):
    c.execute("INSERT INTO odds_history (sport, taken_at, player, market, book, line, "
              "over_odds, under_odds) VALUES ('nfl', ?, ?, 'rec_yds', 'best', ?, -110, -110)",
              (_date(week) + "T17:00:00Z", _norm(player), line))


def _date(week):
    return "2025-09-%02d" % (6 + week)


def _league(c, teams=30, featured_share=0.6, line=50.0, with_air=True, tag=True):
    """Each team: one featured receiver who takes `featured_share` of the
    targets and goes OVER, one depth receiver who takes the rest and
    goes UNDER. Team totals differ by team so a raw count cannot tell
    them apart but a share can."""
    dates = {}
    for t in range(teams):
        team = f"T{t:02d}"
        volume = 20 + t                       # the team's targets that week
        for week in range(1, WEEKS + 1):
            for who, share, yards in ((f"Star {t}", featured_share, 80),
                                      (f"Depth {t}", 1 - featured_share, 20)):
                _log(c, who, team, week, "rec_yds", yards)
                if tag:
                    _log(c, who, team, week, "targets", volume * share)
                    if with_air:
                        _log(c, who, team, week, "air_yards", volume * share * 9)
                _close(c, who, week, line)
            dates[(2025, week, team)] = _date(week)
    return dates


def test_the_share_needs_a_denominator_and_never_invents_one():
    fl = {(2025, 1, "k"): {"targets": 6.0}, (2025, 2, "k"): {"targets": 4.0}}
    totals = {(2025, 1, "LV"): {"targets": 30.0}, (2025, 2, "LV"): {"targets": 0.0}}
    got = F._share_series(fl, totals, "k", 2025, 4, "LV", "targets")
    # Newest first, before week 4: week 3 unknown, week 2 team threw
    # nothing (None, not zero), week 1 is 6/30.
    assert got == [None, None, 0.2], got
    assert F._recent(got) == 0.2


def test_team_totals_are_summed_per_team_week_from_the_rows_own_team():
    c = _conn()
    _log(c, "A", "LV", 3, "targets", 7); _log(c, "B", "LV", 3, "targets", 5)
    _log(c, "C", "DEN", 3, "targets", 9); _log(c, "A", "LV", 4, "targets", 2)
    _log(c, "Z", "", 3, "targets", 99)                       # no team: not a denominator
    got = F._team_totals(c, ("targets",))
    assert got == {(2025, 3, "LV"): {"targets": 12.0}, (2025, 3, "DEN"): {"targets": 9.0},
                   (2025, 4, "LV"): {"targets": 2.0}}, got
    assert F._team_totals(c, ()) == {}


def test_a_share_the_book_ignores_is_found_where_the_count_is_not():
    c = _conn()
    dates = _league(c)
    out = F.signal_scan(c, "rec_yds", min_pairs=100, dates=dates)
    sig = out["signals"]
    for name in ("target_share", "air_share", "wopr"):
        assert sig[name]["z"] > 5, (name, sig.get(name))
        assert sig[name]["auc"] > 0.9
    # The raw count is deliberately confounded by team volume here: a
    # depth receiver on a pass-heavy team out-targets a star on a
    # run-heavy one, so the count orders the outcome far worse than the
    # share of it does.
    assert sig["targets"]["auc"] < sig["target_share"]["auc"] - 0.1, (sig["targets"], sig["target_share"])
    assert F.WOPR_TARGETS == 1.5 and F.WOPR_AIR == 0.7


def test_no_air_yards_on_file_leaves_wopr_thin_rather_than_half_built():
    c = _conn()
    dates = _league(c, with_air=False)
    out = F.signal_scan(c, "rec_yds", min_pairs=100, dates=dates)
    assert out["signals"]["target_share"]["z"] > 5
    assert "air_share" in out["thin"] and "wopr" in out["thin"], out["thin"]
    assert "air_share" not in out["signals"] and "wopr" not in out["signals"]


def test_a_market_without_usage_rows_names_the_shares_as_thin():
    c = _conn()
    dates = _league(c, tag=False)
    out = F.signal_scan(c, "rec_yds", min_pairs=100, dates=dates)
    for name in ("target_share", "air_share", "wopr"):
        assert out["thin"].get(name) == 0, (name, out["thin"])


def test_only_the_receiving_markets_carry_shares():
    assert set(F.SHARE_SIGNALS) == {"rec_yds", "receptions"}
    for m in ("rush_yds", "pass_yds"):
        assert m not in F.SHARE_SIGNALS


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
