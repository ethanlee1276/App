"""A book's cash-out offer is held to what the ticket is worth by our
numbers (slipgrade.cashout, slip.js cashOut).

Ethan, 2026-10-13: "add all of them", the third being a cash-out check —
"Book offers $45, we make it worth $52, so hold," or "take it".

The value is the ticket's return if the rest win (stake × the decimal
payout, a pushed leg taken out) times our chance for the rest — live once
the games are on, pre-game before. The page compares the offer to it as
the reader types, and says what the book keeps. Offline; no network.

    python3 tests/test_a_cash_out_is_held_to_our_number.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import slipgrade as SG                                # noqa: E402

SLIP_JS = ROOT / "web" / "js" / "slip.js"
APP = SLIP_JS.read_text(encoding="utf-8")


def _leg(odds, result=None, state=None):
    l = {"sport": "nfl", "league": "nfl", "player": "X", "team": "LA", "game": "BUF @ LA", "market": "rec_yds",
         "side": "over", "line": 69.5, "odds": odds, "prob": 0.6}
    if result or state:
        l["live"] = {"state": state or "final", "result": result}
    return l


def test_the_value_is_the_return_times_our_chance_for_the_rest():
    legs = [_leg(-110), dict(_leg(-110), team="KC", game="DEN @ KC")]
    out = SG.cashout(legs, {"stake": 10}, 10.0, None, 0.14)
    assert out == {"p": 0.14, "from": "ours", "payout": 10.0, "approx": False, "stake": 10.0, "left": 2,
                   "won": 0, "win": 100.0, "fair": 14.0}, out
    live = SG.cashout(legs, {"stake": 10}, 10.0, {"status": "open", "chance": 0.5, "left": 1, "won": 1}, 0.14)
    assert live["p"] == 0.5 and live["from"] == "live" and live["fair"] == 50.0 and live["left"] == 1 \
        and live["won"] == 1, "once the games are on, the standing's chance, not the pre-game one"
    no_stake = SG.cashout(legs, {}, 10.0, None, 0.14)
    assert no_stake["p"] == 0.14 and "fair" not in no_stake and "win" not in no_stake, \
        "no stake on the slip: the page takes one typed"


def test_a_lost_won_or_unpriced_ticket_has_no_offer_to_weigh():
    legs = [_leg(-110), dict(_leg(-110), team="KC", game="DEN @ KC")]
    assert SG.cashout(legs, {"stake": 10}, 10.0, {"status": "lost", "chance": 0.0}, 0.14) is None
    assert SG.cashout(legs, {"stake": 10}, 10.0, {"status": "won", "chance": 1.0}, 0.14) is None
    assert SG.cashout(legs, {"stake": 10}, 10.0, {"status": "open", "chance": None, "live": 1}, 0.14) is None, \
        "a leg in play with no live number: no box, not a guess"
    assert SG.cashout(legs, {"stake": 10}, 10.0, None, None) is None
    assert SG.cashout(legs, {"stake": 10}, None, None, 0.3) is None
    assert SG.cashout([], {"stake": 10}, 10.0, None, 0.3) is None


def test_a_pushed_leg_comes_out_of_the_return_and_a_same_game_slip_is_about():
    legs = [_leg(-110, result="push"), dict(_leg(-110), team="KC", game="DEN @ KC")]
    out = SG.cashout(legs, {"stake": 10}, 10.0, {"status": "open", "chance": 0.6, "left": 1, "won": 0}, None)
    assert abs(out["payout"] - 10.0 / (1 + 100 / 110)) < 1e-3 and out["approx"] is False   # rounded to 4 places
    assert out["win"] == round(10 * out["payout"], 2) and out["fair"] == round(out["win"] * 0.6, 2)
    bad = [dict(_leg(-110, result="push"), odds=None), dict(_leg(-110), team="KC", game="DEN @ KC")]
    out2 = SG.cashout(bad, {"stake": 10}, 10.0, {"status": "open", "chance": 0.6}, None)
    assert out2["approx"] is True and out2["payout"] == 10.0, "a pushed leg with no price: about, at the full payout"
    same = [_leg(-110), _leg(-105)]
    assert SG.cashout(same, {"stake": 10}, 4.0, None, 0.3)["approx"] is True


def test_the_card_carries_it_in_full_and_in_brief():
    src = (ROOT / "engine" / "slipgrade.py").read_text(encoding="utf-8")
    i = src.index("def grade(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert '"cashout": cashout(legs, slip, payout, now, chance),' in body
    assert body.index('"hedge": hedge(') < body.index('"cashout": cashout(')
    assert "if not brief" not in body[body.index('"cashout"') - 80:body.index('"cashout"')], \
        "the tracker's brief grade carries the cash-out too"


# ---- the page ---------------------------------------------------------------------------
def _node(script: str) -> str | None:
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    return out.stdout


def _vm(body: str) -> str:
    return ("const vm = require('vm'); const fs = require('fs');"
            "const ctx = { window: {} }; vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
            "const S = ctx.window.QBSlip;" + body)


def test_the_offer_is_a_take_a_hold_or_about_even():
    out = _node(_vm("process.stdout.write(JSON.stringify(["
                    "S.cashOut(10, 10, 0.14, ''), S.cashOut(10, 10, 0.14, '$20'), S.cashOut(10, 10, 0.14, '10'),"
                    "S.cashOut(10, 10, 0.14, '14.2'), S.cashOut('', 10, 0.14, '20'), S.cashOut(10, 10, 0, '5')]));"))
    if out is None:
        return
    blank, take, hold, even, no_stake, dead = json.loads(out)
    worth = ("By our 14% for the rest, the ticket is worth <b>$14.00</b> right now — 14% of the <b>$100.00</b> "
             "it returns if the rest win.")
    assert worth in blank and "Type the cash-out your book is offering" in blank
    assert worth in take and "<b class=\"pos\">Take it</b>, by our numbers: $20.00 is <b>$6.00</b> over what the ticket is worth." in take
    assert ("<b class=\"neg\">Hold</b>, by our numbers: the offer is 71% of fair — the book keeps about <b>$4.00</b>. "
            "Holding is 14% to collect $100.00 and 86% to collect nothing.") in hold
    assert "<b>About even</b> — the offer is within 3% of fair. Your call: $14.20 now, or 14% at $100.00." in even
    assert "Type your stake" in no_stake and "the ticket is worth <b>$" not in no_stake
    assert "Any offer beats a ticket we give no chance." in dead


def test_the_card_and_the_tracked_card_draw_the_box():
    card = {"legs": [], "n_legs": 2, "n_priced": 2, "dropped": 0, "book": "FanDuel", "stake": 10, "total_odds": 900,
            "ours": 0.14, "needs": 0.1, "ev": 0.4, "grade": "A", "notes": [], "weakest": "", "swap": None, "sim": None,
            "pairs": [], "alerts": [], "shop": None, "better": None, "first_kickoff": "", "now": None, "hedge": None,
            "cashout": {"p": 0.14, "from": "ours", "payout": 10.0, "approx": False, "stake": 10, "left": 2, "won": 0,
                        "win": 100.0, "fair": 14.0}}
    out = _node(_vm(f"process.stdout.write(S.card({json.dumps(card)}));"))
    if out is None:
        return
    assert '<div class="pgr-hedge pgr-cash" data-pay="10" data-p="0.14">' in out
    assert "<b>Cash-out check</b>" in out and 'data-cash="offer"' in out and 'data-cash="stake"' in out
    assert "the ticket is worth <b>$14.00</b> right now" in out
    assert "Nothing has started: our chance for the rest is the pre-game one." in out
    live = dict(card, cashout=dict(card["cashout"], **{"from": "live", "approx": True}))
    out2 = _node(_vm(f"process.stdout.write(S.card({json.dumps(live)}));"))
    assert "as the games stand now" in out2 and "priced about, not exactly" in out2
    none = dict(card, cashout=None)
    assert "pgr-cash" not in _node(_vm(f"process.stdout.write(S.card({json.dumps(none)}));"))
    # The tracked card on the Live tab carries it beside the hedge, the
    # typing guard keeps a redraw from eating a half-typed offer, and the
    # page's one input listener redoes the numbers.
    assert 'hedgeHTML(c.hedge) + cashoutHTML(c.cashout)' in APP
    assert 'document.activeElement.matches("[data-hedge],[data-cash]")' in APP
    assert 'if (t.matches("[data-cash]")) {' in APP and 'cout.innerHTML = cashOut(cv("stake"), cbox.dataset.pay, cbox.dataset.p, cv("offer"));' in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
