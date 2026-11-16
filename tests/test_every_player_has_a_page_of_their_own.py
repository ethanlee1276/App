"""Every player has a page of their own, with ESPN's menus (2026-11-16).

Ethan, with ESPN's page for Josh Allen: "The page should look just like this
and have each menu for all players in all sports."

engine/playerpage.page gathers what the menus show from what is already kept:
the published roster's facts and latest note, the season's four headline
numbers with their places in the league (a count among everyone with one, a
basketball average among those with half the most games played, a rate and a
fewer-is-better count among those with RATE_SHARE of the leader's volume),
the newest game with the score and both clubs' records, the season's splits a
game's average at a time, and the seasons one by one. server.py serves it free
at /api/players/page; js/playerpage.js turns the Players page into the
player's page (app.js renderPlayers, through its room) with the header in the
club's colours and Overview, News, Stats, Bio, Splits and Game Log.

Run directly: `python3 tests/test_every_player_has_a_page_of_their_own.py`
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
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, playerpage as PP                               # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    games = [("nfl", 2026, "009", "KC@BUF", "BUF", "KC", 24, 27, "2026-11-02"),
             ("nfl", 2026, "010", "BUF@MIA", "MIA", "BUF", 20, 30, "2026-11-09"),
             ("nfl", 2026, "011", "BUF@NYJ", "NYJ", "BUF", 12, 31, "2026-11-16"),
             ("nfl", 2026, "011", "CIN@PIT", "PIT", "CIN", 20, 23, "2026-11-16"),
             ("nfl", 2025, "005", "BUF@NE", "NE", "BUF", 13, 35, "2025-10-05"),
             ("nba", 2026, "2026-11-10", "g1", "NYK", "BOS", 120, 110, "2026-11-10"),
             ("nba", 2026, "2026-11-12", "g2", "PHI", "NYK", 105, 99, "2026-11-12"),
             ("nba", 2026, "2026-11-14", "g3", "NYK", "MIA", 101, 96, "2026-11-14"),
             ("nba", 2026, "2026-11-15", "g4", "ORL", "NYK", 100, 90, "2026-11-15"),
             ("nhl", 2026, "2026-11-12", "n1", "TOR", "BOS", 3, 2, "2026-11-12"),
             ("nhl", 2026, "2026-11-14", "n2", "MTL", "TOR", 3, 4, "2026-11-14"),
             ("mlb", 2026, "2026-06-01", "m1", "NYY", "BOS", 5, 3, "2026-06-01"),
             ("mlb", 2026, "2026-06-07", "m2", "TB", "NYY", 2, 6, "2026-06-07")]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", games)
    rows = []

    def log(sport, season, period, gid, player, team, opp, pos, stats):
        for m, v in stats.items():
            rows.append((sport, season, period, gid, player, team, opp, pos, 1, m, v))
    qb = lambda c, a, y, t, i: {"pass_cmp": c, "pass_att": a, "pass_yds": y, "pass_td": t, "pass_int": i}  # noqa: E731
    log("nfl", 2026, "009", "BUF-009", "Josh Allen", "BUF", "KC", "QB", dict(qb(20, 30, 250, 2, 1), carries=6, rush_yds=40,
                                                                          rush_td=1))
    log("nfl", 2026, "010", "BUF-010", "Josh Allen", "BUF", "MIA", "QB", dict(qb(24, 33, 301, 3, 0), carries=5,
                                                                           rush_yds=22, rush_td=0))
    log("nfl", 2026, "011", "BUF-011", "Josh Allen", "BUF", "NYJ", "QB", dict(qb(21, 28, 252, 2, 0), carries=7,
                                                                           rush_yds=31, rush_td=1))
    log("nfl", 2025, "005", "BUF-005", "Josh Allen", "BUF", "NE", "QB", qb(22, 30, 292, 4, 0))
    log("nfl", 2026, "011", "CIN-011", "Joe Burrow", "CIN", "PIT", "QB", qb(30, 40, 900, 9, 3))
    log("nfl", 2026, "011", "CIN-011", "Backup Arm", "CIN", "PIT", "QB", qb(1, 2, 60, 1, 0))
    box = lambda mn, p, r, a, fm, fa: {"min": mn, "pts": p, "reb": r, "ast": a, "fgm": fm, "fga": fa}  # noqa: E731
    for gid, day, opp, b in (("g1", "2026-11-10", "BOS", box(36, 30, 4, 8, 11, 20)),
                             ("g2", "2026-11-12", "PHI", box(34, 24, 3, 6, 9, 19)),
                             ("g3", "2026-11-14", "MIA", box(35, 27, 5, 7, 10, 21)),
                             ("g4", "2026-11-15", "ORL", {"min": 0, "pts": 0})):
        log("nba", 2026, day, gid, "Jalen Brunson", "NYK", opp, "G", b)
        log("nba", 2026, day, gid, "Role Guy", "NYK", opp, "F", {"min": 20, "pts": 10, "fgm": 4, "fga": 8})
    log("nba", 2026, "2026-11-10", "g1", "One Night", "BOS", "NYK", "F", box(30, 50, 2, 1, 18, 30))
    log("nhl", 2026, "2026-11-12", "n1", "Joseph Woll", "TOR", "BOS", "G",
        {"saves": 28, "shots_against": 30, "goals_against": 2, "toi": 60.0, "started": 1})
    log("nhl", 2026, "2026-11-14", "n2", "Joseph Woll", "TOR", "MTL", "G",
        {"saves": 30, "shots_against": 33, "goals_against": 3, "toi": 58.5, "started": 1})
    log("nhl", 2026, "2026-11-14", "n2", "Relief Goalie", "MTL", "TOR", "G",
        {"saves": 10, "shots_against": 14, "goals_against": 4, "toi": 20.0, "started": 0})
    log("mlb", 2026, "2026-06-01", "m1", "Gerrit Cole", "NYY", "BOS", "P", {"outs": 19, "strikeouts": 8})
    log("mlb", 2026, "2026-06-07", "m2", "Gerrit Cole", "NYY", "TB", "P", {"outs": 18, "strikeouts": 7})
    log("mlb", 2026, "2026-06-07", "m2", "Long Man", "TB", "NYY", "P", {"outs": 3, "strikeouts": 2})
    for gid, day, opp in (("m1", "2026-06-01", "BOS"), ("m2", "2026-06-07", "TB")):
        log("mlb", 2026, day, gid, "Big Swinger", "NYY", opp, "RF", {"pa": 5, "hits": 1, "strikeouts": 10})
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def _rosters():
    d = tempfile.mkdtemp()
    nfl = {"teams": {"BUF": {"players": [
        {"player": "Josh Allen", "team": "BUF", "position": "QB", "number": 17, "height": "6'5\"", "weight": "237 lb",
         "age": 30, "born": "1996-05-21", "college": "Wyoming", "years_exp": 8, "rookie": False, "status": "Active",
         "injury_status": "Questionable", "injury": "Hand", "injury_note": "Allen was limited in Wednesday's practice.",
         "return_date": "", "injury_source": "sleeper", "headshot": "https://example.test/allen.png"},
        {"player": "Rookie Nobody", "team": "BUF", "position": "WR", "number": 88, "rookie": True}]},
        "JAX": {"players": [{"player": "Josh Allen", "team": "JAX", "position": "LB", "number": 41}]}},
        "transactions": {"moves": [{"player": "Rookie Nobody", "from": "JAX", "to": "BUF", "date": "2026-11-10"}]}}
    nba = {"teams": {"NYK": {"players": [{"player": "Jalen Brunson", "team": "NYK", "position": "G", "number": "11",
                                          "height": "6' 2\"", "weight": "190 lbs", "born": "1996-08-31",
                                          "birthplace": "New Brunswick, NJ"}]}}}
    for sport, doc in (("nfl", nfl), ("nba", nba)):
        with open(os.path.join(d, f"rosters_{sport}.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    return d


def _fresh():
    PP._RANKS.clear()
    PP._ROSTERS.clear()
    return _history(), _rosters()


def test_a_quarterbacks_page_reads_like_espns():
    path, rosters = _fresh()
    d = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters)
    assert (d["team"], d["position"], d["role"], d["season"], d["seasons"]) == ("BUF", "QB", "passing", 2026, [2026, 2025])
    b = d["bio"]
    assert (b["number"], b["height"], b["weight"], b["college"], b["years_exp"], b["born"]) == \
        ("17", "6'5\"", "237 lb", "Wyoming", 8, "1996-05-21"), "the quarterback's row, not the linebacker's"
    assert (b["first_season"], b["last_season"], b["games"]) == (2025, 2026, 4)
    assert d["notes"]["injury"] == {"status": "Questionable", "what": "Hand", "back": "", "source": "sleeper",
                                    "note": "Allen was limited in Wednesday's practice."}
    h = {x["key"]: x for x in d["headline"]}
    assert [x["label"] for x in d["headline"]] == ["YDS", "TD", "INT", "RTG"]
    assert (h["yds"]["value"], h["yds"]["rank"], h["td"]["value"], h["td"]["rank"]) == (803, 2, 7, 2)
    assert (h["int"]["value"], h["int"]["rank"], h["int"]["low"]) == (1, 1, True), \
        "fewest among real passers: two throws are no place at all"
    assert (h["rtg"]["value"], h["rtg"]["rank"]) == (119.4, 2)
    last = d["last"]
    assert (last["week"], last["date"], last["opponent"], last["home"]) == (11, "2026-11-16", "NYJ", False)
    assert (last["result"], last["score"], last["record"], last["opp_record"]) == ("W", "31-12", "2-1", "0-1")
    assert [(t["label"], t["value"]) for t in last["tiles"]] == [("RTG", 125.9), ("CMP%", 75.0), ("YDS", 252), ("TD", 2)]
    rows = {r["key"]: r for r in d["splits"]["rows"]}
    assert [r["key"] for r in d["splits"]["rows"]] == ["season", "home", "away", "wins", "losses", "m:2026-11",
                                                       "vs:NYJ", "vs:MIA", "vs:KC"]
    assert (rows["season"]["gp"], rows["season"]["values"]["passing.yds"], rows["season"]["values"]["passing.rtg"]) == \
        (3, 267.7, 119.4), "a game's average, and the rating off the summed line"
    assert (rows["away"]["gp"], rows["losses"]["values"]["passing.yds"], rows["m:2026-11"]["label"]) == \
        (2, 250.0, "November")
    c = d["career"]
    assert [(r["season"], r["team"], r["gp"], r["values"]["passing.yds"]) for r in c["rows"]] == \
        [(2026, "BUF", 3, 803), (2025, "BUF", 1, 292)]
    assert (c["per_game"], c["total"]["gp"], c["total"]["values"]["passing.yds"]) == (False, 4, 1095)
    old = PP.page("nfl", "Josh Allen", season=2025, db_path=path, data_dir=rosters)
    assert old["season"] == 2025 and old["last"]["result"] == "W" and old["last"]["opp_record"] == "0-1"


def test_a_basketball_page_averages_a_game_and_ranks_the_regulars():
    path, rosters = _fresh()
    d = PP.page("nba", "Jalen Brunson", db_path=path, data_dir=rosters)
    assert d["role"] == "box" and d["bio"]["birthplace"] == "New Brunswick, NJ"
    h = {x["key"]: x for x in d["headline"]}
    assert (h["pts"]["value"], h["pts"]["rank"]) == (27.0, 1), \
        "fifty in his one game is no average: half the most games played to be placed"
    assert (h["fgp"]["value"], h["fgp"]["rank"]) == (50.0, 2), "the one-night shooter has the volume, and ties share"
    assert d["last"]["dnp"] is True and d["last"]["record"] == "2-2", "the newest game is one he sat"
    rows = {r["key"]: r for r in d["splits"]["rows"]}
    assert rows["season"]["gp"] == 3 and rows["season"]["values"]["box.fg"] == "10.0-20.0"
    assert rows["season"]["values"]["box.fgp"] == 50.0 and rows["home"]["gp"] == 2 and rows["vs:PHI"]["gp"] == 1
    c = d["career"]
    assert c["per_game"] is True and c["rows"][0]["values"]["box.pts"] == 27.0, "basketball reads a game's average"
    role = PP.page("nba", "Role Guy", db_path=path, data_dir=rosters)
    assert {x["key"]: x["rank"] for x in role["headline"]}["pts"] == 2


def test_a_goalie_and_a_pitcher_lead_with_their_own_numbers():
    path, rosters = _fresh()
    g = PP.page("nhl", "Joseph Woll", db_path=path, data_dir=rosters)
    h = {x["key"]: x for x in g["headline"]}
    assert g["role"] == "goalie" and [x["label"] for x in g["headline"]] == ["SV%", "GAA", "SV", "GS"]
    assert (h["svp"]["value"], h["svp"]["rank"], h["gaa"]["value"], h["gaa"]["rank"]) == (92.1, 1, 2.53, 1)
    assert (h["sv"]["rank"], h["gs"]["value"], h["gs"]["rank"]) == (1, 2, None), "games started is no race"
    assert g["last"]["result"] == "W" and g["last"]["score"] == "4-3" and g["last"]["record"] == "2-0"
    p = PP.page("mlb", "Gerrit Cole", db_path=path, data_dir=rosters)
    h = {x["key"]: x for x in p["headline"]}
    assert p["role"] == "pitching" and (h["ip"]["value"], h["ip"]["rank"]) == ("12.1", 1)
    assert (h["k"]["value"], h["k9"]["value"], h["k9"]["rank"], h["gp"]["value"]) == (15, 10.9, 1, 2), \
        "the long man's eighteen a nine is three outs of it"
    assert h["k"]["rank"] == 1, "a hitter's twenty strikeouts are none of a pitcher's"
    assert [r["key"] for r in p["splits"]["rows"]][:3] == ["season", "home", "away"]
    assert p["last"]["tiles"][0]["label"] == "IP" and p["last"]["tiles"][0]["value"] == "6.0"


def test_a_name_only_a_roster_knows_still_has_a_page():
    path, rosters = _fresh()
    r = PP.page("nfl", "Rookie Nobody", db_path=path, data_dir=rosters)
    assert r["bio"]["rookie"] is True and r["bio"]["number"] == "88" and "season" not in r
    assert r["notes"]["moves"] == [{"from": "JAX", "to": "BUF", "date": "2026-11-10"}]
    assert PP.page("nfl", "Nobody At All", db_path=path, data_dir=rosters) == {}
    assert PP.page("ufc", "Josh Allen", db_path=path, data_dir=rosters) == {}
    jax = PP.roster_row("nfl", "Josh Allen", "JAX", rosters)
    assert jax["position"] == "LB" and PP.roster_row("nfl", "Josh Allen", "", rosters) == {}, \
        "two men of one name are neither, without the club"


def test_the_server_serves_it_free_and_the_players_page_becomes_it():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/players/page", "/api/players/page/"):' in srv
    i = srv.index("def _players_page(self, q):")
    body = srv[i:srv.index("\n    def ", i + 10)]
    assert "playerpage.page(sport, player, team=team," in body and "_entitled" not in body, "facts, free"
    assert 'return self._send(400, b\'{"error":"no player page for this sport"}\', ".json")' in body
    assert "PLAYER_PAGE_TTL = 300" in srv and "PLAYER_PAGE_KEEP = 400" in srv
    assert ('function renderPlayerPage(...a) { return roomCall(renderPlayerPage, "renderPlayerPage", '
            '"js/playerpage.js", "css/playerpage.css", a); }') in APP
    assert ('        const own = drawn.find((m) => searchNorm(m.player) === searchNorm(state.search)) || '
            '(drawn.length === 1 && drawn[0]);\n        if (own && own.sport !== "ufc") renderPlayerPage(host, own.player, '
            'own.sport);\n        return;') in APP, "a league search that finds the player asked for, or just one"
    assert ("  revealChildren(host);\n  const own = q && (shown.find((p) => searchNorm(p) === searchNorm(state.search)) "
            "|| (shown.length === 1 && shown[0]));\n  if (own) renderPlayerPage(host, own, state.sport);\n}") in APP, \
        "a board search too: the name asked for, even beside a near name"
    assert "if (who && who !== player) el.remove();" in PAGE, "a near name's card is not on the page"
    assert '"js/playerpage.js", "css/playerpage.css",' in (ROOT / "engine" / "shrink.py").read_text(encoding="utf-8")
    assert '"/js/playerpage.js", "/css/playerpage.css",' in (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    assert "/js/playerpage.js /css/playerpage.css" in (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    assert 'const PP_TABS = [["overview", "Overview"], ["news", "News"], ["stats", "Stats"], ["bio", "Bio"],\n' \
           '  ["splits", "Splits"], ["log", "Game Log"]];' in PAGE, "ESPN's six menus"
    i = PAGE.index("function renderPlayerPage(host, player, sport) {")
    mount = PAGE[i:PAGE.index("\n}\n", i)]
    assert "while (host.firstChild) kept.appendChild(host.firstChild);" in mount
    assert "tonight.replaceChildren(kept);" in PAGE, "the market cards this page always drew are kept, in Overview"
    assert ("  if (same) {\n    ppMarkets(same, kept);\n    host.replaceChildren(same);\n    return;\n  }") in mount, \
        "the 30-second redraw puts the same page back, only its market cards fresh"
    assert "if (cached) ppFill(page, cached);" in mount, "a first visit draws at once from the visit's copy"
    assert ('  const b = e.target.closest && e.target.closest(".pp .gl-open");' in PAGE
            and "  e.stopPropagation();\n  ppShow(page, \"log\");\n  ppToTabs(page);\n}, true);" in PAGE), \
        "on the page, the card's Game log opens the Game Log menu, not a sheet over it"
    for sel in (".pp-hero", ".pp-mark", ".pp-tabs", ".pp-tab.on", ".pp-panel[hidden]", ".pp-nums", ".pp-score",
                ".pp-tiles", ".pp-break td", ".pp-heads", ".pp-bio", "@media (max-width: 640px)"):
        assert sel in CSS, sel
    assert "color: var(--night-text);" in CSS, "the band is night in either theme, its words the night tokens'"


def test_the_page_draws_every_menu():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    path, rosters = _fresh()
    qb = PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters)
    nba = PP.page("nba", "Jalen Brunson", db_path=path, data_dir=rosters)
    news = {"sports": {"nfl": [
        {"title": "Josh Allen throws four touchdowns in rout", "link": "https://example.test/1", "source": "ESPN",
         "epoch": 1794838306},
        {"title": "Allen, Bills roll past Jets", "link": "https://example.test/2", "source": "CBS Sports", "epoch": 1794838000},
        {"title": "Bills sign a kicker off the practice squad", "link": "https://example.test/3", "source": "ESPN",
         "epoch": 1794837000},
        {"title": "Keenan Allen signs with the Chargers", "link": "https://example.test/4", "source": "ESPN",
         "epoch": 1794836000},
        {"title": "Chiefs hold off the Raiders", "link": "https://example.test/5", "source": "ESPN", "epoch": 1794835000}]}}
    stubs = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
             "const escapeHtml = esc, escapeAttr = esc;"
             "const plural = (n, one) => `${n} ${n === 1 ? one : one + 's'}`;"
             "const trueMinus = (x) => String(x).replace(/(^|[^\\w])-(?=\\d)/g, '$1\\u2212');"
             "const TEAMS = { BUF: { name: 'Buffalo Bills', nick: 'Bills', primary: '#00338d' },"
             "  NYJ: { name: 'New York Jets', nick: 'Jets', primary: '#125740' },"
             "  JAX: { name: 'Jacksonville Jaguars', nick: 'Jaguars' }, NYK: { name: 'New York Knicks', nick: 'Knicks' } };"
             "const teamsIn = () => TEAMS; const teamNameIn = (s, a) => (TEAMS[a] || {}).nick || a;"
             "const teamMarkIn = (s, a, n) => `<i data-mark=\"${a}\"></i>`; const lgCode = (s) => s.toUpperCase();"
             "const playerAvatar = (n) => `<i data-face=\"${n}\"></i>`; const injTag = () => '';"
             "const surname = (n) => n.split(' ').pop();"
             "const document = { addEventListener() {} };\n")
    js = stubs + PAGE + f"""
