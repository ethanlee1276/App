"""Spots, contract years, milestones and the incentive tracker.

Ethan, 2026-10-11: "what other things are there like this we can track for
players" — then, of the list (revenge game, primetime, rest, travel and
body clock, divisional rematch, contract year, coach change, altitude and
surface, late season, milestone chase), "all of it"; and "we need an
incentive tracker for players. like if a player needs so many catches to
get paid".

These check, one rule each: R's save format is read (and the salary tables
nobody reads are dropped as they stream past); a contract year is the last
season of the deal in force — a franchise tag, the fifth-year option, an
extension that adds years — and a first-round pick's fourth year is unknown;
every game spot holds exactly where it is defined and nowhere else; a
revenge game is the first meeting after eight games with the old team; a
milestone flags only in its band and only in its market; the scout raises
both sides of every spot on the markets it reads; the replay scores every
spot; the card shows an unproven spot as a plain line and a proven one as a
caution; an incentive needs a measurable stat and the report's link, shows
on its card with that link, and the box's own entries sit beside the
checked-in table; the weekly refresh never runs in the sandbox.

No network: every source here is a fixture.

Run directly: `python3 tests/test_player_spots.py`
"""
import json
import os
import sqlite3
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import contracts as CT                                  # noqa: E402
from engine import scout as SC                                      # noqa: E402
from engine import spots as SP                                      # noqa: E402


# --- R's save format, written the way R writes it -----------------------------------
def _rds(frame: dict) -> bytes:
    out = bytearray(b"X\n" + struct.pack(">iii", 3, 0x040601, 0x030500) + struct.pack(">i", 5) + b"UTF-8")

    def chars(s):
        b = s.encode("utf-8")
        out.extend(struct.pack(">ii", 0x00040009, len(b)) + b)

    def pairlist(items):
        for tag, val in items:
            out.extend(struct.pack(">i", 2 | 0x400))
            out.extend(struct.pack(">i", 1))
            chars(tag)
            obj(val)
        out.extend(struct.pack(">i", 254))

    def obj(o):
        if o is None:
            out.extend(struct.pack(">i", 254))
        elif isinstance(o, dict):
            out.extend(struct.pack(">ii", 19 | 0x200 | 0x100, len(o)))
            for v in o.values():
                obj(v)
            pairlist([("names", list(o)), ("class", ["data.frame"])])
        elif o and all(isinstance(x, str) for x in o):
            out.extend(struct.pack(">ii", 16, len(o)))
            for x in o:
                chars(x)
        elif o and all(isinstance(x, int) for x in o):
            out.extend(struct.pack(">ii", 13, len(o)) + struct.pack(f">{len(o)}i", *o))
        elif o and all(isinstance(x, float) for x in o):
            out.extend(struct.pack(">ii", 14, len(o)) + struct.pack(f">{len(o)}d", *o))
        else:
            out.extend(struct.pack(">ii", 19, len(o)))
            for x in o:
                obj(x)
    obj(frame)
    return bytes(out)


def _deals(*rows):
    return {"team": ["X"] * len(rows), "contract_type": [r[2] for r in rows],
            "year_signed": [r[0] for r in rows], "yrs": [r[1] for r in rows]}


def _contract_file():
    salary = {"year": ["2024", "Total"], "base_salary": [1.0, 1.0]}
    return _rds({
        "player": ["Option Receiver", "Option Receiver", "Tagged Back", "Late Pick", "Lineman Guy"],
        "position": ["WR", "WR", "RB", "TE", "OT"],
        "otc_id": [1, 1, 2, 3, 4],
        "draft_round": [1, 1, 2, 5, 3],
        "season_history": [salary, salary, salary, salary, salary],
        "contract_history": [_deals((2020, 4, "Drafted"), (2024, 4, "Extension")),
                             _deals((2020, 4, "Drafted"), (2024, 4, "Extension")),
                             _deals((2020, 4, "Drafted"), (2024, 1, "Franchise"), (2025, 4, "Franchise")),
                             _deals((2023, 4, "Drafted")),
                             _deals((2019, 4, "Drafted"))],
    })


