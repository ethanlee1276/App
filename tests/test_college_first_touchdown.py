"""College Long Shots are first-touchdown picks, from college's own fit.

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... I guess only
college football, NFL, and NBA would have that right now. But I also want to
start implementing that too."

What these hold:

  * engine/firsttd carries college's own numbers (tools/cfb_first_td_study.py:
    the line's slope, an offence's share, the share floor) beside the NFL's,
    and the NFL's are unchanged;
  * the college pull buys the first-touchdown market and keeps its quotes
    apart from the anytime market the scorer board reads;
  * the box score marks who scored the game's first touchdown off ESPN's
    scoring plays, and only when it can find him there;
  * a college first-touchdown bet waits while its game's first scorer is
    unknown, and grades off the mark once it is.

Run directly: `python3 tests/test_college_first_touchdown.py`
"""
import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import firsttd as F                                  # noqa: E402
from engine import ledger                                       # noqa: E402
from engine.sources import cfbdata as C                         # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402


# --- the model's numbers ---------------------------------------------------------
def test_college_has_its_own_fit_and_the_nfl_keeps_its_own():
    nfl, cfb = F.params("nfl"), F.params("cfb")
    assert (nfl["team_a"], nfl["team_b"], nfl["off_share"], nfl["eps"]) == (F.TEAM_A, F.TEAM_B, F.OFF_SHARE, F.EPS)
    assert (cfb["team_a"], cfb["team_b"], cfb["off_share"], cfb["eps"]) == (-0.046, 0.379, 0.960, 0.06)
    assert F.params("nba") is F.PARAMS["nfl"], "a league without its own fit reads the NFL's"
    # A two-touchdown college favourite at home, by college's own slope.
    assert abs(F.team_first(-14.0, "cfb") - 1 / (1 + 2.718281828 ** -(-0.046 + 0.379 * 2))) < 1e-6
    assert F.team_first(-14.0, "nfl") != F.team_first(-14.0, "cfb")
    assert F.team_first(-14.0) == F.team_first(-14.0, "nfl"), "the NFL's call is unchanged"


def test_the_share_floor_and_the_offences_share_are_collegess():
    usage = {"A": {"touch": 20, "td": 2}, "B": {"touch": 0, "td": 0}}
    s_nfl, s_cfb = F.shares(usage), F.shares(usage, "cfb")
    # B has nothing but the floor: 0.04 of 1.08 in the NFL, 0.06 of 1.12 in college.
    assert abs(s_nfl["B"] - 0.04 / 1.08) < 1e-9 and abs(s_cfb["B"] - 0.06 / 1.12) < 1e-9
    rows = F.game_probs(usage, {}, -3.0, "HOME", "AWAY", sport="cfb")
    a = next(r for r in rows if r["player"] == "A")
    assert abs(a["prob"] - 0.960 * F.team_first(-3.0, "cfb") * s_cfb["A"]) < 1e-9


def _hist():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, period TEXT, game_id TEXT, player TEXT,"
              " team TEXT, opponent TEXT, market TEXT, value REAL)")
    return c


def test_the_college_board_prices_from_college_logs_and_says_colleges_numbers():
    c = _hist()
    for p, team, car, tgt, td in (("Jeremiyah Love", "ND", 18, 2, 2), ("Jadarian Price", "ND", 9, 1, 1),
                                  ("Ty Simpson", "ALA", 6, 0, 1), ("Ryan Williams", "ALA", 0, 9, 1)):
        for m, v in (("carries", car), ("targets", tgt), ("rush_td", td if car else 0), ("rec_td", 0 if car else td)):
            c.execute("INSERT INTO player_game_logs VALUES ('cfb', 2026, '2026-10-24', 'g1', ?, ?, '', ?, ?)",
                      (p, team, m, v))
    quotes = {"jadarian price|0": {"player": "Jadarian Price", "home": "ND", "away": "ALA",
                                   "quotes": [{"book": "DraftKings", "yes_odds": 900}]}}
    games = [{"home": "ND", "away": "ALA", "spread": -6.5, "date": "2026-10-31", "kickoff": "19:30"}]
    b = F.board(quotes, games, sport="cfb", conn=c, date="2026-10-31")
    assert b["games"] == 1 and b["quoted"] == 1, b
    r = b["rows"][0]
    assert r["team"] == "ND" and r["market"] == "first_td" and r["odds"] == 900
    assert abs(r["team_first"] - round(F.team_first(-6.5, "cfb"), 4)) < 1e-9
    assert "65%" in r["reasons"][0] and "4,174 games" in r["reasons"][0], r["reasons"][0]


