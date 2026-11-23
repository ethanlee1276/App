"""The box reads the conferences' availability reports (decision 20, step ADC).

The sixth look found all four Power 4 conferences' football reports in one vendor's public report
(app.hdintelligence.com). engine/cfbavailread reads each conference's current report on a clock set to when
they post, finds each school's filing in whatever shape the data comes in, and keeps the filings in
data/cfb_availability.json, which college injuries and the Injuries page lay over ESPN's board.

Run directly: `python3 tests/test_the_box_reads_the_conferences_availability_reports.py`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cfbavailread as R                  # noqa: E402
from engine.sources import cfbavail as CA             # noqa: E402


def _et(s):
    """An Eastern wall time as epoch seconds."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("America/New_York")).timestamp()


def test_the_clock_reads_often_when_reports_post_and_seldom_otherwise():
    assert R.due_every(_et("2026-11-28T11:00")) == R.GAME_DAY_S, "Saturday, from 9 AM"
    assert R.due_every(_et("2026-11-28T07:00")) == R.QUIET_S, "Saturday before 9"
    assert R.due_every(_et("2026-11-25T19:30")) == R.EVENING_S, "a weekday evening"
    assert R.due_every(_et("2026-11-25T11:00")) == R.QUIET_S, "a weekday morning"
    assert R.due_every(_et("2026-11-27T12:00"), game_days={"2026-11-27"}) == R.GAME_DAY_S, "Black Friday's games"
    assert R.due_every(_et("2026-11-29T12:00")) == R.QUIET_S, "Sunday"


def test_each_schools_filing_is_found_in_any_shape():
    nested = {"reports": [{"game": "Ohio State at Michigan", "published_at": "2026-11-25T23:00:00Z",
                           "report_type": "Initial",
                           "teams": [{"name": "Ohio State", "players": [
                               {"name": "Smith, Jeremiah", "position": "WR", "status": "Questionable"}]},
                               {"name": "Michigan", "players": [
                                   {"name": "Underwood, Bryce", "position": "QB", "status": "Available"}]}]}]}
    got = R.filings(nested, "B10", 0)
    assert [(f["school"], f["filed_at"], f["players"][0]["word"]) for f in got] == [
        ("Ohio State", "2026-11-25T23:00:00Z", "Questionable"), ("Michigan", "2026-11-25T23:00:00Z", "Available")]
    assert got[0]["conference"] == "b10" and got[0]["game"] == "Ohio State at Michigan"
    flat = [{"school": "Clemson", "player": "Cade Klubnik", "position": "QB", "status": "Probable",
             "updated_at": "2026-11-26T00:00:00Z"}]
    assert R.filings(flat, "ACC", 0)[0]["players"] == [{"player": "Cade Klubnik", "pos": "QB", "word": "Probable"}]
    keyed = {"data": {"Ohio State": [{"player": "Caleb Downs", "status": "Out"}]}}
    assert R.filings(keyed, "B10", 0)[0]["school"] == "Ohio State"
    parts = {"teams": [{"team": {"name": "Alabama", "abbreviation": "ALA"},
                        "athletes": [{"firstName": "Ty", "lastName": "Simpson", "availability": {"label": "Out"}}]}]}
    f = R.filings(parts, "SEC", 0)[0]
    assert f["school"] == "Alabama" and f["players"][0]["player"] == "Ty Simpson"
    final = {"game": "X at Y", "type": "Game Day", "updated_at": "2026-11-28T15:30:00Z",
             "teams": [{"name": "Y", "players": [{"name": "A B", "status": "Game Time Decision"}]}]}
    assert R.filings(final, "B12", 0)[0]["final"] is True
    assert R.filings({"title": "Football", "status": "published"}, "B12", 0) == [], "no rows, no filing"


