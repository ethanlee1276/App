"""Every ranking we can legitimately read, side by side.

Ethan, 2026-08-15: "add where we show every books ranking side by side".

THE HONEST SCOPE IS SMALLER THAN THE ASK and the tests say so out loud.
FantasyPros' consensus is behind a paid key and forbids scraping; ESPN,
Yahoo and CBS keep their rankings inside logged-in products. This repo
does not take credentials and a session cookie is a credential. So what
ships is the sources that are genuinely free and already on disk — our
own VORP board, Sleeper's `search_rank`, the live pick order in YOUR
draft — plus a paste box, which is the honest route to any list you can
already see.

WHAT THE TABLE IS FOR IS THE DISAGREEMENT. Four columns in near-identical
order is wallpaper; the row where our board is thirty spots above
Sleeper's is either the edge or the bug. `disagreements` sorts by spread
for that reason, and the tests below pin the two ways that view could
lie: counting an ABSENCE as a low opinion, and printing an argument
between sources that agree.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import fantasy_ranks as fr                        # noqa: E402

KIT = {"board": [{"player": "Ja'Marr Chase"}, {"player": "Bijan Robinson"},
                 {"player": "Amon-Ra St. Brown"}, {"player": "Puka Nacua"}]}

PLAYERS = {
    "1": {"first_name": "Bijan", "last_name": "Robinson",
          "position": "RB", "search_rank": 1},
    "2": {"first_name": "Ja'Marr", "last_name": "Chase",
          "position": "WR", "search_rank": 2},
    "3": {"first_name": "Puka", "last_name": "Nacua",
          "position": "WR", "search_rank": 14},
    "4": {"first_name": "Ashton", "last_name": "Jeanty",
          "position": "RB", "search_rank": 9},
    "5": {"first_name": "Unranked", "last_name": "Guy",
          "position": "WR", "search_rank": 9999999},
    "6": {"first_name": "Some", "last_name": "Lineman",
          "position": "OL", "search_rank": 3},
}

PICKS = [{"pick_no": 1, "metadata": {"first_name": "Ja'Marr",
                                     "last_name": "Chase"}},
         {"pick_no": 2, "metadata": {"first_name": "Ashton",
                                     "last_name": "Jeanty"}}]


# --- the join key -----------------------------------------------------------
def test_the_key_survives_the_ways_a_name_is_written():
    n = fr.normalize
    assert n("Ja'Marr Chase") == n("Ja’Marr Chase")
    assert n("Amon-Ra St. Brown") == n("Amon Ra St Brown")
    assert n("Marvin Harrison Jr.") == n("Marvin Harrison")
    assert n("  KENNETH   WALKER  III ") == n("Kenneth Walker")


def test_an_apostrophe_dropped_entirely_still_finds_the_same_man():
    """`normalize` matches the page exactly, and inherits the page's one
    weakness: an apostrophe becomes a SPACE, so "Ja'Marr" and "JaMarr" key
    differently. Harmless between our own sources — they spell him the
    same way — and NOT harmless for an import, because apostrophes are
    precisely what other sites' exports disagree about.

    The looser key folds them, and the canonical spelling is the board's
    rather than whichever file happened to be read first."""
    assert fr.squash("Ja'Marr Chase") == fr.squash("JaMarr Chase")
    out = fr.build({"board": [{"player": "Ja'Marr Chase"}]}, {}, [],
                   "1,JaMarr Chase")
    assert len(out["rows"]) == 1, "the two spellings became two players"
    row = out["rows"][0]
    assert row["player"] == "Ja'Marr Chase"
    assert row["ranks"]["ours"] == 1 and row["ranks"]["imported"] == 1


def test_the_key_strips_accents_like_the_page_does():
    """The browser keys Sleeper ids with `ffNorm`, which decomposes and
    drops combining marks. A Python side that skipped that step would key
    "José" differently and half-fill his row — one column from our board,
    the other blank, looking exactly like a source that never ranked him."""
    assert fr.normalize("José Alvarado") == "jose alvarado"
    assert fr.normalize("Nöel Devine") == "noel devine"


def test_the_page_and_the_engine_normalize_the_same_way():
    """Pinned against the JS source rather than trusting that the same
    rules were written twice. If `ffNorm` gains a step, this fails and the
    two are reconciled deliberately."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function ffNorm(")
    body = app[i:app.index("\n}", i)]
    assert "normalize(\"NFD\")" in body, "the page no longer strips accents"
    assert "u0300-\\u036f" in body
    assert "jr|sr|ii|iii|iv|v" in body
    assert ".'’`-" in body or "'’`" in body


