"""Every player you can look up has a game log (2026-11-16).

Ethan, with ESPN's game log for Joe Burrow: "we should have game logs for every
player too that you can look up and see for each player."

engine/gamelog.season_log pivots one player's season out of the history file
(`player_game_logs`) into a line a game: the day and the week, the opponent and
where (read off the games table, not the log row's own flag), the result and
the score, the league's own columns in box-score groups, a basketball game he
sat flagged and left out of the totals, then the season's totals and per-game
averages. server.py serves it free at /api/players/gamelog; js/gamelog.js draws
it in a sheet from every player page's "Game log" door (app.js chartDoor).

Run directly: `python3 tests/test_every_player_has_a_game_log.py`
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

from engine import db as _db, gamelog as GL                                # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "js" / "gamelog.js").read_text(encoding="utf-8")


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    games = [("nfl", 2026, "010", "CIN@PIT", "PIT", "CIN", 27, 33, "2026-11-09"),
             ("nfl", 2026, "011", "TB@CIN", "CIN", "TB", 20, 23, "2026-11-16"),
             ("nfl", 2025, "005", "CIN@BAL", "BAL", "CIN", 13, 35, "2025-10-05"),
             ("nba", 2026, "2026-11-14", "g1", "BOS", "IND", 120, 110, "2026-11-14"),
             ("nba", 2026, "2026-11-15", "g2", "PHI", "BOS", 105, 99, "2026-11-15"),
             ("nhl", 2026, "2026-11-15", "n1", "TOR", "BOS", 3, 2, "2026-11-15"),
             ("mlb", 2026, "2026-06-01", "m1", "NYY", "BOS", 5, 3, "2026-06-01")]
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", games)
    rows = []

    def log(sport, season, period, gid, player, team, opp, pos, stats):
        for m, v in stats.items():
            rows.append((sport, season, period, gid, player, team, opp, pos, 1, m, v))
    log("nfl", 2026, "010", "CIN-010", "Joe Burrow", "CIN", "PIT", "QB",
        {"pass_cmp": 25, "pass_att": 35, "pass_yds": 254, "pass_td": 1, "pass_int": 1, "carries": 5, "rush_yds": 20,
         "rush_td": 0, "receptions": 0})
    log("nfl", 2026, "011", "CIN-011", "Joe Burrow", "CIN", "TB", "QB",
        {"pass_cmp": 20, "pass_att": 31, "pass_yds": 207, "pass_td": 2, "pass_int": 0, "carries": 1, "rush_yds": -1,
         "rush_td": 0, "receptions": 0})
    log("nfl", 2025, "005", "CIN-005", "Joe Burrow", "CIN", "BAL", "QB",
        {"pass_cmp": 22, "pass_att": 30, "pass_yds": 292, "pass_td": 4, "pass_int": 0})
    log("nfl", 2026, "010", "CIN-010", "Ja'Marr Chase", "CIN", "PIT", "WR",
        {"receptions": 6, "targets": 9, "rec_yds": 85, "rec_td": 1, "carries": 0})
    log("nba", 2026, "2026-11-14", "g1", "Jaylen Brown", "BOS", "IND", "G",
        {"min": 36, "pts": 31, "reb": 6, "ast": 4, "stl": 1, "blk": 0, "tov": 2, "fgm": 11, "fga": 20, "fg3m": 3,
         "fg3a": 7, "ftm": 6, "fta": 7, "oreb": 1})
    log("nba", 2026, "2026-11-15", "g2", "Jaylen Brown", "BOS", "PHI", "G", {"min": 0, "pts": 0, "reb": 0})
    log("nhl", 2026, "2026-11-15", "n1", "Joseph Woll", "TOR", "BOS", "G",
        {"saves": 28, "shots_against": 30, "goals_against": 2, "toi": 60.0})
    log("mlb", 2026, "2026-06-01", "m1", "Gerrit Cole", "NYY", "BOS", "P", {"outs": 19, "strikeouts": 8})
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return path


def test_a_quarterbacks_season_reads_like_espns():
    path = _history()
    d = GL.season_log("nfl", "Joe Burrow", db_path=path)
    assert (d["season"], d["seasons"], d["team"], d["position"]) == (2026, [2026, 2025], "CIN", "QB")
    assert [g["key"] for g in d["groups"]] == ["passing", "rushing"], "no receiving wall for a quarterback"
    assert [c["label"] for c in d["groups"][0]["cols"]] == ["CMP", "ATT", "YDS", "CMP%", "AVG", "TD", "INT", "RTG"]
    newest, older = d["games"]
    assert (newest["week"], newest["date"], newest["opponent"], newest["home"]) == (11, "2026-11-16", "TB", True)
    assert (newest["result"], newest["score"]) == ("L", "20-23")
    assert (older["home"], older["result"], older["score"]) == (False, "W", "33-27"), "where, off the games table"
    v = older["values"]
    assert (v["passing.cmp"], v["passing.att"], v["passing.yds"], v["passing.pct"], v["passing.avg"]) == \
        (25, 35, 254, 71.4, 7.3)
    assert v["passing.rtg"] == 89.5 and newest["values"]["passing.rtg"] == 105.2, "the ratings ESPN prints"
    assert (v["rushing.car"], v["rushing.yds"], v["rushing.avg"]) == (5, 20, 4.0)
    t = d["totals"]
    assert (t["passing.cmp"], t["passing.att"], t["passing.yds"], t["passing.td"], t["passing.int"]) == (45, 66, 461, 3, 1)
    assert t["passing.rtg"] == 96.8 and d["played"] == 2
    assert d["per_game"]["passing.yds"] == 230.5 and d["per_game"]["passing.pct"] is None, "a rate has no average"
    old = GL.season_log("nfl", "Joe Burrow", 2025, db_path=path)
    assert old["season"] == 2025 and old["games"][0]["result"] == "W" and old["games"][0]["score"] == "35-13"
    assert GL.season_log("nfl", "Joe Burrow", 1999, db_path=path)["season"] == 2026, "an unknown season is the latest"


def test_a_game_whose_box_score_is_not_in_yet_is_no_game_played():
    """Seen on the live file 2026-11-16: Joe Burrow's Sunday game had a row the
    night of the game (a touchdown flag) and no passing line until the week's
    box scores land. It drew a line of dashes and counted as a game played, so
    his averages fell by a ninth. Now it says the box score is not in yet and
    stays out of the games played, the totals and the averages."""
    path = _history()
    conn = _db.connect(path)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                 "VALUES ('nfl', 2026, '012', 'BAL@CIN', 'CIN', 'BAL', 30, 20, '2026-11-23')")
    conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, home, "
                 "market, value) VALUES ('nfl', 2026, '012', 'CIN-012', 'Joe Burrow', 'CIN', 'BAL', 'QB', 1, "
                 "'anytime_td', 0)")
    conn.commit()
    conn.close()
    d = GL.season_log("nfl", "Joe Burrow", db_path=path)
    newest = d["games"][0]
    assert (newest["week"], newest.get("pending"), newest["result"], newest["score"]) == (12, True, "W", "30-20")
    assert d["played"] == 2 and d["per_game"]["passing.yds"] == 230.5 and d["totals"]["passing.yds"] == 461, \
        "the game still to come is no game of zeros"
    assert GL.has_line("nfl", {"pass_att": 0}) and not GL.has_line("nfl", {"anytime_td": 1, "fp_ppr": 4.2})
    assert 'g.pending ? `<td class="gl-dnp" colspan="${cols.length}">Box score not in yet</td>`' in PAGE

def _college_copies(path):
    """Arch Manning's season as the live file held it on 2026-11-16: one game
    filed twice on the day (the box score's line beside the play file's, whose
    completions went to nobody), one a day off, one keyed by ESPN's numbers."""
    conn = _db.connect(path)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     [("cfb", 2026, "2026-10-10", "401", "OU", "TEX", 27, 24, "2026-10-10"),
                      ("cfb", 2026, "2026-09-19", "402", "TEX", "UTSA", 30, 6, "2026-09-19"),
                      ("cfb", 2026, "2026-09-12", "403", "TEX", "UTEP", 24, 23, "2026-09-12")])
    rows = []

    def log(period, gid, team, opp, stats):
        for m, v in stats.items():
            rows.append(("cfb", 2026, period, gid, "Arch Manning", team, opp, "QB", 1, m, v))
    log("2026-10-10", "401", "TEX", "OU", {"pass_cmp": 19, "pass_att": 31, "pass_yds": 260, "pass_int": 2})
    log("2026-10-10", "TEX@OU-box", "TEX", "OU", {"pass_cmp": 0, "pass_att": 9, "pass_yds": 0, "pass_td": 0,
                                                  "pass_int": 2, "carries": 5, "rush_yds": 30})
    for day, gid in (("2026-09-19", "402"), ("2026-09-20", "402-box")):
        log(day, gid, "TEX", "UTSA", {"pass_cmp": 17, "pass_att": 34, "pass_yds": 164, "pass_td": 2, "pass_int": 0,
                                      "carries": 8, "rush_yds": 53})
    log("2026-09-12", "403", "espn:251", "espn:2638", {"pass_yds": 195})
    log("2026-09-12", "403-play", "TEX", "UTEP", {"pass_cmp": 0, "pass_att": 4, "pass_yds": 0, "pass_int": 1,
                                                  "carries": 6, "rush_yds": 40})
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_a_college_game_filed_more_than_once_is_one_game():
    path = _history()
    _college_copies(path)
    d = GL.season_log("cfb", "Arch Manning", db_path=path)
    assert [g["date"] for g in d["games"]] == ["2026-10-10", "2026-09-19", "2026-09-12"], "seven rows, three games"
    at_ou, utsa, utep = d["games"]
    v = at_ou["values"]
    assert (v["passing.cmp"], v["passing.att"], v["passing.yds"], v["passing.int"]) == (19, 31, 260, 2), \
        "the box score's line, not the play file's 0 of 9"
    assert (v["rushing.car"], v["rushing.yds"], at_ou["result"], at_ou["score"]) == (5, 30, "L", "24-27"), \
        "and the play file's carries, which the box copy lacked"
    assert utsa["values"]["passing.yds"] == 164 and utsa["result"] == "W", "a copy a day off is the same game"
    assert (utep["team"], utep["opponent"], utep["values"]["passing.yds"], utep["values"]["rushing.car"]) == \
        ("TEX", "UTEP", 195, 6), "a copy keyed by ESPN's numbers takes the names"
    assert d["played"] == 3 and d["totals"]["passing.yds"] == 619 and d["totals"]["passing.att"] == 65
    nfl = GL.collapse("nfl", [{"period": "010", "game_id": "a", "team": "CIN", "opponent": "PIT", "stats": {}},
                              {"period": "010", "game_id": "b", "team": "CIN", "opponent": "PIT", "stats": {}}])
    assert len(nfl) == 2, "only where a league plays once a week and its file is known to hold copies"

