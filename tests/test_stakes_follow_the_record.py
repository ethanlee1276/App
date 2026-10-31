"""Which picks carry a stake — the rule the record and every new bet use.

Ethan, 2026-10-31: "I feel like we're winning a lot of bets, but not winning
money ... find what bets and what unit bets ... works best for our ROI to be
positive and our units to be positive, and then we need to implement that,
and then also update our current record on the site."

engine/stakeplan (v4): Edge picks are staked on the price ladder unless a
league's Edge book is clearly losing (100 graded at z <= -2.0, back above
-1.0), and never past +130 (the favourite-longshot cap); Most Likely picks are tracked for their hit rate and staked only once
a league's book beats the price (200 graded at z >= +2.0, off at z <= 0).
The record the site leads with is every graded pick at the stake that rule
gave it on its day — decided from the days before it only.

Run directly: `python3 tests/test_stakes_follow_the_record.py`
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger, stakeplan as SP                   # noqa: E402
from _app import app_js                                      # noqa: E402

APP = app_js()


def _row(day, sport, category, status, odds=-110, stake=1.0, **kw):
    pnl = {"won": stake * (100 / 110 if odds < 0 else odds / 100) if odds < 0 or odds > 0 else 0,
           "lost": -stake, "push": 0.0}[status]
    if status == "won":
        pnl = stake * ((100 / abs(odds)) if odds < 0 else odds / 100)
    return {"day": day, "sport": sport, "category": category, "status": status,
            "odds": odds, "stake_units": stake, "pnl_units": pnl, **kw}


def _days(n, start=1):
    return [f"2026-09-{d:02d}" for d in range(start, start + n)]


# --- the rule ---------------------------------------------------------------
def test_an_edge_book_is_staked_from_its_first_pick():
    flags, state = SP.replay([_row("2026-09-01", "nfl", "main", "lost")])
    assert flags == [True], "Edge picks carry their ladder stake by default"
    assert state[("edge", "nfl")]["staked"] is True


def test_a_most_likely_book_is_tracked_from_its_first_pick():
    flags, state = SP.replay([_row("2026-09-01", "nfl", "likely_live", "won", -200)])
    assert flags == [False], "Most Likely picks are tracked, not staked, by default"
    assert state[("likely", "nfl")]["staked"] is False


def test_an_edge_book_that_is_clearly_losing_stops_and_comes_back():
    rows = []
    # 120 graded, mostly losing: z well under -2 by the end of day 2.
    for i in range(60):
        rows.append(_row("2026-09-01", "cfb", "main", "lost" if i % 6 else "won"))
        rows.append(_row("2026-09-02", "cfb", "main", "lost" if i % 6 else "won"))
    rows.append(_row("2026-09-03", "cfb", "main", "won"))
    flags, state = SP.replay(rows)
    assert all(flags[:120]), "staked while the evidence was gathering"
    assert flags[-1] is False, "stopped the day after it was clearly losing"
    assert state[("edge", "cfb")]["staked"] is False
    # Winning it back: z climbs over -1.0 and the stake returns.
    for d in range(4, 30):
        for i in range(12):
            rows.append(_row(f"2026-09-{d:02d}", "cfb", "main", "won"))
    rows.append(_row("2026-10-01", "cfb", "main", "won"))
    flags, state = SP.replay(rows)
    assert flags[-1] is True and state[("edge", "cfb")]["staked"] is True


def test_a_most_likely_book_is_staked_once_it_beats_the_price_and_not_before():
    rows = []
    for d in _days(10):
        for i in range(25):                         # 250 graded at -150, winning 75%
            rows.append(_row(d, "nba", "likely_live", "won" if i % 4 else "lost", -150, 0.25))
    rows.append(_row("2026-09-20", "nba", "likely_live", "won", -150, 0.25))
    flags, state = SP.replay(rows)
    assert not any(flags[:200]), "nothing staked before 200 graded"
    assert flags[-1] is True, "staked once 200 graded at z >= +2.0"
    plan = SP.plan_from(state)
    assert plan["nba"]["likely"]["staked"] is True
    assert "beaten the price" in plan["nba"]["likely"]["why"]


def test_a_day_is_decided_from_the_days_before_it_only():
    """Two hundred winners graded on one day cannot stake that same day."""
    rows = [_row("2026-09-01", "nba", "likely", "won", -150, 0.1) for _ in range(260)]
    flags, _ = SP.replay(rows)
    assert not any(flags), "no pick knows its own day's results"


def test_an_nfl_week_label_sorts_to_its_sunday():
    assert SP.sort_day("2026-W01") == "2026-09-13"
    assert SP.sort_day("2026-W08") == "2026-11-01"
    assert SP.sort_day("2026-10-29") == "2026-10-29"


def test_an_edge_pick_past_the_price_cap_is_tracked_and_left_out_of_the_evidence():
    """The favourite-longshot bias (2026-10-31): the record's Edge picks at
    +131 or longer hit 37.6% where the price itself said 41.1%."""
    assert SP.EDGE_MAX_ODDS == 130
    rows = [_row("2026-09-01", "nfl", "main", "lost", 150),
            _row("2026-09-01", "nfl", "main", "won", 130),
            _row("2026-09-01", "nfl", "paper", "won", 210),
            _row("2026-09-01", "nfl", "main", "won", -110)]
    flags, state = SP.replay(rows)
    assert flags == [False, True, False, True], "+130 is the longest price staked; past it, paper"
    assert state[("edge", "nfl")]["book"].n == 2, "the league's evidence is the picks the rule would stake"
    assert SP.priced_out("edge", 131) and not SP.priced_out("edge", 130)
    assert not SP.priced_out("likely", 400), "the cap is the Edge half's"
    assert not SP.priced_out("edge", None), "an unreadable price is the journal's business, not the rule's"
    rep = SP.report(rows)
    assert rep["overall"]["tracked"] == 2 and rep["overall"]["settled"] == 2
    assert "nothing longer than +130" in rep["plan"]["nfl"]["edge"]["why"]


def test_books_outside_the_headline_are_left_alone():
    flags, state = SP.replay([_row("2026-09-01", "mlb", "stale", "won", 300)])
    assert flags == [False] and state == {}


# --- the journal --------------------------------------------------------------
def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _insert(conn, day, sport, category, status, odds=-110, stake=1.0, player="P"):
    r = _row(day, sport, category, status, odds, stake)
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, hit_prob,"
        " grade, stake_units, stake_dollars, status, pnl_units, pnl_dollars, category)"
        " VALUES ('t',?,?,?,'rec_yds','OVER',50.5,'DK',?,0.6,'A',?,0,?,?,0,?)",
        (sport, day, f"{player}{conn.execute('SELECT COUNT(*) FROM bets').fetchone()[0]}",
         odds, stake, status, r["pnl_units"], category))


def test_the_staked_record_is_the_ledgers_own_arithmetic_over_the_staked_picks():
    conn = _journal()
    for d in _days(3):
        _insert(conn, d, "nfl", "main", "won")
        _insert(conn, d, "nfl", "main", "lost")
        _insert(conn, d, "nfl", "likely_live", "won", -200, 0.25)
        _insert(conn, d, "nfl", "board", "lost", -150, 0.1)
    conn.commit()
    rep = SP.staked_reports(conn, sports=["nfl"])
    o = rep["overall"]
    edge = ledger.performance(conn, category=ledger.EDGE_BOOKS)
    assert (o["wins"], o["losses"], o["net_units"]) == (edge["wins"], edge["losses"], edge["net_units"]), \
        "with no Most Likely book promoted, the staked record is the Edge book"
    assert o["tracked"] == 6, "the six Most Likely picks are counted as tracked"
    assert o["as_placed"]["settled"] == 12
    assert o["rule"] == SP.VERSION and "by_market" in o and "best_streak" in o, \
        "every field the Record page reads"
    assert rep["by_sport"]["nfl"]["overall"]["settled"] == 6
    assert rep["curve"] and rep["curve"][-1]["cum_u"] == round(edge["net_units"], 2)
    assert rep["plan"]["nfl"]["likely"]["staked"] is False


def test_the_journal_follows_the_stored_plan_and_the_bench_still_wins():
    conn = _journal()
    assert ledger.likely_is_staked("nfl", conn) is False, "no plan yet: tracked"
    SP.store(conn, SP.promoted("nfl", "wnba"))
    assert ledger.likely_is_staked("nfl", conn) is True
    assert ledger.likely_category("nfl", conn) == ledger.LIKELY_LIVE_CATEGORY
    assert ledger.likely_is_staked("wnba", conn) is False, "a benched league never carries money"


def test_a_most_likely_pick_in_an_unpromoted_league_is_journaled_on_paper():
    conn = _journal()
    board = {"sport": "nfl", "date": "2026-11-01", "most_likely": [
        {"player": "A", "market": "rec_yds", "side": "OVER", "line": 40.5, "odds": -190,
         "book": "DK", "model_prob": 0.68, "implied_prob": 0.655, "game_date": "2026-11-01"}]}
    assert ledger.log_most_likely(conn, board) == 1
    r = conn.execute("SELECT category, stake_dollars FROM bets").fetchone()
    assert r["category"] == "likely" and r["stake_dollars"] == 0.0, dict(r)


def test_an_edge_book_the_rule_stopped_journals_on_paper():
    conn = _journal()
    SP.store(conn, {"cfb": {"edge": {"staked": False}, "likely": {"staked": False}}})
    result = {"sport": "cfb", "date": "2026-11-01", "recommendations": [
        {"player": "B", "market": "rec_yds", "side": "OVER", "line": 60.5, "odds": -110,
         "book": "DK", "hit_prob": 0.56, "edge": 0.04, "grade": "A", "stake_units": 1.0,
         "recommended": True, "has_market": True, "game_date": "2026-11-01"}]}
    assert ledger.log_recommendations(conn, result) == 1
    row = conn.execute("SELECT category, stake_units, stake_dollars FROM bets").fetchone()
    assert (row["category"], row["stake_dollars"]) == ("paper", 0.0), dict(row)
    assert row["stake_units"] == 1.0, "the size is kept: the record still answers what it would have made"
    # ...and with the league staked again, the next pick carries money.
    SP.store(conn, {})
    result["recommendations"][0]["player"] = "C"
    assert ledger.log_recommendations(conn, result) == 1
    row = conn.execute("SELECT category, stake_dollars FROM bets WHERE player='C'").fetchone()
    assert row["category"] == "main" and row["stake_dollars"] > 0, dict(row)


def test_a_long_price_edge_pick_journals_on_paper_props_and_game_bets_alike():
    conn = _journal()
    rec = {"player": "D", "market": "receptions", "side": "UNDER", "line": 4.5, "odds": 150,
           "book": "DK", "hit_prob": 0.45, "edge": 0.05, "grade": "A", "stake_units": 0.6,
           "recommended": True, "has_market": True, "game_date": "2026-11-01"}
    near = {**rec, "player": "E", "odds": 125}
    game = {"bet_type": "moneyline", "pick": "NYJ", "odds": 160, "win_prob": 0.42, "edge": 0.04,
            "grade": "A", "stake_units": 0.55, "recommended": True, "game_date": "2026-11-01"}
    result = {"sport": "nfl", "date": "2026-W09", "recommendations": [rec, near], "game_bets": [game]}
    assert ledger.log_recommendations(conn, result) == 3
    got = {r["player"]: (r["category"], r["stake_units"], r["stake_dollars"])
           for r in conn.execute("SELECT player, category, stake_units, stake_dollars FROM bets")}
    assert got["D"][0] == "paper" and got["D"][2] == 0.0 and got["D"][1] == 0.6, got
    assert got["E"][0] == "main" and got["E"][2] > 0, "+125 is inside the cap: staked"
    assert got["NYJ"][0] == "paper" and got["NYJ"][2] == 0.0, "the game bets' insert honours the cap too"
    assert ledger.edge_price_book("likely", 400) == "likely", "only an Edge row moves"


def test_open_picks_past_the_cap_are_not_counted_as_staked():
    conn = _journal()
    for odds in (-110, 150):
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds,"
                     " hit_prob, grade, stake_units, stake_dollars, status, category)"
                     " VALUES ('t','nfl','2026-11-01',?,'receptions','OVER',3.5,'DK',?,0.5,'A',1.0,0,"
                     "'open','main')", (f"O{odds}", odds))
    conn.commit()
    assert SP.staked_reports(conn, sports=["nfl"])["overall"]["open"] == 1


def test_the_card_says_tracked_past_the_cap():
    assert f"const EDGE_MAX_ODDS = {SP.EDGE_MAX_ODDS};" in APP, "the page's cap is the rule's"
    i = APP.index("function edgeStakeTxt(r)")
    body = APP[i:APP.index("\n}", i)]
    assert 'Number(r.odds) > EDGE_MAX_ODDS ? "Tracked · no stake"' in body
    assert APP.count("const stakeTxt = edgeStakeTxt(r);") == 2, "the Edge prop card and the game-bet card"


def test_the_export_ships_the_staked_record_and_stores_the_plan():
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert "_staked = _stakeplan.staked_reports(" in src
    assert "set_cfg(conn, STAKE_PLAN_KEY, json.dumps(_staked.get(\"plan\") or {}, sort_keys=True))" in src
    assert '"staked": {k: _staked[k] for k in ("overall", "curve", "recent", "plan")' in src
    assert '"staked": ((_staked.get("by_sport") or {}).get(sp) or {})}' in src


# --- the page ---------------------------------------------------------------------
def test_the_page_leads_with_the_picks_we_stake():
    i = APP.index("function adoptPooledRecord(rec)")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "const st = s.staked && s.staked.overall && s.staked.overall.settled ? s.staked : null;" in body
    assert "s.overall = (st && st.overall) || s.pooled.edge || s.overall;" in body
    assert "s.curve = (st && st.curve) || s.pooled.edge_curve || s.curve;" in body
    j = APP.index("function recordRibbonsHTML(")
    rib = APP[j:APP.index("\nfunction ", j + 10)]
    assert '"Our record · the picks we stake"' in rib
    assert '"Most Likely · tracked for its hit rate"' in rib, "judged on its hit rate against what its prices need"
    assert '"As placed · before the Oct 31 stake rule"' in rib, "the receipts stay one tile away"


def test_ask_and_the_widget_read_the_staked_record():
    ask = open(os.path.join(ROOT, "engine", "askbot.py"), encoding="utf-8").read()
    assert 'head = staked.get("overall") or pooled.get("overall") or record.get("overall") or {}' in ask
    widget = open(os.path.join(ROOT, "engine", "widgetfeed.py"), encoding="utf-8").read()
    assert 'ov = (rec.get("staked") or {}).get("overall") or rec.get("overall") or {}' in widget


def test_the_study_reruns_from_the_receipts():
    import importlib.util
    spec = importlib.util.spec_from_file_location("stake_study", os.path.join(ROOT, "tools", "stake_study.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    path = os.path.join(tempfile.mkdtemp(), "r.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("date,sport,category,player,market,side,line,odds,book,stake_units,status,pnl_units,"
                "hit_prob,closing_line,grade\n")
        for i in range(40):
            won = i % 2 == 0
            f.write(f"2026-09-{1 + i % 20:02d},nfl,main,P{i},rec_yds,OVER,50.5,-110,DK,1.0,"
                    f"{'won' if won else 'lost'},{0.909 if won else -1.0},0.56,,A\n")
            f.write(f"2026-09-{1 + i % 20:02d},nfl,likely,Q{i},rec_yds,OVER,40.5,-200,DK,0.1,"
                    f"{'won' if i % 3 else 'lost'},{0.05 if i % 3 else -0.1},0.7,,Likely\n")
    import io
    import contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        mod.report(mod.load(path))
    text = out.getvalue()
    assert "1. EACH HALF" in text and "4. THE v4 RULE" in text and "tracked, not staked: 40 picks" in text


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc()
    if fails:
        print(f"{ran} passed, {fails} failed")
        sys.exit(1)
    print(f"\n{ran} tests passed.")
