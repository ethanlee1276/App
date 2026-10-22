"""This week in fantasy points: the NFL board's numbers on every league desk.

Ethan, 2026-10-22: "with all this new data added for nfl with how we do
the offense and defense and game scripts and all the data from our game
reports. We need to make sure we are using that data correctly for
fantasy ... make sure we wrap that into it how it should be".

What this file holds the week (engine/fantasyweek) and the desks to:

* THE BOARD'S NUMBERS, ADDED UP. Each fantasy component is the prop
  board's own projection (the defence against his position, the game
  script, the weather, who is out around him), his touchdowns the
  calibrated touchdown model's, scored in PPR with every component kept
  so a league's own rules apply on top. A component the board does not
  project is NAMED, never guessed.
* AVAILABILITY. Ruled out is zero; questionable is worth the measured
  chance he plays times what he scores if he does; a bye is zero. A
  league platform's own injury status (Sleeper's IR) sits a man the
  week's practice report never lists.
* THIS WEEK FOR THE LINEUP AND THE HEAD-TO-HEAD, THE SEASON FOR TRADES.
  A start is this week's question; a trade is the rest of the season's,
  and a man on a bye this week is not worth zero to it.
* ONLY THIS WEEK'S FILE. A file whose games are over is not this week's,
  and the desk says so and scores season averages.
* MEASURED. The switch from season averages was walked forward over
  2023-2025 (fantasyweekfit.py), and the range on the card is the
  measured one, not a normal band.
* PAID WHOLE. Every number in the file is the model's.

Offline; every file it writes is a temporary one.

Run directly: `python3 tests/test_the_fantasy_week.py`
"""
import datetime as dt
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import fantasyweek as FW          # noqa: E402
from engine import fantasy_h2h as H           # noqa: E402
from engine import fantasy_lineup as FL       # noqa: E402
from engine import gate                       # noqa: E402

SERVER = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()


def _row(player, team, opp, pos, market, proj, **kw):
    r = {"player": player, "team": team, "opponent": opp, "position": pos,
         "market": market, "projection": proj, "headshot": ""}
    r.update(kw)
    return r


def _wr(player="Ja'Marr Chase", team="CIN", opp="PIT", rec_yds=80.0, receptions=6.0, **kw):
    return [_row(player, team, opp, "WR", "rec_yds", rec_yds, **kw),
            _row(player, team, opp, "WR", "receptions", receptions)]


def _step(key, mult, why):
    return {"key": key, "label": key, "mult": mult, "why": why}


def _body(name):
    i = SERVER.index(f"    def {name}(")
    j = SERVER.find("\n    def ", i + 10)
    return SERVER[i:j if j != -1 else len(SERVER)]


# --- the arithmetic -------------------------------------------------------------
def test_touchdowns_come_back_as_the_count_the_model_started_from():
    """The touchdown model makes an expected count and publishes
    1 − e^−count; the week needs the count back."""
    for lam in (0.05, 0.3, 0.6, 1.2):
        assert abs(FW.td_lambda(1.0 - math.exp(-lam)) - lam) < 1e-9
    assert FW.td_lambda(0) == 0.0 and FW.td_lambda(None) == 0.0
    assert math.isfinite(FW.td_lambda(1.0)), "a certainty must not divide by zero"


def test_a_back_s_touchdowns_split_the_way_his_yards_do():
    assert FW.split_tds(1.0, "RB", 60.0, 20.0) == (0.75, 0.25)
    assert FW.split_tds(0.5, "QB", 30.0, 0.0) == (0.5, 0.0), "a passer's own are rushing ones"
    assert FW.split_tds(0.4, "WR", 0.0, 70.0) == (0.0, 0.4)
    assert FW.split_tds(0.4, "RB", 0.0, 0.0) == (0.4, 0.0)
    assert FW.split_tds(0.0, "RB", 50.0, 10.0) == (0.0, 0.0)


def test_ppr_is_the_desks_own_baseline():
    """A season average is nflverse's PPR total; the week is scored in the
    same unit, so a league's rules apply to both the same way."""
    for key, rate in FL.PPR_BASELINE.items():
        assert FW.PPR[FL.SCORING_MARKET[key]] == rate, key
    comp = {"receptions": 5.0, "rec_yds": 60.0, "rec_td": 0.5}
    assert FW.points(comp) == 14.0
    assert FW.points(comp, FW.HALF) == 11.5
    assert FW.points(comp, FW.STANDARD) == 9.0


