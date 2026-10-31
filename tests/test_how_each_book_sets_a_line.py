"""How each book sets a line, fitted from the lines it hung — beside the recipe that predicted results.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 3: every book turns
the same public numbers into a line; fit that recipe, fit the one that
predicted what happened, and the difference is the book's habit.

What these hold: the four features are his last game, his last three, this
season (his career when the season has none) and his career, from games
strictly before the one priced, and three prior games are needed; the fit
is least squares on a constant and those four, and recovers known weights;
"weight on last game" is that slope's share of the four; the history join
dates each close by the schedule and keeps every book's quote; the
outcome recipe is fitted once per player-game, not once per book; the
held-out score only counts closes where the outcome recipe sits 0.75 of
its spread from the line, against the close's own fair chance; the bar
needs 300 closes and every test season above zero; the pick page shows
each book's recipe beside its line, labelled.

Run directly: `python3 tests/test_how_each_book_sets_a_line.py`
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import bookrecipe as R                               # noqa: E402
from engine import db as D                                       # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _synthetic(n=600, seed=1):
    rnd = random.Random(seed)
    xs, ys, ls = [], [], []
    for _ in range(n):
        c = rnd.gauss(60, 15)
        s = c + rnd.gauss(0, 5)
        l3 = s + rnd.gauss(0, 8)
        l1 = l3 + rnd.gauss(0, 15)
        x = {"last1": l1, "last3": l3, "season": s, "career": c}
        xs.append(x)
        ys.append(0.1 * l1 + 0.2 * l3 + 0.4 * s + 0.3 * c + rnd.gauss(0, 20))
        ls.append(0.4 * l1 + 0.2 * l3 + 0.2 * s + 0.2 * c)
    return xs, ys, ls


def test_the_features_come_only_from_earlier_games():
    assert R.features_from([(2025, 50.0), (2025, 70.0)]) is None, "three prior games needed"
    x = R.features_from([(2025, 90.0), (2025, 30.0), (2024, 60.0), (2024, 40.0)])
    assert x == {"last1": 90.0, "last3": 60.0, "season": 60.0, "career": 55.0}
    week1 = R.features_from([(2024, 60.0), (2024, 40.0), (2024, 50.0)])
    assert week1["season"] == 50.0, "his own season while it has games"
    row = {"form": {"last1": 80, "last3": 70, "season": None, "career": 65}}
    assert R.features_from_row(row) == {"last1": 80.0, "last3": 70.0, "season": 65.0, "career": 65.0}
    assert R.features_from_row({"form": {}}) is None


def test_the_fit_recovers_a_known_recipe():
    xs, ys, ls = _synthetic()
    book = R.fit(xs, ls)
    assert book["weights"] == {"last1": 0.4, "last3": 0.2, "season": 0.2, "career": 0.2} and book["sd"] < 0.01
    out = R.fit(xs, ys)
    assert out["weights"]["last1"] < 0.25 and out["n"] == 600
    assert abs(R.predict(book, xs[0]) - ls[0]) < 0.01
    assert R.fit(xs[:50], ls[:50]) is None, "under 200 closes no recipe"


def test_the_history_join_dates_each_close_and_keeps_every_book():
    conn = D.connect(":memory:")
    vals = [40.0, 60.0, 50.0, 90.0]
    for wk, v in enumerate(vals, 1):
        conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES ('nfl', 2025, ?, ?, 'Puka Nacua', 'LA', 'SF', 'WR', 1, 'rec_yds', ?)",
                     (f"{wk:03d}", f"LA-{wk:03d}", v))
    rows = []
    for book, line in (("dk", 70.5), ("fd", 72.5)):
        rows.append({"sport": "nfl", "taken_at": "2025-09-28T16:00:00Z", "event_id": "e4", "home": "LA", "away": "SF",
                     "player": "puka nacua", "market": "rec_yds", "book": book, "line": line, "over_odds": -110,
                     "under_odds": -110, "commence_time": "2025-09-28T20:00:00Z"})
    D.upsert_odds_history(conn, rows)
    dates = {(2025, 4, "LA"): "2025-09-28"}
    got = R.history(conn, "nfl", "rec_yds", dates)
    assert sorted((b, line) for _s, b, line, _f, _x, _a in got) == [("dk", 70.5), ("fd", 72.5)]
    season, _b, _l, fair, x, actual = got[0]
    assert season == 2025 and actual == 90.0 and abs(fair - 0.5) < 1e-9
    assert x == {"last1": 50.0, "last3": 50.0, "season": 50.0, "career": 50.0}, "week 4's numbers are weeks 1-3"
    assert got[0][4] is got[1][4], "one player-game, one set of features, however many books"


def test_the_score_counts_only_parted_closes_and_the_bar_needs_every_season():
    outcome = {"w": [0.0, 0.0, 0.0, 0.0, 1.0], "sd": 10.0}
    x_hi, x_lo = {"last1": 0, "last3": 0, "season": 0, "career": 80.0}, {"last1": 0, "last3": 0, "season": 0, "career": 52.0}
    rows = []
    for i in range(400):
        season = 2024 + i % 2
        rows.append((season, "dk", 70.5, 0.5, x_hi, 90.0 if i % 4 else 60.0))      # recipe 80 vs 70.5: lean over
        rows.append((season, "dk", 50.5, 0.5, x_lo, 40.0))                           # recipe 52 vs 50.5: too close
    sc = R.score(rows, outcome)
    assert len(sc["all"]) == 400 and set(sc["by_season"]) == {2024, 2025}
    assert abs(sum(sc["all"]) / 400 - 0.25) < 1e-9
    assert R.score(rows, None) == {"all": [], "by_season": {}}


def test_the_pick_page_shows_each_books_recipe_beside_its_line():
    xs, ys, ls = _synthetic()
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        assert R.ideas_section([], [], {"recommendations": []}, "nfl") == {"rows": {}, "fitted": False}, \
            "no fit on this box, nothing to show"
        R.save({"sport": "nfl", "markets": {"rec_yds": {"fit": {"outcome": R.fit(xs, ys), "books": {"dk": R.fit(xs, ls)}},
                                                        "verdict": {}}}})
        board = {"recommendations": [{"player": "X", "market": "rec_yds",
                                      "form": {"last1": 110, "last3": 80, "season": 70, "career": 65},
                                      "all_lines": [{"book": "dk", "line": 78.5}, {"book": "fd", "line": 76.5}]}]}
        sec = R.ideas_section([], [], board, "nfl")
        v = R.pick_view(sec, "X", "rec_yds")
        assert [b["book"] for b in v["books"]] == ["dk"], "a book with no fitted recipe is left out"
        assert v["books"][0]["last1"] == 0.4 and v["books"][0]["recipe"] == round(0.4 * 110 + 0.2 * 80 + 0.2 * 70 + 0.2 * 65, 1)
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["recipe"] == "bookrecipe"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    slice_ = {"sections": {"recipe": v}}
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps(slice_)})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "How the books set his line" in h and "<td>dk</td>" in h and "Results weigh last game" in h
    assert "Reading · not measured yet" in h


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
