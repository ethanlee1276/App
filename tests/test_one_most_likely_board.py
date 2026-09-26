"""One Most Likely board: every pick in one pool, four checks, a tier.

Ethan, 2026-09-26: "combine the matchup picks and most likely picks into
one big, just most likely pick area ... I don't want to lose any picks,
but I want to just be more confident in what we're selecting ... so we're
not confusing the user and don't have a million different places for a
million different picks." To the plan (the pool, the model / matchup /
market / record checks, Top · Strong · Worth a look, a touchdown lane):
"yeah do it". engine/likelyboard.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as B                                  # noqa: E402

GAME = {"home": "DET", "away": "NYJ",
        "scan": {"units": {"NYJ": {"def": {"passing": {"rank": 27}, "rushing": {"rank": 25}}},
                           "DET": {"def": {"passing": {"rank": 10}, "rushing": {"rank": 12}}}},
                 "redzone": {"DET": {"off": 12.6, "off_rel": 0.44, "def": 10.6, "def_rel": 0.2},
                             "NYJ": {"off": 6.7, "off_rel": -0.23, "def": 8.2, "def_rel": -0.07}}}}


def _result(**kw):
    base = {"games": [GAME], "recommendations": [{"player": "Amon-Ra St. Brown", "position": "WR"}],
            "scan_reads": {"NYJ@DET": {"players": [
                {"player": "Amon-Ra St. Brown", "team": "DET", "opp": "NYJ", "pos": "WR", "read": "good",
                 "label": "Good matchup", "lean": ["receptions"], "usage": {"tgt_share": 0.30}},
                {"player": "Garrett Wilson", "team": "NYJ", "opp": "DET", "pos": "WR", "read": "tough",
                 "label": "Tough matchup", "lean": ["rec_yds"]}]}},
            "most_likely": [], "matchup_picks": [], "td_scenarios": []}
    base.update(kw)
    return base


def _td(player="Amon-Ra St. Brown", prob=0.52, odds=-115, **kw):
    return {"kind": "td", "player": player, "team": "DET", "opponent": "NYJ", "market": "anytime_td",
            "side": "YES", "line": 0.5, "odds": odds, "book": "BetMGM", "model_prob": prob,
            "implied_prob": 0.50, "rz_chances": 3.1, "implied_total": 27.5, **kw}


def test_one_bet_from_two_makers_is_one_row_that_remembers_both():
    ml = dict(_td(), line=None, side="yes")          # the Most Likely board's shape
    mp = {"game": "NYJ@DET", "home": "DET", "away": "NYJ", "props": [],
          "td": [dict(_td(), matchup_score=8, matchup_lines=["NYJ’s pass defence ranks 27th of 32"])]}
    sc = dict(_td(), scenario=True, scenario_lines=["DET expected to score 27.5 by the lines"])
    b = B.build(_result(most_likely=[ml], matchup_picks=[mp], td_scenarios=[sc]))
    assert len(b["rows"]) == 1, [r["sources"] for r in b["rows"]]
    r = b["rows"][0]
    assert r["sources"] == ["likely", "matchup", "scenario"]
    assert r["case_lines"] == ["NYJ’s pass defence ranks 27th of 32", "DET expected to score 27.5 by the lines"]
    assert r["lane"] == "td" and r["game"] == "NYJ@DET"


def test_the_four_checks_and_the_tiers():
    top = _td()                                              # 52% ≥ 40%, matchup 8/8, 52 vs 50
    b = B.build(_result(most_likely=[top]))
    r = b["rows"][0]
    assert r["checks"] == {"model": True, "matchup": True, "market": True, "record": None}, r["checks"]
    assert r["tier"] == "top" and r["tier_label"] == "Top pick"
    assert r["matchup_score"] >= B.TD_CASE, "a Most Likely scorer is scored off his game's scan"
    far = _td(player="Far Off", prob=0.70, implied_prob=0.50)
    rows = {x["player"]: x for x in B.build(_result(most_likely=[far]))["rows"]}
    assert rows["Far Off"]["checks"]["market"] is False
    assert "far above every book" in rows["Far Off"]["check_notes"]["market"]
    assert rows["Far Off"]["tier"] != "top"


def test_a_prop_is_checked_against_the_matchup_read():
    over = {"kind": "prop", "player": "Amon-Ra St. Brown", "team": "DET", "opponent": "NYJ",
            "market": "receptions", "side": "OVER", "line": 6.5, "odds": -130, "model_prob": 0.62,
            "implied_prob": 0.57}
    against = {"kind": "prop", "player": "Garrett Wilson", "team": "NYJ", "opponent": "DET",
               "market": "rec_yds", "side": "OVER", "line": 60.5, "odds": -110, "model_prob": 0.60,
               "implied_prob": 0.52}
    rows = {r["player"]: r for r in B.build(_result(most_likely=[over, against]))["rows"]}
    assert rows["Amon-Ra St. Brown"]["checks"]["matchup"] is True
    assert rows["Garrett Wilson"]["checks"]["matchup"] is False
    assert "leans the other way" in rows["Garrett Wilson"]["check_notes"]["matchup"]
    assert rows["Amon-Ra St. Brown"]["tier"] in ("top", "strong")


def test_the_record_check_reads_our_own_journal():
    from engine import ledger
    conn = ledger.connect(":memory:")
    for i in range(30):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, hit_prob, status, category) "
                     "VALUES ('nfl', ?, ?, 'receptions', 'over', 4.5, 0.65, ?, 'likely')",
                     (f"2026-W0{i % 3 + 1}", f"P{i}", "won" if i < 20 else "lost"))
    # The same bet in a second bucket is counted once.
    conn.execute("INSERT INTO bets (sport, date, player, market, side, line, hit_prob, status, category) "
                 "VALUES ('nfl', '2026-W01', 'P0', 'receptions', 'over', 4.5, 0.65, 'won', 'matchup_prop')")
    t = B.record_table(conn, "nfl")
    cell = t[("receptions", "over", 0.60)]
    assert cell["n"] == 30 and cell["hits"] == 20
    ok, words = B.record_check(t, "receptions", "over", 0.63)
    assert ok is True and "hit 67% of 30 when we said 65%" in words
    none, words = B.record_check(t, "rush_yds", "under", 0.63)
    assert none is None and "too short" in words


def test_the_tier_rule():
    assert B.tier_of({"model": True, "matchup": True, "market": True, "record": None}) == "top"
    assert B.tier_of({"model": True, "matchup": True, "market": True, "record": True}) == "top"
    assert B.tier_of({"model": True, "matchup": True, "market": None, "record": None}) == "strong"
    assert B.tier_of({"model": True, "matchup": True, "market": True, "record": False}) == "strong"
    # The box, 2026-09-26: 42 Top picks, most with no matchup read. Without
    # the matchup a pick tops out at Strong, whatever else agrees.
    assert B.tier_of({"model": True, "matchup": None, "market": True, "record": True}) == "strong"
    assert B.tier_of({"model": False, "matchup": True, "market": True, "record": True}) == "look"
    assert B.tier_of({"model": True, "matchup": False, "market": False, "record": True}) == "look"


def test_it_is_built_journaled_and_paywalled():
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'result["likely_board"] = _lb.build(result, record=_rec)' in build
    assert 'category="board", grade_label=_label' in build
    from engine import gate
    assert "likely_board" in gate.PAID_KEYS


def test_the_page_draws_one_board_everywhere():
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    # The Most Likely page and Home draw it when the build carries it…
    assert "host.innerHTML = oneBoardHTML() + likelyScriptsHTML(rows)" in js
    assert "${oneBoardHomeHTML()}" in js
    # …the separate shelves fold into it…
    assert 'function matchupPicksHTML() {\n  if (oneBoardOn()) return "";' in js
    assert 'function tdScenariosHTML() {\n  if (oneBoardOn()) return "";' in js
    # …the game page shows this game's rows by tier in place of its old cards…
    assert "if (oneBoardOn()) return obGameHTML(g);" in js
    assert "const likelies = oneBoardOn() ? [] : gameLikely.filter" in js
    # …every row carries its four checks and its why, a touchdown says it
    # in plain words, and a row opens its own pick page.
    for bit in ('["model", "Our number"]', '["matchup", "Matchup"]', '["market", "Market"]',
                '["record", "Our record"]', "hits about ${Math.max(1, Math.round(Number(r.model_prob || 0) * 10))} in 10",
                "((state.data || {}).likely_board || {}).rows || []);"):
        assert bit in js, bit
    # Best of the slate or By game, with lane filters.
    assert 'data-ob-view="best">${icon("trophy", 15)} Best of the slate' in js and 'data-ob-view="game">By game' in js
    assert 'localStorage.setItem("qb.obView", state.obView)' in js


def test_the_record_reads_the_board_back_by_tier():
    """Ethan, 2026-09-26: "yes do the record page next". Every board row is
    journaled on paper under 'board' with its tier as the grade; the Record
    page shows each tier's W-L, hit rate against what we claimed, and ROI."""
    from engine import ledger
    conn = ledger.connect(":memory:")
    rows = [("Top pick", "won", 0.8), ("Top pick", "won", 0.9), ("Top pick", "lost", -1.0),
            ("Strong", "lost", -1.0), ("Worth a look", "open", 0.0)]
    for i, (g, st, pnl) in enumerate(rows):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, hit_prob, stake_units, "
                     "pnl_units, status, category, grade) VALUES ('nfl', '2026-W04', ?, 'rec_yds', 'over', 24.5, "
                     "-120, 0.66, 1.0, ?, ?, 'board', ?)", (f"P{i}", pnl, st, g))
    rep = ledger.board_report(conn, sport="nfl")
    top, strong, look = rep["tiers"]
    assert [t["tier"] for t in rep["tiers"]] == list(ledger.BOARD_TIERS) == ["Top pick", "Strong", "Worth a look"]
    assert (top["w"], top["l"], top["settled"], top["actual"], top["claimed"]) == (2, 1, 3, 0.6667, 0.66)
    assert top["units"] == 0.7 and abs(top["roi"] - 0.7 / 3) < 1e-3
    assert (strong["w"], strong["l"]) == (0, 1) and look["open"] == 1 and look["actual"] is None
    assert rep["settled"] == 4 and rep["open"] == 1
    src = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()
    assert '"board": board_report(conn, since=since),' in src and '"board_by_sport": {' in src
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "+ recBoardSection(scoped ? (d.board_by_sport || {})[scope] : d.board, scope)" in js
    assert "Most Likely board · by tier" in js


