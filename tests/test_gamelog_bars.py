"""Player-stat charts are bars now, and a bar has rules a line does not.

Ethan, 2026-08-16: "instead of line charts for the player stats we should
be using bar graphs instead. They are easier to read and we can label
things better."

He is right for a reason worth writing down: a line says the value moved
CONTINUOUSLY between two points, and nothing moves between Tuesday's game
and Thursday's — the player did not pass through 1.4 hits on Wednesday.
These are independent measurements against a threshold, which is a bar's
job.

Two properties are pinned here because both are ways a bar chart lies.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
FN = VIS[VIS.index("function gamelogBars"):VIS.index("/* ---------------- Sparkline")]


def test_every_player_prop_chart_is_bars_now():
    """No prop chart is a line any more.

    The prop boards draw the full `propAnalysis` block Ethan's render
    specifies; one 64x22 inline chip, where axes and a stat row do not
    fit, keeps the bare bars.

    THE COUNT WENT 4 → 3 ON 2026-08-13 AND THAT WAS A DEAD CALL BEING
    REMOVED, not a chart being lost. `gameBetCard` called
    `propAnalysis(r)` on a GAME bet, which has no `recent_values` at all
    — the function's first line returns "" under three values, so that
    call had never once drawn anything. It now calls `gameBetChart`,
    which builds the series out of the team's own results. A call that
    can never render is worse than a missing one: it reads as covered.
    """
    assert "sparkline(r.recent_values" not in APP
    # The two prop boards plus the prop page they open.
    assert APP.count("propAnalysis(r)") == 3
    # And the game-bet card charts too — through the team-log series,
    # which is the only shape that can carry a run line.
    assert APP.count("gameBetChart(r)") == 1
    assert APP.count("gamelogBars(r.recent_values") == 1
    # ONE line chart survives: the live win-probability track. That IS a
    # continuous quantity — the price existed at every instant between
    # two pulls — so the segment between two points is a real claim. A
    # player's per-game stat is not: it has no value on the days he did
    # not play, and on 2026-08-17 Ethan closed the loophole this comment
    # used to defend ("all charts for player props should be the bar
    # graphs") — the profile trend, the history-market chips and the
    # Trending minis all draw bars now. Lines over per-game quantities
    # were also the charts iOS long-press kept trying to select.
    assert APP.count("sparkline(") == 1
    assert APP.count("sparkline(vals") == 1     # the live line track


PA = VIS[VIS.index("function propAnalysis"):VIS.index("/* ---------------- Game-log bars")]


def test_the_hit_rate_is_computed_not_copied_from_the_render():
    """Ethan's render says 8/10 beside ten bars of which five are green.
    It is a mockup and its stat row is placeholder text. Copying 8/10
    would have put a number on the site that its own chart contradicts,
    so the count comes from the data every time."""
    assert "data.filter(won).length" in PA
    assert "8 / 10" not in PA and "80%" not in PA


def test_an_under_bet_is_not_painted_backwards():
    """"Cleared" means the BET cashed. For an UNDER that is the value
    falling below the line, so colouring on `v > line` regardless of side
    would paint an under-bet's winners red."""
    assert "over ? v > line : v < line" in PA


def test_the_line_pill_has_its_own_gutter():
    """It sat inside the plot and covered the last bar's value label —
    caught by rendering it, like the zero-height bar before it."""
    assert "R = narrow ? 46 : 58" in PA
    assert "${W - R + 6}" in PA


def test_the_axis_fits_the_data_it_is_drawn_for():
    """A power-of-ten tick put a 90-yard game on an axis running to 400:
    the bars used the bottom quarter of the plot and every difference
    between them flattened to nothing. That is the clipped-baseline lie
    pointing the other way — the picture understating a real gap — so the
    step comes off a nice-number ladder that still covers the data.

    Checked as arithmetic, not as a string, because the failure was in
    the numbers rather than in the markup.
    """
    import math

    ladder = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]

    def top_for(hi):
        raw = hi / 4
        mag = 10 ** math.floor(math.log10(raw or 1))
        norm = (raw or 1) / mag
        tick = next((c for c in ladder if c >= norm - 1e-9), 10) * mag
        return tick * 4

    for peak in (0.5, 1.5, 8.5, 49.0, 90.0, 148.0, 317.0, 2400.0):
        hi = peak * 1.12
        top = top_for(hi)
        assert top >= hi - 1e-9, f"{peak} does not fit under {top}"
        # The old rule allowed 4x headroom. Half the plot is the floor:
        # below that the bars are a strip along the bottom again.
        assert peak / top > 0.5, f"{peak} only reaches {peak / top:.0%} of {top}"


