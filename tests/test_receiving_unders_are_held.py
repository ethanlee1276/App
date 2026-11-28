"""Receiving-yards unders come off the NFL and college boards, and college
can join the price cap on one command (engine/likelyboard).

Ethan, 2026-10-31: "keep diving deeper into our NFL edge and most likely bets
and the college edge and most likely bets ... to find better picks." Every
graded Most Likely pick in the public receipts, split at the middle of each
league's season: receiving-yards unders were short of the claim in both
halves in both leagues (NFL 48% vs 65% then 48% vs 53%; college 50% vs 70%
then 50% vs 62%). And the college board's "bolder than the books" picks claim
69% and hit 53% (283 unders, z −6.0) — the over-claim the NFL's price cap
fixed on 2026-10-17; college joins it when its own test passes and Ethan says
yes, with one setenv.

Run directly: `python3 tests/test_receiving_unders_are_held.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as B                              # noqa: E402


class _Env:
    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _prop(market="rec_yds", side="UNDER", **kw):
    return {"kind": "prop", "player": "A Receiver", "team": "DET", "opponent": "NYJ", "market": market,
            "side": side, "line": 45.5, "odds": -130, "model_prob": 0.66, "implied_prob": 0.64, **kw}


def test_an_nfl_receiving_yards_under_is_held_and_its_over_is_not():
    with _Env(QB_NFL_TIGHT=None):
        why = B.tightened_reason(_prop(), "nfl")
        assert why and why.startswith("held back: a receiving-yards under")
        assert "48% where we said 58%" in why
        assert B.tightened_reason(_prop(side="OVER"), "nfl") is None, "the over holds up"
        assert B.tightened_reason(_prop(market="receptions"), "nfl") is None, "receptions unders stay"
        assert B.tightened_reason(_prop(locked=True), "nfl") is None, "a posted pick keeps its seat"
    with _Env(QB_NFL_TIGHT="off"):
        assert B.tightened_reason(_prop(), "nfl") is None, "QB_NFL_TIGHT=off puts it back"


def test_a_college_receiving_yards_under_is_held_on_its_own_switch():
    with _Env(QB_CFB_TIGHT=None):
        why = B.tightened_reason(_prop(), "cfb")
        assert why and "50% where we said 64%" in why
        assert B.tightened_reason(_prop(side="OVER"), "cfb") is None
        assert B.tightened_reason(_prop(market="pass_yds"), "cfb") is None, "only the market the record named"
        assert B.tightened_reason(_prop(reserve=True), "cfb") is None
    with _Env(QB_CFB_TIGHT="off"):
        assert B.tightened_reason(_prop(), "cfb") is None, "QB_CFB_TIGHT=off puts it back"
    assert B.tightened_reason(_prop(), "nba") is None, "no other league"


def test_college_joins_the_price_cap_only_when_named():
    with _Env(QB_PRICE_TRUST=None, QB_PRICE_TRUST_ADD=None):
        assert B.price_trust_rule("cfb") is None, "not until its own test passes and Ethan says yes"
        assert B.price_trust_rule("nfl") == (1.0, 0.0)
    with _Env(QB_PRICE_TRUST=None, QB_PRICE_TRUST_ADD="cfb"):
        assert B.price_trust_rule("cfb") == (1.0, 0.0), "one setenv puts college at the NFL's rule"
        assert B.price_trust_rule("nba") is None
    with _Env(QB_PRICE_TRUST="off", QB_PRICE_TRUST_ADD="cfb"):
        assert B.price_trust_rule("cfb") is None and B.price_trust_rule("nfl") is None, "the off switch wins"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
