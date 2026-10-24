"""Every fight the UFC model prices carries round prices, off the finish times we store.

Ethan, 2026-10-14: "Do 1-7 and the ones we download but don't use" — and
on that list, UFC finish times: "They'd allow 'goes the distance' and
round reads; the odds feed only prices the moneyline, so these would be
our own fair prices to shop by hand." Pinned here:

  * a finish's time is read off its round and clock, and a decision, a
    no contest or a finish with no clock is not a finish time;
  * the league's shape is every stored bout at the fight's scheduled
    length, each bout once, and with too few of them there is no round
    price at all — never the written hazard prior;
  * the two fighters' own finishes lean the shape, PRIOR fights' worth of
    league against each of theirs;
  * the prices agree with the distance price by construction: the round
    it ends in sums to the chance it ends inside the distance, and each
    over and under sums to one;
  * they ride on the fight's own market board as unpriced fair numbers —
    tier 3, never staked, never the fight's best market — on picks and
    near misses alike, and the passed card draws the list too.

Run directly: `python3 tests/test_ufc_round_prices_from_finish_times.py`
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db                                    # noqa: E402
from engine.ufc import markets as M, rounds as R         # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fight(fighter, comp, method, rnd, clock, rounds=3):
    return {"fighter": fighter, "fighter_id": "1", "comp_id": comp, "event_id": "e", "date": "2026-01-01",
            "opp": "Somebody", "opp_id": "2", "result": "W", "method": method, "rnd": rnd, "clock": clock,
            "secs": 0.0, "rounds": rounds, "division": "Lightweight"}


def _conn(league_finishes=130, rounds=3):
    """``league_finishes`` stored bouts that ended inside the distance, in
    round one at 2:00, plus decisions and a no contest."""
    conn = db.connect(":memory:")
    rows = [_fight(f"F{i}", f"c{i}", "KO/TKO", 1, "2:00", rounds) for i in range(league_finishes)]
    rows += [_fight(f"D{i}", f"d{i}", "DEC", rounds, "5:00", rounds) for i in range(40)]
    rows += [_fight("N0", "n0", "NC", 2, "1:00", rounds)]
    db.upsert_ufc_fights(conn, rows)
    conn.commit()
    return conn


def test_a_finish_time_is_its_round_and_clock():
    assert R.finish_secs("KO/TKO", 2, "2:31") == 451.0
    assert R.finish_secs("SUB", 1, "5:00") == 300.0
    assert R.finish_secs("DEC", 3, "5:00") is None
    assert R.finish_secs("SUB", 2, "") is None and R.finish_secs("KO/TKO", None, "1:00") is None
    assert R.finish_secs("NC", 2, "1:00") is None


def test_the_league_shape_counts_each_bout_once_at_its_own_length():
    conn = _conn(130)
    # The same bout filed under both men counts once.
    db.upsert_ufc_fights(conn, [_fight("F0b", "c0", "KO/TKO", 1, "2:00")])
    # A five-round bout is not a three-round one's shape.
    db.upsert_ufc_fights(conn, [_fight("Main", "m1", "KO/TKO", 4, "1:00", rounds=5)])
    conn.commit()
    xs = R.league(conn, 3)
    assert len(xs) == 130 and set(xs) == {120.0}
    assert R.league(conn, 5) == [960.0]


def test_too_few_stored_finishes_is_no_price_never_the_written_prior():
    assert R.board(0.5, 3, [120.0] * (R.MIN_LEAGUE - 1), []) is None
    conn = _conn(R.MIN_LEAGUE - 1)
    result = {"picks": [], "pass_list": [{"p_distance": 0.5, "market_board": [], "fighters": []}]}
    assert R.attach(result, conn) == 0 and result["pass_list"][0]["market_board"] == []
    src = (ROOT / "engine" / "ufc" / "rounds.py").read_text(encoding="utf-8")
    assert "HAZARD_SHAPE" not in src.split('"""', 2)[2], "the written prior never prices a round"


def test_the_prices_agree_with_the_distance_price():
    league = sorted([120.0] * 60 + [420.0] * 40 + [800.0] * 30)        # 130 finishes
    own = [100.0, 500.0]
    got = R.board(0.6, 3, league, own)
    p = {r["selection"]: r["p"] for r in got["rows"]}
    assert set(p) == {"Under 1.5 rounds", "Over 1.5 rounds", "Under 2.5 rounds", "Over 2.5 rounds",
                      "Ends in round 1", "Ends in round 2", "Ends in round 3"}
    for x in ("1.5", "2.5"):
        assert abs(p[f"Under {x} rounds"] + p[f"Over {x} rounds"] - 1.0) < 1e-3
    assert abs(sum(p[f"Ends in round {r}"] for r in (1, 2, 3)) - 0.6) < 1e-3, "rounds sum to inside the distance"
    # By hand: the league's share before 2:30 of round two (450 s) is
    # 100/130, the pair's own 1/2, leaned PRIOR (10) against their 2.
    w = 2 / (2 + R.PRIOR)
    assert abs(p["Under 1.5 rounds"] - round(0.6 * ((1 - w) * 100 / 130 + w * 0.5), 4)) < 1e-4
    assert got["n_league"] == 130 and got["n_own"] == 2 and got["rounds"] == 3
    assert "not measured" in got["note"] and "never a bet" in got["note"]
    five = R.board(0.6, 5, league, own)
    assert {r["selection"] for r in five["rows"] if r["market"] == "round"} >= {"Over 4.5 rounds", "Under 3.5 rounds"}