def test_r_saves_are_read_and_unread_tables_dropped_as_they_stream_past():
    seen = []

    def hook(frame):
        seen.append(sorted(frame))
        return CT._nested(frame)
    frame = CT.read_rds(_contract_file(), frame_hook=hook)
    assert frame["player"][0] == "Option Receiver" and frame["otc_id"][2] == 2
    assert frame["season_history"] == [None] * 5, "a salary table nobody reads is not kept"
    assert frame["contract_history"][2] == [[2020, 4, "Drafted"], [2024, 1, "Franchise"], [2025, 4, "Franchise"]]
    assert any("contract_type" in k for k in seen)
    try:
        CT.read_rds(b"not an R file at all")
        raise AssertionError("garbage must not read")
    except CT.RdsError:
        pass


def test_the_table_keeps_skill_players_once_each():
    t = CT.build(_contract_file())
    assert set(t["players"]) == {"option receiver", "tagged back", "late pick"}, "an offensive tackle is left out"
    assert len(t["players"]["option receiver"]) == 1, "one entry per player, however many rows he has"
    assert t["rows"] == 5 and t["counted"] == 3


def test_a_contract_year_is_the_last_season_of_the_deal_in_force():
    t = CT.build(_contract_file())
    cy = lambda name, s: CT.contract_year(CT.lookup(t, name), s)       # noqa: E731
    # First-round pick, extended in his fifth year: the option year is what
    # the extension builds on (2020 + 4 = 2023, option 2024, + 4 → 2028).
    assert cy("Option Receiver", 2022) is False
    assert cy("Option Receiver", 2023) is None, "a first-rounder's fourth year: the option is not in the data"
    assert cy("Option Receiver", 2024) is False, "extended before the season"
    assert cy("Option Receiver", 2028) is True and cy("Option Receiver", 2027) is False
    # Second-round pick: year four is his contract year; the tag year too;
    # the long deal signed the next spring ends it.
    assert (cy("Tagged Back", 2023), cy("Tagged Back", 2024), cy("Tagged Back", 2025)) == (True, True, False)
    assert cy("Late Pick", 2026) is True and cy("Late Pick", 2025) is False
    assert cy("Late Pick", 2022) is None, "before his first deal: unknown"
    r1 = {"pos": "WR", "round": 1, "deals": [[2021, 4, "Drafted"]]}
    assert CT.contract_year(r1, 2025) is True, "the fifth-year option season, with nothing signed since"
    assert CT.contract_year(r1, 2026) is None


def test_two_players_with_one_name_are_told_apart_by_position_or_not_at_all():
    t = {"players": {"sam jones": [{"pos": "WR", "round": 2, "deals": []},
                                   {"pos": "RB", "round": 3, "deals": []}]}}
    assert CT.lookup(t, "Sam Jones", "RB")["round"] == 3
    assert CT.lookup(t, "Sam Jones") is None and CT.lookup(t, "Sam Jones", "QB") is None


# --- the game's spots ----------------------------------------------------------------
def _row(season, week, away, home, kickoff="13:00", day=None, rest=(7, 7), div=0, surface="grass",
         location="Home", coach=("Away Coach", "Home Coach"), score=(None, None), stadium=""):
    return SP.parse_row({"game_type": "REG", "season": season, "week": week, "away_team": away, "home_team": home,
                         "gameday": day or f"{season}-10-{week:02d}", "gametime": kickoff, "location": location,
                         "away_rest": rest[0], "home_rest": rest[1], "div_game": div, "surface": surface,
                         "away_coach": coach[0], "home_coach": coach[1], "stadium_id": stadium,
                         "away_score": "" if score[0] is None else score[0],
                         "home_score": "" if score[1] is None else score[1]})