# --- one source at a time ---------------------------------------------------
def test_our_board_ranks_by_its_position_in_the_board():
    assert fr.from_board(KIT)["ja marr chase"] == 1
    assert fr.from_board(KIT)["puka nacua"] == 4


def test_sleeper_is_read_in_search_rank_order_not_raw():
    """`search_rank` is a global ordering across every position; the
    column has to be a dense 1..n over the players actually shown or a
    spread against our board is measuring the gaps, not the opinions."""
    got = fr.from_sleeper(PLAYERS)
    assert got["bijan robinson"] == 1
    assert got["ja marr chase"] == 2
    assert got["ashton jeanty"] == 3
    assert got["puka nacua"] == 4


def test_sleepers_unranked_sentinel_is_not_a_rank():
    """Sleeper parks unranked players at a huge number. Sorted naively he
    lands last and reads as a real, very low opinion."""
    assert "unranked guy" not in fr.from_sleeper(PLAYERS)


def test_only_the_fantasy_positions_are_ranked():
    assert "some lineman" not in fr.from_sleeper(PLAYERS)


def test_your_own_draft_is_the_adp_that_matters():
    """National ADP is what strangers did. This is what the eleven people
    across the table have actually done tonight."""
    got = fr.from_picks(PICKS)
    assert got["ja marr chase"] == 1 and got["ashton jeanty"] == 2


def test_a_pick_stream_with_no_numbers_falls_back_to_order():
    got = fr.from_picks([{"metadata": {"first_name": "A", "last_name": "B"}},
                         {"metadata": {"first_name": "C", "last_name": "D"}}])
    assert got["a b"] == 1 and got["c d"] == 2


# --- the paste box, which is the route that needs no password ---------------
def test_an_import_takes_whatever_the_other_site_exported():
    got = fr.parse_import("""rank,player,team
1,Bijan Robinson,ATL
2. Ja'Marr Chase
3 Amon-Ra St. Brown
Puka Nacua
""")
    assert got["bijan robinson"] == 1
    assert got["ja marr chase"] == 2
    assert got["amon ra st brown"] == 3
    assert got["puka nacua"] == 4


def test_an_import_trusts_the_numbers_it_was_given():
    """A keeper list numbered 1, 2, 5 means those gaps — renumbering it
    densely would quietly claim the third man is the third-best."""
    got = fr.parse_import("1,A One\n2,B Two\n5,C Five")
    assert got["c five"] == 5


def test_an_import_ignores_headers_blanks_and_comments():
    got = fr.parse_import("player\n\n# my tiers\nA One\n\nB Two\n")
    assert got == {"a one": 1, "b two": 2}


def test_an_empty_import_is_empty_not_an_error():
    assert fr.parse_import("") == {} and fr.parse_import(None) == {}


# --- side by side -----------------------------------------------------------
def _built():
    return fr.build(KIT, PLAYERS, PICKS,
                    "1,Bijan Robinson\n2,Ja'Marr Chase\n"
                    "3,Amon-Ra St. Brown\n4,Puka Nacua")