def test_the_value_labels_survive_the_threshold_rule():
    """A dashed rule ran straight through the labels it crossed. The
    knockout halo is what keeps both readable."""
    assert 'paint-order="stroke"' in PA


def test_the_scale_starts_at_zero():
    """A bar's LENGTH is its value, so a clipped baseline makes a 2 look
    twice a 1.5. This is the most common way a bar chart lies, and it is
    the one thing a restyled sparkline would have inherited — the old one
    scaled from min(data) on purpose, which is right for a line."""
    assert "Math.max(...data, line ?? 0) || 1" in FN
    assert "Math.min(...data" not in FN, "a bar scale must not start at the minimum"


def test_a_zero_game_is_visible():
    """A 0 is DATA — a night the player was blanked, not a night he did
    not play. At a 1px floor it was indistinguishable from empty space on
    a dark panel. Caught by looking at the render; the arithmetic was
    right and the picture lied."""
    assert "Math.max(3, base - top)" in FN
    # And the bar must be anchored to the baseline after the floor is
    # applied, or a floored bar hangs below it.
    assert 'y="${(base - hgt).toFixed(1)}"' in FN


def test_colour_is_never_the_only_encoding():
    """The site's status pair is #42C268 vs #DF5953 — ΔE 7.5 under
    deuteranopia, inside the 6-8 floor band that is legal ONLY with a
    second, non-colour encoding. Red-green is the textbook CVD collision.

    Two non-colour encodings carry it: the threshold is DRAWN, so a bar
    that clears it is simply taller than a visible rule, and the count is
    stated in words. Colour is the third telling, not the first."""
    assert "stroke-dasharray" in FN, "the threshold rule must be drawn"
    assert "cleared ${line}" in FN, "the count must be stated in text"
    assert "aria-label" in FN
    # Text wears a text token, never the series colour.
    assert 'fill="var(--text-mute)"' in FN


def test_the_newest_game_reads_last():
    """Values arrive newest-first; a bar chart reads left to right as
    time, so they are reversed and the newest is the one at full opacity."""
    assert ".reverse()" in FN
    assert 'opacity="${i === n - 1 ? 1 : 0.72}"' in FN


def test_the_card_tint_carries_a_fact():
    """Ethan's render alternates a red and a green card border between two
    cards that are both OVER bets at similar confidence, so there the
    alternation is decoration. A coloured border on a betting card that
    means nothing is worse than no border, so ours carries the same fact
    the bars do: whether recent form backs the side we took."""
    # The rule moved from "at least half" to "at least break-even" on
    # 2026-08-13 — see
    # test_the_hit_rate_is_judged_against_the_price_not_a_coin_flip. What
    # this test guards is unchanged: the tint means SOMETHING, and it is
    # the same something the bars and the stat tile mean.
    assert "const backs = n > 0 && (hits / n) >= be" in PA
    assert 'const tone = backs ? "good" : "bad"' in PA
    assert 'class="prop-analysis pa-${tone}"' in PA
    # And the stat row reads off the SAME variable, so the tint and the
    # hit-rate tile can never disagree.
    assert PA.count('backs ? "pos" : "neg"') == 2


def test_the_stat_row_does_not_label_two_tiles_the_same():
    """A row reading HIT RATE 6/10 · HIT RATE 60% makes the reader check
    whether they are different measurements. They are one measurement in
    two notations, and the labels now say so."""
    assert PA.count('"HIT RATE"') == 1
    assert '"HIT %"' in PA


def test_the_chart_sizes_from_its_own_ratio():
    """A fixed height attribute letterboxes the chart inside a narrow
    column: the SVG scales down to fit the width and the leftover height
    is dead band, which is exactly what a phone got. Ratio-sizing removes
    it at every width, and the viewport cut keeps the labels legible
    rather than shrinking them to 6px with everything else."""
    assert 'height="${H}"' not in PA, "a fixed height letterboxes the plot"
    assert ".pa-chart svg" in CSS and "height: auto" in CSS
    assert 'matchMedia("(max-width: 760px)")' in PA
    assert "const FS = narrow ? 13 : 10" in PA


