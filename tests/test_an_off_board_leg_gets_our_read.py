"""A leg no board carries gets our own read; a weak leg gets better legs.

Ethan, 2026-10-13, on "Josh Allen Over 5.5 Carries — NOT ON OUR BOARD":
"first we need too offer better legs too replace legs with if needed. And
two, for picks not on our board ... use every single too we have available
... put it into the game script and see if it fits or run our offense and
defense stats against the props ... whatever we do too see if a most likely
pick fits the board, we would do too whatever pick is not on our board ...
We can't just not give the user information on a prop since it's not on
our board".

What is pinned, offline, on a history database built here:

  * THE READ (engine/slipread): the board's own model per sport, run on a
    prop it never built — football's generic engine with the defence rated
    from the same database (this season shrunk toward last), the game card's
    spread, total and weather; basketball's Scalpy projection (split out of
    evaluate_prop with no change to it); hockey's ice time × rate; baseball's
    park and starter; a scorer through the touchdown model;
  * WHO HE IS: the slip's name, else the one man the initial and surname fit,
    never a guess between two; a thin season topped up from last season and
    said so; too few games and no number, as before;
  * WHAT IT ASKS: the four Most Likely checks and the tier they earn, the
    script read for this side, a defence the model does not use shown and
    said to be outside the number, no market ever made of the proxy line;
  * BETTER LEGS (slipgrade.replacements): the board's own picks in the game,
    priced as legs, the ticket re-run with each in place — never a pair the
    parlay engine would not build, never one already on the ticket, never
    one that leaves the ticket worse, never for a game under way;
  * THE PAGE (js/slip.js): the read's tag, a refusal said, the better legs.
"""
import contextlib
import datetime as dt
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import askbot as AB                                   # noqa: E402
from engine import db as DB                                       # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import slipread as SR                                 # noqa: E402

SLIP_JS = ROOT / "web" / "js" / "slip.js"
# The journal's record table is the box's; here it is empty unless a test
# hands one in, so nothing reads or writes data/ledger.db.
_JOURNAL_RECORD = SR._record
SR._record = lambda league: {}


def _row(sport, season, period, player, team, opp, pos, market, value, gid=None):
    return {"sport": sport, "season": season, "period": period, "game_id": gid or f"{team}-{period}",
            "player": player, "team": team, "opponent": opp, "position": pos, "home": 1,
            "market": market, "value": value}


NFL_TEAMS = ["BUF", "MIA", "NYJ", "NE", "KC", "LV", "DEN", "LAC"]


def _nfl_db(weeks_now=5, allen_now=True, soft_mia=False, extra=()) -> tuple:
    """A two-season NFL history: a quarterback and a back on every team,
    Josh Allen running 6-11 times a game. ``soft_mia`` makes Miami give up
    twice the rushing to backs."""
    path = str(_SANDBOX / f"nfl_{random.random():.12f}.db")
    conn = DB.connect(path)
    rng = random.Random(7)
    rows = []
    for season in (2025, 2026):
        weeks = range(1, 18) if season == 2025 else range(1, weeks_now + 1)
        for wk in weeks:
            p = f"{wk:03d}"
            for i, t in enumerate(NFL_TEAMS):
                j = (i + wk) % len(NFL_TEAMS)
                opp = NFL_TEAMS[j] if NFL_TEAMS[j] != t else NFL_TEAMS[(i + 1) % len(NFL_TEAMS)]
                qb = "Josh Allen" if t == "BUF" else f"QB {t}"
                if qb == "Josh Allen" and season == 2026 and not allen_now:
                    pass
                else:
                    att = rng.randint(28, 40)
                    car = rng.randint(6, 11) if t == "BUF" else rng.randint(1, 5)
                    for m, v in (("pass_att", att), ("pass_yds", rng.randint(180, 320)), ("pass_cmp", int(att * .65)),
                                 ("carries", car), ("rush_att", car), ("rush_yds", round(car * 4.5, 1))):
                        rows.append(_row("nfl", season, p, qb, t, opp, "QB", m, v))
                rb = f"RB {t}"
                c = rng.randint(12, 22)
                ypc = 9.0 if (soft_mia and opp == "MIA") else 4.3
                for m, v in (("carries", c), ("rush_att", c), ("rush_yds", round(c * ypc, 1)),
                             ("rec_yds", rng.randint(0, 40)), ("receptions", rng.randint(0, 5)),
                             ("targets", rng.randint(1, 6)), ("anytime_td", rng.choice([0, 0, 1, 1, 2])),
                             ("rush_td", rng.choice([0, 1])), ("rec_td", 0)):
                    rows.append(_row("nfl", season, p, rb, t, opp, "RB", m, v))
    rows += list(extra)
    DB.upsert_player_logs(conn, rows)
    conn.commit()
    return path, conn


def _nfl_board(**kw) -> dict:
    g = {"home": "BUF", "away": "MIA", "date": "2026-10-12", "kickoff": "2026-10-12T17:00:00Z",
         "spread": -7.5, "total": 49.5, "home_ml": -380, "away_ml": 300,
         "weather": {"dome": False, "temp_f": 55, "wind_mph": 8, "measured": True}}
    g.update(kw)
    return {"date": "2026-10-12", "games": [g],
            "recommendations": [{"player": "Josh Allen", "team": "BUF", "market": "pass_yds", "line": 245.5,
                                 "side": "OVER", "projection": 251.0, "proj_std": 50.0, "hit_prob": 0.55}]}


ALLEN = {"sport": "nfl", "player": "Josh Allen", "team": "BUF", "market": "rush_att", "side": "over",
         "line": 5.5, "odds": -130, "game": "MIA @ BUF", "text": ""}


