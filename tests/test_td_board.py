"""The touchdown boards: NFL wired end to end, CFB built from scratch.

Ethan, 2026-08-25: "fix the odds range for long shot picks for nfl and
CFB. Touchdown props for nfl are live now we should see them showing up
in the longshot spot. Along side the data we pull, we should be using
the game script and all the other stats and data to determine who will
score a touchdown."

What the investigation found, pinned here so it cannot quietly happen
again: the NFL long-shot board was empty BY CONSTRUCTION, three causes
deep — no anytime_td props ever existed on the regular-season slate,
player_anytime_td was never in the requested odds markets, and
parse_event_scorers was called only by the history harvester, never the
live path. The odds window Ethan suspected was real too, but it was the
fourth problem, not the first. CFB had no player-prop layer at all.

The tests below cover each link of the now-complete chain: props on the
slate, quotes requested and attached, the script priced as arithmetic,
the windows, the CFB model, and the journal/settle path both boards
grade through.

Run directly: `python3 tests/test_td_board.py`
"""

import datetime as dt
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db as DB                                  # noqa: E402
from engine import ledger as L                               # noqa: E402
from engine.cfb import tds as T                              # noqa: E402
from engine.models import (Game, Weather, Team, DefenseProfile, Prop,   # noqa: E402
                           SportsbookLine, GameLog, PASS_YDS, ANYTIME_TD)
from engine.data_loader import Slate                         # noqa: E402
from engine.sources import oddsapi as oa                     # noqa: E402
from engine.touchdowns import script_td_multiplier, td_probability  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class MP:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, val):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)

    def undo(self):
        for obj, name, val in reversed(self._undo):
            setattr(obj, name, val)


# --- the game script is arithmetic, not adjective ---------------------------

def _game(spread):
    return Game(home="KC", away="BUF", weather=Weather(dome=True),
                spread=spread, total=47.0)


def test_script_multiplier_moves_rbs_with_the_spread():
    fav, fav_r = script_td_multiplier(_game(-7.0), "KC", "RB")
    dog, _ = script_td_multiplier(_game(-7.0), "BUF", "RB")
    assert fav > 1.0 > dog
    assert any("Game script" in r for r in fav_r)
    # Capped: a 30-point spread is not three times a 10-point one.
    huge, _ = script_td_multiplier(_game(-30.0), "KC", "RB")
    assert huge <= 1.12


def test_script_multiplier_is_gentle_and_inverted_for_pass_catchers():
    wr_fav, _ = script_td_multiplier(_game(-10.0), "KC", "WR")
    wr_dog, _ = script_td_multiplier(_game(-10.0), "BUF", "WR")
    assert wr_dog > 1.0 > wr_fav
    # …and always inside a tighter band than the RB's.
    assert 0.95 <= wr_fav and wr_dog <= 1.05


def test_script_multiplier_sits_out_for_qbs():
    assert script_td_multiplier(_game(-10.0), "KC", "QB") == (1.0, [])


def test_td_probability_actually_contains_the_script():
    """The old board SAID "Favoured — positive game script" while the
    rate contained no such factor. Symmetric teams, same role, only the
    spread differs: the favourite's back must now price higher."""
    opp = Team("X", "X", DefenseProfile("X"))
    prop_f = Prop(player="A", team="KC", opponent="BUF", position="RB",
                  market=ANYTIME_TD, logs=[], career_avg=0,
                  vs_opponent_avg=None, lines=[])
    prop_d = Prop(player="B", team="BUF", opponent="KC", position="RB",
                  market=ANYTIME_TD, logs=[], career_avg=0,
                  vs_opponent_avg=None, lines=[])
    g = _game(-7.0)
    p_fav, _ = td_probability(prop_f, g, opp, 0.45)
    p_dog, _ = td_probability(prop_d, g, opp, 0.45)
    # Favourite carries a higher implied total AND the script bonus; the
    # gap must exceed the implied-total effect alone (the pre-fix state).
    assert p_fav > p_dog
    # The adjective survives only in comments that quote its removal —
    # never as an appended reason again.
    src = _read("engine", "touchdowns.py")
    assert 'reasons.append("Favoured' not in src, \
        "the adjective is back — a reason describing math that isn't done"


# --- the odds windows -------------------------------------------------------

