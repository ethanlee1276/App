"""College props: built from the logs, priced by the NFL's own chain.

Ethan, twice on 2026-09-02: "make sure everything I'm telling you to do
for NFL is also being implemented for college football because I'm still
not seeing any props for college football."

`cfb_build` set `"recommendations": []` at the top of `main()` and passed
a literal `[]` to the journal at the bottom, so the Best Bets page, the
every-market box and the Most Likely shelves all read that key and all
found nothing. `engine/cfb/props.py` turns four seasons of ingested
player production into a `Slate`; `pipeline.price_props` — the loop
lifted out of `run_slate` — prices it through the SAME evaluation the
NFL's props go through.

The tests below pin the parts that are college-shaped, because the rest
is deliberately not:

  * a QUARTER of the board changed schools over the summer, so the side
    a player lines up for and the school his production is filed under
    are two different answers (`tds.resolve_side`);
  * a quarterback is found by his PASSING logs, which is the market the
    touchdown board's usage table does not carry — the first cut of this
    module enumerated candidates from that table and had no QBs at all;
  * a proxy line is not a market, so nothing reaches a bet, a journal or
    a likelihood shelf until a book prices it.

Run directly: `python3 tests/test_cfb_props.py`
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db                                        # noqa: E402
from engine.cfb import props as P                            # noqa: E402

SEASON = 2025

#: (name, filed team, position, markets)
ROSTER = [
    ("Carson Beck", "UGA", "QB", ("pass_yds",)),
    ("Nate Frazier", "UGA", "RB", ("rush_yds", "carries")),
    ("Arian Smith", "UGA", "WR", ("rec_yds", "receptions")),
    ("Will Howard", "OSU", "QB", ("pass_yds",)),
    ("Quinshon Judkins", "OSU", "RB", ("rush_yds", "carries")),
    ("Emeka Egbuka", "OSU", "WR", ("rec_yds", "receptions")),
    # Filed at Alabama, playing for Georgia — the transfer case.
    ("Jam Miller", "BAMA", "RB", ("rush_yds", "carries")),
]

MEANS = {"pass_yds": 250.0, "rush_yds": 70.0, "rec_yds": 60.0,
         "receptions": 4.0, "carries": 12.0}

GAMES = [{"game_id": "401", "home": "UGA", "away": "OSU",
          "home_name": "Georgia", "away_name": "Ohio State",
          "date": "2026-09-05", "kickoff": "2026-09-05T23:30Z",
          "spread": -3.5, "total": 52.5,
          "weather": {"dome": False, "temp_f": 78.0, "wind_mph": 7.0,
                      "wind_dir": "NW"},
          "weather_checked": True}]

#: Jam Miller is at Georgia now; his logs are not.
CURRENT = {"jam miller": {"UGA"}}


def _conn(games=10, roster=ROSTER, seed=3):
    d = tempfile.mkdtemp(prefix="cfb-props-")
    os.environ.setdefault("QB_MODELS_DIR", os.path.join(d, "models"))
    conn = db.connect(os.path.join(d, "history.db"))
    rnd = random.Random(seed)
    rows = []
    for name, team, pos, markets in roster:
        for g in range(games):
            for m in markets:
                rows.append({
                    "sport": "cfb", "season": SEASON,
                    "period": f"{SEASON}-09-{g + 1:02d}",
                    "game_id": f"{team}-{g}", "player": name, "team": team,
                    "opponent": "XXX", "position": pos, "home": g % 2,
                    "market": m,
                    "value": max(0.0, rnd.gauss(MEANS[m], MEANS[m] * 0.3)),
                })
    db.upsert_player_logs(conn, rows)
    return conn


def _slate(conn=None, games=None, current=None, census=None):
    return P.build_slate(conn or _conn(), games if games is not None else GAMES,
                         "2026-09-05", SEASON, census=census,
                         current=CURRENT if current is None else current)


def _of(slate, player, market):
    for p in slate.props:
        if p.player == player and p.market == market:
            return p
    return None


# --- the markets ------------------------------------------------------
def test_the_four_markets_are_the_four_that_are_measured():
    from engine import rankfit
    assert set(P.MARKETS) == set(rankfit.MARKETS["cfb"]), \
        "a market on the board that the fitter never walks"


def test_all_four_markets_reach_the_slate():
    got = {p.market for p in _slate().props}
    assert got == set(P.MARKETS), got


def test_a_quarterback_is_found_by_his_passing_logs():
    """THE BUG THIS PINS. The first cut enumerated candidates from
    `tds.usage_table`, which selects carries / receptions / rushing /
    receiving and the red-zone columns and NOT `pass_yds` — so a pocket
    passer was in no team's usage map, could not be placed on a side,
    and the one market with an obvious player per team had none."""
    slate = _slate()
    beck = _of(slate, "Carson Beck", "pass_yds")
    assert beck is not None, "the quarterback never reached the slate"
    assert beck.position == "QB"
    assert {p.player for p in slate.props if p.market == "pass_yds"} == \
        {"Carson Beck", "Will Howard"}


# --- who plays for whom -----------------------------------------------
def test_a_transfer_plays_for_his_new_school_off_his_old_school_s_logs():
    slate = _slate()
    miller = _of(slate, "Jam Miller", "rush_yds")
    assert miller is not None, "a quarter of the college board looks like this"
    assert (miller.team, miller.opponent) == ("UGA", "OSU")
    assert len(miller.logs) == 10, "his Alabama season is his form"


def test_a_transfer_nobody_can_place_is_left_off_rather_than_guessed():
    """`resolve_side` returns nothing without current-season evidence,
    and this keeps that: a back on the wrong side of a 30-point spread
    is worse than a back who is not on the board."""
    slate = _slate(current={})
    assert _of(slate, "Jam Miller", "rush_yds") is None
    assert _of(slate, "Nate Frazier", "rush_yds") is not None


def test_the_census_counts_the_transfers_it_placed():
    census: dict = {}
    _slate(census=census)
    assert census["transfers"] == 1
    assert census["candidates"] == 7
    assert census["props"] == len(_slate().props)
    assert census["usage_season"] == SEASON


def test_a_player_on_neither_team_is_not_on_the_board():
    assert not any(p.player == "Jam Miller"
                   for p in _slate(current={}).props)


# --- the line ---------------------------------------------------------
def test_the_proxy_line_sits_under_recent_form_on_a_half_number():
    for p in _slate().props:
        line = p.lines[0].line
        assert p.lines[0].book == "proxy"
        assert line * 2 == int(line * 2), f"{p.market} line {line} is not a half"
        assert line < p.career_avg + 0.5


def test_a_proxy_priced_row_is_not_a_market():
    """`evaluate_prop` refuses to call it one, which is what keeps an
    unpriced college prop out of the journal, off the likelihood board
    and out of every stake."""
    from engine.pipeline import price_props
    rows = price_props(_slate(), sport="cfb")
    assert rows, "nothing priced"
    assert not any(r["has_market"] for r in rows)
    assert not any(r["recommended"] for r in rows)


# --- history and volume floors ----------------------------------------
def test_a_player_with_too_little_history_is_counted_not_projected():
    census: dict = {}
    _slate(conn=_conn(games=3), census=census)
    assert census["props"] == 0
    assert census["thin_history"] > 0


def test_the_history_floor_matches_the_measurement_s_own():
    from engine.logwalk import settled_props_from_logs
    import inspect
    sig = inspect.signature(settled_props_from_logs)
    assert P.MIN_LOGS == sig.parameters["min_history"].default, \
        "the board prices players the walk-forward AUC never covered"


def test_a_player_who_barely_touches_a_market_is_kept_off_it():
    """Without the floor a third-string receiver lands at 'over 0.5
    yards' and the board fills with them."""
    thin = [("Deep Reserve", "UGA", "WR", ("rec_yds", "receptions"))]
    census: dict = {}
    conn = _conn(roster=thin)
    conn.execute("UPDATE player_game_logs SET value=2.0 "
                 "WHERE market='rec_yds'")
    conn.execute("UPDATE player_game_logs SET value=0.4 "
                 "WHERE market='receptions'")
    conn.commit()
    _slate(conn=conn, census=census)
    assert census["props"] == 0
    assert census["below_volume"] == 2


