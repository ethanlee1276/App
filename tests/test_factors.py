"""What each football factor is actually worth.

engine/matchup, engine/weather and engine/touchdowns price a game the
way a bettor talks about one — a soft run defence, a favourite leaning
on the clock, wind off the lake. Every one of those adjustments is a
hand-set constant, and none had been checked against an outcome.

Measured walk-forward over five seasons, production against the player's
own prior form, split by how generous the opponent had been so far:

    rush_yds     stingiest 1.079 -> most generous 1.277   swing 1.17x
    rec_yds      stingiest 1.168 -> most generous 1.290   swing 1.08x
    receptions   stingiest 0.941 -> most generous 1.053   swing 1.11x

Monotone in all three: the direction is right and the effect is real.
matchup clamps its defensive factor to (0.80, 1.25) — a permitted 1.56x
between extremes against a measured 1.08-1.17x.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import factors


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, player TEXT, team TEXT, opponent TEXT, "
              "market TEXT, value REAL)")
    return c


def _log(c, week, player, opponent, value, season=2025):
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, "
              "team, opponent, market, value) VALUES "
              "('nfl', ?, ?, ?, 'LV', ?, 'rush_yds', ?)",
              (season, "%03d" % week, player, opponent, float(value)))


# --- the walk-forward discipline ---------------------------------------------
def test_a_defence_is_rated_only_on_weeks_already_played():
    """Rating it on the full season would let the yards a player is about
    to gain help decide how generous his opponent was."""
    import inspect
    src = inspect.getsource(factors.defense_effect)
    i_use = src.index("out.setdefault(k, []).append")
    i_add = src.index("allowed[opp] = d_tot + val")
    assert i_use < i_add, "the game was counted before it was scored"


def test_a_player_is_compared_to_his_own_earlier_form():
    import inspect
    src = inspect.getsource(factors.defense_effect)
    i_use = src.index("own = hist.get(player)")
    i_add = src.index("hist.setdefault(player, []).append(val)")
    assert i_use < i_add


def test_ratings_reset_at_a_season_boundary():
    """A defence is a different team every September."""
    import inspect
    assert "allowed, played, hist, season_now = {}, {}, {}, season" in \
        inspect.getsource(factors.defense_effect)


def test_a_thin_defence_or_player_is_not_scored():
    c = _conn()
    for w in (1, 2):
        _log(c, w, "A.Back", "DEN", 50)
    assert factors.defense_effect(c, "rush_yds") == {}


def test_a_thin_bucket_is_not_reported():
    c = _conn()
    for w in range(1, 18):
        _log(c, w, "A.Back", "DEN", 50)
        _log(c, w, "B.Back", "DEN", 50)
    assert factors.defense_effect(c, "rush_yds") == {}, \
        "a bucket under MIN_BUCKET must not be published"


# --- what the numbers mean ----------------------------------------------------
def test_the_swing_is_between_the_extremes():
    effect = {0: {"n": 500, "ratio": 1.00}, 4: {"n": 500, "ratio": 1.20}}
    assert abs(factors.measured_swing(effect) - 1.20) < 1e-9


def test_no_effect_yields_no_swing():
    assert factors.measured_swing({}) is None
    assert factors.measured_swing({2: {"n": 500, "ratio": 1.1}}) is None


def test_the_permitted_swing_comes_from_the_clamp_matchup_actually_uses():
    """Read as numbers, not as text: the source says 0.80 and an f-string
    renders it 0.8, so a substring match fails on formatting alone."""
    import pathlib as _pl
    import re
    src = _pl.Path("engine/matchup.py").read_text()
    m = re.search(r"clamp\(factor,\s*([\d.]+),\s*([\d.]+)\)", src)
    assert m, "matchup no longer clamps its defensive factor"
    assert (float(m.group(1)), float(m.group(2))) == factors.DEFENSE_CLAMP, \
        "the clamp moved and engine/factors did not follow it"
    lo, hi = factors.DEFENSE_CLAMP
    assert abs(factors.applied_swing() - hi / lo) < 1e-9


def test_an_over_applied_factor_is_flagged():
    effect = {0: {"n": 500, "ratio": 1.00}, 4: {"n": 500, "ratio": 1.10}}
    text = "\n".join(factors.report_lines("rush_yds", effect))
    assert "5.6x the effect" in text, text
    assert "a ceiling, not a typical value" in text, \
        "the clamp is a permitted maximum and must not be read as typical"


def test_the_comparison_is_on_the_effect_not_the_multiplier():
    """A swing of 1.10 is a ten percent effect and a permitted 1.56 is a
    fifty-six percent one: the ratio is 5.6, not 1.42. Dividing the
    multipliers understates it by four times, which is what the first
    version of this line did — and it would have read as "the clamp is
    only slightly wide"."""
    effect = {0: {"n": 500, "ratio": 1.00}, 4: {"n": 500, "ratio": 1.10}}
    text = "\n".join(factors.report_lines("rush_yds", effect))
    assert "1.4x" not in text and "1.42" not in text
    assert "measured +10% between extremes" in text
    assert "permits +56%" in text