# --- availability ----------------------------------------------------------------
def test_ruled_out_is_zero_and_questionable_is_the_chance_he_plays():
    out = FW.project_players(_wr(injury_status="Out"))[0]
    assert out["expected"] == 0.0 and out["play"] == 0.0 and out["ppr"] > 0, \
        "an Out receiver still shows what he would have scored, at zero"
    q = FW.project_players(_wr(injury_status="Questionable"))[0]
    assert q["play"] == FW.FALLBACK_PLAY["Questionable|*"]
    assert abs(q["expected"] - q["ppr"] * q["play"]) < 0.01
    healthy = FW.project_players(_wr())[0]
    assert healthy["play"] == 1.0 and healthy["expected"] == healthy["ppr"]


def test_the_practice_report_and_the_club_s_record_set_the_chance():
    listed = {"jamarr chase": {"team": "CIN", "designation": "Questionable",
                               "practice": "Limited", "league": 0.70, "club": 0.80}}
    got = FW.project_players(_wr(injury_status="Questionable"), practice=listed)[0]
    assert got["play"] == 0.70, "the club's number without its bar holding"
    assert got["play_source"] == "practice report" and got["practice"] == "Limited"
    held = {k: {**v, "held_out": {"holds": True}} for k, v in listed.items()}
    got = FW.project_players(_wr(injury_status="Questionable"), practice=held)[0]
    assert got["play"] == 0.80 and "club" in got["play_source"]
    # A practice row for a different team is a different man.
    other = {"jamarr chase": {**listed["jamarr chase"], "team": "DAL"}}
    got = FW.project_players(_wr(injury_status="Questionable"), practice=other)[0]
    assert got["play"] == FW.FALLBACK_PLAY["Questionable|*"]


def test_the_practice_report_names_a_man_the_board_did_not():
    """No status on the prop row, but the week's report lists him: the
    report's designation stands, and with no fit the measured cell for how
    he practised."""
    assert FW.play_chance("", {"designation": "Questionable", "practice": "DNP"},
                          fallback=FW.FALLBACK_PLAY) == (0.5183, "designation and how he practised")
    assert FW.play_chance("", {"designation": "Out"})[0] == 0.0
    assert FW.play_chance("Doubtful", None, fallback=FW.FALLBACK_PLAY)[0] < 0.05
    assert FW.play_chance("", None) == (1.0, "")
    listed = {"jamarr chase": {"team": "CIN", "designation": "Questionable", "practice": "Full"}}
    got = FW.project_players(_wr(), practice=listed)[0]
    assert got["status"] == "Questionable"
    assert got["play"] == FW.fallback_play()["Questionable|Full"]


# --- what a line carries ----------------------------------------------------------
def test_a_line_names_what_it_could_not_project():
    got = FW.project_players([_row("Tee Higgins", "CIN", "PIT", "WR", "rec_yds", 60.0)])[0]
    assert "receptions" in got["missing"], "a receiver without a catches line must say so"
    assert "touchdowns" in got["missing"]
    assert got["ppr"] == 6.0, "only what was projected is counted"
    tds = {("CIN", "Tee Higgins"): {"prob": 0.35, "reasons": ["red zone"], "quoted": True}}
    got = FW.project_players([_row("Tee Higgins", "CIN", "PIT", "WR", "rec_yds", 60.0)], tds)[0]
    assert "touchdowns" not in got["missing"] and got["td_prob"] == 0.35 and got["td_quoted"]
    assert abs(got["proj"]["rec_td"] - FW.td_lambda(0.35)) < 0.01
    assert got["td_reasons"] == ["red zone"]


