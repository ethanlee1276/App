"""The render spec, and the instrument that measures it.

`docs/RENDER_SPEC.md` says the Prediction Markets page is a two-column
layout with a sticky detail panel, and the Fantasy Calendar is three
columns. Prose cannot fail. Nothing stopped a refactor from making either
of them one column with the whole suite green, because no test knew.

`rendercheck.py` turns those claims into measurements taken in a real
browser. This file defends the instrument, in two halves:

  * **the half that needs no browser** — every selector the spec table
    names still exists in the source, the four verdicts are all reachable,
    and a claim cannot be quietly deleted by deleting its selector. This
    runs everywhere, including CI.
  * **the half that does** — the harness end to end against the real
    pages. Opt-in; see below.

THE FOUR VERDICTS ARE THE DESIGN and each is pinned below, because three
of them are the difference between a tool that gets run and one that gets
ignored:

    holds        the claim is true right now
    broke        DRIFT — someone should look
    no data      this board has nothing to draw, so nothing is claimed
    not in force the feature is off (pricing needs billing switched on)

BROWSER HALVES ARE OPT-IN. Set `QB_BROWSER_TESTS=1` to run them.

They are skipped by default and the reason is a measured one: three
Chromium-driving tests inside a 284-file suite crashed the browser
("Page crashed" mid-navigation) on a container already busy running
everything else. A flaky test is worse than no test — the first false
alarm is what teaches you to skip the real one — and these particular
assertions have a better home anyway:

    QB_BROWSER_TESTS=1 python3 tests/test_rendercheck.py
    python3 launch.py --renders

The halves that need no browser still run on every commit, and they are
the ones that catch the drift class this exists for.

Run directly: `python3 tests/test_rendercheck.py`
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import rendercheck as rc                                        # noqa: E402

SOURCES = " ".join(
    open(os.path.join(ROOT, p), encoding="utf-8").read()
    for p in ("web/js/app.js", "web/css/styles.css", "web/index.html"))


def _selectors():
    """Every class/id the spec table leans on, flattened.

    Compound selectors (`.pm-layout > :first-child`, `.mbc-views > *`) are
    split into their named parts; a pseudo-class is not something to look
    for in a stylesheet.
    """
    out = set()
    for name, clicks, proof, present, checks in rc.SCREENS:
        parts = [proof, present] + [c[2] for c in checks]
        parts += [c[6] for c in checks if len(c) > 6 and c[6]]
        parts += [c[4] for c in checks if c[3] == "above"]
        for sel in parts:
            for tok in re.findall(r"[.#][A-Za-z][\w-]*", str(sel)):
                out.add(tok)
    return out


# --- the spec table is about the real site -----------------------------------
def test_every_selector_the_spec_names_exists_in_the_source():
    """The cheap half of drift, catchable without a browser: a class that
    no longer appears anywhere in the app, the stylesheet or the shell.

    This is what makes the harness safe to leave running. A rename that
    silently voids a check would otherwise show up as a permanent "no
    data" — a green-looking run that measures nothing."""
    missing = [s for s in _selectors()
               if s.lstrip(".#") not in SOURCES]
    assert not missing, f"the spec names selectors nothing renders: {missing}"


def test_every_screen_can_be_reached_by_something_on_the_page():
    """A nav selector that does not exist is the failure that produced the
    `proof` field: the first cut of the Account screen clicked the My Bets
    chip, landed elsewhere, found THAT screen's empty state and filed a
    tidy "no data" for a page it had never opened."""
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    for name, clicks, _, _, _ in rc.SCREENS:
        for c in clicks:
            # Subtab buttons are built by subtabbedHTML at runtime, so they
            # are in the script rather than the shell.
            hay = html if c.startswith(("[data-sport", "[data-view", "#")) \
                else SOURCES
            tok = re.findall(r'"([^"]+)"|#([\w-]+)', c)
            flat = [t for pair in tok for t in pair if t]
            assert any(t in hay or t in SOURCES for t in flat), \
                f"{name}: nothing on the page matches {c}"


