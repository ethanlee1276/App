"""A settled moneyline or total keeps its close: the board's last pregame line.

Found 2026-10-15 in Ethan's `closecheck.py --sport nfl` paste: every NFL
moneyline bet (31 of 31) had no close. The game-line branch of the settle
graded the bet and banked nothing — the stores the props close from carry
no game lines. The board's own do: engine/lineopen writes each game's
numbers every build into `now_*` columns and stops at kickoff, so the row
left standing is the last pregame line the board read. The settle now
banks it (`ledger._game_close`): a moneyline on its side's price, a total
on its number, a spread on its club's number negated as the bet is stored
(since 2026-10-17 — "mlb spread (0/21)"), and `fill_game_closes` gives
the ones graded before that their close, fill-only.

Pinned here: an NFL moneyline closes on its own side's price, the club
under either spelling, and its price CLV reads the right way; a total
closes on the number; a Monday night game the history files a day off the
board's Eastern day still finds its line; a baseball series takes its own
night's price, never the next night's; a doubleheader banks none (one row
per pair per day — which leg it ended on is a guess); a price the board
marks as dated never moves the close; no store means no close and the same
grade; a store that can't be read says so, and one no board has written
lines into yet stays quiet; the close repair keeps a game line's close and
counts it apart.

Offline: a temporary journal, history and crowd database each; the crowd
database's path is pointed at its temp file and put back.

Run directly: `python3 tests/test_a_game_line_keeps_its_close.py`
"""
import datetime as dt
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import crowd, db, ledger, lineopen                     # noqa: E402

WEEK, SUNDAY, MONDAY, TUESDAY = "2026-W05", "2026-10-11", "2026-10-12", "2026-10-13"
DAY = (dt.date.today() - dt.timedelta(days=3)).isoformat()
NOW = 1_790_000_000


def _shift(day, n):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def _line(sport, date, away, home, home_ml, away_ml, total, ts=NOW):
    """A line_opens row: opened a day earlier at other numbers, `now_*` the last pregame line."""
    return (sport, date, away, home, ts - 86400, -1.5, total - 1.0, home_ml - 15, away_ml + 15,
            ts, -2.5, total, home_ml, away_ml)


def _crowd(rows):
    p = Path(tempfile.mkdtemp()) / "crowd.db"
    c = sqlite3.connect(p)
    lineopen.ensure_tables(c)
    c.executemany("INSERT INTO line_opens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    return p


def _with_crowd(path, fn):
    saved = crowd.DB_PATH
    crowd.DB_PATH = Path(path)
    try:
        return fn()
    finally:
        crowd.DB_PATH = saved


def _world(sport, games):
    """games: (season, period, game_id, date, home, away, home_score, away_score)."""
    t = Path(tempfile.mkdtemp())
    L, H = ledger.connect(t / "l.db"), db.connect(t / "h.db")
    H.executemany("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [(sport, *g) for g in games])
    H.commit()
    return L, H


def _bet(L, sport, date, market, player, side="OVER", line=0.5, odds=-110, leg=None):
    L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
              "stake_dollars, status, category, leg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 'open', 'board', ?)",
              (f"{DAY}T15:00:00", sport, date, date, player, market, side, line, odds, leg))
    L.commit()


def _closes(L):
    return {(r[0], r[1]): (r[2], r[3], r[4]) for r in L.execute(
        "SELECT market, player, status, closing_line, closing_odds FROM bets")}


#: Rams 24, 49ers 20 in week 5: the history spells the Rams "LA", the board "LAR".
RAMS = [(2026, "005", "2026_05_SF_LA", SUNDAY, "LA", "SF", 24, 20)]


def test_an_nfl_moneyline_closes_on_its_own_sides_last_pregame_price():
    L, H = _world("nfl", RAMS)
    _bet(L, "nfl", WEEK, "moneyline", "LAR", odds=-140)
    _bet(L, "nfl", WEEK, "moneyline", "SF", odds=+125)
    store = _crowd([_line("nfl", SUNDAY, "SF", "LAR", -150, +130, 48.5)])
    assert _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="nfl")) == 2
    got = _closes(L)
    assert got[("moneyline", "LAR")] == ("won", None, -150), got
    assert got[("moneyline", "SF")] == ("lost", None, 130), got
    clv = {r["player"]: ledger._bet_price_clv(r) for r in L.execute("SELECT * FROM bets")}
    assert clv["LAR"] > 0.015, "took -140, closed -150: the market came to us"
    assert clv["SF"] < -0.009, "took +125, closed +130: it went away"


