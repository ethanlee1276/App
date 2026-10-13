"""The NBA board prices points + rebounds, points + assists and rebounds + assists.

Ethan's call, 2026-10-13, from runbook H: "Also add both from my calls,
the CFB and nba things" — answering "NBA points + rebounds, points +
assists, rebounds + assists? They come from columns we already store, like
PRA, but the odds API bills per market on every game pulled." Pinned here:

  * the NBA's odds request carries the three markets and the WNBA's does
    not; the NBA's event cost is three credits more (13 -> 16);
  * the build prices them for the NBA only, from a history that adds each
    game's two columns, the same way PRA's three are added;
  * the spread starts from a stated prior and the build's fit measures it
    from the league's own logs, as every other stat's;
  * a journaled combo settles off its two parts;
  * the card, the shelves, the live tracker, the parlay checker and the
    bet-text reader all know the three by name.

Run directly: `python3 tests/test_nba_prices_the_two_stat_combos.py`
"""
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
from engine import boards, db, hoops, hoops_fit, ledger, livepicks, oddsbudget, parlays, proplive  # noqa: E402
from engine import slipgrade, sliplive, slipread                # noqa: E402
from engine.nba import pipeline, prob                           # noqa: E402
from engine.sources import oddsapi as oa                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMBOS = {"pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}


def test_the_nba_buys_the_three_and_the_wnba_does_not():
    assert hoops.COMBOS == COMBOS
    nba = oa.SPORT_CONFIG["nba"]["markets"]
    assert {k: nba[k] for k in ("player_points_rebounds", "player_points_assists",
                                "player_rebounds_assists")} == \
        {"player_points_rebounds": "pts_reb", "player_points_assists": "pts_ast",
         "player_rebounds_assists": "reb_ast"}
    assert set(oa.SPORT_CONFIG["wnba"]["markets"].values()) == {"pts", "reb", "ast", "fg3m", "pra"}
    assert (oddsbudget.EVENT_CREDITS["nba"], oddsbudget.EVENT_CREDITS["wnba"]) == (16, 13), \
        "three more markets is three more credits on every NBA event pulled"


def test_the_build_prices_them_for_the_nba_only():
    assert nba_build.slate_markets("nba") == nba_build.SLATE_MARKETS + tuple(COMBOS)
    assert nba_build.slate_markets("wnba") == nba_build.SLATE_MARKETS
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "for stat in slate_markets(args.league):" in src


def _logs(conn, player, games):
    rows = []
    for i, (mn, pts, reb, ast) in enumerate(games):
        day = f"2026-01-{i + 1:02d}"
        for market, v in (("min", mn), ("pts", pts), ("reb", reb), ("ast", ast), ("fg3m", 1)):
            rows.append({"sport": "nba", "season": 2026, "period": day, "game_id": f"g{i}",
                         "player": player, "team": "BOS", "opponent": "NYK",
                         "position": "S", "home": 1, "market": market, "value": float(v)})
    db.upsert_player_logs(conn, rows)
    conn.commit()


def test_the_history_adds_each_games_two_columns():
    conn = db.connect(":memory:")
    _logs(conn, "Guard One", [(34, 25, 6, 8), (30, 18, 4, 5), (36, 31, 9, 7)])
    h = nba_build.player_history(conn, {"BOS"})["Guard One"]
    # Newest first, as every other list on the history.
    assert h["pts"] == [31.0, 18.0, 25.0]
    assert h["pts_reb"] == [40.0, 22.0, 31.0]
    assert h["pts_ast"] == [38.0, 23.0, 33.0]
    assert h["reb_ast"] == [16.0, 9.0, 14.0]
    assert h["pra"] == [47.0, 27.0, 39.0]


def test_a_combo_is_priced_through_the_same_pipeline():
    games = 15
    prop = {"player": "Guard One", "team": "BOS", "opponent": "NYK", "market": "pts_reb",
            "line": 29.5, "over_odds": -110, "under_odds": -110, "book": "DK",
            "minutes": [32.0] * games, "values": [30.0] * games,
            "is_starter": True, "spread": -3.0, "is_favorite": True, "rest": "1day"}
    r = pipeline.evaluate_prop(prop)
    assert r["kind"] in ("pick", "near_miss"), r
    assert r["market"] == "pts_reb" and r["market_label"] == "Pts+Reb", r
    assert pipeline.MARKET_LABELS["pts_ast"] == "Pts+Ast" and pipeline.MARKET_LABELS["reb_ast"] == "Reb+Ast"
    # A combo is a sum of counts, priced continuous like PRA, never as a
    # discrete count; its spread is its own.
    assert not set(COMBOS) & prob.DISCRETE
    for c in COMBOS:
        assert c in prob.SD_CV and c in hoops.NBA.sd_cv
    # Wider than PRA (fewer parts to average the noise away), and the
    # two-count combo widest.
    cv = hoops.NBA.sd_cv
    assert cv["pra"] < cv["pts_reb"] <= cv["pts_ast"] < cv["reb_ast"]
    p_low, p_high = prob.p_over("pts_reb", 30.0, 24.5), prob.p_over("pts_reb", 30.0, 35.5)
    assert p_low > 0.5 > p_high


def test_the_fit_measures_their_spread_from_the_leagues_logs():
    conn = db.connect(":memory:")
    for k in range(12):
        games = [(32, 20 + (i % 7) + k, 5 + (i % 3), 4 + (i % 4)) for i in range(40)]
        _logs(conn, f"Player {k}", games)
    cvs, counts = hoops_fit.fit_stat_cvs(conn, "nba")
    for c, parts in COMBOS.items():
        assert c in cvs and counts[c] == 480, (c, counts.get(c))
    # Measured, not the prior: the median of each player's own CV, by hand.
    def cv(vals):
        mean = sum(vals) / len(vals)
        return (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 / mean
    per = sorted(cv([(20 + (i % 7) + k) + (5 + (i % 3)) for i in range(40)]) for k in range(12))
    assert cvs["pts_reb"] == round((per[5] + per[6]) / 2, 3), (cvs["pts_reb"], per)
    assert cvs["pts_reb"] != hoops.NBA.sd_cv["pts_reb"]


def test_a_journaled_combo_settles_off_its_two_parts():
    assert ledger.DERIVED_MARKETS[("nba", "pts_reb")] == ("pts", "reb")
    assert ledger.DERIVED_MARKETS[("nba", "pts_ast")] == ("pts", "ast")
    assert ledger.DERIVED_MARKETS[("nba", "reb_ast")] == ("reb", "ast")
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
                              for m, v in (("min", 34.0), ("pts", 25.0), ("reb", 6.0), ("ast", 8.0))])
    H.commit()
    for market, line, side in (("pts_reb", 30.5, "OVER"), ("pts_ast", 33.5, "UNDER"),
                               ("reb_ast", 13.5, "OVER")):
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category) VALUES (?, 'nba', ?, ?, 'Guard One', "
                  "?, ?, ?, -110, 1, 10, 'open', 'main')",
                  (f"{day}T12:00:00", day, day, market, side, line))
    L.commit()
    ledger.settle_from_history(L, H)
    got = {r["market"]: (r["status"], r["actual"]) for r in
           L.execute("SELECT market, status, actual FROM bets")}
    assert got == {"pts_reb": ("won", 31.0), "pts_ast": ("won", 33.0), "reb_ast": ("won", 14.0)}, got


