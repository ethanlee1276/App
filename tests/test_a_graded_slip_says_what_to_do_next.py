"""The parlay checker, past the grade: what to do with the ticket.

Ethan, 2026-10-13: "Ok so the hedge calculator and better number and saving
uploaded slips too moneys and live chances for props mid game. Make sure all
of this has been done and will be done and is done for all sports".

What is pinned, offline, on fixtures:

  * THE LIVE CHANCE (engine/proplive): a count that adds up, whose halves add
    to the whole; a race that starts at the card's own chance and moves with
    his number and the clock; a whole-number line's push kept out of both
    sides; the spread read off his own row, the range written as one SD
    either side (engine/betting.py); the scoreboard's own clock for every
    clock league and none for overtime; baseball through liveprops with the
    inning, his spot, the man due up and the mound;
  * EVERY LEAGUE'S LIVE STATE (engine/sliplive): hockey's lines off the
    loop's own box file (livescore_build.nhl_box_pass, under cache names the
    settlement never reads), baseball off live_mlb.json and its deep file,
    a saved leg finding its game by the card's label;
  * EVERY LEAGUE'S PRICE: an off-list prop in basketball, hockey and baseball
    gets a chance, its row's own at its own number;
  * THE BETTER NUMBER and THE HEDGE (engine/slipgrade), and the summary;
  * THE TRACKER (server `_ask_track`): gated, no picture, no model call, ten
    slips at most, each held to clean_slip again;
  * THE PAGE (js/slip.js): the chance, the better number, the hedge's
    arithmetic, Save to My Bets, the Live tab's settle rules — and app.js's
    hook, My Bets' paid price, the Live tab's host;
  * THE MEASUREMENT (engine/proplivefit): the replay folds play-by-play into
    player-games honestly (a no-catch game is a zero; a two-point try is no
    stat) and scores four arms.
"""
import itertools
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import proplive as PL                                 # noqa: E402
from engine import proplivefit as PF                              # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import sliplive as SL                                 # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
SLIP_JS = ROOT / "web" / "js" / "slip.js"
SRV = (ROOT / "server.py").read_text(encoding="utf-8")


# ---- the live chance ------------------------------------------------------------
def test_the_count_adds_up_and_its_halves_add_to_the_whole():
    for mean, disp in ((0.7, 1.0), (4.2, 1.0), (61.0, 15.0), (6.4, 1.3)):
        ps = list(itertools.islice(PL._pmf_iter(mean, disp), 4000))
        mu = sum(k * p for k, p in enumerate(ps))
        var = sum((k - mu) ** 2 * p for k, p in enumerate(ps))
        assert abs(sum(ps) - 1.0) < 1e-9 and abs(mu - mean) < 1e-6 * max(1.0, mean), (mean, disp)
        want = mean * (disp if disp > PL.POISSON_D else 1.0)
        assert abs(var - want) < 1e-5 * max(1.0, want), (mean, disp, var)
    # INDEPENDENT INCREMENTS: two halves of a game, each NegBin with half
    # the mean and the same ratio, add to the whole game exactly — which is
    # why "the rest of the game is the share left of it" is not a guess.
    half = list(itertools.islice(PL._pmf_iter(30.5, 15.0), 2000))
    whole = list(itertools.islice(PL._pmf_iter(61.0, 15.0), 2000))
    for k in (0, 10, 40, 61, 120, 300):
        conv = sum(half[i] * half[k - i] for i in range(k + 1))
        assert abs(conv - whole[k]) < 1e-12, k
    assert PL.at_least(0, 3.0, 1.0) == 1.0 and PL.exactly(2.5, 3.0, 1.0) == 0.0


def test_the_race_starts_where_the_card_starts():
    for p0 in (0.3, 0.55, 0.8):
        mu = PL.anchor(p0, 64.5, 15.0)
        assert abs(PL.p_over_full(64.5, mu, 15.0) - p0) < 1e-6
        win, push = PL.race("over", 64.5, 0.0, 1.0, mu, 15.0)
        assert abs(win - p0) < 1e-6 and push == 0.0, "at kickoff the live number is the card's"
        assert abs(PL.race("under", 64.5, 0.0, 1.0, mu, 15.0)[0] - (1 - p0)) < 1e-6
    # A WHOLE-NUMBER LINE: the push is neither side's, and the three add to one.
    mu = PL.anchor_side(0.40, "under", 5.0, 1.2)
    under, push = PL.race("under", 5.0, 0.0, 1.0, mu, 1.2)
    over, push2 = PL.race("over", 5.0, 0.0, 1.0, mu, 1.2)
    assert abs(under - 0.40) < 1e-6 and push > 0.05 and push == push2
    assert abs(over + under + push - 1.0) < 1e-9
    assert abs(PL.p_win_full("under", 5.0, mu, 1.2) - 0.40) < 1e-6
    assert PL.anchor(None, 5.5, 1.0) is None and PL.anchor(0.5, -1, 1.0) is None


def test_the_race_moves_with_his_number_and_the_clock():
    mu = PL.anchor(0.55, 64.5, 15.0)
    at_half = [PL.race("over", 64.5, b, 0.5, mu, 15.0)[0] for b in (0, 20, 40, 60)]
    assert at_half == sorted(at_half) and at_half[0] < 0.2 and at_half[-1] > 0.9, at_half
    assert PL.race("over", 64.5, 30, 0.25, mu, 15.0)[0] < PL.race("over", 64.5, 30, 0.5, mu, 15.0)[0], \
        "the same number with less game left is a worse over"
    assert PL.race("over", 64.5, 65, 0.5, mu, 15.0)[0] == 1.0, "past his number: the over is won"
    assert PL.race("under", 64.5, 65, 0.5, mu, 15.0)[0] == 0.0, "and the under is lost, whatever the clock"


def test_the_spread_is_his_own_when_his_row_carries_one():
    assert PL.row_dispersion({"projection": 60.0, "proj_std": 30.0}) == 15.0
    assert abs(PL.row_dispersion({"projection": 3.0, "sd": 1.8}) - 1.08) < 1e-9
    # THE RANGE IS ONE SD EITHER SIDE — engine/betting.py and the baseball
    # betting both write `mean - std` and `mean + std`. Read as a 10th-90th
    # span it would have shrunk every one of those spreads by a fifth.
    assert abs(PL.row_dispersion({"projection": 26.0, "proj_low": 20.0, "proj_high": 32.0}) - 36.0 / 26.0) < 1e-9
    assert "proj_low=round(proj.mean - proj.std, 1)" in (ROOT / "engine" / "betting.py").read_text()
    assert "proj_high=round(proj.mean + proj.std, 2)" in (ROOT / "engine" / "mlb" / "betting.py").read_text()
    # Baseball floors the low at zero; the high side, which nothing floors, says the SD.
    assert abs(PL.row_dispersion({"projection": 0.6, "proj_low": 0.0, "proj_high": 1.5}) - 0.81 / 0.6) < 1e-9
    assert PL.row_dispersion({"projection": 1.1, "proj_low": 0.2, "proj_high": 2.0}) == 1.0, \
        "a count tighter than Poisson is read as Poisson, never tighter"
    assert PL.row_dispersion({"projection": 60.0, "proj_std": 0}) is None
    assert PL.row_dispersion({"projection": 60.0, "proj_low": 70.0, "proj_high": 50.0}) is None
    assert PL.dispersion({}, "rec_yds") == PL.FALLBACK_D["rec_yds"] and PL.dispersion({}, "made_up") is None


def test_the_clock_is_the_scoreboards_own_in_every_clock_league():
    assert abs(PL.share_left("nfl", {"period": 3, "clock": "8:12"}) - 1392 / 3600) < 1e-12
    assert abs(PL.share_left("cfb", {"period": "Q1", "clock": "15:00"}) - 1.0) < 1e-12
    assert abs(PL.share_left("nba", {"period": 4, "clock": "2:00"}) - 120 / 2880) < 1e-12
    assert abs(PL.share_left("wnba", {"period": 2, "clock": "5:00"}) - 1500 / 2400) < 1e-12
    assert abs(PL.share_left("nhl", {"period": 2, "clock": "10:00"}) - 0.5) < 1e-12
    for lg, live in (("nfl", {"period": 5, "clock": "8:00"}), ("nhl", {"period": 4, "clock": "3:00"}),
                     ("nba", {"period": 2, "clock": ""}), ("mlb", {"period": "Top 5th"}), ("nfl", None)):
        assert PL.share_left(lg, live) is None, (lg, live)


