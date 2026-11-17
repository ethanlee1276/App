"""Each game report keeps watch on the injury report and the news (2026-11-17).

Ethan, 2026-11-17: "make sure the game reports keep a constant watch and
update on nfl news and injuries". A report is rebuilt once a board sweep;
between builds engine/reportwatch looks every five minutes. What these hold:

  - the watch takes each board's games from six hours back to eight days
    ahead, and knows a club by its full name, its nickname or, for a
    college, its school without the mascot;
  - an injury designation that moved is an update ("Questionable to Out"),
    the first look at a league only remembers, and an unchanged one is
    never news;
  - a headline goes on a game's card when it is about one of its clubs
    (ESPN's own tags, or the names in the title), is from the last three
    days, and is not about half the league; injury and roster news is
    marked;
  - the free file it writes (report_watch.json, registered with the gate)
    holds each game's updates and headlines, and a feed that fails is said,
    never fatal;
  - the report's own "Latest news and injury moves" says them in words, and
    the page's card at the top shows what landed after the build, read
    again while the page is open;
  - the launcher runs the watch on its own thread.

    python3 tests/test_a_game_report_keeps_watch.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamereport as GR, gate, reportwatch as RW                  # noqa: E402
from engine.sources import espnnews                                            # noqa: E402

NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=dt.timezone.utc).timestamp()
REPORT_JS = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
DETAIL_JS = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
LAUNCH = (ROOT / "launch.py").read_text(encoding="utf-8")


def _iso(hours):
    return dt.datetime.fromtimestamp(NOW + hours * 3600, dt.timezone.utc).isoformat().replace("+00:00", "Z")


BOARD = {"games": [
    {"away": "KC", "home": "DEN", "kickoff": _iso(5)},           # this afternoon
    {"away": "BUF", "home": "MIA", "kickoff": _iso(-3)},          # under way
    {"away": "NE", "home": "NYJ", "kickoff": _iso(-30)},          # yesterday: no longer watched
    {"away": "GB", "home": "CHI", "kickoff": _iso(24 * 10)},      # too far ahead
]}


def _rows(rice="Questionable", hill="Questionable"):
    return [{"team": "Kansas City Chiefs", "player": "Rashee Rice", "pos": "WR", "status": rice, "injury": "Knee",
             "date": "2026-11-21T20:00Z", "comment": "Rice (knee) is listed as questionable."},
            {"team": "Miami Dolphins", "player": "Tyreek Hill", "pos": "WR", "status": hill, "injury": "Ankle"},
            {"team": "Green Bay Packers", "player": "Jordan Love", "pos": "QB", "status": "Out", "injury": "Shoulder"}]


def _news():
    return [{"title": "Chiefs rule out WR Rashee Rice for Sunday", "link": "https://espn.example/1", "source": "ESPN",
             "epoch": int(NOW - 1800), "teams": ["Kansas City Chiefs"], "athletes": ["Rashee Rice"]},
            {"title": "Broncos sign veteran pass rusher", "link": "https://espn.example/2", "source": "ESPN",
             "epoch": int(NOW - 7200), "teams": ["Denver Broncos"], "athletes": []},
            {"title": "Week 12 power rankings: Chiefs, Bills, Dolphins and Broncos climb",
             "link": "https://espn.example/3", "source": "ESPN", "epoch": int(NOW - 600),
             "teams": ["Kansas City Chiefs", "Buffalo Bills", "Miami Dolphins", "Denver Broncos"], "athletes": []},
            {"title": "Old news about the Chiefs", "link": "https://espn.example/4", "source": "ESPN",
             "epoch": int(NOW - 4 * 86400), "teams": ["Kansas City Chiefs"], "athletes": []}]


def _rss():
    return [{"title": "Tyreek Hill limited again as Dolphins prepare for Bills", "link": "https://cbs.example/9",
             "source": "CBS Sports", "epoch": int(NOW - 3600)},
            {"title": "A story about nobody on the slate", "link": "https://cbs.example/10", "source": "CBS Sports",
             "epoch": int(NOW - 3600)}]


def _run(state, rows, news=None, rss=None, boom=False):
    def bad(_league):
        raise RuntimeError("feed down")
    return RW.run(now=NOW, leagues=("nfl",), boards={"nfl": BOARD}, state_path=state, publish=False,
                  fetch_injuries=(bad if boom else (lambda _l: rows)),
                  fetch_news=(lambda _l: news if news is not None else _news()),
                  fetch_rss=(lambda _l: rss if rss is not None else _rss()))


def test_the_watch_takes_this_weeks_games_and_knows_each_club():
    games = RW.watched_games(BOARD, NOW)
    assert [g["key"] for g in games] == ["KC@DEN", "BUF@MIA"], games
    table = RW.team_table("nfl", games)
    assert RW.code_of("Kansas City Chiefs", table) == "KC" and table.get("chiefs") == "KC"
    college = RW.team_table("cbb", [{"names": {"DUKE": "Duke", "UNC": "North Carolina"}}])
    assert RW.code_of("Duke Blue Devils", college) == "DUKE"
    assert RW.code_of("North Carolina Tar Heels", college) == "UNC"
    assert RW.code_of("Gonzaga Bulldogs", college) is None


def test_the_nfls_bare_eastern_clock_is_read_beside_its_date():
    """The NFL's board carries "20:15" beside "2026-11-19", not a stamp: the
    first version read only a stamp, and on its first morning live it held
    every league's games but the NFL's (17 November)."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    kick = dt.datetime(2026, 11, 19, 20, 15, tzinfo=ZoneInfo("America/New_York")).timestamp()
    board = {"games": [{"away": "IND", "home": "HOU", "date": "2026-11-19", "kickoff": "20:15"},
                       {"away": "MIA", "home": "BUF", "date": "2026-12-20", "kickoff": "13:00"},
                       {"away": "TB", "home": "DET", "kickoff": "2026-11-19T18:00:00Z"}]}
    assert RW.kickoff_epoch(board["games"][0]) == kick
    got = RW.watched_games(board, kick - 2 * 86400)
    assert [g["key"] for g in got] == ["IND@HOU", "TB@DET"], got
    assert RW.watched_games(board, kick + 7 * 3600) == [], "six hours after kickoff it is let go"


