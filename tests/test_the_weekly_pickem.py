"""The weekly pick'em: pick the winner of every game on the board, free, graded from the final.

Ethan, 2026-10-15, the last of the sixteen ideas he asked to have built
("do every one for every sport"): a free weekly pick'em with a leaderboard
on Social. Nothing on the board reads or moves for it.

What these hold: a week runs Tuesday to Monday, Eastern, so a Thursday
night and a Monday night game are one NFL week; a pick needs a Social
handle, names one of the two teams of a game on that sport's own board,
and locks at kickoff (or the board's live flag) — it can change until
then and never after; grading reads the finals table only, oriented to
the pick's own home and away, a tie is a push, two different finals are
refused rather than guessed, and a game with no final ten days on is
void; the standings rank wins then fewest losses, share a rank on a tie,
name only people with a handle and hide a block; the week keeps a game
the board has since dropped; the endpoints read only which game and
which team and open the finals read-only; a deleted account takes its
picks with it; and Social draws the tab, the games, the split and both
tables.

Run directly: `python3 tests/test_the_weekly_pickem.py`
"""
import datetime as dt
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import pickem as PK                                  # noqa: E402
from engine import socialfeed as SF                              # noqa: E402

SOCIAL = ROOT / "web" / "js" / "social.js"
UTC = dt.timezone.utc


def _t(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


NOW = _t(2026, 10, 16, 16)                    # Friday noon, Eastern
GAMES = [  # Thursday night (already played), Sunday, and Monday night
    {"home": "MIN", "away": "DET", "date": "2026-10-15", "kickoff": "2026-10-16T00:15:00Z"},
    {"home": "CHI", "away": "GB", "date": "2026-10-18", "kickoff": "2026-10-18T17:00:00Z"},
    {"home": "NYJ", "away": "BUF", "date": "2026-10-19", "kickoff": "2026-10-20T00:15:00Z", "live": False},
]


def _board(tmp, games=GAMES, name="recommendations.json"):
    (Path(tmp) / name).write_text(json.dumps({"games": games}), encoding="utf-8")
    return Path(tmp)


def _conn(*handles):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    SF.ensure_tables(c)
    for i, h in enumerate(handles, 1):
        if h:
            assert SF.profile_set(c, i, h, "")[0] == 200
    return c


def test_a_week_runs_tuesday_to_monday_eastern():
    thu, mon = PK._ts(GAMES[0]["kickoff"]), PK._ts(GAMES[2]["kickoff"])
    assert PK.week_of(thu) == PK.week_of(mon) == "2026-10-13", "Thursday night to Monday night is one week"
    assert PK.week_of(_t(2026, 10, 20, 3, 30)) == "2026-10-13", "Monday 11:30 p.m. Eastern is still Monday"
    assert PK.week_of(_t(2026, 10, 20, 4, 30)) == "2026-10-20", "Tuesday 12:30 a.m. Eastern starts the next one"
    assert PK.week_label("2026-10-13") == "Oct 13 – 19" and PK.week_label("2026-10-27") == "Oct 27 – Nov 2"
    assert PK.valid_week("2026-10-13") and not PK.valid_week("2026-10-14") and not PK.valid_week("junk")


def test_a_pick_is_a_team_in_a_board_game_before_kickoff():
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp)
        c = _conn(None, "rival")
        gb = "2026-10-18|GB@CHI"
        assert PK.pick(c, 1, "nfl", gb, "GB", NOW, d)[0] == 409, "no handle, no entry: the table names people"
        assert SF.profile_set(c, 1, "ethan_t", "")[0] == 200
        assert PK.pick(c, 1, "xfl", gb, "GB", NOW, d)[0] == 400
        assert PK.pick(c, 1, "nfl", "2026-10-18|GB@DAL", "GB", NOW, d)[0] == 404, "only a game on the board"
        assert PK.pick(c, 1, "nfl", gb, "DAL", NOW, d)[0] == 400, "one of its two teams"
        code, out = PK.pick(c, 1, "nfl", "2026-10-15|DET@MIN", "DET", NOW, d)
        assert code == 409 and "picks lock at kickoff" in out["error"]
        assert PK.pick(c, 1, "nfl", gb, "GB", NOW, d) == (200, {"ok": True, "gid": gb, "pick": "GB", "week": "2026-10-13"})
        assert PK.pick(c, 1, "nfl", gb, "CHI", NOW + 3600, d)[0] == 200, "changed before kickoff"
        assert PK.pick(c, 1, "nfl", gb, "GB", PK._ts(GAMES[1]["kickoff"]) + 1, d)[0] == 409, "never after"
        rows = c.execute("SELECT pick, result FROM pickem_picks").fetchall()
        assert [tuple(r) for r in rows] == [("CHI", None)]
        _board(tmp, [dict(GAMES[2], live=True)])
        assert PK.pick(c, 2, "nfl", "2026-10-19|BUF@NYJ", "BUF", NOW, d)[0] == 409, "the board's live flag locks it too"


