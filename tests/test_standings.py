"""Standings and the postseason bracket, counted from our own results.

Every finished game already carries both teams and both scores, so a
standings table is arithmetic over rows we own. That is worth more than a
saved request: the ratings, the settlement and the standings all read the
same games, so a record here and a record on a matchup card cannot drift
apart.

The load-bearing tests are the two separations. Standings are REGULAR
SEASON — counting playoff results there showed a 14-3 team as 17-4 on real
data and gave nearly every club a losing streak, because the last thing
most teams do is lose a playoff game. And the bracket is drawn only from
games that were played; a chart that looks authoritative gets believed, so
nothing on it may be predicted.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import divisions, playoffs, standings
from engine.db import connect, upsert_games


def _seed(sport="nfl", season=2025, games=None):
    conn = connect(":memory:")
    rows = []
    for i, (period, home, away, hs, as_) in enumerate(games or []):
        rows.append({"sport": sport, "season": season, "period": period,
                     "game_id": str(i), "home": home, "away": away,
                     "home_score": hs, "away_score": as_})
    upsert_games(conn, rows)
    return conn


# --- the regular-season / postseason split ---------------------------------
def test_playoff_games_are_not_counted_in_the_standings():
    """The bug this pins, found on real data: a 14-3 team showed as 17-4
    and the deepest playoff run got the best "regular season" record."""
    conn = _seed(games=[
        ("001", "NE", "BUF", 30, 10), ("002", "NE", "MIA", 24, 17),
        ("019", "NE", "HOU", 27, 20),        # Wild Card — postseason
        ("020", "NE", "DEN", 21, 24),        # Divisional loss
    ])
    t = standings.compute(conn, "nfl", season=2025)
    ne = next(r for g in t["groups"] for r in g["teams"] if r["team"] == "NE")
    assert ne["record"] == "2-0", f"playoff games leaked in: {ne['record']}"
    assert t["games_counted"] == 2


def test_a_playoff_loss_does_not_become_a_regular_season_streak():
    conn = _seed(games=[("001", "NE", "BUF", 30, 10),
                        ("002", "NE", "MIA", 24, 17),
                        ("020", "NE", "DEN", 10, 24)])
    ne = next(r for g in standings.compute(conn, "nfl", 2025)["groups"]
              for r in g["teams"] if r["team"] == "NE")
    assert ne["streak_label"] == "W2"


def test_the_postseason_boundary_is_per_sport():
    assert playoffs.is_postseason("nfl", 2025, "018") is False
    assert playoffs.is_postseason("nfl", 2025, "019") is True
    assert playoffs.is_postseason("mlb", 2026, "2026-09-15") is False
    assert playoffs.is_postseason("mlb", 2026, "2026-10-05") is True
    # The NBA's postseason lands in the NEXT calendar year.
    assert playoffs.is_postseason("nba", 2025, "2026-03-01") is False
    assert playoffs.is_postseason("nba", 2025, "2026-05-01") is True


# --- the table itself -------------------------------------------------------
def test_records_splits_and_differential_are_all_counted():
    conn = _seed(games=[
        ("001", "NE", "BUF", 30, 10),      # NE home win
        ("002", "MIA", "NE", 20, 27),      # NE road win
        ("003", "NYJ", "NE", 21, 14),      # NE road loss
    ])
    ne = next(r for g in standings.compute(conn, "nfl", 2025)["groups"]
              for r in g["teams"] if r["team"] == "NE")
    assert ne["record"] == "2-1" and ne["home"] == "1-0" and ne["away"] == "1-1"
    assert ne["diff"] == (30 + 27 + 14) - (10 + 20 + 21)
    assert abs(ne["pct"] - 2 / 3) < 1e-4


def test_a_tie_is_half_a_win_and_ends_a_streak():
    """The NFL plays ties. Extending a win streak through one would be a
    claim about form the results do not support."""
    conn = _seed(games=[("001", "NE", "BUF", 20, 10),
                        ("002", "NE", "MIA", 17, 17),
                        ("003", "NE", "NYJ", 24, 14)])
    ne = next(r for g in standings.compute(conn, "nfl", 2025)["groups"]
              for r in g["teams"] if r["team"] == "NE")
    assert ne["record"] == "2-0-1"
    assert abs(ne["pct"] - 2.5 / 3) < 1e-4
    assert ne["streak_label"] == "W1", "the streak ran through a tie"


def test_teams_are_grouped_into_their_real_divisions():
    conn = _seed(games=[("001", "NE", "BUF", 30, 10),
                        ("002", "DAL", "PHI", 20, 17)])
    labels = {g["label"] for g in standings.compute(conn, "nfl", 2025)["groups"]}
    assert "AFC East" in labels and "NFC East" in labels


def test_a_relocated_franchise_is_one_team_not_two():
    """Six seasons of history contains relocations. Oakland in 2021 and
    Las Vegas in 2026 are one club's record, and splitting them would show
    two half teams."""
    assert divisions.canonical("nfl", "OAK") == "LV"
    assert divisions.canonical("nfl", "STL") == "LA"
    assert divisions.canonical("nfl", "SD") == "LAC"
    assert divisions.group_of("nfl", "OAK") == ("AFC", "West")


def test_an_unknown_team_is_listed_rather_than_dropped():
    """A page that crashes on an expansion franchise is worse than one
    that lists it under "League" until somebody adds the row."""
    conn = _seed(sport="wnba", season=2026,
                 games=[("2026-06-01", "ZZZ", "ATL", 90, 80)])
    t = standings.compute(conn, "wnba", season=2026)
    everyone = {r["team"] for g in t["groups"] for r in g["teams"]}
    assert "ZZZ" in everyone
    assert any(g["conference"] == "League" for g in t["groups"])


def test_the_order_does_not_claim_to_be_the_leagues_tiebreakers():
    conn = _seed(games=[("001", "NE", "BUF", 30, 10)])
    note = standings.compute(conn, "nfl", 2025)["order_note"]
    assert "our own order" in note and "official" in note


# --- the bracket ------------------------------------------------------------
def test_no_bracket_before_the_postseason():
    conn = _seed(games=[("001", "NE", "BUF", 30, 10)])
    b = playoffs.bracket(conn, "nfl", season=2025)
    assert b["started"] is False and b["rounds"] == []
    assert "actually played" in b["note"]


def test_rounds_come_from_who_played_whom():
    """Derived rather than tabulated, so byes and reseeding come out right
    without a format table that has to be maintained per league per year."""
    conn = _seed(games=[
        ("019", "NE", "HOU", 27, 20),     # Wild Card
        ("019", "BUF", "PIT", 24, 17),
        ("020", "NE", "BUF", 21, 14),     # Divisional: both R1 winners
        ("022", "NE", "SEA", 20, 24),     # Final
    ])
    b = playoffs.bracket(conn, "nfl", season=2025)
    assert b["started"] is True
    got = [(r["name"], len(r["matchups"])) for r in b["rounds"]]
    assert got[0][1] == 2 and got[-1][1] == 1
    assert got[-1][0] == "Super Bowl", got


def test_a_shallow_bracket_is_named_from_the_end_not_the_start():
    """A chart seen at the Conference Finals has two rounds in it, and
    calling those "Wild Card" and "Divisional" would be wrong in the most
    visible place on the page."""
    conn = _seed(games=[("021", "NE", "DEN", 27, 20),
                        ("022", "NE", "SEA", 20, 24)])
    names = [r["name"] for r in playoffs.bracket(conn, "nfl", 2025)["rounds"]]
    assert names == ["Conference Championship", "Super Bowl"]


def test_a_series_score_is_games_won_not_a_prediction():
    conn = _seed(sport="nba", season=2025, games=[
        ("2026-04-20", "BOS", "MIA", 110, 100),
        ("2026-04-22", "BOS", "MIA", 105, 108),
        ("2026-04-24", "MIA", "BOS", 99, 112),
    ])
    m = playoffs.bracket(conn, "nba", 2025)["rounds"][0]["matchups"][0]
    assert sorted(m["teams"]) == ["BOS", "MIA"]
    assert m["games"] == 3 and m["leader"] == "BOS"
    assert sorted(m["score"], reverse=True) == [2, 1]


def test_a_projected_seeding_is_never_called_a_bracket():
    conn = _seed(games=[("001", "NE", "BUF", 30, 10),
                        ("002", "KC", "DEN", 24, 17)])
    seeds = standings.conference_seeds(standings.compute(conn, "nfl", 2025))
    assert seeds and all("seed" in t for c in seeds for t in c["seeds"])
    import standings_build
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "standings_build.py")).read()
    assert "projected_seeds" in src
    # It must not be published alongside a real bracket — two charts of the
    # same thing, one real and one imagined, is how the imagined one gets
    # believed.
    assert 'bracket["started"] or not teams' in src


# --- the page ---------------------------------------------------------------
def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_standings_is_a_per_sport_tab():
    html = _read("web", "index.html")
    assert 'data-view="standings"' in html
    assert 'id="view-standings"' in html
    js = _read("web", "js", "app.js")
    assert "standings_${key}.json" in js, "the page loads one shared file"
    assert '"standings"' in js[js.index("const VIEW_ORDER"):
                               js.index("const VIEW_ORDER") + 300]


def test_switching_leagues_redraws_the_table():
    js = _read("web", "js", "app.js")
    fn = js[js.index("function renderAll("):js.index("function renderEmptySlate(")]
    assert 'state.view === "standings"' in fn


def test_the_bracket_round_names_share_one_line():
    """Letting the round name ride the space-around distribution walked
    the headings diagonally down the page — the later the round, the lower
    its label. Only the matchups spread out to meet the next round."""
    css = _read("web", "css", "styles.css")
    js = _read("web", "js", "app.js")
    assert ".brk-matches" in css and "brk-matches" in js, \
        "the matchups have no wrapper, so the heading still spreads"
    block = css[css.index(".brk-round {"):]
    block = block[:block.index("}") + 1]
    assert "justify-content" not in block, \
        "the round column still distributes its heading"


def test_the_launcher_builds_them():
    src = _read("launch.py")
    fn = src[src.index("def refresh_all("):src.index("def _run_maintenance(")]
    assert "refresh_standings(" in fn


def test_every_sport_with_a_board_gets_standings_except_ufc():
    import standings_build
    assert set(standings_build.SPORTS) == {"nfl", "mlb", "nba", "wnba", "cfb"}



# --- the league's own table, and the tie that never happened ---------------
# Ethan, 2026-08-12: "This is not live or real data at all. We need too fix
# that so our standings pages displays the actual standings of the current
# seasons LIVE DATA." The MLB page showed 70-69-1 and 66-68-4 — ties, in a
# sport that has none — and the order followed them.

def test_a_sport_without_ties_never_records_one():
    """An equal-score row in baseball is a suspended, postponed or
    unscored game, not half a result. Counting it inflated games played,
    moved every pct and diff, and put a .504 club atop the AL Central."""
    conn = _seed(sport="mlb", season=2026, games=[
        ("2026-04-01", "NYY", "BOS", 5, 3),
        ("2026-04-02", "NYY", "BOS", 2, 4),
        ("2026-04-03", "NYY", "BOS", 0, 0),     # never finished
    ])
    t = standings.compute(conn, "mlb", season=2026, today="2026-08-12")
    row = [r for g in t["groups"] for r in g["teams"] if r["team"] == "NYY"][0]
    assert row["ties"] == 0, "baseball does not play ties"
    assert row["record"] == "1-1", row["record"]
    assert row["games"] == 2, "the unfinished game must not count as played"
    assert t["unfinished_skipped"] == 1
    assert t["games_counted"] == 2


def test_football_still_counts_the_ties_it_actually_plays():
    """The other half: the NFL does play them, so nothing changes there."""
    conn = _seed(sport="nfl", season=2025, games=[
        ("001", "NE", "BUF", 20, 20), ("002", "NE", "MIA", 24, 17)])
    t = standings.compute(conn, "nfl", season=2025, today="2025-12-01")
    row = [r for g in t["groups"] for r in g["teams"] if r["team"] == "NE"][0]
    assert row["ties"] == 1 and row["record"] == "1-0-1"


def test_the_computed_table_admits_what_it_is():
    conn = _seed(sport="mlb", season=2026,
                 games=[("2026-04-01", "NYY", "BOS", 5, 3)])
    t = standings.compute(conn, "mlb", season=2026, today="2026-08-12")
    assert t["source"] == "computed"


MLB_FEED = {"records": [
    {"standingsType": "regularSeason", "division": {"id": 201},
     "teamRecords": [
        {"team": {"id": 147, "name": "New York Yankees"},
         "wins": 79, "losses": 62, "runsScored": 700, "runsAllowed": 644,
         "streak": {"streakCode": "W1"},
         "records": {"homeRecord": "44-27", "awayRecord": "35-35"}},
        {"team": {"id": 111, "name": "Boston Red Sox"},
         "wins": 72, "losses": 68, "runsScored": 690, "runsAllowed": 648,
         "streak": {"streakCode": "L4"},
         "records": {"homeRecord": "40-30", "awayRecord": "32-38"}},
        {"team": {"id": 999, "name": "Not A Club"}, "wins": 1},   # dropped
     ]},
]}


def test_the_mlb_feed_parses_by_key_and_drops_rather_than_guesses():
    from engine.sources import leaguestandings as ls
    rows = ls.parse_mlb(MLB_FEED)
    assert len(rows) == 2, "a club with no win/loss pair is not a row"
    nyy = [r for r in rows if r["team"] == "NYY"][0]
    assert (nyy["wins"], nyy["losses"], nyy["ties"]) == (79, 62, 0)
    assert nyy["streak"] == 1 and nyy["points_for"] == 700
    assert (nyy["home_wins"], nyy["away_losses"]) == (44, 35)
    bos = [r for r in rows if r["team"] == "BOS"][0]
    assert bos["streak"] == -4, "L4 is a losing streak, and must be signed"
    assert ls.parse_mlb({}) == [] and ls.parse_mlb(None) == []


ESPN_FEED = {"children": [
    {"name": "American Football Conference", "children": [
        {"name": "AFC East", "standings": {"entries": [
            {"team": {"abbreviation": "BUF"}, "stats": [
                {"name": "wins", "value": 13}, {"name": "losses", "value": 4},
                {"name": "ties", "value": 0},
                {"name": "pointsFor", "value": 483},
                {"name": "pointsAgainst", "value": 350},
                {"name": "streak", "value": 3},
                {"name": "Home", "displayValue": "7-1"},
                {"name": "Road", "displayValue": "6-3"}]},
            {"team": {"abbreviation": "MIA"}, "stats": [
                {"name": "wins", "value": 8}, {"name": "losses", "value": 9},
                {"name": "streak", "value": -2}]},
            {"team": {"abbreviation": "NOPE"}, "stats": []},      # dropped
        ]}},
    ]},
]}


def test_the_espn_feed_is_walked_at_whatever_depth_it_nests():
    from engine.sources import leaguestandings as ls
    rows = ls.parse_espn(ESPN_FEED)
    assert len(rows) == 2, "an entry with no wins/losses is not a row"
    buf = [r for r in rows if r["team"] == "BUF"][0]
    assert (buf["wins"], buf["losses"]) == (13, 4)
    assert buf["points_for"] == 483 and buf["streak"] == 3
    assert (buf["home_wins"], buf["home_losses"]) == (7, 1)
    assert [r for r in rows if r["team"] == "MIA"][0]["streak"] == -2
    assert ls.parse_espn({}) == []


def test_from_feed_keeps_our_grouping_and_our_order():
    """The feed supplies NUMBERS. Divisions come from our own table and the
    sort from our own key, so one envelope moving cannot reorganize the
    league or make the page disagree with itself."""
    from engine.sources import leaguestandings as ls
    t = standings.from_feed("mlb", ls.parse_mlb(MLB_FEED), 2026)
    assert t["source"] == "league"
    grp = [g for g in t["groups"] if g["teams"]][0]
    assert grp["conference"] == "AL" and grp["division"] == "East"
    assert [r["team"] for r in grp["teams"]] == ["NYY", "BOS"], "our sort"
    nyy = grp["teams"][0]
    assert nyy["record"] == "79-62" and nyy["streak_label"] == "W1"
    assert nyy["diff"] == 56
    # Baseball rows can never carry a tie, whatever a feed sends.
    assert all(r["ties"] == 0 for r in grp["teams"])


def test_the_build_falls_back_loudly_when_the_feed_is_down():
    """A fallback that looks official is the whole defect. The payload must
    carry the reason, and the page must have something to print."""
    import standings_build
    from unittest import mock
    with mock.patch.object(standings_build, "_live_table",
                           lambda *a, **k: (None, "HTTPError: 403")):
        blob = standings_build.build("mlb", season=2026, today="2026-08-12")
    assert blob["source"] == "computed"
    assert blob["feed_error"] == "HTTPError: 403"


def test_the_page_reports_which_source_it_is_showing():
    app = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("async function renderStandings()")
    fn = app[i:app.index("\nasync function ", i + 10)]
    assert 'd.source === "league"' in fn
    # Typographic apostrophe — the house rule for visible copy.
    assert "the league\u2019s own records" in fn
    assert "fallbackBanner" in fn, "a fallback table must not look official"


def test_last_ten_is_the_leagues_number_or_a_dash_never_a_zero():
    """An empty ordered run rendered as "0-0", which reads as a measured
    10-game record of nothing. Neither feed publishes the run, so: the
    league's own last-ten where it sends one, a dash where it does not."""
    from engine.sources import leaguestandings as ls
    feed = {"records": [{"teamRecords": [
        {"team": {"id": 147}, "wins": 79, "losses": 62,
         "records": {"splitRecords": [
             {"type": "lastTen", "wins": 6, "losses": 4}]}},
        {"team": {"id": 111}, "wins": 72, "losses": 68, "records": {}},
    ]}]}
    rows = ls.parse_mlb(feed)
    assert [r["last10"] for r in rows] == ["6-4", ""]
    t = standings.from_feed("mlb", rows, 2026)
    by = {r["team"]: r for g in t["groups"] for r in g["teams"]}
    assert by["NYY"]["last10_label"] == "6-4"
    assert by["BOS"]["last10_label"] == "\u2014", "no fabricated 0-0"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