# --- the slate the odds feed has to join to ---------------------------
def test_the_games_carry_the_book_s_own_school_names():
    """`oddsapi.apply_odds_to_slate` prefers the slate's own names over
    the static table precisely so a 134-school map never has to exist —
    the rescue it grew for the WNBA. Without these the join has nothing
    to work with and every college event drops."""
    g = _slate().games[0]
    assert (g.home_name, g.away_name) == ("Georgia", "Ohio State")


def test_the_kickoff_forecast_reaches_the_game():
    g = _slate().games[0]
    assert g.weather.measured is True
    assert (g.weather.wind_mph, g.weather.temp_f) == (7.0, 78.0)
    assert g.spread == -3.5 and g.total == 52.5


def test_an_unpulled_forecast_is_unmeasured_rather_than_a_mild_day():
    games = [{**GAMES[0], "weather": None, "weather_checked": False}]
    g = _slate(games=games).games[0]
    assert g.weather.measured is False


def test_a_dome_is_measured_because_a_roof_is_a_fact():
    games = [{**GAMES[0], "weather": {"dome": True}, "weather_checked": True}]
    g = _slate(games=games).games[0]
    assert g.weather.dome is True and g.weather.measured is True


def test_a_prop_whose_game_is_not_on_the_slate_never_ships():
    """`Slate.game_for` raises on a prop it cannot place, which would
    take the whole board down mid-loop rather than drop one row."""
    slate = _slate()
    for p in slate.props:
        assert slate.game_for(p) is not None