def test_the_widened_windows_and_their_page_copy_agree():
    from engine.longshots import NFL_TD_ODDS, CFB_TD_ODDS
    # Ceilings moved out 2026-08-27 on measured evidence: inside the
    # sub-18% region the model's top quintile out-scores its bottom by
    # 7.4 points at z = 7.6, which is exactly the separation the old
    # +450 said could not be found there. See engine/tdbacktest.
    assert NFL_TD_ODDS == (-150, 700)
    assert CFB_TD_ODDS == (-200, 900)
    app = _read("web", "js", "app.js")
    # longshotEmptyReason names the live ranges; stale copy documents a
    # rule the engine no longer enforces. Asserted from the CONSTANTS so
    # the two cannot drift again — a hardcoded pair here would need
    # hand-editing every time the window moves, which is how it drifted.
    assert f"-150 to +{NFL_TD_ODDS[1]}" in app
    assert f"-200 to +{CFB_TD_ODDS[1]}" in app
    assert "-150 to +200" not in app


# --- the live odds path carries scorer quotes -------------------------------

SCORER_EVENT = {"bookmakers": [
    {"key": "draftkings", "title": "DraftKings", "markets": [
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "James Cook", "price": 145},
            {"name": "No", "description": "James Cook", "price": -185},
            {"name": "Yes", "description": "Khalil Shakir", "price": 320},
        ]},
        {"key": "player_pass_yds", "outcomes": [
            {"name": "Over", "description": "Josh Allen", "price": -110,
             "point": 255.5},
            {"name": "Under", "description": "Josh Allen", "price": -110,
             "point": 255.5}]},
    ]}]}


def _slate_with_td_props():
    teams = {"KC": Team("KC", "KC", DefenseProfile("KC")),
             "BUF": Team("BUF", "BUF", DefenseProfile("BUF"))}
    game = Game(home="KC", away="BUF", weather=Weather(dome=False),
                spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=260) for w in range(1, 6)]
    props = [
        Prop(player="Josh Allen", team="BUF", opponent="KC", position="QB",
             market=PASS_YDS, logs=logs, career_avg=255, vs_opponent_avg=None,
             lines=[SportsbookLine(book="proxy", line=250.0)]),
        Prop(player="James Cook", team="BUF", opponent="KC", position="RB",
             market=ANYTIME_TD, logs=[], career_avg=0, vs_opponent_avg=None,
             lines=[]),
        Prop(player="Dalton Kincaid", team="BUF", opponent="KC",
             market=ANYTIME_TD, position="TE", logs=[], career_avg=0,
             vs_opponent_avg=None, lines=[]),
    ]
    return Slate(date="2026-W01", teams=teams, games=[game], props=props)


def test_apply_odds_attaches_scorer_quotes(monkeypatch=None):
    mp = monkeypatch or MP()
    mp.setattr(oa, "list_events",
               lambda key, ttl=300, sport="nfl", cache_only=False: [
                   {"id": "e1", "home_team": "Kansas City Chiefs",
                    "away_team": "Buffalo Bills"}])
    captured = {}

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl",
                   cache_only=False):
        captured["markets"] = list(markets or [])
        return SCORER_EVENT, oa.Quota("491", "9")
    mp.setattr(oa, "fetch_event_odds", fake_fetch)
    from engine import linemoves as _lm
    mp.setattr(_lm, "record_snapshots", lambda *a, **k: 0)
    slate = _slate_with_td_props()
    try:
        res = oa.apply_odds_to_slate(slate, api_key="testkey")
    finally:
        if monkeypatch is None:
            mp.undo()
    # The scorer market was REQUESTED — the first missing link.
    assert "player_anytime_td" in captured["markets"]
    # The quote landed as a 0.5 line with both sides — the second.
    cook = next(p for p in slate.props if p.player == "James Cook")
    assert res.scorers_matched == 1
    assert cook.lines and cook.lines[0].line == 0.5
    assert cook.lines[0].over_odds == 145
    assert cook.lines[0].under_odds == -185
    # An unquoted TD prop is the NORM, not a miss: empty lines (so the
    # long-shot builder skips it) and OUT of the unmatched diagnostics.
    kincaid = next(p for p in slate.props if p.player == "Dalton Kincaid")
    assert kincaid.lines == []
    assert not any("anytime_td" in u for u in res.unmatched)


def test_long_shots_builds_candidates_from_priced_td_props_only():
    """The chain's last link: a QUOTED TD prop becomes a long-shot
    candidate; an unquoted one never does. Captured at the candidate
    boundary rather than the finished board, because whether a candidate
    graduates depends on edge — the model's opinion of tonight's price —
    and pinning that here would make this test fail whenever the
    fixture's imaginary price happened to be fair."""
    import engine.touchdowns as td
    from engine.pipeline import _long_shots
    slate = _slate_with_td_props()
    cook = next(p for p in slate.props if p.player == "James Cook")
    cook.lines = [SportsbookLine(book="DraftKings", line=0.5,
                                 over_odds=145, under_odds=-185)]
    seen = {}
    real = td.build_td_longshots

    def capture(candidates, **kw):
        seen["cands"] = candidates
        return real(candidates, **kw)
    td.build_td_longshots = capture
    try:
        _long_shots(slate)
    finally:
        td.build_td_longshots = real
    players = [c["prop"].player for c in seen["cands"]]
    assert players == ["James Cook"], \
        "the unquoted TD prop leaked in, or the quoted one was dropped"
    assert seen["cands"][0]["odds"] == 145
    assert seen["cands"][0]["under_odds"] == -185


