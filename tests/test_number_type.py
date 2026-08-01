"""The numbers were the tell.

"Fonts for the numbers need to be changed, the website is still giving heavy
AI slop and I need it to look and feel human made."

The numbers were set in the same grotesque as the labels, at weight 800 with
-0.5px tracking — the house style of every generated dashboard, and the part
that read as machine-made whatever else changed around it. They are now IBM
Plex Mono (SIL OFL, latin subset, 20KB for two weights): slotted zero,
flagged one, a column you can scan down.

The serif was tried first and MEASURED out, which is why it is worth writing
down rather than re-litigating later:

  * it has no `tnum` feature at all — "111" renders 29.9px and "777" renders
    43.7px, a 46% jump on a board that rewrites itself every 60 seconds, and
    `font-variant-numeric: tabular-nums` does nothing because the feature is
    not in the file
  * its "1" is an unflagged vertical stroke, so "11" reads as "ll"

Beautiful for a masthead. Unusable for a scoreboard.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _block(selector_start: str) -> str:
    i = CSS.index(selector_start)
    return CSS[i:CSS.index("}", i)]


# --- the face ---------------------------------------------------------------
def test_the_mono_is_self_hosted_like_everything_else():
    """A board that renders with the network unplugged does not get to make
    an exception for the typeface its numbers are in."""
    for name in ("plex-mono.woff2", "plex-mono-500.woff2"):
        path = os.path.join(ROOT, "web", "fonts", name)
        assert os.path.exists(path), f"{name} is referenced but not shipped"
        assert 4000 < os.path.getsize(path) < 60000, f"{name} looks wrong"
    assert 'url("../fonts/plex-mono.woff2")' in CSS


def test_the_mono_leads_the_stack():
    m = re.search(r"--font-mono: ([^;]+);", CSS)
    assert m and m.group(1).strip().startswith('"IBM Plex Mono"')
    # …and still degrades to a real monospace if the file ever fails.
    assert "monospace" in m.group(1)


def test_both_weights_have_a_job():
    """A face nothing matches is a file the browser never fetches and a line
    of CSS that quietly means nothing — the dead declaration the italic
    serif was deleted for."""
    for weight in ("400", "500"):
        assert f"font-weight: {weight};" in CSS
    i = CSS.index("Both weights get a job")
    assert "font-weight: 400" in CSS[i:i + 400]


# --- what is set in it ------------------------------------------------------
def test_the_numbers_are_the_mono_and_the_prose_is_not():
    block = _block(".tile .v, .metric .v, .stat-v, .ml-odds, .conf-num")
    assert "font-family: var(--font-mono)" in block
    for kpi in (".tile .v", ".metric .v", ".ml-odds", ".rec-chart .rc-net"):
        assert kpi in block, f"{kpi} is still set in the sans"
    # td and .book carry player names and "FanDuel"; a proportional word in
    # a fixed-pitch face looks like a bug rather than a choice.
    assert "td.num" in block and "td," not in block


def test_the_weight_is_one_the_font_actually_ships():
    """800 on a face that ships 400 and 500 is browser-faked bold — a
    smeared outline at 30px, the loudest thing on the page."""
    block = _block(".tile .v, .metric .v, .stat-v, .ml-odds, .conf-num")
    assert "font-weight: 500;" in block
    assert "800" not in block


def test_the_negative_tracking_is_gone():
    """Tight tracking is the Inter-dashboard tell, and on a fixed-pitch face
    it fights the one property the face has."""
    block = _block(".tile .v, .metric .v, .stat-v, .ml-odds, .conf-num")
    assert "letter-spacing: 0;" in block


def test_figures_are_tabular_and_the_zero_is_slashed():
    block = _block(".tile .v, .metric .v, .stat-v, .ml-odds, .conf-num")
    assert '"tnum" 1' in block
    assert '"zero" 1' in block


def test_a_wallet_address_is_monospaced_because_you_compare_it_by_eye():
    assert ".wallet { font-family: var(--font-mono); }" in CSS
    assert 'class="wallet"' in JS


# --- what the wider face broke, and how it was fixed ------------------------
def test_the_unit_is_subordinate_to_the_figure():
    """A mono is wider per character than the sans it replaced, and
    "-106.50 pts" at full display size wrapped onto a second line at EVERY
    width. The unit is not part of the number."""
    block = _block(".tile .v .unit")
    assert "font-size: .5em" in block
    assert "font-weight: 400" in block


def test_the_value_can_still_break_between_number_and_unit():
    """White-space: nowrap fixed the wrap and started a clip — an
    unbreakable value ran 56px out of a 320px phone tile, which is worse
    than two lines. Two lines on a phone is fine; losing "pts" is not."""
    assert ".tile .v { white-space: nowrap; }" not in CSS
    # The space before the span IS the break opportunity. Without it the run
    # is continuous and clips again.
    assert """' <span class="unit">pts</span>'""" in JS


def test_the_header_note_counts_the_files_that_ship():
    n = len(set(re.findall(r'url\("\.\./fonts/([^"]+)"', CSS)))
    assert n == 4
    assert "Four files" in CSS
    assert "IBM Plex Mono for every NUMBER" in CSS


def test_the_serif_rejection_is_recorded_with_its_measurement():
    """So the next person to think "the numbers should be the serif" finds
    the reason instead of repeating the experiment."""
    assert "no `tnum` feature" in CSS
    assert "reads as \"ll\"" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
