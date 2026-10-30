"""Every game on every team's schedule opens its own page (engine/gamearchive,
the /api/game route, js/more.js openPastGame, js/detail.js pbpArchived,
js/gamecast.js scoringHTML).

Ethan, 2026-10-30, three screenshots of ESPN's Panthers–Packers final (the
game leaders, the scoring plays a quarter at a time with each drive's
summary, the box score and team stats tabs): "one thing we need to add is
being able to see game history for each team. We should be able to go to
each specific game and see all this type of data that espn offers. So add
these pages for every sport for each team."

The game page existed and the games did not: the live loops write a game's
file while it is on and prune it a day and a half later, so a schedule's
earlier games opened the opponent instead. What these hold:

  * the server finds a past game on its day by its two sides — the day asked
    for first and its answer final, a neighbouring day only when that day
    answered without it, never for baseball (a series repeats the matchup),
    a doubleheader's leg by our own id — and refuses a malformed question;
  * its page is the live page's own document, from the same builder, and a
    final is kept so the second reader costs nothing;
  * the route is free like the play-by-play files, and says 400, 404 or 503;
  * every game played on a team's schedule, on any season's chips and on the
    Versus tab opens it, by tap or by keyboard, and comes back to the team;
  * the game page falls back to it when the live file is gone;
  * the Gamecast tab carries ESPN's scoring plays: a card per scoring drive
    under its quarter, the side read off the score (a pick-six is the
    defence's), the drive's plays, yards and time, and the score it left;
    a goal at a time for hockey.

Run directly: `python3 tests/test_every_game_has_a_page.py`
"""
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamearchive as GA                           # noqa: E402
from engine.sources import espnplays as E                      # noqa: E402
from engine.sources.fetch import DataUnavailable               # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
APP, MORE, DETAIL, SERVER = (READ("web", "js", "app.js"), READ("web", "js", "more.js"),
                             READ("web", "js", "detail.js"), READ("server.py"))


def _gct():
    """tests/test_gamecast.py, whose ESPN summary and node harness these
    tests build on. Imported where it is used: a test file is not a helper,
    and tests/test_doctor.py keeps module-scope imports to the standard
    library and first-party modules."""
    import test_gamecast
    return test_gamecast


def _team(abbr, tid, name):
    """An ESPN competitor's team, as tests/test_gamecast.py builds one."""
    return {"id": tid, "abbreviation": abbr, "displayName": name}


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i)]


# --- finding the game -------------------------------------------------------------
def _event(eid, home, away, hs="27", as_="19", state="post"):
    return {"id": eid, "date": "2026-10-26T17:00Z", "status": {"type": {"state": state, "shortDetail": "Final"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": home, "score": hs},
                {"homeAway": "away", "team": away, "score": as_}]}]}


GB = _team("GB", "9", "Green Bay Packers")
CAR = _team("CAR", "29", "Carolina Panthers")
NYG = _team("NYG", "19", "New York Giants")
PHI = _team("PHI", "21", "Philadelphia Eagles")


def _boards(days):
    """A fake ESPN scoreboard fetch: ``{YYYYMMDD: [events]}``; a day not
    listed does not answer."""
    asked = []

    def fetch(url, name, ttl=None, user_agent=None):
        day = re.search(r"dates=(\d{8})", url).group(1)
        asked.append((day, ttl))
        if day not in days:
            raise DataUnavailable("the feed did not answer")
        return json.dumps({"events": days[day]})
    return fetch, asked


def _with(fetch, fn):
    real = GA.fetch_text
    GA.fetch_text = fetch
    try:
        return fn()
    finally:
        GA.fetch_text = real


