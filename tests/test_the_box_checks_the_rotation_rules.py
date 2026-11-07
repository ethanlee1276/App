"""`nbarules.py` asks the box's own seasons whether the rotation's rules hold
(runbook JZ; engine/nba/minutes, docs/NBA_LAB.md "The scout").

The rules were measured in the lab on the league's public box scores; this
read-only check replays every stored season through the board's own
projection at the values the board runs, each rule taken out in turn, each
side on its own level factor. THE BAR, written before the first box run:
every season with 100+ games a rule touches, minutes AND points better with
the rule. It changes nothing; QB_NBA_ROTATION=0 is the switch if it fails.

Run directly: `python3 tests/test_the_box_checks_the_rotation_rules.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nbarules                                   # noqa: E402
from engine.hoops import NBA                      # noqa: E402


def _club():
    """One club, 30 games: A plays every game (30 min), B misses games 18-20
    and comes back, C's minutes jump from 16 to 30 at game 22."""
    games = {}
    for i in range(30):
        d = f"2026-{11 + i // 28:02d}-{1 + i % 28:02d}"
        g = {"A": {"min": 30.0, "pts": 15.0, "starter": True}}
        if not 17 <= i <= 19:
            g["B"] = {"min": 32.0 if i != 20 else 27.0, "pts": 18.0, "starter": True}
        g["C"] = {"min": 16.0 if i < 22 else 30.0, "pts": 8.0 if i < 22 else 15.0, "starter": i >= 22}
        g["D"] = {"min": 20.0, "pts": 9.0, "starter": False}
        games[d] = g
    return {(2027, "BOS"): games}


def test_each_rule_finds_the_games_it_touches():
    rows = nbarules.cases(_club(), NBA, 0.0)
    by = {}
    for r in rows:
        for t in r["touched"]:
            by.setdefault(t, set()).add(r["prop"]["player"])
    assert by.get("first game back") == {"B"}, by
    assert by.get("second game back") == {"B"}, by
    assert "C" in by.get("role jump", set()), by
    assert by.get("a regular's return") == {"A", "C", "D"}, "every teammate gives some back, never B himself"
    back = [r for r in rows if "first game back" in r["touched"]][0]
    assert back["prop"]["missed_games"] == 3 and back["prop"]["return_minutes"] == 0.0


def test_the_measurement_and_the_bar():
    res = nbarules.measure(nbarules.cases(_club(), NBA, 0.0), NBA)
    assert set(res) == {2027} and res[2027]["n"] > 0
    for rule in nbarules.RULES:
        assert "minutes" in res[2027][rule] and "points" in res[2027][rule]
    fine = {2025: {"n": 900, **{r: {"n": 150, "minutes": 0.02, "points": 0.01} for r in nbarules.RULES}}}
    assert nbarules.verdict(fine) == (True, [])
    bad = {2025: {"n": 900, **{r: {"n": 150, "minutes": 0.02, "points": 0.01} for r in nbarules.RULES}}}
    bad[2025]["role jump"] = {"n": 150, "minutes": 0.03, "points": -0.002}
    ok, why = nbarules.verdict(bad)
    assert not ok and "role jump in 2025" in why[0]
    thin = {2025: {"n": 50, **{r: {"n": 20, "minutes": -0.5, "points": -0.5} for r in nbarules.RULES}}}
    assert nbarules.verdict(thin)[0] is False, "nothing judged is not a pass"
    text = "\n".join(nbarules.report(fine, 0.0))
    assert "HOLDS — the board keeps all three." in text
    text = "\n".join(nbarules.report(bad, 0.3))
    assert "DOES NOT HOLD" in text and "QB_NBA_ROTATION=0" in text


def test_it_is_read_only_and_measures_with_the_rules_on():
    src = (ROOT / "nbarules.py").read_text()
    assert "mode=ro" in src and ".save(" not in src
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "open("):
        assert verb not in src, verb
    assert 'os.environ["QB_NBA_ROTATION"] = "1"' in src, "the run that decides the switch measures the rules"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