def _live_leg(**kw):
    leg = {"league": "nfl", "market": "receptions", "side": "over", "line": 5.5, "prob": 0.70,
           "row": {"projection": 6.4, "proj_std": 1.9},
           "live": {"state": "live", "share_left": 0.5, "current": 3}}
    leg.update(kw)
    return leg


def test_a_prop_in_play_gets_its_chance_and_refuses_what_it_cannot_see():
    leg = _live_leg()
    ch = PL.clock_chance(leg)
    disp = PL.dispersion(leg["row"], "receptions")
    mu = PL.anchor(0.70, 5.5, disp)
    want, _ = PL.race("over", 5.5, 3, 0.5, mu, disp)
    assert ch["p"] == round(want, 4) and ch["model"] == "clock" and ch["from"] == "ours" and ch["share_left"] == 0.5
    assert ch["expected"] == round(3 + mu * 0.5, 1)
    under = PL.clock_chance(_live_leg(side="under", prob=0.30))
    assert abs(under["p"] - (1 - want)) <= 1e-4, "an under is its own side's chance, held to its own number"
    assert PL.clock_chance(_live_leg(prob=None, needs=0.6))["from"] == "price", \
        "a leg off our boards starts from its price's break-even, and says so"
    for bad in (dict(live={"state": "final", "share_left": 0.5, "current": 3}),
                dict(live={"state": "live", "share_left": 0.5, "current": 3, "result": "won"}),
                dict(live={"state": "live", "current": 3}),
                dict(live={"state": "live", "share_left": 0.0, "current": 3}),
                dict(live={"state": "live", "share_left": 0.5}),
                dict(prob=None, needs=None),
                dict(market="made_up", row={}),
                dict(side="team")):
        assert PL.clock_chance(_live_leg(**bad)) is None, bad
    td = PL.clock_chance(_live_leg(market="anytime_td", side="yes", line=0.5, prob=0.45, row={},
                                   live={"state": "live", "share_left": 0.5, "current": 0}))
    assert 0.2 < td["p"] < 0.45, "a scorer is a race to one, and half the game gone halves his chances"


def test_baseball_reads_the_inning_the_spot_and_the_mound():
    from engine.mlb import liveprops as lp
    assert PL.mlb_inning("Top 5th", 1) == (5, "Top", 1)
    assert PL.mlb_inning("Bottom 9th", 2) == (9, "Bottom", 2)
    assert PL.mlb_inning("Middle 3rd", 3) == (3, "Bottom", 0)
    assert PL.mlb_inning("End 7th", 3) == (8, "Top", 0)
    assert PL.mlb_inning("Delayed", 0) is None and PL.mlb_inning("", 0) is None
    board = {"recommendations": [{"player": "Aaron Judge", "market": "hits", "projection": 1.05},
                                 {"player": "Aaron Judge", "market": "home_runs", "projection": 0.32},
                                 {"player": "Gerrit Cole", "market": "strikeouts", "projection": 7.1}]}
    leg = {"league": "mlb", "player": "Aaron Judge", "market": "hits", "side": "over", "line": 1.5,
           "live": {"state": "live", "period": "Top 5th", "home_score": 2, "away_score": 1, "current": 1,
                    "situation": {"outs": 1, "is_home": False, "spot": 2, "batter_spot": 9}}}
    ch = PL.mlb_chance(leg, board)
    rates = lp.rates_for("hits", {"hits": 1.05, "home_runs": 0.32}, 2)
    n = lp.remaining_pa(2, 9, lp.outs_left(5, "Top", 1, False, 2, 1))
    assert ch["p"] == round(lp.hitter_probability(rates, "hits", 1.5, "OVER", 1, n), 4)
    assert ch["model"] == "mlb" and ch["left_unit"] == "plate appearances" and ch["left"] == round(n, 1)
    assert PL.leg_chance(leg, {"mlb": board}) == ch, "the router sends baseball to liveprops"
    k = dict(leg, player="Gerrit Cole", market="strikeouts", line=6.5, current=5,
             live=dict(leg["live"], current=5, situation={"outs": 1, "is_home": True, "on_mound": False, "bf": 22}))
    gone = PL.mlb_chance(k, board)
    assert gone["p"] == PL.FLOOR and gone["left"] == 0.0, "a starter who has left cannot add a strikeout"
    still = PL.mlb_chance(dict(k, live=dict(k["live"], situation=dict(k["live"]["situation"], on_mound=True))), board)
    assert still["p"] > gone["p"] and still["left_unit"] == "batters"
    nospot = dict(leg, live=dict(leg["live"], situation={"outs": 1, "is_home": False}))
    assert PL.mlb_chance(nospot, board) is None
    assert PL.mlb_chance(dict(leg, market="outs"), board) is None, "no model for outs: his number, no chance"


def test_the_router_borrows_the_main_rows_spread_for_a_seated_leg():
    boards = {"nfl": {"recommendations": [{"player": "Puka Nacua", "market": "receptions",
                                           "projection": 6.4, "proj_std": 2.6}]}}
    seat = {"player": "Puka Nacua", "market": "receptions", "side": "Over", "line": 5.5, "model_prob": 0.77}
    leg = _live_leg(player="Puka Nacua", prob=0.77, row=seat)
    got = PL.leg_chance(leg, boards)
    assert got == PL.clock_chance(leg, boards["nfl"]["recommendations"][0]), \
        "the seat carries the chance; the main row carries the spread"
    assert got != PL.clock_chance(leg, seat), "and the stock spread is not what was used"
    assert PL.leg_chance(dict(leg, market="moneyline"), boards) is None
    assert PL.leg_chance(dict(leg, league="ufc"), boards) is None


# ---- every league's live state -----------------------------------------------------
def _fast(files: dict, age_s: int = 0) -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "pbp").mkdir()
    for name, doc in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))
        if age_s:
            old = time.time() - age_s
            os.utime(p, (old, old))
    return d


NHL_SCORE = {"league": "nhl", "games": [{"event_id": "501", "home": "EDM", "away": "CGY",
                                         "live": {"state": "live", "home_score": 2, "away_score": 1,
                                                  "period": 2, "clock": "10:00"}}]}
NHL_BOX = {"generated_at": "2026-10-13T00:30:00Z", "games": [{"away": "CGY", "home": "EDM", "nhl_id": "2025020123",
           "state": "live", "players": [
               {"player": "Connor McDavid", "team": "EDM", "position": "C",
                "stats": {"sog": 3.0, "points": 1.0, "goals": 0.0, "assists": 1.0, "blocks": 0.0}},
               {"player": "L. Draisaitl", "team": "EDM", "position": "C", "stats": {"sog": 2.0, "points": 2.0}},
               {"player": "J. Smith", "team": "CGY", "position": "D", "stats": {"sog": 1.0}},
               {"player": "J. Smith", "team": "EDM", "position": "D", "stats": {"sog": 0.0}},
               {"player": "Stuart Skinner", "team": "EDM", "position": "G", "stats": {"saves": 14.0}}]}]}


def _nhl_leg(**kw):
    leg = {"league": "nhl", "player": "Connor McDavid", "team": "EDM", "opponent": "CGY", "market": "sog",
           "side": "over", "line": 3.5, "odds": -130}
    leg.update(kw)
    return leg


def test_hockey_reads_the_loops_own_box_file():
    fast = _fast({"live_nhl.json": NHL_SCORE, SL.NHL_BOX_FILE: NHL_BOX})
    st = SL.live_state(_nhl_leg(), fast)
    assert st["state"] == "live" and st["current"] == 3 and st["result"] is None
    assert st["clock"] == "P2 10:00" and st["share_left"] == 0.5 and st["period"] == 2
    assert SL.live_state(_nhl_leg(player="Leon Draisaitl", market="points", line=1.5), fast)["result"] == "won", \
        "the league's short name, matched on initial and surname when exactly one fits"
    smith = SL.live_state(_nhl_leg(player="John Smith", market="sog", line=0.5), fast)
    assert "current" not in smith and smith["note"] == "not in the box score yet", "two J. Smiths is a guess"
    assert SL.live_state(_nhl_leg(player="Stuart Skinner", market="saves", line=24.5), fast)["current"] == 14
    assert SL.live_state(_nhl_leg(market="anytime_goal", side="yes", line=0.5), fast)["current"] == 0
    stale = _fast({"live_nhl.json": NHL_SCORE})
    (stale / SL.NHL_BOX_FILE).write_text(json.dumps(NHL_BOX))
    old = time.time() - SL.FAST_FRESH_S - 60
    os.utime(stale / SL.NHL_BOX_FILE, (old, old))
    assert SL.live_state(_nhl_leg(), stale)["note"] == "not in the box score yet", "a stopped box file is no box"


