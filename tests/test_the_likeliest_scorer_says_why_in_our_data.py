"""The likeliest scorer is said in our data and the matchup (2026-11-15).

Ethan, circling the short version's "Jahmyr Gibbs, the Lions' running back —
11 touchdowns in 8 games this season (9 rushing, 2 receiving); Lions's
likeliest scorer by our touchdown numbers (64%), with Lions expected to score
about 26": "wanna make sure we are displaying who's likely to score based off
our data and the matchup and all that shit and not just the books lines".

He was already picked by our touchdown model (readlogic.mark_scorers): his
share of the work, his red-zone touches, his own touchdowns and what the
defense gives up to his position, on the points the game's lines expect his
team to score; no player's price is in it. What the line showed was the
chance and the books' team total. Now (engine/gamereport.scorer_words) it
says our chance beside his price's, then the evidence: his touchdowns this
season, his carries and targets inside the 20 with his share of his team's,
and the touchdowns this defense gives up to his position. "Lions's" is "the
Lions'".

    python3 tests/test_the_likeliest_scorer_says_why_in_our_data.py
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402
from engine import readlogic as RL  # noqa: E402


class _Harness:
    """The game report test's own board, imported when a test first needs it
    (never at module scope: test_doctor)."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_the_game_report_reads_like_the_research"), attr)


GR = _Harness()

GIBBS = {"games": 6, "rz_car": 14, "i5_car": 5, "rz_tgt": 2, "i10_tgt": 1}


def _board(odds=-175):
    board = copy.deepcopy(GR._board())
    for r in board["scan_reads"]["GB@DET"]["players"]:
        if r["player"] == "Jahmyr Gibbs":
            r["td"].update(goal_line=dict(GIBBS), rz_share=0.36, odds=odds, model_prob=0.64)
            r["scoring"] = {"go_to": True, "prob": 0.64, "implied": 26.0}
    return board


def _rep(**kw):
    board = _board(**kw)
    return R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)


def test_the_short_version_says_our_chance_beside_his_price_then_the_evidence():
    text = R.to_text(_rep())
    i = text.index("Likeliest to score: ")
    line = text[i:text.index("\n", i)]
    assert line.startswith("Likeliest to score: Jahmyr Gibbs, the Lions' running back — 64% to score by our "
                           "numbers (the price, −175, says 64%): "), line
    assert ("14 carries (5 inside the 5) and 2 targets (1 inside the 10) inside the 20 in the last 6 games, "
            "36% of the Lions' red-zone work") in line, line
    assert "the Packers give up the second-most touchdowns to running backs" in line, line
    # Not the books' team total as the reason, and never "Lions's".
    assert "expected to score about" not in line and "Lions's" not in text and "by our touchdown numbers" not in line


def test_our_chance_and_his_price_can_disagree_and_both_are_said():
    line = R.to_text(_rep(odds=150))
    i = line.index("Likeliest to score: ")
    assert "64% to score by our numbers (the price, +150, says 40%)" in line[i:i + 200], line[i:i + 200]


def test_his_card_says_whose_likeliest_scorer_he_is():
    rep = _rep()
    sec = next(s for s in rep["sections"] if s["key"] == "matchups")
    cards = [it for b in sec["blocks"] if b.get("type") == "verdicts" for it in b.get("items") or []]
    gibbs = next(it for it in cards if it.get("player") == "Jahmyr Gibbs")
    assert gibbs["why"][0].startswith("The Lions' likeliest scorer — 64% to score by our numbers (the price, −175, "
                                      "says 64%): "), gibbs["why"][0]


def test_the_pick_is_our_models_and_a_plural_nickname_takes_its_apostrophe():
    # mark_scorers ranks by our touchdown model's chance (`td.model_prob`), not the price.
    reads = {"G": {"players": [
        {"player": "A", "team": "DET", "pos": "RB", "td": {"model_prob": 0.40, "odds": -300}},
        {"player": "B", "team": "DET", "pos": "WR", "td": {"model_prob": 0.45, "odds": 200}}]}}
    assert RL.mark_scorers(reads) == 1
    picked = [x["player"] for x in reads["G"]["players"] if (x.get("scoring") or {}).get("go_to")]
    assert picked == ["B"], "the longer price, the better chance by our numbers"
    b = reads["G"]["players"][1]
    assert RL.scoring_words(b, team_words="Lions").startswith("Lions' likeliest scorer")
    assert RL.scoring_words(b, team_words="Duke").startswith("Duke's likeliest scorer")


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
