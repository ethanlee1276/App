"""Tonight's opponent beside his chart: the matchup view, every league.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done" — the list's seventh: "Matchup view. Tonight's defense next to his
chart ... This is context only." And: "All sports screens should
basically be identical."

What is pinned, offline, on rows shaped like each chart table's:

  * ONE PICTURE (engine/matchview): his chart's zones, his share of the
    volume in each, the opponent's rate there shrunk toward the league's
    by a fixed count of plays, the difference, and the fit (the
    difference weighted by the share); the opponent's overall rate and
    its rank, first being the best side for the player;
  * EVERY LEAGUE: an NFL receiver against what the defence allows his
    position group by depth and side, a back by hole, a passer by depth
    and side (his own chart decides which, not the bet); college by field
    zone; basketball by shot zone; a hockey skater by distance, a goalie
    against where tonight's opponent shoots from, with his own save
    percentage on each row; a hitter against tonight's starter's pitches
    (the staff's with none named) and a pitcher against the lineup's
    slugging;
  * THE OPPONENT: a pick's spelling of a club finds the table's (the Rams
    as LA or LAR, a school with its nickname), and an opponent with too
    little this season is read on the last;
  * THE DOOR AND THE PAGE: /api/players/chart answers kind=matchup told
    the opponent; a pick page's slot carries tonight's opponent and the
    matchup is offered after his own chart, never ahead of it; the drawing
    is its own module, CSP-clean and tokens only.

Run directly: `python3 tests/test_a_matchup_view_for_every_player.py`
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

from engine import charts as CH, db as D, matchview as M  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MV_JS = (ROOT / "web" / "js" / "chart-matchup.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

DEFENCES = ("DET", "GB", "MIN", "CHI", "LA")
BASE = {"deep": 12.0, "mid": 8.0, "short": 5.0, "behind": 3.0}
SIDE = {"L": "L", "M": "M", "R": "R"}
_n = [0]


def _play():
    _n[0] += 1
    return str(_n[0])


def _row(table_kw, **kw):
    out = {"sport": "nfl", "season": 2026, "period": "001", "date": "2026-10-04", "player_id": "x", "team": "BAL",
           "home": 0, "jersey": "1", "qtr": 1, "clock": "5:00", "down": 1, "distance": 10, "yardline_100": 40,
           "td": 0, "first_down": 0, "play_id": _play()}
    out.update(table_kw)
    out.update(kw)
    out.setdefault("game_id", f"{out['team']}@{out['opponent']}{out['period']}")
    return out


def _air(zone):
    return {"deep": 25.0, "mid": 14.0, "short": 5.0, "behind": -2.0}[zone]


def _nfl(conn):
    """Five defences, 80 targets each to receivers and 30 to tight ends
    over every zone; Detroit gives up 30 a target deep right to
    receivers. Zay Flowers: half his targets deep right, half short
    middle. A back with carries by hole; a passer who also scrambles."""
    t, c, p = [], [], []
    for opp in DEFENCES:
        for per in (1, 2, 3):
            for d in ("deep", "mid", "short"):
                for s in "LMR":
                    for i in range(3 if per < 3 else 2):
                        y = 30.0 if (opp == "DET" and d == "deep" and s == "R") else BASE[d]
                        t.append(_row({}, period=f"{per:03d}", opponent=opp, player=f"WR{i}", position="WR",
                                      air_yards=_air(d), side=s, complete=1, yards=y))
                    t.append(_row({}, period=f"{per:03d}", opponent=opp, player="TE1", position="TE",
                                  air_yards=_air(d), side=s, complete=1, yards=6.0))
            for i in range(3):
                t.append(_row({}, period=f"{per:03d}", opponent=opp, player="WR9", position="WR",
                              air_yards=-2.0, side="M", complete=1, yards=3.0))
            for h in ("LE", "LT", "LG", "M", "RG", "RT", "RE"):
                for i in range(3):
                    y = 9.0 if (opp == "GB" and h == "RT") else 4.0
                    c.append(_row({}, period=f"{per:03d}", opponent=opp, player=f"RB{i}", position="RB",
                                  hole=h, yards=y, scramble=0))
            for d in ("deep", "mid", "short"):
                for s in "LMR":
                    for i in range(4):
                        p.append(_row({}, period=f"{per:03d}", opponent=opp, player=f"QB{i}", position="QB",
                                      kind="pass", air_yards=_air(d), side=s, complete=1, yards=BASE[d] + 1))
    for i in range(10):
        t.append(_row({}, opponent="PIT", player="Zay Flowers", position="WR", air_yards=25.0, side="R",
                      complete=1, yards=10.0))
        t.append(_row({}, opponent="PIT", player="Zay Flowers", position="WR", air_yards=5.0, side="M",
                      complete=1, yards=4.0))
    t.append(_row({}, opponent="PIT", player="Derrick Henry", position="RB", air_yards=-2.0, side="L",
                  complete=1, yards=4.0))
    for h in ("RT", "RT", "RT", "M", "LG"):
        for _ in range(4):
            c.append(_row({}, opponent="PIT", player="Derrick Henry", position="RB", hole=h, yards=5.0, scramble=0))
    for _ in range(12):
        p.append(_row({}, opponent="PIT", player="Lamar Jackson", position="QB", kind="pass", air_yards=25.0,
                      side="L", complete=1, yards=20.0))
    for _ in range(8):
        c.append(_row({}, opponent="PIT", player="Lamar Jackson", position="QB", hole="LE", yards=8.0, scramble=0))
    for _ in range(15):
        c.append(_row({}, opponent="PIT", player="Lamar Jackson", position="QB", hole="", yards=7.0, scramble=1))
    D.upsert_targets(conn, t)
    D.upsert_carries(conn, c)
    D.upsert_passes(conn, p)


def _conn():
    conn = D.connect(":memory:")
    _nfl(conn)
    return conn


def _zone(d, key):
    return next(z for z in d["zones"] if z["key"] == key)


def test_a_receiver_beside_what_the_defence_allows_his_group():
    d = M.chart(_conn(), "nfl", "zay flowers", "DET")
    assert d["family"] == "routes" and d["group"] == "WR" and d["opp"] == "DET" and d["season"] == 2026
    assert d["right"] == "Yards a target allowed to WRs" and d["season_line"]["n"] == 20
    z = _zone(d, "deepR")
    assert (z["n"], z["share"], z["rn"], z["raw"]) == (10, 0.5, 8, 30.0)
    # Receivers only: the tight ends' 6 a target in every zone are not the
    # league's deep-right rate. Detroit 8 x 30, four defences 8 x 12, his own
    # ten at 10 against Pittsburgh.
    lg = (8 * 30 + 4 * 8 * 12 + 10 * 10) / (8 + 32 + 10)
    assert abs(z["league"] - round(lg, 3)) < 1e-9
    k = M.SHRINK["routes"]
    assert abs(z["rate"] - round((240 + k * lg) / (8 + k), 3)) < 1e-9, "shrunk toward the league by k plays"
    assert abs(z["diff"] - round(z["rate"] - z["league"], 3)) < 0.002
    short = _zone(d, "shortM")
    assert abs(d["fit"] - round(0.5 * z["diff"] + 0.5 * short["diff"], 3)) < 0.002 and d["fit"] > 1
    o = d["overall"]
    assert o["rank"] == 1 and o["of"] == 6 and o["n"] == 81 and o["rate"] > o["league"]
    assert [x["key"] for x in d["zones"]][:3] == ["deepL", "deepM", "deepR"] and d["zones"][-1]["key"] == "behind"
    assert d["tested"] is True and d["good"] == 1


def test_a_pick_s_spelling_of_the_club_finds_the_table_s():
    conn = _conn()
    assert M.chart(conn, "nfl", "Zay Flowers", "LAR")["opp"] == "LA", "the Rams are LA in the play-by-play"
    assert M.chart(conn, "nfl", "Zay Flowers", "") == {} and M.chart(conn, "nfl", "Zay Flowers", "XXX") == {}
    assert M.chart(conn, "nfl", "Nobody", "DET") == {}
    assert M.find("nfl", {"LA": {}}, "STL") == "LA"
    assert M.find("cfb", {"Michigan": {}, "Ohio State": {}}, "Michigan Wolverines") == "Michigan"


def test_his_own_chart_picks_the_zones_not_the_bet():
    conn = _conn()
    back = M.chart(conn, "nfl", "Derrick Henry", "GB", hint="routes")
    assert back["family"] == "carries", "a back with twenty carries and one target is read by hole"
    rt = _zone(back, "RT")
    assert rt["share"] == 0.6 and rt["diff"] > 0 and back["fit"] > 0
    assert [z["key"] for z in back["zones"]] == ["LE", "LT", "LG", "M", "RG", "RT", "RE"]
    qb = M.chart(conn, "nfl", "Lamar Jackson", "DET")
    assert qb["family"] == "passes", "a passer who runs is still a passer"
    assert qb["season_line"]["n"] == 12 and _zone(qb, "deepL")["share"] == 1.0
    assert "scramble" not in json.dumps(qb)


def _cfb(conn):
    rows = []
    for opp, y in (("Michigan", 9.0), ("Ohio State", 5.0), ("Texas", 6.0)):
        for per in (1, 2, 3):
            for yl in (70, 35, 12, 3):
                for i in range(10):
                    rows.append(_row({}, sport="cfb", period=f"{per:03d}", team="Rutgers", opponent=opp,
                                     player=f"RB{i}", position="RB", hole="", yards=y + (3 if yl == 12 else 0),
                                     scramble=0, yardline_100=yl))
    for yl in (70, 70, 12):
        rows.append(_row({}, sport="cfb", team="Rutgers", opponent="Iowa", player="Kyle Monangai", position="RB",
                         hole="", yards=5.0, scramble=0, yardline_100=yl))
    D.upsert_carries(conn, rows)


def test_college_by_field_zone():
    conn = D.connect(":memory:")
    _cfb(conn)
    d = M.chart(conn, "cfb", "Kyle Monangai", "Michigan Wolverines")
    assert d["family"] == "runs" and d["opp"] == "Michigan" and d["tested"] is False
    assert [z["key"] for z in d["zones"]] == ["own", "mid", "rz", "gl"]
    assert _zone(d, "own")["share"] == round(2 / 3, 3) and _zone(d, "rz")["share"] == round(1 / 3, 3)
    assert d["fit"] > 0 and d["overall"]["rank"] == 1


def test_basketball_by_shot_zone():
    conn = D.connect(":memory:")
    rows, a = [], 0
    for opp, rim in (("BOS", 0.45), ("BKN", 0.70), ("NYK", 0.60), ("MIA", 0.60)):
        for g in range(4):
            for zone, pct in (("ra", rim), ("mid", 0.40), ("above3", 0.35)):
                for i in range(20):
                    a += 1
                    rows.append({"game_id": f"g{opp}{g}", "action": a, "season": 2025, "date": "2026-10-25",
                                 "person_id": 100 + i, "player": f"P{i}", "team": "LAL", "opponent": opp, "home": 0,
                                 "kind": "3pt" if zone == "above3" else "2pt", "made": 1 if i < pct * 20 else 0,
                                 "zone": zone})
    for i in range(30):
        a += 1
        rows.append({"game_id": "gx", "action": a, "season": 2025, "date": "2026-10-22", "person_id": 7,
                     "player": "Jalen Brunson", "team": "NYK", "opponent": "CLE", "home": 1,
                     "kind": "2pt", "made": 1 if i % 2 else 0, "zone": "ra" if i < 20 else "mid"})
    D.upsert_nba_shots(conn, rows)
    soft = M.chart(conn, "nba", "Jalen Brunson", "BRK")
    hard = M.chart(conn, "nba", "Jalen Brunson", "BOS")
    assert soft["family"] == "shots" and soft["opp"] == "BKN", "Brooklyn as BRK finds BKN"
    assert soft["fit"] > 0 > hard["fit"] and _zone(soft, "ra")["share"] == round(20 / 30, 3)
    assert soft["fmt"] == "pct" and soft["season_label"] == "2025-26"
    assert hard["overall"]["rank"] == hard["overall"]["of"], "the stingiest defence is last for the shooter"


def _nhl(conn):
    rows, e = [], 0
    for team in ("TOR", "BOS", "MTL", "OTT"):
        for g in range(3):
            for dist, goals in ((5, 4 if team == "TOR" else 2), (15, 3), (28, 2), (50, 1)):
                for i in range(10):
                    e += 1
                    rows.append({"game_id": 1000 + g, "event_id": e, "date": "2026-10-10", "season": 2026,
                                 "team": team, "opponent": "NYR" if team != "NYR" else "TOR", "shooter": f"S{team}{i}",
                                 "goalie": "Igor Shesterkin", "kind": "goal" if i < goals else "sog",
                                 "dist": float(dist), "is_goal": 1 if i < goals else 0, "empty_net": 0})
    # Toronto's own skater, shooting at three other goalies.
    for opp, saves in (("BOS", 9), ("MTL", 8), ("OTT", 7)):
        for g in range(3):
            for dist in (5, 15, 28, 50):
                for i in range(10):
                    e += 1
                    rows.append({"game_id": 2000 + g, "event_id": e, "date": "2026-10-11", "season": 2026,
                                 "team": "XYZ", "opponent": opp, "shooter": "Other Skater", "goalie": f"G{opp}",
                                 "kind": "sog" if i < saves else "goal", "dist": float(dist),
                                 "is_goal": 0 if i < saves else 1, "empty_net": 0})
    for dist in (5, 5, 15, 15, 50):
        e += 1
        rows.append({"game_id": 3000, "event_id": e, "date": "2026-10-12", "season": 2026, "team": "TOR",
                     "opponent": "DET", "shooter": "Auston Matthews", "goalie": "Alex Lyon", "kind": "sog",
                     "dist": float(dist), "is_goal": 0, "empty_net": 0})
    D.upsert_nhl_shots(conn, rows)


def test_hockey_a_skater_and_a_goalie():
    conn = D.connect(":memory:")
    _nhl(conn)
    sk = M.chart(conn, "nhl", "Auston Matthews", "OTT", hint="shotmap")
    assert sk["family"] == "skater" and [z["key"] for z in sk["zones"]] == ["crease", "slot", "high", "point"]
    assert _zone(sk, "crease")["share"] == 0.4 and sk["fit"] > 0, "Ottawa's goalie lets in the most"
    gk = M.chart(conn, "nhl", "Igor Shesterkin", "TOR", hint="saves")
    assert gk["family"] == "goalie" and gk["good"] == -1 and gk["left"] == "Their shots"
    crease = _zone(gk, "crease")
    # Toronto's shots: 30 from the crease against him plus Matthews' two.
    assert crease["n"] == 32 and crease["share"] == round(32 / 125, 3) and crease["diff"] > 0, \
        "Toronto scores most from the crease"
    assert crease["mine"] == round(1 - 30 / 120, 3), "his own save percentage there: 30 goals on 120"
    assert gk["overall"]["rank"] == gk["overall"]["of"], "the best shooting side is the worst for the goalie"


def _mlb(conn):
    """Boston's staff and lineup, three other clubs, and Aaron Judge: his
    plate appearances end on pitches in the heart (homers) and down
    (strikeouts). Brayan Bello pitches for Boston, mostly down."""
    pa, pitches = [], []
    pk = 0

    def add(team, opp, batter, bid, pitcher, pid, zone, event, n=2):
        nonlocal pk
        pk += 1
        pa.append({"game_pk": pk, "at_bat": 1, "season": 2026, "date": "2026-09-01", "batter_id": bid,
                   "batter": batter, "bat_side": "R", "pitcher_id": pid, "pitcher": pitcher, "pitch_hand": "R",
                   "team": team, "opponent": opp, "home": 0, "inning": 1, "half": "T", "event": event,
                   "event_type": event, "rbi": 0, "pitches": n})
        for i in range(1, n + 1):
            pitches.append({"game_pk": pk, "at_bat": 1, "n": i, "season": 2026, "date": "2026-09-01",
                            "pitcher_id": pid, "batter_id": bid, "bat_side": "R", "inning": 1, "pitch_type": "FF",
                            "zone": zone if i == n else 13, "code": "X" if i == n else "B"})

    for staff, pid, heart in (("BOS", 50, "home_run"), ("NYY", 60, "single"), ("TB", 70, "field_out"),
                              ("TOR", 80, "double")):
        for i in range(40):
            add("SEA", staff, f"H{i}", 900 + i, f"P{staff}", pid, 5 if i % 2 else 8,
                heart if i % 2 else "single" if i % 4 == 0 else "strikeout")
        for i in range(40):
            add(staff, "SEA", f"B{staff}{i}", 300 + pid + i, "Seattle Arm", 10, 5 if i % 2 else 8,
                heart if i % 2 else "field_out")
    for i in range(30):
        add("NYY", "TB", "Aaron Judge", 592450, "PTB", 70, 5 if i % 3 == 0 else 8,
            "home_run" if i % 3 == 0 else "strikeout")
    for i in range(30):
        add("TB", "BOS", "B" + str(i), 800 + i, "Brayan Bello", 51, 8 if i % 4 else 5, "field_out", n=3)
    for i in range(30):
        add("TB", "NYY", "Q" + str(i), 700 + i, "Gerrit Cole", 45, 5 if i % 2 else 2, "single")
    D.upsert_mlb_pa(conn, pa)
    D.upsert_mlb_pitches(conn, pitches)


def test_baseball_a_hitter_against_tonight_s_starter_and_a_pitcher_against_the_lineup():
    conn = D.connect(":memory:")
    _mlb(conn)
    keep = M.STARTER
    try:
        M.STARTER = lambda team, opp: "Brayan Bello" if opp == "BOS" else ""
        hit = M.chart(conn, "mlb", "Aaron Judge", "BOS", hint="spray")
        staff = M.chart(conn, "mlb", "Aaron Judge", "NYY", hint="spray")
    finally:
        M.STARTER = keep
    assert hit["family"] == "hitter" and hit["starter"] == "Brayan Bello" and hit["left"] == "Where Brayan Bello pitches"
    heart, down = _zone(hit, "heart"), _zone(hit, "down")
    assert heart["diff"] > 0 > down["diff"], "his slugging: homers in the heart, strikeouts down"
    assert down["share"] > heart["share"] and hit["fit"] < staff["fit"] + 1, "Bello lives down, where he misses"
    assert staff["left"] == "Where their staff pitches" and "starter" not in staff
    p = M.chart(conn, "mlb", "Gerrit Cole", "BOS", hint="pitches")
    assert p["family"] == "pitcher" and p["good"] == -1 and p["right"] == "Their slugging"
    assert _zone(p, "heart")["diff"] > 0, "Boston slugs in the heart (its homers)"
    assert p["overall"]["rank"] == p["overall"]["of"], "the hardest-slugging lineup is the worst for a pitcher"


def test_too_little_this_season_reads_the_last():
    conn = _conn()
    rows = [_row({}, season=2027, opponent="DET", player="WR1", position="WR", air_yards=5.0, side="M",
                 complete=1, yards=5.0) for _ in range(5)]
    D.upsert_targets(conn, rows)
    d = M.chart(conn, "nfl", "Zay Flowers", "DET")
    assert d["season"] == 2026 and d["newest"] == 2027, "five targets in 2027 is not a defence"


def test_the_door_answers_the_matchup():
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
        q = {"kind": ["matchup"], "sport": ["nfl"], "player": ["Zay Flowers"], "opp": ["DET"], "fam": ["routes"]}
        h._players_chart(q)
        conn = D.connect(path)
        _nfl(conn)
        conn.close()
        h._players_chart(q)
        h._players_chart(dict(q, opp=[""]))
        h._players_chart(dict(q, sport=["ufc"]))
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "matchup" and sent[1][1]["family"] == "routes"
    assert sent[2] == (200, {}), "no opponent, no matchup"
    assert sent[3][0] == 400
    assert all(CH.known("matchup", lg) for lg in ("nfl", "cfb", "nba", "nhl", "mlb"))
    assert not CH.known("matchup", "wnba") and not CH.known("matchup", "ufc")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{MV_JS}\n"
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


def test_the_page_draws_one_row_a_zone():
    d = M.chart(_conn(), "nfl", "Zay Flowers", "DET")
    d["kind"] = "matchup"
    got = _node(f"""
      const d = {json.dumps(d)}, P = T.DRAW.matchup, v = P.only(d, "nfl");
      return {{ fig: v.fig, side: v.side, tail: v.tail, top: v.top, note: P.note(d),
                rows: (v.fig.match(/class="mv-row/g) || []).length, gain: (v.fig.match(/mv-diff gain/g) || []).length,
                kind: [T.KIND.matchup.chip, T.KIND.matchup.title] }};
    """)
    if got is None:
        return
    assert got["rows"] == 10 and got["gain"] >= 1
    assert got["top"] == '<div class="cc-title">Tonight: DET · 2026</div>'
    assert "Yards a target allowed to WRs" in got["fig"] and ">+" in got["fig"]
    assert ">Fit<" in got["side"] and "1st of 6" in got["side"] and "yds/target where he’s thrown to" in got["side"]
    assert "Zone by zone" in got["tail"] and "(8)" in got["tail"]
    assert "did not make our picks better on their own" in got["note"] and "nothing here moves a price" in got["note"]
    assert got["kind"] == ["Matchup", "Matchup"]


def test_the_slot_carries_tonight_s_opponent_and_the_matchup_comes_last():
    i = APP_JS.index("function chartSlot(")
    assert 'data-opp="${escapeAttr(r.opponent || "")}"' in APP_JS[i:i + 600]
    assert 'if (d.opp && kinds.some((k) => MATCHED.has(k))) kinds.push("matchup");' in CC_JS
    assert 'const LATE = { role: 1, matchup: 2 };' in CC_JS and "(LATE[a.k] || 0) - (LATE[b.k] || 0)" in CC_JS
    assert '&opp=${encodeURIComponent(S.opp || "")}&fam=${encodeURIComponent(S.fam || "")}' in CC_JS
    for k in ("carries", "routes", "passes", "shots", "shotmap", "saves", "spray", "pitches"):
        assert f'"{k}"' in CC_JS[CC_JS.index("const MATCHED = new Set("):CC_JS.index("const MATCHED = new Set(") + 140]
    assert 'matchup: "matchup"' in CC_JS and 'Q.draw("matchup"' in MV_JS
    assert "onclick" not in MV_JS and "onerror" not in MV_JS and not re.search(r"on(error|load)\s*=", MV_JS)
    for cls in (".mv-svg", ".mv-share", ".mv-diff.gain", ".mv-diff.loss", ".mv-v.gain", ".mv-row.hot .mv-z",
                ".mv-fit.gain b"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