MLB_FAST = {"games": [
    {"game_pk": 7001, "home": "NYY", "away": "BOS",
     "live": {"state": "final", "home_score": 5, "away_score": 2}},
    {"game_pk": 7002, "home": "NYY", "away": "BOS",
     "live": {"state": "live", "home_score": 1, "away_score": 2, "period": "Top 5th", "outs": 1}}]}
MLB_DEEP = {"current": {"batter": "Rafael Devers"}, "players": [
    {"player": "Aaron Judge", "team": "NYY", "spot": 2, "stats": {"hits": 1.0, "total_bases": 4.0, "home_runs": 1.0, "pa": 2.0}},
    {"player": "Juan Soto", "team": "NYY", "spot": 1, "stats": {"hits": 0.0, "total_bases": 0.0, "home_runs": 0.0, "pa": 3.0}},
    {"player": "Anthony Volpe", "team": "NYY", "spot": 3, "stats": {"hits": 0.0, "pa": 2.0}},
    {"player": "Gerrit Cole", "team": "NYY", "on_mound": True, "stats": {"strikeouts": 6.0, "ip": "4.1", "bf": 18.0}},
    {"player": "Rafael Devers", "team": "BOS", "spot": 3, "stats": {"hits": 1.0, "pa": 2.0}},
    {"player": "Brayan Bello", "team": "BOS", "on_mound": False, "stats": {"strikeouts": 4.0, "ip": "6.1", "bf": 26.0}}]}


def test_baseball_reads_live_mlb_and_its_deep_file():
    fast = _fast({SL.MLB_FILE: MLB_FAST, "pbp/mlb_7002.json": MLB_DEEP})
    leg = {"league": "mlb", "player": "Aaron Judge", "team": "NYY", "opponent": "BOS", "market": "hits",
           "side": "over", "line": 1.5}
    st = SL.live_state(leg, fast)
    assert st["state"] == "live" and st["current"] == 1 and st["clock"] == "Top 5th · 1 out", \
        "a doubleheader's live game is the leg's, not the earlier final"
    sit = st["situation"]
    # Boston is batting: the man at the plate is theirs, so Judge's side is
    # due the spot after its own seven trips — 7 % 9 + 1.
    assert sit == {"outs": 1, "is_home": True, "spot": 2, "batter_spot": 8}, sit
    bos = SL.live_state(dict(leg, player="Rafael Devers", team="BOS", opponent="NYY"), fast)
    assert bos["situation"]["batter_spot"] == 3 and bos["situation"]["is_home"] is False, \
        "his own side batting: the man at the plate's spot"
    k = SL.live_state(dict(leg, player="Gerrit Cole", market="strikeouts", line=6.5), fast)
    assert k["current"] == 6 and k["situation"]["on_mound"] is True and k["situation"]["bf"] == 18
    outs = SL.live_state(dict(leg, player="Brayan Bello", team="BOS", opponent="NYY", market="outs", line=17.5), fast)
    assert outs["current"] == 19 and outs["result"] == "won", "6.1 innings is nineteen outs"
    tb = SL.live_state(dict(leg, market="total_bases", line=1.5), fast)
    assert tb["result"] == "won"
    assert [SL._ip_outs(x) for x in ("6.1", "0.2", "7", "", "x")] == [19.0, 2.0, 21.0, 0.0, 0.0]


def test_a_saved_leg_finds_its_game_by_the_cards_label():
    fast = _fast({"live_nfl.json": {"games": [{"event_id": "401", "home": "LA", "away": "BUF",
                                               "live": {"state": "live", "home_score": 7, "away_score": 3,
                                                        "period": 2, "clock": "4:00"}}]}})
    saved = {"league": "nfl", "player": "Kyren Williams", "team": "Rams", "game": "BUF @ LA",
             "market": "rush_yds", "side": "over", "line": 69.5}
    assert SL.live_state(saved, fast)["state"] == "live", \
        "a slip saved yesterday still carries its game's codes, whatever the board says today"
    assert SL.live_state(dict(saved, team="LA", game=""), fast)["state"] == "live"
    assert SL.live_state(dict(saved, team="Rams", game=""), fast) is None, "a name the scoreboard never uses finds nothing"
    assert SL.live_state(dict(saved, team="LA", opponent="DEN", game=""), fast) is None, \
        "two teams named means both, never one of them"


def test_the_loop_writes_hockeys_box_under_its_own_cache_names():
    import datetime as dt
    import livescore_build as LB
    day = {"games": [{"id": 2025020123, "gameType": 2, "gameState": "LIVE", "startTimeUTC": "2026-10-13T00:00:00Z",
                      "homeTeam": {"abbrev": "EDM", "score": 2}, "awayTeam": {"abbrev": "CGY", "score": 1},
                      "periodDescriptor": {"number": 2, "periodType": "REG"}, "clock": {"timeRemaining": "10:00"}}]}
    box = {"homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "CGY"}, "playerByGameStats": {
        "homeTeam": {"forwards": [{"playerId": 8478402, "name": {"default": "C. McDavid"}, "position": "C",
                                   "goals": 0, "assists": 1, "points": 1, "sog": 3, "toi": "14:10"}],
                     "defense": [], "goalies": [{"playerId": 8479973, "name": {"default": "S. Skinner"},
                                                 "saves": 14, "shotsAgainst": 15, "toi": "30:00", "starter": True}]},
        "awayTeam": {"forwards": [], "defense": [], "goalies": []}}}
    asked = []

    def fetch_day(d):
        asked.append(("day", d))
        return day if d == "2026-10-12" else {"games": []}

    def fetch_box(gid, final=False):
        asked.append(("box", gid, final))
        return box
    out = Path(tempfile.mkdtemp())
    games = [{"home": "EDM", "away": "CGY", "live": {"state": "live"}},
             {"home": "TOR", "away": "MTL", "live": {"state": "scheduled"}}]
    note = LB.nhl_box_pass(games, out, fetch_day=fetch_day, fetch_box=fetch_box,
                           names={"8478402": "Connor McDavid"}, today=dt.date(2026, 10, 13))
    doc = json.loads((out / LB.NHL_BOX_FILE).read_text())
    g = doc["games"][0]
    assert (g["away"], g["home"], g["state"]) == ("CGY", "EDM", "live") and note.startswith("nhl box: 1 of 1")
    mc = next(p for p in g["players"] if p["team"] == "EDM" and p["position"] == "C")
    assert mc["player"] == "Connor McDavid" and mc["stats"]["sog"] == 3.0 and mc["stats"]["points"] == 1.0
    sk = next(p for p in g["players"] if p["position"] == "G")
    assert sk["player"] == "S. Skinner" and sk["stats"]["saves"] == 14.0, "no roster name: the league's short one"
    assert ("day", "2026-10-13") in asked and ("day", "2026-10-12") in asked, "a late game runs past midnight"
    assert ("box", "2025020123", False) in asked
    assert LB.nhl_box_pass([{"live": {"state": "scheduled"}}], out) == "", "nothing on: nothing read"
    # THE SETTLEMENT READS `nhl_box_{id}` FOR A MONTH: a mid-game snapshot
    # written there would be graded as the final. The loop's names are its own.
    src = (ROOT / "livescore_build.py").read_text()
    body = src[src.index("def nhl_box_pass("):src.index("def main(")]
    assert 'f"nhl_live_score_{d}.json"' in body and 'f"nhl_live_box_{gid}.json"' in body
    assert '"nhl_box_' not in body and "fetch_boxscore(" not in body
    assert "nhl_box_pass(payload.get(\"games\") or [], Path(out_dir))" in src


def test_the_baseball_box_carries_the_lineup_spot_and_the_mound():
    from engine.mlb.livestats import box_rows

    def player(pid, name, order=None, bat=None, pit=None, pos="RF"):
        p = {"person": {"id": pid, "fullName": name}, "position": {"abbreviation": pos},
             "stats": {"batting": bat or {}, "pitching": pit or {}}}
        if order:
            p["battingOrder"] = order
        return {f"ID{pid}": p}
    home = {**player(1, "Aaron Judge", "200", {"hits": 1, "doubles": 0, "triples": 0, "homeRuns": 1, "plateAppearances": 2}),
            **player(2, "Pinch Hitter", "201", {"hits": 0, "plateAppearances": 1}),
            **player(3, "Gerrit Cole", None, None, {"strikeOuts": 6, "inningsPitched": "4.1", "battersFaced": 18}, "P"),
            **player(4, "Luke Weaver", None, None, {"strikeOuts": 0, "inningsPitched": "0.0", "battersFaced": 0}, "P")}
    boxscore = {"teams": {"home": {"players": home, "pitchers": [3, 4]}, "away": {"players": {}, "pitchers": []}}}
    rows = {r["player"]: r for r in box_rows(boxscore, home="NYY", away="BOS")}
    assert rows["Aaron Judge"]["spot"] == 2 and rows["Pinch Hitter"]["spot"] == 2, "a sub bats in the spot he took"
    assert rows["Luke Weaver"]["on_mound"] is True and rows["Gerrit Cole"]["on_mound"] is False
    for r in rows.values():
        assert "spot" not in r["stats"] and "on_mound" not in r["stats"], "beside the stats: the box table draws every stat"