def test_a_right_sized_factor_is_not_flagged():
    effect = {0: {"n": 500, "ratio": 1.00}, 4: {"n": 500, "ratio": 1.40}}
    assert "the effect this data supports" not in \
        "\n".join(factors.report_lines("rush_yds", effect))


def test_the_levels_are_never_compared_against_one():
    """Every bucket reads above 1.0 because a player who keeps getting
    snaps is usually one whose role is growing, so his next game beats
    his own trailing average. The bias is identical in every bucket,
    which is why only the comparison between them is used."""
    import inspect
    assert "never against 1.0" in inspect.getsource(factors)


def test_it_reads_no_odds():
    import pathlib as _pl
    src = _pl.Path(factors.__file__).read_text()
    for word in ("odds_history", "over_odds", "closing_odds_by_date"):
        assert word not in src


# --- the game-level factors ---------------------------------------------------
def test_every_factor_has_a_label_for_every_bucket():
    """n edges make n+1 buckets. spread had five labels for five edges and
    the last bucket printed as "5"."""
    for name, spec in factors.GAME_FACTORS.items():
        assert len(spec["labels"]) == len(spec["edges"]) + 1, name


def test_a_game_is_found_for_every_team_that_played_in_it():
    """Sixteen games share a period, so keying on (season, period) keeps
    only the last and the team guard then discards everyone in the other
    fifteen. It showed up as buckets of two hundred where the defence
    measurement had thousands."""
    import inspect
    src = inspect.getsource(factors.game_effect)
    assert 'games[(int(g["season"]), g["period"], side)] = g' in src
    assert 'games.get((season, r["period"], team))' in src


def test_the_spread_is_read_from_the_players_own_side():
    """engine.matchup's convention: negative is favoured. Reading the
    home team's number for an away player inverts every game."""
    class _G(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)
    g = _G(home="PHI", away="DAL", spread=-8.5, roof="outdoors")
    spec = factors.GAME_FACTORS["spread"]
    assert factors._factor_value("spread", spec, g, "PHI") == -8.5
    assert factors._factor_value("spread", spec, g, "DAL") == 8.5


def test_indoor_games_are_skipped_for_weather():
    class _G(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)
    dome = _G(home="LV", away="KC", roof="dome", wind=None, temp=None)
    out = _G(home="GB", away="CHI", roof="outdoors", wind=12.0, temp=28.0)
    assert factors._factor_value("wind", factors.GAME_FACTORS["wind"],
                                 dome, "LV") is None
    assert factors._factor_value("wind", factors.GAME_FACTORS["wind"],
                                 out, "GB") == 12.0


def test_bucketing_puts_a_value_above_every_edge_in_the_last_bucket():
    assert factors._bucket(-20.0, (-9.5, -3.5, 0.0)) == 0
    assert factors._bucket(0.0, (-9.5, -3.5, 0.0)) == 3
    assert factors._bucket(99.0, (-9.5, -3.5, 0.0)) == 3


# --- shape, not just endpoints ------------------------------------------------
def test_a_climbing_series_is_named_as_one():
    e = {i: {"n": 500, "ratio": 1.0 + 0.05 * i} for i in range(5)}
    assert factors.trend(e) == "(climbs every step)"


def test_a_falling_series_is_named_as_one():
    e = {i: {"n": 500, "ratio": 1.3 - 0.05 * i} for i in range(5)}
    assert factors.trend(e) == "(falls every step)"


def test_a_wandering_series_is_flagged_however_big_its_ends():
    """rush_yds against the spread reads +21% end to end and goes 1.103,
    1.219, 1.184, 1.104, 1.167, 1.340 getting there — the ends differ and
    nothing in between agrees, and the ends are the thinnest buckets.
    Read as an effect size that licenses a large adjustment; read as a
    shape it is noise with two loud edges."""
    real = (1.103, 1.219, 1.184, 1.104, 1.167, 1.340)
    e = {i: {"n": 800, "ratio": r} for i, r in enumerate(real)}
    assert "wanders" in factors.trend(e)
    assert e[5]["ratio"] / e[0]["ratio"] - 1 > 0.20,         "the endpoints alone would have licensed a 21% adjustment"


def test_a_two_bucket_series_gets_no_shape_claim():
    assert factors.trend({0: {"n": 5, "ratio": 1.0},
                          1: {"n": 5, "ratio": 1.5}}) == ""


