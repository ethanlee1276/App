"""The settle pass parses only the snapshot lines its open bets ask about.

Found 2026-10-15 in Ethan's BL paste: the box's settle step took 502 of a
cycle's 504 seconds with a second settle running beside it, and every board
build (each settles at its end) ran out its 600 seconds, the NFL's ten
times in seven hours on a game day. One settle pass reads the odds snapshot
file (millions of lines) up to three times and parsed every line each time,
keeping only the open bets' players afterwards. `linemoves.stream_wanted`
reads a line's market and player off its text first and parses only the
lines a bet wants; anything not in the plain shape is parsed, so nothing
wanted is lost, and the old filter still runs on what comes back.

Run directly: `python3 tests/test_settling_reads_only_the_lines_it_needs.py`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, linemoves                             # noqa: E402
from engine.sources.oddsapi import normalize_name                # noqa: E402

T0 = 1790000000.0


def _row(player, market, line=64.5, over=-115, under=-105, ts=T0, book="DraftKings", **kw):
    return {"ts": ts, "player": player, "market": market, "book": book, "line": line,
            "over_odds": over, "under_odds": under, **kw}


def _file(compact=()):
    """A snapshot file in the shapes the box holds, and a few it shouldn't."""
    rows = [_row("Amon-Ra St. Brown", "rec_yds"), _row("Amon-Ra St. Brown", "receptions", line=6.5),
            _row("Ronald Acuña Jr.", "hits", line=0.5, over=-200, under=160),
            _row("Josh Allen", "pass_yds", line=255.5), _row("Somebody Else", "rec_yds"),
            _row("Amon-Ra St. Brown", "rec_yds", ts=T0 + 3600, over=-125, under=105, start_ts=T0 + 7200),
            _row("Bo Nix", "rush_att", line=4.5, book="FanDuel")]
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            fh.write((json.dumps(r, separators=(",", ":")) if i in compact else json.dumps(r)) + "\n")
        fh.write("\n")                                 # a blank line
        fh.write('{"ts": 1, "player": "Bo Nix", "market": "rush_att", "li\n')   # a torn last write
        fh.write(json.dumps(_row("Bo Nix", "rush_att", line=5.5)) + "\n")
    return p


WANT = {(normalize_name("Amon-Ra St. Brown"), "rec_yds"), (normalize_name("Ronald Acuna"), "hits"),
        (normalize_name("Bo Nix"), "rush_att")}


def test_the_filtered_read_gives_exactly_the_old_answer():
    for compact in ((), (0, 2, 5)):
        p = _file(compact)
        old = list(ledger._wanted_rows(linemoves.stream_history(p), WANT))
        new = list(ledger._wanted_rows(linemoves.stream_wanted(WANT, p), WANT))
        assert new == old, (compact, new, old)
        assert {(normalize_name(r["player"]), r["market"]) for r in new} == WANT


def test_it_parses_only_the_lines_a_bet_wants():
    p = _file()
    seen = []
    real = linemoves.json.loads

    class _Counting:
        JSONDecodeError = json.JSONDecodeError

        @staticmethod
        def loads(s):
            seen.append(s)
            return real(s)

    linemoves.json = _Counting
    try:
        got = list(linemoves.stream_wanted(WANT, p))
    finally:
        linemoves.json = json
    # Five wanted rows, the torn line (its player is read, then it fails to
    # parse) and nothing else: Josh Allen, "Somebody Else" and St. Brown's
    # receptions are told apart without being parsed.
    assert len(got) == 5, got
    assert len(seen) == 6, seen
    assert not any("Josh Allen" in s or "Somebody Else" in s or '"receptions"' in s for s in seen)


def test_an_escaped_or_compact_line_is_parsed_rather_than_skipped():
    """A name `json.dumps` escaped, or a line in another separator style,
    cannot be judged from its text, so it is parsed and judged as a row."""
    p = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_row("Ronald Acuña Jr.", "hits", line=0.5)) + "\n")
        fh.write(json.dumps(_row("Bo Nix", "rush_att"), separators=(",", ":")) + "\n")
        fh.write(json.dumps(_row("Bo Nix", "rec_yds")) + "\n")
    assert "\\u00f1" in p.read_text()
    # The text check judges market and player apart (Bo Nix's receiving
    # yards passes it: both are wanted, though not together); the pair is
    # judged by `_wanted_rows` after, as it always was.
    got = [(r["player"], r["market"]) for r in ledger._wanted_rows(linemoves.stream_wanted(WANT, p), WANT)]
    assert got == [("Ronald Acuña Jr.", "hits"), ("Bo Nix", "rush_att")], got


def test_the_settle_readers_answer_as_before():
    p = _file((2,))
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = p
    try:
        odds = ledger._snapshot_close_odds(want=WANT)
        lines = ledger._snapshot_closes(WANT)
        every = ledger._snapshot_close_odds()
    finally:
        linemoves.HISTORY_PATH = saved
    assert dict(odds) == dict(linemoves.closing_odds_by_date(ledger._wanted_rows(linemoves.stream_history(p), WANT)))
    assert dict(lines) == dict(linemoves.closing_lines_by_date(ledger._wanted_rows(linemoves.stream_history(p), WANT)))
    assert dict(every) == dict(linemoves.closing_odds_by_date(linemoves.stream_history(p)))
    assert any(k[0] == normalize_name("Ronald Acuna") for k in odds), odds


def test_no_want_still_reads_everything_and_a_missing_file_reads_nothing():
    p = _file()
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = p
    try:
        assert len(list(ledger._snapshot_stream(None))) == 8
    finally:
        linemoves.HISTORY_PATH = saved
    assert list(linemoves.stream_wanted(WANT, Path(tempfile.mkdtemp()) / "none.jsonl")) == []
    import inspect
    assert inspect.isgeneratorfunction(linemoves.stream_wanted)
    assert len(list(linemoves.stream_history(p))) == 8


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
