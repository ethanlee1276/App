"""The game reports' parlays are built to win (PARLAYWIN1, 2026-11-19).

Ethan, 2026-11-19: "if the three-leg parlays aren't working and aren't making
money, then we're not making good selections and good picks ... Clearly we're
doing okay on the picks, but the parlays we make are not doing good, so work
on that, make those better."

What the record said (record.json, 19 November):

  * every graded ticket (2,085): the 1,321 priced with a positive link between
    their legs hit 382, where the link said 443 and the legs alone 407 — the
    link pushed our number further from the truth (z -3.7 with it, -1.5
    without), so a ticket's chance counts a positive link at the weight the
    record supports, 0 until it shows the linked legs hit together
    (`link_weight`, fitted nightly);
  * since the parlays were built from the report's own picks (17 November),
    hockey's three-leg tickets hit 4 of 10 and the NBA's two-leg ones 9 of 11,
    where a prop the report never picked hit 62% as a leg against the picks'
    75% (step WH): a game fills with the report's own picks first and takes
    another prop only at 60% or better;
  * a market benched for losing money (stakeplan.MARKET_BENCH) is no leg;
  * the bars a ticket clears are said without the link: two picks at 63%
    (40%), three at 63% (25%).

    python3 tests/test_the_parlays_are_built_to_win.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP, modelstate, parlayledger as PL  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                    # the shared fixture
GAME = EG.GAME


def _leg(player, market, p, team="NYG", pos="WR", side="Over", line=2.5):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": pos, "market": market, "market_label": market, "side": side,
            "line": line, "odds": -150, "book": "DraftKings", "p": p, "game_date": "2099-11-12"}


class _Models:
    """A models directory of the test's own, and the link's cache cleared."""

    def __enter__(self):
        self.was = os.environ.get(modelstate.ENV_VAR)
        self.dir = tempfile.mkdtemp()
        os.environ[modelstate.ENV_VAR] = self.dir
        GP._LINK.clear()
        return self

    def __exit__(self, *exc):
        if self.was is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = self.was
        GP._LINK.clear()


def _linked_pair():
    """A quarterback's yards and the receiver's: legs our relation links."""
    qb = _leg("Jaxson Dart", "pass_yds", 0.66, pos="QB", line=210.5)
    wr = _leg("Malik Nabers", "rec_yds", 0.65, line=60.5)
    fits, rho, _why, _cav = GP.pair_link("nfl", qb, wr, GAME)
    assert fits and rho > 0, ("the fixture needs a positive link", rho)
    return qb, wr


def test_a_positive_link_does_not_raise_a_tickets_chance_until_the_record_says_so():
    qb, wr = _linked_pair()
    with _Models():
        assert GP.link_weight() == GP.LINK_WEIGHT_DEFAULT == 0.0
        t = GP.ticket("nfl", [qb, wr], GAME)
        assert t["joint"] == round(0.66 * 0.65, 4), (t["joint"], "the legs alone")
        assert not t["links"], "a link we do not price is not said as one"
        # A fit that found the linked legs did hit together: the link counts.
        import json
        with open(modelstate.path(GP.LINK_FILE), "w") as f:
            json.dump({"weight": 1.0, "fitted": True}, f)
        GP._LINK.clear()
        assert GP.link_weight() == 1.0
        assert GP.ticket("nfl", [qb, wr], GAME)["joint"] > round(0.66 * 0.65, 4)
        # A file that cannot be read is said, and the default is in force.
        with open(modelstate.path(GP.LINK_FILE), "w") as f:
            f.write("{not json")
        GP._LINK.clear()
        assert GP.link_weight() == GP.LINK_WEIGHT_DEFAULT and GP.LINK_ERROR, GP.LINK_ERROR


def _record(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    for i, (m, ind, st) in enumerate(rows):
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status, modeled_joint, independent_joint)"
                  " VALUES ('2026-11-19T00:00:00','nba','2026-11-18',?,'same_game',3,'A@B',1,0,1,0,'game_three',?,?,?)",
                  (f"k{i}", st, m, ind))
    c.commit()
    return c


def test_the_link_weight_is_fitted_on_the_record():
    with _Models():
        # Too few linked tickets settled: the default, said why.
        few = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 20))
        assert few["weight"] == GP.LINK_WEIGHT_DEFAULT and not few["fitted"] and "waiting on the record" in few["why"]
        # 300 linked tickets that hit at the legs' own rate, 30%: the link earned nothing.
        flat = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 90 + [(0.34, 0.30, "lost")] * 210))
        assert flat["fitted"] and flat["raw"] == 0.0 and flat["weight"] == 0.0, flat
        # 300 that hit at the link's 34%: it earned all of it, shrunk toward the default.
        full = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 102 + [(0.34, 0.30, "lost")] * 198))
        assert full["raw"] == 1.0 and full["weight"] == round(300 / (300 + GP.LINK_PRIOR_N), 3), full
        GP._LINK.clear()
        assert GP.link_weight() == full["weight"], "the weight written is the weight read"
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "gameparlays.fit_link_weight(lconn)" in m, "fitted nightly with the one-club bar"


def test_a_prop_the_report_did_not_pick_fills_only_at_60():
    b = EG.board()
    b["most_likely"] = []
    b["td_field"] = []
    recs = [EG._rec("A One", "NYG", "WR", "receptions", "Over", 2.5, 0.72, -150),
            EG._rec("B Two", "WAS", "RB", "rush_yds", "Over", 40.5, 0.70, -150),
            EG._rec("C Three", "NYG", "TE", "rec_yds", "Over", 30.5, 0.68, -150),
            EG._rec("D Four", "WAS", "WR", "receptions", "Over", 3.5, 0.55, -150),   # no pick, under 60%
            EG._rec("E Five", "NYG", "RB", "rush_att", "Over", 12.5, 0.62, -150)]   # no pick, at 60%+
    b["recommendations"] = recs
    b["game_parlays"] = GP.build(b, "nfl")
    picks = [{"player": r["player"], "market": r["market"], "side": "OVER", "line": r["line"]} for r in recs[:3]]
    x = GP.from_report(b, "nfl", GAME, picks)
    legs = {l["player"] for t in x["threes"] for l in t["legs"]}
    assert "D Four" not in legs, "a prop the report never picked, under 60%, is no leg"
    assert len(x["threes"]) == GP.THREE_MIN and "E Five" in legs, "one at 60% fills the second ticket"


def test_a_benched_market_is_no_leg():
    b = EG.board()
    b["recommendations"] = [EG._rec("Jayden Daniels", "WAS", "QB", "pass_cmp", "Over", 19.5, 0.70, -150),
                            EG._rec("Jalen Hurts", "WAS", "QB", "pass_yds", "Over", 210.5, 0.70, -150)]
    got = {l["market"] for l in GP.legs_for(b, "nfl")}
    assert "pass_cmp" not in got and "pass_yds" in got, got


def test_the_bars_are_said_without_the_link():
    assert (GP.TWO_FLOOR, GP.THREE_FLOOR) == (0.40, 0.25)
    assert round(0.63 ** 3, 2) == GP.THREE_FLOOR and round(0.63 ** 2, 2) == GP.TWO_FLOOR


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