# --- the pull ---------------------------------------------------------------------
def _event(home="ND", away="ALA"):
    def scorer(key, name, yes, no=None):
        outs = [{"name": "Yes", "description": name, "price": yes}]
        if no is not None:
            outs.append({"name": "No", "description": name, "price": no})
        return {"key": key, "outcomes": outs}
    return {"id": "e0", "home_team": home, "away_team": away, "bookmakers": [
        {"key": "draftkings", "markets": [scorer("player_anytime_td", "Jeremiyah Love", -150, 120),
                                          scorer("player_1st_td", "Jeremiyah Love", 450),
                                          scorer("player_1st_td", "Jadarian Price", 900)]}]}


def test_the_college_pull_buys_first_touchdown_and_keeps_it_apart():
    import cfb_build as B
    assert B.PLAYER_MARKETS[:2] == ["player_anytime_td", "player_1st_td"]
    assert B.CREDITS_PER_EVENT == len(B.PLAYER_MARKETS) == 14
    assert "player_1st_td" in oa.UNPROVEN_MARKETS, "behind the drop-and-retry guard"
    games = [{"game_id": "g0", "home": "ND", "away": "ALA", "kickoff": "2026-10-31T23:30:00Z"}]
    priced = {"g0": {"event_id": "e0", "spread": (-6.5, -110, -110), "total": (52.5, -110, -110)}}
    real = oa.fetch_event_odds
    oa.fetch_event_odds = lambda *a, **k: (_event(), oa.Quota("491", "9"))
    ft: dict = {}
    try:
        scorers, _lines, _note, _age = B.attach_player_quotes(
            games, priced, cache_only=True, now=dt.datetime(2026, 10, 31, 15, tzinfo=dt.timezone.utc),
            cap=1, first_td=ft)
    finally:
        oa.fetch_event_odds = real
    anytime = scorers[0]
    assert set(anytime) == {"jeremiyah love"}, "the anytime board never sees a first-touchdown price"
    assert [q["yes_odds"] for q in anytime["jeremiyah love"]] == [-150]
    assert set(ft) == {"jeremiyah love|0", "jadarian price|0"}
    assert ft["jadarian price|0"]["home"] == "ND" and ft["jadarian price|0"]["away"] == "ALA"
    assert [q["yes_odds"] for q in ft["jadarian price|0"]["quotes"]] == [900]


def test_the_college_build_makes_first_touchdown_its_long_shots():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    i = src.index("FIRST TOUCHDOWN IS COLLEGE'S LONG SHOTS")
    seg = src[i:i + 2400]
    assert '_ftd.board(first_td_quotes, _ft_games, sport="cfb"' in seg
    assert 'out["long_shots"] = _ft["picks"]' in seg and 'out["first_td"] = _ft' in seg
    assert "first_td=first_td_quotes" in src
    # The page draws the first-touchdown shelf for any league that ships one.
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "const ftd = !!state.data.first_td;" in app


