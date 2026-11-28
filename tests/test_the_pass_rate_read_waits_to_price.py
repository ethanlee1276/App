"""The pass-rate read as a price (step AIS, 28 November 2026): measured on play-by-play on top of a player's form,
what the defense allows the position and the line, it carries into completions and wide receivers' catches. A team
tendency priced against the league made the live model worse once (engine/teamcontext), so this one is a switchable
mode, off, that the backtest over real props judges first. The numbers below are made up for the fixtures."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import teamcontext as TC  # noqa: E402


def test_the_read_shades_only_the_markets_it_was_measured_on():
    f, why = TC.read_multiplier(0.05, "pass_cmp", "QB")
    assert abs(f - (1 + 0.46 * 0.05)) < 1e-9 and why and "throwing more" in why[0]
    f, _ = TC.read_multiplier(-0.05, "receptions", "WR")
    assert abs(f - (1 - 0.60 * 0.05)) < 1e-9
    # Not a tight end's or a back's catches, not yards, not carries, not attempts (a hair short of the rule).
    for market, pos in (("receptions", "TE"), ("receptions", "RB"), ("rec_yds", "WR"), ("rush_att", "RB"),
                        ("pass_att", "QB"), ("pass_yds", "QB")):
        assert TC.read_multiplier(0.05, market, pos) == (1.0, []), (market, pos)
    # Bounded, and quiet without a read.
    assert TC.read_multiplier(0.9, "pass_cmp")[0] == TC.READ_CLAMP[1]
    assert TC.read_multiplier(None, "pass_cmp") == (1.0, []) and TC.read_multiplier("x", "pass_cmp") == (1.0, [])
    assert TC.read_multiplier(0.01, "pass_cmp")[1] == [], "a nudge under 2% says nothing"


def test_a_week_reads_each_team_against_its_opponent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE team_units (sport TEXT, season INTEGER, period TEXT, team TEXT, side TEXT, opp TEXT, "
                 "plays INTEGER, dropbacks INTEGER, rushes INTEGER)")
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, home TEXT, away TEXT, "
                 "home_score REAL, away_score REAL)")
    conn.execute("CREATE TABLE team_weeks (sport TEXT, season INTEGER, period TEXT, team TEXT, plays INTEGER, "
                 "proe REAL)")
    pairs = {1: (("A", "B"), ("C", "D")), 2: (("A", "C"), ("B", "D")), 3: (("A", "D"), ("B", "C")),
             4: (("A", "B"), ("C", "D"))}
    rate = {"A": (40, 20), "B": (30, 30), "C": (33, 27), "D": (36, 24)}
    for wk, games in pairs.items():
        for x, y in games:
            for off, dfn in ((x, y), (y, x)):
                db, ru = rate[off]
                conn.execute("INSERT INTO team_units VALUES ('nfl', 2026, ?, ?, 'off', ?, ?, ?, ?)",
                             (f"{wk:03d}", off, dfn, db + ru, db, ru))
        for t, oe in (("A", 0.06), ("B", -0.04), ("C", 0.0), ("D", 0.01)):
            conn.execute("INSERT INTO team_weeks VALUES ('nfl', 2026, ?, ?, 60, ?)", (f"{wk:03d}", t, oe))
    ctx = TC.read_context(conn, 2026, 5, {"A": "C", "C": "A", "B": "D", "D": "B"})
    assert ctx["mode"] == "read" and set(ctx["reads"]) == {"A", "B", "C", "D"}
    from engine import passrun
    tab = passrun.tables(conn, 2026, 5)
    r = passrun.read(tab, "A", "C")
    assert ctx["reads"]["A"] == round(r["expect"] / r["own"] - 1.0, 4)
    assert TC.read_context(conn, 2026, 2, {"A": "C"}) == {}, "too few games: no read, no context"


def test_the_mode_is_wired_off_and_keeps_the_lines_script():
    proj = (ROOT / "engine" / "projection.py").read_text(encoding="utf-8")
    assert 'elif context.get("mode") == "read":' in proj and "read_multiplier((context.get(\"reads\")" in proj
    assert 'measured_context=bool(context) and context.get("mode") != "read"' in proj
    bt = (ROOT / "engine" / "backtest.py").read_text(encoding="utf-8")
    assert 'if use_team_context and team_context_mode == "read":' in bt and "read_context(_hc, season" in bt
    cli = (ROOT / "backtest.py").read_text(encoding="utf-8")
    assert 'choices=("level", "drift", "read")' in cli
    # Off: nothing on the live board passes a team context (only the backtest asks for one).
    import subprocess
    hits = subprocess.run(["grep", "-rln", "team_context=", "--include=*.py", str(ROOT / "engine"),
                           str(ROOT / "launch.py")], capture_output=True, text=True).stdout.split()
    assert sorted(Path(h).name for h in hits) == ["backtest.py", "pipeline.py"], hits


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