def test_a_finish_at_the_line_is_over_and_a_finish_at_the_horn_is_that_round():
    league = [450.0] * 130
    p = {r["selection"]: r["p"] for r in R.board(1.0, 3, league, [])["rows"]}
    assert p["Under 1.5 rounds"] == 0.0 and p["Over 1.5 rounds"] == 1.0, "2:30 of round two is over 1.5"
    p = {r["selection"]: r["p"] for r in R.board(1.0, 3, [300.0] * 130, [])["rows"]}
    assert p["Ends in round 1"] == 1.0, "a stoppage at 5:00 of round one ended in round one"


def test_they_ride_on_the_board_as_fair_numbers_to_shop():
    conn = _conn(130)
    db.upsert_ufc_fights(conn, [_fight("Alpha One", "a1", "SUB", 3, "4:00"),
                                _fight("Alpha One", "a2", "DEC", 3, "5:00"),
                                _fight("Beta Two", "b1", "KO/TKO", 2, "0:30")])
    conn.commit()
    ml = M.price_market({"market": "moneyline", "selection": "Alpha One", "p": 0.6}, -150, 0.6)
    pick = {"kind": "pick", "p_distance": 0.45, "scheduled_rounds": 3, "thin_data": False,
            "fighters": [{"name": "Alpha One"}, {"name": "Beta Two"}], "market_board": [ml], "best_market": ml}
    near = {"kind": "pass", "reason_code": "gate", "near_miss": True, "p_distance": 0.5,
            "fighters": [{"name": "Gamma"}, {"name": "Delta"}], "market_board": []}
    waiting = {"kind": "pass", "reason_code": "no_price", "fighters": []}
    result = {"picks": [pick], "pass_list": [near, waiting]}
    assert R.attach(result, conn) == 2
    rounds = [c for c in pick["market_board"] if c["market"] in ("round", "exact_round")]
    assert len(rounds) == 7 and all(c["priced"] is False and c["odds"] is None and c["fair_odds"] for c in rounds)
    assert all(c["market_tier"] == 3 and c["volatility"] == "EXTREME" for c in rounds)
    assert "go and shop it" in rounds[0]["note"]
    assert M.best_market(pick["market_board"]) is ml, "an unpriced fair number is never the bet"
    assert pick["round_read"]["n_own"] == 2, "his submission and the other man's knockout; the decision is not one"
    # All but two of the 132 stored finishes (the two above join the
    # league too) landed in round one, and this pair has none of its own:
    # round one is nearly the whole inside-the-distance chance, and the
    # other two rounds are too small a number to shop.
    assert {c["selection"]: c["p_used"] for c in near["market_board"]
            if c["market"] == "exact_round"} == {"Ends in round 1": round(0.5 * 130 / 132, 4)}
    assert "market_board" not in waiting, "a fight the model never priced gets no round price"
    # A number no book hangs is not shown: every stored finish here is in
    # round one, so "ends in round 3" is near nothing for a pair with none.
    lone = {"p_distance": 0.5, "fighters": [], "market_board": []}
    R.attach({"picks": [lone]}, conn)
    assert all(0.01 <= c["p_used"] <= 0.99 for c in lone["market_board"])
    assert "Ends in round 3" not in {c["selection"] for c in lone["market_board"]}
    R.attach(result, conn)
    assert len([c for c in pick["market_board"] if c["market"] == "round"]) == 4, "a rebuild never doubles them"


def test_the_build_attaches_them_and_the_card_draws_them_on_a_pass_too():
    build = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    assert "_rounds.attach(out, _rc)" in build
    i = APP.index("const shopList = (p) =>")
    j = APP.index("const passCard = (m) =>")
    assert "${shopList(p)}" in APP[i:j] and "${shopList(m)}" in APP[j:APP.index("const c = d.counts", j)]
    assert 'round: "Round", exact_round: "Exact round"' in APP
    if not shutil.which("node"):
        return
    a = APP.index("const shopRow = (c) =>")
    src = APP[a:APP.index("const pickCard = (p) =>", a)]
    prog = ("const escapeHtml = (s) => String(s); const american = (o) => (o > 0 ? `+${o}` : `${o}`);"
            'const MARKET_LABEL = { round: "Round", exact_round: "Exact round" };'
            + src + "\nprocess.stdout.write(shopList(" + json.dumps({"market_board": [
                {"market": "round", "selection": "Over 1.5 rounds", "priced": False, "fair_odds": 150},
                {"market": "exact_round", "selection": "Ends in round 1", "priced": False, "fair_odds": 0}]})
            + "));")
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert "Every market this fight implies (1)" in out.stdout and "fair +150" in out.stdout
    assert re.search(r"Over 1\.5 rounds", out.stdout) and "shop it" in out.stdout


def test_the_call_is_in_the_runbook():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "engine/ufc/rounds" in doc and re.search(r"round prices", doc, re.I)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