def test_the_game_is_found_on_its_day_by_its_two_sides():
    fetch, asked = _boards({"20261026": [_event("402", PHI, NYG), _event("401", GB, CAR)]})
    row = _with(fetch, lambda: GA.find("nfl", dt.date(2026, 10, 26), "GB", "CAR"))
    assert row and row["event_id"] == "401" and (row["home"], row["away"]) == ("GB", "CAR")
    assert asked == [("20261026", GA.PAST_DAY_TTL)], "a past day is kept, and only that day was asked"
    # A neutral site may list the two the other way round: matched on the day itself.
    row = _with(fetch, lambda: GA.find("nfl", dt.date(2026, 10, 26), "CAR", "GB"))
    assert row and row["event_id"] == "401"


def test_a_neighbouring_day_only_when_the_day_answered_without_it():
    fetch, asked = _boards({"20261026": [_event("402", PHI, NYG)], "20261025": [],
                            "20261027": [_event("401", GB, CAR)]})
    row = _with(fetch, lambda: GA.find("nfl", dt.date(2026, 10, 26), "GB", "CAR"))
    assert row and row["event_id"] == "401", "a late kick filed across midnight"
    assert [d for d, _ in asked] == ["20261026", "20261025", "20261027"]
    fetch, _ = _boards({"20261027": [_event("401", GB, CAR)]})
    try:
        _with(fetch, lambda: GA.find("nfl", dt.date(2026, 10, 26), "GB", "CAR"))
        raise AssertionError("a day that did not answer was guessed past")
    except DataUnavailable:
        pass


def test_baseball_never_looks_next_door_and_knows_a_doubleheaders_legs():
    def day(rows):
        return lambda d: rows.get(d.isoformat(), [])
    real = GA._mlb_day
    try:
        GA._mlb_day = day({"2026-07-04": [], "2026-07-05": [
            {"event_id": "9", "game_pk": 9, "home": "BOS", "away": "NYY", "game_number": 1}]})
        assert GA.find("mlb", dt.date(2026, 7, 4), "BOS", "NYY") is None, "the next day's game is another game"
        GA._mlb_day = day({"2026-07-04": [
            {"event_id": "12", "game_pk": 12, "home": "BOS", "away": "NYY", "game_number": 2},
            {"event_id": "11", "game_pk": 11, "home": "BOS", "away": "NYY", "game_number": 1}]})
        assert GA.find("mlb", dt.date(2026, 7, 4), "BOS", "NYY", "NYY@BOS-G2")["event_id"] == "12"
        assert GA.find("mlb", dt.date(2026, 7, 4), "BOS", "NYY", "NYY@BOS")["event_id"] == "11"
    finally:
        GA._mlb_day = real


def test_a_malformed_question_is_refused():
    for kw in ({"league": "xfl", "event": "1"}, {"league": "nfl", "event": "../etc"},
               {"league": "nfl", "date": "yesterday", "home": "GB", "away": "CAR"},
               {"league": "nfl", "date": "2026-10-26", "home": "GB", "away": "GB"},
               {"league": "nfl", "date": "2026-10-26", "home": "GB", "away": "<script>"},
               {"league": "nfl", "date": "2026-13-45", "home": "GB", "away": "CAR"}):
        try:
            GA.game(**kw)
            raise AssertionError(f"answered {kw}")
        except GA.BadRequest:
            pass


# --- the page's document ----------------------------------------------------------
def _final_summary():
    s = _gct()._summary()
    hdr = s["header"]
    hdr["id"] = "401"
    comp = hdr["competitions"][0]
    comp["date"] = "2026-10-26T17:00Z"
    comp["status"] = {"type": {"state": "post", "shortDetail": "Final", "completed": True}}
    for c in comp["competitors"]:
        c["score"] = "7" if c["homeAway"] == "home" else "0"
    return s