def test_a_total_closes_on_the_number_and_a_spread_on_its_clubs_number():
    L, H = _world("nfl", RAMS)
    _bet(L, "nfl", WEEK, "total", "SF@LAR", side="OVER", line=47.5)      # 44 points: lost
    # The journal stores a spread NEGATED, side OVER (`game_row_keys`):
    # LAR laid at -2.0 is line 2.0; SF taking +2.0 is line -2.0.
    _bet(L, "nfl", WEEK, "spread", "LAR", line=2.0)                      # won by 4
    _bet(L, "nfl", WEEK, "spread", "SF", line=-2.0)                      # lost by 4
    store = _crowd([_line("nfl", SUNDAY, "SF", "LAR", -150, +130, 48.5)])   # LAR closes -2.5
    assert _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="nfl")) == 3
    got = _closes(L)
    assert got[("total", "SF@LAR")] == ("lost", 48.5, None), got
    assert got[("spread", "LAR")] == ("won", 2.5, None), got
    assert got[("spread", "SF")] == ("lost", -2.5, None), got
    clv = {r["player"]: ledger._bet_clv(r) for r in L.execute(
        "SELECT * FROM bets WHERE market='spread'")}
    assert clv == {"LAR": 0.5, "SF": -0.5}, \
        "laid -2 and it closed -2.5: the market came to the Rams bettor, away from the 49ers one"


def test_a_run_line_graded_before_its_close_was_read_is_filled_once():
    """Ethan's doctor, 2026-10-17: "mlb spread (0/21)". A settled bet never
    settles again, so the run lines graded before the spread could close
    are filled by `fill_game_closes` — fill-only, the settle's own store
    and function, a close already banked never touched."""
    L, H = _world("mlb", [(2026, DAY, "746201", DAY, "NYY", "BOS", 3, 5)])
    _bet(L, "mlb", DAY, "spread", "BOS", line=-1.5)        # BOS -1.5, won by 2
    _bet(L, "mlb", DAY, "moneyline", "BOS", odds=+120)
    _bet(L, "mlb", DAY, "total", "BOS@NYY", line=8.5)
    L.execute("UPDATE bets SET status='won', closing_line=NULL, closing_odds=NULL")
    L.execute("UPDATE bets SET closing_line=9.0 WHERE market='total'")   # banked already
    L.commit()
    store = _crowd([_line("mlb", DAY, "BOS", "NYY", +110, -130, 8.5)])  # home -2.5 → BOS +2.5
    dry = _with_crowd(store, lambda: ledger.fill_game_closes(L, H, apply=False))
    assert (dry["examined"], dry["filled"]) == (2, 2), dry
    assert _closes(L)[("spread", "BOS")][1] is None, "a dry run writes nothing"
    wet = _with_crowd(store, lambda: ledger.fill_game_closes(L, H, apply=True))
    assert wet["by_market"] == {"mlb moneyline": 1, "mlb spread": 1}, wet
    got = _closes(L)
    assert got[("spread", "BOS")][1] == -2.5 and got[("moneyline", "BOS")][2] == -130, got
    assert got[("total", "BOS@NYY")][1] == 9.0, "a banked close is never touched"
    again = _with_crowd(store, lambda: ledger.fill_game_closes(L, H, apply=True))
    assert again["examined"] == 0, "once filled, nothing left to examine"


def test_a_monday_night_game_filed_a_day_apart_still_finds_its_line():
    # The history dates the game Tuesday (UTC); the board files it Monday (Eastern).
    L, H = _world("nfl", [(2026, "005", "2026_05_DAL_WAS", TUESDAY, "WAS", "DAL", 17, 27)])
    _bet(L, "nfl", WEEK, "moneyline", "DAL", odds=-105)
    store = _crowd([_line("nfl", MONDAY, "DAL", "WAS", +100, -120, 44.5)])
    assert _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="nfl")) == 1
    assert _closes(L)[("moneyline", "DAL")] == ("won", None, -120), _closes(L)


def test_a_baseball_series_takes_its_own_nights_price():
    L, H = _world("mlb", [(2026, DAY, "746001", DAY, "NYY", "BOS", 3, 5)])
    _bet(L, "mlb", DAY, "moneyline", "BOS", odds=+120)
    store = _crowd([_line("mlb", _shift(DAY, -1), "BOS", "NYY", -160, +140, 8.5, ts=NOW - 86400),
                    _line("mlb", DAY, "BOS", "NYY", -145, +125, 8.5, ts=NOW),
                    _line("mlb", _shift(DAY, 1), "BOS", "NYY", -130, +110, 9.0, ts=NOW + 86400)])
    _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="mlb"))
    assert _closes(L)[("moneyline", "BOS")] == ("won", None, 125), "tonight's price, not tomorrow's"


def test_a_doubleheader_banks_no_close():
    L, H = _world("mlb", [(2026, DAY, "746100", DAY, "NYY", "BOS", 6, 2),
                          (2026, DAY, "746100-G2", DAY, "NYY", "BOS", 1, 4)])
    _bet(L, "mlb", DAY, "moneyline", "NYY", odds=-130, leg=1)
    store = _crowd([_line("mlb", DAY, "BOS", "NYY", -140, +120, 8.0)])
    _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="mlb"))
    assert _closes(L)[("moneyline", "NYY")] == ("won", None, None), \
        "graded off its own leg; the one stored row could be either leg's price"