def test_a_football_clock_and_the_scoreboard_status_are_read_right():
    """The box, 2026-10-16: BV read "0 games" with the NFL board full. The
    NFL's kickoff is a bare Eastern clock beside its date, and every game
    carries the scoreboard's status, "scheduled" before the start."""
    nfl = [{"home": "CHI", "away": "GB", "date": "2026-10-18", "kickoff": "13:00", "live": {"state": "scheduled"}},
           {"home": "NYJ", "away": "BUF", "date": "2026-10-19", "kickoff": "20:15", "live": None},
           {"home": "MIN", "away": "DET", "date": "2026-10-15", "kickoff": "20:15", "live": {"state": "final"}},
           {"home": "KC", "away": "LV", "date": "2026-W06", "kickoff": "16:25"}]
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp, nfl)
        got = {g["gid"]: g for g in PK.board_games("nfl", d)}
        assert set(got) == {"2026-10-18|GB@CHI", "2026-10-19|BUF@NYJ", "2026-10-15|DET@MIN"}, \
            "a week label is no day: that game is left off, not guessed"
        assert got["2026-10-18|GB@CHI"]["kickoff"] == _t(2026, 10, 18, 17), "13:00 Eastern on the 18th"
        assert got["2026-10-18|GB@CHI"]["live"] is False and got["2026-10-15|DET@MIN"]["live"] is True
        c = _conn("ann")
        assert PK.pick(c, 1, "nfl", "2026-10-18|GB@CHI", "GB", NOW, d)[0] == 200, "a scheduled game takes a pick"
        v = PK.view(c, "nfl", 1, now=NOW, data_dir=d)
        assert [g["locked"] for g in v["games"]] == [True, False, False]


def _hist(rows):
    h = sqlite3.connect(":memory:")
    h.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, date TEXT, home TEXT, away TEXT, "
              "home_score REAL, away_score REAL)")
    h.executemany("INSERT INTO games VALUES (?,?,?,?,?,?,?,?)", rows)
    return h