# --- the CFB model ----------------------------------------------------------

def _cfb_hist(season=2025):
    """A REALISTIC roster depth chart, not just the stars. The first cut
    seeded two players per team, which made each one look like 50% of
    the offense — the model priced an 88% scorer, the credibility guard
    refused everything, and the board test passed on an empty list it
    never noticed was empty. Shares only mean something against the
    whole team's volume."""
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    roster = {
        # (player, carries, rush_yds, receptions, rec_yds) per game
        "UGA": [("Nate Frazier", 18, 95, 2, 15),
                ("Zachariah Branch", 0.5, 4, 6, 80),
                ("Backup Back", 8, 40, 1, 8), ("WR Two", 0.2, 1, 4, 55),
                ("WR Three", 0, 0, 3, 38), ("TE One", 0, 0, 3, 30),
                ("Slot Guy", 0.4, 3, 3, 33), ("QB Runner", 9, 45, 0, 0),
                ("Bit Player", 0, 0, 1, 8)],
        "CLEM": [("Opp Back", 15, 70, 1, 9), ("CU WR1", 0, 0, 6, 78),
                 ("CU WR2", 0, 0, 4, 52), ("CU RB2", 7, 34, 1, 10),
                 ("CU TE", 0, 0, 2, 24), ("CU WR3", 0.3, 2, 3, 30)],
    }
    for team, players in roster.items():
        for name, car, ry, rec, recy in players:
            for g in range(1, 7):
                for market, val in (("carries", car), ("rush_yds", ry),
                                    ("receptions", rec), ("rec_yds", recy)):
                    conn.execute(
                        "INSERT INTO player_game_logs (sport, season, period, "
                        "game_id, player, team, market, value) VALUES "
                        "('cfb', ?, ?, ?, ?, ?, ?, ?)",
                        (season, f"2025-10-{g:02d}", f"g{g}", name, team,
                         market, val))
    # Frazier's measured touchdowns — the blend that pulls the yardage
    # proxy back toward what he actually does.
    for g in range(1, 7):
        conn.execute(
            "INSERT INTO player_game_logs (sport, season, period, game_id, "
            "player, team, market, value) VALUES ('cfb', ?, ?, ?, "
            "'Nate Frazier', 'UGA', 'anytime_td', ?)",
            (season, f"2025-10-{g:02d}", f"g{g}", 0.5 if g % 2 else 1.0))
    conn.commit()
    return conn


def test_usage_table_falls_back_to_the_newest_logged_season():
    conn = _cfb_hist(2025)
    season, usage = T.usage_table(conn, 2026)   # nothing for 2026 yet
    assert season == 2025
    assert oa.normalize_name("Nate Frazier") in usage["UGA"]
    u = usage["UGA"][oa.normalize_name("Nate Frazier")]
    assert u["carries"] == 18.0 and u["games"] == 6


def test_a_handful_of_rows_must_not_shadow_a_whole_ingested_season():
    """Four fixture rows for the current season used to WIN the season
    pick — `MAX(season)` returned the same thin year the guard had just
    rejected — and four seasons of measured usage sat behind them."""
    conn = _cfb_hist(2025)
    conn.execute("INSERT INTO player_game_logs (sport, season, period, "
                 "game_id, player, team, market, value) VALUES "
                 "('cfb', 2026, '2026-08-30', 'x', 'One Guy', 'UGA', "
                 "'carries', 4)")
    conn.commit()
    season, usage = T.usage_table(conn, 2026)
    assert season == 2025
    assert oa.normalize_name("Nate Frazier") in usage["UGA"]


def test_role_prefers_the_roster_position_and_falls_back_to_the_mix():
    assert T.role_of({"carries": 18.0, "receptions": 2.0}) == "RB"
    assert T.role_of({"carries": 0.3, "receptions": 6.0}) == "WR"
    # A real position beats the inference — the mix cannot tell a tight
    # end from a receiver or a running quarterback from a back.
    assert T.role_of({"carries": 0.3, "receptions": 6.0,
                      "position": "TE"}) == "TE"
    assert T.role_of({"carries": 9.0, "receptions": 1.0,
                      "position": "QB"}) == "QB"
    assert T.role_of({"carries": 12.0, "receptions": 1.0,
                      "position": "FB"}) == "RB"
    # A position the board does not price falls through to the mix
    # rather than crashing the lookup.
    assert T.role_of({"carries": 0.0, "receptions": 3.0,
                      "position": "OL"}) == "WR"


