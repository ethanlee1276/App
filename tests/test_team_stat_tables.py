"""The team page, to the shape of the one Ethan put beside it.

Ethan, 2026-09-10, with ESPN's Rams tab open next to ours: "we could
still be showing more data, and we can use... now the ESPN uses theirs
as an example of how we should make ours work and the data we could
show."

Theirs is a leaders strip over Passing / Rushing / Receiving. Ours is
now the same page, built out of `player_game_logs` — the table the props
already grade against, so every name on it is a name this site can price.

WHAT IS DELIBERATELY ABSENT, and it is the whole discipline of the
change: ESPN prints LNG (longest play), BIG (plays over twenty) and
CMP/CMP%. A game log holds the yards, not the plays that made them, and
it holds no completion count. AVG is arithmetic on two numbers we have —
yards over carries — so AVG is here. A longest run is not arithmetic on
anything we have, so that column does not exist rather than being
estimated. AIR runs the other way: ESPN has no such column and nflverse
gives us air yards, so the receiving table shows one they do not.

A COLUMN EXISTS WHEN SOMEBODY HAS A NUMBER FOR IT. That is what lets one
table serve both football leagues without a second table to drift: the
college feed writes no targets, no air yards and no interceptions
(`sources.cfbstats.MARKETS`), so the college header simply does not
mention them. Nothing is filled with zeroes and nothing is filled with
dashes.

Run directly: `python3 tests/test_team_stat_tables.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, teamdex                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
SRV = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def _db(sport, team, rows):
    """rows = [(player, position, market, value, game_id)]"""
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [{
        "sport": sport, "season": 2025, "period": "001", "game_id": g,
        "player": p, "team": team, "opponent": "SEA", "position": pos,
        "home": 1, "market": m, "value": v} for p, pos, m, v, g in rows])
    conn.commit()
    return conn


def _rams():
    rows = []
    for g in ("g1", "g2"):
        rows += [("Matthew Stafford", "QB", "pass_yds", 282, g),
                 ("Matthew Stafford", "QB", "pass_att", 35, g),
                 ("Matthew Stafford", "QB", "pass_td", 2, g),
                 ("Matthew Stafford", "QB", "pass_int", 1, g),
                 ("Kyren Williams", "RB", "rush_yds", 71, g),
                 ("Kyren Williams", "RB", "carries", 15, g),
                 ("Kyren Williams", "RB", "rush_td", 1, g),
                 ("K.Williams", "", "xfp", 15.4, g),
                 ("Puka Nacua", "WR", "rec_yds", 107, g),
                 ("Puka Nacua", "WR", "receptions", 8, g),
                 ("Puka Nacua", "WR", "targets", 10, g),
                 ("Puka Nacua", "WR", "rec_td", 1, g),
                 ("Puka Nacua", "WR", "air_yards", 90, g)]
    return _db("nfl", "LA", rows)


def _section(t, key):
    for s in t["sections"]:
        if s["key"] == key:
            return s
    return None


def _cell(sec, player, col):
    i = sec["columns"].index(col)
    for r in sec["rows"]:
        if r["player"] == player:
            return r["cells"][i]
    raise AssertionError(f"{player} is not in {sec['key']}")


# --- the three tables -------------------------------------------------------
def test_the_page_draws_passing_rushing_and_receiving():
    t = teamdex.stat_tables(_rams(), "nfl", "LA")
    assert [s["title"] for s in t["sections"]] == ["Passing", "Rushing",
                                                   "Receiving"]


def test_the_numbers_are_the_seasons_own_totals():
    sec = _section(teamdex.stat_tables(_rams(), "nfl", "LA"), "passing")
    assert _cell(sec, "Matthew Stafford", "GP") == 2
    assert _cell(sec, "Matthew Stafford", "YDS") == 564.0
    assert _cell(sec, "Matthew Stafford", "ATT") == 70.0
    assert _cell(sec, "Matthew Stafford", "TD") == 4.0
    assert _cell(sec, "Matthew Stafford", "INT") == 2.0


def test_an_average_is_the_division_it_claims_to_be():
    """142 yards on 30 carries is 4.7, and that is arithmetic on two
    numbers this table holds — unlike a longest run, which is why there
    is no LNG column."""
    sec = _section(teamdex.stat_tables(_rams(), "nfl", "LA"), "rushing")
    assert _cell(sec, "Kyren Williams", "AVG") == 4.7
    assert _cell(sec, "Kyren Williams", "YDS/G") == 71.0


def test_no_column_claims_a_play_level_fact():
    t = teamdex.stat_tables(_rams(), "nfl", "LA")
    for sec in t["sections"]:
        for banned in ("LNG", "BIG", "CMP", "CMP%"):
            assert banned not in sec["columns"], (sec["key"], banned)


def test_the_leaders_strip_names_the_three_ESPN_names():
    t = teamdex.stat_tables(_rams(), "nfl", "LA")
    assert [(L["title"], L["player"], L["value"]) for L in t["leaders"]] == [
        ("Passing", "Matthew Stafford", 564.0),
        ("Rushing", "Kyren Williams", 142.0),
        ("Receiving", "Puka Nacua", 214.0)]


def test_the_leader_is_the_top_of_his_own_table():
    """Two facts, one query. A strip that could disagree with the table
    under it is two answers to one question."""
    rows = [("Backup", "RB", "rush_yds", 20, "g1"),
            ("Bell Cow", "RB", "rush_yds", 200, "g1")]
    t = teamdex.stat_tables(_db("nfl", "LA", rows), "nfl", "LA")
    assert t["leaders"][0]["player"] == "Bell Cow"
    assert _section(t, "rushing")["rows"][0]["player"] == "Bell Cow"


# --- one table, two leagues -------------------------------------------------
def test_college_gets_the_columns_its_feed_actually_writes():
    """`sources.cfbstats.MARKETS` has no targets, no air yards and no
    interceptions. The header must not mention them."""
    rows = []
    for g in ("g1", "g2"):
        rows += [("Nate Frazier", "WR", "rec_yds", 80, g),
                 ("Nate Frazier", "WR", "receptions", 6, g),
                 ("Nate Frazier", "WR", "rec_td", 1, g)]
    sec = _section(teamdex.stat_tables(_db("cfb", "UGA", rows), "cfb", "UGA"),
                   "receiving")
    assert sec["columns"] == ["GP", "REC", "YDS", "AVG", "TD", "YDS/G"]


def test_a_column_nobody_has_a_number_for_is_left_out_not_dashed():
    rows = [("Puka Nacua", "WR", "rec_yds", 107, "g1"),
            ("Puka Nacua", "WR", "receptions", 8, "g1")]
    sec = _section(teamdex.stat_tables(_db("nfl", "LA", rows), "nfl", "LA"),
                   "receiving")
    assert "TGTS" not in sec["columns"] and "TD" not in sec["columns"]
    assert all(c is not None for r in sec["rows"] for c in r["cells"])


def test_a_section_nobody_qualifies_for_is_not_drawn_empty():
    rows = [("Kyren Williams", "RB", "rush_yds", 71, "g1")]
    t = teamdex.stat_tables(_db("nfl", "LA", rows), "nfl", "LA")
    assert [s["key"] for s in t["sections"]] == ["rushing"]


def test_a_sport_with_no_football_shape_gets_no_tables():
    """A pitching line is not a passing line. Baseball and basketball
    get nothing here until they get their own sections, which is a
    better answer than a table that fits the wrong sport.

    The mapping is asserted directly rather than through an empty
    result: a baseball team has no passing yards either way, so an
    MLB fixture comes back empty whether the sport is mapped or not,
    and a test that reads that as a pass is not testing anything."""
    assert set(teamdex.STAT_SPORTS) == {"nfl", "cfb"}, teamdex.STAT_SPORTS
    rows = [("Shohei Ohtani", "DH", "hits", 2, "g1")]
    t = teamdex.stat_tables(_db("mlb", "LAD", rows), "mlb", "LAD")
    assert t["sections"] == [] and t["leaders"] == []


# --- one identity across both sections --------------------------------------
def test_the_stat_table_and_the_squad_agree_about_who_a_player_is():
    """The fold that stopped the squad listing K.Williams beside Kyren
    Williams is read by both, so the two sections of one page cannot
    name him two ways."""
    conn = _rams()
    sec = _section(teamdex.stat_tables(conn, "nfl", "LA"), "rushing")
    names = {r["player"] for r in sec["rows"]}
    squad = {w["player"] for g in teamdex.squad(conn, "nfl", "LA")["positions"]
             for w in g["players"]}
    assert "K.Williams" not in names and "K.Williams" not in squad
    assert "Kyren Williams" in names and "Kyren Williams" in squad


# --- the page -------------------------------------------------------------
def test_the_endpoint_publishes_the_tables_behind_its_own_guard():
    """A second section that fails must cost that section and not the
    page — the lesson `_squad_or_empty` was written to record after a
    NameError turned the whole team page into a 503."""
    assert "def _stats_or_empty(" in SRV
    i = SRV.index("def _stats_or_empty(")
    assert "except Exception" in SRV[i:i + 900]
    assert '"stats": _stats_or_empty(teamdex, conn, sport, team)' in SRV


def test_the_page_draws_them_above_the_squad():
    """Stats first, then the depth chart: ESPN's order and the order a
    reader wants — who is good here, then who plays here."""
    i = APP.index("${teamStatsHTML(d.stats, d.sport)}")
    assert i < APP.index("${teamSquadHTML(d.squad, d.sport)}")


def test_every_stat_row_is_a_door_to_the_player():
    i = APP.index("function teamStatsHTML(")
    block = APP[i:APP.index("\nfunction ", i + 1)]
    assert 'data-player-page="${escapeAttr(slugify(r.player))}"' in block
    assert 'tabindex="0"' in block and 'role="link"' in block


def test_a_door_that_is_not_a_button_answers_the_keyboard():
    """`role="link"` with `tabindex="0"` is a promise to a screen reader
    that the thing is operable. Until this the player door kept it only
    for a mouse — on the stat rows, and on every `likelyDoor` card that
    fell through to a player page."""
    i = APP.index("/* Keyboard parity: a card you can click is a control")
    block = APP[i:APP.index("\n});", i)]
    # A SOURCE PIN, and named as one: the handler is an inline listener
    # on `document`, so there is no function to call in node without a
    # DOM. What it pins is that the lookup is the lookup — the first
    # cut of this test matched the SELECTOR alone and passed happily
    # against `const guy = null && e.target.closest(...)`.
    assert 'const guy = e.target.closest("[data-player-page]");' in block
    assert "openPlayerRoute(guy.dataset.playerPage);" in block


def test_the_scroll_edge_says_there_is_more_to_the_right():
    """The season table has always scrolled sideways; nothing said so,
    so a column cut mid-digit read as a broken table (Ethan's
    screenshot)."""
    i = CSS.index(".rank-scroll {")
    block = CSS[i:i + 700]
    assert "mask-image" in block and "-webkit-mask-image" in block
    assert "scrollbar-gutter" in block


def test_the_leader_cards_and_stat_rows_have_their_styles():
    for sel in (".tld-card", ".tld-v", ".tst-row", ".tst-pos"):
        assert sel + " " in CSS or sel + "," in CSS or sel + ":" in CSS, sel


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
