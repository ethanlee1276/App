"""A report's card puts the picks the record backs first (step AAM's evidence, step AAO, 21 November).

On the record of every settled Most Likely pick: an NFL pick whose chance sat more than ten points
over the book's own fair chance hit 45% and then 53% (where we said 75% and 87%) while every other
NFL pick hit 58%; an NBA prop one play settles hit 62% as a single where every other NBA pick hit
65%. On a game's card those go behind every other bet; reads stay last; nothing is taken off.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as GR          # noqa: E402

SRC = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")


def _row(player, p, odds, market="receptions", side="OVER", line=3.5, **kw):
    return {"player": player, "team": "NYG", "opponent": "WAS", "market": market, "side": side, "line": line,
            "odds": odds, "model_prob": p, "bettable": True, "kind": "prop", **kw}


def _card(rows, sport, featured=False):
    c = SimpleNamespace(result={"likely_board": {"rows": rows}}, teams=("NYG", "WAS"), featured=featured, sport=sport)
    return [r["player"] for r in GR._card_rows(c)]


def test_an_nfl_pick_far_over_the_books_chance_goes_behind_the_others():
    rows = [_row("Far Over", 0.86, -110), _row("Backed A", 0.66, -220), _row("Backed B", 0.64, -200),
            _row("Backed C", 0.62, -180), _row("Backed D", 0.61, -170), _row("A Read", 0.70, -150, bettable=False)]
    assert _card(rows, "nfl") == ["Backed A", "Backed B", "Backed C", "Backed D"], "a full card leaves it off"
    assert _card(rows, "nfl", featured=True) == ["Backed A", "Backed B", "Backed C", "Backed D", "Far Over", "A Read"]
    # The book's own fair chance speaks where the row has one; within ten points is no doubt.
    near = [_row("Near", 0.70, -110, implied_prob=0.62)] + rows[1:5]
    assert _card(near, "nfl")[0] == "Near"
    assert _card(rows, "cfb")[0] == "Far Over", "college football's card is left as it was"
    os.environ["QB_CARD_DOUBT"] = "off"
    try:
        assert _card(rows, "nfl")[0] == "Far Over"
    finally:
        os.environ.pop("QB_CARD_DOUBT", None)


def test_a_ladder_rung_is_read_against_its_own_line_not_its_main_line():
    """Step AAT: a rung's `fair_prob` is its main line's. Read against that, every -250 rung looked twenty
    points over a -110 book and went behind; the NFL's cards of 21 November filled with touchdown picks."""
    rung = _row("Ladder Rung", 0.72, -250, rung="alt", implied_prob=0.674, fair_prob=0.50)
    rows = [rung, _row("Backed A", 0.66, -220), _row("Backed B", 0.64, -200), _row("Backed C", 0.62, -180),
            _row("Backed D", 0.61, -170)]
    assert _card(rows, "nfl")[0] == "Ladder Rung", "72% against its own rung's 67%: no doubt"
    far = dict(rung, model_prob=0.86)
    assert _card([far] + rows[1:], "nfl")[-1] == "Backed D" and "Ladder Rung" not in _card([far] + rows[1:], "nfl"), \
        "86% against its own rung's 67% is still far over, and still goes behind"


def test_an_nba_one_play_prop_goes_behind_the_others():
    rows = [_row("Bench Big", 0.70, -230, market="reb", line=1.5), _row("Rim Guard", 0.69, -230, market="blk", side="UNDER", line=0.5),
            _row("Wing", 0.66, -200, market="reb", line=4.5), _row("Guard", 0.65, -200, market="ast", line=1.5)]
    assert _card(rows, "nba") == ["Wing", "Guard", "Bench Big", "Rim Guard"]
    assert _card(rows, "nhl") == ["Bench Big", "Rim Guard", "Wing", "Guard"], "the NBA's alone"


def test_the_record_behind_it_is_in_its_words():
    assert GR.CARD_BOOK_GAP == 0.10 and GR.CARD_DOUBT_SPORTS == ("nfl",)
    for words in ("hit 45% (92 picks, where we", "hit 62% as a", "Switch: QB_CARD_DOUBT=off"):
        assert words in SRC, words


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
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