def test_each_player_shows_his_own_groups_and_columns():
    path = _history()
    wr = GL.season_log("nfl", "Ja'Marr Chase", db_path=path)
    assert [g["key"] for g in wr["groups"]] == ["receiving"], "a carry row of zero is no rushing"
    assert wr["games"][0]["values"]["receiving.avg"] == 14.2
    cfb = GL._rating("cfb", {"pass_att": 35, "pass_cmp": 25, "pass_yds": 254, "pass_td": 1, "pass_int": 1})
    assert cfb == round((8.4 * 254 + 330 + 2500 - 200) / 35, 1), "college's passer efficiency"
    nba = GL.season_log("nba", "Jaylen Brown", db_path=path)
    played, sat = nba["games"][1], nba["games"][0]
    assert sat.get("dnp") is True and (sat["result"], sat["score"], sat["home"]) == ("L", "99-105", False)
    assert (played["result"], played["home"], played["values"]["box.fg"], played["values"]["box.fgp"]) == \
        ("W", True, "11-20", 55.0)
    assert nba["played"] == 1 and nba["totals"]["box.pts"] == 31 and nba["per_game"]["box.pts"] == 31.0, \
        "a game he sat is out of the totals and the averages"
    goalie = GL.season_log("nhl", "Joseph Woll", db_path=path)
    assert [g["key"] for g in goalie["groups"]] == ["goalie"]
    assert goalie["games"][0]["values"]["goalie.svp"] == 93.3 and goalie["totals"]["goalie.toi"] == 60.0
    arm = GL.season_log("mlb", "Gerrit Cole", db_path=path)
    assert [g["key"] for g in arm["groups"]] == ["pitching"] and arm["games"][0]["values"]["pitching.ip"] == "6.1"
    assert GL.season_log("ufc", "Anyone", db_path=path) == {} and GL.season_log("nba", "Nobody", db_path=path) == {}


