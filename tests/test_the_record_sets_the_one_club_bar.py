"""The record sets the one-club bar for each game's parlays and touchdown pairs.

Ethan, 2026-11-16, asked whether the bar for a ticket all of one team's (4
points likelier than the best ticket with both sides, 3 research points for
a touchdown pair) was right: "idk whatever is best". What is best is what the
record shows. engine/gameparlays.fit_side_bar runs after each settle pass
that moved a ticket (engine/maintenance). It splits every settled game
parlay into one-club and two-club tickets by its legs' teams (side_record)
and compares how each hit against the chance it was posted at. One-club
tickets that hit below their posted chance more than two-club ones do need
a bigger edge, and ones above it a smaller one. The comparison is shrunk
toward "no difference" by SIDE_PRIOR_N tickets, waits for SIDE_MIN_N of each,
and the bar never leaves its ranges. `choose` reads the bar in force
(side_bar), and the build log says it.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402
from engine import parlayledger as PL  # noqa: E402


class _Models:
    """A models directory of the test's own, put back after."""
    def __enter__(self):
        self.was = os.environ.get("QB_MODELS_DIR")
        os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
        return self

    def __exit__(self, *exc):
        if self.was is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = self.was


def _ledger(groups):
    """An in-memory ledger: groups of (source, teams per ticket, n, won, joint)."""
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)
    k = 0
    for source, teams, n, won, joint in groups:
        for i in range(n):
            k += 1
            cur = conn.execute(
                "INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, source, status, modeled_joint) "
                "VALUES ('2026-11-16', 'nfl', '2026-11-16', ?, 'same_game', ?, ?, ?, ?)",
                (f"k{k}", len(teams), source, "won" if i < won else "lost", joint))
            for j, team in enumerate(teams, start=1):
                conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status) "
                             "VALUES (?, ?, ?, ?, 'receptions', 'OVER', 3.5, 'won')", (cur.lastrowid, j, f"P{j}", team))
    # An open ticket and a void one never count.
    cur = conn.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, source, status, "
                       "modeled_joint) VALUES ('x', 'nfl', 'x', 'open1', 'same_game', 2, 'game_three', 'open', 0.4)")
    conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status) "
                 "VALUES (?, 1, 'X', 'SF', 'receptions', 'OVER', 3.5, 'open')", (cur.lastrowid,))
    return conn


ONE, TWO = ["SF", "SF", "SF"], ["SF", "DAL", "SF"]


def test_the_record_splits_one_club_from_two_club_tickets():
    conn = _ledger([("game_three", ONE, 4, 1, 0.3), ("game_three", TWO, 6, 3, 0.25),
                    ("game_td", ["SF", "SF"], 2, 0, 0.2), ("game_td", ["SF", "DAL"], 3, 1, 0.2)])
    rec = GP.side_record(conn)
    assert rec["three"]["one"] == {"n": 4, "won": 1, "expected": 1.2}, rec
    assert rec["three"]["two"] == {"n": 6, "won": 3, "expected": 1.5}, rec
    assert rec["scorers"]["one"]["n"] == 2 and rec["scorers"]["two"]["n"] == 3, rec


def test_until_enough_settle_the_bar_is_the_default_and_says_why():
    with _Models():
        conn = _ledger([("game_three", ONE, 10, 2, 0.35), ("game_three", TWO, 40, 14, 0.35)])
        fit = GP.fit_side_bar(conn)
        assert fit["three"] == {"bar": GP.SIDE_EDGE, "fitted": False,
                                "why": f"waiting on the record: 10 one-club and 40 two-club ticket(s) settled, "
                                       f"{GP.SIDE_MIN_N} of each needed"}, fit["three"]
        assert GP.side_bar() == (GP.SIDE_EDGE, GP.SIDE_RESEARCH, False)


