"""One risk view of every open bet — how the tickets move together, the bad night, and the hedge that helps most.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 13: three slips that
lean on one quarterback are one bet three times.

What these hold: a ticket needs a stake and a price, a hand-logged bet is
a leg of its own, and the same leg on two slips is one event; legs in one
game are joined by the parlay engine's number, legs in different games
not at all; the copula's matrix is made drawable; a ticket wins only when
all its legs do, so five copies of one leg lose together half the time;
the hedge is the other side that lifts the bad night most, or none; the
exposure counts each ticket once per player; the endpoint is members-only
and keeps nothing; and My Bets' open tab draws the card while the settled
tab keeps the report card. No test touches the network.

Run directly: `python3 tests/test_one_risk_view_of_every_open_bet.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import parlays as P                                  # noqa: E402
from engine import risk as R                                     # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"


def _leg(player, market, side, line, odds=-110, team="BUF", game="MIA @ BUF"):
    return {"sport": "nfl", "player": player, "team": team, "game": game, "market": market, "side": side,
            "line": line, "odds": odds}


ALLEN = _leg("Josh Allen", "pass_yds", "over", 245.5)
SHAKIR = _leg("Khalil Shakir", "rec_yds", "over", 55.5)


def test_tickets_need_a_stake_and_a_price_and_a_leg_is_one_event():
    bets = R.clean_bets([{"id": "a", "stake": 10, "odds": 250, "legs": [ALLEN, SHAKIR]},
                         {"id": "b", "stake": 5, "odds": -110, "legs": [ALLEN]},
                         {"id": "c", "stake": 20, "odds": 150, "desc": "Yankees ML"},
                         {"id": "d", "stake": 0, "odds": 150}, {"id": "e", "stake": 5, "odds": 50}, "junk"])
    assert [b["id"] for b in bets] == ["a", "b", "c"], "no stake, or no price, is no ticket"
    priced = R.price_legs(bets, None)
    assert len(priced) == 3, "Allen on two slips is one leg; the hand-logged bet is a leg of its own"
    allen = priced[R.leg_key(ALLEN)]
    assert allen["source"] == "price" and abs(allen["prob"] - (110 / 210) / (1 + R.HEDGE_MARGIN)) < 1e-9


def test_one_game_takes_the_parlay_engines_number_and_other_games_none():
    bets = R.clean_bets([{"id": "a", "stake": 10, "odds": 250, "legs": [ALLEN, SHAKIR]},
                         {"id": "b", "stake": 5, "odds": -110, "legs": [_leg("Tua Tagovailoa", "pass_yds", "over", 230.5,
                                                                          team="MIA", game="MIA @ BUF")]},
                         {"id": "c", "stake": 5, "odds": -110, "legs": [_leg("Puka Nacua", "rec_yds", "over", 80.5,
                                                                          team="LAR", game="SF @ LAR")]}])
    priced = R.price_legs(bets, None)
    keys = list(priced)
    rho = R.correlations(keys, priced)
    rel = P.relate("nfl", {"player": "Josh Allen", "team": "BUF", "market": "pass_yds", "side": "OVER"},
                   {"player": "Khalil Shakir", "team": "BUF", "market": "rec_yds", "side": "OVER"})
    want = rel.rho if rel.measured else rel.rho * P.RHO_SHRINK
    assert abs(rho[0][1] - want) < 1e-9 and rho[0][1] > 0.1, "a passer and his receiver move together"
    assert rho[0][3] == 0.0 and rho[1][3] == 0.0, "a game across the country shares nothing"
    low = R.cholesky([[1.0, 0.95, -0.95], [0.95, 1.0, 0.95], [-0.95, 0.95, 1.0]])
    assert all(low[i][i] > 0 for i in range(3)), "an impossible matrix is shrunk until it can be drawn"


def test_a_ticket_wins_only_when_all_its_legs_do():
    five = [{"id": str(i), "stake": 10, "odds": -110, "legs": [ALLEN]} for i in range(5)]
    r = R.analyze(five, nights=4000)
    assert r["legs"] == 1 and 0.45 < r["all_lose"] < 0.55, "five copies of one leg lose together"
    assert r["independent_all_lose"] < 0.05 and r["bad_night"] == -50.0
    assert r["exposure"]["players"] == [{"name": "Josh Allen", "stake": 50.0, "share": 1.0}]
    h = r["hedge"]
    assert h["leg"].startswith("Josh Allen") and h["bad_night_after"] > -10 and h["cost"] < 0
    spread = R.analyze([{"id": str(i), "stake": 10, "odds": -110,
                         "legs": [_leg(f"P{i}", "rec_yds", "over", 50.5, team=f"T{i}", game=f"G{i}")]} for i in range(5)],
                       nights=4000)
    assert spread["all_lose"] < 0.1 and spread["hedge"] is None, "five unrelated legs: no single hedge helps much"
    assert R.analyze([]) == {"bets": 0}


def test_the_endpoint_is_for_members_and_keeps_nothing():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/mybets/risk"' in src and "def _mybets_risk(self, body: dict):" in src
    body = src[src.index("def _mybets_risk"):src.index("def _hoops_whatif")]
    assert "self._entitled(conn, who)" in body and "401 if not who else 402" in body
    assert "RK.analyze(bets[:RK.MAX_BETS], boards)" in body and "INSERT" not in body


def test_my_bets_draws_the_card_on_the_open_tab():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '`<div id="mb-risk"></div>`' in app and '`<div id="mb-report"></div>`' in app
    assert 'X.riskView(document.getElementById("mb-risk"))' in app
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    r = R.analyze([{"id": "a", "stake": 10, "odds": 250, "legs": [ALLEN, SHAKIR]},
                   {"id": "b", "stake": 5, "odds": -110, "legs": [ALLEN]},
                   {"id": "c", "stake": 20, "odds": 150, "desc": "Yankees ML"}], nights=3000)
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx); const X = ctx.window.QBExtras;"
              f"process.stdout.write(JSON.stringify({{h: X.riskHTML({json.dumps(r)}), none: X.riskHTML({{bets: 0}})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    got = json.loads(out.stdout)
    h = got["h"]
    assert "Your open bets, together" in h and "A bad night (1 in 20)" in h and "Every ticket loses" in h
    assert "of your money rides on <b>Josh Allen</b>" in h and "A reading, not advice" in h
    assert got["none"] == ""


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
