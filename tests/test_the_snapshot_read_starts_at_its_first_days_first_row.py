"""The settle pass's read of our own snapshot file starts at the first row
filed under the first day it serves (engine/linemoves.day_offsets,
day_start, _line_day, _Copies.unsure, stream_wanted's ``start``;
engine/ledger._PassSnapshots._day_start, _read, _one_read).

The heartbeat, 20:26 on Saturday 7 November: 89.6 seconds of grading, 82.8
of them one read of 30% of the snapshot file. It read from 15 October, the
SNAPSHOT_LEAD_DAYS before the 29th, the first day an open bet could close
on, in case a game's snapshot was taken that long before it. What these
hold:

  * the day index files each slate day under the first byte of its first
    row, exactly as parsing every line and asking `_slate_day` does, and an
    odd line (escapes, a null start, no stamp, half a line) never hides a
    day's first row;
  * it picks up where it stopped as the file grows, leaves a line still
    being written for later, spreads its first build over calls by its
    budget, and is built again when its file is no longer the one it read;
  * the recent read starts at the first row of the days the open props
    close on, less a lead for each player's earlier quotes of his own: a
    fraction of what the old lead read, and every close it serves is the
    whole file's; it never starts before the old lead did;
  * a copied quote set it cannot place (a name with no read of his own in
    what was read) has the read done again from the old lead;
  * a day no open bet can close on (a card priced weeks ahead) does not move
    where the read starts;
  * while the index is still being built, the read starts at the old lead.

Run directly: `python3 tests/test_the_snapshot_read_starts_at_its_first_days_first_row.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import closebook, db, ledger, linemoves as LM          # noqa: E402
from engine.sources.oddsapi import normalize_name                   # noqa: E402

ET = ZoneInfo("America/New_York")
TODAY = dt.datetime.now(ET).date()
PLAYERS = (("Aaron Judge", "NYY", "BOS"), ("Juan Soto", "NYM", "PHI"),
           ("Gunnar Henderson", "BAL", "TOR"), ("Bobby Witt Jr.", "KC", "DET"))
OTHERS = ("Mookie Betts", "Freddie Freeman", "Kyle Tucker")
BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars")
DAYS_BACK = 40


def _day(back: int) -> dt.date:
    return TODAY - dt.timedelta(days=back)


def _start(day: dt.date) -> float:
    return dt.datetime(day.year, day.month, day.day, 19, 10, tzinfo=ET).timestamp()


def _season():
    """Every day's games priced from a day and a half before first pitch to
    the last pull before it, and once in play; the lines move late on some
    days."""
    rows = []
    for back in range(DAYS_BACK, -2, -1):
        day = _day(back)
        start = _start(day)
        pulls = [start - h * 3600 - 600 for h in (36, 20, 10, 4, 1)] + [start + 1800]
        for i, ts in enumerate(pulls):
            for k, player in enumerate([p for p, _t, _o in PLAYERS] + list(OTHERS)):
                for market, base in (("total_bases", 1.5), ("hits", 0.5)):
                    moved = (back + k) % 3 == 0 and i >= len(pulls) - 3
                    for j, book in enumerate(BOOKS):
                        rows.append({"ts": ts, "player": player, "market": market, "book": book,
                                     "line": base + (1.0 if moved and market == "total_bases" else 0.0),
                                     "over_odds": -110 - ((back + i + j + k) % 7) * 5,
                                     "under_odds": 100 - ((back + j) % 4) * 5, "start_ts": start})
    return rows


def _file(rows, name="line_history.jsonl") -> Path:
    rows = sorted(rows, key=lambda r: r["ts"])
    p = Path(tempfile.mkdtemp()) / name
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _truth(path: Path) -> dict:
    """Each day's first row, by parsing every line and asking `_slate_day`."""
    out, pos = {}, 0
    with path.open("rb") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
                day = LM._slate_day(r) if isinstance(r, dict) else None
            except Exception:                                       # noqa: BLE001
                day = None
            if day is not None:
                out.setdefault(day, pos)
            pos += len(raw)
    return out


