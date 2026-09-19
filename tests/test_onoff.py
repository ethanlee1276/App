"""Who inherits a sitting player's share — WNBA §6's on/off half.

Run directly: `python3 tests/test_onoff.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.nba import onoff                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(date, player, stat, value, team="LVA"):
    return {"team": team, "period": date, "player": player,
            "market": stat, "value": value}


def _season(star_dates, out_dates):
    rows = []
    for d in star_dates:
        rows += [_row(d, "Star", "pts", 24), _row(d, "Star", "min", 33),
                 _row(d, "A", "pts", 12), _row(d, "A", "min", 28),
                 _row(d, "B", "pts", 12), _row(d, "B", "min", 25)]
    for d in out_dates:
        rows += [_row(d, "A", "pts", 22), _row(d, "A", "min", 34),
                 _row(d, "B", "pts", 10), _row(d, "B", "min", 25)]
    return rows


def test_the_teammate_who_inherits_is_named_and_ranked_first():
    res = onoff.inheritance(_season(["07-01", "07-03", "07-05", "07-07"],
                                    ["07-09", "07-11", "07-13"]),
                            "LVA", "Star")
    assert res["enough"] is True
    assert list(res["beneficiaries"])[0] == "A"
    assert res["beneficiaries"]["A"]["delta"] > 0
    a = res["beneficiaries"]["A"]
    assert a["with"] == 0.25 and a["without"] == round(22 / 32, 4)


def test_share_not_volume_so_pace_cancels():
    """A's raw points FALL in the absent games (fast games to slow ones)
    and her SHARE still rises — the whole point."""
    rows = []
    for d in ("07-01", "07-03"):
        rows += [_row(d, "Star", "pts", 30), _row(d, "Star", "min", 30),
                 _row(d, "A", "pts", 20), _row(d, "A", "min", 30),
                 _row(d, "F", "pts", 50)]      # 100-pt track meets
    for d in ("07-05", "07-07", "07-09"):
        rows += [_row(d, "A", "pts", 18), _row(d, "A", "min", 30),
                 _row(d, "F", "pts", 42)]      # 60-pt grinders
    res = onoff.inheritance(rows, "LVA", "Star")
    a = res["beneficiaries"]["A"]
    assert a["with"] == 0.2 and a["without"] == 0.3
    assert a["delta"] > 0, "raw points fell; the share rose"


def test_a_scoreless_night_is_still_a_played_game():
    """Presence is judged by MINUTES, not by the stat being shared —
    judging by points would call a 0-point night an absence."""
    rows = _season(["07-01", "07-03"], ["07-05", "07-07", "07-09"])
    rows += [_row("07-15", "Star", "pts", 0), _row("07-15", "Star", "min", 20),
             _row("07-15", "A", "pts", 20), _row("07-15", "A", "min", 30)]
    res = onoff.inheritance(rows, "LVA", "Star")
    assert res["n_played"] == 3, "the scoreless night must count as played"


def test_two_missed_games_are_reported_as_not_enough():
    res = onoff.inheritance(_season(["07-01", "07-03", "07-05"],
                                    ["07-07", "07-09"]), "LVA", "Star")
    assert res["n_out"] == 2 and res["enough"] is False
    assert "NOT ENOUGH GAMES" in onoff.report(res)


def test_another_teams_games_never_pool():
    rows = _season(["07-01", "07-03"], ["07-05", "07-07", "07-09"])
    rows += [_row("07-05", "Rival", "pts", 40, team="NYL")]
    res = onoff.inheritance(rows, "LVA", "Star")
    assert "Rival" not in res["beneficiaries"]


def test_nothing_here_prices_anything():
    src = open(os.path.join(ROOT, "engine", "nba", "onoff.py"),
               encoding="utf-8").read()
    # CODE only — the module docstring says "the claimed edge measures
    # AUC 0.479", which is the disclaimer, not a pricing path. Banning
    # the word from the disclaimer would ban the module from explaining
    # why it prices nothing.
    import re
    # End of the module docstring: the second triple-quote.
    close = src.index('"""', src.index('"""') + 3)
    body_src = src[close + 3:]
    for banned in ("hit_prob", "stake", "edge"):
        assert not re.search(rf"\b{banned}\b", body_src), banned
    assert "THE_INFORMATION_TEST" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