def test_the_card_carries_the_matchup_the_script_and_why():
    steps = [_step("form", 1.0, "base"),
             _step("matchup", 1.08, "PIT allow 160 receiving yards a game to WRs"),
             _step("weather", 0.99, "light wind"),
             _step("injury", 1.12, "T.Higgins out: his targets go somewhere"),
             _step("cap", 1.0, "cap")]
    rows = _wr(matchup_card={"rank": 3, "of": 32, "text": "PIT allow a lot", "stat": "rec yds",
                             "model": {"applied": True}},
               game_script={"role": "favourite", "team_implied": 27.5, "lean": "pass",
                            "summary": "CIN by 6"},
               chain={"steps": steps})
    got = FW.project_players(rows)[0]
    assert got["matchup"]["grade"] == "soft" and got["matchup"]["applied"] is True
    assert got["script"]["team_implied"] == 27.5
    assert [r["key"] for r in got["reasons"]] == ["injury", "matchup"], \
        "biggest move first; a flat step and the plumbing are not reasons"
    assert FW._grade({"rank": 30, "of": 32}) == "tough"
    assert FW._grade({"rank": 16, "of": 32}) == "neutral"
    assert FW._grade(None) is None
    card = FW.week_card(got)
    assert card["matchup"]["grade"] == "soft" and card["why"][0].startswith("T.Higgins out")


def test_the_scan_s_read_and_a_role_change_ride_along_as_reasons():
    reads = {("CIN", "Ja'Marr Chase"): {"read": "shine", "label": "could shine",
                                        "headline": "soft coverage"}}
    roles = {"Ja'Marr Chase": {"reads": {"tgt": {"flag": True, "games_ago": 2, "before": 0.22,
                                                 "after": 0.31, "changed": 0.09}}}}
    plain = FW.project_players(_wr())[0]
    got = FW.project_players(_wr(), reads=reads, roles=roles)[0]
    assert got["ppr"] == plain["ppr"], "a reading moves no number"
    why = FW.week_card(got)["why"]
    assert "Matchup scan: could shine" in why
    assert any("target share went from 22% to 31% 2 games ago" in w for w in why)


def test_players_are_ordered_by_what_they_are_worth_this_week():
    rows = (_wr("Low WR", rec_yds=30.0, receptions=2.0)
            + _wr("High WR", rec_yds=95.0, receptions=8.0)
            + _wr("Hurt WR", rec_yds=120.0, receptions=9.0, injury_status="Out"))
    got = [r["player"] for r in FW.project_players(rows)]
    assert got == ["High WR", "Low WR", "Hurt WR"]


def test_the_range_is_the_measured_one():
    assert FW.range_for("WR", 12) == (3.3, 22.3)
    lo, hi = FW.range_for("RB", 0.5)
    assert lo == 0.0 and hi > lo
    assert FW.range_for("K", 8) is None, "no measured range, no range"
    got = FW.project_players(_wr())[0]
    assert got["range"] == list(FW.range_for("WR", got["ppr"]))
    # Fantasy points lean high: the top of the range sits further from
    # the projection than the bottom.
    assert got["range"][1] - got["ppr"] > got["ppr"] - got["range"][0]


def test_the_numbers_it_runs_on_were_measured():
    for pos in ("QB", "RB", "WR", "TE"):
        assert pos in FW.RESIDUAL and pos in FW.RANGE, pos
    q = FW.FALLBACK_PLAY
    assert q["Questionable|DNP"] < q["Questionable|Limited"] < q["Questionable|Full"]
    assert q["Doubtful|*"] < 0.05
    assert not any(k.startswith("Out") for k in q), "Out is zero by rule, not by table"
    score = FW.MEASURED["score"]
    every = score["ALL"]
    assert every["pairs_week"] > every["pairs_season"] and every["pairs_gain_t"] >= 2.0
    assert every["mae_week"] < every["mae_season"]
    for pos in ("QB", "RB", "WR", "TE"):
        assert score[pos]["mae_week"] <= score[pos]["mae_season"], f"{pos} behind the average"
        assert score[pos]["pairs_week"] >= score[pos]["pairs_season"], pos


def test_a_questionable_man_swings_wider_than_his_week():
    e = FW.week_entry({"position": "RB", "ppr": 15.0, "play": 0.65, "sd": 8.0,
                       "proj": {"rush_yds": 70.0, "receptions": 3.0}}, {"_games": 6})
    assert e["fp_ppr"] == 9.75 and e["rush_yds"] == 45.5 and e["receptions"] == 1.95
    assert abs(e["_sd"] - math.sqrt(0.65 * 64 + 0.65 * 0.35 * 225)) < 0.01
    full = FW.week_entry({"position": "RB", "ppr": 15.0, "play": 1.0, "sd": 8.0, "proj": {}}, {})
    assert full["_sd"] == 8.0 and full["_sd_basis"] == "week"


