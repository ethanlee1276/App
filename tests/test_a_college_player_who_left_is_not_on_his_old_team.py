"""A college player who left is read at his new school only (2026-11-14).

Ethan's picks audit read Dylan Lonergan twice in one Saturday: "BC vs ND,
QB" and "RUTG vs NEB, QB". This season's logs have him at Rutgers; the
props board reads two seasons of logs, so last season's Boston College
rows found him under Boston College and placed him on that side too —
priced off last year's games, and read in Boston College's game report.
Every school's graduates were placed the same way all season.

    python3 tests/test_a_college_player_who_left_is_not_on_his_old_team.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.cfb import props as P                       # noqa: E402
from engine.cfb.tds import resolve_side                 # noqa: E402


def _slot(player, *rows, market="rush_yds"):
    """rows: (period, opponent, value, prior)."""
    return {"player": player, "position": "",
            market: [(p, o, True, float(v), bool(pr)) for p, o, v, pr in rows]}


def _filed():
    return {
        "BC": {"dylan lonergan": _slot("Dylan Lonergan", ("2025-11-29", "SYR", 40, True),
                                       market="pass_yds"),
               "grad back": _slot("Grad Back", ("2025-11-29", "SYR", 88, True)),
               "now back": _slot("Now Back", ("2026-11-07", "SMU", 61, False),
                                 ("2025-11-29", "SYR", 30, True)),
               "pocket qb": _slot("Pocket Qb", ("2026-11-07", "SMU", 233, False), market="pass_yds"),
               "hurt back": _slot("Hurt Back", ("2025-11-29", "SYR", 70, True))},
        "RUTG": {"dylan lonergan": _slot("Dylan Lonergan", ("2026-11-07", "MD", 251, False),
                                         market="pass_yds")},
        "ND": {"nd back": _slot("Nd Back", ("2026-11-07", "NAVY", 95, False))},
        "NEB": {"neb back": _slot("Neb Back", ("2026-11-07", "IOWA", 77, False))},
    }


#: This season's logged carries and catches (teams_by_name) plus the slate's
#: rosters: Lonergan at Rutgers, the back hurt all season on BC's roster. The
#: pocket passer has no carry this season, so he is in neither.
CURRENT = {"dylan lonergan": {"RUTG"}, "now back": {"BC"}, "hurt back": {"BC"},
           "nd back": {"ND"}, "neb back": {"NEB"}}


def test_a_man_filed_at_his_old_school_is_placed_only_at_the_new_one():
    filed = _filed()
    assert resolve_side("dylan lonergan", "ND", "BC", filed, CURRENT) == ("", "")
    assert resolve_side("dylan lonergan", "RUTG", "NEB", filed, CURRENT) == ("RUTG", "RUTG")


def test_the_week_one_bridge_and_a_returner_are_unchanged():
    filed = {"OLD": {"mover": _slot("Mover", ("2025-11-29", "X", 80, True))},
             "BC": {"stays": _slot("Stays", ("2025-11-29", "X", 50, True))}}
    # A transfer before his first game for the new school: placed there, his
    # usage read where it is filed.
    assert resolve_side("mover", "NEW", "BC", filed, {"mover": {"NEW"}}) == ("NEW", "OLD")
    assert resolve_side("mover", "OLD", "BC", filed, {"mover": {"NEW"}}) == ("", "")
    # A returner on his roster, and anyone at all before this season's logs exist.
    assert resolve_side("stays", "BC", "ND", filed, {"stays": {"BC"}}) == ("BC", "BC")
    assert resolve_side("stays", "BC", "ND", filed, {}) == ("BC", "BC")


def test_once_his_side_has_played_a_man_gone_since_last_season_is_not_a_candidate():
    census: dict = {}
    got = P._candidates([{"home": "ND", "away": "BC"}, {"home": "RUTG", "away": "NEB"}],
                        _filed(), CURRENT, census)
    placed = {(side, norm) for side, _opp, _filed_team, norm in got}
    assert ("BC", "dylan lonergan") not in placed, "last season's Boston College rows are not tonight's"
    assert ("RUTG", "dylan lonergan") in placed
    assert ("BC", "grad back") not in placed, "a graduate: no game this season, on no roster"
    assert ("BC", "now back") in placed and ("BC", "hurt back") in placed, "playing, or on the roster"
    assert ("BC", "pocket qb") in placed, "his own passing rows this season count, carries or not"
    assert census.get("gone") == 1, census


def test_before_his_sides_first_game_last_season_is_all_it_has():
    filed = {"BC": {"grad back": _slot("Grad Back", ("2025-11-29", "SYR", 88, True)),
                    "old back": _slot("Old Back", ("2025-11-29", "SYR", 50, True))},
             "ND": {}}
    census: dict = {}
    got = P._candidates([{"home": "ND", "away": "BC"}], filed, {}, census)
    assert {n for _s, _o, _f, n in got} == {"grad back", "old back"}
    assert not census.get("gone")


def test_the_build_says_how_many_it_left_off():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert "gone since last season" in src
    assert "cands = _candidates(games, filed, current, census)" in (ROOT / "engine" / "cfb" / "props.py").read_text(
        encoding="utf-8")


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