# ---- football ---------------------------------------------------------------------
def test_josh_allens_carries_get_the_boards_own_model():
    SR.clear_cache()
    _, conn = _nfl_db()
    row = SR.read({"nfl": _nfl_board()}, ALLEN, conn=conn)
    assert row and row["league"] == "nfl" and row["player"] == "Josh Allen" and row["position"] == "QB"
    assert row["opponent"] == "MIA" and row["home"] == "BUF" and row["away"] == "MIA"
    assert 6.0 < row["projection"] < 10.0 and row["proj_std"] > 0, row["projection"]
    assert row["proj_low"] < row["projection"] < row["proj_high"]
    assert row["season_games"] == 5 and row["carried"] == 0
    assert row["why_off"] == "our board does not build that market for quarterbacks"
    steps = [s["key"] for s in row["chain"]["steps"]]
    assert {"matchup", "weather", "injury", "player", "lineup"} <= set(steps), steps
    # THE SLIP'S BET is the row's, not the side the model would have taken.
    assert (row["side"], row["line"], row["odds"]) == ("over", 5.5, -130)
    # A defence the model reads nothing from for this market is SHOWN and
    # said to be outside the number — a quarterback's runs against what the
    # defence gives up to quarterbacks on the ground.
    card = row["matchup_card"]
    assert card["shown_only"] and card["stat"] == "rushing yards to QBs" and card["opponent"] == "MIA"
    # No market is ever made of the proxy line.
    assert row["has_market"] is False and row["fair_prob"] is None and row["all_lines"] == []


def test_the_grader_prices_the_read_says_the_facts_and_asks_the_four_checks():
    SR.clear_cache()
    path, _ = _nfl_db()
    AB.HISTORY_DB = path
    try:
        at = SG.price_leg({"nfl": _nfl_board()}, dict(ALLEN))
    finally:
        AB.HISTORY_DB = None
    assert at["found"] == "read" and at["league"] == "nfl" and at["prob"] is not None
    raw = at["row"]["raw_prob"]
    assert at["prob"] == SG._honest("nfl", raw, "over", -130)
    assert abs(raw - SG.prob_at_line(at["row"], "rush_att", "over", 5.5)) < 1e-9
    assert at["verdict"] == SG.verdict(at["prob"], at["prob"] - SG.implied(-130))
    rd = at["read"]
    assert rd["why_off"].startswith("our board does not build") and rd["games"] == 5
    c = at["row"]["read_checks"]
    from engine import likelyboard as LB
    assert set(c["checks"]) == {"model", "matchup", "market", "record"}
    assert c["checks"]["model"] == (at["prob"] >= LB.MODEL_BAR["prop"])
    assert c["tier"] == LB.tier_of(c["checks"]) and c["tier_label"] == LB.TIER_LABEL[c["tier"]]
    assert rd["would_be"] == c["tier_label"] and rd["passed"] == [k for k in ("model", "matchup", "market", "record")
                                                                 if c["checks"][k] is True]
    facts = {f["k"]: f["t"] for f in SG.why({"nfl": _nfl_board()}, at)}
    assert facts["Our read"].startswith("Not on our board — our board does not build that market for quarterbacks")
    assert facts["Projection"].startswith("We project ") and "against 5.5" in facts["Projection"]
    assert "Cleared 5.5 in" in facts["Recent games"] and facts["This season"].endswith("over 5 games")
    assert "shown, not in our number" in facts["Defense"]
    assert "nothing measured says it moves a quarterback's own runs" in facts["Game script"]
    assert facts["Checks"].startswith("Passes ") and "Would be" in facts
    assert "The books" not in facts, "the proxy line is no market"


def test_the_summary_says_which_legs_are_our_read():
    SR.clear_cache()
    path, _ = _nfl_db()
    AB.HISTORY_DB = path
    try:
        card = SG.grade({"legs": [dict(ALLEN), {"sport": "nfl", "player": "RB BUF", "team": "BUF",
                                                "market": "rush_yds", "side": "over", "line": 60.5,
                                                "odds": -115, "game": "MIA @ BUF", "text": ""}],
                         "total_odds": 260, "stake": 10}, {"nfl": _nfl_board()})
    finally:
        AB.HISTORY_DB = None
    assert card["n_priced"] == 2 and card["n_read"] == 2
    text = SG.summary(card)
    assert text.startswith("Graded parlay, 2 legs (0 on our boards, 2 more read by our own model off the board).")
    assert "Josh Allen over 5.5 carries: ours " in text and "our read: not on our board" in text


def test_the_box_check_prints_a_read():
    import contextlib
    import io
    SR.clear_cache()
    path, _ = _nfl_db()
    AB.HISTORY_DB = path
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = SR.main(["nfl", "Josh Allen", "rush_att", "over", "5.5", "-130"])
    finally:
        AB.HISTORY_DB = None
    assert code == 0
    got = json.loads(buf.getvalue())
    assert got["found"] in ("read", "") and "why" in got, "the live boards decide the game; the read prints either way"
    assert SR.main([]) == 2


def test_a_name_is_his_or_nobodys():
    SR.clear_cache()
    _, conn = _nfl_db(extra=[_row("nfl", 2026, "005", "Jalen Allison", "NE", "BUF", "QB", "carries", 4),
                             _row("nfl", 2026, "005", "Jalen Allison", "NE", "BUF", "QB", "rush_att", 4)])
    mk = ("rush_att", "carries")
    assert SR.resolve(conn, "nfl", {"player": "Josh Allen"}, mk)["player"] == "Josh Allen"
    assert SR.resolve(conn, "nfl", {"player": "J. Allen"}, mk)["player"] == "Josh Allen"
    assert SR.resolve(conn, "nfl", {"player": "Allen", "team": "BUF"}, mk)["player"] == "Josh Allen"
    assert SR.resolve(conn, "nfl", {"player": "Jordan Allen"}, mk) is None, "a full first name that is not his"
    _, conn2 = _nfl_db(extra=[_row("nfl", 2026, "005", "Jake Allen", "NE", "BUF", "QB", "carries", 4)])
    assert SR.resolve(conn2, "nfl", {"player": "J. Allen"}, mk) is None, "two of them: a guess is not graded"
    assert SR.resolve(conn2, "nfl", {"player": "J. Allen", "team": "NE"}, mk)["player"] == "Jake Allen"


