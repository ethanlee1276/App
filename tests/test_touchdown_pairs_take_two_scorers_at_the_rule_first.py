"""Football's touchdown pairs take two scorers at our touchdown rule first (step AAP, 21 November).

Ethan, 2026-11-21: "dial in the 2-leg parlays, the 3-leg parlays, and the 2-leg touchdown picks".
On the record of every settled Most Likely touchdown pick, a college scorer at 40% or better
scored 51% then 53% of the time, one under it 41% then 36%: two at the rule land together about
27% of the time, two under it about 15%. The rule (TD_RULE_PAIR) was the pair card's words only;
now it orders the pairs (after their stand-ins, before their research) and the scorers tried.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402

SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
GAME = {"home": "SF", "away": "DAL", "date": "2099-11-15", "kickoff": "16:25", "spread": -3.5, "total": 46.5}


def _scorer(player, team, pos, p, research, odds=150):
    return {"player": player, "team": team, "opponent": "DAL" if team == "SF" else "SF", "home": "SF", "away": "DAL",
            "position": pos, "market": "anytime_td", "market_label": "Anytime TD", "side": "Over", "line": 0.5,
            "odds": odds, "book": "DraftKings", "p": p, "research": research, "research_of": GP.RESEARCH_MAX,
            "game_date": "2099-11-15"}


def _pair(*ps, research=(5, 5), stand_ins=0):
    return {"legs": [{"p": p, "research": r} for p, r in zip(ps, research)], "joint": round(ps[0] * ps[1], 4),
            "stand_ins": stand_ins}


def test_a_pair_at_the_rule_ranks_ahead_of_a_stronger_research_case_under_it():
    rank = GP.scorer_rank(True)
    at = _pair(0.45, 0.41, research=(3, 2))
    under = _pair(0.45, 0.33, research=(7, 7))
    assert sorted([under, at], key=rank)[0] is at, "both scorers at 40%: first, whatever the research says"
    # Inside each side of the rule the research still orders them, and a stand-in still goes last.
    hi, lo = _pair(0.42, 0.41, research=(6, 6)), _pair(0.50, 0.44, research=(2, 2))
    assert sorted([lo, hi], key=rank)[0] is hi
    stand = _pair(0.60, 0.55, stand_ins=1)
    assert sorted([stand, under], key=rank)[0] is under
    # Hockey's pairs rank on our chance alone, as before.
    assert sorted([at, under], key=GP.scorer_rank(False))[0] is at
    os.environ["QB_TD_RULE_FIRST"] = "off"
    try:
        assert sorted([under, at], key=GP.scorer_rank(True))[0] is under, "the switch: research first again"
    finally:
        os.environ.pop("QB_TD_RULE_FIRST", None)


def test_a_game_with_two_scorers_at_the_rule_posts_them_first():
    scorers = [_scorer("Red Zone Back", "SF", "RB", 0.36, 9), _scorer("Slot Weapon", "DAL", "WR", 0.34, 8),
               _scorer("Lead Back", "SF", "RB", 0.47, 4), _scorer("Big Receiver", "DAL", "WR", 0.43, 3)]
    pairs = GP.build_game("nfl", GAME, [], scorers)["scorers"]
    assert pairs, "the game posts its pairs"
    first = {l["player"] for l in pairs[0]["legs"]}
    assert first == {"Lead Back", "Big Receiver"}, first
    assert pairs[0].get("td_rule") is True or all(float(l["p"]) >= GP.TD_RULE_PAIR for l in pairs[0]["legs"])


def test_the_record_behind_it_is_in_its_words():
    assert GP.TD_RULE_PAIR == 0.40 and GP.TD_RULE_SPORTS == ("nfl", "cfb")
    for words in ("scored 51% of the time in the first 60% of days and 53%", "Switch: QB_TD_RULE_FIRST=off",
                  "this lifts how often\n#: a pair lands, not its price"):
        assert words in SRC, words


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