# ---- every league's price ------------------------------------------------------------
def _board(league, rows):
    return {league: {"recommendations": rows}}


def test_every_league_prices_its_off_list_props():
    cases = [
        ("nba", {"player": "Jalen Brunson", "team": "NYK", "opponent": "BOS", "market": "pts", "side": "Over",
                 "line": 25.5, "odds": -115, "projection": 27.1, "proj_low": 21.1, "proj_high": 33.1, "hit_prob": 0.58}),
        ("wnba", {"player": "A'ja Wilson", "team": "LV", "opponent": "SEA", "market": "reb", "side": "Under",
                  "line": 10.5, "odds": -110, "projection": 9.6, "proj_low": 6.6, "proj_high": 12.6, "hit_prob": 0.57}),
        ("nhl", {"player": "Connor McDavid", "team": "EDM", "opponent": "CGY", "market": "sog", "side": "Over",
                 "line": 3.5, "odds": -125, "projection": 4.1, "sd": 2.1, "hit_prob": 0.55}),
        ("mlb", {"player": "Aaron Judge", "team": "NYY", "opponent": "BOS", "market": "total_bases", "side": "Over",
                 "line": 1.5, "odds": 120, "projection": 1.9, "proj_low": 0.4, "proj_high": 3.4, "hit_prob": 0.47}),
    ]
    for league, row in cases:
        boards = _board(league, [row])
        side = row["side"].lower()
        at = SG.price_leg(boards, {"sport": league, "player": row["player"], "team": "", "game": "",
                                   "market": row["market"], "side": side, "line": row["line"],
                                   "odds": row["odds"], "text": ""})
        assert at["found"] == "prop" and abs(at["prob"] - row["hit_prob"]) < 1e-3, (league, at["prob"])
        lower = row["line"] - 1.0
        moved = SG.price_leg(boards, {"sport": league, "player": row["player"], "team": "", "game": "",
                                      "market": row["market"], "side": side, "line": lower,
                                      "odds": row["odds"], "text": ""})
        assert moved["prob"] is not None, league
        assert (moved["prob"] > at["prob"]) == (side == "over"), (league, "a lower number is an easier over")


def test_a_whole_number_keeps_its_push_out_of_both_sides():
    row = {"player": "X", "market": "pts", "side": "Over", "line": 24.5, "projection": 25.0,
           "proj_low": 19.0, "proj_high": 31.0, "hit_prob": 0.55}
    over = SG.prob_at_line(row, "pts", "over", 25.0)
    under = SG.prob_at_line(row, "pts", "under", 25.0)
    mu = PL.anchor_side(0.55, "over", 24.5, PL.dispersion(row, "pts"))
    push = PL.exactly(25.0, mu, PL.dispersion(row, "pts"))
    assert abs(over + under + push - 1.0) < 2e-4 and push > 0.02
    assert abs(SG.prob_at_line(row, "pts", "over", 24.5) - 0.55) < 1e-4, "its own number at its own chance"


# ---- the better number -----------------------------------------------------------------
REC = {"player": "Davante Adams", "team": "LA", "opponent": "BUF", "market": "rec_yds", "side": "Over",
       "line": 69.5, "odds": -115, "projection": 71.0, "proj_std": 22.0, "recent_values": [70, 60, 80],
       "all_lines": [{"book": "DraftKings", "line": 69.5, "over_odds": -115, "under_odds": -105},
                     {"book": "FanDuel", "line": 69.5, "over_odds": -112, "under_odds": -108}],
       "alt_lines": [{"book": "FanDuel", "line": 59.5, "over_odds": -150, "under_odds": 120},
                     {"book": "DraftKings", "line": 49.5, "over_odds": -300, "under_odds": 230},
                     {"book": "Pinnacle", "line": 59.5, "over_odds": -110, "under_odds": -110}]}
NFL = {"nfl": {"recommendations": [REC], "games": [{"home": "LA", "away": "BUF", "date": "2026-10-18", "kickoff": "16:25"}]}}


def _adams(**kw):
    leg = {"sport": "nfl", "player": "Davante Adams", "team": "", "game": "", "market": "rec_yds",
           "side": "over", "line": 69.5, "odds": -115, "text": ""}
    leg.update(kw)
    return leg


def test_a_better_number_is_the_card_s_own_chance_at_another_book_s_number():
    leg = SG.price_leg(NFL, _adams())
    idx = SL.quote_index(NFL["nfl"])
    bn = SG.better_number(leg, idx, NFL)
    raw59 = SG.prob_at_line(REC, "rec_yds", "over", 59.5)
    p59 = SG._honest("nfl", raw59, "over", -150)
    raw49 = SG.prob_at_line(REC, "rec_yds", "over", 49.5)
    ev = {59.5: p59 * SG.to_decimal(-150) - 1, 49.5: SG._honest("nfl", raw49, "over", -300) * SG.to_decimal(-300) - 1}
    best = max(ev, key=ev.get)
    ev_here = leg["prob"] * SG.to_decimal(-115) - 1
    assert best == 59.5 and ev[best] >= ev_here + SG.BETTER_NUMBER_GAIN, "the fixture is built to have one"
    assert bn["line"] == 59.5 and bn["book"] == "FanDuel" and bn["odds"] == -150
    assert bn["p_here"] == round(leg["prob"], 4), "the slip's number at the card's own chance"
    assert abs(bn["ev"] - round(ev[best], 4)) < 1e-4 and bn["label"] == f"Over {best:g}"
    assert bn["book"] != "Pinnacle", "the sharp book is a reference, never a price to take"


def test_a_better_number_needs_the_gain_and_a_ladder():
    leg = SG.price_leg(NFL, _adams())
    idx = SL.quote_index(NFL["nfl"])
    rich = dict(idx)
    key = (SG._key("Davante Adams"), "rec_yds")
    rich[key] = dict(idx[key], quotes=idx[key]["quotes"] + [(59.5, "Caesars", 150, -180)])
    bn = SG.better_number(leg, rich, NFL)
    assert bn and bn["line"] == 59.5 and bn["odds"] == 150 and bn["book"] == "Caesars", \
        "Over 59.5 at +150 beats Over 69.5 at -115 by any honest model"
    assert bn["ev"] >= bn["ev_here"] + SG.BETTER_NUMBER_GAIN and bn["p"] > bn["p_here"]
    thin = dict(idx)
    thin[key] = dict(idx[key], quotes=[q for q in idx[key]["quotes"] if q[0] == 69.5])
    assert SG.better_number(leg, thin, NFL) is None, "no other number: nothing to name"
    assert SG.better_number(dict(leg, market="moneyline"), rich, NFL) is None
    assert SG.better_number(dict(leg, prob=None), rich, NFL) is None, "no chance of ours at the slip's number: no comparison"
    # On the card: the ticket at the better number, and the summary's line.
    card = SG.grade({"legs": [_adams(), {"sport": "nfl", "player": "", "team": "Bills", "game": "", "market": "moneyline",
                                         "side": "team", "line": 0, "odds": 120, "text": ""}], "total_odds": 300},
                    NFL, live=SL.Live({"nfl": rich}, fast_dir=_fast({})))
    adams = next(l for l in card["legs"] if l["player"] == "Davante Adams")
    bn = adams["better_number"]
    assert bn["line"] == 59.5
    # The ticket at the better number: its payout by the two prices' ratio,
    # its chance by the model's own ratio between the two numbers.
    assert bn["ticket_odds"] == SG.from_decimal(SG.to_decimal(300) * SG.to_decimal(150) / SG.to_decimal(-115))
    pay2 = SG.to_decimal(300) * SG.to_decimal(150) / SG.to_decimal(-115)
    assert abs(bn["ticket_ev"] - round(card["ours"] * bn["p"] / bn["p_here"] * pay2 - 1, 4)) < 2e-3
    assert "Better number for Davante Adams over 69.5 receiving yards: Over 59.5 at +150 (Caesars)" in SG.summary(card)