def _seed(c, uid, gid, home, away, date, kickoff, pick, sport="nfl"):
    c.execute("INSERT INTO pickem_picks (user_id, sport, week, gid, home, away, game_date, kickoff, pick, created_at, "
              "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (uid, sport, PK.week_of(kickoff), gid, home, away, date, kickoff, pick, kickoff - 99, kickoff - 99))


def test_grading_reads_the_final_and_never_guesses():
    c = _conn("abe", "bea", "cal")
    PK.ensure_tables(c)
    k = _t(2026, 10, 18, 17)
    _seed(c, 1, "g1", "CHI", "GB", "2026-10-18", k, "GB")
    _seed(c, 2, "g1", "CHI", "GB", "2026-10-18", k, "CHI")
    _seed(c, 1, "g2", "LAR", "SEA", "2026-10-18", k, "SEA")       # filed the other way round in the finals
    _seed(c, 1, "g3", "PHI", "DAL", "2026-10-18", k, "DAL")       # a tie
    _seed(c, 1, "g4", "MIA", "NE", "2026-10-18", k, "NE")         # two different finals
    _seed(c, 1, "g5", "TEN", "HOU", "2026-10-01", _t(2026, 10, 1, 17), "HOU")    # never a final
    _seed(c, 3, "g6", "KC", "LV", "2026-10-19", k + 86400, "KC")  # not due yet
    h = _hist([("nfl", 2026, "7", "2026-10-18", "CHI", "GB", 24, 17),
               ("nfl", 2026, "7", "2026-10-18", "SEA", "LAR", 20, 13),
               ("nfl", 2026, "7", "2026-10-18", "PHI", "DAL", 20, 20),
               ("nfl", 2026, "7", "2026-10-18", "MIA", "NE", 10, 3),
               ("nfl", 2026, "7", "2026-10-19", "MIA", "NE", 3, 10),
               ("nba", 2026, "2026-10-18", None, "CHI", "GB", 1, 0)])
    now = k + 4 * 3600
    assert PK.grade(c, lambda: h, now) == 5, "two on g1, then g2, the push and the void"
    got = {(r["user_id"], r["gid"]): r["result"] for r in c.execute("SELECT * FROM pickem_picks")}
    assert got[(1, "g1")] == "lost" and got[(2, "g1")] == "won"
    assert got[(1, "g2")] == "won", "oriented to the pick's own home and away"
    assert got[(1, "g3")] == "push" and got[(1, "g4")] is None, "ambiguity is refused, not guessed"
    assert got[(1, "g5")] == "void" and got[(3, "g6")] is None
    assert PK.grade(c, lambda: h, now + 60) == 0, "a pick tried a minute ago waits its retry"
    assert PK.grade(c, lambda: 1 / 0, now + 3600) == 0, "a finals table that will not open grades nothing"


def test_the_table_ranks_wins_then_fewest_losses():
    c = _conn("ann", "bob", "cyd", None)
    PK.ensure_tables(c)
    k = _t(2026, 10, 18, 17)
    res = {1: ["won", "won", "lost"], 2: ["won", "won", "push"], 3: ["won", "won", "lost"], 4: ["won"] * 3}
    for uid, rs in res.items():
        for i, r in enumerate(rs):
            _seed(c, uid, f"g{i}", "CHI", "GB", "2026-10-18", k, "GB")
            c.execute("UPDATE pickem_picks SET result=? WHERE user_id=? AND gid=?", (r, uid, f"g{i}"))
    _seed(c, 1, "old", "CHI", "GB", "2026-09-20", _t(2026, 9, 20, 17), "GB")
    c.execute("UPDATE pickem_picks SET result='won' WHERE gid='old'")
    wk = PK.standings(c, "nfl", "2026-10-13", viewer=3, now=k)
    assert [(r["handle"], r["rank"], r["w"], r["l"], r["p"]) for r in wk["rows"]] == \
        [("bob", 1, 2, 0, 1), ("ann", 2, 2, 1, 0), ("cyd", 2, 2, 1, 0)], "a tie shares the rank"
    assert wk["me"]["handle"] == "cyd" and wk["players"] == 3, "no handle, not on the table"
    season = PK.standings(c, "nfl", None, now=k)
    assert season["rows"][0]["handle"] == "ann" and season["rows"][0]["w"] == 3, "the season counts every week"
    SF.toggle_block(c, 1, "bob")
    assert "bob" not in [r["handle"] for r in PK.standings(c, "nfl", "2026-10-13", viewer=1, now=k)["rows"]]


def test_the_week_keeps_what_the_board_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp)
        c = _conn("ann", "bob")
        PK.pick(c, 1, "nfl", "2026-10-18|GB@CHI", "GB", NOW, d)
        PK.pick(c, 2, "nfl", "2026-10-18|GB@CHI", "CHI", NOW, d)
        PK.pick(c, 2, "nfl", "2026-10-19|BUF@NYJ", "BUF", NOW, d)
        _board(tmp, GAMES[2:])                    # the Sunday game fell off the board
        v = PK.view(c, "nfl", 1, now=NOW, data_dir=d)
        assert [g["gid"] for g in v["games"]] == ["2026-10-18|GB@CHI", "2026-10-19|BUF@NYJ"]
        gb = v["games"][0]
        assert gb["pick"] == "GB" and gb["n_away"] == 1 and gb["n_home"] == 1 and gb["locked"] is False
        assert v["week"] == "2026-10-13" and v["current"] and v["next"] is None and v["prev"] == "2026-10-06"
        assert v["has_handle"] and v["week_table"]["players"] == 2
        past = PK.view(c, "nfl", 1, week="2026-10-06", now=NOW, data_dir=d)
        assert past["games"] == [] and past["next"] == "2026-10-13" and not past["current"]
        assert PK.view(c, "nfl", None, week="junk", now=NOW, data_dir=d)["week"] == "2026-10-13"


