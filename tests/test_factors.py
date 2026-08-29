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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