def test_a_thin_season_is_topped_up_and_too_few_games_is_no_number():
    SR.clear_cache()
    _, conn = _nfl_db(weeks_now=1)
    row = SR.read({"nfl": _nfl_board()}, ALLEN, conn=conn)
    assert row["season_games"] == 1 and row["carried"] == SR.TOP_UP - 1
    assert any(g.get("prior") for g in row["logs"]), "last season's games marked as carried"
    SR.clear_cache()
    path = str(_SANDBOX / "thin.db")
    c2 = DB.connect(path)
    DB.upsert_player_logs(c2, [_row("nfl", 2026, f"{w:03d}", "Josh Allen", "BUF", "MIA", "QB", m, 8)
                               for w in (1, 2) for m in ("carries", "rush_att")])
    c2.commit()
    assert SR.read({"nfl": _nfl_board()}, ALLEN, conn=c2) is None
    AB.HISTORY_DB = path
    try:
        at = SG.price_leg({"nfl": _nfl_board()}, dict(ALLEN))
    finally:
        AB.HISTORY_DB = None
    assert at["found"] == "" and at["prob"] is None and at["verdict"] == "unpriced", "as before: not on our board"


def test_the_defence_is_rated_from_the_database_and_reaches_the_number():
    SR.clear_cache()
    leg = {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds", "side": "over",
           "line": 70.5, "odds": -115, "game": "MIA @ BUF"}
    _, hard = _nfl_db()
    _, soft = _nfl_db(soft_mia=True)
    a = SR.read({"nfl": _nfl_board()}, leg, conn=hard)
    SR.clear_cache()
    b = SR.read({"nfl": _nfl_board()}, leg, conn=soft)
    ma = next(s["mult"] for s in a["chain"]["steps"] if s["key"] == "matchup")
    mb = next(s["mult"] for s in b["chain"]["steps"] if s["key"] == "matchup")
    assert mb > ma and mb > 1.0, (ma, mb)
    assert b["matchup_card"]["rank"] == 1 and not b["matchup_card"].get("shown_only")
    # The ratings are this season's, shrunk toward last season's whole.
    rated = SR.defence_ratings(soft, "nfl", 2026)
    r = rated["MIA"]["rb_rush_yds"]
    assert r["games"] >= 1 and r["rank"] == 1 and r["factor"] > 1.0


def test_the_game_script_is_read_for_this_side():
    card = _nfl_board()["games"][0]
    run_over = SR.script_for(card, "BUF", "rush_yds", "over", "RB")
    run_under = SR.script_for(card, "BUF", "rush_yds", "under", "RB")
    pass_over = SR.script_for(card, "MIA", "pass_att", "over", "QB")
    qb_runs = SR.script_for(card, "BUF", "rush_att", "over", "QB")
    assert run_over["fits"] == 1 and run_under["fits"] == -1, "the favourite runs the clock"
    assert pass_over["fits"] == 1, "the dog trails and throws"
    assert qb_runs["fits"] == 0 and "quarterback's own runs" in qb_runs["note"]
    assert "BUF favorite by 7.5, implied 28.5 points" in run_over["text"]
    assert SR.script_for(dict(card, home_ml=0, away_ml=0), "BUF", "rush_yds", "over", "RB") is None, \
        "a total no book posted is no script"


def test_the_matchup_check_reads_the_scans_lean_on_him():
    SR.clear_cache()
    _, conn = _nfl_db()
    board = _nfl_board()
    board["scan_reads"] = {"MIA@BUF": {"players": [
        {"player": "RB BUF", "team": "BUF", "read": "good", "label": "Good matchup", "lean": ["rush_yds", "rec_yds"]}]}}
    leg = {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds", "side": "over", "line": 60.5,
           "odds": -115, "game": "MIA @ BUF"}
    row = SR.read({"nfl": board}, leg, conn=conn)
    c = SR.checks(row, board, "nfl", 0.62)
    assert c["checks"]["matchup"] is True and "Good matchup" in c["notes"]["matchup"]
    c2 = SR.checks(dict(row, side="under"), board, "nfl", 0.62)
    assert c2["checks"]["matchup"] is False, "the lean says over"
    nolean = SR.checks(row, _nfl_board(), "nfl", 0.62)
    # No scan read: the board's own rule now reads the projection's own
    # Matchup step (Ethan, 2026-10-14, "do 1-11"), here -6% for this game:
    # against the over, with the under, and a step too small says nothing.
    assert nolean["checks"]["matchup"] is False and "matchup moved our number -6%" in nolean["notes"]["matchup"]
    assert SR.checks(dict(row, side="under"), _nfl_board(), "nfl", 0.62)["checks"]["matchup"] is True
    flat = dict(row, chain={"steps": [{"key": "matchup", "mult": 1.01}]})
    assert SR.checks(flat, _nfl_board(), "nfl", 0.62)["checks"]["matchup"] is None, "not enough to call"
    rec = {("rush_yds", "over", 0.60): {"n": 40, "hits": 30, "claimed": 24.8}}
    SR._record = lambda league: rec
    try:
        assert SR.checks(row, board, "nfl", 0.62)["checks"]["record"] is True
    finally:
        SR._record = lambda league: {}


def test_a_journal_that_cannot_be_read_is_said_and_asked_again():
    """A record table the journal could not give is not a short record: the
    check says it could not read it, the log names the error, and the
    failure is not kept, so the next leg asks the journal again. (The
    journal here is a stub that raises; data/ledger.db is never opened.)"""
    from engine import ledger
    SR.clear_cache()
    _, conn = _nfl_db()
    board = _nfl_board()
    leg = {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds", "side": "over", "line": 60.5,
           "odds": -115, "game": "MIA @ BUF"}
    row = SR.read({"nfl": board}, leg, conn=conn)
    asked = []

    def locked(*a, **k):
        asked.append(1)
        raise RuntimeError("database is locked")
    real = ledger.connect
    ledger.connect, SR._record = locked, _JOURNAL_RECORD
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            c = SR.checks(row, board, "nfl", 0.62)
            assert SR._record("nfl") is None
        assert c["checks"]["record"] is None
        assert c["notes"]["record"] == "our record could not be read just now", c["notes"]["record"]
        assert "too short" not in c["notes"]["record"], "a failed read passed for a short record"
        assert len(asked) == 2, "the failed read was cached"
        assert "the nfl record could not be read (RuntimeError: database is locked)" in err.getvalue()
    finally:
        ledger.connect, SR._record = real, (lambda league: {})
        SR.clear_cache()


