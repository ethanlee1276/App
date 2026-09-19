"""Live win probability: a margin model on a clock, and honest about it.

docs/IDEAS.md filed this under "needs data we do not have" on
2026-08-20 — "needs play-by-play at a latency we do not have". Three
weeks later #136/#137/#138 shipped exactly that latency for five
leagues, and nobody went back to the list. The entry outlived its own
blocker, which is the ordinary way a list rots.

The maths is deliberately the game model's own: `gamebets.MARGIN_SD` is
the SD the pregame moneyline is priced from, so this is that
distribution read from later in the evening rather than a second opinion
with constants of its own to drift.
"""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import livewp                                    # noqa: E402
from engine.gamebets import MARGIN_SD                        # noqa: E402


# ------------------------------------------------------------- the shape

def test_a_pick_em_at_kickoff_is_a_coin_flip():
    assert livewp.win_prob("nfl", 0, 3600, 0) == 0.5


def test_the_pregame_line_is_the_whole_prior_at_kickoff():
    """With no game played, the only information is the line — so the
    number must match what the pregame model itself says about that
    margin, not merely be 'somewhere above half'."""
    from engine.statmath import normal_cdf
    got = livewp.win_prob("nfl", 0, 3600, 6.0)
    assert abs(got - normal_cdf(6.0 / MARGIN_SD["nfl"])) < 1e-9, got


def test_a_lead_is_worth_more_later():
    """The same seven points with a quarter left beats seven at the
    half, because there is less time for it to come back."""
    half = livewp.win_prob("nfl", 7, 1800, 0)
    q4 = livewp.win_prob("nfl", 7, 900, 0)
    assert q4 > half > 0.5


def test_the_line_decays_as_the_game_is_played():
    """A favourite is owed its points evenly. Level at the half, a
    six-point favourite is owed three, not six — most of the edge it was
    given has already failed to appear."""
    at_kick = livewp.win_prob("nfl", 0, 3600, 6.0)
    at_half = livewp.win_prob("nfl", 0, 1800, 6.0)
    assert 0.5 < at_half < at_kick, (at_half, at_kick)


def test_trailing_is_the_mirror_of_leading_in_a_pick_em():
    up = livewp.win_prob("nfl", 7, 900, 0)
    down = livewp.win_prob("nfl", -7, 900, 0)
    assert abs((up + down) - 1.0) < 1e-9


# --------------------------------------------------------------- the ends

def test_a_finished_game_is_read_off_the_scoreboard():
    """No distribution left to integrate: the margin IS the result."""
    assert livewp.win_prob("nfl", 3, 0, 0) == 1.0
    assert livewp.win_prob("nfl", -3, 0, 0) == 0.0


def test_a_tie_at_zero_is_not_a_claim_about_the_game():
    """It is a game going to overtime, which this does not price. 0.5 is
    the honest statement of that rather than a prediction."""
    assert livewp.win_prob("nfl", 0, 0, 0) == 0.5


def test_a_blowout_late_is_allowed_to_read_the_scoreboard():
    """`gamebets` clamps its win probabilities into [0.01, 0.99] because
    a PRICE built on a certainty cannot be wrong and that is never true
    before kickoff. Late in a blowout it is true, and printing 99% on
    four scores with a minute left would be the model refusing to look."""
    assert livewp.win_prob("nfl", 28, 60, 0) > 0.99


def test_the_clock_cannot_run_past_the_game():
    """A feed that reports more time than the sport has must not make a
    lead worth less than it is."""
    assert livewp.win_prob("nfl", 7, 99999, 0) == livewp.win_prob(
        "nfl", 7, 3600, 0)


def test_a_negative_clock_is_a_final_not_an_error():
    assert livewp.win_prob("nfl", 7, -5, 0) == 1.0


# -------------------------------------------------- what it cannot see

def test_the_endgame_window_is_marked_rather_than_hidden():
    """Three up with the ball and forty seconds is a win; three up having
    just punted is a coin flip; this prints the same number for both. The
    row has to say so — the site does not get to publish a number this
    confident without naming where it goes wrong."""
    assert livewp.possession_blind("nfl", 3, 120) is True
    row = livewp.reading("nfl", "SEA", "NE", 3, 120)
    assert row["possession_blind"] is True
    assert "possession" in row["caveat"]