# --- the changes the measurements licensed ------------------------------------
def test_the_defensive_rating_is_shrunk_to_what_transfers():
    """DefenseProfile stores "yards allowed vs league average" and this
    was applied whole: a defence giving up 20% more multiplied the
    projection by 1.20. Regressing production against a player's own
    prior form on that defence's walk-forward rating gives the slope that
    actually reaches him — 0.48 rushing, 0.30 receptions, 0.24 receiving
    yards. The slope IS the least-squares coefficient, so applying the
    raw rating used 1.0 where the data says a quarter to a half."""
    from engine.matchup import DEFENSE_TRANSFER, DEFENSE_TRANSFER_DEFAULT
    from engine.models import PASS_YDS, RECEPTIONS, REC_YDS, RUSH_YDS
    assert DEFENSE_TRANSFER[RUSH_YDS] == 0.48
    assert DEFENSE_TRANSFER[RECEPTIONS] == 0.30
    assert DEFENSE_TRANSFER[REC_YDS] == 0.24
    assert DEFENSE_TRANSFER[PASS_YDS] == 0.0
    assert 0 < DEFENSE_TRANSFER_DEFAULT <= max(DEFENSE_TRANSFER.values())


def test_a_generous_defence_now_moves_a_runner_half_as_far():
    from engine.matchup import DEFENSE_TRANSFER
    from engine.models import RUSH_YDS
    raw = 1.25
    shrunk = 1.0 + DEFENSE_TRANSFER[RUSH_YDS] * (raw - 1.0)
    assert abs(shrunk - 1.12) < 0.005


def test_a_passing_defence_moves_a_quarterback_not_at_all():
    """Slope -0.06 on n=2,035, smaller than its own standard error. A
    defence's passing rating does not predict an individual
    quarterback's yardage — his own team's pass rate and the game script
    drive it, and a good defence forcing an opponent to throw cuts the
    other way."""
    from engine.matchup import DEFENSE_TRANSFER
    from engine.models import PASS_YDS
    raw = 1.25
    assert 1.0 + DEFENSE_TRANSFER[PASS_YDS] * (raw - 1.0) == 1.0


def test_the_shrink_happens_before_the_clamp():
    """Otherwise the clamp is still catching an over-applied factor
    rather than bounding a reasonable one."""
    import inspect
    from engine import matchup
    src = inspect.getsource(matchup.evaluate_matchup)
    i_shrink = src.index("factor = 1.0 + transfer * (factor - 1.0)")
    i_clamp = src.index("factor = clamp(factor, 0.80, 1.25)")
    assert i_shrink < i_clamp


def test_the_pace_term_points_the_way_the_data_does():
    """The rule was "high total => more plays, more production for
    everyone": +3% at 48 and above. No market has a positive
    relationship with the total, and rush_yds falls at every bucket —
    1.243 in the lowest-total games to 1.064 in the highest."""
    from engine.matchup import TOTAL_BASELINE, TOTAL_CLAMP, TOTAL_COEF
    from engine.models import RUSH_YDS
    from engine.statmath import clamp
    assert TOTAL_COEF[RUSH_YDS] < 0
    low = clamp(1 + TOTAL_COEF[RUSH_YDS] * (38 - TOTAL_BASELINE), *TOTAL_CLAMP)
    high = clamp(1 + TOTAL_COEF[RUSH_YDS] * (52 - TOTAL_BASELINE), *TOTAL_CLAMP)
    assert low > 1.0 > high, (low, high)


def test_only_a_monotone_series_earned_a_pace_term():
    """pass_yds carries the larger t (-2.5) and its buckets wander, its
    sample is a fifth the size, and four markets were tested. A
    counter-intuitive sign is where a marginal number should be trusted
    least."""
    from engine.matchup import TOTAL_COEF
    from engine.models import PASS_YDS, RECEPTIONS, REC_YDS, RUSH_YDS
    assert set(TOTAL_COEF) == {RUSH_YDS}
    for m in (PASS_YDS, REC_YDS, RECEPTIONS):
        assert m not in TOTAL_COEF


def test_the_shape_test_catches_a_series_that_doubles_back():
    """Counting directions was not enough: wind against rush_yds goes
    1.186, 1.116, 1.207, 1.116 — one step up and two down, which a bare
    count called "mostly one direction" while the series plainly walks
    back its own progress."""
    real = (1.186, 1.116, 1.207, 1.116)
    e = {i: {"n": 800, "ratio": r} for i, r in enumerate(real)}
    assert "wanders" in factors.trend(e)


def test_a_clean_run_still_reads_as_one_direction():
    """The real rush_yds defence series: it climbs, dips once at the far
    end, and travels 83% of the distance it walks. That is a trend with a
    wobble, not a series that doubles back."""
    real = (1.079, 1.186, 1.234, 1.277, 1.259)
    e = {i: {"n": 800, "ratio": r} for i, r in enumerate(real)}
    assert factors.trend(e) == "(mostly one direction)"


def test_flat_steps_do_not_count_as_reversals():
    """A series that falls and then holds is still falling."""
    e = {i: {"n": 800, "ratio": r}
         for i, r in enumerate((1.24, 1.24, 1.13, 1.13, 1.06))}
    assert factors.trend(e) == "(falls every step)"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
