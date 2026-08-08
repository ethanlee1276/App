"""The Futures page, its build, and the two things it must never do.

A futures board is the one surface here that talks about months rather than
tonight, and it can mislead in two ways nothing else on the site can:

  * presenting a preseason PRIOR as a projection — in August three of these
    four leagues have played no games, so every rating is last season's;
  * costing money quietly. Prices are one credit per sport per week, and
    that only holds while nothing in the page path can reach the wire.

Both are asserted below, along with the layout defect that cost the most
time: a media query that hides columns has to hide exactly as many as the
grid drops, or the surviving cells wrap into a second row.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _flat(text: str) -> str:
    """Whitespace collapsed. Prose in this file is wrapped to fit the column,
    so a sentence to assert on routinely spans a line break and a literal
    match against the source would fail on formatting rather than on
    meaning."""
    return " ".join(text.split())
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _tracks(spec: str) -> int:
    """Count grid tracks. A naive split() reports five for
    "44px minmax(0, 1fr) 52px 50px" because minmax carries a space of its
    own, which would have this test passing on a four-track row and failing
    on a correct one."""
    depth = n = 0
    token = False
    for ch in spec.strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            token = False
        elif not token:
            token = True
            n += 1
    return n


def _rules(text: str) -> str:
    """CSS with its comments removed. The comment ABOVE these rules explains
    why :nth-of-type is not used, and a naive search found that explanation
    and called it the defect."""
    import re
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()


# --- the build --------------------------------------------------------------
def test_all_four_sports_build():
    import futures_build
    assert set(futures_build.SPORTS) == {"nfl", "mlb", "cfb", "nba"}


def test_college_football_has_no_season_totals_on_purpose():
    """There are no college player logs in this database. Projecting a
    season total from nothing is the single thing a futures page must not
    do, so the market list is empty rather than optimistic."""
    import futures_build
    assert futures_build.SEASON_MARKETS["cfb"] == []
    for sport in ("mlb", "nfl", "nba"):
        assert futures_build.SEASON_MARKETS[sport], sport


def test_the_board_is_a_shortlist_not_a_database_dump():
    import futures_build
    assert 5 <= futures_build.PER_MARKET <= 25


def test_the_build_writes_one_file_per_sport():
    import futures_build
    assert 'f"futures_{sport}.json"' in open(
        os.path.join(ROOT, "futures_build.py"), encoding="utf-8").read()


def test_the_doctrine_is_written_once_and_carried():
    """Said in the payload so every surface inherits the same wording rather
    than each one inventing its own."""
    import futures_build
    d = futures_build.DOCTRINE
    assert "not from reading a price" in d
    assert "least likely to hold a sure thing" in d
    # And the build hands that constant out rather than restating it.
    src = open(os.path.join(ROOT, "futures_build.py"), encoding="utf-8").read()
    assert 'out["doctrine"] = DOCTRINE' in src


# --- the money ---------------------------------------------------------------
def test_the_daily_rebuild_cannot_pull_odds():
    """The refresh loop rebuilds the projections; it must not be able to
    reach the meter. Prices come from futures_build.py --odds, run on
    purpose, one credit per sport, cached for a week."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _run_futures(")
    block = src[i:src.index("\ndef ", i + 1)]
    assert "live_odds=False" in block
    assert "--odds" not in block.replace("futures_build.py --odds", "")