def test_a_scorer_goes_through_the_touchdown_model():
    SR.clear_cache()
    _, conn = _nfl_db()
    leg = {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "anytime_td", "side": "yes", "line": 0.5,
           "odds": 120, "game": "MIA @ BUF"}
    row = SR.read({"nfl": _nfl_board()}, leg, conn=conn)
    assert 0.05 < row["model_over"] < 0.95 and abs(row["model_over"] + row["model_under"] - 1) < 1e-9
    assert row["implied_total"] == 28.5 and 0 < row["touch_share"] < 1
    assert row["matchup_card"]["stat"] == "TDs to RBs"
    SR.clear_cache()
    unposted = SR.read({"nfl": _nfl_board(home_ml=0, away_ml=0)}, leg, conn=conn)
    assert unposted["refused"].startswith("no posted spread and total") and unposted.get("model_over") is None


def test_the_injury_report_comes_first():
    SR.clear_cache()
    path, conn = _nfl_db()
    out = _nfl_board()
    out["games"][0]["scan"] = {"injuries": [{"team": "BUF", "player": "Josh Allen", "position": "QB",
                                             "status": "OUT"}]}
    row = SR.read({"nfl": out}, ALLEN, conn=conn)
    assert row["injury_status"] == "Out" and row["projection"] is None and row["model_over"] is None
    assert row["refused"] == "he is listed out — the board takes a ruled-out player off"
    AB.HISTORY_DB = path
    try:
        at = SG.price_leg({"nfl": out}, dict(ALLEN))
        at["why"] = SG.why({"nfl": out}, at)
    finally:
        AB.HISTORY_DB = None
    assert at["found"] == "read" and at["prob"] is None and at["verdict"] == "unpriced"
    facts = {f["k"]: f["t"] for f in at["why"]}
    assert facts["Status"] == "Listed Out" and facts["Our model"].startswith("Won't put a number on it: he is listed out")
    assert "Josh Allen: listed Out" in SG.alerts([at])
    SR.clear_cache()
    q = _nfl_board()
    q["games"][0]["scan"] = {"injuries": [{"team": "BUF", "player": "Josh Allen", "status": "QUESTIONABLE"}]}
    kept = SR.read({"nfl": q}, ALLEN, conn=conn)
    assert kept["injury_status"] == "Questionable" and kept["projection"] is not None and not kept.get("refused")
    SR.clear_cache()
    pulled = _nfl_board()
    pulled["games"][0]["scan"] = {"pulled": ["Josh Allen"]}
    gone = SR.read({"nfl": pulled}, ALLEN, conn=conn)
    assert gone["projection"] is None and gone["refused"].startswith("every book took his props down")


def test_every_sports_injury_list_is_read():
    SR.clear_cache()
    _, conn = _other_db()
    nhl = json.loads(json.dumps(OTHER_BOARDS))
    nhl["nhl"]["games"][0]["nhl_tape"] = {"sides": {"TOR": {"injuries": [{"player": "Fwd TOR", "status": "out"}]},
                                                     "MTL": {"injuries": []}}}
    leg = {"sport": "nhl", "player": "Fwd TOR", "market": "sog", "side": "over", "line": 2.5, "odds": -140}
    assert SR.read(nhl, leg, conn=conn)["refused"].startswith("he is listed out")
    SR.clear_cache()
    nhl["nhl"]["games"][0]["nhl_tape"]["sides"]["TOR"]["injuries"][0]["status"] = "day-to-day"
    dtd = SR.read(nhl, leg, conn=conn)
    assert dtd["injury_status"] == "Day-To-Day" and dtd["projection"] is not None
    SR.clear_cache()
    mlb = json.loads(json.dumps(OTHER_BOARDS))
    mlb["mlb"]["injured_list"] = ["Slugger CHC"]
    il = SR.read(mlb, {"sport": "mlb", "player": "Slugger CHC", "market": "hits", "side": "over", "line": 0.5,
                       "odds": -200}, conn=conn)
    assert il["projection"] is None and il["refused"] == "he is listed injured list — the board takes a ruled-out player off"


def test_a_game_not_on_the_board_says_so():
    SR.clear_cache()
    _, conn = _nfl_db()
    row = SR.read({"nfl": {"games": []}}, ALLEN, conn=conn)
    assert row["why_off"] == "his game is not on tonight's board yet, so nothing in it was priced"
    assert row["game_script"] is None and row["script_fit"] is None


