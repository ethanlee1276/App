"""College football, baseball and basketball say when their stats are behind.

The NFL's week-table check (engine/freshness.football_weeks) reached the
page on 2026-09-25 — Ethan: "if that shit's stale, then the user should know
that or we shouldn't show it." Asked to carry on with the rest, this is the
same question for the leagues whose `period` is a date: the last day played
against the latest day each table holds (engine/freshness.daily), stamped on
every board by its build (`stamp_board`) and said on the page.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, freshness as F                            # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _box(sport="nba", finals_through="2026-10-24", logs_through="2026-10-24"):
    c = db.connect(":memory:")
    games, logs = [], []
    for day in ("2026-10-22", "2026-10-23", "2026-10-24", "2026-10-26"):
        final = day <= finals_through
        games.append({"sport": sport, "season": 2026, "period": day, "game_id": f"A@B{day}",
                      "home": "B", "away": "A", "home_score": 100 if final else None,
                      "away_score": 99 if final else None, "date": day, "spread": 0.0,
                      "total": 220.0, "roof": "", "surface": "", "temp": None, "wind": None,
                      "extra": None})
        if day <= logs_through:
            logs.append({"sport": sport, "season": 2026, "period": day, "game_id": f"A@B{day}",
                         "player": "P", "team": "A", "opponent": "B", "position": "G", "home": 0,
                         "market": "points", "value": 20.0})
    db.upsert_games(c, games)
    db.upsert_player_logs(c, logs)
    return c


TODAY = datetime.date(2026, 10, 26)


def test_a_current_league_is_current():
    r = F.daily(_box(), "nba", TODAY)
    assert r["played"] == "2026-10-24" and r["unit"] == "day", r
    assert r["tables"] == {"results": "2026-10-24", "player stats": "2026-10-24"} and r["behind"] == []
    assert F.line(r).endswith("All current."), F.line(r)


def test_a_table_behind_the_last_day_played_is_named():
    r = F.daily(_box(logs_through="2026-10-22"), "nba", TODAY)
    assert r["behind"] == ["player stats"], r
    assert "BEHIND: player stats" in F.line(r)
    r = F.daily(_box(finals_through="2026-10-23"), "nba", TODAY)
    assert r["behind"] == ["results"], r


def test_the_grace_waits_for_the_nightly_ingest():
    # Played last night: not due until today's ingest has run.
    r = F.daily(_box(logs_through="2026-10-23"), "nba", datetime.date(2026, 10, 24))
    assert r["played"] == "2026-10-23" and r["behind"] == [], r
    # College's player logs come a week at a time: a game is due three days on.
    r = F.daily(_box("cfb", logs_through="2026-10-22"), "cfb", datetime.date(2026, 10, 25))
    assert r["played"] == "2026-10-22" and r["behind"] == [], r
    r = F.daily(_box("cfb", logs_through="2026-10-22"), "cfb", datetime.date(2026, 10, 27))
    assert r["played"] == "2026-10-24" and r["behind"] == ["player stats"], r


def test_baseball_checks_only_its_dated_table():
    r = F.daily(_box("mlb", logs_through="2026-10-01"), "mlb", TODAY)
    assert list(r["tables"]) == ["results"] and r["behind"] == [], \
        "MLB's player logs are keyed by game index, not date"


def test_an_empty_league_is_never_behind():
    r = F.daily(db.connect(":memory:"), "wnba", TODAY)
    assert r["played"] is None and r["behind"] == []


def test_every_build_stamps_it():
    for f, call in (("cfb_build.py", '_fresh.stamp_board(out, "cfb")'),
                    ("mlb_build.py", '_fresh.stamp_board(result, "mlb")'),
                    ("nba_build.py", '_fresh.stamp_board(out, str(out.get("sport") or "nba"))')):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert call in src, f
        assert src.index(call) < src.index("gate.publish(", src.index(call) - 400), f


def test_the_page_says_it_in_days():
    if not shutil.which("node"):
        return
    i = APP.index("function dataBehindHTML(")
    fn = APP[i:APP.index("\n}\n", i) + 2]
    prog = ("var escapeHtml=(s)=>String(s==null?'':s); var icon=()=>'';"
            "var formatGameDate=(s)=>'D('+s+')';"
            'const DATA_TABLE_WORDS = { "results": "final scores", "player stats": "player stats" };\n'
            + fn + "\nconsole.log(JSON.stringify(dataBehindHTML(" + json.dumps(
                {"played": "2026-10-24", "unit": "day",
                 "tables": {"results": "2026-10-24", "player stats": "2026-10-22"},
                 "behind": ["player stats"]}) + ").replace(/<[^>]+>/g, '')));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    text = " ".join(json.loads(out.stdout).split())
    assert text.startswith("Games through D(2026-10-24) are played, but our data isn’t all in yet: "
                           "player stats through D(2026-10-22)."), text
    assert "built without the latest games" in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
