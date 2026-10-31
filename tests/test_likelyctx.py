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


def test_a_flag_on_most_of_the_record_is_the_record_and_is_not_fitted():
    rows = _picks(True)
    for r in rows:
        r["flags"] = r["flags"] + ["thin_sample"]                   # up on every pick
    ks = C.fit_flags(rows)
    assert "thin_sample" not in ks, "the whole record's over-claim is likelycal's, not a flag's"
    assert "dog_run_over" in ks


def test_the_correction_stacks_on_likelycal_and_never_corrects_twice():
    pick = {"flags": ["dog_run_over"], "p": 0.70, "odds": -120, "won": False, "day": "2026-09-27",
            "player": "x", "team": "LV", "side": "OVER", "sources": {"board", "bold"}, "ctx": None}
    q = C.price_chance(-120)
    cal = {"bold|over": {"k": 0.25}, "list|over": {"k": 1.0}}
    base = C._rows_for_fit([pick], cal)[0]["p"]
    assert abs(base - (q + 0.25 * (0.70 - q))) < 1e-9, "the fit starts from what the board shows after likelycal"
    listed = dict(pick, sources={"list", "board"})
    assert C._rows_for_fit([listed], cal)[0]["p"] == 0.70, "the list's pick, left alone by likelycal, stays raw"
    assert C.maker({"board", "matchup"}) == "matchup" and C.maker({"list", "bold"}) == "bold"


def test_history_proves_a_flag_only_in_both_halves_and_never_one_the_model_prices():
    from engine import scouthist as H
    cell = lambda g1, g2, n=500: {"early": {"n": n, "rate": 0.3, "base": 0.3 - g1, "gap": g1},
                                  "late": {"n": n, "rate": 0.3, "base": 0.3 - g2, "gap": g2}}
    h = {"flags": {"back_from_absence": {"rec_yds OVER": cell(-0.076, -0.069), "rec_yds UNDER": cell(0.07, 0.06),
                                         "anytime_td YES": cell(-0.065, -0.084),
                                         "rush_att OVER": {"late": cell(-0.1, -0.1)["late"]}},
                   "wind_pass_over": {"pass_yds OVER": cell(-0.16, -0.19)},
                   "shootout_under": {"pass_att UNDER": cell(-0.03, -0.06, n=140), "rec_yds UNDER": cell(-0.05, 0.01)},
                   "boom_bust": {"pass_yds UNDER": cell(-0.09, -0.04, n=40)}}}
    found = H.proven(h)
    assert set(found) == {"back_from_absence", "shootout_under"}, found
    assert found["back_from_absence"]["rec_yds OVER"]["shift"] == -0.069, "the smaller half's gap"
    assert "rush_att OVER" not in found["back_from_absence"], "one half is not proof"
    assert "wind_pass_over" not in found, "the model already prices wind"
    assert "pass_att UNDER" in found["shootout_under"] and "rec_yds UNDER" not in found["shootout_under"]


def test_a_proven_history_shift_lowers_the_pick_and_says_why():
    hist = {"flags": {"back_from_absence": {"rec_yds OVER": {"shift": -0.069, "n": 1557},
                                            "anytime_td YES": {"shift": -0.065, "n": 1803}}}}
    over = {"market": "rec_yds", "side": "OVER", "odds": -150, "model_prob": 0.68, "scout_flags": ["back_from_absence"]}
    td = {"market": "anytime_td", "odds": +150, "model_prob": 0.45, "scout_flags": ["back_from_absence"]}
    under = {"market": "rec_yds", "side": "UNDER", "odds": -150, "model_prob": 0.68,
             "scout_flags": ["back_from_absence"]}
    assert C.apply([over, td, under], "nfl", store={}, history=hist) == 2
    assert over["model_prob"] == round(0.68 - 0.069, 4) and "first game back" in over["ctx_note"]
    assert td["model_prob"] < 0.45, "a scorer with no side written is read as a yes"
    assert under["model_prob"] == 0.68, "an under is never raised, and this one has no proven shift"
    cheap = {"market": "rec_yds", "side": "OVER", "odds": -110, "model_prob": 0.53,
             "scout_flags": ["back_from_absence"]}
    C.apply([cheap], "nfl", store={}, history=hist)
    assert cheap["model_prob"] == round(C.price_chance(-110), 4), "lowered, but never below the price"
    priced = {"market": "anytime_td", "odds": +110, "model_prob": 0.45, "scout_flags": ["back_from_absence"]}
    assert C.apply([priced], "nfl", store={}, history=hist) == 0, "the price already says less: left as it is"


def test_the_history_store_round_trips_and_runs_weekly():
    from engine import scouthist as H
    p = Path(tempfile.mkdtemp()) / "scout_history.json"
    H.save({"back_from_absence": {"receptions OVER": {"shift": -0.046, "n": 1569}}}, [2021, 2025], p)
    store = H.load(p)
    assert H.shift_for(["thin_sample", "back_from_absence"], "receptions", "over", store) == (-0.046,
                                                                                               "back_from_absence")
    assert H.shift_for(["back_from_absence"], "receptions", "UNDER", store) == (0.0, None)
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    body = src[src.index("def _run_deep_refit("):src.index("def _run_lab(")]
    assert '_spawn_module("engine.scouthist", log)' in body, "re-measured every week with the deep fitters"


def test_the_store_round_trips_and_the_board_runs_the_read():
    p = Path(tempfile.mkdtemp()) / "ctx.json"
    C.save({"sport": "nfl", "flags": {"thin_sample": {"k": 0.6, "n": 31, "hit": 0.5, "claimed": 0.6}},
            "held_out": {"n": 10}, "fitted_at": "now"}, p)
    assert C.load(p)["nfl"]["flags"]["thin_sample"]["k"] == 0.6
    src = open(os.path.join(ROOT, "engine", "likelyboard.py"), encoding="utf-8").read()
    i, j = src.index("_calibrate([pool[k] for k in order]"), src.index("_ctx.annotate(_rows, result, sport)")
    assert i < j, "the scout reads after the record's calibration"
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "<b>Scout:</b>" in js and "r.ctx_note" in js


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
