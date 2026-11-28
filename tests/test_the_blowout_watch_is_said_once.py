"""The blowout watch is said once, in the short version, and still graded (step AII, 27 November 2026).

A basketball report with a spread of 10 or more said "Blowout watch: with a spread of 10 or more, the starters'
minutes are the first thing a coach takes back if it turns lopsided" twice, word for word: in the short version and
again in the game facts five lines below. It is the short version's to say (a caution, not a fact of the game), so
it is said there once, and the claim a finished game checks it by (the final margin, engine/reportgrade) rides with
it there.

    python3 tests/test_the_blowout_watch_is_said_once.py
"""
import io
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R                                   # noqa: E402


def _report():
    import test_every_league_gets_a_game_report as LT
    with contextlib.redirect_stdout(io.StringIO()):
        board, meta = LT._nba_board()
        rep, _line = LT._attach(board, "nba", meta=meta)
    return rep


def _sec(rep, key):
    return next((s for s in rep["sections"] if s["key"] == key), None)


def test_said_once_in_the_short_version_with_its_claim():
    rep = _report()
    text = R.to_text(rep)
    assert text.count("Blowout watch") == 1, text
    short = [b for b in _sec(rep, "short")["blocks"] if b.get("type") == "list"][0]
    i = next(i for i, t in enumerate(short["items"]) if t.startswith("Blowout watch"))
    assert short.get("claims") and short["claims"][i] == {"kind": "blowout"}, short
    assert len(short["claims"]) == len(short["items"]), "a line and its claim stay in step"
    facts = _sec(rep, "facts")
    assert not any("Blowout watch" in t for b in facts["blocks"] for t in b.get("items") or []), facts
    assert not any((cl or {}).get("kind") == "blowout" for b in facts["blocks"] for cl in b.get("claims") or [])


def test_a_finished_game_still_grades_it():
    from engine import reportgrade as G
    rep = _report()
    lists = list(G._claim_lists(rep))
    assert any((cl or {}).get("kind") == "blowout" for _k, b in lists for cl in b.get("claims") or []), lists


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
