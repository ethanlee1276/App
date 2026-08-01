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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