def test_the_picks_tab_is_the_one_board_and_one_door_to_the_edge_picks():
    """Ethan, 2026-09-26: "any user could hop on and know exactly, 'okay,
    these are the bets I need to do'". The phone's Picks tab is the Pick of
    the Day, then Top picks, then Strong; the edge bets are one button to
    their own page, not a second copy of them."""
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    tn = js[js.index("function renderTonight() {"):]
    tn = tn[:tn.index("\nfunction ", 10)]
    branch = tn[tn.index("if (oneBoardOn()) {"):tn.index("/* The Picks page in the redesign's shape")]
    assert (branch.index("${potdHeroHTML(d)}") < branch.index('<div class="section-title">Top picks')
            < branch.index('<div class="section-title">Strong'))
    assert 'data-goto="edge">Edge picks · ${plural(n, "bet")} tonight' in branch
    assert "edgeRow" not in branch and "cardHTML" not in branch, "no second copy of the edge bets"
    assert "(r.checks || {}).matchup === true" in branch, "the note is the matchup's reason, only when it backs the pick"
    guide = js[js.index("function renderLikely() {"):]
    assert "Every pick goes through four checks" in guide[:9000]


def test_the_page_and_home_follow_the_render():
    """Ethan, 2026-09-26, two renders of the Most Likely page: "For when you
    click on the most likely bets and it takes you to the full page, follow
    this render. And then obviously on the main dashboard, we want to follow
    this render as well." The hero over the stadium art, the four pills, and
    each pick as a card: rank, face with the team mark, the bet and book,
    the tags, the four checks and Why?, the price, the ring (TOP on a Top
    pick), the door and View details. Home draws the same card."""
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    hero = js[js.index("function obHeroHTML() {"):]
    hero = hero[:hero.index("\nfunction ", 10)]
    for bit in ("Most Likely <em>to Hit</em>", "Every pick in one place, tiered by how many checks agree.",
                "img/venues/variants/${art}-gold.jpg", "How we know", "How it’s ranked and what it turned down",
                'href="#record"'):
        assert bit in hero, bit
    card = js[js.index("function obCardHTML(r, rank, opts = {}) {"):]
    card = card[:card.index("\nfunction ", 10)]
    for bit in ('<span class="ob-rank">#${rank}</span>', "${obFaceHTML(r)}", "${tags}", "${obChecksHTML(r)}",
                '<span class="ob-odds">', "${obRingHTML(r)}", 'class="ob-door"', "View details"):
        assert bit in card, bit
    assert card.count("${door}") == 3, "the face, the door and View details all open the pick"
    assert '${r.tier === "top" ? "<small>TOP</small>" : ""}' in js
    assert "obCardHTML(r, i + 1, { why: false })" in js, "Home draws the same card"
    assert "note.innerHTML = obHeroHTML();" in js and ".view.ob-on > .section-title { display: none; }" in css
    assert 'const OB_SORTS = [["prob", "Highest hit rate"], ["kick", "Kickoff"], ["price", "Best price"]];' in js
    # A phone reads the picks first: one sideways row of pills, tiers and lanes.
    phone = css[css.index(".ob-pills, .one-board .ob-summary, .ob-filters { flex-wrap: nowrap;") - 400:]
    assert "@media (max-width: 760px)" in phone[:400]