# ---- basketball, hockey, baseball -----------------------------------------------------
def _other_db() -> tuple:
    path = str(_SANDBOX / f"other_{random.random():.12f}.db")
    conn = DB.connect(path)
    rng = random.Random(3)
    rows = []
    nba = ["BOS", "NYK", "MIA", "PHI", "MIL", "CHI"]
    for gi in range(15):
        day = (dt.date(2026, 10, 21) + dt.timedelta(days=2 * gi)).isoformat()
        for i, t in enumerate(nba):
            opp = nba[(i + gi + 1) % 6] if nba[(i + gi + 1) % 6] != t else nba[(i + 2) % 6]
            for j, (pl, mins, pts) in enumerate(((f"Star {t}", 34, 26), (f"Bench {t}", 18, 8))):
                pos = "S" if j == 0 else "B"
                m = round(mins + rng.uniform(-3, 3), 1)
                if pl == "Bench MIA":
                    m = 14.0 if gi in (3, 9) else 0.0      # in uniform twice, on the floor twice
                for mk, v in (("min", m), ("pts", max(0, round(pts + rng.uniform(-7, 7)))),
                              ("reb", rng.randint(2, 9)), ("ast", rng.randint(1, 7)), ("fg3m", rng.randint(0, 4))):
                    rows.append(_row("nba", 2026, day, pl, t, opp, pos, mk, v))
    nhl = ["TOR", "MTL", "BOS", "NYR"]
    for gi in range(20):
        day = (dt.date(2026, 10, 8) + dt.timedelta(days=2 * gi)).isoformat()
        for i, t in enumerate(nhl):
            opp = nhl[(i + 1 + gi) % 4] if nhl[(i + 1 + gi) % 4] != t else nhl[(i + 2) % 4]
            for pl, pos, toi, sog in ((f"Fwd {t}", "C", 19.0, 3.2), (f"Dman {t}", "D", 22.0, 1.4)):
                s = max(0, round(sog + rng.uniform(-2, 2)))
                g = 1 if rng.random() < 0.05 * s else 0
                a = rng.choice([0, 0, 1])
                for mk, v in (("toi", toi + rng.uniform(-2, 2)), ("sog", s), ("goals", g), ("assists", a),
                              ("points", g + a), ("blocks", rng.randint(0, 3))):
                    rows.append(_row("nhl", 2026, day, pl, t, opp, pos, mk, v))
            for mk, v in (("saves", rng.randint(22, 34)), ("shots_against", rng.randint(25, 36)), ("toi", 60.0)):
                rows.append(_row("nhl", 2026, day, f"Goalie {t}", t, opp, "G", mk, v))
    mlb = ["CHC", "PHI", "NYY", "BOS"]
    for gi in range(30):
        day = (dt.date(2026, 6, 1) + dt.timedelta(days=gi)).isoformat()
        for i, t in enumerate(mlb):
            opp = mlb[(i + 1) % 4]
            for mk, v in (("hits", rng.choice([0, 1, 1, 2])), ("total_bases", rng.choice([0, 1, 2, 4])),
                          ("home_runs", rng.choice([0, 0, 0, 1]))):
                rows.append(_row("mlb", 2026, day, f"Slugger {t}", t, opp, "1B", mk, v))
            if gi % 5 == 0:
                rows.append(_row("mlb", 2026, day, f"Ace {t}", t, opp, "SP", "strikeouts", rng.randint(4, 10)))
                rows.append(_row("mlb", 2026, day, f"Ace {t}", t, opp, "SP", "outs", rng.randint(15, 21)))
    DB.upsert_player_logs(conn, rows)
    conn.commit()
    return path, conn


OTHER_BOARDS = {
    "nba": {"date": "2026-11-20", "games": [{"home": "BOS", "away": "NYK", "date": "2026-11-20"},
                                             {"home": "MIA", "away": "PHI", "date": "2026-11-20"}],
            "game_bets": [{"market": "spread", "home": "BOS", "away": "NYK", "team": "BOS", "line": -6.5},
                          {"market": "total", "home": "BOS", "away": "NYK", "side": "over", "line": 226.5}]},
    "nhl": {"date": "2026-11-20", "games": [{"home": "TOR", "away": "MTL", "date": "2026-11-20"}]},
    "mlb": {"date": "2026-07-01", "games": [{"home": "CHC", "away": "PHI", "date": "2026-07-01", "total": 9.5,
                                             "total_posted": True, "park": {"key": "wrigley"},
                                             "pitchers": {"home": {"name": "Ace CHC", "throws": "R", "xera": 3.5,
                                                                   "k_rate": 0.27},
                                                          "away": {"name": "Ace PHI", "throws": "L", "xera": 4.2,
                                                                   "k_rate": 0.21}}}]},
}


def test_basketball_reads_scalpys_projection_and_its_refusal():
    SR.clear_cache()
    _, conn = _other_db()
    leg = {"sport": "nba", "player": "Star BOS", "market": "pts", "side": "over", "line": 24.5, "odds": -115}
    row = SR.read(OTHER_BOARDS, leg, conn=conn)
    assert row["league"] == "nba" and row["opponent"] == "NYK" and row["projection"] > 15
    assert 0 < row["model_over"] < 1 and abs(row["model_over"] + row["model_under"] - 1) < 1e-9
    assert row["rung_probs"]["24.5"] == row["model_over"]
    keys = sorted(float(k) for k in row["rung_probs"])
    ps = [row["rung_probs"][f"{k:g}"] for k in keys]
    assert all(a >= b for a, b in zip(ps, ps[1:])), "a higher number is never an easier over"
    assert row["matchup_card"] and "NYK allow" in row["matchup_card"]["text"]
    pra = SR.read(OTHER_BOARDS, dict(leg, market="pra", side="under", line=39.5), conn=conn)
    assert pra["projection"] is not None, "a price that disagrees is a betting gate, not a refusal to project"
    swing = SR.read(OTHER_BOARDS, {"sport": "nba", "player": "Bench MIA", "market": "reb", "side": "over",
                                   "line": 4.5, "odds": -110}, conn=conn)
    assert swing["projection"] is None and swing["refused"] == "thin sample — under 3 usable games", \
        "a role the model cannot read is its own refusal, said as the board says it"


def test_the_projection_split_left_scalpys_card_as_it_was():
    from engine.hoops import for_league
    from engine.nba.pipeline import evaluate_prop, project
    tune = for_league("nba")
    prop = {"player": "X", "team": "BOS", "opponent": "NYK", "market": "pts", "line": 24.5,
            "over_odds": -110, "under_odds": -110, "book": "dk", "minutes": [34, 33, 35, 36, 34, 33, 35, 34],
            "values": [26, 24, 30, 22, 27, 25, 29, 23], "is_starter": True, "spread": -4.0, "is_favorite": True,
            "game_total": 228.0, "rest": "1day"}
    card = evaluate_prop(prop, tune)
    pj = project(prop, tune)
    assert card["kind"] in ("pick", "near_miss") and card["projection"] == pj["projection"]
    assert card["proj_minutes"] == pj["proj_min"] and card["base_minutes"] == pj["base"]
    thin = dict(prop, minutes=[30, 31], values=[20, 22])
    assert evaluate_prop(thin, tune) == {"kind": "skip", "why": "thin sample — under 3 usable games"}
    assert project(thin, tune) == {"skip": "thin sample — under 3 usable games"}