def test_a_designation_that_moved_is_an_update_and_the_first_look_only_remembers():
    state = Path(tempfile.mkdtemp()) / "state.json"
    first = _run(state, _rows())
    assert first["leagues"]["nfl"]["games"]["KC@DEN"]["updates"] == [], "a status already true is not news"
    second = _run(state, _rows(rice="Out"))
    ups = second["leagues"]["nfl"]["games"]["KC@DEN"]["updates"]
    assert [(u["player"], u["from"], u["to"], u["team"]) for u in ups] == [("Rashee Rice", "Questionable", "Out", "KC")]
    assert second["leagues"]["nfl"]["games"]["BUF@MIA"]["updates"] == [], "unchanged is never news"
    # Kept for the week, and a further move adds to it.
    third = _run(state, _rows(rice="Out", hill="Out"))
    assert [u["player"] for u in third["leagues"]["nfl"]["games"]["BUF@MIA"]["updates"]] == ["Tyreek Hill"]
    assert [u["to"] for u in third["leagues"]["nfl"]["games"]["KC@DEN"]["updates"]] == ["Out"]


def test_a_headline_goes_on_its_games_card_and_league_wide_pieces_do_not():
    state = Path(tempfile.mkdtemp()) / "state.json"
    doc = _run(state, _rows())
    kc = doc["leagues"]["nfl"]["games"]["KC@DEN"]["news"]
    assert [n["title"] for n in kc] == ["Chiefs rule out WR Rashee Rice for Sunday", "Broncos sign veteran pass rusher"]
    assert [n["flag"] for n in kc] == ["injury", "roster"]
    assert kc[0]["teams"] == ["KC"] and kc[0]["players"] == ["Rashee Rice"] and kc[0]["at"].endswith("Z")
    mia = doc["leagues"]["nfl"]["games"]["BUF@MIA"]["news"]
    assert [n["title"] for n in mia] == ["Tyreek Hill limited again as Dolphins prepare for Bills"], \
        "an untagged headline is read for the clubs' names"
    assert mia[0]["flag"] == "injury" and set(mia[0]["teams"]) == {"MIA", "BUF"}


def test_a_feed_that_fails_is_said_and_costs_nothing_else():
    state = Path(tempfile.mkdtemp()) / "state.json"
    doc = _run(state, _rows(), boom=True)
    nfl = doc["leagues"]["nfl"]
    assert nfl["notes"] == ["injury report not read: RuntimeError"]
    assert nfl["games"]["KC@DEN"]["news"], "the news still read"
    # The first good read after a failure is still only remembered.
    assert _run(state, _rows(rice="Out"))["leagues"]["nfl"]["games"]["KC@DEN"]["updates"] == []


