"""EXP-007b: EXP-007's strikeout models at the books' own lines — the placement and the one read.

research/exp7b_mlb_strikeout_lines_box.py prices EXP-007's models at the
strikeout lines the box's two stores hold and decides on EXP-007's holdout
starts, once. The table keeps a start's date, not its first pitch, so what
these hold first is the placement: a quote carrying its game's start lands
on that day's start only if taken before it; one carrying none lands on
his next start within two days, and on the day itself only before 11 a.m.
Eastern. Then: the last two-sided quote per book wins across both stores;
A is read at the line and B and H as counts; the decision is read only
with the flag, under EXP-007's guards, and only on enough props; and on
made-up leagues H* finds a shape built on batters faced and not one that
is not, while B* can also win on its centre alone.

Run directly: `python3 tests/test_mlb_strikeout_lines_lab.py`
"""
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _mlb_league import _league                                    # noqa: E402  (path set above)
from research import exp7_mlb_strikeouts_box as E7               # noqa: E402
from research import exp7b_mlb_strikeout_lines_box as E7B        # noqa: E402

UTC = dt.timezone.utc


def test_a_quote_lands_on_the_start_it_was_hung_for():
    days = ["2026-07-01", "2026-07-06", "2026-07-11"]
    start = dt.datetime(2026, 7, 6, 23, 10, tzinfo=UTC)
    assert E7B.place(days, start - dt.timedelta(hours=5), start) == "2026-07-06"
    assert E7B.place(days, start + dt.timedelta(minutes=5), start) is None, "after first pitch"
    assert E7B.place(days, dt.datetime(2026, 7, 5, 22, tzinfo=UTC), None) == "2026-07-06", "the next start"
    assert E7B.place(days, dt.datetime(2026, 7, 6, 14, tzinfo=UTC), None) == "2026-07-06"
    assert E7B.place(days, dt.datetime(2026, 7, 6, 18, tzinfo=UTC), None) is None, "too late on the day, start unknown"
    assert E7B.place(days, dt.datetime(2026, 7, 7, 2, tzinfo=UTC), None) is None, "10 p.m. Eastern on the day"
    assert E7B.place(days, dt.datetime(2026, 7, 6, 3, tzinfo=UTC), None) == "2026-07-06", "11 p.m. Eastern the night before"
    assert E7B.place(days, dt.datetime(2026, 7, 2, 12, tzinfo=UTC), None) is None, "four days out"


def test_the_last_two_sided_quote_per_book_wins_across_both_stores():
    days = {"ace": ["2026-07-06"]}
    t = dt.datetime(2026, 7, 6, 12, tzinfo=UTC)
    snaps = [{"ts": (t - dt.timedelta(hours=3)).timestamp(), "player": "Ace", "market": "strikeouts", "book": "dk",
              "line": 5.5, "over_odds": -120, "under_odds": 100},
             {"ts": (t - dt.timedelta(hours=1)).timestamp(), "player": "Ace", "market": "strikeouts", "book": "fd",
              "line": 5.5, "over_odds": -110, "under_odds": -110}]
    hist = [((t - dt.timedelta(hours=2)).isoformat(), "Ace", "dk", 6.5, 105, -125, None),
            ((t - dt.timedelta(hours=2)).isoformat(), "Ace", "fd", 4.5, -200, 160, None),
            ((t - dt.timedelta(minutes=30)).isoformat(), "Ace", "dk", 7.5, 130, None, None)]
    got = E7B.gather(days, snaps, hist)
    assert got[("ace", "2026-07-06")] == {"dk": (6.5, 105, -125), "fd": (5.5, -110, -110)}, \
        "dk's later one-sided quote does not displace its last two-sided one"


def _league_with_lines(**kw):
    """EXP-007's made-up league, with three books hanging every start's
    strikeouts at his direct model's mean (to the half below), quoted the
    morning of the start."""
    conn = _league(**kw)
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    rows = E7.rows_from(E7.starts(conn))
    w = sqlite3.connect(path)
    for x in rows:
        line = max(0.5, int(x["mu_a"]) + 0.5)
        for book, o, u in (("dk", -115, -105), ("fd", -110, -110), ("mgm", -120, 100)):
            w.execute("INSERT INTO odds_history (sport, taken_at, event_id, home, away, player, market, book, line, "
                      "over_odds, under_odds, commence_time) VALUES ('mlb',?,?,?,?,?,?,?,?,?,?,NULL)",
                      (f"{x['date']}T13:00:00Z", f"e{x['date']}", "H", "A", x["name"], "strikeouts", book,
                       line, o, u))
    w.commit()
    w.close()
    return E7.open_db(path)


def test_the_decision_is_read_once_with_the_flag_and_only_on_enough_props():
    conn = _league_with_lines()
    quiet = []
    first = E7B.study(conn, os.devnull, say=quiet.append)
    assert first["verdict"] == "NOT READ" and first["dev"] > 0 and first["post"] >= E7B.MIN_DECIDE
    assert any("funnel" in ln and "props joined to a scored start" in ln for ln in quiet)
    read = E7B.study(conn, os.devnull, holdout=True, say=quiet.append)
    assert set(read["verdict"]) == {"B*", "H*"}
    assert all(v in ("PASSES", "INCONCLUSIVE", "FAILS") for v in read["verdict"].values())
    short = E7B.study(_league_with_lines(missing=60), os.devnull, holdout=True, say=quiet.append)
    assert short["verdict"] == "NOT READ" and short["why"], "a season still filling is not read"
    keep = E7B.MIN_DECIDE
    E7B.MIN_DECIDE = 10 ** 6
    try:
        assert E7B.study(conn, os.devnull, holdout=True, say=quiet.append)["verdict"] == "NO DECISION"
    finally:
        E7B.MIN_DECIDE = keep


def test_a_is_read_at_the_line_and_b_and_h_as_counts():
    conn = _league(seasons=(2026,), pitchers=12, starts_each=14)
    rows = E7.rows_from(E7.starts(conn))
    fit = E7.Fit(rows)
    x = rows[0]
    got = E7B.chances(fit, x, 5.5)
    assert got["A"] == 1.0 - fit.cdf_a(x, 5.5) and got["B"] == 1.0 - fit.cdf_b(x)[5]
    same = dict(x, mu_a=fit.mean_b(x))
    at = E7B.chances(fit, same, 5.5)
    assert abs(at["H"] - at["B"]) < 1e-12, "at B's own mean, H is B"
    assert E7B.proxy_line(fit, x) % 1 == 0.5


def test_h_is_the_shape_test_at_the_line_and_b_also_carries_its_centre():
    """The bar both ways on made-up leagues of 30 pitchers, three books
    each. Measured over twenty leagues of each kind: where strikeouts are
    batters faced times a rate, Q1 (B*) passed in 19 and Q2 (H*) in 17;
    where they come from his mean whatever his batters faced, Q2 passed in
    1 and Q1 still in 13. B's pooled season rate is a steadier centre than
    the form blend (its squared error on the decision starts was 3-9% lower
    over six leagues of each kind), and at one line the centre counts for
    more than the shape. So H*, A's centre with B's shape, is the shape
    test at the line; B* tests the whole model."""
    quiet = []
    for seed in (0, 2, 3):
        built = E7B.study(_league_with_lines(seed=seed), os.devnull, holdout=True, say=quiet.append)["verdict"]
        assert built == {"B*": "PASSES", "H*": "PASSES"}, (seed, built)
        flat = E7B.study(_league_with_lines(seed=seed, direct=True), os.devnull, holdout=True,
                         say=quiet.append)["verdict"]
        assert flat["H*"] != "PASSES", (seed, flat)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
