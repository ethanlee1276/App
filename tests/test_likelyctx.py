"""The scout's read on the NFL Most Likely board, and the record's say on it.

Ethan, 2026-10-03: "think like a human when it comes to making the pick
selections." Checks, one rule each: every NFL board row gets the flags a
football person would raise, from its own game's spread, total and weather
and his own recent results; a flag is a note and moves no number until a
store exists; a flag the record proves over-claims (out of sample) pulls a
pick toward its price, by the most cautious flag it carries, and only ever
down; the journal keeps the first claim; a fit on noise does not pass; the
board runs the read after the record's calibration; the card shows it.

Run directly: `python3 tests/test_likelyctx.py`
"""
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyctx as C                                  # noqa: E402


def _result():
    games = [{"home": "KC", "away": "LV", "spread": -9.5, "total": 51.0, "kickoff": "2026-10-04T20:20:00Z",
              "weather": {"dome": False, "wind_mph": 4, "measured": True}}]
    recs = [{"player": "Back Raider", "team": "LV", "logs": [{"week": 1}, {"week": 2}]},
            {"player": "Wide Out", "team": "LV", "logs": [{"week": 1}, {"week": 2}, {"week": 3}]}]
    return {"games": games, "recommendations": recs}


def test_every_board_row_gets_the_scouts_flags_and_no_number_moves():
    rows = [
        {"player": "Back Raider", "team": "LV", "opponent": "KC", "market": "rush_yds", "side": "OVER",
         "line": 55.5, "odds": -130, "model_prob": 0.66, "recent_values": [50, 52, 49, 51, 50, 48]},
        {"player": "Wide Out", "team": "LV", "opponent": "KC", "market": "rec_yds", "side": "UNDER",
         "line": 60.5, "odds": -120, "model_prob": 0.62, "recent_values": [70, 65, 72, 68, 66]},
        {"kind": "game", "market": "moneyline", "model_prob": 0.7},
    ]
    n = C.annotate(rows, _result())
    assert n == 2
    a, b = rows[0], rows[1]
    assert "dog_run_over" in a["scout_flags"] and "back_from_absence" in a["scout_flags"], a["scout_flags"]
    assert "shootout_under" in b["scout_flags"] and "dog_pass_under" in b["scout_flags"]
    assert all(isinstance(t, str) and t for t in a["scout_notes"])
    assert "scout_flags" not in rows[2], "a game row is not a player's spot"
    before = [r["model_prob"] for r in rows]
    assert C.apply(rows, "nfl", store={}) == 0 and [r["model_prob"] for r in rows] == before


def test_a_proven_flag_pulls_toward_the_price_by_its_most_cautious_flag():
    store = {"nfl": {"flags": {"dog_run_over": {"k": 0.5, "n": 40, "hit": 0.48, "claimed": 0.66},
                               "back_from_absence": {"k": 0.2, "n": 35, "hit": 0.4, "claimed": 0.63}}}}
    r = {"player": "x", "market": "rush_yds", "side": "OVER", "odds": -130, "model_prob": 0.66,
         "scout_flags": ["dog_run_over", "back_from_absence"]}
    assert C.apply([r], "nfl", store=store) == 1
    q = C.price_chance(-130)
    assert abs(r["model_prob"] - round(q + 0.2 * (0.66 - q), 4)) < 1e-9, "the smaller k wins"
    assert r["ctx_raw_prob"] == 0.66 and r["board_raw_prob"] == 0.66 and "first game back" in r["ctx_note"]
    low = {"player": "y", "market": "rush_yds", "side": "OVER", "odds": +150, "model_prob": 0.30,
           "scout_flags": ["dog_run_over"]}
    C.apply([low], "nfl", store=store)
    assert low["model_prob"] <= 0.30, "a chance is only ever lowered"


def _picks(flag_effect: bool, seed=7):
    rng = random.Random(seed)
    rows = []
    for g in range(160):
        flagged = g % 2 == 0
        for i in range(3):
            p = 0.65
            truth = 0.45 if (flagged and flag_effect) else 0.65
            rows.append({"flags": ["dog_run_over"] if flagged else [], "p": p, "q": 0.55,
                         "won": rng.random() < truth, "game": f"g{g}"})
    return rows


def test_the_correction_passes_on_a_real_effect_and_not_on_noise():
    real = C.held_out(_picks(True))
    assert real["lo"] > 0, real
    ks = C.fit_flags(_picks(True))
    assert ks["dog_run_over"]["k"] < 1.0 and ks["dog_run_over"]["n"] >= C.MIN_GROUP
    noise = C.held_out(_picks(False))
    assert not noise["lo"] > 0, noise


def test_the_store_round_trips_and_the_board_runs_the_read():
    p = Path(tempfile.mkdtemp()) / "ctx.json"
    C.save({"sport": "nfl", "flags": {"thin_sample": {"k": 0.6, "n": 31, "hit": 0.5, "claimed": 0.6}},
            "held_out": {"n": 10}, "fitted_at": "now"}, p)
    assert C.load(p)["nfl"]["flags"]["thin_sample"]["k"] == 0.6
    src = open(os.path.join(ROOT, "engine", "likelyboard.py"), encoding="utf-8").read()
    i, j = src.index("_calibrate([pool[k] for k in order]"), src.index("_ctx.annotate(_rows, result)")
    assert i < j, "the scout reads after the record's calibration"
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "<b>Scout:</b>" in js and "r.ctx_note" in js


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