def test_the_server_serves_it_free_and_the_page_has_its_door():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if parsed.path in ("/api/players/gamelog", "/api/players/gamelog/"):' in srv
    i = srv.index("def _players_gamelog(self, q):")
    body = srv[i:srv.index("def _parlay_check(self, body: dict):", i)]
    assert "gamelog.season_log(sport, player, int(season) if season.isdigit() else None)" in body
    assert "_entitled" not in body, "a box score is a fact, free like his other logs"
    i = APP.index("function chartDoor(")
    door = APP[i:APP.index("\n}\n", i)]
    assert '<button class="btn gl-open" type="button" data-gl="${escapeAttr(player)}" data-lg="${lg}">Game log</button>' \
        in door
    assert ('function glOpen(...a) { return roomCall(glOpen, "glOpen", "js/gamelog.js", "css/gamelog.css", a); }'
            in APP)
    assert 'if (b) glOpen(b.dataset.gl, b.dataset.lg);' in APP
    shrink = (ROOT / "engine" / "shrink.py").read_text(encoding="utf-8")
    assert '"js/gamelog.js", "css/gamelog.css",' in shrink
    assert '"/js/gamelog.js", "/css/gamelog.css",' in (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "css" / "gamelog.css").read_text(encoding="utf-8")
    for sel in ("#gl-overlay.open", ".gl-table .gl-fix", ".gl-w", ".gl-l", ".gl-dnp", ".gl-sum td", ".gl-gloss"):
        assert sel in css, sel