# ---- the hedge ----------------------------------------------------------------------
GAMES = {"nfl": {"recommendations": [], "games": [
    {"home": "LA", "away": "BUF", "date": "2026-10-18", "kickoff": "13:00"},
    {"home": "KC", "away": "DEN", "date": "2026-10-18", "kickoff": "16:25"}],
    "game_bets": [
        {"bet_type": "moneyline", "market": "moneyline", "home": "LA", "away": "BUF", "team": "LA", "pick": "LA",
         "pick_is_home": True, "win_prob": 0.58, "odds": -140, "home_odds": -140, "away_odds": 120,
         "home_book": "FanDuel", "away_book": "DraftKings", "book": "FanDuel", "has_market": True, "fair_prob": 0.57},
        {"bet_type": "moneyline", "market": "moneyline", "home": "KC", "away": "DEN", "team": "KC", "pick": "KC",
         "pick_is_home": True, "win_prob": 0.66, "odds": -180, "home_odds": -180, "away_odds": 155,
         "home_book": "BetMGM", "away_book": "Caesars", "book": "BetMGM", "has_market": True, "fair_prob": 0.63}]}}


def _ml(team, odds):
    return {"sport": "nfl", "player": "", "team": team, "game": "", "market": "moneyline", "side": "team",
            "line": 0, "odds": odds, "text": f"{team} ML"}


def _scores(first_state="final", first_home=24, first_away=20):
    return _fast({"live_nfl.json": {"games": [
        {"event_id": "1", "home": "LA", "away": "BUF",
         "live": {"state": first_state, "home_score": first_home, "away_score": first_away, "period": 4, "clock": "0:00"}},
        {"event_id": "2", "home": "KC", "away": "DEN", "live": {"state": "scheduled"}}]}})


def test_one_leg_left_the_hedge_locks_or_wins_the_stake_back():
    slip = {"legs": [_ml("Rams", -140), _ml("Chiefs", -180)], "total_odds": 170, "stake": 20}
    card = SG.grade(slip, GAMES, live=SL.Live({"nfl": {}}, fast_dir=_scores()))
    h = card["hedge"]
    assert h and h["plan"] is False and h["leg"] == "KC moneyline" and h["other"] == "DEN moneyline"
    assert h["odds"] == 155 and h["book"] == "Caesars" and h["stale"] is False
    W = 20 * SG.to_decimal(170)
    d = SG.to_decimal(155)
    assert h["payout"] == round(SG.to_decimal(170), 4) and h["stake"] == 20
    assert h["lock"] == {"hedge": round(W / d, 2), "either": round(W - 20 - W / d, 2)}
    assert h["back"] == {"hedge": round(20 / (d - 1), 2), "if_hits": round(W - 20 - 20 / (d - 1), 2)}
    assert h["p_leg"] == 0.66 and h["from"] == "ours"
    assert f"One leg left, KC moneyline: {W / d:.2f} on DEN moneyline at +155 locks" in SG.summary(card)


def test_before_kickoff_it_is_a_plan_for_the_last_leg_and_a_push_shortens_it():
    slip = {"legs": [_ml("Rams", -140), _ml("Chiefs", -180)], "total_odds": 170, "stake": 20}
    plan = SG.grade(slip, GAMES, live=SL.Live({"nfl": {}}, fast_dir=_fast({})))["hedge"]
    assert plan["plan"] is True and plan["leg"] == "KC moneyline", "the leg that kicks off last"
    assert "If the rest hit, the last leg is KC moneyline" in SG.summary(SG.grade(slip, GAMES, live=SL.Live({"nfl": {}}, fast_dir=_fast({}))))
    same = {"nfl": dict(GAMES["nfl"], games=[dict(g, kickoff="13:00") for g in GAMES["nfl"]["games"]])}
    assert SG.grade(slip, same, live=SL.Live({"nfl": {}}, fast_dir=_fast({})))["hedge"] is None, \
        "two legs at the same kickoff have no last leg"
    lost = SG.grade(slip, GAMES, live=SL.Live({"nfl": {}}, fast_dir=_scores(first_home=17)))
    assert lost["hedge"] is None, "a ticket that has lost has nothing to hedge"
    pushed = SG.grade(slip, GAMES, live=SL.Live({"nfl": {}}, fast_dir=_scores(first_home=20)))
    assert abs(pushed["hedge"]["payout"] - round(SG.to_decimal(170) / SG.to_decimal(-140), 4)) < 1e-4, \
        "a pushed leg comes out of the payout"
    assert SG.hedge([SG.price_leg(GAMES, _ml("Rams", -140))], slip, 2.7) is None, "one leg is no parlay"


def test_a_prop_hedge_is_the_other_side_at_the_same_number():
    leg = SG.price_leg(NFL, _adams())
    pr = SL.leg_prices(leg, SL.quote_index(NFL["nfl"]), NFL["nfl"])
    assert pr["other"] == {"book": "DraftKings", "odds": -105}, "the best under at 69.5 a bettor can take"
    assert SG._other_name(leg) == "Davante Adams Under 69.5 receiving yards"
    assert SG._other_name(dict(leg, market="anytime_td", side="yes")) == "Davante Adams not to score"


# ---- the tracker -------------------------------------------------------------------
def test_the_tracker_route_is_bounded_and_before_ask():
    route = SRV.index('if parsed.path in ("/api/ask/track", "/api/ask/track/"):')
    assert SRV.index('if parsed.path in ("/api/ask/slip", "/api/ask/slip/"):') < route < \
        SRV.index('if parsed.path in ("/api/ask", "/api/ask/"):')
    head = SRV[route:SRV.index("return self._ask_track(body)", route)]
    assert "length > MAX_TRACK_BYTES" in head and "413" in head
    import server
    assert server.MAX_TRACK_SLIPS == 10 and server.MAX_TRACK_BYTES <= 64_000
    assert server.RATE_TRACK_PER_MIN <= 6


def _track_body():
    i = SRV.index("    def _ask_track(self")
    return SRV[i:SRV.index("\n    def ", i + 10)]


def test_the_tracker_reads_no_picture_and_spends_nothing():
    body = _track_body()
    order = ['self._rate_limited(RATE_TRACK_PER_MIN, "track")', "self._entitled(conn, who)",
             "len(raw) > MAX_TRACK_SLIPS", "AB.board_at(path)", "SG.clean_slip(dict(s, is_bet_slip=True))",
             "SG.grade(slip, boards, live=live, brief=True)"]
    at = [body.index(x) for x in order]
    assert at == sorted(at), dict(zip(order, at))
    for never in ("read_slip", "decode_image", "count_question", "over_limit", "sign_turn", "open(", ".write_"):
        assert never not in body, never
    assert "401 if not who else 402" in body


class _Conn:
    def close(self):
        pass


def _handler(entitled=True, who=None):
    import server
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
    h._rate_limited = lambda limit, bucket="read": False
    h._account = lambda conn: who if who is not None else {"id": 7}
    h._entitled = lambda conn, w: entitled
    return h, sent


def test_the_tracker_grades_saved_slips_off_the_live_files():
    import server
    from engine import askbot as AB
    from engine import gate as GATE_
    boards_dir = Path(tempfile.mkdtemp())
    (boards_dir / "recommendations.json").write_text(json.dumps(GAMES["nfl"]))
    fast = _scores()
    saved = (server._acct, GATE_.full_board_file, SL.FAST_DIR)
    server._acct = lambda: type("A", (), {"connect": staticmethod(lambda: _Conn())})()
    GATE_.full_board_file = lambda name: (boards_dir / name) if name == AB.BOARD_FILES["nfl"] else None
    SL.FAST_DIR = fast
    try:
        h, sent = _handler()
        slips = [{"id": "17604", "legs": [dict(_ml("LA", -140), game="BUF @ LA"), dict(_ml("KC", -180), game="DEN @ KC")],
                  "stake": 20, "total_odds": 170, "book": "FanDuel"},
                 {"id": "junk", "legs": [{"market": "not a market"}]}]
        h._ask_track({"slips": slips})
        code, out = sent[-1]
        assert code == 200, out
        card = out["slips"][0]
        assert card["id"] == "17604" and card["slip"]["now"]["won"] == 1 and card["slip"]["now"]["status"] == "open"
        assert card["slip"]["hedge"]["leg"] == "KC moneyline" and card["slip"]["sim"] is None, "brief: no replay"
        assert out["slips"][1] == {"id": "junk", "error": "no legs to track"}
        h._ask_track({"slips": []})
        assert sent[-1][0] == 400
        h._ask_track({"slips": slips * 6})
        assert sent[-1][0] == 400, "eleven or more slips is not a Live tab"
        locked, sent2 = _handler(entitled=False, who={})
        locked._ask_track({"slips": slips})
        assert sent2[-1][0] == 401 and sent2[-1][1]["locked"] is True
        lapsed, sent3 = _handler(entitled=False, who={"id": 9})
        lapsed._ask_track({"slips": slips})
        assert sent3[-1][0] == 402
    finally:
        server._acct, GATE_.full_board_file, SL.FAST_DIR = saved


