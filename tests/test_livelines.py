"""The live line, charted, for one credit a pull.

Ethan, 2026-08-14: "when games are live, can we track the live line like
this... Only if it doesn't cost us an arm and a leg to pull those lines
all the time."

The cost question had a real answer and it was not the obvious one. The
API bills per MARKET per REGION, so the price of live tracking is set by
WHICH ENDPOINT is called, not by how often:

    event endpoint   8 credits × every game × every pull
    board endpoint   1 credit  × every market, whatever the slate size

15 games polled every 5 minutes for 6 hours is 8,640 credits on the first
and 72 on the second. The free plan is 500 a month. So this module calls
the board endpoint and asks for exactly one market, and the tests below
pin that — a second market on the list doubles the bill forever, silently.

The other half is what gets drawn. American odds cannot be charted: they
have a hole in the middle (-101 → +101 with nothing between), so a hair
of movement across even money draws a cliff. De-vigged probability is the
same information without the hole.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import livelines as ll                    # noqa: E402


def _ev(eid, home, away, books, commence="2020-01-01T00:00:00Z"):
    """A board-endpoint event carrying h2h prices per book."""
    return {"id": eid, "home_team": home, "away_team": away,
            "commence_time": commence,
            "bookmakers": [
                {"key": k, "title": k, "markets": [{"key": "h2h", "outcomes": [
                    {"name": home, "price": p[0]},
                    {"name": away, "price": p[1]}]}]}
                for k, p in books.items()]}


TEAMS = {"Chicago Cubs": "CHC", "Milwaukee Brewers": "MIL"}


# --- the cost, which is the whole question ----------------------------------
def test_the_market_list_is_the_whole_bill():
    """Every name here is another credit on every pull, forever. It was
    `h2h` alone on a 500-credit month; Ethan upgraded a key to 100k
    (pool 105,284) and three markets became 6.2% of it."""
    assert tuple(ll.LIVE_MARKETS) == ("h2h", "spreads", "totals")


def test_a_pull_costs_one_credit_PER_MARKET_whatever_the_slate_size():
    """The board endpoint bills per market, not per game. That is the
    entire reason live tracking is affordable at all — thirty games cost
    the same as three."""
    assert ll.credits_per_pull() == 3
    assert ll.credits_per_pull(("h2h",)) == 1
    assert ll.credits_per_pull(("h2h", "totals")) == 2


def test_only_the_moneyline_can_answer_a_bet():
    """Recorded here because it is a MODELLING limit, not a cost one, and
    the two are easy to confuse now that all three markets are pulled. A
    moneyline has no line, so de-vigging today's price answers exactly the
    question the bet asks. A spread or total is quoted at the MARKET's
    number: a live price on -0.5 says nothing direct about a -1.5 ticket.
    Converting needs the dispersion of finals around a live line, and no
    sample of that exists yet — the recording is what will build one."""
    import inspect
    src = inspect.getsource(ll)
    assert "alternate" in src.lower() or "ITS number" in src


def test_the_cadence_follows_the_plan_rather_than_a_guess():
    """Ethan, 2026-08-14: "i upgraded 1 of the api keys to 100k credits a
    month so we can adjust acordingly."

    The first version pinned the gap at 30 minutes because that is what a
    500-credit free month can carry. That was a fact about ONE PLAN
    written into the code as if it were a fact about the world, and the
    moment the plan changed the chart kept crawling for no reason. The
    budget already learns the real quota from the API's own
    `x-requests-remaining` header; the cadence now asks it."""
    starved = ll.gap_for(0)
    free = ll.gap_for(16)                    # ~500/month
    paid = ll.gap_for(2763)                  # ~100k/month
    assert starved == ll.LIVE_GAP_CEILING_S
    assert free == ll.LIVE_GAP_CEILING_S
    assert paid == ll.LIVE_GAP_FLOOR_S
    assert paid < free, "a bigger plan does not poll faster"


def test_the_gap_never_leaves_its_bounds():
    """However rich or broke the month, the answer stays sane. An
    unbounded division is how a 10-million-credit plan ends up polling
    every two seconds for a chart that redraws once a minute."""
    for allowance in (0, 1, 16, 100, 541, 2763, 10 ** 7):
        gap = ll.gap_for(allowance)
        assert ll.LIVE_GAP_FLOOR_S <= gap <= ll.LIVE_GAP_CEILING_S, (allowance, gap)


def test_the_floor_exists_because_faster_buys_the_same_picture():
    """`series` collapses consecutive identical prices, so polling a quiet
    market harder spends credits and draws the same line. Five minutes is
    where the extra spend stops buying signal."""
    assert ll.LIVE_GAP_FLOOR_S == 5 * 60


def test_the_chart_never_gets_more_than_its_share_of_the_day():
    """The board's own pricing is the thing that makes money. A
    nice-to-have must not be able to outbid it however large the plan
    gets."""
    for allowance in (16, 541, 2763, 10 ** 6):
        a_night = (ll.LIVE_WINDOW_S / ll.gap_for(allowance)) * ll.credits_per_pull()
        assert a_night <= max(1.0, allowance * ll.LIVE_BUDGET_SHARE) + 1e-9 \
            or ll.gap_for(allowance) == ll.LIVE_GAP_CEILING_S, allowance


def test_a_broke_month_falls_back_to_the_slowest_cadence():
    """Not to zero, and not to an exception: the chart keeps drawing from
    stored history either way, and the pull is separately budget-gated."""
    assert ll.gap_for(0) == ll.LIVE_GAP_CEILING_S
    assert ll.gap_for(-5) == ll.LIVE_GAP_CEILING_S


def test_the_narrow_pull_does_not_clobber_the_full_board_cache():
    """`fetch_sport_odds` keys its cache by sport alone. A one-market live
    pull writing over a three-market board pull would have the board read
    back a payload with no spreads and no totals in it and conclude the
    books had stopped posting them — a data outage manufactured by a
    filename. The tag keeps the two apart."""
    import inspect
    src = inspect.getsource(ll.pull_and_record)
    assert 'cache_tag="live"' in src
    from engine.sources import oddsapi
    assert "cache_tag" in inspect.signature(oddsapi.fetch_sport_odds).parameters
    # And the default stays empty, so the existing CFB caller's filename
    # is byte-for-byte what it was.
    assert inspect.signature(oddsapi.fetch_sport_odds).parameters[
        "cache_tag"].default == ""


def test_the_cadence_gate_is_only_about_time():
    """Budget is `oddsbudget`'s answer, asked separately. If this function
    ever started deciding affordability too, a live chart could become the
    reason tonight's board went unpriced."""
    assert ll.affordable(0, now=600, gap=600) is True
    assert ll.affordable(100, now=699, gap=600) is False
    # The names the compiled body actually reaches for — the docstring
    # explains the separation, so it has to be the CODE that is checked.
    names = set(ll.affordable.__code__.co_names)
    assert not names & {"oddsbudget", "remaining", "load", "pool_remaining"}, \
        f"the cadence gate reads budget state: {names}"


