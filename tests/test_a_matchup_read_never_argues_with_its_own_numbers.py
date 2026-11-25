"""A matchup read never argues with the numbers printed beside it (step ACW, 23 November 2026).

Ethan, the Bengals at the Commanders: "We list the Bengals as giving up 76 yards and 6.2 catches a game to tight
ends. That's the second highest in the league ... But yet we're still saying the Commanders tight end is a tough
matchup. It doesn't really make much sense compared to the data we're giving out."

Rebuilt from the 2026 box scores through week 11: the Bengals give up 76.1 receiving yards (2nd) and 6.2 catches
(5th) a game to tight ends and 237 passing yards a game overall (15th). A pass catcher's count reads the overall
number (engine/defensevs.MODEL_STAT; re-measured that morning, 2022-2025 each held out: overall +0.15% on tight
ends' yards and +0.40% on their catches, the position's own number -0.12% and -0.17%), so the defence had no vote,
and the read leaned tough on the forecast 9 mph wind alone (receiving yards 3.3% lower). What these hold:

  * a read that leans against what the defence gives up to his own position, at the league's ends, is mixed: it
    leans neither way, names both numbers, and makes no pick or headline;
  * a read the defence had no vote in is a spot ("Tough spot"), not a matchup;
  * a read the defence carried keeps its matchup words;
  * the report's cards, names and "where the defense is weakest" lines say it the same way.

    python3 tests/test_a_matchup_read_never_argues_with_its_own_numbers.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as GR, gamescan as S                  # noqa: E402

WIND = {"dome": False, "temp_f": 56.0, "wind_mph": 9.0, "wind_dir": "NW", "rain": False, "snow": False,
        "measured": True, "precip_chance": 0.15, "forecast": True}


def _row(pg, rank, of=32, games=9):
    return {"pg": pg, "rank": rank, "of": of, "games": games, "factor": 1.0}


def _cin(te_rank=2, pass_rank=15):
    return {"te_rec_yds": _row(76.11, te_rank), "te_rec": _row(6.22, 5), "te_td": _row(0.22, 25),
            "qb_pass_yds": _row(237.11, pass_rank), "wr_rec_yds": _row(128.33, 25), "wr_rec": _row(10.11, 23)}


def _read(allowed, weather=WIND, share=0.15, pos="TE"):
    usage = {"tgt_share": share, "targets_pg": 4.0, "games": 9, "share_of": "targets"}
    return S.player_read("Washington Tight End", "WAS", "CIN", pos, usage=usage, ratings={}, room=None,
                         scheme=None, split=None, tackling=None, line_out=None, mates_out=None, n_teams=32,
                         allowed=allowed, points=24.25, line_words="", weather=weather)


def test_the_commanders_tight_end_reads_mixed_not_tough():
    r = _read(_cin())
    assert r["read"] == "neutral" and r["label"] == "Neutral", r
    assert r["mixed_was"] == "tough", "it leaned tough on the wind"
    assert r["mixed"] == "CIN gives up the 2nd-most receiving yards to tight ends (76 a game)", r["mixed"]
    assert r["mixed_with"].startswith("The wind is forecast at 9 mph"), r["mixed_with"]
    assert "237" in r["defense_line"] and "15th-most of 32" in r["defense_line"], r["defense_line"]
    from engine import matchpicks as MP
    reads = [dict(r)]
    picks = [{"player": r["player"], "team": "WAS", "side": "under", "market": "rec_yds", "model_prob": 0.6}]
    assert MP.stamp_reads(reads, picks) == 0 and "matchup_pick" not in reads[0], "a mixed read makes no pick"


def test_a_lean_on_the_wind_alone_is_a_spot():
    r = _read(_cin(te_rank=15))
    assert r["read"] == "tough" and r.get("spot") and r["label"] == "Tough spot", r
    assert r["drivers"] == ["weather"]
    assert GR.verdict_of(r) == ("unfavorable", "TOUGH SPOT") and GR.tone_of(r) == ("down", "Tough spot")


def test_a_lean_the_defense_carried_keeps_its_matchup_words():
    r = _read(_cin(te_rank=15, pass_rank=30), weather=None)
    assert r["read"] == "tough" and not r.get("spot") and r["label"] == "Tough matchup", r
    assert r["drivers"] == ["defense"] and GR.verdict_of(r) == ("unfavorable", "UNFAVORABLE")
    # …and a stingy defence against a soft tight-end funnel is mixed the same way.
    m = _read(_cin(te_rank=2, pass_rank=30), weather=None)
    assert m["read"] == "neutral" and m["mixed_was"] == "tough" and "fewest passing yards" in m["mixed_with"], m


def test_the_report_says_it_the_same_way():
    r = _read(_cin())
    assert GR.verdict_of(r) == ("neutral", "NEUTRAL — MIXED")
    line = GR.mixed_line(r)
    assert line.startswith("The numbers point both ways: CIN gives up the 2nd-most receiving yards to tight ends")
    assert ", but the wind is forecast at 9 mph: about 3% off a receiver's yards" in line, line
    assert line.endswith("— so neither way"), line

    class C:
        allowed = {"CIN": _cin()}
    out = GR.funnel_lines(C, "CIN")
    assert out[0].startswith("Where CIN's defense is weakest, over 9 games: it gives up the 2nd-most receiving yards")
    assert out[-1] == ("Our receiver and tight end reads count the passing yards CIN allows overall (237 a game, "
                       "the 15th-most of 32) and show what it allows each position beside it: over 2022-2025 the "
                       "overall number split their games at least as well as the position's own, and counting both "
                       "split them less"), out[-1]
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'const word = (x.spot && x.label) || SCAN_READ_WORD[x.read] || x.label || "";' in js


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
