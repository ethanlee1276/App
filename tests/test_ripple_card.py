"""The beneficiary's card says what the stats measured when his teammate
sat — and the projection does not move for it.

Ethan, 2026-09-14: "RB2 Isiah Pacheco is now out till October 11th so
RB1 Jahmyr Gibbs should be seeing a lot more usage and shit like that ...
I wanna make sure we are adjusting if needed and reading this data."
Two sizes were offered and he took both. This is the safe one: when a
teammate at the same position is ruled out, the card carries "Pacheco
out — over his 3 missed games, X absorbed +11% of the carries" where
the sample clears the floor, and "usage likely up — not enough games to
measure" where it does not. Display only. The pricing half is
engine.ripplefit, and it waits on the information test.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import redistribute as rd                          # noqa: E402
from engine.models import Injury, RUSH_YDS, REC_YDS, RECEPTIONS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(season, week, player, team, pos, carries=0, targets=0):
    return {"season": season, "week": week, "player_display_name": player,
            "recent_team": team, "position": pos, "carries": carries,
            "targets": targets, "season_type": "REG"}


def _season(season, weeks, out_weeks=(), team="KC"):
    """RB1 and RB2 split the carries 60/40 with both in; RB2 takes 75%
    when RB1 sits. A receiver rides along so targets exist too."""
    rows = []
    for w in weeks:
        if w in out_weeks:
            rows += [_row(season, w, "RB Two", team, "RB", carries=18),
                     _row(season, w, "RB Three", team, "RB", carries=6)]
        else:
            rows += [_row(season, w, "RB One", team, "RB", carries=15),
                     _row(season, w, "RB Two", team, "RB", carries=10),
                     _row(season, w, "RB Three", team, "RB", carries=0)]
        rows += [_row(season, w, "WR One", team, "WR", targets=9),
                 _row(season, w, "WR Two", team, "WR", targets=6)]
    return rows


class _Prop:
    def __init__(self, player, team, position, market):
        self.player, self.team, self.position, self.market = player, team, position, market


def _out(player="RB One", team="KC", pos="RB", status="OUT"):
    return Injury(player=player, team=team, position=pos, role="rb1", status=status)


def test_a_measured_absence_is_said_with_its_number():
    prior = _season(2025, range(1, 18), out_weeks=(5, 6, 7, 8))
    cur = _season(2026, range(1, 3))
    props = [_Prop("RB Two", "KC", "RB", RUSH_YDS)]
    got = rd.ripples_for_props(props, [_out()], cur, prior, 2026, 3)
    n = got[("RB Two", RUSH_YDS)][0]
    assert n["measured"] and n["n_out"] == 4
    # 40% of the carries with him, 75% without: +35 points of share.
    assert abs(n["delta"] - 0.35) < 0.02, n
    assert n["text"].startswith("RB One out — over his 4 missed games, Two absorbed +35% of the carries"), n["text"]
    assert n["with"] < n["without"]


def test_below_the_floor_the_card_says_it_could_not_measure():
    prior = _season(2025, range(1, 18), out_weeks=(9,))
    cur = _season(2026, range(1, 3))
    got = rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [_out()], cur, prior, 2026, 3)
    n = got[("RB Two", RUSH_YDS)][0]
    assert not n["measured"] and n["delta"] is None and n["n_out"] == 1
    assert "usage likely up; not enough games to measure (1 missed game" in n["text"], n["text"]


def test_a_share_that_did_not_move_is_said_as_such_not_as_a_boost():
    """Three absences in which RB Three, not RB Two, took the work."""
    rows = []
    for w in range(1, 18):
        if w in (5, 6, 7):
            rows += [_row(2025, w, "RB Two", "KC", "RB", carries=10),
                     _row(2025, w, "RB Three", "KC", "RB", carries=15)]
        else:
            rows += [_row(2025, w, "RB One", "KC", "RB", carries=15),
                     _row(2025, w, "RB Two", "KC", "RB", carries=10),
                     _row(2025, w, "RB Three", "KC", "RB", carries=0)]
    got = rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [_out()], [], rows, 2026, 1)
    n = got[("RB Two", RUSH_YDS)][0]
    assert n["measured"] and "did not move" in n["text"], n["text"]


def test_two_seasons_do_not_pool_the_same_week_number():
    """Week 3 of 2025 and week 3 of 2026 are two games. Keyed by week
    alone they were one, and a share averaged across both."""
    prior = _season(2025, range(1, 18), out_weeks=(3, 4, 5))
    cur = _season(2026, range(1, 4))          # played weeks 1-3, all with RB One
    got = rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [_out()], cur, prior, 2026, 4)
    n = got[("RB Two", RUSH_YDS)][0]
    assert n["n_out"] == 3, n
    weeks = rd.team_weeks(prior + cur, "KC")
    assert (2025, 3) in weeks and (2026, 3) in weeks and 3 not in weeks


def test_the_window_starts_the_week_he_first_appeared():
    """A man signed in week 6 did not 'miss' weeks 1-5."""
    prior = [r for r in _season(2025, range(1, 18))
             if not (r["player_display_name"] == "RB One" and r["week"] < 6)]
    got = rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [_out()], [], prior, 2026, 1)
    n = got[("RB Two", RUSH_YDS)][0]
    assert n["n_out"] == 0 and not n["measured"], n
    assert "has not missed a game" in n["text"]


def test_this_seasons_window_stops_before_the_week_being_built():
    """The week being built has no stats yet — or Thursday's only — and
    must not read as a missed game for everyone who plays Sunday."""
    cur = _season(2026, range(1, 3)) + _season(2026, (3,), out_weeks=(3,))
    got = rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [_out()], cur, [], 2026, 3)
    assert got[("RB Two", RUSH_YDS)][0]["n_out"] == 0


def test_only_the_same_position_group_and_the_usage_it_feeds():
    prior = _season(2025, range(1, 18), out_weeks=(5, 6, 7, 8))
    props = [_Prop("WR One", "KC", "WR", REC_YDS),       # a receiver: RB out is not his ripple
             _Prop("RB Two", "KC", "RB", REC_YDS),       # an RB's receiving card: carries do not feed it
             _Prop("RB Two", "KC", "RB", RUSH_YDS),
             _Prop("RB Two", "LAC", "RB", RUSH_YDS)]     # another team's RB
    got = rd.ripples_for_props(props, [_out()], [], prior, 2026, 1)
    assert set(got) == {("RB Two", RUSH_YDS)}, set(got)
    # A receiver out feeds targets on the receivers' cards, never carries.
    wr_out = _out(player="WR One", pos="WR")
    got = rd.ripples_for_props([_Prop("WR Two", "KC", "WR", RECEPTIONS),
                                _Prop("RB Two", "KC", "RB", RUSH_YDS)],
                               [wr_out], [], prior, 2026, 1)
    assert set(got) == {("WR Two", RECEPTIONS)}, set(got)


def test_a_questionable_teammate_is_not_out_and_a_never_played_one_has_nothing_to_give():
    prior = _season(2025, range(1, 18), out_weeks=(5, 6, 7, 8))
    q = _out(status="QUESTIONABLE")
    assert rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                                [q], [], prior, 2026, 1) == {}
    rookie = _out(player="RB Rookie")
    assert rd.ripples_for_props([_Prop("RB Two", "KC", "RB", RUSH_YDS)],
                                [rookie], [], prior, 2026, 1) == {}
    # His own hold is not a ripple on his own card.
    assert rd.ripples_for_props([_Prop("RB One", "KC", "RB", RUSH_YDS)],
                                [_out()], [], prior, 2026, 1) == {}


def test_the_row_carries_it_and_the_projection_does_not_read_it():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert 'd["ripples"] = list((ripples or {}).get((prop.player, prop.market)) or [])' in src
    # Attached AFTER the projection and the evaluation: display only.
    assert src.index("proj = build_projection(") < src.index('d["ripples"]')
    assert src.index("rec = evaluate_prop(") < src.index('d["ripples"]')
    # `build_projection` never sees the ripples.
    import inspect
    from engine import projection
    assert "ripple" not in inspect.getsource(projection.build_projection)
    likely = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    assert likely.count('"ripples": row.get("ripples") or []') == 2, \
        "the Most Likely prop and touchdown rows both carry the note"
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "ripples_for_props(slate.props" in build
    assert build.index("ripples_for_props(") < build.index("result = run_slate(")


def test_the_page_says_it_on_the_card_the_prop_page_and_the_likely_card():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    for fn in ("function rippleChip(", "function rippleCardHTML(", "function rippleLine("):
        assert fn in app, fn
    i = app.index("function cardHTML(")
    assert "${rippleChip(r)}" in app[i:i + 12000], "the board card has no ripple chip"
    assert app.count("${rippleCardHTML(r)}") == 2, \
        "the prop page and the depth panel both carry the Next man up block"
    i = app.index("function likelyCard(")
    assert "${rippleLine(r)}" in app[i:i + 9000], "the Most Likely card has no ripple line"
    i = app.index("function rippleCardHTML(")
    assert "has not been moved" in app[i:i + 1500], \
        "the block must say the projection did not move for it"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
