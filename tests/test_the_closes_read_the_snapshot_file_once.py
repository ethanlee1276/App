"""The settle pass reads our own snapshot file once, and only its recent
part, for its three closes (engine/ledger._PassSnapshots, _snapshot_floor;
engine/linemoves.stream_wanted's ``since``, LineCloses, OddsCloses;
engine/closebook.SameBookCloses.begin/add/finish).

The heartbeat, 19:15 on Saturday 7 November: 402.5 seconds of grading for
152 bets, 393 of them three reads of the snapshot file (the line closes
152 s, the price closes 145 s, the same book's close 96 s), each the whole
season's file for the open bets' players. What these hold:

  * the line and price readers a row at a time are the functions' own
    answers, and the same-book pass in pieces is ``prepare``'s;
  * a read from an epoch never parses what came before it (less the margin
    and the 64 KB the search lands within), and keeps everything after;
  * the pass's first day is the earliest day a recent open prop can close
    on: an old open bet does not move it, and with nothing recent there is
    no window and the whole file is read, as before;
  * a pass settles every bet exactly as the three whole-file reads did
    (status, result, closing line, closing price, fair close), with one
    read when every gradable bet is recent, and a second, of the whole
    file, only when a bet older than the window grades;
  * that one read parses a fraction of the lines the whole file holds, and
    it is one read only while the recent part is at most a third of the
    file (the three readers hold their rows at once on a 1 GB box); past
    that each reads on its own from the same place, with the same answers;
  * a read that fails falls back to the three readers on the whole file.

Run directly: `python3 tests/test_the_closes_read_the_snapshot_file_once.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import closebook, db, ledger, linemoves                # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402

ET = ZoneInfo("America/New_York")
TODAY = dt.datetime.now(ET).date()
PLAYERS = (("Aaron Judge", "NYY", "BOS"), ("Juan Soto", "NYM", "PHI"),
           ("Gunnar Henderson", "BAL", "TOR"), ("Bobby Witt Jr.", "KC", "DET"),
           ("Jose Ramirez", "CLE", "MIN"), ("Corbin Carroll", "ARI", "SF"))
OTHERS = ("Mookie Betts", "Freddie Freeman", "Kyle Tucker", "Pete Alonso")
BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars")
DAYS_BACK = 45


def _day(back: int) -> dt.date:
    return TODAY - dt.timedelta(days=back)


def _start(day: dt.date) -> float:
    return dt.datetime(day.year, day.month, day.day, 19, 10, tzinfo=ET).timestamp()


def _rows():
    """A season of pulls, in the order the box writes them (by time): every
    day's game priced from six days before it (a few early reads) through
    the last pull before first pitch, and one in-play pull after it; the
    lines move late on some days, so a bet's line is sometimes not the
    close's."""
    rows = []
    for back in range(DAYS_BACK, -2, -1):
        day = _day(back)
        start = _start(day)
        pulls = [start - 6 * 86400, start - 3 * 86400] + [start - h * 3600 - 600 for h in (30, 20, 10, 4, 1)]
        pulls.append(start + 1800)                                  # in play: never a close
        for i, ts in enumerate(pulls):
            for k, (player, _team, _opp) in enumerate(PLAYERS + tuple((o, "", "") for o in OTHERS)):
                for market, base in (("total_bases", 1.5), ("hits", 0.5)):
                    moved = (back + k) % 3 == 0 and i >= len(pulls) - 3
                    line = base + (1.0 if moved and market == "total_bases" else 0.0)
                    for j, book in enumerate(BOOKS):
                        if (back + k + j) % 5 == 0 and i == len(pulls) - 2:
                            continue                               # a book missing from the last pull
                        over = -110 - ((back + i + j + k) % 7) * 5
                        under = None if market == "hits" and j == 3 else 100 - ((back + j) % 4) * 5
                        rows.append({"ts": ts, "player": player, "market": market, "book": book,
                                     "line": line, "over_odds": over, "under_odds": under,
                                     "start_ts": start})
    # Yesterday, Corbin Carroll's books took his total bases down after the
    # read three days out, and no other read came (the close is that read:
    # a read that starts too late would lose it).
    start = _start(_day(1))
    rows = [r for r in rows if not (r["player"] == "Corbin Carroll" and r["market"] == "total_bases"
                                    and r["start_ts"] == start and r["ts"] > start - 2 * 86400)]
    # And the copy the odds adapter once made: yesterday's last read of Josh
    # Bell's hits filed under Jake Bell too, the same pull, the same quotes
    # (linemoves._Copies); each has reads of his own before it, and Josh
    # Bell's sit by the copy, so it is his and Jake Bell's close is his own.
    for name, line, over in (("Jake Bell", 0.5, -150), ("Josh Bell", 0.5, -120)):
        for h in (30, 10):
            for book in BOOKS[:3]:
                rows.append({"ts": start - h * 3600 - 300, "player": name, "market": "hits", "book": book,
                             "line": line, "over_odds": over, "under_odds": 110, "start_ts": start})
    for name in ("Jake Bell", "Josh Bell"):
        for book in BOOKS[:3]:
            rows.append({"ts": start - 1800, "player": name, "market": "hits", "book": book,
                         "line": 0.5, "over_odds": -125, "under_odds": 105, "start_ts": start})
    rows.sort(key=lambda r: r["ts"])
    return rows


