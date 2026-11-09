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


def _wiki(calls, behind=("Nobody Reads",)):
    """A Wikipedia that has not published yesterday yet: every article's
    views stop the day before it, and an article nobody reads answers 404."""
    import urllib.parse

    def get(url):
        calls.append(url)
        if "srsearch" in url:
            name = urllib.parse.unquote(url.split("srsearch=")[1]).replace(" American football", "")
            return {"query": {"search": [{"title": name}]}}
        if any(b.replace(" ", "_") in url for b in behind):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        return {"items": [{"timestamp": "2026101400", "views": 800}]}
    return get


def test_a_title_short_of_yesterday_waits_for_the_recheck_and_the_next_man_gets_his_turn():
    """The NFL build's journal took 8.4 of its readings' 30 seconds at 10:12
    on 9 November: a man whose views stop short of yesterday was asked again
    on every build, the board's first names first, until the budget ran out."""
    conn = sqlite3.connect(":memory:")
    calls, t = [], [1_800_000_000.0]
    get, clock = _wiki(calls), (lambda: t[0])
    views = lambda: len([c for c in calls if "/pageviews/" in c])     # noqa: E731
    real = A.PAUSE
    A.PAUSE = 0
    try:
        today = dt.date(2026, 10, 16)
        assert A.keep_current(conn, "nfl", ["Nobody Reads", "Puka Nacua"], get, today, clock=clock) == 2
        assert views() == 2 and conn.execute("SELECT MAX(date) FROM pageviews").fetchone()[0] == "2026-10-14"
        t[0] += 600
        assert A.keep_current(conn, "nfl", ["Nobody Reads", "Puka Nacua", "Kyren Williams"], get, today,
                              clock=clock) == 1, "the two asked ten minutes ago wait; the next man is asked"
        assert views() == 3 and "Kyren_Williams" in calls[-1]
        t[0] += A.RECHECK_SECONDS
        assert A.keep_current(conn, "nfl", ["Nobody Reads", "Puka Nacua"], get, today, clock=clock) == 2, \
            "past the recheck they are asked again"
        assert views() == 5
        t[0] += 60
        conn.execute("INSERT OR REPLACE INTO pageviews VALUES ('Puka Nacua', '2026-10-15', 900)")
        t[0] += A.RECHECK_SECONDS
        assert A.keep_current(conn, "nfl", ["Puka Nacua"], get, today, clock=clock) == 0, \
            "current through yesterday: not asked, recheck or not"
        assert sum("srsearch" in c for c in calls) == 3, "each title looked up once and kept"
    finally:
        A.PAUSE = real


def _old_reading(conn, title, today):
    """What the section read before 9 November: every stored day."""
    views = A.stored_views(conn, title)
    a = A.ratio(views, today)
    return a and {**a, "title": title, "days": [v for _d, v in sorted(views.items())[-30:]]}


def test_the_reading_reads_only_its_month_and_reads_the_same():
    """Every stored day of every board player (seasons of backfill each) was
    6.9 of the NFL readings' 30 seconds at 10:12 on 9 November; the reading
    looks at a month."""
    conn = sqlite3.connect(":memory:")
    A.ensure_tables(conn)
    d0 = dt.date.today()
    today = d0.isoformat()
    day = lambda i: (d0 - dt.timedelta(days=i)).isoformat()             # noqa: E731
    men = {
        # three seasons kept, the last month whole
        "Puka Nacua": {day(i): 500 + (i * 37) % 900 for i in range(1, 1100)},
        # a spike over a quiet month with a few days left out
        "Jake Bobo": {day(i): (2400 if i <= 3 else 300 + i % 7) for i in range(1, 400) if i <= 3 or i % 5},
        # read about so little that half his month's days are left out, so
        # his newest thirty stored days reach back past it: still thirty drawn
        "Rarely Read": {day(i): 40 + i % 9 for i in range(1, 800) if i <= 3 or i % 2 == 0},
        # too few days in his month for a reading at all
        "Nobody Reads": {day(i): 3 + i % 4 for i in range(1, 800) if i % 4 == 0 or i <= 3},
        # a day stored ahead of today (a clock that moved) is read as before
        "Davante Adams": {**{day(i): 9000 for i in range(1, 60)}, day(-1): 12000},
    }
    for p, views in men.items():
        conn.execute("INSERT INTO wiki_titles VALUES ('nfl', ?, ?, ?)", (p, p, today))
        conn.executemany("INSERT INTO pageviews VALUES (?, ?, ?)", [(p, d, v) for d, v in views.items()])
    sec = A.ideas_section([], [], {"recommendations": [{"player": p} for p in men]}, "nfl", conn=conn)
    for p in men:
        assert sec["players"].get(p) == (_old_reading(conn, p, today) or None), p
        assert len(A.recent_views(conn, p, today)) <= A.RECENT + A.BASELINE + 2 + A.SHOWN_DAYS
    assert sec["players"]["Jake Bobo"]["spike"] and len(sec["players"]["Puka Nacua"]["days"]) == 30
    rare = A.recent_views(conn, "Rarely Read", today)
    assert len(sec["players"]["Rarely Read"]["days"]) == 30 and min(rare) < day(A.RECENT + A.BASELINE), \
        "his newest thirty reach past the month and are all read"
    assert "Nobody Reads" not in sec["players"], "too few days in his month is no reading, as before"


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