# ---- the page --------------------------------------------------------------------------
def _node(script: str) -> str | None:
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    return out.stdout


def _vm(body: str, book: bool = False) -> str:
    stub = ("let BETS = []; ctx.mbLoad = () => JSON.parse(JSON.stringify(BETS));"
            "ctx.mbSave = (b) => { BETS = JSON.parse(JSON.stringify(b)); };") if book else ""
    return ("const vm = require('vm'); const fs = require('fs');"
            f"const ctx = {{ window: {{}} }}; {stub} vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
            "const S = ctx.window.QBSlip;" + body)


LIVE = {"state": "live", "home": "LA", "away": "BUF", "home_score": 17, "away_score": 10, "clock": "8:12 - 3rd",
        "current": 4, "chance": {"p": 0.41, "push": 0.0, "share_left": 0.387, "from": "ours", "model": "clock",
                                 "expected": 5.2}}
PAGE_CARD = {
    "legs": [
        {"sport": "nfl", "league": "nfl", "player": "Puka Nacua", "team": "LA", "game": "BUF @ LA", "market": "receptions",
         "side": "over", "line": 5.5, "odds": -140, "prob": 0.77, "needs": 0.58, "verdict": "strong", "found": "likely",
         "live": LIVE},
        {"sport": "nfl", "league": "nfl", "player": "Davante Adams", "team": "LA", "game": "BUF @ LA", "market": "rec_yds",
         "side": "over", "line": 69.5, "odds": -115, "prob": 0.52, "needs": 0.53, "verdict": "weak", "found": "prop",
         "kickoff": "2026-10-18 16:25",
         "better_number": {"line": 59.5, "odds": 150, "book": "Caesars", "p": 0.66, "ev": 0.65, "p_here": 0.52,
                           "ev_here": -0.03, "side": "over", "label": "Over 59.5", "ticket_odds": 480, "ticket_ev": 0.4}},
        {"sport": "mlb", "league": "mlb", "player": "Aaron Judge", "team": "NYY", "game": "BOS @ NYY", "market": "hits",
         "side": "over", "line": 1.5, "odds": 150, "prob": 0.35, "needs": 0.4, "verdict": "weak", "found": "prop",
         "live": {"state": "live", "home": "NYY", "away": "BOS", "home_score": 1, "away_score": 2, "clock": "Top 5th · 1 out",
                  "current": 1, "chance": {"p": 0.38, "push": 0.0, "from": "ours", "model": "mlb", "left": 2.4,
                                           "left_unit": "plate appearances"}}}],
    "n_legs": 3, "n_priced": 3, "dropped": 0, "book": "FanDuel", "stake": 10, "total_odds": 900, "ours": 0.14,
    "needs": 0.1, "ev": 0.4, "grade": "A", "notes": [], "weakest": "", "swap": None, "sim": None, "pairs": [],
    "alerts": [], "shop": None, "better": None, "first_kickoff": "2026-10-18 13:00",
    "now": {"won": 0, "lost": 0, "push": 0, "live": 2, "status": "open", "left": 3, "start": 1, "chance": 0.12},
    "hedge": {"leg": "Davante Adams over 69.5 receiving yards", "other": "Davante Adams Under 69.5 receiving yards",
              "plan": True, "odds": -105, "book": "DraftKings", "stale": False, "stake": 10, "payout": 10.0,
              "approx": True, "p_leg": 0.52, "from": "ours"},
}


def test_the_card_draws_the_live_chance_the_better_number_and_the_hedge():
    out = _node(_vm(f"process.stdout.write(S.card({json.dumps(PAGE_CARD)}));"))
    if out is None:
        return
    assert "Our chance now <b>41%</b> · on course for about 5.2" in out
    assert "Our chance now <b>38%</b> · about 2.4 plate appearances left" in out
    assert "our chance for the rest <b>12%</b>" in out
    assert ("<b>Better number:</b> Over 59.5 at +150 (Caesars) — ours 66% vs 52% at your number, return "
            '<b class="pos">+65%</b> vs −3% a dollar. The ticket would pay +480, return +40%.') in out
    assert "<b>Hedge plan</b> — if the rest hit, <b>Davante Adams over 69.5 receiving yards</b> decides the ticket." in out
    assert "The hedge is <b>Davante Adams Under 69.5 receiving yards</b>." in out
    assert 'data-hedge="odds" inputmode="numeric" value="-105"' in out and 'data-pay="10"' in out
    assert "Same-game parlays pay their own way" in out and "our last pull: DraftKings -105." in out
    assert "data-save-slip" not in out, "no My Bets on the page, no Save"


def test_the_hedges_arithmetic():
    out = _node(_vm("process.stdout.write(JSON.stringify([S.hedgeOut(10, 3.1, -150, 0.7, 'X'),"
                    "S.hedgeOut(10, 3.1, -150, '', 'X'), S.hedgeOut('', 3.1, -150, 0.7, 'X'),"
                    "S.hedgeOut(10, 1.2, -150, 0.7, 'X')]));"))
    if out is None:
        return
    full, nop, empty, none = json.loads(out)
    # W = 31; d = 5/3; H = W/d = 18.60, either = 31 - 10 - 18.60 = 2.40;
    # B = 10/(2/3) = 15.00, if it hits 31 - 10 - 15 = 6.00; by our 70% the
    # hedge bet is worth 18.60 × (0.3 × 5/3 − 1) = −9.30.
    assert "No hedge: <b class=\"pos\">+$21.00</b> if it hits, <b class=\"neg\">−$10.00</b> if it misses." in full
    assert "Lock it: bet <b>$18.60</b> and you’re up <b class=\"pos\">$2.40</b> whichever way it goes." in full
    assert "Stake back: bet <b>$15.00</b> — <b class=\"pos\">+$6.00</b> if it hits, $0.00 if it misses." in full
    assert "By our 70% for X, locking costs about <b>$9.30</b> in expected value." in full
    assert "By our" not in nop and "Type your stake" in empty
    assert "no hedge locks a profit" in none


def test_save_puts_the_slip_in_my_bets_with_its_legs():
    out = _node(_vm(f"""
        const card = {json.dumps(PAGE_CARD)};
        const html = S.card(card);
        const key = S.slipKey(card);
        const flipped = Object.assign({{}}, card, {{ legs: card.legs.slice().reverse() }});
        const e = S.entryOf(card, 25, 900, key);
        BETS = [e];
        const again = S.card(card);
        process.stdout.write(JSON.stringify({{ html, key, same: S.slipKey(flipped) === key, e, again }}));
    """, book=True))
    if out is None:
        return
    got = json.loads(out)
    assert 'data-save-key="' + got["key"] + '"' in got["html"] and "data-save-slip" in got["html"]
    assert 'data-save-stake inputmode="decimal" value="10"' in got["html"], "the slip's own stake, filled in"
    assert got["same"], "the same ticket read in another order is the same ticket"
    e = got["e"]
    assert e["src"] == "slip" and e["slip_key"] == got["key"] and e["result"] == "pending"
    assert e["stake"] == 25 and e["odds"] == 900 and e["book"] == "FanDuel" and e["date"] == "2026-10-18"
    assert e["sport"] == "Other", "an NFL and MLB ticket is no one sport"
    assert e["desc"].startswith("3-leg parlay: Puka Nacua Over 5.5 Receptions + ")
    assert e["legs"][0] == {"sport": "nfl", "player": "Puka Nacua", "team": "LA", "game": "BUF @ LA",
                            "market": "receptions", "side": "over", "line": 5.5, "odds": -140}, \
        "the board's names and codes, and the game that finds it tomorrow"
    assert "Saved to My Bets · followed on the Live tab." in got["again"] and "data-save-slip" not in got["again"]