def test_a_missing_source_is_blank_rather_than_last():
    """THE ONE THAT WOULD RUIN THE TABLE. Our board is last season's usage
    run forward, so every rookie is absent BY CONSTRUCTION. Scoring that
    absence as rank 999 would put the entire rookie class at the top of
    the disagreements list, every year, for a reason that is not an
    opinion about them."""
    rows = {r["player"]: r for r in _built()["rows"]}
    jeanty = rows["Ashton Jeanty"]
    assert jeanty["ranks"]["ours"] is None
    assert jeanty["ranks"]["sleeper"] == 3
    # And the absence is not folded into the spread.
    assert jeanty["spread"] == abs(jeanty["ranks"]["sleeper"]
                                   - jeanty["ranks"]["adp"])


def test_the_consensus_is_the_median_of_the_opinions_that_exist():
    rows = {r["player"]: r for r in _built()["rows"]}
    chase = rows["Ja'Marr Chase"]
    have = sorted(v for v in chase["ranks"].values() if v is not None)
    assert len(have) == 4
    assert chase["consensus"] == (have[1] + have[2]) / 2


def test_a_player_only_one_source_ranks_has_no_spread():
    """A spread needs two opinions. One source disagreeing with nothing is
    not a disagreement."""
    out = fr.build({"board": [{"player": "Only Here"}]}, {}, [], "")
    assert out["rows"][0]["spread"] is None
    assert out["disagreements"] == []


def test_agreement_is_not_printed_as_an_argument():
    """A spread of zero with a named "high source" and "low source" shows
    a fight between two sources that said the same thing."""
    out = fr.build(KIT, PLAYERS, [], "1,Ja'Marr Chase\n2,Bijan Robinson")
    for r in out["disagreements"]:
        assert r["spread"] > 0
        assert r["high_source"] != r["low_source"]


def test_the_disagreements_name_who_is_high_and_who_is_low():
    """An average hides the fight. The reader decides whose argument they
    believe, which needs to know whose argument it is.

    Ten filler players either side so the gap survives densification —
    Sleeper's `search_rank` is global across every position, so the column
    is compacted to 1..n before comparison and a two-row fixture cannot
    express a real disagreement."""
    board = [{"player": "Sleeper Fade"}] + [
        {"player": f"Filler {i}"} for i in range(10)]
    players = {str(i): {"first_name": "Filler", "last_name": str(i),
                        "position": "WR", "search_rank": i + 1}
               for i in range(10)}
    players["x"] = {"first_name": "Sleeper", "last_name": "Fade",
                    "position": "WR", "search_rank": 400}
    out = fr.build({"board": board}, players, [], "")
    top = out["disagreements"][0]
    assert top["player"] == "Sleeper Fade"
    assert top["high_source"] == "ours" and top["low_source"] == "sleeper"
    assert top["ranks"]["ours"] == 1 and top["ranks"]["sleeper"] == 11


def test_coverage_says_which_columns_are_actually_populated():
    """A silently empty column looks exactly like a source that agrees
    with us about everything."""
    cov = {c["key"]: c for c in fr.build(KIT, PLAYERS, [], "")["sources"]}
    assert cov["ours"]["present"] and cov["ours"]["players"] == 4
    assert cov["adp"]["present"] is False and cov["adp"]["players"] == 0
    assert cov["imported"]["present"] is False


def test_it_builds_from_nothing_without_raising():
    """The offseason state: no draft, no import, maybe no board."""
    out = fr.build()
    assert out["rows"] == [] and out["disagreements"] == []
    assert len(out["sources"]) == len(fr.SOURCES)


def test_the_display_name_is_stable_rather_than_first_arrival():
    """Sources spell him differently and whichever landed first would win
    by accident, so the board's spelling is preferred."""
    out = fr.build(KIT, PLAYERS, PICKS, "")
    names = {r["player"] for r in out["rows"]}
    assert "Ja'Marr Chase" in names and "JaMarr Chase" not in names


