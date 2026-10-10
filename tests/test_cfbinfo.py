"""The college information test: every input on disk, against the close.

Ethan, 2026-09-07: "make sure you do the same exact work to make CFB
just as good."

`engine.cfbinfo` is `engine.nflinfo`'s question asked of college: with
the closing number as a fixed offset, does anything computable from
earlier games still predict the outcome? The walk must see only the
past; the starter must be whoever threw for the most yards; a bye must
be twelve days off and not the first game of the season; the report
must be the shared one, with college's own feature lists; and what it
measured must be on the record.

Run directly: `python3 tests/test_cfbinfo.py`
"""

import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine import cfbinfo as C                              # noqa: E402
from engine import nflinfo as N                              # noqa: E402


def _row(season, date, home, away, hs, as_, ml=(-110, -110), spread=-3.0,
         total=52.0, neutral=False):
    extra = {"ml": list(ml), "neutral": neutral}
    return {"sport": "cfb", "season": season, "period": date,
            "game_id": f"{season}-{date}-{away}@{home}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": spread, "total": total,
            "roof": None, "surface": None, "temp": None, "wind": None,
            "extra": json.dumps(extra)}


def _db(games, logs=()):
    conn = db.connect(":memory:")
    db.upsert_games(conn, games)
    conn.executemany(
        "INSERT INTO player_game_logs (sport, season, period, game_id, player, team, "
        "opponent, position, home, market, value) VALUES ('cfb',?,?,?,?,?,?,?,?,?,?)", logs)
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def _saturday(season, wk):
    return str(datetime.date(season, 9, 5) + datetime.timedelta(days=7 * (wk - 1)))


def _season(season, teams=("A", "B", "C", "D"), weeks=8, skip=None, passer=None):
    """A round of games on consecutive Saturdays; A beats everyone, D
    loses to everyone. ``skip`` is ``(team, week)`` — that team's game
    that week is not played (a bye). ``passer`` overrides a team's
    starter for a week: ``{(team, week): name}``."""
    games, logs = [], []
    order = [("A", "B", "C", "D"), ("A", "C", "B", "D"), ("A", "D", "B", "C")]
    for wk in range(1, weeks + 1):
        date = _saturday(season, wk)
        h1, a1, h2, a2 = order[wk % 3]
        for h, a in ((h1, a1), (h2, a2)):
            if skip and skip[1] == wk and skip[0] in (h, a):
                continue
            hs, as_ = (30, 10) if h < a else (10, 30)
            games.append(_row(season, date, h, a, hs, as_))
            for team, opp in ((h, a), (a, h)):
                qb = (passer or {}).get((team, wk), f"QB-{team}")
                logs.append((season, date, f"g{wk}", qb, team, opp, "QB",
                             1 if team == h else 0, "pass_yds", 240.0))
    return games, logs


def test_the_walk_sees_only_the_past():
    games, logs = _season(2023)
    rows = {(r.season, r.period): r for r in C.build_rows(_db(games, logs))}
    first = rows[(2023, _saturday(2023, 1))]
    # No prior game anywhere: no rating, no rest, no drift, no starter.
    assert "pts_wp" not in first.f and "rest_h" not in first.f and "drift_h" not in first.f
    assert "qb_change_h" not in first.f
    late = rows[(2023, _saturday(2023, 8))]
    assert "pts_wp" in late.f and "drift_diff" in late.f and "rest_diff" in late.f
    # Rest is seven days between consecutive Saturdays, and not a bye.
    assert late.f["rest_h"] == 7.0 and late.f["bye_h"] == 0.0


def test_the_starter_is_whoever_threw_for_the_most_and_a_change_is_noticed():
    games, logs = _season(2023, passer={("B", 7): "Backup-B"})
    # The usual starter also threw that week, for forty yards in relief:
    # the starter is the passer with the MOST yards, so the week reads
    # as a change and not as the usual man with a backup behind him.
    logs.append((2023, _saturday(2023, 7), "g7", "QB-B", "B", "A", "QB", 1, "pass_yds", 40.0))
    rows = C.build_rows(_db(games, logs))
    r = next(r for r in rows if r.period == _saturday(2023, 7) and "B" in (r.home, r.away))
    side = "h" if r.home == "B" else "a"
    assert r.f[f"qb_change_{side}"] == 1.0 and r.f[f"qb_starts_{side}"] == 0.0
    assert r.f["qb_new_diff"] == (1.0 if side == "h" else -1.0)
    r6 = next(r for r in rows if r.period == _saturday(2023, 6) and "B" in (r.home, r.away))
    side6 = "h" if r6.home == "B" else "a"
    assert r6.f[f"qb_change_{side6}"] == 0.0