# --- the box score marks the first scorer ------------------------------------------
def _summary(plays, extra_rows=()):
    rush = [{"athlete": {"displayName": "Jeremiyah Love", "id": "1"}, "stats": ["18", "120", "6.7", "1", "40"]},
            {"athlete": {"displayName": "Jadarian Price", "id": "2"}, "stats": ["9", "60", "6.7", "1", "22"]}]
    rec = [{"athlete": {"displayName": "Ryan Williams", "id": "3"}, "stats": ["5", "90", "18.0", "1", "60"]}]
    players = [{"team": {"abbreviation": "ND"}, "statistics": [
                    {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"], "athletes": rush}]},
               {"team": {"abbreviation": "ALA"}, "statistics": [
                    {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG"], "athletes": rec},
                    *extra_rows]}]
    return {"boxscore": {"players": players}, "scoringPlays": plays}


def _play(text, team, kind="Rushing Touchdown", abbr="TD", period=1):
    return {"type": {"text": kind}, "scoringType": {"abbreviation": abbr}, "text": text,
            "period": {"number": period}, "team": {"abbreviation": team}}


def _marks(summary):
    return {r["player"]: r["stats"].get("first_td") for r in C.parse_summary(summary)}


def test_the_first_touchdown_is_read_off_the_scoring_plays_in_order():
    s = _summary([_play("Will Reichard 30 Yd Field Goal", "ALA", "Field Goal Good", "FG"),
                  _play("Ryan Williams 75 Yd pass from Ty Simpson (Kick)", "ALA", "Passing Touchdown", period=2),
                  _play("Jadarian Price 4 Yd Run (Kick)", "ND")])
    assert C.first_touchdown(s) == {"player": "Jadarian Price", "team": "ND", "offense": True}
    assert _marks(s) == {"Jeremiyah Love": 0.0, "Jadarian Price": 1.0, "Ryan Williams": 0.0}
    # A pass names the catcher first.
    s2 = _summary([_play("Ryan Williams 75 Yd pass from Ty Simpson (Kick)", "ALA", "Passing Touchdown")])
    assert _marks(s2)["Ryan Williams"] == 1.0 and _marks(s2)["Jadarian Price"] == 0.0


def test_an_unknown_first_scorer_marks_nobody():
    # No scoring plays at all (ESPN leaves them off some payloads)…
    assert set(_marks(_summary([])).values()) == {None}
    # …or a first scorer nobody in this box score answers to: nothing is
    # written, so no bet grades against a guess.
    s = _summary([_play("Somebody Else 3 Yd Run (Kick)", "ND")])
    assert set(_marks(s).values()) == {None}
    assert C.mark_first_td(C.parse_summary(s), s) is False


def test_a_defences_first_touchdown_loses_every_offensive_player():
    pick6 = [{"name": "interceptions", "labels": ["INT", "YDS", "TD"],
              "athletes": [{"athlete": {"displayName": "Zabien Brown", "id": "9"}, "stats": ["1", "40", "1"]}]}]
    s = _summary([_play("Zabien Brown 40 Yd Interception Return (Kick)", "ALA", "Interception Return Touchdown")],
                 extra_rows=pick6)
    assert C.first_touchdown(s)["offense"] is False
    m = _marks(s)
    # The defender's interception group is no stat this box keeps, so he has
    # no row — and still no ball carrier or catcher scored first.
    assert m["Jeremiyah Love"] == m["Jadarian Price"] == m["Ryan Williams"] == 0.0
    assert m.get("Zabien Brown") in (None, 1.0), m
    # A kick returner the box does list gets his 1.
    ret = _summary([_play("Ryan Williams 95 Yd Kickoff Return (Kick)", "ALA", "Kickoff Return Touchdown")])
    assert _marks(ret)["Ryan Williams"] == 1.0 and _marks(ret)["Jeremiyah Love"] == 0.0


def test_names_meet_across_spellings():
    assert C._same_player("Jeremiyah Love", "Jeremiyah Love")
    assert C._same_player("D'Von Smith Jr.", "D'Von Smith")
    assert C._same_player("J. Love", "Jeremiyah Love")
    assert not C._same_player("Jeremiyah Love", "Jadarian Price")


# --- the bet waits, then grades ------------------------------------------------------
def _settle_world():
    import os
    import tempfile
    os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
    from engine import cfbroster, db
    cfbroster.CACHE_DIR = Path(tempfile.mkdtemp())        # never the box's roster file
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    day = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('cfb', 2026, ?, '401777', ?, 'ND', 'ALA', 31, 24)", (day, day))
    for who, market, v in (("Jeremiyah Love", "rush_td", 1), ("Jadarian Price", "rush_td", 1)):
        db.upsert_player_logs(H, [{"sport": "cfb", "season": 2026, "period": day, "game_id": "401777-box",
                                   "player": who, "team": "ND", "opponent": "ALA", "position": "RB",
                                   "home": 1, "market": market, "value": float(v)}])
    H.commit()
    for who in ("Jeremiyah Love", "Jadarian Price"):
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, stake_units, "
                  "stake_dollars, status, category, team) VALUES (?, 'cfb', ?, ?, ?, 'first_td', 'OVER', 0.5, "
                  "900, 0.1, 0, 'open', 'longshot', 'ND')", (f"{day}T12:00:00", day, day, who))
    L.commit()
    return L, H, day


def _statuses(L):
    return {r["player"]: r["status"] for r in L.execute("SELECT player, status FROM bets")}


def test_a_college_first_touchdown_bet_waits_then_grades_off_the_mark():
    from engine import db
    L, H, day = _settle_world()
    ledger.settle_from_history(L, H, sport="cfb")
    assert set(_statuses(L).values()) == {"open"}, ("no first scorer on file: it waits, never voids",
                                                     _statuses(L))
    for who, v in (("Jeremiyah Love", 0.0), ("Jadarian Price", 1.0)):
        db.upsert_player_logs(H, [{"sport": "cfb", "season": 2026, "period": day, "game_id": "401777-box",
                                   "player": who, "team": "ND", "opponent": "ALA", "position": "RB",
                                   "home": 1, "market": "first_td", "value": v}])
    H.commit()
    ledger.settle_from_history(L, H, sport="cfb")
    assert _statuses(L) == {"Jeremiyah Love": "lost", "Jadarian Price": "won"}, _statuses(L)


def test_a_college_first_touchdown_bet_waits_for_its_first_scorer():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = src.index('if b["market"] == "first_td":')
    seg = src[i:i + 900]
    assert "market='first_td'" in seg and "has no scorer on file yet" in seg
    assert seg.index("return None") < seg.index("PLAY_FILE_MARKETS") if "PLAY_FILE_MARKETS" in seg else True
    assert "first_td" in ledger.SETTLEABLE_LONGSHOTS


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