def test_each_game_spot_holds_where_it_is_defined():
    rows = [_row(2025, 1, "DAL", "PHI", div=1, coach=("Old Coach", "Nick Sirianni")),
            _row(2025, 2, "SEA", "PHI", kickoff="13:00", surface="grass", coach=("Mike Macdonald", "Nick Sirianni")),
            _row(2025, 3, "PHI", "DEN", kickoff="20:20", rest=(11, 7), coach=("Nick Sirianni", "Sean Payton")),
            _row(2025, 4, "PHI", "LA", kickoff="16:25", surface="matrixturf", coach=("Nick Sirianni", "Sean McVay")),
            _row(2025, 5, "PHI", "DAL", div=1, surface="matrixturf", coach=("Nick Sirianni", "New Coach")),
            _row(2025, 6, "MIN", "CLE", kickoff="09:30", location="Neutral", stadium="LON00"),
            _row(2025, 7, "SF", "ARI", location="Neutral", stadium="MEX00", kickoff="20:15")]
    s = SP.Schedule(rows)
    g = lambda w, h: s.game(2025, w, h)                                   # noqa: E731
    assert SP.game_spots(s, g(1, "PHI"), "PHI") == {}, "an ordinary home opener has no spots"
    sea = SP.game_spots(s, g(2, "PHI"), "SEA")
    assert "body_clock" in sea and "10:00am" in sea["body_clock"], "a West Coast team at 1pm Eastern"
    assert "long_trip" in sea and sea["long_trip"].startswith("3 time zones")
    assert "surface_switch" in sea and sea["surface_switch"] == "grass here, turf at home"
    den = SP.game_spots(s, g(3, "DEN"), "PHI")
    assert den["primetime"] == "kicks off 8:20pm Eastern" and "extra_rest" in den and "altitude" in den
    assert "long_trip" in den, "Eastern to Mountain is two zones"
    assert "altitude" not in SP.game_spots(s, g(3, "DEN"), "DEN"), "the Broncos live there"
    assert "extra_rest" not in SP.game_spots(s, g(3, "DEN"), "DEN")
    la = SP.game_spots(s, g(4, "LA"), "PHI")
    assert "primetime" not in la and "surface_switch" in la, "4:25 is not primetime"
    dal = SP.game_spots(s, g(5, "DAL"), "PHI")
    assert dal["div_rematch"] == "second meeting with DAL this season"
    assert "new_coach" not in dal, "the road team's coach has not changed"
    assert SP.game_spots(s, g(5, "DAL"), "DAL")["new_coach"] == "game 1 under New Coach"
    assert "div_rematch" not in SP.game_spots(s, g(1, "PHI"), "PHI"), "the first meeting is not a rematch"
    lon = SP.game_spots(s, g(6, "CLE"), "CLE")
    assert lon["long_trip"] == "a neutral site abroad" and "body_clock" in lon, "both teams travel abroad"
    assert "surface_switch" not in lon, "a neutral site's surface is not trusted"
    mex = SP.game_spots(s, g(7, "ARI"), "ARI")
    assert mex["altitude"] == "7,350 feet up" and "primetime" in mex
    assert SP.game_spots(s, g(2, "PHI"), "KC") == {}, "a team not in the game has no spots"


def test_a_new_head_coach_counts_four_games_and_the_staff_file_fills_nflverse_in():
    rows = [_row(2025, 17, "ARI", "SEA", coach=("Jonathan Gannon", "Mike Macdonald"))]
    rows += [_row(2026, w, "ARI", f"T{w}", coach=("Jonathan Gannon", "X")) for w in range(1, 7)]
    s = SP.Schedule(rows)
    staff = {2026: {"ARI": {"hc": "Mike LaFleur"}}}
    got = [SP.coach_games(s, s.by_team["ARI"][w], "ARI", staff) for w in range(1, 7)]
    assert got[0] == ("Mike LaFleur", 1) and got[3] == ("Mike LaFleur", 4) and got[4] == ("Mike LaFleur", 5)
    assert "new_coach" in SP.game_spots(s, s.by_team["ARI"][4], "ARI", staff)
    assert "new_coach" not in SP.game_spots(s, s.by_team["ARI"][5], "ARI", staff), "game five is not new"
    assert SP.coach_games(s, s.by_team["ARI"][1], "ARI") is None, "no change seen, no claim"