def test_a_bye_is_twelve_days_off_and_never_the_first_game():
    games, logs = _season(2023, skip=("C", 5))
    rows = C.build_rows(_db(games, logs))
    r = next(r for r in rows if r.period == _saturday(2023, 6) and "C" in (r.home, r.away))
    side = "h" if r.home == "C" else "a"
    assert r.f[f"rest_{side}"] == 14.0 and r.f[f"bye_{side}"] == 1.0, r.f
    other = "a" if side == "h" else "h"
    assert r.f[f"bye_{other}"] == 0.0 and r.f["bye_diff"] == (1.0 if side == "h" else -1.0)
    # An opener is not a bye: the season's first game has no rest feature.
    first = next(r for r in rows if r.period == _saturday(2023, 1))
    assert "bye_h" not in first.f and "rest_h" not in first.f


def test_a_neutral_site_is_read_off_the_schedule_and_drops_the_home_field():
    """The same last game, played at home and on a neutral field: the
    flag flips, and the projected margin loses exactly the home field —
    the prior's, since a fixture this small never fits its own."""
    from engine.cfb import ratings as CR
    games, logs = _season(2023)
    g = games[-1]
    at_home = C.build_rows(_db(games, logs))[-1]
    games[-1] = _row(2023, _saturday(2023, 8), g["home"], g["away"],
                     g["home_score"], g["away_score"], neutral=True)
    neutral = C.build_rows(_db(games, logs))[-1]
    assert (at_home.home, at_home.away) == (neutral.home, neutral.away)
    assert at_home.f["neutral"] == 0.0 and neutral.f["neutral"] == 1.0
    assert abs((at_home.f["pts_margin"] - neutral.f["pts_margin"]) - CR.PRIOR.home_field) < 1e-9
    assert neutral.f["pts_wp"] < at_home.f["pts_wp"]


def test_the_report_is_the_shared_one_with_colleges_own_features():
    games22, logs22 = _season(2022)
    games23, logs23 = _season(2023)
    lines = C.report(C.build_rows(_db(games22 + games23, logs22 + logs23)),
                     train=(2022,), test=(2023,))
    assert lines[0].startswith("CFB information test · train (2022,)")
    text = "\n".join(lines)
    for name in C.ML_FEATURES:
        assert name in text, name
    assert "SPREAD — each feature alone" in text and "TOTAL — each feature alone" in text
    # It is nflinfo's table, parametrised — not a college copy.
    import inspect
    assert "report_for(" in inspect.getsource(C.report)
    assert "report_for(rows, \"NFL\"" in inspect.getsource(N.report)


def test_the_measurement_and_its_verdict_are_on_the_record():
    doc = C.__doc__
    assert "MEASURED 2026-09-07" in doc, "the college information test has not recorded its result"
    # The table as printed, and the verdict as ruled.
    for cell in ("qb_change_diff   train −0.392 ± 0.114** test −0.172 ± 0.114",
                 "pts_gap          train −0.108 ± 0.112   test −0.038 ± 0.093",
                 "log-loss WORSE by 0.0141", "Nothing holds at the bar",
                 "Nothing here is shipped"):
        assert cell in doc, cell
    # The near miss is pre-registered with the number that decides it,
    # and the number is the one the table printed.
    w = C.QB_CHANGE_WATCH
    assert w["feature"] == "qb_change_diff" and w["market"] == "moneyline"
    assert w["measured"]["train"] == (-0.392, 0.114) and w["measured"]["test"] == (-0.172, 0.114)
    assert w["test_seasons"] == (2024, 2025, 2026) and "two standard errors" in w["decides"]
    # …and nothing reads it: a watch is not a feature.
    import inspect
    from engine import gamebets, gamecal
    import cfb_build
    for mod in (gamebets, gamecal, cfb_build):
        assert "QB_CHANGE_WATCH" not in inspect.getsource(mod), mod.__name__


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