def test_a_part_the_board_is_silent_on_comes_from_his_season_average():
    """Walked forward, the board had no catches line for hundreds of
    receivers with a yards line: each was four points short and ordered
    behind men he outscores. His own per-game average stands in, named."""
    rows = [_row("Tee Higgins", "CIN", "PIT", "WR", "rec_yds", 60.0),
            _row("Short WR", "CIN", "PIT", "WR", "rec_yds", 62.0),
            _row("Short WR", "CIN", "PIT", "WR", "receptions", 1.0)]
    players = FW.project_players(rows)
    assert players[0]["player"] == "Short WR", "before the fill, the catches gap orders him last"
    got = FW.fill_missing(players, {"Tee Higgins": {"receptions": 5.0, "rec_td": 0.4}})
    tee = got[0]
    assert tee["player"] == "Tee Higgins", "filled, he is ahead again"
    assert tee["proj"]["receptions"] == 5.0 and tee["sources"]["receptions"] == "season average"
    assert tee["proj"]["rec_td"] == 0.4 and tee["sources"]["rec_td"] == "season average"
    assert tee["missing"] == [] and tee["filled"] == ["receptions", "touchdowns"]
    assert tee["ppr"] == round(6.0 + 5.0 + 0.4 * 6, 2) and tee["expected"] == tee["ppr"]
    assert tee["range"] == list(FW.range_for("WR", tee["ppr"]))
    # A part with no average stays named, and the touchdown model's own
    # chance is never replaced by a season rate.
    tds = {("CIN", "Short WR"): {"prob": 0.3}}
    short = FW.fill_missing(FW.project_players(rows, tds), {"Short WR": {"rec_td": 0.9}})
    short = [r for r in short if r["player"] == "Short WR"][0]
    assert short["sources"]["rec_td"] == "touchdown model" and "filled" not in short
    assert FW.fill_missing(players, None) is players


def test_the_touchdown_scale_is_only_ever_a_measured_one():
    assert FW.TD_SCALE == {}, "no scale from a run that could not see the usage maps"
    assert FW.td_scale_for("RB") == 1.0
    rows = [_row("Some Back", "KC", "LV", "RB", "rush_yds", 60.0)]
    tds = {("KC", "Some Back"): {"prob": 0.4}}
    plain = FW.project_players(rows, tds)[0]
    keep = dict(FW._SAVED)
    try:
        FW._SAVED["fit"] = {"td_scale": {"RB": 1.5}}
        scaled = FW.project_players(rows, tds)[0]
    finally:
        FW._SAVED.clear()
        FW._SAVED.update(keep)
    assert abs(scaled["proj"]["rush_td"] - 1.5 * plain["proj"]["rush_td"]) < 0.01
    assert scaled["td_prob"] == plain["td_prob"], "the chance shown is the touchdown board's"
    assert scaled["sources"]["rush_td"] == "touchdown model, scaled as measured"


def test_the_fit_keeps_a_touchdown_scale_only_where_it_held():
    import fantasyweekfit as FIT
    rows = []
    for season in (2023, 2024, 2025):
        for i in range(300):
            lam = 0.2 + (i % 5) * 0.1
            # Backs score half again what the model says, every season;
            # receivers exactly what it says.
            rows.append((season, 5, "RB", f"b{i}", 10.0, 9.0, 12.0, lam, 1.5 * lam, 9.0))
            rows.append((season, 5, "WR", f"w{i}", 10.0, 9.0, 10.0, lam, lam, 9.0))
    got = FIT.td_scale_fit(rows)
    assert got == {"RB": 1.5}, got
    moved = FIT.with_td_scale(rows[:2], got)
    assert abs(moved[0][4] - (10.0 + 6 * 0.2 * 0.5)) < 1e-9 and moved[1][4] == 10.0
    assert FIT.td_report(rows)["RB"] == (0.4, 0.6, 900)


# --- the desks ---------------------------------------------------------------------
def _doc(**kw):
    players = FW.project_players(
        _wr("Ja'Marr Chase", rec_yds=90.0, receptions=7.0)
        + _wr("D.J. Moore", "CHI", "WAS", rec_yds=70.0, receptions=5.0)
        + _wr("Free Agent WR", "NYJ", "NE", rec_yds=65.0, receptions=5.0)
        + _wr("Hurt FA", "NYJ", "NE", rec_yds=65.0, receptions=5.0, injury_status="Out"))
    doc = {"week": 8, "season": 2026, "players": players, "byes": ["LA", "KC"],
           "listed": {"Ruled Out Guy": {"team": "SEA", "status": "Out"}},
           "teams": {"CIN": {"date": "2026-10-25"}}}
    doc.update(kw)
    return doc