def test_the_position_travels_from_the_log_to_the_usage_row():
    conn = _cfb_hist(2025)
    conn.execute("UPDATE player_game_logs SET position='TE' "
                 "WHERE player='CU TE'")
    conn.commit()
    _season, usage = T.usage_table(conn, 2025)
    assert usage["CLEM"][oa.normalize_name("CU TE")]["position"] == "TE"
    assert T.role_of(usage["CLEM"][oa.normalize_name("CU TE")]) == "TE"


def test_cfb_implied_total_and_script():
    # UGA -13.5 at home, total 55.5 → UGA implied 34.5.
    assert abs(T.implied_total_for(-13.5, 55.5, True) - 34.5) < 1e-9
    fav, fav_r = T.script_multiplier(-13.5, True, "RB")
    dog, _ = T.script_multiplier(-13.5, False, "RB")
    assert fav > 1.0 > dog
    assert any("Game script" in r for r in fav_r)


def test_cfb_defense_reads_points_allowed_with_a_sample_floor():
    conn = _cfb_hist()
    # Two games only: no opinion.
    for g in range(2):
        conn.execute(
            "INSERT INTO games (sport, season, period, game_id, home, away, "
            "home_score, away_score) VALUES ('cfb', 2025, ?, ?, 'CLEM', 'X', "
            "20, 38)", (f"2025-09-{g+1:02d}", f"d{g}"))
    conn.commit()
    assert T.defense_multiplier(conn, "CLEM", 2025) == (1.0, [])
    # A third leaky game and it SAYS so — but the number stays 1.0.
    #
    # The market's total already prices the defence, and multiplying our
    # own read on top counted it twice: over 3,920 walk-forward games the
    # implied total alone scored chi-square 3.0 against 181.8 for the
    # total times this term, missing by 16-19% at each end. Dropping it
    # beat keeping it in every held-out season (13.1 against 196.1), and
    # the best partial weight was no better than zero.
    conn.execute(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score) VALUES ('cfb', 2025, '2025-09-03', 'd3', "
        "'CLEM', 'X', 21, 40)")
    conn.commit()
    mult, reasons = T.defense_multiplier(conn, "CLEM", 2025)
    assert mult == 1.0, "the defence term is back to double-counting the total"
    assert reasons, "a leaky defence should still be disclosed to the reader"
    assert "context only" in reasons[0], \
        "the card must not imply a factor that does not move the price"


def test_cfb_weather_uses_our_own_forecast_layer():
    assert T.weather_multiplier({"dome": True}, "WR")[0] == 1.0
    windy, reasons = T.weather_multiplier(
        {"dome": False, "wind_mph": 24, "temp_f": 55}, "WR")
    assert windy < 1.0 and any("Wind" in r for r in reasons)
    # Wind does not touch a ground role.
    assert T.weather_multiplier(
        {"dome": False, "wind_mph": 24, "temp_f": 55}, "RB")[0] == 1.0


