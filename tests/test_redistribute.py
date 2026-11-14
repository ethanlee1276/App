"""Where a player's usage goes when he is out — NFL_MODEL §7's ripple.

What exists today is `engine/injuries.py`, and it is worth being exact:
a table of INVENTED multipliers. Opponent CB1 out multiplies a receiving
projection by 1.09; interior DT out, 1.06; own left tackle out, 0.95.
Nobody measured those. They are plausible, round, and identical for every
team and every player.

Run directly: `python3 tests/test_redistribute.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import redistribute as rd                          # noqa: E402


def _row(week, player, team, targets):
    return {"week": week, "player_display_name": player, "recent_team": team,
            "season_type": "REG", "targets": targets}


def _season(star_weeks, out_weeks, star_tg=10, a_on=6, a_off=12,
            b_on=4, b_off=4, total=20):
    """Weeks where the star played, and weeks he did not. `A` absorbs his
    work; `B` does not."""
    rows = []
    for w in star_weeks:
        rows += [_row(w, "Star", "NE", star_tg), _row(w, "A", "NE", a_on),
                 _row(w, "B", "NE", b_on),
                 _row(w, "Filler", "NE", total - star_tg - a_on - b_on)]
    for w in out_weeks:
        rows += [_row(w, "A", "NE", a_off), _row(w, "B", "NE", b_off),
                 _row(w, "Filler", "NE", total - a_off - b_off)]
    return rows


def test_the_teammate_who_absorbs_the_work_is_named():
    res = rd.redistribution(_season([1, 2, 3, 4], [5, 6, 7]), "NE", "Star")
    assert res["enough"] is True
    top = list(res["beneficiaries"])[0]
    assert top == "A", res["beneficiaries"]
    assert res["beneficiaries"]["A"]["delta"] > 0
    assert res["beneficiaries"]["B"]["delta"] <= 0


def test_share_not_volume_so_game_script_cancels():
    """A teammate's raw targets rise in a game the team threw 45 times and
    fall in one it threw 22, and neither has anything to do with who was
    absent. Here the ABSENT weeks are low-volume: A's raw targets fall from
    6 to 5, and his SHARE still rises."""
    rows = []
    for w in (1, 2, 3, 4):
        rows += [_row(w, "Star", "NE", 10), _row(w, "A", "NE", 6),
                 _row(w, "Filler", "NE", 24)]        # 40 team targets
    for w in (5, 6, 7):
        rows += [_row(w, "A", "NE", 5), _row(w, "Filler", "NE", 15)]  # 20
    res = rd.redistribution(rows, "NE", "Star")
    a = res["beneficiaries"]["A"]
    assert a["with"] == 0.15 and a["without"] == 0.25
    assert a["delta"] > 0, "raw targets FELL; the share rose — that is the point"


def test_a_two_game_absence_is_reported_as_not_enough():
    """THE GUARD. A six-point move in share over two games is one busy
    afternoon, and printing it as a finding is how an invented 1.09 gets
    replaced by an invented 1.24."""
    res = rd.redistribution(_season([1, 2, 3, 4], [5, 6]), "NE", "Star")
    assert res["n_out"] == 2
    assert res["enough"] is False
    assert "NOT ENOUGH GAMES" in rd.report(res)


def test_the_deltas_still_print_below_the_floor_but_labelled():
    """Hiding them would be its own dishonesty — the shape is worth seeing.
    It just must not read as evidence."""
    res = rd.redistribution(_season([1, 2, 3, 4], [5, 6]), "NE", "Star")
    out = rd.report(res)
    assert "not evidence of anything" in out
    assert "A" in out


def test_absence_is_read_from_the_stats_not_from_a_report():
    """An injury report says who was LISTED. The stats say who did not
    play, and only the second is what a redistribution is about."""
    rows = _season([1, 2, 3, 4], [5, 6, 7])
    # Star has no row at all in weeks 5-7 — that IS the absence signal.
    assert not [r for r in rows
                if r["player_display_name"] == "Star" and r["week"] > 4]
    assert rd.redistribution(rows, "NE", "Star")["n_out"] == 3


def test_a_teammate_seen_in_only_one_state_is_not_compared():
    """A rookie who first appears the week the star got hurt has no
    'with' baseline, so his share difference is undefined rather than
    enormous."""
    rows = _season([1, 2, 3, 4], [5, 6, 7])
    rows += [_row(w, "Rookie", "NE", 3) for w in (5, 6, 7)]
    res = rd.redistribution(rows, "NE", "Star")
    assert "Rookie" not in res["beneficiaries"]


def test_another_teams_players_are_never_pooled_in():
    rows = _season([1, 2, 3, 4], [5, 6, 7])
    rows += [_row(w, "Other", "BUF", 30) for w in range(1, 8)]
    res = rd.redistribution(rows, "NE", "Star")
    assert "Other" not in res["beneficiaries"]


def test_a_week_with_no_usage_at_all_does_not_crash_or_count():
    rows = _season([1, 2, 3, 4], [5, 6, 7])
    rows += [_row(9, "A", "NE", 0), _row(9, "B", "NE", 0)]
    res = rd.redistribution(rows, "NE", "Star")
    assert res["n_out"] == 3        # week 9 has no denominator, so no week


def test_carries_work_the_same_way_as_targets():
    rows = []
    for w in (1, 2, 3, 4):
        rows += [{"week": w, "player_display_name": "RB1", "recent_team": "NE",
                  "carries": 15},
                 {"week": w, "player_display_name": "RB2", "recent_team": "NE",
                  "carries": 5}]
    for w in (5, 6, 7):
        rows += [{"week": w, "player_display_name": "RB2", "recent_team": "NE",
                  "carries": 18}]
    res = rd.redistribution(rows, "NE", "RB1", kind="carries")
    assert res["beneficiaries"]["RB2"]["without"] == 1.0


def test_nothing_here_prices_anything():
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "redistribute.py"), encoding="utf-8").read()
    assert "multiplier" not in src.split('"""')[2] if '"""' in src else True
    assert "THE_INFORMATION_TEST" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