def test_late_season_reads_clinched_and_eliminated_without_tiebreakers():
    # Through week 14 the home side wins every one of these games: BUF
    # sweeps a division that loses every week, and eight AFC teams are out
    # of the Jets' reach.
    pairs = [("MIA", "BUF"), ("NYJ", "KC"), ("NE", "PIT"), ("LV", "LAC"), ("TEN", "HOU"), ("JAX", "IND"),
             ("CLE", "BAL"), ("DEN", "CIN")]
    rows = [_row(2025, w, a, h, score=(10, 30)) for w in range(1, 15) for a, h in pairs]
    rows.append(_row(2025, 15, "BUF", "NYJ"))
    rows.append(_row(2025, 15, "DAL", "PHI"))
    s = SP.Schedule(rows)
    st = SP.statuses(s, 2025, 15)
    assert st.get("BUF") == "clinched" and st.get("NYJ") == "eliminated", st
    assert "PHI" not in st and "KC" not in st, "no claim the finals cannot prove"
    g = s.game(2025, 15, "NYJ")
    assert SP.game_spots(s, g, "BUF")["late_season"] == "BUF has clinched its division"
    assert SP.game_spots(s, g, "NYJ")["late_season"] == "NYJ is eliminated"
    assert "late_season" not in SP.game_spots(s, s.game(2025, 14, "BUF"), "BUF"), "before week 15, nothing"


def test_a_revenge_game_is_the_first_meeting_after_eight_games_with_them():
    games = [("MIN", "X")] * 8 + [("NYG", "Y"), ("NYG", "MIN"), ("NYG", "MIN")]
    assert SP.revenge(games, 9) == "MIN" and SP.revenge(games, 10) is None, "only the first meeting"
    short = [("MIN", "X")] * 7 + [("NYG", "MIN")]
    assert SP.revenge(short, 7) is None, "seven games is not a former team"
    assert SP.revenge([("MIN", "X")] * 9 + [("MIN", "NYG")], 9) is None, "still with them"


def test_a_milestone_flags_only_in_its_band_and_names_the_chase():
    # 913 receiving yards in 13 games (70.2 a game), four games left: 87 to
    # go is easy — named on the card, not flagged.
    easy = SP.milestone("rec_yds", [913 / 13] * 13, 4)
    assert easy and not easy["flag"] and "needs 87 more in his last 4 games for 1,000" in easy["note"]
    tight = SP.milestone("rec_yds", [60.0] * 13, 4)                    # needs 220 at 60 a game: ratio .92
    assert tight["flag"] and tight["need"] == 220
    far = SP.milestone("rec_yds", [40.0] * 13, 4)                      # needs 480 at 40: out of reach
    assert far is None
    assert SP.milestone("rec_yds", [60.0] * 13, 6)["flag"] is False, "six games out is named, not flagged"
    assert SP.milestone("rush_att", [20.0] * 13, 4) is None, "no round number in carries"
    assert SP.milestone("receptions", [5.5] * 3, 2) is None, "three games is not a season"


def test_the_scout_raises_both_sides_of_every_spot_on_the_markets_it_reads():
    assert set(SC.SPOTS) == set(SC.SPOT_TITLES)
    for code in SC.SPOTS:
        assert f"{code}_over" in SC.FLAGS and f"{code}_under" in SC.FLAGS
    s = SC.situation("rec_yds", "UNDER", line=55, values=[50] * 6, spots={"primetime", "revenge", "nonsense"})
    assert {"primetime_under", "revenge_under"} <= set(SC.flags(s))
    assert not [f for f in SC.flags(s) if "nonsense" in f]
    s = SC.situation("anytime_td", "YES", values=[0, 1, 0, 1, 0, 1], spots={"contract_year"})
    assert "contract_year_over" in SC.flags(s), "a touchdown Yes is the over side"
    s = SC.situation("kick_pts", "OVER", line=7.5, values=[8] * 6, spots={"primetime"})
    assert not [f for f in SC.flags(s) if f.startswith("primetime")], "only the markets the scout reads"


