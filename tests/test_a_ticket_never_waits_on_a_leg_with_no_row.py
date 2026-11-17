"""No game parlay waits on the box score for good (engine/parlayledger._no_row_verdict,
_with_leg_rows; engine/ledger._paper_leg_absent), STUCKLEGS1.

Ethan's How our reports did, 17 November: nine of Magic at Celtics' parlays a
dash a day and more after the final, and on the record six to nineteen tickets
of every NFL game of the 15th still waiting on the box score two days on. Two
ways a ticket's leg could never grade:

  * no row to grade from: a ticket's legs are journaled on paper first and the
    paper journal refuses a game under way, so a board built before a start and
    journaled after it wrote the tickets and not their legs. Such a leg voids
    once every other leg of its ticket has graded (the game is over), as a book
    voids a leg it cannot settle; a ticket none of whose legs has a row waits;
    the settle and the re-audit agree; and no new ticket is journaled without
    its legs' rows;
  * a player who never played voids already: football by its snap counts
    and the college box, every other league by the no-show sweep once its
    day's games are all final (ledger.settle_from_history). Held here for a
    ticket's paper leg, so the stuck tickets are the legs with no row.

    python3 tests/test_a_ticket_never_waits_on_a_leg_with_no_row.py
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import db, gameparlays as GP, ledger, parlayledger as PL       # noqa: E402

GP.paper_hold = lambda sport: None
EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)


def _journaled():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    b = EG.board()
    GP.attach(b, "nfl")
    PL.journal_game_parlay_legs(conn, b, "nfl")
    assert PL.log_game_parlays(conn, b["game_parlays"], "nfl", b["date"]) == 7
    return conn, b


def _tickets_with(conn, player):
    return [r[0] for r in conn.execute("SELECT DISTINCT parlay_id FROM parlay_legs WHERE player=?", (player,))]


def test_a_leg_with_no_row_voids_once_its_ticket_s_other_legs_graded():
    conn, _b = _journaled()
    # The paper journal refused one leg (its game under way when the board was journaled).
    conn.execute("DELETE FROM bets WHERE player='Isaiah Likely'")
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn.commit()
    hit = _tickets_with(conn, "Isaiah Likely")
    assert hit, "the fixture has tickets on him"
    res = PL.settle(conn)
    assert res["waiting"] == 0 and res["settled"] == 7, res
    for pid in hit:
        p = conn.execute("SELECT status, legs_void, n_legs FROM parlays WHERE id=?", (pid,)).fetchone()
        assert p["legs_void"] == 1, dict(p)
        assert p["status"] == ("won" if p["n_legs"] >= 3 else "void"), dict(p)
        leg = conn.execute("SELECT status FROM parlay_legs WHERE parlay_id=? AND player='Isaiah Likely'",
                           (pid,)).fetchone()
        assert leg["status"] == "void"
    # The re-audit reads the same rule: nothing reopened, nothing moved.
    again = PL.resettle(conn)
    assert again == {"fixed": [], "reopened": 0}, again


def _receptions_leg(conn, player="Isaiah Likely"):
    return conn.execute("SELECT * FROM parlay_legs WHERE player=? AND market='receptions' LIMIT 1",
                        (player,)).fetchone()


def _other_book(conn, b, leg, status, actual, line=None):
    """The same prop in the Most Likely book, settled off the box."""
    conn.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
                 "stake_dollars, status, category, team, actual) VALUES ('2099-11-12T12:00:00', 'nfl', ?, "
                 "'2099-11-12', ?, ?, ?, ?, -150, 1, 10, ?, 'likely', ?, ?)",
                 (b["date"], leg["player"], leg["market"], leg["side"],
                  float(leg["line"]) if line is None else line, status, leg["team"], actual))
    conn.commit()


def _lost_on_its_line(leg):
    """The box's number that loses this leg on its own line."""
    up = str(leg["side"] or "").upper() in ("OVER", "YES")
    return float(leg["line"]) - 0.5 if up else float(leg["line"]) + 0.5


def test_a_leg_with_no_paper_row_grades_from_the_same_prop_in_another_book():
    conn, b = _journaled()
    leg = _receptions_leg(conn)
    assert leg is not None, "the fixture has his catches on a ticket"
    conn.execute("DELETE FROM bets WHERE player='Isaiah Likely'")
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn.commit()
    # Another book took a line a catch lower and won; on the leg's own line the box lost.
    up = str(leg["side"] or "").upper() in ("OVER", "YES")
    _other_book(conn, b, leg, "won", _lost_on_its_line(leg), line=float(leg["line"]) + (-1 if up else 1))
    res = PL.settle(conn)
    assert res["waiting"] == 0, res
    hit = [r[0] for r in conn.execute("SELECT DISTINCT parlay_id FROM parlay_legs WHERE player='Isaiah Likely' "
                                      "AND market='receptions'")]
    assert hit
    for pid in hit:
        p = conn.execute("SELECT status, legs_lost FROM parlays WHERE id=?", (pid,)).fetchone()
        assert (p["status"], p["legs_lost"]) == ("lost", 1), dict(p)
        l = conn.execute("SELECT status FROM parlay_legs WHERE parlay_id=? AND player='Isaiah Likely' "
                         "AND market='receptions'", (pid,)).fetchone()
        assert l["status"] == "lost"
    assert PL.resettle(conn) == {"fixed": [], "reopened": 0}


