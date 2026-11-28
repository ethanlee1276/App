"""A read whose only pick from us goes the other way is mixed, never a breakout (step ACZ).

Ethan, 23 November: "I'm still noticing like conflicting information in the
game reports compared to the picks we're giving and the breakout candidates
we're giving." A report could list a player under "Breakout candidates" and
then, on the same card, say "Our Most Likely pick on this player goes the
other way: Under 25.5 points". Now such a read (the list has him on the
other side, and nothing of ours sits on the read's side) is mixed, as a
verdict against the defense's own number has been since step ACW: neutral,
its first reason and our pick said side by side, off the breakout and fade
lists. The pick itself is untouched.

Run directly: `python3 tests/test_a_read_our_own_pick_goes_against_is_mixed.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import breakouts as BO                    # noqa: E402
from engine import gamereport as GR                   # noqa: E402
from engine import matchpicks as MP                   # noqa: E402

UNDER = {"player": "Jay Star", "market": "pts", "market_label": "Points", "side": "UNDER", "line": 25.5,
         "odds": -130, "model_prob": 0.61}


def _read(read="breakout", **kw):
    r = {"player": "Jay Star", "team": "BOS", "opp": "MIA", "pos": "", "read": read,
         "label": {"breakout": "Breakout spot", "good": "Good matchup", "tough": "Tough matchup"}.get(read, "Neutral"),
         "pro": ["MIA allows the 2nd-most points a game (119.4)", "Minutes up 20% over the last five"],
         "con": ["MIA allows the 2nd-fewest rebounds a game (40.2)"], "notes": [], "lean": ["pts"],
         "usage": {"mpg": 34.0}}
    r.update(kw)
    return r


def test_a_breakout_our_list_takes_the_under_on_is_mixed():
    x = _read(pick_other_side=UNDER)
    assert MP.settle_other_side([x]) == 1
    assert x["read"] == "neutral" and x["label"] == "Neutral" and x["mixed_was"] == "breakout"
    assert x["mixed"] == "MIA allows the 2nd-most points a game (119.4)" and x["mixed_pick"] is UNDER
    assert GR.verdict_of(x) == GR.MIXED_LABEL
    assert GR.tone_of(x) == ("", "Neutral matchup — the numbers point both ways")
    assert GR.mixed_line(x) == ("The numbers point both ways: MIA allows the 2nd-most points a game (119.4), "
                                f"but our number takes {GR._pick_words(UNDER)} — so neither way")
    assert GR.read_pick(x).startswith("Our Most Likely pick on this player goes the other way"), \
        "the pick itself is still said"


def test_a_tough_read_our_list_takes_the_over_on_is_mixed_on_its_own_reason():
    over = dict(UNDER, side="OVER")
    x = _read("tough", pick_other_side=over)
    MP.settle_other_side([x])
    assert x["read"] == "neutral" and x["mixed"] == "MIA allows the 2nd-fewest rebounds a game (40.2)"


def test_a_read_with_a_pick_on_its_own_side_is_left_as_it_is():
    for extra in ({"pick": dict(UNDER, side="OVER")}, {"matchup_pick": dict(UNDER, side="OVER", market="reb")}):
        x = _read(pick_other_side=UNDER, **extra)
        assert MP.settle_other_side([x]) == 0 and x["read"] == "breakout", extra
    assert MP.settle_other_side([_read("neutral", pick_other_side=UNDER)]) == 0
    assert MP.settle_other_side([_read()]) == 0, "no pick the other way: nothing to settle"


def test_a_settled_read_is_off_the_breakout_list():
    settled = _read(pick_other_side=UNDER)
    MP.settle_other_side([settled])
    other = _read(player="Al Wing")
    other["player"] = "Al Wing"
    blocks = BO.blocks([settled, other])
    names = [i["player"] for b in blocks if b.get("type") == "verdicts" for i in b["items"]]
    assert names == ["Al Wing"], names


def test_the_matchup_picks_settle_every_game_they_build():
    games = [{"home": "BOS", "away": "MIA", "kickoff": "19:30", "scan": True}]
    x = _read(pick_other_side=UNDER)
    reads = {"MIA@BOS": {"players": [x]}}
    MP.build(games, reads, [], [], sport="nba")
    assert x["read"] == "neutral" and x.get("mixed_pick") is UNDER, x


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