def test_the_free_file_is_registered_and_written_through_the_gate():
    assert "report_watch.json" in gate.FREE_FILES and "report_watch.json" in gate.KNOWN_BOARDS
    assert gate.is_free("report_watch.json")
    src = (ROOT / "engine" / "reportwatch.py").read_text(encoding="utf-8")
    assert 'gate.publish(out, out_path or WATCH_PATH, "report_watch.json")' in src


def test_espns_newsroom_is_read_by_its_tags_and_never_its_text():
    payload = {"articles": [
        {"headline": "Chiefs' Rice out", "description": "ESPN's own words, never read",
         "links": {"web": {"href": "https://www.espn.com/nfl/story/_/id/1"}}, "published": "2026-11-22T14:30:00Z",
         "categories": [{"type": "league", "description": "NFL"},
                        {"type": "team", "description": "Kansas City Chiefs"},
                        {"type": "athlete", "athlete": {"description": "Rashee Rice"}}]},
        {"headline": "", "links": {"web": {"href": "https://x"}}},
        {"headline": "No link", "links": {}}]}
    got = espnnews.parse(payload)
    assert got == [{"title": "Chiefs' Rice out", "link": "https://www.espn.com/nfl/story/_/id/1", "source": "ESPN",
                    "epoch": int(dt.datetime(2026, 11, 22, 14, 30, tzinfo=dt.timezone.utc).timestamp()),
                    "teams": ["Kansas City Chiefs"], "athletes": ["Rashee Rice"]}]
    assert all("ESPN's own words" not in json.dumps(r) for r in got), "the story's text is never taken"


def test_the_report_says_the_watch_in_words():
    state = Path(tempfile.mkdtemp()) / "state.json"
    _run(state, _rows())
    doc = _run(state, _rows(rice="Out"))
    keep = GR._watch_doc
    GR._watch_doc = lambda: doc
    try:
        c = GR.Ctx({"away": "KC", "home": "DEN"}, {}, sport="nfl", names={"KC": "Chiefs", "DEN": "Broncos"})
        sec = GR.sec_news(c)
        empty = GR.sec_news(GR.Ctx({"away": "GB", "home": "CHI"}, {}, sport="nfl", names={}))
    finally:
        GR._watch_doc = keep
    assert sec["key"] == "news" and sec["title"] == "Latest news and injury moves"
    items = next(b for b in sec["blocks"] if b.get("type") == "list")["items"]
    assert items[0] == "Rashee Rice, the Chiefs' wide receiver: questionable to out (knee), seen Sun 10:00 AM ET.", items
    heads = next(b for b in sec["blocks"] if b.get("type") == "headlines")["items"]
    assert heads[0] == {"headline": "Chiefs rule out WR Rashee Rice for Sunday", "href": "https://espn.example/1",
                        "source": "ESPN", "at": heads[0]["at"], "flag": "injury"}
    assert empty is None, "nothing seen, no section"
    # A publisher's headline is never rewritten by the plain-words pass.
    assert {"headline", "source", "at", "flag", "href"} <= GR.PLAIN_SKIP
    assert GR.et_words("2026-11-22T17:05:00Z") == "Sun 12:05 PM"


def test_the_page_draws_the_watch_and_reads_it_again():
    assert 'if (b.type === "headlines") return newsListHTML(b.items || []);' in REPORT_JS
    assert "function watchCardHTML(w, since)" in REPORT_JS and "Since this report was written" in REPORT_JS
    assert "watchCardHTML(extras.watch, r.watch_at)" in REPORT_JS
    assert 'target="_blank" rel="noopener noreferrer"' in REPORT_JS
    assert "function reportWatchFor(g, sport)" in DETAIL_JS and 'fetch("data/report_watch.json", { cache: "no-cache" })' in DETAIL_JS
    assert "const RWATCH_MS = 120000;" in DETAIL_JS
    for rule in (".gr-watch {", ".gr-watch-ups li.down", ".gr-news {", ".gr-news-flag {"):
        assert rule in CSS, rule
    assert '"watch_at": (_watch_doc() or {}).get("generated_at") or ""' in (ROOT / "engine" / "gamereport.py").read_text()


def test_the_launcher_runs_the_watch_on_its_own_thread():
    assert "def _report_watcher() -> None:" in LAUNCH
    body = LAUNCH[LAUNCH.index("def _report_watcher() -> None:"):]
    body = body[:body.index("\ndef ")]
    assert "_rw.run()" in body and "time.sleep(_rw.WATCH_EVERY_S)" in body and "except Exception" in body
    assert 'threading.Thread(target=_report_watcher, daemon=True, name="reportwatch").start()' in LAUNCH
    assert RW.WATCH_EVERY_S == 300


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
