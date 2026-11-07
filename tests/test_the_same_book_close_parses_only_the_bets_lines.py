"""The same-book close parses only the snapshot lines a bet in hand names
(engine/closebook.SameBookCloses.prepare, engine/linemoves.stream_wanted).

The settle pass's grading took 346 seconds of a 493-second pass on Saturday
7 November. One of its reads was this one: on every pass that graded a prop
it streamed the whole snapshot file through `stream_history`, which parses
every line of every sport's every pull, and kept the handful for the bets
in hand. The settle's own two snapshot readers had moved to `stream_wanted`
(a line's market and player read off its text first) on 15 October; this
one had not. What these hold:

  * prepared from the file, the closes are exactly what the whole parsed
    file gives, the recorded starts too;
  * only lines whose text names a wanted player and market are parsed (a
    wanted man's other lines, at another number, included: the line is
    judged after the parse, as before);
  * with no bet in hand, nothing is parsed.

Run directly: `python3 tests/test_the_same_book_close_parses_only_the_bets_lines.py`
"""
import datetime as dt
import json
import sys
import tempfile
import types
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import linemoves                                       # noqa: E402
from engine.closebook import SameBookCloses                        # noqa: E402

START = dt.datetime(2026, 11, 7, 19, 5, tzinfo=ZoneInfo("America/New_York")).timestamp()
DAY = "2026-11-07"


def _row(player, market, line, book, over, under, ago_min, start=START):
    return {"ts": start - ago_min * 60, "player": player, "market": market, "book": book,
            "line": line, "over_odds": over, "under_odds": under, "start_ts": start}


ROWS = [
    # The bet's own lines: two books, two pulls each, then one in play.
    _row("Jalen Brunson", "points", 26.5, "fanduel", -115, -105, 120),
    _row("Jalen Brunson", "points", 26.5, "draftkings", -110, -110, 120),
    _row("Jalen Brunson", "points", 26.5, "fanduel", -125, 105, 15),
    _row("Jalen Brunson", "points", 26.5, "draftkings", -120, 100, 10),
    _row("Jalen Brunson", "points", 26.5, "fanduel", -300, 240, -30),
    # The same man at another number: parsed, then left out by its line.
    _row("Jalen Brunson", "points", 27.5, "fanduel", 105, -125, 15),
    # Nobody's bet: another player, and the bettor's other market.
    _row("Josh Hart", "points", 10.5, "fanduel", -110, -110, 15),
    _row("Josh Hart", "rebounds", 9.5, "fanduel", -110, -110, 15),
    _row("Jalen Brunson", "assists", 7.5, "draftkings", -115, -105, 15),
]
BET = {"sport": "nba", "date": DAY, "player": "Jalen Brunson", "market": "points",
       "line": 26.5, "side": "OVER", "book": "FanDuel"}


class _Counting:
    """`json` for linemoves, counting the lines it parses."""
    def __init__(self):
        self.parsed = 0
        self.JSONDecodeError = json.JSONDecodeError
        self.dumps = json.dumps

    def loads(self, raw):
        self.parsed += 1
        return json.loads(raw)


def _with_file(fn):
    saved_path, saved_json = linemoves.HISTORY_PATH, linemoves.json
    counting = _Counting()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "line_history.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in ROWS), encoding="utf-8")
        linemoves.HISTORY_PATH = path
        try:
            whole = SameBookCloses(None, snapshots=list(linemoves.stream_history(path)))
            whole.prepare([BET])
            linemoves.json = counting
            return fn(whole, counting)
        finally:
            linemoves.HISTORY_PATH, linemoves.json = saved_path, saved_json


def test_the_closes_are_the_whole_files_and_only_the_bets_lines_are_parsed():
    def check(whole, counting):
        sb = SameBookCloses(None)
        sb.prepare([BET])
        assert sb._snap == whole._snap and sb._snap
        assert sb._stamped_keys == whole._stamped_keys == {("jalen brunson", "points", DAY)}
        assert counting.parsed == 6, counting.parsed      # Brunson's six points lines
        # The posted book's last pre-game price, not the in-play one.
        assert sb.close_for(dict(BET), [DAY]) == whole.close_for(dict(BET), [DAY]) == -125
        under = dict(BET, side="UNDER", book="DraftKings")
        assert sb.close_for(under, [DAY]) == 100
    _with_file(check)


def test_with_no_bet_in_hand_nothing_is_parsed():
    def check(whole, counting):
        sb = SameBookCloses(None)
        sb.prepare([{"player": "Jalen Brunson", "market": "points", "line": None}])
        assert counting.parsed == 0 and sb._snap == {}
    _with_file(check)


def test_the_settle_hands_it_no_rows_so_it_reads_the_file():
    import inspect
    from engine import ledger
    src = inspect.getsource(ledger._same_book_close)
    assert "SameBookCloses(hist_conn" in src and "snapshots=" not in src, \
        "the settle's reader streams the file itself"
    assert "stream_history()" not in inspect.getsource(SameBookCloses.prepare)


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