def test_a_past_games_page_is_the_live_pages_own_document_and_a_final_is_kept():
    calls = []
    real, real_dir = E.fetch_summary, GA.ARCHIVE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        GA.ARCHIVE_DIR = Path(tmp) / "gamearchive"
        E.fetch_summary = lambda lg, ev, ttl=4: calls.append((lg, ev, ttl)) or _final_summary()
        try:
            doc = GA.game("nfl", event="401")
            again = GA.game("nfl", event="401")
            kept = list(GA.ARCHIVE_DIR.glob("*"))
            size = sum(p.stat().st_size for p in kept)
        finally:
            E.fetch_summary, GA.ARCHIVE_DIR = real, real_dir
    assert (doc["home"], doc["away"], doc["event_id"]) == ("DAL", "TB", "401")
    assert doc["live"]["state"] == "final" and doc["live"]["home_score"] == 7
    assert doc["archive"] is True and doc["date"] == "2026-10-26"
    assert [d.get("result") for d in doc["drives"]] == ["Punt", "Touchdown"]
    assert doc["box"] and doc["team_stats"] and doc["records"]["DAL"] == "2-2"
    assert _gct().TEXT not in json.dumps(doc), "the builder's rule holds: never a written account"
    assert calls == [("nfl", "401", GA.FEED_TTL)], "a final is kept: the second reader costs nothing"
    assert again == doc and [p.name for p in kept] == ["nfl_401.json.gz"], "kept gzipped, nothing left half-written"
    assert size < len(json.dumps(doc)), "smaller on the shelf than on the wire"


def test_the_shelf_keeps_its_size_and_drops_the_longest_unread():
    real_dir, real_max = GA.ARCHIVE_DIR, GA.ARCHIVE_MAX
    with tempfile.TemporaryDirectory() as tmp:
        GA.ARCHIVE_DIR, GA.ARCHIVE_MAX = Path(tmp) / "gamearchive", 4
        try:
            for i, ev in enumerate(("1", "2", "3", "4")):
                path = GA.ARCHIVE_DIR / f"nfl_{ev}.json.gz"
                GA._keep(path, {"event_id": ev, "live": {"state": "final"}})
                os.utime(path, (1000 + i, 1000 + i))
            assert GA.event_doc("nfl", "1")["event_id"] == "1", "the oldest, read again"
            GA._keep(GA.ARCHIVE_DIR / "nfl_5.json.gz", {"event_id": "5", "live": {"state": "final"}})
            left = sorted(p.name for p in GA.ARCHIVE_DIR.iterdir())
        finally:
            GA.ARCHIVE_DIR, GA.ARCHIVE_MAX = real_dir, real_max
    assert left == ["nfl_1.json.gz", "nfl_4.json.gz", "nfl_5.json.gz"], left


def test_a_game_not_over_is_built_and_not_kept():
    s = _final_summary()
    s["header"]["competitions"][0]["status"] = {"type": {"state": "in"}, "period": 2, "displayClock": "4:00"}
    real, real_dir = E.fetch_summary, GA.ARCHIVE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        GA.ARCHIVE_DIR = Path(tmp) / "gamearchive"
        E.fetch_summary = lambda lg, ev, ttl=4: s
        try:
            doc = GA.game("nfl", event="401")
            kept = list(GA.ARCHIVE_DIR.glob("*")) if GA.ARCHIVE_DIR.exists() else []
        finally:
            E.fetch_summary, GA.ARCHIVE_DIR = real, real_dir
    assert doc["live"]["state"] == "live" and not kept


def test_the_baseball_page_comes_from_the_baseball_builder():
    lb = READ("live_build.py")
    assert "def mlb_doc(g: dict, payload: dict, plays: list[dict]," in lb
    assert "doc = mlb_doc(g, payload, plays, chances=chances)" in lb, "the live file and the archive share one builder"
    src = READ("engine", "gamearchive.py")
    assert "doc = lvb.mlb_doc(g, payload, every, chances=chances)" in src
    assert "doc = lb.pbp_doc(league, g, payload, sides=sides)" in src


