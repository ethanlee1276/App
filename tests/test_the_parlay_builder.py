"""The parlay builder: tonight's legs put together, priced with the correlation between them.

Ethan, 2026-10-15, one of the sixteen ideas he asked to have built ("do
every one for every sport"): a correlated parlay builder. Context only;
nothing on the board moves for it.

What these hold: a leg is a named pick with a chance; legs in two games
are independent, so the joint is their product, and a same-game pair is
priced by the engine's own measured correlation — and a cross-game leg
beside it does not wash that correlation out; a pair the taxonomy kills
(the same man twice, the pass game against the run game) is refused with
its reason, and so is a ticket past the sport's ceiling; a same-game
ticket claims no edge against its legs' prices multiplied; the stacks are
the board's legs that move with the ones chosen, the refused and the
chosen left out; the endpoint reads only what it is sent; and every
board sport's Toolbox draws the builder, its ticket and its refusal.

Run directly: `python3 tests/test_the_parlay_builder.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import parlaybuild as PB                             # noqa: E402
from engine import parlays as P                                  # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"
G = {"team": "BUF", "opponent": "MIA", "game_date": "2026-10-19"}
QB = {"player": "Josh Allen", "market": "pass_yds", "side": "over", "line": 249.5, "position": "QB", "odds": -115, "p": 0.58, **G}
WR = {"player": "Khalil Shakir", "market": "rec_yds", "side": "over", "line": 52.5, "position": "WR", "odds": -110, "p": 0.55, **G}
TE = {"player": "Dalton Kincaid", "market": "rec_yds", "side": "over", "line": 40.5, "position": "TE", "odds": -110, "p": 0.52, **G}
RB = {"player": "James Cook", "market": "rush_yds", "side": "over", "line": 70.5, "position": "RB", "odds": -110, "p": 0.56, **G}
DET = {"player": "Jared Goff", "market": "pass_yds", "side": "over", "line": 260.5, "position": "QB", "odds": -110, "p": 0.60,
       "team": "DET", "opponent": "GB", "game_date": "2026-10-19"}


def test_a_leg_is_a_named_pick_with_a_chance():
    assert PB.clean(QB)["p"] == 0.58
    assert PB.clean(dict(QB, p=1.0)) is None and PB.clean(dict(QB, p="x")) is None and PB.clean(dict(QB, market="")) is None
    assert PB.clean(dict(QB, player="")) is None, "no man and no game: nothing to price"
    assert PB.clean({"home": "MIA", "away": "BUF", "market": "total", "side": "over", "p": 0.5}) is not None
    assert PB.clean("junk") is None and len(PB.clean(dict(QB, player="x" * 200))["player"]) == 60
    assert PB.build("nfl", [])["ok"] is False


def test_two_games_are_independent_and_one_game_is_correlated():
    two = PB.build("nfl", [QB, DET])
    assert two["ok"] and two["pairs"] == [] and two["same_game"] is False
    assert abs(two["joint"] - 0.58 * 0.60) < 1e-4 and two["joint"] == two["independent"]
    dec = P.american_to_decimal(-115) * P.american_to_decimal(-110)
    assert two["ev"] == round(two["joint"] * dec - 1, 4), "across games the legs' prices multiplied are what the book pays"
    one = PB.build("nfl", [QB, WR])
    assert one["ok"] and one["same_game"] is True and one["ev"] is None, "a same-game ticket claims no edge on the product"
    r = P.relate("nfl", QB, WR).rho
    assert one["pairs"][0]["pair"] == [0, 1] and one["pairs"][0]["rho"] == round(r, 2) and one["pairs"][0]["why"]
    assert abs(one["joint"] - P.joint_two(0.58, 0.55, r)) < 1e-4 and one["joint"] > one["independent"]
    assert one["fair"] == P.decimal_to_american(1 / one["joint"])


def test_a_leg_in_another_game_keeps_the_pair_its_correlation():
    three = PB.build("nfl", [QB, WR, DET])
    r = P.relate("nfl", QB, WR).rho
    assert abs(three["joint"] - P.joint_two(0.58, 0.55, r) * 0.60) < 1e-3, \
        "priced as one block the zero pair would shrink the one-factor copula to independence"
    assert PB.joint([0.5, 0.5], {(0, 1): 0.0}) == 0.25
    assert abs(PB.joint([0.58, 0.55, 0.52], {(0, 1): 0.4, (0, 2): 0.4, (1, 2): 0.3})
               - P.joint_three((0.58, 0.55, 0.52), (0.4, 0.4, 0.3))) < 1e-9, "all positive: the model's own copula"
    neg = PB.joint([0.5, 0.5, 0.5], {(0, 1): 0.6, (0, 2): -0.2, (1, 2): 0.3})
    assert 0.0 < neg < 0.5 and neg == PB.joint([0.5, 0.5, 0.5], {(0, 1): 0.6, (0, 2): -0.2, (1, 2): 0.3}), \
        "simulated with a fixed seed: the same ticket reads the same twice"
    assert 0.0 < PB.joint_n([0.5] * 3, {(0, 1): 0.9, (0, 2): 0.9, (1, 2): -0.9}, draws=4000) < 0.5, \
        "a matrix that cannot be is shrunk until it can"


def test_the_engine_refuses_what_its_rules_kill():
    dup = PB.build("nfl", [QB, dict(QB, side="under")])
    assert dup["ok"] is False and dup["pair"] == [0, 1] and "same player" in dup["reason"]
    kill = PB.build("nfl", [QB, WR, RB])
    assert kill["ok"] is False and kill["pair"] == [0, 2] and kill["reason"]
    assert PB.build("nfl", [QB, WR, DET, dict(DET, player="Amon-Ra St. Brown", market="rec_yds")])["reason"] == "3 legs is the ceiling"
    nhl = [dict(QB, player=n, market="sog") for n in "abc"]
    assert PB.build("nhl", nhl)["reason"] == "2 legs is the ceiling" and PB.build("nhl", nhl[:1])["cap"] == 2


def test_the_stacks_move_with_the_ticket():
    got = PB.build("nfl", [QB], [WR, TE, RB, DET, QB, {"junk": 1}])
    names = [s["player"] for s in got["stacks"]]
    assert names == ["Khalil Shakir", "Dalton Kincaid"], names
    assert all(s["rho"] >= PB.STACK_RHO for s in got["stacks"]), "the run game and another game do not stack"
    assert "Josh Allen" not in names, "the chosen leg is not offered again"
    two = PB.build("nfl", [QB, WR], [TE, DET])
    assert two["stacks"] == [], "the catch-pie split with the receiver chosen is refused, not offered"
    assert PB.build("nfl", [QB, WR, DET], [TE])["stacks"] == [], "a full ticket offers nothing"


def test_the_endpoint_reads_only_what_it_is_sent():
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'parsed.path in ("/api/parlay/build", "/api/parlay/build/")' in srv
    assert 'if parsed.path.startswith("/api/parlay/build"):\n                return self._parlay_build(body)' in srv
    i = srv.index("def _parlay_build(")
    body = srv[i:srv.index("\n    def ", i + 10)]
    assert "PB.build(sport, legs[:12], pool[:PB.MAX_POOL])" in body and "open(" not in body and "connect(" not in body


def _node(body: str):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {}, document: { addEventListener() {} }, state: { sport: 'nfl' } }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx);"
              "const X = ctx.window.QBExtras;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_every_board_sport_draws_the_builder():
    rows = [dict(QB, model_prob=0.58, market_label="Pass yards"), dict(WR, hit_prob=0.55, market_label="Receiving yards"),
            dict(DET, model_prob=0.6), dict(QB, model_prob=0.58), {"player": "No Chance", "market": "rec_yds"}]
    built = PB.build("nfl", [QB, WR], [TE])
    refused = PB.build("nfl", [QB, dict(QB, side="under")])
    got = _node(f"const d = {{most_likely: {json.dumps(rows[:3])}, recommendations: {json.dumps(rows[3:])}}};"
                "const rows = X.pbRows(d); const html = X.builderHTML(d);"
                f"X.PB.legs = [X.PB.rows[0], X.PB.rows[1]]; X.PB.out = Object.assign({json.dumps(built)}, {{sent: X.PB.legs}});"
                "const ticket = X.pbTicketHTML();"
                f"X.PB.out = {json.dumps(refused)}; const no = X.pbTicketHTML();"
                "const locked = X.builderHTML({locked: {most_likely: true}}), empty = X.builderHTML({});"
                "process.stdout.write(JSON.stringify({n: rows.length, html, ticket, no, locked, empty}));")
    if got is None:
        return
    assert got["n"] == 3, "deduped, and a row with no chance is not a leg"
    assert "Parlay builder" in got["html"] and got["html"].count('data-xt="pb-add"') == 3 and 'data-xw="pb-game"' in got["html"]
    assert "BUF · MIA" in got["html"] and "Josh Allen Over 249.5 Pass yards" in got["html"]
    t = got["ticket"]
    assert t.count('data-xt="pb-del"') == 2 and "All hit, with the correlation" in t and "As if independent" in t
    assert "A same-game ticket" in t and "Josh Allen &amp; Khalil Shakir" in t and "+0.64" in t
    assert "same player" in got["no"] and 'class="xt-pb-no"' in got["no"]
    assert "come with a membership" in got["locked"] and "No legs on the board yet" in got["empty"]
    src = EXTRAS.read_text(encoding="utf-8")
    i = src.index("const SPORT_TOOLS = {")
    tools = src[i:src.index("};", i)]
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba", "nhl"):
        line = next(l for l in tools.splitlines() if l.strip().startswith(f"{sport}:"))
        assert "builderHTML" in line, sport
    assert 'fetch("/api/parlay/build"' in src and "if (seq !== PB.seq) return;" in src, "the last ask wins"


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