# --- de-vig -----------------------------------------------------------------
def test_an_even_two_sided_market_is_a_coin_flip():
    assert abs(ll.devig_pair(-110, -110) - 0.5) < 1e-9


def test_the_vig_is_removed_not_ignored():
    """-110/-110 implies 52.4% + 52.4% = 104.8%. The 4.8% is the book's
    take and must not survive into a probability."""
    raw = ll._implied(-110) * 2
    assert raw > 1.0
    assert abs(ll.devig_pair(-110, -110) * 2 - 1.0) < 1e-9


def test_a_favourite_reads_above_half():
    p = ll.devig_pair(-200, +170)
    assert 0.5 < p < 1.0


def test_one_sided_quotes_are_not_completed():
    """A book quoting only the favourite is a book with no opinion on the
    dog's price. Inventing the other side is how fake edges get made."""
    assert ll.devig_pair(-150, None) is None
    assert ll.devig_pair(None, +130) is None
    assert ll.devig_pair(-150, 0) is None


def test_the_consensus_never_mixes_two_books_sides():
    """THE ONE THAT MATTERS. Book A has the home side at -300 and no away
    price; book B has the away side at +400 and no home price. Pairing
    across them gives 75% + 20% = 95% — an arbitrage that exists only in
    our arithmetic. Neither book quoted a market, so there is no point."""
    by_book = {"A": {"CHC": -300}, "B": {"MIL": +400}}
    assert ll.event_probability(by_book, "CHC", "MIL") is None


def test_the_consensus_is_the_median_of_complete_books():
    by_book = {"A": {"CHC": -110, "MIL": -110},     # 0.500
               "B": {"CHC": -110, "MIL": -110},     # 0.500
               "C": {"CHC": -300, "MIL": +250}}     # ~0.72
    agg = ll.event_probability(by_book, "CHC", "MIL")
    assert agg["books"] == 3
    assert abs(agg["p_home"] - 0.5) < 1e-9, "an outlier book moved the median"


def test_the_displayed_price_is_the_best_one_available():
    """The probability comes from complete books; the number shown to a
    reader is the best price they could actually get, which can come from
    a book that only quotes one side."""
    by_book = {"A": {"CHC": -110, "MIL": -110}, "B": {"MIL": +105}}
    agg = ll.event_probability(by_book, "CHC", "MIL")
    assert agg["away_odds"] == 105
    assert agg["books"] == 1


# --- snapshots --------------------------------------------------------------
def test_a_live_game_is_captured():
    rows = ll.snapshot_rows([_ev("e1", "Chicago Cubs", "Milwaukee Brewers",
                                 {"A": (-110, -110)})],
                            TEAMS, "mlb", ts=1000, now=1_600_000_000)
    assert len(rows) == 1 and rows[0]["home"] == "CHC" and rows[0]["p_home"] == 0.5