# --- the replay ----------------------------------------------------------------------
def _hist_db():
    """A Philadelphia receiver: five ordinary weeks, then a Sunday night
    game in Denver off a long week (week 6)."""
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, logs = [], []
    for wk in range(1, 8):
        home, away = ("DEN", "PHI") if wk == 6 else ("PHI", f"O{wk}")
        games.append(("nfl", 2025, str(wk), f"{away}@{home}", home, away, 24, 20, -3.0, 44.5, None))
        logs.append(("nfl", 2025, str(wk), f"PHI-00{wk}", "Spot Receiver", "PHI", "DEN" if wk == 6 else f"O{wk}",
                     "WR", 0 if wk == 6 else 1, "receptions", 5 + (wk % 3)))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    c.row_factory = sqlite3.Row
    return c


def _sched():
    rows = [_row(2025, w, f"O{w}", "PHI") for w in range(1, 8) if w != 6]
    rows.append(_row(2025, 6, "PHI", "DEN", kickoff="20:20", rest=(10, 7)))
    return SP.Schedule(rows)


def test_the_replay_scores_every_spot_and_says_how_many():
    from engine import scouthist as H
    h = H.replay(_hist_db(), sport="nfl", sched=_sched())
    sp = h["spots"]
    assert set(sp) == set(SC.SPOTS), "every spot is reported, held or not"
    for code in ("primetime", "extra_rest", "altitude", "long_trip"):
        assert sp[code]["games"] == 1, (code, sp[code])
        assert set(sp[code]["cells"]) == {"receptions OVER", "receptions UNDER"}, "both sides"
    assert sp["revenge"]["games"] == 0 and sp["div_rematch"]["games"] == 0
    other = SP.Schedule([_row(2025, 6, "KC", "DEN", kickoff="20:20")])
    assert H.replay(_hist_db(), sport="nfl", sched=other)["spots"]["primetime"]["games"] == 0, \
        "a schedule row for another fixture is not this game"
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    assert "_print_spots(" in src and "--spot" in src


def test_the_weekly_run_refreshes_contract_years_but_never_in_the_sandbox():
    src = open(os.path.join(ROOT, "engine", "scouthist.py"), encoding="utf-8").read()
    i = src.index("CT.refresh(log=print)")
    guard = src[src.rindex("if ", 0, i):i]
    assert "not a.dry_run" in guard and "CT.stale()" in guard and "modelstate.ENV_VAR" in guard
    out = []
    assert CT.refresh(log=out.append, source=b"garbage") == {} and "not rebuilt" in out[0], \
        "a file that will not read is said, and yesterday's table stays"


# --- the card ------------------------------------------------------------------------
def _board(sched, side="OVER", proven=None):
    from engine import likelyctx as L
    from engine import scouthist as H
    real = (SP.load_schedule, SP.player_history)
    SP.load_schedule = lambda path=None: sched
    SP.player_history = lambda hist, players, since: {
        "Spot Receiver": {"games": [(2025, w, "PHI", f"O{w}") for w in range(1, 6)],
                          "values": {(2025, "receptions"): [(w, 6.0) for w in range(1, 6)]}}}
    H.save(proven or {}, [2025], sport="nfl")
    try:
        rows = [{"player": "Spot Receiver", "team": "PHI", "opponent": "DEN", "position": "WR",
                 "market": "receptions", "side": side, "line": 5.5, "recent_values": [6, 6, 6, 6, 6]}]
        result = {"games": [{"home": "DEN", "away": "PHI", "date": "2025-10-06", "spread": 3.0, "total": 44.5}],
                  "recommendations": []}
        L.annotate(rows, result, "nfl")
        return rows[0]
    finally:
        SP.load_schedule, SP.player_history = real


def test_the_card_shows_an_unproven_spot_as_a_line_and_a_proven_one_as_a_caution():
    r = _board(_sched())
    assert "primetime_over" in r["scout_flags"]
    assert any(t.startswith("Primetime — kicks off 8:20pm Eastern") for t in r["scout_spots"]), r.get("scout_spots")
    assert any(t.startswith("Altitude") for t in r["scout_spots"])
    assert not [t for t in r["scout_notes"] if "primetime" in t], "an unproven spot is not a caution"
    proven = {"primetime_over": {"receptions OVER": {"shift": -0.05, "n": 300, "gaps": [-0.05, -0.06]}}}
    r = _board(_sched(), proven=proven)
    assert any("primetime" in t for t in r["scout_notes"]), "proven by history, it is a caution"
    assert not [t for t in r.get("scout_spots") or [] if t.startswith("Primetime")], "said once, not twice"


