"""The live line chart on the live board.

Ethan, 2026-08-14, holding up a sportsbook's in-play chart: "when games
are live, can we track the live line like this. Like we pull the updated
line every so often and show this chart with the live games. Only if it
doesn't cost us an arm and a leg to pull those lines all the time."

The cost half is measured in `test_livelines.py` — one credit a pull for
the whole slate, because the BOARD endpoint bills per market while the
event endpoint bills per market per game. This file is the other half:
that the number reaches the page, and that drawing it stays free.

TWO THINGS ARE PINNED HERE AND BOTH ARE ABOUT NOT SPENDING MONEY.

  1. ATTACHING IS UNCONDITIONAL, PULLING IS NOT. The history sits on
     disk, so every 60-second rebuild can draw the chart for nothing. If
     the attach were ever put behind the same `args.odds` gate as the
     pull, the chart would blink out on every cached cycle and look
     broken — and the obvious "fix" for that is to pull more often.

  2. THE PULL IS BEHIND THE BUDGET. A live chart is a nice-to-have. It
     must never be the reason tonight's board went unpriced.

And one that is about honesty: the chart's axis is de-vigged probability,
labelled as the MARKET's number. It is not our model's win probability
and must never read as if it were.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()


def _block():
    i = APP.index("function lineTrackHTML(")
    return APP[i:APP.index("\n}\n", i)]


# --- the build side ---------------------------------------------------------
def test_the_pull_only_happens_when_a_game_is_live():
    """Pre-game movement is already recorded free by `linemoves`. Paying
    the live endpoint for it would be buying the same fact twice."""
    i = BUILD.index("_ll.pull_and_record")
    before = BUILD[max(0, i - 700):i]
    assert "_live_games" in before and 'state") == "live"' in before


def test_attaching_is_not_behind_the_odds_flag():
    """THE ONE THAT MATTERS. `_ll.attach` reads a file we already wrote.
    Gating it on `args.odds` would blank the chart on every cached cycle
    — which looks like a bug, and whose tempting fix is to pull more."""
    i = BUILD.index("_ll.attach(")
    # Walk back to the start of the enclosing statement's line and check
    # nothing between the paid pull and here re-opens an `args.odds` test.
    seg = BUILD[BUILD.index("_ll.pull_and_record"):i]
    assert "args.odds" not in seg, "the free attach got folded under the paid gate"


def test_the_pull_is_and_the_attach_is_not(  # noqa: D401
):
    """Stated the other way round, so the pair cannot drift apart."""
    i = BUILD.index("_ll.pull_and_record")
    line_start = BUILD.rindex("\n", 0, i)
    guard = BUILD[max(0, line_start - 200):line_start]
    assert "args.odds" in guard


def test_tonights_chart_cannot_open_with_an_earlier_meeting():
    """The file is append-only across the season and these two teams play
    a dozen times. Without a cut the chart's first point is from May."""
    assert "_since = _dt_since(args.date)" in BUILD
    assert "_ll.attach(result[\"games\"], \"mlb\", since=_since)" in BUILD


def test_the_day_cut_matches_the_slate_day():
    """5 AM, the same roll `launch._slate_date` uses — a west-coast game
    running past midnight belongs to the night it started."""
    i = BUILD.index("def _dt_since(")
    fn = BUILD[i:BUILD.index("\ndef ", i + 1)]
    assert "hour=5" in fn


def test_a_broken_feed_never_fails_the_build():
    """Everything else on this page is the actual product."""
    i = BUILD.index("from engine import livelines as _ll")
    block = BUILD[max(0, i - 200):BUILD.index("live line tracking unavailable", i) + 40]
    assert "try:" in block and "except Exception" in block


# --- the render side --------------------------------------------------------
def test_the_card_draws_the_track():
    i = APP.index("function liveCardHTML(")
    assert "${lineTrackHTML(g)}" in APP[i:i + 2600]


def test_a_game_with_no_history_draws_nothing():
    """Not an empty frame, not a "no data" box — nothing. Most games will
    have no track for their first half hour."""
    assert 'if (!t || !(t.values || []).length) return "";' in _block()


def test_it_reuses_the_sparkline_rather_than_growing_a_second_chart():
    """Chart isolation: one line chart in the codebase, one bar chart. A
    second implementation of either is two things to keep correct."""
    b = _block()
    assert "sparkline(t.values" in b
    assert "<svg" not in b, "the track is hand-rolling its own chart"


def test_the_even_money_rule_is_drawn():
    """50% is where the market stops calling this team the favourite —
    the one crossing on the axis worth marking."""
    assert "line: 50" in _block()


def test_the_values_are_handed_over_newest_first():
    """`sparkline` takes newest-first and reverses internally. The Python
    side builds `values` that way (test_livelines) and this passes it
    straight through — no reverse on either side, or the night is drawn
    backwards."""
    b = _block()
    assert ".reverse()" not in b and "[...t.values].reverse" not in b


def test_labels_ride_with_the_values():
    """Same order discipline that broke the game-log bars once: a label
    list built separately from the values it captions drifts."""
    assert "labels: t.labels" in _block()


def test_it_says_whose_number_this_is():
    """Not our model. A reader who thinks this is our win probability is
    reading our confidence off a book's price."""
    b = _block()
    assert "market" in b.lower()
    assert "not ours" in b


def test_a_flat_line_is_not_coloured_as_a_move():
    """A 0.4-point drift painted green reads as a swing that did not
    happen."""
    assert "Math.abs(move) < 1" in _block()


def test_a_half_point_wobble_is_not_drawn_as_a_collapse():
    """CAUGHT IN CHROMIUM, not in review. The first build charted a night
    that went 50.4 → 49.9 → 50.3 as a dramatic V filling the whole card,
    because a bare sparkline autoscales to whatever it is handed — the
    same "cliff where nothing happened" problem the probability axis was
    chosen to avoid, reappearing on the other axis.

    `minSpan` floors the vertical domain at 20 points of probability, so
    a market that barely moved draws as a market that barely moved."""
    assert "minSpan: 20" in _block()


def test_min_span_is_opt_in_so_existing_charts_are_untouched():
    """Two other callers use `sparkline` for game logs and coin prices,
    where autoscaling is exactly right. A default of anything but 0 would
    silently flatten both."""
    vis = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
    i = vis.index("const minSpan =")
    assert "Number(opts.minSpan) || 0" in vis[i:i + 80]
    # And it only ever WIDENS the domain — a minSpan smaller than the real
    # range must not crop points off the chart.
    guard = vis[i:i + 260]
    assert "if (hi - lo < minSpan)" in guard


def test_the_track_has_styling():
    for sel in (".lb-track", ".lb-track-head", ".lb-move.up", ".lb-move.down"):
        assert sel in CSS, f"{sel} is unstyled"


def test_the_chart_fills_the_card_rather_than_overflowing_it():
    """The sparkline is emitted at a fixed pixel width; the card is
    fluid. Without this the chart is clipped on a narrow phone."""
    i = CSS.index(".lb-track .spark")
    assert "width: 100%" in CSS[i:i + 120]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