def test_a_two_score_game_is_not_blind():
    """Possession stops deciding once the trailing team needs more than
    one of them."""
    assert livewp.possession_blind("nfl", 14, 120) is False
    assert livewp.reading("nfl", "SEA", "NE", 14, 120)["caveat"] == ""


def test_the_third_quarter_is_not_blind():
    assert livewp.possession_blind("nfl", 3, 1500) is False


def test_basketball_gets_its_own_one_score_width():
    """Six points is one possession in basketball and eight is not; in
    football it is the reverse. A shared constant would mark the wrong
    games in both."""
    assert livewp.possession_blind("nba", 7, 120) is False
    assert livewp.possession_blind("nfl", 7, 120) is True


# ---------------------------------------------------------- the row

def test_both_sides_are_printed_so_nobody_subtracts():
    """A panel showing only the favourite makes the reader do the
    arithmetic, and they get it wrong on a pick'em."""
    row = livewp.reading("nfl", "SEA", "NE", 7, 900, 0)
    assert abs(row["home_win_prob"] + row["away_win_prob"] - 1.0) < 0.001
    assert row["leader"] == "SEA"


def test_the_trailing_side_is_named_as_the_leader_when_it_leads():
    row = livewp.reading("nfl", "SEA", "NE", -7, 900, 0)
    assert row["leader"] == "NE", row


def test_the_row_says_what_the_number_is_built_from():
    """"Win probability" on a sports site is assumed to mean a fitted
    play-by-play model. This one is a margin and a clock, and the row
    says which so nobody has to guess how much to trust it."""
    row = livewp.reading("nfl", "SEA", "NE", 0, 1800)
    assert row["basis"] == "score and clock against the pregame line"


# -------------------------------------------------------- the boundaries

def test_each_league_gets_its_own_regulation_length():
    """Five minutes left is 10.4% of a 2880-second game and 8.3% of a
    3600-second one — so the SHORTER game has proportionally more left
    to play, and the same six-point lead is worth LESS there. A shared
    constant would misprice every hoops lead, in that direction.

    Exercised through the explicit override, because the sport itself is
    refused — see the test below."""
    assert livewp.REGULATION_S["nba"] == 2880
    assert livewp.REGULATION_S["wnba"] == 2400
    shorter = livewp.win_prob("nfl", 6, 300, 0, regulation_s=2880)
    longer = livewp.win_prob("nfl", 6, 300, 0, regulation_s=3600)
    assert shorter < longer, (shorter, longer)


def test_a_clock_this_module_knows_is_not_permission_to_price_it():
    """Basketball has a regulation length here and no measured margin SD
    in `gamebets`. The refusal wins: a live panel is not a licence to
    invent a number the pregame model would not print, and NBA turns on
    the day its SD is measured with no change to this file."""
    assert "nba" in livewp.REGULATION_S
    from engine.gamebets import MARGIN_SD as _sd_table
    assert "nba" not in _sd_table
    try:
        livewp.win_prob("nba", 6, 300, 0)
    except ValueError as exc:
        assert "nba" in str(exc), exc
    else:
        raise AssertionError("priced basketball off another sport's SD")


def test_a_sport_with_no_measured_margin_sd_refuses_rather_than_borrows():
    """`gamebets._sd` exists so one sport never silently prices on
    another's variance. A live panel is not a licence to break that."""
    try:
        livewp.win_prob("cricket", 7, 900, 0)
    except Exception as exc:
        assert "cricket" in str(exc) or "margin SD" in str(exc), exc
    else:
        raise AssertionError("priced a sport with no measured SD")


def test_nothing_prices_or_journals_off_this():
    """It is a reading of a game in progress, not an input to a stake.
    The moment it becomes one it needs the measurement against real
    in-game closes that it has never had."""
    import pathlib
    root = pathlib.Path(ROOT)
    for rel in ("engine/betting.py", "engine/gamebets.py",
                "engine/ledger.py", "engine/likely.py"):
        assert "livewp" not in (root / rel).read_text(), rel


def test_the_idea_list_no_longer_calls_this_impossible():
    """The entry outlived its blocker by three weeks. A list that keeps
    a dead reason is worse than no list — it is how the same idea gets
    refused twice on grounds that stopped being true."""
    doc = open(os.path.join(ROOT, "docs", "IDEAS.md"), encoding="utf-8").read()
    dead = doc.split("Ideas that need data we do not have", 1)[1]
    assert "live win probability" not in dead.lower(), \
        "IDEAS.md still lists live win probability as unbuildable"


