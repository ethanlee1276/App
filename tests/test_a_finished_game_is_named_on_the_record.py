"""A finished game on How our reports did is named, not coded (2026-11-17).

Live on 17 November, How our reports did read "espn:2145 63 at DEN 101" for
Colorado-Colorado Springs at Denver: a report that called no winner (a college
game nothing was priced on) leaves each side's code as its name in its row
(engine/reportrecord.row_of), and the page only fell back to its own names
when a row had none at all. What these hold:

  - the record (and Ask's single game) fills a side whose name is its code
    from the league's kept names: college basketball's school cards, as its
    reports say a school ("Denver"), and the pro leagues' nicknames;
  - a row's real names are left as they are;
  - and the page treats a name that is its code as no name.

    python3 tests/test_a_finished_game_is_named_on_the_record.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import reportrecord as RR                                         # noqa: E402

PAGE = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")


def test_a_coded_side_takes_the_leagues_name_and_a_named_one_keeps_its_own():
    keep = RR.league_names
    RR.league_names = lambda sport: {"DEN": "Denver", "espn:2145": "UC Col Springs", "MINN": "Gophers"} if sport == "cbb" else {}
    try:
        rows = [{"away": "espn:2145", "home": "DEN", "names": {"espn:2145": "espn:2145", "DEN": "DEN"}},
                {"away": "WIU", "home": "MINN", "names": {"WIU": "Western Illinois", "MINN": "Minnesota"}},
                {"away": "XYZ", "home": "DEN"}]
        got = RR.named("cbb", rows)
    finally:
        RR.league_names = keep
    assert got[0]["names"] == {"espn:2145": "UC Col Springs", "DEN": "Denver"}, got[0]
    assert got[1]["names"] == {"WIU": "Western Illinois", "MINN": "Minnesota"}, "a report's own names stay"
    assert got[2]["names"] == {"DEN": "Denver"}, "a code the league keeps no name for stays a code"


def test_the_league_tables_are_colleges_cards_and_the_pros_nicknames():
    src = (ROOT / "engine" / "reportrecord.py").read_text(encoding="utf-8")
    fn = src[src.index("def league_names("):src.index("def named(")]
    assert 'c.get("short") or c.get("loc") or c.get("name")' in fn and "cbbteams.cards()" in fn
    assert "from .leaguereport import team_names" in fn
    rec = src[src.index("def record("):src.index("def _day(")]
    assert '"games": named(sport, every[:CARD_ROWS])' in rec
    ask = (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")
    assert "row = reportrecord.named(league, [row])[0]" in ask, "Ask's single game names its sides the same way"


def test_the_page_takes_a_code_for_no_name():
    assert "const nm = (t) => { const n = (r.names || {})[t]; return n && n !== t ? n : teamName(t); };" in PAGE


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
