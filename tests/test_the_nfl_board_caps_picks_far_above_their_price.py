"""The NFL's Most Likely picks far above their own price are capped at it plus ten points (step AAV, 21 November).

Ethan's answer to decision 17: "cap them". On the public record of every settled NFL Most Likely pick, those
shown more than ten points over their own price's chance (the book's cut taken out) hit 65 of 137 (47%)
where we said 79%; every other NFL pick hit 60% where we said 62%. The books' field (`trust_price`) only holds
a pick whose number three books quote on both sides, so these, mostly alternate numbers one book prices, kept
their own. Now an NFL prop is shown at no more than its own price's chance plus NFL_CAP_ROOM.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import likelyboard as LB          # noqa: E402

SRC = (ROOT / "engine" / "likelyboard.py").read_text(encoding="utf-8")


def _row(p, odds, **kw):
    return {"player": "Far Over", "market": "receptions", "side": "Over", "line": 3.5, "odds": odds,
            "book": "DraftKings", "model_prob": p, "kind": "prop", **kw}


def test_a_pick_far_over_its_price_is_shown_at_the_price_plus_ten_points():
    fair = (130 / 230) / 1.045                                   # -130 with the book's cut out: 54.1%
    r = _row(0.87, -130)
    stats: dict = {}
    assert LB.cap_far_over([r], "nfl", stats=stats) == 1 and stats == {"capped": 1, "capped_posted": 0}
    assert r["model_prob"] == round(fair + 0.10, 4) and r["nfl_cap"] == r["model_prob"]
    assert r["board_raw_prob"] == 0.87 and r["ceiling_from"] == r["trust_from"] == 0.87
    assert "hit 47% on our record where we said 79%" in r["trust_note"] and "64%" in r["trust_note"], r["trust_note"]
    # Within ten points of its price: untouched.
    near = _row(0.62, -130)
    assert LB.cap_far_over([near], "nfl") == 0 and near["model_prob"] == 0.62 and "nfl_cap" not in near


def test_the_cap_leaves_what_it_should():
    for r in (_row(0.87, -130, trust_rule=["field"]),            # the books' field holds it already
              _row(0.87, -130, paper_hold=True),                 # on paper: its own claim is what is measured
              _row(0.87, -130, has_market=False),                # no real price
              _row(0.87, -130, book="proxy"),
              _row(0.87, None),                                  # no price at all
              dict(_row(0.87, -130), kind="game", market="moneyline")):
        assert LB.cap_far_over([r], "nfl") == 0 and r["model_prob"] == 0.87, r
    for sport in ("cfb", "nba", "nhl", "mlb"):
        r = _row(0.87, -130)
        assert LB.cap_far_over([r], sport) == 0 and r["model_prob"] == 0.87, sport
    os.environ["QB_NFL_CAP"] = "off"
    try:
        r = _row(0.87, -130)
        assert LB.cap_far_over([r], "nfl") == 0 and r["model_prob"] == 0.87
    finally:
        os.environ.pop("QB_NFL_CAP", None)


def test_a_posted_pick_is_restated_and_counted():
    r = _row(0.90, -150, locked=True)
    stats: dict = {}
    LB.cap_far_over([r], "nfl", stats=stats)
    assert stats == {"capped": 1, "capped_posted": 1} and r["model_prob"] == round((150 / 250) / 1.045 + 0.10, 4)


def test_it_runs_with_the_ceilings_on_the_number_the_page_shows():
    body = SRC[SRC.index("    ceiling_stats: dict = {}"):SRC.index("    rows, tiers, lanes, held = [], {t: 0 for t, _ in TIERS}, {}, []")]
    assert body.index("hold_to_own_price(") < body.index("cap_far_over(") < body.index("mark_one_sided(")
    assert LB.NFL_CAP_ROOM == 0.10 and LB.NFL_CAP_SPORTS == ("nfl",)
    for words in ("hit 65 of 137 (47%) where\n#: we said 79%", "Off without a deploy: ``sudo ./deploy/setenv.sh QB_NFL_CAP off``"):
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