def test_the_vendors_own_shape_reads_each_schools_last_column():
    """The vendor's sort helper (sortReportsByKickoff) reads an object of reports keyed by id, each with a footer
    holding its game's date and time, and "_" keys beside them; a table with a column per report reads its last
    column as the man's word, and the footer is the game, never the filing."""
    doc = {"101": {"footer": {"date": "2026-11-28", "time": "12:00"},
                   "home": {"name": "Ohio State", "players": [
                       {"Player": "Jeremiah Smith", "Position": "WR", "Thursday": "Questionable", "Friday": "Out",
                        "Thursday_id": 9}]},
                   "away": {"name": "Michigan", "players": [{"Player": "Bryce Underwood", "Wednesday": "Probable"}]}},
           "_nextReportDate": "2026-11-26"}
    got = R.filings(doc, "B10", CA._ts("2026-11-27T01:00:00Z"))
    assert [(f["school"], f["players"][0]["player"], f["players"][0]["word"]) for f in got] == [
        ("Ohio State", "Jeremiah Smith", "Out"), ("Michigan", "Bryce Underwood", "Probable")]
    assert got[0]["kickoff"] == "2026-11-28 12:00" and got[0]["filed_at"] == "2026-11-27T01:00:00Z"
    assert got[0]["players"][0]["pos"] == "WR"


def test_a_row_with_no_time_of_its_own_takes_the_reads():
    got = R.filings([{"school": "Clemson", "player": "A B", "status": "Out"}], "ACC", 1795000000)
    assert got[0]["filed_at"] == "2026-11-18T11:06:40Z"


def test_the_cache_keeps_one_of_each_filing_and_nothing_old():
    now = CA._ts("2026-11-26T12:00:00Z")
    old = {"conference": "acc", "school": "Clemson", "filed_at": "2026-11-10T00:00:00Z", "players": []}
    kept = {"conference": "acc", "school": "Clemson", "filed_at": "2026-11-25T23:00:00Z",
            "players": [{"player": "A", "word": "Out"}]}
    again = dict(kept, players=[{"player": "A", "word": "Doubtful"}])
    cache = R.merge({"reports": [old, kept]}, [again], now)
    assert cache["reports"] == [again]


def test_an_unchanged_filing_keeps_the_time_it_was_first_seen():
    def seen(at, word, kick="2026-11-28 12:00"):
        return {"conference": "b10", "school": "Ohio State", "kickoff": kick, "filed_at": at, "seen": True,
                "players": [{"player": "Jeremiah Smith", "word": word}]}
    now = CA._ts("2026-11-27T12:00:00Z")
    cache = R.merge({}, [seen("2026-11-25T23:10:00Z", "Questionable")], now)
    cache = R.merge(cache, [seen("2026-11-25T23:30:00Z", "Questionable")], now)
    assert [r["filed_at"] for r in cache["reports"]] == ["2026-11-25T23:10:00Z"], "the same filing, read again"
    cache = R.merge(cache, [seen("2026-11-26T23:30:00Z", "Out")], now)
    assert [r["filed_at"] for r in cache["reports"]] == ["2026-11-25T23:10:00Z", "2026-11-26T23:30:00Z"]
    cache = R.merge(cache, [seen("2026-11-27T00:00:00Z", "Out")], now)
    assert len(cache["reports"]) == 2, "unchanged since the last one"
    cache = R.merge(cache, [seen("2026-11-27T00:00:00Z", "Out", kick="2026-12-05 20:00")], now)
    assert len(cache["reports"]) == 3, "another game's filing is its own"


