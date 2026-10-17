"""Hockey's three: the goalie board, the line matchups, and the live xG race.

Ethan, 2026-10-15, three of the sixteen ideas he asked to have built ("do
every one for every sport"): an NHL goalie board, line matchups with each
line's and pair's xGF and xGA, and a live xG race. Context, all of it: the
board already prices the goalie, and a line's on-ice record over two games
is a handful of attempts, so nothing here moves a number.

What these hold: a unit is credited with an even-strength attempt only
when every one of its men was on the ice for it (a shift ending on the
second counts, one starting on it does not), power plays and empty nets
left out, the team's and the opponent's shots kept apart; the build adds
the record only when the shot model is fitted and a play-by-play that will
not load costs only its own game; each shot keeps its second; the goalie
board reads the tape (with how sure the start is); and the live page's
flow pane races expected goals with the game's biggest chance named.

Run directly: `python3 tests/test_hockey_goalies_lines_and_the_xg_race.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import nhl_build                                                 # noqa: E402
from engine.nhl import lineimpact as LI                          # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"
RINK = (ROOT / "web" / "js" / "rinkcast.js").read_text(encoding="utf-8")

CHART = {"C1": [(0, 45), (120, 165)], "L1": [(0, 45), (120, 165)], "R1": [(0, 45), (120, 160)],
         "D1": [(0, 45)], "D2": [(0, 45)], "C2": [(45, 90)]}
LINE = {"players": ["C1", "L1", "R1"], "together": 0.9}
PAIR = {"players": ["D1", "D2"], "together": 0.8}


def _shot(t, team="EDM", xg=0.1, kind="sog", strength="EV", empty=0):
    return {"t": t, "team": team, "kind": kind, "strength": strength, "empty_net": empty, "xg": xg}


def price(s):
    return s["xg"]


def test_a_unit_is_credited_only_with_every_man_on():
    assert LI.on_ice(CHART, ["C1", "L1"], 45), "a shift ending on the second counts"
    assert not LI.on_ice(CHART, ["C2"], 45), "one starting on it does not"
    assert not LI.on_ice(CHART, ["C1", "R1"], 163), "R1 was off by then"
    assert not LI.on_ice(CHART, ["C1", "Nobody"], 10)
    shots = [_shot(10, xg=0.2), _shot(20, team="CGY", xg=0.3), _shot(30, kind="goal", xg=0.4),
             _shot(140, xg=0.05), _shot(163, xg=0.5),                       # R1 off: not the line's
             _shot(40, kind="block", xg=0.9),                               # blocked: not priced
             _shot(41, strength="PP", xg=0.9), _shot(42, empty=1, xg=0.9),  # power play, empty net
             _shot(50, xg=0.7), {"team": "EDM", "kind": "sog", "strength": "EV", "empty_net": 0, "xg": 1.0}]
    line, pair = LI.unit_xg([LINE, PAIR], [(CHART, shots)], "EDM", price)
    assert line["xgf"] == 0.65 and line["att_for"] == 3, line          # 0.2 + 0.4 + 0.05
    assert line["xga"] == 0.3 and line["att_against"] == 1
    assert line["xgf_pct"] == round(0.65 / 0.95, 3) and line["games"] == 1
    assert pair["xgf"] == 0.6 and pair["att_for"] == 2, pair            # 0.2 + 0.4, the pair's shift ends at 45
    assert line["players"] == LINE["players"] and line["together"] == 0.9, "the unit keeps what it was"
    empty = LI.unit_xg([LINE], [(None, shots), ({}, shots)], "EDM", price)[0]
    assert empty["xgf"] == 0 and empty["xgf_pct"] is None and empty["games"] == 0


def test_the_build_adds_the_record_only_with_a_fitted_model():
    lines = {"forwards": [LINE], "defence": [PAIR], "games": 1}
    payloads = {11: {"ok": 1}, 12: None}
    from engine.sources import nhlpbp
    from engine.sources.fetch import DataUnavailable

    def fetch(gid):
        if payloads[gid] is None:
            raise DataUnavailable("no play-by-play")
        return payloads[gid]
    real = nhlpbp.parse_shots
    nhlpbp.parse_shots = lambda payload, *a, **k: [_shot(10, xg=0.2), _shot(20, team="CGY", xg=0.3)]
    try:
        got = nhl_build._line_xg(lines, [(11, CHART), (12, CHART)], "EDM", price, pbp_fetch=fetch)
    finally:
        nhlpbp.parse_shots = real
    f = got["forwards"][0]
    assert f["xgf"] == 0.2 and f["xga"] == 0.3 and f["games"] == 2, "the game that would not load costs only its shots"
    assert got["xg_games"] == 2 and got["games"] == 1
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert "price=(lambda s: X.xg(_xm, s)) if _xm else None)" in src
    assert "if price is not None:\n                out[team] = _line_xg(" in src


def test_every_shot_keeps_its_second():
    import test_nhl_shots_and_xg as T
    from engine.sources import nhlpbp
    rows = nhlpbp.parse_shots(T.PBP, "2025-10-30", 2025)
    assert rows and all(isinstance(r["t"], int) for r in rows)
    assert all((r["period"] - 1) * 1200 <= r["t"] <= r["period"] * 1200 for r in rows)
    from engine import db
    assert "t" not in db.NHL_SHOT_COLS, "the stored table is unchanged; the second rides only in memory"


def test_the_tape_says_how_sure_the_start_is():
    from engine.nhl import scan
    teams = {"EDM": {"gf": 3.4, "ga": 2.9}, "CGY": {"gf": 2.8, "ga": 3.1}}
    ctx = {"EDM": {"starter": "Stuart Skinner", "starter_sure": False, "starter_source": "recent starts", "b2b": True},
           "CGY": {"starter": "Dustin Wolf", "starter_sure": True, "starter_source": "confirmed"}}
    t = scan.tape("EDM", "CGY", teams, ctx)
    assert t["sides"]["EDM"]["starter_source"] == "recent starts" and t["sides"]["CGY"]["starter_source"] == "confirmed"


def _node(body: str):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx);"
              "const X = ctx.window.QBExtras;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _side(starter, gsax, src, sure=True, b2b=False, xg=3.0):
    return {"starter": starter, "starter_sv": 0.91, "starter_gsax": gsax, "starter_share": 0.7,
            "starter_sure": sure, "starter_source": src, "b2b": b2b, "xg": xg}


def test_the_goalie_board_and_the_lines_card():
    board = {"games": [{"home": "BOS", "away": "NYR", "nhl_tape": {"sides": {
                "BOS": _side("Jeremy Swayman", 4.2, "confirmed", xg=3.1), "NYR": _side("Igor Shesterkin", 7.9, "probable", xg=2.7)}}},
                       {"home": "EDM", "away": "CGY", "nhl_tape": {"sides": {
                "EDM": _side("Stuart Skinner", None, "recent starts", sure=False, b2b=True), "CGY": _side("Dustin Wolf", -1.0, "confirmed")}}},
                       {"home": "SEA", "away": "VAN"}],
             "lines": {"EDM": {"forwards": [dict(LINE, xgf=1.4, xga=0.6, xgf_pct=0.7, att_for=18, att_against=9)],
                               "defence": []}}}
    got = _node(f"const b = {json.dumps(board)};"
                "process.stdout.write(JSON.stringify({g: X.goalies(b), html: X.goaliesHTML(b), lines: X.linesHTML(b),"
                "none: X.goaliesHTML({}), nolines: X.linesHTML({games: b.games})}));")
    if got is None:
        return
    order = [r["goalie"] for r in got["g"]]
    assert order == ["Igor Shesterkin", "Jeremy Swayman", "Dustin Wolf", "Stuart Skinner"], order
    nyr = got["g"][0]
    assert nyr["faces"] == 3.1 and nyr["opp"] == "BOS" and nyr["home"] is False
    html = got["html"]
    assert "Probable" in html and "Confirmed" in html and "Our guess" in html and "B2B" in html
    assert "+7.9" in html and ".910" in html
    assert "CGY @ EDM" in got["lines"] and "70%" in got["lines"] and "C1 · L1 · R1" in got["lines"]
    assert "Context only, and small" in got["lines"]
    assert "No starters on the board yet" in got["none"] and "No lines read yet" in got["nolines"]
    js = EXTRAS.read_text(encoding="utf-8")
    # 2026-10-15: the parlay builder (step 126) joins every board sport's Toolbox after these two.
    assert "nhl: [goaliesHTML, linesHTML, builderHTML]" in js


def test_the_live_flow_races_expected_goals():
    assert "flowBy: \"att\"" in RINK and 'data-rc-flow="xg">xG race</button>' in RINK
    assert "if (ds.rcFlow) S.flowBy = ds.rcFlow;" in RINK and "[data-rc-flow]" in RINK
    i = RINK.index("function flow(d)")
    body = RINK[i:RINK.index("\n  }\n", i)]
    assert "xa += x" in body and "xh += x" in body and "best = { xg: x, e, side: s }" in body
    assert "Biggest chance:" in RINK
    # Only when the game's attempts are priced: a page without our model keeps the attempt race alone.
    assert "const has = !!(d.rink || {}).xg;" in RINK and 'S.flowBy === "xg" && (d.rink || {}).xg' in RINK


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
