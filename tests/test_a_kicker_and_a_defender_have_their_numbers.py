"""A kicker's and a defender's pages carry their numbers (2026-11-17).

Ethan, with Cameron Dicker's page (Stats: "No seasons on file yet"; Game Log:
"No games are on file for this player yet. A game is added once its box
score is in."): "Also the player page is missing a bunch of data".

WHY IT WAS EMPTY. The weekly file's kicking and defensive columns were read
for the three markets the board prices (a kicker's points and field goals, a
defender's tackles) and no more, and the player page and the game log drew
passing, rushing and receiving alone, so a kicker's and a defender's rows
had nowhere to go.

NOW engine/ingest stores a kicker's tries, extra points, long and makes from
50 and beyond, and a defender's solo tackles, sacks, tackles for loss, hits
on the quarterback, interceptions, passes defended, forced fumbles and
touchdowns (NFL_KICKING_MARKETS, NFL_DEFENSE_MARKETS); the night's box score
carries the same (engine/boxsettle.special_rows, pinned in
test_bets_settle_minutes_after_the_final); college's play file gives its
kickers' field goals (engine/sources/cfbstats.KICK_MARKETS); engine/gamelog
draws Kicking and Defense, a long being a season's best game and never a
sum (PEAK); engine/playerpage leads those pages with their numbers and
places; the server fills every season already on file once, at start
(launch._fill_football_box_lines); and a page whose position no feed covers
(a punter, a college defender) says so instead of "No seasons on file yet".

Run directly: `python3 tests/test_a_kicker_and_a_defender_have_their_numbers.py`
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

from engine import db as _db, gamelog as GL, ingest as IG, playerpage as PP     # noqa: E402
from engine.sources import cfbstats as CS                                      # noqa: E402

PAGE_JS = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")


def _week(name, team, opp, wk, pos, group, kind="REG", **stats):
    return {"season_type": kind, "week": str(wk), "player_display_name": name, "recent_team": team,
            "opponent_team": opp, "position": pos, "position_group": group,
            **{k: str(v) for k, v in stats.items()}}


def _kick(name, team, opp, wk, made, tried, long_, fifty=0, pat=(1, 1), kind="REG"):
    return _week(name, team, opp, wk, "K", "SPEC", kind=kind, fg_made=made, fg_att=tried,
                 fg_long=long_ if made else "NA", fg_made_50_59=fifty, fg_made_60_=0, pat_made=pat[0],
                 pat_att=pat[1])


def _stop(name, team, opp, wk, solo, ast, sacks=0, tfl=0, hits=0, picks=0, pd=0, ff=0, td=0, pos="OLB"):
    return _week(name, team, opp, wk, pos, "LB", def_tackles_solo=solo, def_tackle_assists=ast, def_sacks=sacks,
                 def_tackles_for_loss=tfl, def_qb_hits=hits, def_interceptions=picks, def_pass_defended=pd,
                 def_fumbles_forced=ff, def_tds=td)


WEEKLY = [
    _kick("Cameron Dicker", "LAC", "KC", 1, 3, 3, 52, fifty=1, pat=(2, 2)),
    _kick("Cameron Dicker", "LAC", "LV", 2, 0, 1, 0, pat=(3, 3)),
    _kick("Cameron Dicker", "LAC", "DEN", 3, 2, 3, 47, pat=(1, 1)),
    _kick("Cameron Dicker", "LAC", "HOU", 19, 1, 1, 38, kind="POST"),
    _kick("Cameron Dicker", "LAC", "SF", 0, 2, 2, 40, kind="PRE"),
    _kick("Other Leg", "KC", "LAC", 1, 1, 2, 33, pat=(1, 2)),
    _stop("Will Anderson Jr.", "HOU", "JAX", 1, 4, 2, sacks=1.5, tfl=2, hits=3, ff=1),
    _stop("Will Anderson Jr.", "HOU", "TEN", 2, 3, 1, sacks=1, hits=2, pd=1),
    _stop("Kyle Hamilton", "BAL", "CLE", 1, 6, 3, picks=1, pd=2, td=1, pos="SS"),
    _week("JK Scott", "LAC", "KC", 1, "P", "SPEC", punts=5),
    _week("Justin Herbert", "LAC", "KC", 1, "QB", "QB", completions=20, attempts=30, passing_yards=250),
]


def _by(rows):
    out: dict = {}
    for r in rows:
        out.setdefault((r["player"], r["period"]), {})[r["market"]] = r["value"]
    return out


# --- the weekly file ---------------------------------------------------------------------------
def test_the_weekly_file_gives_a_kicker_and_a_defender_their_whole_line():
    rows = IG.nfl_box_rows(WEEKLY, 2026)
    got = _by(rows)
    assert got[("Cameron Dicker", "001")] == {"fg_att": 3, "fg_50": 1, "xp_made": 2, "xp_att": 2, "fg_long": 52}
    assert got[("Cameron Dicker", "002")] == {"fg_att": 1, "fg_50": 0, "xp_made": 3, "xp_att": 3}, \
        "no field goal made is no long, not a 0-yard kick"
    assert ("Cameron Dicker", "019") in got, "a playoff game is his too"
    assert ("Cameron Dicker", "000") not in got, "a preseason game is not"
    assert got[("Will Anderson Jr.", "001")] == {
        "tackles_solo": 4, "def_sacks": 1.5, "def_tfl": 2, "def_qb_hits": 3, "def_int": 0, "def_pd": 0,
        "def_ff": 1, "def_td": 0}
    assert got[("Kyle Hamilton", "001")]["def_int"] == 1 and got[("Kyle Hamilton", "001")]["def_td"] == 1
    assert not any(p in ("JK Scott", "Justin Herbert") for p, _ in got), \
        "a punter's and a passer's rows come from elsewhere or not at all"
    one = next(r for r in rows if r["player"] == "Cameron Dicker" and r["period"] == "001")
    assert (one["position"], one["game_id"], one["team"], one["opponent"]) == ("K", "LAC-001", "LAC", "KC"), \
        "keyed as the board's rows for the same game, so the game log reads them as one game"
    assert {r["position"] for r in rows if r["player"] == "Kyle Hamilton"} == {"DEF"}
    src = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    assert src.count("rows += nfl_box_rows(weekly, season)") == 2, "the daily pull and the full ingest both store them"


def _history(rows=(), games=()):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", list(games))
    if rows:
        _db.upsert_player_logs(conn, list(rows))
    conn.commit()
    return path, conn


def _nfl_world():
    from engine.ingest import nfl_player_log_rows
    weekly = [r for r in WEEKLY if r["season_type"] != "PRE"]
    rows = nfl_player_log_rows(weekly, 2026) + IG.nfl_box_rows(weekly, 2026)
    games = [("nfl", 2026, "001", "KC@LAC", "LAC", "KC", 27, 20, "2026-09-13"),
             ("nfl", 2026, "002", "LAC@LV", "LV", "LAC", 17, 24, "2026-09-20"),
             ("nfl", 2026, "003", "DEN@LAC", "LAC", "DEN", 30, 13, "2026-09-27"),
             ("nfl", 2026, "001", "JAX@HOU", "HOU", "JAX", 21, 17, "2026-09-13"),
             ("nfl", 2026, "002", "HOU@TEN", "TEN", "HOU", 10, 20, "2026-09-20"),
             ("nfl", 2026, "001", "BAL@CLE", "CLE", "BAL", 14, 31, "2026-09-13")]
    return _history(rows, games)


# --- the game log --------------------------------------------------------------------------------
def test_the_game_log_draws_a_kickers_season_with_the_best_kick_as_the_long():
    path, conn = _nfl_world()
    conn.close()
    log = GL.season_log("nfl", "Cameron Dicker", db_path=path)
    assert [g["key"] for g in log["groups"]] == ["kicking"], log["groups"]
    cols = [c["key"] for c in log["groups"][0]["cols"]]
    assert cols == ["fg", "pct", "lng", "fg50", "xp", "pts"], cols
    t = log["totals"]
    assert t["kicking.fg"] == "6-8" and t["kicking.pct"] == 75.0, t
    assert t["kicking.lng"] == 52, "a season's long is its best kick, not a sum of longs"
    assert t["kicking.xp"] == "7-7" and t["kicking.pts"] == 25, t
    assert t["kicking.fg50"] == 1
    week2 = next(g for g in log["games"] if g.get("week") == 2)
    assert week2["values"]["kicking.fg"] == "0-1" and week2["values"]["kicking.lng"] is None
    assert GL.add_up({"fg_long": 52.0, "fg_att": 3.0}, {"fg_long": 47.0, "fg_att": 3.0}) == {"fg_long": 52.0,
                                                                                             "fg_att": 6.0}


def test_the_game_log_draws_a_defenders_season():
    path, conn = _nfl_world()
    conn.close()
    log = GL.season_log("nfl", "Will Anderson Jr.", db_path=path)
    assert [g["key"] for g in log["groups"]] == ["defense"], log["groups"]
    t = log["totals"]
    assert (t["defense.tot"], t["defense.solo"], t["defense.sack"], t["defense.qbh"]) == (10, 7, 2.5, 5), t
    assert t["defense.ff"] == 1 and t["defense.pd"] == 1


# --- the player page -----------------------------------------------------------------------------
def test_a_kickers_page_leads_with_field_goals_and_ranks_them():
    PP._RANKS.clear()
    PP._ROSTERS.clear()
    path, conn = _nfl_world()
    conn.close()
    d = PP.page("nfl", "Cameron Dicker", db_path=path, data_dir=tempfile.mkdtemp())
    assert d["role"] == "kicking", d.get("role")
    head = {h["key"]: h for h in d["headline"]}
    assert list(head) == ["fgm", "pct", "lng", "pts"]
    assert head["fgm"]["value"] == 6 and head["fgm"]["rank"] == 1, "six makes, the playoff game's included"
    assert head["pct"]["value"] == 75.0 and head["pts"]["value"] == 25
    assert head["lng"]["value"] == 52 and head["lng"]["rank"] is None, "one kick is shown, not ranked"
    assert [t["id"] for t in d["last"]["tiles"]] == ["kicking.fg", "kicking.lng", "kicking.xp", "kicking.pts"]
    assert "no_stats" not in d


def test_a_defenders_page_leads_with_tackles_and_sacks():
    PP._RANKS.clear()
    PP._ROSTERS.clear()
    path, conn = _nfl_world()
    conn.close()
    d = PP.page("nfl", "Will Anderson Jr.", db_path=path, data_dir=tempfile.mkdtemp())
    assert d["role"] == "defense", d.get("role")
    head = {h["key"]: h for h in d["headline"]}
    assert list(head) == ["tot", "sack", "int", "pd"]
    assert head["sack"]["value"] == 2.5 and head["sack"]["rank"] == 1
    assert head["tot"]["value"] == 10 and head["tot"]["rank"] == 1, "ten tackles to Kyle Hamilton's nine"
    assert head["int"]["value"] == 0 and head["int"]["rank"] is None, "a count of nothing is not a place"
    for pos, kind in (("K", "kicking"), ("PK", "kicking"), ("CB", "defense"), ("EDGE", "defense"),
                      ("DT", "defense"), ("FS", "defense"), ("WR", "receiving")):
        assert PP.role("nfl", pos, {}) == kind, pos
    assert PP.role("nfl", "", {"fg_att": 3.0}) == "kicking", "a position the roster left blank is read off the volume"
    assert PP.role("nfl", "", {"tackles_ast": 5.0}) == "defense"


def test_the_league_places_are_among_kickers_and_among_defenders():
    PP._RANKS.clear()
    path, conn = _nfl_world()
    try:
        defense = PP.rank_table(conn, "nfl", 2026, "defense", db_path=path)
        kicking = PP.rank_table(conn, "nfl", 2026, "kicking", db_path=path)
    finally:
        conn.close()
    assert defense["tot"] == {"Will Anderson Jr.": 1, "Kyle Hamilton": 2}, defense["tot"]
    assert defense["sack"] == {"Will Anderson Jr.": 1}, "no sack is no place"
    assert set(kicking["fgm"]) == {"Cameron Dicker", "Other Leg"}, "only kickers are among kickers"
    assert kicking["pct"] == {"Cameron Dicker": 1}, \
        "a percentage needs RATE_SHARE of the leader's tries: two tries to his eight is too few"
    assert "lng" not in kicking, "a long is not ranked"


def test_a_punters_page_and_a_college_defenders_page_say_why_they_are_empty():
    assert PP.no_stats_note("nfl", "P") == ("Our NFL stats feed doesn't include punting, "
                                            "so there are no numbers to show here.")
    assert PP.no_stats_note("nfl", "LS") == ("Box scores keep no numbers for long snappers, "
                                             "so there are none to show here.")
    for pos in ("OT", "G", "C", "OL"):
        assert PP.no_stats_note("cfb", pos) == PP.no_stats_note("nfl", pos) == \
            "Box scores keep no numbers for offensive linemen, so there are none to show here.", pos
    assert "college stats feed doesn't include defense" in PP.no_stats_note("cfb", "LB")
    assert PP.no_stats_note("nfl", "LB") == "" and PP.no_stats_note("nfl", "K") == "", "the NFL's feed has both"
    assert PP.no_stats_note("cfb", "PK") == "" and PP.no_stats_note("nba", "P") == ""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "rosters_nfl.json"), "w", encoding="utf-8") as fh:
        json.dump({"teams": {"LAC": {"players": [{"player": "JK Scott", "team": "LAC", "position": "P",
                                                   "number": 16}]}}}, fh)
    PP._ROSTERS.clear()
    path, conn = _history()
    conn.close()
    page = PP.page("nfl", "JK Scott", db_path=path, data_dir=d)
    assert page["no_stats"].startswith("Our NFL stats feed doesn't include punting"), page
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    stubs = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
             "const escapeHtml = esc, escapeAttr = esc; const trueMinus = (x) => x;"
             "const document = { addEventListener() {} };\n")
    js = stubs + PAGE_JS + f"""
