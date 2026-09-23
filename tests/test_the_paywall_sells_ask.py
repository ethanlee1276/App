"""The paywall page shows Ask Qellys.

Ethan, 2026-09-23: "Also make sure we display this feature on the paywall
page." Four places, each where a visitor deciding whether to pay looks:

  * A SECTION OF ITS OWN under the hero — "Meet Ask Qellys." — with a
    preview built from the Ask page's own parts and the four things it
    does. The preview shows a question and Ask's typing dots and NO
    ANSWER: an answer written for a sales page would be numbers nobody
    computed on the one page where every other number is graded in public;
  * the FIRST CARD in the feature grid;
  * the SECOND LINE of the plan's list, so the longer plans' four-line
    summary carries it too;
  * a CHIP in the breadth row, wearing the same mark as its card.

And what it sells is sold: /api/ask answers subscribers only.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
SERVER = (ROOT / "server.py").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_a_section_of_its_own_under_the_hero():
    pw = _fn("paywallHTML")
    hero_end = pw.index('<div class="pw-sports">')
    at = pw.index("${pwAskHTML()}")
    grid = pw.index('<h2 class="pw-h2"><em>Everything</em> you need.')
    assert hero_end < at < grid, "after the hero, before the feature grid"
    ask = _fn("pwAskHTML")
    assert '<h2 class="pw-h2" id="pw-ask-h">Meet <em>Ask Qellys.</em></h2>' in ask
    assert '<section class="pw-ask" aria-labelledby="pw-ask-h">' in ask
    assert '<span class="ask-pill">AI</span>' in ask, "the Ask page's own pill"
    assert "Your AI betting assistant." in ask


def test_the_preview_is_the_ask_page_and_invents_no_answer():
    ask = _fn("pwAskHTML")
    demo = ask[ask.index('<div class="pw-ask-demo" aria-hidden="true"'):ask.index('<ul class="pw-ask-points">')]
    assert 'qbotHTML("head", "pw-ask-bar-bot")' in demo and "askAva(true)" in demo, "the mascot, thinking"
    assert '<div class="pw-ask-demo" aria-hidden="true" data-bot="thinking">' in ask
    assert '<div class="ask-turn me">How have the Lions done against the Packers?</div>' in demo
    bots = re.findall(r'<div class="ask-turn bot[^"]*">(.*?)</div></div>', demo)
    assert bots == ['<span class="ask-dots"><i></i><i></i><i></i></span>'], \
        f"Ask's side of the preview is its typing dots and nothing else: {bots}"
    assert re.search(r"\d+-\d+|\d+%|\d+\.\d", demo.replace("Ask about a player", "")) is None, \
        "no score, record or percentage appears in the preview"
    assert 'askIcon("clip", 18)' in demo and 'askIcon("plane", 18)' in demo
    assert "<button" not in demo and "<textarea" not in demo and "<input" not in demo, "a picture, not a control"
    assert re.search(r"\.pw-ask-demo \{[^}]*pointer-events: none;", CSS)
    points = re.findall(r'point\("([^"]+)"\)', ask)
    assert len(points) == 4 and any("never tells you to bet" in p for p in points), points
    assert any("not just who plays tonight" in p for p in points), "his own complaint, answered on the shop"


def test_the_first_card_the_plan_line_and_the_chip():
    grid = _fn("paywallHTML")
    grid = grid[grid.index('<div class="pw-feats">'):]
    first = re.search(r'feature\("([^"]+)", "([^"]+)"', grid)
    assert first.groups() == ("🤖", "Ask Qellys"), "the grid leads with it"
    feats = re.search(r"const PLAN_FEATURES = \[(.*?)\n\];", APP, re.S).group(1)
    lines = re.findall(r'^\s*"([^"]+)",', feats, re.M)
    assert lines[1] == "Ask Qellys, the AI assistant — any team, player or game", lines[:3]
    plan = _fn("paywallHTML")
    assert "PLAN_EXTRAS[pl.id].concat(PLAN_FEATURES.slice(0, 4))" in plan, \
        "the longer plans show the first four lines, so the second is on every plan"
    chips = dict(re.findall(r'\["([^"]+)",\s*"([^"]+)"\]',
                            re.search(r"const PW_SPORTS = \[(.*?)\n\];", APP, re.S).group(1)))
    assert chips.get("Ask Qellys AI") == first.group(1), "the chip and its card wear one mark"


def test_what_the_shop_sells_is_behind_the_subscription():
    body = SERVER[SERVER.index("    def _ask(self, body):"):SERVER.index("    def _receipts_csv(self):")]
    assert "if not self._entitled(conn, who):" in body
    assert body.index("self._entitled(conn, who)") < body.index("AB.ask(payload"), \
        "a stranger is turned away before anything is spent"


if __name__ == "__main__":
    import sys
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