# --- the route ----------------------------------------------------------------------
def test_the_route_is_free_and_says_what_went_wrong():
    assert 'if parsed.path in ("/api/game", "/api/game/"):\n            return self._game(parse_qs(parsed.query))' in SERVER
    body = SERVER[SERVER.index("    def _game(self, q):"):SERVER.index("    def _record_day(self, q):")]
    assert "except gamearchive.BadRequest as exc:\n            return self._send(400," in body
    assert "return self._send(503," in body and "return self._send(404," in body
    assert "gate" not in body.split('"""')[2], "not gated: scores and plays are public facts"
    from engine import gate
    assert "pbp" in gate.FREE_DIRS
    # Its own ceilings, one a reader and one for everybody, before a feed is asked.
    assert body.index('if self._rate_limited(RATE_GAME_PER_MIN, "game"):') < body.index("gamearchive.game(")
    assert body.index('if not rate_ok("game:everyone", RATE_GAME_ALL_PER_MIN):') < body.index("gamearchive.game(")
    assert "RATE_GAME_PER_MIN = 30\nRATE_GAME_ALL_PER_MIN = 300\n" in SERVER


# --- the doors ----------------------------------------------------------------------
def test_every_game_played_opens_its_page_and_comes_back_to_the_team():
    door = _fn(MORE, "teamGameDoor")
    assert "if (g.final && PAST_GAME_LEAGUES.has(d.sport)) return teamPastGameAttrs(d, g);" in door
    assert 'const PAST_GAME_LEAGUES = new Set(["nfl", "cfb", "nba", "wnba", "nhl", "mlb"]);' in MORE
    attrs = _fn(MORE, "teamPastGameAttrs")
    for k in ("data-past-game", "data-pg-date", "data-pg-home", "data-pg-away", "data-pg-id"):
        assert k in attrs, k
    assert 'String(g.date || g.period || "").slice(0, 10)' in attrs, "a daily sport's period is its day"
    opener = _fn(MORE, "openPastGame")
    assert "await fetch(`/api/game?${q}`" in opener and 'openPbp(league, doc.event_id, "team")' in opener
    assert "window.QB_PAST_GAMES" in opener and "tfToast(" in opener, "handed to the page; a miss is said"
    assert "teamPastGameAttrs({ sport }, g)" in _fn(MORE, "teamH2HHTML"), "every meeting on the Versus tab"
    assert 'const past = e.target.closest && e.target.closest("[data-past-game]");\n  if (past) return openPastGame(past);' in APP
    assert "[data-gs-toggle],[data-past-game]\";" in APP, "a keyboard stop like every other door"
    back = _fn(DETAIL, "pbpBack")
    assert 'if (from === "team" && _teamState && _teamState.team) {' in back


def test_the_page_falls_back_to_the_archive_when_the_live_file_is_gone():
    page = _fn(DETAIL, "renderPbpPage")
    assert "if (!d && league && event) {\n    const got = await pbpArchived(league, event);" in page
    reader = DETAIL[DETAIL.index("async function pbpArchived("):DETAIL.index("async function renderPbpPage(")]
    assert "/api/game?league=${encodeURIComponent(league)}&event=${encodeURIComponent(event)}" in reader
    assert "(window.QB_PAST_GAMES || {})[key]" in reader, "a team's schedule already asked"
    # A final is drawn once and never polled; anything else polls as a live page does.
    assert 'if (d && d.archive && (d.live || {}).state === "final") return;\n    _pbpTimer = setTimeout(' in page


def test_the_schedule_says_every_game_opens():
    sched = _fn(MORE, "teamScheduleHTML")
    assert "every game played opens its own page" in sched


# --- the scoring plays --------------------------------------------------------------
def _drive(team, plays, result, n=3, yards=10, elapsed="1:20", period=1):
    return {"id": f"d-{team}-{period}-{result}", "team": team, "plays": plays, "result": result,
            "offensive_plays": n, "yards": yards, "elapsed": elapsed, "period": period, "scoring": True}


def _p(event, away, home, period=1, clock="5:00", scoring=True, players=None, yards=0):
    row = {"kind": "football", "event": event, "away_score": away, "home_score": home, "period": period,
           "clock": clock, "scoring": scoring, "yards": yards, "team": ""}
    if players:
        row["players"] = players
    return row