def test_a_game_that_has_not_started_is_skipped():
    """Pre-game movement is already recorded free by `linemoves`. Paying
    for it twice is the definition of an arm and a leg."""
    ev = _ev("e1", "Chicago Cubs", "Milwaukee Brewers", {"A": (-110, -110)},
             commence="2030-01-01T00:00:00Z")
    assert ll.snapshot_rows([ev], TEAMS, "mlb", ts=1000, now=1_600_000_000) == []


def test_an_unresolvable_team_is_dropped_not_guessed():
    """A chart is a time series. One point stored under a guessed key
    silently belongs to a different game's line."""
    ev = _ev("e1", "Chicago Cubs", "Some Other Club", {"A": (-110, -110)})
    assert ll.snapshot_rows([ev], TEAMS, "mlb", ts=1000, now=1_600_000_000) == []


def test_a_naive_start_time_is_not_treated_as_live():
    """A bare clock is not an instant; guessing a zone onto it decides
    which games count as live, and a wrong guess charts a game that has
    not begun."""
    ev = _ev("e1", "Chicago Cubs", "Milwaukee Brewers", {"A": (-110, -110)},
             commence="2020-01-01T00:00:00")
    assert ll.snapshot_rows([ev], TEAMS, "mlb", ts=1000, now=1_600_000_000) == []


# --- storage and series -----------------------------------------------------
def _tmp():
    return os.path.join(tempfile.mkdtemp(), "live_lines.jsonl")


def _write(path, pts, home="CHC", away="MIL", sport="mlb"):
    ll.record([{"ts": t, "sport": sport, "event_id": "e1", "home": home,
                "away": away, "p_home": p, "books": 3,
                "home_odds": -110, "away_odds": -110} for t, p in pts], path)


def test_a_round_trip_keeps_order():
    path = _tmp()
    _write(path, [(3, 0.6), (1, 0.5), (2, 0.55)])
    assert [r["ts"] for r in ll.load(path)] == [1, 2, 3]


def test_a_truncated_line_does_not_blank_the_chart():
    """The file is written by an append that can be interrupted."""
    path = _tmp()
    _write(path, [(1, 0.5), (2, 0.6)])
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"ts": 3, "p_home": 0.7')      # killed mid-write
    assert len(ll.load(path)) == 2


def test_an_earlier_meeting_is_cut_off():
    """The same two teams meet many times a season into one append-only
    file. Without the cut, tonight's chart opens with last month's line."""
    path = _tmp()
    _write(path, [(100, 0.4), (5000, 0.5), (5100, 0.6)])
    assert len(ll.series(ll.load(path), "CHC", "MIL", since=1000)) == 2


def test_a_flat_stretch_is_not_drawn_as_a_staircase():
    """Consecutive identical prices are one fact reported twice — the book
    had not moved. Keeping them makes the chart's step width our polling
    interval rather than the market's actual movement."""
    path = _tmp()
    _write(path, [(1, 0.5), (2, 0.5), (3, 0.5), (4, 0.62)])
    assert [r["p_home"] for r in ll.series(ll.load(path), "CHC", "MIL")] == [0.5, 0.62]


def test_another_games_points_never_join_this_series():
    path = _tmp()
    _write(path, [(1, 0.5), (2, 0.6), (3, 0.7)])
    _write(path, [(1, 0.1), (2, 0.2)], home="NYY", away="BOS")
    assert len(ll.series(ll.load(path), "CHC", "MIL")) == 3


# --- the chart block --------------------------------------------------------
def test_the_track_is_newest_first_to_match_every_other_chart():
    """`visuals.js` takes values newest-first and reverses them itself.
    Handing it oldest-first draws the whole night backwards."""
    path = _tmp()
    _write(path, [(1, 0.40), (2, 0.55), (3, 0.70)])
    t = ll.track_for(ll.load(path), "CHC", "MIL")
    assert t["values"] == [70.0, 55.0, 40.0]
    assert t["opened"] == 40.0 and t["now"] == 70.0


def test_labels_stay_pinned_to_their_points():
    path = _tmp()
    _write(path, [(1, 0.40), (2, 0.55), (3, 0.70)])
    t = ll.track_for(ll.load(path), "CHC", "MIL")
    assert len(t["labels"]) == len(t["values"])


def test_two_points_is_not_a_chart():
    """Below the floor the caller shows the current price instead of
    drawing a line between two dots and calling it a trend."""
    path = _tmp()
    _write(path, [(1, 0.5), (2, 0.6)])
    assert ll.track_for(ll.load(path), "CHC", "MIL") is None


def test_a_game_with_no_history_returns_nothing_rather_than_an_empty_chart():
    assert ll.track_for([], "CHC", "MIL") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
