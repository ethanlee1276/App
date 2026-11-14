"""Every league's Most Likely pick carries the same kinds of information.

Ethan, 2026-10-13: "Then make sure all sports have the same most likely
screens with same type of info and info is being used how it should be.
All sports screens should basically be identical."

The card and the pick page are one renderer for every league; what
differed was what each league's rows carried. What is pinned, offline:

  * THE MATCHUP CARD, in every league with player picks: baseball's (what
    tonight's staff allows a game in the pick's stat, or how often the
    lineup strikes out, off the season's stored plate appearances) and
    hockey's (what tonight's opponent allows or takes a game, off the
    model's own team profiles), each ranked, beside the league's rate,
    last season's while this one is thin, and saying what the model did
    with it — drawn by the page's one matchup card;
  * BASKETBALL'S PROJECTION WALK (engine/chain), as the NFL's and
    baseball's: base × every step = the number that shipped, its Matchup
    step the measured defence read — which the one board's matchup check
    now reads (it said "no matchup read for this sport yet" while the
    projection read the defence);
  * BASKETBALL'S PAST GAMES name the opponent and home or away, as every
    other league's do (the team history stays off the number and off the
    card: the WNBA spec's pin);
  * BASKETBALL'S TEAMMATE OUT is the teammate card every league draws,
    said once — not also a bullet.

Run directly: `python3 tests/test_every_league_reads_the_same_on_most_likely.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nba_build                                        # noqa: E402
from engine import chain as C, db as D, likely as L      # noqa: E402
from engine.hoops import NBA                            # noqa: E402
from engine.mlb import matchupcard as MMC               # noqa: E402
from engine.nba import pipeline as NP                   # noqa: E402
from engine.nhl import matchupcard as NMC, model as NM  # noqa: E402

APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


# --- baseball ------------------------------------------------------------------------

def _pa_conn():
    """Four clubs, six games each this season; NYY's staff gives up the most
    hits, BOS's lineup strikes out the most."""
    conn = D.connect(":memory:")
    rows, n = [], 0
    for g in range(6):
        for i, (bat, field) in enumerate((("BOS", "NYY"), ("NYY", "BOS"), ("TB", "TOR"), ("TOR", "TB"))):
            gpk = 1000 + g * 2 + (i // 2)
            hits = {"NYY": 10, "BOS": 8, "TOR": 7, "TB": 6}[field]
            ks = {"BOS": 12, "NYY": 7, "TOR": 9, "TB": 8}[bat]
            for k in range(hits):
                n += 1
                rows.append({"game_pk": gpk, "at_bat": n, "season": 2026, "date": f"2026-09-{g + 1:02d}",
                             "batter_id": n, "batter": "x", "team": bat, "opponent": field,
                             "event_type": "home_run" if k == 0 else "single"})
            for k in range(ks):
                n += 1
                rows.append({"game_pk": gpk, "at_bat": n, "season": 2026, "date": f"2026-09-{g + 1:02d}",
                             "batter_id": n, "batter": "x", "team": bat, "opponent": field,
                             "event_type": "strikeout"})
    D.upsert_mlb_pa(conn, rows)
    return conn


def _mlb_row(market, opp, mult=1.06, why="platoon edge vs LHP; starter allows .460 SLG to RHB", key="matchup"):
    return {"player": "A Hitter", "market": market, "opponent": opp, "side": "OVER",
            "chain": {"base": {"value": 1.0}, "steps": [{"key": "park", "mult": 1.0},
                                                        {"key": key, "mult": mult, "why": why}], "mean": mult}}


def test_baseball_counts_each_staff_and_lineup_per_game():
    t = MMC.table(_pa_conn(), 2026)
    assert t["NYY"]["games"] == 6
    assert t["NYY"]["staff"]["hits"] == 10 and t["NYY"]["staff"]["home_runs"] == 1
    assert t["NYY"]["staff"]["total_bases"] == 13            # nine singles and a homer a game
    assert t["BOS"]["lineup"]["strikeouts"] == 12 and t["TB"]["staff"]["hits"] == 6


def test_a_baseball_pick_carries_the_matchup_card_every_league_draws():
    conn = _pa_conn()
    rows = [_mlb_row("hits", "NYY"), _mlb_row("strikeouts", "BOS"), _mlb_row("total_bases", "TB", mult=1.0),
            _mlb_row("hits", "LAD"), _mlb_row("outs", "NYY"), _mlb_row("hits", "TOR", key="learned", mult=1.1)]
    assert MMC.attach(conn, rows, 2026) == 4
    hits, ks, tb, nobody, outs, learned = (r.get("matchup_card") for r in rows)
    assert hits["opponent"] == "NYY" and hits["stat"] == "hits allowed" and hits["per_game"] == 10.0
    assert (hits["rank"], hits["of"], hits["games"]) == (1, 4, 6) and hits["league"] == 7.8
    assert "+6%" in hits["note"] and "platoon edge" in hits["note"] and "context" in hits["note"]
    assert ks["stat"] == "strikeouts" and ks["per_game"] == 12.0 and ks["rank"] == 1, "the lineup's strikeouts"
    assert tb["rank"] == 4 and "left this projection where it was" in tb["note"]
    assert nobody is None and outs is None, "no number, no card"
    assert "learned model sets this number's matchup weight" in learned["note"]
    # Thin this season: last season's, and said.
    assert MMC.card(_mlb_row("hits", "NYY"), {2026: {}, 2025: MMC.table(conn, 2026)}, 2026)["last_season"] is True


# --- hockey ---------------------------------------------------------------------------

TEAMS = {"TOR": {"sog_against": 33.0, "ga": 3.4, "sog_for": 31.0, "n": 20, "gp_season": 8},
         "MTL": {"sog_against": 28.0, "ga": 2.6, "sog_for": 34.0, "n": 20, "gp_season": 8},
         "BOS": {"sog_against": 30.0, "ga": 3.0, "sog_for": 29.0, "n": 20, "gp_season": 1}}


def test_a_hockey_pick_carries_the_matchup_card_every_league_draws():
    sog = NMC.card("sog", "TOR", TEAMS, {"opp": 1.06, "pp_factor": 1.0})
    assert sog["opponent"] == "TOR" and sog["stat"] == "shots allowed" and sog["per_game"] == 33.0
    assert (sog["rank"], sog["of"], sog["league"]) == (1, 3, 30.3) and "last_season" not in sog
    assert "their shots allowed moves it +6%" in sog["note"] and "not a measured transfer" in sog["note"]
    goal = NMC.card("goals", "MTL", TEAMS, {"opp": 0.95 * 1.02, "pp_factor": 1.02, "shot_model": "xg"})
    assert goal["stat"] == "goals allowed" and goal["rank"] == 3
    assert "the chances they allow at five-on-five and their starter" in goal["note"] and "-5%" in goal["note"]
    saves = NMC.card("saves", "MTL", TEAMS)
    assert saves["stat"] == "shots taken" and saves["rank"] == 1 and "shots against" in saves["note"]
    thin = NMC.card("sog", "BOS", TEAMS, {"opp": 1.0, "pp_factor": 1.0})
    assert thin["last_season"] is True and "not at all" in thin["note"]
    assert NMC.card("hits", "TOR", TEAMS) is None and NMC.card("sog", "NYR", TEAMS) is None
    assert f"±{NM.OPP_CAP:.0%}" in sog["note"]


# --- basketball ---------------------------------------------------------------------

def _prop(**kw):
    p = {"player": "A Guard", "market": "pts", "minutes": [34, 35, 33, 36, 34, 32, 35, 34],
         "values": [24, 28, 22, 30, 26, 25, 27, 23], "is_starter": True, "spread": -4.0, "is_favorite": True,
         "rest": "1day", "game_total": 232.0, "days_off": 1, "dvp_mult": 1.04,
         "dvp_note": "Matchup: BOS allow 118.0 points a game (3rd-most of 30) — +4% on his projection",
         "line": 25.5, "over_odds": -110, "under_odds": -110, "book": "dk", "opponent": "BOS", "team": "NYK"}
    p.update(kw)
    return p


def test_basketball_publishes_its_projection_walk_with_the_measured_matchup_step():
    pj = NP.project(_prop(), NBA)
    ch = pj["chain"]
    assert C.closes(ch) and ch["mean"] == pj["projection"] and ch["base"]["source"] == "rate"
    steps = {s["key"]: s for s in ch["steps"]}
    assert list(steps) == ["player", "environment", "rest", "matchup"]
    assert steps["matchup"]["mult"] == 1.04 and steps["matchup"]["why"].startswith("Matchup: BOS allow")
    assert steps["environment"]["label"] == "Scoring environment" and steps["rest"]["label"] == "Rest and layoff"
    assert NP.evaluate_prop(_prop(), NBA)["chain"] == ch


def test_basketball_rows_name_each_past_opponent_and_carry_the_teammate_card():
    card = {"team": "NYK", "out": ["A Star"], "applied": 1.0, "headline": "Out tonight: A Star (34 min a game)",
            "note": "Shown for you."}
    prop = _prop(opps=["BOS", "MIA", "PHI", "BOS"], homes=[1, 0, 1, 0], mate_card=card,
                 lineup_note="Out tonight: A Star (34 min a game). Those minutes go to the rest.")
    rows = NP.shared_recommendations([prop], dates_map={"A Guard": ["2026-10-10", "2026-10-08", "2026-10-06",
                                                                    "2026-10-04"]}, tune=NBA)
    r = rows[0]
    assert [(g["opponent"], g["home"]) for g in r["logs"][:4]] == [("BOS", 1), ("MIA", 0), ("PHI", 1), ("BOS", 0)]
    assert r["form"]["vs_opponent"] is None, "team history stays off the card (the WNBA spec)"
    assert r["mate_card"] == card and not any("Out tonight" in x for x in r["reasons"]), "said once, on the card"
    assert C.closes(r["chain"])
    # No card: the evidence is still said, as the bullet it was.
    bare = NP.shared_recommendations([_prop(lineup_note="Out tonight: Someone.")], tune=NBA)[0]
    assert "Out tonight: Someone." in bare["reasons"] and bare["logs"][0]["opponent"] == ""


def test_the_teammate_card_has_the_shape_every_league_draws():
    dates = [f"2026-02-{d:02d}" for d in range(10, 20)]
    sat = set(dates[:4])
    hist = {"Star": {"team": "BOS", "by_week": {d: {"min": 34.0, "pts": 30.0} for d in dates if d not in sat}},
            "Wing": {"team": "BOS", "by_week": {d: {"min": 30.0, "pts": 26.0 if d in sat else 16.0} for d in dates}}}
    gone = {"BOS": [("Star", 34.0)]}
    c = nba_build.lineup_card("Wing", "pts", "BOS", gone, hist)
    assert set(c) >= {"team", "out", "headline", "applied", "note"} and c["out"] == ["Star"]
    assert c["headline"] == "Out tonight: Star (34 min a game)" and c["note"].startswith("Shown for you.")
    assert nba_build.lineup_card("Star", "pts", "BOS", gone, hist) is None
    assert nba_build.lineup_note("Wing", "pts", "BOS", gone, hist).startswith("Out tonight: Star (34 min a game).")


def test_the_history_keeps_who_he_played_and_where():
    conn = D.connect(":memory:")
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("nba", 2026, d, f"g{d}", "A Guard", "NYK", opp, "S", home, m, v)
                      for d, opp, home in (("2026-10-10", "BOS", 1), ("2026-10-08", "MIA", 0))
                      for m, v in (("min", 34.0), ("pts", 25.0))])
    h = nba_build.player_history(conn, {"NYK"}, "nba")["A Guard"]
    assert h["dates"] == ["2026-10-10", "2026-10-08"] and h["opps"] == ["BOS", "MIA"] and h["homes"] == [1, 0]


