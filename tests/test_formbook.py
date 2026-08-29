"""Fitting the recency dial against a book instead of against ourselves.

`engine.formfit` grid-searches the recency curve through `logwalk.walk`,
which prices every game against `logwalk._naive_line` — the player's own
trailing average. So it asks which look-back windows best predict a
number computed from those same windows. The hot end wins because it is
closest to being the same object. On the droplet:

    nfl:rush_yds   dial +1.0 adopted    AUC 0.468 vs a real book, shut
    nfl:rec_yds    dial +1.0            AUC 0.477 vs a real book, shut
    nfl:receptions dial -0.6 adopted    AUC 0.564, the board's only edge
    nfl:pass_yds   dial -0.5 adopted    interior

`engine.propcal` made this repair for the calibrations and the
temperature came back different. `engine.formbook` makes it for the
curve the calibration is applied to, joining game logs straight to
`odds_history` so all twenty-one dial settings cost one pass instead of
twenty-one nine-minute replays.

These tests run on a synthetic book, because the real one lives on the
box that bought it.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import formbook
from engine.backtest import _norm


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, game_id TEXT, player TEXT, team TEXT, "
              "opponent TEXT, position TEXT, home INTEGER, market TEXT, "
              "value REAL)")
    c.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, "
              "event_id TEXT, home TEXT, away TEXT, player TEXT, "
              "market TEXT, book TEXT, line REAL, over_odds INTEGER, "
              "under_odds INTEGER)")
    return c


def _date(week):
    return "2025-09-%02d" % (6 + week)          # one game day per week


def _world(conn, market, values_by_player, line=50.0, team="LV"):
    """One team, one game a week, a close hung on every week."""
    dates = {}
    for player, values in values_by_player.items():
        for week, v in enumerate(values, 1):
            conn.execute(
                "INSERT INTO player_game_logs (sport, season, period, player,"
                " team, opponent, market, value) VALUES "
                "('nfl', 2025, ?, ?, ?, 'DEN', ?, ?)",
                ("%03d" % week, player, team, market, float(v)))
            # NORMALISED ON WRITE, the way the harvester stores it.
            # `db.closing_odds_by_date` keys on the raw stored name and
            # the join looks it up normalised, so the two meet only here.
            # A fixture that skipped this matched nothing and read as
            # "no closes stored" — which is exactly how this would fail
            # in production if the harvester ever stopped normalising.
            conn.execute(
                "INSERT INTO odds_history (sport, taken_at, player, market, "
                "book, line, over_odds, under_odds) VALUES "
                "('nfl', ?, ?, ?, 'best', ?, -110, -110)",
                (_date(week) + "T17:00:00", _norm(player), market,
                 float(line)))
            dates[(2025, week, team)] = _date(week)
    return dates


# --- the join ----------------------------------------------------------------
def test_a_pair_needs_a_close_on_that_players_own_game_date():
    """A week holds a Thursday, a Sunday and a Monday, and those are
    three different closes — so the join is keyed by the team's date."""
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": [40] * 10})
    assert formbook.pairs_for(c, "rush_yds", dates=dates)
    # Same logs, schedule pointing at days nothing was harvested on.
    wrong = {k: "2030-01-01" for k in dates}
    assert formbook.pairs_for(c, "rush_yds", dates=wrong) == []


def test_a_thin_log_is_not_scored():
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": [40] * 10})
    pairs = formbook.pairs_for(c, "rush_yds", dates=dates)
    assert len(pairs) == 10 - formbook.MIN_HISTORY


def test_history_holds_only_games_already_played():
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": list(range(1, 11))})
    pairs = formbook.pairs_for(c, "rush_yds", dates=dates)
    for hist, _career, _vs, _line, _over in pairs:
        assert max(hist) < 10, "a later week leaked into the history"


def test_a_push_is_dropped():
    """Landing exactly on the number decided nothing."""
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": [50] * 10}, line=50.0)
    assert formbook.pairs_for(c, "rush_yds", dates=dates) == []


def test_the_outcome_is_whether_it_beat_the_number():
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": [80] * 10}, line=50.0)
    pairs = formbook.pairs_for(c, "rush_yds", dates=dates)
    assert all(over == 1 for *_r, over in pairs)
    dates = _world(_conn(), "rush_yds", {"A.Back": [10] * 10}, line=50.0)
    c2 = _conn()
    dates = _world(c2, "rush_yds", {"A.Back": [10] * 10}, line=50.0)
    assert all(over == 0 for *_r, over in formbook.pairs_for(
        c2, "rush_yds", dates=dates))


