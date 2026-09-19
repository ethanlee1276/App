"""Both hoops leagues buy their alternate ladders, priced exactly as the main line.

Ethan, 2026-09-15, after the baseball fix: "After that scan every sport
and make sure this is not an issue."

It was, and worse: every basketball line is hung at the player's
median, so the main number sits near 50% on all five markets and the
Most Likely floor refuses the whole slate. Baseball had one such market
(strikeouts); hoops has nothing but. The remedy is the ladder, and the
rule is the one the baseball ladder set the same day: a rung is priced
by the curve that priced the main line — here the model's curve at the
rung, the market's correction, and the humility clamp toward the rung's
own de-vigged price at the main line's weight.

Run directly: `python3 tests/test_hoops_ladder.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import hoops                                                   # noqa: E402
from engine.nba import pipeline as P                                       # noqa: E402
from engine.nba.prob import p_over, devig, humility_clamp, CLAMP_KILL_DIFF  # noqa: E402
from engine.sources import oddsapi as oa                                   # noqa: E402

STEADY = [30, 31, 29, 32, 30, 31, 30, 29, 31, 30]


def _prop(market="pts", line=19.5, rate=0.65, **kw):
    p = {"player": kw.pop("player", "A Guard"), "team": kw.pop("team", "BOS"),
         "opponent": kw.pop("opponent", "NYK"),
         "market": market, "line": line, "over_odds": -110, "under_odds": -110,
         "spread": -3.0, "is_starter": True, "minutes": list(STEADY),
         "values": [round(m * rate, 1) for m in STEADY]}
    p.update(kw)
    return p


def _ln(line, over, under=0, book="DraftKings"):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def test_both_leagues_ask_for_five_ladders_behind_the_guard():
    for sport in ("nba", "wnba"):
        assert oa.SPORT_CONFIG[sport]["alternates"] is oa.HOOPS_ALT_ODDS_TO_MARKET, sport
    assert set(oa.HOOPS_ALT_ODDS_TO_MARKET.values()) == {"pts", "reb", "ast", "fg3m", "pra"}
    assert set(oa.HOOPS_ALT_ODDS_TO_MARKET.values()) == set(oa.NBA_ODDS_TO_MARKET.values()), \
        "a ladder for every market the board can rank, and no other"
    assert all(k.endswith("_alternate") for k in oa.HOOPS_ALT_ODDS_TO_MARKET)
    assert set(oa.HOOPS_ALT_ODDS_TO_MARKET) <= oa.UNPROVEN_MARKETS


def test_a_rung_is_priced_the_way_the_main_line_is():
    tune = hoops.NBA
    proj, w = 20.0, 0.45
    # Priced within the clamp's tolerance of the model's own curve
    # (14.5 → 0.82, 16.5 → 0.72, 24.5 → 0.23); a rung the market prices
    # further away is killed, and the next test is about that.
    alts = [_ln(14.5, -300, 230), _ln(14.5, -290, 225, "FanDuel"),
            _ln(16.5, -220, 175), _ln(24.5, 230, -300)]
    got = P.rung_probs("pts", proj, alts, w, tune)
    assert set(got) == {"14.5", "16.5", "24.5"}, got          # one entry per distinct number
    # Exactly the main line's arithmetic at the rung: model curve, then
    # the clamp toward the rung's own de-vigged over at the same weight.
    for line, over, under in ((14.5, -300, 230), (16.5, -220, 175), (24.5, 230, -300)):
        p_model = p_over("pts", proj, line, tune)
        mkt_over, _ = devig(over, under)
        want, _ = humility_clamp(p_model, mkt_over, w)
        assert abs(got[f"{line:g}"] - round(want, 4)) < 1e-9, (line, got)
    assert got["14.5"] > got["16.5"] > got["24.5"], got
    assert got["14.5"] > 0.55, got                            # where "likely" is for sale


def test_a_one_sided_rung_carries_the_model_and_a_killed_rung_is_left_out():
    tune = hoops.NBA
    # One side only: nothing to clamp toward, so the model's own number.
    got = P.rung_probs("reb", 8.0, [_ln(5.5, -300)], 0.45, tune)
    assert abs(got["5.5"] - round(p_over("reb", 8.0, 5.5, tune), 4)) < 1e-9, got
    # A rung the market prices far from the model is what the clamp
    # KILLS on a main line; on a rung it is simply not priced, so the
    # ladder cannot show it from some other curve.
    p_model = p_over("pts", 20.0, 14.5, tune)
    far = [_ln(14.5, 120, -150)]                              # market says ~45% over
    mkt, _ = devig(120, -150)
    assert abs(p_model - mkt) > CLAMP_KILL_DIFF
    assert P.rung_probs("pts", 20.0, far, 0.45, tune) == {}
    assert P.rung_probs("pts", 20.0, [], 0.45, tune) == {}
    assert P.rung_probs("pts", 20.0, [_ln("bad", -110, -110)], 0.45, tune) == {}


def test_the_row_carries_the_ladder_and_its_prices():
    prop = _prop()
    alts = [_ln(14.5, -300, 230), _ln(24.5, 230, -300)]
    rows = P.shared_recommendations([prop], {}, {}, tune=hoops.NBA,
                                    alt_map={("A Guard", "pts"): alts},
                                    alt_sharp_map={("A Guard", "pts"): [_ln(14.5, -240, 200, "Pinnacle")]})
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["alt_lines"] == alts
    assert r["alt_sharp_lines"][0]["book"] == "Pinnacle"
    assert set(r["rung_probs"]) == {"14.5", "24.5"}, r["rung_probs"]
    # Without a ladder the row still ships, empty-handed rather than absent.
    bare = P.shared_recommendations([prop], {}, {}, tune=hoops.NBA)[0]
    assert bare["alt_lines"] == [] and bare["rung_probs"] == {}


def test_the_build_hands_the_ladders_over():
    with open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8") as f:
        src = f.read()
    at = src.index("recs = shared_recommendations(")
    call = src[at:at + 400]
    assert "alt_map=alt_map" in call and "alt_sharp_map=alt_sharp_map" in call
    i = src.index("alt_map, alt_sharp_map = {}, {}")
    assert 'getattr(pr, attr, None)' in src[i:i + 900]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
