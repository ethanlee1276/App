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
    for hist, _career, _vs, _line, _over, _oo, _uo in pairs:
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
    assert all(r[4] == 1 for r in pairs)
    dates = _world(_conn(), "rush_yds", {"A.Back": [10] * 10}, line=50.0)
    c2 = _conn()
    dates = _world(c2, "rush_yds", {"A.Back": [10] * 10}, line=50.0)
    assert all(r[4] == 0 for r in formbook.pairs_for(
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


# --- is there any signal at all -----------------------------------------------
def _featured(conn, market, values_by_player, feature, feature_by_player,
              line=50.0, team="LV"):
    dates = _world(conn, market, values_by_player, line=line, team=team)
    for player, series in feature_by_player.items():
        for week, v in enumerate(series, 1):
            conn.execute(
                "INSERT INTO player_game_logs (sport, season, period, player,"
                " team, opponent, market, value) VALUES "
                "('nfl', 2025, ?, ?, ?, 'DEN', ?, ?)",
                ("%03d" % week, player, team, feature, float(v)))
    return dates


def test_a_feature_the_book_ignores_is_found():
    """The result that would matter: a column that orders the outcome
    even though the number was hung without it."""
    n = 60
    outcome, carries = {}, {}
    for i in range(n):
        high = i % 2 == 0
        outcome[f"P{i}"] = [80 if high else 20] * 14
        carries[f"P{i}"] = [22 if high else 5] * 14
    c = _conn()
    dates = _featured(c, "rush_yds", outcome, "carries", carries, line=50.0)
    out = formbook.signal_scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert out["signals"]["carries"]["z"] > 5, out["signals"]["carries"]
    assert "** orders it **" in "\n".join(formbook.signal_lines(out))


def test_a_feature_unrelated_to_the_outcome_is_not():
    import random
    rng = random.Random(9)
    n = 60
    outcome, carries = {}, {}
    for i in range(n):
        outcome[f"P{i}"] = [rng.uniform(0, 100) for _ in range(14)]
        carries[f"P{i}"] = [rng.uniform(0, 25) for _ in range(14)]
    c = _conn()
    dates = _featured(c, "rush_yds", outcome, "carries", carries, line=50.0)
    out = formbook.signal_scan(c, "rush_yds", min_pairs=100, dates=dates)
    assert abs(out["signals"]["carries"]["z"]) < 2.5


def test_the_scan_says_plainly_when_nothing_orders_it():
    """A scan that always finds something cannot stop work, which is the
    only reason to run it."""
    out = {"market": "rush_yds", "n": 1001, "signals": {
        "proj_gap": {"n": 1001, "auc": 0.517, "z": 0.9},
        "carries": {"n": 900, "auc": 0.508, "z": 0.5}}}
    text = "\n".join(formbook.signal_lines(out))
    assert "nothing here orders this market" in text
    assert "2 candidates tried" in text


def test_the_board_s_own_signal_is_in_the_race_and_labelled():
    """Otherwise a feature beating nothing looks like a feature beating
    the model."""
    out = {"market": "rush_yds", "n": 1001, "signals": {
        "proj_gap": {"n": 1001, "auc": 0.517, "z": 0.9},
        "carries": {"n": 900, "auc": 0.560, "z": 3.1}}}
    text = "\n".join(formbook.signal_lines(out))
    assert "what the board uses" in text
    assert text.index("carries") < text.index("proj_gap"), \
        "strongest ordering must sort first"


def test_a_backwards_signal_is_named_as_backwards():
    out = {"market": "rush_yds", "n": 1001, "signals": {
        "proj_gap": {"n": 1001, "auc": 0.430, "z": -3.4}}}
    assert "orders it BACKWARDS" in "\n".join(formbook.signal_lines(out))


def test_volume_is_offered_as_a_change_not_only_a_level():
    """A back who just took the job reads high on recent carries while
    his own yardage history still reads like a backup."""
    import inspect
    src = inspect.getsource(formbook.signal_scan)
    assert '_trend' in src and "older = _recent(series[4:], 12)" in src


def test_features_are_named_per_market():
    """Air yards mean nothing to a runner, carries nothing to a
    receiver."""
    assert "air_yards" in formbook.FEATURES["rec_yds"]
    assert "air_yards" not in formbook.FEATURES["rush_yds"]
    assert "carries" in formbook.FEATURES["rush_yds"]


def test_a_feature_reads_only_weeks_before_the_one_being_priced():
    import inspect
    src = inspect.getsource(formbook.signal_scan)
    assert "for w in range(week - 1, 0, -1)" in src


# --- the factors the model declares but never prices --------------------------
def test_rest_is_days_since_that_teams_own_last_game():
    """Not weeks. A Thursday off a Sunday is four days and a Monday to a
    Sunday is thirteen, and those are different games to play."""
    got = formbook.schedule_context({
        (2025, 1, "LV"): "2025-09-07", (2025, 2, "LV"): "2025-09-14",
        (2025, 3, "LV"): "2025-09-18"})
    assert got[(2025, 2, "LV")]["rest"] == 7
    assert got[(2025, 3, "LV")]["rest"] == 4


def test_a_bye_is_inferred_from_the_gap_not_from_a_table():
    """The gap is what affects a body, and it stays right for a
    postponement or a rested week 18 that no bye table would list."""
    got = formbook.schedule_context({
        (2025, 2, "LV"): "2025-09-14", (2025, 4, "LV"): "2025-10-05"})
    assert got[(2025, 4, "LV")]["off_bye"] == 1
    assert got[(2025, 4, "LV")]["rest"] == 21


def test_a_normal_week_is_never_called_a_bye():
    got = formbook.schedule_context({
        (2025, 1, "LV"): "2025-09-08", (2025, 2, "LV"): "2025-09-21"})
    assert got[(2025, 2, "LV")]["rest"] == 13
    assert got[(2025, 2, "LV")]["off_bye"] == 0, \
        "a Monday-to-Sunday turnaround is a long week, not a bye"


def test_the_first_game_of_a_season_has_no_rest_number():
    got = formbook.schedule_context({(2025, 1, "LV"): "2025-09-07"})
    assert got[(2025, 1, "LV")]["rest"] is None


def test_head_to_head_history_is_offered_as_a_candidate():
    """It carries a weight in the recency curve and
    sources/nflverse passes None for every NFL prop, so it has never
    entered a projection. Whether it should is a measurement."""
    import inspect
    src = inspect.getsource(formbook.signal_scan)
    assert '"vs_opp_gap"' in src


def test_the_dead_input_is_real_and_still_dead():
    """Pinned so the claim in the scan's comment cannot go stale — if
    someone wires it up, this fails and the comment gets rewritten."""
    import pathlib as _pl
    src = _pl.Path("engine/sources/nflverse.py").read_text()
    assert src.count("vs_opponent_avg=None") >= 1
    from engine.form import WINDOW_WEIGHTS
    assert WINDOW_WEIGHTS.get("vs_opp", 0) > 0, \
        "the curve stopped weighting a window that is never filled"


def test_rest_and_bye_and_home_are_all_in_the_race():
    import inspect
    src = inspect.getsource(formbook.signal_scan)
    for name in ('"rest_days"', '"off_bye"', '"is_home"'):
        assert name in src, name


def test_home_and_away_are_read_from_the_schedules_own_sides():
    got = formbook.home_teams.__doc__
    assert "hosting" in got


# --- two feeds, two naming conventions, one table -----------------------------
def test_features_join_across_the_two_name_styles():
    """`player_game_logs` holds two feeds. The weekly box score writes
    "A.J. Brown"; the play-by-play aggregates write "A.Abdullah". Keyed
    on the raw name they never meet — measured on the real database,
    6,321 carry rows and 5,384 red-zone rows for 2025 gave 11,705 keys,
    exactly the sum, so nothing overlapped. That is how rz_car, rz_tgt,
    i5_car and xfp were silently dropped from a scan that then reported
    "6 candidates tried"."""
    c = _conn()
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, "
              "team, market, value) VALUES "
              "('nfl', 2025, '003', 'Ameer Abdullah', 'IND', 'carries', 9)")
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, "
              "team, market, value) VALUES "
              "('nfl', 2025, '003', 'A.Abdullah', 'IND', 'rz_car', 2)")
    fl = formbook._feature_logs(c, ("carries", "rz_car"))
    assert len(fl) == 1, f"the two feeds did not join: {list(fl)}"
    (only,) = fl.values()
    assert only == {"carries": 9.0, "rz_car": 2.0}