def test_every_reader_knows_the_three_by_name():
    for c in COMBOS:
        assert c in proplive.FALLBACK_D, c
        assert c in livepicks.TRACKER_LABELS, c
        assert c in parlays.TIER, c
        assert c in slipgrade.MARKETS and c in slipgrade.MARKET_WORDS, c
        assert c in slipread.HOOPS_LOGS and c in sliplive.BOX_STAT, c
    assert slipread.HOOPS_LOGS["pts_reb"] == (("pts", "reb"),)
    assert sliplive.BOX_STAT["reb_ast"] == ("reb", "ast")
    shelf = {s[0]: s[2] for s in boards.HOOPS_SHELVES}
    assert {"pts_reb", "pts_ast"} <= set(shelf["scoring"]) and "reb_ast" in shelf["glass"]
    src = (ROOT / "engine" / "slipgrade.py").read_text(encoding="utf-8")
    assert "pts_reb (points+rebounds)" in src and "reb_ast (rebounds+assists)" in src


def test_the_page_knows_them_and_reads_them_off_a_bet():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '"pra",\n                      "pts_reb", "pts_ast", "reb_ast"];' in app
    assert "|pts_reb|pts_ast|reb_ast)$/" in app
    for js, needle in (("slip.js", 'pts_reb: "Pts + Reb"'), ("social.js", 'pts_reb: "P+R"')):
        assert needle in (ROOT / "web" / "js" / js).read_text(encoding="utf-8"), js
    i = app.index("const MB_PROP_WORDS = [")
    block = app[i:app.index("];", i) + 2]
    if not shutil.which("node"):
        return
    js = block + """
      const read = (t) => (MB_PROP_WORDS.find(([re]) => re.test(t)) || [0, "none"])[1];
      process.stdout.write(JSON.stringify(["LeBron O 35.5 Pts + Reb + Ast", "Points + Rebounds + Assists 40.5",
        "Jokic Pts + Reb 38.5", "Points + Assists over 30.5", "Reb + Ast u 12.5"].map(read)));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    import json
    assert json.loads(out.stdout) == ["points + rebounds + assists", "points + rebounds + assists",
                                      "points + rebounds", "points + assists", "rebounds + assists"]


def test_the_call_is_marked_answered_in_the_runbook():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert re.search(r"points \+ rebounds, points \+ assists, rebounds \+ assists", doc, re.I)
    assert "Answered 2026-10-13" in doc


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
