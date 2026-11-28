"""The usage ripple is measured against the close before it prices
anything — and nothing prices from it yet.

Three synthetic worlds, seeded, no network, no box: one where the book
never priced a teammate's absence (the ripple carries information and
clears), one where the book priced it fully (the residual is noise and
the ripple is declined), and one too thin to say anything.
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, ripplefit as rf                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABSENT = (3, 4, 5, 9, 12, 15)
RATE = 4.5


def _world(book_prices_absence, teams: int = 6, seasons=(2025, 2026),
           noise: float = 12.0, seed: int = 7, over_odds: int = -110):
    """Each team: RB One ~60% of its carries, RB Two the rest; when One
    sits, Two takes most of it and Three the remainder — by a share and
    a volume that differ team to team, so the predicted extra varies.
    The book hangs a line on Two only. ``book_prices_absence`` is how
    much of the absence the close carries: 1.0 all of it, 0.0 none."""
    conn = db.connect(":memory:")
    rng = random.Random(seed)
    priced = float(book_prices_absence)
    logs, odds, dates = [], [], {}
    for season in seasons:
        for ti in range(teams):
            team = f"T{ti}"
            volume = 24 + (ti % 5) * 2                    # 24..32 carries
            take = 0.65 + (ti % 4) * 0.06                 # Two's share when One sits
            for w in range(1, 18):
                date = f"{season}-10-{w:02d}"
                dates[(season, w, team)] = date
                out = w in ABSENT
                two_in = round(volume * 0.4)
                two_out = round(volume * take)
                # NAMED PER TEAM: a close is keyed by player and date, as
                # the real table is, and one "RB Two" across twelve teams
                # on one Sunday would be twelve lines on one key.
                one, two, three = (f"RB One {team}", f"RB Two {team}", f"RB Three {team}")
                split = ({two: two_out, three: volume - two_out} if out
                         else {one: volume - two_in, two: two_in, three: 0})
                for p, c in split.items():
                    yds = max(0.0, c * RATE + (rng.gauss(0, noise) if c else 0.0))
                    for market, v in (("carries", float(c)), ("rush_yds", yds)):
                        logs.append({"sport": "nfl", "season": season,
                                     "period": f"{w:03d}", "game_id": f"{team}-{w}",
                                     "player": p, "team": team, "opponent": "X",
                                     "position": "RB", "home": 1,
                                     "market": market, "value": v})
                usual = two_in * RATE
                line = usual + priced * (split[two] * RATE - usual)
                odds.append({"sport": "nfl", "taken_at": f"{date}T18:00:00",
                             "event_id": f"{team}-{season}-{w}", "home": team,
                             "away": "X", "player": two, "market": "rush_yds",
                             "book": "dk", "line": line, "over_odds": over_odds,
                             "under_odds": -110})
    db.upsert_player_logs(conn, logs)
    db.upsert_odds_history(conn, odds)
    return conn, dates


def test_a_ripple_the_book_never_priced_clears():
    conn, dates = _world(book_prices_absence=0.0)
    rows = rf.build_rows(conn, dates=dates)
    assert len(rows) == 6 * 2 * len(ABSENT), len(rows)
    assert all(r.market == "rush_yds" and r.absent == f"RB One {r.team}" for r in rows)
    out = rf.fit(rows)
    m = out["markets"]["rush_yds"]
    assert m["verdict"] == "clears", m
    assert out["adopt"]["rush_yds"] is True
    assert m["resid_mean"] > 20, m                    # the book missed the absence
    assert "judged on 2026" in m["split"]
    assert m["bets"] >= rf.MIN_BETS and m["roi"] > 0
    assert m["judged_resid_mean"] > 2 * m["judged_resid_se"]
    # The size of the ripple orders the size of the miss, here.
    assert m["test_slope"] > 0, m
    # Measured only where the absence sample had cleared the floor.
    assert m["n_measured"] < m["n"]


def test_a_real_but_small_miss_that_cannot_pay_the_price_is_declined():
    """The close carries 93% of the absence and charges -300 on the
    over: the residual is measurably positive and the bet still loses.
    A coefficient that cannot pay the vig is a finding, not a model."""
    conn, dates = _world(book_prices_absence=0.93, teams=12, over_odds=-300)
    out = rf.fit(rf.build_rows(conn, dates=dates))
    m = out["markets"]["rush_yds"]
    assert m["judged_resid_mean"] > 2 * m["judged_resid_se"], m   # the miss is real
    assert m["roi"] < 0 and m["bets"] >= rf.MIN_BETS, m           # and it does not pay
    assert m["verdict"] == "declined" and "ROI" in m["reason"], m


def test_a_ripple_the_book_already_priced_is_declined():
    conn, dates = _world(book_prices_absence=1.0)
    out = rf.fit(rf.build_rows(conn, dates=dates))
    m = out["markets"]["rush_yds"]
    assert m["verdict"] == "declined", m
    assert out["adopt"]["rush_yds"] is False
    assert abs(m["resid_mean"]) < 4 * m["resid_se"], m   # noise around zero
    assert m.get("reason")


def test_a_bet_that_pays_on_price_alone_does_not_clear():
    """The close carries the whole absence and the over is +150: a coin
    flip at plus money shows a profit on this sample, and the residual
    says the market missed nothing. Profit without a miss is the price,
    not information — declined."""
    conn, dates = _world(book_prices_absence=1.0, teams=12, over_odds=150)
    out = rf.fit(rf.build_rows(conn, dates=dates))
    m = out["markets"]["rush_yds"]
    assert m["roi"] > 0 and m["bets"] >= rf.MIN_BETS, m
    assert m["verdict"] == "declined" and "already carries" in m["reason"], m


def test_too_thin_a_sample_is_not_enough_not_a_coefficient():
    conn, dates = _world(book_prices_absence=0.0, teams=1)
    out = rf.fit(rf.build_rows(conn, dates=dates))
    assert out["markets"]["rush_yds"]["verdict"] == "not enough"
    assert out["adopt"]["rush_yds"] is False
    assert "floor" in out["markets"]["rush_yds"]["reason"]
    # No absence at all: nothing to measure, and it says so.
    empty = rf.fit([])
    assert empty["markets"]["rush_yds"]["verdict"] == "not enough"


def test_absence_needs_a_real_role_and_a_played_week():
    conn, dates = _world(book_prices_absence=0.0, teams=1, seasons=(2026,))
    logs = rf.load_logs(conn, seasons=[2026])
    group = rf.KINDS["carries"]["group"]
    # RB Three carried nothing while One played: he is not "absent" on
    # a week his row is missing. RB One is.
    assert rf.absent_this_week(logs, 2026, 3, "T0", "carries", group) == ["RB One T0"]
    # Week 1: no earlier weeks to know anybody's role.
    assert rf.absent_this_week(logs, 2026, 1, "T0", "carries", group) == []
    # A bye — the team has no rows — is not an absence.
    assert rf.absent_this_week(logs, 2026, 30, "T0", "carries", group) == []


def test_the_verdict_is_stored_where_a_pricing_hook_would_read_it():
    conn, dates = _world(book_prices_absence=0.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = rf.run(conn, dates=dates, models_dir=tmp, log=lambda *a: None)
        assert out["measured_at"]
        back = rf.load(models_dir=tmp)
        assert back["adopt"] == out["adopt"]
        assert back["markets"]["rush_yds"]["verdict"] == "clears"
        assert rf.load(models_dir=os.path.join(tmp, "nowhere")) == {}


def test_nothing_prices_from_the_ripple_yet():
    """The measurement exists so that a pricing change can be made ON a
    measurement. Until a market clears there is no pricing hook, and
    this pins that the projection, the evaluator, the pipeline and the
    build do not read the verdict."""
    for rel in ("engine/projection.py", "engine/betting.py",
                "engine/pipeline.py", "nfl_build.py", "engine/redistribute.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "ripplefit.load" not in src and "ripplefit import" not in src, rel


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
