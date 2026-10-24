"""Every UFC fight card says where its line opened and where it is now.

Ethan, 2026-10-13: "ik CFB and mlb and nba and ufc is missing stuff."
docs/UFC_MODEL.md names line movement one of "the two upgrades worth
money", and the UFC build has written a snapshot of every book's price on
every paid pull since 2026-08-10 (`linemoves.record_fight_snapshots`) —
and nothing has read it. engine/ufc/moves reads it for each bout on the
card and says it on the card. Pinned here:

  * only this bout's rows count — not his last fight's, not anything
    taken after the start, not another sport's moneyline;
  * the opener and the latest are the median across the books at the
    first and last pull, and the move is in implied-probability points;
  * one pull is a line, not a move — nothing is said;
  * the card's sentence says toward or against the pick, and says it is
    shown, not priced: the grade's movement component stays None;
  * the build puts it on pick and pass rows, and the page draws it,
    escaped, on both cards.

Run directly: `python3 tests/test_ufc_lines_say_where_they_opened.py`
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.ufc import moves as M                       # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

START = "2026-10-18T02:00:00Z"
T0 = datetime.datetime(2026, 10, 18, 2, tzinfo=datetime.timezone.utc).timestamp()


def _snap(player, odds, opp, hours_before, start=T0, book="DraftKings", market="moneyline"):
    row = {"ts": start - hours_before * 3600, "player": player, "market": market,
           "book": book, "line": 0.5, "over_odds": odds, "under_odds": opp}
    if start is not None:
        row["start_ts"] = start
    return row


def _history(rows):
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "line_history.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return tmp, path


def _bout_rows():
    return [
        # Six days out: two books open him at -150 / -140.
        _snap("José Aldo", -150, 130, 144), _snap("José Aldo", -140, 120, 144, book="FanDuel"),
        _snap("Jon Rival", 130, -150, 144), _snap("Jon Rival", 120, -140, 144, book="FanDuel"),
        # Fight day: -190 / -180.
        _snap("José Aldo", -190, 160, 6), _snap("José Aldo", -180, 150, 6, book="FanDuel"),
        _snap("Jon Rival", 160, -190, 6), _snap("Jon Rival", 150, -180, 6, book="FanDuel"),
    ]


def test_only_this_bouts_rows_are_read():
    stale = [
        # His August bout: two months back, its own start.
        _snap("José Aldo", +200, -240, 24 * 60, start=T0 - 60 * 86400),
        # In play, after this bout started.
        _snap("José Aldo", -900, 600, -0.5),
        # An NFL moneyline is not a fight, and another fighter is not him.
        _snap("Kansas City Chiefs", -300, 250, 5),
        _snap("Someone Else", -110, -110, 5),
        # A spread row for him in some other market never parses as his line.
        _snap("José Aldo", -110, -110, 5, market="spread"),
    ]
    tmp, path = _history(_bout_rows() + stale)
    try:
        rows = M.read({"Jose Aldo", "Jon Rival"}, path)        # accents fold
        assert {r["player"] for r in rows} == {"José Aldo", "Jon Rival"}
        assert all(r["market"] == "moneyline" for r in rows)
        mine = M.bout_rows(rows, START)
        assert len(mine) == 8, len(mine)
        assert M.bout_rows(rows, None) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_open_and_the_now_are_the_books_median_and_the_move_is_in_points():
    mv = M.fighter_move(_bout_rows(), "Jose Aldo")
    # Two books at each pull: the median of a pair is the upper one sorted.
    assert (mv["open"], mv["now"]) == (-140, -180)
    assert mv["pulls"] == 2 and mv["books_open"] == 2 and mv["books_now"] == 2
    # -140 is 58.3%, -180 is 64.3%: six points toward him.
    assert mv["pts"] == 6.0
    rival = M.fighter_move(_bout_rows(), "Jon Rival")
    assert rival["pts"] < 0
    assert M.fighter_move(_bout_rows(), "Nobody") is None


def test_one_pull_is_a_line_not_a_move():
    one = [r for r in _bout_rows() if r["ts"] < T0 - 100 * 3600]
    assert M.bout_move(one, "José Aldo", "Jon Rival", START) is None
    two = M.bout_move(_bout_rows(), "José Aldo", "Jon Rival", START)
    assert two["a"]["name"] == "José Aldo" and two["b"]["name"] == "Jon Rival"


def test_the_card_says_toward_or_against_the_pick_and_that_it_is_not_priced():
    mv = M.bout_move(_bout_rows(), "José Aldo", "Jon Rival", START)
    toward = M.note(mv, "José Aldo")
    assert toward.startswith("Line opened José Aldo -140 → -180 · Jon Rival +130 → +160")
    assert "moved 6.0 points toward José Aldo" in toward
    assert toward.endswith("(2 pulls). Shown, not priced.")
    against = M.note(mv, "Jon Rival")
    assert "against Jon Rival" in against
    # A pass names no pick: both lines, no verdict.
    plain = M.note(mv)
    assert "toward" not in plain and "against" not in plain
    assert M.note(None, "José Aldo") == ""
    flat = M.bout_move([_snap("A", -110, -110, 50), _snap("A", -112, -108, 5)], "A", "B", START)
    assert "Barely moved for A" in M.note(flat, "A")


def test_the_grade_still_scores_movement_as_absent():
    src = (ROOT / "engine" / "ufc" / "model.py").read_text(encoding="utf-8")
    assert "movement=None" in src, "a shown move must not reach the grade until it is measured"


def test_the_build_puts_the_move_on_pick_and_pass_rows():
    tmp, path = _history(_bout_rows())
    try:
        out = {"picks": [{"fight": "José Aldo vs Jon Rival", "pick": "José Aldo"}],
               "pass_list": [{"fight": "José Aldo vs Jon Rival"},
                             {"fight": "No History vs At All"}]}
        fights = [{"prices": {"fighter_a": "José Aldo", "fighter_b": "Jon Rival"},
                   "commence": START},
                  {"prices": {"fighter_a": "No History", "fighter_b": "At All"},
                   "commence": START}]
        assert M.attach(out, fights, path) == 1
        pick, passed, bare = out["picks"][0], out["pass_list"][0], out["pass_list"][1]
        assert "toward José Aldo" in pick["line_note"] and pick["line_move"]["a"]["now"] == -180
        assert passed["line_note"] and "toward" not in passed["line_note"]
        assert "line_note" not in bare
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    src = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    assert "_mv.attach(out, fights)" in src
    assert '"commence": ev.get("commence_time")' in src


def _fn(src, decl):
    i = src.index(decl)
    j = src.find("\nfunction ", i + len(decl))
    return src[i:j if j != -1 else len(src)]


def test_the_page_draws_the_line_escaped_on_both_cards():
    app = app_js()
    code = re.sub(r"/\*.*?\*/", "", app, flags=re.S)
    assert "${ufcLineHTML(p.line_note)}" in code, "the pick card does not draw the line"
    assert "${ufcLineHTML(m.line_note)}" in code, "the pass card does not draw the line"
    fn = _fn(app, "function ufcLineHTML(")
    if not shutil.which("node"):
        assert "escapeHtml(t)" in fn
        return
    js = ("const escapeHtml = (s) => String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');\n"
          "const icon = () => '<i></i>';\n" + fn +
          "\nprocess.stdout.write(JSON.stringify([ufcLineHTML(''), ufcLineHTML(null), "
          "ufcLineHTML('Line opened <b>A</b> -140 → -180')]));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    empty, none, drawn = json.loads(out.stdout)
    assert empty == "" and none == ""
    assert "&lt;b&gt;A&lt;/b&gt; -140 → -180" in drawn and "<b>" not in drawn


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