# ------------------------------------------------- the clock, off the feed

def test_a_period_and_a_clock_become_seconds_of_regulation():
    assert livewp.seconds_left("nfl", 1, "15:00") == 3600
    assert livewp.seconds_left("nfl", 3, "05:00") == 1200
    assert livewp.seconds_left("nfl", 4, "0:00") == 0


def test_basketball_quarters_are_shorter_and_are_not_footballs():
    """Twelve-minute quarters, not fifteen. A shared period length would
    put every hoops game an hour ahead of itself."""
    assert livewp.seconds_left("nba", 4, "2:00") == 120
    assert livewp.seconds_left("nba", 1, "12:00") == 2880


def test_a_tenths_clock_parses_rather_than_failing():
    """ESPN gives "00:37.5" inside the last minute. Refusing it would
    blank the panel exactly when the game is most worth watching."""
    assert livewp.seconds_left("nfl", 4, "00:37.5") == 37.5


def test_overtime_returns_no_reading_at_all():
    """Past regulation this model has no claim: overtime is a fresh coin
    flip with its own rules. Pretending the clock ran to zero would print
    a certainty on a tied game."""
    assert livewp.seconds_left("nfl", 5, "10:00") is None


def test_a_missing_clock_is_not_read_as_a_final():
    """Guessing "0:00" from an empty string turns every pre-game card
    into a finished game — the failure that reads as ordinary data."""
    assert livewp.seconds_left("nfl", 2, "") is None
    assert livewp.seconds_left("nfl", 2, None) is None
    assert livewp.seconds_left("nfl", None, "10:00") is None


def test_a_clock_too_long_for_the_period_is_refused():
    """20:00 in an NFL quarter is not an NFL clock. Trusting it would
    make the game longer than the sport."""
    assert livewp.seconds_left("nfl", 2, "20:00") is None


def test_a_sport_with_no_clock_table_is_refused_not_guessed():
    assert livewp.seconds_left("mlb", 4, "5:00") is None
    assert livewp.seconds_left("cricket", 1, "5:00") is None


def test_the_period_count_and_the_regulation_length_cannot_disagree():
    """Both tables are consulted for the same fact. If one gains a sport
    the other has not, a period length silently becomes wrong rather
    than absent."""
    assert set(livewp.PERIODS) <= set(livewp.REGULATION_S)
    for sport, n in livewp.PERIODS.items():
        assert livewp.REGULATION_S[sport] % n == 0, sport


# ------------------------------------------- and onto the live scoreboard


class _State:
    """The `livescores` state object, cut to what `_row` reads."""
    state = "live"
    home_score, away_score = 17, 10
    period, clock = 3, "05:00"
    detail = start_time = ""
    yard_line = possession = None


def _live_row(league="nfl", **kw):
    import livescore_build as lb
    st = _State()
    for k, v in kw.items():
        setattr(st, k, v)
    return lb._row({"event_id": "1", "home": "SEA", "away": "NE",
                    "home_name": "Seahawks", "away_name": "Patriots",
                    "live": st}, league)["live"]


def test_a_live_football_game_carries_a_reading():
    wp = _live_row()["win_prob"]
    assert wp["leader"] == "SEA"
    assert 0.5 < wp["home_win_prob"] < 1.0
    assert wp["seconds_left"] == 1200


def test_the_leader_is_named_by_its_own_abbreviation():
    """"home" and "away" in a payload make the front end resolve them
    again against a merge key it has already resolved once, and that
    round trip is where the live tab lost a league to another one."""
    wp = _live_row(home_score=10, away_score=17)["win_prob"]
    assert wp["leader"] == "NE", wp


def test_a_pre_game_card_gets_no_reading_rather_than_a_coin_flip():
    """A confident 50% on a game that has not kicked off is worse than
    an absent panel: it looks like information."""
    assert "win_prob" not in _live_row(state="pre", period=0, clock="")


def test_a_final_gets_no_live_reading():
    """The scoreboard already says who won. A panel restating it as
    100% is noise on the one card that needs none."""
    assert "win_prob" not in _live_row(state="post")


def test_a_sport_with_no_clock_table_shows_no_panel_and_still_scores():
    """Baseball has no game clock at all, so there is nothing to read."""
    row = _live_row(league="mlb")
    assert "win_prob" not in row
    assert row["home_score"] == 17


