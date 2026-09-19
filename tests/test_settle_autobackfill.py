"""A stranded journal row is placed by the settler itself, not by a person.

Ethan, 2026-09-14, from work and unable to run anything: "None of the nfl
edge or most likely bets settled." The stamping at the journal door was
fixed on 09-11, but 134 rows were already sitting under "2026-W01" with
no `game_day`, and the only repair was `--backfill-days --apply` — a
command that waits for a keyboard. `_open_bet_days` cannot see a row
without a calendar day, and `settle_open` returns EARLY on an empty list,
so those rows did not merely go ungraded: they stopped the results ingest
that would have graded them.

So `settle_open` runs `ledger.backfill_game_days` first, every pass. It
only ever fills a NULL and never touches `date` (the settle key), which is
why it is safe to run on every cycle.
"""

import re
import sys
import datetime as dt
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, db, maintenance                   # noqa: E402

SRC = (ROOT / "engine" / "maintenance.py").read_text()
_REAL_CONNECT = db.connect          # captured once; each world patches over it


def _world():
    t = Path(tempfile.mkdtemp())
    ledger.DEFAULT_DB = t / "l.db"
    L = ledger.connect(ledger.DEFAULT_DB)
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = _REAL_CONNECT(t / "h.db")
    # A one-game Week 1 with a final and the stat line the bet needs.
    H.execute("INSERT INTO games (sport, season, period, game_id, home, away, "
              "home_score, away_score, date) VALUES "
              "('nfl',2026,'001','NE@SEA','SEA','NE',13,10,'2026-09-09')")
    H.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, "
              "team, opponent, position, home, market, value) VALUES "
              "('nfl',2026,'001','SEA-001','Cooper Kupp','SEA','NE','WR',1,'rec_yds',71)")
    H.commit()
    # THE STRANDED ROW: week label, no game day — exactly the droplet's 134.
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
              "odds, stake_units, stake_dollars, status, category) VALUES "
              "('2026-09-09T20:00:00','nfl','2026-W01',NULL,'Cooper Kupp','rec_yds',"
              "'OVER',60.5,-110,1,10,'open','likely')")
    L.commit()
    db.connect = lambda path=None: _REAL_CONNECT(t / "h.db")   # settle_open's history
    maintenance.ingest_for_open_bets = lambda *a, **k: {"games": 0}   # no network
    return t, L


def test_the_backfill_runs_before_the_window_is_built():
    """Order is the whole point: placed first, THEN asked which days are open."""
    i_bf = SRC.index("ledger.backfill_game_days(lconn, hconn)")
    i_days = SRC.index("days = _open_bet_days(lconn, today, SETTLE_LOOKBACK_DAYS)")
    assert i_bf < i_days, "the backfill must run before _open_bet_days"


def test_a_stranded_row_settles_in_one_pass():
    t, L = _world()
    before = L.execute("SELECT game_day, status FROM bets").fetchone()
    assert before["game_day"] is None and before["status"] == "open"
    n = maintenance.settle_open(log=lambda *a: None, state_path=t / "st.json",
                                today=dt.date(2026, 9, 11), force=True)
    after = L.execute("SELECT game_day, status, actual, date FROM bets").fetchone()
    assert after["game_day"] == "2026-09-09", dict(after)
    assert after["status"] == "won" and after["actual"] == 71.0, dict(after)
    assert after["date"] == "2026-W01", "the settle key must never be rewritten"
    assert n == 1, n


def test_a_backfill_failure_does_not_stop_the_settle():
    """The repair is a helper to the settle, never a gate on it."""
    t, L = _world()
    L.execute("UPDATE bets SET game_day='2026-09-09'")
    L.commit()
    real = ledger.backfill_game_days
    ledger.backfill_game_days = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        n = maintenance.settle_open(log=lambda *a: None, state_path=t / "st.json",
                                    today=dt.date(2026, 9, 11), force=True)
    finally:
        ledger.backfill_game_days = real
    assert n == 1, n


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