def _journal(extra=()):
    """Open props on the last two days, their stat lines and final scores."""
    L = ledger.connect(":memory:")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1.0)
    H = db.connect(":memory:")
    bets = [(back, p, t, o, m, s) for back in (1, 2) for p, t, o in PLAYERS
            for m, s in (("total_bases", "OVER"), ("hits", "UNDER"))] + list(extra)
    for back, player, team, opp, market, side in bets:
        day = _day(back).isoformat()
        L.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
                  "stake_units, stake_dollars, status, category, team) VALUES "
                  "(?, 'mlb', ?, ?, ?, ?, 1.5, 'FanDuel', -110, 1, 10, 'open', 'main', ?)",
                  (f"{day}T12:00:00", day, player, market, side, team))
        db.upsert_games(H, [{"sport": "mlb", "season": TODAY.year, "period": day,
                             "game_id": f"{opp}@{team}-{day}", "home": team, "away": opp,
                             "home_score": 5, "away_score": 3, "spread": 0.0, "total": 8.5,
                             "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    L.commit()
    H.commit()
    rows = L.execute("SELECT * FROM bets WHERE status='open'").fetchall()
    return rows, H


def _both(path: Path, extra=()):
    """The pass's recent read and the three whole-file reads, for the
    journal's open bets: ``(pass reader, its read, whole lines, whole odds,
    whole same-book, parts)``; the old lead's share of the file goes on
    ``parts["lead_share"]``."""
    rows, H = _journal(extra)
    want = {(normalize_name(b["player"]), b["market"]) for b in rows}
    days = ledger._close_days(H, rows)
    saved = LM.HISTORY_PATH
    LM.HISTORY_PATH = path
    try:
        parts: dict = {}
        snap = ledger._PassSnapshots(want, rows, H, days, parts, today=TODAY)
        recent = snap._read(snap.since)
        lines = ledger._snapshot_closes(want)
        odds = ledger._snapshot_close_odds(want=want)
        sb = closebook.SameBookCloses(H, days=days)
        sb.prepare([dict(r) for r in rows if r["market"] not in ledger.GAME_MARKETS])
        parts["lead_share"] = round(ledger._snapshot_share(snap.since), 2)
    finally:
        LM.HISTORY_PATH = saved
    return snap, recent, lines, odds, sb, parts


def _served_equal(snap, recent, lines, odds, sb):
    """Every close on a day the recent read serves (an open prop's, from its
    first day on) is the whole file's."""
    days = snap.days
    assert days and min(days) == snap.first_day
    for whole, got in ((lines, recent["lines"]), (odds, recent["odds"])):
        ka = {k for k in whole if str(k[2]) in days}
        kb = {k for k in got if str(k[2]) in days}
        assert ka and ka == kb, (ka ^ kb)
        assert all(whole[k] == got[k] for k in ka), [k for k in ka if whole[k] != got[k]]
    st = lambda ix: {k for k in getattr(ix, "stamped", ()) if str(k[2]) in days}     # noqa: E731
    assert st(lines) == st(recent["lines"])
    other = recent["samebook"]["_samebook"]._snap or {}
    mine = {k: v for k, v in (sb._snap or {}).items() if str(k[2]) in days}
    assert mine and mine == {k: v for k, v in other.items() if str(k[2]) in days}


SEASON = _season()
FILE = _file(SEASON)


def test_the_index_is_each_days_first_row_as_parsing_every_line_says():
    held = LM.day_offsets(FILE, budget=None)
    assert held["done"] and held["end"] == held["size"] == FILE.stat().st_size
    assert held["first"] == _truth(FILE) and len(held["first"]) >= DAYS_BACK
    assert LM.day_index_path(FILE).name == "line_history.days.json"


def test_odd_lines_never_hide_a_days_first_row():
    st = _start(_day(3))
    odd = [
        json.dumps({"ts": st - 7200, "player": "Ronald Acuña Jr.", "market": "hits", "book": "FanDuel",
                    "line": 0.5, "over_odds": -150, "under_odds": 120, "start_ts": st}),   # an escape
        json.dumps({"ts": st - 7100, "player": "No Stamp", "market": "hits", "book": "FanDuel",
                    "line": 0.5, "over_odds": -150, "under_odds": 120}),                    # no start
        json.dumps({"ts": st - 7000, "player": "Null Start", "market": "hits", "book": "FanDuel",
                    "line": 0.5, "over_odds": -150, "under_odds": 120, "start_ts": None}),
        json.dumps({"ts": st - 6900, "start_ts": st + 86400 * 2, "player": "Odd Order",
                    "market": "hits", "book": "FanDuel", "line": 0.5}),
        '{"ts": %r, "player": "Half A Li' % (st - 6800),                                # cut short
        "",
        "not json at all",
        json.dumps({"ts": st - 6700, "player": "Tight", "market": "hits"}, separators=(",", ":")),
        json.dumps({"ts": st - 6600, "player": "N", "market": "hits", "extra": {"start_ts": 1.0}}),
        json.dumps({"ts": st - 6500, "player": "Quarter", "market": "hits",
                    "start_ts": _start(_day(4)) - 19 * 3600 - 10 * 60}),                # 00:00:00 ET
    ]
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in sorted(SEASON[:4000], key=lambda r: r["ts"]):
            fh.write(json.dumps(r) + "\n")
        for line in odd:
            fh.write(line + "\n")
        for r in sorted(SEASON[4000:8000], key=lambda r: r["ts"]):
            fh.write(json.dumps(r) + "\n")
    held = LM.day_offsets(p, budget=None)
    truth = _truth(p)
    assert set(truth) <= set(held["first"])
    assert all(held["first"][d] <= o for d, o in truth.items()), \
        {d: (held["first"][d], o) for d, o in truth.items() if held["first"][d] > o}
    # Each odd row that parses is filed under its own `_slate_day`.
    memo: dict = {}
    for line in odd:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and "ts" in r:
            assert LM._line_day(line.encode() + b"\n", memo) == LM._slate_day(r), line


def test_it_picks_up_where_it_stopped_and_waits_for_a_line_being_written():
    rows = sorted(SEASON, key=lambda r: r["ts"])
    cut = len(rows) * 2 // 3
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows[:cut]:
            fh.write(json.dumps(r) + "\n")
    first = LM.day_offsets(p)
    assert first["done"] and first["end"] == p.stat().st_size
    tail = [json.dumps(r) + "\n" for r in rows[cut:]]
    with p.open("a", encoding="utf-8") as fh:
        fh.write("".join(tail[:-1]))
        fh.write(tail[-1][:40])                                    # still being written
    mid = LM.day_offsets(p)
    assert mid["end"] == p.stat().st_size - 40 and mid["done"]
    with p.open("a", encoding="utf-8") as fh:
        fh.write(tail[-1][40:])
    got = LM.day_offsets(p)
    assert got["end"] == p.stat().st_size and got["first"] == _truth(p)
    assert got["first"] == _truth(FILE) == LM.day_offsets(FILE, budget=None)["first"]
    again = LM.day_offsets(p)
    assert again == got, "nothing new: nothing changes"


def test_a_budget_spreads_the_first_build_and_nothing_starts_from_it_until_done():
    p = _file(SEASON)
    size = p.stat().st_size
    step = size // 5 + 1
    seen = []
    for _ in range(10):
        held = LM.day_offsets(p, budget=step)
        seen.append(held["end"])
        if held["done"]:
            break
        assert LM.day_start(_day(2).isoformat(), p, budget=0) is None, "not done: no start"
    assert held["done"] and len(seen) >= 5 and seen == sorted(seen)
    assert held["first"] == _truth(p)
    assert LM.day_start(_day(2).isoformat(), p) is not None


def test_an_index_that_is_not_its_files_any_more_is_built_again():
    p = _file(SEASON[: len(SEASON) // 2])
    LM.day_offsets(p, budget=None)
    ip = LM.day_index_path(p)
    # Another file in its place, as long or longer, read from its own start.
    q = _file(SEASON[len(SEASON) // 4:])
    p.write_bytes(q.read_bytes())
    assert LM.day_offsets(p, budget=None)["first"] == _truth(p)
    # Cut short.
    p.write_bytes(q.read_bytes()[: q.stat().st_size // 3].rsplit(b"\n", 1)[0] + b"\n")
    assert LM.day_offsets(p, budget=None)["first"] == _truth(p)
    # Written over past its head, the same length.
    data = bytearray(p.read_bytes())
    held = json.loads(ip.read_text())
    i = data.rfind(b"\n", 0, held["end"] - 10) + 1
    data[i:i + 4] = b"{\"x\""[:4] if data[i:i + 4] != b"{\"x\"" else b"{\"y\""
    p.write_bytes(bytes(data))
    assert LM.day_offsets(p, budget=None)["end"] == len(data)
    assert json.loads(ip.read_text())["tail"] != held["tail"]
    # A broken or hand-edited index.
    ip.write_text("{ not json")
    assert LM.day_offsets(p, budget=None)["first"] == _truth(p)
    bad = json.loads(ip.read_text())
    bad["first"]["1999-01-01"] = bad["end"] + 5
    ip.write_text(json.dumps(bad))
    assert "1999-01-01" not in LM.day_offsets(p, budget=None)["first"]


def test_the_recent_read_starts_at_the_first_days_first_row_with_the_whole_files_closes():
    snap, recent, lines, odds, sb, parts = _both(FILE)
    assert snap.first_day == _day(2).isoformat() and snap.start is not None
    assert parts["snapshot_share"] < parts["lead_share"] * 0.5, parts
    assert parts["snapshot_indexed"] == 1.0 and parts["snapshot_index"] >= 0.0
    assert "snapshot_unsure" not in parts
    # It starts before the first day's first row by about the lead, no more.
    first_row = LM.day_offsets(FILE)["first"][snap.first_day]
    with FILE.open("rb") as fh:
        fh.seek(snap.start)
        t0 = json.loads(fh.readline())["ts"]
        fh.seek(first_row)
        t1 = json.loads(fh.readline())["ts"]
    # The search lands within 64 KB before the lead's mark: a few pulls.
    assert snap.start <= first_row and LM.DAY_INDEX_LEAD_S <= t1 - t0 <= LM.DAY_INDEX_LEAD_S + 86400, \
        (t1 - t0) / 3600
    _served_equal(snap, recent, lines, odds, sb)


def test_a_day_whose_rows_began_before_the_old_lead_reads_from_the_old_lead():
    """Corbin Carroll's books priced yesterday's game once three weeks
    before it. The lead's own rule says no game is priced that early; the
    read never starts before the lead did, so it stays where it was."""
    st = _start(_day(1))
    early = [{"ts": st - 21 * 86400, "player": "Corbin Carroll", "market": "hits", "book": b,
              "line": 0.5, "over_odds": -140, "under_odds": 115, "start_ts": st} for b in BOOKS]
    p = _file(SEASON + early)
    extra = [(1, "Corbin Carroll", "ARI", "SF", "hits", "OVER")]
    snap, recent, lines, odds, sb, parts = _both(p, extra)
    assert snap.since > st - 21 * 86400, "the lead starts after that read"
    assert snap.start is None and parts["snapshot_indexed"] == 1.0, parts
    assert parts["snapshot_share"] == parts["lead_share"], "the lead's read, no longer"


def test_a_card_priced_weeks_ahead_does_not_pull_the_start_back():
    """A fight card ten days out, priced since three weeks before it: no
    open bet can close on its day, so its early rows do not move where the
    read starts (the first rows of the days the open props close on do)."""
    card = _start(_day(-10))
    early = [{"ts": card - 21 * 86400 + h * 3600, "player": f, "market": "moneyline", "book": b,
              "line": 0.5, "over_odds": -150, "under_odds": 130, "start_ts": card}
             for h in range(0, 400, 12) for f in ("Fighter One", "Fighter Two") for b in BOOKS]
    p = _file(SEASON + early)
    snap, recent, lines, odds, sb, parts = _both(p)
    assert snap.start is not None and _day(-10).isoformat() not in snap.days
    assert parts["snapshot_share"] < parts["lead_share"] * 0.5, parts
    _served_equal(snap, recent, lines, odds, sb)


def test_a_copy_its_reads_cannot_place_reads_again_from_the_old_lead():
    """Yesterday's last pull filed Jake Bell's hits under Josh Bell too.
    Josh Bell's own reads were nine days ago: inside the old lead, before
    the first day's first row. Without them the read cannot place the copy
    as the whole file does, so it reads again from the old lead."""
    st1, st9 = _start(_day(1)), _start(_day(9))
    bells = []
    for h in (20, 10):
        bells += [{"ts": st1 - h * 3600 - 300, "player": "Jake Bell", "market": "hits", "book": b,
                   "line": 0.5, "over_odds": -150, "under_odds": 110, "start_ts": st1} for b in BOOKS[:3]]
        bells += [{"ts": st9 - h * 3600 - 300, "player": "Josh Bell", "market": "hits", "book": b,
                   "line": 0.5, "over_odds": -120, "under_odds": 100, "start_ts": st9} for b in BOOKS[:3]]
    for name in ("Jake Bell", "Josh Bell"):
        bells += [{"ts": st1 - 1800, "player": name, "market": "hits", "book": b, "line": 0.5,
                   "over_odds": -125, "under_odds": 105, "start_ts": st1} for b in BOOKS[:3]]
    p = _file(SEASON + bells)
    extra = [(1, "Jake Bell", "MIA", "ATL", "hits", "OVER")]
    snap, recent, lines, odds, sb, parts = _both(p, extra)
    assert snap.start is not None and parts.get("snapshot_unsure") == 1, parts
    assert parts["snapshot_share"] == parts["lead_share"], "read from the old lead"
    jake = normalize_name("Jake Bell")
    assert (jake, "hits", _day(1).isoformat(), 0.5) in odds
    assert recent["odds"][(jake, "hits", _day(1).isoformat(), 0.5)] == \
        odds[(jake, "hits", _day(1).isoformat(), 0.5)]
    _served_equal(snap, recent, lines, odds, sb)


def test_while_the_index_is_building_the_read_starts_at_the_old_lead():
    p = _file(SEASON)
    saved = LM.DAY_INDEX_BUDGET
    LM.DAY_INDEX_BUDGET = p.stat().st_size // 4
    try:
        snap, recent, lines, odds, sb, parts = _both(p)
    finally:
        LM.DAY_INDEX_BUDGET = saved
    assert snap.start is None and parts["snapshot_indexed"] < 1.0, parts
    assert parts["snapshot_share"] == parts["lead_share"]
    _served_equal(snap, recent, lines, odds, sb)


def test_a_read_given_a_byte_starts_there():
    want = {(normalize_name(p), "hits") for p, _t, _o in PLAYERS}
    held = LM.day_offsets(FILE)
    at = held["first"][_day(5).isoformat()]
    every = list(LM.stream_wanted(want, FILE))
    late = list(LM.stream_wanted(want, FILE, start=at))
    with FILE.open("rb") as fh:
        fh.seek(at)
        t = json.loads(fh.readline())["ts"]
    assert late and late == [r for r in every if r["ts"] >= t]


def test_the_pass_reads_its_start_from_the_index():
    import inspect
    src = inspect.getsource(ledger._PassSnapshots)
    assert "linemoves.day_offsets(budget=linemoves.DAY_INDEX_BUDGET)" in src
    assert "linemoves.day_start(sorted(self.days), index=held)" in src
    assert "self._one_read(since, start)" in src and "self._each_read(since, start)" in src
    assert 'self.parts["snapshot_unsure"]' in src


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