def _means():
    return {
        "Ja'Marr Chase": {"position": "WR", "fp_ppr": 18.0, "receptions": 7.0, "_games": 7,
                          "team": "CIN", "_sd": 7.0},
        "DJ Moore": {"position": "WR", "fp_ppr": 13.0, "receptions": 5.0, "_games": 7, "team": "CHI"},
        "Puka Nacua": {"position": "WR", "fp_ppr": 21.0, "receptions": 8.0, "_games": 7,
                       "team": "LA", "_sd": 8.0},
        "Ruled Out Guy": {"position": "WR", "fp_ppr": 12.0, "receptions": 5.0, "_games": 7, "team": "SEA"},
        "Bench Guy": {"position": "WR", "fp_ppr": 6.0, "receptions": 3.0, "_games": 7, "team": "DAL"},
        "IR Guy": {"position": "RB", "fp_ppr": 14.0, "receptions": 2.0, "_games": 5, "team": "DAL"},
    }


def test_a_season_average_desk_becomes_this_week_s():
    means = _means()
    before = json.dumps(means, sort_keys=True)
    got = FW.with_week(means, _doc(), list(means), teams={"Puka Nacua": "LAR"},
                       statuses={"IR Guy": "IR"})
    assert json.dumps(means, sort_keys=True) == before, "the season means were changed in place"
    chase = got["Ja'Marr Chase"]
    assert chase["_from_week"] and chase["_week"]["opponent"] == "PIT"
    assert chase["fp_ppr"] == FW.index(_doc())["jamarr chase"]["expected"]
    assert got["DJ Moore"]["_from_week"], "'DJ Moore' must find 'D.J. Moore'"
    puka = got["Puka Nacua"]
    assert puka["fp_ppr"] == 0.0 and puka["_week"]["bye"], "Sleeper's LAR is the board's LA"
    assert puka["receptions"] == 0.0 and puka["_sd"] == 0.0 and puka["_sd_basis"] == "zero"
    assert got["Ruled Out Guy"]["fp_ppr"] == 0.0 and got["Ruled Out Guy"]["_week"]["status"] == "Out"
    assert got["IR Guy"]["fp_ppr"] == 0.0 and got["IR Guy"]["_week"]["source"] == "league"
    assert got["Bench Guy"]["fp_ppr"] == 6.0 and got["Bench Guy"]["_week"] == {"season_average": True}


def test_a_league_s_own_status_does_not_sit_a_questionable_man():
    got = FW.with_week(_means(), _doc(), ["Bench Guy"], statuses={"Bench Guy": "Questionable"})
    assert got["Bench Guy"]["fp_ppr"] == 6.0
    got = FW.with_week(_means(), _doc(), ["Bench Guy"], statuses={"Bench Guy": "Sus"})
    assert got["Bench Guy"]["fp_ppr"] == 0.0, "Sleeper spells suspended 'Sus'"


def test_no_week_leaves_the_season_desk_as_it_was():
    means = _means()
    assert FW.with_week(means, {}, list(means)) == means
    assert FW.with_week(means, {"players": []}, list(means)) == means


def test_the_lineup_benches_the_bye_and_starts_this_week_s_numbers():
    roster = [{"player": "Puka Nacua", "position": "WR", "starting": True},
              {"player": "Ja'Marr Chase", "position": "WR", "starting": True},
              {"player": "DJ Moore", "position": "WR", "starting": False}]
    means = _means()
    season = FL.lineup(roster, ["WR", "WR"], {}, means)
    assert {s["player"] for s in season["starters"]} == {"Puka Nacua", "Ja'Marr Chase"}
    week = FL.lineup(roster, ["WR", "WR"], {},
                     FW.with_week(means, _doc(), [r["player"] for r in roster],
                                  teams={"Puka Nacua": "LAR"}))
    assert {s["player"] for s in week["starters"]} == {"Ja'Marr Chase", "DJ Moore"}, \
        "a receiver on a bye was started over one who plays"
    assert week["swaps"] and week["swaps"][0]["out"] == "Puka Nacua"
    assert all(s["basis"] == "week" for s in week["starters"]) and week["basis"] == {"week": 2}
    chase = [s for s in week["starters"] if s["player"] == "Ja'Marr Chase"][0]
    assert chase["week"]["opponent"] == "PIT"