def test_the_gamecast_carries_espns_scoring_plays():
    d = {"league": "nfl", "event_id": "401", "home": "GB", "away": "CAR",
         "live": {"state": "final", "home_score": 13, "away_score": 3},
         "drives": [
             _drive("CAR", [_p("Rush", 0, 0, scoring=False), _p("Field Goal Good", 3, 0, clock="11:43", yards=39)],
                    "Field Goal", n=6, yards=8, elapsed="3:12"),
             _drive("GB", [_p("Pass Reception", 3, 0, scoring=False),
                           _p("Passing Touchdown", 3, 6, clock="5:08", players=["Tucker Kraft", "Jordan Love"], yards=12),
                           _p("Extra Point Missed", 3, 6, scoring=False)],
                    "Touchdown", n=8, yards=56, elapsed="3:33"),
             # A pick run back: the defence's touchdown on the offence's drive.
             _drive("CAR", [_p("Interception Return Touchdown", 3, 12, period=2, clock="14:57"),
                            _p("Extra Point Good", 3, 13, period=2, clock="14:57")],
                    "Interception Touchdown", n=2, yards=4, elapsed="0:40", period=2),
             _drive("GB", [_p("Punt", 3, 13, period=2, scoring=False)], "Punt", period=2)]}
    got = _gct()._node(f"""
      const d = {json.dumps(d)};
      const html = QBGamecast.panel("gamecast", {{ d, league: "nfl" }});
      const i = html.indexOf("Scoring plays");
      return {{ html: html.slice(i), i }};""")
    if got is None:
        print("      (skipped: no node)")
        return
    html = got["html"]
    assert got["i"] >= 0, "the card is on the Gamecast tab"
    cards = re.findall(r'<div class="gc-sc">(.*?)</div>\s*</div>', html, re.S)
    assert len(cards) == 3, "one card per scoring drive: the punt is not a score, the missed kick is not its own"
    assert html.index("1st quarter") < html.index("2nd quarter")
    car_fg, gb_td, pick = cards
    assert '<span class="mark">CAR</span>' in car_fg and "<b>Field goal</b>" in car_fg and "<b>3</b>" in car_fg
    assert "Field goal good, 39 yds" in car_fg, "the play in the site's own words (footballWords)"
    assert "6 plays, 8 yards, 3:12" in car_fg
    assert '<span class="mark">GB</span>' in gb_td and "Tucker Kraft, Jordan Love" in gb_td and "<b>6</b>" in gb_td
    assert '<span class="mark">GB</span>' in pick, "the side is read off the score, not the drive"
    assert "<b>13</b>" in pick, "the score after the kick that followed it"


def test_hockey_lists_its_goals():
    d = {"league": "nhl", "event_id": "7", "home": "BOS", "away": "NYR",
         "live": {"state": "final", "home_score": 2, "away_score": 1},
         "plays": [{"kind": "hockey", "event": "Shot", "away_score": 0, "home_score": 0, "period": 1, "scoring": False},
                   {"kind": "hockey", "event": "Goal", "away_score": 0, "home_score": 1, "period": 1, "clock": "4:12",
                    "scoring": True, "team": "BOS", "players": ["David Pastrnak"]},
                   {"kind": "hockey", "event": "Goal", "away_score": 1, "home_score": 1, "period": 2, "clock": "9:30",
                    "scoring": True, "team": "NYR"},
                   {"kind": "hockey", "event": "Goal", "away_score": 1, "home_score": 2, "period": 4, "clock": "1:05",
                    "scoring": True, "team": "BOS"}]}
    got = _gct()._node(f"""
      const html = QBGamecast.panel("gamecast", {{ d: {json.dumps(d)}, league: "nhl" }});
      return html.slice(html.indexOf("Scoring plays"));""")
    if got is None:
        print("      (skipped: no node)")
        return
    assert got.count('class="gc-sc"') == 3
    assert "1st period" in got and "2nd period" in got and "Overtime" in got
    assert "David Pastrnak" in got


