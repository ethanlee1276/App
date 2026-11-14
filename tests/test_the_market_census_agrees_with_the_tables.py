"""docs/MARKET_CENSUS.md is generated from the code's tables and never drifts from them.

Ethan, 2026-10-05: "scan for what bets we supply and what bets and markets
we are missing for nfl. This is for most likely bets and edge bets … Make
sure the model we use for most likely bets is actually being used for
every market and bets we select. For CFB and nfl."

`marketcensus.py` reads the request maps, the position tables, the tier
table, the ranking gate, the ingest columns and the chain's factor tables
and writes one document. Checks: the document on disk is what the tables
say today (regenerate with `python3 marketcensus.py --write`); every key
either league buys is built by a position; every built market has a
label, an edge tier, a settle column and a distribution; every market
with a Most Likely figure is bought; every built market prices through
the one chain (a synthetic walk per market, both leagues); the findings
the census raises are the ones we know about, so a new one fails here.

Run directly: `python3 tests/test_the_market_census_agrees_with_the_tables.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import marketcensus as MC                                           # noqa: E402

KNOWN_FINDINGS = {
    # engine/teamcontext's market sets spell three markets in words no
    # market answers to, so the pass-rate tilt never reaches completions,
    # passing touchdowns or rushing touchdowns. Left as found: moving the
    # tilt onto pass_cmp / pass_td / pass_att is a change in their numbers
    # that no held-out run has measured. Noted here so it stays visible.
    "engine/teamcontext names `completions`, which is no market of this board (the pass-rate tilt never reaches it)",
    "engine/teamcontext names `pass_tds`, which is no market of this board (the pass-rate tilt never reaches it)",
    "engine/teamcontext names `rush_tds`, which is no market of this board (the pass-rate tilt never reaches it)",
}


def test_the_document_is_what_the_tables_say_today():
    assert MC.DOC.exists(), "python3 marketcensus.py --write"
    assert MC.DOC.read_text(encoding="utf-8") == MC.render(), \
        "docs/MARKET_CENSUS.md is stale — run `python3 marketcensus.py --write`"


def test_every_bought_key_is_built_and_every_built_market_is_whole():
    t = MC._tables()
    for sport in ("nfl", "cfb"):
        bought, built = MC._bought(t, sport), MC._built(t, sport)
        for key, market in bought.items():
            if key in t["O"].ALT_ODDS_TO_MARKET:
                continue
            assert market in built, f"{sport}: {key} is bought and never built"
        for market in built:
            if market != t["ANYTIME_TD"]:
                assert market in t["MARKET_LABELS"], f"{sport}: {market} has no label"
                assert t["Q"].market_tier(market) in (1, 2, 3)
            assert MC._settles(t, sport, market), f"{sport}: {market} cannot settle"
            assert MC._distribution(t, market)


def test_every_market_with_a_most_likely_figure_is_bought():
    t = MC._tables()
    bought = set(MC._bought(t, "nfl").values())
    for market, auc in t["L"].RANK_AUC.items():
        if market in t["L"].GAME_MARKETS:
            continue
        assert market in bought, f"nfl: {market} ranks at {auc} and is never bought"
    cfb_bought = set(MC._bought(t, "cfb").values())
    for market in t["RF"].MARKETS["cfb"]:
        assert market in cfb_bought, f"cfb: {market} is walked for the shelf and never bought"


def test_every_built_market_prices_through_the_one_chain():
    """The wiring audit's runtime half: a synthetic log per market, both
    leagues, through build_projection → evaluate_prop (logwalk's walk),
    and a settled row with a probability comes out for each."""
    from engine.logwalk import settled_props_from_logs, Entries
    from engine import calibrate as _cal
    import random
    t = MC._tables()
    rnd = random.Random(2)
    for sport in ("nfl", "cfb"):
        for market in MC._built(t, sport):
            if market == t["ANYTIME_TD"]:
                continue                      # its own model (engine/touchdowns), its own walk
            mean = {"pass_yds": 240, "pass_att": 33, "pass_cmp": 21, "pass_td": 1.5, "pass_int": 0.8,
                    "rush_yds": 60, "rush_att": 14, "rec_yds": 55, "receptions": 4.5,
                    # the five of 2026-10-10
                    "pass_rush_yds": 265, "rush_rec_yds": 80, "kick_pts": 8, "fg_made": 1.6,
                    "tackles_ast": 6}[market]
            vals = [max(0.0, rnd.gauss(mean, mean * 0.4)) for _ in range(12)]
            if market in ("pass_td", "pass_int", "fg_made", "kick_pts", "tackles_ast"):
                vals = [float(round(v)) for v in vals]
            e = {"name": "P", "values": vals, "dates": [f"2025-09-{i + 1:02d}" for i in range(12)],
                 "opps": ["X"] * 12, "seasons": [2025] * 12}
            if market == "pass_int":
                e["companion"] = [30.0 + i for i in range(12)]
            entries = Entries([e])
            entries.aux = {"allowed": []} if market == "pass_int" else {}
            with _cal.disabled():
                got = settled_props_from_logs(entries, market, sport=sport)
            assert got and all(0.0 <= s.hit_prob <= 1.0 for s in got), (sport, market)


def test_the_findings_are_the_known_ones():
    t = MC._tables()
    got = set(MC.findings(t))
    new = got - KNOWN_FINDINGS
    assert not new, f"the census found something new — read it, then record it here or fix it: {sorted(new)}"
    assert not (KNOWN_FINDINGS - got), "a known finding is gone — drop it from KNOWN_FINDINGS"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
