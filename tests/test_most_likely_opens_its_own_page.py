"""A Most Likely pick opens the pick page in its own terms, explained.

Ethan, 2026-09-23, from the phone's Most Likely shelves: "What I wanna fix
now is giving explanations for the most likely picks too. When I click on
them it just shows charts, it doesn't show the page we show when you click
on edge bets."

The tap did reach the pick page — the edge board's reading of it: "Edge
+0.0%", a grade, the edge row's 66% instead of the 71% on the row, and the
first explanation under the charts, opening "No credible market edge".
Now the row opens the page as ITS pick (side, line, book, price, chance),
"Why it’s likely" leads, the chart reads against that line with the chance
and tier in place of EV and confidence, and the edge board's price
refusals and gates stay on the edge board. The address says so
(#pick/<slug>/likely), so a refresh or a shared link keeps it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _const(src, name):
    i = src.index(f"const {name} =")
    return src[i:src.index(";\n", i) + 2]


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PROP = {"player": "Garrett Wilson", "market": "rec_yds", "market_label": "Receiving Yards",
        "side": "OVER", "line": 49.5, "odds": -150, "book": "DraftKings", "projection": 58.2,
        "logs": [{"week": w, "opponent": o, "value": v, **({"partial": True, "snaps": .39} if o == "CLE" else {})}
                 for w, o, v in ((2, "GB", 57), (1, "TEN", 79), (10, "CLE", 0), (6, "DEN", 13), (5, "DAL", 71),
                                 (4, "MIA", 82), (3, "TB", 84), (2, "BUF", 50), (1, "PIT", 95))],
        "chain": {"base": {"value": 53.8}, "mean": 58.2, "steps": [
            {"key": "matchup", "label": "Matchup", "mult": 1.0815,
             "why": "Soft matchup — DET allow the 2nd-most passing yards (329 a game) (×1.05); Game script: "
                    "6.5-pt underdog (×1.03)"},
            {"key": "weather", "label": "Weather", "mult": 1.0, "why": "Dome game"}]}}
LIKELY = {"kind": "prop", "player": "Garrett Wilson", "market": "rec_yds", "side": "OVER", "line": 49.5,
          "book": "DraftKings", "odds": -150, "model_prob": 0.71, "implied_prob": 0.58, "rung": "main"}


def _why(prop, likely, data=None):
    prog = ("const state = " + json.dumps({"data": data or {}}) + ";\n"
            + _fn(APP, "escapeHtml") + "const oddsTxt = (o) => (o > 0 ? '+' : '') + o;\n"
            + _const(APP, "wholePct") + _fn(APP, "probTier") + _fn(APP, "whyLikelyHTML")
            # every bet's section shares its shell and its held line (2026-09-24)
            + _fn(APP, "whySectionHTML") + _fn(APP, "whyHeldItem") + _fn(APP, "whyBoardOf")
            + _fn(APP, "impliedOf") + _const(APP, "WHY_SCORER")
            # the "On the board" line (test_most_likely_holds_its_picks.py)
            + _const(APP, "LIKELY_NEW_MIN") + _fn(APP, "likelyWhen") + _fn(APP, "likelyHeld")
            # the game-script line (tests/test_game_scripts.py) is its own test
            + "const scriptWhyItem = () => null;\n"
            + "const pickScanRead = () => null; const scanWhyList = () => \"\";\n"
            + "const tzOpts = (o) => Object.assign({timeZone: 'America/New_York'}, o);\n"
            + "const tzTime = (d) => new Date(d).toLocaleTimeString('en-US', tzOpts({hour: 'numeric', minute: '2-digit'}));\n"
            + f"\nconst r = {json.dumps(prop)}, lk = {json.dumps(likely)};\n"
            + "const v = lk.line != null ? {...r, side: lk.side, line: lk.line, odds: lk.odds, book: lk.book} : r;\n"
            + "console.log(JSON.stringify(whyLikelyHTML(v, r, lk)));")
    got = _node(prog)
    return None if got is None else " ".join(got.split())


def test_the_card_explains_the_pick_from_the_row_itself():
    got = _why(PROP, LIKELY)
    if got is None:
        print("  SKIP node not installed")
        return
    assert "Why it’s likely" in got
    assert "71% — Top, the 68% or more band" in got
    assert "We have him at 58.2 receiving yards — 8.7 above the 49.5 line." in got
    assert "Over 49.5 in 7 of his last 9 — one was a game he left early, and it is one of the misses." in got
    assert "Matchup +8%</b> — Soft matchup — DET allow the 2nd-most passing yards (329 a game) (×1.05); " \
           "Game script: 6.5-pt underdog (×1.03)" in got, "the whole reason, so +8% adds up"
    assert "Weather" not in got, "a step that moved nothing is not a reason"
    assert "DraftKings -150 implies 58%; we have it at 71%." in got
    assert "Whether the price is worth paying is the Edge board’s question." in got


def test_an_alternate_line_says_which_number_it_stands_beside():
    rung = dict(LIKELY, line=39.5, odds=-235, book="BetRivers", rung="alt", main_line=49.5,
                main_side="OVER", main_odds=-150)
    got = _why(PROP, rung)
    if got is None:
        return
    assert "We have him at 58.2 receiving yards — 18.7 above the 39.5 line." in got
    assert "An alternate line: the book’s main number is over 49.5 at -150" in got


def test_a_scorer_and_a_thin_player_read_right():
    td = {"player": "Kenneth Walker III", "market": "anytime_td", "side": "OVER", "line": 0.5, "odds": -220,
          "logs": [{"week": w, "opponent": "X", "value": v} for w, v in ((3, 1), (2, 0), (1, 2), (17, 1))]}
    got = _why(td, {"kind": "td", "player": "Kenneth Walker III", "market": "anytime_td", "side": "yes",
                    "line": None, "book": "FanDuel", "odds": -220, "model_prob": 0.68, "implied_prob": 0.66})
    if got is None:
        return
    assert "Scored in 3 of his last 4" in got and "We have him at" not in got
    thin = _why(PROP, LIKELY, data={"thin": {"Garrett Wilson": {"games": 2}}})
    assert "only 2 games this season to go on — shown, not staked" in thin


def test_the_price_refusals_stay_on_the_edge_board():
    from engine import betting as B
    prog = (_const(APP, "EDGE_ONLY_REASON").replace("const EDGE_ONLY_REASON", "const R")
            + f"\nconsole.log(JSON.stringify({json.dumps(list(B.REFUSAL_REASONS))}.map((x) => R.test(x))"
            + " .concat([R.test('Edge +1.2% is under the Tier 2 bar (4.0% post-haircut) — pass, not a lean'),"
            + " R.test('Soft matchup — DET allow the 2nd-most passing yards'), R.test('Dome game')])));")
    got = _node(prog)
    if got is None:
        return
    assert got == [True] * len(B.REFUSAL_REASONS) + [True, False, False], got


def test_the_row_the_url_and_the_page_carry_it():
    assert "if (kind === \"likely\") return openProp(target, { likely: true });" in APP
    assert 'return ` data-open="likely:${escapeAttr(propId(t))}"`;' in APP
    assert 'data-prop="${escapeAttr(propId(t))}" data-likely="1"' in APP
    assert APP.count('openProp(card.dataset.prop, { likely: card.dataset.likely === "1", bet: card.dataset.bet })') == 2
    assert "state.propLikely = !!opts.likely;" in APP
    assert '`#pick/${encodeURIComponent(state.propId)}${state.propLikely ? "/likely" : ""}`' in APP
    assert 'const likely = kind === "pick" && p.length >= 3 && p[p.length - 1] === "likely";' in APP
    body = APP[APP.index("function renderPropPage()"):APP.index("function invNorm(")]
    # A bet opened from the Live tab is drawn the same way, at its own
    # number (betPickFor, 2026-09-25); from any other board, nothing.
    assert "const lk = state.propLikely ? likelyFor(r) : betPickFor(r);" in body
    assert body.index("whyLikelyHTML(v, r, lk)") < body.index("propAnalysis({ ...v, logs: r.logs }")
    assert "${lk ? \"\" : checksHTML(r)}" in body, "the edge board's gates stay on the edge board"
    assert "!lk && r.edge != null" in body and "${lk ? \"\" : r.grade ?" in body


def test_the_chart_shows_the_chance_not_the_edge_boards_ev():
    row = {"player": "Garrett Wilson", "market": "rec_yds", "market_label": "Receiving Yards", "side": "OVER",
           "line": 49.5, "odds": -150, "recent_values": [57, 79, 0, 13, 71], "ev_per_unit": 0.03, "confidence": 4}
    base = _fn(APP, "escapeHtml") + _fn(VIS, "escapeAttr") + _fn(VIS, "propAnalysis")
    got = _node(base + f"\nconsole.log(JSON.stringify([propAnalysis({json.dumps(row)}, {{chance: 0.71, tier: 'Top'}}),"
                       f" propAnalysis({json.dumps(row)})]));")
    if got is None:
        return
    likely, edge = got
    assert "OUR CHANCE" in likely and ">TOP<" in likely and "CONFIDENCE" not in likely and ">EV<" not in likely
    assert "CONFIDENCE" in edge and ">EV<" in edge, "the edge board's page is as it was"


def test_its_styles_use_the_tokens():
    block = CSS[CSS.index("A Most Likely pick, explained"):]
    for cls in (".why-likely", ".wl-head", ".wl-item", ".wl-moves", ".wl-foot", ".pp-board", ".pp-book"):
        assert cls in block, cls
    assert "px solid" not in block and "#" not in block.split("*/", 1)[1], "tokens only"


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