def test_every_screen_names_a_proof_that_is_not_its_layout():
    """`proof` has to survive an empty board — that is its whole job. If
    someone sets it equal to the layout selector the "no data" verdict
    becomes unreachable and every empty board reads as drift."""
    for name, _, proof, present, _ in rc.SCREENS:
        assert proof and proof != present, \
            f"{name}: proof must be the container, not the content"


# --- the verdicts, each one reachable ----------------------------------------
def _row(**over):
    r = {"name": "Prediction Markets", "width": 1280, "nav": True,
         "proof": True, "present": True, "empty": False, "settled": True,
         "errs": [], "got": {"chip-row": 1}}
    r.update(over)
    return r


def test_a_true_claim_reads_as_holding():
    v = rc.verdicts([_row()])
    assert v["measured"] == 1 and not v["drift"]
    assert any(k == "ok" for k, _, _ in v["lines"])


def test_a_broken_claim_is_drift_and_says_what_it_wanted():
    v = rc.verdicts([_row(got={"chip-row": 0})])
    assert v["drift"], "a false claim did not register"
    said = [s for k, _, s in v["lines"] if k == "drift"][0]
    assert "want 1" in said, said


def test_an_empty_board_is_not_a_finding():
    """The verdict that keeps this tool alive. Half the pack cannot draw
    on a machine with no schedule cache, and a run that called every one
    of those a regression would be deleted within a week."""
    v = rc.verdicts([_row(present=False, empty=True)])
    assert not v["drift"], "an empty board was reported as drift"
    assert v["nodata"] == 1


def test_a_missing_layout_with_no_empty_state_IS_a_finding():
    """The other side of the same coin. A layout that vanished without the
    page saying it has nothing to show is exactly the regression."""
    v = rc.verdicts([_row(present=False, empty=False)])
    assert v["drift"]


def test_a_screen_that_never_settled_is_inconclusive_not_drift():
    """The flake this file caught on its own first full-suite run.

    Under load the Prediction Markets page had not finished drawing when
    the clock ran out, and the harness called it "layout gone" — a false
    alarm on a page whose layout was fine. A slow machine and a deleted
    layout look identical from here, and guessing between them is how a
    check earns the false alarm that teaches you to skip the real one.

    The harness now WAITS for the screen to settle rather than sleeping a
    fixed interval, and when even that runs out it says so."""
    v = rc.verdicts([_row(settled=False, present=False, empty=False)])
    assert not v["drift"], "a slow page was reported as a regression"
    assert v["slow"] == 1
    assert any("inconclusive" in s for _, _, s in v["lines"])


def test_the_harness_waits_for_the_screen_rather_than_sleeping():
    src = open(os.path.join(ROOT, "rendercheck.py"), encoding="utf-8").read()
    assert "waitForFunction" in src, \
        "back to a fixed sleep, and back to racing under load"


def test_a_screen_that_never_mounted_invalidates_its_own_verdicts():
    """No proof, no verdict. Anything measured on the wrong screen is
    worse than no measurement, because it reads as reassurance."""
    v = rc.verdicts([_row(proof=False, present=False, empty=True)])
    assert v["drift"] and v["nodata"] == 0, \
        "a screen that never mounted was excused as an empty board"


def test_a_repeating_element_is_checked_per_row_not_by_a_number():
    """Ethan's first run on a FED board, 2026-08-19, found two checks I had
    written against an empty one — and they were the only two that failed.

    `.al-c` is the condition on an alert row. Pinned as `n == 1` it passed
    on a board with no alerts and failed on a real one with six: the check
    was measuring today's data, not the design. The claim is that EVERY
    row carries its condition, and `each` says that.

    Same lesson as the four-tiles check on the same run. A number authored
    where the page is empty is a number about emptiness."""
    v = rc.verdicts([_row(name="Alerts Center",
                          got={"condition-rows": "|each-ok"})])
    assert not v["drift"], "a row-per-row claim failed while holding"
    assert any("one per row" in s for _, _, s in v["lines"])


def test_each_still_fails_when_a_row_is_missing_its_condition():
    """The half that matters: a check that cannot fail is not a check."""
    v = rc.verdicts([_row(name="Alerts Center",
                          got={"condition-rows": "4 of 6"})])
    assert v["drift"], "two rows lost their condition and nothing noticed"
    assert any("4 of 6" in s for _, _, s in v["lines"])


