"""tools/book_keys.py: which books the odds feed really answers for (step JL).

The list is ten since 2026-11-02 (tests/test_ten_books_cost_one_region.py),
and theScore Bet is asked for under two keys until the box shows which one
answers. The tool counts the bookmaker keys in the cached payloads — one
event, a board, or a historical wrapper — over the last few days, names the
books that never answered, and says which theScore key is the live one.

Run directly: `python3 tests/test_book_keys.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import book_keys as BK                                 # noqa: E402

NOW = 1_800_000_000.0


def _event(*keys):
    return {"id": "e", "bookmakers": [{"key": k, "title": k} for k in keys]}


def _write(folder: Path, name: str, payload, age_days: float = 0.0):
    path = folder / name
    path.write_text(json.dumps(payload))
    t = NOW - age_days * 86400
    os.utime(path, (t, t))


def test_it_counts_every_payload_shape_and_only_recent_ones():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        _write(folder, "odds_event_nba_1_a.json", _event("draftkings", "espnbet", "pinnacle"))
        _write(folder, "odds_board_nfl.json", [_event("draftkings", "fanduel"), _event("espnbet")])
        _write(folder, "odds_hist_event_nfl_2_b.json", {"timestamp": "x", "data": _event("betmgm")})
        _write(folder, "odds_event_nba_3_c.json", _event("fliff"), age_days=9)      # too old
        (folder / "odds_event_nba_4_d.json").write_text("{not json")                # broken: skipped
        _write(folder, "scores_nba.json", _event("draftkings"))                     # not an odds file
        files, seen = BK.count(folder, days=3, now=NOW)
    assert files == 3
    assert seen == {"draftkings": 2, "espnbet": 2, "pinnacle": 1, "fanduel": 1, "betmgm": 1}


def test_the_report_names_the_silent_books_and_the_live_thescore_key():
    asked = ["draftkings", "fanduel", "espnbet", "thescorebet", "pinnacle"]
    lines = BK.report(4, BK.collections.Counter({"draftkings": 9, "espnbet": 5, "pinnacle": 7,
                                                 "fliff": 1}), asked=asked)
    text = "\n".join(lines)
    assert lines[0] == "Asked for (5): draftkings, fanduel, espnbet, thescorebet, pinnacle"
    assert "fliff" in text and "(not asked for now)" in text
    assert "Never answered: fanduel, thescorebet" in text
    assert ("theScore Bet: espnbet 5, thescorebet 0 — it answers to espnbet; "
            "thescorebet can give its slot to another book.") in text


def test_nothing_cached_says_so_rather_than_printing_an_empty_table():
    lines = BK.report(0, BK.collections.Counter(), asked=["draftkings"])
    assert lines[-1] == "No odds payloads cached in the last 3 days to count."


def test_the_runbook_and_the_catchup_run_it():
    line = "cd /srv/qellys && sudo -u qellys python3 tools/book_keys.py"
    assert line in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert line in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    assert "catchup.sh JL" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