def test_hockey_and_baseball_read_their_own_models():
    SR.clear_cache()
    _, conn = _other_db()
    sog = SR.read(OTHER_BOARDS, {"sport": "nhl", "player": "Fwd TOR", "market": "sog", "side": "over",
                                 "line": 2.5, "odds": -140}, conn=conn)
    assert sog["league"] == "nhl" and sog["opponent"] == "MTL" and 1.5 < sog["projection"] < 5
    whole = SR.read(OTHER_BOARDS, {"sport": "nhl", "player": "Fwd TOR", "market": "sog", "side": "under",
                                   "line": 3.0, "odds": 110}, conn=conn)
    assert whole["model_over"] + whole["model_under"] < 0.99, "at a whole number the push is neither side's"
    goal = SR.read(OTHER_BOARDS, {"sport": "nhl", "player": "Fwd TOR", "market": "anytime_goal", "side": "yes",
                                  "line": 0.5, "odds": 160}, conn=conn)
    assert 0 < goal["model_over"] < 0.6
    saves = SR.read(OTHER_BOARDS, {"sport": "nhl", "player": "Goalie TOR", "market": "saves", "side": "over",
                                   "line": 27.5, "odds": -110}, conn=conn)
    assert 15 < saves["projection"] < 40 and "save rate" in saves["reasons"][0]
    tb = SR.read(OTHER_BOARDS, {"sport": "mlb", "player": "Slugger CHC", "market": "total_bases", "side": "over",
                                "line": 1.5, "odds": 120}, conn=conn)
    assert tb["league"] == "mlb" and tb["facing"]["name"] == "Ace PHI" and tb["facing"]["throws"] == "L"
    k = SR.read(OTHER_BOARDS, {"sport": "mlb", "player": "Ace CHC", "market": "strikeouts", "side": "over",
                               "line": 6.5, "odds": -105}, conn=conn)
    assert k["position"] == "SP" and k["projection"] > 3 and 0 < k["model_over"] < 1
    # NO SPORT ON THE SLIP: the market's leagues are tried, and he is found in one.
    anon = SR.read(OTHER_BOARDS, {"sport": "", "player": "Fwd TOR", "market": "sog", "side": "over", "line": 2.5,
                                  "odds": -140}, conn=conn)
    assert anon["league"] == "nhl"


# ---- better legs ---------------------------------------------------------------------
def _likely(player, team, opp, market, side, line, odds, p, tier="strong", label="Strong"):
    return {"player": player, "team": team, "opponent": opp, "market": market, "side": side, "line": line,
            "odds": odds, "model_prob": p, "tier": tier, "tier_label": label}


def _swap_board():
    b = _nfl_board()
    b["likely_board"] = {"rows": [
        _likely("WR BUF", "BUF", "MIA", "receptions", "over", 4.5, -125, 0.66),
        _likely("QB MIA", "MIA", "BUF", "pass_att", "over", 33.5, -110, 0.61, "look", "Worth a look"),
        _likely("QB KC", "KC", "LV", "pass_att", "over", 33.5, -110, 0.72, "top", "Top pick"),
        _likely("RB BUF", "BUF", "MIA", "rush_yds", "over", 55.5, -140, 0.70, "top", "Top pick"),
        _likely("TE BUF", "BUF", "MIA", "receptions", "over", 3.5, -120, 0.53, "look", "Worth a look"),
    ]}
    return b


def _weak_leg():
    return {"sport": "nfl", "player": "WR MIA", "team": "MIA", "market": "rec_yds", "side": "over",
            "line": 80.5, "odds": -115, "game": "MIA @ BUF", "text": ""}


def _priced(boards, *legs):
    out = [SG.price_leg(boards, dict(l)) for l in legs]
    return out


def test_a_weak_leg_gets_the_boards_better_legs_in_its_game():
    SR.clear_cache()
    boards = {"nfl": _swap_board()}
    boards["nfl"]["recommendations"].append({"player": "WR MIA", "team": "MIA", "opponent": "BUF",
                                             "market": "rec_yds", "line": 80.5, "side": "OVER",
                                             "projection": 70.0, "proj_std": 25.0, "hit_prob": 0.36})
    legs = _priced(boards, _weak_leg(), dict(ALLEN, player="QB KC", team="KC", market="pass_att", line=33.5,
                                             odds=-110, game="LV @ KC"))
    assert legs[0]["verdict"] in ("weak", "against") and legs[0]["found"] == "prop"
    payout = SG.to_decimal(-115) * SG.to_decimal(-110)
    chance = SG._ticket_chance(legs)
    ev = chance * payout - 1.0
    got = SG.replacements(legs, boards, payout, ev)
    assert list(got) == [0], "only the weak leg"
    sw = got[0]
    assert 1 <= len(sw) <= SG.SWAPS_PER_LEG
    names = [x["label"] for x in sw]
    assert all("KC" not in n for n in names), "a pick in another game is never offered"
    assert all(x["ticket_ev"] > ev + SG.SWAP_GAIN for x in sw), "a swap leaves the ticket better"
    assert [x["ticket_ev"] for x in sw] == sorted((x["ticket_ev"] for x in sw), reverse=True)
    top = sw[0]
    c = SG.price_leg(boards, {"sport": "nfl", "player": top["player"], "team": "", "market": top["market"],
                              "side": top["side"], "line": top["line"], "odds": top["odds"], "game": "MIA @ BUF"})
    assert abs(c["prob"] - top["prob"]) < 1e-9 and c["found"] == top["found"], "priced exactly as a leg"
    new = [c, legs[1]]
    assert abs(SG._ticket_chance(new) - top["ticket_chance"]) < 1e-3
    assert top["ticket_odds"] == SG.from_decimal(payout * SG.to_decimal(top["odds"]) / SG.to_decimal(-115))
    assert all(x["verdict"] in ("strong", "fair") for x in sw)


