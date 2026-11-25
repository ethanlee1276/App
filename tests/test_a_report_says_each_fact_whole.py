"""A report says each fact whole, the same way everywhere it says it (25 November 2026).

Read off a full NFL report (the Patriots at the Bears, Ethan's game) the way a reader meets it:

  * the case for a side named three of the Bears' four starters out, beside a short version and an injury list
    that named the fourth; a case names three and counts the rest ("and one more");
  * one meeting read "NE has won 1 of the last 1 meeting; against the spread NE is 1-0; 0 went over the total
    and 1 under"; one meeting is said as one;
  * the copied text of a player with no verdict word read "D'Andre Swift =  — 55% of the carries"; the "=" goes
    with the word.

Offline. Run directly: `python3 tests/test_a_report_says_each_fact_whole.py`
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402

_spec = importlib.util.spec_from_file_location("short", ROOT / "tests" / "test_the_short_version_reads_as_sentences.py")
SHORT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHORT)


def _sec(rep, key):
    return next(s for s in rep["sections"] if s["key"] == key)


def test_a_case_names_three_out_and_counts_the_rest():
    rep = SHORT._chi_ne()
    items = [i for b in _sec(rep, "verdict")["blocks"] if b.get("type") == "list" for i in b["items"]]
    line = next(i for i in items if i.startswith("The Bears are without"))
    assert line == ("The Bears are without T.J. Edwards (LB), out, Kyle Monangai (RB), out, Dayo Odeyingbo (DE), "
                    "out and one more."), line
    assert any(i == "The Patriots are without Carlton Davis III (CB), out." for i in items), "one: no count"
    assert R._more_out(3) == [] and R._more_out(4) == ["one more"] and R._more_out(9) == ["6 more"]


def test_one_meeting_is_said_as_one():
    rep = SHORT._chi_ne()
    head = _sec(rep, "meetings")["blocks"][0]["text"]
    assert head == "NE won the last meeting; NE covered; it went under the total.", head
    g = {"away": "NE", "home": "CHI", "spread": -3.0, "total": 50.5}
    two = [{"season": 2024, "week": 10, "day": "2024-11-10", "home": "CHI", "away": "NE", "hs": 3, "as": 19,
            "winner": "NE", "spread_home": -6.5, "total": 37.5, "covered": "NE", "ou": "under"},
           {"season": 2022, "week": 7, "day": "2022-10-24", "home": "CHI", "away": "NE", "hs": 33, "as": 14,
            "winner": "CHI", "spread_home": 8.5, "total": 40.5, "covered": "CHI", "ou": "over"}]
    c = R.Ctx(g, {"games": [g]}, names={"NE": "Patriots", "CHI": "Bears"}, meetings=two)
    head2 = R.sec_meetings(c)["blocks"][0]["text"]
    assert head2.startswith("The last 2 meetings are split 1-1; against the spread"), head2
    assert "1 went over the total and 1 under" in head2


def test_a_player_with_no_verdict_word_is_copied_without_the_sign():
    text = R.to_text(SHORT._chi_ne())
    assert "=  —" not in text and " = —" not in text
    assert "  • D'Andre Swift — 55% of the carries (15 a game)" in text
    assert "  • A.J. Brown vs CHI's coverage = FAVORABLE — 27% of the targets (8.4 a game)" in text, "a word stays"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
