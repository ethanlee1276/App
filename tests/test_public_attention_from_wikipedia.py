"""Public attention from Wikipedia's own page views — are the players everyone is reading about priced too high?

Ethan, 2026-10-16: "add everything now. 1-13" — idea 6: when a player's
page spikes, public money follows; if the book shades for it, his over is
the expensive side.

What these hold: his article is the first search hit that is his name or
his name with a parenthesis ("Josh Allen (quarterback)"), never a page that
merely contains it, and a failed search raises rather than read as "no
page"; the views call names the article with underscores and a day range,
and an article with no views (404) is an empty record; the attention ratio
is his last three days over his median day in the four weeks before, and
needs those days; the builds keep each board player current at most once a
day inside a few seconds; the ideas section only reads, and before the
first journal reads nothing; the bar is the under on spiked closes in the
last two seasons, 300 closes, every season above zero, with the line's
shading reported beside it; and the pick page shows the ratio and the
month, labelled. No test touches the network.

Run directly: `python3 tests/test_public_attention_from_wikipedia.py`
"""
import datetime as dt
import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import attention as A                                # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def test_his_article_is_his_name_not_a_page_that_mentions_it():
    hits = [{"title": "Allen Park, Michigan"}, {"title": "Josh Allen (quarterback)"}, {"title": "Josh Allen"}]
    assert A.pick_title(hits, "Josh Allen") == "Josh Allen (quarterback)"
    assert A.pick_title([{"title": "Joshua Allen Smith"}], "Josh Allen") is None
    asked = []

    def get(url):
        asked.append(url)
        return {"query": {"search": [{"title": "Puka Nacua"}]}}
    assert A.lookup_title("nfl", "Puka Nacua", get) == "Puka Nacua"
    assert "American%20football" in asked[0]

    def broken(url):
        raise urllib.error.URLError("down")
    try:
        A.lookup_title("nfl", "Puka Nacua", broken)
        raise AssertionError("a failed search must not read as 'no page'")
    except urllib.error.URLError:
        pass


def test_the_views_call_and_an_article_with_none():
    seen = []

    def get(url):
        seen.append(url)
        return {"items": [{"timestamp": "2026101500", "views": 1200}, {"timestamp": "2026101600", "views": 900}]}
    v = A.fetch_views("Josh Allen (quarterback)", "2026-10-15", "2026-10-16", get)
    assert v == {"2026-10-15": 1200, "2026-10-16": 900}
    assert "Josh_Allen_%28quarterback%29/daily/2026101500/2026101600" in seen[0]

    def gone(url):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)
    assert A.fetch_views("Nobody", "2026-10-15", "2026-10-16", gone) == {}


def _month(base=1000, spike=None, day="2026-10-19"):
    d = dt.date.fromisoformat(day)
    out = {(d - dt.timedelta(days=i)).isoformat(): base for i in range(1, 33)}
    for i in range(1, 4):
        if spike:
            out[(d - dt.timedelta(days=i)).isoformat()] = spike
    return out


def test_the_ratio_is_his_last_three_days_over_his_usual():
    a = A.ratio(_month(1000, 3000), "2026-10-19")
    assert a == {"ratio": 3.0, "recent": 3000, "usual": 1000, "spike": True}
    calm = A.ratio(_month(1000), "2026-10-19")
    assert calm["ratio"] == 1.0 and not calm["spike"]
    assert A.ratio({"2026-10-18": 5}, "2026-10-19") is None, "too few days is no reading"


def test_the_builds_keep_each_player_current_once_a_day():
    conn = sqlite3.connect(":memory:")
    calls = []

    def get(url):
        calls.append(url)
        if "srsearch" in url:
            return {"query": {"search": [{"title": "Puka Nacua"}]}}
        return {"items": [{"timestamp": "2026101500", "views": 800}]}
    real = A.PAUSE
    A.PAUSE = 0
    try:
        today = dt.date(2026, 10, 16)
        assert A.keep_current(conn, "nfl", ["Puka Nacua"], get, today) == 1
        conn.execute("INSERT OR REPLACE INTO pageviews VALUES ('Puka Nacua', '2026-10-15', 800)")
        assert A.keep_current(conn, "nfl", ["Puka Nacua"], get, today) == 0, "already current through yesterday"
        assert sum("srsearch" in c for c in calls) == 1, "the title is looked up once and kept"
        assert A.keep_current(conn, "nfl", ["Puka Nacua"], get, today, budget=-1) == 0, "the budget is honoured"
    finally:
        A.PAUSE = real


def test_the_section_only_reads_and_reads_nothing_before_the_first_journal():
    conn = sqlite3.connect(":memory:")
    sec = A.ideas_section([], [], {"recommendations": [{"player": "Puka Nacua"}]}, "nfl", conn=conn)
    assert sec["players"] == {} and sec["board_players"] == ["Puka Nacua"]
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='wiki_titles'").fetchone() is None, \
        "reading never creates a table"
    A.ensure_tables(conn)
    conn.execute("INSERT INTO wiki_titles VALUES ('nfl', 'Puka Nacua', 'Puka Nacua', '2026-10-16')")
    today = dt.date.today().isoformat()
    conn.executemany("INSERT INTO pageviews VALUES ('Puka Nacua', ?, ?)", list(_month(1000, 2500, today).items()))
    sec = A.ideas_section([], [], {"recommendations": [{"player": "Puka Nacua"}]}, "nfl", conn=conn)
    p = A.pick_view(sec, "Puka Nacua", "rec_yds")
    assert p["ratio"] == 2.5 and p["spike"] and len(p["days"]) == 30
    assert ID.SECTIONS["attention"] == "attention"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps({'sections': {'attention': p}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "How much the public is reading about him" in h and "2.5×" in h and "lb-spark" in h
    assert "far more than usual" in h


def test_the_bar_is_the_under_on_spiked_closes_in_the_last_two_seasons():
    rows = []
    for season in (2023, 2024, 2025):
        for i in range(200):
            spiked = i % 2 == 0
            over = 0 if (spiked and i % 4 == 0) else (i % 3 == 0)
            rows.append((season, "rec_yds", 60.5, 0.5, 3.0 if spiked else 1.0, int(over), 58.0 if spiked else 61.0))
    v = A.verdict(rows)
    assert v["test"] == [2024, 2025] and v["under_when_spiked"]["n"] == 200
    assert set(v["under_when_spiked"]["by_season"]) == {"2024", "2025"}
    assert v["line_minus_average"] == {"spiked": 2.5, "not": -0.5}
    assert not A.verdict(rows[:300])["holds"]


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
