"""Most Likely learns by market and side too (engine/likelycal, BY MARKET TOO).

Ethan, 2026-11-03, "2, yes": the record's cuts found picks over-claiming
inside groups that were honest as a whole (college receiving-yards unders
hit 50% where we said 70%; NFL tight-end unders 46% against 59%). So a
maker's side on one market is a group of its own once it has enough settled
picks. What these hold:

  * a market that over-claims inside an honest side is found and pulled,
    and the rest of that side is left as it was;
  * the market level is kept only when it beats the raw chance and the
    maker level on games it was not fitted on — where the markets do not
    differ, the maker level stands, exactly as before;
  * the board, the scout's stacked correction and the slip grader all read
    the same group;
  * Ethan's rule: a chance is only ever lowered, and nothing leaves the pool.

Run directly: `python3 tests/test_most_likely_learns_by_market_too.py`
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QB_NFL_TIGHT"] = "off"

from engine import ledger, likelycal as LC                         # noqa: E402

_INS = ("INSERT INTO bets (ts, sport, date, game_day, team, player, market, side, line, odds, hit_prob, grade, "
        "stake_units, stake_dollars, status, category, pnl_units) VALUES ('t','cfb',?,?,?,?,?,?,?,?,?,?,0.1,0,?,?,0)")


def _journal(kind="bad_market", seed=11):
    """The list's unders, all claiming 70% at even money (the price says
    about 48%). ``bad_market``: rushing yards and receptions hit 70%, as
    claimed, and receiving yards hits 48%, the price. ``uniform``: every
    market hits 58%, the same over-claim everywhere."""
    conn = ledger.connect(":memory:")
    rng = random.Random(seed)
    teams = [f"T{i}" for i in range(30)]
    for d in range(8):
        day = f"2026-09-{5 + d:02d}"
        for t in teams:
            for market in ("rush_yds", "receptions", "rec_yds"):
                if kind == "uniform":
                    hit = 0.58
                else:
                    hit = 0.48 if market == "rec_yds" else 0.70
                won = "won" if rng.random() < hit else "lost"
                conn.execute(_INS, (day, day, t, f"{market}-{day}-{t}", market, "UNDER", 40.5, 100,
                                    0.70, "Likely", won, "likely"))
    conn.commit()
    return conn


def test_a_market_that_over_claims_inside_an_honest_side_is_found():
    res = LC.fit(_journal(), "cfb")
    g = res["groups"]
    assert res["passed"] and res["by_market"], res["held_out"]
    rec = g["list|under|rec_yds"]
    assert rec["k"] <= 0.3 and rec["n"] == 240, rec
    # Each pick is fitted in the group it reads: the honest markets are
    # not dragged down by the bad one.
    for m in ("rush_yds", "receptions"):
        mg = g.get(f"list|under|{m}")
        assert mg is None or mg["k"] >= 0.8, (m, mg)
    rest = g.get("list|under")
    assert rest is None or rest["k"] >= 0.8, rest
    mk = res["held_out"]["market"]
    assert mk["lo"] > 0 and mk["lo_vs_raw"] > 0, mk


def test_where_the_markets_do_not_differ_the_maker_level_stands():
    """The same over-claim on every market: the maker level corrects it, and
    splitting by market buys nothing on held-out games, so it is not kept."""
    res = LC.fit(_journal("uniform"), "cfb")
    assert res["passed"] and res["by_market"] is False, res["held_out"]
    assert res["groups"]["list|under"]["k"] < 1.0
    assert not any(k.count("|") == 2 for k in res["groups"]), res["groups"]


def test_the_level_is_chosen_on_the_bar_as_written():
    def ho(lo, mlo_raw, mlo):
        return {"n": 500, "lo": lo, "market": {"lo_vs_raw": mlo_raw, "lo": mlo}}
    assert LC.choose_level(ho(0.01, 0.02, 0.005)) == (True, True)
    assert LC.choose_level(ho(0.01, 0.02, -0.001)) == (True, False), "must beat the maker level too"
    assert LC.choose_level(ho(-0.01, 0.02, -0.001)) == (True, True), "the maker level failed; this passed"
    assert LC.choose_level(ho(-0.01, -0.001, 0.01)) == (False, False)
    assert LC.choose_level({"n": 0}) == (False, False)


def test_a_pick_reads_its_market_then_its_side_then_its_maker():
    groups = {"list|under|rec_yds": {"k": 0.2}, "list|under": {"k": 0.9}, "list|both": {"k": 0.7}}
    assert LC.k_for(groups, "list|under", "rec_yds")["k"] == 0.2
    assert LC.k_for(groups, "list|under", "Rec Yds")["k"] == 0.2, "one key however it is written"
    assert LC.k_for(groups, "list|under", "points")["k"] == 0.9
    assert LC.k_for(groups, "list|under")["k"] == 0.9
    assert LC.k_for({"list|both": {"k": 0.7}}, "list|under", "rec_yds")["k"] == 0.7


def _store():
    return {"cfb": {"by_market": True, "groups": {
        "list|under|rec_yds": {"k": 0.0, "n": 240, "hit": 0.45, "claimed": 0.70},
        "list|under": {"k": 1.0, "n": 480, "hit": 0.62, "claimed": 0.62}}}}


def test_the_board_lowers_the_market_and_says_which():
    rows = [{"player": "A", "market": "rec_yds", "side": "under", "odds": -150, "model_prob": 0.70,
             "sources": ["likely"]},
            {"player": "B", "market": "rush_yds", "side": "under", "odds": -150, "model_prob": 0.66,
             "sources": ["likely"]}]
    assert LC.apply(rows, "cfb", _store()) == 1
    a, b = rows
    assert a["board_raw_prob"] == 0.70 and a["model_prob"] < 0.60, a
    assert "Most Likely list on the under on receiving yards have hit 45% of 240" in a["cal_note"], a["cal_note"]
    assert b["model_prob"] == 0.66 and "board_raw_prob" not in b, "the honest market is left alone"
    assert len(rows) == 2, "nothing leaves the pool"


def test_a_market_correction_never_raises_a_chance():
    rows = [{"player": "C", "market": "rec_yds", "side": "under", "odds": -400, "model_prob": 0.55,
             "sources": ["likely"]}]
    LC.apply(rows, "cfb", _store())
    assert rows[0]["model_prob"] == 0.55


def test_the_scout_stacks_on_the_same_group_the_board_shows():
    from engine import likelyctx
    cal = _store()["cfb"]["groups"]
    q = LC.price_chance(-150)
    r = {"sources": {"list"}, "side": "UNDER", "market": "rec_yds", "p": 0.70}
    assert likelyctx._cal_base(r, q, cal) == LC.shrink(0.70, q, 0.0)
    r2 = dict(r, market="rush_yds")
    assert likelyctx._cal_base(r2, q, cal) == 0.70


def test_the_slip_grader_reads_the_same_group():
    from engine import slipgrade
    d = tempfile.mkdtemp(prefix="likelycal-")
    path = os.path.join(d, "likely_calibration.json")
    Path(path).write_text(json.dumps(_store()), encoding="utf-8")
    old = os.environ.get("QB_LIKELY_CAL")
    os.environ["QB_LIKELY_CAL"] = path
    try:
        lowered = slipgrade._honest("cfb", 0.70, "under", -150, "rec_yds")
        assert lowered < 0.60, lowered
        assert slipgrade._honest("cfb", 0.66, "under", -150, "rush_yds") == 0.66
    finally:
        if old is None:
            os.environ.pop("QB_LIKELY_CAL", None)
        else:
            os.environ["QB_LIKELY_CAL"] = old


def test_the_store_says_which_level_it_kept():
    d = tempfile.mkdtemp(prefix="likelycal-")
    path = os.path.join(d, "likely_calibration.json")
    res = LC.fit(_journal(), "cfb")
    LC.save(res, path)
    got = LC.load(path)["cfb"]
    assert got["by_market"] is True and "list|under|rec_yds" in got["groups"]



def test_the_record_page_names_every_part_of_a_group():
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert 'escapeHtml(g.split("|").join(" · "))' in js, "list · under · rec_yds, not list · under|rec_yds"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