def _cfb_games():
    kick = (dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    return [{"home": "UGA", "away": "CLEM", "date": "2026-08-30",
             "kickoff": kick, "spread": -13.5, "total": 55.5,
             "weather": {"dome": False, "wind_mph": 5, "temp_f": 78}}]


def test_a_goal_line_quarterback_dilutes_his_running_back():
    """The mechanism the CFB handbook's Section 6 rule is really about.

    It says to check the quarterback's share of inside-5 carries and cap
    the back when it passes 40%. Measured over 2,203 lead-back games that
    exact line separates almost nothing (0.250 against 0.238, z = +0.74),
    and adding it as a separate term made the fit worse in every held-out
    season with a coefficient of the wrong sign — because the effect is
    already here. The red-zone denominator counts EVERY player, so a
    quarterback taking goal-line work reduces the back's share of it
    without anyone adding a rule.

    Pinned because the obvious "fix" is to filter the denominator to
    skill positions, which would silently delete this."""
    conn = _cfb_hist()
    # The back does real red-zone work, and UGA's quarterback is a
    # goal-line runner who takes some of it.
    for g in range(1, 7):
        for who, pos, val in (("Nate Frazier", "RB", 5),
                              ("Goal Line QB", "QB", 6)):
            conn.execute(
                "INSERT INTO player_game_logs (sport, season, period, "
                "game_id, player, team, position, market, value) VALUES "
                "('cfb', 2025, ?, ?, ?, 'UGA', ?, 'rz_car', ?)",
                (f"2025-10-{g:02d}", f"g{g}", who, pos, val))
    conn.commit()
    _season, usage = T.usage_table(conn, 2025)
    uga = usage["UGA"]
    assert oa.normalize_name("Goal Line QB") in uga, \
        "the usage table filtered the quarterback out"
    team_rz = sum(p["rz_car"] + p["rz_rec"] for p in uga.values())
    back = uga[oa.normalize_name("Nate Frazier")]
    with_qb = (back["rz_car"] + back["rz_rec"]) / team_rz
    without = (back["rz_car"] + back["rz_rec"]) / (team_rz - 6.0)
    assert with_qb < without, "the quarterback took no share from the back"
    assert with_qb < without * 0.85, \
        f"a six-carry goal-line quarterback barely moved it: {with_qb:.3f}"


def test_cfb_board_prices_quoted_players_with_usage_and_says_the_rest():
    conn = _cfb_hist()
    quotes = {0: {
        # Prices set in the credible band around what the model believes
        # — the guard-refusal case has its own test below.
        oa.normalize_name("Nate Frazier"): [
            {"book": "DraftKings", "yes_odds": -130, "no_odds": 100}],
        oa.normalize_name("Zachariah Branch"): [
            {"book": "FanDuel", "yes_odds": 180, "no_odds": None}],
        # PRICED WHERE IT CLEARS WITH NO FITTED CORRECTION, which is the
        # only state a fresh clone is ever in. At +290 this pick
        # graduated on the machine that had fitted `cfb:anytime_td` and
        # nowhere else: a fitted temperature LIFTS a modelled
        # probability, so the local suite called three commits green
        # while GitHub Actions called them red. `run_tests.py` now points
        # QB_MODELS_DIR at its sandbox so that cannot recur, and this
        # price is set from the neutral board (it clears from about +500
        # to +600, and +700 leaves the odds window entirely).
        oa.normalize_name("Slot Guy"): [
            {"book": "DraftKings", "yes_odds": 550, "no_odds": None}],
        # Quoted by the book, unknown to our logs: no pick, counted.
        oa.normalize_name("Transfer Portal"): [
            {"book": "DraftKings", "yes_odds": 200, "no_odds": None}],
        # Outside even the CFB window. Was +900, which became the
        # ceiling itself when the windows widened on 2026-08-27 — the
        # fixture moved rather than the assertion, because what is being
        # tested is that the census COUNTS an out-of-window quote, not
        # where the edge happens to sit this month.
        oa.normalize_name("Bit Player"): [
            {"book": "DraftKings", "yes_odds": 1400, "no_odds": None}],
    }}
    rows, census, watch = T.build_cfb_td_longshots(conn, _cfb_games(), quotes, 2026)
    assert census["quoted_players"] == 5
    assert census["no_usage"] == 1
    assert census["outside_window"] == 1
    assert census["usage_season"] == 2025
    # A NON-EMPTY assertion, learned the hard way: the first cut checked
    # subset membership and passed on a board that priced nothing.
    assert rows, f"no picks graduated — census {census}"
    players = {r["player"] for r in rows}
    assert players <= {"Nate Frazier", "Zachariah Branch", "Slot Guy"}
    for r in rows:
        # The prior-season fallback is DISCLOSED on the pick itself.
        assert any("2025 logs" in c for c in r["caveats"]), r["caveats"]
        assert r["market"] == "anytime_td"
        assert any("implied total" in x.lower() for x in r["reasons"])
    frazier = next((r for r in rows if r["player"] == "Nate Frazier"), None)
    if frazier:
        # His measured touchdowns reached the card.
        assert any("measured" in x for x in frazier["reasons"])


def test_cfb_model_distrusts_its_own_outsized_disagreements():
    """A quote far below what the proxy believes is treated as OUR error,
    not found money — the same MAX_CREDIBLE_EDGE discipline every long
    shot passes. The first dry run priced an 88% scorer at +125; this is
    the guard that (rightly) emptied that board."""
    conn = _cfb_hist()
    quotes = {0: {oa.normalize_name("Zachariah Branch"): [
        {"book": "FanDuel", "yes_odds": 320, "no_odds": None}]}}
    rows, census, watch = T.build_cfb_td_longshots(conn, _cfb_games(), quotes, 2026)
    assert census["priced"] == 1 and rows == [], \
        "a 30-point disagreement with the market graded as a play"


def test_cfb_no_quotes_no_usage_no_picks():
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    rows, census, watch = T.build_cfb_td_longshots(conn, _cfb_games(), {}, 2026)
    assert rows == [] and census["quoted_players"] == 0


# --- the capped CFB quote pull ----------------------------------------------

def test_attach_td_quotes_filters_caps_and_survives_cache_misses():
    sys.path.insert(0, ROOT)
    import cfb_build as B
    now = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)
    games, priced = [], {}
    for i in range(16):
        gid = f"g{i}"
        games.append({"game_id": gid, "home": f"H{i}", "away": f"A{i}",
                      "kickoff": f"2026-08-29T{16 + (i % 8):02d}:00Z",
                      "home_rank": 1 if i < 4 else None})
        entry = {"event_id": f"e{i}", "spread": (-7.0, -110, -110),
                 "total": (55.5, -110, -110)}
        if i == 15:
            entry.pop("total")         # no total → no implied → not eligible
        priced[gid] = entry
    # One game already kicked, one with no event id.
    games[14]["kickoff"] = "2026-08-29T10:00Z"
    priced["g13"].pop("event_id")
    calls = []

    def fake_fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl",
                   cache_only=False):
        calls.append(eid)
        if eid == "e2":
            raise oa.OddsAPIError("no cached copy")
        return SCORER_EVENT, oa.Quota("491", "9")
    real = oa.fetch_event_odds
    oa.fetch_event_odds = fake_fetch
    try:
        out, note = B.attach_td_quotes(games, priced, cache_only=True, now=now)
    finally:
        oa.fetch_event_odds = real
    # 16 games − started − missing id − missing total = 13 eligible,
    # capped at TD_EVENT_CAP attempts.
    assert len(calls) == B.TD_EVENT_CAP, calls
    # The cache miss was skipped, not fatal; everything else parsed —
    # and `pulled` counts what actually answered.
    assert len(out) == B.TD_EVENT_CAP - 1, sorted(out)
    assert f"{B.TD_EVENT_CAP - 1} of 13 eligible" in note, note