def test_first_game_back_is_read_from_the_schedule_not_a_carried_season():
    """2026-10-11, the box after the replay saved: 59 picks lowered, and
    the first eight all "his first game back" — St. Brown and Gibbs in one
    build. A teammate's carried week 17 from last season sat beside this
    season's week 5 in the rows' recent games, so every man on the team
    looked to have missed its last game. Now: the schedule and his logs."""
    from engine import likelyctx as L
    real = (SP.load_schedule, SP.player_history)
    SP.load_schedule = lambda path=None: _sched()
    SP.player_history = lambda hist, players, since: {
        "Played Receiver": {"games": [(2025, w, "PHI", f"O{w}") for w in range(1, 6)], "values": {}},
        "Sat Receiver": {"games": [(2025, w, "PHI", f"O{w}") for w in range(1, 5)], "values": {}}}
    try:
        rows = [{"player": p, "team": "PHI", "opponent": "DEN", "position": "WR", "market": "receptions",
                 "side": "OVER", "line": 5.5, "recent_values": [6, 6, 6, 6, 6]}
                for p in ("Played Receiver", "Sat Receiver")]
        carried = [{"week": w, "value": 5.0} for w in range(17, 0, -1)]      # last season, carried
        result = {"games": [{"home": "DEN", "away": "PHI", "date": "2025-10-06"}],
                  "recommendations": [{"player": "Returning Back", "team": "PHI", "logs": carried},
                                      {"player": "Played Receiver", "team": "PHI",
                                       "logs": [{"week": w, "value": 6} for w in range(5, 0, -1)]}]}
        L.annotate(rows, result, "nfl")
    finally:
        SP.load_schedule, SP.player_history = real
    assert "back_from_absence" not in rows[0]["scout_flags"], "he played week 5"
    assert "back_from_absence" in rows[1]["scout_flags"], "he did not"
    m = SP.missed_last(_sched(), _sched().game(2025, 6, "DEN"), "PHI", {"games": []}, {(2025, 5, "PHI")})
    assert m is None, "no game of his this season: unknown, not missed"
    assert SP.missed_last(_sched(), _sched().game(2025, 6, "DEN"), "PHI",
                          {"games": [(2025, 1, "PHI", "O1")]}, set()) is None, "last game not in our logs yet"