# --- the scan ----------------------------------------------------------------
def _many(pattern, n=60):
    return {f"P{i}": pattern(i) for i in range(n)}


def test_a_thin_market_is_refused_by_name():
    c = _conn()
    dates = _world(c, "rush_yds", {"A.Back": [40] * 10})
    out = formbook.scan(c, "rush_yds", dates=dates)
    assert "book-priced pairs" in out["skipped"]


def test_a_market_with_no_ordering_is_reported_as_such():
    """The result that matters most, because it is the one a dial cannot
    fix. Values independent of anything the history contains."""
    import random
    rng = random.Random(5)
    c = _conn()
    dates = _world(c, "rush_yds",
                   _many(lambda i: [rng.uniform(0, 100) for _ in range(14)]),
                   line=50.0)
    out = formbook.scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert out["n"] >= 100
    best = out["dial"][out["best_auc_r"]]
    assert abs(best["z"]) < 2.0, best
    assert "no dial setting orders this market to significance" in \
        "\n".join(formbook.report_lines(out))


def test_a_market_the_history_really_does_order_is_found():
    """Players who are consistently above or below the number. Any
    sensible curve should rank them, so AUC must clear 0.5 comfortably."""
    c = _conn()
    dates = _world(c, "rush_yds",
                   _many(lambda i: [20 + 60 * (i % 2)] * 14), line=50.0)
    out = formbook.scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert out["dial"][out["best_auc_r"]]["auc"] > 0.9
    assert "no dial setting orders" not in \
        "\n".join(formbook.report_lines(out))
    assert out["dial"][out["best_auc_r"]]["z"] > 5


def test_every_dial_setting_is_scored_on_the_same_pairs():
    """The join happens once; the dial does not get to change which rows
    it is judged on. That was the bug engine/formcheck had."""
    c = _conn()
    dates = _world(c, "rush_yds",
                   _many(lambda i: [20 + 60 * (i % 2)] * 14), line=50.0)
    out = formbook.scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert len({d["n"] for d in out["dial"].values()}) == 1


def test_the_whole_family_is_swept():
    from engine.formfit import GRID
    c = _conn()
    dates = _world(c, "rush_yds",
                   _many(lambda i: [20 + 60 * (i % 2)] * 14), line=50.0)
    out = formbook.scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert set(out["dial"]) == set(GRID)


def test_a_bare_auc_threshold_would_have_called_noise_an_edge():
    """660 synthetic pairs with outcomes independent of the history: the
    best of twenty-one dials read AUC 0.537, over any sane fixed bar and
    1.6 standard errors from nothing. Taking the max of twenty-one noisy
    numbers flatters itself; only the error bar sees that."""
    import inspect
    src = inspect.getsource(formbook.report_lines)
    assert 'abs(d[top].get("z") or 0.0) < 2.0' in src
    # The old bar is named in the comment that explains its removal, so
    # look for it as a live comparison rather than as text.
    assert 'd[top]["auc"] or 0.5) <= 0.52' not in src


def test_the_auc_is_not_a_second_implementation():
    """This statistic already exists in engine/propcal, and two copies
    of one measurement is how they drift apart."""
    import inspect
    assert "from .propcal import discrimination" in \
        inspect.getsource(formbook._auc)


def test_ordering_beats_brier_when_they_disagree():
    """A prop needs a side picked, not a well-behaved average."""
    out = {"market": "rush_yds", "n": 900, "best_brier_r": 0.4,
           "best_auc_r": -0.6,
           "dial": {0.4: {"brier": 0.240, "auc": 0.531, "z": 2.4, "n": 900},
                    -0.6: {"brier": 0.243, "auc": 0.572, "z": 4.1, "n": 900}}}
    text = "\n".join(formbook.report_lines(out))
    assert "ordering is what a prop needs" in text and "-0.6" in text


def test_the_probability_matches_how_the_engine_prices_one():
    """Same blend, same variance floor — otherwise the dial is fitted
    against a model the board does not run, which is the whole mistake
    this file exists to stop repeating."""
    import inspect
    src = inspect.getsource(formbook._prob)
    assert "from .form import compute_form" in src
    assert "CV_FLOOR" in src and "prob_over" in src


def test_it_reads_no_proxy_line_anywhere():
    """The whole point. The docstring NAMES logwalk._naive_line to
    explain what it refuses to use, so look for the import rather than
    the word — matching prose is how a check like this passes or fails
    on how the comment is worded."""
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path(formbook.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("logwalk" in m for m in imported), sorted(imported)
    assert any("db" in m or "backtest" in m for m in imported)
    src = pathlib.Path(formbook.__file__).read_text()
    assert "closing_odds_by_date" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