process.stdout.write(JSON.stringify([plrStatsHTML({json.dumps(page)}), plrStatsHTML({{}}),
  plrNum(52, "LNG", true), plrNum(100, "FT%", false), plrNum(41.0, "3P%", true)]));"""
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    punter, nobody, lng, ftp, fg3p = json.loads(out.stdout)
    assert lng == "52", "a long is one kick, never a game's average (52.0)"
    assert (ftp, fg3p) == ("100.0", "41.0"), "a percentage reads to a tenth, as FG% does"
    gl_js = (ROOT / "web" / "js" / "gamelog.js").read_text(encoding="utf-8")
    assert 'const GL_RATES = ["CMP%", "AVG", "RTG", "FG%", "3P%", "FT%", "SV%"];' in gl_js
    assert punter == ('<p class="plr-quiet">Our NFL stats feed doesn&#39;t include punting, '
                      'so there are no numbers to show here.</p>'), punter
    assert nobody == '<p class="plr-quiet">No seasons on file yet.</p>'
    assert "const quiet = !(d && (d.games || []).length) && page._plr.noStats;" in PAGE_JS, \
        "the Game Log tab says the same, not that a box score is still to come"


def test_the_overview_says_why_a_page_has_no_numbers():
    """A punter's Overview drew nothing at the top: its first block is the
    season's numbers, and with none the server's reason (`no_stats`, the
    line the Stats and Game Log menus already show) never reached it. A
    team defense with no games said "No games on file" instead of what it
    is."""
    i = PAGE_JS.index("function plrFill(")
    fn = PAGE_JS[i:PAGE_JS.index("\n}\n", i)]
    # The last season played stands between them (2026-11-17, `prior`): a page with no numbers at all has none.
    assert 'plrSeasonHTML(d) || plrPriorHTML(d) || (d.no_stats ? quiet(d.no_stats) : "")' in fn, \
        "games with no numbers: the Overview leads with the reason"
    assert 'quiet(d.no_stats || "No games on file for this player yet.' in fn, \
        "no games at all: the server's reason first, the roster line after"


def test_a_page_that_finds_nobody_says_so_and_one_that_failed_says_that():
    """The server's empty answer means the league holds nobody by the name (no box score, no roster: a player
    gone to another league, an old link); no answer at all means the page could not load. Both said "could
    not load", on every menu but the Overview, and a failed load threw before saying anything (`d.no_stats`
    read off null)."""
    i = PAGE_JS.index("function plrFill(")
    fn = PAGE_JS[i:PAGE_JS.index("\n}\n", i)]
    # A fighter's page has its own filler (plrFillUfc), which says the same two things in a fighter's words.
    assert fn.startswith('function plrFill(page, d) {\n  if (page._plr.sport === "ufc") return plrFillUfc(page, d);\n'
                         '  page._plr.noStats = (d && d.no_stats) || "";'), "a failed load reaches its message"
    ufc = PAGE_JS[PAGE_JS.index("function plrFillUfc("):]
    assert "We have no UFC fighter named ${escapeHtml(page._plr.player)}: no dossier or tracked fight lists them." in ufc
    assert ': "This page could not load. Open it again in a minute."}</p>`;' in ufc[:ufc.index("\n}\n")]
    assert "We have no ${escapeHtml(lgCode(sport))} player named ${escapeHtml(player)}: no box" in fn
    assert ': "This page could not load. Open it again in a minute."}</p>`;' in fn
    assert 'page.querySelectorAll(".plr-panel[data-plr-panel]:not([data-plr-panel=\\"overview\\"]), .plr-season")' in fn, \
        "the Overview's first block says it too"


def test_a_name_with_no_games_is_never_a_near_names_page():
    """Live, 17 Nov: JK Scott, the Chargers' punter, has no games on file, and
    his page and his Game Log tab drew Nick Scott's, the Panthers' safety,
    tackles and all: the nearest stored name stood in for one with none."""
    rows = []
    for wk, tot in (("009", 6.0), ("010", 1.0)):
        rows.append({"sport": "nfl", "season": 2026, "period": wk, "game_id": f"CAR-{wk}", "player": "Nick Scott",
                     "team": "CAR", "opponent": "NO", "position": "DEF", "home": 1, "market": "tackles_ast",
                     "value": tot})
    rows.append({"sport": "nfl", "season": 2026, "period": "010", "game_id": "CHI-010", "player": "DJ Moore",
                 "team": "CHI", "opponent": "GB", "position": "WR", "home": 1, "market": "receptions", "value": 6.0})
    rows.append({"sport": "nfl", "season": 2026, "period": "010", "game_id": "TEN-010", "player": "TJ Cope",
                 "team": "TEN", "opponent": "HOU", "position": "WR", "home": 1, "market": "receptions", "value": 3.0})
    rows.append({"sport": "nfl", "season": 2026, "period": "010", "game_id": "HOU-010", "player": "Ace Flagg",
                 "team": "HOU", "opponent": "TEN", "position": "WR", "home": 0, "market": "receptions", "value": 2.0})
    for who, club, pos, market in (("Kimani Vidal", "LAC", "RB", "carries"), ("Anthony Richardson", "IND", "QB", "pass_att"),
                                   ("Anthony Gould", "IND", "WR", "receptions"), ("Caleb Banks", "MIN", "DEF", "tackles_ast")):
        rows.append({"sport": "nfl", "season": 2026, "period": "010", "game_id": f"{club}-010", "player": who,
                     "team": club, "opponent": "KC", "position": pos, "home": 1, "market": market, "value": 4.0})
    path, conn = _history(rows)
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "rosters_nfl.json"), "w", encoding="utf-8") as fh:
        json.dump({"teams": {
            "LAC": {"players": [{"player": "JK Scott", "team": "LAC", "position": "P", "number": 16},
                                {"player": "Kimani Vidal Jr.", "team": "LAC", "position": "RB", "number": 30}]},
            "CHI": {"players": [{"player": "D.J. Moore", "team": "CHI", "position": "WR", "number": 2}]},
            "CAR": {"players": [{"player": "Nick Scott", "team": "CAR", "position": "DB", "number": 21}]},
            "IND": {"players": [{"player": "Anthony Richardson Sr.", "team": "IND", "position": "QB", "number": 5}]},
            "MIN": {"players": [{"player": "Caleb Tiernan", "team": "MIN", "position": "OT", "number": 72}]},
            "NE": {"players": [{"player": "New England Patriots", "team": "NE", "position": "DEF"}]}}}, fh)
    PP._ROSTERS.clear()
    try:
        assert PP.stored_name(conn, "nfl", "JK Scott", "", d) == "", "the roster's punter is not the Panthers' safety"
        assert PP.stored_name(conn, "nfl", "D.J. Moore", "", d) == "DJ Moore", "the same name written another way"
        assert PP.stored_name(conn, "nfl", "Kimani Vidal Jr.", "", d) == "Kimani Vidal", \
            "the box scores drop the suffix the roster keeps"
        assert PP.stored_name(conn, "nfl", "Anthony Richardson Sr.", "", d) == "Anthony Richardson", \
            "live, 17 Nov: his page drew Anthony Gould's, a near name on his own club"
        assert PP.stored_name(conn, "nfl", "Caleb Tiernan", "MIN", d) == "", \
            "a lineman with no games is not his club's Caleb Banks"
        assert PP.stored_name(conn, "nfl", "Nik Scot", "", d) == "Nick Scott", "a typed name no roster carries"
        # Live, 17 Nov: college's page for Cooper Flagg (in the NBA now) drew TJ Cope's, because "Cope" is
        # near "Cooper". One word near one word is a guess for a search list, not whose page this is.
        assert PP.stored_name(conn, "nfl", "Cooper Flagg", "", d) == "", "a name on no roster is not a near word's"
        assert PP.page("nfl", "Cooper Flagg", db_path=path, data_dir=d) == {}, "and the page knows nobody by it"
        assert PP.stored_name(conn, "nfl", "Tj Cope", "", d) == "TJ Cope", "the same name, another case"
        assert PP.stored_name(conn, "nfl", "Nick Scot", "", d) == "Nick Scott", "a whole name misspelled still is"
        from engine.statlogs import resolve_player
        assert resolve_player(conn, "nfl", "Cooper Flagg") == "" and resolve_player(conn, "nfl", "Nik Scot") == "Nick Scott", \
            "the rule is the resolver's, so a log and a matchup history keep it too"
        # Live, after the first fix: Cooper Flagg drew Ace Flagg's page, his twin at Maine, the whole-name
        # score carried by the surname. A misspelling is near word by word.
        assert PP.stored_name(conn, "nfl", "Cooper Flagg", "", d) == "", "the twin is not the same player"
        assert resolve_player(conn, "nfl", "Ace Flag") == "Ace Flagg", "and a letter off is still a misspelling"
        assert PP.stored_name(conn, "nfl", "Nick Scott", "", d) == "Nick Scott"
        assert PP.core_name("Nolan Smith Jr.") == PP.core_name("nolan smith") == "nolan smith"
        assert PP.core_name("D.J. Moore") == PP.core_name("DJ Moore") == "dj moore"
        assert PP.core_name("A. J. Brown III") == "aj brown"
    finally:
        conn.close()
    page = PP.page("nfl", "JK Scott", db_path=path, data_dir=d)
    assert page["player"] == "JK Scott" and page["position"] == "P" and page["seasons"] == []
    assert page["no_stats"].startswith("Our NFL stats feed doesn't include punting"), page
    rich = PP.page("nfl", "Anthony Richardson Sr.", team="IND", db_path=path, data_dir=d)
    assert (rich["player"], rich["position"], rich["bio"].get("number")) == ("Anthony Richardson", "QB", "5"), \
        "the box scores' spelling still wears the roster's number and position (a Jr.'s page read 'DEF')"
    assert PP.page("nfl", "Caleb Tiernan", team="MIN", db_path=path, data_dir=d)["no_stats"].startswith(
        "Box scores keep no numbers for offensive linemen")
    assert PP.page("nfl", "New England Patriots", team="NE", db_path=path, data_dir=d)["no_stats"] == PP.TEAM_DEFENSE, \
        "the roster's fantasy team defense is not a player"


def test_a_page_with_no_numbers_says_why():
    """The live sweep of 17 Nov: a tight end whose every game on file carries
    zeros (Justin Joly) had a blank Stats tab, not even "No seasons on file
    yet"; and college rosters list schools whose games the play file does
    not cover, their pages empty without a word."""
    rows = [{"sport": "nfl", "season": 2026, "period": wk, "game_id": f"MIA-{wk}", "player": "Justin Joly",
             "team": "MIA", "opponent": "BUF", "position": "TE", "home": 1, "market": m, "value": 0.0}
            for wk in ("009", "010") for m in ("targets", "receptions")]
    games = [("cfb", 2026, "2026-11-14", "401", "OSU", "MICH", 31, 24, "2026-11-14")]
    path, conn = _history(rows, games)
    conn.close()
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "rosters_cfb.json"), "w", encoding="utf-8") as fh:
        json.dump({"teams": {"WORU": {"players": [{"player": "Logan South", "team": "WORU", "position": "PK"}]},
                             "OSU": {"players": [{"player": "Brennen Schramm", "team": "OSU", "position": "WR"}]}}}, fh)
    PP._ROSTERS.clear()
    PP._RANKS.clear()
    joly = PP.page("nfl", "Justin Joly", db_path=path, data_dir=tempfile.mkdtemp())
    assert joly["seasons"] == [2026] and joly["no_stats"] == PP.NO_NUMBERS, joly.get("no_stats")
    assert PP.page("cfb", "Logan South", db_path=path, data_dir=d)["no_stats"] == PP.NOT_FBS
    assert "no_stats" not in PP.page("cfb", "Brennen Schramm", db_path=path, data_dir=d), \
        "a backup at a school with games on file has simply not played: no note"
    page_js = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
    assert "if (!(c.rows || []).length || !(c.groups || []).length) {" in page_js, \
        "seasons with no table draw the note, not a blank tab"


# --- the seasons already on file -----------------------------------------------------------------
def test_the_fill_reads_each_season_once_and_a_finished_one_off_the_disk():
    from engine.sources import nflverse
    path, conn = _history()
    calls = []
    real = nflverse.load_weekly_stats

    def load(season, ttl=None):
        calls.append((season, ttl))
        return [dict(r) for r in WEEKLY if r["season_type"] != "PRE"]
    nflverse.load_weekly_stats = load
    try:
        # A night's box score for the newest season is one game, not its season.
        _db.upsert_player_logs(conn, [{"sport": "nfl", "season": 2026, "period": "011", "game_id": "LAC-011-box",
                                       "player": "Cameron Dicker", "team": "LAC", "opponent": "PIT",
                                       "position": "K", "home": 1, "market": "fg_att", "value": 2.0}])
        got = IG.backfill_nfl_box(conn, [2026, 2025, 2025])
        assert got["seasons"] == [2025, 2026] and got["rows"] > 0 and not got["skipped"], got
        assert calls == [(2025, IG.FINISHED_SEASON_TTL), (2026, None)], \
            "a finished season off the copy on disk; the newest at the fetcher's own age"
        board = {r[0] for r in conn.execute("SELECT DISTINCT market FROM player_game_logs WHERE sport='nfl' "
                                            "AND season=2025 AND position IN ('K', 'DEF')")}
        assert {"kick_pts", "fg_made", "tackles_ast"} <= board, \
            "the board's own kicker and defender rows too: a season ingested before 2026-10-10 has none"
        calls.clear()
        again = IG.backfill_nfl_box(conn, [2025, 2026])
        assert again == {"seasons": [], "rows": 0, "skipped": []} and calls == [], "a season on file is not read"
        # Live, 17 Nov: the first fill wrote the box rows and not the board's,
        # so Dicker's 2025 read "—" for FG and PTS. A season half-filled so is
        # read again.
        conn.execute("DELETE FROM player_game_logs WHERE sport='nfl' AND season=2025 AND market='kick_pts'")
        conn.commit()
        third = IG.backfill_nfl_box(conn, [2025, 2026])
        assert third["seasons"] == [2025] and calls == [(2025, IG.FINISHED_SEASON_TTL)], third
    finally:
        nflverse.load_weekly_stats = real
    from engine.sources.fetch import DataUnavailable

    def gone(season, ttl=None):
        raise DataUnavailable("the release is not up")
    nflverse.load_weekly_stats = gone
    try:
        missing = IG.backfill_nfl_box(conn, [2024])
        assert missing["seasons"] == [] and missing["skipped"] == ["nfl box rows 2024: the release is not up"]
    finally:
        nflverse.load_weekly_stats = real
        conn.close()


def test_the_server_fills_them_at_start_and_never_falls_over_on_it():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    chores = src[src.index("def _startup_chores"):]
    assert chores.index("_fill_missing_lines()") < chores.index("playerpage.warm(delay=0)"), \
        "the lines are in before the ranks are built on them"
    fill = src[src.index("def _fill_missing_lines"):src.index("def _kick_chores")]
    for call in ('football("nfl", _ing.backfill_nfl_box)', 'football("cfb", _ing.backfill_cfb_kicks)',
                 "_nhl.backfill_lines(conn, int(season))"):
        assert call in fill, call
    assert "WHERE sport=? AND market=?" in fill and "PASS_YDS" in fill, \
        "the seasons the pages show, not the games table's back to 1999"
    assert "_pp.forget_ranks(league)" in fill, "a table built mid-fill is not kept six hours"
    PP._RANKS.clear()
    PP._RANKS[("nfl", 2026, "kicking")] = (0.0, {"fgm": {"Cameron Dicker": 1}})
    PP._RANKS[("nba", 2026, "box")] = (0.0, {})
    assert PP.forget_ranks("nfl") == 1 and list(PP._RANKS) == [("nba", 2026, "box")]
    PP._RANKS.clear()
    import launch
    from engine import db as dbmod
    real = dbmod.connect

    def broken(*a, **k):
        raise OSError("disk unplugged")
    dbmod.connect = broken
    try:
        assert launch._fill_missing_lines() == {}
    finally:
        dbmod.connect = real


# --- college ---------------------------------------------------------------------------------------
def _play(gid, team, **cols):
    return {"game_id": gid, "week": "3", "team": team, **{k: str(v) for k, v in cols.items()}}


COLLEGE_GAMES = {"401": {"period": "2026-09-12", "home": "OSU", "away": "TEX", "home_name": "Ohio State",
                         "away_name": "Texas", "points": 0}}


def test_college_counts_its_kickers_field_goals_off_the_play_file():
    plays = [
        _play("401", "Ohio State", field_goal_attempt_player="Jayden Fielding", field_goal_attempt_player_id="9",
              field_goal_made_player="Jayden Fielding", field_goal_made_stat="52"),
        _play("401", "Ohio State", field_goal_attempt_player="Jayden Fielding", field_goal_missed_player="Jayden Fielding",
              field_goal_missed_stat="45"),
        _play("401", "Ohio State", field_goal_attempt_player="Jayden Fielding",
              field_goal_made_player="Jayden Fielding", field_goal_made_stat="30"),
        _play("401", "Texas", field_goal_attempt_player="Mason Shipley", field_goal_missed_player="Mason Shipley",
              field_goal_missed_stat="48"),
        _play("401", "Texas", rush_player="Quintrevion Wisner", rush_yds="6", yards_to_goal="60"),
    ]
    out = CS.parse_player_stats(plays, 2026, COLLEGE_GAMES, {"9": {"name": "Jayden Fielding", "position": "PK"}})
    got = {}
    for r in out["rows"]:
        got.setdefault(r["player"], {})[r["market"]] = r["value"]
    assert got["Jayden Fielding"] == {"fg_att": 3.0, "fg_made": 2.0, "fg_long": 52.0, "fg_50": 1.0}, \
        "no anytime-touchdown zero for a kicker who only kicked"
    assert got["Mason Shipley"] == {"fg_att": 1.0, "fg_made": 0.0, "fg_50": 0.0}, "0 of 1, and no long"
    assert got["Quintrevion Wisner"]["anytime_td"] == 0.0, "a back's zero is still a played-and-did-not-score"
    fielding = next(r for r in out["rows"] if r["player"] == "Jayden Fielding")
    assert (fielding["team"], fielding["opponent"], fielding["position"], fielding["home"]) == ("OSU", "TEX", "PK", 1)
    assert set(CS.KICK_MARKETS) <= set(CS.MARKETS)


def test_the_college_fill_writes_the_kicks_alone():
    real = (CS.fetch_season, CS.fetch_rosters, IG.cfb_games_for)
    asked = []

    def season(s, games, ttl=None, roster=None, also=None):
        asked.append((s, ttl))
        return {"rows": [
            {"sport": "cfb", "season": s, "period": "2026-09-12", "game_id": "401", "player": "Jayden Fielding",
             "team": "OSU", "opponent": "TEX", "position": "PK", "home": 1, "market": m, "value": v}
            for m, v in (("fg_att", 3.0), ("fg_made", 2.0), ("carries", 1.0))]}
    CS.fetch_season = season
    CS.fetch_rosters = lambda s: {}
    IG.cfb_games_for = lambda conn, s: COLLEGE_GAMES
    path, conn = _history()
    try:
        got = IG.backfill_cfb_kicks(conn, [2025, 2026])
        assert got["seasons"] == [2025, 2026] and got["rows"] == 4, got
        assert asked == [(2025, IG.FINISHED_SEASON_TTL), (2026, None)], asked
        markets = {r[0] for r in conn.execute("SELECT market FROM player_game_logs WHERE sport='cfb'")}
        assert markets == {"fg_att", "fg_made"}, "the play file's other rows are the weekly ingest's to write"
        asked.clear()
        assert IG.backfill_cfb_kicks(conn, [2025, 2026])["seasons"] == [] and asked == []
    finally:
        CS.fetch_season, CS.fetch_rosters, IG.cfb_games_for = real
        conn.close()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