def test_every_chip_counts_the_cards_it_shows():
    """Ethan, 2026-09-26: "It'll display we're showing 70 yard picks, but
    then we'll only show 10… it shows that we have 153 picks total, but it
    doesn't show that many." The tier chips and the kind chips are two
    filters on one list; each chip counts what it would show with the other
    as it stands; every counted pick is drawn — no fold, no closed tier —
    and a line says how many are showing and how they split."""
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    fn = lambda name: js[js.index(f"function {name}("):][:js[js.index(f"function {name}("):].index("\nfunction ", 10)]
    board, secs, games = fn("oneBoardHTML"), fn("obTierSections"), fn("obByGameHTML")
    for body in (secs, games):
        assert "foldRowsHTML" not in body and "<details" not in body, "a counted pick is never folded away"
    assert "const rows = obPicked(all, tier, f);" in board
    assert "obPicked(all, t, f).length" in board and "<span>${obPicked(all, tier, k).length}</span>" in board, \
        "each chip counts with the other filter applied"
    assert '[["all", "All tiers"], ...OB_TIERS]' in board and 'data-ob-tier="${t}"' in board
    assert "${obShowingHTML(rows, tier)}" in board
    assert 'state.obTier = b.dataset.obTier === state.obTier ? "all" : b.dataset.obTier;' in js
    assert 'obFilter: "all", obTier: "all",' in js
    # The phone card is two lines: who beside the price and ring, then the checks.
    phone = css[css.index('everything\'s very bulky'):]
    phone = phone[:phone.index("\n}\n")]
    assert 'grid-template-areas: "who odds ring" "checks checks checks";' in phone
    assert ".ob-door { display: none; }" in phone and ".ob-sec-sub { display: none; }" in phone


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