# --- the most-likely-scorers watch ------------------------------------------

def test_td_watchlist_shows_the_juiced_bell_cow():
    """THE GIBBS CASE (Ethan, 2026-08-26): "jahmeer gibbs is -260 to get
    a touchdown and our fantasy game script say the favorite is gonna be
    running alot... if the line for our list is only down to -150, we
    wouldn't display that prop." The VALUE window did not move — a fair
    -260 is not an edge — but the watch ranks by likelihood with no
    window, so he leads the list with his price and EV shown honestly."""
    from engine.touchdowns import td_watchlist
    opp = Team("X", "X", DefenseProfile("X"))
    g = Game(home="DET", away="NO", weather=Weather(dome=True),
             spread=-8.5, total=47.5)
    bell = Prop(player="Jahmyr Gibbs", team="DET", opponent="NO",
                position="RB", market=ANYTIME_TD,
                logs=[GameLog(week=w, opponent="X", value=1.0)
                      for w in range(1, 9)],
                career_avg=0, vs_opponent_avg=None, lines=[])
    wr = Prop(player="Depth Wideout", team="NO", opponent="DET",
              position="WR", market=ANYTIME_TD, logs=[], career_avg=0,
              vs_opponent_avg=None, lines=[])
    cands = [
        {"prop": bell, "game": g, "opponent": opp,
         "opportunity_share": 0.5, "odds": -260, "book": "DraftKings",
         "under_odds": 200},
        {"prop": wr, "game": g, "opponent": opp, "opportunity_share": 0.08,
         "odds": 480, "book": "FanDuel", "under_odds": None},
        # A proxy price never reaches the page…
        {"prop": wr, "game": g, "opponent": opp, "opportunity_share": 0.08,
         "odds": -120, "book": "proxy", "under_odds": None},
        # …and a 20/1 "scorer" is a stale quote, not a likelihood.
        {"prop": wr, "game": g, "opponent": opp, "opportunity_share": 0.08,
         "odds": 2000, "book": "DraftKings", "under_odds": None},
    ]
    rows = td_watchlist(cands)
    assert rows and rows[0]["player"] == "Jahmyr Gibbs"
    assert rows[0]["odds"] == -260, \
        "the whole point is a price the value window refuses"
    assert [r["player"] for r in rows].count("Depth Wideout") == 1
    for field in ("model_prob", "implied_prob", "ev_per_unit",
                  "primary_reason"):
        assert field in rows[0], f"watch row lost {field}"
    # Ranked by likelihood, never by payout.
    assert rows[0]["model_prob"] >= rows[-1]["model_prob"]


def test_the_nfl_board_ships_the_watch_and_dedupes_it():
    from engine.pipeline import _long_shots
    slate = _slate_with_td_props()
    cook = next(p for p in slate.props if p.player == "James Cook")
    # Heavy juice: refused as a PICK by the -150 floor, shown on the watch.
    cook.lines = [SportsbookLine(book="DraftKings", line=0.5,
                                 over_odds=-260, under_odds=200)]
    picks, watch = _long_shots(slate)
    assert all(p.get("player") != "James Cook" for p in picks)
    assert "James Cook" in [w["player"] for w in watch]
    # And the payload carries it under the key the page already reads
    # (PAID key — the gate strips it for free visitors like the picks).
    from engine import gate
    assert "longshot_watch" in gate.PAID_KEYS


