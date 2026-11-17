"""A passing chart for every college passer (2026-11-17).

Ethan, on the player page: "We should still have the players route charts
and pass charts and shit on the player page." A college quarterback had runs
and a role and no passing chart. What these hold:

  * THE FOLD (engine/passes.CfbPasses), over the college play file the logs,
    carries and targets are read from: every attempt the file names the
    passer of (an incompletion, an interception), every completion with its
    passer settled the way the logs settle it (`cfbstats.split_pass`, the
    file swapping the two names on a score), a sack with its yards lost
    (``sack_taken_stat``), one attempt a row at most, a touchdown by the
    feed's name (the geometry alone is not one), the receiver where the
    file names one, no air yards, no side and no hit, a school not in the
    game and a game not ingested left out, and only the games the logs keep;
  * ONE READ: the nightly college ingest and the chart filler store the
    throws beside the carries and targets, a game the logs drop cleared;
  * THE CHART: `passes.chart(..., sport="cfb")` says what it has (no air,
    no depth or side or pressure splits), the doors serve it, the filler
    owes it, and an NFL lookup never reaches it;
  * THE PAGE: a college passer's charts are the throws, the runs and the
    role; the throws are drawn straight upfield with the misses at the line
    and the picks and sacks crossed; the player page leads with them.

Run directly: `python3 tests/test_a_passing_chart_for_every_college_passer.py`.
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

from engine import carries as CR, chartfill as CF, charts as CH, db as D, passes as PS  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
PAGE_JS = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
GAMES = {"401": {"period": "2026-09-13", "home": "UGA", "away": "ALA",
                 "home_name": "Georgia", "away_name": "Alabama"},
         "402": {"period": "2026-09-20", "home": "UGA", "away": "TENN",
                 "home_name": "Georgia", "away_name": "Tennessee"}}
ROSTER = {"77": {"name": "Zachariah Branch", "position": "WR", "headshot": ""},
          "11": {"name": "Gunner Stockton", "position": "QB", "headshot": ""}}


def _row(**kw):
    row = {"game_id": "401", "season": "2026", "week": "3", "team": "Georgia", "play_id": "401000000000000100",
           "period": "1", "yards_to_goal": "75", "down": "1", "distance": "10",
           "completion_player": "Gunner Stockton", "completion_player_id": "11",
           "reception_player": "Zachariah Branch", "reception_player_id": "77",
           "reception_yds": "14", "completion_yds": "14", "incompletion_player": "NA", "incompletion_player_id": "NA",
           "target_player": "NA", "target_player_id": "NA", "interception_thrown_player": "NA",
           "interception_thrown_player_id": "NA", "sack_taken_player": "NA", "sack_taken_player_id": "NA",
           "sack_taken_stat": "NA", "touchdown_player": "NA", "rush_player": "NA"}
    row.update(kw)
    return row


def _miss(**kw):
    base = dict(completion_player="NA", completion_player_id="NA", reception_player="NA",
                reception_player_id="NA", reception_yds="NA", completion_yds="NA",
                incompletion_player="Gunner Stockton", incompletion_player_id="11",
                target_player="Zachariah Branch", target_player_id="77")
    base.update(kw)
    return _row(**base)


def _sack(**kw):
    base = dict(completion_player="NA", completion_player_id="NA", reception_player="NA",
                reception_player_id="NA", reception_yds="NA", completion_yds="NA",
                sack_taken_player="Gunner Stockton", sack_taken_player_id="11", sack_taken_stat="7")
    base.update(kw)
    return _row(**base)


def _rows():
    return [
        _row(),                                                                  # 14-yard completion
        _miss(play_id="401000000000000200", down="2"),                           # thrown at Branch, incomplete
        # The file swaps the two names on a score: the passer's misses and
        # sack say who threw it. The feed names the scorer.
        _row(play_id="401000000000000300", completion_player="Zachariah Branch", completion_player_id="77",
             reception_player="Gunner Stockton", reception_player_id="11", reception_yds="9",
             completion_yds="9", yards_to_goal="9", touchdown_player="Zachariah Branch", period="2"),
        _row(play_id="401000000000000500", completion_player="NA", reception_player="NA",
             interception_thrown_player="Gunner Stockton", interception_thrown_player_id="11"),  # picked off
        _miss(play_id="401000000000000600", target_player="NA", target_player_id="NA"),  # a miss naming nobody
        _sack(play_id="401000000000000650", period="2"),                          # sacked for 7
        _row(play_id="401000000000000700", team="Tennessee"),                     # not a school in this game
        _row(game_id="999", play_id="999000000000000001"),                        # a game not ingested
        # 31 yards from the 40 with no name on the score: the geometry alone is no touchdown.
        _row(game_id="402", play_id="402000000000000100", reception_yds="40", completion_yds="40",
             yards_to_goal="40", distance="5", period="3"),
        # A row naming a sack and an incompletion is one attempt, as the logs count it.
        _miss(game_id="402", play_id="402000000000000200", sack_taken_player="Gunner Stockton",
              sack_taken_player_id="11", sack_taken_stat="4"),
    ]


def _fold(rows=None, season=2026):
    fold = PS.CfbPasses(season, GAMES, ROSTER)
    for r in rows or _rows():
        fold.add(r)
    return fold


# --- the fold ---------------------------------------------------------------------
def test_every_throw_and_sack_the_file_names_the_passer_of():
    rows = {r["play_id"]: r for r in _fold().rows()}
    assert sorted(rows) == ["401000000000000100", "401000000000000200", "401000000000000300", "401000000000000500",
                            "401000000000000600", "401000000000000650", "402000000000000100",
                            "402000000000000200"], sorted(rows)
    assert all(r["player"] == "Gunner Stockton" and r["sport"] == "cfb" for r in rows.values()), \
        "every throw is the passer's, the swapped score too"
    swapped = rows["401000000000000300"]
    assert (swapped["kind"], swapped["complete"], swapped["yards"], swapped["td"], swapped["receiver"]) == \
        ("pass", 1, 9.0, 1, "Zachariah Branch")
    first = rows["401000000000000100"]
    assert (first["complete"], first["yards"], first["first_down"], first["receiver"], first["receiver_id"]) == \
        (1, 14.0, 1, "Zachariah Branch", "77")
    assert (first["air_yards"], first["side"], first["hit"], first["yac"], first["clock"]) == (None, "", None, None, ""), \
        "nothing the file does not record"
    assert first["position"] == "QB" and first["qtr"] == 1 and first["yardline_100"] == 75
    miss = rows["401000000000000200"]
    assert (miss["kind"], miss["complete"], miss["interception"], miss["receiver"]) == ("pass", 0, 0, "Zachariah Branch")
    assert rows["401000000000000600"]["receiver"] == "", "a miss the file names nobody on is still an attempt"
    pick = rows["401000000000000500"]
    assert (pick["kind"], pick["complete"], pick["interception"], pick["receiver"]) == ("pass", 0, 1, "")
    sack = rows["401000000000000650"]
    assert (sack["kind"], sack["yards"], sack["complete"]) == ("sack", -7.0, 0), "sack_taken_stat is the yards lost"
    assert rows["402000000000000200"]["kind"] == "pass", "a row naming both is one attempt, not a sack too"
    long_ = rows["402000000000000100"]
    assert long_["td"] == 0 and long_["yards"] == 40.0, "the geometry alone is no touchdown: the feed names scorers"


def test_only_the_games_the_logs_keep():
    assert {r["game_id"] for r in _fold().rows(kept={"402"})} == {"402"}
    assert _fold().rows(kept=set()) == []


def test_one_read_stores_the_throws_beside_the_carries_and_targets():
    from engine import ingest
    from engine.sources import cfbstats
    tmp = tempfile.mkdtemp()
    try:
        conn = D.connect(os.path.join(tmp, "history.db"))
        for gid, period, away, away_name in (("401", "2026-09-13", "ALA", "Alabama"),
                                             ("402", "2026-09-20", "TENN", "Tennessee")):
            D.upsert_games(conn, [{"sport": "cfb", "season": 2026, "period": period, "game_id": gid,
                                   "home": "UGA", "away": away, "home_score": 7.0, "away_score": 0.0,
                                   "extra": json.dumps({"home_name": "Georgia", "away_name": away_name})}])
        keep = (cfbstats._stream, cfbstats.fetch_rosters)
        reads = []

        def stream(url, name, ttl):
            reads.append(name)
            return iter(_rows())
        cfbstats._stream = stream
        cfbstats.fetch_rosters = lambda season, ttl=0: ROSTER
        try:
            ingest.ingest_cfb_player_history(conn, [2026], quiet=True)
            nightly = conn.execute("SELECT COUNT(*), SUM(complete), SUM(kind='sack') FROM passes "
                                   "WHERE sport='cfb' AND player='Gunner Stockton'").fetchone()
            conn.execute("DELETE FROM passes WHERE sport='cfb'")
            CR.backfill_cfb(conn, 2026)
            filled = conn.execute("SELECT COUNT(*) FROM passes WHERE sport='cfb'").fetchone()[0]
        finally:
            cfbstats._stream, cfbstats.fetch_rosters = keep
        assert reads == ["cfb_player_stats_2026.csv"] * 2, "one read each: the nightly, then the filler"
        logs = dict(conn.execute("SELECT market, SUM(value) FROM player_game_logs WHERE sport='cfb' AND "
                                 "player='Gunner Stockton' AND market IN ('pass_att', 'pass_cmp') "
                                 "GROUP BY market").fetchall())
        n, cmp_, sacks = nightly
        assert (n - sacks, cmp_) == (int(logs["pass_att"]), int(logs["pass_cmp"])), (nightly, logs)
        assert sacks == 1 and filled == n, "the filler stores what the nightly stores"
        # A game the logs drop takes its throws with it.
        CR.store_cfb(conn, 2026, CR.CfbCarries(2026, GAMES, ROSTER), _target_fold(), {"401"}, _fold())
        assert {r[0] for r in conn.execute("SELECT DISTINCT game_id FROM passes WHERE sport='cfb'")} == {"401"}
        conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _target_fold():
    from engine import targets as TG
    fold = TG.CfbTargets(2026, GAMES, ROSTER)
    for r in _rows():
        fold.add(r)
    return fold


# --- the chart --------------------------------------------------------------------
def _conn(path=":memory:"):
    conn = D.connect(path)
    D.upsert_passes(conn, _fold().rows())
    return conn


def test_the_college_chart_says_what_it_has():
    d = PS.chart(_conn(), "Gunner Stockton", sport="cfb")
    assert d["sport"] == "cfb" and d["air"] is False and d["ngs"] == {}
    assert d["by_zone"] == [] and d["by_pressure"] == [], "no depth, side or pressure on file: no such splits"
    assert [g["id"] for g in d["games"]] == ["402", "401"] and d["games"][0]["week"] is None, "newest first"
    L = d["season_line"]
    assert (L["att"], L["cmp"], L["yds"], L["td"], L["int"], L["sk"], L["sk_yds"]) == (7, 3, 63.0, 1, 1, 1, -7.0), L
    assert L["adot"] is None and L["cpoe"] is None, "no air yards, no completion over expected"
    assert [x["down"] for x in d["by_down"]] == [1, 2], d["by_down"]
    assert d["by_target"] == [{"to": "Zachariah Branch", "tgt": 5, "rec": 3, "yds": 63.0, "td": 1, "int": 0}]
    assert PS.chart(_conn(), "Gunner Stockton") == {}, "the NFL's passing chart is the NFL's"
    assert PS.chart(_conn(), "gunner stockton", sport="cfb")["player"] == "Gunner Stockton"


def test_the_doors_serve_college_and_the_filler_owes_it():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        _conn(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_chart({"kind": ["passes"], "sport": ["cfb"], "player": ["Gunner Stockton"]})
        h._players_chart({"kind": ["passes"], "sport": ["nba"], "player": ["Gunner Stockton"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0][0] == 200 and sent[0][1]["kind"] == "passes" and sent[0][1]["air"] is False
    assert sent[0][1]["season_line"]["att"] == 7 and "face" in sent[0][1]
    assert sent[1][0] == 400
    assert CH.known("passes", "cfb") and ("cfb", "passes") in CF.TABLES
    import datetime as dt
    conn = D.connect(":memory:")
    D.upsert_games(conn, [{"sport": "cfb", "season": 2026, "period": "2026-09-13", "game_id": "401",
                           "home": "UGA", "away": "ALA", "home_score": 7.0, "away_score": 0.0}])
    D.upsert_carries(conn, [{"sport": "cfb", "season": 2026, "period": "2026-09-13", "game_id": "401",
                             "play_id": "1", "player": "Nate Frazier"}])
    assert ("cfb", 2026, "passes") in CF.owed(conn, dt.date(2026, 11, 17)), "carries on file, no throws: owed"
    D.upsert_passes(conn, _fold().rows())
    assert ("cfb", 2026, "passes") not in CF.owed(conn, dt.date(2026, 11, 17))


# --- the page -----------------------------------------------------------------------
def _node(js):
    node = shutil.which("node") or ("/opt/node22/bin/node" if os.path.exists("/opt/node22/bin/node") else None)
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = f"{stubs}\n{CC_JS}\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_college_throws_straight_upfield():
    d = PS.chart(_conn(), "Gunner Stockton", sport="cfb")
    got = _node(f"""
      const d = {json.dumps(d)}, g = d.games[1];
      const P = T.DRAW.passes, svg = P.game(g, d), season = P.season(d);
      return {{
        completions: (svg.match(/class="rc-route/g) || []).length, misses: (svg.match(/class="rc-miss/g) || []).length,
        crosses: (svg.match(/class="rc-sack/g) || []).length, tds: (svg.match(/class="cc-td"/g) || []).length,
        marks: (svg.match(/class="cc-carry"/g) || []).length,
        aria: /aria-label="Passing chart: 5 throws vs ALA/.test(svg),
        dots: (season.match(/class="rc-dot c"/g) || []).length, cells: (season.match(/class="rc-cell"/g) || []).length,
        avg: season.includes("21.0 a completion"), counted: season.includes("3 incomplete · 1 intercepted"),
        bands: (season.match(/>1 of 3</g) || []).length, seasonLegend: T.DRAW.passes.seasonSide(d),
        side: P.seasonSide(d), gameSide: P.gameSide(g, d), note: P.note(d), nflNote: P.note({{}}),
        words: T.passWords(g.throws[1]), title: T.kindOf("passes", "cfb").title, sec: T.descOf("passes", "cfb"),
        kinds: [T.kindsFor("cfb", "pass_yds", "QB"), T.kindsFor("cfb", "pass_yds", ""), T.kindsFor("cfb", "rush_yds", "QB"),
                T.kindsFor("nfl", "pass_yds", "QB"), T.kindsFor("cfb", "receptions", "WR")],
      }};
    """)
    if got is None:
        return
    # Game 401: 14 and 9 completed (the 9 a score), a miss to Branch, a pick, a miss naming nobody, a sack.
    assert got["completions"] == 2 and got["misses"] == 2 and got["crosses"] == 2 and got["tds"] == 1, got
    assert got["marks"] == 6 and got["aria"], got
    # The season is bands, not a mark a throw: a passer's hundreds of throws drawn one by one were a solid wedge.
    assert got["dots"] == 3 and got["avg"], "63 yards on three completions: 21.0 a completion"
    assert got["bands"] == 3 and got["counted"] and got["cells"] >= 3, "9, 14 and 40 yards: one in each band"
    assert "Share of the completions" in got["seasonLegend"]
    assert "Cmp/Att</span><b>3/7</b>" in got["side"] and "aDOT" not in got["side"] and "Throw time" not in got["side"]
    assert "Sacked</span><b>1 (−7)</b>" in got["side"] or "Sacked</span><b>1 (-7)</b>" in got["side"], got["side"]
    assert "Interception · sack" in got["gameSide"]
    assert "not how far the ball travelled" in got["note"] and "game log" in got["note"]
    assert "air yards" in got["nflNote"], "the NFL's note is the NFL's"
    assert got["words"] == "to Zachariah Branch", got["words"]
    assert got["title"] == "Passing chart" and "names the passer of" in got["sec"]
    assert got["kinds"] == [["passes", "carries", "role"], ["passes", "carries", "role"], ["passes", "carries", "role"],
                            ["passes", "carries", "role"], ["routes", "carries", "role"]], got["kinds"]


def test_the_player_page_leads_with_a_college_passers_throws():
    i = PAGE_JS.index("function plrChartRow(")
    body = PAGE_JS[i:PAGE_JS.index("\n}\n", i)]
    assert 'const mkt = PLR_CHART_MKT[d.role] || "";' in body and "rush_yds" not in body
    assert 'cfb: ["carries", "routes", "passes", "role"]' in CC_JS


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
