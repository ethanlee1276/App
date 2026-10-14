"""His role, game by game, in every league: the role chart.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list had
a role trend chart for every sport on it.

What is pinned, offline, on rows stored the way each league's ingest
stores them:

  * THE NFL: snap share leads a receiver, attempts lead a passer; target
    and carry shares are of his own team's that game; red-zone looks are
    joined from the play-by-play's short names ("J.Chase") the way the
    touchdown model joins them; home and the date come from the schedule;
    a count he barely has is not listed;
  * COLLEGE: carries, catches and attempts, and his share of his team's;
  * BASKETBALL: minutes and starts from the box score, shots, threes and
    free throws tried from the shot chart's play-by-play (the NBA only);
  * BASEBALL: a hitter's spot in the order is where he came up among his
    side's first nine; off the bench he has no spot and did not start; a
    pitcher's pitch count, batters faced, whether he faced the first
    batter, and his rest counting every game he pitched; a doubleheader's
    games kept apart;
  * HOCKEY: a skater's ice time and shots with every attempt and the
    power-play ones, a goalie's shots faced leading and his relief games;
  * A NUMBER NOT ON FILE IS A GAP, NEVER A ZERO;
  * THE DOOR AND THE PAGE: /api/players/chart serves kind=role in every
    league with a box score; every league's pick page offers it after its
    own chart, never ahead of it; the drawing is its own module.

Run directly: `python3 tests/test_a_role_chart_for_every_player.py`
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import charts as CH, db as D, role as R  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
ROLE_JS = (ROOT / "web" / "js" / "chart-role.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
DB_PY = (ROOT / "engine" / "db.py").read_text(encoding="utf-8")


def _log(conn, sport, season, period, gid, player, team, opp, pos, home, market, value):
    conn.execute("INSERT OR REPLACE INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (sport, season, period, gid, player, team, opp, pos, home, market, value))


def _nfl():
    conn = D.connect(":memory:")
    weeks = [(0.82, 9, 0, 110), (0.88, 11, 1, 140), (None, 6, 0, 60), (0.91, 12, 0, 150)]
    for wk, (snap, tgt, car, air) in enumerate(weeks, 1):
        p = f"{wk:03d}"
        mine = (("targets", tgt), ("carries", car), ("air_yards", air), ("receptions", tgt - 3))
        for m, v in mine + ((("snap_pct", snap),) if snap is not None else ()):
            _log(conn, "nfl", 2026, p, f"CIN-{p}", "Ja'Marr Chase", "CIN", "BAL", "WR", 1, m, v)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "Tee Higgins", "CIN", "BAL", "WR", 1, "targets", 7)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "Chase Brown", "CIN", "BAL", "RB", 1, "carries", 15)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "Joe Burrow", "CIN", "BAL", "QB", 1, "pass_att", 35 + wk)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "Joe Burrow", "CIN", "BAL", "QB", 1, "carries", 2)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "Joe Burrow", "CIN", "BAL", "QB", 1, "snap_pct", 1.0)
        # The play-by-play's own short names: his, and a namesake on
        # another club who must not be joined.
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "J.Chase", "CIN", "", "", 1, "rz_tgt", wk % 3)
        _log(conn, "nfl", 2026, p, f"CIN-{p}", "J.Chase", "CIN", "", "", 1, "rz_car", 0)
        _log(conn, "nfl", 2026, p, f"KC-{p}", "J.Chase", "KC", "", "", 1, "rz_tgt", 9)
        D.upsert_games(conn, [{"sport": "nfl", "season": 2026, "period": p, "game_id": f"G{wk}",
                               "home": "CIN" if wk % 2 else "BAL", "away": "BAL" if wk % 2 else "CIN",
                               "date": f"2026-09-{6 + 7 * (wk - 1):02d}"}])
    conn.commit()
    return conn


def test_an_nfl_receiver_leads_with_his_snaps_and_his_share_is_his_teams():
    d = R.chart(_nfl(), "nfl", "jamarr chase")
    assert d["player"] == "Ja'Marr Chase" and d["lead"] == "snap" and d["position"] == "WR"
    keys = [m["key"] for m in d["metrics"]]
    assert keys == ["snap", "tgt", "tgt_sh", "rz", "air"], "a carry a game is not his: not listed"
    g = d["games"][0]
    assert g["week"] == 4 and g["home"] is False and g["date"] == "2026-09-27" and g["opp"] == "BAL"
    assert g["v"]["tgt_sh"] == round(12 / 19, 4), "his twelve of the nineteen his club's players drew"
    assert g["v"]["rz"] == 1.0, "J.Chase's red-zone looks for Cincinnati, never Kansas City's"
    wk3 = d["games"][1]
    assert "snap" not in wk3["v"] and wk3["v"]["tgt"] == 6.0, "a snap count not on file is a gap"
    L = d["season_line"]
    assert L["n"] == 4 and L["avg"]["snap"] == round((0.82 + 0.88 + 0.91) / 3, 4)
    assert L["avg"]["tgt"] == 9.5 and L["last3"]["tgt"] == round((11 + 6 + 12) / 3, 4)
    assert L["high"]["tgt"] == 12.0 and L["low"]["tgt"] == 6.0 and L["starts"] is None
    place = {s["key"]: s for s in d["splits"]["place"]}
    assert place["home"]["n"] == 2 and place["away"]["avg"]["tgt"] == round((11 + 12) / 2, 4)


def test_an_nfl_passer_leads_with_his_attempts():
    d = R.chart(_nfl(), "nfl", "Joe Burrow")
    assert d["lead"] == "att" and [m["key"] for m in d["metrics"]][:2] == ["att", "snap"]
    assert d["games"][0]["v"]["car_sh"] == round(2 / 17, 4)


def test_a_college_back_leads_with_his_carries_and_his_share():
    conn = D.connect(":memory:")
    for i, (car, rec) in enumerate([(22, 2), (18, 3), (25, 1)]):
        d = f"2026-09-0{i + 1}"
        for m, v in (("carries", car), ("receptions", rec), ("rz_car", 3), ("rz_rec", 1)):
            _log(conn, "cfb", 2026, d, f"40{i}", "Jeremiyah Love", "ND", "MIA", "RB", i % 2, m, v)
        _log(conn, "cfb", 2026, d, f"40{i}", "Jadarian Price", "ND", "MIA", "RB", i % 2, "carries", 10)
        _log(conn, "cfb", 2026, d, f"40{i}", "Jaden Greathouse", "ND", "MIA", "WR", i % 2, "receptions", 6)
    d = R.chart(conn, "cfb", "Jeremiyah Love")
    assert d["lead"] == "car" and [m["key"] for m in d["metrics"]] == ["car", "car_sh", "rec", "rec_sh", "rz"]
    assert next(m for m in d["metrics"] if m["key"] == "rz")["name"] == "Red-zone touches"
    g = d["games"][0]
    assert g["v"]["car_sh"] == round(25 / 35, 4) and g["v"]["rec_sh"] == round(1 / 7, 4) and g["v"]["rz"] == 4.0
    assert g["home"] is False and g["date"] == "2026-09-03" and d["season_label"] == "2026"


def test_basketball_minutes_starts_and_the_shots_he_tried():
    conn = D.connect(":memory:")
    for i, (mn, s) in enumerate([(34.5, "S"), (36.0, "S"), (12.0, "B")]):
        d = f"2025-11-0{i + 1}"
        _log(conn, "nba", 2025, d, f"Josh Hart-{d}", "Josh Hart", "NYK", "BOS", s, i % 2, "min", mn)
        _log(conn, "wnba", 2025, d, f"Caitlin Clark-{d}", "Caitlin Clark", "IND", "NY", s, 1, "min", mn)
    rows = []
    for k, kind in enumerate(["2pt", "3pt", "3pt", "ft", "ft", "2pt"]):
        rows.append({"game_id": "0022500010", "action": k, "season": 2025, "date": "2025-11-03",
                     "person_id": 1628404, "player": "Josh Hart", "team": "NYK", "opponent": "BOS", "home": 0,
                     "period": 1, "clock": "", "kind": kind, "made": 1, "shot": "", "descriptor": "",
                     "distance": 5.0, "x": 0.0, "y": 10.0, "zone": "paint", "area": "", "assist": "",
                     "blocked": 0, "quals": ""})
    D.upsert_nba_shots(conn, rows)
    d = R.chart(conn, "nba", "Josh Hart")
    assert d["lead"] == "min" and [m["key"] for m in d["metrics"]] == ["min", "fga", "fg3a", "fta"]
    g = d["games"][0]
    assert g["start"] is False and g["v"] == {"min": 12.0, "fga": 4.0, "fg3a": 2.0, "fta": 2.0}
    assert d["season_line"]["starts"] == 2 and d["season_label"] == "2025-26" and d["position"] == ""
    split = {s["key"]: s for s in d["splits"]["start"]}
    assert split["start"]["avg"]["min"] == 35.25 and split["bench"]["name"] == "Off the bench"
    w = R.chart(conn, "wnba", "Caitlin Clark")
    assert [m["key"] for m in w["metrics"]] == ["min"] and w["season_label"] == "2025"


def _mlb():
    conn = D.connect(":memory:")
    ab = {}

    def pa(pk, date, inning, half, batter_id, batter, pitcher_id, pitcher, n=4):
        i = ab[pk] = ab.get(pk, -1) + 1
        team, opp = ("BOS", "NYY") if half == "T" else ("NYY", "BOS")
        conn.execute("INSERT INTO mlb_pa (game_pk, at_bat, season, date, batter_id, batter, pitcher_id, pitcher, team, "
                     "opponent, home, inning, half, event, event_type, pitches) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pk, i, 2026, date, batter_id, batter, pitcher_id, pitcher, team, opp, int(half == "B"), inning,
                      half, "Single", "single", n))
        if pitcher_id == 45:
            for k in range(n):
                conn.execute("INSERT INTO mlb_pitches (game_pk, at_bat, n, season, date, pitcher_id) VALUES (?,?,?,?,?,?)",
                             (pk, i, k, 2026, date, 45))
    # Game 1 (Jun 1): Cole starts; Judge bats second. Game 2 (Jun 3, the
    # first of two): Cole relieves in the first after the opener; Judge
    # pinch-hits in the seventh. Game 3 (Jun 3, the second): Cole starts
    # again; Judge leads off.
    for pk, date, cole_first, judge in ((7001, "2026-06-01", True, 2), (7002, "2026-06-03", False, None),
                                        (7003, "2026-06-03", True, 1)):
        if not cole_first:
            pa(pk, date, 1, "T", 500, "Lead Off", 77, "An Opener")
        for k in range(3):
            pa(pk, date, 1, "T", 501 + k, f"B{k}", 45, "Gerrit Cole", 5)
        for k in range(9):
            spot = k + 1
            who = (99, "Aaron Judge") if spot == judge else (600 + k, f"N{k}")
            pa(pk, date, 1 + k // 3, "B", who[0], who[1], 60, "Chris Sale")
        if judge is None:
            pa(pk, date, 7, "B", 99, "Aaron Judge", 60, "Chris Sale", 6)
        _log(conn, "mlb", 2026, date, f"Aaron Judge-{date}" + ("-G2" if pk == 7003 else ""), "Aaron Judge", "NYY",
             "BOS", "RF", 1, "pa", 1.0 if judge is None else 4.0)
        _log(conn, "mlb", 2026, date, f"Gerrit Cole-{date}" + ("-G2" if pk == 7003 else ""), "Gerrit Cole", "NYY",
             "BOS", "P", 1, "outs", 3.0)
    conn.commit()
    return conn


def test_a_hitter_has_his_spot_in_the_order_and_off_the_bench_he_has_none():
    d = R.chart(_mlb(), "mlb", "Aaron Judge")
    assert d["lead"] == "pa" and [m["key"] for m in d["metrics"]] == ["pa", "spot", "seen"]
    by = {g["id"]: g for g in d["games"]}
    assert set(by) == {"2026-06-01", "2026-06-03", "2026-06-03-G2"}, "a doubleheader's games kept apart"
    assert by["2026-06-01"]["v"]["spot"] == 2.0 and by["2026-06-01"]["start"] is True
    assert by["2026-06-03"]["start"] is False and "spot" not in by["2026-06-03"]["v"], "a pinch hitter has no spot"
    assert by["2026-06-03"]["v"]["seen"] == 6.0
    assert by["2026-06-03-G2"]["v"]["spot"] == 1.0
    assert {s["name"] for s in d["splits"]["start"]} == {"Started", "Off the bench"}


def test_a_pitcher_has_his_pitch_count_his_starts_and_his_rest():
    d = R.chart(_mlb(), "mlb", "Gerrit Cole")
    assert d["lead"] == "pitches" and [m["key"] for m in d["metrics"]] == ["pitches", "bf", "outs", "rest"]
    by = {g["id"]: g for g in d["games"]}
    assert by["2026-06-01"]["v"]["pitches"] == 15.0 and by["2026-06-01"]["v"]["bf"] == 3.0
    assert by["2026-06-01"]["start"] is True and "rest" not in by["2026-06-01"]["v"]
    assert by["2026-06-03"]["start"] is False, "in the first, but after the opener faced the leadoff man"
    assert by["2026-06-03"]["v"]["rest"] == 1.0 and by["2026-06-03-G2"]["v"]["rest"] == 0.0
    assert {s["name"] for s in d["splits"]["start"]} == {"Started", "In relief"}


def test_hockey_ice_time_shots_and_the_goalie_s_shots_faced():
    conn = D.connect(":memory:")
    for i, (toi, sog) in enumerate([(18.5, 3), (20.1, 5), (17.0, 1)]):
        d = f"2025-10-1{i}"
        for m, v in (("toi", toi), ("sog", sog)):
            _log(conn, "nhl", 2025, d, f"g{i}", "Auston Matthews", "TOR", "MTL", "C", 1, m, v)
        for m, v in (("toi", 60.0 if i != 1 else 22.0), ("shots_against", 30 + i), ("saves", 27),
                     ("started", 0.0 if i == 1 else 1.0)):
            _log(conn, "nhl", 2025, d, f"g{i}", "Joseph Woll", "TOR", "MTL", "G", 1, m, v)
    D.upsert_nhl_shots(conn, [{"game_id": 2025020100 + k // 4, "event_id": k, "date": "2025-10-12", "season": 2025,
                               "team": "TOR", "opponent": "MTL", "shooter_id": "1", "shooter": "Auston Matthews",
                               "goalie_id": "2", "goalie": "Sam Montembeault", "kind": "sog", "x": 70.0, "y": 0.0,
                               "dist": 19.0, "angle": 0.0, "shot_type": "wrist", "strength": "PP" if k < 2 else "EV",
                               "empty_net": 0, "rebound": 0, "rush": 0, "is_goal": 0, "period": 1,
                               "assist1": "", "assist2": ""} for k in range(4)])
    s = R.chart(conn, "nhl", "Auston Matthews")
    assert s["lead"] == "toi" and [m["key"] for m in s["metrics"]] == ["toi", "sog", "sat", "pp"]
    assert s["games"][0]["v"] == {"toi": 17.0, "sog": 1.0, "sat": 4.0, "pp": 2.0}
    assert "sat" not in s["games"][1]["v"], "attempts not on file are a gap"
    g = R.chart(conn, "nhl", "Joseph Woll")
    assert g["lead"] == "sa" and [m["key"] for m in g["metrics"]] == ["sa", "toi"]
    assert g["season_line"]["starts"] == 2 and {x["name"] for x in g["splits"]["start"]} == {"Started", "In relief"}


def test_nobody_and_a_league_without_a_box_score():
    conn = _nfl()
    assert R.chart(conn, "nfl", "Nobody At All") == {}
    assert R.chart(conn, "ufc", "Ja'Marr Chase") == {}
    assert R.chart(conn, "nfl", "Ja'Marr Chase", 2019)["season"] == 2026, "a season he never played is his newest"


def test_the_door_serves_every_league():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        D.connect(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_chart({"kind": ["role"], "sport": ["nfl"], "player": ["Ja'Marr Chase"]})
        c = D.connect(path)
        for r in _nfl().execute("SELECT * FROM player_game_logs"):
            _log(c, *tuple(r))
        c.commit()
        c.close()
        h._players_chart({"kind": ["role"], "sport": ["nfl"], "player": ["Ja'Marr Chase"]})
        h._players_chart({"kind": ["role"], "sport": ["ufc"], "player": ["Ja'Marr Chase"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "role" and sent[1][1]["lead"] == "snap" and "face" in sent[1][1]
    assert sent[2][0] == 400
    assert all(CH.known("role", lg) for lg in ("nfl", "cfb", "nba", "wnba", "mlb", "nhl"))
    assert not CH.known("role", "ufc")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{ROLE_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_his_role():
    nfl = R.chart(_nfl(), "nfl", "Ja'Marr Chase")
    mlb = R.chart(_mlb(), "mlb", "Aaron Judge")
    got = _node(f"""
      const d = {json.dumps(nfl)}, b = {json.dumps(mlb)}, P = T.DRAW.role;
      const g = d.games[0], game = P.game(g, d), season = P.season(d);
      const out = {{
        lit: (game.match(/rl-bar on cx-mark/g) || []).length, doors: (game.match(/data-gi="/g) || []).length,
        last3: (season.match(/rl-bar on"/g) || []).length, seasonDoors: (season.match(/data-gi="/g) || []).length,
        means: (season.match(/class="rl-mean"/g) || []).length, strips: (game.match(/rl-strip/g) || []).length,
        labels: (game.match(/class="rl-val/g) || []).length, chip: P.chip(g, d), count: P.count(d.season_line, d),
        title: P.listTitle(g, d), items: P.items(g, d).length, side: P.gameSide(g, d), sside: P.seasonSide(d),
        list: P.list(g, d), tables: P.splits(d), note: P.note(d), tip: P.tip(d.metrics[0], g, d),
      }};
      out.mlbChip = P.chip(b.games[0], b); out.mlbSide = P.gameSide(b.games[2], b);
      out.mlbTables = P.splits(b); out.mlbCount = P.count(b.season_line, b);
      out.kinds = [T.kindsFor("nfl", "rec_yds", "WR"), T.kindsFor("nfl", "pass_yds", "QB"),
                   T.kindsFor("nfl", "kicking_points", "K"), T.kindsFor("cfb", "pass_yds", "QB"),
                   T.kindsFor("cfb", "pass_yds", ""), T.kindsFor("nba", "pts", "G"), T.kindsFor("wnba", "pts", "G"),
                   T.kindsFor("mlb", "strikeouts", "P"), T.kindsFor("nhl", "saves", "G"), T.kindsFor("nba", "", "")];
      out.sec = [T.kindOf("role", "nba").sec, T.kindOf("role", "wnba").sec, T.KIND.role.chip];
      return out;
    """)
    if got is None:
        return
    assert got["strips"] == 5 and got["lit"] == 5 and got["doors"] == 5 * 4 - 1, "every bar but a gap is a door"
    assert got["last3"] == 5 * 3 - 1 and got["seasonDoors"] == 0 and got["means"] == 5
    assert got["labels"] == 5 * 4 - 1, "four games: every number fits over its bar"
    assert got["chip"] == "91% snaps" and got["count"] == "87% of snaps" and got["items"] == 5
    assert got["title"] == "That game beside his season · 5 numbers"
    assert "avg 87%" in got["side"] and ">Target share<" in got["side"] and "Last 3" in got["sside"]
    assert "His stretch, beside his season" in got["tables"] and "Home (2)" in got["tables"]
    assert "Snap share" in got["list"] and "does not move any price" in got["note"] and "his season 87%" in got["tip"]
    assert got["mlbChip"] == "4 PA" and ">2nd<" in got["mlbSide"] and "In the lineup or off the bench" in got["mlbTables"]
    assert got["mlbCount"] == "9 plate appearances"
    assert got["kinds"] == [["routes", "carries", "role"], ["passes", "carries", "role"], ["kicks"], ["role"], ["role"],
                            ["shots", "role"], ["role"], ["pitches", "role"], ["saves", "role"], []]
    assert got["sec"][0].startswith("his minutes") and got["sec"][1].startswith("her minutes") and got["sec"][2] == "Role"


def test_the_module_its_styles_and_the_lead():
    assert 'role: "role"' in CC_JS and 'Q.draw("role"' in ROLE_JS
    assert '(a.k === "role") - (b.k === "role") || b.v - a.v' in CC_JS, "his role never leads"
    assert 'P.listTitle ? P.listTitle(g, d)' in CC_JS and 'P.chip(x, d)' in CC_JS
    assert "onclick" not in ROLE_JS and "onerror" not in ROLE_JS and not re.search(r"on(error|load)\s*=", ROLE_JS)
    for cls in (".rl-svg", ".rl-bar.on", ".rl-mean", ".rl-val", ".rl-start.s", ".dt.rl-m"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    for ix in ("nhl_shots_shooter ON nhl_shots (shooter, season)", "nhl_shots_goalie ON nhl_shots (goalie, season)",
               "mlb_pa_batter_name ON mlb_pa (batter)", "mlb_pa_pitcher_name ON mlb_pa (pitcher)",
               "nba_shots_name ON nba_shots (player)"):
        assert ix in DB_PY, ix


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