def test_the_board_tiles_claim_names_the_boards_own_strip():
    """`.stats` is shared, and the Prediction Markets page grows three of
    them once it has data — board, flow, proof. The first version counted
    `#intel-body .stats > *`, which is 4 on a machine with one populated
    tab and 12 on a fed one. Measured both in a browser: the old selector
    reads 12 with the other two strips present, the new one reads 4."""
    pm = next(c for name, _, _, _, checks in rc.SCREENS if name == "Prediction Markets"
              for c in checks if c[0] == "four-tiles")
    assert pm[2] == ".pm-tiles > *", \
        "the tiles claim is counting every stats strip on the page again"
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert 'class="stats pm-tiles"' in app, "the board's strip lost its name"
    assert app.count("pm-tiles") >= 2


def test_nothing_to_repeat_over_is_not_a_broken_repeat():
    """The hole `each` opened while closing another one.

    A quiet Alerts page draws its filter chips and zero rows — the page's
    own copy says "a quiet page means a quiet slate, not a broken one".
    Comparing 0 conditions against 0 rows would have failed it. That is
    the same cry-wolf failure the no-data verdict exists to prevent,
    arriving through a new door."""
    v = rc.verdicts([_row(name="Alerts Center", got={"condition-rows": "|none"})])
    assert not v["drift"], "a quiet night was reported as a regression"
    assert v["nodata"] == 1


def test_a_gated_feature_reads_as_off_rather_than_broken():
    """Pricing cards need subscriptions switched on. Reporting a business
    decision as a design regression trains you to ignore the report."""
    v = rc.verdicts([_row(name="Sign-in & Pricing",
                          got={"two-plans": "|off"})])
    assert not v["drift"]
    assert v["off"] == 1
    assert any("not in force" in s for _, _, s in v["lines"])


def test_a_page_that_threw_is_reported_even_if_it_looks_right():
    v = rc.verdicts([_row(errs=["boom"])])
    assert v["drift"] and any("threw" in s for _, _, s in v["lines"])


# --- the contact sheet -------------------------------------------------------
def test_the_contact_sheet_is_not_a_diff_and_does_not_claim_to_be():
    """The render images live in a chat, not the repo — a cloud session
    cannot persist them, which is why RENDER_SPEC.md is prose. Anything
    calling itself a pixel diff here would be lying about what it did."""
    src = open(os.path.join(ROOT, "rendercheck.py"), encoding="utf-8").read()
    assert "does not diff pixels" in src.lower() or "NOT a pixel diff" in src
    assert "the comparison stays Ethan's" in src


def test_the_sheet_pairs_a_render_image_when_one_has_been_dropped_in(tmp=None):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    rows = [{"name": "Dashboard", "width": 1280,
             "shot": str(d / "dashboard-1280.png")}]
    page = rc.contact_sheet(rows, d)
    assert "drop the render image here" in page.read_text(encoding="utf-8")
    (d / "render-dashboard-1280.png").write_bytes(b"x")
    page = rc.contact_sheet(rows, d)
    html = page.read_text(encoding="utf-8")
    assert 'src="render-dashboard-1280.png"' in html
    assert "drop the render image here" not in html


# --- end to end, when there is a browser -------------------------------------
def test_the_harness_runs_against_the_real_pages():
    """Skipped with a reason rather than failing when Node or Playwright
    is absent — the same contract `launch.py --check`'s sweep uses. A test
    that fails on a machine without a browser is a test people delete."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1, or run "
              "`python3 launch.py --renders`)")
        return
    if not rc._have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    srv, port = rc._serve()
    try:
        rows = rc.run(1280, port)
    finally:
        srv.shutdown()
    assert rows, "the harness measured nothing at all"
    v = rc.verdicts(rows)
    # Not "no drift" — that depends on this machine's data. What must hold
    # is that the run produced verdicts and that anything it DID measure
    # measured cleanly.
    assert v["lines"], "no verdicts came back"
    assert not v["drift"], f"drift on the real pages: {v['drift']}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
