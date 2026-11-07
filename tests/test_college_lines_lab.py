"""EXP-004c: the college two-stage results at the books' own lines — the joins and the one read.

research/exp4c_college_lines_box.py prices EXP-004's college models at the
lines the box's two stores hold, against the books' de-vigged consensus,
and decides each question once. What these hold: a quote lands on the game
its own start names, only before kickoff and never from too far out, the
last two-sided quote per book wins across both stores, and a quote two
same-named players could claim (or an NFL namesake's, a day apart) lands
nowhere; the schedule reads the mirror's file; every forecast is a chance
and the blend sits between its parts; a week is complete only when its
major-college games are final and in the play file; and each question is
decided on the first complete weeks that reach the minimum, the same on
every later run.

Run directly: `python3 tests/test_college_lines_lab.py`
"""
import csv
import datetime as dt
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import exp1_two_stage as E1                         # noqa: E402
from research import exp4c_college_lines_box as C4               # noqa: E402

UTC = dt.timezone.utc
K1 = dt.datetime(2026, 10, 3, 19, 30, tzinfo=UTC)
K2 = dt.datetime(2026, 10, 10, 19, 30, tzinfo=UTC)


def _snap(ts, start, book, line, over=-110, under=-110, player="Jo Smith", market="receptions"):
    row = {"ts": ts.timestamp(), "player": player, "market": market, "book": book, "line": line,
           "over_odds": over, "under_odds": under}
    if start is not None:
        row["start_ts"] = start.timestamp()
    return row


def test_a_quote_lands_on_the_game_its_own_start_names():
    kicks = {"jo smith": [(K1, "g1"), (K2, "g2")]}
    h = dt.timedelta(hours=1)
    snaps = [_snap(K1 - 3 * h, K1, "dk", 4.5), _snap(K1 - h, K1, "dk", 5.5),       # the later one wins
             _snap(K1 + h / 6, K1, "fd", 6.5),                                     # in play: dropped
             _snap(K1 - dt.timedelta(days=6), K1, "mgm", 3.5),                     # too far out
             _snap(K1 - 2 * h, K1 + dt.timedelta(hours=20), "cz", 9.5),            # an NFL namesake's Sunday
             _snap(K2 - 2 * h, None, "fd", 4.5)]                                   # no start: his next kickoff
    hist = [((K2 - dt.timedelta(days=2)).isoformat(), "Jo Smith", "receptions", "dk", 3.5, -120, 100, None),
            ((K2 - h).isoformat(), "Jo Smith", "receptions", "fd", 5.5, -105, -115, K2.isoformat()),
            ((K2 + h).isoformat(), "Jo Smith", "receptions", "mgm", 2.5, -130, 110, K2.isoformat()),
            ((K2 - h / 2).isoformat(), "Jo Smith", "receptions", "dk", 4.5, 120, None, K2.isoformat())]
    got = C4.gather(kicks, snaps, hist)
    assert got[("jo smith", "g1", "receptions")] == {"dk": (5.5, -110, -110)}
    assert got[("jo smith", "g2", "receptions")] == {"dk": (3.5, -120, 100), "fd": (5.5, -105, -115)}, \
        "the odds table's later fd quote beats the snapshot's; the in-play mgm one is dropped; " \
        "dk's later one-sided quote does not displace its last two-sided one"


def test_two_same_named_players_on_one_day_lose_the_quote():
    games = [(K1, "g1"), (K1 + dt.timedelta(hours=3), "g9")]
    assert C4.place(games, K1) is None
    assert C4.place(games[:1], K1 + dt.timedelta(hours=5)) == "g1"
    assert C4.next_game(games[:1], K1 - dt.timedelta(days=6)) is None, "more than LOOKAHEAD out"


def test_the_schedule_reads_the_mirrors_file():
    path = os.path.join(tempfile.mkdtemp(), "cfb_schedules_2026.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["game_id", "season", "week", "season_type", "start_date", "completed",
                    "home_division", "away_division"])
        w.writerow(["401", 2026, 9, "regular", "2026-10-25T00:00:00.000Z", "TRUE", "fbs", "fcs"])
        w.writerow(["402", 2026, 9, "regular", "2026-10-24T16:00:00.000Z", "FALSE", "ii", "ii"])
        w.writerow(["403", 2026, 16, "postseason", "2026-12-20T16:00:00.000Z", "FALSE", "fbs", "fbs"])
    s = C4.schedule(path)
    assert set(s) == {"401", "402"}, "a bowl is not the regular season"
    assert s["401"]["day"] == "2026-10-24", "an 8 pm Eastern kickoff is Saturday, not Sunday"
    assert s["401"]["done"] and s["401"]["fbs"] and not s["402"]["fbs"] and s["401"]["week"] == 9