def test_the_prop_bar_cannot_collide_with_itself():
    """The identity panel this used to guard is gone — it was the
    duplicated face Ethan flagged, and the two-equal-columns version of
    it had put STRIKEOUTS through (UNDER) at 69px a column.

    The same hazard survives the redesign in smaller form: PROP, LINE and
    ODDS now share one horizontal bar, so a long market label must wrap
    rather than run into the price beside it.
    """
    assert ".pa-bar { display: flex" in CSS
    assert "flex-wrap: wrap" in CSS
    assert "overflow-wrap: anywhere" in CSS


def test_the_retired_header_markup_left_no_dead_rules_behind():
    """`.pa-who` / `.pa-sub` styled a header that no longer exists. A
    stylesheet that keeps rules for deleted markup is how the next person
    edits the wrong block."""
    for dead in (".pa-who ", ".pa-sub "):
        assert dead not in CSS, f"{dead} styles markup that is gone"
    assert "pa-who2" in CSS and "pa-who2" in PA


def test_an_anytime_market_gets_the_threshold_it_actually_has():
    """Ethan's Long Shots board, 2026-08-13: every card read "LINE NaN",
    "0 / 10", "0%", ten red bars.

    Not a rendering fault — the arithmetic ran against NaN. A long shot is
    an ANYTIME market ("does he homer at all"), so the row carries
    recent_values and no `line`, and `v > NaN` is false for every game
    ever played. The chart was stating that Brandon Nimmo had not homered
    in ten games while drawing the bars that show three.

    "1 or more" is a threshold, written down elsewhere: 0.5. Reading it
    off the market is not inventing a number. Anything with no derivable
    threshold renders NOTHING, because a chart against an unknown line is
    the same bug wearing a coat.
    """
    assert "Number.isFinite(line)" in PA
    assert "line = 0.5" in PA
    assert "return \"\";" in PA or "return '';" in PA


def test_the_hit_rate_is_judged_against_the_price_not_a_coin_flip():
    """It compared `hits * 2 >= n` — at least half — which is the right
    question only at even money. Nimmo homered in 3 of 10 at +550 and the
    card called it bad; break-even there is 15.4%, so 30% is about double
    what the bet needs. A card contradicting the pick above it is worse
    than a card with no colour on it.

    Checked as arithmetic across the ladder, because the failure was in
    the comparison rather than in the markup.
    """
    assert "r.odds > 0 ? 100 / (r.odds + 100)" in PA
    assert "(hits / n) >= be" in PA

    def be(odds):
        return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)

    def backs(odds, hits, n):
        return (hits / n) >= be(odds)

    # A long shot clearing its price is backed, however far from 50%.
    assert backs(550, 3, 10), "a 30% rate at +550 is roughly double break-even"
    assert backs(375, 4, 10)
    # Even money is unchanged: the old rule and the new agree near -110.
    assert backs(-110, 6, 10) and not backs(-110, 5, 10)
    # And heavy chalk has to clear a HIGHER bar, which the old rule missed
    # in the other direction.
    assert not backs(-200, 6, 10), "60% does not clear break-even at -200"


def test_the_panel_does_not_repeat_a_face_the_card_already_shows():
    """Ethan, 2026-08-13: "we are definitely showing the players face too
    much here." Structural, not a one-page slip — the props card, the long
    shot card and the top-picks card all lead with `playerAvatar`, so the
    92px portrait inside this block was the same photograph twice, forty
    pixels apart. Removing it is also what gave the chart its width."""
    assert "betMark(r, 92)" not in PA
    assert "pa-shot" not in PA and "pa-side" not in PA
    assert ".pa-shot" not in CSS and ".pa-side" not in CSS
    # The prop bar replaced it — the reader still needs the threshold and
    # the price the chart is drawn against.
    assert "pa-bar" in PA and ".pa-bar" in CSS
    # And the plot is no longer sharing its row with anything.
    assert "grid-template-columns: 208px" not in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
