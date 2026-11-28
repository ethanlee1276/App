"""Near even money, Top and Strong are capped at Worth a look — only once proven.

Ethan, 2026-10-04: "lets do what we need to do." Every one-board pick
graded correctly, and still, at +120 to −149, the board's tiers ran
backwards: Top pick 18-40, Strong 38-52, Worth a look 158-176.
engine/bandcap writes the rule down before its first run; bandcheck
--save stores the verdict; the board caps the label only when a saved
verdict holds. Checks: the four conditions each block the verdict alone;
the board caps an in-band Top pick and leaves a −200 one alone; no
verdict, or one that does not hold, changes nothing; the card shows why.

Run directly: `python3 tests/test_near_even_labels_are_capped_only_when_proven.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())

from engine import bandcap as C                                     # noqa: E402
from engine import likelyboard as B                                 # noqa: E402

#: The one-board fixtures (as tests/test_one_most_likely_board.py): a game
#: with a scan that backs St. Brown's touchdown, so the pick tiers Top.
GAME = {"home": "DET", "away": "NYJ",
        "scan": {"units": {"NYJ": {"def": {"passing": {"rank": 27}, "rushing": {"rank": 25}}},
                           "DET": {"def": {"passing": {"rank": 10}, "rushing": {"rank": 12}}}},
                 "redzone": {"DET": {"off": 12.6, "off_rel": 0.44, "def": 10.6, "def_rel": 0.2},
                             "NYJ": {"off": 6.7, "off_rel": -0.23, "def": 8.2, "def_rel": -0.07}}}}


def _result(**kw):
    base = {"games": [GAME], "recommendations": [{"player": "Amon-Ra St. Brown", "position": "WR"}],
            "scan_reads": {"NYJ@DET": {"players": [
                {"player": "Amon-Ra St. Brown", "team": "DET", "opp": "NYJ", "pos": "WR", "read": "good",
                 "label": "Good matchup", "lean": ["receptions"], "usage": {"tgt_share": 0.30}}]}},
            "most_likely": [], "matchup_picks": [], "td_scenarios": []}
    base.update(kw)
    return base


def _td(player="Amon-Ra St. Brown", prob=0.52, odds=-115, **kw):
    return {"kind": "td", "player": player, "team": "DET", "opponent": "NYJ", "market": "anytime_td",
            "side": "YES", "line": 0.5, "odds": odds, "book": "BetMGM", "model_prob": prob,
            "implied_prob": 0.50, "rz_chances": 3.1, "implied_total": 27.5, **kw}


def _rows(spec):
    """spec: [(day, odds, grade, won, count)]"""
    out = []
    for day, odds, grade, won, k in spec:
        out += [{"day": day, "need": C.implied(odds), "grade": grade, "won": won}] * k
    return out


def _backwards(**over):
    base = {"top_w": 9, "top_l": 21, "look_w": 23, "look_l": 27, "out_w": 30, "out_l": 15}
    base.update(over)
    spec = []
    for d in ("2026-09-20", "2026-09-28"):
        spec += [(d, -125, "Top pick", True, base["top_w"]), (d, -125, "Top pick", False, base["top_l"]),
                 (d, -125, "Strong", True, base["top_w"]), (d, -125, "Strong", False, base["top_l"]),
                 (d, -125, "Worth a look", True, base["look_w"]), (d, -125, "Worth a look", False, base["look_l"]),
                 (d, -200, "Top pick", True, base["out_w"]), (d, -200, "Top pick", False, base["out_l"])]
    return spec


def test_backwards_tiers_in_the_band_hold():
    v = C.judge(_rows(_backwards()))
    assert v["holds"], v["checks"]


def test_each_condition_alone_blocks_it():
    assert not C.judge(_rows(_backwards(top_w=15, top_l=15)))["checks"][0], "not far enough below the price"
    late_fine = _backwards()
    late_fine = [x for x in late_fine if not (x[0] == "2026-09-28" and x[2] in ("Top pick", "Strong"))]
    late_fine += [("2026-09-28", -125, g, w, k) for g in ("Top pick", "Strong") for w, k in ((True, 22), (False, 8))]
    late_fine += [("2026-09-20", -125, g, w, k) for g in ("Top pick", "Strong") for w, k in ((True, 2), (False, 40))]
    assert not C.judge(_rows(late_fine))["checks"][1], "the later half must lose too"
    assert not C.judge(_rows(_backwards(look_w=10, look_l=40)))["checks"][2], "look worse than top: label not the cause"
    assert not C.judge(_rows(_backwards(out_w=15, out_l=30)))["checks"][3], "tiers fail at -200 too"


def test_the_board_caps_only_in_the_band_and_only_on_a_verdict_that_holds():
    v = C.judge(_rows(_backwards()))
    near, heavy = _td(odds=-115), _td(player="Heavy Fav", odds=-200)
    rows = {r["player"]: r for r in B.build(_result(most_likely=[near, heavy]), band_verdict=v)["rows"]}
    assert rows["Amon-Ra St. Brown"]["tier"] == "look" and "Worth a look" in rows["Amon-Ra St. Brown"]["band_note"]
    assert "have gone 36-84" in rows["Amon-Ra St. Brown"]["band_note"], "the record the verdict was made on"
    assert "band_note" not in rows["Heavy Fav"]
    for none in (None, {**v, "holds": False}):
        r = B.build(_result(most_likely=[_td(odds=-115)]), band_verdict=none)["rows"][0]
        assert r["tier"] == "top" and "band_note" not in r


def test_the_saved_verdict_round_trips_and_the_card_shows_why():
    p = Path(tempfile.mkdtemp()) / "v.json"
    v = C.judge(_rows(_backwards()))
    C.save(v, p)
    assert C.verdict(p)["holds"] is True and C.cap_note(C.verdict(p), -130)
    assert C.cap_note(C.verdict(p), -160) is None and C.cap_note(None, -130) is None
    app = (ROOT / "web" / "js" / "app.js").read_text()
    i = app.index("function obCardHTML(")
    body = app[i:app.index("\n}\n", i)]
    assert "r.band_note" in body and "${band}" in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