def test_defence_is_league_average_rather_than_invented():
    """`DefenseProfile` is nflverse-shaped and college has no equivalent
    ingest. A plausible-looking number here would put a matchup
    multiplier on every card that no measurement stands behind — and
    the walk-forward AUC is measured against a neutral defence, so this
    is also what keeps the live board and the measurement in agreement."""
    from engine.models import DefenseProfile
    for team in _slate().teams.values():
        assert team.defense == DefenseProfile(team=team.abbr)


# --- and it is the shared evaluation, not a college copy --------------
def test_the_shared_prop_loop_is_what_prices_them():
    from engine import pipeline
    import inspect
    src = inspect.getsource(pipeline.run_slate)
    assert "price_props(" in src, \
        "run_slate grew its own copy of the loop again"
    assert "sport" in inspect.signature(pipeline.price_props).parameters


def test_the_sport_reaches_every_self_tuning_store():
    from engine import pipeline
    import inspect
    src = inspect.getsource(pipeline.price_props)
    assert "usage=u, sport=sport" in src
    assert "game=game, sport=sport" in src


def test_college_never_reads_the_nfl_s_wind_table():
    """`nfl_game_winds` keys a game "AWAY@HOME" on abbreviations, and
    college shares several with the NFL — Miami, Cincinnati, Houston,
    Buffalo. A college log spelling an NFL game would otherwise be
    stamped with that Sunday's wind and journaled as measured."""
    from engine.pipeline import _log_wind
    from engine.models import GameLog, Prop, SportsbookLine

    class _P:
        team, opponent = "CIN", "BUF"
    log = GameLog(week=1, opponent="BUF", value=50.0)
    assert _log_wind(_P(), log, "cfb") == {}
    assert isinstance(_log_wind(_P(), log, "nfl"), dict)


def test_the_build_wires_the_rows_into_every_reader_of_them():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'out["recommendations"] = _price_props(_prop_slate, sport="cfb")' in src
    # The likelihood board reads them...
    assert 'out["most_likely"] = _likely(out.get("recommendations") or []' in src
    # ...and so does the journal, which used to be handed a literal [].
    assert '"recommendations": out.get("recommendations") or []' in src
    assert '"recommendations": [],\n' not in src.split("def main")[1], \
        "the empty literal is back in the journal call"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