def test_a_swap_is_never_a_bet_already_on_it_or_a_pair_the_engine_would_not_build():
    SR.clear_cache()
    boards = {"nfl": _swap_board()}
    boards["nfl"]["likely_board"]["rows"].append(
        {"kind": "game", "market": "total", "side": "under", "line": 49.5, "odds": -110, "model_prob": 0.66,
         "home": "BUF", "away": "MIA", "tier": "strong", "tier_label": "Strong"})
    boards["nfl"]["game_bets"] = [{"market": "total", "home": "BUF", "away": "MIA", "side": "under", "line": 49.5,
                                   "win_prob": 0.66, "odds": -110, "other_odds": -110}]
    total_over = {"sport": "nfl", "player": "", "team": "", "market": "total", "side": "over", "line": 49.5,
                  "odds": -110, "game": "MIA @ BUF", "text": ""}
    rb = {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds", "side": "over", "line": 55.5,
          "odds": -140, "game": "MIA @ BUF", "text": ""}
    legs = _priced(boards, total_over, _weak_leg(), rb)
    payout = SG.to_decimal(-110) * SG.to_decimal(-115) * SG.to_decimal(-140)
    got = SG.replacements(legs, boards, payout, None)
    for i, sw in got.items():
        for x in sw:
            assert not (x["market"] == "rush_yds" and x.get("player") == "RB BUF"), "already on the ticket"
            if i != 0:
                assert not (x["market"] == "total" and x["side"] == "under"), \
                    "the other side of a total on the ticket cannot both win"


def test_the_other_side_of_a_weak_total_is_a_fair_swap():
    SR.clear_cache()
    boards = {"nfl": _swap_board()}
    boards["nfl"]["likely_board"]["rows"] = [
        _likely("QB KC", "KC", "LV", "pass_att", "over", 33.5, -110, 0.72, "top", "Top pick"),
        {"kind": "game", "market": "total", "side": "under", "line": 49.5, "odds": -110, "model_prob": 0.66,
         "home": "BUF", "away": "MIA", "tier": "strong", "tier_label": "Strong"}]
    boards["nfl"]["game_bets"] = [{"market": "total", "home": "BUF", "away": "MIA", "side": "under", "line": 49.5,
                                   "win_prob": 0.66, "odds": -110, "other_odds": -110}]
    over = SG.price_leg(boards, {"sport": "nfl", "player": "", "team": "", "market": "total", "side": "over",
                                 "line": 49.5, "odds": -110, "game": "MIA @ BUF", "text": ""})
    kc = SG.price_leg(boards, {"sport": "nfl", "player": "QB KC", "team": "KC", "market": "pass_att",
                               "side": "over", "line": 33.5, "odds": -110, "game": "LV @ KC", "text": ""})
    assert over["found"] == "game" and over["verdict"] in ("weak", "against") and kc["found"] == "likely"
    payout = SG.to_decimal(-110) * SG.to_decimal(-110)
    got = SG.replacements([over, kc], boards, payout, SG._ticket_chance([over, kc]) * payout - 1.0)
    assert [(x["market"], x["side"], x["line"]) for x in got[0]] == [("total", "under", 49.5)], got
    # …but beside a player's over in the same game, the parlay engine never
    # pairs a total's under with it (the pace link the wrong way), so no.
    boards["nfl"]["likely_board"]["rows"].append(
        _likely("RB BUF", "BUF", "MIA", "rush_yds", "over", 55.5, -140, 0.70, "top", "Top pick"))
    rb = SG.price_leg(boards, {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds",
                               "side": "over", "line": 55.5, "odds": -140, "game": "MIA @ BUF", "text": ""})
    assert rb["found"] == "likely"
    got2 = SG.replacements([over, rb], boards, payout, None)
    assert not any(x["market"] == "total" for x in got2.get(0, [])), got2


def test_strong_legs_and_games_under_way_get_no_swaps():
    SR.clear_cache()
    boards = {"nfl": _swap_board()}
    strong = SG.price_leg(boards, {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds",
                                   "side": "over", "line": 55.5, "odds": -140, "game": "MIA @ BUF"})
    assert strong["verdict"] in ("strong", "fair")
    weak = SG.price_leg(boards, _weak_leg())
    weak["live"] = {"state": "live"}
    assert SG.replacements([strong, weak], boards, 3.0, 0.1) == {}


def test_an_unpriced_leg_gets_better_legs_by_chance_and_the_card_carries_them():
    SR.clear_cache()
    boards = {"nfl": _swap_board()}
    slip = {"legs": [_weak_leg() | {"player": "Nobody Known"},
                     {"sport": "nfl", "player": "RB BUF", "team": "BUF", "market": "rush_yds", "side": "over",
                      "line": 55.5, "odds": -140, "game": "MIA @ BUF", "text": ""}],
            "total_odds": 0, "stake": 10}
    card = SG.grade(slip, boards)
    lost = next(l for l in card["legs"] if l["player"] == "Nobody Known")
    assert lost["verdict"] == "unpriced" and lost["swaps"], "a leg we cannot price still gets legs we can"
    assert all(x["prob"] >= SG.implied(-115) + SG.SWAP_GAIN for x in lost["swaps"])
    text = SG.summary(card)
    assert "Better leg for Nobody Known over 80.5 receiving yards:" in text


