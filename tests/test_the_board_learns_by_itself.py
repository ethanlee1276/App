"""The Most Likely board learns from its own record, every league, by itself.

Ethan, 2026-10-03: "we shouldn't have to constantly run tests for every
sport like this to make it better and see where it's winning and losing,
our models and the site should automatically be able to do this by
itself." Checks, one rule each: a settle pass refits the record's
correction and adopts it when it holds on games it never saw; it grades
the record by maker, market and claim, so a losing maker reads as losing
and an honest one as holding up; a league whose graded picks did not
change is not refitted; a correction the record stops proving is removed;
the settle pass runs it; the Record page draws it.

Run directly: `python3 tests/test_the_board_learns_by_itself.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
os.environ.pop("QB_LIKELY_CAL", None)
os.environ.pop("QB_LIKELY_CTX", None)

from engine import boardlearn as B                                   # noqa: E402
from engine import ledger as LG                                      # noqa: E402
from engine import likelycal                                         # noqa: E402


def _ledger(bold_hits_per_20: int):
    """150 games: the list's pick hits 13 in 20 at 65% claimed; the bold
    pick, claimed at 75% against a -120 price, hits ``bold_hits_per_20``."""
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    led = LG.connect(path)
    for i in range(150):
        day = f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}"
        team = f"T{i % 30}"
        rows = [(f"Lister {i}", "rec_yds", 0.65, -150, i % 20 < 13, ("likely", "board")),
                (f"Bold {i}", "rush_yds", 0.75, -120, i % 20 < bold_hits_per_20, ("board", "bold"))]
        for player, market, p, odds, won, cats in rows:
            for cat in cats:
                led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, "
                            "hit_prob, status, category) VALUES ('nfl',?,?,?,?,?,'OVER',40.5,?,?,?,?)",
                            (day, day, player, team, market, odds, p, "won" if won else "lost", cat))
    led.commit()
    return led


def test_a_settle_pass_adopts_what_the_record_proves_and_grades_every_maker():
    rep = Path(tempfile.mkdtemp()) / "board_learning.json"
    lines = []
    ran = B.refresh(_ledger(7), None, log=lines.append, sports=("nfl",), path=rep)
    assert "nfl" in ran, lines
    groups = likelycal.load()["nfl"]["groups"]
    assert groups["bold|over"]["k"] < 1.0, "the bold picks are pulled toward their price"
    assert groups.get("list|over", {}).get("k", 1.0) == 1.0, "the honest list is left alone"
    maker = {s["key"]: s for s in ran["nfl"]["slices"]["maker"]}
    assert maker["bolder than the books · over"]["verdict"] == "over-claims"
    assert maker["Most Likely list · over"]["verdict"] == "holds up"
    assert json.loads(rep.read_text())["nfl"]["calibration"]["passed"] is True
    assert any("adopted" in ln for ln in lines)


def test_a_bold_pick_is_found_however_its_books_dated_it():
    # The box, 2026-10-04: the audit found 61 bold picks and likelycal's
    # fit printed no bold group, because it matched books on `date`.
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    led = LG.connect(path)
    for cat, date in (("board", "2026-W04"), ("bold", "2026-09-27")):
        led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, hit_prob, "
                    "status, category) VALUES ('nfl',?,'2026-09-27','X','LV','rush_yds','OVER',40.5,-120,0.75,"
                    "'lost',?)", (date, cat))
    led.commit()
    rows = likelycal.journal_rows(led, "nfl")
    assert [r["group"] for r in rows] == ["bold|over"], rows


def test_a_maker_too_small_on_each_side_is_fitted_on_both():
    # The box, 2026-10-04: bold went 13-20 on unders and 17-25 on overs,
    # claiming 71-74%, and neither side reached a fit inside a fold.
    path = Path(tempfile.mkdtemp()) / "ledger.db"
    led = LG.connect(path)
    for i in range(160):
        day = f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}"
        rows = [(f"Lister {i}", "rec_yds", "OVER", 0.65, -150, i % 20 < 13, ("likely", "board"))]
        if i % 3 == 0:                                            # 54 bold: 27 a side
            rows.append((f"Bold {i}", "rush_yds", "OVER" if i % 6 == 0 else "UNDER", 0.74, -120, i % 20 < 8,
                         ("board", "bold")))
        for player, market, side, p, odds, won, cats in rows:
            for cat in cats:
                led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, "
                            "hit_prob, status, category) VALUES ('nfl',?,?,?,'T',?,?,40.5,?,?,?,?)",
                            (day, day, player, market, side, odds, p, "won" if won else "lost", cat))
    led.commit()
    res = likelycal.fit(led, "nfl")
    assert "bold|over" not in res["groups"] and "bold|under" not in res["groups"], "27 a side is too few"
    assert res["groups"]["bold|both"]["k"] < 1.0 and res["passed"], res["held_out"]
    row = {"model_prob": 0.74, "odds": -120, "side": "UNDER", "bold": True, "sources": ["likely"]}
    assert likelycal.apply([row], "nfl", {"nfl": {"groups": res["groups"]}}) == 1
    assert row["model_prob"] < 0.74 and "overs and unders together" in row["cal_note"]


def test_nothing_new_graded_means_nothing_refitted():
    rep = Path(tempfile.mkdtemp()) / "board_learning.json"
    led = _ledger(7)
    assert B.refresh(led, None, log=lambda *_: None, sports=("nfl",), path=rep)
    assert B.refresh(led, None, log=lambda *_: None, sports=("nfl",), path=rep) == {}


def test_a_correction_the_record_stops_proving_is_removed():
    rep = Path(tempfile.mkdtemp()) / "board_learning.json"
    B.refresh(_ledger(7), None, log=lambda *_: None, sports=("nfl",), path=rep)
    assert "nfl" in likelycal.load()
    lines = []
    B.refresh(_ledger(15), None, log=lines.append, sports=("nfl",), path=rep, force=True)   # bold now honest
    assert "nfl" not in likelycal.load(), "the store holds what the record supports today"
    assert any("removed" in ln for ln in lines), lines


def test_the_settle_pass_runs_it_and_the_record_page_draws_it():
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    body = src[src.index("def settle_open("):]
    body = body[:body.index("\ndef ", 10)]
    assert "_run_board_learning(lconn, hconn, log)" in body, "the settle pass, not a command on the box"
    assert "BOARDLEARN_EVERY_S" in body, "throttled, so a game day does not refit every few minutes"
    helper = src[src.index("def _run_board_learning("):src.index("def _run_deep_refit(")]
    assert '_spawn_module("engine.boardlearn", log, args=("--auto",))' in helper, \
        "on the box it runs in its own niced process, never the web server's"
    led = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert '"board_learning": _board_learning_block()' in led
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "recBoardLearningSection(d.board_learning, scoped ? scope : null)" in app
    node = shutil.which("node")
    if not node:
        return
    i = app.index("function recBoardLearningSection(")
    fn = app[i:app.index("\nfunction ", i + 10)]
    sample = {"nfl": {"at": "2026-10-04T03:00:00", "record": {"n": 40, "won": 22, "hit": 0.55, "said": 0.64,
                                                              "verdict": "over-claims"},
                      "slices": {"maker": [{"key": "bolder than the books · over", "n": 20, "won": 7, "hit": 0.35,
                                            "said": 0.75, "z": -4.1, "verdict": "over-claims"}]},
                      "calibration": {"passed": True, "groups": {"bold|over": {"k": 0.2, "n": 20, "hit": 0.35,
                                                                               "claimed": 0.75}}}}}
    prog = ("const escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n" + fn +
            f"\nconsole.log(recBoardLearningSection({json.dumps(sample)}, 'nfl'));"
            f"\nconsole.log('MLB:' + recBoardLearningSection({json.dumps(sample)}, 'mlb').length);")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    html = out.stdout
    assert "NFL — 22-18 on 40 graded picks" in html and "over-claims" in html
    assert "pulled 80% of the way to the price" in html
    assert re.search(r"MLB:0\s*$", html), "a league with no report draws nothing"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
