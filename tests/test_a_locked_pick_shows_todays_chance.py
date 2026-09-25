"""A locked Most Likely pick shows today's chance, and the one it went up at.

Ethan, 2026-09-25, circling Jameson Williams UNDER 69.5 receiving yards:
the Model tile read 75% and a TOP tag, while the lock note under his name
said "Our chance has eased under 55% since this went up". "How can we
display our model is saying this has a 71% chance too hit but then say it
went under 55% in the other spot. Which number do I trust? ... We need
the models estimate to be constantly updating."

A locked pick carried the chance it was POSTED at, forever. It now keeps
its number, price and book as posted, and carries the model's chance at
that number off every build (`likely._prob_at`, the derivation a ladder
rung is priced with), today's projection beside it, and the posted
chance as `first_prob`. The note says both numbers.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}
RUNG = [{"book": "Novig", "line": 69.5, "over_odds": 300, "under_odds": -212}]


def _row(projection):
    return {"player": "Jameson Williams", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
            "market_label": "Rush Yards", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
            "has_market": True, "fair_prob": 0.50, "projection": projection, "ev_per_unit": 0.01,
            "reasons": ["because"], "recent_values": [55, 71, 48, 66], "game_date": "2026-09-27",
            "kickoff": "13:00", "hit_prob": 0.56, "raw_prob": 0.58, "alt_lines": RUNG,
            "alt_sharp_lines": []}


def _board(props, previous=None, now="2026-09-24T02:00:00Z"):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    turn: dict = {}
    try:
        rows = K.build(props, sport="nfl", fits=FITS, previous=previous, now=now, turnover=turn)
    finally:
        K.rankable = real
    return rows, turn


def _posted():
    b0, t0 = _board([_row(52.0)], now="2026-09-23T20:00:00Z")
    (r,) = b0
    assert (r["side"], r["line"]) == ("under", 69.5), r
    return b0, t0, r["model_prob"]


def test_the_chance_on_a_locked_pick_is_todays():
    b0, t0, then = _posted()
    prev = {"rows": b0, "day": t0.get("day") or {}, "earlier": []}
    b1, _ = _board([_row(90.0)], previous=prev)
    (r,) = b1
    assert r["locked"] and (r["side"], r["line"]) == ("under", 69.5), "the number stays as posted"
    assert r["model_prob"] < K.MIN_PROB < then, (r["model_prob"], then)
    assert r["first_prob"] == then, "the chance it went up at rides beside it"
    assert r["projection"] == 90.0, "today's projection, not the posted one"
    assert f"now {round(r['model_prob'] * 100)}%, down from {round(then * 100)}%" in r["lock_note"]


def test_the_card_labels_it_now_and_shows_the_posted_chance():
    i = APP.index("function likelyCard(")
    card = APP[i:APP.index("\nfunction ", i + 10)]
    assert 'r.locked ? " now" : ""' in card
    assert "when posted</div>" in card


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
