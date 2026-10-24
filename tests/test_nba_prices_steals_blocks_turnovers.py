"""The NBA board prices steals, blocks and turnovers.

Ethan, 2026-10-14: "Do 1-7 and the ones we download but don't use" — and
on that list: "NBA steals, blocks and turnovers are in the box scores we
save, but we drop them. Saving them would allow those markets, though each
new market costs odds credits." Both NBA ingests have stored them since
2026-10-13; nothing priced them. Pinned here:

  * the NBA's odds request carries the three, behind the drop-and-retry
    guard, and costs three credits more (16 -> 19); the WNBA's does not;
  * A MISSING ROW IS NOT A ZERO: a game ingested before the stats were
    stored has no row, and the history, the build and the replay read
    only the run of his newest games that carry the count;
  * each is priced as a count (exact, never tighter than Poisson), from a
    stated prior the build's fit measures from the league's own logs, and
    held to the high-hold bar threes are;
  * the card under the pick says what tonight's opponent gives up in each,
    in words that fit; the NBA's projection reads it at the share measured
    on the box (2026-10-14, Ethan: "yes count the defence for those three"
    — pin changed that night and told to him: it held that the model left
    them out), the WNBA's still shows it and leaves it out;
  * a journaled pick settles off its own row; every reader knows the three
    by name; the replay and the ranking walk measure them, and the walk now
    adds PRA and the combos up from their parts, so those can be ranked too.

Run directly: `python3 tests/test_nba_prices_steals_blocks_turnovers.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

# The fitted models must not decide this file (see tests/test_nba.py).
from engine import calibrate as _cal, losspatterns as _lp, playerfit as _pf   # noqa: E402
_void = Path(tempfile.gettempdir()) / "qb-no-such-fit.json"
for _m in (_cal, _pf, _lp):
    _m.DEFAULT_PATH = _void
    _m._cache = {}

import nba_build                                                # noqa: E402
from engine import boards, db, hoops, hoops_fit, hoopsdvp, hoopsreplay, ledger, livepicks  # noqa: E402
from engine import logwalk, markets, oddsbudget, parlays, proplive, rankfit  # noqa: E402
from engine import slipgrade, sliplive, slipread                # noqa: E402
from engine.nba import pipeline, prob                           # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COUNTS = ("stl", "blk", "tov")


def test_the_nba_buys_the_three_behind_the_guard_and_the_wnba_does_not():
    assert hoops.COUNTS == COUNTS
    nba = oa.SPORT_CONFIG["nba"]["markets"]
    keys = {"player_steals": "stl", "player_blocks": "blk", "player_turnovers": "tov"}
    assert {k: nba[k] for k in keys} == keys == oa.HOOPS_COUNT_ODDS_TO_MARKET
    assert set(keys) <= oa.UNPROVEN_MARKETS and set(keys) <= oa.NEWEST_ODDS_KEYS, \
        "new keys: a refusal drops them, and an unnamed one drops them first"
    assert not set(keys) & set(oa.SPORT_CONFIG["wnba"]["markets"])
    for sport, price in (("nba", 19), ("wnba", 13)):
        cfg = oa.SPORT_CONFIG[sport]
        assert len(cfg["markets"]) + len(cfg["alternates"]) + 3 == oddsbudget.EVENT_CREDITS[sport] == price
    assert not set(keys.values()) & set(oa.HOOPS_ALT_ODDS_TO_MARKET.values()), "main lines only"


def _rows(player, games, team="BOS", sport="nba"):
    """``games`` newest LAST: (minutes, {stat: value}) per game."""
    out = []
    for i, (mn, stats) in enumerate(games):
        day = f"2026-01-{i + 1:02d}"
        for market, v in {"min": mn, "pts": 20, "reb": 5, "ast": 4, "fg3m": 2, **stats}.items():
            out.append({"sport": sport, "season": 2026, "period": day, "game_id": f"g{i}",
                        "player": player, "team": team, "opponent": "NYK",
                        "position": "S", "home": 1, "market": market, "value": float(v)})
    return out


def test_a_missing_row_is_not_a_zero():
    assert hoops.carried([{"stl": 1}, {"stl": 0}, {"pts": 9}, {"stl": 3}], "stl") == 2
    assert hoops.carried([{"pts": 9}, {"stl": 3}], "stl") == 0 and hoops.carried([], "stl") == 0
    conn = db.connect(":memory:")
    # Five games; the box stored the counts only for the newest three (the
    # older two were ingested before 2026-10-13).
    db.upsert_player_logs(conn, _rows("Guard One", [(30, {}), (31, {}), (32, {"stl": 1, "blk": 0, "tov": 2}),
                                                    (33, {"stl": 3, "blk": 1, "tov": 4}),
                                                    (34, {"stl": 2, "blk": 2, "tov": 3})]))
    # His newest game has no row: the old rows behind it are not his form.
    db.upsert_player_logs(conn, _rows("Wing Two", [(30, {"stl": 4, "blk": 1, "tov": 1}), (30, {}), (31, {})]))
    conn.commit()
    h = nba_build.player_history(conn, {"BOS"})
    g = h["Guard One"]
    assert g["minutes"] == [34.0, 33.0, 32.0, 31.0, 30.0]
    assert g["stl"] == [2.0, 3.0, 1.0] and g["blk"] == [2.0, 1.0, 0.0] and g["tov"] == [3.0, 4.0, 2.0]
    assert g["pts"] == [20.0] * 5, "the volume stats keep every game"
    assert h["Wing Two"]["stl"] == [] and h["Wing Two"]["tov"] == []
    w = db.connect(":memory:")
    db.upsert_player_logs(w, _rows("Wnba Guard", [(30, {"stl": 1})] * 4, sport="wnba"))
    w.commit()
    assert "stl" not in nba_build.player_history(w, {"BOS"}, sport="wnba")["Wnba Guard"], \
        "the WNBA prices none of the three"


def test_the_build_prices_them_for_the_nba_only_and_never_from_a_thin_history():
    assert nba_build.slate_markets("nba")[-3:] == COUNTS
    assert not set(COUNTS) & set(nba_build.slate_markets("wnba"))
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    loop = src[src.index("for stat in slate_markets(args.league):"):]
    assert loop.index("if len(h.get(stat) or ()) < 3:") < loop.index("slate.props.append(")
    assert "--seasons 2025 --refresh" in src, "the terminal names the backfill that fills last season"


def _prop(market, values, minutes=None, **kw):
    games = len(values)
    p = {"player": "Guard One", "team": "BOS", "opponent": "NYK", "market": market,
         "line": 1.5, "over_odds": -120, "under_odds": -105, "book": "DK",
         "minutes": minutes or [32.0] * games, "values": values,
         "is_starter": True, "spread": -3.0, "is_favorite": True, "rest": "1day"}
    p.update(kw)
    return p


def test_a_count_is_priced_as_a_count_on_the_high_hold_bar():
    assert set(COUNTS) <= prob.DISCRETE
    assert {pipeline.MARKET_LABELS[m] for m in COUNTS} == {"Steals", "Blocks", "Turnovers"}
    assert hoops.NBA.sd_cv["tov"] == 0.60 and "tov" in prob.SD_CV
    # Exact and never tighter than Poisson: at a mean of one, a CV below 1
    # still prices a Poisson count.
    import math
    assert prob.p_over("stl", 1.0, 0.5) == round(1 - math.exp(-1.0), 4)
    assert prob.p_over("tov", 3.0, 3.5) < 0.5 < prob.p_over("tov", 3.0, 1.5)
    for m in COUNTS:
        assert m in pipeline.HIGH_HOLD_MARKETS
        assert prob.required_edge(m, 0.03, hoops.NBA, high_hold_market=m in pipeline.HIGH_HOLD_MARKETS) \
            == prob.GATE_EDGE_PTS_HIGH_HOLD
    r = pipeline.evaluate_prop(_prop("stl", [2.0] * 15))
    assert r["kind"] in ("pick", "near_miss"), r
    assert r["market_label"] == "Steals" and r["sd"] > 0


def test_his_rate_reads_only_the_games_that_carry_the_count():
    # Ten games of minutes, steals stored for the newest three: the rate is
    # those three games' steals over those three games' minutes.
    pj = pipeline.project(_prop("stl", [2.0, 1.0, 3.0], minutes=[30.0, 30.0, 30.0] + [36.0] * 7))
    assert pj["chain"]["base"]["rate_per_min"] == round(6.0 / 90.0, 4)
    # ...and a count on fewer stored games than the thin-sample bar is
    # clamped as thin, however many games of minutes he has.
    thin = pipeline.evaluate_prop(_prop("stl", [2.0] * 5, minutes=[32.0] * 15))
    full = pipeline.evaluate_prop(_prop("stl", [2.0] * 15, minutes=[32.0] * 15))
    assert thin["w"] == pipeline.CLAMP_W_THIN and full["w"] == pipeline.CLAMP_W_DEFAULT, (thin, full)


def test_the_nbas_counts_carry_a_matchup_step_the_wnbas_do_not_and_the_board_says_so():
    """Pin changed 2026-10-14 and told to Ethan: this held that the NBA's
    three had no Matchup step; on his yes the defence is read into them."""
    from engine.hoops import WNBA
    for m in COUNTS:
        steps = {s["key"] for s in pipeline.project(_prop(m, [1.0] * 12))["chain"]["steps"]}
        assert "matchup" in steps and {"player", "environment", "rest"} <= steps, m
        wn = {s["key"] for s in pipeline.project(_prop(m, [1.0] * 12), WNBA)["chain"]["steps"]}
        assert "matchup" not in wn, m
    pts = {s["key"] for s in pipeline.project(_prop("pts", [20.0] * 12, line=19.5))["chain"]["steps"]}
    assert "matchup" in pts, "a measured market keeps its step"
    from engine import likelyboard as LB
    got = LB.matchup_check({"player": "Guard One", "market": "blk", "side": "OVER", "lane": "prop"},
                           {}, {}, LB.model_matchups([{"player": "Guard One", "market": "blk",
                                                       "chain": {"steps": []}}]), source="model")
    assert got == (None, "the model has no matchup step for this market")


def _dvp_rows():
    rows = []
    teams = ["BOS", "NYK", "PHX", "DEN"]
    for d in range(12):
        day = f"2026-01-{d + 1:02d}"
        order = teams[d % 4:] + teams[:d % 4]
        for a, b in zip(order[::2], order[1::2]):
            for team, opp in ((a, b), (b, a)):
                for k in range(5):
                    # PHX's ball-handlers cough it up: everyone facing them steals more.
                    rows.append((day, team, opp, "stl", 2.0 if opp == "PHX" else 1.0))
                    rows.append((day, team, opp, "tov", 3.0 if opp == "DEN" else 2.0))
                    rows.append((day, team, opp, "blk", 1.0))
    return rows


def test_the_card_says_what_the_opponent_gives_up_in_words_that_fit_and_the_nba_reads_it():
    rating = hoopsdvp.ratings(_dvp_rows())
    stl = hoopsdvp.matchup_card("PHX", rating, "stl")
    assert stl["rank"] == 1 and stl["stat"] == "steals given up"
    assert stl["text"].startswith("PHX give up 10.0 steals a game, the 1st-most of 4")
    assert "Read into the projection" in stl["note"]
    tov = hoopsdvp.matchup_card("DEN", rating, "tov")
    assert tov["stat"] == "turnovers forced" and tov["text"].startswith("DEN force 15.0 turnovers a game")
    assert hoopsdvp.matchup_card("BOS", rating, "blk")["stat"] == "shots blocked"
    # The NBA's measured shares (hoopsdvpfit on the box, 2026-10-14), each
    # capped at the defence's whole lean; the WNBA's three are not read.
    assert {m: hoopsdvp.TRANSFER["nba"][m] for m in ("stl", "blk", "tov")} == {"stl": 1.0, "blk": 0.96, "tov": 1.0}
    assert not any(m in hoopsdvp.TRANSFER["wnba"] for m in ("stl", "blk", "tov"))
    mult, note = hoopsdvp.projection_mult("nba", rating, "PHX", "stl")
    f = rating["PHX"]["stl"]["factor"]
    assert f > 1 and mult == round(1.0 + (f - 1.0), 4) and note.startswith("Matchup: PHX give up 10.0 steals a game")
    assert "the whole defence's lean reaches one player" in note
    bmult, bnote = hoopsdvp.projection_mult("nba", rating, "DEN", "tov")
    assert bmult > 1 and "DEN force 15.0 turnovers a game" in bnote
    assert hoopsdvp.projection_mult("wnba", rating, "PHX", "stl") == (1.0, "")
    assert "not measured yet" in hoopsdvp.matchup_card("PHX", rating, "stl", sport="wnba")["note"]
    assert "Read into the projection" in hoopsdvp.matchup_card(
        "PHX", hoopsdvp.ratings([(r[0], r[1], r[2], "pts", r[4] * 10) for r in _dvp_rows()]), "pts")["note"]
    build = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "_dvp.attach(recs, _dvp_rt, _dvp_last, args.league)" in build
    # The box measures how much reaches one player before anything moves.
    assert {"stl", "blk", "tov"} <= set(hoopsdvp.measure(_dvp_rows()))


def test_the_fit_measures_turnovers_from_the_leagues_logs():
    assert "tov" in hoops_fit.STATS and hoops_fit.SUMS is hoops.SUMS
    conn = db.connect(":memory:")
    for k in range(12):
        db.upsert_player_logs(conn, _rows(f"Player {k}", [(32, {"tov": 1 + (i % 4) + (k % 3)}) for i in range(40)]))
    conn.commit()
    cvs, counts = hoops_fit.fit_stat_cvs(conn, "nba")
    assert counts["tov"] == 480 and "tov" in cvs and cvs["tov"] != hoops.NBA.sd_cv["tov"]


def test_a_journaled_count_settles_off_its_own_row():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    day = "2026-01-05"
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score) VALUES ('nba', 2026, ?, 'g1', ?, 'BOS', 'NYK', 110, 101)", (day, day))
    db.upsert_player_logs(H, [{"sport": "nba", "season": 2026, "period": day, "game_id": "g1",
                               "player": "Guard One", "team": "BOS", "opponent": "NYK",
                               "position": "S", "home": 1, "market": m, "value": v}
                              for m, v in (("min", 34.0), ("pts", 25.0), ("stl", 3.0), ("blk", 0.0),
                                           ("tov", 4.0))])
    H.commit()
    for market, line, side in (("stl", 1.5, "OVER"), ("blk", 0.5, "OVER"), ("tov", 3.5, "UNDER")):
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category) VALUES (?, 'nba', ?, ?, 'Guard One', "
                  "?, ?, ?, -110, 1, 10, 'open', 'main')",
                  (f"{day}T12:00:00", day, day, market, side, line))
    L.commit()
    ledger.settle_from_history(L, H)
    got = {r["market"]: (r["status"], r["actual"]) for r in
           L.execute("SELECT market, status, actual FROM bets")}
    assert got == {"stl": ("won", 3.0), "blk": ("lost", 0.0), "tov": ("lost", 4.0)}, got


def test_every_reader_knows_the_three_by_name():
    for m in COUNTS:
        assert m in proplive.FALLBACK_D and m in livepicks.TRACKER_LABELS, m
        assert parlays.TIER[m] == 3 and m in parlays.FAMILY and m in parlays.EXTREME_MARKETS, m
        assert m in slipgrade.MARKETS and m in slipgrade.MARKET_WORDS, m
        assert slipread.HOOPS_LOGS[m] == ((m,),) and sliplive.BOX_STAT[m] == (m,), m
        assert slipread.LEAGUES_FOR[m] == ("nba", "wnba"), m
    assert [markets.label(m) for m in COUNTS] == ["Steals", "Blocks", "Turnovers"]
    shelf = {s[0]: s[2] for s in boards.HOOPS_SHELVES}
    assert shelf["counts"] == COUNTS
    src = (ROOT / "engine" / "slipgrade.py").read_text(encoding="utf-8")
    assert "stl (steals), blk (blocks)," in src and "tov (turnovers)" in src
    for js, needle in (("slip.js", 'stl: "Steals", blk: "Blocks", tov: "Turnovers"'),
                       ("social.js", 'stl: "STL", blk: "BLK", tov: "TO"')):
        assert needle in (ROOT / "web" / "js" / js).read_text(encoding="utf-8"), js
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = app.index("const MB_PROP_WORDS = [")
    block = app[i:app.index("];", i) + 2]
    if not shutil.which("node"):
        return
    js = block + """
      const read = (t) => (MB_PROP_WORDS.find(([re]) => re.test(t)) || [0, "none"])[1];
      process.stdout.write(JSON.stringify(["Curry over 3.5 turnovers", "Wemby 2.5 blocks", "Holiday steals"].map(read)));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["other props"] * 3