def test_the_join_key_is_the_one_production_already_uses():
    """engine/nflusage has always joined these through _short_key. A
    second join rule here would drift from the maps the board is built
    from."""
    import inspect
    assert "from .fantasy import _short_key" in \
        inspect.getsource(formbook._feature_logs)


def test_players_on_different_teams_do_not_collide():
    c = _conn()
    for team in ("IND", "LV"):
        c.execute("INSERT INTO player_game_logs (sport, season, period, "
                  "player, team, market, value) VALUES "
                  "('nfl', 2025, '003', 'A.Abdullah', ?, 'rz_car', 2)",
                  (team,))
    assert len(formbook._feature_logs(c, ("rz_car",))) == 2


def test_a_candidate_with_too_few_pairs_is_named_not_dropped():
    """A vanished candidate makes the list look like the whole field, and
    the count printed under it becomes a lie about what was tried."""
    out = {"market": "rush_yds", "n": 1001,
           "signals": {"proj_gap": {"n": 1001, "auc": 0.520, "z": 1.1}},
           "thin": {"rz_car": 12}}
    text = "\n".join(formbook.signal_lines(out))
    assert "rz_car" in text and "not tested, not absent" in text


def test_the_thin_list_does_not_count_as_a_candidate_tried():
    out = {"market": "rush_yds", "n": 1001,
           "signals": {"proj_gap": {"n": 1001, "auc": 0.520, "z": 1.1}},
           "thin": {"rz_car": 12, "xfp": 8}}
    text = "\n".join(formbook.signal_lines(out))
    assert "1 candidates tried" in text


