"""Probable starters on the ballpark cards.

"Who's pitching tonight?" is the first question a bettor asks about a
game, and the model already knows the answer — it prices every batter
matchup off those arms. The card now says it instead of making the
reader open the game page to find out.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.pipeline import run_mlb_slate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLATE = os.path.join(ROOT, "data", "mlb_sample_slate.json")


def test_the_board_ships_the_probable_starters():
    """The Game object always carried them (the matchup math runs on
    them); the board dict did not — the first cut shipped an empty dict
    because g.pitchers holds Pitcher DATACLASSES and the serializer
    guarded isinstance(dict). Display fields only, both sides."""
    g = run_mlb_slate(SLATE)["games"][0]
    p = g.get("pitchers") or {}
    assert p.get("home", {}).get("name") and p.get("away", {}).get("name")
    for side in ("home", "away"):
        assert p[side].get("throws") in ("L", "R")
        assert p[side].get("xera") is not None


def test_the_card_renders_the_arms_in_matchup_order():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function gameCard(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    assert "g.pitchers.away" in fn and "g.pitchers.home" in fn
    # Away first, then home — the same order the matchup line reads.
    assert fn.index("pfmt(g.pitchers.away)") < fn.index(
        "pfmt(g.pitchers.home)")
    assert '"TBD"' in fn, "a missing probable must say so, not vanish"
    assert "${starters}" in fn, "built but never placed on the card"
    assert "xERA" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
