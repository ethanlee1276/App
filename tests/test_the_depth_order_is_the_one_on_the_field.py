"""The teammate-out step runs from week 2, on the depth order by snaps.

Ethan, 2026-09-27, pasting another model's Jets @ Lions card: Kenyon
Sadiq 2.5+ catches because Mason Taylor is out. Our engine priced the same
game (a real week-3 build with that model's lines) and Sadiq's teammate
step never ran, for two reasons found and measured here:

  * THE ORDER NEEDED THREE GAMES. engine/matefit ranked a position only on
    players with three games this season, so every team's order was empty
    until week 4 — the step was off for the first three weeks of every
    season. Measured in weeks 2-3 (`python3 matefit.py --early`), every
    "above" effect pointed the same way as the week-4+ one and sat within
    its error; the order now ranks on the games played so far.
  * TARGETS PUT THE BACKUP FIRST. Taylor, on 66% and 46% of the snaps,
    drew 0 targets in week 2, so the box scores had no row for him and the
    target order made Sadiq (36%) the starter. Ranked on snap share, with
    every game a player took a snap in, the effects measured at least as
    strong on 2022-2025 and more of them cleared the shipping rule
    (`python3 matefit.py --snaps` → teammates.EFFECT_SNAPS).
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import matefit as F                                   # noqa: E402
from engine import teammates as T                                 # noqa: E402


def _stat(week, name, pos, targets, rec=0):
    return {"season_type": "REG", "week": str(week), "team": "NYJ", "position": pos,
            "player_display_name": name, "targets": str(targets), "receptions": str(rec)}


def _snap(week, name, pos, pct):
    return {"game_type": "REG", "week": str(week), "team": "NYJ", "player": name,
            "position": pos, "offense_snaps": str(int(pct * 70)), "offense_pct": str(pct)}


# The Jets' tight ends through week 2 of 2026, as the feeds have them.
STATS = [_stat(1, "Mason Taylor", "TE", 3, 2), _stat(1, "Kenyon Sadiq", "TE", 3, 3),
         _stat(2, "Kenyon Sadiq", "TE", 3, 2), _stat(1, "Jeremy Ruckert", "TE", 1, 1),
         _stat(2, "Jeremy Ruckert", "TE", 2, 1)]
SNAPS = [_snap(1, "Mason Taylor", "TE", 0.66), _snap(1, "Kenyon Sadiq", "TE", 0.42),
         _snap(1, "Jeremy Ruckert", "TE", 0.43), _snap(2, "Mason Taylor", "TE", 0.46),
         _snap(2, "Kenyon Sadiq", "TE", 0.36), _snap(2, "Jeremy Ruckert", "TE", 0.34)]


def test_the_order_ranks_from_week_two():
    assert [F.early_min_games(w) for w in (1, 2, 3, 4, 9)] == [1, 1, 2, 3, 3]
    by_targets = T.depth_table(STATS, {"NYJ"}, 3)
    assert by_targets["basis"] == "targets"
    assert [o[0] for o in by_targets["order"]["NYJ|TE"]][0] == "Kenyon Sadiq", \
        "the box scores alone crown the backup — the bug"


def test_on_snaps_the_starter_is_the_starter():
    d = T.depth_table(STATS, {"NYJ"}, 3, SNAPS)
    assert d["basis"] == "snaps"
    names = [o[0] for o in d["order"]["NYJ|TE"]]
    assert names[0] == "Mason Taylor" and names[1] in ("Kenyon Sadiq", "Jeremy Ruckert")
    assert d["order"]["NYJ|TE"][0][2] == 2, "his blanked week counts as a game played"


def test_the_starter_out_lifts_the_man_behind_him_by_the_snap_measurement():
    d = T.depth_table(STATS, {"NYJ"}, 3, SNAPS)
    game = types.SimpleNamespace(home="DET", away="NYJ", lineup=None)
    inj = [types.SimpleNamespace(team="NYJ", player="Mason Taylor", status="OUT")]
    slate = types.SimpleNamespace(games=[game], props=[])
    T.stamp(slate, d, inj)
    assert game.lineup["NYJ"]["basis"] == "snaps"
    prop = types.SimpleNamespace(player="Kenyon Sadiq", team="NYJ", position="TE",
                                 market="receptions")
    mult, why, card = T.effect(prop, game)
    assert mult == T.EFFECT_SNAPS[("receptions", "TE", "above_new")] and mult > 1.4
    assert "Mason Taylor just ruled out ahead of him at TE" in why and card["applied"] == round(mult, 3)


def test_the_snap_table_is_what_the_measurement_shipped():
    """Every entry clears qbfit.shipped's rule on the snap-ranked run; the
    headline cells are pinned so a refit that moves them is seen."""
    assert T.EFFECT_SNAPS[("rec_yds", "TE", "above_new")] == 1.747
    assert T.EFFECT_SNAPS[("receptions", "TE", "above_new")] == 1.568
    assert T.EFFECT_SNAPS[("rush_yds", "RB", "above_new")] == 1.662
    assert all(v > 1.0 for v in T.EFFECT_SNAPS.values())
    fit = open(os.path.join(ROOT, "matefit.py"), encoding="utf-8").read()
    assert "--snaps" in fit and "--early" in fit and "EFFECT_SNAPS" in fit


def test_the_build_hands_the_depth_table_its_snaps():
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    i = src.index("from ..teammates import depth_table as _depth_table")
    block = src[i:i + 400]
    assert "_snap_rows = load_snap_counts(season)" in block
    assert "_depth_table(stats, participating, upto_week, _snap_rows)" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