def test_the_endpoints_read_only_the_game_and_the_team():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    i = srv.index("def _feed_get(")
    get = srv[i:srv.index("\n    def ", i + 10)]
    assert 'if path == "pickem":' in get and '?mode=ro", uri=True' in get and "PK.grade(conn," in get
    j = srv.index("def _feed_post(")
    post = srv[j:srv.index("\n    def ", j + 10)]
    assert '"pin", "pickem", "pickem-remind", "pickem-group"):' in post
    assert 'PK.pick(conn, uid, txt("sport"), str(body.get("gid") or "")[:80],' in post
    assert post.index('if not who:') < post.index('elif path == "pickem":'), "a pick needs a session"
    c = _conn("ann")
    PK.ensure_tables(c)
    _seed(c, 1, "g", "CHI", "GB", "2026-10-18", _t(2026, 10, 18, 17), "GB")
    assert SF.export_user(c, 1)["pickem"][0]["pick"] == "GB"
    SF.delete_user(c, 1)
    assert c.execute("SELECT COUNT(*) FROM pickem_picks").fetchone()[0] == 0, "the account takes its picks"


def _node(body):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'}[c]));"
              "const ctx = { window: {}, location: { hash: '' }, history: {}, escapeHtml: esc, escapeAttr: esc,"
              " icon: (n) => '<i data-i=\"' + n + '\"></i>', teamMark: (a) => '<b class=\"tm\">' + a + '</b>', leagueMark: () => '',"
              " oddsTxt: String, trueMinus: String, tfToast() {},"
              " sessionStorage: { getItem() { return null; }, setItem() {} }, localStorage: { getItem() { return null; }, setItem() {} },"
              " document: { addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; }, getElementById() { return null; } } };"
              "vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(SOCIAL))}, 'utf8'), ctx);"
              "const S = ctx.window.QBSocial;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_social_draws_the_games_the_split_and_the_tables():
    with tempfile.TemporaryDirectory() as tmp:
        d = _board(tmp)
        c = _conn("ann", "bob")
        PK.pick(c, 1, "nfl", "2026-10-18|GB@CHI", "GB", NOW, d)
        PK.pick(c, 2, "nfl", "2026-10-18|GB@CHI", "GB", NOW, d)
        PK.pick(c, 2, "nfl", "2026-10-19|BUF@NYJ", "NYJ", NOW, d)
        v = PK.view(c, "nfl", 1, now=NOW, data_dir=d)
        out = PK.view(c, "nfl", None, now=NOW, data_dir=d)
    got = _node(f"process.stdout.write(JSON.stringify({{me: S.pickemPageHTML({json.dumps(v)}),"
                f"out: S.pickemPageHTML({json.dumps(out)}), none: S.pickemPageHTML(null)}}));")
    if got is None:
        return
    me = got["me"]
    assert me.count('data-fd="pk-pick"') == 6 and me.count("disabled") == 2, "the played Thursday game is locked"
    assert 'class="fd-pk-team on"' in me and "Your pick" in me and "Locked" in me
    assert "100% GB" in me and "2 picks" in me and "This week · Oct 13 – 19" in me
    assert me.count('class="fd-lead me"') == 2, "you, on the week's table and the season's"
    assert "No entry fee, no prizes" in me and "graded from the final score" in me
    assert "Sign in (free)" in got["out"] and got["out"].count("disabled") == 6, "signed out: look, don't pick"
    assert "did not load" in got["none"]
    src = SOCIAL.read_text(encoding="utf-8")
    assert '["pickem", "#feed/pickem", "trophy", "Pick’em"]' in src and 'if (kind === "pickem") {' in src
    assert 'await api("pickem", { sport: F.pk.sport, gid: d.gid, team: d.team });' in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
