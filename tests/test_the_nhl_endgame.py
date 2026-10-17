"""The NHL endgame: score effects and the pulled goalie, priced only once they hold.

Ethan, 2026-10-17: "create models and features that don't exist ... new
equations and methods". engine/nhl/endgame replaces the steady-rate regulation
model with a time-and-score Markov chain whose multipliers are fitted from
every regulation goal on the clock, and gates it behind a held-out verdict.

Pinned here: the play file says when the shooter's own goalie was pulled and
when every goal went in, and the goal clock is stored; a game whose goals lack
the clock is read again by the nightly backfill; a chain with every multiplier
at 1 is the old model; whatever the multipliers, each side keeps the expected
goals it was given; an empty-net endgame makes two-goal finishes likelier; the
fit finds a pulled goalie in games that had one, and none in games that did
not; a half-read play file never trains or scores; the held-out verdict holds
on seasons drawn from an endgame process and does not on seasons drawn from a
steady one; the build prices with the chain only when the saved verdict holds;
and the card says so in one line.

Offline: synthetic seasons from a fixed seed, a temporary history database and
models directory.

Run directly: `python3 tests/test_the_nhl_endgame.py`
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import db                                              # noqa: E402
from engine.nhl import endgame as E, model as M                    # noqa: E402
from engine.sources import nhlpbp                                  # noqa: E402

TEAMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
#: The "true" endgame the synthetic seasons are drawn from: down one in the
#: last two minutes the trailer scores ×3, the leader ×7 (the empty net).
TRUE_LATE = {"m59": {-1: 3.0, 1: 7.0}, "m60": {-1: 3.0, 1: 7.0}}


def _true_m(phase, diff):
    return TRUE_LATE.get(phase, {}).get(max(-1, min(1, diff)) if abs(diff) == 1 else 99, 1.0)


def _season(season, n_games, rng, endgame=True):
    """n_games synthetic finals, each side's goals drawn second by second."""
    strength = {t: 0.8 + 0.4 * rng.random() for t in TEAMS}
    out = []
    for i in range(n_games):
        home, away = rng.sample(TEAMS, 2)
        lh, la = 2.9 * strength[home] * 1.04, 2.9 * strength[away] / 1.04
        h = a = 0
        goals = []
        for t in range(0, E.REG_S, 10):
            ph = E._phase(t + 5)
            mh = _true_m(ph, h - a) if endgame else 1.0
            ma = _true_m(ph, a - h) if endgame else 1.0
            u = rng.random()
            if u < lh / 360 * mh:
                goals.append((t + 5, True))
                h += 1
            elif u < lh / 360 * mh + la / 360 * ma:
                goals.append((t + 5, False))
                a += 1
        final = (h + 1, a) if h == a and rng.random() < 0.52 else ((h, a + 1) if h == a else (h, a))
        out.append({"gid": season * 10000 + i, "season": season, "date": f"{season}-11-{1 + i % 28:02d}",
                    "home": home, "away": away, "goals": goals, "final": final, "reg": (h, a)})
    return out


def test_the_play_file_says_who_pulled_his_goalie_and_when_each_goal_went_in():
    # situation code: away goalie, away skaters, home skaters, home goalie
    assert nhlpbp.own_pulled("1650", home_shooter=True) == 1, "home side, its goalie out"
    assert nhlpbp.own_pulled("1650", home_shooter=False) == 0
    assert nhlpbp.own_pulled("0651", home_shooter=False) == 1, "away side, its goalie out"
    assert nhlpbp.own_pulled("1551", home_shooter=True) == 0
    assert nhlpbp.own_pulled("", home_shooter=True) == 0, "an unreadable code is not a pulled goalie"
    assert "t" in db.NHL_SHOT_COLS and "pulled" in db.NHL_SHOT_COLS