def test_a_refused_margin_sd_is_swallowed_and_the_score_survives():
    """BASKETBALL, not baseball — and the difference is the whole test.
    MLB bails on the clock before the SD is ever consulted, so it never
    exercises the refusal. NBA parses a clock fine and then `_sd` raises
    for having no measured margin variance. That raise must not take the
    scoreboard down with it: the page still wants the score."""
    from engine.gamebets import MARGIN_SD
    from engine import livewp as _wp
    assert _wp.seconds_left("nba", 4, "02:00") == 120   # the clock is fine
    assert "nba" not in MARGIN_SD                       # the variance is not
    row = _live_row(league="nba", period=4, clock="02:00")
    assert "win_prob" not in row
    assert row["home_score"] == 17


def test_the_endgame_caveat_reaches_the_payload():
    wp = _live_row(home_score=13, away_score=10, period=4,
                   clock="02:00")["win_prob"]
    assert wp["possession_blind"] is True
    assert "possession" in wp["caveat"]


def test_the_reading_is_nested_so_absent_is_not_zero():
    """Loose keys would hand the card `null` to tell apart from "this
    sport has no such thing", which are different facts — the same
    reason `yard_line` is absent rather than null beside it."""
    assert isinstance(_live_row()["win_prob"], dict)
    assert "home_win_prob" not in _live_row()


# ------------------------------------------------ and onto the page itself

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _card_fn():
    i = APP.index("function pbpModelWinProbHTML(")
    return APP[i:APP.index("\nfunction ", i + 10)]


def test_the_card_is_drawn_in_the_play_by_play_rail():
    page = APP[APP.index("async function renderPbpPage("):]
    page = page[:page.index("\n}\n")]
    assert "${pbpModelWinProbHTML(d)}" in page, page[-600:]


def test_it_reads_the_server_side_number_and_does_not_recompute_it():
    """The maths lives in `engine/livewp`. Writing the normal CDF again
    in JavaScript is the two-copies-of-one-rule mistake that left
    baseball game cards with no book name for a fortnight."""
    card = _card_fn()
    assert "live || {}).win_prob" in card
    for banned in ("Math.exp", "Math.sqrt", "erf", "MARGIN_SD"):
        assert banned not in card, banned


def test_no_block_means_no_card_rather_than_a_neutral_fifty():
    """Absent is the answer for a pre-game card, overtime, an unreadable
    clock, or a sport with no measured variance — and the page does not
    need to tell those apart. A 50% on a game that has not kicked off
    looks like information and is not."""
    card = _card_fn()
    assert 'if (!wp || wp.home_win_prob == null) return "";' in card
    # The only early exit is the empty string. A fallback probability
    # anywhere in here would be the card inventing a reading the server
    # deliberately declined to give it.
    code = "\n".join(ln for ln in card.splitlines()
                      if not ln.strip().startswith(("*", "/*")))
    assert code.count("return ") == 2, code          # the guard, and the card
    assert 'return "";' in code


def test_both_teams_are_drawn_not_just_the_favourite():
    card = _card_fn()
    assert "[wp.home, wp.home_win_prob], [wp.away, wp.away_win_prob]" in card


def test_the_endgame_caveat_is_rendered_when_the_row_carries_it():
    card = _card_fn()
    assert "wp.possession_blind ?" in card
    assert "escapeHtml(wp.caveat)" in card


def test_every_value_from_the_payload_is_escaped():
    """Team abbreviations and the basis string come from a feed. This
    file has been bitten by unescaped feed text before."""
    card = _card_fn()
    assert "escapeHtml(wp.basis)" in card
    assert "escapeHtml(String(t || \"\"))" in card


def test_the_card_says_it_is_ours_and_that_nothing_is_staked_on_it():
    """The rail already carries the market's line track directly above.
    Two probabilities about one game, unlabelled, is worse than one."""
    card = _card_fn()
    assert "Ours" in card
    assert "not a" in card and "staked" in card


def test_the_bar_has_styling_to_render_at_all():
    """Each class needs its OWN rule, not merely the substring:
    `.pbp-wp-bar i` contains `.pbp-wp-bar`, so a plain `in` check passes
    while the bar itself has no height and renders as nothing."""
    import re as _re
    for cls in (".pbp-wp-row", ".pbp-wp-bar", ".pbp-wp-blind", ".pbp-wp-tm"):
        assert _re.search(_re.escape(cls) + r"\s*\{", CSS), cls


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
