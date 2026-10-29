"""The pick'em, ranked by beating the close (engine/pickem chance, pick,
note_closes, clv_table; js/social.js pickemRankHTML / pickemClvTable).

Ethan's second research paper (2026-10-29): "CLV pick'em: Free weekly
picks, leaderboard ranked by beating the close, not by wins" (Pigskin
Pick'em and Streak). What these hold:

  * a pick keeps the market's chance for its team when it was made (the
    board's two moneylines, margin out); a changed pick takes the new
    team's; the same team again keeps the first;
  * until kickoff each open pick's close follows the market; once the game
    has begun it stays where the last price left it;
  * the table ranks named players by the average move, in points, over
    picks of begun games with both prices, three a week and ten a season to
    be on it, a block hiding both ways and the friends table only friends;
  * the page carries both prices for the viewer's own picks and the
    switch between wins and beating the close.

Run directly: `python3 tests/test_pickem_ranks_by_beating_the_close.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import pickem as PK                                  # noqa: E402

UTC = dt.timezone.utc


def _t(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


NOW = _t(2026, 10, 16, 16)                         # Friday noon, Eastern


def _db(*handles):
    from test_the_weekly_pickem import _conn        # a sibling test's fixtures, imported where used
    c = _conn(*handles)
    PK.ensure_tables(c)
    return c


def _board(games):
    d = Path(tempfile.mkdtemp())
    (d / "recommendations.json").write_text(json.dumps({"games": games}), encoding="utf-8")
    return d


def _game(home="CHI", away="GB", home_ml=-150, away_ml=130, kickoff="2026-10-18T17:00:00Z", date="2026-10-18", **kw):
    return dict({"home": home, "away": away, "date": date, "kickoff": kickoff, "home_ml": home_ml, "away_ml": away_ml}, **kw)


def test_the_market_s_chance_with_the_margin_out():
    g = {"home": "CHI", "away": "GB", "ml": (-150, 130)}
    ph, pa = PK.chance(g, "CHI"), PK.chance(g, "GB")
    assert abs(ph + pa - 1) < 1e-3 and 0.57 < ph < 0.59, (ph, pa)
    assert PK.chance(g, "MIN") is None
    for bad in ((None, 130), (-150, None), (50, 130), ("x", 130)):
        assert PK.chance({"home": "CHI", "away": "GB", "ml": bad}, "CHI") is None, bad


def test_a_pick_keeps_its_price_and_a_change_takes_the_new_one():
    c = _db("abe")
    data = _board([_game()])
    gid = PK.board_games("nfl", data)[0]["gid"]
    assert PK.pick(c, 1, "nfl", gid, "GB", now=NOW, data_dir=data)[0] == 200
    first = c.execute("SELECT p_pick, p_close FROM pickem_picks").fetchone()
    assert first[0] == first[1] and 0.41 < first[0] < 0.43, tuple(first)
    later = _board([_game(home_ml=-120, away_ml=100)])
    PK.pick(c, 1, "nfl", gid, "GB", now=NOW + 60, data_dir=later)
    assert c.execute("SELECT p_pick FROM pickem_picks").fetchone()[0] == first[0], "the same team keeps its moment"
    PK.pick(c, 1, "nfl", gid, "CHI", now=NOW + 120, data_dir=later)
    p = c.execute("SELECT p_pick, p_close FROM pickem_picks").fetchone()
    assert p[0] == p[1] and 0.52 < p[0] < 0.54, "a changed pick is priced again, its close too"
    nolines = _board([_game(home_ml=None, away_ml=None, home="DAL", away="NYG")])
    gid2 = PK.board_games("nfl", nolines)[0]["gid"]
    PK.pick(c, 1, "nfl", gid2, "NYG", now=NOW, data_dir=nolines)
    assert c.execute("SELECT p_pick FROM pickem_picks WHERE gid=?", (gid2,)).fetchone()[0] is None, "no prices, no price"


def test_the_close_follows_the_market_until_kickoff_and_stays():
    c = _db("abe")
    data = _board([_game()])
    gid = PK.board_games("nfl", data)[0]["gid"]
    PK.pick(c, 1, "nfl", gid, "GB", now=NOW, data_dir=data)
    moved = _board([_game(home_ml=-110, away_ml=-110)])
    assert PK.note_closes(c, now=NOW + 3600, data_dir=moved) == 1
    assert abs(c.execute("SELECT p_close FROM pickem_picks").fetchone()[0] - 0.5) < 1e-3
    after = _board([_game(home_ml=-400, away_ml=300)])
    kick = PK._ts("2026-10-18T17:00:00Z")
    assert PK.note_closes(c, now=kick + 60, data_dir=after) == 0, "begun: the close stands"
    assert abs(c.execute("SELECT p_close FROM pickem_picks").fetchone()[0] - 0.5) < 1e-3


def _seed(c, uid, gid, kickoff, p_pick, p_close, sport="nfl"):
    c.execute("INSERT INTO pickem_picks (user_id, sport, week, gid, home, away, game_date, kickoff, pick, created_at, "
              "updated_at, p_pick, p_close) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (uid, sport, PK.week_of(kickoff), gid, "CHI", "GB", "2026-10-18", kickoff, "GB", kickoff - 99,
               kickoff - 99, p_pick, p_close))


def test_the_table_ranks_by_the_average_move():
    from engine import socialfeed as SF
    c = _db("abe", "bea", "cal", "dan")
    k = _t(2026, 10, 18, 17)
    for i in range(3):
        _seed(c, 1, f"a{i}", k, 0.40, 0.45)              # abe: +5 every time
        _seed(c, 2, f"b{i}", k, 0.50, 0.48 if i else 0.60)   # bea: +10, -2, -2 → +2
        _seed(c, 4, f"d{i}", k, 0.30, 0.10)              # dan: -20
    _seed(c, 3, "c0", k, 0.40, 0.90)                     # cal: one pick only
    _seed(c, 1, "late", _t(2026, 10, 19, 17), 0.30, 0.90)   # not begun yet: not counted
    t = PK.clv_table(c, "nfl", PK.week_of(k), viewer=2, now=_t(2026, 10, 18, 20))
    rows = [(r["handle"], r["clv"], r["n"], r["beat"], r["rank"]) for r in t["rows"]]
    assert rows == [("abe", 5.0, 3, 3, 1), ("bea", 2.0, 3, 1, 2), ("dan", -20.0, 3, 0, 3)], rows
    assert t["me"]["handle"] == "bea" and t["min"] == PK.CLV_MIN_WEEK
    assert all(r["handle"] != "cal" for r in t["rows"]), "one pick is not a table"
    season = PK.clv_table(c, "nfl", None, now=_t(2026, 10, 18, 20))
    assert season["rows"] == [] and season["min"] == PK.CLV_MIN_SEASON, "ten a season"
    friends = PK.clv_table(c, "nfl", PK.week_of(k), viewer=2, now=_t(2026, 10, 18, 20), only={2, 4})
    assert [r["handle"] for r in friends["rows"]] == ["bea", "dan"]
    SF.ensure_tables(c)
    c.execute("INSERT INTO feed_blocks (user_id, blocked_id, created_at) VALUES (2, 1, 0)")
    hidden = PK.clv_table(c, "nfl", PK.week_of(k), viewer=2, now=_t(2026, 10, 18, 20))
    assert [r["handle"] for r in hidden["rows"]] == ["bea", "dan"], "a block hides both ways"


def test_the_page_carries_the_prices_and_the_switch():
    c = _db("abe")
    data = _board([_game()])
    gid = PK.board_games("nfl", data)[0]["gid"]
    PK.pick(c, 1, "nfl", gid, "GB", now=NOW, data_dir=data)
    v = PK.view(c, "nfl", viewer=1, now=NOW, data_dir=data)
    g = v["games"][0]
    assert g["pick"] == "GB" and g["p_pick"] and g["p_close"] == g["p_pick"]
    for k in ("week_clv", "season_clv", "week_clv_friends", "season_clv_friends"):
        assert k in v, k
    soc = (ROOT / "web" / "js" / "social.js").read_text(encoding="utf-8")
    assert 'data-fd="pk-rank"' in soc and 'if (act === "pk-rank")' in soc
    assert "pickemClvTable(tbl(1, 1)," in soc and '(fr ? "clv_friends" : "clv")' in soc
    assert "when you picked" in soc and "Ranked by beating the close" in soc
    pm = (ROOT / "engine" / "pushmine.py").read_text(encoding="utf-8")
    assert "_pk.note_closes(conn, now=t, data_dir=Path(web) / \"data\")" in pm


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
