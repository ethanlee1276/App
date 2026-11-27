"""No pick is certain, on any path onto the boards (step AIC, 27 November 2026).

The Record page's week read "Toughest miss: Jake Elliott under 10.5 Kicking Points (−170) at 100%". The one board
had journaled that pick at 99.9%, against a price that says about 63%. engine/boldcheck has refused a number that
high since 18 November (CERTAIN; Emmett Johnson's carries went up at 100%). That check only runs inside the bold
check, though, and the bold check runs only where the book's de-vigged chance is known. A row without one was asked
nothing, and the shared bar (likely._credible) answers "credible" when there is no fair number to compare with.
What holds:

  * the Most Likely list's one bar (likely.admissible) refuses a chance at or above CERTAIN, whatever built it;
  * the one board holds such a row back with the reason (likelyboard.held_reason), never posts it;
  * a posted (locked) pick keeps its seat, as every posted pick does;
  * an ordinary chance passes both.

Offline. Run directly: `python3 tests/test_no_pick_is_certain_on_any_path.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import boldcheck, likely, likelyboard                    # noqa: E402


def _row(p, **kw):
    r = {"kind": "prop", "player": "Jake Elliott", "team": "PHI", "market": "kick_pts", "side": "UNDER",
         "line": 10.5, "odds": -170, "book": "DraftKings", "model_prob": p, "implied_prob": None}
    r.update(kw)
    return r


def test_the_list_refuses_a_certain_chance_whatever_built_it():
    assert boldcheck.CERTAIN == 0.99
    assert likely.admissible(_row(0.999)) == "a chance this near certain is a data problem, not a pick"
    assert likely.admissible(_row(0.99)) == "a chance this near certain is a data problem, not a pick"
    assert likely.admissible(_row(0.70)) == "", "an ordinary chance with no fair number to compare still passes"


def test_the_board_holds_it_back_and_says_why():
    why = likelyboard.held_reason(_row(0.999), {"matchup": None})
    assert why == ("held back: our number says 99.9%, and no prop is that certain — a spread that narrow is the "
                   "model's arithmetic, not a find"), why
    assert likelyboard.held_reason(_row(0.72), {"matchup": None}) is None
    assert likelyboard.held_reason(_row(0.999, locked=True), {"matchup": None}) is None, "a posted pick stays"
    assert likelyboard.certain_reason(None) is None and likelyboard.certain_reason("x") is None


def test_the_weeks_toughest_miss_says_the_number_we_gave():
    """The week's card rounded 0.999 to "100%", a number we never gave; a claim near certain is said to its tenth."""
    src = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert ('const pc = (v) => v == null ? "—" : v > 0.995 && v < 1 ? `${(v * 100).toFixed(1)}%` : '
            '`${Math.round(v * 100)}%`;') in src


def test_a_finished_games_script_is_said_in_words_on_the_record():
    """"Simulation right · Script C" meant nothing off the report; the chip says the script's words too."""
    import json
    import test_the_injury_tally_counts_who_it_listed as IT
    rp = IT.RP
    i = rp.index("const RP_SCRIPT = ")
    script = rp[i:rp.index("};\n", i) + 3]
    got = IT._node(IT._harness() + "\n" + script + """
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const row = {date: "2026-11-26", away: "CHI", home: "DET", final: {away: 39, home: 35}, sim: "right", script: "C"};
      const none = {date: "2026-11-26", away: "CHI", home: "DET", final: {away: 39, home: 35}, sim: "wrong"};
      console.log(JSON.stringify({c: text(rpFactRowHTML(row)), none: text(rpFactRowHTML(none))}));""")
    if got is None:
        return
    assert "Simulation right · Script C: the favorite by 1 to 7" in got["c"], got["c"]
    assert "Simulation wrong" in got["none"] and "Script" not in got["none"], got["none"]
    from engine import reportfacts as F
    for k, words in F.SCRIPT_SAID.items():
        assert f'{k}: "{words}"' in script, (k, script)


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