const qb = {json.dumps(qb)}, nba = {json.dumps(nba)}, news = {json.dumps(news)};
process.stdout.write(JSON.stringify({{
  hero: ppHeroHTML(qb.player, qb.sport, qb.team, qb.position, '', qb.bio),
  season: ppSeasonHTML(qb), prev: ppPrevHTML(qb), splitlet: ppSplitletHTML(qb), stats: ppStatsHTML(qb),
  bio: ppBioHTML(qb), splits: ppSplitsHTML(nba), nbaPrev: ppPrevHTML(nba), nbaSeason: ppSeasonHTML(nba),
  nbaStats: ppStatsHTML(nba), news: ppNewsHTML(qb, news),
  latest: ppLatestHTML(qb, news), tabs: ppTabsHTML('news'), panels: ppPanelsHTML('news'),
}}));"""
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout)
    hero = got["hero"]
    assert '<span>Josh</span> <b>Allen</b>' in hero and "Buffalo Bills · #17 · QB" in hero
    assert "6&#39;5&#34; · 237 lb · Age " in hero and 'style="--pp-c:#00338d"' in hero
    s = got["season"]
    assert "2026 season" in s and "<b>803</b>" in s and '<span class="pp-rank">2nd</span>' in s
    assert '<span class="pp-rank">1st fewest</span>' in s and "<b>119.4</b>" in s
    p = got["prev"]
    assert "Previous game <span>Week 11 · " in p and " · away</span>" in p and '<span class="gl-w">Won</span> · Final' in p
    assert "<small>2-1</small>" in p and "<small>0-1</small>" in p and '<span class="pp-pts pp-won">31</span>' in p
    assert '<span class="pp-k">RTG</span><b>125.9</b>' in p and '<span class="pp-k">CMP%</span><b>75.0</b>' in p
    sl = got["splitlet"]
    for label in ("This game", "November", "vs NYJ", "Away", "Season"):
        assert f'<td class="gl-fix">{label}</td>' in sl, label
    assert sl.index("This game") < sl.index("November") < sl.index("vs NYJ") < sl.index("Away") < sl.index(">Season<")
    assert 'data-pp-go="splits">Every split</button>' in sl
    st = got["stats"]
    assert '<td class="gl-fix">2026 · BUF</td>' in st and '<tr class="gl-sum"><td class="gl-fix">Career</td>' in st
    assert "Passing <span>Totals</span>" in st and '<td class="num">1,095</td>' in st
    bio = got["bio"]
    assert "<dt>College</dt><dd>Wyoming</dd>" in bio and "<dt>Experience</dt><dd>9th season</dd>" in bio
    assert "<dt>Number</dt><dd>#17</dd>" in bio and "1996 (age " in bio and "2025 to 2026 · 4 games" in bio
    sp = got["splits"]
    assert '<tr class="pp-break"><td class="gl-fix" colspan="' in sp and ">By month</td>" in sp and ">By opponent</td>" in sp
    assert '<td class="num">10.0-20.0</td>' in sp and "A game’s average" in sp
    assert '<p class="pp-dnp">Did not play.</p>' in got["nbaPrev"]
    assert "2026–27 season" in got["nbaSeason"] and '<td class="gl-fix">2026–27 · NYK</td>' in got["nbaStats"], \
        "a basketball season is said across its two years"
    assert "<b>27.0</b>" in got["nbaSeason"] and "<span>A game’s average</span>" in got["nbaStats"], \
        "an average reads as one: 27.0, not 27"
    assert '<td class="num">27.0</td>' in got["nbaStats"] and '<td class="num">252</td>' in sl and \
        '<td class="num">267.7</td>' in sl, "the one game whole, the averages to a tenth"
    n = got["news"]
    assert "<h3>The latest</h3>" in n and "Questionable · Hand" in n and "Per Sleeper" in n
    named = n[n.index("In the headlines"):n.index("Bills headlines")]
    assert "Josh Allen throws four touchdowns" in named and "Allen, Bills roll past Jets" in named
    assert "Keenan Allen" not in n, "another Allen, another club"
    assert "Bills sign a kicker" in n[n.index("Bills headlines"):] and "Chiefs hold off" not in n
    assert 'target="_blank" rel="noopener noreferrer"' in n and "The reporting lives at the source." in n
    assert got["latest"].count("<li>") == 3 and 'data-pp-go="news">All news</button>' in got["latest"]
    assert '<button type="button" role="tab" class="pp-tab on" data-pp-tab="news" aria-selected="true">News</button>' \
        in got["tabs"]
    assert '<div class="pp-panel" data-pp-panel="overview" role="tabpanel" hidden>' in got["panels"]


def _browser(run):
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                return run(browser, port)
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_the_players_page_becomes_the_players_own():
    """The address #player/josh-allen draws his page: the header, six menus,
    the season's numbers, the market card kept in Overview; a menu opens in
    place; the Players page's 30-second redraw puts the same page back."""
    from engine import gamelog as GL
    path, rosters = _fresh()
    body = {"page": PP.page("nfl", "Josh Allen", db_path=path, data_dir=rosters),
            "log": GL.season_log("nfl", "Josh Allen", db_path=path),
            "hits": {"players": [{"player": "Josh Allen", "sport": "nfl", "team": "BUF", "position": "QB", "games": 4,
                                  "rank": 0, "headshot": ""}]},
            "logs": {"player": "Josh Allen", "stats": {"Passing Yards": [
                {"value": 252, "week": 11, "opponent": "NYJ", "home": False},
                {"value": 301, "week": 10, "opponent": "MIA", "home": False}]}},
            "news": {"sports": {"nfl": [{"title": "Josh Allen throws four touchdowns", "link": "https://example.test/1",
                                         "source": "ESPN", "epoch": 1794838306}]}},
            "board": {"sport": "nfl", "recommendations": [], "player_stats": {}}}

    def run(browser, port):
        ctx = browser.new_context(viewport={"width": 412, "height": 823}, is_mobile=True, has_touch=True,
                                  device_scale_factor=1, service_workers="block")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        local = f"http://127.0.0.1:{port}/"
        page.route(lambda u: not u.startswith(local), lambda r: r.abort())
        # A factory, not a default argument: Playwright hands a two-parameter
        # handler the request as its second argument.
        def answer(key):
            return lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body[key]))
        for pattern, key in (("**/api/players/search*", "hits"), ("**/api/players/logs*", "logs"),
                             ("**/api/players/page*", "page"), ("**/api/players/gamelog*", "log"),
                             ("**/data/news.json*", "news"), ("**/api/recommendations*", "board"),
                             ("**/data/recommendations*", "board")):
            page.route(pattern, answer(key))
        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                             "catch(e){}")
        page.goto(f"{local}index.html?sport=nfl#player/josh-allen", wait_until="load")
        page.wait_for_selector(".pp .pp-nums .pp-num", timeout=30000)
        page.wait_for_timeout(800)
        out = {"hero": page.inner_text(".pp-hero"),
               "tabs": page.eval_on_selector_all(".pp-tab", "els => els.map((e) => e.textContent)"),
               "nums": page.eval_on_selector_all(".pp-num", "els => els.map((e) => e.innerText.replace(/\\s+/g, ' '))"),
               "card": page.evaluate("!!document.querySelector('.pp-tonight .profile')"),
               "splitlet": page.eval_on_selector_all(".pp-splitlet td.gl-fix", "els => els.map((e) => e.textContent)")}
        page.click('.pp-tab[data-pp-tab="splits"]')
        out["splits"] = page.evaluate("""[document.querySelector('[data-pp-panel="splits"]').hidden,
            document.querySelector('[data-pp-panel="overview"]').hidden,
            document.querySelectorAll('[data-pp-panel="splits"] tbody tr').length]""")
        page.click('.pp-tab[data-pp-tab="log"]')
        page.wait_for_selector('[data-pp-panel="log"] .gl-table', timeout=20000)
        out["redraw"] = page.evaluate("""async () => { const before = document.querySelector('.pp');
            await renderPlayers();
            const after = document.querySelector('.pp');
            return [before === after, document.querySelector('.pp-tab.on').dataset.ppTab,
                    !!after.querySelector('[data-pp-panel="log"] .gl-table'),
                    !!after.querySelector('.pp-tonight .profile')]; }""")
        out["errors"] = errors
        ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    assert "Josh" in got["hero"] and "Allen" in got["hero"] and "#17" in got["hero"] and "QB" in got["hero"], got["hero"]
    assert "Age " in got["hero"] and "237 lb" in got["hero"], got["hero"]
    assert got["tabs"] == ["Overview", "News", "Stats", "Bio", "Splits", "Game Log"], got["tabs"]
    assert len(got["nums"]) == 4 and "YDS 803 2nd" in got["nums"][0], got["nums"]
    assert got["card"], "the market card the page always drew, kept in Overview"
    assert got["splitlet"][:2] == ["This game", "November"], got["splitlet"]
    assert got["splits"][0] is False and got["splits"][1] is True and got["splits"][2] >= 9, got["splits"]
    assert got["redraw"] == [True, "log", True, True], ("the redraw rebuilt the page", got["redraw"])
    assert not got["errors"], got["errors"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