def test_the_engine_row_fields_are_drawn_on_the_card():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function obWhyHTML(")
    fn = app[i:app.index("\nfunction ", i + 1)]
    for field in ("r.scout_spots", "r.milestone_note", "r.incentive_note", "r.incentive_source"):
        assert field in fn, field
    assert "Spot:" in fn and 'rel="noopener noreferrer"' in fn
    i = app.index("function renderIncentives(")
    fn = app[i:app.index("\nfunction ", i + 1)]
    assert "inc.milestones" in fn and "Milestone watch" in fn and "r.source" in fn


# --- the incentive tracker -----------------------------------------------------------
def _logs(player="Chase Guy", team="KC", per_game=6.0, games=13, stat="receptions"):
    from engine.db import connect, upsert_games, upsert_player_logs
    h = connect(":memory:")
    for wk in range(1, games + 1):
        upsert_games(h, [{"sport": "nfl", "season": 2026, "period": f"2026-W{wk}", "game_id": f"g{wk}",
                          "home": team, "away": "LV", "home_score": 24, "away_score": 17, "spread": -3.0,
                          "total": 44.5, "roof": "open", "surface": "grass", "temp": None, "wind": None,
                          "extra": ""}])
        upsert_player_logs(h, [{"sport": "nfl", "season": 2026, "period": f"2026-W{wk}", "game_id": f"g{wk}",
                                "player": player, "team": team, "opponent": "LV", "position": "WR", "home": 1,
                                "market": stat, "value": per_game}])
    return h


def test_an_incentive_needs_a_stat_we_measure_and_the_reports_link():
    from engine import incentives as INC
    p = os.path.join(tempfile.mkdtemp(), "box.json")
    h = _logs()
    for bad in ({"stat": "sacks", "source": "https://x.test/a"}, {"stat": "receptions", "source": ""},
                {"stat": "receptions", "source": "a beat writer said so"},
                {"stat": "receptions", "source": "https://link-to-the-report"}):
        try:
            INC.add("Chase Guy", bad["stat"], 100, "500K", bad["source"], path=p, hconn=h)
            raise AssertionError(f"taken: {bad}")
        except ValueError:
            pass
    e = INC.add("Chase Guy", "receptions", 100, "$500K", "https://x.test/report", season=2026, path=p, hconn=h)
    assert e["bonus_usd"] == 500000 and e["threshold"] == 100.0
    assert e["team"] == "KC", "his team comes from our logs when not given"
    INC.add("Chase Guy", "receptions", 90, "1.5M", "https://x.test/newer", season=2026, path=p, hconn=h)
    tbl = INC.load(p)
    assert len(tbl["entries"]) == 1 and tbl["entries"][0]["bonus_usd"] == 1.5e6, "the same chase is replaced"
    assert INC.remove("Chase Guy", "receptions", path=p) == 1 and INC.load(p)["entries"] == []


def test_a_name_our_logs_have_never_seen_is_refused():
    """2026-10-11: the runbook's example — "Player Name", with
    "https://link-to-the-report" — was pasted as it stood and saved."""
    from engine import incentives as INC
    p = os.path.join(tempfile.mkdtemp(), "box.json")
    for name in ("Player Name", "Chase Gyu"):
        try:
            INC.add(name, "receptions", 100, "500K", "https://x.test/r", season=2026, path=p, hconn=_logs())
            raise AssertionError(f"taken: {name}")
        except ValueError as exc:
            assert "not in our NFL game logs" in str(exc)
    assert INC.load(p)["entries"] == [], "nothing saved"
    assert INC.logged_team(_logs(), "chase guy", 2027) == "KC", "last season counts, spelled any case"


def test_the_box_entries_sit_beside_the_checked_in_table_and_last_season_stays_out():
    from engine import incentives as INC
    INC.add("Chase Guy", "receptions", 100, 500000, "https://x.test/r", season=2026, hconn=_logs())
    INC.add("Old Guy", "receptions", 100, 500000, "https://x.test/old", season=2025,
            hconn=_logs(player="Old Guy"))
    tbl = INC.load()
    assert {e["player"] for e in tbl["entries"]} >= {"Chase Guy", "Old Guy"}
    rep = INC.report(_logs(), 2026)
    assert [e["player"] for e in rep["entries"]] == ["Chase Guy"], "last season's money is not this season's"
    assert rep["entries"][0]["source"] == "https://x.test/r"
    INC.remove("Chase Guy")
    INC.remove("Old Guy")


def test_a_live_incentive_shows_on_its_card_with_the_link():
    from engine import incentives as INC
    p = os.path.join(tempfile.mkdtemp(), "box.json")
    INC.add("Chase Guy", "receptions", 100, 500000, "https://x.test/r", season=2026, path=p, hconn=_logs())
    entries = INC.report(_logs(), 2026, p)["entries"]
    rows = [{"player": "Chase Guy", "market": "receptions", "model_prob": 0.6},
            {"player": "Chase Guy", "market": "rec_yds"}]
    assert INC.card_notes(rows, entries) == 1
    assert "78 of 100 receptions — needs 22 more in 4 games for $500,000" in rows[0]["incentive_note"]
    assert rows[0]["incentive_source"] == "https://x.test/r" and rows[0]["model_prob"] == 0.6
    assert "incentive_note" not in rows[1]


def test_the_milestone_watch_lists_chases_from_our_logs():
    from engine import incentives as INC
    rows = INC.milestones(_logs(per_game=6.5, games=13), 2026)       # 84.5 catches, needs 15.5 in 4
    assert rows and rows[0]["player"] == "Chase Guy" and rows[0]["target"] == 100
    assert "for 100" in rows[0]["note"]
    assert INC.milestones(_logs(per_game=6.5, games=5), 2026) == [], "five games in, no chase yet"
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert 'inc["milestones"] = incentives.milestones(_hc)' in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
