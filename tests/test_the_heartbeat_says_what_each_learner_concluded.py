"""The heartbeat says what each learner concluded, league by league
(engine/maintenance, 2026-11-14).

Ethan, 2026-11-14: "make sure all of our calibrations are working and all
of the learning is working and hypothesis is working and all that stuff for
every single sport". The learning pass's seconds were on the public
heartbeat (`chores` -> `settle` -> `phases` -> `last_learned` -> `parts`),
what each learner concluded only in the box's own log. So the audit could
see that a learner ran, never whether it learned anything for a league.

Each learner's verdict now rides with the pass, under `last_learned` ->
`verdicts`: the loss patterns' slices closed by league, the journal's
temperatures fitted, owned and still collecting by league, the selection
haircut's settled picks and whether each league's own fit is applied, the
game-line calibrations adopted, the correlations adopted, and the
hypothesis lab's claims by standing. Counts and keys only: no fitted
number leaves the box.

    python3 tests/test_the_heartbeat_says_what_each_learner_concluded.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import maintenance as M                  # noqa: E402


def test_each_learners_verdict_by_league():
    lp = {"n_records": 9100, "tested": 312,
          "closed": [{"sport": "nfl", "action": "close"}, {"sport": "nfl"}, {"sport": "mlb"}, {}]}
    assert M.verdict_losspatterns(lp) == {"records": 9100, "tested": 312,
                                          "closed": {"all": 1, "mlb": 1, "nfl": 2}}
    jf = {"temperatures": {"fitted": [{"key": "nba:pts", "temperature": 0.91}],
                           "refitted": [{"key": "nba:reb"}], "owned": [{"key": "nfl:pass_yds"}],
                           "collecting": [{"key": "nhl:sog", "n": 143, "need": 200}, {"key": "cbb:pts"}]},
          "memory": {"fitted": [{"key": "nba:pts", "adopted": True}, {"key": "nba:ast", "adopted": False}]}}
    assert M.verdict_journal(jf) == {"cbb": {"collecting": 1}, "nba": {"fitted": 2, "memory": 1},
                                     "nfl": {"owned": 1}, "nhl": {"collecting": 1}}
    sf = {"pooled": {"n": 4100, "applied": True, "shift": -0.14},
          "sports": {"nba": {"n": 227, "applied": False, "shift": -0.3}, "nfl": {"n": 1900, "applied": True}}}
    said = M.verdict_selection(sf)
    assert said == {"pooled": {"n": 4100, "applied": True}, "nba": {"n": 227, "applied": False},
                    "nfl": {"n": 1900, "applied": True}}
    assert "shift" not in json.dumps(said), "the fitted number stays on the box"
    hs = {"hypotheses": [{"sport": "nfl", "action": "close"}, {"sport": "nfl", "action": "watch"},
                         {"sport": "mlb", "action": "watch"}, {"action": None}]}
    assert M.verdict_hypotheses(hs) == {"all": {"none": 1}, "mlb": {"watch": 1},
                                        "nfl": {"close": 1, "watch": 1}}
    assert M.verdict_losspatterns({}) == {"records": None, "tested": None, "closed": {}}
    assert M.verdict_journal({}) == {} and M.verdict_hypotheses({}) == {}


def test_the_game_line_calibration_says_why_it_held_each_fit():
    """The heartbeat named the adopted fits only, so basketball's and
    hockey's game lines, which the calibration has no model for (0.0
    seconds a fit on 14 November), read as a learner that had stopped."""
    gc = {"adopted": [{"key": "nfl:spread", "shrink": 0.03}],
          "held": [{"key": "nba:spread", "why": "no scoring baseline registered for 'nba'"},
                   {"key": "nba:moneyline", "why": "no win-probability curve registered for 'nba'"},
                   {"key": "cbb:total", "why": "212 games, needs 400"},
                   {"key": "wnba:total", "why": "0 graded games with a close"},
                   {"key": "cfb:moneyline", "why": "slope ±0.311 is looser than the ±0.25 needed to act on"},
                   {"key": "x:y", "why": "unusable fit"}]}
    said = M.verdict_gamecal_held(gc)
    assert said == {"held": {"no game-line model of its own here": ["nba:moneyline", "nba:spread"],
                             "too few graded games": ["cbb:total", "wnba:total"],
                             "too loose to act on": ["cfb:moneyline"],
                             "unusable fit": ["x:y"]}}, said
    assert "0.311" not in json.dumps(said) and "212" not in json.dumps(said), "keys only"
    assert M.verdict_gamecal_held({"adopted": [], "held": []}) == {}
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert 'verdicts["game lines"].update(verdict_gamecal_held(gc))' in src


def test_the_verdicts_are_kept_with_the_last_pass_that_learned():
    state = {}
    phases = {"learn": 356.4, "learn_parts": {"gamecal.refresh": 173.5},
              "learn_verdicts": {"note": M._learn_verdicts_note(),
                                 "selection haircut": {"nba": {"n": 227, "applied": True}}}}
    M._keep_last_parts(state, phases, 1794666044.0)
    kept = state["last_learned"]
    assert kept["verdicts"]["selection haircut"]["nba"] == {"n": 227, "applied": True}
    assert phases["last_learned"]["verdicts"] == kept["verdicts"], "on the pass's phases, so the heartbeat"
    # A quiet pass keeps the last one that learned.
    quiet = {"graded": 0}
    M._keep_last_parts(state, quiet, 1794667044.0)
    assert quiet["last_learned"]["verdicts"]["selection haircut"]["nba"]["n"] == 227


def test_the_learning_step_writes_every_learners_verdict():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index("        def learn():"):src.index("        # PLACE THE STRANDED ROWS FIRST")]
    for line in ('verdicts["loss patterns"] = verdict_losspatterns(lp)',
                 'verdicts["journal fits"] = verdict_journal(jf)',
                 'verdicts["selection haircut"] = verdict_selection(sf)',
                 'verdicts["correlations"] = {"adopted": len(cf.get("adopted") or [])}',
                 'verdicts["game lines"] = {"adopted": sorted(str(a.get("key")) for a in gc.get("adopted") or [])}',
                 'verdicts["hypotheses"] = verdict_hypotheses(hs)'):
        assert line in body, line


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
                traceback.print_exc(limit=3)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
