"""The hypothesis lab reads every sport's record — and says where a
sport without a hypothesis stands.

Ethan, 2026-09-14: "I also don't see anything about nfl in the
hypothesis lab. We need to make sure nfl and CFB is getting the same
treatment the mlb gets."
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import hypotheses as hyp  # noqa: E402
from engine import ledger  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_proposer_never_drops_a_sports_last_market_first():
    """The pack was cut from the end of a list sorted by sport name, so
    nfl, ufc and wnba went first and mlb never did."""
    markets = ([{"sport": "mlb", "market": f"m{i}", "n": 1000 - i} for i in range(6)]
               + [{"sport": "nfl", "market": "rec_yds", "n": 9}]
               + [{"sport": "wnba", "market": "pts", "n": 30}])
    size = lambda ms: 10 * len(ms)                       # each market "costs" 10
    kept = hyp.trim_markets(markets, size, cap=40)      # room for four
    assert len(kept) == 4
    assert {m["sport"] for m in kept} == {"mlb", "nfl", "wnba"}
    # The mlb markets cut were its smallest, not its last-named.
    assert [m["market"] for m in kept if m["sport"] == "mlb"] == ["m0", "m1"]
    # With no room for every sport, the smallest overall goes last.
    kept = hyp.trim_markets(markets, size, cap=20)
    assert len(kept) == 2 and {m["sport"] for m in kept} <= {"mlb", "nfl", "wnba"}


def test_the_export_says_how_many_records_each_sport_has_and_the_floor():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    for sport, n in (("mlb", 12), ("nfl", 5)):
        for i in range(n):
            conn.execute(
                "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
                "stake_units,status,category,pnl_units,hit_prob) VALUES "
                "(?,'2026-09-13',?,'hits','OVER',1.5,-110,'B',0.5,'won','main',0.1,0.6)",
                (sport, f"{sport} {i}"))
    conn.commit()
    p = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, p)
    import json
    hl = json.loads(open(p).read())["hypothesis_lab"]
    assert hl["coverage"]["nfl"] == 5 and hl["coverage"]["mlb"] == 12
    assert hl["coverage"]["cfb"] == 0                    # every tracked sport
    assert hl["min_n"] >= 1


def test_the_page_says_where_a_sport_without_a_hypothesis_stands():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    k = app.index("function recHypothesisLab(")
    body = app[k:k + 3000]
    assert "hl.coverage" in body and "hl.min_n" in body
    assert "on the same weekly" in body
    assert "never skipped for being newer" in hyp.SYSTEM


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