def test_one_club_tickets_hitting_short_of_their_chance_raise_the_bar_inside_its_range():
    with _Models():
        # One-club tickets hit half their posted chance, two-club ones all of it.
        conn = _ledger([("game_three", ONE, 40, 7, 0.35), ("game_three", TWO, 40, 14, 0.35),
                        ("game_td", ["SF", "SF"], 40, 4, 0.2), ("game_td", ["SF", "DAL"], 40, 8, 0.2)])
        fit = GP.fit_side_bar(conn)
        three, pairs = fit["three"], fit["scorers"]
        assert three["fitted"] and three["q"] == 0.5 and three["q_shrunk"] == 0.8, three
        # 4 points and 35% x (1 - 0.8) = 11 points, held at the range's 10.
        assert three["bar"] == GP.SIDE_EDGE_RANGE[1], three
        assert three["why"] == "one-club tickets hit 50% of their posted chance over 40, two-club 100% over 40"
        assert pairs["bar"] == 5, pairs
        assert GP.side_bar() == (0.10, 5, True), "the board reads the fit"
        # A one-club ticket 6 points likelier: taken at the default bar, not at this one.
        legs = lambda t, p: [{"player": f"{t}{i}", "team": t, "market": "receptions", "side": "Over",  # noqa: E731
                              "line": 3.5, "p": p} for i in range(3)]
        sf = {"legs": legs("SF", 0.8), "joint": 0.46}
        mixed = {"legs": legs("SF", 0.8)[:2] + legs("DAL", 0.7)[:1], "joint": 0.40}
        mixed["legs"][2]["player"] = "DAL9"
        got = GP.choose([sf, mixed], 1)
        assert got[0]["legs"][2]["team"] == "DAL", "10 points needed, 6 is not enough"


def test_one_club_tickets_beating_their_chance_lower_the_bar_to_its_floor():
    with _Models():
        conn = _ledger([("game_three", ONE, 40, 21, 0.35), ("game_three", TWO, 40, 14, 0.35),
                        ("game_td", ["SF", "SF"], 40, 12, 0.2), ("game_td", ["SF", "DAL"], 40, 8, 0.2)])
        fit = GP.fit_side_bar(conn)
        assert fit["three"]["bar"] == GP.SIDE_EDGE_RANGE[0] and fit["scorers"]["bar"] == 2, fit
        assert GP.side_bar()[:2] == (0.02, 2)


def test_a_broken_file_falls_back_to_the_defaults():
    with _Models():
        from engine import modelstate
        p = modelstate.path(GP.SIDE_BAR_FILE)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        Path(p).write_text("{not json", encoding="utf-8")
        assert GP.side_bar() == (GP.SIDE_EDGE, GP.SIDE_RESEARCH, False)
        assert GP.SIDE_BAR_ERROR and GP.SIDE_BAR_ERROR.startswith("JSONDecodeError"), "a broken file is said"
        gp = {"counts": {"side_bar": {"edge": 0.04, "research": 3, "fitted": False, "error": GP.SIDE_BAR_ERROR}}}
        assert "(the defaults: its fit could not be read (JSONDecodeError" in GP.summary(gp), GP.summary(gp)
        os.remove(p)
        assert GP.side_bar() == (GP.SIDE_EDGE, GP.SIDE_RESEARCH, False) and GP.SIDE_BAR_ERROR is None, \
            "no file is the quiet state before the first fit"
        Path(p).write_text('{"three": {"bar": 0.9, "fitted": true}, "scorers": {"bar": 40, "fitted": true}}',
                           encoding="utf-8")
        assert GP.side_bar()[:2] == (GP.SIDE_EDGE_RANGE[1], GP.SIDE_RESEARCH_RANGE[1]), "never outside its range"


def test_the_build_log_says_the_bar_and_maintenance_refits_it():
    gp = {"counts": {"games": 1, "threes": 4, "scorers": 3, "one_club_threes": 1, "one_club_scorers": 0,
                     "side_bar": {"edge": 0.04, "research": 3, "fitted": False}}}
    assert GP.summary(gp).endswith(f"; one-club bar 4 points, 3 research points (the defaults until "
                                   f"{GP.SIDE_MIN_N} of each settle)"), GP.summary(gp)
    gp["counts"]["side_bar"] = {"edge": 0.07, "research": 4, "fitted": True}
    assert GP.summary(gp).endswith("; one-club bar 7 points, 4 research points (set by the record)")
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = m.index("parlayledger.settle(lconn)")
    assert i < m.index("gameparlays.fit_side_bar(lconn)") < m.index('lap("parlays")', i), "after the settle pass"


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
