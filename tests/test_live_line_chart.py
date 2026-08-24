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
    # `vals` since 2026-08-18: the track can orient to the BET'S team on
    # an open-bet row (a road bet reads its chance as 100 − p), so the
    # call site draws the possibly-flipped copy. Same series, one chart.
    assert "sparkline(vals" in b
    assert "t.values.map((v) => +(100 - v)" in b, \
        "the away orientation lost its arithmetic"
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


def test_the_fast_scoreboard_merges_instead_of_replacing():
    """Ethan, 2026-08-18: "the live probablility chart definitly doesnt
    show or work." It didn't — and the chart itself was fine. The fast
    scoreboard file (live_mlb.json, the 30-second loop) REPLACED the
    board's game objects wholesale in fetchAllLive, and the fast file
    carries only scores — so line_track AND the odds grid vanished from
    every live card the day the fast loop shipped. The merge keeps fast
    fields where both speak (they are fresher) and board-only fields
    alive."""
    i = APP.index("async function fetchAllLive(")
    fn = APP[i:i + 3000]
    assert "byKey" in fn and "...bg, ...fg" in fn
    assert "games = df.games;" not in fn, "wholesale replacement is back"


def test_every_league_build_attaches_the_track():
    """"we should be showing that for ALL live games" — the wiring that
    was MLB-only rides every league build with a name map for the odds
    feed. CFB joined last (2026-08-18): its 134-school map cannot be a
    hand-written table, so the feed's names resolve through the same
    runtime lookup the odds attach already trusts."""
    for fname in ("mlb_build.py", "nfl_build.py", "nba_build.py",
                  "cfb_build.py"):
        src = open(os.path.join(ROOT, fname), encoding="utf-8").read()
        assert "livelines" in src and ".attach(" in src, fname
        assert "pull_and_record(" in src, fname


def test_cfb_resolves_feed_names_at_runtime_and_pays_only_when_live():
    """The CFB specifics. The adapter must resolve through cfbdata's
    lookup (a checked-in school table is the thing this build refuses to
    have), the paid pull sits behind BOTH the odds flag and a live game,
    and the free attach is outside that gate — the same budget discipline
    the MLB pins above defend."""
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    i = src.index("class _FeedNames")
    assert "cfbdata.resolve_team(name" in src[i:i + 400]
    j = src.index("_ll.pull_and_record", i)
    gate = src[src.rindex("if ", i, j):j]
    assert "_live_games" in gate and "args.odds" in gate
    k = src.index("_ll.attach(", j)
    assert "args.odds" not in src[j + 30:k], \
        "the free attach got folded under the paid gate"


def test_cfb_marks_survive_the_cross_sport_live_tab():
    """The Live tab draws every league at once, but CFB's team table
    rides in its own payload — viewed from the MLB page there is no CFB
    payload in state.data, and every school falls back to a drawn chip.
    The live fetch keeps the last table it saw, and the resolver prefers
    it."""
    i = APP.index("function teamsForSport(")
    assert "_cfbTeams ||" in APP[i:i + 500]
    j = APP.index("async function fetchAllLive(")
    assert '_cfbTeams = d.teams' in APP[j:j + 800]


def test_cfb_games_speak_the_live_dict_every_other_league_speaks():
    """The Live tab keeps a game when live.state == "live" and reads the
    score off that dict. CFB carried only a top-level state, so a
    Saturday in progress never appeared there at all — the parser had
    the score and the clock the whole time."""
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    i = src.index('out["games"] = [')
    # 2600, not 1600: the weather fields (2026-08-24) sit between the
    # opening bracket and the live dict, and the claim here is that the
    # live dict ships, not that it ships within N characters.
    block = src[i:i + 2600]
    assert '"live": {"state": g.get("state", "scheduled")' in block
    for key in ('"home_score"', '"away_score"', '"period"'):
        assert key in block, f"the live dict lost {key}"


def test_open_bet_rows_wear_the_track_for_team_markets():
    """"also for our live bets iff possible" — it is possible exactly
    where the tracked market IS the bet's market family: a moneyline,
    spread or team-total row gets the game's win-probability chart
    oriented to ITS team (a road bet reads 100 − p). Props do NOT get
    it: the game line under a strikeouts bet reads as the prop's own
    odds, which it is not."""
    i = APP.index("const betTrack = (r)")
    fn = APP[i:i + 700]
    assert "TEAM_MKTS.has(r.market)" in fn
    assert 'r.phase !== "live"' in fn, "a finished game must not chart"
    assert "lineTrackHTML(g, team ? { team } : {})" in fn
    j = APP.index("const TEAM_MKTS = new Set")
    assert '"moneyline", "spread", "team_total", "total"' in APP[j:j + 120]


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