def test_the_scoring_card_has_its_own_styles_on_tokens():
    css = READ("web", "css", "gamecast.css")
    i = css.index(".gc-sc-q {")
    block = css[i:css.index("\n\n", i)] if "\n\n" in css[i:] else css[i:]
    for sel in (".gc-sc {", ".gc-sc-t {", ".gc-sc-line {", ".gc-sc-score {"):
        assert sel in block, sel
    assert "#" not in re.sub(r"/\*.*?\*/", "", block, flags=re.S), "colours through tokens"


# --- in a browser: the team, a game played, its page, and back ----------------------
TEAM = {"sport": "nfl", "team": "DAL", "name": "Dallas Cowboys",
        "profile": {"team": "DAL", "name": "Dallas Cowboys", "seasons": []}, "opponents": [],
        "squad": None, "stats": None, "roster": None, "depth": None,
        "schedule": {"season": 2026, "seasons": [2026], "games": [
            {"season": 2026, "period": "008", "date": "2026-10-26", "game_id": "2026_08_TB_DAL",
             "home": "DAL", "away": "TB", "at_home": True, "opponent": "TB", "final": True, "result": "W",
             "points_for": 7, "points_against": 0, "home_score": 7, "away_score": 0, "margin": 7,
             "line": -3.5, "covered": True, "total": 44.5, "ou": "under"},
            {"season": 2026, "period": "009", "date": "2099-11-02", "game_id": "2026_09_DAL_NYG",
             "home": "NYG", "away": "DAL", "at_home": False, "opponent": "NYG", "final": False,
             "line": None, "total": None}]}}


def test_an_old_game_says_its_day_and_has_no_chat():
    detail = READ("web", "js", "detail.js")
    assert "const ago = d.archive ? pbpPlayedOn(d) : pbpAgo(d.generated_at);" in detail
    assert "function pbpPlayedOn(d) {" in detail
    assert 'return day && y !== String(new Date().getFullYear()) ? `${day}, ${y}` : day;' in detail, \
        "a past season's meeting names its year"
    assert ('if (d && d.archive) { if (typeof chatReset === "function") { chatReset(); chatFab(); } }\n'
            "  else chatMount(league, event, d);") in detail
    slot = '${d.archive ? "" : `<div class="gch-entry-slot"></div>`}'
    assert slot in detail
    hoops = READ("web", "js", "hoopscast.js")
    assert slot in hoops and 'd.archive && typeof pbpPlayedOn === "function" ? pbpPlayedOn(d)' in hoops
    # No play's thread bubble either: the rail (pbpRoom), the gamecast's Play-by-play tab, the hoops page.
    assert 'const pbpRoom = (d, league) => {\n  if (d && d.archive) return "";' in detail
    assert 'd.event_id && !d.archive ? chatPlayBadge(`${league}_${d.event_id}`, p)' in hoops
    gc = READ("web", "js", "gamecast.js")
    assert gc.count("room: d.event_id && !d.archive ? `${league}_${d.event_id}` : \"\"") == 2
    assert '${d.archive ? "" : `<p class="mini" style="opacity:.6">Box score ${esc(pbpAgo(d.generated_at))}.</p>`}' in gc


def test_a_hidden_card_stays_hidden():
    css = READ("web", "css", "styles.css")
    card = css.index("\n.card {\n")
    assert "display: flex;" in css[card:css.index("\n}\n", card)], "the rule this answers"
    assert css.index(".card[hidden] { display: none; }") > card, "and it comes after it"


def _browser_doc():
    real, real_dir = E.fetch_summary, GA.ARCHIVE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        GA.ARCHIVE_DIR = Path(tmp) / "gamearchive"
        E.fetch_summary = lambda lg, ev, ttl=4: _final_summary()
        try:
            return GA.game("nfl", event="401")
        finally:
            E.fetch_summary, GA.ARCHIVE_DIR = real, real_dir


