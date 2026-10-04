"""Roadmap #8 — the delivery mechanics, and the one that was refused.

Freshness pulses (a card whose number moved in the last rebuild flashes
once), the return banner ("since you last looked…", counted off the
feed), and web push — which did NOT ship, on purpose, with the reason
written down: RFC 8291 needs P-256 ECDH and AES-128-GCM, the stdlib has
neither, and hand-rolled curve crypto on a site that holds accounts is
the wrong risk. A refusal that is not written down gets re-attempted by
somebody who has not seen the reasoning.

Run directly: `python3 tests/test_delivery.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")


# --- freshness pulses --------------------------------------------------------

def test_the_baseline_is_captured_before_the_fetch_replaces_the_board():
    """The diff needs the OLD board; captured after the fetch there is
    nothing left to diff against."""
    i = APP.index("captureFreshBaseline(meta.api)")
    j = APP.index('const tag = _boardTags[meta.api]')
    assert i < j, "the baseline is captured after the fetch began"


def test_pulses_apply_after_the_render_that_draws_the_cards():
    i = APP.index("  renderAll();\n  applyFreshPulses();")
    assert i > 0


def test_a_changed_number_is_the_trigger_not_a_changed_row():
    """Line, odds or projection — the NUMBERS. A row whose reasons were
    reworded did not move, and a board where every rebuild pulses every
    card is a strobe, not a signal."""
    i = APP.index("function _freshFp(r)")
    body = APP[i:APP.index("\n}", i)]
    assert "r.line" in body and "r.odds" in body and "r.projection" in body
    i = APP.index("function applyFreshPulses()")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "prev !== undefined" in body, \
        "a row NEW to the board pulses — appearing is the feed's event, not a pulse"


def test_the_pulse_reuses_the_live_ticks_flash():
    """One visual language for 'this changed': the same audited one-shot
    background flash, animating nothing the compositor can't own."""
    assert ".fresh-pulse { animation: tickMove" in CSS


def test_a_board_switch_never_pulses_the_new_sport():
    i = APP.index("function captureFreshBaseline")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "_boardFor === api" in body, \
        "switching leagues would diff MLB rows against NFL rows"


# --- the return banner -------------------------------------------------------

def test_the_previous_visit_is_captured_before_this_one_overwrites_it():
    cap = APP.index("localStorage.getItem(SEEN_KEY)")
    mark = APP.index("markSeen();")
    assert cap < mark, "the banner would always compare against right now"


def test_the_banner_needs_a_real_absence_and_real_news():
    i = APP.index("function freshBannerHTML")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "30 * 60000" in body, "a tab flip is not a return"
    assert "evs.length < 3" in body, "a quiet gap earns no banner"
    assert "_freshDismissed" in body, "no way to dismiss it"


def test_the_banner_rides_in_the_allowlisted_daycard_zone():
    """test_board_order allows exactly the ids it names above the picks;
    the banner lives inside daycard-zone rather than claiming a new slot,
    and stays empty on the pass that test measures."""
    i = APP.index("async function renderDayCard()")
    body = APP[i:APP.index("\nfunction renderRecommended", i)]
    assert "freshBannerHTML(d)" in body
    assert 'host.innerHTML = banner;' in body.replace("\n", " ") \
        or "host.innerHTML = banner" in body


def test_the_banner_counts_off_the_feed_and_links_to_it():
    i = APP.index("function freshBannerHTML")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    for kind in ("edge_appeared", "edge_died", "card_posted"):
        assert kind in body
    assert 'href="#alerts"' in body, "news with no way to read it"


# --- web push: refused, in writing ------------------------------------------

def test_the_push_refusal_is_written_down_where_ideas_live():
    ideas = _read("docs", "IDEAS.md")
    assert "Web push — measured and refused" in ideas
    assert "P-256" in ideas and "stdlib" in ideas


def test_no_half_shipped_push_code_exists():
    """The worst outcome is a subscribe button wired to nothing. If push
    ever ships it arrives whole (see the IDEAS entry); until then the
    words must not appear in anything a browser runs."""
    assert "pushManager" not in APP
    assert "applicationServerKey" not in APP
    for name in ("sw.js", "service-worker.js", "serviceworker.js"):
        p = os.path.join(ROOT, "web", name)
        if os.path.exists(p):
            src = open(p, encoding="utf-8").read()
            assert "push" not in src.lower() or "pushState" in src, \
                f"{name} carries a push handler nothing can send to"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