def test_a_dated_price_never_moves_the_close():
    c = sqlite3.connect(":memory:")
    g = {"away": "BOS", "home": "NYY", "date": DAY, "kickoff": "2099-01-01T23:05:00Z",
         "spread": -1.5, "total": 8.5, "home_ml": -145, "away_ml": 125}
    assert lineopen.record(c, "mlb", [g], NOW) == {"games": 1, "opened": 1, "updated": 0}
    dated = dict(g, home_ml=-200, away_ml=170, total=7.0, price_stale=True)
    assert lineopen.record(c, "mlb", [dated], NOW + 3600) == {"games": 1, "opened": 0, "updated": 0}
    assert c.execute("SELECT now_ts, now_home_ml, now_away_ml, now_total FROM line_opens").fetchone() == \
        (NOW, -145, 125, 8.5), "a dated price leaves the last current one standing"
    # A game first seen on a dated price opens its row, with no close in it.
    first = dict(g, away="TB", home="TOR", price_stale=True)
    assert lineopen.record(c, "mlb", [first], NOW)["opened"] == 1
    assert c.execute("SELECT open_home_ml, now_ts, now_home_ml FROM line_opens WHERE home='TOR'").fetchone() == \
        (-145, None, None)
    b = {"sport": "mlb", "market": "moneyline", "player": "TOR", "date": DAY}
    assert ledger._game_close({"_line_opens": c}, None, b, {"home": "TOR", "away": "TB"}) == (None, None)
    assert ledger._game_close({"_line_opens": c}, None, dict(b, player="NYY"),
                              {"home": "NYY", "away": "BOS"}) == (None, -145)
    line = lineopen.attach_to_board({"games": [dated]}, "mlb", conn=c, now=NOW + 7200)
    assert "1 dated price(s) kept out of the close" in line, line


def test_no_store_means_no_close_and_the_same_grade():
    L, H = _world("nfl", RAMS)
    _bet(L, "nfl", WEEK, "moneyline", "LAR", odds=-140)
    absent = Path(tempfile.mkdtemp()) / "none" / "crowd.db"
    assert _with_crowd(absent, lambda: ledger.settle_from_history(L, H, sport="nfl")) == 1
    assert _closes(L)[("moneyline", "LAR")] == ("won", None, None)
    assert not absent.exists(), "the settle reads the store; it never creates one"


def test_an_unreadable_store_says_so_and_a_quiet_one_does_not():
    import contextlib
    import io
    L, H = _world("nfl", RAMS)
    _bet(L, "nfl", WEEK, "moneyline", "LAR", odds=-140)
    bad = Path(tempfile.mkdtemp()) / "crowd.db"
    bad.write_bytes(b"not a database. " * 64)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert _with_crowd(bad, lambda: ledger.settle_from_history(L, H, sport="nfl")) == 1
    assert "game-line closes skipped, the board's lines unreadable" in out.getvalue(), out.getvalue()
    assert _closes(L)[("moneyline", "LAR")] == ("won", None, None), "graded all the same"
    quiet = Path(tempfile.mkdtemp()) / "crowd.db"
    c = sqlite3.connect(quiet)
    c.execute("CREATE TABLE crowd_snaps (x)")
    c.commit()
    c.close()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert _with_crowd(quiet, ledger._line_opens_ro) is None
    assert out.getvalue() == "", "no board has written its lines yet: nothing to say"


def test_the_repair_keeps_a_game_lines_close_and_counts_it_apart():
    from engine import linemoves
    L, H = _world("nfl", RAMS)
    _bet(L, "nfl", WEEK, "moneyline", "LAR", odds=-140)
    store = _crowd([_line("nfl", SUNDAY, "SF", "LAR", -150, +130, 48.5)])
    _with_crowd(store, lambda: ledger.settle_from_history(L, H, sport="nfl"))
    fd, snaps = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = Path(snaps)
    try:
        r = ledger.repair_closing_odds(L, apply=True, hist_conn=H)
    finally:
        linemoves.HISTORY_PATH = saved
        os.unlink(snaps)
    assert (r["kept"], r["cleared"], r["agreed"]) == (1, 0, 0), r
    assert _closes(L)[("moneyline", "LAR")] == ("won", None, -150), "never cleared"


def test_the_wiring():
    led = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = led.index("def settle_from_history(")
    assert "_game_close(closes_cache, hist_conn, b, g, n_games=len(rows))" in led[i:i + 9000]
    assert "_settle_one(conn, b, actual_fn(g), _cl, closing_odds=_co)" in led[i:i + 9000]
    pipe = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
    j = pipe.index("def _game_to_dict(")
    assert '"price_stale": bool(getattr(g, "price_stale", False)),' in pipe[j:j + 2500], \
        "the NFL board's game row says when its price is dated"
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert "KEPT       a moneyline's, total's or spread's close" in launch
    i = launch.index("def fill_game_closes(")
    assert "ledger.fill_game_closes(conn, hist_db.connect(), apply=apply, sport=sport)" in launch[i:i + 3000]
    assert '_backed_up("fill-game-closes")' in launch[i:i + 3000], "a write takes the backup first"
    assert '"--fill-game-closes" in argv' in launch


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
