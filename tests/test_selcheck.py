"""The test that has to be able to say no.

selcheck exists to try to KILL the selection hypothesis before anything is
built on it, so the property that matters most is that it returns "not
selection" when the data says so. A diagnostic that can only confirm is
not a diagnostic.

The fit carries a free intercept on purpose. guardfit forced its line
through a hinge, which handed the whole level to the slope and produced a
recommendation to raise a favourite surcharge for a miscalibration that
every price shares. Same mistake, one script over, would manufacture the
finding this one is meant to be able to reject.

Run directly: `python3 tests/test_selcheck.py`
"""

import os
import random
import sqlite3
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import selcheck as sc                                           # noqa: E402


def _rows(spec):
    """spec: [(edge, claimed, landed_rate, n), …] → journal-shaped dicts."""
    rng = random.Random(17)
    out = []
    for edge, claimed, rate, n in spec:
        for _ in range(n):
            out.append({"sport": "mlb", "market": "strikeouts", "side": "OVER",
                        "odds": -110, "hit_prob": claimed, "edge": edge,
                        "status": "won" if rng.random() < rate else "lost"})
    return out


# --- the shape it must be able to reject ------------------------------------
def test_a_flat_gap_is_reported_as_not_selection():
    """Every bucket over-claims by the same 12 points. That is a LEVEL
    error — stale lines, a bad de-vig, a weak market shrink — and a
    selection shrink is the wrong instrument for it."""
    rows = _rows([(0.01, 0.60, 0.48, 400), (0.03, 0.60, 0.48, 400),
                  (0.05, 0.60, 0.48, 400), (0.10, 0.60, 0.48, 400)])
    f = sc.fit_line(sc.buckets(rows))
    z = f["slope"] / f["se"]
    assert abs(z) < 2.0, (f["slope"], z)
    # …and the level is still recovered, because it is real.
    assert 0.09 < f["level"] < 0.15, f["level"]


def test_a_gap_that_grows_with_claimed_edge_reads_as_selection():
    """The winner's curse: the more edge we thought we had, the more of it
    was our own error."""
    rows = _rows([(0.01, 0.60, 0.585, 400), (0.03, 0.60, 0.545, 400),
                  (0.05, 0.60, 0.505, 400), (0.10, 0.60, 0.405, 400)])
    f = sc.fit_line(sc.buckets(rows))
    assert f["slope"] > 0
    assert f["slope"] / f["se"] > 2.0, (f["slope"], f["se"])


def test_a_gap_that_shrinks_with_claimed_edge_is_flagged_backwards():
    """Selection cannot produce this, so it means something else is wrong
    and the script must not quietly call it a pass."""
    rows = _rows([(0.01, 0.60, 0.42, 400), (0.03, 0.60, 0.48, 400),
                  (0.05, 0.60, 0.54, 400), (0.10, 0.60, 0.60, 400)])
    f = sc.fit_line(sc.buckets(rows))
    assert f["slope"] / f["se"] < -2.0


# --- the construction fault this script was written to avoid ----------------
def test_the_line_is_not_forced_through_the_origin():
    """The bug in guardfit, which turned a level into a slope and
    recommended a pricing change on the strength of it.

    A flat +12 at every edge must fit as intercept 0.12 and slope ~0, not
    as a positive slope through zero. This is the same data as the first
    test, checked against the specific failure mode.
    """
    rows = _rows([(0.01, 0.60, 0.48, 400), (0.03, 0.60, 0.48, 400),
                  (0.05, 0.60, 0.48, 400), (0.10, 0.60, 0.48, 400)])
    f = sc.fit_line(sc.buckets(rows))
    assert f["level"] > 0.05, "the level vanished into the slope"
    assert abs(f["slope"]) < 2.0, "a flat gap produced a large slope"
    import inspect
    src = inspect.getsource(sc.fit_line)
    assert "intercept" in src