def _rows(n, seed=4):
    """Made-up college player-games in EXP-001's row shape."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        if i % 2:
            mu_o, p = rng.uniform(3, 9), rng.uniform(0.55, 0.75)
            o = max(0, round(rng.gauss(mu_o, 1.8)))
            y = sum(rng.random() < p for _ in range(o))
            m, pos, mu_a = "receptions", "REC", mu_o * p
        else:
            mu_o, p = rng.uniform(8, 20), rng.uniform(3.5, 5.5)
            o = max(0, round(rng.gauss(mu_o, 3)))
            y = round(o * p + rng.gauss(0, 3 * max(1, o) ** 0.5))
            m, pos, mu_a = "rush_yds", "RB", mu_o * p
        out.append({"m": m, "s": 2026, "pos": pos, "who": f"P{i}|T|2026", "name": f"Player {i}", "team": "T",
                    "gid": f"g{i % 6}", "week": 6 + i % 6, "y": float(y), "o": float(o), "mu_a": mu_a,
                    "mu_o": mu_o, "opps": 4 * mu_o, "prod": 4 * mu_o * p})
    return out


def test_every_forecast_is_a_chance_and_the_blend_sits_between_its_parts():
    rows = _rows(600)
    fit = E1.Fit(rows)
    cals = C4.calibrators(fit, rows)
    assert {k for _m, k in cals} == {"A", "B", "H"}
    sched = {f"g{j}": {"day": (dt.date(2026, 10, 3) + dt.timedelta(days=7 * j)).isoformat()} for j in range(6)}
    props = {}
    for x in rows[:200]:
        line = (round(x["mu_a"]) + 0.5) if x["m"] == "receptions" else (round(x["mu_a"] / 5) * 5 + 0.5)
        props[(C4._norm(x["name"]), x["gid"], x["m"])] = {b: (line, -115, -105) for b in ("dk", "fd", "mgm")}
    sc = C4.scored(fit, cals, props, rows, sched)
    assert 150 <= len(sc) <= 200
    for r in sc:
        assert all(0 < r[k] < 1 for k in C4.KEYS), r
        lo, hi = sorted((r[C4.SHAPE[r["m"]]], r["C"]))
        assert lo - 1e-9 <= r["D"] <= hi + 1e-9
        assert r["after"] == (r["day"] > C4.FREEZE) and r["wk"] == f"2026-{r['week']:02d}"
    x = rows[1]
    same = dict(x, mu_a=fit.mean_b(x))
    got = C4.chances(fit, same, 4.5)
    assert abs(got["H"] - got["B"]) < 1e-12, "at B's own mean, H is B"


def _sched(weeks):
    """{gid: game} with ``weeks`` = {week: [(done, fbs), ...]}, Saturdays from October 24."""
    out = {}
    for wk, games in weeks.items():
        day = (dt.date(2026, 10, 24) + dt.timedelta(days=7 * (wk - 9))).isoformat()
        for j, (done, fbs) in enumerate(games):
            out[f"{wk}-{j}"] = {"week": wk, "day": day, "done": done, "fbs": fbs}
    return out


def test_a_week_is_complete_only_when_its_major_college_games_are_final_and_played():
    weeks = {8: [(True, True)], 9: [(True, True)] * 20 + [(False, False)], 10: [(True, True)] * 20,
             11: [(True, True)] * 20}
    sched = _sched(weeks)
    sched["8-0"]["day"] = "2026-10-17"
    played = {g for g in sched if not g.startswith("10-")} | {f"10-{j}" for j in range(18)}
    assert C4.complete_weeks(sched, played) == ([9], False), \
        "a lower-division game still open does not hold week 9; 18 of 20 played stops week 10, and 11 with it"
    played |= {"10-18"}
    assert C4.complete_weeks(sched, played) == ([9, 10, 11], True)


def test_each_question_is_decided_once_on_the_first_weeks_that_reach_the_minimum():
    def rows(week, market, n):
        return [{"week": week, "m": market} for _ in range(n)]
    post = rows(9, "receptions", 200) + rows(10, "receptions", 150) + rows(11, "receptions", 400)
    post += rows(9, "rush_yds", 50) + rows(10, "rush_yds", 50) + rows(11, "rush_yds", 50)
    chosen, how = C4.decision_weeks(post, [9, 10, 11], "receptions", False)
    assert chosen == (9, 10) and "first complete weeks" in how
    later = post + rows(12, "receptions", 900)
    assert C4.decision_weeks(later, [9, 10, 11, 12], "receptions", False)[0] == (9, 10), "fixed once reached"
    assert C4.decision_weeks(post, [9, 10, 11], "rush_yds", False) == ((), "NOT YET: 150 rows in complete weeks, 300 needed")
    assert C4.decision_weeks(post, [9, 10, 11], "rush_yds", True)[0] == (9, 10, 11), "the season's end decides on all"
    assert C4.decision_weeks(post[:-100], [9, 10, 11], "rush_yds", True)[1].startswith("NO DECISION")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