# --- the board and the page -------------------------------------------------------------

def test_the_cards_reach_the_most_likely_row_in_every_league():
    mu = {"opponent": "NYY", "stat": "hits allowed", "per_game": 9.1, "league": 8.4, "rank": 3, "of": 30,
          "games": 140, "note": "Model: …"}
    mate = {"team": "NYK", "out": ["A Star"], "headline": "Out tonight: A Star", "note": "Shown for you."}
    row = {"player": "P", "team": "T", "opponent": "NYY", "market": "hits", "side": "OVER", "line": 0.5,
           "odds": -150, "book": "dk", "matchup_card": mu, "mate_card": mate, "chain": {"steps": []}}
    got = L._row_from(row, "hits", "mlb", lambda m: True, 0.66, shown=0.66)
    assert got["matchup_card"] == mu and got["mate_card"] == mate


def test_the_page_draws_every_leagues_card_with_its_one_renderer():
    node = shutil.which("node")
    if not node:
        return
    i = APP_JS.index("const MU_EDGE = ")
    j = APP_JS.index("function pickInjuryNote(")
    src = APP_JS[i:j]
    mlb = {"side": "OVER", "matchup_card": MMC.card(_mlb_row("hits", "NYY"), {2026: MMC.table(_pa_conn(), 2026)},
                                                    2026)}
    nhl = {"side": "UNDER", "matchup_card": NMC.card("sog", "TOR", TEAMS, {"opp": 1.06, "pp_factor": 1.0})}
    prog = ("const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')"
            ".replace(/>/g, '&gt;').replace(/\"/g, '&quot;');\n"
            f"{src}\nconsole.log(JSON.stringify([matchupCardHTML({json.dumps(mlb)}), matchupCardHTML({json.dumps(nhl)})]));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr[-800:]
    a, b = json.loads(out.stdout.strip())
    assert "Matchup vs NYY" in a and "this season, 6 games" in a and ">10</b> hits allowed a game" in a
    assert "1st-most of 4" in a and "Model: tonight" in a
    assert "Matchup vs TOR" in b and ">33</b> shots allowed a game" in b and "not a measured transfer" in b
    # The rank is coloured for the pick's side: the most shots allowed hurts an under.
    assert re.search(r'mu-rank bad">1st-most of 3', b)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