def test_a_league_s_scoring_applies_to_the_week_as_to_a_season():
    """Half PPR takes half a point per projected catch off the week's
    number, exactly as it does off an average."""
    means = FW.with_week(_means(), _doc(), ["Ja'Marr Chase"])
    m = means["Ja'Marr Chase"]
    half = FL.league_points(m, {"rec": 0.5})
    assert abs(half["points"] - (m["fp_ppr"] - 0.5 * m["receptions"])) < 0.01 and half["exact"]


def test_the_head_to_head_counts_a_known_zero_as_no_swing():
    means = FW.with_week(_means(), _doc(), ["Puka Nacua", "Ja'Marr Chase"],
                         teams={"Puka Nacua": "LAR"})
    side = H.team_total([{"player": "Puka Nacua", "position": "WR"},
                         {"player": "Ja'Marr Chase", "position": "WR"}], ["WR", "WR"], {}, means)
    assert "Puka Nacua" not in side["unmeasured"], "a bye is a known zero, not an unmeasured spread"
    nacua = [s for s in side["starters"] if s["player"] == "Puka Nacua"][0]
    assert nacua["points"] == 0.0 and not nacua["sd"]


def test_free_agents_are_this_week_s_best_nobody_rosters():
    got = FW.free_agents(_doc(), ["Ja'Marr Chase", "DJ Moore"], limit_per_pos=5)
    names = [r["player"] for r in got["WR"]]
    assert names == ["Free Agent WR"], names
    assert got["WR"][0]["card"]["opponent"] == "NE"
    assert FW.free_agents({}, []) == {}


# --- only this week's file ----------------------------------------------------------
def _at(et_hour, day):
    from zoneinfo import ZoneInfo
    return dt.datetime(2026, 10, day, et_hour, 0, tzinfo=ZoneInfo("America/New_York"))


def test_the_week_is_this_week_until_its_last_game_is_played():
    doc = _doc(teams={"KC": {"date": "2026-10-22"}, "CIN": {"date": "2026-10-25"},
                      "SEA": {"date": "2026-10-26"}})
    assert FW.current(doc, now=_at(12, 24))
    assert FW.current(doc, now=_at(23, 26)), "Monday night is still this week"
    assert FW.current(doc, now=_at(5, 27)), "until the week turns at six"
    assert not FW.current(doc, now=_at(7, 27)), "Tuesday morning it is last week's"
    undated = _doc(teams={}, built_at="2026-10-20T09:00:00")
    assert FW.current(undated, now=_at(9, 23))
    assert not FW.current(undated, now=_at(9, 29))
    assert not FW.current({"players": []}, now=_at(12, 24))


class _Conn:
    def close(self):
        pass


def test_the_desk_reads_the_week_for_members_and_says_why_otherwise():
    import server
    soon = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    gone = (dt.date.today() - dt.timedelta(days=9)).isoformat()
    keep_load, keep_acct = FW.load, server._acct
    h = object.__new__(server.Handler)
    h._account = lambda conn: None
    try:
        server._acct = lambda: SimpleNamespace(connect=lambda: _Conn())
        FW.load = lambda path=None: _doc(teams={"CIN": {"date": soon}})
        h._entitled = lambda conn, who: True
        doc, meta = h._fantasy_week()
        assert doc["players"] and meta["state"] == "ok" and meta["week"] == 8
        assert meta["measured"] is None or "score" in meta["measured"]
        h._entitled = lambda conn, who: False
        doc, meta = h._fantasy_week()
        assert doc == {} and meta["locked"] and meta["state"] == "locked"
        assert "membership" in meta["note"]
        FW.load = lambda path=None: _doc(teams={"CIN": {"date": gone}})
        h._entitled = lambda conn, who: True
        doc, meta = h._fantasy_week()
        assert doc == {} and meta["state"] == "stale" and "over" in meta["note"]
        FW.load = lambda path=None: {}
        doc, meta = h._fantasy_week()
        assert doc == {} and meta["state"] == "none" and not meta["locked"]
    finally:
        FW.load, server._acct = keep_load, keep_acct


