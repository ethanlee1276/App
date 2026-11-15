"""Kinds of pick the record says we oversell go on paper (2026-11-15).

Ethan, after step BK showed the NFL board's picks 15+ points above the
market said 76% and hit 36%: "we should only be recording paper bets and
not posting the bets so we can still learn ... that should be automated
and not asking me. if any bets is like that we should switch them to paper
and stop posting them till we learn and get them better".

engine/paperhold measures every Most Likely kind (league, market, distance
above the price) on the board's own graded record and holds the ones that
ran hot by ten points or more; a held pick leaves the board and every list
(likelyboard.held_reason, harmonize), is journaled under ``held`` and
graded, and its kind comes back on its own once thirty of its paper picks
run honest. The picks 15+ points above the price are held from today in
every league. On the Edge boards, a pick the record alone refused
(losspatterns.veto: a convicted slice, a stopped shelf, a confirmed
hypothesis) goes on paper too (``edge_held``), so the slice keeps a record
to come back on.

    python3 tests/test_kinds_we_oversell_go_on_paper.py
"""
import datetime as dt
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger, likelyboard as LB, paperhold as P           # noqa: E402

TODAY = dt.date(2026, 11, 15)


def _tmp(name="paperhold.json"):
    d = tempfile.mkdtemp(prefix="paperhold-")
    return Path(d) / name


def _journal(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, line REAL, player TEXT, date TEXT, "
                 "game_day TEXT, ts TEXT, hit_prob REAL, edge REAL, fair_consensus REAL, status TEXT, "
                 "category TEXT)")
    for r in rows:
        conn.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (r.get("sport", "nba"), r.get("market", "points"), r.get("side", "OVER"), r.get("line", 20.5),
                      r["player"], r["day"], r["day"], r["day"] + "T12:00:00", r["prob"], r.get("edge"),
                      r.get("fc"), r["status"], r.get("category", "board")))
    return conn


def _kind(n, prob, wins, day="2026-11-01", **kw):
    return [dict(player=f"P{i}-{day}-{prob}-{kw.get('market', 'points')}", day=day, prob=prob,
                 status="won" if i < wins else "lost", **kw) for i in range(n)]


def test_the_bands_read_the_gap_to_the_market_first():
    assert [P.band(x) for x in (0.20, 0.15, 0.10, 0.0, -0.10, None)] == ["15+", "15+", "5-15", "near", "below", None]
    row = {"model_prob": 0.80, "implied_prob": 0.60}
    assert abs(P.gap_of(row) - 0.20) < 1e-9, "its own price de-vigged where nothing else"
    row["field_prob"] = 0.70
    assert abs(P.gap_of(row) - 0.10) < 1e-9, "the books' field before its own price"
    row["market_prob"] = 0.78
    assert abs(P.gap_of(row) - 0.02) < 1e-9, "the price rule's field first"


def test_a_kind_that_ran_far_hot_goes_on_paper_and_an_honest_one_stays():
    rows = P.rows_from_ledger(_journal(
        _kind(60, 0.76, 22, edge=0.18)                                 # said 76%, hit 37%
        + _kind(60, 0.62, 37, market="rebounds", edge=0.02)            # said 62%, hit 62%
        + _kind(20, 0.80, 2, market="assists", edge=0.20)))            # too few to test
    got = P.measure(rows, TODAY)
    held = {(h["sport"], h["market"], h["band"]) for h in got["held"]}
    assert ("nba", "points", "15+") in held and ("nba", "points", "all") in held, held
    assert not any(m == "rebounds" for _, m, _ in held), "an honest kind stays posted"
    assert not any(m == "assists" for _, m, _ in held), "a kind under forty picks is not tested"
    h = next(h for h in got["held"] if h["market"] == "points" and h["band"] == "15+")
    assert h["said"] == 0.76 and abs(h["hit"] - 22 / 60) < 1e-3 and h["n"] == 60


def test_a_kind_that_merely_ran_a_little_hot_stays():
    rows = P.rows_from_ledger(_journal(_kind(400, 0.62, 236, edge=0.03)))   # said 62%, hit 59%
    assert not P.measure(rows, TODAY)["held"], "three points hot is the corrections' business, not a hold"