def _hist(stl_from):
    """Twenty games oldest first; steals stored from game ``stl_from`` on."""
    rows = []
    for i in range(20):
        g = {"min": 32.0, "pts": 20.0, "reb": 5.0, "ast": 4.0}
        if i >= stl_from:
            g["stl"] = 3.0
        rows.append((f"2026-01-{i + 1:02d}", True, g))
    return {"Guard One": rows}


def test_the_replay_reads_only_the_games_that_carried_the_count():
    assert set(COUNTS) <= set(hoopsreplay.MARKETS)
    settled, counts = hoopsreplay.settled_props(_hist(12), "stl", min_history=8)
    # Games 12-14 have fewer than three stored before them and are skipped;
    # every game after is priced off steals that are all threes — never off
    # the twelve games with no row read as zeros.
    assert counts["priced"] == len(settled) == 5 and counts["skipped"] == 3, counts
    assert all(s.projection > 2.0 for s in settled), [s.projection for s in settled]


def test_the_ranking_walk_measures_the_counts_and_adds_the_sums_up():
    assert set(COUNTS) | {"pra", "pts_reb", "pts_ast", "reb_ast"} <= set(rankfit.MARKETS["nba"])
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, _rows("Guard One", [(32, {"stl": 1})] * 10))
    # A game missing a part is not summed short.
    db.upsert_player_logs(conn, [{"sport": "nba", "season": 2026, "period": "2026-02-01", "game_id": "gx",
                                  "player": "Guard One", "team": "BOS", "opponent": "NYK", "position": "S",
                                  "home": 1, "market": "pts", "value": 40.0}])
    conn.commit()
    # Since the same day every basketball walk reads these entries — the
    # rank walk and the price fitters alike (tests/test_nba_self_tunes_on_
    # its_own_model) — with his minutes beside each game, and a game whose
    # box lacks a part kept as None rather than dropped, as his window does.
    got = logwalk.load_entries(conn, "nba", "pra")
    assert len(got) == 1 and got[0]["values"] == [29.0] * 10 + [None] and len(got[0]["dates"]) == 11
    assert got[0]["minutes"] == [32.0] * 10 + [0.0]
    assert logwalk.load_entries(conn, "nba", "pts_reb")[0]["values"] == [25.0] * 10 + [None]
    assert logwalk.load_entries(conn, "nba", "stl")[0]["values"] == [1.0] * 10, "that box has no steals row"
    src = (ROOT / "engine" / "rankfit.py").read_text(encoding="utf-8")
    assert "load_entries(conn, sport, market)" in src


def test_the_call_is_in_the_runbook():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert re.search(r"steals, blocks and turnovers", doc, re.I)
    assert "python3 ingest.py nba --seasons 2025 --refresh" in doc
    assert "python3 hoopsdvpfit.py nba" in doc


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