# --- the boundary this feature must not cross -------------------------------
def _code_tokens(path):
    """Identifiers and literals from a file, with comments and docstrings
    dropped — a prose guard that reads its own explanation is a guard that
    fails for saying what it protects against."""
    import io
    import tokenize
    names = set()
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(io.BytesIO(fh.read()).readline):
            if tok.type == tokenize.NAME:
                names.add(tok.string.lower())
            elif tok.type == tokenize.STRING and len(tok.string) < 200:
                names.add(tok.string.strip("\"'").lower())
    return names


def test_no_source_here_needs_a_credential():
    """The standing rule, checked in the file that would be tempted to
    break it. Every source is handed IN — this module fetches nothing, so
    it cannot grow a login."""
    names = _code_tokens(os.path.join(ROOT, "engine", "fantasy_ranks.py"))
    for word in ("password", "espn_s2", "swid", "cookie", "cookies",
                 "oauth", "requests", "urlopen", "urllib", "auth", "token"):
        assert word not in names, f"fantasy_ranks reached for {word!r}"


def test_this_module_cannot_fetch_anything_at_all():
    """Structural rather than a promise: every source arrives as an
    argument, so there is no request here to grow a credential onto."""
    names = _code_tokens(os.path.join(ROOT, "engine", "fantasy_ranks.py"))
    assert "fetch_text" not in names and "fetch" not in names
    src = open(os.path.join(ROOT, "engine", "fantasy_ranks.py"),
               encoding="utf-8").read()
    assert "import re" in src and "http" not in src.replace("https", "")


# --- the two columns that only exist in the browser -------------------------
def _js(name):
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index(f"function {name}(")
    return app[i:app.index("\n}", i)]


def test_the_page_owns_the_two_columns_the_build_cannot_have():
    """Our board and Sleeper are built server-side. A live draft's pick
    order and a pasted list exist only in this browser, so the merge has
    to happen there — and that is the ONLY arithmetic duplicated across
    the two languages."""
    merge = _js("ffRankMerge")
    assert "adp" in merge and "imported" in merge
    assert "consensus" in merge and "spread" in merge


def test_the_browser_merge_uses_the_same_median_rule():
    """Mean of the middle two when even, matching `_median`. A different
    tie-break would make the page and the probe disagree about the same
    player on the same data."""
    merge = _js("ffRankMerge")
    assert "have[mid - 1] + have[mid]) / 2" in merge
    assert "n % 2 ? have[mid]" in merge


def test_the_browser_never_scores_an_absence_as_a_rank():
    merge = _js("ffRankMerge")
    assert "filter((v) => v != null)" in merge
    assert "n >= 2 ? r.worst - r.best : null" in merge


def test_a_player_only_the_draft_knows_is_added_not_dropped():
    """A rookie taken in your draft is absent from our board BY
    CONSTRUCTION. Dropping him would hide the pick that just happened."""
    merge = _js("ffRankMerge")
    assert "out.push(row)" in merge


def test_the_browser_import_parser_matches_the_engine_s_rules():
    js = _js("ffRankParseImport")
    assert "player" in js and "rank" in js         # header row skipped
    assert "startsWith(\"#\")" in js               # comments skipped
    assert "seen" in js                            # order is the fallback rank


def test_a_finished_draft_stops_claiming_to_be_live():
    """A disconnected draft's column labelled "Your draft" long after it
    ended is the same lie as a stale price."""
    stop = _js("dkStop")
    assert "dkState.adp = {}" in stop


def test_the_pick_order_is_recorded_as_it_arrives():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function dkStart(")
    body = app[i:app.index("\nfunction ", i + 1)]
    assert "dkState.adp" in body and "pick_no" in body


def test_the_paste_box_says_why_it_exists():
    """The reason there is a paste box at all is that the sites with the
    best rankings cannot be fetched without a login. Leaving that unsaid
    makes the feature look lazy instead of principled."""
    html = _js("rankBoardHTML")
    low = html.lower()
    assert "password" in low
    assert "rank-paste" in html


def test_the_board_is_a_pane_rather_than_a_page():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".rank-scroll {")
    block = css[i:css.index("}", i)]
    assert "max-height" in block
    j = css.index(".rank-table th {")
    assert "sticky" in css[j:css.index("}", j)]


