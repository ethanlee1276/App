"""A parlay leg's chance is one our own rules stand behind.

Ethan, 2026-11-16: "go look into why footballs stated chances run 10 to 30
points too high". The record that morning: NFL game-parlay legs hit 49.9% of
the time against the 68.4% we stated (receptions 34% against 71%), college's
56.2% against 71.2% (passing yards 31% against 76%). The Most Likely picks in
the same 60-75% band hit what they said (NFL 65.7% stated, 65.9% hit, 1,259
picks), so the model's chances were not the trouble. The leg pool was:

* every priced prop joined it on 14 November at its tempered chance,
  `hit_prob`, which the Edge path pulls halfway to the book's fair price. A
  main line near even money only shows 60% when the raw model says 70% or
  more against a book at about 52%: past the Edge path's own credibility
  limit (betting.MAX_CREDIBLE_EDGE, ten points), where it refuses the pick as
  "a data error, not alpha". The board kept the row and the parlays took it;
* when two sources priced the same bet, the higher number won.

Now a priced leg passes the Edge path's own test (gameparlays.credible_row),
the most trusted copy of a bet speaks for it (SOURCE_RANK: the Most Likely
board, then the Edge picks, then any other priced prop), and every leg keeps
its source and the book's chance in the journal, so the record can say which
legs hit what they said, each bet counted once. And each leg is graded on its
own line (parlayledger._own_verdict): the singles journal keeps one row a
player's market and side, and a leg at another line used to take that row's
result.

Run directly: `python3 tests/test_football_legs_say_what_they_hit.py`
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import betting, gameparlays as GP, parlayledger  # noqa: E402

GAME = {"home": "NYG", "away": "WAS", "date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00",
        "spread": -2.5, "total": 44.5}


def _ml(player, team, market, side, line, p, odds, implied):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": "WR", "market": market, "market_label": market, "side": side, "line": line,
            "odds": odds, "book": "DraftKings", "model_prob": p, "implied_prob": implied,
            "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00", "reasons": []}


def _rec(player, team, market, side, line, hit, odds, fair, raw, reasons=()):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": "WR", "market": market, "side": side, "line": line, "odds": odds,
            "book": "DraftKings", "hit_prob": hit, "fair_prob": fair, "raw_prob": raw, "has_market": True,
            "recommended": False, "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00",
            "reasons": list(reasons)}


# --- the Edge path's own test, on every priced leg --------------------------------------

def test_a_row_the_edge_path_refused_is_no_leg():
    assert GP.credible_row({"reasons": [betting.IMPLAUSIBLE_EDGE_REASON], "raw_prob": 0.6, "fair_prob": 0.55}) is False
    for reason in betting.REFUSAL_REASONS:
        assert GP.credible_row({"reasons": ["Volume up.", reason]}) is False, reason[:40]
    assert GP.credible_row({"raw_prob": 0.80, "fair_prob": 0.52}) is False, "twenty-eight points off the book"
    assert GP.credible_row({"raw_prob": 0.70, "fair_prob": 0.62}) is True
    assert GP.credible_row({"raw_prob": 0.0, "fair_prob": 0.52}) is True, "no raw read kept: the reasons decide"
    assert GP.credible_row({"raw_prob": "x", "fair_prob": 0.52}) is False, "a number we cannot read is no leg"
    assert GP.credible_row({}) is True


def test_a_main_line_at_even_money_cannot_reach_the_floor_credibly():
    """The arithmetic behind the leak: the tempered chance a main line shows
    is fair + shrink x (raw - fair), and the shrink is half at most, so 60%
    at a book of 52% needs a raw read 16 points or more off the book."""
    hit, _edge, credible = betting.temper_edge(0.68, 0.52, "DraftKings", shrink=0.5)
    assert hit >= GP.LEG_FLOOR and credible is False
    hit, _edge, credible = betting.temper_edge(0.68, 0.62, "DraftKings", shrink=0.5)
    assert hit >= GP.LEG_FLOOR and credible is True, "a juiced line can carry a credible 60%"


def test_the_priced_pool_keeps_the_credible_rows_only():
    board = {"date": "2099-W10", "games": [GAME], "recommendations": [
        _rec("Wan'Dale Robinson", "NYG", "receptions", "Over", 5.5, 0.66, -110, 0.52, 0.80,
             [betting.IMPLAUSIBLE_EDGE_REASON]),
        _rec("Darius Slayton", "NYG", "receptions", "Over", 2.5, 0.66, -110, 0.52, 0.80),
        _rec("Theo Johnson", "NYG", "receptions", "Over", 2.5, 0.64, -150, 0.60, 0.68)]}
    legs = GP.priced_legs(board, "nfl")
    assert [l["player"] for l in legs] == ["Theo Johnson"], legs
    assert legs[0]["fair"] == 0.6 and legs[0]["pool"] == "priced"


def test_the_most_trusted_copy_of_a_bet_speaks_for_it():
    """The same bet from the Most Likely board at 64% and as a priced prop
    at 72%: the Most Likely copy is the leg, not the higher number."""
    board = {"date": "2099-W10", "games": [GAME],
             "most_likely": [_ml("Theo Johnson", "NYG", "receptions", "Over", 2.5, 0.64, -150, 0.60)],
             "recommendations": [_rec("Theo Johnson", "NYG", "receptions", "Over", 2.5, 0.72, -150, 0.60, 0.70)]}
    legs = [l for l in GP.legs_for(board, "nfl") if l["player"] == "Theo Johnson"]
    assert len(legs) == 1 and legs[0]["p"] == 0.64 and legs[0]["pool"] == "likely", legs
    # Within one source the likelier copy still wins.
    a, b = {"pool": "priced", "p": 0.66}, {"pool": "priced", "p": 0.61}
    assert GP._speaks_first(a, b) and not GP._speaks_first(b, a)
    assert GP._speaks_first({"pool": "likely", "p": 0.6}, {"pool": "edge", "p": 0.7})
    assert GP.SOURCE_RANK == {"likely": 0, "edge": 1, "priced": 2}


def test_a_published_leg_keeps_its_source_and_the_books_chance():
    leg = GP.slim({"player": "Theo Johnson", "market": "receptions", "side": "Over", "line": 2.5, "odds": -150,
                   "p": 0.64, "pool": "likely", "fair": 0.6, "_game_leg": False})
    assert leg["pool"] == "likely" and leg["fair"] == 0.6 and "_game_leg" not in leg


# --- the journal and the record ----------------------------------------------------------

def _leg(player, p, pool, fair, line=2.5):
    return {"player": player, "team": "NYG", "market": "receptions", "side": "Over", "line": line, "odds": -150,
            "book": "DraftKings", "p": p, "pool": pool, "fair": fair}


def test_the_journal_keeps_each_legs_source_and_the_record_counts_each_bet_once():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    shared = _leg("Theo Johnson", 0.64, "likely", 0.60)
    gp = {"games": [{"game": "WAS@NYG", "home": "NYG", "away": "WAS", "threes": [
        {"joint": 0.3, "independent": 0.27, "take_dec": 3.4,
         "legs": [shared, _leg("Darius Slayton", 0.66, "priced", 0.55), _leg("Cam Skattebo", 0.7, "edge", 0.66)]},
        {"joint": 0.31, "independent": 0.28, "take_dec": 3.3,
         "legs": [shared, _leg("Darius Slayton", 0.66, "priced", 0.55, line=3.5),
                  _leg("Isaiah Likely", 0.68, "likely", 0.64)]}], "scorers": []}]}
    assert parlayledger.log_game_parlays(conn, gp, "nfl", "2099-W10") == 2
    rows = conn.execute("SELECT player, pool, fair FROM parlay_legs ORDER BY id").fetchall()
    assert [(r["pool"], r["fair"]) for r in rows][:3] == [("likely", 0.6), ("priced", 0.55), ("edge", 0.66)]
    # Grade them: every leg hit but the priced ones.
    conn.execute("UPDATE parlay_legs SET status = CASE WHEN pool = 'priced' THEN 'lost' ELSE 'won' END")
    conn.execute("UPDATE parlays SET status = 'lost', legs_lost = 1")
    # The game starts with both tickets up: the set the record counts (parlayledger.mark_at_start).
    parlayledger.mark_started_games(conn, {"games": [dict(gp["games"][0], kept="Sun 1:00 PM ET")]}, "nfl", "2099-W10")
    rec = parlayledger.game_parlay_record(conn)["nfl"]["three"]
    legs = rec["legs"]
    assert legs["graded"] == 6, "per ticket, the shared leg twice"
    assert legs["once"]["graded"] == 5 and legs["once"]["won"] == 3, legs["once"]
    by = legs["by_pool"]
    assert by["priced"]["graded"] == 2 and by["priced"]["won"] == 0 and by["priced"]["fair"] == 0.55, by
    assert by["likely"]["graded"] == 2 and by["likely"]["won"] == 2 and by["likely"]["chance"] == 0.66, by
    assert by["edge"] == {"graded": 1, "won": 1, "chance": 0.7, "fair": 0.66}, by


def test_an_older_journal_gains_the_columns_and_its_legs_read_as_before():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(parlayledger.SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    assert "pool" not in cols and "fair" not in cols, "the base schema is the old one; ensure_schema adds the rest"
    parlayledger.ensure_schema(conn)
    parlayledger.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    assert {"pool", "fair"} <= cols
    once, by = parlayledger.legs_once([{"id": 1, "date": "2099-W10", "grade": "WAS@NYG"}],
                                      [{"parlay_id": 1, "player": "A", "market": "receptions", "side": "OVER",
                                        "line": 2.5, "p_final": 0.7, "status": "won", "pool": None, "fair": None}])
    assert once == {"graded": 1, "won": 1, "chance": 0.7, "fair": None} and list(by) == ["before"]


def test_a_leg_takes_its_own_lines_verdict():
    """The singles journal keeps one row a player's market and side (the
    first line journaled), so a leg at another line is graded on its own
    line from the number that row settled on, never on the row's verdict."""
    row = {"side": "OVER", "line": 1.5, "status": "won", "actual": 2.0, "odds": -230, "closing_line": 1.5}
    V = parlayledger._own_verdict
    assert V({"side": "OVER", "line": 1.5, "odds": -230}, row)["status"] == "won", "its own bet: the row's verdict"
    got = V({"side": "OVER", "line": 3.5, "odds": 120}, row)
    assert got["status"] == "lost" and got["actual"] == 2.0 and got["line"] == 3.5, got
    assert got["odds"] == 120 and got["closing_line"] is None, "never the other line's price or close"
    assert V({"side": "UNDER", "line": 4.5, "odds": -138}, row)["status"] == "won"
    assert V({"side": "OVER", "line": 2.0, "odds": -110}, row)["status"] == "void", "a push on its own line"
    assert V({"side": "OVER", "line": 3.5, "odds": 120}, {**row, "status": "void", "actual": None})["status"] == "void"
    assert V({"side": "OVER", "line": 3.5, "odds": 120}, {**row, "actual": None})["status"] == "void", \
        "no number to grade it on: void, not another bet's verdict"
    # The oldest tickets and singles carry no side or line: the row is theirs.
    assert V({"side": None, "line": None, "odds": -110}, row)["status"] == "won"
    assert V({"side": "OVER", "line": 3.5, "odds": -110}, {**row, "side": None, "line": None})["status"] == "won"