def test_a_paper_row_still_open_reads_the_same_prop_settled_in_another_book():
    conn, b = _journaled()
    leg = _receptions_leg(conn)
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99 "
                 "WHERE NOT (player='Isaiah Likely' AND market='receptions')")
    conn.commit()
    assert PL.settle(conn)["waiting"] > 0, "its paper row is open: those tickets wait"
    _other_book(conn, b, leg, "lost", _lost_on_its_line(leg))
    res = PL.settle(conn)
    assert res["waiting"] == 0, res
    assert conn.execute("SELECT COUNT(*) FROM parlays WHERE status='open'").fetchone()[0] == 0


def test_the_waiting_report_says_what_each_leg_waits_on():
    conn, b = _journaled()
    conn.execute("DELETE FROM bets WHERE player='Isaiah Likely'")
    conn.commit()
    late = PL.waiting(conn, days=2, today=dt.date(2099, 11, 20))
    assert len(late) == 7, len(late)
    assert all(t["day"] == "2099-11-12" and t["game"] for t in late), late[0]
    states = {l["state"].split(":")[0] for t in late for l in t["legs"]}
    assert states == {"open", "no row"}, states
    assert PL.waiting(conn, days=2, today=dt.date(2099, 11, 13)) == [], "not two days on yet"
    # Graded legs say so, and which book they came from.
    leg = _receptions_leg(conn)
    _other_book(conn, b, leg, "lost", _lost_on_its_line(leg))
    said = [l["state"] for t in PL.waiting(conn, days=2, today=dt.date(2099, 11, 20)) for l in t["legs"]
            if l["player"] == "Isaiah Likely" and l["market"] == "receptions"]
    assert said and all(s == "graded: lost (from the likely book)" for s in said), said


def test_a_push_in_another_book_still_holds_the_players_number():
    conn, b = _journaled()
    leg = _receptions_leg(conn)
    conn.execute("DELETE FROM bets WHERE player='Isaiah Likely'")
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn.commit()
    # Another book's whole-number line pushed on the box's number; the leg's own line lost on it.
    a = _lost_on_its_line(leg)
    _other_book(conn, b, leg, "push", a, line=a)
    assert PL.settle(conn)["waiting"] == 0
    states = {r[0] for r in conn.execute("SELECT status FROM parlay_legs WHERE player='Isaiah Likely' "
                                         "AND market='receptions'")}
    assert states == {"lost"}, states


def _ml_ticket():
    """A first-week three-leg ticket (14-16 November) that took a club to win:
    two props on paper, and the club's moneyline, which no paper row holds."""
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    b = EG.board()
    GP.attach(b, "nfl")
    x = GP.for_game(b, "NYG", "WAS")
    t = dict(x["threes"][0])
    props = [l for l in t["legs"] if l["player"] != "Malik Nabers"][:2]
    ml = {"player": "NYG ML", "team": "NYG", "market": "moneyline", "side": "", "line": 0.0, "odds": -130,
          "book": "FanDuel", "p": 0.62, "_game_leg": True}
    t["legs"] = props + [ml]
    x.update(threes=[t], scorers=[])
    b["game_parlays"]["games"] = [x]
    PL.journal_game_parlay_legs(conn, b, "nfl")
    assert PL.log_game_parlays(conn, b["game_parlays"], "nfl", b["date"]) == 1
    assert not conn.execute("SELECT 1 FROM bets WHERE market='moneyline'").fetchone(), "no paper row for the club"
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn.commit()
    return conn, b


def _club_bet(conn, b, status):
    """The same moneyline in the Most Likely book, as the journal writes one
    (ledger.game_row_keys: the club at OVER 0.5), graded off the final."""
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, stake_units, stake_dollars, "
                 "status, category, team) VALUES ('2099-11-12T12:00:00', 'nfl', ?, 'NYG', 'moneyline', 'OVER', 0.5, "
                 "-130, 0.1, 1, ?, 'likely', 'NYG')", (b["date"], status))
    conn.commit()