def test_every_desk_scores_this_week_and_trades_on_the_season():
    for name in ("_league_desk", "_league_desk_espn", "_league_desk_yahoo"):
        body = _body(name)
        assert "self._fantasy_week()" in body, name
        assert "fantasyweek.with_week(season_means, week_doc" in body, name
        assert "fantasy_lineup.lineup(mine, slots, scoring, means)" in body, name
        call = body[body.index("fantasy_trade.generate("):]
        assert call[:call.index(")") + 1].endswith("season_means)"), \
            f"{name}: a trade is the rest of the season's question"
        assert '"projection_week": week_meta' in body, name
        assert "fantasyweek.free_agents(week_doc, league_names)" in body, name
    sleeper = _body("_league_desk")
    assert "teams=team_of" in sleeper and "statuses=status_of" in sleeper
    assert "means if same_week else season_means" in sleeper, \
        "another week's head-to-head must not use this week's numbers"


# --- the file -------------------------------------------------------------------------
class _Inj:
    def __init__(self, player, team, status):
        self.player, self.team, self.status = player, team, status


def test_the_file_is_built_from_the_board():
    rows = _wr(matchup_card={"rank": 4, "of": 32, "text": "soft"},
               game_script={"role": "favourite", "team_implied": 27.0, "lean": "pass"})
    result = {"recommendations": rows, "date": "2026-W08",
              "games": [{"home": "CIN", "away": "PIT", "date": "2026-10-25",
                         "kickoff": "2026-10-25T17:00:00Z"}],
              "scan_reads": {"g1": {"players": [{"player": "Ja'Marr Chase", "team": "CIN",
                                                 "label": "could shine"}]}}}
    ideas = {"sections": {"practice": {"listed": {}, "held_out": {"holds": False}},
                          "role": {"players": {}}}}
    slate = SimpleNamespace(games=[SimpleNamespace(injuries=[_Inj("Tee Higgins", "CIN", "OUT")])])
    doc = FW.from_board(result, {("CIN", "Ja'Marr Chase"): {"prob": 0.5}}, ideas=ideas,
                        season=2026, week=8, slate=slate, built_at="2026-10-22T10:00:00")
    assert doc["week"] == 8 and doc["date"] == "2026-W08"
    assert len(doc["byes"]) == 30 and "CIN" not in doc["byes"] and "LA" in doc["byes"]
    assert doc["teams"]["CIN"]["opponent"] == "PIT" and doc["teams"]["CIN"]["implied"] == 27.0
    assert doc["listed"]["Tee Higgins"] == {"team": "CIN", "status": "Out"}
    chase = doc["players"][0]
    assert chase["game"]["date"] == "2026-10-25" and chase["read"]["label"] == "could shine"
    assert doc["measured"] == FW.measured()
    assert FW.current(doc, now=_at(12, 24))
    assert "Fantasy week: 1 players projected (1 WR)" in FW.summary_line(doc)


def test_the_file_is_paid_whole():
    assert "fantasy_week.json" in gate.PAID_FILES and "fantasy_week.json" in gate.KNOWN_BOARDS
    assert not gate.is_free("fantasy_week.json")
    public = gate.redact(_doc(built_at="2026-10-22T10:00:00"), "fantasy_week.json")
    assert "players" not in public and public["locked_reason"] == "subscription"


def test_publish_keeps_the_full_copy_private_and_load_reads_it():
    keep = gate.enabled
    with tempfile.TemporaryDirectory() as d:
        board = Path(d) / "web" / "data" / "recommendations.json"
        try:
            gate.enabled = lambda: True
            pub, full = FW.publish(_doc(built_at="2026-10-22T10:00:00"), board)
        finally:
            gate.enabled = keep
        assert Path(pub) == board.parent / "fantasy_week.json"
        assert "players" not in json.loads(Path(pub).read_text()), "the public copy leaked the week"
        assert Path(full).parent != board.parent
        assert FW.load(full)["players"], "the private copy is the whole week"
    assert FW.publish({}, "") is None


def test_the_build_writes_the_week_beside_its_board():
    i = BUILD.index("from engine import fantasyweek as _fw")
    hook = BUILD[i:BUILD.index('_mem("fantasy week"', i)]
    assert "_td_chances(slate, nfl_usage)" in hook
    assert "_fw.publish(_fw_doc, args.out)" in hook
    assert "except Exception" in hook, "the week must never cost the board"


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
