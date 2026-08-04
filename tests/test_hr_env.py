"""hr_env: park and wind become journaled, mineable, vetoing dimensions.

The hypothesis lab's top watchlist idea ("park and wind factors for
home-run overs"), drafted into a spec by the triage bench, built here.
The raw measurements existed all along — the parks table carries an HR
index, the weather layer classifies wind against each park's real
center-field bearing — but nothing JOURNALED them, so no slice could
ever be tested. Now every MLB bet records the park index, the signed
wind toward CF, and the roof state at pick time; the miner bands and
slices them under the same false-discovery control as everything else;
a convicted pocket vetoes the next matching pick; and the lab can
propose intersections on them.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger
from engine import losspatterns as lp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the bands ---------------------------------------------------------------
def test_the_park_bands_cover_the_spec():
    assert lp.park_band(0.85) == "suppressing park"
    assert lp.park_band(1.0) == "neutral park"
    assert lp.park_band(1.22) == "boosting park"
    assert lp.park_band(1.22, roofed=True) == "roof closed/dome"
    assert lp.park_band(None) is None
    assert lp.park_band("garbage") is None


def test_the_wind_bands_are_signed_and_silent_indoors():
    assert lp.wind_band(-12) == "wind in hard"
    assert lp.wind_band(-5) == "wind in"
    assert lp.wind_band(0) == "calm/cross"
    assert lp.wind_band(5) == "wind out"
    assert lp.wind_band(14) == "wind out hard"
    # Indoors there is no wind dimension at all — the park band already
    # says "roof", and a duplicate band would double-count the same fact.
    assert lp.wind_band(14, roofed=True) is None
    assert lp.wind_band(None) is None


# --- journal → miner → veto --------------------------------------------------
def test_a_journaled_bet_carries_its_environment():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": "2099-01-01",
        "recommendations": [{
            "player": "Env Bat", "market": "hits", "side": "OVER",
            "line": 1.5, "odds": -110, "grade": "A", "stake_units": 1.0,
            "hit_prob": 0.57, "edge": 0.04, "confidence": 8.0,
            "recommended": True, "team": "CHC", "opponent": "PHI",
            "park_hr": 1.04, "wind_out": 11.0, "roofed": False}],
        "games": []})
    row = conn.execute(
        "SELECT park_hr, wind_out, roofed FROM bets").fetchone()
    assert (row[0], row[1], row[2]) == (1.04, 11.0, 0)


def test_the_miner_reads_the_environment_off_the_journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " hit_prob, stake_units, status, category, park_hr, wind_out, roofed)"
        " VALUES ('t','mlb','2026-07-01','X','home_runs','OVER',0.5,350,"
        "0.2,0.1,'won','longshot',1.22,9.0,0)")
    conn.commit()
    recs = lp.records_from_ledger(conn)
    assert recs[0]["feats"]["park"] == "boosting park"
    assert recs[0]["feats"]["wind"] == "wind out hard"


def test_a_convicted_wind_pocket_vetoes_the_next_matching_pick():
    import json as _json
    path = tempfile.mktemp(suffix=".json")
    open(path, "w").write(_json.dumps({"findings": [], "closed": [
        {"sport": "mlb", "market": "home_runs", "dim": "wind",
         "value": "wind in hard", "reading": "ran hot"}]}))
    hit = lp.veto("mlb", "home_runs", side="OVER", odds=350,
                  wind_out=-10.0, path=path)
    assert hit and "wind in hard" in hit
    # Outdoor pick with no wind reading, or an indoor pick: never blocked.
    assert lp.veto("mlb", "home_runs", side="OVER", odds=350,
                   wind_out=None, path=path) is None
    assert lp.veto("mlb", "home_runs", side="OVER", odds=350,
                   wind_out=-10.0, roofed=True, path=path) is None


def test_the_miner_can_convict_an_environment_pocket():
    recs = []
    for i in range(120):    # wind-out overs: said 20%, hit 10% — a pocket
        recs.append({"sport": "mlb", "market": "home_runs", "prob": 0.20,
                     "won": 1 if i < 12 else 0,
                     "feats": lp.features_of(side="OVER", odds=350,
                                             prob=0.20, park_hr=1.0,
                                             wind_out=10.0)})
    for i in range(120):    # calm: calibrated
        recs.append({"sport": "mlb", "market": "home_runs", "prob": 0.20,
                     "won": 1 if i < 24 else 0,
                     "feats": lp.features_of(side="OVER", odds=350,
                                             prob=0.20, park_hr=1.0,
                                             wind_out=0.0)})
    out = lp.mine(recs)
    winds = [f for f in out["findings"] if f["dim"] == "wind"]
    assert any(f["value"] == "wind out hard" for f in winds), out["findings"]


# --- the pipeline attaches what the journal records --------------------------
def test_the_board_ships_the_environment_on_every_mlb_rec():
    from engine.mlb.pipeline import run_mlb_slate
    out = run_mlb_slate(os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    recs = out["recommendations"]
    assert recs and all("park_hr" in r and "wind_out" in r and "roofed" in r
                        for r in recs)
    shots = out["long_shots"]
    assert all("park_hr" in s for s in shots)
    # A dome game's wind is honestly absent, not zero.
    domed = [r for r in recs if r["roofed"]]
    assert all(r["wind_out"] is None for r in domed)


def test_the_mlb_gate_hands_the_veto_its_live_environment():
    src = open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
               encoding="utf-8").read()
    i = src.index("pattern_block = lp_veto(")
    assert "_env_of(game)" in src[max(0, i - 700):i]
    assert "**_env" in src[i:i + 400]


def test_football_wind_is_magnitude_and_baseball_wind_is_signed():
    """The sport decides what wind MEANS. Baseball's is signed against the
    park's center-field bearing; football has no "out" — speed is what
    leans on the passing game. Slices are keyed by sport, so the two
    vocabularies can never pool."""
    assert lp.wind_band(10, sport="mlb") == "wind out hard"
    assert lp.wind_band(10, sport="nfl") == "windy (8-15mph)"
    assert lp.wind_band(18, sport="nfl") == "howling (15mph+)"
    assert lp.wind_band(5, sport="cfb") == "calm (<8mph)"
    assert lp.wind_band(10, roofed=True, sport="nfl") is None


def test_the_nfl_board_journals_its_weather_too():
    from engine.pipeline import run_slate
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    recs = out["recommendations"]
    assert recs and all("roofed" in r and "wind_out" in r for r in recs)
    for r in recs:
        if r["roofed"]:
            assert r["wind_out"] is None    # indoors has no wind dimension


def test_the_nfl_gate_hands_the_veto_its_weather():
    src = open(os.path.join(ROOT, "engine", "betting.py"),
               encoding="utf-8").read()
    i = src.index("pattern_block = lp_veto(")
    before = src[max(0, i - 900):i]
    assert 'sport in ("nfl", "cfb")' in before
    assert "**_env" in src[i:i + 500]


def test_the_environment_coverage_matrix_is_honest():
    """Every sport gets exactly the environment physics supports — and
    the N/As are decisions, not omissions. MLB: park index + signed wind.
    NFL: dome + wind magnitude. CFB: gate wired, but its build pulls no
    weather feed (documented on the board as 'weather not pulled'), so
    rows band unknown until one exists. NBA/WNBA/UFC: indoor sports —
    attaching a constant "roof" band to every bet would be a
    non-discriminating slice, i.e. noise wearing a dimension's name."""
    mlb_pipe = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
                    encoding="utf-8").read()
    nfl_pipe = open(os.path.join(ROOT, "engine", "pipeline.py"),
                    encoding="utf-8").read()
    nba_pipe = open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
                    encoding="utf-8").read()
    assert "_env_of(game)" in mlb_pipe
    assert 'd["wind_out"]' in nfl_pipe
    assert "wind_out" not in nba_pipe, \
        "an indoor sport grew a wind dimension — that is noise, not data"


def test_the_lab_can_propose_on_park_and_wind():
    from engine import hypotheses as hyp
    assert "park" in hyp.DIMS and "wind" in hyp.DIMS
    props = hyp.SCHEMA["properties"]["hypotheses"]["items"]
    for dim in ("park", "wind"):
        assert dim in props["properties"] and dim in props["required"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