def test_the_sheet_draws_the_log_like_a_box_score():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    path = _history()
    qb = GL.season_log("nfl", "Joe Burrow", db_path=path)
    nba = GL.season_log("nba", "Jaylen Brown", db_path=path)
    goalie = GL.season_log("nhl", "Joseph Woll", db_path=path)
    js = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const escapeHtml = esc, escapeAttr = esc;"
          "const plural = (n, one) => `${n} ${n === 1 ? one : one + 's'}`;"
          "const trueMinus = (x) => String(x).replace(/(^|[^\\w])-(?=\\d)/g, '$1\\u2212');\n" + PAGE
          + f"\nprocess.stdout.write(JSON.stringify([glBodyHTML({json.dumps(qb)}, 'nfl'), "
            f"glBodyHTML({json.dumps(nba)}, 'nba'), glBodyHTML({json.dumps(goalie)}, 'nhl'), glBodyHTML({{}}, 'nfl')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    qb_html, nba_html, goalie_html, empty = json.loads(out.stdout)
    assert "Joe Burrow <span>Game log</span>" in qb_html and "CIN · QB · NFL · 2026" in qb_html
    assert '<th colspan="8">Passing</th><th colspan="4">Rushing</th>' in qb_html, "the groups over their columns"
    assert qb_html.index("<b>Wk 11</b>") < qb_html.index("<b>Wk 10</b>"), "the newest game first"
    assert "<b>Wk 10</b><span>@ PIT · " in qb_html and '<span class="gl-w">W</span> 33-27' in qb_html
    assert '<span class="gl-l">L</span> 20-23' in qb_html and "<b>Wk 11</b><span>vs TB · " in qb_html
    assert '<td class="num">7.0</td>' in qb_html and '<td class="num">\u22121</td>' in qb_html, \
        "a rate to a tenth, a true minus"
    assert '<td class="num">89.5</td>' in qb_html and '<td class="num">105.2</td>' in qb_html
    assert "Season · 2 games" in qb_html and "Per game" in qb_html and '<td class="num">96.8</td>' in qb_html
    assert '<option value="2025">2025</option>' in qb_html, "a season picker where he has more than one"
    assert "<b>CMP%</b> Completion percentage" in qb_html and "What the columns mean" in qb_html
    assert "Did not play</td>" in nba_html and '<td class="num">11-20</td>' in nba_html
    assert "<span>vs IND</span>" in nba_html and "<span>@ PHI</span>" in nba_html
    assert '<tr class="gl-groups">' not in nba_html, "a basketball box needs no group row"
    assert '<td class="num">60:00</td>' in goalie_html and '<td class="num">93.3</td>' in goalie_html
    assert "No games are on file for this player yet." in empty


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
