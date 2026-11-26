"""The record says what an ordinary game does, beside our reads' record (step AIB, 26 November 2026).

Our record read "breakout candidates beat their average 56 of 108 times (52%)" under Bears at Lions' Players to
watch, which reads as a coin flip. It is not one. The stats a read is graded on (catches, rushing yards, passing
yards) are skewed, so a player's average sits above most of the player's games. Measured the way reportgrade grades
a read: the read's first stat against the player's previous games, at most 10, at least 2. The data was nflverse
weekly stats for every key player in the 2017-2025 regular seasons, 25,403 games. The player beat that average in
42.2% of them and fell short in 56.6%, and every season sat between 40% and 44%. So 52% is ten points over an
ordinary game, and the fades' 68% eleven. What holds:

  * the football record line says the ordinary game beside ours, with the seasons it was measured on;
  * a league not measured says nothing of the kind;
  * the measured numbers are pinned here, so a change to them is a change someone made on purpose.

Offline. Run directly: `python3 tests/test_the_record_says_an_ordinary_game.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import reportrecord as RR                                # noqa: E402

TOTALS = {"games": 28, "since": "2026-11-12", "groups": {"candidates": (56, 108), "fades": (30, 44)}}


def test_the_football_record_says_an_ordinary_game_beside_ours():
    line = RR.track_lines(TOTALS, "nfl")["watch"]
    assert line == ("Our record so far: breakout candidates beat their average 56 of 108 times (52%) and fades fell "
                    "short of it 30 of 44 times (68%), on 28 finished NFL games since Nov 12. For comparison, a key "
                    "player in an ordinary game beats that average 42% of the time and falls short of it 57% "
                    "(measured over the 2017–2025 seasons)."), line


def test_a_league_not_measured_says_nothing_of_the_kind():
    for sport in ("nba", "cfb", "nhl", "mlb", "cbb", "wnba"):
        line = RR.track_lines(TOTALS, sport)["watch"]
        assert "ordinary game" not in line, (sport, line)
        assert RR.base_words(sport) == ""


def test_the_measured_numbers_are_pinned():
    assert RR.BASE_RATES == {"nfl": {"over": 0.422, "under": 0.566, "seasons": "2017–2025"}}
    src = (ROOT / "engine" / "reportrecord.py").read_text(encoding="utf-8")
    assert "25,403 games" in src and "42.2%" in src and "56.6%" in src, "the measurement is said where it is used"


def test_the_record_page_says_it_too():
    """The Report Picks page's "How our reports did" draws the record's ``base`` under the kinds (reportpicks.js
    rpTotalsHTML); with no base (a league not measured), nothing."""
    import test_the_injury_tally_counts_who_it_listed as IT
    from engine import reportrecord as RRm
    base = {"words": RRm.base_words("nfl"), **RRm.BASE_RATES["nfl"]}
    import json as _json
    got = IT._node(IT._harness() + f"""
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const t = {{games: 28, groups: {{candidates: [56, 108], fades: [30, 44]}}}};
      const withBase = rpTotalsHTML(t, {_json.dumps(base)});
      const without = rpTotalsHTML(t);
      const line = (h) => {{ const m = h.match(/rpk-fact-base">([\\s\\S]*?)<\\/p>/); return m ? text(m[1]) : null; }};
      console.log(JSON.stringify({{withBase: line(withBase), without: line(without)}}));""")
    if got is None:
        return
    assert got["withBase"] == ("For comparison, a key player in an ordinary game beats that average 42% of the time "
                               "and falls short of it 57% (measured over the 2017–2025 seasons): a breakout candidate "
                               "or a good spot is right when it beats it, a fade when it falls short."), got
    assert got["without"] is None, got


def test_the_record_api_carries_it_for_football_only():
    src = (ROOT / "engine" / "reportrecord.py").read_text(encoding="utf-8")
    assert 'out["base"] = {"words": base_words(sport), **BASE_RATES[sport]}' in src


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
