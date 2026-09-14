"""Sunday's props grade the day the numbers exist, not the night after.

Ethan, Monday 2026-09-14: "none of the nfl bets from Sunday settled."
A prop grades from nflverse's weekly stat file, pulled ONCE in the nightly
chores; on a Sunday slate nflverse publishes overnight, after our pull,
so every Sunday prop sat open until Tuesday. The intraday settle now
re-pulls the weekly stats while an NFL pick is open, throttled on its own
ingest_log row.
"""

import sys
import tempfile
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, db, maintenance, ingest             # noqa: E402


def _world(open_nfl=True):
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    if open_nfl:
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
                  "odds, stake_units, stake_dollars, status, category) VALUES "
                  "('2026-09-13T20:00:00','nfl','2026-W01','2026-09-13','X','rec_yds',"
                  "'OVER',60.5,-110,1,10,'open','main')")
        L.commit()
    calls = []
    keep = (ingest.ingest_nfl_results, maintenance.__dict__.get("_nba_day"),
            maintenance.__dict__.get("_wnba_day"))
    ingest.ingest_nfl_results = lambda conn, season: (calls.append(season) or
                                                       {"player_logs": 3, "skipped": []})
    maintenance._nba_day = None
    maintenance._wnba_day = None
    from engine.sources import livescores
    keep_fin = livescores.ingest_finals
    livescores.ingest_finals = lambda conn, league: {"games": 0, "waiting": 0, "skipped": []}
    def restore():
        ingest.ingest_nfl_results = keep[0]
        maintenance._nba_day, maintenance._wnba_day = keep[1], keep[2]
        livescores.ingest_finals = keep_fin
    return L, H, calls, restore


def test_the_pull_runs_while_an_nfl_pick_is_open():
    L, H, calls, restore = _world()
    try:
        maintenance.ingest_for_open_bets(L, H, ["2026-09-13"], log=lambda *a: None)
    finally:
        restore()
    assert calls == [2026], calls
    row = H.execute("SELECT sport, kind, rows FROM ingest_log ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(row) == ("nfl", maintenance.NFL_STATS_KIND, 3), tuple(row)


def test_the_pull_is_throttled_on_its_own_log_row():
    L, H, calls, restore = _world()
    try:
        maintenance.ingest_for_open_bets(L, H, ["2026-09-13"], log=lambda *a: None)
        maintenance.ingest_for_open_bets(L, H, ["2026-09-13"], log=lambda *a: None)
    finally:
        restore()
    assert calls == [2026], f"pulled {len(calls)} times inside the throttle"
    assert maintenance._nfl_stats_due(H) is False
    later = dt.datetime.utcnow().timestamp() + maintenance.NFL_STATS_EVERY_S + 1
    assert maintenance._nfl_stats_due(H, now=later) is True


def test_no_open_nfl_pick_means_no_pull():
    L, H, calls, restore = _world(open_nfl=False)
    try:
        maintenance.ingest_for_open_bets(L, H, ["2026-09-13"], log=lambda *a: None)
    finally:
        restore()
    assert calls == [], calls


def test_the_season_follows_the_football_calendar():
    assert maintenance._nfl_season_of("2026-09-13") == 2026
    assert maintenance._nfl_season_of("2027-01-10") == 2026
    assert maintenance._nfl_season_of("2027-08-01") == 2027


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
