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


def test_a_past_weeks_reports_stay_apart_by_their_games_day():
    rows = [{"Team": "Ohio State", "Player": "Jeremiah Smith", "Date": "11/21/2026", "Wed": "Out", "Game Day": "Out"},
            {"Team": "Ohio State", "Player": "Caleb Downs", "Date": "2026-11-14", "Game Day": "Available"}]
    got = R.filings({"data": rows, "report_days": ["Wed", "Game Day"]}, "B10", CA._ts("2026-11-23T21:00:00Z"))
    assert sorted((f["kickoff"], f["players"][0]["player"]) for f in got) == [
        ("2026-11-14", "Caleb Downs"), ("2026-11-21", "Jeremiah Smith")]


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


def _report(post_day, post_time, kick_day, kick_time, kind="Report Pending", rows=None, zone="CT"):
    return {"ReportType": kind, "conferenceTimeZone": zone, "publishDate": post_day, "postedTime": post_time,
            "footer": {"date": kick_day, "time": kick_time, "location": "Iowa City, IA"},
            "games": [{"teamName": "Nebraska", "teamDisplayName": "Nebraska", "rows": rows or []},
                      {"teamName": "Iowa", "teamDisplayName": "Iowa", "rows": []}]}


def test_each_conference_is_read_on_its_own_reports_clock():
    """The first live read (21:47 UTC, 23 November): Nebraska at Iowa's report "Report Pending", posting
    2026-11-24 at 19:00 CT, kickoff 2026-11-27 at 11:00 CT. The reader is due two minutes after the post and 85 and
    40 minutes before the kickoff, and only the conference whose time came is read."""
    doc = {"10003526": _report("2026-11-24", "19:00:00", "2026-11-27", "11:00:00"), "_nextReportDate": "x"}
    now = CA._ts("2026-11-23T21:47:12Z")
    assert R.due_times(doc, now) == [CA._ts("2026-11-25T01:02:00Z"), CA._ts("2026-11-27T15:35:00Z"),
                                     CA._ts("2026-11-27T16:20:00Z")]
    assert R.filings(doc, "B10", now) == [], "a pending report is no filing"
    asked = []

    def post(u, b):
        asked.append(b["conference"])
        return "ok", "application/json", json.dumps(doc).encode()
    tmp = Path(tempfile.mkdtemp())
    just_read = CA._ts("2026-11-25T00:20:00Z")                    # the safety net read every conference then
    R._LAST.update(at={c: just_read for c in R.CONFS}, archive=just_read)
    R._NEXT.clear()
    R._NEXT["B10"] = R.due_times(doc, now)
    assert R.read_once(now=CA._ts("2026-11-25T00:30:00Z"), post=post, out=tmp / "c.json",
                       seen_out=tmp / "s.json") <= R.IDLE_S and asked == []
    R.read_once(now=CA._ts("2026-11-25T01:03:00Z"), post=post, out=tmp / "c.json", seen_out=tmp / "s.json")
    assert asked == ["B10"], "only the conference whose report posted"
    seen = json.loads((tmp / "s.json").read_text())
    assert seen["conferences"]["B10"]["reports"][0] == {"type": "Report Pending", "posts": "2026-11-24 19:00:00",
                                                        "kickoff": "2026-11-27 11:00:00",
                                                        "teams": ["Nebraska", "Iowa"], "rows": [0, 0]}


def test_a_posted_report_is_dated_by_its_own_post_time():
    rows = [{"Player": "Dylan Raiola", "Number": "#15", "Status": "Questionable"}]
    doc = {"1": _report("2026-11-24", "19:00:00", "2026-11-27", "11:00:00", kind="Initial", rows=rows)}
    got = R.filings(doc, "B10", CA._ts("2026-11-25T03:00:00Z"))
    assert [(f["school"], f["filed_at"], f["kickoff"], f["players"][0]["word"]) for f in got] == [
        ("Nebraska", "2026-11-25T01:00:00Z", "2026-11-27 11:00:00", "Questionable")]
    assert got[0]["seen"] is False