def test_a_read_writes_the_cache_and_what_it_saw():
    tmp = Path(tempfile.mkdtemp())
    body = json.dumps([{"school": "Clemson", "player": "Cade Klubnik", "status": "Probable",
                        "updated_at": "2026-11-26T00:00:00Z"}]).encode()
    asked = []

    def post(u, b):
        asked.append((u.rsplit("/", 1)[-1], b["conference"]))
        assert b == {"sport": "Football", "organization": b["conference"], "conference": b["conference"]}
        return ("ok", "application/json", body) if b["conference"] == "ACC" else ("HTTP 404", "", b"")
    R._LAST.update(at=0.0, archive=0.0)
    R.read_once(now=CA._ts("2026-11-26T01:00:00Z"), post=post, out=tmp / "c.json", seen_out=tmp / "s.json",
                checker=lambda archive: {"acc": {"filings": len(archive)}})
    assert asked == [(k, c) for c in R.CONFS for k in ("get-publish-public", "get-archive-public")]
    asked.clear()
    R._LAST["at"] = 0.0
    R.read_once(now=CA._ts("2026-11-26T02:00:00Z"), post=post, out=tmp / "c.json", seen_out=tmp / "s.json",
                checker=lambda archive: 1 / 0)
    assert asked == [("get-publish-public", c) for c in R.CONFS], "the archive, 6-hourly"
    cache = json.loads((tmp / "c.json").read_text())
    assert [r["school"] for r in cache["reports"]] == ["Clemson"] and cache["read_at"]
    seen = json.loads((tmp / "s.json").read_text())
    assert seen["conferences"]["ACC"]["filings"] == 1 and seen["conferences"]["SEC"]["status"] == "HTTP 404"
    assert seen["conferences"]["ACC"]["shape"][0] == 1, "the answer's shape, for checking the reading"
    assert seen["check"] == {"acc": {"filings": 1}} and seen["trusted"] is False, "the first read's check, kept"
    assert R.BASE == "https://app.hdintelligence.com" and R.DATA == {"report": "/api/get-publish-public",
                                                                    "archive": "/api/get-archive-public"}


def test_the_check_holds_past_reports_to_the_games_box_scores():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, player TEXT,"
                 " team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, date TEXT)")
    conn.execute("INSERT INTO games VALUES ('cfb', 2026, '13', 'g1', '2026-11-21')")
    for name in ("Played Anyway", "Was Available"):
        conn.execute("INSERT INTO player_game_logs VALUES ('cfb', 2026, '13', 'g1', ?, 'OSU', 'MICH', 'WR', 1,"
                     " 'rec_yds', 40)", (name,))
    conn.execute("INSERT INTO player_game_logs VALUES ('cfb', 2026, '9', 'g0', 'Sat Out', 'OSU', 'PSU', 'RB', 1,"
                 " 'rush_yds', 10)")
    conn.execute("INSERT INTO games VALUES ('cfb', 2026, '9', 'g0', '2026-10-24')")
    archive = [{"conference": "b10", "school": "The Ohio State University", "filed_at": "2026-11-19T23:00:00Z",
                "players": [{"player": "Anyway, Played", "word": "Out"}, {"player": "Sat Out", "word": "Out"},
                            {"player": "Was Available", "word": "Available"},
                            {"player": "Never Logged", "word": "Questionable"}]},
               {"conference": "b10", "school": "Nowhere State", "filed_at": "2026-11-19T23:00:00Z", "players": []},
               # An earlier filing the school's last one replaced: never held to the game.
               {"conference": "b10", "school": "The Ohio State University", "filed_at": "2026-11-18T23:00:00Z",
                "players": [{"player": "Was Available", "word": "Out"}]}]
    got = R.check_archive(archive, conn, {"ohio state": "OSU"})["b10"]
    assert (got["filings"], got["keyed"], got["men"], got["known"]) == (2, 1, 4, 3)
    assert (got["out"], got["out_played"], got["avail"], got["avail_played"]) == (2, 1, 1, 1)
    assert got["contradicted"] == ["The Ohio State University: Anyway, Played (2026-11-19T23:00:00Z)"]


def test_nothing_reaches_picks_or_the_injuries_page_until_the_reading_is_checked():
    import os
    assert CA.TRUSTED is False and not CA.on()
    os.environ[CA.ENV] = "on"
    try:
        assert CA.on(), "the switch can put it on without a deploy"
    finally:
        os.environ.pop(CA.ENV)


def test_it_asks_as_a_plain_reader_and_has_a_switch():
    assert R.AGENT == "availability-reader/1.0" and "qellys" not in R.AGENT.lower()
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert "def _cfb_avail_reader()" in src and 'name="cfbavailread"' in src
    import os
    os.environ[R.ENV] = "off"
    try:
        assert not R.on()
    finally:
        os.environ.pop(R.ENV)
    assert R.on()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
