"""The Edge page's two lists pick the same best row in each market.

Audit V-7 / roadmap #48. "Every market, the best we have" took the
highest GRADE in each market and printed its edge in points; the Edge
Board under it sorted by EV and kept rows the model grades 0 as its own
error. On the audited slate the box's best Total read "+1.2%" (an Under
49 whose EV was −2.3%) while the board listed "Over 43 · +5.8% EV", a
row the model calls not credible. Same page, same market, two answers,
and "+1.2%" (points) typeset exactly like "+5.8% EV" (per cent).

Pinned here:
  * one candidate filter (`edgeCandidate`) and one order (`edgeOrder`)
    serve both lists, so a market's best row is the board's top row for it;
  * a not-credible row is on neither list;
  * the box prints "EV ±x%" coloured by its sign, and the edge as
    "edge ±y pts", and names the game.

Run directly: `python3 tests/test_the_edge_page_agrees_with_itself.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


def _game(label, bet_type, q, ev, edge, credible=True, grade="Lean"):
    return {"pick_label": label, "bet_type": bet_type, "market": bet_type, "odds": -110,
            "quality": q, "credible": credible, "ev_per_unit": ev, "edge": edge,
            "grade": grade, "matchup": "CHI @ DET", "home": "DET", "away": "CHI"}


def _prop(player, q, ev, edge, credible=None):
    return {"player": player, "market": "rec_yds", "market_label": "Rec Yds", "side": "OVER",
            "line": 50.5, "odds": -110, "quality": q, "credible": credible,
            "ev_per_unit": ev, "edge": edge, "grade": "Lean", "team": "DET", "opponent": "CHI"}


# The audited slate's shape: a high-grade negative-EV Under, a not-credible
# Over carrying the biggest EV, and a credible positive-EV Under.
SLATE = {
    "game_bets": [
        _game("Under 49", "total", 48, -0.023, 0.0118),
        _game("Over 43", "total", 0, 0.058, 0.054, credible=False),
        _game("Under 47", "total", 40, 0.031, 0.022),
        _game("CHI +6.5", "spread", 0, 0.055, 0.0526, credible=False),
        _game("DET -6.5", "spread", 60, 0.012, 0.008),
    ],
    "recommendations": [
        _prop("High Grade", 70, 0.009, 0.020),
        _prop("Best Price", 52, 0.044, 0.031),
        _prop("Not Credible", 0, 0.090, 0.080, credible=False),
    ],
}


def _run():
    if not shutil.which("node"):
        return None
    body = "\n".join(_fn(n) for n in (
        "edgeCandidate", "edgeOrder", "marketRank", "marketBest", "betLabelKey",
        "edgePropRow", "edgeBoardRows"))
    order = re.search(r"const MARKET_ORDER = \[.*?\];", APP, re.S).group(0)
    harness = f"""
const slugify = (x) => String(x || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
const gameBetId = (r) => r.pick_label;
const rowStarted = () => false, gameBetSeries = () => null, passesGameBet = () => false,
      gameBetAttrs = () => "", leagueMark = () => "", teamMark = () => "",
      passesFilters = () => false, propAttrs = () => "", betMark = () => "",
      teamName = (t) => t;
const state = {{ sport: "nfl", maxJuice: -10000, data: JSON.parse(process.argv[2]) }};
{order}
{body}
const sig = {{ props: [], sharpBets: [], modelBets: [] }};
process.stdout.write(JSON.stringify({{
  best: marketBest(sig).map((r) => r.pick_label || r.player),
  board: edgeBoardRows().map((r) => r.label),
}}));
"""
    path = os.path.join(tempfile.mkdtemp(), "e.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    out = subprocess.run(["node", path, json.dumps(SLATE)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_each_market_s_best_row_is_the_board_s_top_row_for_it():
    got = _run()
    if got is None:
        return
    best, board = got["best"], got["board"]
    assert best == ["DET -6.5", "Under 47", "Best Price"], best   # MARKET_ORDER
    # The board's first total and first prop are the box's picks.
    totals = [x for x in board if x.startswith(("Under", "Over"))]
    props = [x for x in board if "Rec Yds" in x]
    assert totals[0] == "Under 47", board
    assert props[0].startswith("Best Price"), board


def test_a_not_credible_row_is_on_neither_list():
    got = _run()
    if got is None:
        return
    for name in ("Over 43", "CHI +6.5", "Not Credible"):
        assert not any(name in x for x in got["best"] + got["board"]), (name, got)


def test_both_lists_share_one_filter_and_one_order():
    board = _fn("edgeBoardRows")
    assert "edgeCandidate(r)" in board and "edgeCandidate(b)" in board
    assert ".sort(edgeOrder)" in board
    best = _fn("marketBest")
    assert "edgeCandidate(r)" in best and "edgeOrder(r, cur)" in best
    assert "quality" not in best.split("const cur")[1], \
        "the box ranks by grade again; the board ranks by EV"


def test_the_box_names_ev_and_edge_apart_and_colours_by_sign():
    html = _fn("marketBestHTML")
    assert "EV ${signedPct(ev)}" in html
    assert "pts`" in html, "the edge in points is labelled as points"
    assert 'ev > 0 ? "var(--good)" : ev < 0 ? "var(--bad)"' in html
    assert "r.matchup" in html and "teamName(r.opponent)" in html, "the row names its game"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