def test_a_chain_with_every_multiplier_at_one_is_the_old_model():
    flat = {"m": {p: {d: 1.0 for d in range(-3, 4)} for p, _, _ in E.PHASES}}
    a, b = E.game_probs(3.2, 2.6, flat, dt=10), M.game_probs(3.2, 2.6)
    for k in ("home_ml", "away_ml", "home_-1.5", "away_-1.5", "tie"):
        assert abs(a[k] - b[k]) < 0.01, (k, a[k], b[k])
    assert abs(a["totals"][6] - b["totals"][6]) < 0.01
    assert a["endgame"] is True and "endgame" not in b


def test_each_side_keeps_the_goals_it_was_given():
    strong = {"m": {p: {d: 1.0 for d in range(-3, 4)} for p, _, _ in E.PHASES}}
    strong["m"]["m60"] = {-1: 3.5, 1: 9.0, -2: 2.5, 2: 4.0, 0: 1.0, 3: 1.0, -3: 1.0}
    strong["m"]["early"] = {d: 1.0 + 0.06 * (-d) for d in range(-3, 4)}     # the score effect
    pr = E.game_probs(3.4, 2.5, strong, dt=10)
    P = E._run(3.4, 2.5, strong, 1.0, 1.0, 10)
    eh, ea = E._means(P)
    assert abs(eh - 3.4) > 0.01 or abs(ea - 2.5) > 0.01, "the raw chain moves the means; the rescale must matter"
    # Read the means back off the priced distribution's margins.
    exp_total = sum(t * p for t, p in pr["totals"].items()) - pr["tie"]   # take the decider back out
    assert abs(exp_total - (3.4 + 2.5)) < 0.03, exp_total


def test_an_empty_net_endgame_makes_two_goal_finishes_likelier():
    late = {"m": {p: {d: 1.0 for d in range(-3, 4)} for p, _, _ in E.PHASES}}
    late["m"]["m59"] = late["m"]["m60"] = {**{d: 1.0 for d in range(-3, 4)}, -1: 3.0, 1: 7.0}
    a, b = E.game_probs(3.0, 2.8, late, dt=10), M.game_probs(3.0, 2.8)
    assert a["home_-1.5"] + a["away_-1.5"] > b["home_-1.5"] + b["away_-1.5"] + 0.03
    assert a["tie"] > b["tie"] - 0.005, "the extra attacker's goals tie games as well"
    line = E.note(a, 3.0, 2.8)
    assert line and "pulls its goalie" in line and "%" in line
    assert E.note(b, 3.0, 2.8) is None, "the old model's numbers carry no endgame note"


def test_the_fit_finds_a_pulled_goalie_where_there_was_one_and_not_where_there_was_not():
    rng = random.Random(7)
    with_net = _season(2023, 900, rng, endgame=True)
    got = E.fit(with_net)["m"]
    assert got["m60"][1] > 2.5 and got["m60"][-1] > 1.6, got["m60"]
    assert 0.85 < got["early"][0] < 1.15, got["early"]
    steady = E.fit(_season(2023, 900, random.Random(8), endgame=False))["m"]
    assert steady["m60"][1] < 1.8, steady["m60"]