def test_the_archives_rows_read_game_day_over_the_updates():
    """The archive's rows, as the first live read returned them (21:47 UTC): their columns come in alphabetical
    order, so Game Day sits before Initial and Update 2 last; the game is the row's Week."""
    row = {"Game Day": "Out", "Initial": "Doubtful", "Number": "#1", "Opponent": "at Ohio St.",
           "OpponentDisplay": "at Ohio State", "Player": "Jayshon Platt", "Team": "Illinois", "TeamDisplay": "Illinois",
           "Update 1": "Doubtful", "Update 2": "Doubtful", "Week": "Sat, 26 Sep 2026 00:00:00 GMT", "WeekNum": 4}
    early = dict(row, **{"Game Day": "", "Player": "Pending Man", "Update 2": "Questionable"})
    doc = {"data": [row, early, dict(row, Week="Sat, 03 Oct 2026 00:00:00 GMT", Player="Another Week")],
           "report_days": ["Initial", "Update 1", "Update 2", "Game Day"], "loaded": True}
    got = R.filings(doc, "B10", CA._ts("2026-11-23T21:47:12Z"))
    words = {(f["kickoff"], p["player"]): p["word"] for f in got for p in f["players"]}
    assert words == {("2026-09-26", "Jayshon Platt"): "Out", ("2026-09-26", "Pending Man"): "Questionable",
                     ("2026-10-03", "Another Week"): "Out"}
    assert {f["game"] for f in got} == {"at Ohio St."}


def test_a_read_writes_the_cache_and_what_it_saw():
    tmp = Path(tempfile.mkdtemp())
    body = json.dumps([{"school": "Clemson", "player": "Cade Klubnik", "status": "Probable",
                        "updated_at": "2026-11-26T00:00:00Z"}]).encode()
    asked = []

    def post(u, b):
        asked.append((u.rsplit("/", 1)[-1], b["conference"]))
        assert b == {"sport": "Football", "organization": b["conference"], "conference": b["conference"]}
        return ("ok", "application/json", body) if b["conference"] == "ACC" else ("HTTP 404", "", b"")
    R._LAST.update(at={}, archive=0.0)
    R._NEXT.clear()
    R.read_once(now=CA._ts("2026-11-26T01:00:00Z"), post=post, out=tmp / "c.json", seen_out=tmp / "s.json",
                checker=lambda archive: {"acc": {"filings": len(archive)}})
    assert asked == [("get-publish-public", c) for c in R.CONFS] + [("get-archive-public", c) for c in R.CONFS]
    asked.clear()
    R._LAST["at"] = {}
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
                "kickoff": "2026-11-21 12:00",
                "players": [{"player": "Anyway, Played", "word": "Out"}, {"player": "Sat Out", "word": "Out"},
                            {"player": "Was Available", "word": "Available"},
                            {"player": "Never Logged", "word": "Questionable"}]},
               {"conference": "b10", "school": "Nowhere State", "filed_at": "2026-11-19T23:00:00Z", "players": []},
               # An earlier filing the school's last one replaced: never held to the game.
               {"conference": "b10", "school": "The Ohio State University", "filed_at": "2026-11-18T23:00:00Z",
                "kickoff": "2026-11-21 12:00", "players": [{"player": "Was Available", "word": "Out"}]},
               # A filing read with the read's own time, held to its own game's day (24 October), not the read's.
               {"conference": "b10", "school": "Ohio State", "filed_at": "2026-11-23T21:00:00Z",
                "kickoff": "2026-10-24", "players": [{"player": "Sat Out", "word": "Out"}]}]
    got = R.check_archive(archive, conn, {"ohio state": "OSU"})["b10"]
    assert (got["filings"], got["keyed"], got["men"], got["known"]) == (3, 2, 5, 4)
    assert (got["out"], got["out_played"], got["avail"], got["avail_played"]) == (3, 2, 1, 1)
    assert got["contradicted"] == ["The Ohio State University: Anyway, Played (2026-11-19T23:00:00Z)",
                                   "Ohio State: Sat Out (2026-11-23T21:00:00Z)"]


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