def test_a_moneyline_leg_is_graded_on_the_game_not_voided():
    conn, b = _ml_ticket()
    _club_bet(conn, b, "lost")
    assert PL.settle(conn)["settled"] == 1
    p = conn.execute("SELECT status, legs_void, legs_lost FROM parlays").fetchone()
    assert (p["status"], p["legs_void"], p["legs_lost"]) == ("lost", 0, 1), dict(p)
    leg = conn.execute("SELECT status FROM parlay_legs WHERE market='moneyline'").fetchone()
    assert leg["status"] == "lost"


def test_a_ticket_graded_on_a_voided_moneyline_is_put_right():
    """The Ravens' ticket of 16 November: graded while its moneyline had nothing
    to grade on (void), so it read won on its two props though the club lost.
    The re-audit reads the club's own bet and grades it again."""
    conn, b = _ml_ticket()
    assert PL.settle(conn)["settled"] == 1
    p = conn.execute("SELECT status, legs_void FROM parlays").fetchone()
    assert (p["status"], p["legs_void"]) == ("won", 1), dict(p)
    _club_bet(conn, b, "lost")
    again = PL.resettle(conn)
    assert len(again["fixed"]) == 1 and again["fixed"][0]["status"] == "lost", again
    p = conn.execute("SELECT status, legs_void, legs_lost FROM parlays").fetchone()
    assert (p["status"], p["legs_void"], p["legs_lost"]) == ("lost", 0, 1), dict(p)
    # The club's bet still to grade keeps the ticket waiting, never graded around it.
    conn2, b2 = _ml_ticket()
    _club_bet(conn2, b2, "open")
    assert PL.settle(conn2)["waiting"] == 1


def test_a_ticket_none_of_whose_legs_has_a_row_waits():
    conn, _b = _journaled()
    conn.execute("DELETE FROM bets")
    conn.commit()
    res = PL.settle(conn)
    assert res["settled"] == 0 and res["waiting"] == 7, res


def test_a_leg_still_open_keeps_its_ticket_waiting():
    conn, _b = _journaled()
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99 WHERE player != 'Malik Nabers'")
    conn.commit()
    res = PL.settle(conn)
    assert res["waiting"] == len(_tickets_with(conn, "Malik Nabers")), res


def test_no_ticket_is_journaled_without_its_legs_rows():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    b = EG.board()
    GP.attach(b, "nfl")
    PL.journal_game_parlay_legs(conn, b, "nfl")
    conn.execute("DELETE FROM bets WHERE player='Cam Skattebo'")
    conn.commit()
    gp, dropped = PL._with_leg_rows(conn, b["game_parlays"], "nfl", b["date"])
    on_him = sum(1 for x in b["game_parlays"]["games"] for k in ("threes", "scorers") for t in x.get(k) or []
                 if any(l["player"] == "Cam Skattebo" for l in t["legs"]))
    assert dropped == on_him and on_him, (dropped, on_him)
    assert not any(l["player"] == "Cam Skattebo" for x in gp["games"] for k in ("threes", "scorers")
                   for t in x.get(k) or [] for l in t["legs"])
    assert PL.log_game_parlays(conn, gp, "nfl", b["date"]) == 7 - on_him
    # The board's own copy is untouched: the report still shows every ticket.
    assert any(l["player"] == "Cam Skattebo" for x in b["game_parlays"]["games"] for k in ("threes", "scorers")
               for t in x.get(k) or [] for l in t["legs"])
    src = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
    i = src.index("def journal_built_boards(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("journal_game_parlay_legs(conn, board, sport)") < body.index("_with_leg_rows(") \
        < body.index("log_game_parlays(conn, gp_ok,"), "the legs first, then only the tickets they cover"


# --- a player who never played: the no-show sweep's, already -----------------------------------
DAY = (dt.date.today() - dt.timedelta(days=2)).isoformat()


def test_a_paper_leg_on_a_player_who_never_played_voids_by_the_no_show_sweep():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('nba', 2026, ?, 'g1', ?, 'BOS', 'ORL', 105, 115)", (DAY, DAY))
    db.upsert_player_logs(H, [{"sport": "nba", "season": 2026, "period": DAY, "game_id": "g1",
                               "player": f"Celtic {i}", "team": "BOS", "opponent": "ORL", "position": "G",
                               "home": 1, "market": "pts", "value": 10.0} for i in range(8)])
    H.commit()
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category, team) VALUES (?, 'nba', ?, ?, 'Scratched Celtic', 'reb', 'OVER', "
              "3.5, -150, 0, 0, 'open', ?, 'BOS')", (f"{DAY}T12:00:00", DAY, DAY, PL.PARLAY_LEG_CATEGORY))
    L.commit()
    ledger.settle_from_history(L, H)
    assert L.execute("SELECT status FROM bets").fetchone()[0] == "void"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
