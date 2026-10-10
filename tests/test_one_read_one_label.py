"""A player's read says the same thing on every part of the page.

Ethan, 2026-09-26, two screenshots of the NFL page: "Dalton Kincaid was
listed as a breakout candidate up here, but then he's listed as a good
matchup down here … fix it so all that data is linked together and not
showing different shit because that's wrong and confusing."

The Top Picks card was a LOCKED pick, posted Friday. `likely._locked`
copies the posted row whole, so it kept the `scan_label` stamped when it
went up ("Breakout candidate"), while the reads shelf drew Saturday's
scan ("Good matchup"). Two fixes, one rule — the label is today's read:

  * engine/likely.stamp_reads runs AFTER the posted picks are carried
    forward, clears every row's stamp and sets it again from this build's
    leans, so a carried row never keeps a label the scan no longer gives;
  * the page's card tag reads the live read (pickScanRead) — the same one
    the shelf and the pick page show — and uses the stamped label only
    when the reads are not on the page.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LIKELY = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()

GOOD = {"side": "over", "read": "good", "label": "Good matchup"}


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_a_carried_row_takes_todays_label():
    rows = [{"player": "Dalton Kincaid", "team": "BUF", "market": "rec_yds", "side": "over",
             "locked": True, "scan_read": "breakout", "scan_label": "Breakout candidate"}]
    K.stamp_reads(rows, {("Dalton Kincaid", "BUF", "rec_yds"): GOOD})
    assert (rows[0]["scan_read"], rows[0]["scan_label"]) == ("good", "Good matchup")


def test_a_read_that_is_gone_or_turned_leaves_no_label():
    gone = {"player": "A", "team": "BUF", "market": "rec_yds", "side": "over",
            "scan_read": "breakout", "scan_label": "Breakout candidate"}
    turned = {"player": "B", "team": "BUF", "market": "rec_yds", "side": "under",
              "scan_read": "tough", "scan_label": "Tough matchup"}
    K.stamp_reads([gone, turned], {("B", "BUF", "rec_yds"): GOOD})
    assert "scan_label" not in gone and "scan_read" not in gone, "no read today, no tag"
    assert "scan_label" not in turned, "today's read is on the other side"


def test_the_board_restamps_after_the_posted_picks_come_back():
    body = LIKELY[LIKELY.index("\ndef build("):]
    carried = body.index("_stamp_hold(out, held, stamp)")
    assert "stamp_reads(out, leans)" in body[carried:], "the stamp runs on the carried rows too"


def test_the_card_names_the_live_read():
    f = _fn("likelyTagsHTML")
    assert "cardScanRead(r)" in f and "r.scan_label" not in f
    g = _fn("cardScanRead")
    assert "pickScanRead(r)" in g
    if not shutil.which("node"):
        return
    side = APP[APP.index("const SCAN_READ_SIDE"):]
    side = side[:side.index("\n") + 1]
    harness = ("let state={data:{}};\n" + side + _fn("pickScanRead") + "\n" + _fn("cardScanRead")
               + "\nconst cases=JSON.parse(process.argv[2]);"
               "process.stdout.write(JSON.stringify(cases.map(([d,r])=>{state.data=d;return cardScanRead(r);})));")
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    game = {"games": [{"home": "MIA", "away": "BUF"}]}
    read = lambda r, l: {"scan_reads": {"BUF@MIA": {"players": [  # noqa: E731
        {"player": "Dalton Kincaid", "team": "BUF", "read": r, "label": l}]}}, **game}
    row = {"player": "Dalton Kincaid", "team": "BUF", "opponent": "MIA", "side": "over",
           "scan_read": "breakout", "scan_label": "Breakout candidate"}
    cases = [
        [read("good", "Good matchup"), row],                       # the shelf's word wins
        [read("neutral", "Neutral"), row],                         # no lean today: no tag
        [read("tough", "Tough matchup"), row],                     # turned: not on an over
        [{**game, "scan_reads": {"BUF@MIA": {"players": []}}}, row],  # not read today
        [game, row],                                               # reads not on the page
        [read("good", "Good matchup"), {**row, "side": "yes", "lane": "td",
                                         "scan_read": None, "scan_label": None}],
    ]
    out = json.loads(subprocess.run(["node", path, json.dumps(cases)], capture_output=True,
                                    text=True, check=True).stdout)
    assert out == [{"read": "good", "label": "Good matchup"}, None, None, None,
                   {"read": "breakout", "label": "Breakout candidate"},
                   {"read": "good", "label": "Good matchup"}], out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
