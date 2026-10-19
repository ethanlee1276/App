"""The game report: every NFL game written out like the research reports (engine/gamereport).

Ethan, 2026-10-19: "I want our board too kinda look like that when you
click on a game. I want a full layed out detailed explanation for every
nfl game just like how the report is. Obv keep out the prop picks but
everything else it valuable information too have typed out so the user
can just read it."

What these hold: the report comes in the outside reports' order; it never
carries a prop pick (no line, price or probability on a player, however
the board spelled it); every number in it is the board's own; a missing
input drops its sentence instead of printing a placeholder; the build's
weather placeholder is never written as conditions; it is paid and kept out
of the light copy; the build hangs it last and a broken board never stops
the build; and the game page draws it, steps the scan and the plan's
narrative steps aside, and locks it for a reader without the subscription.

ITS PAGE CODE LOADS ON FIRST USE (js/report.js, css/report.css), like the
Toolbox and the parlay grader: the report added 1.2 KB gzipped to app.js,
over the first paint's budget, and only a game page ever draws it. Until it
lands a loading line stands in; if it fails the page draws as it did before
the report existed.

Run directly: `python3 tests/test_the_game_report_reads_like_the_research.py`
"""
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamereport as R                                 # noqa: E402
from engine import gate                                             # noqa: E402
from engine import lightboard                                       # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
REPORT_CSS = open(os.path.join(ROOT, "web", "css", "report.css"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()

NAMES = {"GB": "Packers", "DET": "Lions"}

#: Numbers a prop pick carries, planted where the board keeps them. None
#: may reach the report in any spelling.
PICK_MARKS = ("17.25", "-137", "+333", "43.21", "0.4321", "SENTINEL", "Carries OVER", "anytime_td")


def _unit(value, rank, now=None):
    return {"value": value, "rank": rank, "now_rank": now or rank}


def _units(team, off_ranks, def_ranks, games=5, blend=0.45, changed=None):
    keys = ("overall", "passing", "rushing", "success", "explosive", "pressure", "ypc",
            "third_down", "redzone", "short", "mid", "deep")
    vals = {"overall": 0.05, "passing": 0.19, "rushing": -0.18, "success": 0.44, "explosive": 0.094,
            "pressure": 0.16, "ypc": 3.4, "third_down": 0.43, "redzone": 0.62, "short": 5.4,
            "mid": 11.2, "deep": 13.7}
    return {"games": games, "blend": blend, "changed": changed or {},
            "off": {k: _unit(vals[k], r) for k, r in zip(keys, off_ranks)},
            "def": {k: _unit(vals[k], r) for k, r in zip(keys, def_ranks)}}


def _read(player, team, pos, read, usage, pro=(), con=(), notes=()):
    return {"player": player, "team": team, "opp": "DET" if team == "GB" else "GB", "pos": pos,
            "read": read, "label": dict(R.VERDICT).get(read, ("", ""))[1].title(),
            "pro": list(pro), "con": list(con), "notes": list(notes), "usage": usage,
            "headshot": "", "lean": ["rush_att", "anytime_td"],
            "no_pick": {"refused": "SENTINEL no-pick reason", "best": None},
            "td": {"model_prob": 0.4321, "odds": 333, "rz_chances": 2.4, "why": ["SENTINEL td why"]}}


def _board():
    game = {
        "away": "GB", "home": "DET", "date": "2026-10-25", "kickoff": "16:25",
        "spread": -3.0, "total": 52.5, "home_ml": -166, "away_ml": 140, "favorite": "DET",
        "roof": "dome", "surface": "fieldturf", "neutral_site": False,
        "stadium": {"name": "Ford Field", "roof": "dome", "surface": "turf", "altitude_ft": 600,
                    "plays": "Fixed dome: identical conditions every week, no weather read needed."},
        "weather": {"dome": True, "temp_f": 70.0, "wind_mph": 0.0, "measured": True, "forecast": False},
        "conditions": {"why": ["Dome game — no weather impact on the passing game"]},
        "sim": {"trials": 4000, "p_home_win": 0.58, "cover": 0.48, "cover_push": 0.063, "over": 0.503,
                "one_score": 0.448, "blowout": 0.356,
                "margin_hist": [0.2008, 0.1703, 0.209, 0.1985, 0.1237, 0.0978]},
        "line_open": {"spread_home": -2.5, "spread_move": -0.5, "total": 51.0, "total_move": 1.5},
        "crowd": {"kalshi": 0.61, "polymarket": 0.6, "books": 0.6, "gap_pts": 0.5, "kalshi_over": 0.52},
        "money": {"ml": {"home": 0.7, "away": 0.3, "usd": 52000, "n": 300},
                  "total": {"over": 0.62, "under": 0.38, "usd": 9000, "n": 80}, "venues": ["Kalshi"]},
        "scan": {
            "units": {"GB": _units("GB", (10, 4, 30, 14, 12, 22, 29, 8, 15, 23, 5, 7),
                                   (15, 15, 18, 18, 2, 13, 6, 21, 25, 10, 15, 2),
                                   games=6, blend=0.5, changed={"def": ["new defensive coordinator (Jonathan Gannon)"]}),
                      "DET": _units("DET", (3, 5, 14, 11, 7, 25, 10, 25, 3, 7, 1, 16),
                                    (24, 22, 24, 16, 26, 5, 23, 26, 30, 11, 21, 28))},
            "edges": [{"unit": "passing", "label": "passing game", "off": "GB", "def": "DET",
                       "off_rank": 4, "def_rank": 22, "gap": 18},
                      {"unit": "pressure", "label": "pass protection vs pass rush", "off": "GB", "def": "DET",
                       "off_rank": 22, "def_rank": 5, "gap": -17}],
            "coverage": {
                "DET": {"corners": [{"name": "D.J. Reed", "spot": "LCB", "targets": 28, "rating": 126.5,
                                     "yds_per_tgt": 11.3, "td": 2},
                                    {"name": "Roger McCreary", "spot": "NB", "targets": 32, "rating": 104.4,
                                     "yds_per_tgt": 8.3, "td": 2}],
                        "missing": [], "weakest": "D.J. Reed"},
                "GB": {"corners": [{"name": "Brandon Cisse", "spot": "RCB", "targets": 17, "rating": 142.8,
                                    "yds_per_tgt": 11.4, "td": 2}], "missing": [], "weakest": "Brandon Cisse"}},
            "scheme": {"GB": {"zone": 0.788, "man": 0.212, "mofo": 0.468, "blitz": 0.219, "pressure": 0.307,
                              "shells": {"COVER_3": 0.319, "COVER_2": 0.288, "COVER_1": 0.185}},
                       "DET": {"zone": 0.574, "man": 0.426, "blitz": 0.289, "pressure": 0.318,
                               "shells": {"COVER_1": 0.286}}},
            "scheme_season": 2025,
            "charting": {"season": 2026, "weeks": 5,
                         "offense": {"GB": {"play_action_rate": 0.203, "motion_rate": 0.624}},
                         "defense": {"GB": {"blitz_rate": 0.335, "heavy_box_rate": 0.043, "light_box_rate": 0.56}}},
            "rush": {"DET": [{"name": "Aidan Hutchinson", "pressures": 15, "sacks": 4.0},
                             {"name": "Alim McNeill", "pressures": 10, "sacks": 1.0}],
                     "GB": [{"name": "Lukas Van Ness", "pressures": 9, "sacks": 2.5}]},
            "line_out": {"GB": ["Zach Tom (RT)"], "DET": []},
            "injuries": [{"team": "GB", "player": "Zach Tom", "position": "T", "status": "OUT",
                          "opens": "GB's protection weakens against the 5th pass rush"},
                         {"team": "DET", "player": "Sam LaPorta", "position": "TE", "status": "QUESTIONABLE",
                          "opens": "If he sits — 19% of DET's targets to share out"}],
            "pulled": ["Isaac TeSlaa"],
            "redzone": {"DET": {"off": 11.98, "def": 9.83, "off_rel": 0.299, "def_rel": 0.059},
                        "GB": {"off": 10.02, "def": 10.68, "off_rel": 0.087, "def_rel": 0.151}},
            "numbers": {
                "DET": {"games": 5, "pts_for": {"value": 32.8, "rank": 2}, "rz_off": {"value": 0.8, "rank": 3},
                        "rz_def": {"value": 0.8, "rank": 30}, "sacks": {"value": 4.0, "rank": 1},
                        "run_rate": {"value": 0.386, "rank": None}},
                "GB": {"games": 6, "pts_for": {"value": 21.167, "rank": 23}, "rz_off": {"value": 0.538, "rank": 25},
                       "rz_def": {"value": 0.696, "rank": 23}, "sacks": {"value": 2.5, "rank": 16},
                       "run_rate": {"value": 0.339, "rank": None}}},
            "method": {"teams": 32, "opponent_adjusted": True},
        },
    }
    reads = [
        _read("Jahmyr Gibbs", "DET", "RB", "breakout",
              {"carry_share": 0.692, "carries_pg": 18.0, "tgt_share": 0.176, "snap_pct": 0.72},
              pro=["Takes 69% of the carries (18 a game)", "GB gives up the 2nd-most touchdowns to running backs (1.7 a game)",
                   "The lines expect DET to score about 28 (−3 at home, total 52.5)"],
              notes=["Usage is 55% this season, 45% last season — last season he had 55% of the carries",
                     "Tracking: +0.53 rushing yards over expected a carry (13th of 49 RBs)"]),
        _read("Amon-Ra St. Brown", "DET", "WR", "neutral",
              {"tgt_share": 0.314, "targets_pg": 10.8, "snap_pct": 0.87},
              pro=["Commands 31% of the targets (10.8 a game)",
                   "The lines expect DET to score about 28 (−3 at home, total 52.5)"],
              con=["GB gives up the 6th-fewest passing yards (209 a game)"],
              notes=["Brandon Cisse (RCB) has allowed a 143 passer rating on 17 targets"]),
        _read("Jared Goff", "DET", "QB", "neutral", {"snap_pct": 0.99, "carry_share": 0.06},
              pro=["The lines expect DET to score about 28 (−3 at home, total 52.5)"],
              notes=["Charted: 2 interception-worthy throws on 191 attempts (1%)"]),
        _read("Christian Watson", "GB", "WR", "good", {"tgt_share": 0.213, "targets_pg": 6.9, "snap_pct": 0.75},
              pro=["DET gives up the 1st-most passing yards (320 a game)"]),
        _read("Matthew Golden", "GB", "WR", "tough", {"tgt_share": 0.196, "targets_pg": 6.6, "snap_pct": 0.7},
              pro=["DET gives up the 1st-most passing yards (320 a game)"],
              con=["Only 4 catches in his last 2 games"]),
        _read("Brock Wright", "DET", "TE", "tough", {"tgt_share": 0.058, "targets_pg": 1.9},
              con=["Only 6% of the targets so far"]),
    ]
    micro = [{"player": "Jahmyr Gibbs", "team": "DET", "market": "rush_att", "market_label": "Carries",
              "side": "OVER", "line": 17.25, "odds": -137, "prob": 0.4321, "read": "breakout"}]
    return {
        "date": "2026-10-25", "built_at": "2026-10-19T22:09",
        "games": [game],
        "scan_reads": {"GB@DET": {"players": reads, "microscope": micro}},
        "game_plans": [{"away": "GB", "home": "DET",
                        "script": {"archetype": "Everyone eats", "confidence": "moderate"},
                        "steps": [{"key": "line", "lines": ["DET by 3 at 52.5: …",
                                                             "DET favored in a shootout — everyone eats"]},
                                  {"key": "fits", "rows": [{"player": "Jahmyr Gibbs", "market": "rush_att",
                                                            "line": 17.25, "odds": -137}]}]}],
        "most_likely": [{"player": "Jahmyr Gibbs", "market": "rush_att", "line": 17.25, "odds": -137,
                         "model_prob": 0.4321}],
        "fatigue": {"teams": {"GB": {"rest_days": 7, "rest_band": "normal week",
                                     "notes": ["Rest deficit: 7 days to the opponent's 14"]},
                              "DET": {"rest_days": 14, "rest_band": "off a bye",
                                      "notes": ["Off a bye: 14 days of rest and two weeks of prep",
                                                "Rest edge: 14 days to the opponent's 7"]}}},
        "playoff_picture": {"teams": {"GB": {"wins": 4, "losses": 2, "ties": 0, "status": "in the hunt"},
                                      "DET": {"wins": 3, "losses": 2, "ties": 0, "status": "in the hunt"}}},
        "team_recent": {"DET": [{"opponent": "ARI", "home": False, "scored": 45.0, "allowed": 21.0, "won": True}],
                        "GB": [{"opponent": "DAL", "home": True, "scored": 23.0, "allowed": 13.0, "won": True}]},
        "qb_changes": [{"team": "PHI", "headline": "Someone else's quarterback change"}],
        "injury_status": {"asked": True, "applied": True, "total": 40},
        "data_freshness": {"behind": []},
    }


ALLOWED = {"DET": {"te_rec_yds": {"pg": 109.0, "league": 55.0, "rank": 1, "of": 32, "games": 5},
                   "rb_rush_yds": {"pg": 70.0, "league": 95.0, "rank": 30, "of": 32, "games": 5}},
           "GB": {"rb_td": {"pg": 1.7, "league": 0.9, "rank": 2, "of": 32, "games": 6}}}


def _report(board=None, **kw):
    board = board or _board()
    return R.build(board["games"][0], board, allowed=kw.pop("allowed", ALLOWED), names=NAMES, **kw)


def _text(report) -> str:
    return json.dumps(report, ensure_ascii=False)


def test_the_report_comes_in_the_research_reports_order():
    rep = _report()
    keys = [s["key"] for s in rep["sections"]]
    assert keys == ["short", "facts", "market", "rankings", "identity", "injuries", "matchups",
                    "trenches", "redzone", "context", "scripts", "watch", "weather", "before"], keys
    assert rep["title"] == "Packers at Lions" and rep["game"] == "GB@DET"
    assert rep["words"] > 400 and rep["minutes"] >= 2
    text = R.to_text(rep)
    assert text.index("THE SHORT VERSION") < text.index("WHO'S GUARDING WHO") < text.index("BEFORE KICKOFF")


def test_no_prop_pick_reaches_the_report_however_the_board_spelled_it():
    """The microscope's line and price, the read's touchdown chance and
    price, its leaning markets, its no-pick reason, the game plan's plays
    and the Most Likely rows are all on this board, each with planted
    numbers. Not one of them is in the report."""
    text = _text(_report())
    for mark in PICK_MARKS + ("43.2%",):
        assert mark not in text, mark


def test_every_number_is_the_boards_own():
    rep = _report()
    text = R.to_text(rep)
    # The lines: −3 at 52.5 implies 27.75 and 24.75; −166/+140 is 60% with the cut out.
    assert "DET at about 27.8 points and GB at about 24.8" in text
    assert "DET wins 60% of the time once the book's cut is taken out" in text
    # The opener and the move; the crowd and the money.
    assert "opened at DET \u22122.5 and has moved 0.5 points toward DET" in text
    assert "The total opened at 51 and is up 1.5" in text
    assert "DET at 61% on Kalshi and DET at 60% on Polymarket" in text
    assert "moneyline: 70% of the money on DET ($52,000 traded)" in text
    assert "Moneyline: DET \u2212166, GB +140" in text
    # The units, as the scan ranked them, and the edge column on the bar.
    tables = [b for s in rep["sections"] if s["key"] == "rankings" for b in s["blocks"] if b["type"] == "table"]
    gb_off = next(t for t in tables if t["title"] == "Packers offense vs Lions defense")
    passing = next(r for r in gb_off["rows"] if r[0] == "Pass EPA")
    assert passing == ["Pass EPA", "+0.19 · 4th", "+0.19 · 22nd", "GB"], passing
    rushing = next(r for r in gb_off["rows"] if r[0] == "Rush EPA")
    assert rushing == ["Rush EPA", "\u22120.18 · 30th", "\u22120.18 · 24th", "—"], rushing
    pressure = next(r for r in gb_off["rows"] if r[0] == "Pressure")
    assert pressure[3] == "DET", pressure
    # The simulator's six buckets, home by 15+ first.
    sims = [b for s in rep["sections"] if s["key"] == "scripts" for b in s["blocks"] if b["type"] == "table"]
    assert sims[0]["rows"][0] == ["DET by 15+", "20%"] and sims[0]["rows"][-1] == ["GB by 15+", "10%"]
    assert "covered −3 in 48% (a push in 6%)" in text
    # The corners, the rush, the red zone, the funnels.
    assert "D.J. Reed (LCB) — 126.5 passer rating allowed on 28 targets, 11.3 yards a target, 2 touchdowns" in text
    assert "Aidan Hutchinson (15 pressures, 4 sacks)" in text and "Alim McNeill (10 pressures, 1 sack)" in text
    assert "DET scores a touchdown on 80% of its red-zone trips this season (3rd of 32)" in text
    assert "tight ends — the 1st-most receiving yards (109 a game)" in text
    assert "running backs on the ground — the 3rd-fewest rushing yards (70 a game)" in text
    assert "Expected red-zone chances" not in text or "about 2.4 a game" in text


def test_a_shared_reason_is_said_once_and_his_share_of_the_work_is_his_line():
    rep = _report()
    matchups = next(s for s in rep["sections"] if s["key"] == "matchups")
    shared = [b["text"] for b in matchups["blocks"] if b["type"] == "p" and b["text"].startswith("Across DET")]
    assert shared and "The lines expect DET to score about 28" in shared[0], shared
    det = [v for b in matchups["blocks"] if b["type"] == "verdicts" for v in b["items"] if v["team"] == "DET"]
    gibbs = next(v for v in det if v["player"] == "Jahmyr Gibbs")
    assert gibbs["label"] == "FAVORABLE — breakout candidate" and gibbs["verdict"] == "favorable"
    assert gibbs["role"].startswith("69% of the carries (18 a game)")
    assert not any("The lines expect" in w or "of the carries" in w for w in gibbs["why"]), gibbs["why"]
    assert not any("Usage is" in w for v in det for w in v["why"])
    # A depth tight end with 6% of the targets is not a key player.
    assert "Brock Wright" not in [v["player"] for v in det]


def test_a_missing_input_drops_its_sentence_never_prints_a_placeholder():
    board = _board()
    g = board["games"][0]
    for k in ("sim", "line_open", "crowd", "money", "scan", "home_ml", "away_ml"):
        g.pop(k, None)
    board.pop("scan_reads")
    board.pop("game_plans")
    rep = _report(board, allowed={})
    keys = [s["key"] for s in rep["sections"]]
    for gone in ("rankings", "matchups", "trenches", "redzone", "scripts", "watch", "identity"):
        assert gone not in keys, (gone, keys)
    text = _text(rep)
    for junk in ("None", "nan", "null", "undefined", "()", " ,"):
        assert junk not in text, junk
    assert "No sportsbook moneyline was on the board" in text


def test_the_builds_weather_placeholder_is_never_written_as_conditions():
    board = _board()
    g = board["games"][0]
    g.update(roof="outdoors", stadium={"name": "Lambeau Field", "plays": "Open air, lake winds."},
             weather={"dome": False, "temp_f": 60.0, "wind_mph": 6.0, "measured": False, "forecast": False},
             conditions={"why": ["Outdoors, no forecast pulled for this game — weather is left out of the number"]})
    text = R.to_text(_report(board))
    assert "60°F" not in text and "6 mph" not in text
    assert "no forecast pulled" in text
    g["weather"] = {"dome": False, "temp_f": 41.0, "wind_mph": 17.0, "wind_dir": "NW", "measured": True,
                    "forecast": True, "precip_chance": 0.3}
    text = R.to_text(_report(board))
    assert "Forecast for kickoff: 41°F, wind 17 mph from the NW, 30% chance of rain" in text


def test_the_injury_report_is_named_when_it_was_not_read():
    board = _board()
    board["games"][0]["scan"]["injuries"] = []
    board["games"][0]["scan"]["line_out"] = {}
    board["games"][0]["scan"]["pulled"] = []
    board["injury_status"] = {"asked": False, "applied": False, "total": 0}
    assert "The injury report was not read for this build" in R.to_text(_report(board))
    board["injury_status"] = {"asked": True, "applied": True, "total": 31}
    assert "Neither team lists a starter or a featured player" in R.to_text(_report(board))


def test_the_same_fact_is_not_said_twice():
    text = R.to_text(_report())
    assert "Rest deficit" not in text and "DET: Rest edge: 14 days to the opponent's 7" in text
    assert text.count("Brandon Cisse (RCB) has allowed") == 0, "the corner's line says it once"
    assert "Someone else's quarterback change" not in text


def test_it_is_paid_and_stays_out_of_the_light_copy():
    assert R.KEY == "game_reports" and "game_reports" in gate.PAID_KEYS
    board = _board()
    R.attach(board, allowed=ALLOWED)
    assert board["game_reports"]
    sealed = gate.redact(copy.deepcopy(board), "recommendations.json")
    assert "game_reports" not in sealed or not sealed["game_reports"]
    assert (sealed.get("locked") or {}).get("game_reports")
    assert "game_reports" in lightboard.DROP_TOP
    assert "game_reports" not in lightboard.light(board, "nfl")


def test_attach_never_raises_and_the_build_hangs_it_last():
    board = {"date": "2026-10-25", "games": [{"away": "GB", "home": "DET", "scan": "not a dict"}, None, 7]}
    line = R.attach(board)
    assert isinstance(line, str)
    assert "_greport.attach(result, allowed=_allowed, season=args.season)" in BUILD
    assert BUILD.index("_lo.attach_to_board(result") < BUILD.index("_greport.attach(") \
        < BUILD.index("gate.publish(result, args.out)")


def test_the_box_command_prints_a_game():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "board.json")
    board = _board()
    R.attach(board, allowed=ALLOWED)
    with open(path, "w") as fh:
        json.dump(board, fh)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert R.main(["--board", path, "--game", "det"]) == 0
    assert "THE SHORT VERSION" in out.getvalue() and "GB@DET" in out.getvalue()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert R.main(["--board", path]) == 0
    assert "GB@DET" in out.getvalue()


def test_the_game_page_draws_it_and_steps_the_others_aside():
    for needle in ("function gameReportHTML(g, extras)", "function loadReport()",
                   "d.locked && d.locked.game_reports",
                   '["gp-sec-report", "Game report"]',
                   'gamePlanHTML(g, report ? { skip: ["line", "out", "matchup", "watch"] } : null)',
                   '${report ? "" : matchupScanHTML(g) || mlbScanHTML(g) || nhlScanHTML(g)}',
                   "simCard && !report",
                   '.gp-jump [data-jump], .gr-toc [data-jump]'):
        assert needle in APP, needle
    js = open(REPORT_JS, encoding="utf-8").read()
    # A player in the report opens his player page, never a bet.
    assert 'data-open="player:' in js and "likelyOpen" not in js and "prop:" not in js
    for rule in (".gr-card", ".gr-sec", ".gr-table-wrap { margin: 12px 0; overflow-x: auto; }", ".gr-person"):
        assert rule in REPORT_CSS, rule


def test_its_page_code_loads_on_first_use_and_a_failed_load_falls_back():
    loader = APP[APP.index("function loadReport()"):APP.index("function gameReportHTML(g, extras)")]
    assert 'css.href = "css/report.css"' in loader and 's.src = "js/report.js"' in loader
    # Both files, not the script alone: drawn before its rules land, the
    # report would flash unstyled.
    assert "let left = 2;" in loader and "css.onload" in loader and "s.onload" in loader
    # A failure (or a script that defines nothing) is final for the visit,
    # and the page draws without the report — no loading line forever, no
    # loop of loads.
    assert "if (!ok || !window.QBReport) _grFailed = true;" in loader
    getter = APP[APP.index("function gameReportFor(g)"):APP.index("function loadReport()")]
    assert "if (_grFailed) return null;" in getter
    draw = APP[APP.index("function gameReportHTML(g, extras)"):APP.index("function matchupScanHTML(g)")]
    assert "if (window.QBReport) return window.QBReport.html(r, extras);" in draw
    assert 'state.view === "game" && state.gameId === id' in draw, "it redraws only the game it loaded for"
    # Nothing of it rides the first paint.
    index = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    sw = open(os.path.join(ROOT, "web", "sw.js"), encoding="utf-8").read()
    assert 'src="js/report.js"' not in index and "report.css" not in index
    assert "/js/report.js" not in sw
    assert ".gr-" not in CSS, "the report's rules live in css/report.css"
    assert "function grBlockHTML" not in APP and "GR_TONE" not in APP


def test_the_module_draws_a_real_report():
    """The engine's own report, drawn by js/report.js with app.js's
    helpers stubbed: every section, the tables, the players' doors and
    the subscription teaser — and no "undefined" or "[object" anywhere."""
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    rep = _report()
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
        "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
        " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
        " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>' };"
        "vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
        "const R = ctx.window.QBReport;"
        f"const rep = {json.dumps(rep, ensure_ascii=False)};"
        "process.stdout.write(JSON.stringify({full: R.html(rep, {scripts: '<div id=simcard></div>'}),"
        " locked: R.html(null, null)}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout)
    full = got["full"]
    for sec in rep["sections"]:
        assert f'id="gr-{sec["key"]}"' in full, sec["key"]
        assert f'data-jump="gr-{sec["key"]}"' in full, sec["key"]
    assert full.count("<table") >= 2 and 'data-open="player:' in full
    # The simulation card takes the place of the scripts table.
    scripts = full[full.index('id="gr-scripts"'):]
    scripts = scripts[:scripts.index("</section>")]
    assert "id=simcard" in scripts and "<table" not in scripts
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in full, bad
    assert "part of the subscription" in got["locked"] and "<table" not in got["locked"]
    assert f"about {rep['minutes']} min to read" in full and "min to read" not in got["locked"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
