"""The college props were priced with no correction at all, and it showed.

The first live college prop board (2026-09-04) priced 22 props and
recommended none of them. Every one was `grade=Pass`, and the comps said
why on the row itself:

    model says 63% but 4,852 similar past spots went 80% to the under
    model says 64% but 3,002 similar past spots went 83% to the under
    model says 61% but 2,977 similar past spots went 81% to the under

Every one an UNDER, every one with the comps saying the model understated
it. That is a distribution pulled toward 50%, and it produces edges
(0.10-0.17) that sail past `betting.MAX_CREDIBLE_EDGE` — so a market
priced without a correction does not merely price badly, it prices
itself off the board.

THE CAUSE WAS A TABLE, not a model. `formfit`, `playerfit` and
`calibrate` each carry a `SPORT_MARKETS` dict, `--sport` validates
against it, and all three left college out with the same sentence:
"College is priced at GAME level (spread / total / moneyline) and has no
player-prop logs to walk." True when written; false since
`engine/cfb/props.py`. So `calibrate.correction_for("cfb", …)` returned
the neutral (1.0, 0.0) on every college prop ever priced — the same
shape of gap `engine.rankfit.MARKETS` had, closed the same way.

Run directly: `python3 tests/test_cfb_calibration.py`
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CFB_MARKETS = ["pass_yds", "rush_yds", "rec_yds", "receptions"]


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- every fitter can now reach college -------------------------------
def test_all_three_fitters_list_college():
    """`--sport` validates against each module's own table, so a sport
    missing from any one of them cannot be fitted by that fitter."""
    import calibrate, formfit, playerfit
    for mod in (formfit, playerfit, calibrate):
        assert mod.SPORT_MARKETS.get("cfb") == CFB_MARKETS, mod.__name__


def test_the_stale_reason_is_gone_from_all_three():
    for name in ("formfit.py", "playerfit.py", "calibrate.py"):
        src = _src(name)
        assert "has no player-prop logs to walk" not in src, name


def test_ufc_stays_out_because_its_reason_still_holds():
    """The table is not a free-for-all: UFC has no game logs at all, so
    listing it would offer a fit that can never run."""
    import calibrate, formfit, playerfit
    for mod in (formfit, playerfit, calibrate):
        assert "ufc" not in mod.SPORT_MARKETS, mod.__name__


def test_the_markets_fitted_are_the_markets_built_and_measured():
    import calibrate
    from engine import rankfit
    from engine.cfb import props
    assert set(calibrate.SPORT_MARKETS["cfb"]) == set(rankfit.MARKETS["cfb"])
    assert set(calibrate.SPORT_MARKETS["cfb"]) == set(props.MARKETS)


# --- and the fit actually runs on college logs ------------------------
def _logs(market="rush_yds", players=160, games=28, seed=17):
    rnd = random.Random(seed)
    rows = []
    for i in range(players):
        skill = 20 + i * 0.7
        for g in range(games):
            rows.append({
                "sport": "cfb", "season": 2025 + g // 14,
                "period": f"2025-09-{g + 1:02d}", "game_id": f"g{i}-{g}",
                "player": f"Back {i}", "team": "AAA", "opponent": "BBB",
                "position": "RB", "home": g % 2, "market": market,
                "value": max(0.0, rnd.gauss(skill, skill * 0.55)),
            })
    return rows


def test_fit_market_walks_college_logs_and_returns_a_calibration():
    from calibrate import fit_market
    from engine import db
    d = tempfile.mkdtemp(prefix="cfb-cal-")
    os.environ.setdefault("QB_MODELS_DIR", os.path.join(d, "models"))
    conn = db.connect(os.path.join(d, "history.db"))
    db.upsert_player_logs(conn, _logs())
    got, err = fit_market(conn, "rush_yds", None, 200, sport="cfb")
    assert err is None, err
    c, _report = got
    assert c.samples >= 200
    assert c.temperature > 0


def test_a_college_market_with_no_logs_is_skipped_not_invented():
    from calibrate import fit_market
    from engine import db
    d = tempfile.mkdtemp(prefix="cfb-cal-")
    conn = db.connect(os.path.join(d, "history.db"))
    got, err = fit_market(conn, "rec_yds", None, 200, sport="cfb")
    assert got is None and err


def test_the_deep_refit_will_pick_college_up_by_itself():
    """`deepfit.sports_with_history` reads formfit's table, so adding
    college there is what puts it in the weekly pass — no second list."""
    from engine import deepfit
    import inspect
    src = inspect.getsource(deepfit.sports_with_history)
    assert "from formfit import SPORT_MARKETS" in src
    assert deepfit.REFIT_ORDER == (("recency dial", "formfit.py"),
                                   ("player memory", "playerfit.py"),
                                   ("temperatures", "calibrate.py"))


# --- counts.recommended means the same thing on every board -----------
def test_recommended_counts_props_not_game_bets():
    """It counted game bets on college alone, so the one key named the
    same thing on five boards meant something else on the sixth — and it
    read low the moment college gained props to recommend."""
    src = _src("cfb_build.py")
    assert '"recommended": sum(1 for r in _built\n' in src \
        or '"recommended": sum(1 for r in _built' in src
    assert '"game_bets": len(bets)' in src, \
        "the game-bet count lost its own name"
    assert '"recommended": len(bets)' not in src


def test_the_merge_arithmetic_keeps_both():
    earlier = {"props_built": 440, "recommended": 3, "game_bets": 1}
    merged = {**earlier, "priced": 21, "published": 0}
    assert merged["recommended"] == 3 and merged["game_bets"] == 1


# --- the thin college allowance buys more by not being split ----------
def test_the_prime_window_spends_the_day_s_slice_in_one_pull():
    """The measured college allowance is about 26 credits a day. Split
    across the pacer's four touchpoints that buys ONE game of player
    props at five credits each, three of those pulls hours before
    anybody could use them."""
    from engine.oddsbudget import BudgetState, affordable_events
    st = BudgetState(remaining=1800)
    split = affordable_events(5, state=st)
    whole = affordable_events(5, state=st, pulls_per_day=1)
    assert whole > split, (split, whole)


def test_the_build_asks_for_the_whole_slice_only_inside_the_window():
    src = _src("cfb_build.py")
    assert "prime_window" in src
    assert "pulls_per_day=1 if hot else None" in src, \
        "an early cycle could spend the afternoon's board"


def test_the_cap_is_still_a_ceiling_over_whatever_the_pacer_says():
    import cfb_build as B
    src = _src("cfb_build.py")
    assert "cap = min(cap, affordable_events(" in src
    assert B.PLAYER_EVENT_CAP == 12, \
        "raising this was the wrong lever — the 63-credit pull already " \
        "starves at a 26-credit allowance; see launch.CFB_LINES_COST"


def test_a_pull_outside_the_window_keeps_the_default_split():
    """`prime_window` returns None when kickoffs are unknown, and the
    default split has to stand for that case as well as for False."""
    from engine.oddsbudget import prime_window
    assert prime_window([], 1_000_000.0) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