def test_old_picks_outside_the_window_do_not_hold_a_kind():
    rows = P.rows_from_ledger(_journal(_kind(60, 0.76, 22, day="2026-06-01", edge=0.18)))
    assert not P.measure(rows, TODAY)["held"], "judged on how it picks now"


def test_the_standing_hold_and_its_release():
    path = _tmp()
    why = P.reason("nfl", "receptions", 0.18, path)
    assert why == ("on paper, not posted: picks this far above the books' price said 76% and hit 36% on our "
                   "NFL board — our rule records them without posting them until 30 run honest"), why
    assert P.reason("cbb", "points", 0.16, path), "every league"
    assert P.reason("nfl", "receptions", 0.10, path) is None and P.reason("nfl", "receptions", None, path) is None
    # Thirty of its paper picks, run honest since the hold began: it comes back.
    conn = _journal(_kind(30, 0.70, 21, day="2026-11-20", category="held", edge=0.17))
    out = P.refresh(conn, path, today=dt.date(2026, 11, 25))
    assert [h["key"] for h in out["released"]] == ["*|*|15+"], out["released"]
    assert out["released"][0]["after"]["n"] == 30
    assert P.reason("nfl", "receptions", 0.18, path) is None, "released, nobody asked"


def test_a_measured_hold_carries_its_start_and_releases_on_its_paper_picks():
    path = _tmp()
    conn = _journal(_kind(60, 0.62, 20, market="rebounds", edge=0.03, day="2026-11-01"))
    out = P.refresh(conn, path, today=TODAY)
    keys = {h["key"]: h for h in out["holds"]}
    assert "nba|rebounds|near" in keys and keys["nba|rebounds|near"]["since"] == "2026-11-15"
    assert "nba|rebounds|all" in keys
    why = P.reason("nba", "rebounds", 0.0, path)
    assert why and "our NBA rebounds picks within 5 points of the price said 62% and hit 33% over 60" in why, why
    # The next pass keeps the start.
    out = P.refresh(conn, path, today=dt.date(2026, 11, 16))
    assert {h["key"]: h for h in out["holds"]}["nba|rebounds|near"]["since"] == "2026-11-15"
    # Its paper picks since run honest: back on the board, both views of it.
    for r in _kind(40, 0.60, 25, market="rebounds", edge=0.02, day="2026-11-20", category="held"):
        conn.execute("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("nba", "rebounds", "OVER", 20.5, r["player"], r["day"], r["day"], r["day"] + "T12:00:00",
                      r["prob"], r["edge"], None, r["status"], "held"))
    out = P.refresh(conn, path, today=dt.date(2026, 11, 28))
    back = {h["key"] for h in out["released"]}
    assert {"nba|rebounds|near", "nba|rebounds|all"} <= back, out
    assert P.reason("nba", "rebounds", 0.0, path) is None


def test_one_row_a_pick_and_the_market_read_off_the_journal():
    conn = _journal([dict(player="A", day="2026-11-10", prob=0.7, status="won", category="board", edge=0.02, fc=0.40,
                          side="UNDER"),
                     dict(player="A", day="2026-11-10", prob=0.7, status="won", category="held", edge=0.02,
                          side="UNDER")])
    rows = P.rows_from_ledger(conn)
    assert len(rows) == 1 and rows[0]["category"] == "board"
    # fair_consensus is the over's: an under at 70% against an over at 40%
    # is 10 points above the market.
    assert rows[0]["band"] == "5-15"


def _row(prob, implied, locked=False, **kw):
    return {"kind": "prop", "player": "Amon-Ra St. Brown", "team": "DET", "opponent": "NYJ",
            "market": "receptions", "side": "OVER", "line": 6.5, "odds": -190, "book": "FanDuel",
            "model_prob": prob, "implied_prob": implied, "locked": locked, **kw}


