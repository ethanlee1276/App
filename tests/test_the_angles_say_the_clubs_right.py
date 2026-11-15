"""The angles say each club the way the rest of the report does (2026-11-15).

Ethan's screenshot of "The angles" on a Patriots–Lions report: "Lions gives
up", "Lions's coverage", "Lions blitzes", "against Lions in its last 3
games", "Patriots runs on 55% of its red-zone plays" and "R.Stevenson has 6
of its red-zone carries". engine/angles wrote its sentences for a team code
and dropped the nickname in. Now each club is said through the report's own
helpers (gamereport.team_np, team_owner, _many): "the Lions give up", "the
Lions' coverage", "the Patriots run on 55% of their red-zone plays", a
school stays singular ("Indiana gives up … its"), and the play-by-play's
short name is the box score's full one. A red-zone man the injury report
names is not where to look: the next one is.

    python3 tests/test_the_angles_say_the_clubs_right.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import angles as A                       # noqa: E402


def _db(off="NE", dfn="DET"):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")

    def put(player, team, opp, pos, week, **m):
        for k, v in m.items():
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl',2099,?,?,?,?,?,?,1,?,?)",
                         (f"{week:03d}", f"{team}-{week:03d}", player, team, opp, pos, k, v))
    # The defence: top receivers, tight ends and quarterbacks all ran up numbers on it.
    for w, team in enumerate(("AAA", "BBB", "CCC", "DDD"), 1):
        put(f"{team} Wr", team, dfn, "WR", w, targets=11, receptions=8, rec_yds=112 - w, rec_td=1)
        put(f"{team} Te", team, dfn, "TE", w, targets=7, receptions=6, rec_yds=70, rec_td=1)
        put(f"{team} Qb", team, dfn, "QB", w, rush_yds=40 + w, rush_att=6)
    # Two stingy defences, so the ranks mean something.
    for w in range(1, 5):
        for d in ("KKK", "LLL"):
            put(f"{d} Opp Wr", f"O{d}", d, "WR", w, targets=12, receptions=3, rec_yds=25, rec_td=0)
            put(f"{d} Opp Te", f"O{d}", d, "TE", w, targets=3, receptions=1, rec_yds=8, rec_td=0)
            put(f"{d} Opp Qb", f"O{d}", d, "QB", w, rush_yds=2, rush_att=1)
    # The offence's red zone, in its other games: the play-by-play's short
    # names, and the box score's full ones for the same men.
    for w in range(5, 9):
        put("R.Stevenson", off, "XXX", "RB", w, rz_car=3, rz_tgt=0, i5_car=1)
        put("Rhamondre Stevenson", off, "XXX", "RB", w, carries=14, rush_yds=60)
        put("T.Henderson", off, "XXX", "RB", w, rz_car=1, rz_tgt=1)
        put("TreVeyon Henderson", off, "XXX", "RB", w, carries=6, rush_yds=30)
        put("Stefon Diggs", off, "XXX", "WR", w, targets=9, receptions=6, rec_yds=70, rz_tgt=1)
    conn.commit()
    return conn


class _Ctx:
    sport = "nfl"

    def __init__(self, tables, names=None, injuries=(), off="NE", dfn="DET"):
        self.teams = (off, dfn)
        self.opp = {off: dfn, dfn: off}
        self.angle_tables = tables
        self._names = names or {"NE": "Patriots", "DET": "Lions"}
        self.reads = [
            {"player": "Stefon Diggs", "team": off, "pos": "WR", "usage": {"tgt_share": 0.28}},
            {"player": "Hunter Henry", "team": off, "pos": "TE", "usage": {"tgt_share": 0.18}},
            {"player": "Drake Maye", "team": off, "pos": "QB", "usage": {"rush_yds_pg": 31.0}}]
        self.scan = {"injuries": list(injuries), "charting": {
            "defense": {dfn: {"blitz_rate": 0.41}},
            "defense_weeks": {dfn: [{"week": 6, "opp": off, "dropbacks": 40, "blitz": 18}]}}}

    def name(self, t):
        return self._names.get(t, t)

    def poss(self, t):
        n = self.name(t)
        return f"{n}'" if n.endswith("s") else f"{n}'s"


def _texts(ctx):
    return {(r["player"], r["points_to"]): r["text"] for r in A.for_game(ctx, ctx.angle_tables)}


def test_a_plural_nickname_takes_a_plural_verb_and_its_own_possessive():
    t = _texts(_Ctx(A.nfl_tables(_db(), 2099, before_week=10)))
    wr = t[("Stefon Diggs", "catches and yards")]
    assert "against the Lions' coverage of No. 1 receivers: the Lions give up" in wr, wr
    assert "to the top receiver they face (" in wr, wr
    te = t[("Hunter Henry", "catches, yards and a touchdown")]
    assert "against the Lions' tight-end coverage: the Lions give up" in te, te
    qb = t[("Drake Maye", "rushing yards")]
    assert "the Lions blitz on 41% of dropbacks this season" in qb, qb
    assert "45% of the Patriots' dropbacks when they met in week 6" in qb, qb
    assert "yards against the Lions in their last 3 games" in qb, qb
    rz = t[("Rhamondre Stevenson", "a touchdown")]
    assert rz.startswith("The Patriots run on "), rz
    assert "of their red-zone plays" in rz and "12 of their red-zone carries (4 inside the 5)" in rz, rz
    assert "of their red-zone touches" in rz, rz
    every = " ".join(t.values())
    for bad in ("Lions gives", "Lions's", "Lions blitzes", "Patriots runs", "Patriots's", " its ",
                "against Lions", "R.Stevenson"):
        assert bad not in every, bad


def test_the_play_by_plays_short_name_is_the_box_scores_full_one():
    rz = A.nfl_tables(_db(), 2099, before_week=10)["rz"]["NE"]
    names = [x["player"] for x in rz["top"]]
    assert names[0] == "Rhamondre Stevenson" and "R.Stevenson" not in names, names
    assert rz["top"][0]["car"] == 12 and rz["top"][0]["i5"] == 4
    assert "TreVeyon Henderson" in names, names


def test_a_red_zone_man_the_injury_report_names_is_not_where_to_look():
    ctx = _Ctx(A.nfl_tables(_db(), 2099, before_week=10),
               injuries=[{"player": "Rhamondre Stevenson", "team": "NE", "status": "Out"}])
    t = _texts(ctx)
    assert not any(p == "Rhamondre Stevenson" for p, _ in t), list(t)
    rz = next(v for (p, k), v in t.items() if k == "a touchdown")
    assert "Stevenson" not in rz, rz


def test_a_school_is_one_club_and_its_own():
    ctx = _Ctx(A.nfl_tables(_db("IU", "OSU"), 2099, before_week=10),
               names={"IU": "Indiana", "OSU": "Ohio State"}, off="IU", dfn="OSU")
    ctx.sport = "cfb"
    t = _texts(ctx)
    wr = t[("Stefon Diggs", "catches and yards")]
    assert "against Ohio State's coverage of No. 1 receivers: Ohio State gives up" in wr, wr
    assert "to the top receiver it faces (" in wr, wr
    rz = next(v for (p, k), v in t.items() if k == "a touchdown")
    assert rz.startswith("Indiana runs on ") and "of its red-zone plays" in rz, rz


def test_a_context_without_the_reports_helpers_still_reads():
    class Bare(_Ctx):
        sport = None

        def poss(self, t):
            raise AttributeError("no possessive")
    t = _texts(Bare(A.nfl_tables(_db(), 2099, before_week=10)))
    assert t, "the angles survive a context the report's helpers cannot read"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
