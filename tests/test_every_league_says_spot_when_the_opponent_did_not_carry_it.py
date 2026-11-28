"""Every league's verdict says "spot" when the opponent did not carry it (step ACY).

Ethan, 23 November, on a report calling a tight end's game a tough matchup
beside a defence giving up the 2nd-most to tight ends: "It doesn't really
make much sense compared to the data we're giving out." Football's reads
have said "Tough spot" since step ACW when the defence had no vote in the
verdict (the wind, the lines). The NBA's, the WNBA's, college basketball's,
hockey's and baseball's still said "Tough matchup" on a back-to-back and a
blowout spread alone. One rule now, in engine/readlogic: a good, tough or
avoid read that no opponent family carried (its defence, the goalie, the
starter and his hand, its penalties) says "spot" and carries ``spot`` and
``drivers``, which the reports and the cards already read.

Run directly: `python3 tests/test_every_league_says_spot_when_the_opponent_did_not_carry_it.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import readlogic as RL                    # noqa: E402
from engine.nba import scan as S                      # noqa: E402


def _hist(mins, pts, reb=None, ast=None, team="BOS"):
    n = len(mins)
    dates = [f"2026-01-{30 - i:02d}" for i in range(n)]
    h = {"team": team, "starter": True, "minutes": list(mins), "pts": list(pts),
         "reb": list(reb or [2] * n), "ast": list(ast or [1] * n), "fg3m": [0] * n,
         "dates": dates, "opps": ["NYK"] * n, "by_week": {}}
    for i, d in enumerate(dates):
        h["by_week"][d] = {"min": mins[i], "pts": h["pts"][i], "reb": h["reb"][i], "ast": h["ast"][i]}
    return h


# --- the rule ------------------------------------------------------------------------------------
def test_the_families_that_carried_a_verdict_are_counted_one_vote_each():
    fam = {"a": RL.SCHEDULE, "b": RL.BLOWOUT, "c": RL.DEFENSE, "d": RL.DEFENSE}
    assert RL.carried_by("tough", ["c"], ["a", "b", "d"], fam) == [RL.BLOWOUT, RL.SCHEDULE], \
        "the defence's two reasons cancel: it carried nothing"
    assert RL.carried_by("good", ["c", "d"], ["a"], fam) == [RL.DEFENSE]
    assert RL.carried_by("neutral", ["c"], ["a"], fam) == []


def test_a_verdict_no_opponent_carried_says_spot_and_one_it_carried_says_matchup():
    fam = {"b2b": RL.SCHEDULE, "spread": RL.BLOWOUT, "dfn": RL.DEFENSE}
    spot = RL.mark_spot({"read": "tough", "label": "Tough matchup", "pro": [], "con": ["b2b", "spread"]}, fam)
    assert spot["label"] == "Tough spot" and spot["spot"] is True and spot["drivers"] == [RL.BLOWOUT, RL.SCHEDULE]
    real = RL.mark_spot({"read": "tough", "label": "Tough matchup", "pro": [], "con": ["b2b", "dfn"]}, fam)
    assert real["label"] == "Tough matchup" and "spot" not in real and RL.DEFENSE in real["drivers"]
    good = RL.mark_spot({"read": "good", "label": "Good matchup", "pro": ["b2b", "spread"], "con": []}, fam)
    assert good["label"] == "Good spot" and good["spot"]
    avoid = RL.mark_spot({"read": "avoid", "label": "Avoid", "pro": [], "con": ["b2b", "spread"]}, fam)
    assert avoid["label"] == "Avoid" and avoid["spot"], "avoid keeps its word; the report says it is a spot"
    brk = RL.mark_spot({"read": "breakout", "label": "Breakout spot", "pro": ["b2b", "spread"], "con": []}, fam)
    assert brk["label"] == "Breakout spot" and "spot" not in brk, "a breakout keeps its own word"
    for fam_name in (RL.GOALIE, RL.PITCHER, RL.PLATOON, RL.SPECIAL_TEAMS):
        r = RL.mark_spot({"read": "good", "label": "Good matchup", "pro": ["x", "b2b"], "con": []},
                         {"x": fam_name, "b2b": RL.SCHEDULE})
        assert r["label"] == "Good matchup", fam_name


def test_football_and_every_other_league_use_the_same_words():
    from engine import gamescan
    assert gamescan.SPOT_LABELS == RL.SPOT_LABELS


# --- the leagues ---------------------------------------------------------------------------------
def test_an_nba_read_carried_by_the_schedule_and_the_lines_says_tough_spot():
    h = _hist(mins=[34] * 15, pts=[20] * 15)
    # A starter needs one family more against him before he reads tough (readlogic.ladder).
    env = {"BOS": {"implied": 104.0, "league_pts": 113.0, "pace": None, "league_pace": None, "spread": 12.0}}
    r = S.read_player("Jay Star", h, "BOS", "MIA", env=env, rest={"BOS": "3in4", "MIA": "2plus"})
    assert r["read"] == "tough", r
    assert r["label"] == "Tough spot" and r["spot"] is True, r["label"]
    assert r["drivers"] == [RL.BLOWOUT, RL.POINTS, RL.SCHEDULE], r["drivers"]
    # The same night with the defence against him too: a matchup.
    dvp = {"MIA": {"pts": {"pg": 104.0, "league": 113.0, "rank": 30, "of": 30, "games": 9}}}
    r2 = S.read_player("Jay Star", h, "BOS", "MIA", env=env, rest={"BOS": "3in4", "MIA": "2plus"}, dvp=dvp)
    assert r2["read"] in ("tough", "avoid") and r2["label"] in ("Tough matchup", "Avoid"), r2["label"]
    assert "spot" not in r2 and RL.DEFENSE in r2["drivers"]


def test_hockey_and_baseball_reads_go_through_the_same_rule():
    for rel, n in (("engine/nhl/scan.py", 2), ("engine/mlb/scan.py", 2), ("engine/nba/scan.py", 1)):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert src.count("return RL.mark_spot(") == n, rel


def test_the_league_report_card_says_the_spot():
    from engine.leaguereport import _verdict
    r = RL.mark_spot({"player": "Jay Star", "team": "BOS", "read": "tough", "label": "Tough matchup",
                      "pro": [], "con": ["b2b", "spread"]}, {"b2b": RL.SCHEDULE, "spread": RL.BLOWOUT})
    card = _verdict(r, both=True)
    assert card["label"] == "Tough spot" and card["verdict"] == "down"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
