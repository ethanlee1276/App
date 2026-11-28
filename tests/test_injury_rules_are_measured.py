"""The injury knock-on rules carry measured numbers, and fire once.

The 2026-09-23 scan ("make sure all the models aren't being affected by
issues where data isn't being used … we don't want to have any mistakes
with our models") found every knock-on in engine/injuries.py hand-set and
most of them bigger than the games show: an opponent's starting corner out
was ×1.09 on every catch and yard, measured ×1.03 on a receiver's yards;
the quarterback's own tackle out was ×0.95 on passing yards, measured
×1.00. engine/injuryfit.py measures each rule the way the board applies it;
`python3 injuryfit.py` re-runs it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import injuryfit as F                                    # noqa: E402
from engine.injuries import KNOCK_ONS, KnockOn, evaluate_injuries     # noqa: E402
from engine.models import Injury, Prop, SportsbookLine, PASS_YDS, REC_YDS, RECEPTIONS, RUSH_YDS  # noqa: E402


def _prop(position, market, team="NO", opp="DET", usage="wr1"):
    return Prop(player="P", team=team, opponent=opp, position=position, market=market, logs=[],
                career_avg=0.0, vs_opponent_avg=None, lines=[SportsbookLine("x", 50.5)], usage_role=usage)


def _out(role, team="DET", who="X"):
    return Injury(player=who, team=team, position="", role=role, status="OUT")


def test_the_rules_in_use_are_the_measured_ones():
    by = {r.key: r for r in KNOCK_ONS}
    assert by["cb_out_wr_yds"].mult == 1.03 and by["cb_out_wr_rec"].mult == 1.06 and by["cb_out_te"].mult == 1.03
    assert by["dl_out_rb"].mult == 1.02 and by["ol_out_wr"].mult == 0.96
    assert [r.key for r in KNOCK_ONS if not r.measured] == ["slot_out_wr2"], "the one too rare to measure"
    assert not any(PASS_YDS in r.markets for r in KNOCK_ONS), "own tackle out measured ×1.00 on passing"


def test_a_rule_fires_once_however_many_are_out():
    two = [_out("cb1", who="A"), _out("cb1", who="B")]
    eff = evaluate_injuries(_prop("WR", RECEPTIONS), two)
    assert eff.multiplier == 1.06 and eff.reasons == ["Opponent CB A and B out — coverage downgrade"]
    assert evaluate_injuries(_prop("WR", REC_YDS), two).multiplier == 1.03
    assert evaluate_injuries(_prop("RB", REC_YDS, usage="rb1"), two).multiplier == 1.0, \
        "a corner out was never measured to move a back"
    assert evaluate_injuries(_prop("RB", RUSH_YDS, usage="rb1"), [_out("dt")]).multiplier == 1.02
    assert evaluate_injuries(_prop("QB", PASS_YDS, usage="starter"), [_out("LT", team="NO")]).multiplier == 1.0
    assert evaluate_injuries(_prop("WR", REC_YDS), [_out("LT", team="NO")]).multiplier == 0.96
    assert evaluate_injuries(_prop("WR", REC_YDS), [_out("cb1", team="NO")]).multiplier == 1.0, "his own corner"
    q = Injury(player="Q", team="DET", position="CB", role="cb1", status="QUESTIONABLE")
    assert evaluate_injuries(_prop("WR", REC_YDS), [q]).multiplier == 1.0, "only a ruled-out player counts"


def _season(effect=1.5):
    """Two teams, one receiver each, ten weeks: DET's corner is out in weeks
    6 and 8, and the receiver facing DET does ``effect`` times his usual."""
    rows = []
    for wk in range(1, 11):
        for team, opp, name in (("NO", "DET", "Olave"), ("DET", "NO", "St. Brown")):
            y = 60.0 * (effect if (opp == "DET" and wk in (6, 8)) else 1.0) + (wk % 3)
            rows.append({"season_type": "REG", "week": str(wk), "team": team, "opponent_team": opp,
                         "player_display_name": name, "position": "WR", "targets": "8",
                         "receiving_yards": str(y), "receptions": "5"})
    out = {wk: ({"DET": {"cb1"}} if wk in (6, 8) else {}) for wk in range(1, 11)}
    return rows, out


def test_the_fitter_recovers_a_known_effect():
    rule = KnockOn("t", "opp", frozenset({"cb1"}), frozenset({"WR"}), frozenset({REC_YDS}), 1.0, "")
    rows, out = _season(1.5)
    pts = F.samples(rows, out, (rule,))["t"]
    assert sum(1 for _e, fl, _y in pts if fl) == 2, "two flagged games"
    m = F.measure(pts)
    assert 1.4 < m["mult"] < 1.6 and m["n"] == 2
    rows, out = _season(1.0)
    assert abs(F.measure(F.samples(rows, out, (rule,))["t"])["mult"] - 1.0) < 0.05, "no effect, no multiplier"
    assert F.measure([])["mult"] is None


def test_the_wr2_filter_is_the_board_s_ranking():
    rule = KnockOn("s", "opp", frozenset({"cb1"}), frozenset({"WR"}), frozenset({REC_YDS}), 1.0, "",
                   usage=frozenset({"wr2"}))
    rows, out = _season(1.5)
    assert F.samples(rows, out, (rule,))["s"] == [], "each team has one receiver: a WR1, not a WR2"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