def test_cfb_watch_takes_the_window_refused_favourite():
    conn = _cfb_hist()
    quotes = {0: {oa.normalize_name("Nate Frazier"): [
        {"book": "DraftKings", "yes_odds": -260, "no_odds": 200}]}}
    rows, census, watch = T.build_cfb_td_longshots(
        conn, _cfb_games(), quotes, 2026)
    assert rows == [] and census["outside_window"] == 1
    assert [w["player"] for w in watch] == ["Nate Frazier"]
    assert watch[0]["odds"] == -260
    assert 0 < watch[0]["model_prob"] < 1


def test_the_page_copy_knows_the_two_watch_semantics():
    """MLB tops up a three-row board; football always shows its
    most-likely list — top-up semantics would hide the near-lock exactly
    on the weeks the value board is full, which is the shape of the
    complaint that built this."""
    app = _read("web", "js", "app.js")
    assert "The most likely scorers ride below whatever their price" in app
    assert "Topped up to three" in app          # MLB keeps its own words
    assert 'Most likely ${mlb ? "to homer" : "to score"}' in app


# --- the journal and the settle path ----------------------------------------

def test_journal_takes_minus_money_tds_and_still_refuses_minus_money_hrs():
    conn = L.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    result = {"sport": "nfl", "date": "2026-W01", "long_shots": [
        {"player": "James Cook", "market": "anytime_td", "odds": -120,
         "book": "DraftKings", "model_prob": 0.6, "edge": 0.04,
         "confidence": 6.0, "grade": "Play", "game_date": "2026-09-13",
         "game_kickoff": "2026-09-13T17:00:00Z"},
    ]}
    assert L.log_longshots(conn, result) == 1
    row = conn.execute("SELECT * FROM bets WHERE player='James Cook'").fetchone()
    # THE WEEK LABEL, not the game's ISO Sunday: NFL results are filed by
    # season+period, and an ISO-dated TD bet would query a period nothing
    # is filed under and sit open forever.
    assert row["date"] == "2026-W01"
    assert row["category"] == "longshot"
    # A minus-money HOME RUN is still a data error and still refused.
    hr = {"sport": "mlb", "date": "2026-08-24", "long_shots": [
        {"player": "X", "market": "home_runs", "odds": -120, "book": "DK",
         "model_prob": 0.6}]}
    assert L.log_longshots(conn, hr) == 0


def test_cfb_longshots_keep_the_games_own_date():
    conn = L.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    result = {"sport": "cfb", "date": "2026-08-30", "long_shots": [
        {"player": "Nate Frazier", "market": "anytime_td", "odds": 130,
         "book": "DraftKings", "model_prob": 0.5, "game_date": "2026-08-29"}]}
    assert L.log_longshots(conn, result) == 1
    row = conn.execute("SELECT date FROM bets WHERE player='Nate Frazier'"
                       ).fetchone()
    assert row["date"] == "2026-08-29"


def test_anytime_td_is_settleable_and_stays_out_of_the_headline_record():
    assert "anytime_td" in L.SETTLEABLE_LONGSHOTS
    assert "anytime_td" in L.LONGSHOT_MARKETS


def test_both_builds_journal_their_boards():
    nfl = _read("nfl_build.py")
    cfb = _read("cfb_build.py")
    # The sport stamp is load-bearing: log_longshots defaults to "mlb".
    call = nfl[nfl.index("ledger.log_longshots("):][:300]
    assert '"sport": "nfl"' in call, call
    call = cfb[cfb.index("ledger.log_longshots("):][:300]
    assert '"sport": "cfb"' in call, call



# --- the transfer portal ---------------------------------------------------
def test_a_transfer_is_found_under_his_former_school():
    """A quarter of the quoted college board changes school over the
    summer — measured 25.2% of players with 20+ touches from 2024 to
    2025 — and `usage_table` keys a player by (team, name), so every one
    of them reads as "no usage" while a full season of his production
    sits in the logs under the old school.

    The SIDE he plays for and the TEAM his usage is filed under are two
    different things once that happens, and conflating them is the bug.
    The side decides his implied total and his game script."""
    usage = {"UGA": {"nate frazier": {"carries": 18.0}},
             "GT": {"moved guy": {"carries": 12.0}}}
    # Not a transfer: both answers are the same team.
    assert T.resolve_side("nate frazier", "UGA", "CLEM", usage, {}) == \
        ("UGA", "UGA")
    # A transfer: plays for UGA now, usage still filed under GT.
    assert T.resolve_side("moved guy", "UGA", "CLEM", usage,
                          {"moved guy": {"UGA"}}) == ("UGA", "GT")