def test_the_rebuild_is_throttled_to_a_day():
    """A full MLB season at 20,000 trials takes 3.6 seconds. Four sports on
    the 60-second loop would spend fourteen seconds of every minute
    re-answering a question whose answer moves over weeks."""
    import launch
    assert launch.FUTURES_EVERY_HOURS >= 12
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _run_futures(")
    assert ".futures_built" in src[i:i + 900]


# --- the page ---------------------------------------------------------------
def test_the_tab_and_the_view_both_exist():
    assert 'data-view="futures"' in HTML
    assert 'id="view-futures"' in HTML
    assert 'id="futures-body"' in HTML


def test_futures_is_in_the_view_order():
    i = APP.index("const VIEW_ORDER = [")
    assert '"futures"' in APP[i:i + 400]


def test_sports_without_a_season_do_not_get_the_tab():
    """A fight card, a prediction market and a fantasy draft have no season
    to project, and a tab that can only ever say so is worse than no tab."""
    i = APP.index("const HIDDEN_VIEWS = {")
    block = APP[i:i + 1400]
    for sport in ("ufc", "polymarket", "fantasy", "wnba"):
        line = [l for l in block.splitlines() if l.strip().startswith(f"{sport}:")]
        assert line and "futures" in line[0], sport


def test_the_renderer_is_dispatched_like_the_other_standalone_pages():
    """Futures has its own per-sport payload, so nothing in the slate render
    redraws it — switching leagues on the tab would otherwise leave the
    previous league's teams under the new league's header."""
    assert 'if (state.view === "futures") renderFutures();' in APP


def test_the_preseason_warning_is_a_banner_not_a_footnote():
    """A division number in August is a prior wearing a projection's
    clothes, and nothing about the figure itself communicates that."""
    i = APP.index("function futuresDoctrine(")
    block = _flat(APP[i:APP.index("\nfunction ", i + 1)])
    assert "prior_share" in block
    assert "prior, not a projection" in block
    assert "fx-prior" in block


def test_a_board_with_no_prices_still_says_something():
    """The model is the product. Where no book price exists the probability
    stands on its own, exactly as the Parlay Zone publishes a required price
    rather than inventing a quote."""
    i = APP.index("function futuresTeamTable(")
    block = _flat(APP[i:APP.index("\nconst fxPct", i)])
    assert "No book price attached" in block
    assert "stands on its own" in block


def test_the_projection_shows_its_band():
    i = APP.index("function futuresTeamTable(")
    block = APP[i:APP.index("\nconst fxPct", i)]
    assert "proj_wins_lo" in block and "proj_wins_hi" in block


# --- the layout defect that cost the most time ------------------------------
def test_the_columns_are_named_not_selected_by_position():
    """Every cell in this table is a <span>, so :nth-of-type counts TAGS. A
    rule meant for the second percentage matched the group cell instead, the
    playoff column never hid, seven cells went into five tracks, and every
    row's edge wrapped onto a line of its own."""
    body = _rules(CSS)
    seg = body[body.index(".fx-row {"):body.index(".rec-stamp {")]
    assert ":nth-of-type" not in seg
    for cls in (".fx-div", ".fx-po", ".fx-ttl"):
        assert cls in CSS, cls
        assert f'class="{cls[1:]}"' in APP, cls


def _phone_blocks(css):
    """Every `@media (max-width: 760px)` block, braces-matched.

    "Up to the next @media" is the obvious slice and it is wrong here: this
    stylesheet keeps each media query beside the rules it modifies rather
    than grouping them at the end, so that slice swallows every top-level
    rule in between and a block appears to contain selectors nowhere near
    it.
    """
    out = []
    i = css.find("@media (max-width: 760px)")
    while i >= 0:
        start = css.index("{", i)
        depth = 0
        for k in range(start, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    out.append(css[start:k + 1])
                    break
        i = css.find("@media (max-width: 760px)", i + 30)
    return out


def test_the_phone_hides_exactly_as_many_cells_as_tracks_it_drops():
    """The invariant behind that bug, stated as arithmetic. Nine cells in a
    priced row, four hidden on a phone, four tracks declared."""
    # The block that contains the futures rules, not "the first 760px block
    # in the file". This stylesheet keeps each media query next to the rules
    # it modifies, so a new component added anywhere ABOVE the futures table
    # silently became the first match and this read a block with no .fx- in
    # it. Anchor on the thing meant, never on ordinal position.
    block = next((b for b in _phone_blocks(CSS)
                  if ".fx-table.priced .fx-row {" in b), "")
    assert block, "no 760px block declares the priced futures row"
    j = block.index(".fx-table.priced .fx-row {")
    tracks = block[j:j + 200].split("grid-template-columns:")[1].split(";")[0]
    assert _tracks(tracks) == 4, tracks
    hidden = {c for c in (".fx-grp", ".fx-rec", ".fx-po", ".fx-odds", ".fx-div")
              if c in block}
    assert hidden == {".fx-grp", ".fx-rec", ".fx-po", ".fx-odds", ".fx-div"}


def test_the_table_is_capped_so_the_numbers_sit_near_their_names():
    """Slack in a grid lands somewhere. Full width put all of it in the group
    column: the abbreviation alone at the far left, a canyon, then the
    figures."""
    i = CSS.index(".fx-table {")
    assert "max-width" in CSS[i:i + 120]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
