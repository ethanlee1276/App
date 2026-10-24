"""The stake is read off the record, not typed in.

Ethan, 2026-09-21: *"we need to figure out what unit sizes and money
sizes makes the most sense and make the most money and highest roi on
the most likley bets."*

THE ANSWER THAT HAS TO COME FIRST IS THAT HALF THE QUESTION HAS NO
SIZING ANSWER. A flat stake cannot change ROI — net units over units
staked scale together — so "most money" and "highest ROI" are two
different requests and only the first is about size. That is pinned
below rather than left in a docstring, because it is the finding most
likely to be quietly un-learned.

WHAT THE RULE ACTUALLY DOES: sizes on the LOWER bound of the measured
edge (a board that got lucky shrinks back on its own), divides by the
MEASURED same-slate correlation rather than an assumed one, and holds
the whole thing under a one-night exposure cap that does not depend on
any measurement being right.

Run directly:
`python3 tests/test_what_to_stake_on_the_likelihood_board.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                     # noqa: E402
from engine import likelysize as size                         # noqa: E402


class _Row(dict):
    """A journal row, indexable the way sqlite3.Row is."""


def _rows(n, hit=0.706, odds=-181, slates=10, start=1):
    """`n` settled rows spread over `slates` calendar days.

    Deterministic rather than random: a sizing rule tested on a coin
    flip is a rule whose test fails on some seeds and not others, and
    this one is about money.
    """
    out, per = [], max(1, n // slates)
    for i in range(n):
        day = start + (i // per)
        # Exactly round(n*hit) wins, spread evenly — `i % 1000 < hit*1000`
        # was the first cut and it made every row a win at n=20, which
        # is the sort of fixture that tests the fixture.
        won = int((i + 1) * hit) > int(i * hit)
        out.append(_Row(date=f"2026-09-{day:02d}",
                        status="won" if won else "lost", odds=odds))
    return out


def _day(sl):
    return f"2026-{1 + sl // 28:02d}-{1 + sl % 28:02d}"


def _thin(n, hit, slates, odds=-181):
    """`n` rows over many SMALL slates, so the one-night cap is loose and
    the Kelly arithmetic is what decides the stake. The default fixture
    above puts ten rows a slate, which makes the exposure cap bind on
    everything and hides whether the rest of the rule works at all."""
    out, per = [], max(1, n // slates)
    for i in range(n):
        won = int((i + 1) * hit) > int(i * hit)
        out.append(_Row(date=_day(i // per),
                        status="won" if won else "lost", odds=odds))
    return out


def _blocky(n, hit, slates, spread, odds=-181):
    """The same rows with slate win-rates alternating ``hit ± spread`` —
    PARTIAL correlation, which is what a real slate has. `spread=0` is
    the independent control; a big spread is a board whose whole night
    moves together."""
    out, per = [], max(1, n // slates)
    for sl in range((n + per - 1) // per):
        h = min(0.99, max(0.01, hit + (spread if sl % 2 else -spread)))
        for j in range(min(per, n - sl * per)):
            won = int((j + 1) * h) > int(j * h)
            out.append(_Row(date=_day(sl),
                            status="won" if won else "lost", odds=odds))
    return out


# --- the half of the question that is not about size --------------------
def test_a_flat_stake_cannot_change_roi():
    """THE FINDING. Doubling every stake doubles the net AND the staked,
    so the percentage is untouched. Ethan asked for the size that gives
    "the most money and highest roi"; those are two requests and this is
    why only one of them is a sizing question."""
    rows = _rows(200)
    got = size.replay(rows, [0.1, 0.25, 0.5, 1.0, 2.0, 5.0])
    rois = {round(r["roi"], 10) for r in got}
    assert len(rois) == 1, got
    # …while the money and the risk scale exactly with it.
    small, big = got[0], got[-1]
    assert abs(big["net_units"] - small["net_units"] * 50) < 0.05
    assert abs(big["max_drawdown_u"] - small["max_drawdown_u"] * 50) < 0.05


# --- sized on what is proved, not on what is hoped ----------------------
def test_a_lucky_looking_board_with_no_sample_is_not_sized_up():
    """A twenty-row board at +16% is a run of luck wearing a result —
    and the lower bound ALONE does not catch it, which is why there is
    a row count gate as well: a point estimate that high keeps its bound
    positive even when the bound is enormous."""
    rec = size.recommend(size.measure(_rows(20, hit=0.78)))
    assert rec["roi"] > 0.05, rec["roi"]
    assert rec["roi_lb"] > 0, "this test is not exercising the n gate"
    assert rec["units"] == size.FLOOR_U, rec["why"]
    assert f"{size.MIN_N} needed" in rec["why"], rec["why"]


def test_the_row_bar_is_the_one_the_board_already_waits_for():
    """A stake is a stronger statement than a verdict, so it must not
    move on less evidence than the verdict needs."""
    assert size.MIN_N == ledger.LIKELY_VERDICT_N, (
        size.MIN_N, ledger.LIKELY_VERDICT_N)


def test_the_same_edge_with_more_rows_earns_a_bigger_stake():
    """This is the whole design: the stake grows as the bound tightens,
    with nobody deciding anything."""
    thin = size.recommend(size.measure(_rows(60, hit=0.75, slates=10)))
    thick = size.recommend(size.measure(_rows(2000, hit=0.75, slates=200)))
    assert thick["roi_lb"] > thin["roi_lb"], (thin["roi_lb"], thick["roi_lb"])
    assert thick["units"] > thin["units"], (thin["units"], thick["units"])


def test_a_losing_board_is_never_sized_above_the_floor():
    rec = size.recommend(size.measure(_rows(2000, hit=0.55, slates=200)))
    assert rec["roi"] < 0, rec["roi"]
    assert rec["units"] == size.FLOOR_U, rec["why"]
    # …and it SAYS the edge is not there, rather than printing a Kelly
    # sum that happened to floor out. Without this the whole negative
    # branch could be deleted and the number would not move.
    assert "not yet an edge" in rec["why"], rec["why"]


def test_the_stake_comes_off_the_BOUND_and_not_the_point_estimate():
    """Pinned on a board where the two give different answers and
    NEITHER is capped or floored — every other fixture here has a cap
    binding, which hides whether this half of the rule runs at all."""
    rows = _thin(1200, hit=0.664, slates=400)
    rec = size.recommend(size.measure(rows))
    assert size.FLOOR_U < rec["units"] < size.CAP_U, rec["why"]
    m = size.measure(rows)
    # What the point estimate alone would have staked, by hand:
    point = size.KELLY_FRACTION * (m["roi"] / m["b"]) * 100.0 / m["corr"]
    assert point > rec["units"] * 1.5, (point, rec["units"])


def test_the_absolute_cap_holds_a_hot_board_under_the_edge_books_own():
    """A board still inside its own noise band does not out-stake the
    book with the most evidence behind it."""
    rec = size.recommend(size.measure(_thin(1200, hit=0.70, slates=400)))
    assert rec["units"] == size.CAP_U, rec["why"]
    assert rec["slate_cap_u"] > size.CAP_U, "the one-night cap bound first"
    assert size.CAP_U < 1.25, "the Edge book's own ceiling is 1.25u"


def test_a_correlated_board_is_staked_smaller_than_an_independent_one():
    """Same rows, same edge, same slate sizes — only the correlation
    differs. Kelly assumes one bet at a time; this board bets a whole
    slate at once, and the divisor is the whole of that adjustment."""
    alone = size.recommend(size.measure(_blocky(1200, 0.70, 40, 0.0)))
    together = size.recommend(size.measure(_blocky(1200, 0.70, 40, 0.18)))
    assert together["corr"] > alone["corr"] * 3, (alone["corr"],
                                                  together["corr"])
    assert together["units"] < alone["units"], (alone["units"],
                                                together["units"])


def test_the_inflation_actually_moves_the_stake():
    """Not just the reported number: the INFLATED correlation is what
    the stake is divided by. Without this the inflation could be
    computed, printed and ignored."""
    m = size.measure(_blocky(1200, 0.70, 40, 0.18))
    rec = size.recommend(m)
    assert m["corr"] > m["corr_raw"] * 1.1, (m["corr_raw"], m["corr"])
    raw_only = dict(m, corr=m["corr_raw"])
    assert size.recommend(raw_only)["units"] > rec["units"], (
        size.recommend(raw_only)["units"], rec["units"])


def test_the_stake_stays_inside_its_own_bounds_whatever_the_record():
    for hit in (0.50, 0.62, 0.706, 0.80, 0.95):
        for n in (10, 150, 900):
            rec = size.recommend(size.measure(_rows(n, hit=hit)))
            assert size.FLOOR_U <= rec["units"] <= size.CAP_U, (hit, n, rec)


# --- how many bets are really riding at once ----------------------------
def test_the_correlation_is_measured_once_there_are_slates_to_measure():
    rec = size.recommend(size.measure(_rows(600, slates=60)))
    assert rec["corr_measured"] is True, rec
    assert rec["corr_raw"] is not None


def test_too_few_slates_assumes_the_whole_slate_moves_as_one():
    m = size.measure(_rows(60, slates=2))
    assert m["corr_measured"] is False
    assert m["corr"] == m["slate_n"], m


def test_few_slates_inflate_the_estimate_rather_than_pretend_it_is_exact():
    """A variance read off nine slates could honestly be half again what
    it looks like, and erring low here over-bets a whole slate at once.
    The first cut had a hard 20-slate cliff instead, which called an NFL
    Sunday — forty props across thirteen games — ONE bet, and held a
    league at the floor on an assumption nobody had checked."""
    few = size.measure(_rows(300, slates=6))
    many = size.measure(_rows(300, slates=60))
    assert few["corr_measured"] and many["corr_measured"]
    assert few["corr_se_rel"] > many["corr_se_rel"], (few, many)
    # Same underlying rows, so the raw ratios are close; the INFLATED
    # one is bigger where the sample is thinner.
    assert (few["corr"] / max(few["corr_raw"], 1e-9)
            > many["corr"] / max(many["corr_raw"], 1e-9))


def test_a_bigger_slate_is_a_smaller_stake():
    """The one-night cap, which is the guard that does not depend on any
    measurement being right."""
    lean = size.recommend(size.measure(_rows(600, hit=0.75, slates=120)))
    fat = size.recommend(size.measure(_rows(600, hit=0.75, slates=12)))
    assert fat["slate_max"] > lean["slate_max"]
    assert fat["units"] < lean["units"], (lean["units"], fat["units"])
    # Either the exposure is inside the cap, or the floor won and the
    # rule SAYS the board is too wide to stake at this bankroll —
    # never quietly over the cap with nothing said.
    assert (fat["units"] * fat["slate_max"] <= size.MAX_SLATE_U + 1e-9
            or fat["over_exposed"]), fat["why"]
    if fat["over_exposed"]:
        assert "wide for this bankroll" in fat["why"], fat["why"]


def test_the_one_night_number_is_printed_beside_the_roi():
    """The loss the ROI column cannot show: a slate is bet all at once,
    so a correlated bad night takes all of it together."""
    got = size.replay(_rows(120, slates=10), [1.0])[0]
    assert got["biggest_slate_rows"] == 12, got
    assert got["if_a_slate_all_lost_u"] == -12.0, got


# --- the evidence it reads ----------------------------------------------
def test_paper_rows_count_as_evidence_for_the_stake():
    """`likely_live` only exists from 2026-09-19. Sizing on it alone
    would read a fortnight and hold every league at the floor forever,
    while the answer sat in the paper book — the same selection at a
    smaller stake, and ROI does not care what a row cost."""
    assert "likely" in size.EVIDENCE_BOOKS
    assert "likely_live" in size.EVIDENCE_BOOKS
    conn = _journal()
    _seed(conn, "nfl", 200, category="likely")
    m = size.measure(size._rows(conn, "nfl"))
    assert m["n"] == 200, m["n"]


def test_an_nfl_week_label_is_not_one_slate():
    """The NFL journals `date` as "2026-W3". Grouping on it would call a
    whole week one slate, and the correlation divisor is the slate's row
    count — so a league that spreads its rows over Thursday, Sunday and
    Monday would have been sized as if it bet them all together."""
    conn = _journal()
    _seed(conn, "nfl", 90, category="likely", weekly=True)
    m = size.measure(size._rows(conn, "nfl"))
    assert m["slates"] == 9, m["slates"]      # 3 weeks x 3 game days


# --- and what the journal actually stakes -------------------------------
def _journal():
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


_INS = ("INSERT INTO bets (ts, sport, game_day, date, player, market, side,"
        " line, odds, hit_prob, stake_units, stake_dollars, status,"
        " category, pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _seed(conn, sport, n, category="likely", hit=0.75, weekly=False):
    for i in range(n):
        if weekly:
            wk, day = i // 30, ("04", "07", "08")[(i // 10) % 3]
            gd = f"2026-09-{int(day) + wk * 7:02d}"
            date = f"2026-W{wk + 1}"
        else:
            gd = date = f"2026-09-{1 + (i // 10):02d}"
        won = int((i + 1) * hit) > int(i * hit)
        conn.execute(_INS, ("t", sport, gd, date, f"P{i}", "rec_yds", "OVER",
                            40.5, -181, 0.66, 0.1, 0.0,
                            "won" if won else "lost", category,
                            0.0551 if won else -0.1))
    conn.commit()


def test_the_journal_stakes_the_measured_size_not_the_constant():
    conn = _journal()
    _seed(conn, "nfl", 900, hit=0.78)
    got = ledger.likely_stake_for(conn, "nfl", 0.66)
    assert got > ledger.LIKELY_LIVE_STAKE, got
    assert got == size.for_sport(conn, "nfl")["units"], got


def test_an_unstaked_league_still_gets_nothing():
    conn = _journal()
    _seed(conn, "ufc", 900, hit=0.78)
    assert ledger.likely_stake_for(conn, "ufc", 0.66) == 0.0


def test_a_benched_league_still_gets_nothing():
    conn = _journal()
    _seed(conn, "wnba", 900, hit=0.78)
    assert ledger.likely_stake_for(conn, "wnba", 0.66) == 0.0


def test_the_sizing_rule_can_never_stop_the_night_being_journaled():
    """A stake that raises is a stake that loses the night's record. The
    old constant is the fallback, not an exception."""
    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("journal is busy")
    size._CACHE.clear()
    assert size.staked_units(Broken(), "nfl") == size.FLOOR_U
    size._CACHE.clear()


def test_the_check_is_registered_and_reads_only():
    import inspect
    import homecheck
    assert "sizing" in homecheck.CHECKS, sorted(homecheck.CHECKS)
    src = inspect.getsource(homecheck.sizing)
    assert "_journal_ro()" in src
    assert "ledger.connect(" not in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