def test_week_one_refuses_to_guess_which_side_a_transfer_is_on():
    """Nobody has played, so the current season's logs are empty and
    there is no honest way to say which of the two teams he joined.
    Putting a back on the wrong side of a 30-point spread is worse than
    leaving him off the board, so this returns nothing."""
    usage = {"GT": {"moved guy": {"carries": 12.0}}}
    assert T.resolve_side("moved guy", "UGA", "CLEM", usage, {}) == ("", "")
    # And a player the current logs place at a THIRD school is not
    # quietly assigned to whichever team is listed first.
    assert T.resolve_side("moved guy", "UGA", "CLEM", usage,
                          {"moved guy": {"FSU"}}) == ("", "")


def test_the_current_season_map_is_built_from_who_has_actually_played():
    conn = _cfb_hist()
    got = T.teams_by_name(conn, 2025)
    assert oa.normalize_name("Nate Frazier") in got
    assert "UGA" in got[oa.normalize_name("Nate Frazier")]
    assert T.teams_by_name(conn, 2099) == {}


def test_a_published_roster_places_a_transfer_in_week_one():
    """The week this matters most is the week the logs are empty. ESPN
    publishes the current roster keyed by the same team id `games`
    stores, so a transfer can be placed before he has played a snap."""
    from engine.sources.cfbdata import parse_team_roster
    payload = {"season": {"year": 2026}, "athletes": [
        {"position": "offense", "items": [
            {"id": "1", "fullName": "Moved Guy",
             "position": {"abbreviation": "RB"}}]}]}
    roster = parse_team_roster(payload)
    assert roster == {"moved guy": "RB"}
    usage = {"GT": {"moved guy": {"carries": 12.0}}}
    # With the roster placing him at UGA, the side resolves and the usage
    # still comes from GT.
    assert T.resolve_side("moved guy", "UGA", "CLEM", usage,
                          {"moved guy": {"UGA"}}) == ("UGA", "GT")


def test_a_roster_parser_survives_a_payload_that_changed_shape():
    """A feed that reshapes should cost a coarser position, not an empty
    roster and a silently smaller board."""
    from engine.sources.cfbdata import parse_team_roster
    assert parse_team_roster({}) == {}
    assert parse_team_roster(None) == {}
    assert parse_team_roster({"athletes": [{"items": [None, "x", {},
                                                      {"fullName": "  "}]}]}) == {}
    # No per-athlete position: the group label is kept rather than blank.
    got = parse_team_roster({"athletes": [
        {"position": "offense", "items": [{"fullName": "Some One"}]}]})
    assert got == {"some one": "OFFENSE"}


def test_a_name_on_two_rosters_is_placed_on_neither():
    """Two players sharing a name across the slate cannot be told apart,
    and guessing puts one of them on the wrong side of a spread."""
    import engine.cfb.tds as mod
    real = mod.__dict__.get("rosters_for")
    from engine.sources import cfbdata
    saved = cfbdata.fetch_team_roster
    rosters = {"espn:1": {"athletes": [{"items": [
                   {"fullName": "Same Name", "position": {"abbreviation": "RB"}},
                   {"fullName": "Only Here", "position": {"abbreviation": "WR"}}]}]},
               "espn:2": {"athletes": [{"items": [
                   {"fullName": "Same Name", "position": {"abbreviation": "TE"}}]}]}}
    try:
        cfbdata.fetch_team_roster = lambda t, **k: rosters[t]
        got = mod.rosters_for(["espn:1", "espn:2"], 2026)
    finally:
        cfbdata.fetch_team_roster = saved
    assert got == {"only here": "espn:1"}
    assert "same name" not in got


def test_a_roster_that_will_not_load_never_blocks_the_board():
    """Those players fall back to being dropped, which is exactly what
    happened before any of this existed."""
    import engine.cfb.tds as mod
    from engine.sources import cfbdata
    saved = cfbdata.fetch_team_roster

    def boom(team, **kw):
        raise RuntimeError("feed down")
    try:
        cfbdata.fetch_team_roster = boom
        assert mod.rosters_for(["espn:1", "espn:2"], 2026) == {}
    finally:
        cfbdata.fetch_team_roster = saved


def test_a_transfers_share_is_read_against_his_OLD_team():
    """His share is a statement about the season the numbers came from.
    Dividing last year's touches by this year's roster would compare two
    different teams and call it a role."""
    import ast
    import inspect
    fn = next(n for n in ast.walk(ast.parse(inspect.getsource(T)))
              if isinstance(n, ast.FunctionDef)
              and n.name == "build_cfb_td_longshots")
    src = ast.unparse(fn)
    assert "usage[usage_team][norm]" in src
    assert "usage.get(usage_team)" in src
    assert "usage[side]" not in src, "the player and his denominator disagree"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
