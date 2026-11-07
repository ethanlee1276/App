"""The game report reads what the board does not carry (engine/reportdata, engine/gamereport).

Ethan, 2026-10-20, on the game report: "I want you too do all of it
besides D". The report gained what the outside research reports had and
the board did not:

  K1  every key player's season, his last three games and his red-zone
      work, off the game logs — the right man when two share a name, his
      home and away off the schedule (the logs' own flag reads 1 always);
  K2  the practice report, with how often men listed the same way have
      played — his club's own record only once it has beaten the league's
      on held-out seasons;
  K3  the role changes the detector sees, called a reading until it holds;
  K4  the last meetings, at the lines they closed at;
  K5  tempo and turnovers off play-by-play, ranked, a tie sharing a rank;
  K6  the kicking air, said only where it is real (a forecast outdoors, or
      a thousand feet up), abroad at the host city's altitude;
  K7  the coaching calls — fourth-and-short, two-point tries, the pass rate
      two scores up and down — each counted where the call is the coach's.

And the nightly play-by-play step now writes the team weeks, which only a
hand-run `ingest.py nfl` wrote before, so pace and pass rate over expected
stopped at whatever week someone last ran it.

Run directly: `python3 tests/test_the_game_report_reads_the_history.py`
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                               # noqa: E402
from engine import gamereport as R                                  # noqa: E402
from engine import gamescan                                         # noqa: E402
from engine import kickphysics                                      # noqa: E402
from engine import reportdata as RD                                 # noqa: E402
from engine.sources import nflpbp                                   # noqa: E402

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
REPORT_CSS = open(os.path.join(ROOT, "web", "css", "report.css"), encoding="utf-8").read()
MAINT = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()

NAMES = {"GB": "Packers", "DET": "Lions"}


# --- fixtures --------------------------------------------------------------------------
def _log(player, team, season, week, **stats):
    opp = stats.pop("opp", "OPP")
    return [{"sport": "nfl", "season": season, "period": f"{week:03d}", "game_id": f"{team}-{week:03d}",
             "player": player, "team": team, "opponent": opp, "position": "",
             "home": 1, "market": k, "value": float(v)} for k, v in stats.items()]


def _conn():
    conn = db.connect(":memory:")
    rows = []
    # Gibbs: 40, 50 yards from scrimmage, then 120, 130, 140 — up lately.
    for wk, (car, ry, rec, yy) in enumerate([(10, 30, 2, 10), (12, 40, 1, 10), (20, 100, 3, 20),
                                             (21, 110, 2, 20), (25, 120, 4, 20)], start=1):
        rows += _log("Jahmyr Gibbs", "DET", 2026, wk, opp=f"O{wk}", rush_att=car, rush_yds=ry,
                     rush_td=1 if wk == 5 else 0, receptions=rec, rec_yds=yy, targets=rec + 1, rec_td=0)
    # His red zone under play-by-play's short name, and a teammate's.
    for wk in range(1, 6):
        rows += _log("J.Gibbs", "DET", 2026, wk, rz_car=3, i5_car=1, rz_tgt=1, i10_tgt=0)
        rows += _log("D.Montgomery", "DET", 2026, wk, rz_car=1, i5_car=0, rz_tgt=0, i10_tgt=0)
        rows += _log("A.St. Brown", "DET", 2026, wk, rz_car=0, i5_car=0, rz_tgt=3, i10_tgt=1)
    # Two men named Mike Williams in the same weeks: the board's team wins.
    for wk in (4, 5):
        rows += _log("Mike Williams", "NYJ", 2026, wk, receptions=5, rec_yds=70, targets=7, rec_td=0)
        rows += _log("Mike Williams", "LAC", 2026, wk, receptions=1, rec_yds=9, targets=2, rec_td=0)
    # A veteran back from injury: last season only.
    for wk in (16, 17, 19):
        rows += _log("Old Vet", "GB", 2025, wk, receptions=4, rec_yds=50, targets=6, rec_td=1)
    db.upsert_player_logs(conn, rows)
    return conn


SCHED_HEAD = ("game_id,season,game_type,week,gameday,away_team,away_score,home_team,home_score,"
              "location,spread_line,total_line\n")


def _schedule(extra=""):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "games.csv")
    with open(p, "w") as fh:
        fh.write(SCHED_HEAD
                 + "a,2025,REG,13,2025-11-27,GB,31,DET,24,Home,2.5,48.5\n"     # DET −2.5, GB covers, over
                 + "b,2025,REG,1,2025-09-07,DET,13,GB,27,Home,1.5,48.5\n"       # GB −1.5, GB covers, under
                 + "c,2024,REG,14,2024-12-05,GB,31,DET,34,Home,3,53\n"          # DET −3 wins by 3: push, over
                 + "d,2024,DIV,20,2025-01-18,GB,20,DET,17,Home,-1,40\n"         # GB favored 1 in the playoffs
                 + "e,2026,REG,7,2026-10-25,GB,,DET,,Home,3,52.5\n"             # tonight: not played
                 + "f,2025,REG,5,2025-10-05,CHI,10,DET,20,Home,4,44\n"          # someone else
                 + "g,2026,REG,5,2026-10-05,DET,45,ARI,21,Home,-3,47\n"         # DET away at ARI
                 + "h,2026,REG,4,2026-09-28,MIN,20,DET,23,Neutral,0,45\n"       # DET at a neutral site
                 + extra)
    return p


def _num(v, rank=None, of=32):
    return {"value": v, "rank": rank, "of": of}


def _board():
    game = {"away": "GB", "home": "DET", "date": "2026-10-25", "kickoff": "16:25",
            "spread": -3.0, "total": 52.5, "roof": "dome",
            "stadium": {"name": "Ford Field", "roof": "dome", "altitude_ft": 600},
            "weather": {"dome": True, "temp_f": 70.0, "measured": True, "forecast": False},
            "scan": {"units": {}, "method": {"teams": 32},
                     "numbers": {
                         "DET": {"games": 5, "plays_pg": _num(66.0, 7), "pace": _num(30.4, 10),
                                 "proe": _num(0.007, 9), "giveaways": _num(0.2, 1), "takeaways": _num(1.0, 23),
                                 "to_margin": _num(4, 5), "go4_rate": _num(1.0, 1),
                                 "lead_pass": _num(0.524, None, 20), "trail_pass": _num(0.763, None, 27),
                                 "counts": {"weeks": 5, "go4_opps": 4, "go4_att": 4, "go4_conv": 3,
                                            "two_pt_att": 0, "two_pt_conv": 0}},
                         "GB": {"games": 6, "plays_pg": _num(59.7, 22), "pace": _num(28.2, 3),
                                "proe": _num(-0.021, 25), "to_margin": _num(4, 5), "giveaways": _num(1.2, 16),
                                "takeaways": _num(1.8, 3),
                                "counts": {"weeks": 6, "go4_opps": 7, "go4_att": 6, "go4_conv": 4,
                                           "two_pt_att": 2, "two_pt_conv": 1}}}}}
    reads = [
        {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "read": "breakout", "label": "Breakout candidate",
         "usage": {"carry_share": 0.69, "carries_pg": 18.0}, "pro": ["Takes 69% of the carries"]},
        {"player": "Mike Williams", "team": "GB", "pos": "WR", "read": "good", "label": "Good matchup",
         "usage": {"tgt_share": 0.05, "targets_pg": 1.5}, "pro": ["A soft corner"]},
        {"player": "Old Vet", "team": "GB", "pos": "WR", "read": "good", "label": "Good matchup",
         "usage": {"tgt_share": 0.08, "targets_pg": 2.0}, "pro": ["Back from injured reserve"]},
    ]
    return {"date": "2026-W7", "built_at": "2026-10-20T12:00", "games": [game],
            "scan_reads": {"GB@DET": {"players": reads}}}


def _built(**kw):
    board = _board()
    return R.build(board["games"][0], board, names=NAMES, **kw)


def _sec(rep, key):
    return next((s for s in rep["sections"] if s["key"] == key), None)


def _blocks_text(sec) -> str:
    return json.dumps(sec, ensure_ascii=False) if sec else ""


# --- K1: form --------------------------------------------------------------------------
def test_form_reads_his_season_his_last_three_and_his_red_zone():
    board = _board()
    sched = _schedule("x,2026,REG,5,2026-10-05,DET,1,O5,2,Home,0,40\n")
    form = RD.player_form(_conn(), 2026, R.report_players(board), schedule=sched)
    g = form["Jahmyr Gibbs"]
    assert g["games"][0]["where"] == "away", "off the schedule, not the logs' home flag"
    form = RD.player_form(_conn(), 2026, R.report_players(board), schedule=_schedule())
    assert [x["week"] for x in g["games"]] == [5, 4, 3], "newest first, three of them"
    assert g["season"]["games"] == 5 and g["season"]["s"]["rush_yds"] == 400.0
    # 15 of DET's 20 carries inside the 20 are his: the short-name join and
    # the team's total.
    assert g["rz"]["rz_car"] == 15.0 and g["rz"]["team_rz_car"] == 20.0 and g["rz"]["i5_car"] == 5.0
    rep = _built(form=form)
    card = next(i for b in _sec(rep, "matchups")["blocks"] if b.get("type") == "verdicts" for i in b["items"])
    rows = dict((k, v) for k, v in card["form"])
    assert rows["This season"] == ["5 games: 88 carries, 400 yds (4.5 a carry), 1 TD; 12 catches, 80 yds"]
    assert rows["Last 3"][0] == "Wk 5 at O5: 25 carries, 120 yds, 1 TD; 4 catches, 20 yds"
    assert rows["Lately"] == ["130 yards from scrimmage a game over his last 3, up from 45 in his other 2"]
    assert rows["Red zone"] == ["15 carries inside the 20 (5 inside the 5) — 75% of DET's; "
                                "5 targets inside the 20 (0 inside the 10) — 25% of DET's"]
    text = R.to_text(rep)
    assert "      · This season: 5 games: 88 carries" in text and "      · Last 3: Wk 5 at O5:" in text


def test_two_men_of_one_name_are_told_apart_by_the_boards_team():
    form = RD.player_form(_conn(), 2026, {"Mike Williams": "NYJ"})
    assert [g["team"] for g in form["Mike Williams"]["games"]] == ["NYJ", "NYJ"]
    assert form["Mike Williams"]["season"]["s"]["rec_yds"] == 140.0
    form = RD.player_form(_conn(), 2026, {"Mike Williams": "LAC"})
    assert form["Mike Williams"]["season"]["s"]["rec_yds"] == 18.0


def test_a_man_with_no_games_this_season_shows_last_seasons_and_says_so():
    board = _board()
    form = RD.player_form(_conn(), 2026, R.report_players(board))
    vet = form["Old Vet"]
    assert "season" not in vet and vet["last_season"]["games"] == 3
    rep = _built(form=form)
    item = next(i for b in _sec(rep, "watch")["blocks"] if b.get("type") == "players"
                for i in b["items"] if i["player"] == "Old Vet")
    rows = dict((k, v) for k, v in item["form"])
    assert rows["Last season"] == ["3 games: 12 catches on 18 targets, 150 yds (50 a game), 3 TD — none yet this season"]
    # Week 19 of a 2021-on season is the wild-card round, not "week 19".
    assert rows["Last 3"][0].startswith("2025 wild-card round"), rows["Last 3"]
    # No trend and no red-zone line off a season he has not played in.
    assert "Lately" not in rows and "Red zone" not in rows


def test_a_key_players_form_is_on_his_matchup_card_not_said_again_under_watch():
    form = RD.player_form(_conn(), 2026, R.report_players(_board()))
    rep = _built(form=form)
    watch = [i for b in _sec(rep, "watch")["blocks"] if b.get("type") == "players" for i in b["items"]]
    gibbs = next(i for i in watch if i["player"] == "Jahmyr Gibbs")
    assert "form" not in gibbs
    williams = next(i for i in watch if i["player"] == "Mike Williams")
    assert williams.get("form"), "a player with no matchup card carries his own"


def test_home_and_away_come_off_the_schedule_not_the_logs():
    path = _schedule()
    assert RD.venue(2026, 5, "DET", path=path) == "away"
    assert RD.venue(2026, 5, "ARI", path=path) == "home"
    assert RD.venue(2026, 4, "DET", path=path) == "neutral"
    assert RD.venue(2026, 9, "DET", path=path) == ""


def test_the_week_label_names_playoff_rounds_and_other_seasons():
    assert R.week_label(2026, 5, 2026) == "Wk 5"
    assert R.week_label(2025, 13, 2026) == "2025 wk 13"
    assert R.week_label(2025, 19, 2026) == "2025 wild-card round"
    assert R.week_label(2025, 22, 2026) == "2025 Super Bowl"
    assert R.week_label(2019, 18, 2026) == "2019 wild-card round", "a 17-game season's week 18 was the playoffs"


# --- K4: the meetings ------------------------------------------------------------------
def test_the_meetings_are_the_two_teams_finished_games_newest_first_at_their_lines():
    ms = RD.meetings("DET", "GB", "2026-10-25", path=_schedule())
    assert [m["day"] for m in ms] == ["2025-11-27", "2025-09-07", "2025-01-18", "2024-12-05"]
    a, b, d, c = ms
    assert a["winner"] == "GB" and a["spread_home"] == -2.5 and a["covered"] == "GB" and a["ou"] == "over"
    assert b["home"] == "GB" and b["covered"] == "GB" and b["ou"] == "under"
    assert c["covered"] == "push", "DET −3 winning by 3 is a push"
    assert d["round"] == "divisional round" and d["spread_home"] == 1.0 and d["covered"] == "GB"
    assert R.meeting_line(a) == "2025 week 13 at DET: GB won 31-24 · DET −2.5, GB covered · total 48.5, over"
    assert R.meeting_line(d) == ("2024 divisional round at DET: GB won 20-17 · GB −1, GB covered · "
                                 "total 40, under")


def test_the_meetings_section_sums_them_and_the_short_version_names_the_last():
    ms = RD.meetings("DET", "GB", "2026-10-25", path=_schedule())
    rep = _built(meetings=ms)
    keys = [s["key"] for s in rep["sections"]]
    assert keys.index("facts") + 1 == keys.index("meetings")
    head = _sec(rep, "meetings")["blocks"][0]["text"]
    assert head == ("GB has won 3 of the last 4 meetings; against the spread GB is 3-0-1; "
                    "2 went over the total and 2 under."), head
    assert ("The last time they met (week 13 of 2025), the Packers won 31-24 on the road as 2.5-point "
            "underdogs; the 55 points went over the 48.5 total.") in R.to_text(rep)
    assert _sec(_built(meetings=[]), "meetings") is None


# --- K5 / K7: the play-by-play counts --------------------------------------------------
def _play(**kw):
    base = {"week": "3", "posteam": "AAA", "defteam": "BBB", "play_type": "run", "yardline_100": "50",
            "qtr": "2", "half_seconds_remaining": "600", "wp": "0.5", "down": "1", "ydstogo": "10"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_the_turnovers_and_the_coaching_calls_are_counted_where_the_call_is_the_coachs():
    plays = [
        _play(play_type="pass", interception=1, qb_dropback=1),                      # AAA gives, BBB takes
        _play(play_type="punt", down=4, fumble_lost=1, fumbled_1_team="BBB"),       # a muffed punt: BBB's
        _play(play_type="run", fumble_lost=1, fumbled_1_team="AAA"),               # AAA gives
        _play(down=4, ydstogo=1, yardline_100=40, fourth_down_converted=1),        # a go, converted
        _play(play_type="punt", down=4, ydstogo=2, yardline_100=55, punt_attempt=1),  # a kick
        _play(play_type="field_goal", down=4, ydstogo=1, yardline_100=8, field_goal_attempt=1),
        _play(down=4, ydstogo=1, yardline_100=80),                                 # his own 20: not counted
        _play(play_type="no_play", down=4, ydstogo=1, yardline_100=40),             # a penalty: not a call
        _play(down=4, ydstogo=1, yardline_100=40, wp=0.95),                        # decided: not counted
        _play(down=4, ydstogo=1, yardline_100=40, half_seconds_remaining=60),      # the clock's call
        _play(down=4, ydstogo=3, yardline_100=40),                                 # 3 to go: not short
        _play(play_type="pass", down="", two_point_attempt=1, two_point_conv_result="success",
              half_seconds_remaining=20),                                          # every try counts
        _play(score_differential=10, qb_dropback=0),                               # up two scores, a run
        _play(play_type="pass", score_differential=10, qb_dropback=1),             # up two scores, a pass
        _play(play_type="pass", score_differential=10, qb_dropback=1, half_seconds_remaining=90),  # late: out
        _play(play_type="pass", score_differential=-9, qb_dropback=1),             # down two scores
    ]
    agg = nflpbp.aggregate_pbp(plays)
    rows = {r["team"]: r for r in nflpbp.team_week_rows(agg, 2026)}
    a, b = rows["AAA"], rows["BBB"]
    assert (a["giveaways"], a["takeaways"], b["giveaways"], b["takeaways"]) == (2, 1, 1, 2)
    assert (a["go4_opps"], a["go4_att"], a["go4_conv"]) == (3, 1, 1)
    assert (a["two_pt_att"], a["two_pt_conv"]) == (1, 1)
    assert (a["lead_plays"], a["lead_pass"], a["trail_plays"], a["trail_pass"]) == (2, 1, 1, 1)
    assert set(nflpbp.TENDENCY_KEYS) <= set(db.TEAM_WEEK_COLS)
    for col in ("interception", "fumble_lost", "fumbled_1_team", "fourth_down_converted",
                "two_point_conv_result", "score_differential", "qb_dropback", "half_seconds_remaining"):
        assert col in nflpbp.NEEDED, col


def test_the_season_numbers_rank_tempo_and_turnovers_and_a_tie_shares_its_rank():
    conn = db.connect(":memory:")
    rows = []
    for t, (gv, tk, opps, att) in {"AAA": (1, 5, 4, 3), "BBB": (2, 6, 5, 1), "CCC": (0, 0, 1, 1)}.items():
        rows.append({"sport": "nfl", "season": 2026, "period": "001", "team": t, "plays": 60, "proe": 0.02,
                     "pace": 28.0, "giveaways": gv, "takeaways": tk, "go4_opps": opps, "go4_att": att,
                     "go4_conv": att, "two_pt_att": 0, "two_pt_conv": 0, "lead_plays": 30, "lead_pass": 15,
                     "trail_plays": 5, "trail_pass": 4})
    # A week written before the tendency columns: plays count, tendencies do not.
    rows.append({"sport": "nfl", "season": 2026, "period": "002", "team": "AAA", "plays": 70, "proe": 0.0,
                 "pace": 30.0})
    db.upsert_team_weeks(conn, rows)
    nums = gamescan.season_numbers(conn, 2026)
    a, b, c = nums["AAA"], nums["BBB"], nums["CCC"]
    assert a["plays_pg"]["value"] == 65.0 and a["counts"]["weeks"] == 1
    assert a["to_margin"]["value"] == 4 and b["to_margin"]["value"] == 4
    assert a["to_margin"]["rank"] == b["to_margin"]["rank"] == 1 and c["to_margin"]["rank"] == 3
    assert "go4_rate" not in c, "one fourth-and-short is not a rate"
    assert a["go4_rate"]["value"] == 0.75 and a["go4_rate"]["rank"] == 1
    assert "trail_pass" not in a, "five plays down two scores is not a pass rate"
    assert a["lead_pass"]["value"] == 0.5 and a["lead_pass"]["rank"] is None


def test_an_old_team_weeks_table_gains_the_new_columns():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "old.db")
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE team_weeks (sport TEXT, season INTEGER, period TEXT, team TEXT, plays INTEGER, "
                "proe REAL, off_epa REAL, pass_epa REAL, rush_epa REAL, def_epa REAL, pace REAL, "
                "PRIMARY KEY (sport, season, period, team))")
    raw.execute("INSERT INTO team_weeks (sport, season, period, team, plays) VALUES ('nfl', 2026, '001', 'AAA', 60)")
    raw.commit()
    raw.close()
    conn = db.connect(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(team_weeks)")}
    assert set(nflpbp.TENDENCY_KEYS) <= cols
    assert conn.execute("SELECT giveaways FROM team_weeks").fetchone()[0] is None, "an old week reads NULL"


def test_the_nightly_play_by_play_step_writes_the_team_weeks():
    assert "_pdb.upsert_team_weeks(_pc, team_week_rows(agg, season))" in MAINT
    assert "or _carries_behind or _weeks_behind:" in MAINT
    assert "giveaways IS NULL" in MAINT


def test_tempo_turnovers_and_the_coaching_calls_are_written_out():
    rep = _built()
    ident = R.to_text(rep)
    assert ("Tempo: DET runs 66 plays a game (7th-most), snaps it every 30.4 seconds with the game in the "
            "balance (10th-quickest) and throws on 0.7% more of its plays than the down, distance and score "
            "call for (9th-most in the league)") in ident
    # A bottom-half rank is read from the near end.
    assert "59.7 plays a game (11th-fewest)" in ident and "(8th-fewest in the league)" in ident
    nums = next(b for b in _sec(rep, "rankings")["blocks"] if b.get("title") == "This season's numbers")
    margin = next(r for r in nums["rows"] if r[0] == "Turnover margin")
    assert margin == ["Turnover margin", "+4 · 5th", "+4 · 5th"], margin
    calls = _blocks_text(_sec(rep, "context"))
    assert "DET went for it on 4 of 4 fourth-and-shorts (the most often) and converted 3" in calls
    assert "has not tried a two-point conversion" in calls
    assert "GB went for it on 6 of 7 fourth-and-shorts" in calls and "tried 2 two-point conversions (1 good)" in calls
    assert "passes on 52% of plays up by 8 or more and on 76% down by 8 or more" in calls
    assert ("In turnover margin this season, the Packers and the Lions are both +4 (5th), near the top of "
            "the league.") in ident


# --- K2: the practice report -----------------------------------------------------------
PRACTICE = {"rows": [
    {"player": "Jahmyr Gibbs", "team": "DET", "designation": "Questionable", "practice": "Limited",
     "injury": "Ankle", "league": 0.81, "n": 1240, "ratio": 0.93, "club": 0.7, "club_n": 30},
    {"player": "Backup Guy", "team": "GB", "designation": "Doubtful", "practice": "DNP", "injury": "Knee",
     "league": 0.2, "n": 300, "ratio": None, "club": None, "club_n": 0}],
    "measured": True, "held_out": {"holds": False}}


def test_the_practice_report_says_how_often_men_listed_the_same_way_have_played():
    rep = _built(ideas={"practice": PRACTICE})
    text = _blocks_text(_sec(rep, "injuries"))
    assert ("Jahmyr Gibbs (DET, ankle) — questionable; he was limited in practice at his last practice of the "
            "week. Players listed questionable who were limited in practice have played 81% of the time "
            "(1,240 listings), taking 93% of their usual snaps when they did") in text
    assert "own record" not in text, "the club's number waits until it holds out"
    assert "Also listed: Backup Guy (GB, doubtful)" in text
    held = dict(PRACTICE, held_out={"holds": True})
    text = _blocks_text(_sec(_built(ideas={"practice": held}), "injuries"))
    assert "With DET's own record of who it lists and who plays folded in: 70%" in text


# --- K3: role changes ------------------------------------------------------------------
ROLE = {"rows": [{"player": "Mike Williams", "team": "GB", "share": "tgt", "label": "Target share",
                  "before": 0.08, "after": 0.21, "games_ago": 3, "changed": 0.82, "holds": False}]}


def test_a_role_change_is_his_share_before_and_since_called_a_reading_until_it_holds():
    text = _blocks_text(_sec(_built(ideas={"role": ROLE}), "watch"))
    assert ("Mike Williams (GB): target share up to 21% over his last 3 games, from 8% before — the detector "
            "is 82% sure the change is real") in text
    assert "this is a reading" in text and "Roles on the move" in text
    held = {"rows": [dict(ROLE["rows"][0], holds=True)]}
    assert "so the board reads it" in _blocks_text(_sec(_built(ideas={"role": held}), "watch"))


def test_the_ideas_views_are_read_from_the_builds_ideas_file():
    data = {"sections": {
        "practice": {"listed": {"jahmyrgibbs": dict(PRACTICE["rows"][0])}, "measured": True,
                     "held_out": {"holds": False}},
        "role": {"players": {"Mike Williams": {"team": "GB", "opponent": "DET", "reads": {
            "tgt": {"flag": True, "games_ago": 3, "before": 0.08, "after": 0.21, "changed": 0.82,
                    "verdict": {"holds": True}}}}}}}}
    got = R.ideas_for(data, "DET", "GB")
    assert got["practice"]["rows"][0]["player"] == "Jahmyr Gibbs"
    assert got["role"]["rows"][0]["holds"] is True


# --- K6: the kicking air ---------------------------------------------------------------
def _kick_board(weather, stadium, roof=""):
    b = _board()
    g = b["games"][0]
    g["weather"], g["stadium"], g["roof"] = weather, stadium, roof
    return b, g


def test_the_kicking_air_is_said_only_where_it_is_real():
    # Indoors at sea level: every other building's air, so nothing.
    b, g = _kick_board({"dome": True, "temp_f": 70, "measured": True}, {"altitude_ft": 600}, "dome")
    k = kickphysics.conditions(g)
    assert not R.kick_lines(R.Ctx(g, b, names=NAMES, ideas={"kicks": k}))
    # Outdoors with a real forecast: cold air is denser.
    b, g = _kick_board({"temp_f": 20, "measured": True, "forecast": True, "wind_mph": 5},
                       {"altitude_ft": 600})
    g["home"] = "GB"
    k = kickphysics.conditions(g)
    lines = R.kick_lines(R.Ctx(g, b, names=NAMES, ideas={"kicks": k}))
    assert lines and lines[0].startswith("Kicking air (20°F): ") and "denser than air at sea level" in lines[0]
    # The build's placeholder is never the game's air.
    b, g = _kick_board({"temp_f": 60, "measured": False, "forecast": False}, {"altitude_ft": 600})
    g["home"] = "GB"
    assert not R.kick_lines(R.Ctx(g, b, names=NAMES, ideas={"kicks": kickphysics.conditions(g)}))
    # A mile up, even without a forecast.
    b, g = _kick_board({"temp_f": 60, "measured": False}, {"altitude_ft": 5280})
    g["home"] = "DEN"
    lines = R.kick_lines(R.Ctx(g, b, names=NAMES, ideas={"kicks": kickphysics.conditions(g)}))
    assert "5,280 feet up" in lines[0] and "thinner than air at sea level, so kicks carry noticeably farther" in lines[0]


def test_abroad_the_kicking_air_is_the_host_citys():
    g = {"home": "DEN", "away": "KC", "weather": {"temp_f": 60, "measured": True},
         "stadium": {"abroad": True, "altitude_ft": 0}}
    assert kickphysics.conditions(g)["altitude_ft"] == 0.0, "Denver's home game in London is at sea level"
    g["stadium"] = {"altitude_ft": 5280}
    assert kickphysics.conditions(g)["altitude_ft"] == 5280.0


# --- K8: Ask reads it -----------------------------------------------------------------
def test_ask_reads_the_report_for_a_named_game_and_keeps_it_short():
    from engine import askbot as AB
    from engine import served
    board = _board()
    form = RD.player_form(_conn(), 2026, R.report_players(board), schedule=_schedule())
    board["game_reports"] = [R.build(board["games"][0], board, names=NAMES, form=form,
                                     meetings=RD.meetings("DET", "GB", "2026-10-25", path=_schedule()),
                                     ideas={"practice": PRACTICE, "role": ROLE})]
    facts = AB.game_facts(board, board["games"][0], scan=True)["game_report"]
    assert facts["last_meetings"][0].startswith("GB has won 3 of the last 4 meetings")
    assert any(x.startswith("Tempo: DET runs 66 plays a game") for x in facts["tempo"])
    assert facts["practice_report"][0].startswith("Jahmyr Gibbs (DET, ankle) — questionable")
    assert facts["roles_on_the_move"][0].startswith("Mike Williams (GB): target share up to 21%")
    assert facts["player_form"]["Jahmyr Gibbs"][0].startswith("This season: 5 games: 88 carries")
    assert any("went for it on 4 of 4" in x for x in facts["coaching_and_schedule"])
    # Held under its cap: the players' form gives way first.
    many = {f"P{i}": ["This season: " + "x" * 300] for i in range(40)}
    big = dict(board["game_reports"][0])
    big["sections"] = big["sections"] + [{"key": "watch", "title": "w", "blocks": [
        {"type": "players", "items": [{"player": k, "form": [["This season", v]]} for k, v in many.items()]}]}]
    trimmed = AB.report_facts(dict(board, game_reports=[big]), board["games"][0])
    assert len(json.dumps(trimmed, ensure_ascii=False)) <= AB.REPORT_CHARS
    # A game with no report reads nothing; Ask's copy of the board keeps the reports.
    assert AB.report_facts({"game_reports": []}, board["games"][0]) == {}
    assert "game_reports" in served.for_ask({"game_reports": [1], "player_stats": {}})
    assert "game_report is our written report on it" in AB.SYSTEM
    assert "It carries no prop picks: never turn a line of it into one." in AB.SYSTEM


# --- the build and the page ------------------------------------------------------------
def test_attach_reads_the_logs_and_never_raises_without_them():
    board = _board()
    line = R.attach(board, conn=_conn(), ideas={})
    assert "form for 3 player(s)" in line, line
    rep = board["game_reports"][0]
    assert any(i.get("form") for b in _sec(rep, "matchups")["blocks"] if b.get("type") == "verdicts"
               for i in b["items"])
    board = _board()
    bad = sqlite3.connect(":memory:")                       # no tables at all
    assert R.attach(board, conn=bad, ideas={}).startswith("Game reports: 1 game(s)")


def test_nothing_new_carries_a_prop_pick():
    form = RD.player_form(_conn(), 2026, R.report_players(_board()))
    rep = _built(form=form, meetings=RD.meetings("DET", "GB", "2026-10-25", path=_schedule()),
                 ideas={"practice": PRACTICE, "role": ROLE})
    text = R.to_text(rep)
    for mark in ("OVER ", "UNDER ", " -110", "+333", "model_prob", "anytime_td", "lean"):
        assert mark not in text, mark


def test_the_page_draws_his_form():
    assert ".gr-form-row { display: grid; grid-template-columns: 6.5em minmax(0, 1fr);" in REPORT_CSS
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    form = RD.player_form(_conn(), 2026, R.report_players(_board()), schedule=_schedule())
    rep = _built(form=form)
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
        "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
        " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
        " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>' };"
        "vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
        f"process.stdout.write(ctx.window.QBReport.html({json.dumps(rep, ensure_ascii=False)}, null));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    html = out.stdout
    assert '<dl class="gr-form">' in html and "<dt>This season</dt>" in html and "<dt>Red zone</dt>" in html
    assert "Wk 5 at O5: 25 carries, 120 yds, 1 TD; 4 catches, 20 yds" in html
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in html, bad


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
