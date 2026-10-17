"""A pick never wears the word "Avoid" (Ethan, 2026-10-02).

His screenshot circled four Most Likely top picks — Quentin Johnston
Under 3.5 receptions, Cole Kmet Under 1.5, Johnston Under 33.5 yards,
Oronde Gadsden II Under 25.5 — each with a red "Avoid" chip: "What are we
saying to avoid these bets but then displaying them as the top bets".

"Avoid" is the matchup scan's worst tier for a PLAYER (stay off his
over). The board seated those UNDERS because of that read. The chip was
the player's label printed on the bet, in the alarm colour. Now a pick
says what the read means for the bet: "Worst matchup · backs the under",
in the agreeing colour; a read that fights the side says so.

Run directly: `python3 tests/test_a_pick_never_wears_avoid.py`
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


def _run(cases):
    if not shutil.which("node"):
        return None
    word = re.search(r"const SCAN_READ_WORD = \{.*?\};", APP, re.S).group(0)
    side = re.search(r"const SCAN_READ_SIDE = \{.*?\};", APP).group(0)
    js = (side + "\n" + word + "\n" + _fn("scanReadForBet")
          + f"\nprocess.stdout.write(JSON.stringify({json.dumps(cases)}.map(([x, s]) => scanReadForBet(x, s))));")
    path = os.path.join(tempfile.mkdtemp(), "r.js")
    Path(path).write_text(js, encoding="utf-8")
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_an_avoid_read_on_an_under_backs_it():
    got = _run([[{"read": "avoid", "label": "Avoid"}, "UNDER"],
                [{"read": "tough", "label": "Tough matchup"}, "under"],
                [{"read": "breakout", "label": "Breakout candidate"}, "OVER"],
                [{"read": "avoid", "label": "Avoid"}, "OVER"],
                [{"read": "avoid", "label": "Avoid"}, "No"]])
    if got is None:
        return
    assert got[0] == {"text": "Worst matchup · backs the under", "tone": "up"}, got[0]
    assert got[1] == {"text": "Tough matchup · backs the under", "tone": "up"}, got[1]
    assert got[2] == {"text": "Breakout candidate", "tone": "up"}, got[2]
    assert got[3] == {"text": "Worst matchup · against this side", "tone": "down"}, got[3]
    assert got[4]["tone"] == "up", "an anytime-TD No is the under"
    assert not any("Avoid" in g["text"] for g in got), "the player's label reached a bet"


def test_the_row_tag_and_the_pick_page_both_say_it_for_the_bet():
    tags = _fn("likelyTagsHTML")
    assert "scanReadForBet(sr, r.side)" in tags and "tags.push([sr.label" not in tags
    assert "scanReadForBet(x, (lk && lk.side) || r.side)" in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
