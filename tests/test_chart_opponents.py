"""The bars are labelled with who the game was against, not 1-10.

Ethan, 2026-08-13, circling the row of numbers under the chart: "instead
of showing 1-10 under the graphs, we should show 'vs whatever team they
played that game'."

The numbers were never information — they counted the bars, which the
reader can already see. The opponent is the one thing a bar cannot say
for itself and the first thing anyone asks about a three-strikeout game:
three against WHO.

NO NEW DATA WAS NEEDED. Every pipeline builds `recent_values` as
`[g.value for g in prop.logs]`, so `logs` is index-aligned with it —
same rows, same order — and the log table under the chart has been
printing those opponents all along. The chart simply never looked.

THE ORDER IS THE WHOLE RISK. `recent_values` is newest-first; the chart
reverses to oldest-first so time runs left to right. Labels that do not
reverse with it caption every bar with the wrong game and look
completely fine doing it — a chart that is confidently wrong, which is
the failure mode this file exists to prevent.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
PA = VIS[VIS.index("function propAnalysis("):
         VIS.index("/* ---------------- Game-log bars")]


# --- where the names come from ---------------------------------------------
def test_the_axis_prints_the_opponent():
    assert "const axisText = (i) =>" in PA
    assert "labels[i]" in PA
    assert ">${i + 1}</text>" not in PA, "the bar index is still the axis label"


def test_the_labels_are_taken_from_the_log_that_built_the_values():
    """`recent_values` IS `[g.value for g in prop.logs]` in every
    pipeline. Reading the opponent from anywhere else would be a second
    source that can disagree with the bar above it."""
    assert "labelsOf(r.logs)" in PA
    for py in ("engine/pipeline.py", "engine/mlb/pipeline.py"):
        src = open(os.path.join(ROOT, py), encoding="utf-8").read()
        assert "vals = [g.value for g in prop.logs]" in src, py


def test_both_label_paths_reverse_with_the_bars():
    """THE ONE THAT MATTERS. The values are reversed to run oldest-left;
    labels that do not follow are attached to the wrong games and the
    chart looks perfectly normal while lying about every bar.

    Both paths — the log-derived ones and a caller's `opts.labels` —
    take the same input order (newest first, as the values are) and
    reverse. Two orders for one argument is how this breaks silently.
    """
    fn = PA[PA.index("const labelsOf ="):PA.index("const CW =")]
    assert fn.count(".reverse()") == 2, fn
    assert "const data = vals.slice(0, 10).map(Number).reverse();" in PA


def test_a_short_or_empty_log_falls_back_to_the_numbers():
    """Long shots carry `recent_values` and no `logs`, and an older
    payload has neither. A partial label set would caption some bars and
    not others, which is worse than captioning none."""
    fn = PA[PA.index("const labelsOf ="):PA.index("const labels =")]
    assert "src.length < n" in fn, "a log shorter than the chart must be refused"
    assert "out.every(Boolean) ? out : null" in fn, "one missing name voids the set"


def test_away_games_are_marked_and_home_games_are_not():
    """`@` is the box-score convention and costs one character where
    there is no room for three."""
    fn = PA[PA.index("const labelsOf ="):PA.index("const labels =")]
    assert 'g.home === false ? "@" : ""' in fn
    # Strict `=== false`: a log with no `home` key must not be called away.
    assert "g.home ?" not in fn


# --- fitting them under the bars -------------------------------------------
def test_it_staggers_before_it_shrinks():
    """Ten clubs under ten bars on a phone is 28 viewBox units each.
    Setting "@SDP" to fill that leaves under two units of gutter — a
    smear. Dropping alternate names a line doubles the room and keeps
    the type at the size the rest of the chart uses."""
    assert "const stagger =" in PA
    assert "fits(2 * slot)" in PA
    assert "const axisY = (i) => (stagger ? (i % 2 ? H - 4 : H - 16) : H - 8);" in PA


def test_the_second_row_stays_inside_the_plot_s_own_margin():
    """B is the bottom margin the plot already reserves. Both rows have
    to sit inside it or a label prints over the lowest gridline."""
    m = re.search(r"const L = narrow \? \d+ : \d+, R = narrow \? \d+ : \d+, "
                  r"T = (\d+), B = (\d+);", PA)
    assert m, "the margins moved — re-check the label rows"
    B = int(m.group(2))
    # The rows sit at H-16 and H-4; the plot ends at H-B.
    assert 16 < B, f"the upper label row overlaps the plot (B={B})"


def test_a_name_too_small_to_read_is_dropped_for_the_number():
    """Below the floor the opponent is not printed at 4px — a label
    nobody can read is a worse answer than the index it replaced."""
    assert "Math.max(6.5," in PA
    assert "axisFS >= 6.6" in PA


# --- the game bets get the same treatment ----------------------------------
def test_game_bet_charts_label_their_own_opponents():
    """The team's log carries the opponent exactly as a player's does."""
    i = APP.index("function gameBetSeries(")
    block = APP[i:APP.index("function gameBetChart(")]
    assert "const labels = rows.map((g) =>" in block
    assert '(g.home ? "" : "@")' in block
    assert block.count("labels,") >= 4, "every market must carry them"


def test_the_game_bet_labels_reach_both_chart_call_sites():
    """The card and the page draw the same chart through two calls. One
    of them missing the labels is the half-finished state that this
    project keeps paying for."""
    i = APP.index("function gameBetChart(")
    assert "labels: s.labels" in APP[i:i + 900]
    j = APP.index("function renderGameBetPage(")
    assert "labels: s.labels" in APP[j:j + 4000]


def test_the_tooltip_names_the_game_too():
    """Same fact, and the tooltip has the room the axis does not."""
    assert 'data-tip="${escapeAttr(labels ? `${labels[i]} — ${v}`' in PA


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