def test_the_pasted_list_follows_the_account_to_the_phone():
    """It is typed once and wanted at the draft table, which is the whole
    reason accounts exist on this site."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function acctGather(")
    assert "FF_IMPORT_KEY" in app[i:app.index("\n}", i)]
    j = app.index("function acctApplySection(")
    assert "FF_IMPORT_KEY" in app[j:app.index("\n}", j)]


def test_the_sub_tab_exists_and_is_wired():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert '["ranks", "Rankings"' in app
    assert "rankBoardHTML(d.ranks)" in app
    assert "initRankBoard();" in app


def test_the_build_ships_the_two_server_side_columns():
    src = open(os.path.join(ROOT, "fantasy_build.py"), encoding="utf-8").read()
    assert "fantasy_ranks.build(kit, blob or {})" in src
    assert '"ranks":' in src


# --- the order, made visible -------------------------------------------------
def test_the_board_says_what_it_is_ordered_by():
    """Ethan, 2026-08-23: "I'm kinda confused on the order of all these
    players ... if they're lined up a certain way, we should display
    that."

    They WERE lined up a certain way — `ffRankMerge` sorts on
    `consensus`, the median across every source — and nothing on the
    page said so. Two of the columns he could see are sources, neither of
    which is sorted, so the list looked arbitrary."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    head = app[app.index("function rankBoardHTML("):]
    head = head[:head.index("\n}")]
    assert "Ordered by <b>consensus</b>" in head, (
        "the subtitle never names the sort")
    assert "median rank" in head, "and never says what consensus means"
    # The sort itself has not moved.
    merge = _js("ffRankMerge")
    assert "out.sort((a, b) => (a.consensus - b.consensus)" in merge


def test_the_position_leads_the_row():
    """A column of 1, 2, 3 is what tells a reader at a glance that this
    is an order. It is the ORDINAL rather than the consensus, because
    consensus is a median and ties — four players sat at 4.0 on the
    board Ethan sent, which as a leading column reads as broken."""
    render = _js("renderRankBoard")
    assert '<span\n          class="rank-ord">${i + 1}</span>' in render \
        or 'class="rank-ord">${i + 1}</span>' in render, (
        "the row does not carry its position")
    assert "rows.slice(0, 200).map((r, i)" in render, (
        "the map has no index, so there is no position to print")
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".rank-ord {" in css, "the ordinal is unstyled"


def test_a_source_nobody_is_ranked_by_is_not_a_column():
    """"Your draft" fills in when a draft starts and "Imported" when a
    list is pasted. Before that they were two of the four columns a
    phone could show, both entirely dashes — and they pushed the column
    the order comes from off the right edge."""
    render = _js("renderRankBoard")
    assert "FF_RANK_SOURCES.filter(([k]) => counts[k] > 0)" in render, (
        "empty source columns are still drawn")
    assert "shown.map(" in render, "the header still walks every source"
    # …but never down to no columns at all.
    assert "live.length ? live : FF_RANK_SOURCES.slice(0, 1)" in render, (
        "an empty board would render a table with no source columns")


def test_the_name_column_is_pinned_and_matches_its_own_row():
    """Sticky needs an opaque background, and a background that does not
    match what it sits beside turns the table into two panels with a
    seam down the middle — which is what `--panel` against the card's
    `--grad-card` wash actually looked like."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".rank-table tbody td { background:")
    block = css[i:i + 400]
    assert "position: sticky; left: 0" in block
    assert "background: var(--panel-2)" in block, (
        "the body cells and the pinned cell must take the same flat "
        "colour or the seam comes back")
    assert "th.rank-name { background: var(--panel)" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
