"""Every bet the site offers carries a "Why it's likely" section.

Ethan, 2026-09-24, beside a Packers moneyline page that had none: "we
need to have a 'why it's likley' section for the Moneyline bets too.
Every single bet we offer needs too have a 'why it's likley' section."

The section existed for Most Likely props alone. Every door onto a bet
now draws one — the pick page (Edge props, Most Likely props, long
shots), the game-bet page (moneyline, spread, totals, from either board)
and the UFC pick card — through one shell (`whySectionHTML`), so the
heading, the list and the footer cannot drift between them. A bet under
50% is not called likely: its heading is "Why it's worth it".
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_every_bet_page_draws_the_section():
    prop = _fn("renderPropPage")
    assert "${whyLikelyHTML(v, r, lk)}" in prop, "every prop, not only Most Likely rows"
    assert "${lk ? whyLikelyHTML" not in prop
    game = _fn("renderGameBetPage")
    assert "${whyGameHTML(b, likely)}" in game, "moneyline, spread and totals"
    assert "ufcWhyHTML(p, title, shown)" in APP, "the UFC pick card"
    for fn in ("whyLikelyHTML", "whyGameHTML", "ufcWhyHTML"):
        assert "return whySectionHTML(items, " in _fn(fn), fn


def test_a_likely_game_row_heads_with_its_own_numbers():
    game = _fn("renderGameBetPage")
    assert 'const likely = b.kind === "game";' in game
    for k in ("Chance", "Book implies", "Our model alone"):
        assert f'<div class="k">{k}</div>' in game, k
    prop = _fn("renderPropPage")
    assert 'g.kind === "game" && gameBetId(g) === state.propId' in prop \
        and "renderGameBetPage(lkRow || b)" in prop, \
        "opened from Most Likely, the page is that board's row"


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PRELUDE = "\n".join([
    'const escapeHtml = (s) => String(s);',
    'const wholePct = (x) => `${Math.round(Number(x) * 100)}%`;',
    'const american = (o) => (o > 0 ? `+${o}` : `${o}`);',
    'const oddsTxt = american;',
    'const impliedOf = (o) => (o < 0 ? (-o) / ((-o) + 100) : 100 / (o + 100));',
    'const teamName = (t) => ({ GB: "Packers", CHI: "Bears" }[t] || t);',
    'const likelyHeld = () => null;',
    'let state = { data: { team_recent: { GB: [3, -17, 7, 7, 17].map((m) => ({ margin: m })) } } };',
    'const teamRecent = (t) => (state.data.team_recent[t] || []);',
])


def test_a_moneyline_explains_itself():
    fns = [_fn(n) for n in ("probTier", "whyHeldItem", "whySectionHTML", "gameBetSeries", "whyGameHTML")]
    i = APP.index("const GAME_EDGE_ONLY = ")
    j = APP.index("const EDGE_ONLY_REASON = ")
    consts = APP[i:APP.index("\n", i)] + "\n" + APP[j:APP.index(";\n", j) + 2]
    row = {"kind": "game", "bet_type": "moneyline", "market": "moneyline", "team": "GB",
           "home": "GB", "away": "ATL", "odds": -228, "book": "FanDuel", "model_prob": 0.689,
           "implied_prob": 0.689, "win_prob": 0.63, "rank_note": "Ranked on the market's number.",
           "reasons": ["The likely side.", "a +4.2% edge on ATL after the haircut"]}
    got = _node(PRELUDE + "\n" + consts + "\n" + "\n".join(fns)
                + f"\nprocess.stdout.write(JSON.stringify(whyGameHTML({json.dumps(row)}, true)));")
    if got is None:
        print("  SKIP node not installed")
        return
    assert "Why it’s likely" in got and "69% — Top" in got
    assert "Packers won 4 of their last 5" in got, got
    assert "FanDuel -228 implies 69%" in got
    assert "edge on ATL" not in got, "the other side's price verdict stays off this pick"


def test_a_long_shot_is_not_called_likely():
    fns = [_fn(n) for n in ("probTier", "whySectionHTML")]
    got = _node(PRELUDE + "\n" + "\n".join(fns)
                + '\nprocess.stdout.write(JSON.stringify([whySectionHTML([["Our chance", "23%"]], 0.23, "longshot"),'
                  ' whySectionHTML([], 0.61, "pass")]));')
    if got is None:
        print("  SKIP node not installed")
        return
    assert "Why it’s worth it" in got[0] and "Why it’s likely" not in got[0]
    assert "Not a pick on the Edge board" in got[1], "a row the board did not pick says so"


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