def test_the_tracker_settles_what_the_box_score_settles():
    out = _node(_vm("""
        const mk = (now, legs) => ({ now, legs: legs || [] });
        const base = () => ({ result: "pending", odds: 600, stake: 10 });
        const cases = {
          lost: [base(), mk({ status: "lost", won: 0, push: 0 })],
          won: [base(), mk({ status: "won", won: 3, push: 0 })],
          allpush: [base(), mk({ status: "won", won: 0, push: 2 })],
          pushwin: [base(), mk({ status: "won", won: 2, push: 1 },
                    [{ odds: 100, live: { result: "push" } }, { odds: -110, live: { result: "won" } }])],
          pushunknown: [base(), mk({ status: "won", won: 2, push: 1 }, [{ odds: 0, live: { result: "push" } }])],
          open: [base(), mk({ status: "open", won: 1, push: 0 })],
          already: [Object.assign(base(), { result: "loss" }), mk({ status: "won", won: 3, push: 0 })],
        };
        const out = {};
        for (const [k, [b, c]] of Object.entries(cases)) { const moved = S.settleOne(b, c); out[k] = { moved, b }; }
        process.stdout.write(JSON.stringify(out));
    """))
    if out is None:
        return
    got = json.loads(out)
    assert got["lost"]["b"]["result"] == "loss" and got["lost"]["b"]["settled_by"] == "box"
    assert got["won"]["b"]["result"] == "win" and "paid_odds" not in got["won"]["b"]
    assert got["allpush"]["b"]["result"] == "push"
    # +600 is 7.0; without the even-money leg that pushed it pays 3.5 — +250.
    assert got["pushwin"]["b"]["result"] == "win" and got["pushwin"]["b"]["paid_odds"] == 250
    assert got["pushunknown"]["b"]["result"] == "pending" and "set the price your book paid" in got["pushunknown"]["b"]["settle_note"]
    assert got["open"]["moved"] is False and got["already"]["moved"] is False, "a settled bet is the reader's"


def test_app_js_hooks_the_live_tab_and_my_bets_reads_the_paid_price():
    i = APP.index("function liveSlips(")
    hook = APP[i:APP.index("\n}\n", i)]
    assert 'document.getElementById("live-slips")' in hook and 'b.src === "slip" && b.result === "pending"' in hook
    assert "S.track(h, { load: mbLoad, save: mbSave, live: () => state.view === \"live\" })" in hook
    live = APP[APP.index("async function renderLiveBoard("):]
    assert live.index("liveSlips();") < live.index("await fetchAllLive()")
    prof = APP[APP.index("function mbProfit("):]
    assert "mbDecimal(bet.paid_odds || bet.odds)" in prof[:prof.index("\n}\n")]
    view = HTML[HTML.index('<section class="view" id="view-live">'):]
    view = view[:view.index("</section>")]
    assert view.index('id="live-board"') < view.index('id="live-slips"') < view.index('id="sweat-zone"')
    js = SLIP_JS.read_text(encoding="utf-8")
    assert 'fetch("/api/ask/track"' in js and "const TRACK_MS = 60000;" in js
    assert 'document.addEventListener("input"' in js and 'document.addEventListener("click"' in js
    assert "onclick" not in js and "oninput" not in js, "no inline handlers: the page's policy forbids them"
    # My Bets' profit, run: a slip that won with a leg pushed pays its paid price.
    i = APP.index("function mbDecimal(")
    dec = APP[i:APP.index("\n}\n", i) + 3]
    i = APP.index("function mbProfit(")
    prof = APP[i:APP.index("\n}\n", i) + 3]
    out = _node(dec + prof + "process.stdout.write(JSON.stringify([mbProfit({result:'win',stake:10,odds:600,paid_odds:250}),"
                "mbProfit({result:'win',stake:10,odds:600})]));")
    if out is not None:
        assert json.loads(out) == [25, 60]


# ---- the measurement -----------------------------------------------------------------
def test_the_replay_folds_play_by_play_honestly():
    play = {"game_id": "2024_05_KC_NO", "qtr": "1", "play_type": "pass", "passer_player_name": "P.Mahomes",
            "receiver_player_name": "T.Kelce", "complete_pass": "0", "receiving_yards": "NA", "passing_yards": "NA",
            "yards_gained": "0", "sack": "0", "pass_attempt": "1", "two_point_attempt": "0"}
    assert sorted(PF.nfl_play_stats(play)) == [("P.Mahomes", "pass_att", 1.0), ("T.Kelce", "rec_yds", 0.0),
                                                ("T.Kelce", "receptions", 0.0)], \
        "an incomplete target is a zero for him, not a game he was missing from"
    catch = dict(play, complete_pass="1", receiving_yards="12", passing_yards="12")
    assert ("T.Kelce", "rec_yds", 12.0) in PF.nfl_play_stats(catch) and ("P.Mahomes", "pass_yds", 12.0) in PF.nfl_play_stats(catch)
    assert PF.nfl_play_stats(dict(catch, two_point_attempt="1")) == [], "a two-point try is no stat"
    assert all(m != "pass_att" for _, m, _ in PF.nfl_play_stats(dict(play, sack="1"))), "a sack is no attempt"
    run = {"game_id": "g", "qtr": "2", "play_type": "run", "rusher_player_name": "I.Pacheco", "rushing_yards": "7",
           "yards_gained": "7", "two_point_attempt": "0"}
    assert PF.nfl_play_stats(run) == [("I.Pacheco", "rush_att", 1.0), ("I.Pacheco", "rush_yds", 7.0)]
    games = PF.nfl_games([catch, dict(catch, qtr="3", receiving_yards="20"), dict(catch, qtr="5", receiving_yards="5")])
    g = games[("2024_05_KC_NO", "T.Kelce")]["rec_yds"]
    assert g["final"] == 37.0 and g["periods"] == {1: 12.0, 3: 20.0, 5: 5.0}, "overtime counts toward the final"
    box = [("2025-11-01", "EDM", "Connor McDavid", 4.0), ("2025-11-03", "EDM", "Connor McDavid", 0.0),
           ("2025-11-05", "EDM", "Connor McDavid", 5.0)]
    shots = [("2025-11-01", "EDM", "Connor McDavid", 1), ("2025-11-01", "EDM", "Connor McDavid", 3),
             ("2025-11-03", "EDM", "Zach Hyman", 2)]
    nhl = PF.nhl_games(box, shots)
    assert nhl[("2025-11-01", "Connor McDavid")]["sog"] == {"final": 4.0, "periods": {1: 1.0, 3: 1.0}}
    assert nhl[("2025-11-03", "Connor McDavid")]["sog"]["final"] == 0.0, "a night with no shot still counts"
    assert ("2025-11-05", "Connor McDavid") not in nhl, "a game whose shots were never stored is left out"


def test_the_replay_asks_the_shipping_function_and_scores_four_arms():
    games = {}
    for i in range(12):
        final = [3, 5, 7, 4, 6, 2, 8, 5, 4, 6, 9, 3][i]
        games[(f"2024_{i + 1:02d}", "W.One")] = {"receptions": {"final": float(final),
                                                               "periods": {1: final * 0.2, 2: final * 0.3, 3: final * 0.3, 4: final * 0.2}}}
    rows = PF.replay(games, PF.NFL_STOPS, ("receptions",))
    assert len(rows) == (12 - PF.MIN_GAMES) * 3, "every game with four behind it, at every stop"
    r = rows[0]
    assert set(r) >= {"ours", "pregame", "pace", "blend", "hit"} and r["stop"] == "end of Q1"
    scored = PF.score(rows)["receptions"]
    assert set(scored) == {"end of Q1", "halftime", "end of Q3"}
    for v in scored.values():
        assert v["n"] == 12 - PF.MIN_GAMES and sum(c["n"] for c in v["calibration"]) == v["n"]
        assert set(v["brier"]) == set(PF.ARMS)
    text = PF.report(PF.score(rows), "test")
    assert "receptions" in text and "Nothing here changes the model." in text
    src = (ROOT / "engine" / "proplivefit.py").read_text()
    assert "PL.clock_chance(leg, row)" in src, "the replay scores the function that ships, not a copy of it"
    assert "write_text" in src and src.count("write_text") == 1, "it writes only the report it is asked for"


