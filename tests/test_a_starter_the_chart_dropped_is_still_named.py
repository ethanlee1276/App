"""A starter the depth chart has already replaced is still named when he is out.

Ethan's Patriots–Bears research, 2026-10-22: New England started two
backup interior linemen — Alijah Vera-Tucker (every snap through week 5)
and Ben Brown out, Vera-Tucker since moved to injured reserve — and Romeo
Doubs had gone on reserve. The matchup scan names a player out only when
he starts on the depth chart (or has targets, carries or pressures to be
counted by), and the chart drops a man the day he is hurt — the day his
absence is the news. A lineman has nothing else to be counted by.

engine/gamescan.recent_starters reads who has been starting off nflverse's
snap counts — half his side's snaps in at least half the games he played
among his team's last three — and the scan names those players too, in
"who is out" and on the starting line. A depth player who never played
half the snaps (Karon Prunty, Channing Canada: 5% at most) is not one, nor
is a starter lost weeks ago (his absence is in the numbers already).

Run directly: `python3 tests/test_a_starter_the_chart_dropped_is_still_named.py`
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                   # noqa: E402

SRC = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()


def _snap(week, player, pos, off=0.0, dfn=0.0, team="NE"):
    return {"game_type": "REG", "week": str(week), "team": team, "player": player, "position": pos,
            "offense_pct": str(off), "defense_pct": str(dfn)}


def _inj(player, team, pos, status):
    return types.SimpleNamespace(player=player, team=team, position=pos, status=status, role="")


#: The Patriots' snaps, weeks 1–6 of 2026, as nflverse has them.
SNAPS = [
    _snap(4, "Alijah Vera-Tucker", "G", 1.0), _snap(5, "Alijah Vera-Tucker", "G", 1.0),
    _snap(6, "Alijah Vera-Tucker", "G", 0.32),
    _snap(4, "Ben Brown", "C", 1.0), _snap(5, "Ben Brown", "C", 1.0), _snap(6, "Ben Brown", "C", 0.79),
    # Hurt three snaps into week 6: half his games, not his average.
    _snap(4, "Romeo Doubs", "WR", 0.64), _snap(5, "Romeo Doubs", "WR", 0.83), _snap(6, "Romeo Doubs", "WR", 0.03),
    _snap(2, "Karon Prunty", "CB", dfn=0.0), _snap(3, "Karon Prunty", "CB", dfn=0.05),
    _snap(4, "Karon Prunty", "CB", dfn=0.0),
    _snap(2, "Channing Canada", "CB", dfn=0.03), _snap(3, "Channing Canada", "CB", dfn=0.05),
    # Lost in week 2: old news by week 7.
    _snap(1, "Mike Onwenu", "G", 1.0), _snap(2, "Mike Onwenu", "G", 1.0),
    # One start in three is a fill-in.
    _snap(4, "Walter Rouse", "OL", 1.0), _snap(5, "Walter Rouse", "OL", 0.0), _snap(6, "Walter Rouse", "OL", 0.21),
    _snap(1, "Will Campbell", "T", 1.0), _snap(2, "Will Campbell", "T", 1.0), _snap(3, "Will Campbell", "T", 1.0),
    # The week being scanned is not "before" it.
    _snap(7, "Next Week", "G", 1.0),
    _snap(5, "Montez Sweat", "DL", dfn=0.70, team="CHI"), _snap(6, "Jack Sanborn", "LB", dfn=0.16, team="CHI"),
]


def test_a_starter_is_half_the_snaps_in_half_his_recent_games():
    got = G.recent_starters(SNAPS, before_week=7)
    for name in ("Alijah Vera-Tucker", "Ben Brown", "Romeo Doubs"):
        assert G._key(name) in got["NE"], name
    for name in ("Karon Prunty", "Channing Canada", "Mike Onwenu", "Walter Rouse", "Will Campbell", "Next Week"):
        assert G._key(name) not in got["NE"], name
    assert got["CHI"] == {G._key("Montez Sweat")}, "a defender by his defensive snaps"
    assert G.recent_starters([], before_week=7) == {} and G.recent_starters(None) == {}


def test_a_starter_the_chart_dropped_is_named_out_and_on_the_line():
    # Thursday's chart: the replacements already at the top.
    charts = {"NE": [{"position": "LG", "players": ["Walter Rouse"]},
                     {"position": "RG", "players": ["Matt Pryor"]},
                     {"position": "WR", "players": ["A.J. Brown", "DeMario Douglas", "Kyle Williams"]}]}
    inj = [_inj("Alijah Vera-Tucker", "NE", "G", "IR"), _inj("Ben Brown", "NE", "C", "OUT"),
           _inj("Romeo Doubs", "NE", "WR", "IR"), _inj("Karon Prunty", "NE", "CB", "OUT"),
           _inj("Channing Canada", "NE", "CB", "OUT")]
    kw = dict(ratings={}, charts=charts, defenders_now={}, usage={}, injuries=inj, props=[])
    out = G.scan_game("CHI", "NE", recent=G.recent_starters(SNAPS, before_week=7), **kw)
    assert [r["player"] for r in out["injuries"] if r["team"] == "NE"] == \
        ["Alijah Vera-Tucker", "Ben Brown", "Romeo Doubs"]
    assert out["line_out"]["NE"] == ["Alijah Vera-Tucker (G)", "Ben Brown (C)"]
    # Without the snap counts: the miss the research found.
    old = G.scan_game("CHI", "NE", **kw)
    assert not [r for r in old["injuries"] if r["team"] == "NE"] and old["line_out"]["NE"] == []


def test_a_lineman_the_chart_still_starts_is_named_once():
    charts = {"NE": [{"position": "LG", "players": ["Alijah Vera-Tucker", "Walter Rouse"]}]}
    inj = [_inj("Alijah Vera-Tucker", "NE", "G", "OUT")]
    assert G._line_out("NE", charts["NE"], inj, G.recent_starters(SNAPS, before_week=7)) == \
        ["Alijah Vera-Tucker (LG)"]
    # Questionable is not out.
    assert G._line_out("NE", [], [_inj("Ben Brown", "NE", "C", "QUESTIONABLE")],
                       G.recent_starters(SNAPS, before_week=7)) == []


def test_the_build_reads_the_snap_counts_once_for_both():
    assert "recent = recent_starters(snaps, before_week=week)" in SRC
    assert "usage_table(_safe(load_weekly_stats, season), snaps, before_week=week)" in SRC
    assert "contact=contact, recent=recent)" in SRC


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