def _file(rows) -> Path:
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


ROWS = _rows()
FILE = _file(ROWS)


def _journal(old: bool = True, future: bool = True):
    """Open props on the last two days (and, if asked, one from a month ago
    whose stat line just landed, and tomorrow's), their stat lines and final
    scores."""
    L = ledger.connect(":memory:")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1.0)
    H = db.connect(":memory:")
    bets = []
    for back in (1, 2):
        for k, (player, team, opp) in enumerate(PLAYERS):
            bets.append((back, player, team, opp, "total_bases", "OVER", 1.5, BOOKS[k % 4], -115, 2.0))
            bets.append((back, player, team, opp, "hits", "UNDER", 0.5, BOOKS[(k + 1) % 4], 105, 0.0))
    bets.append((1, "Jake Bell", "MIA", "ATL", "hits", "OVER", 0.5, "DraftKings", -150, 1.0))
    if old:
        bets.append((30, "Aaron Judge", "NYY", "BOS", "total_bases", "OVER", 1.5, "FanDuel", -120, 3.0))
        bets.append((30, "Juan Soto", "NYM", "PHI", "hits", "UNDER", 0.5, "BetMGM", 110, 1.0))
    for back, player, team, opp, market, side, line, book, odds, value in bets:
        day = _day(back).isoformat()
        L.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
                  "stake_units, stake_dollars, status, category, team) VALUES "
                  "(?, 'mlb', ?, ?, ?, ?, ?, ?, ?, 1, 10, 'open', 'main', ?)",
                  (f"{day}T12:00:00", day, player, market, side, line, book, odds, team))
        db.upsert_games(H, [{"sport": "mlb", "season": TODAY.year, "period": day,
                             "game_id": f"{opp}@{team}-{day}", "home": team, "away": opp,
                             "home_score": 5, "away_score": 3, "spread": 0.0, "total": 8.5,
                             "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
        db.upsert_player_logs(H, [{"sport": "mlb", "season": TODAY.year, "period": day,
                                   "game_id": f"{opp}@{team}-{day}", "player": player, "team": team,
                                   "opponent": opp, "position": "RF", "home": 1, "market": market,
                                   "value": value}])
    if future:
        day = _day(-1).isoformat()
        L.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
                  "stake_units, stake_dollars, status, category, team) VALUES "
                  "(?, 'mlb', ?, 'Juan Soto', 'total_bases', 'OVER', 1.5, 'FanDuel', -110, 1, 10, "
                  "'open', 'main', 'NYM')", (f"{day}T12:00:00", day))
    L.commit()
    H.commit()
    return L, H


COLS = ("id", "status", "actual", "closing_line", "closing_odds", "closing_fair", "pnl_units")


def _settle(old: bool = True, future: bool = True, the_old_way: bool = False, share=None):
    """Settle the journal; ``share`` sets ONE_READ_MAX_SHARE (1.0: always one
    read of the recent part; 0.0: each reader on its own from it)."""
    L, H = _journal(old, future)
    saved = (linemoves.HISTORY_PATH, ledger._PassSnapshots._one_read,
             ledger._PassSnapshots._each_read, ledger.ONE_READ_MAX_SHARE)
    linemoves.HISTORY_PATH = FILE
    if share is not None:
        ledger.ONE_READ_MAX_SHARE = share
    if the_old_way:
        def _refuse(self, since):
            raise RuntimeError("the old way")
        ledger._PassSnapshots._one_read = ledger._PassSnapshots._each_read = _refuse
    try:
        ledger.take_grade_parts()
        n = ledger.settle_from_history(L, H)
        parts = ledger.take_grade_parts()
    finally:
        (linemoves.HISTORY_PATH, ledger._PassSnapshots._one_read,
         ledger._PassSnapshots._each_read, ledger.ONE_READ_MAX_SHARE) = saved
    got = [tuple(r[c] for c in COLS) for r in L.execute(f"SELECT {', '.join(COLS)} FROM bets ORDER BY id")]
    return n, got, parts


def test_the_readers_a_row_at_a_time_are_the_functions():
    lines, odds = linemoves.LineCloses(), linemoves.OddsCloses()
    for r in ROWS:
        lines.add(r)
        odds.add(r)
    li, oi = lines.index(), odds.index()
    lf, of = linemoves.closing_lines_by_date(ROWS), linemoves.closing_odds_by_date(ROWS)
    assert dict(li) == dict(lf) and li.stamped == lf.stamped and li.copied == lf.copied
    assert dict(oi) == dict(of) and oi.stamped == of.stamped
    assert lf and of and lf.stamped
    bets = [{"player": p, "market": "total_bases", "line": 1.5} for p, _t, _o in PLAYERS]
    whole = closebook.SameBookCloses(None, snapshots=ROWS)
    whole.prepare(bets)
    parts = closebook.SameBookCloses(None)
    parts.begin(bets)
    for r in ROWS:
        parts.add(r)
    parts.finish()
    assert parts._snap == whole._snap and parts._stamped_keys == whole._stamped_keys and whole._snap


def test_a_read_from_an_epoch_skips_what_came_before_and_keeps_the_rest():
    want = {(normalize_name(p), "total_bases") for p, _t, _o in PLAYERS}
    since = _start(_day(10)) - 86400
    every = list(linemoves.stream_wanted(want, FILE))
    late = list(linemoves.stream_wanted(want, FILE, since=since))
    cut = since - linemoves.SINCE_MARGIN_S
    must = [r for r in every if r["ts"] >= cut]
    assert late[-len(must):] == must, "every line from the epoch on, in order"
    assert len(late) < len(every) * 0.5, (len(late), len(every))
    # The search lands at most 64 KB early: a few minutes of pulls, not days.
    assert min(r["ts"] for r in late) > cut - 3 * 86400
    assert FILE.stat().st_size > 20 * 65536, "big enough for the search to cut"


def test_the_first_day_is_the_earliest_a_recent_bet_can_close_on():
    L, H = _journal()
    rows = L.execute("SELECT * FROM bets WHERE status='open'").fetchall()
    first, since = ledger._snapshot_floor(H, rows, today=TODAY)
    assert first == _day(2).isoformat(), "the month-old bet does not move it"
    start = _day(2) - dt.timedelta(days=ledger.SNAPSHOT_LEAD_DAYS)
    assert since == dt.datetime(start.year, start.month, start.day, tzinfo=ET).timestamp()
    old = [r for r in rows if r["date"] == _day(30).isoformat()]
    assert ledger._snapshot_floor(H, old, today=TODAY) == (None, None), "nothing recent: no window"
    assert ledger.SNAPSHOT_LEAD_DAYS >= 7
    assert ledger.SNAPSHOT_RECENT_DAYS > ledger.PLAY_FILE_DAYS, \
        "a college bet waiting for its play file grades inside the recent read"


def test_a_pass_settles_every_bet_exactly_as_the_three_whole_reads_did():
    n_old, old, parts_old = _settle(the_old_way=True)
    for share in (None, 1.0, 0.0):
        n, got, _parts = _settle(share=share)
        assert n == n_old == 27, (share, n, n_old)
        assert got == old, (share, [(a, b) for a, b in zip(got, old) if a != b])
    n_new, new, parts = _settle()
    assert 0.0 < parts["snapshot_share"] < 0.6, parts
    # Corbin Carroll's close is the read three days out, and Jake Bell's fair
    # close is his own last read (-150/+110), the copy (-125/+105) left out.
    byid = {r[0]: r for r in new}
    L, _H = _journal()
    carroll = L.execute("SELECT id FROM bets WHERE player='Corbin Carroll' AND market='total_bases' "
                        "AND date=?", (_day(1).isoformat(),)).fetchone()[0]
    bell = L.execute("SELECT id FROM bets WHERE player='Jake Bell'").fetchone()[0]
    assert byid[carroll][3] == 1.5, byid[carroll]
    assert byid[bell][3] == 0.5 and byid[bell][5] == 0.5575, byid[bell]
    # The closes are real, not two empties agreeing.
    assert sum(1 for r in new if r[3] is not None) >= 20 and sum(1 for r in new if r[4] is not None) >= 20
    assert sum(1 for r in new if r[5] is not None) >= 10
    assert parts["snapshot_from"] == _day(2).isoformat()
    assert parts["snapshot_reads"] == 2 and parts["snapshot_whole"] == 1, \
        "the recent read, and the whole file for the month-old bets"
    assert parts_old["snapshot_reads"] == 2, parts_old


def test_with_only_recent_bets_one_read_does_it_and_parses_a_fraction():
    loads = []
    real = linemoves.json.loads

    class _Counting:
        JSONDecodeError = json.JSONDecodeError

        @staticmethod
        def loads(s):
            loads.append(1)
            return real(s)
    linemoves.json = _Counting
    try:
        n_new, new, parts = _settle(old=False, share=1.0)
    finally:
        linemoves.json = json
    n_old, old, _p = _settle(old=False, the_old_way=True)
    assert n_new == n_old == 25 and new == old
    assert parts["snapshot_reads"] == 1 and "snapshot_whole" not in parts, parts
    wanted = sum(1 for r in ROWS if r["player"] in {p for p, _t, _o in PLAYERS}
                 and r["market"] in ("total_bases", "hits"))
    assert len(loads) < wanted * 0.6, (len(loads), wanted)


def test_a_read_that_fails_is_done_the_old_way():
    printed = []
    import builtins
    saved = builtins.print
    builtins.print = lambda *a, **k: printed.append(" ".join(map(str, a)))
    try:
        n, got, parts = _settle(the_old_way=True)
    finally:
        builtins.print = saved
    assert n == 27 and any("each close reader reads it on its own" in t for t in printed), printed


def test_the_settle_pass_reads_through_it():
    import inspect
    src = inspect.getsource(ledger.settle_from_history)
    assert "_PassSnapshots(_want, _open_rows, hist_conn, closes_cache[\"_close_days\"], parts)" in src
    assert "_snapshot_closes(" not in src and "_snapshot_close_odds(" not in src
    assert src.count("_snapfile.for_bet(b, _dates)") == 3


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