def test_the_board_holds_the_pick_on_paper_and_every_list_drops_it():
    far, near = _row(0.82, 0.62), _row(0.66, 0.62, player="Jahmyr Gibbs")
    posted = _row(0.85, 0.62, locked=True, player="Sam LaPorta")
    res = {"games": [], "most_likely": [far, near, posted], "td_scenarios": [],
           "matchup_picks": [{"td": [], "props": [dict(far)]}], "recommendations": []}
    board = LB.build(res, sport="cbb", calibration={}, band_verdict=None)
    res["likely_board"] = board
    held = {r["player"]: r for r in board["held"]}
    assert "Amon-Ra St. Brown" in held and held["Amon-Ra St. Brown"]["held_note"].startswith("on paper, not posted")
    assert "Jahmyr Gibbs" not in held, "five points above the price stays"
    assert "Sam LaPorta" not in held, "a posted pick keeps its seat until its game"
    assert board["paper_held"] == 1
    LB.harmonize(res)
    assert [r["player"] for r in res["most_likely"]] == ["Jahmyr Gibbs", "Sam LaPorta"]
    assert res["matchup_picks"][0]["props"] == [] and board["paper_off_lists"] == 1


def test_a_held_pick_is_journaled_on_paper_with_the_market_it_was_banded_on():
    conn = ledger.connect(_tmp("ledger.db"))
    row = _row(0.82, 0.62, game_date="2026-11-16", field_prob=0.64, field_books=4, side="UNDER")
    n = ledger.log_most_likely(conn, {"sport": "cbb", "date": "2026-11-16", "games": [], "most_likely": [row]},
                               depth=None, category=LB.HELD_CATEGORY, grade_label=LB.HELD_LABEL)
    assert n == 1
    b = conn.execute("SELECT category, stake_dollars, fair_consensus, consensus_books FROM bets").fetchone()
    assert b["category"] == "held" and b["stake_dollars"] == 0.0
    assert abs(b["fair_consensus"] - 0.36) < 1e-9 and b["consensus_books"] == 4, "the over's, as the column keeps"


def _edge_rec(**kw):
    return {"player": "Bam Adebayo", "team": "MIA", "opponent": "BOS", "market": "rebounds", "side": "OVER",
            "line": 9.5, "book": "DraftKings", "odds": -110, "projection": 10.4, "hit_prob": 0.58,
            "edge": 0.05, "confidence": 6, "grade": "Pass", "stake_units": 0.0, "has_market": True,
            "recommended": False, **kw}


def test_an_edge_pick_the_record_alone_refused_goes_on_paper_once():
    conn = ledger.connect(_tmp("ledger.db"))
    held = _edge_rec(record_hold="The record shows a blind spot here: nba rebounds, odds -110 — ran hot")
    passed = _edge_rec(player="Jayson Tatum")
    res = {"sport": "nba", "date": "2026-11-16", "recommendations": [held, passed], "games": []}
    assert ledger.log_recommendations(conn, res) == 1
    b = conn.execute("SELECT player, category, stake_units, stake_dollars FROM bets").fetchall()
    assert [tuple(x) for x in b] == [("Bam Adebayo", "edge_held", 0.1, 0.0)], [tuple(x) for x in b]
    assert ledger.log_recommendations(conn, res) == 0, "one pick, one row"
    assert "edge_held" not in ledger.BOOK, "never in the headline record"


def test_the_edge_gates_mark_the_record_hold_only_when_it_was_the_one_gate():
    for rel in ("engine/betting.py", "engine/mlb/betting.py"):
        src = Path(ROOT, rel).read_text(encoding="utf-8")
        assert "gate_ok = gate_but_record and pattern_block is None" in src, rel
        assert "record_hold = pattern_block if gate_but_record and pattern_block else None" in src, rel
        assert "record_hold=record_hold" in src, rel
    nba = Path(ROOT, "engine/nba/pipeline.py").read_text(encoding="utf-8")
    assert "hold = _block if _block and fails == [_block] else None" in nba
    assert '"record_hold": r.get("record_hold"),' in nba
    for rel in ("engine/pipeline.py", "engine/mlb/pipeline.py"):
        assert '"record_hold": getattr(rec, "record_hold", None),' in Path(ROOT, rel).read_text(encoding="utf-8"), rel


def test_the_settle_pass_measures_it_and_says_so():
    src = Path(ROOT, "engine/maintenance.py").read_text(encoding="utf-8")
    assert "ph = paperhold.refresh(lconn)" in src and 'verdicts["paper holds"] = paperhold.verdict(ph)' in src
    v = P.verdict({"records": 9, "tested": 3, "holds": [{"sport": "nba"}, {"sport": "*"}],
                   "released": [{"sport": "nfl"}]})
    assert v == {"records": 9, "tested": 3, "on_paper": {"*": 1, "nba": 1}, "back": {"nfl": 1}}


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