# ---- the browser half ------------------------------------------------------------
# Opt-in, as tests/test_ask_keyboard.py explains: a screenshot goes up through
# the real page (the API answered by a fixture), the hedge is typed into, the
# slip is saved, and the Live tab follows it — with a second saved slip one
# leg from done and a third the box score settles as lost.
#
#     QB_BROWSER_TESTS=1 python3 tests/test_a_graded_slip_says_what_to_do_next.py
_WALK = r"""
import { chromium } from 'playwright';
const [PORT, PNG, RESP, TRACK, OUT] = [process.argv[2], process.argv[3], JSON.parse(process.argv[4]), JSON.parse(process.argv[5]), process.argv[6]];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium', undefined]) {
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const result = {};
for (const [w, h] of [[390, 844], [1280, 900]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
  await p.addInitScript(() => { try { localStorage.setItem('qb.tour', 'done'); } catch (e) {} });
  await p.route('**/api/ask/slip', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESP) }));
  let tracked = null;
  await p.route('**/api/ask/track', async (route) => {
    tracked = JSON.parse(route.request().postData() || '{}');
    const slips = (tracked.slips || []).map((s, i) => ({ id: s.id, slip: TRACK[i % TRACK.length] }));
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ slips }) });
  });
  await p.goto(`http://127.0.0.1:${PORT}/#ask`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('#ask-input', { timeout: 20000 });
  await p.click('[data-ask-clip]');
  await p.waitForSelector('[data-ask-slip]', { state: 'attached', timeout: 5000 });
  await p.setInputFiles('[data-ask-slip]', { name: 'slip.png', mimeType: 'image/png', buffer: Buffer.from(PNG, 'base64') });
  await p.waitForSelector('.pgr-card .pgr-hedge', { timeout: 20000 });
  const before = await p.textContent('.pgr-hedge-out');
  await p.fill('[data-hedge="odds"]', '+120');
  await p.waitForTimeout(150);
  const after = await p.textContent('.pgr-hedge-out');
  await p.fill('[data-save-stake]', '25');
  await p.click('[data-save-slip]');
  await p.waitForSelector('.pgr-save.done', { timeout: 5000 });
  const bets = await p.evaluate(() => JSON.parse(localStorage.getItem('qb_mybets_v1') || '[]'));
  // A second slip saved earlier, one leg left, and a third the box score will settle.
  await p.evaluate(() => {
    const b = JSON.parse(localStorage.getItem('qb_mybets_v1') || '[]');
    b.push({ id: '1760000000001', book: 'DraftKings', sport: 'NFL', date: '2026-10-18', desc: '2-leg parlay: LA moneyline + KC moneyline',
             stake: 20, odds: 170, result: 'pending', src: 'slip', slip_key: 'sx1',
             legs: [{ sport: 'nfl', team: 'LA', game: 'BUF @ LA', market: 'moneyline', side: 'team', line: 0, odds: -140 },
                    { sport: 'nfl', team: 'KC', game: 'DEN @ KC', market: 'moneyline', side: 'team', line: 0, odds: -180 }] });
    b.push({ id: '1760000000000', book: 'FanDuel', sport: 'NBA', date: '2026-10-18', desc: '2-leg parlay: Jalen Brunson Over 25.5 Points + Josh Hart Over 9.5 Rebounds',
             stake: 10, odds: 264, result: 'pending', src: 'slip', slip_key: 'sx0',
             legs: [{ sport: 'nba', player: 'Jalen Brunson', team: 'NYK', game: 'BOS @ NYK', market: 'pts', side: 'over', line: 25.5, odds: -115 },
                    { sport: 'nba', player: 'Josh Hart', team: 'NYK', game: 'BOS @ NYK', market: 'reb', side: 'over', line: 9.5, odds: -110 }] });
    localStorage.setItem('qb_mybets_v1', JSON.stringify(b));
  });
  await p.goto(`http://127.0.0.1:${PORT}/#live`, { waitUntil: 'domcontentloaded' });
  let panel = null;
  try {
    await p.waitForSelector('#live-slips .pgr-track-card .pgr-legs', { timeout: 25000 });
    panel = await p.$('#live-slips');
  } catch (e) { errs.push('no tracker panel: ' + e); }
  let shot = null, settled = null, overflow = null, typing = null;
  if (panel) {
    shot = await p.evaluate(() => ({
      cards: document.querySelectorAll('#live-slips .pgr-track-card').length,
      chance: document.querySelectorAll('#live-slips .pgr-chance').length,
      hedge: document.querySelectorAll('#live-slips .pgr-hedge').length,
      settledText: (document.querySelector('#live-slips .pgr-now.s-lost') || {}).textContent || '',
    }));
    settled = await p.evaluate(() => JSON.parse(localStorage.getItem('qb_mybets_v1') || '[]').map((b) => [b.id, b.result, b.settled_by || '']));
    overflow = await p.evaluate(() => document.scrollingElement.scrollWidth > window.innerWidth + 1);
    const inp = await p.$('#live-slips [data-hedge="odds"]');
    if (inp) {
      await inp.fill('+140');
      typing = await p.textContent('#live-slips .pgr-hedge-out');
    }
  }
  result[w] = { before, after, saved: bets.filter((x) => x.src === 'slip').map((x) => ({ stake: x.stake, odds: x.odds, legs: (x.legs || []).length, desc: x.desc })),
                tracked: tracked && (tracked.slips || []).map((s) => ({ id: s.id, legs: s.legs.length, odds: s.total_odds })),
                shot, settled, overflow, typing, errors: errs };
  await ctx.close();
}
console.log(JSON.stringify(result));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
                           capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def _png(w=600, h=1200) -> bytes:
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


TRACK_ONE_LEFT = {"legs": [
    {"sport": "nfl", "league": "nfl", "team": "LA", "game": "BUF @ LA", "market": "moneyline", "side": "team", "line": 0,
     "odds": -140, "live": {"state": "final", "home": "LA", "away": "BUF", "home_score": 24, "away_score": 20,
                            "clock": "Final", "result": "won"}},
    {"sport": "nfl", "league": "nfl", "team": "KC", "game": "DEN @ KC", "market": "moneyline", "side": "team", "line": 0,
     "odds": -180, "live": {"state": "live", "home": "KC", "away": "DEN", "home_score": 17, "away_score": 13,
                            "clock": "5:41 - 3rd", "win_prob": 0.62}}],
    "now": {"won": 1, "lost": 0, "push": 0, "live": 1, "status": "open", "left": 1, "start": 0, "chance": 0.62},
    "hedge": {"leg": "KC moneyline", "other": "DEN moneyline", "plan": False, "odds": 155, "book": "Caesars",
              "stale": True, "stake": 20, "payout": 2.7, "approx": False, "p_leg": 0.62, "from": "live"},
    "first_kickoff": "2026-10-18 13:00"}
TRACK_LOST = {"legs": [
    {"sport": "nba", "league": "nba", "player": "Jalen Brunson", "team": "NYK", "game": "BOS @ NYK", "market": "pts",
     "side": "over", "line": 25.5, "odds": -115, "live": {"state": "final", "home": "NYK", "away": "BOS", "home_score": 108,
                                                          "away_score": 112, "clock": "Final", "current": 22, "result": "lost"}}],
    "now": {"won": 0, "lost": 1, "push": 0, "live": 0, "status": "lost", "left": 0, "start": 0, "chance": 0.0,
            "lost_leg": "Jalen Brunson over 25.5 points"}, "hedge": None, "first_kickoff": "2026-10-18 19:30"}


def test_a_slip_is_hedged_saved_and_followed_on_the_live_tab_at_both_widths():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    import base64
    import rendercheck
    resp = {"slip": PAGE_CARD, "text": "Graded parlay, 3 legs.", "sig": "x"}
    track = [dict(PAGE_CARD, hedge=None), TRACK_ONE_LEFT, TRACK_LOST]
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, dir=ROOT) as fh:
            fh.write(_WALK)
            script = fh.name
        proc = subprocess.run(["node", script, str(port), base64.b64encode(_png()).decode(), json.dumps(resp),
                               json.dumps(track), tempfile.mkdtemp()], cwd=ROOT, capture_output=True, text=True, timeout=300)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    for w, got in out.items():
        assert "Lock it: bet $51.22" in got["before"] and "Lock it: bet $45.45" in got["after"], \
            (w, "the hedge redoes its arithmetic as the price is typed")
        assert got["saved"] and got["saved"][0]["stake"] == 25 and got["saved"][0]["legs"] == 3, (w, got["saved"])
        assert [s["legs"] for s in got["tracked"]] == [3, 2, 2], (w, "every pending saved slip, newest first")
        assert got["shot"] == {"cards": 3, "chance": 2, "hedge": 1, "settledText": got["shot"]["settledText"]}, (w, got["shot"])
        assert got["shot"]["settledText"].startswith("Settled in My Bets from the box score: Lost."), w
        assert ["1760000000000", "loss", "box"] in got["settled"], (w, got["settled"])
        assert got["typing"] and "Lock it: bet $22.50" in got["typing"], (w, "the Live tab's hedge types too")
        assert got["overflow"] is False and not got["errors"], (w, got["errors"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
