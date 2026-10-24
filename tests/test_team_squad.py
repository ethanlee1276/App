"""A team page you arrive at from search, with nobody on it.

Ethan, 2026-09-10, looking at the Los Angeles Rams page: "We should be
showing more info too when you look up a team on the search page. We
should show a depth chart and player stats and all that shit."

The page had the record, the season-by-season ranks and the head-to-head
picker — every number a scoreline can produce — and not one player. It is
the surface somebody lands on from search, and it was a dead end with a
table on it.

A DEPTH CHART MEASURED RATHER THAN PUBLISHED. nflverse publishes a real
one and `engine/sources/depthcharts` already reads it — but it is what a
coach filed, it is NFL-only, and it goes stale against a chart nobody
refiled. `teamdex.squad` orders each position by what the players
actually did: games first, then that position's leading market. It covers
every league this repo ingests and answers the question a bettor is
really asking — who gets the ball. What it cannot do is call a Week 1
starter who has not played yet, and the page says so under the section
rather than letting a reader assume.

Everything comes out of `player_game_logs`, the table the props grade
against, so a name on this page is a name the rest of the site can price.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, teamdex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
SRV = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def _logs(*rows):
    """A history DB holding exactly these (player, pos, market, value, game)."""
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [{
        "sport": "nfl", "season": 2025, "period": "001", "game_id": g,
        "player": p, "team": "LA", "opponent": "SEA", "position": pos,
        "home": 1, "market": m, "value": v} for p, pos, m, v, g in rows])
    conn.commit()
    return conn


def _starters(conn, team="LA"):
    """{position: [player, ...]} in the order the page will draw them."""
    sq = teamdex.squad(conn, "nfl", team)
    return {g["position"]: [w["player"] for w in g["players"]]
            for g in sq["positions"]}


# --- who plays here ---------------------------------------------------------
def test_the_squad_lists_the_teams_players_by_position():
    conn = _logs(("Matthew Stafford", "QB", "pass_yds", 300, "g1"),
                 ("Kyren Williams", "RB", "rush_yds", 90, "g1"),
                 ("Puka Nacua", "WR", "rec_yds", 110, "g1"))
    assert _starters(conn) == {"QB": ["Matthew Stafford"],
                               "RB": ["Kyren Williams"],
                               "WR": ["Puka Nacua"]}


def test_the_order_inside_a_position_is_games_then_volume():
    """This is the depth part. The man who played every week is above the
    man who played once, whatever either did in his."""
    conn = _logs(("Backup", "RB", "rush_yds", 400, "g1"),
                 ("Starter", "RB", "rush_yds", 40, "g1"),
                 ("Starter", "RB", "rush_yds", 40, "g2"))
    assert _starters(conn)["RB"] == ["Starter", "Backup"]


def test_volume_breaks_the_tie_when_the_games_agree():
    conn = _logs(("Second", "WR", "rec_yds", 20, "g1"),
                 ("First", "WR", "rec_yds", 120, "g1"))
    assert _starters(conn)["WR"] == ["First", "Second"]


def test_a_players_leading_stat_is_the_one_his_position_is_read_by():
    """THE PASS-CATCHING BACK, chosen because he is the case where the
    position's market and the player's biggest number disagree — a
    receiving back can out-gain his own carries. Reading him by receiving
    yards would put him among the receivers' numbers and rank the backs
    by who catches most, which is not what a backfield is.

    Every tidier fixture passes with the position table deleted
    entirely (`rush_yds` is a quarterback's biggest number too), which is
    exactly how the first cut of this test let that mutant live."""
    conn = _logs(("Receiving Back", "RB", "rush_yds", 30, "g1"),
                 ("Receiving Back", "RB", "rec_yds", 200, "g1"))
    who = teamdex.squad(conn, "nfl", "LA")["positions"][0]["players"][0]
    assert who["lead_market"] == "rush_yds", \
        "the back is being read by the receivers' market"
    assert who["stats"][0]["market"] == "rush_yds"


def test_a_position_the_table_has_never_seen_reads_by_its_biggest_number():
    """A college roster carries positions this repo has no lead market
    for, and guessing at them is worse than reading the numbers."""
    conn = _logs(("Utility Guy", "ATH", "rush_yds", 12, "g1"),
                 ("Utility Guy", "ATH", "rec_yds", 90, "g1"))
    who = teamdex.squad(conn, "nfl", "LA")["positions"][0]["players"][0]
    assert who["lead_market"] == "rec_yds"


def test_the_per_game_number_is_per_game_played_not_per_row():
    conn = _logs(("Kyren Williams", "RB", "rush_yds", 100, "g1"),
                 ("Kyren Williams", "RB", "rush_yds", 50, "g2"))
    st = teamdex.squad(conn, "nfl", "LA")["positions"][0]["players"][0]
    assert st["games"] == 2
    assert st["stats"][0]["total"] == 150.0 and st["stats"][0]["per_game"] == 75.0


# --- what it refuses --------------------------------------------------------
def test_another_teams_player_is_not_on_this_squad():
    conn = _logs(("Ours", "QB", "pass_yds", 300, "g1"))
    db.upsert_player_logs(conn, [{
        "sport": "nfl", "season": 2025, "period": "001", "game_id": "g9",
        "player": "Theirs", "team": "SEA", "opponent": "LA", "position": "QB",
        "home": 0, "market": "pass_yds", "value": 400}])
    conn.commit()
    assert _starters(conn)["QB"] == ["Ours"]


def test_a_team_with_no_logged_games_gets_an_empty_squad_not_an_error():
    """Which in the first week of a season is most of a roster, and the
    page draws nothing rather than an empty table."""
    sq = teamdex.squad(db.connect(":memory:"), "nfl", "LA")
    assert sq == {"season": None, "positions": [], "players": 0}


def test_only_the_latest_season_with_logs_is_shown():
    """A squad is who plays here NOW; pooling five seasons would list
    every player who ever passed through."""
    conn = _logs(("This Year", "QB", "pass_yds", 300, "g1"))
    db.upsert_player_logs(conn, [{
        "sport": "nfl", "season": 2021, "period": "001", "game_id": "old",
        "player": "Long Gone", "team": "LA", "opponent": "SEA",
        "position": "QB", "home": 1, "market": "pass_yds", "value": 999}])
    conn.commit()
    sq = teamdex.squad(conn, "nfl", "LA")
    assert sq["season"] == 2025
    assert _starters(conn)["QB"] == ["This Year"]


def test_a_long_position_group_is_capped_and_says_how_many_there_are():
    """A 90-man roster is not a page, and a truncated list that does not
    say it is truncated is a lie about the squad's size."""
    conn = _logs(*[(f"WR {i}", "WR", "rec_yds", 100 - i, f"g{i}")
                   for i in range(12)])
    grp = teamdex.squad(conn, "nfl", "LA")["positions"][0]
    assert len(grp["players"]) == teamdex.SQUAD_PER_POSITION
    assert grp["listed"] == 12


def test_the_positions_read_in_the_roster_pages_own_order():
    """Two orderings of one squad on two pages is the drift this
    borrows `engine.rosters` to avoid."""
    conn = _logs(("A Kicker", "K", "rush_yds", 1, "g1"),
                 ("A Corner", "CB", "rec_yds", 1, "g1"),
                 ("A Passer", "QB", "pass_yds", 1, "g1"))
    assert [g["position"] for g in teamdex.squad(conn, "nfl", "LA")["positions"]] \
        == ["QB", "CB", "K"]


# --- the door and the page --------------------------------------------------
def test_the_endpoint_hands_the_squad_over():
    i = SRV.index("def _team(self, q):")
    block = SRV[i:SRV.index("\n    def ", i + 1)]
    assert '"squad": _squad_or_empty' in block


def test_a_bad_squad_read_cannot_take_the_record_down_with_it():
    """The record above it has been right since 09-09 and comes from a
    different query against a different table."""
    i = SRV.index("def _squad_or_empty(")
    body = SRV[i:SRV.index("\n    def ", i + 1)]
    assert "except Exception" in body and '"positions": []' in body


def test_every_name_on_the_squad_opens_that_players_page():
    """The point of putting a squad here: the team page is where somebody
    arrives from search, and it was a dead end."""
    i = APP.index("function teamSquadHTML(")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert 'data-player-page="${escapeAttr(slugify(w.player))}"' in body


def test_the_section_is_drawn_on_the_team_page():
    i = APP.index("function renderTeamPage(")
    body = APP[i:APP.index("\n/* Delegated", i)]
    assert "teamSquadHTML(d.squad, d.sport)" in body


def test_the_page_says_what_the_order_means_and_what_it_cannot_know():
    """"Ordered by what he actually did" and "a player who has not taken
    a snap is not here" — both, because a reader who assumes this is the
    coach's chart is being misled by silence."""
    i = APP.index("function teamSquadHTML(")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "actually did" in body
    assert "has not taken a snap" in body


def test_nothing_is_drawn_when_the_squad_is_empty():
    i = APP.index("function teamSquadHTML(")
    body = APP[i:APP.index("\nfunction ", i + 1)]
    assert "if (!groups.length) return \"\";" in body


def test_the_rows_wrap_rather_than_scroll_sideways_on_a_phone():
    """The season table above already has to scroll; one horizontal
    scroller a page is plenty."""
    i = CSS.index(".tsq-stats {")
    assert "flex: 1 0 100%" in CSS[CSS.index("@media (max-width: 560px)", i):
                                   CSS.index("@media (max-width: 560px)", i) + 200]
    assert "overflow-x" not in CSS[i:i + 400]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
