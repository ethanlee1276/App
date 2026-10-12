"""From week 4 a player's form leans on his own last season, as measured.

Ethan, 2026-10-12, four outside reports on Bills @ Rams, every one of them
anchored on last season ("2025: 6+ catches in 13 of 16 games"). The model
stopped reading it the moment a player had three games this season, and
its widest misses against the market that night were exactly where the
two seasons disagree: Kyren Williams 5.8 catches projected off a 6- and a
10-catch game (2.1 a game in 2025, the line 3.5).

engine/carry.SEASON_PRIOR_GAMES pulls the form toward his last-season
per-game number by compute_form's own shrink, w = n/(n+k), measured market
by market with each season held out (`python3 seasonpriorfit.py`; the bar,
set first: every held-out season's error falls). Offline, on fixtures.

Run directly: `python3 tests/test_last_season_anchors_the_form.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import carry as C                                    # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog, Prop                          # noqa: E402
from engine.sources.nflverse import season_anchor                # noqa: E402


def _rows(col, vals, pos="WR", **extra):
    return [{"season_type": "REG", "week": str(i + 1), "position": pos, col: str(v), **extra}
            for i, v in enumerate(vals)]


def test_the_table_is_what_the_measurement_shipped():
    """Pinned so a refit that moves them is seen."""
    assert C.SEASON_PRIOR_GAMES == {"rec_yds": 6.0, "receptions": 4.0, "rush_yds": 2.0, "rush_att": 1.5,
                                    "pass_yds": 10.0, "pass_att": 10.0, "pass_cmp": 8.0, "rush_rec_yds": 2.0}
    assert "pass_rush_yds" not in C.SEASON_PRIOR_GAMES, "failed 2025 held out"
    src = open(os.path.join(ROOT, "seasonpriorfit.py"), encoding="utf-8").read()
    assert "every held-out season" in src.lower() or "falls in every season" in src
    assert "quarterbacked" in src, "the measurement reads a QB's season as the board does"


def test_his_own_last_season_is_the_anchor_and_a_cameo_is_not():
    a = season_anchor(_rows("receptions", [2, 3, 1, 2, 2, 3, 2, 1, 3, 2]), "receptions")
    assert a == {"anchor": 2.1, "n": 10, "k": 4.0}
    assert season_anchor(_rows("receptions", [2, 3, 1, 2, 2]), "receptions") is None, \
        "under MIN_PRIOR_GAMES is not a season"
    assert season_anchor(_rows("kick_pts", [8] * 12, pos="K"), "kick_pts") is None, "not measured, not applied"
    playoff = [dict(r, season_type="POST") for r in _rows("receptions", [9] * 3)]
    a = season_anchor(_rows("receptions", [2] * 8) + playoff, "receptions")
    assert a["anchor"] == 2.0 and a["n"] == 8, "regular season only"


def test_a_man_whose_role_has_shrunk_is_not_pulled_back_to_last_seasons_job():
    """The measurement scored players above a floor of involvement this
    season (carry.SEASON_PRIOR_FLOOR); under it nothing is applied — a
    receiver at 3 yards a game after a 50-yard season (Jauan Jennings, the
    first local build: 3.1 -> 27.2) is not in the population the bar saw."""
    last = _rows("receiving_yards", [50] * 15)
    shrunk = [GameLog(week=w, opponent="", value=v) for w, v in ((4, 4.0), (3, 2.0), (2, 0.0), (1, 6.0))]
    assert season_anchor(last, "rec_yds", shrunk) is None
    starter = [GameLog(week=w, opponent="", value=v) for w, v in ((4, 70.0), (3, 40.0), (2, 55.0), (1, 30.0))]
    assert season_anchor(last, "rec_yds", starter)["anchor"] == 50.0
    assert C.SEASON_PRIOR_FLOOR["rec_yds"] == 15.0 and set(C.SEASON_PRIOR_FLOOR) == set(C.SEASON_PRIOR_GAMES)
    src = open(os.path.join(ROOT, "seasonpriorfit.py"), encoding="utf-8").read()
    assert "C.SEASON_PRIOR_FLOOR" in src, "the measurement and the board use one floor"


def test_a_quarterback_season_is_his_real_games_only():
    qb = _rows("passing_yards", [250] * 7, pos="QB", attempts="34") + \
        [{"season_type": "REG", "week": "9", "position": "QB", "passing_yards": "12", "attempts": "2"}]
    assert season_anchor(qb, "pass_yds") == {"anchor": 250.0, "n": 7, "k": 10.0}, \
        "a two-attempt relief appearance is not his season (it failed 2024 when it was)"


def test_the_shrink_is_the_forms_own_and_fades_as_the_season_fills():
    a = season_anchor(_rows("receptions", [2.1] * 17), "receptions")
    now = [GameLog(week=w, opponent="", value=v) for w, v in ((4, 10.0), (3, 6.0), (2, 2.0), (1, 3.0))]
    raw = compute_form(now, 5.25, None).mean
    pulled = compute_form(now, 5.25, None, prior=a["anchor"], prior_n=a["n"], prior_games=a["k"])
    w = 4 / (4 + 4.0)
    assert abs(pulled.mean - (w * raw + (1 - w) * a["anchor"])) < 1e-9 and abs(pulled.shrunk_to - 2.1) < 1e-9
    assert 3.5 < pulled.mean < raw, (raw, pulled.mean)
    later = [GameLog(week=w, opponent="", value=5.0) for w in range(12, 0, -1)]
    assert compute_form(later, 5.0, None, prior=2.1, prior_n=17, prior_games=4.0).mean > 4.2, \
        "by week 13 this season carries three quarters of it"


def test_the_build_hands_it_to_the_prop_and_the_page_says_which_anchor():
    p = Prop(player="X", team="LA", opponent="BUF", position="RB", market="receptions",
             logs=[], career_avg=0.0, vs_opponent_avg=None, lines=[])
    assert p.form_prior_kind == ""
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    assert "season_prior = (season_anchor(mine_before, spec.market, logs)" in src
    assert 'form_prior_kind="thin" if thin else "season" if season_prior else ""' in src
    assert "if carried is None and thin is None else None" in src, "a carried or thin player keeps his own anchor"
    proj = open(os.path.join(ROOT, "engine", "projection.py"), encoding="utf-8").read()
    assert "shrink_kind=" in proj
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert 'base.shrink_kind === "season"' in js and "his own per-game number last season" in js


def test_the_calibration_replay_reads_last_season_as_the_board_does():
    """propcal fits the corrections the live board applies, and the live
    board builds every NFL slate with --carry (launch.py) — so last season
    is in its form from week 4. The replay asks for the same; every other
    replay keeps exactly what it had (opt-in, like usage_conn)."""
    import inspect
    import engine.pipeline as pl
    import engine.sources.nflverse as nv
    from engine import backtest as bt, propcal
    assert "usage_conn=conn, carry=True" in inspect.getsource(propcal.fit)
    assert inspect.signature(bt.backtest_from_stats).parameters["carry"].default is False
    seen = []
    saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
    nv.load_weekly_stats = lambda season: []
    nv.build_slate = lambda season, w, upto_week=None, **kw: seen.append(kw) or object()
    pl.run_slate = lambda slate, config=None, **kw: {"recommendations": []}
    try:
        bt.backtest_from_stats(2024, [6])
        bt.backtest_from_stats(2024, [6], carry=True)
    finally:
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = saved
    assert seen == [{}, {"carry": True}], seen


def test_the_usage_bridge_leans_on_last_season_where_it_measured():
    """engine/carry.BRIDGE_SEASON_MARKETS (bridgefit.py): the bridge's role
    — recent opportunities × this season's efficiency — is pulled toward
    last season by the form's own n/(n+k), only where the form itself was
    pulled. Passing yards failed 2025 and keeps its bridge as it was."""
    from engine.models import DefenseProfile, Game, Team, Weather
    from engine.projection import USAGE_PRIOR_GAMES, build_projection
    assert C.BRIDGE_SEASON_MARKETS == frozenset({"receptions", "rec_yds", "rush_yds"})
    src = open(os.path.join(ROOT, "bridgefit.py"), encoding="utf-8").read()
    assert "at most one of --unseen is worse" in src and "C.BRIDGE_SEASON_MARKETS" in src
    game = Game(home="KC", away="BUF", weather=Weather(dome=True))
    opp = Team(abbr="BUF", name="BUF", defense=DefenseProfile(team="BUF"))
    usage = {"opp_per_game": 8.0, "eff": 9.0, "opp_market": "targets"}      # role 72.0

    def proj(market, kind="season", prior=40.0, position="WR"):
        p = Prop(player="P", team="KC", opponent="BUF", position=position, market=market,
                 logs=[GameLog(week=w, opponent="BUF", value=60.0) for w in (4, 3, 2, 1)],
                 career_avg=60.0, vs_opponent_avg=None, lines=[], form_prior=prior, form_prior_n=17,
                 form_prior_games=6.0, form_prior_kind=kind)
        return build_projection(p, game, opp, usage=usage)

    got = proj("rec_yds")
    n, k = 4, 6.0
    form = n / (n + k) * 60.0 + k / (n + k) * 40.0                      # the form, pulled: 48.0
    role = n / (n + k) * 72.0 + k / (n + k) * 40.0                      # the role, pulled the same: 52.8
    w = n / (n + USAGE_PRIOR_GAMES)
    assert abs(got.form.mean - form) < 1e-9
    base = got.chain["steps"][0]["mult"] * got.form.mean if got.chain["steps"][0]["key"] == "usage" else None
    assert base is not None and abs(base - (w * form + (1 - w) * role)) < 1e-6, base
    assert "pulled 60% toward his 40.0 last season to 52.8" in " ".join(got.reasons)
    untouched = proj("pass_yds", position="QB")
    assert "last season to" not in " ".join(untouched.reasons), "passing yards keeps its bridge as it was"
    thin = proj("rec_yds", kind="thin")
    assert "last season to" not in " ".join(thin.reasons), "a thin anchor is the position, not his season"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
