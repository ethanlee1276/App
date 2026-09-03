"""The college football board: its feed, its variance, and its one gate.

``test_cfb.py`` covers the decision layer — the attention dial, the grade,
the caps. This file covers everything that had to exist for that layer to
see a real Saturday, and the tests are aimed squarely at the ways this
particular sport lies to you.

**The weekday is the model's single biggest input and the easiest to get
wrong.** ESPN stamps kickoffs in UTC, so a Saturday 8pm ET game is Sunday
and a Wednesday MACtion game is Thursday. Read naively, prime-time
Saturday would be classed as a weeknight and handed the low-attention
haircut — the model would claim a soft number on the most-watched window
of the week and stake it. Two tests pin exactly those cases.

**Missing data must never read as soft data.** An unresolved conference,
an unrated team, an unfitted variance: each has an honest answer that
isn't "bet it".

**The conditional has to promise what confirming actually delivers.** §2.3
publishes a conditional instead of a bet; if the grade it advertises is
higher than the grade confirmation would produce, that conditional is an
advertisement rather than a promise.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, gamebets, teamrates
from engine.cfb import context as C
from engine.cfb import ratings as R
from engine.cfb import status as S
from engine.cfb.model import attention_tier
from engine.cfb.pipeline import evaluate_play
from engine.sources import cfbdata as D


def _event(gid="1", home="TOL", away="BGSU", hconf="15", aconf="15",
           hrank=None, arank=None, when="2026-10-11T02:30:00Z",
           hs=None, as_=None, done=False):
    return {
        "id": gid, "date": when, "shortName": f"{away} @ {home}",
        "season": {"year": 2026, "type": 2}, "week": {"number": 5},
        "competitions": [{
            "neutralSite": False, "conferenceCompetition": hconf == aconf,
            "venue": {"fullName": "Glass Bowl", "indoor": False},
            "status": {"type": {"state": "post" if done else "pre",
                                "completed": done}},
            "competitors": [
                {"homeAway": "home", "score": hs,
                 "curatedRank": {"current": hrank or 99},
                 "team": {"abbreviation": home, "displayName": f"{home} Rockets",
                          "conferenceId": hconf}},
                {"homeAway": "away", "score": as_,
                 "curatedRank": {"current": arank or 99},
                 "team": {"abbreviation": away, "displayName": f"{away} Falcons",
                          "conferenceId": aconf}}]}]}


# --- the weekday, in the time zone the sport is played in -------------------
def test_a_saturday_night_kickoff_is_not_a_sunday_game():
    """8pm ET Saturday is 00:00 UTC Sunday. Read as UTC, the biggest window
    of the week would be classed a weeknight and handed the soft-market
    haircut."""
    assert D.weekday_et("2026-10-11T00:00:00Z") == "Saturday"
    assert D.to_eastern("2026-10-11T00:00:00Z").date().isoformat() == "2026-10-10"


def test_mid_week_maction_is_not_a_thursday_game():
    # 7:30pm ET Wednesday = 00:30 UTC Thursday.
    assert D.weekday_et("2026-10-08T00:30:00Z") == "Wednesday"


def test_the_eastern_offset_follows_daylight_time():
    # November bowl-season games are on standard time; September is not.
    assert D.to_eastern("2026-09-05T23:00:00Z").hour == 19       # EDT, −4
    assert D.to_eastern("2026-12-05T23:00:00Z").hour == 18       # EST, −5


def test_an_unparseable_kickoff_does_not_invent_a_weekday():
    assert D.weekday_et("") == ""
    assert D.to_eastern("not a date") is None


# --- the feed ---------------------------------------------------------------
def test_the_scoreboard_carries_everything_the_tier_needs():
    g = D.parse_scoreboard({"events": [_event(hconf="8", aconf="8", hrank=3,
                                              arank=7,
                                              when="2026-10-11T00:00:00Z")]})[0]
    assert (g["home_conference"], g["away_conference"]) == ("SEC", "SEC")
    assert (g["home_rank"], g["away_rank"]) == (3, 7)
    assert g["weekday"] == "Saturday"
    assert attention_tier(g) == "marquee"


def test_unranked_is_none_not_ninety_nine():
    g = D.parse_scoreboard({"events": [_event()]})[0]
    assert g["home_rank"] is None and g["away_rank"] is None
    # 99 leaking through would make every team "ranked" and every game marquee.
    assert attention_tier(g) == "low"


def test_an_unresolvable_conference_is_empty_not_soft():
    g = D.parse_scoreboard({"events": [_event(hconf="999", aconf="998")]})[0]
    assert g["home_conference"] == "" and g["away_conference"] == ""
    # Saturday + unknown conferences must NOT be claimed as a soft market.
    g["weekday"] = "Saturday"
    assert attention_tier(g) == "standard"


def test_the_feed_never_claims_a_quarterback_it_has_not_seen():
    g = D.parse_scoreboard({"events": [_event()]})[0]
    assert g["qb_confirmed"] is False
    assert g["participation_verified"] is False


def test_only_finished_games_reach_the_ratings_table():
    payload = {"events": [_event("1", done=True, hs=31, as_=17),
                          _event("2", when="2026-10-11T02:30:00Z")]}
    rows = D.game_rows(D.parse_scoreboard(payload))
    assert [r["game_id"] for r in rows] == ["1"]
    assert rows[0]["sport"] == "cfb" and rows[0]["home_score"] == 31.0


def test_team_names_join_across_feeds():
    teams = D.parse_teams({"sports": [{"leagues": [{"teams": [
        {"team": {"id": "2", "abbreviation": "TAMU",
                  "displayName": "Texas A&M Aggies",
                  "shortDisplayName": "Texas A&M",
                  "color": "500000", "alternateColor": "FFFFFF"}}]}]}]})
    assert teams["TAMU"]["primary"] == "#500000"
    lookup = D.team_lookup(teams)
    # Every spelling a book might use has to land on the same team. The
    # ampersand collapses rather than becoming "and", so the two ways of
    # writing A&M agree.
    assert D.name_key("Texas A&M") == D.name_key("Texas A M")
    for spelling in ("Texas A&M Aggies", "Texas A&M", "  texas a&m  aggies "):
        assert D.resolve_team(spelling, lookup) == "TAMU"


def test_an_unknown_school_resolves_to_nothing_rather_than_the_wrong_one():
    lookup = {"toledo rockets": "TOL", "toledo": "TOL"}
    assert D.resolve_team("Toledo Rockets", lookup) == "TOL"
    assert D.resolve_team("Bowling Green Falcons", lookup) == ""


def test_a_book_nickname_still_finds_the_school():
    # ESPN's short name is "Miami (OH)"; a book quotes the nickname too.
    lookup = D.team_lookup({"M-OH": {"name": "Miami (OH) RedHawks",
                                     "nick": "Miami (OH)"}})
    assert D.resolve_team("Miami (OH) RedHawks", lookup) == "M-OH"
    assert D.resolve_team("Miami OH", lookup) == "M-OH"


def test_conferences_parse_from_either_shape_espn_returns():
    a = D.parse_conferences({"groups": [{"groupId": "8", "name": "SEC"}]})
    b = D.parse_conferences({"children": [{"id": "8",
                                           "name": "Southeastern Conference"}]})
    assert a == {"8": "SEC"} and b == {"8": "SEC"}


# --- the variance is measured, or it says it isn't --------------------------
def _seeded_db(n_games: int):
    conn = db.connect(":memory:")
    import random
    rng = random.Random(11)
    teams = [f"T{i}" for i in range(12)]
    rows = []
    for i in range(n_games):
        h, a = rng.sample(teams, 2)
        rows.append({"sport": "cfb", "season": 2026, "period": f"2026-09-{i%28+1:02d}",
                     "game_id": str(i), "home": h, "away": a,
                     "home_score": max(0, rng.gauss(31, 12)),
                     "away_score": max(0, rng.gauss(24, 12)), "extra": "{}"})
    db.upsert_games(conn, rows)
    return conn


def test_without_a_sample_the_numbers_are_a_prior_and_say_so():
    conn = _seeded_db(20)
    fit = R.fit_from_history(conn, {})
    assert fit.fitted is False
    assert fit.probation is True, "an unfitted board must not be staked"
    assert "20 CFB games" in fit.note and "400 needed" in fit.note


def test_with_a_sample_the_numbers_are_measurements():
    conn = _seeded_db(600)
    ratings = teamrates.compute_team_ratings(conn, "cfb", shrink=8.0)
    fit = R.fit_from_history(conn, ratings)
    assert fit.fitted is True and fit.probation is False
    assert fit.games == 600
    # Measured, not the prior it replaced.
    assert fit.margin_sd != R.PRIOR.margin_sd
    assert 5.0 < fit.margin_sd < 30.0
    assert 20.0 < fit.scoring_baseline < 40.0


def test_installing_the_fit_is_what_prices_the_game():
    fit = R.CFBRatings(scoring_baseline=30.0, home_field=3.0, margin_sd=17.0,
                       total_sd=16.0, team_total_sd=12.0, fitted=True,
                       games=500, note="")
    R.install(fit)
    try:
        assert gamebets.MARGIN_SD["cfb"] == 17.0
        assert gamebets.game_margin("cfb", 5.0, 1.0) == 7.0   # gap + home field
        assert gamebets.project_total("cfb", 3.0, 0.0, 1.0, 0.0) == 64.0
    finally:
        R.install(R.PRIOR)


def test_a_wider_margin_spread_makes_the_same_gap_less_certain():
    tight = R.win_prob(7.0, R.CFBRatings(28, 2, 10.0, 15, 11, True, 500, ""))
    loose = R.win_prob(7.0, R.CFBRatings(28, 2, 24.0, 15, 11, True, 500, ""))
    assert tight > loose > 0.5


# --- the quarterback gate ---------------------------------------------------
def test_a_confirmation_is_scoped_to_one_game_date(tmp_path=None):
    import tempfile
    from pathlib import Path
    store_path = Path(tempfile.mkdtemp()) / "qb.json"
    S.record("TOL", "2026-10-10", starter="Tucker Gleason", path=store_path)
    store = S.load_store(store_path)
    assert S.state_for("TOL", "2026-10-10", store)["state"] == S.CONFIRMED
    # Last week's answer cannot authorise this week's bet.
    assert S.state_for("TOL", "2026-10-17", store)["state"] == S.UNKNOWN


def test_both_sidelines_have_to_be_confirmed():
    game = {"home": "TOL", "away": "BGSU", "date": "2026-10-10"}
    half = {"TOL": {"2026-10-10": {"state": S.CONFIRMED}}}
    g = S.annotate_game(game, half)
    assert g["qb_confirmed"] is False
    assert "BGSU" in g["qb_uncertain_team"]
    both = {**half, "BGSU": {"2026-10-10": {"state": S.CONFIRMED}}}
    assert S.annotate_game(game, both)["qb_confirmed"] is True


def test_a_reported_backup_is_information_not_silence():
    game = {"home": "TOL", "away": "BGSU", "date": "2026-10-10"}
    store = {"TOL": {"2026-10-10": {"state": S.BACKUP}},
             "BGSU": {"2026-10-10": {"state": S.CONFIRMED}}}
    g = S.annotate_game(game, store)
    # Knowing the starter is OUT is knowledge — the game is priceable.
    assert g["qb_confirmed"] is True
    assert g["qb_downgrade"] == ["TOL"]


def test_september_is_not_penalised_for_a_bowl_season_risk():
    sept = {"kickoff": "2026-09-05T20:00:00Z"}
    dec = {"kickoff": "2026-12-30T20:00:00Z"}
    assert S.certainty(sept) > S.certainty(dec)
    assert S.certainty(dec, assume_confirmed=True) > S.certainty(dec)


def _play(game, p_model=0.60):
    return {"game": game, "market": "side", "selection": "TOL +6.5",
            "line": 6.5, "odds": -110, "opposing_odds": -110,
            "p_model": p_model, "book": "FanDuel",
            "information_certainty": S.certainty(game),
            "information_certainty_confirmed": S.certainty(
                game, assume_confirmed=True),
            "attention_fit": 1.0, "situational_fit": 0.6,
            "matchup_fit": 1.0, "environment_fit": 0.6}


def test_the_conditional_promises_exactly_what_confirming_delivers():
    """A conditional that advertises a grade confirmation can't produce is
    an advertisement, not a promise — and it is the number the human is
    deciding whether to go and check."""
    base = {"home": "TOL", "away": "BGSU", "game_id": "2", "date": "2026-10-10",
            "home_conference": "MAC", "away_conference": "Big Ten",   # a power side: G5-only games are not bet since 2026-09-02
            "weekday": "Wednesday", "kickoff": "2026-10-11T02:30:00Z",
            "spread": 6.5}
    CONF = {"state": S.CONFIRMED}
    held = evaluate_play(_play(S.annotate_game(base, {})))
    live = evaluate_play(_play(S.annotate_game(
        base, {"TOL": {"2026-10-10": CONF}, "BGSU": {"2026-10-10": CONF}})))
    assert held["kind"] == "hold" and held["grade_label"] == "Conditional"
    assert live["kind"] == "play"
    assert held["grade"] == live["grade"]
    # The conditional carries the number but never the stake.
    assert held.get("stake_fraction") is None
    assert held["stake_if_confirmed"] == live["stake_fraction"] > 0


def test_a_conditional_still_has_to_clear_the_bar():
    """Holding every thin number would bury the games worth a phone call."""
    base = {"home": "TOL", "away": "BGSU", "game_id": "2", "date": "2026-10-10",
            "home_conference": "MAC", "away_conference": "Big Ten",   # a power side: G5-only games are not bet since 2026-09-02
            "weekday": "Wednesday", "kickoff": "2026-10-11T02:30:00Z"}
    thin = evaluate_play(_play(S.annotate_game(base, {}), p_model=0.51))
    assert thin["kind"] == "pass"


# --- the context scores are facts, not vibes --------------------------------
def test_attention_fit_is_the_thesis_as_a_number():
    assert C.attention_fit("low") > C.attention_fit("standard") > C.attention_fit("marquee")


def test_matchup_fit_measures_how_much_we_actually_know():
    assert C.matchup_fit(0, 10) == 0.0, "one unrated side means no read"
    assert C.matchup_fit(8, 9) == 1.0
    assert 0 < C.matchup_fit(4, 9) < 1


def test_an_unchecked_sky_costs_a_total_more_than_a_side():
    outdoor = {"indoor": False}
    assert C.environment_fit(outdoor, "total") < C.environment_fit(outdoor, "side")
    assert C.environment_fit({"indoor": True}, "total") == 1.0


def test_the_schedule_proves_the_situational_spots():
    game = {"home": "TOL", "away": "BGSU", "date": "2026-10-10",
            "conference_game": True, "week": 5}
    prev = {"TOL": {"home": "OSU", "away": "TOL", "home_rank": 2,
                    "date": "2026-10-04"}}
    nxt = {"BGSU": {"home": "BGSU", "away": "ND", "away_rank": 8,
                    "date": "2026-10-17"}}
    tags = C.situational_tags(game, prev, nxt)
    assert "letdown" in tags        # TOL just played a ranked team
    assert "lookahead" in tags      # BGSU plays one next
    assert "short_week" in tags     # six days
    assert C.situational_fit(tags) > C.situational_fit([])


def test_a_neutral_week_is_neutral_not_perfect():
    # Scoring an ordinary game as a perfect spot would hand ten free grade
    # points to every play on a 60-game board.
    assert C.situational_fit([]) < 1.0


def test_neighbours_keep_the_closest_game_on_each_side():
    before = [{"home": "A", "away": "B", "date": "2026-09-20"},
              {"home": "A", "away": "C", "date": "2026-10-04"}]
    after = [{"home": "A", "away": "D", "date": "2026-10-17"},
             {"home": "A", "away": "E", "date": "2026-10-31"}]
    prev, nxt = C.neighbours(before, after)
    assert prev["A"]["date"] == "2026-10-04"
    assert nxt["A"]["date"] == "2026-10-17"


# --- plumbing ---------------------------------------------------------------
def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_odds_adapter_knows_the_league():
    from engine.sources.oddsapi import SPORT_CONFIG
    assert SPORT_CONFIG["cfb"]["sport_key"] == "americanfootball_ncaaf"
    # 134 schools must not be a checked-in table.
    assert SPORT_CONFIG["cfb"]["teams"] == {}


def test_the_whole_board_is_priced_in_one_request():
    """Per-event pricing of the GAME markets would cost ~60 credits a
    Saturday, which the budget pacer would never authorise — so the game
    board stays one bulk call. The TD long-shot pull (2026-08-25) is the
    priced-in exception: player markets are only served per event, so it
    pays a credit a game and is CAPPED at TD_EVENT_CAP of the best
    games. The authorization estimate covers both — the bulk call plus
    the worst-case cap — so light days cost less than authorized, never
    more."""
    src = _read("engine", "sources", "oddsapi.py")
    assert "def fetch_sport_odds(" in src
    assert 'f"{ODDS_BASE}/sports/{cfg[\'sport_key\']}/odds"' in src
    launch = _read("launch.py")
    assert "CFB_ODDS_COST = 15" in launch
    assert "cost=CFB_ODDS_COST" in launch
    build = _read("cfb_build.py")
    assert "TD_EVENT_CAP = 12" in build
    assert "cands[:TD_EVENT_CAP]" in build, \
        "the TD pull lost its cap — an uncapped Saturday is 60 credits"


def test_the_server_serves_the_league():
    from server import LIVE_FILES
    assert LIVE_FILES["cfb"].name == "cfb.json"
    src = _read("server.py")
    assert "/api/cfb/recommendations" in src
    assert '("nba", "wnba", "cfb")' in src


def test_the_page_is_wired_end_to_end():
    html = _read("web", "index.html")
    assert 'data-sport="cfb"' in html
    app = _read("web", "js", "app.js")
    assert '"/api/cfb/recommendations"' in app
    # Identity ships in the payload, not a 134-team file.
    assert "teamsForSport" in app and "state.data && state.data.teams" in app
    assert "window.ACTIVE_TEAMS = teamsForSport(state.sport);" in app


def test_no_cfb_page_is_hidden_any_more():
    """"players" LEFT THIS LIST on 2026-08-24 (ESPN box scores feed CFB
    player_game_logs), "longshots" left on 2026-08-25 (engine/cfb/tds
    prices anytime-TD quotes off usage shares, the script, the
    opponent's scoring and kickoff weather), and TRENDING LEFT ON
    2026-09-03 — the last one, and the last thing the old reason
    covered. It ranks movers off the board's per-player PROJECTIONS,
    which college genuinely did not build until `engine/cfb/props.py`
    turned the ingested logs into props and `pipeline.price_props`
    projected them through the same chain the NFL's run through.

    The list is now EMPTY for college, which is the claim worth pinning:
    every page has an engine behind it, so the sidebar needs no college
    branch at all. Checked on CFB's own line rather than anywhere in the
    block, which is what let the first version of this pass on other
    sports' entries."""
    app = _read("web", "js", "app.js")
    assert "HIDDEN_VIEWS" in app
    block = app[app.index("const HIDDEN_VIEWS"):]
    block = block[:block.index("};")]
    cfb = block[block.index("cfb:"):]
    cfb = cfb[:cfb.index("]")]
    for view in ("players", "rosters", "longshots", "trending", "weather"):
        assert f'"{view}"' not in cfb, \
            f"{view} is hidden again — its CFB engine shipped"


def test_the_game_card_does_not_print_nan_degrees():
    """College weather is PULLED since 2026-08-24 (CFBD venue coordinates
    + Open-Meteo at the kickoff hour) — but only for games the venue
    join could answer. The claim this test has always made survives as
    the FALLBACK: a game WITHOUT a reading says so in words, never
    'NaN°F · NaNmph'. A game with one reads like the NFL's."""
    app = _read("web", "js", "app.js")
    # The college-only branch became the shared rule on 2026-08-26, when
    # the NFL's weather turned out to be a prior rather than a forecast.
    # Same three claims, read off the one guard.
    i = app.index("const wxKnown =")
    seg = app[i:i + 480]
    assert '"Outdoor · weather not pulled"' in seg,         "the unstamped-game fallback is gone — NaN degrees are back"
    assert "Math.round(w.temp_f)" in seg,         "a stamped college game hides its reading"
    assert seg.index("g.weather") < seg.index("g.indoor"),         "the reading is checked after the indoor guess instead of first"


def test_a_conditional_never_wears_a_stake_chip():
    app = _read("web", "js", "app.js")
    assert "r._ok && r.stake_units > 0" in app
    assert "stake_if_confirmed_units" in app
    # Amber, never green.
    assert '"Conditional": "lean"' in app


def test_a_conditional_is_not_counted_as_a_recommended_bet():
    """It clears every filter on the numbers — that's the point of
    publishing it — so without this the page said '11 game bets, all
    journaled' about a board where five were journaled."""
    app = _read("web", "js", "app.js")
    fn = app[app.index("function passesGameBet"):]
    fn = fn[:fn.index("\n}\n")]
    assert "!r.conditional" in fn


def test_a_conditional_is_still_visible_without_show_all():
    """A bet you cannot see is not one you can go and confirm."""
    app = _read("web", "js", "app.js")
    assert "state.showAll ? true : r._ok || r.conditional" in app


def test_a_withholding_reason_does_not_wear_a_green_check():
    app = _read("web", "js", "app.js")
    block = app[app.index("const NEG_REASON"):]
    block = block[:block.index('"i");')]
    for phrase in ("unconfirmed", "unverified", "CONDITIONAL"):
        assert phrase in block


def test_the_stats_tiles_count_college_props_like_every_other_sport():
    """THE PREMISE THIS TEST WAS WRITTEN UNDER IS GONE. It pinned a
    `cfb ? "Markets priced" : "Props analyzed"` branch, correctly, for
    as long as college had no player model: "18 props analyzed" on a
    board with no props is just wrong.

    College has props now (`engine/cfb/props.py`), and the branch would
    have gone on hiding them — the tile that exists to say how many
    players were considered would have kept saying how many GAMES were.
    So the branch is gone and both numbers are published under their own
    names instead: `props_built` / `props_analyzed` the way every other
    board names them, and `markets_priced` for the game markets the
    college engine prices."""
    app = _read("web", "js", "app.js")
    assert '"Markets priced"' not in app, \
        "the college tile is branching on sport again"
    assert '{ k: "Props analyzed", to: d.counts.props_analyzed' in app
    build = _read("cfb_build.py")
    assert '"props_built": len(_built)' in build
    assert '"markets_priced": len(plays)' in build


def test_every_league_with_a_board_is_deep_linkable():
    """?sport=wnba silently fell back to NFL once because this list was a
    duplicate of SPORT_META that someone forgot to extend."""
    app = _read("web", "js", "app.js")
    allow = app[app.index('sport: (['):]
    allow = set(__import__("re").findall(r'"(\w+)"', allow[:allow.index("]")]))
    meta = app[app.index("const SPORT_META = {"):]
    meta = meta[:meta.index("\n};")]
    leagues = set(__import__("re").findall(r"^  (\w+): \{", meta, __import__("re").M))
    # NFL is the default, so it needs no query-param entry.
    assert leagues - allow == {"nfl"}, f"not deep-linkable: {leagues - allow - {'nfl'}}"


def test_the_phone_menu_keeps_its_height_when_a_sport_hides_pages():
    """The failure this pinned: CFB hides pages it has no engine for, and
    the old slide-down menu got 52px shorter the instant you tapped CFB —
    sliding buttons up under a finger already on its way down. The NEW
    LOOK drawer (2026-08-11) is anchored top:64px/bottom:0, so its height
    is the viewport's and CANNOT change with the sport's page list."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(root, "web", "css", "styles.css"), encoding="utf-8").read()
    i = css.index(".sidebar { position: fixed;")
    block = css[i:i + 300]
    # `top` moved from a bare 64px to var(--topbar-h) when the bar learned
    # to grow by the notch inset on an installed iPhone. What this test
    # cares about is unchanged and is the pair: anchored to BOTH edges, so
    # the height is the viewport's and cannot follow the content.
    assert ("top: var(--topbar-h)" in block or "top: 64px" in block), \
        "the drawer is no longer anchored to the bottom of the bar"
    assert "bottom: 0" in block, \
        "the drawer's height follows content again — sport switches will resize it"

def test_the_launcher_refreshes_the_board():
    launch = _read("launch.py")
    assert "def refresh_cfb(" in launch
    assert "refresh_cfb(quiet=quiet)" in launch, "defined but never called"
    assert "def confirm_qb_cli(" in launch
    assert '"--confirm-qb" in argv' in launch


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