def test_a_ticket_at_another_line_grades_on_its_own_and_the_record_heals():
    from engine import ledger
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)

    def leg(player, market, side, line, odds):
        return {"player": player, "team": "NYG", "opponent": "WAS", "home": "NYG", "away": "WAS", "market": market,
                "side": side, "line": line, "odds": odds, "book": "DraftKings", "p": 0.66, "position": "WR",
                "game_date": "2099-11-12"}
    easy, hard = leg("Theo Johnson", "receptions", "Over", 1.5, -230), leg("Theo Johnson", "receptions", "Over", 3.5, 120)
    rest = [leg("Darius Slayton", "rec_yds", "Over", 40.5, -150), leg("Cam Skattebo", "rush_yds", "Over", 30.5, -160)]
    gp = {"games": [{"game": "WAS@NYG", "home": "NYG", "away": "WAS", "scorers": [], "threes": [
        {"joint": 0.33, "independent": 0.3, "take_dec": 3.2, "legs": [easy] + rest},
        {"joint": 0.2, "independent": 0.18, "take_dec": 5.5, "legs": [hard] + rest}]}]}
    parlayledger.journal_game_parlay_legs(conn, {"date": "2099-W10", "games": [GAME], "game_parlays": gp}, "nfl")
    assert parlayledger.log_game_parlays(conn, gp, "nfl", "2099-W10") == 2
    held = conn.execute("SELECT line FROM bets WHERE player='Theo Johnson'").fetchall()
    assert [r[0] for r in held] == [1.5], "the journal keeps the first line of a player's market and side"
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=2 WHERE player='Theo Johnson'")
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=60 WHERE player<>'Theo Johnson'")
    conn.commit()
    assert parlayledger.settle(conn)["settled"] == 2
    st = sorted(r[0] for r in conn.execute("SELECT status FROM parlays"))
    assert st == ["lost", "won"], st
    l = conn.execute("SELECT status, actual FROM parlay_legs WHERE player='Theo Johnson' AND line=3.5").fetchone()
    assert (l[0], l[1]) == ("lost", 2.0), "two catches: the over 3.5 lost, whatever the over 1.5 did"
    # A ticket graded the old way (off the over 1.5's row) is put right by
    # the re-audit every settle pass runs.
    bad = conn.execute("SELECT parlay_id FROM parlay_legs WHERE player='Theo Johnson' AND line=3.5").fetchone()[0]
    conn.execute("UPDATE parlay_legs SET status='won' WHERE parlay_id=?", (bad,))
    conn.execute("UPDATE parlays SET status='won', legs_lost=0 WHERE id=?", (bad,))
    conn.commit()
    fixed = parlayledger.resettle(conn)["fixed"]
    assert [(f["id"], f["was"], f["status"]) for f in fixed] == [(bad, "won", "lost")], fixed
    assert parlayledger.resettle(conn) == {"fixed": [], "reopened": 0}, "and it holds"


def test_the_record_page_counts_each_leg_once_and_names_the_books_chance():
    rec = open(os.path.join(ROOT, "web", "js", "record.js"), encoding="utf-8").read()
    i = rec.index("function gpBlockHTML(b, kind, sport) {")
    body = rec[i:rec.index("\n}\n", i)]
    assert "const one = legs.once && legs.once.graded ? legs.once : null;" in body
    assert "`, the books ${Math.round(L.fair * 100)}%`" in body
    assert "each leg once (${legs.graded} across the tickets)" in body


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as exc:                                  # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    if fails:
        print(f"\n{fails} failed")
        sys.exit(1)
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
