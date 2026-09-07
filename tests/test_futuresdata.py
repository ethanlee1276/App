"""Assembling what the season simulator plays with.

Two things decide whether a futures board is honest, and both live here
rather than in the simulator.

**Which games are still to come.** A fixture list that includes postponed
games hands every team phantom wins; one that includes finished games plays
them twice. Each league says "not played yet" in its own way and each
adapter is tested against a payload shaped like the real one.

**How much of the rating is last year's.** In August three of these four
leagues have played nothing, so every number is a prior. The blend has to
report that rather than present it as a projection.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine import futuresdata as FD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hist(seasons=((2025, 40), (2026, 20))):
    import random
    from engine.divisions import MLB
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    teams, rng = list(MLB), random.Random(5)
    for season, n in seasons:
        for i in range(n):
            for j in range(0, len(teams) - 1, 2):
                h, a = teams[j], teams[j + 1]
                hs, as_ = rng.randint(0, 9), rng.randint(0, 9)
                if hs == as_:
                    hs += 1
                c.execute(
                    "INSERT OR REPLACE INTO games (sport,season,period,game_id,"
                    "home,away,home_score,away_score) VALUES ('mlb',?,?,?,?,?,?,?)",
                    (season, f"{season}-06-{i % 28 + 1:02d}",
                     f"{h}@{a}-{i}", h, a, hs, as_))
    c.commit()
    return c


# --- the ratings blend ------------------------------------------------------
def test_a_season_with_no_games_is_entirely_prior():
    """August, for the NFL, CFB and the NBA. The arithmetic is real and the
    inputs are last year's, and a board that does not say so is presenting a
    prior as a projection."""
    c = _hist()
    _, prior, played = FD.blended_ratings(c, "mlb", 2027)
    assert played == 0 and prior == 1.0


def test_the_prior_recedes_as_the_season_is_played():
    c = _hist(seasons=((2025, 40), (2026, 2)))
    _, thin, _ = FD.blended_ratings(c, "mlb", 2026)
    c2 = _hist(seasons=((2025, 40), (2026, 60)))
    _, thick, _ = FD.blended_ratings(c2, "mlb", 2026)
    assert thick < thin
    assert 0.0 < thick < 0.5


def test_last_seasons_rating_is_decayed_before_it_is_trusted():
    """A team is not the team it was last year. Leaning on a stale number at
    full strength is how a preseason board ends up confidently wrong about a
    club that lost half its starters."""
    assert 0.5 <= FD.PRIOR_DECAY < 1.0
    c = _hist(seasons=((2025, 40),))
    blended, prior, _ = FD.blended_ratings(c, "mlb", 2026)
    from engine.teamrates import compute_team_ratings
    raw = compute_team_ratings(c, "mlb", seasons=[2025])
    assert prior == 1.0
    team = max(raw, key=lambda t: abs(raw[t].net))
    # Margin rather than a bare comparison (see test_sidebias.py).
    # Measured: 0.91 against 1.22 — the tightest of these, and still
    # a third clear.
    assert abs(blended[team]) < abs(raw[team].net) * 0.9


def test_a_game_means_a_different_amount_in_each_league():
    """Twelve NFL games is most of a season; twelve MLB games is a
    fortnight. One constant for both would have the NFL still mostly last
    year at Thanksgiving."""
    assert FD.PRIOR_GAMES["nfl"] < FD.PRIOR_GAMES["mlb"]
    assert FD.PRIOR_GAMES["nba"] < FD.PRIOR_GAMES["mlb"]


# --- remaining fixtures, per league ----------------------------------------
def test_mlb_skips_finals_and_postponements():
    """A postponed game will never be played, so it is not remaining —
    counting it hands both teams a phantom game and inflates their
    projected wins."""
    from engine.mlb.sources import mlbstats
    payload = {"dates": [{"games": [
        {"status": {"abstractGameState": "Final", "codedGameState": "F"},
         "teams": {"home": {"team": {"abbreviation": "NYM"}},
                   "away": {"team": {"abbreviation": "ATL"}}}},
        {"status": {"abstractGameState": "Preview", "codedGameState": "D"},
         "teams": {"home": {"team": {"abbreviation": "NYM"}},
                   "away": {"team": {"abbreviation": "PHI"}}}},
        {"status": {"abstractGameState": "Preview", "codedGameState": "S"},
         "teams": {"home": {"team": {"abbreviation": "LAD"}},
                   "away": {"team": {"abbreviation": "SD"}}}},
    ]}]}
    orig = mlbstats.fetch_schedule
    mlbstats.fetch_schedule = lambda *a, **k: payload
    try:
        fx = FD._mlb_fixtures(2026)
    finally:
        mlbstats.fetch_schedule = orig
    assert [(f.home, f.away) for f in fx] == [("LAD", "SD")]


def test_nba_skips_finished_games():
    from engine.sources import nbadata
    sched = {"leagueSchedule": {"gameDates": [{"games": [
        {"gameStatus": 3, "homeTeam": {"teamTricode": "BOS"},
         "awayTeam": {"teamTricode": "NYK"}},
        {"gameStatus": 1, "homeTeam": {"teamTricode": "LAL"},
         "awayTeam": {"teamTricode": "GSW"}},
    ]}]}}
    orig = nbadata.fetch_schedule
    nbadata.fetch_schedule = lambda *a, **k: sched
    try:
        fx = FD._nba_fixtures(2026)
    finally:
        nbadata.fetch_schedule = orig
    assert [(f.home, f.away) for f in fx] == [("LAL", "GSW")]


def test_nfl_takes_the_regular_season_only_and_only_unplayed():
    """A preseason friendly counts toward nobody's division, and a played
    week must not be simulated on top of the record it already produced."""
    from engine.sources import nflverse
    rows = [
        {"season": "2026", "game_type": "REG", "home_team": "GB",
         "away_team": "CHI", "home_score": "27"},          # played
        {"season": "2026", "game_type": "PRE", "home_team": "KC",
         "away_team": "DEN", "home_score": ""},            # preseason
        {"season": "2025", "game_type": "REG", "home_team": "SF",
         "away_team": "SEA", "home_score": ""},            # wrong season
        {"season": "2026", "game_type": "REG", "home_team": "BUF",
         "away_team": "MIA", "home_score": ""},            # the one
    ]
    orig = nflverse.load_schedules
    nflverse.load_schedules = lambda *a, **k: rows
    try:
        fx = FD._nfl_fixtures(2026)
    finally:
        nflverse.load_schedules = orig
    assert [(f.home, f.away) for f in fx] == [("BUF", "MIA")]


def test_every_league_has_an_adapter():
    assert set(FD.FIXTURES) == {"mlb", "nba", "nfl", "cfb"}


# --- never take the sport down ---------------------------------------------
def test_a_dead_schedule_feed_does_not_raise():
    """A futures board is an extra on every page it appears on. A feed that
    is down must produce "no projection", not a broken sport."""
    c = _hist()
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        out = FD.build(c, "mlb", season=2026)
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["fixtures"] == []
    assert "unavailable" in out["note"]


def test_an_empty_fixture_list_says_which_kind_of_empty():
    c = _hist()
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: []
    try:
        out = FD.build(c, "mlb", season=2026)
    finally:
        FD.FIXTURES["mlb"] = orig
    assert "season is over" in out["note"] or "not published" in out["note"]


def test_a_preseason_build_says_it_is_a_prior_in_words():
    """The number alone does not communicate this. Somebody reading a
    division projection in August needs the sentence."""
    c = _hist(seasons=((2025, 40),))
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: [FD.Fixture("NYM", "ATL")]
    try:
        out = FD.build(c, "mlb", season=2026)
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["prior_share"] == 1.0
    assert "prior, not a projection" in out["note"]


# --- the one call a builder makes -------------------------------------------
def test_project_runs_the_season_and_carries_the_caveat_through():
    c = _hist(seasons=((2025, 40),))
    from engine.divisions import MLB
    teams = list(MLB)
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: [
        FD.Fixture(teams[i], teams[j])
        for i in range(len(teams)) for j in range(i + 1, len(teams))]
    try:
        out = FD.project(c, "mlb", season=2026, trials=200)
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["teams"], "the projection produced no teams"
    assert out["prior_share"] == 1.0
    assert out["fixtures_remaining"] > 0
    assert "prior" in out["note"]
    # The conservation law still holds through this path.
    assert abs(sum(t["p_title"] for t in out["teams"]) - 1.0) < len(out["teams"]) * 5e-5


def test_the_model_half_never_touches_the_meter():
    """Ratings, records and fixtures come from keyless sources — statsapi,
    the NBA's CDN, nflverse, ESPN — so the projection itself can be rebuilt
    as often as anyone likes for nothing.

    This test used to assert that oddsapi was not importable from this
    module at all. That was true until prices were added and is now wrong:
    the invariant is not "no odds", it is that ONLY title_prices reaches
    them, and that it cannot go to the wire unless asked.
    """
    src = open(os.path.join(ROOT, "engine", "futuresdata.py"),
               encoding="utf-8").read()
    for name in ("_mlb_fixtures", "_nba_fixtures", "_nfl_fixtures",
                 "_cfb_fixtures", "blended_ratings", "records",
                 "player_season_totals"):
        i = src.index(f"def {name}(")
        body = src[i:src.index("\ndef ", i + 1)]
        assert "oddsapi" not in body, f"{name} would put the model on the meter"
    # And the one function that does touch it is the one that says so.
    i = src.index("def title_prices(")
    assert "oddsapi" in src[i:src.index("\ndef ", i + 1)]
# --- player season totals from the logs we already have ---------------------
def _logs(c, rows, season=2026, market="home_runs"):
    for player, team, values in rows:
        for i, v in enumerate(values):
            c.execute(
                "INSERT OR REPLACE INTO player_game_logs (sport,season,period,"
                "game_id,player,team,opponent,position,home,market,value) "
                "VALUES ('mlb',?,?,?,?,?,'X','OF',1,?,?)",
                (season, f"{season}-06-{i % 28 + 1:02d}", f"g{i}", player,
                 team, market, float(v)))
    c.commit()


def test_a_players_rate_becomes_a_season_projection():
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    _logs(c, [("Slugger", "NYM", [1, 0, 1, 0, 1, 0, 1, 0, 1, 0])])
    out = FD.player_season_totals(c, "mlb", "home_runs", season=2026,
                                  team_games_left={"NYM": 50})
    assert out and out[0]["player"] == "Slugger"
    row = out[0]
    assert row["banked"] == 5 and row["games_played"] == 10
    assert row["mean"] > row["banked"], "the rest of the season adds nothing"


def test_a_hot_week_is_not_a_season_projection():
    """The most confident wrong number this module could produce. Three
    games at two a night projects a record no one has ever set."""
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    _logs(c, [("Hot Guy", "NYM", [2, 2, 2])])
    out = FD.player_season_totals(c, "mlb", "home_runs", season=2026,
                                  team_games_left={"NYM": 50})
    assert out == []
    assert FD.MIN_GAMES_FOR_RATE >= 5


def test_availability_comes_from_his_own_appearances():
    """A player who has already missed a third of the year is telling us
    something, and it is the only injury signal available without a feed."""
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    # The team has played 20 games; the everyday man played all of them,
    # the part-timer half.
    _logs(c, [("Everyday", "NYM", [1] * 20), ("Part Timer", "NYM", [1] * 10)])
    out = {r["player"]: r for r in FD.player_season_totals(
        c, "mlb", "home_runs", season=2026, team_games_left={"NYM": 40})}
    assert out["Everyday"]["availability"] == 1.0
    assert out["Part Timer"]["availability"] < 0.6
    # Same per-game rate, so the gap is availability and nothing else.
    assert out["Everyday"]["mean"] > out["Part Timer"]["mean"]


def test_a_line_attaches_a_probability_and_no_line_still_projects():
    """"48 home runs, give or take 6" is worth publishing with no market
    attached — that is the point of doing this from the schedule instead of
    from a price."""
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    _logs(c, [("Slugger", "NYM", [1, 0] * 10)])
    plain = FD.player_season_totals(c, "mlb", "home_runs", season=2026,
                                    team_games_left={"NYM": 50})[0]
    assert plain["line"] is None and plain["p_over"] == 0.0
    assert plain["mean"] > 0 and plain["sd"] > 0
    priced = FD.player_season_totals(c, "mlb", "home_runs", season=2026,
                                     team_games_left={"NYM": 50},
                                     lines={"Slugger": 30.5})[0]
    assert priced["line"] == 30.5 and 0 < priced["p_over"] < 1


def test_games_left_comes_from_the_same_fixture_list_the_season_plays():
    """Two halves of one board disagreeing about how much season is left is
    the kind of defect nobody sees until a number is obviously wrong."""
    fx = [FD.Fixture("NYM", "ATL"), FD.Fixture("ATL", "NYM"),
          FD.Fixture("NYM", "PHI")]
    assert FD.games_left_by_team(fx) == {"NYM": 3, "ATL": 2, "PHI": 1}


def test_a_team_with_no_games_left_projects_only_what_is_banked():
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    _logs(c, [("Done", "NYM", [1] * 12)])
    row = FD.player_season_totals(c, "mlb", "home_runs", season=2026,
                                  team_games_left={})[0]
    assert row["mean"] == row["banked"] == 12
    assert row["sd"] == 0.0
# --- the price side, and what it is allowed to cost -------------------------
def test_one_futures_pull_is_one_credit():
    """The entire reason this is safe to automate. _classify bills a board
    call at markets x regions, so a single market in a single region is one
    credit — four sports weekly is four credits a week against a plan of
    twenty thousand.

    Adding a second market or a second region doubles it; a per-event loop
    would multiply it by thirty. This test is the thing standing between
    "seventeen credits a month" and another burn.
    """
    from engine.sources import oddsapi
    src = open(os.path.join(ROOT, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()
    i = src.index("def fetch_outrights(")
    block = src[i:i + 1200]
    assert '"regions": "us"' in block, "one region"
    assert '"markets": "outrights"' in block, "one market"
    assert "," not in block.split('"markets": "')[1].split('"')[0]
    # And it is a BOARD call, so _classify prices it per market x region.
    assert "odds_board_futures_" in block
    kind, _, cost, _ = oddsapi._classify(
        "https://x/v4/sports/k/odds?markets=outrights&regions=us",
        "odds_board_futures_mlb.json")
    assert (kind, cost) == ("live_board", 1)


def test_a_week_is_the_cadence_and_the_cache_enforces_it():
    """Futures are the slowest market a book runs. Pulling one more often
    buys nothing and spends every time."""
    from engine.sources import oddsapi
    assert oddsapi.FUTURES_TTL == 7 * 86400


def test_a_build_cannot_spend_by_accident():
    """title_prices defaults to cache-only and project() defaults live_odds
    off. Something has to ASK to go to the wire — a board that silently
    spent every time it rebuilt is exactly the failure that burned 20,000
    credits."""
    src = open(os.path.join(ROOT, "engine", "futuresdata.py"),
               encoding="utf-8").read()
    assert "def title_prices(sport: str, cache_only: bool = True)" in src
    assert "live_odds: bool = False" in src
    i = src.index("if prices:")
    assert "cache_only=not live_odds" in src[i:i + 200]


def test_every_futures_sport_has_a_key():
    from engine.sources.oddsapi import FUTURES_KEYS
    assert set(FUTURES_KEYS) == {"nfl", "mlb", "nba", "cfb"}


def test_the_best_price_for_the_bettor_wins():
    from engine.sources.oddsapi import parse_outrights
    payload = [{"bookmakers": [
        {"title": "Shorty", "markets": [{"key": "outrights", "outcomes": [
            {"name": "New York Mets", "price": 500}]}]},
        {"title": "Longy", "markets": [{"key": "outrights", "outcomes": [
            {"name": "New York Mets", "price": 800}]}]},
    ]}]
    got = parse_outrights(payload, {"New York Mets": "NYM"})
    assert got["NYM"]["odds"] == 800 and got["NYM"]["book"] == "Longy"
    assert abs(got["NYM"]["implied"] - 1 / 9) < 1e-3


def test_a_runner_we_cannot_map_is_dropped_not_guessed():
    """A futures price attached to the wrong team's projection is worse than
    no price at all — it would show as an edge on a team nobody priced."""
    from engine.sources.oddsapi import parse_outrights
    payload = [{"bookmakers": [{"title": "B", "markets": [
        {"key": "outrights", "outcomes": [
            {"name": "New York Mets", "price": 500},
            {"name": "Some Relocated Club", "price": 2500}]}]}]}]
    got = parse_outrights(payload, {"New York Mets": "NYM"})
    assert set(got) == {"NYM"}


def test_a_renamed_team_still_matches_once_normalised():
    from engine.sources.oddsapi import parse_outrights
    payload = [{"bookmakers": [{"title": "B", "markets": [
        {"key": "outrights", "outcomes": [
            {"name": "st. louis cardinals", "price": 900}]}]}]}]
    got = parse_outrights(payload, {"St. Louis Cardinals": "STL"})
    assert got["STL"]["odds"] == 900


def test_no_prices_still_produces_a_board():
    """The model is the product; the price is a comparison bolted on. A
    futures board with no prices is still a futures board."""
    c = _hist(seasons=((2025, 40),))
    from engine.divisions import MLB
    teams = list(MLB)
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: [FD.Fixture(teams[0], teams[1])]
    orig_p = FD.title_prices
    FD.title_prices = lambda *a, **k: {}
    try:
        out = FD.project(c, "mlb", season=2026, trials=50)
    finally:
        FD.FIXTURES["mlb"] = orig
        FD.title_prices = orig_p
    assert out["teams"] and out["priced"] == 0
    assert "title_edge_pts" not in out["teams"][0]


def test_the_edge_is_the_model_minus_the_book():
    c = _hist(seasons=((2025, 40),))
    from engine.divisions import MLB
    teams = list(MLB)
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda _s: [FD.Fixture(teams[0], teams[1])]
    orig_p = FD.title_prices
    FD.title_prices = lambda *a, **k: {
        teams[0]: {"odds": 900, "book": "B", "implied": 0.10}}
    try:
        out = FD.project(c, "mlb", season=2026, trials=200)
    finally:
        FD.FIXTURES["mlb"] = orig
        FD.title_prices = orig_p
    row = {t["team"]: t for t in out["teams"]}[teams[0]]
    assert row["title_implied"] == 0.10
    assert abs(row["title_edge_pts"] - (row["p_title"] - 0.10) * 100) < 0.11



# --- the offseason rolls forward ---------------------------------------------
def test_the_offseason_board_rolls_forward_to_the_published_next_season():
    """season_of answers "which season does this date belong to" — and in
    August that is the NFL season that just ENDED, because the label has to
    key game logs consistently right up to kickoff. A futures board asks a
    different question: which season is there left to project? Answering it
    with the finished one produced an empty board reading "the season is
    over" while 272 published, unplayed 2026 fixtures sat in the games
    table — and left three of the four boards empty for the whole
    offseason, exactly when a futures market is most alive.

    Measured after the fix on the real NFL DB: 32 teams, 272 fixtures,
    season 2026, prior_share 1.0, and every conservation law holding —
    title probs 1.0000, conferences 2.0004, divisions 8.0001, playoff
    berths 14.0000, mean projected wins 8.51 on a 17-game season."""
    from engine.mlb.models import MLBGame  # noqa: F401 (import guard only)

    class _Fx:
        __slots__ = ("home", "away")

        def __init__(self, h, a):
            self.home, self.away = h, a

    c = _hist(seasons=((2025, 40),))       # 2025 complete, nothing in 2026
    calendar = FD.season_of("mlb", __import__("datetime").date.today().isoformat())
    orig = FD.FIXTURES["mlb"]
    # The calendar season has nothing left; the next one has a schedule.
    FD.FIXTURES["mlb"] = (lambda s: [] if s == calendar
                          else [_Fx("NYY", "BOS"), _Fx("LAD", "SF")])
    try:
        out = FD.build(c, "mlb")           # no season pinned — the live path
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["season"] == calendar + 1
    assert len(out["fixtures"]) == 2
    # A rolled-forward board is all prior, and it says so in words.
    assert out["prior_share"] == 1.0
    assert "prior, not a projection" in out["note"]


def test_an_explicitly_pinned_season_never_rolls_forward():
    """A caller who names a season means that season. Rolling a backtest of
    2024 forward to 2025 because 2024 is finished would answer a question
    nobody asked."""
    c = _hist(seasons=((2025, 40),))
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda s: []
    try:
        out = FD.build(c, "mlb", season=2025)
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["season"] == 2025
    assert out["fixtures"] == []
    assert "season is over" in out["note"] or "not published" in out["note"]


def test_a_wholly_unpublished_future_stays_an_honest_empty_board():
    """Both the calendar season and the next have nothing: the note stands,
    the board renders as "no projection", nothing invents a schedule."""
    c = _hist(seasons=((2025, 40),))
    orig = FD.FIXTURES["mlb"]
    FD.FIXTURES["mlb"] = lambda s: []
    try:
        out = FD.build(c, "mlb")
    finally:
        FD.FIXTURES["mlb"] = orig
    assert out["fixtures"] == []
    assert "season is over" in out["note"] or "not published" in out["note"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