# --- the arithmetic ---------------------------------------------------------
def test_the_error_bar_is_poisson_binomial_not_pooled():
    """Each bet is its own Bernoulli trial with its own probability.
    Averaging the claims first and then taking n·p̄(1−p̄) understates the
    spread on a group whose claims vary, which would make a bucket look
    more certain than it is."""
    mixed = [{"hit_prob": p, "status": "won", "sport": "mlb",
              "market": "m", "edge": 0.05, "side": "OVER", "odds": -110}
             for p in (0.10, 0.90) * 50]
    s = sc._stats(mixed)
    pooled = (0.5 * 0.5 * len(mixed)) ** 0.5 / len(mixed)
    assert s["se"] < pooled, (s["se"], pooled)


def test_no_bucket_is_ever_thin():
    """Equal-count buckets, so a wide error bar cannot appear at the end of
    the range — which is exactly where a spurious slope would come from.

    The fixed-band version this replaced put 242 of the real journal's 243
    bets into two bands and one lone bet into a third, whose ±95.6% error
    bar carried a +64.6% gap. Nothing useful can be fitted through that.
    """
    rows = _rows([(0.01, 0.60, 0.48, 300), (0.03, 0.60, 0.48, 300),
                  (0.05, 0.60, 0.48, 300), (0.10, 0.60, 0.48, 5)])
    bs = sc.buckets(rows)
    assert min(b["n"] for b in bs) >= sc.MIN_BUCKET_N, [b["n"] for b in bs]
    assert sum(b["n"] for b in bs) == len(rows)
    assert sc.fit_line(bs)["bands"] == len(bs)


def test_it_finds_resolution_where_the_edges_actually_are():
    """The real journal's failure, reproduced.

    Every bet sat between 2% and 6% claimed edge — the board's bar decides
    that, not the test — and fixed bands at 0/2/4/6/9 gave only two usable
    buckets where a line needs three. Splitting the observed distribution
    puts the same count in each bucket wherever it sits.
    """
    rng = random.Random(4)
    rows = [{"sport": "mlb", "market": "strikeouts", "side": "OVER",
             "odds": -110, "hit_prob": 0.58, "edge": rng.uniform(0.02, 0.06),
             "status": "won" if rng.random() < 0.465 else "lost"}
            for _ in range(243)]
    bs = sc.buckets(rows)
    assert len(bs) == sc.TARGET_BUCKETS, [b["n"] for b in bs]
    assert sc.fit_line(bs)["slope"] is not None, "still cannot fit"
    # The buckets have to actually span the range, not sit on top of it.
    assert bs[-1]["edge"] - bs[0]["edge"] > 0.02, [b["edge"] for b in bs]


def test_every_bet_lands_in_exactly_one_bucket():
    rows = _rows([(0.0, 0.6, 0.5, 10), (0.02, 0.6, 0.5, 10),
                  (0.039, 0.6, 0.5, 10), (0.5, 0.6, 0.5, 10)])
    assert sum(b["n"] for b in sc.buckets(rows)) == len(rows)


def test_it_declines_to_speak_on_too_little_data():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc.report(_rows([(0.05, 0.6, 0.5, 20)]))
    assert "Need" in buf.getvalue()
    assert "CONSISTENT WITH SELECTION" not in buf.getvalue()


def test_the_query_only_takes_settled_bets_that_carry_both_numbers():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, market TEXT, side TEXT, "
                 "odds INTEGER, book TEXT, hit_prob REAL, edge REAL, "
                 "status TEXT, category TEXT)")
    conn.executemany("INSERT INTO bets VALUES (?,?,?,?,?,?,?,?,?)", [
        ("mlb", "k", "OVER", -110, "dk", 0.6, 0.05, "won", "main"),
        ("mlb", "k", "OVER", -110, "dk", 0.6, None, "won", "main"),   # no edge
        ("mlb", "k", "OVER", -110, "dk", None, 0.05, "won", "main"),  # no claim
        ("mlb", "k", "OVER", -110, "dk", 0.6, 0.05, "open", "main"),  # unsettled
        ("nfl", "r", "OVER", -110, "dk", 0.6, 0.05, "won", "main"),   # other
    ])
    assert len(sc.load(conn, sport="mlb")) == 1
    assert len(sc.load(conn, sport="all")) == 2



