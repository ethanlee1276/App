"""The injury report read closely: how he practised, and how honest his club's "questionable" is.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 5: a questionable
man who was limited on Friday and one who did not practise are different
bets, and some clubs list half the roster questionable and play them all.

What these hold: a designation is Questionable, Doubtful or Out and the
practice note folds to did not / limited / full / none; a listing counts
only for a man the snap logs follow, he "played" when his share that game
was above zero, and his snap ratio needs two prior games; the table is
kept per designation and practice and per designation overall; a club's
questionable rate is shrunk toward the league by 20 listings; his chance
folds the club in only for the questionable designation, capped below
one; the held-out test fits on every season but the last and compares log
loss on the last; the ideas section reads only this NFL week's report off
the board's own week, and the pick and game pages show it labelled, with
the board's hold unchanged.

Run directly: `python3 tests/test_practice_reports_and_club_honesty.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ideas as ID                                   # noqa: E402
from engine import practice as P                                 # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _inj(season, week, team, name, status, practice):
    return {"season": season, "week": week, "team": team, "full_name": name, "report_status": status,
            "practice_status": practice}


def test_designations_and_practice_notes_fold_to_a_few_words():
    assert P.designation_of(" questionable ") == "Questionable" and P.designation_of("") == ""
    assert P.practice_of("Did Not Participate In Practice") == "DNP"
    assert P.practice_of("Limited Participation in Practice") == "Limited"
    assert P.practice_of("Full Participation in Practice") == "Full" and P.practice_of(None) == "None"


def test_a_listing_counts_only_for_a_man_the_logs_follow():
    inj = [_inj(2025, 5, "KC", "Travis Kelce", "Questionable", "Limited Participation in Practice"),
           _inj(2025, 5, "KC", "Rashee Rice", "Questionable", "Did Not Participate In Practice"),
           _inj(2025, 5, "KC", "Some Lineman", "Questionable", "Limited"),
           _inj(2025, 5, "KC", "Noone Listed", "", "Limited")]
    snaps = {("travis kelce", 2025, 5): 0.7, ("travis kelce", 2025, 4): 0.8, ("travis kelce", 2025, 3): 0.8,
             ("rashee rice", 2025, 4): 0.6, ("rashee rice", 2025, 3): 0.6}
    rows = P.listings(inj, snaps)
    assert rows == [(2025, "KC", "Questionable", "Limited", True, 0.7 / 0.8),
                    (2025, "KC", "Questionable", "DNP", False, None)], "no snaps on file and no designation are skipped"


def test_the_table_and_the_clubs_shrunk_toward_the_league():
    rows = [(2024, "KC", "Questionable", "Limited", True, 0.9)] * 30 + [(2024, "KC", "Questionable", "DNP", False, None)] * 10
    rows += [(2024, "NYJ", "Questionable", "Limited", i % 2 == 0, None) for i in range(10)]
    tab = P.table(rows)
    assert tab["Questionable|Limited"]["n"] == 40 and tab["Questionable|*"]["n"] == 50
    assert tab["Questionable|Limited"]["ratio"] == 0.9
    q = tab["Questionable|*"]["played"]
    cl = P.clubs(rows, q)
    assert cl["KC|2024"]["raw"] == 0.75 and cl["NYJ|2024"]["raw"] == 0.5
    assert abs(cl["NYJ|2024"]["played"] - (5 + 20 * q) / 30) < 1e-4, "ten listings pulled toward the league by twenty"
    c = P.chance({"table": tab, "clubs": cl}, "NYJ", 2025, "Questionable", "Limited")
    assert c["league"] == tab["Questionable|Limited"]["played"] and c["club_n"] == 10, "last season's club when this one has none"
    assert c["club"] < c["league"], "an honest club's questionable plays less often"
    out = P.chance({"table": {"Out|*": {"n": 9, "played": 0.02, "ratio": None}}, "clubs": cl}, "KC", 2024, "Out", "DNP")
    assert out["league"] == 0.02 and out["club"] is None, "the club is folded in for questionable only"


def test_the_held_out_season_is_the_last():
    rows = []
    for season in (2023, 2024, 2025):
        for i in range(40):
            rows.append((season, "KC", "Questionable", "Limited", i % 10 != 0, None))
            rows.append((season, "NYJ", "Questionable", "Limited", i % 2 == 0, None))
    h = P.held_out(rows)
    assert h["season"] == 2025 and h["n"] == 80 and h["gain"] > 0
    assert not h["holds"], "80 listings is not 300"


def test_the_section_reads_this_weeks_report_and_the_pages_draw_it():
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    real = P._week_rows
    P._week_rows = lambda season, week: [_inj(season, week, "KC", "Travis Kelce", "Questionable",
                                              "Limited Participation in Practice"),
                                         _inj(season, week, "KC", "Mike Danna", "Out", "Did Not Participate In Practice")]
    try:
        assert P.ideas_section([], [], {"date": "2026-10-19"}, "nfl") is None, "a board with no NFL week reads nothing"
        assert P.ideas_section([], [], {"date": "2026-W07"}, "mlb") is None
        bare = P.ideas_section([], [], {"date": "2026-W07"}, "nfl")
        assert bare["measured"] is False and bare["listed"]["travis kelce"]["designation"] == "Questionable"
        rows = [(2025, "KC", "Questionable", "Limited", True, 0.9)] * 30
        tab = P.table(rows)
        P.save({"sport": "nfl", "table": tab, "clubs": P.clubs(rows, 1.0), "held_out": {"n": 0}, "seasons": [2025]})
        sec = P.ideas_section([], [], {"date": "2026-W07"}, "nfl")
        pv = P.pick_view(sec, "Travis Kelce", "rec_yds")
        assert pv["league"] == 1.0 and pv["practice"] == "Limited" and pv["measured"]
        gv = P.game_view(sec, "KC", "BUF")
        assert [r["player"] for r in gv["rows"]] == ["Travis Kelce"], "a man ruled out is not a question"
    finally:
        P._week_rows = real
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["practice"] == "practice"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    payload = json.dumps({"p": {"sections": {"practice": pv}}, "g": {"home": "KC", "sections": {"practice": gv}}})
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"const d = {payload}; process.stdout.write(JSON.stringify({{p: L.pickHTML(d.p), g: L.gameHTML(d.g)}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    got = json.loads(out.stdout)
    assert "The injury report, read closely" in got["p"] and "he was limited in practice" in got["p"]
    assert "the board’s injury hold is unchanged" in got["p"]
    assert "Who is on the injury report" in got["g"] and "Travis Kelce" in got["g"]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
