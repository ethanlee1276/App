"""NHL line combinations: forward lines and defence pairs off shared ice.

Ethan, 2026-10-03: "do all of them" — line combinations among them.
Checks, one rule each: a shift chart reads into absolute seconds per player
(goal and penalty rows are not shifts); two players' overlap is counted to
the second; the three forwards who share the most ice are a line and the
two defencemen a pair, never mixing the two; a player we have no position
for is left off; the board reads each team's newest charts from the games
it stored (a chart that will not load costs only that team's lines); a row
says its line; two linemates' scoring legs read their shared shifts in a
ticket; the team page carries the lines.

Run directly: `python3 tests/test_nhl_lines.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                             # noqa: E402
from engine import parlays as P                                   # noqa: E402
from engine.nhl import lines as LN                                # noqa: E402
from engine.sources import nhlshifts as SH                        # noqa: E402

POS = {"C1": "C", "L1": "L", "R1": "R", "C2": "C", "L2": "L", "R2": "R",
       "D1": "D", "D2": "D", "D3": "D", "D4": "D", "G1": "G", "Ghost": ""}


def _chart():
    rows = []
    def shift(name, per, a, b, team="EDM", code=517):
        first, last = name[0], name[1:]
        rows.append({"firstName": first, "lastName": last, "teamAbbrev": team, "period": per,
                     "startTime": a, "endTime": b, "typeCode": code})
    for per in (1, 2, 3):
        for a, b in (("00:00", "00:45"), ("02:00", "02:45")):
            for n in ("C1", "L1", "R1", "D1", "D2"):
                shift(n, per, a, b)
        for a, b in (("00:45", "01:30"), ("02:45", "03:30")):
            for n in ("C2", "L2", "R2", "D3", "D4"):
                shift(n, per, a, b)
    shift("G1", 1, "00:00", "20:00")
    shift("C1", 1, "05:00", "05:10", code=505)            # a goal event, not a shift
    shift("Ghost", 1, "00:00", "00:45")
    shift("X9", 1, "00:00", "00:30", team="CGY")
    return {"data": rows}


def _shifts(chart):
    # first letter as first name, the rest as last — "C 1" for "C1"
    return {t: {n.replace(" ", ""): v for n, v in d.items()} for t, d in SH.parse_shifts(chart).items()}


def test_a_chart_reads_into_absolute_seconds_and_drops_events():
    sh = _shifts(_chart())
    assert sh["EDM"]["C1"][0] == (0, 45) and sh["EDM"]["C1"][2] == (1200, 1245), "period two starts at 1,200"
    assert len(sh["EDM"]["C1"]) == 6, "the goal event is not a shift"
    assert "CGY" in sh and SH.parse_shifts({}) == {}


def test_overlap_is_counted_to_the_second():
    assert LN.overlap([(0, 45), (100, 150)], [(30, 120)]) == 15 + 20
    assert LN.overlap([(0, 10)], [(10, 20)]) == 0


def test_the_lines_and_pairs_come_from_who_shares_the_ice():
    sh = _shifts(_chart())["EDM"]
    got = LN.build([sh], POS)
    f = [sorted(g["players"]) for g in got["forwards"]]
    d = [sorted(g["players"]) for g in got["defence"]]
    assert sorted(["C1", "L1", "R1"]) in f and sorted(["C2", "L2", "R2"]) in f
    assert sorted(["D1", "D2"]) in d and sorted(["D3", "D4"]) in d
    assert all("G1" not in g and "Ghost" not in g for g in f + d), "no goalie, no unknown position"
    assert got["forwards"][0]["together"] == 1.0
    slot = LN.slot_of(got, "L1")
    assert slot["unit"] == "F1" and sorted(slot["mates"]) == ["C1", "R1"]
    assert LN.slot_of(got, "Nobody") is None


def test_the_board_reads_each_teams_newest_charts():
    import nhl_build as B
    conn = db.connect(Path(tempfile.mkdtemp()) / "h.db")
    db.upsert_games(conn, [
        {"sport": "nhl", "season": 2025, "period": d, "game_id": f"CGY@EDM{d}", "home": "EDM", "away": "CGY",
         "home_score": 3, "away_score": 2, "date": d, "extra": json.dumps({"nhl_id": gid})}
        for d, gid in (("2025-10-28", 11), ("2025-10-29", 12), ("2025-10-30", 13))])
    asked = []
    def fetch(gid):
        asked.append(gid)
        if gid == 12:
            from engine.sources.fetch import DataUnavailable
            raise DataUnavailable("no chart")
        return _chart()
    # The chart names read "C 1" (first name "C", last name "1").
    players = {f"{n[0]} {n[1:]}": {"position": v} for n, v in POS.items()}
    got = B.team_lines(conn, ["EDM"], players, fetch=fetch)
    assert asked == [13, 12], "the two newest finals, newest first"
    assert got["EDM"]["games"] == 1, "the chart that would not load costs only itself"
    assert B.team_lines(conn, ["VAN"], players, fetch=fetch) == {}


def test_linemates_read_their_shared_shifts_in_a_ticket():
    a = dict(player="C1", market="points", team="EDM", opponent="CGY", side="OVER", game_date="d", line_unit="EDM-F1")
    b = dict(a, player="L1")
    c = dict(a, player="C2", line_unit="EDM-F2")
    assert P.relate("nhl", a, b).rho == 0.30
    assert P.relate("nhl", a, c).rho == 0.20, "teammates on different lines read the team rate"


def test_rows_and_the_team_page_carry_the_lines():
    src = open(os.path.join(ROOT, "nhl_build.py"), encoding="utf-8").read()
    assert 'r["line_unit"] = f"{r[\'team\']}-{slot[\'unit\']}"' in src and "save_lines(" in src
    srv = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert 'nhl_lines.json' in srv and 'depth["lines"] = got' in srv
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function teamLinesHTML(ln)" in js and "teamLinesHTML(pub && pub.lines)" in js


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