def _run_browser():
    from playwright.sync_api import sync_playwright
    import rendercheck
    doc, asked, errs, got = _browser_doc(), [], [], {}
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())

                def fake_game(route):
                    asked.append(route.request.url)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(doc))
                page.route("**/api/game?*", fake_game)
                page.route("**/api/team?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                 body=json.dumps(TEAM)))
                page.route("**/api/account/me*", lambda r: r.fulfill(status=200, content_type="application/json",
                    body=json.dumps({"signed_in": True, "email": "you@example.com", "profile": {"handle": "t"}})))
                page.route("**/api/billing/status*", lambda r: r.fulfill(status=200, content_type="application/json",
                    body=json.dumps({"signed_in": True, "paywall": True, "entitled": True, "plans": []})))
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl#team/nfl/DAL", wait_until="load")
                page.wait_for_function("() => document.querySelector('#team-page .tm-tabs')", timeout=15000)
                page.click('[data-team-tab="schedule"]')
                page.wait_for_timeout(300)
                got["rows"] = page.evaluate("""() => [...document.querySelectorAll('#team-page .tm-row')].map((r) =>
                    [r.dataset.pastGame || '', r.dataset.teamOpen || ''])""")
                page.click("#team-page .tm-row[data-past-game]")
                # textContent, not innerText: the heads are uppercased by CSS.
                page.wait_for_function("() => state.view === 'pbp' && (document.getElementById('pbp-body') || {}).textContent"
                                       " && document.getElementById('pbp-body').textContent.includes('Scoring plays')",
                                       timeout=20000)
                got["hash"] = page.evaluate("location.hash")
                got["page"] = page.evaluate("document.getElementById('pbp-body').textContent")
                # An old game: the day it was played, no chat, and no blank slots.
                got["old"] = page.evaluate("""() => ({
                    stamp: [...document.querySelectorAll('#pbp-body .pbp-sb-ago')].map((e) => e.textContent),
                    chat: document.querySelectorAll('#pbp-body .gch-entry-slot, #pbp-body .gch-entry, #pbp-body .pr-chat').length + (document.getElementById('gch-fab') ? 1 : 0),
                    plays: document.querySelectorAll('#pbp-body .lb-play').length,
                    slots: ['pbp-action', 'pbp-pace', 'pbp-split'].map((id) => { const e = document.getElementById(id);
                        return e ? [e.hidden, getComputedStyle(e).display, e.getBoundingClientRect().height] : null; })})""")
                got["back"] = page.evaluate("(document.getElementById('pbp-back') || {}).textContent || ''")
                page.click("#pbp-back")
                page.wait_for_timeout(600)
                got["after"] = page.evaluate("state.view")
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return got, asked, errs


def test_in_a_browser_a_game_on_the_schedule_opens_its_page_and_comes_back():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    got, asked, errs = _run_browser()
    assert not errs, errs
    assert got["rows"] == [["nfl", ""], ["", "NYG"]], ("the game played opens its page, the one to come the opponent", got["rows"])
    assert len(asked) == 1, ("the page drew the document it was handed, without asking twice", asked)
    q = asked[0]
    for want in ("league=nfl", "date=2026-10-26", "home=DAL", "away=TB", "game_id=2026_08_TB_DAL"):
        assert want in q, (want, q)
    assert got["hash"] == "#pbp/nfl/401", got["hash"]
    for want in ("Scoring plays", "Touchdown", "1st quarter"):
        assert want in got["page"], (want, got["page"][:600])
    assert "Back to the Cowboys" in got["back"], got["back"]
    assert got["after"] == "team"
    old = got["old"]
    assert len(old["stamp"]) == 1 and "Oct 26" in old["stamp"][0] and "updated" not in old["stamp"][0], \
        ("an old game says the day it was played, not how fresh its file is", old["stamp"])
    assert old["plays"] > 0 and old["chat"] == 0, ("no room, no card, no bar and no play's bubble on an old game", old)
    for slot in old["slots"]:
        assert slot and slot[0] and slot[1] == "none" and slot[2] == 0, ("a waiting slot takes no room", old["slots"])


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
