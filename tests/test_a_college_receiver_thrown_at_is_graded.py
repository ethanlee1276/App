"""A college receiver the play file shows was thrown at is graded, not voided.

Ethan's call, 2026-10-13, from runbook H: "Also add both from my calls,
the CFB and nba things." Since 2026-09-14 a college player with no line in
a final box score has his prop voided, because the box lists only players
with a stat and a scratch looked the same as a receiver who caught
nothing. The college play file names the man every pass was thrown at,
and the nightly now writes that game as a 0 (step 53). So:

  * a bet in a receiving market (and anytime TD, which the file writes for
    every man it has) waits while only the box score is in;
  * once the play file has read his team's game, a man it has as thrown at
    is graded at zero, the way the book grades a player who played — and a
    man still absent is voided, as before;
  * a game the file has not reached in five days falls back to the old
    rule, so nothing waits for ever;
  * every other college market voids off the box score as before;
  * a bet already voided stays voided: past grades are never touched;
  * the stuck-bets report calls a waiting bet waiting, not stuck.

Run directly: `python3 tests/test_a_college_receiver_thrown_at_is_graded.py`
"""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, ledger, cfbroster                       # noqa: E402

cfbroster.CACHE_DIR = Path(tempfile.mkdtemp())     # never the box's roster file

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()      # noqa: E731


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _bet(L, day, player, market, line, side="OVER"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category, team) VALUES "
        "(?, 'cfb', ?, ?, ?, ?, ?, ?, -110, 1, 10, 'open', 'likely', 'IOWA')",
        (f"{day}T12:00:00", day, day, player, market, side, line))
    L.commit()
    return L.execute("SELECT id FROM bets ORDER BY id DESC LIMIT 1").fetchone()[0]


def _game(H, period, game_id="401555"):
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, "
              "home_score, away_score) VALUES ('cfb', 2026, ?, ?, ?, 'IOWA', 'ISU', 24, 20)",
              (period, game_id, period))
    H.commit()


def _log(H, period, game_id, player, market, value):
    db.upsert_player_logs(H, [{"sport": "cfb", "season": 2026, "period": period,
                               "game_id": game_id, "player": player, "team": "IOWA",
                               "opponent": "ISU", "position": "WR", "home": 1,
                               "market": market, "value": float(value)}])
    H.commit()


def _status(L, bid):
    r = L.execute("SELECT status, actual FROM bets WHERE id=?", (bid,)).fetchone()
    return r["status"], r["actual"]


def _box_only(H, game_day):
    """The game is final and ESPN's box score is filed (`-box` rows) — the
    play file has not read it yet."""
    _game(H, game_day)
    _log(H, game_day, "401555-box", "Some Hawkeye", "rec_yds", 40)


def test_a_receiving_bet_waits_while_only_the_box_score_is_in():
    L, H = _world()
    _box_only(H, D(-3))          # a day game: filed under the bet's own date
    bids = [_bet(L, D(-3), "Thrown At", m, ln) for m, ln in
            (("receptions", 1.5), ("rec_yds", 14.5), ("rec_td", 0.5), ("anytime_td", 0.5))]
    assert ledger.settle_from_history(L, H) == 0
    assert all(_status(L, b)[0] == "open" for b in bids)
    b = L.execute("SELECT * FROM bets WHERE id=?", (bids[0],)).fetchone()
    assert ledger._absent_player_verdict(H, b) == "wait"
    # The stuck report says so, instead of "player has no log".
    rows = {r["id"]: r for r in ledger.why_open(L, H, TODAY.isoformat())}
    assert rows[bids[0]]["reason"] == "waiting on the college play file", rows[bids[0]]


def test_any_other_college_market_still_voids_off_the_box_score():
    L, H = _world()
    _box_only(H, D(-2))
    rush = _bet(L, D(-3), "Absent Back", "rush_yds", 30.5)
    passing = _bet(L, D(-3), "Absent Passer", "pass_yds", 180.5, side="UNDER")
    assert ledger.settle_from_history(L, H) == 2
    assert _status(L, rush)[0] == "void" and _status(L, passing)[0] == "void"


def test_the_play_file_has_him_thrown_at_so_he_is_graded_at_zero():
    L, H = _world()
    _game(H, D(-2))
    # The nightly has read the play file: the box rows are gone, and his
    # game is a 0 in every receiving market (cfbstats ZERO_WHEN, ALWAYS).
    _log(H, D(-2), "401555", "Some Hawkeye", "rec_yds", 40)
    for m in ("receptions", "rec_yds", "rec_td", "anytime_td"):
        _log(H, D(-2), "401555", "Thrown At", m, 0)
    over = _bet(L, D(-3), "Thrown At", "receptions", 1.5)
    under = _bet(L, D(-3), "Thrown At", "rec_yds", 14.5, side="UNDER")
    td = _bet(L, D(-3), "Thrown At", "anytime_td", 0.5)
    assert ledger.settle_from_history(L, H) == 3
    assert _status(L, over) == ("lost", 0.0)
    assert _status(L, under) == ("won", 0.0)
    assert _status(L, td) == ("lost", 0.0)


def test_a_man_the_play_file_does_not_have_is_voided():
    L, H = _world()
    _game(H, D(-2))
    _log(H, D(-2), "401555", "Some Hawkeye", "rec_yds", 40)
    bid = _bet(L, D(-3), "Never Thrown At", "receptions", 1.5)
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[0] == "void"


def test_a_game_the_play_file_never_reaches_falls_back_to_the_old_rule():
    L, H = _world()
    _box_only(H, D(-ledger.PLAY_FILE_DAYS - 1))
    bid = _bet(L, D(-ledger.PLAY_FILE_DAYS - 2), "Thrown At", "receptions", 1.5)
    assert ledger.settle_from_history(L, H) == 1
    assert _status(L, bid)[0] == "void"


def test_a_bet_already_voided_stays_voided_when_the_zero_lands():
    L, H = _world()
    _box_only(H, D(-2))
    bid = _bet(L, D(-3), "Thrown At", "receptions", 1.5)
    L.execute("UPDATE bets SET status='void', pnl_units=0, pnl_dollars=0 WHERE id=?", (bid,))
    L.commit()
    _log(H, D(-2), "401555", "Thrown At", "receptions", 0)
    ledger.settle_from_history(L, H)
    ledger.resettle_mismatches(L, H)
    assert _status(L, bid)[0] == "void", "past grades are never touched"


def test_the_rule_names_its_markets_and_its_wait():
    assert set(ledger.PLAY_FILE_MARKETS) == {"receptions", "rec_yds", "rec_td", "anytime_td"}
    assert 3 <= ledger.PLAY_FILE_DAYS <= 7
    doc = (Path(__file__).resolve().parents[1] / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "thrown at" in doc and "Answered 2026-10-13" in doc


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