def test_the_better_number_leads_the_swaps_when_it_lifts_the_ticket():
    l = {"verdict": "weak", "market": "rec_yds", "side": "over", "line": 69.5, "odds": -115, "prob": 0.5,
         "needs": 0.53, "player": "Davante Adams", "team": "LA", "league": "nfl", "game": "BUF @ LA",
         "row": {"home": "LA", "away": "BUF"},
         "better_number": {"line": 59.5, "odds": 150, "book": "Caesars", "p": 0.66, "ev": 0.65, "p_here": 0.5,
                           "ev_here": -0.07, "label": "Over 59.5", "ticket_odds": 480, "ticket_ev": 0.4}}
    got = SG.replacements([l], {"nfl": {}}, 3.0, 0.1)
    assert got[0][0]["kind"] == "number" and got[0][0]["label"] == "Davante Adams Over 59.5 receiving yards"
    assert got[0][0]["book"] == "Caesars" and got[0][0]["ticket_ev"] == 0.4
    assert SG.replacements([l], {"nfl": {}}, 3.0, 0.45) == {}, "a better number that does not lift the ticket"


# ---- the page ------------------------------------------------------------------------
def _node(script: str) -> str | None:
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    return out.stdout


def _vm(body: str) -> str:
    return ("const vm = require('vm'); const fs = require('fs');"
            "const ctx = { window: {} }; vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
            "const S = ctx.window.QBSlip;" + body)


PAGE = {
    "legs": [
        {"sport": "nfl", "league": "nfl", "player": "Josh Allen", "team": "BUF", "game": "MIA @ BUF",
         "market": "rush_att", "side": "over", "line": 5.5, "odds": -130, "prob": 0.71, "needs": 0.57,
         "verdict": "strong", "found": "read",
         "read": {"why_off": "our board does not build that market for quarterbacks", "would_be": "Strong",
                  "makes_board": True, "passed": ["model", "market"], "against": [], "refused": "", "games": 5},
         "why": [{"k": "Our read", "t": "Not on our board — our board does not build that market for quarterbacks."}]},
        {"sport": "nba", "league": "nba", "player": "Bench MIA", "team": "MIA", "game": "PHI @ MIA",
         "market": "reb", "side": "over", "line": 4.5, "odds": -110, "prob": None, "needs": 0.52,
         "verdict": "unpriced", "found": "read",
         "read": {"why_off": "he is not one of the players our board prices in that game", "would_be": "",
                  "makes_board": False, "passed": [], "against": [], "refused": "minutes that swing", "games": 15},
         "why": [{"k": "Our read", "t": "Not on our board."}],
         "swaps": [{"kind": "leg", "label": "Star MIA over 7.5 rebounds", "player": "Star MIA", "market": "reb",
                    "side": "over", "line": 7.5, "odds": -120, "prob": 0.64, "verdict": "strong",
                    "tier": "Top pick", "found": "likely", "same_player": False, "ticket_chance": 0.4,
                    "ticket_odds": 160, "ticket_ev": 0.04, "approx": False}]},
        {"sport": "nfl", "league": "nfl", "player": "WR MIA", "team": "MIA", "game": "MIA @ BUF",
         "market": "rec_yds", "side": "over", "line": 80.5, "odds": -115, "prob": 0.36, "needs": 0.53,
         "verdict": "against", "found": "prop", "is_weakest": True,
         "swaps": [{"kind": "number", "label": "WR MIA Over 65.5 receiving yards", "odds": 120, "book": "FanDuel",
                    "prob": 0.52, "verdict": "", "ticket_odds": 410, "ticket_ev": 0.08},
                   {"kind": "leg", "label": "WR BUF over 4.5 receptions", "player": "WR BUF",
                    "market": "receptions", "side": "over", "line": 4.5, "odds": -125, "prob": 0.66,
                    "verdict": "strong", "tier": "Strong", "found": "likely", "same_player": False,
                    "ticket_chance": 0.31, "ticket_odds": 238, "ticket_ev": 0.05, "approx": True}]}],
    "n_legs": 3, "n_priced": 2, "dropped": 0, "book": "", "stake": 10, "total_odds": 500, "ours": 0.2,
    "needs": 0.17, "ev": -0.02, "grade": "C*", "notes": [], "weakest": "WR MIA over 80.5 receiving yards",
    "swap": {"player": "WR BUF", "market": "receptions", "side": "over", "line": 4.5, "odds": -125, "prob": 0.66},
    "sim": None, "pairs": [], "alerts": [], "shop": None, "better": None, "first_kickoff": "", "now": None,
    "hedge": None,
}
PAGE["notes"] = [{"legs": ["Josh Allen over 5.5 carries", "RB BUF over 15.5 carries"], "kind": "kill",
                  "exclusive": False, "why": "two teammates splitting one rush_att pie"},
                 {"legs": ["BUF moneyline", "MIA moneyline"], "kind": "kill", "exclusive": True,
                  "why": "cannot both win"}]


def test_the_card_draws_the_read_a_refusal_and_the_better_legs():
    out = _node(_vm(f"process.stdout.write(S.card({json.dumps(PAGE)}));"))
    if out is None:
        return
    assert "Our read — not on our board · would be <b>Strong</b> on Most Likely · passes 2 of 4 checks" in out
    assert ("Not on our board — he is not one of the players our board prices in that game. "
            "Our model won’t price it: minutes that swing") in out
    assert "No number of ours" in out and "What we found" in out
    assert "<b>Better legs for this spot</b>" in out
    assert ('<span class="pgr-swap-k">Better number</span> <b>WR MIA Over 65.5 receiving yards</b> at +120 '
            "(FanDuel) — ours 52% · the ticket pays +410, return <b class=\"pos\">+8%</b>") in out
    assert ('<span class="pgr-swap-k">Strong</span> <b>WR BUF over 4.5 receptions</b> at -125 — ours 66% · '
            "the ticket pays +238 (about), return <b class=\"pos\">+5%</b>") in out
    assert '<span class="pgr-swap-k">Top pick</span> <b>Star MIA over 7.5 rebounds</b>' in out
    assert "Better legs for it are listed under it." in out and "Our likeliest pick in that game" not in out
    assert "<b>Our parlay engine never pairs these:</b> Josh Allen over 5.5 carries + RB BUF over 15.5 carries" in out
    assert "<b>These can’t both win:</b> BUF moneyline + MIA moneyline" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
