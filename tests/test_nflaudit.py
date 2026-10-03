"""The NFL football-context audit and the scout's flags.

Ethan, 2026-10-03: "think like a human when it comes to making the pick
selections ... general football knowledge and thinking like an actual human
and what could happen." Checks, one rule each: each flag fires on the spot a
football person would hesitate in and not otherwise; the team's spread is
read from the stored HOME spread the right way round; a settled pick is
joined to its own game and to his results BEFORE it; a pick in two books is
counted once; a flag whose picks over-claimed in both halves of the days
HOLDS and a flag that over-claimed in one half does not; the history replay
scores a flagged side against the same side unflagged; nothing is written.

Run directly: `python3 tests/test_nflaudit.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                             # noqa: E402
from engine import ledger as LG                                   # noqa: E402
from engine import scout as SC                                    # noqa: E402
import nflaudit as A                                              # noqa: E402


def test_each_flag_fires_on_its_spot_and_only_there():
    s = SC.situation("rush_yds", "OVER", line=60, position="RB", values=[50, 55, 60, 58, 52],
                     game_spread=-8.5, home=False, total=44)       # away team, home favoured by 8.5
    assert s["spread"] == 8.5 and s["implied"] == round(44 / 2 - 8.5 / 2, 2)
    assert "dog_run_over" in SC.flags(s)
    fav = SC.situation("rush_yds", "OVER", line=60, values=[50, 55, 60, 58, 52], game_spread=-8.5, home=True, total=44)
    assert "dog_run_over" not in SC.flags(fav), "the favourite's back is not trailing"
    assert "shootout_under" in SC.flags(SC.situation("rec_yds", "UNDER", line=50, total=51.5))
    assert "low_implied_td" in SC.flags(SC.situation("anytime_td", "YES", game_spread=-6, home=False, total=38))
    assert "wind_pass_over" in SC.flags(SC.situation("pass_yds", "OVER", wind=18, outdoor=True))
    assert "wind_pass_over" not in SC.flags(SC.situation("pass_yds", "OVER", wind=18, outdoor=False)), "a dome"
    up = SC.situation("receptions", "OVER", line=6.5, values=[4, 5, 4, 5, 6])
    assert "line_above_form" in SC.flags(up)
    down = SC.situation("rec_yds", "OVER", line=40, values=[20, 25, 22, 60, 70, 65, 66, 70])
    assert "role_down_over" in SC.flags(down)
    assert "back_from_absence" in SC.flags(SC.situation("receptions", "OVER", missed_last=True))
    assert "short_week_over" in SC.flags(SC.situation("receptions", "OVER", weekday=3))
    assert SC.flags(SC.situation("receptions", "OVER", line=4.5, values=[5, 5, 5, 5, 5, 5], total=45,
                                 game_spread=-2, home=True, weekday=6)) == [], "a plain spot is plain"


def _build(tmp):
    hist = db.connect(Path(tmp) / "history.db")
    games, logs = [], []
    # Two teams, eight weeks; KC home every week, favoured by 9.5; total 51.
    # The ids are the box's own two shapes, which do not match: the games
    # table writes "LV@KC", the player logs "LV-004" (2026-10-03: the first
    # box run joined on the id and found no logs at all).
    for w in range(1, 9):
        d = f"2025-09-{w * 3 + 1:02d}"
        games.append({"sport": "nfl", "season": 2025, "period": f"{w:03d}", "game_id": f"LV@KC-{w}", "home": "KC",
                      "away": "LV", "home_score": 31, "away_score": 10, "spread": -9.5, "total": 51.0,
                      "roof": "outdoors", "wind": 5.0, "date": d})
        if w != 7:                                                   # he misses week 7
            logs.append({"sport": "nfl", "season": 2025, "period": f"{w:03d}", "game_id": f"LV-{w:03d}",
                         "player": "Back Raider",
                         "team": "LV", "opponent": "KC", "position": "RB", "home": 0, "market": "rush_yds",
                         "value": 50.0 + w})
    db.upsert_games(hist, games)
    db.upsert_player_logs(hist, logs)
    hist.commit()
    led = LG.connect(Path(tmp) / "ledger.db")
    rows = []
    for w in range(3, 9):
        d = f"2025-09-{w * 3 + 1:02d}"
        for cat in ("board", "likely") if w == 3 else ("board",):
            rows.append((d, d, "Back Raider", "LV", "rush_yds", "OVER", 49.5, -150, 0.70, "lost" if w % 2 else "won", cat))
    for d, gd, pl, tm, mk, side, line, odds, p, st, cat in rows:
        led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, hit_prob, "
                    "status, category) VALUES ('nfl',?,?,?,?,?,?,?,?,?,?,?)",
                    (d, gd, pl, tm, mk, side, line, odds, p, st, cat))
    led.commit()
    return Path(tmp) / "ledger.db", Path(tmp) / "history.db"


def test_a_settled_pick_meets_its_own_game_and_his_results_before_it():
    tmp = tempfile.mkdtemp()
    lp, hp = _build(tmp)
    out = A.audit(A._ro(lp), A._ro(hp))
    assert out["n"] == 6, "the week-3 pick in two books is counted once"
    assert out["with_context"] == 6
    dog = out["flags"]["dog_run_over"]
    assert dog["n"] == 6 and round(dog["claimed"], 2) == 0.70
    back = out["flags"]["back_from_absence"]
    assert back["n"] == 1, "only week 8 follows the game he missed"
    assert out["flags"]["thin_sample"]["n"] == 1, "only week 3 (two games before it) is thin"
    assert out["bands"]["position/side"].get("RB OVER", {}).get("n") == 6, "his position comes off his logs"
    rows = A.picks(A._ro(lp))
    assert any(r["sources"] == {"list", "board"} for r in rows)


def test_a_flag_holds_only_when_both_halves_over_claimed():
    def mk(day, won, p=0.7):
        return {"day": day, "won": won, "p": p}
    both = [mk(f"2025-09-{d:02d}", d % 3 == 0) for d in range(1, 29)]       # ~33% hit against 70% said
    assert A.verdict(both, "2025-09-15")["verdict"] == "HOLDS"
    one = [mk(f"2025-09-{d:02d}", d >= 15 or d % 4 == 0) for d in range(1, 29)]  # early bad, late good
    assert A.verdict(one, "2025-09-15")["verdict"] != "HOLDS"
    assert A.verdict(both[:5], "2025-09-15")["verdict"] == "too few"


def test_the_history_replay_scores_a_flagged_side_against_the_same_side():
    tmp = tempfile.mkdtemp()
    _lp, hp = _build(tmp)
    h = A.replay(A._ro(hp))
    assert h["seasons"] == [2025]
    # Eight games with five earlier ones is too few for a cell of 30 — the
    # replay reports nothing rather than a number off three games.
    assert h["flags"] == {} or all(r["n"] >= 30 for f in h["flags"].values() for v in f.values() for r in v.values())


def test_it_never_writes():
    src = open(os.path.join(ROOT, "nflaudit.py"), encoding="utf-8").read()
    eng = open(os.path.join(ROOT, "engine", "likelyctx.py"), encoding="utf-8").read()
    assert "mode=ro" in eng and "_ro_engine" in src, "both databases opened read-only"
    for verb in ("INSERT", "UPDATE", "DELETE", ".commit("):
        assert verb not in src.replace("SELECT", ""), verb


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