def test_it_reports_what_it_could_not_have_seen():
    """A flat answer at this sample size is weak, and the output has to say
    so. Simulated on null data the |z|>=2 rule fires 4.7% of the time —
    correct — but at 243 bets it also MISSES a real slope of +5 about half
    the time. A verdict that reads "not selection" without its own
    resolution beside it invites closing a live question.
    """
    import contextlib
    import io
    rng = random.Random(21)
    rows = [{"sport": "mlb", "market": "strikeouts", "side": "OVER",
             "odds": -110, "hit_prob": 0.58, "edge": rng.uniform(0.02, 0.06),
             "status": "won" if rng.random() < 0.465 else "lost"}
            for _ in range(243)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc.report(rows)
    out = buf.getvalue()
    assert "smallest slope this sample could resolve" in out
    if "NOT PROVEN" in out:
        assert "no evidence for, not evidence against." in out
        assert "do not close the question" in out.lower()


def test_the_level_is_quoted_inside_the_data_not_extrapolated_to_zero():
    """The real run printed "(The level itself is +26.4% and real.)" when
    the actual average gap was +12.1%.

    No bet is placed under about 2.4% claimed edge — the board's bar sees
    to that — so a regression intercept at zero is an extrapolation four
    points beyond anything observed, and it swings with a slope of -3.56
    that was not significant (z -0.66). Quoted as real, it is a number
    someone could act on.
    """
    rng = random.Random(31)
    rows = [{"sport": "mlb", "market": "m", "side": "OVER", "odds": -110,
             "hit_prob": 0.58, "edge": rng.uniform(0.024, 0.07),
             "status": "won" if rng.random() < 0.46 else "lost"}
            for _ in range(247)]
    f = sc.fit_line(sc.buckets(rows))
    # The level sits where the bets are…
    assert 0.024 <= f["at_edge"] <= 0.07, f["at_edge"]
    # …and equals the weighted average gap, which is what "the level" means.
    assert abs(f["level"] - 0.12) < 0.06, f["level"]
    # The extrapolated value is still available, just not the headline.
    assert "intercept_at_zero" in f


def test_categories_are_never_pooled():
    """`bets.edge` is two different quantities and pooling them is a
    Simpson's-paradox machine.

    engine/ledger.py writes `r.get("edge", r.get("ev_per_unit"))` on a
    longshot row, so a home-run bet's "edge" is a per-unit expected value
    that runs from about -0.6 to +0.6 on a +900 price, while a main-board
    row's is an edge in probability points. The first `--category all` run
    bucketed the two together and reported CONSISTENT WITH SELECTION at
    z +2.13 across buckets whose claimed probabilities were 10.3%, 15.1%,
    53.0%, 45.6% and 27.2% — the buckets differed in what they CONTAINED
    before they differed in anything measured.
    """
    import inspect
    src = inspect.getsource(sc.main)
    assert 'groups.setdefault(r.get("category")' in src, (
        "main() must split by category before reporting; one pooled slope "
        "over two definitions of `edge` is not a measurement"
    )
    assert "report(rs)" in src


def test_the_market_table_carries_a_relative_gap():
    """+2.9 points on a 14.7% claim is a fifth of the claim; +3.3 on 58.9%
    is a twentieth. Ranking home runs against main-board props on absolute
    probability points compares nothing."""
    import contextlib
    import io
    rows = ([{"sport": "mlb", "market": "home_runs", "side": "OVER",
              "odds": 700, "hit_prob": 0.147, "edge": 0.05,
              "status": "won" if i % 7 == 0 else "lost", "category": "longshot"}
             for i in range(300)]
            + [{"sport": "mlb", "market": "hits", "side": "OVER",
                "odds": -110, "hit_prob": 0.589, "edge": 0.04,
                "status": "won" if i % 2 else "lost", "category": "longshot"}
               for i in range(300)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc._markets(rows)
    out = buf.getvalue()
    assert "rel" in out
    # home runs must show the LARGER relative miss despite smaller points
    hr = [l for l in out.splitlines() if "home_runs" in l][0]
    assert hr.strip().endswith("%")


# --- selected vs rejected: the test that actually had leverage -------------
def _pair(market, claim, sel_rate, rej_rate, n=200, book="dk"):
    # crc32, NOT hash(): Python randomises string hashing per process, so a
    # hash()-seeded fixture is a different fixture every run. This test
    # passed three times and failed the next three before that was caught.
    rng = random.Random(zlib.crc32(f"{market}|{book}".encode()))
    mk = lambda rate, cat: [
        {"sport": "mlb", "market": market, "side": "OVER", "odds": -110,
         "book": book, "hit_prob": claim, "edge": 0.04, "category": cat,
         "status": "won" if rng.random() < rate else "lost"} for _ in range(n)]
    return mk(sel_rate, "main"), mk(rej_rate, "loose")


def test_a_gate_that_picks_the_worse_bets_is_caught():
    """The real journal's shape: rejected props calibrated, selected ones
    twelve points hot, same model and same nights."""
    sel, rej = _pair("hits", 0.58, 0.46, 0.58, n=400)
    r = sc.across(sel, rej)
    assert r["raw"]["diff"] > 0.08
    assert r["raw"]["diff"] / r["raw"]["se"] > 2.0
    assert r["adjusted"] is not None
    assert r["adjusted"]["diff"] / r["adjusted"]["se"] > 2.0


def test_a_gate_that_works_is_not_called_a_curse():
    sel, rej = _pair("hits", 0.58, 0.62, 0.50, n=400)
    r = sc.across(sel, rej)
    assert r["raw"]["diff"] / r["raw"]["se"] < -2.0


def test_composition_alone_does_not_survive_the_adjustment():
    """The confound this test exists to rule out.

    Both markets are equally calibrated WITHIN themselves — no gate effect
    at all — but the gate routes a market with a low hit rate mostly into
    the selected side. The raw difference is large and meaningless; the
    within-strata difference has to collapse, or the whole comparison is
    worthless.
    """
    hard_s, hard_r = _pair("home_runs", 0.30, 0.20, 0.20, n=300)
    easy_s, easy_r = _pair("hits", 0.60, 0.60, 0.60, n=300)
    # selected is mostly the hard market, rejected mostly the easy one
    sel = hard_s + easy_s[:40]
    rej = hard_r[:40] + easy_r
    r = sc.across(sel, rej)
    assert abs(r["raw"]["diff"]) > 0.03, "fixture did not create a confound"
    assert r["adjusted"] is not None
    za = r["adjusted"]["diff"] / r["adjusted"]["se"]
    assert abs(za) < 2.0, (r["adjusted"], za)


def test_the_balance_table_shows_the_mix():
    sel, rej = _pair("hits", 0.58, 0.46, 0.58, n=100)
    other_s, other_r = _pair("home_runs", 0.30, 0.25, 0.25, n=100)
    b = sc.balance(sel + other_s, rej, lambda r: r["market"])
    by = {r["key"]: r for r in b}
    assert by["home_runs"]["n_sel"] == 100 and by["home_runs"]["n_rej"] == 0
    assert abs(by["hits"]["p_rej"] - 1.0) < 1e-9


def test_across_declines_on_a_thin_side():
    import contextlib
    import io
    sel, rej = _pair("hits", 0.58, 0.46, 0.58, n=20)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc.report_across(sel, rej)
    assert "Need 60" in buf.getvalue()
    assert "WINNER" not in buf.getvalue().upper()


def test_an_underpowered_adjustment_is_not_called_composition():
    """The real run's shape, and the note that got it wrong.

    Raw +12.7% became adjusted +8.5% — two thirds of the effect intact —
    and the z fell under 2 only because stratifying dropped 301 of 809
    bets. Reporting that as "composition explains it" points at the
    opposite action from "collect more bets".
    """
    import contextlib
    import io
    r = {"sel": {"n": 247, "claimed": .579, "landed": .457, "gap": .122, "se": .031},
         "rej": {"n": 562, "claimed": .593, "landed": .598, "gap": -.005, "se": .0195},
         "raw": {"diff": .127, "se": .0366},
         "adjusted": {"diff": .085, "se": .0455},
         "strata": [{}] * 6, "covered": 508}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc._across_note(r, 809)
    out = buf.getvalue()
    assert "UNDER-POWERED" in out
    assert "explains it" not in out


def test_a_real_composition_effect_is_still_called_out():
    import contextlib
    import io
    r = {"raw": {"diff": .127, "se": .0366},
         "adjusted": {"diff": .012, "se": .0455}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc._across_note(r, 809)
    out = buf.getvalue()
    assert "Composition" in out and "UNDER-POWERED" not in out


def test_book_is_not_in_the_strata():
    """Book is a mediator, not a confounder: a prop clears the bar BECAUSE
    a book hung an out-of-line price, so adjusting for book subtracts the
    effect being measured. The docstring has to keep saying so, because the
    balance table makes it look like an obvious thing to add."""
    import inspect
    src = inspect.getsource(sc.across)
    assert "mediator" in src
    assert '"book"' not in src.split('"""')[2], "book crept into the strata key"


# --- sensitivity: is the answer a property of the data or of the cells? ----
def test_a_real_effect_holds_across_every_scheme():
    """One adjusted number is one analyst's choice of strata. An effect
    that is really there should barely move from coarse to fine."""
    sel, rej = _pair("hits", 0.58, 0.46, 0.58, n=400)
    s2, r2 = _pair("total_bases", 0.62, 0.50, 0.62, n=400)
    r = sc.across(sel + s2, rej + r2)
    got = [x for x in r["schemes"] if x["diff"] is not None]
    assert len(got) == 1 + len(sc.SCHEMES), [x["name"] for x in got]
    st = sc.stability(r["schemes"])
    assert st["stable"] is True, st
    assert st["one_sign"]


def test_a_cell_artifact_is_caught_by_the_spread():
    """Two markets, each perfectly calibrated inside itself, with the gate
    routing the low-base-rate one to the selected side. Raw is large;
    controlling for market must kill it, so the schemes disagree."""
    # The minority side needs enough rows to MEASURE zero: at 40 its own
    # error bar is +-7.7%, so "no within-market difference" is untestable
    # there and the first version of this test failed on its own noise.
    hard_s, hard_r = _pair("home_runs", 0.30, 0.20, 0.20, n=500)
    easy_s, easy_r = _pair("hits", 0.60, 0.60, 0.60, n=500)
    r = sc.across(hard_s + easy_s[:150], hard_r[:150] + easy_r)
    by = {x["name"]: x for x in r["schemes"] if x["diff"] is not None}
    assert abs(by["raw (no adjustment)"]["diff"]) > 0.03, by["raw (no adjustment)"]
    assert abs(by["market"]["diff"]) < 0.03, by["market"]


def test_coverage_falls_as_the_scheme_gets_finer():
    """The cost of control, and the reason the finest scheme is not
    automatically the best one to quote."""
    sel, rej = _pair("hits", 0.58, 0.46, 0.58, n=200)
    s2, r2 = _pair("total_bases", 0.62, 0.50, 0.62, n=200)
    s3, r3 = _pair("strikeouts", 0.30, 0.22, 0.30, n=200)
    r = sc.across(sel + s2 + s3, rej + r2 + r3)
    cov = {x["name"]: x["covered"] for x in r["schemes"]}
    assert cov["raw (no adjustment)"] >= cov["market"] >= cov[sc.PRIMARY]


def test_book_is_not_one_of_the_schemes():
    """A mediator, not a confounder — adjusting for it subtracts the very
    effect being measured. The balance table makes adding it look obvious,
    so the guard is explicit."""
    assert all("book" not in name for name, _ in sc.SCHEMES)
    import inspect
    assert "mediator" in inspect.getsource(sc.across)


def test_stability_declines_to_speak_on_one_scheme():
    assert sc.stability([{"name": "raw (no adjustment)", "diff": 0.1, "se": 0.02},
                         {"name": "market", "diff": 0.1, "se": 0.02}])["stable"] is None


# --- is it one book? the abandon condition ----------------------------------
def _bk(book, p, n, land, cat="main"):
    return [{"sport": "mlb", "market": "total_bases", "side": "OVER",
             "odds": -110, "book": book, "hit_prob": p, "edge": 0.04,
             "category": cat,
             "status": "won" if i < round(n * land) else "lost"}
            for i in range(n)]


def test_within_book_is_not_promoted_into_the_scheme_table():
    """It is biased toward zero by construction — book is on the causal
    path. Quoting it beside the honest adjustments would understate the
    effect while looking like a stricter version of it."""
    assert all("book" not in name for name, _ in sc.SCHEMES)
    import inspect
    src = inspect.getsource(sc.within_book)
    assert "floor" in src.lower() and "toward zero" in src.lower()


def test_a_gap_present_in_every_book_survives_the_within_book_floor():
    sel = sum([_bk(b, 0.58, n, 0.46) for b, n in
               (("ESPN BET", 76), ("DraftKings", 49), ("BetMGM", 48),
                ("Hard Rock", 38))], [])
    rej = sum([_bk(b, 0.59, n, 0.60, "loose") for b, n in
               (("theScore Bet", 215), ("Hard Rock", 146),
                ("DraftKings", 116), ("BetMGM", 66))], [])
    w = sc.within_book(sel, rej)
    assert w["diff"] is not None
    assert w["diff"] / w["se"] >= 2.0, w


def test_a_gap_living_in_one_unpaired_book_is_localised_not_generalised():
    """The §9 abandon condition. If the over-claim is one book that never
    appears on the rejected side, the finding is about a price feed and a
    global shrink is the wrong instrument."""
    sel = _bk("ESPN BET", 0.58, 76, 0.20)
    sel += sum([_bk(b, 0.58, n, 0.585) for b, n in
                (("DraftKings", 49), ("BetMGM", 48), ("Hard Rock", 38))], [])
    rej = sum([_bk(b, 0.59, n, 0.60, "loose") for b, n in
               (("theScore Bet", 215), ("Hard Rock", 146),
                ("DraftKings", 116), ("BetMGM", 66))], [])
    sp = sc.book_split(sel, rej)
    assert sp["n_outside"] == 76 and "ESPN BET" not in sp["paired"]
    assert sp["outside"]["gap"] > 0.30            # the bad feed
    assert abs(sp["inside"]["gap"]) < 0.05        # everything else is clean
    # …and the floor correctly refuses to confirm on this data
    w = sc.within_book(sel, rej)
    assert w["diff"] is None or abs(w["diff"] / w["se"]) < 2.0


def test_a_book_too_thin_to_quote_is_left_blank():
    """A five-bet book has no gap worth printing, and printing one invites
    reading it."""
    import contextlib
    import io as _io
    sel = _bk("Tiny", 0.58, 5, 0.40) + _bk("DraftKings", 0.58, 120, 0.46)
    rej = _bk("DraftKings", 0.59, 200, 0.60, "loose")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc.report_books(sel, rej)
    line = [x for x in buf.getvalue().split("\n") if x.strip().startswith("Tiny")]
    assert line and line[0].count("—") == 4, line


def test_the_book_section_never_claims_to_be_an_adjustment():
    import contextlib
    import io as _io
    sel = _bk("DraftKings", 0.58, 120, 0.46)
    rej = _bk("DraftKings", 0.59, 200, 0.60, "loose")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc.report_books(sel, rej)
    out = buf.getvalue()
    assert "MEDIATOR" in out
    assert "nothing here is an adjusted estimate" in out
    assert "FLOOR" in out

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
