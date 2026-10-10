"""A pushed model change reaches the board, the same way every time, and the site says so.

Ethan, 2026-09-23: "the same most likely pics that we had earlier are the
same ones that are there now … make sure all of our new changes are
taking effect and our models are being updated and pics are updated."

Three things stood between a push and the picks:

  * A slow build. A build that misses its 600-second ceiling keeps the last
    good board (launch.refresh_nfl, "kept last board"), and the slate build
    re-read the whole season for every player and market — 80 of 108
    seconds here, several times that on the droplet's one core, and the
    day's model work added players and markets to it. Each player's rows
    are read once now (nflverse._rows_by_player): 69 s → 21 s on 2026
    week 3, the same 611 rows.
  * A board that changed with the process. The team order came from a set,
    so a quarterback ranked on his old team's rows could take his new
    team's starter slot on one run and not the next — Cincinnati's starter
    was Flacco under four hash seeds of six and Burrow under two. A
    quarterback who played for the team claims it first, and teams run in
    order.
  * Nothing on the site said which code was running or whether the NFL
    board rebuilt on it. The Status page does now.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import nflverse as N                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_a_quarterback_who_played_for_the_team_claims_it_whatever_the_order():
    S = N.PlayerSpec
    home = {"Joe Burrow": "CIN", "Jake Browning": "CIN", "Joe Flacco": "CIN", "Dillon Gabriel": "CLE"}
    team_of = home.get
    burrow = [S("Joe Burrow", "pass_yds", "starter", "QB", "CIN"), S("Jake Browning", "pass_yds", "backup", "QB", "CIN")]
    flacco = [S("Joe Flacco", "pass_yds", "starter", "QB", "CLE")]      # Cleveland's weeks, Cincinnati now
    for specs in (burrow + flacco, flacco + burrow):
        got = N.one_quarterback_each(specs, team_of)
        assert [(s.player, s.usage_role) for s in got] == \
            [(s.player, s.usage_role) for s in specs if s.player != "Joe Flacco"], got
    wr = S("Ja'Marr Chase", "rec_yds", "wr1", "WR", "CIN")
    got = N.one_quarterback_each([wr] + flacco + burrow, team_of)
    assert got[0] is wr and [s.player for s in got] == ["Ja'Marr Chase", "Joe Burrow", "Jake Browning"], \
        "everything else keeps its place"
    only = N.one_quarterback_each(flacco, team_of)
    assert [s.player for s in only] == ["Joe Flacco"], "with nobody who played there, he is still the one"


def test_the_rankings_come_out_in_one_order():
    rows = []
    for team in ("NYG", "BUF", "KC", "ATL", "DAL"):
        for wk in (1, 2):
            rows.append({"season_type": "REG", "week": str(wk), "recent_team": team, "position": "WR",
                         "player_display_name": f"{team} WR", "targets": "8"})
    specs = N.top_players_for_week(rows, {"NYG", "BUF", "KC", "ATL", "DAL"}, 3)
    teams = [s.team for s in specs]
    assert teams == sorted(teams) and set(teams) == {"NYG", "BUF", "KC", "ATL", "DAL"}
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    body = src[src.index("def _carry_specs("):src.index("def one_quarterback_each(")]
    assert "for team in sorted(teams):" in body and "pos, team))" in body


def test_each_player_s_rows_are_read_once_and_mean_the_same():
    rows = [{"player_display_name": "A", "week": "1", "receiving_yards": "10"},
            {"player_name": "B", "week": "1", "receiving_yards": "20"},
            {"player_display_name": "A", "week": "2", "receiving_yards": "30"}]
    by = N._rows_by_player(rows)
    assert [r["week"] for r in by["A"]] == ["1", "2"] and len(by["B"]) == 1
    for name in ("A", "B"):
        assert [g.value for g in N.player_game_logs(by[name], name, "rec_yds", 9)] == \
            [g.value for g in N.player_game_logs(rows, name, "rec_yds", 9)]
        assert N.career_average(by[name], name, "rec_yds") == N.career_average(rows, name, "rec_yds")
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    body = src[src.index("def build_slate("):]
    assert "stats_of = _rows_by_player(stats)" in body and "prior_of = _rows_by_player(prior_stats)" in body
    assert "player_game_logs(stats," not in body and "career_average(\n                prior_stats" not in body


def test_the_status_page_names_the_code_and_each_league_s_last_build():
    assert "${buildsCardHTML(hb)}" in APP
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    def fn(name):
        i = APP.index(f"function {name}(")
        return APP[i:APP.index("\n}\n", i) + 2]
    lead = APP[APP.index("const BUILD_LEAGUES"):APP.index("function buildsCardHTML(")]
    hb = {"commit": "c790076e", "auto_update": True, "boards": {
        "nfl": {"ok": False, "at_epoch": 0, "note": "kept last board (611 props) — full build failed: timed out"},
        "mlb": {"ok": True, "at_epoch": 0}, "memes": {"ok": True, "at_epoch": 0}}}
    prog = (fn("escapeHtml") + "\nconst ageText = (s) => `${Math.round(s)}s`;\n" + lead + fn("buildsCardHTML")
            + f"\nconsole.log(JSON.stringify([buildsCardHTML({json.dumps(hb)}), buildsCardHTML(null)]));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html, none = json.loads(out.stdout)
    assert none == "" and "Model builds" in html and "c790076e" in html and "updates itself" in html
    assert "st-bad" in html and "build failed" in html and "full build failed: timed out" in html
    assert "rebuilt" in html and "memes" not in html.lower(), "leagues only"
    assert ".st-bad { color: var(--bad); }" in open(os.path.join(ROOT, "web", "css", "styles.css"),
                                                     encoding="utf-8").read()


def _launch():
    os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
    import launch
    return launch


def test_the_code_running_is_read_even_when_git_will_not_answer():
    """Ethan's Status page, 2026-09-23: "Code running: unknown". The site
    runs as `qellys` and the checkout is root's, so git refuses it
    ("dubious ownership"); the files themselves are readable."""
    L = _launch()
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".git", "refs", "heads"))
    with open(os.path.join(d, ".git", "HEAD"), "w") as fh:
        fh.write("ref: refs/heads/main\n")
    with open(os.path.join(d, ".git", "refs", "heads", "main"), "w") as fh:
        fh.write("c790076ef56a437ced062c92a8ad882b49b57a84\n")
    assert L._commit_from_files(d) == "c790076e"
    os.remove(os.path.join(d, ".git", "refs", "heads", "main"))
    with open(os.path.join(d, ".git", "packed-refs"), "w") as fh:
        fh.write("# pack-refs with: peeled\nd23232e8354f648694cdcc790ea3b5d479d0539a refs/heads/main\n")
    assert L._commit_from_files(d) == "d23232e8", "a packed ref"
    with open(os.path.join(d, ".git", "HEAD"), "w") as fh:
        fh.write("8cf89a87968d049118a0e5d629930a5eceb79e3c\n")
    assert L._commit_from_files(d) == "8cf89a87", "detached"
    assert L._commit_from_files(tempfile.mkdtemp()) == ""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "_RUNNING_COMMIT.append(out if ok else _commit_from_files(ROOT))" in src


def test_each_league_s_most_likely_and_edge_boards_are_counted_after_a_build():
    L = _launch()
    path = os.path.join(tempfile.mkdtemp(), "zz_status_counts_test.json")
    with open(path, "w") as fh:
        json.dump({"most_likely": [{}, {}, {}],
                   "recommendations": [{"ev_per_unit": 0.04, "recommended": True},
                                       {"ev_per_unit": 0.02, "has_market": False},
                                       {"ev_per_unit": 0.003}, {"ev_per_unit": 0.06}],
                   "game_bets": [{"ev_per_unit": 0.05, "grade": "B", "recommended": True},
                                 {"ev_per_unit": 0.05, "grade": "Pass"}]}, fh)
    assert L._board_counts(path) == {"most_likely": 3, "edge": 3, "staked": 2}
    assert L._board_counts(path + ".missing") == {}
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _note_board("):src.index("def _note_board(") + 3000]
    assert "_BOARD_RUNS[name].update(_board_counts(BOARD_FILES[name]))" in body


def test_a_young_process_does_not_call_a_healthy_board_stale():
    i = APP.index("function staleAfterMs(")
    fn = APP[i:APP.index("\n}", i)]
    assert "if (!_cycleMs) return STALE_FLOOR_MS * 2;" in fn


def test_the_status_page_names_both_boards_under_each_league():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    def fn(name):
        i = APP.index(f"function {name}(")
        return APP[i:APP.index("\n}\n", i) + 2]
    lead = APP[APP.index("const BUILD_LEAGUES"):APP.index("function buildsCardHTML(")]
    hb = {"commit": "d23232e8", "boards": {
        "nfl": {"ok": True, "at_epoch": 0, "most_likely": 40, "edge": 3, "staked": 1},
        "cfb": {"ok": False, "at_epoch": 0, "note": "timed out", "most_likely": 12, "edge": 0, "staked": 0},
        "ufc": {"ok": True, "at_epoch": 0}}}
    prog = (fn("escapeHtml") + "\nconst ageText = (s) => `${Math.round(s)}s`;\n" + lead + fn("buildsCardHTML")
            + f"\nconsole.log(JSON.stringify(buildsCardHTML({json.dumps(hb)})));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html = " ".join(json.loads(out.stdout).split())
    assert "Most Likely board" in html and "40 picks" in html and "Edge board" in html and "3 bets" in html
    assert "1 staked" in html and "nothing priced wrong" in html and "the last good board" in html
    assert html.count("Most Likely board") == 2, "a board with no counts (UFC) gets no rows"


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