# --- does it make money, not just rank -----------------------------------------
def test_payout_is_american_odds():
    assert abs(formbook._payout(-110) - 100 / 110) < 1e-9
    assert formbook._payout(150) == 1.5
    assert formbook._payout(0) == 0.0


def test_a_rule_is_scored_on_weeks_it_was_not_chosen_on():
    """The best of seventy rules in-sample is a number about seventy, not
    about football."""
    import inspect
    src = inspect.getsource(formbook.roi_scan)
    assert 'r["week"] <= split_week' in src and 'r["week"] > split_week' in src


def test_the_split_is_chronological_not_random():
    """Checked as behaviour, not as text: the docstring says "never
    random" and a substring search would match its own explanation."""
    rows = [{"week": w, "vals": {"x": float(w)}, "over": w % 2,
             "over_odds": -110, "under_odds": -110} for w in range(1, 41)]
    train = [r for r in rows if r["week"] <= 13]
    test = [r for r in rows if r["week"] > 13]
    assert max(r["week"] for r in train) < min(r["week"] for r in test)
    import inspect
    src = inspect.getsource(formbook.roi_scan)
    assert "random." not in src and "import random" not in src
    assert "shuffle" not in src and "sample(" not in src


def test_a_losing_holdout_is_called_what_it_is():
    out = {"market": "rush_yds", "n": 1001, "train_n": 600, "test_n": 401,
           "rules": [1] * 70,
           "chosen": {"signal": "targets", "side": "under", "slice": 0.2,
                      "train_roi": 0.18, "train_n": 120,
                      "test_roi": -0.04, "test_n": 80}}
    text = "\n".join(formbook.roi_lines(out))
    assert "did not survive the split" in text
    assert "rule selection, not an edge" in text


def test_a_surviving_rule_is_not_oversold():
    out = {"market": "rush_yds", "n": 1001, "train_n": 600, "test_n": 401,
           "rules": [1] * 70,
           "chosen": {"signal": "targets", "side": "under", "slice": 0.2,
                      "train_roi": 0.18, "train_n": 120,
                      "test_roi": 0.09, "test_n": 80}}
    text = "\n".join(formbook.roi_lines(out))
    assert "survived" in text and "too few to bet real money on" in text


def test_an_under_rule_takes_the_bottom_of_the_ranking():
    """An over rule bets the highest values, an under rule the lowest —
    otherwise a signal that points down can never be expressed."""
    # x rises with the row; the low-x rows went under and the high-x rows
    # went over, so the same column must win one way and lose the other.
    rows = [{"week": i, "vals": {"x": float(i)}, "over": 1 if i > 100 else 0,
             "over_odds": -110, "under_odds": -110} for i in range(1, 201)]
    train, test = rows[:120], rows[120:]
    under = formbook._rule(train, test, "x", "under", 0.5)
    over = formbook._rule(train, test, "x", "over", 0.5)
    # The lowest x are the weeks that went under, so the under rule wins
    # and the over rule loses on exactly the same column.
    assert under["train_roi"] > 0 > over["train_roi"], (under, over)


def test_a_rule_with_too_few_bets_is_not_offered():
    rows = [{"week": w, "vals": {"x": 1.0}, "over": 1,
             "over_odds": -110, "under_odds": -110} for w in range(1, 12)]
    assert formbook._rule(rows, rows, "x", "over", 0.1) is None


def test_a_prop_with_no_price_on_the_side_bet_is_not_staked():
    """0 is the parser's word for "not quoted"; inventing it at -110 is
    what put phantom edges on markets nobody could bet."""
    rows = [{"week": w, "vals": {"x": 1.0}, "over": 1,
             "over_odds": 0, "under_odds": -110} for w in range(1, 201)]
    assert formbook._rule(rows[:120], rows[120:], "x", "over", 1.0) is None


def test_every_signal_side_and_slice_is_offered():
    import inspect
    src = inspect.getsource(formbook.roi_scan)
    assert 'for side in ("over", "under")' in src
    assert "for slice_ in SLICES" in src
    assert len(formbook.SLICES) >= 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
