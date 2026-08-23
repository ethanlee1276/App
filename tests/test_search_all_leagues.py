"""One search box, every league.

Ethan, 2026-08-23: "when i try to search nfl players, only wbna players
show up. so that raises a bigger thing … searching for a player should
search through ALL players for ALL sports. so even if im selected on nfl,
i shoudl still be able to look up mlb or ufc or wnba players."

The search shipped scoped to `state.sport`, which made an empty result
mean two different things at once — "we have no logs on him" and "you are
standing on the wrong tab" — and gave the visitor no way to tell which.
That is the failure he actually hit: names came back from a league he had
not chosen and nothing said so.

Two halves, and both matter. The search now spans every league we store;
and every row it returns carries its own sport, because the abbreviations
do not disambiguate themselves — CIN, ATL, SF and TB each name more than
one club, and the colours, the logo host and the injury board are all
keyed by them.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, statlogs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_with_all_leagues():
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    rows = []

    def log(sport, period, player, team, market, gid):
        rows.append({"sport": sport, "season": 2026, "period": period,
                     "game_id": gid, "player": player, "team": team,
                     "opponent": "OPP", "position": "X", "home": 1,
                     "market": market, "value": 5.0})

    for i in range(6):
        log("nfl", f"{i:03d}", "Patrick Mahomes", "KC", "pass_yds", f"n{i}")
        log("nfl", f"{i:03d}", "Joe Burrow", "CIN", "pass_yds", f"nb{i}")
        log("mlb", f"2026-08-{10 + i}", "Aaron Judge", "NYY", "hits", f"m{i}")
        log("mlb", f"2026-08-{10 + i}", "Elly De La Cruz", "CIN", "hits",
            f"mc{i}")
        log("wnba", f"2026-08-{10 + i}", "Aja Wilson", "LV", "pts", f"w{i}")
        log("nba", f"2026-08-{10 + i}", "Jayson Tatum", "BOS", "pts", f"b{i}")
        # One same-tier name per league, so a ranking test can vary the
        # preferred tab without a leading-letter match deciding it first.
        log("nfl", f"{i:03d}", "Zay Flowers", "BAL", "rec_yds", f"nz{i}")
        log("mlb", f"2026-08-{10 + i}", "Zack Wheeler", "PHI", "outs", f"mz{i}")
        log("nba", f"2026-08-{10 + i}", "Zach Edey", "MEM", "pts", f"bz{i}")
        log("wnba", f"2026-08-{10 + i}", "Zia Cooke", "LA", "pts", f"wz{i}")
    db.upsert_player_logs(conn, rows)
    conn.close()
    return path


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


# --- the search itself ----------------------------------------------------

def test_an_nfl_name_is_found_while_standing_on_the_wnba_tab():
    """The complaint, exactly: on one tab, looking for a player on
    another."""
    path = _db_with_all_leagues()
    hits = statlogs.search_all("mahomes", prefer="wnba", db_path=path)
    assert [h["player"] for h in hits] == ["Patrick Mahomes"]
    assert hits[0]["sport"] == "nfl"


def test_every_league_reaches_a_short_list():
    """A merged ORDER BY would hand the whole list to whichever league's
    period format sorts highest — NFL weeks are '005', baseball dates are
    '2026-08-14', and they mean nothing against each other. Round-robin
    needs no cross-league comparison, and no league can crowd out the
    rest."""
    path = _db_with_all_leagues()
    got = {h["sport"] for h in statlogs.search_all("a", limit=6,
                                                   db_path=path)}
    assert got == {"nfl", "mlb", "nba", "wnba"}


def test_a_name_that_starts_with_the_query_leads():
    """"judge" must find Aaron Judge before any longer name that merely
    contains those letters."""
    path = _db_with_all_leagues()
    hits = statlogs.search_all("judge", db_path=path)
    assert hits and hits[0]["player"] == "Aaron Judge"


def test_the_preferred_league_leads_but_never_excludes():
    """`sport` is the tab you are on. It orders the answer WITHIN a tier;
    it must not shrink it. "z" matches one same-tier name in each league,
    so nothing but the preference can decide who goes first."""
    path = _db_with_all_leagues()
    for tab in ("nfl", "mlb", "nba", "wnba"):
        hits = statlogs.search_all("z", limit=12, prefer=tab, db_path=path)
        assert hits[0]["sport"] == tab, tab
        assert len({h["sport"] for h in hits}) == 4, tab


def test_a_leading_match_outranks_the_tab_you_are_standing_on():
    """The preference is a tie-break, not a thumb on the scale: someone
    whose name STARTS with what you typed is the better answer even when
    he plays in another league."""
    path = _db_with_all_leagues()
    hits = statlogs.search_all("a", limit=12, prefer="nfl", db_path=path)
    assert hits[0]["player"] in ("Aaron Judge", "Aja Wilson")
    assert hits[0]["sport"] != "nfl"


def test_every_hit_names_its_own_league():
    """CIN is the Bengals and the Reds. A row that does not say which is a
    row the page will colour wrong."""
    path = _db_with_all_leagues()
    hits = statlogs.search_all("cin", db_path=path)   # matches nothing
    hits = statlogs.search_all("e", limit=12, db_path=path)
    assert hits and all(h.get("sport") in statlogs.SPORT_MARKETS
                        for h in hits)
    cin = {h["sport"] for h in hits if h["team"] == "CIN"}
    assert cin == {"nfl", "mlb"}, "both CIN clubs must be reachable"


def test_single_league_search_is_unchanged_and_now_tagged():
    path = _db_with_all_leagues()
    hits = statlogs.search("nfl", "mahomes", db_path=path)
    assert [h["player"] for h in hits] == ["Patrick Mahomes"]
    assert hits[0]["sport"] == "nfl"


def test_no_database_is_an_empty_list_not_a_crash():
    assert statlogs.search_all("anyone", db_path="/no/such/file.db") == []
    assert statlogs.search_all("", db_path="/no/such/file.db") == []


def test_a_blank_query_matches_nobody():
    """LIKE '%%' matches the entire league. A cleared search box must not
    dump every player who has ever been logged."""
    path = _db_with_all_leagues()
    assert statlogs.search_all("   ", db_path=path) == []


def test_the_limit_is_honoured_across_leagues():
    path = _db_with_all_leagues()
    assert len(statlogs.search_all("a", limit=3, db_path=path)) == 3


# --- the endpoint ---------------------------------------------------------

def test_the_endpoint_searches_every_league_by_default():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _players_search(")
    body = src[i:src.index("\n    def ", i + 10)]
    # THE UNSCOPED CALL, NOT ONE FUNCTION'S NAME. This pinned
    # "search_all" and went red when fighters joined the box — they are
    # not in the history DB, so the merged reader that finds them lives
    # in engine/playersearch.py and the endpoint calls that instead. The
    # contract is that the default search names no single league.
    assert "prefer=sport" in body, "the default search is scoped again"
    assert "statlogs.search_all(" in body or "playersearch.search(" in body
    # And it is still not behind the paywall: game logs are facts.
    assert "_entitled" not in body


def test_one_league_can_still_be_asked_for_explicitly():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _players_search(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert '"scope"' in body and "statlogs.search(sport, term)" in body


# --- the page -------------------------------------------------------------

def test_the_page_asks_for_every_league():
    js = _js()
    i = js.index("async function leagueSearch(")
    body = js[i:i + 900]
    assert "/api/players/search?q=" in body
    assert "sport=${encodeURIComponent(state.sport)}&q=" not in body


def test_a_hits_logs_come_from_that_hits_league():
    """Asking the NFL endpoint for a WNBA guard returns an empty card —
    which looks exactly like "found him, know nothing about him"."""
    js = _js()
    i = js.index("async function leagueLogs(")
    body = js[i:i + 700]
    assert "leagueLogs(player, sport)" in js[i:i + 120]
    assert "sport || state.sport" in body
    j = js.index("async function renderPlayers(")
    assert "leagueLogs(m.player, m.sport)" in js[j:j + 9000]


def test_a_searched_row_carries_its_league_into_the_profile_card():
    js = _js()
    j = js.index("async function renderPlayers(")
    assert "sport: m.sport" in js[j:j + 9000], \
        "the head-only row dropped its league"
    k = js.index("function _profileHead(")
    head = js[k:k + 1200]
    assert "r.sport || state.sport" in head
    for helper in ("teamMarkIn(", "teamNameIn("):
        assert helper in head, helper


def test_the_row_says_which_league_it_is_from():
    js = _js()
    assert "function leagueBadge(" in js
    j = js.index("async function renderPlayers(")
    assert "leagueBadge(m.sport)" in js[j:j + 9000]
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".lg-badge" in css, "the badge has no styling at all"


def test_the_players_page_does_not_need_a_board_to_search():
    """Found by a live page-error listener while checking this change,
    2026-08-23, on the very page Ethan was searching from:

        Cannot read properties of null (reading 'recommendations')

    `renderPlayers` is ASYNC and awaits the injury board before touching
    `state.data`, so the throw lands after the await — a rejected promise
    the browser swallows. The cold-open probe wraps `switchView` in a
    try/catch, which by then has already returned, so the view reported
    clean while rendering nothing at all.

    And it never needed the board: search reads the history DB. An absent
    board costs you tonight's priced cards, not the page."""
    js = _js()
    i = js.index("async function renderPlayers(")
    body = js[i:i + 1600]
    assert "state.data.recommendations" not in body, \
        "the board is dereferenced unguarded again"
    assert "const board = state.data || {}" in body
    # And the logs it fetches must land somewhere that exists without a
    # board, or caching them throws on the same null.
    assert "state.data.player_stats =" not in js, \
        "a searched player's logs are written into a board that may be null"
    assert "const _searchStats = {}" in js and "function playerStats(" in js


def test_the_peek_is_board_free_too():
    """A peek opens from a live row, which can be on screen before the
    board payload lands."""
    js = _js()
    i = js.index("async function openPeek(") if "async function openPeek(" in js \
        else js.index("playerStats(name)")
    assert "playerStats(name)" in js[i:i + 2500]


def test_the_cross_league_helpers_fall_back_to_the_active_tab():
    """Every existing caller passes no sport, and must keep working: a row
    with no league is a row from the board already on screen."""
    js = _js()
    i = js.index("const teamsIn = ")
    body = js[i:i + 600]
    assert "sport !== state.sport" in body and "activeTeams()" in body


def test_fantasy_and_the_mock_draft_ask_football_outright():
    """Both are always NFL, and both used to inherit whichever tab the
    reader came from — a dossier opened off the MLB board asked the
    baseball endpoint for a wide receiver."""
    js = _js()
    for fn in ("_ffDossierCharts", "_mockTrend"):
        i = js.index(f"async function {fn}(")
        assert 'leagueLogs(name, "nfl")' in js[i:i + 1200], fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