def test_a_half_read_play_file_never_trains_or_scores():
    t = Path(tempfile.mkdtemp())
    H = db.connect(t / "h.db")

    def game(gid, hs, as_, ended):
        H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score, extra) "
                  "VALUES ('nhl', 2025, '2025-11-01', ?, '2025-11-01', 'AAA', 'BBB', ?, ?, ?)",
                  (f"BBB@AAA{gid}", hs, as_, json.dumps({"nhl_id": gid, "ended_in": ended})))

    def goal(gid, ev, team, period, t):
        H.execute("INSERT INTO nhl_shots (game_id, event_id, team, kind, is_goal, period, t, assist1) "
                  "VALUES (?, ?, ?, 'goal', 1, ?, ?, '')", (gid, ev, team, period, t))
    game(1, 3, 1, "REG")
    goal(1, 1, "AAA", 1, 400), goal(1, 2, "BBB", 2, 1500), goal(1, 3, "AAA", 3, 3000), goal(1, 4, "AAA", 3, 3590)
    game(2, 2, 1, "OT")                                      # a tie after sixty minutes, won in overtime
    goal(2, 1, "AAA", 1, 100), goal(2, 2, "BBB", 3, 3500), goal(2, 3, "AAA", 4, 3700)
    game(3, 4, 2, "REG")                                     # the play file is missing a goal
    goal(3, 1, "AAA", 1, 100), goal(3, 2, "BBB", 2, 1300)
    game(4, 2, 0, "REG")                                     # no clock yet (stored before 2026-10-17)
    H.execute("INSERT INTO nhl_shots (game_id, event_id, team, kind, is_goal, period, assist1) "
              "VALUES (4, 1, 'AAA', 'goal', 1, 1, '')")
    H.commit()
    got = {g["gid"]: g for g in E.load_games(H)}
    assert set(got) == {1, 2}, sorted(got)
    assert got[1]["reg"] == (3, 1) and got[2]["reg"] == (1, 1)
    assert got[1]["goals"][-1] == (3590, True)
    # And the nightly backfill reads the unclocked game's play file again.
    seen = []
    nhlpbp.backfill(H, fetch=lambda gid: seen.append(gid) or {"id": gid, "plays": []})
    assert seen == [4], seen


def test_the_verdict_holds_on_an_endgame_league_and_not_on_a_steady_one():
    saved = E.MIN_TRAIN_GAMES
    E.MIN_TRAIN_GAMES = 100
    try:
        rng = random.Random(11)
        league = _season(2023, 300, rng) + _season(2024, 300, rng) + _season(2025, 300, rng)
        v = E.heldout(league, dt=60)
        assert v["holds"], v["why"]
        assert [f["season"] for f in v["folds"]] == [2024, 2025]
        tg = v["folds"][-1]["two_goal_finish"]
        miss_end, miss_plain = abs(tg["endgame"] - tg["actual"]), abs(tg["plain"] - tg["actual"])
        assert miss_end + 0.03 < miss_plain, ("two-goal finishes: the chain's miss is the smaller by a margin", tg)
        rng = random.Random(12)
        flat = (_season(2023, 300, rng, False) + _season(2024, 300, rng, False)
                + _season(2025, 300, rng, False))
        assert not E.heldout(flat, dt=60)["holds"], "a steady league gives the chain nothing to win"
        assert E.heldout(league[:50], dt=60)["holds"] is False
    finally:
        E.MIN_TRAIN_GAMES = saved


def test_the_build_prices_with_the_chain_only_once_it_holds():
    late = {"m": {p: {str(d): 1.0 for d in range(-3, 4)} for p, _, _ in E.PHASES}}
    late["m"]["m60"].update({"-1": 3.0, "1": 7.0})
    plain = M.game_probs(3.0, 2.7)
    E.save({"fit": late, "verdict": {"holds": False, "why": "not yet"}})
    assert E.priced(3.0, 2.7) == plain, "a verdict that does not hold leaves the old model"
    E.save({"fit": late, "verdict": {"holds": True, "why": "held"}})
    got = E.priced(3.0, 2.7)
    assert got.get("endgame") and got["home_-1.5"] != plain["home_-1.5"], "a holding verdict prices with the chain"
    os.unlink(os.path.join(os.environ["QB_MODELS_DIR"], E.STORE))
    assert E.priced(3.0, 2.7) == plain, "no store: the old model"
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    i = src.index("def game_bets(")
    assert "probs = EG.priced(*lam)" in src[i:i + 4000] and "EG.note(probs, *lam)" in src[i:i + 4000]


def test_the_command_reads_saves_and_says_its_verdict():
    import contextlib
    import io
    t = Path(tempfile.mkdtemp())
    H = db.connect(t / "h.db")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = E.run(H)
    assert res["verdict"]["holds"] is False and "0 NHL finals" in out.getvalue()
    assert 'if __name__ == "__main__":' in (ROOT / "engine" / "nhl" / "endgame.py").read_text(encoding="utf-8")


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
