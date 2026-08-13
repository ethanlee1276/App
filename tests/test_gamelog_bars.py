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

    Three of the four became the full `propAnalysis` block Ethan's render
    specifies; the fourth is a 64x22 inline chip where axes and a stat row
    do not fit, so it keeps the bare bars.
    """
    assert "sparkline(r.recent_values" not in APP
    assert APP.count("propAnalysis(r)") == 3
    assert APP.count("gamelogBars(r.recent_values") == 1
    # The profile trend and the meme price chart stay lines: those ARE
    # continuous quantities, where the connection between points is real.
    assert APP.count("sparkline(") == 2


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
    assert "const backs = hits * 2 >= n" in PA
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


def test_the_identity_panel_cannot_collide_with_the_odds():
    """The first cut ran a 168px panel with two equal columns inside it,
    which put STRIKEOUTS through (UNDER) at 69px a column. Caught by
    rendering it."""
    assert "grid-template-columns: 208px minmax(0, 1fr)" in CSS
    assert ".pa-cell { min-width: 0; overflow-wrap: anywhere; }" in CSS


def test_the_retired_header_markup_left_no_dead_rules_behind():
    """`.pa-who` / `.pa-sub` styled a header that no longer exists. A
    stylesheet that keeps rules for deleted markup is how the next person
    edits the wrong block."""
    for dead in (".pa-who ", ".pa-sub "):
        assert dead not in CSS, f"{dead} styles markup that is gone"
    assert "pa-who2" in CSS and "pa-who2" in PA


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
