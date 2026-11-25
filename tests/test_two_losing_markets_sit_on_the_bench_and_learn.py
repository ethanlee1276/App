"""Two losing Edge markets sit on the bench and keep learning (engine/stakeplan
MARKET_BENCH), MKTBENCH1.

Ethan, 18 November 2026, asked whether the two Edge markets that had lost all
season should keep their stakes (the NFL's quarterback completions, 44-53 and
-11.9 units; the NBA's points, 63-71 and -10.2 units) or be benched: "bench and
learn". What these hold:

  * from the day of the bench, an Edge pick in either market carries no stake
    in the staked record, is counted as tracked, and is left out of its
    league's evidence; a pick before the bench, another market, another
    league's points and a Most Likely pick are as they were;
  * its own record since the bench is kept apart, and lifts the bench by
    itself once MARKET_RELEASE_N graded since have made money at flat stakes
    (from the next day); losing, or short of the count, it stays benched;
  * the stored plan says where each bench stands, and the journal reads it: a
    new pick in a benched market goes on paper, and back on the stake once the
    plan says the bench was lifted;
  * the board marks such a pick `tracked`, so its card says "Tracked · no
    stake", the Pick of the Day never leads with it, and the Record page names
    the benched markets.

    python3 tests/test_two_losing_markets_sit_on_the_bench_and_learn.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger as L, potd, stakeplan as SP                          # noqa: E402


def _row(day, sport, market, status="won", odds=-110, category="main", stake=1.0):
    return {"day": day, "date": day, "sport": sport, "market": market, "category": category, "odds": odds,
            "status": status, "stake_units": stake, "pnl_units": (100 / 110) if status == "won" else -1.0}


def test_the_two_markets_are_named_from_the_day_he_said_so():
    named = {(b["sport"], b["market"]): b for b in SP.MARKET_BENCH}
    # …and the NFL's pass attempts since 21 November (Ethan's answer to decision 16: "bench them"), and its
    # carries since 25 November (the same rule, under decision 19's "do whatever you think").
    assert set(named) == {("nfl", "pass_cmp"), ("nba", "pts"), ("nfl", "pass_att"), ("nfl", "rush_att")}, named
    assert {b["since"] for k, b in named.items() if k in (("nfl", "pass_cmp"), ("nba", "pts"))} == {"2026-11-18"}
    assert named[("nfl", "rush_att")]["since"] == "2026-11-25" and named[("nfl", "rush_att")]["was"] == "40-46, -6.7 units"
    assert SP.market_benched("nfl", "rush_att", {}, "2026-11-26") and SP.market_benched("nfl", "rush_att", {}, "2026-11-24") is None
    assert SP.market_benched("cfb", "rush_att", {}, "2026-11-28") is None, "college's carries made money: not benched"
    assert named[("nfl", "pass_att")]["since"] == "2026-11-21" and named[("nfl", "pass_att")]["was"] == "21-26, -4.0 units"
    assert SP.market_benched("nfl", "pass_cmp", {}, "2026-11-18") and SP.market_benched("NBA", "PTS", {}, "2026-11-20")
    assert SP.market_benched("nfl", "pass_cmp", {}, "2026-11-17") is None, "not before the day"
    assert SP.market_benched("nfl", "pass_att", {}, "2026-11-21") and SP.market_benched("nfl", "pass_att", {}, "2026-11-20") is None
    for sport, market in (("cbb", "pts"), ("wnba", "pts"), ("nba", "pts_reb"), ("cfb", "pass_att"), ("nba", "ast")):
        assert SP.market_benched(sport, market, {}, "2026-11-21") is None, (sport, market)


def test_a_benched_pick_carries_no_stake_and_stays_out_of_its_leagues_evidence():
    rows = [_row("2026-11-10", "nfl", "pass_cmp"), _row("2026-11-20", "nfl", "pass_cmp", "lost"),
            _row("2026-11-20", "nfl", "receptions"), _row("2026-11-20", "nba", "pts", "lost"),
            _row("2026-11-20", "cbb", "pts", "lost"),
            _row("2026-11-20", "nba", "pts", "won", category="likely")]
    flags, state = SP.replay(rows)
    assert flags[:5] == [True, False, True, False, True], flags
    assert flags[5] is False, "Most Likely is tracked anyway, as it was"
    assert state[("edge", "nfl")]["book"].n == 2, "the benched loss is not in the NFL's evidence"
    assert state[("bench", "nfl")]["pass_cmp"]["book"].n == 1 and state[("bench", "nba")]["pts"]["book"].n == 1
    rep = SP.report(rows)
    assert rep["overall"]["tracked"] == 3, rep["overall"]
    plan = rep["plan"]
    b = plan["nfl"]["benched_markets"]["pass_cmp"]
    assert b["since"] == "2026-11-18" and not b["released"] and b["n"] == 1, b
    assert b["why"].startswith("NFL quarterback completions: tracked, not staked, since 18 November"), b["why"]
    assert "staked again once 60 graded since make money at flat stakes" in b["why"]
    assert plan["nba"]["benched_markets"]["pts"]["words"] == "points"


def test_the_bench_lifts_itself_once_its_picks_since_make_money():
    days = [f"2026-11-{d:02d}" for d in range(18, 30)] + [f"2026-12-{d:02d}" for d in range(1, 31)]
    winning = [_row(days[i // 2], "nba", "pts", "won" if i % 5 else "lost") for i in range(SP.MARKET_RELEASE_N)]
    nxt = _row("2026-12-30", "nba", "pts")
    flags, state = SP.replay(winning + [nxt])
    b = state[("bench", "nba")]["pts"]
    assert b["released"] == winning[-1]["day"], b["released"]
    assert flags[-1] is True, "staked again the day after its record lifted it"
    assert not any(flags[:-1]), "the picks that earned it back were all on paper"
    plan = SP.plan_from(state)
    assert plan["nba"]["benched_markets"]["pts"]["released"] and \
        SP.market_benched("nba", "pts", plan, "2026-12-31") is None
    # Short of the count, or losing over it: still on the bench.
    flags, state = SP.replay(winning[:-1])
    assert not state[("bench", "nba")]["pts"]["released"]
    losing = [_row(days[i // 2], "nba", "pts", "lost" if i % 2 else "won") for i in range(SP.MARKET_RELEASE_N + 10)]
    flags, state = SP.replay(losing)
    assert not state[("bench", "nba")]["pts"]["released"] and not any(flags)


def test_the_journal_puts_a_benched_pick_on_paper():
    conn = L.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    import datetime as dt
    today = dt.date.today().isoformat()
    if today >= "2026-11-18":
        assert L.market_book(conn, "main", "nfl", "pass_cmp") == "paper"
        assert L.market_book(conn, "main", "nba", "pts") == "paper"
    assert L.market_book(conn, "main", "nfl", "receptions") == "main"
    assert L.market_book(conn, "paper", "nba", "pts") == "paper"
    assert L.market_book(conn, "likely", "nba", "pts") == "likely", "only the Edge book's stake is benched"
    # Once the stored plan says the bench was lifted, the pick is staked again.
    L.set_cfg(conn, L.STAKE_PLAN_KEY, '{"nba": {"benched_markets": {"pts": {"released": "2026-12-20"}}}}')
    assert L.market_book(conn, "main", "nba", "pts") == "main"
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert ("row_book = EDGE_HELD_CATEGORY if held else market_book(\n"
            "            conn, edge_price_book(prop_book(category, sport, r.get(\"side\", \"OVER\")), "
            "r.get(\"odds\", -110)),\n            sport, r.get(\"market\"))") in src


def test_the_board_says_tracked_and_the_pick_of_the_day_passes_it_by():
    board = {"sport": "nba", "date": "2099-11-20", "recommendations": [
        {"player": "A Scorer", "market": "pts", "side": "OVER", "line": 22.5, "odds": -110, "recommended": True,
         "stake_units": 1.0, "game_date": "2099-11-20", "kickoff": "2099-11-20T19:00:00-05:00"},
        {"player": "A Passer", "market": "ast", "side": "OVER", "line": 6.5, "odds": -115, "recommended": True,
         "stake_units": 0.9, "game_date": "2099-11-20", "kickoff": "2099-11-20T19:00:00-05:00"}],
        "game_bets": []}
    assert SP.stamp_tracked(board, "nba", _plan={}, today="2099-11-20") == 1
    assert board["recommendations"][0].get("tracked") and not board["recommendations"][1].get("tracked")
    for r in board["recommendations"]:
        r.pop("tracked", None)
    best, n = potd.board_best(board)
    assert best is not None and best["player"] == "A Passer" and n == 1, (best, n)
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'r.tracked ? "Tracked · no stake"' in app
    gate = (ROOT / "engine" / "gate.py").read_text(encoding="utf-8")
    assert "stakeplan.stamp_tracked(payload, sport)" in gate
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'and not _stakeplan_priced_out(r.get("odds")) and not r.get("tracked")),' in launch


def test_the_record_page_names_the_benched_markets():
    rec = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert "+ recBenchNote(d.staked, scope)" in rec
    i = rec.index("function recBenchNote(")
    body = rec[i:rec.index("\n}\n", i)]
    assert "benched_markets" in body and "Markets on the bench" in body and "escapeHtml(b.why" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
