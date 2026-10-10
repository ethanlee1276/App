"""Every tracked sport has a place in the learning ladder and the
hypothesis lab, tuned or not.

Ethan, 2026-09-14: "the 'model tuned itself' page ... It's only showing
mlb and nothing about nfl or CFB. I also don't see anything about nfl
in the hypothesis lab. We need to make sure nfl and CFB is getting the
same treatment the mlb gets." The treatment was the same — the same
floors for every league — but the page showed only the sports that had
cleared them, so an early sport read as an untreated one.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger  # noqa: E402
from engine import propcal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ledger():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    def bet(sport, market, n, prob=0.6):
        for i in range(n):
            conn.execute(
                "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
                "stake_units,status,category,pnl_units,hit_prob) VALUES "
                "(?,'2026-09-13',?,?,'OVER',1.5,-110,'B',0.5,?,'main',0.1,?)",
                (sport, f"{sport} {market} {i}", market, "won" if i % 2 else "lost", prob))
    bet("mlb", "hits", 250)
    bet("nfl", "rec_yds", 9)
    bet("nfl", "rush_yds", 7)
    bet("cfb", "anytime_td", 5)
    conn.commit()
    return conn


def test_every_tracked_sport_is_placed_with_its_distance_to_the_floor():
    conn = _ledger()
    st = {"markets": [{"sport": "mlb", "market": "hits", "reading": "ran hot — tempered toward 50%"}]}
    was = propcal.load_pairs
    propcal.load_pairs = lambda path=None: {"season": 2025, "markets": {
        "rec_yds": [(0.5, 1)] * 12, "receptions": [(0.5, 1)] * 450}}
    try:
        cov = ledger.learning_coverage(conn, st)
    finally:
        propcal.load_pairs = was
    assert set(cov) == set(ledger.TRACKED_SPORTS)          # nba, wnba, ufc too
    assert cov["mlb"]["markets"]["hits"]["state"] == "tuned"
    nfl = cov["nfl"]
    assert nfl["settled"] == 16 and nfl["tuned"] == 0
    # Against the close first, where pairs exist: the NFL prop rule.
    assert nfl["markets"]["rec_yds"]["state"] == "uncorrected"
    assert "12 of 400 book-priced pairs" in nfl["markets"]["rec_yds"]["note"]
    assert nfl["markets"]["receptions"]["state"] == "fit due"
    # The journal floor, where no pairs exist.
    assert nfl["markets"]["rush_yds"]["state"] == "collecting"
    assert "7 of 200 graded journal bets" in nfl["markets"]["rush_yds"]["note"]
    assert cov["cfb"]["markets"]["anytime_td"]["state"] == "collecting"
    assert cov["ufc"] == {"settled": 0, "tuned": 0, "collecting": 0, "markets": {}}


def test_the_export_carries_coverage_on_the_ladder():
    conn = _ledger()
    p = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, p)
    import json
    d = json.loads(open(p).read())
    assert set(d["self_tuning"]["coverage"]) == set(ledger.TRACKED_SPORTS)


def test_the_page_shows_where_each_sport_stands():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function learningCoverageHTML(" in app
    i = app.index("function recSelfTuningSection(")
    j = app.index("function recHypothesisLab(")
    body = app[i:j]
    assert body.count("learningCoverageHTML(st.coverage, sport)") == 2, \
        "both the empty state and the populated view place every sport"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
