"""Basketball's matchup read: what tonight's defence allows, under the pick.

The NFL, college and MLB boards say whom a player is facing; basketball's
said nothing. `engine/hoopsdvp` rates every defence by what it concedes a
game in points, rebounds, assists and threes — walk-forward, shrunk by
games — and hangs the NFL's own `matchup_card` on each pick. Measured on
the box (hoopsdvpfit.py, 2026-09-27), it now moves the projection.
"""
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hoopsdvp as H                                  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
BUILD = (ROOT / "nba_build.py").read_text(encoding="utf-8")


def _logs(days=20, soft="PHX", lift=1.3, seed=3):
    """Six teams, one opponent each night; `soft` concedes `lift`× points."""
    rnd = random.Random(seed)
    teams = ["BOS", "NYK", "PHX", "DEN", "LAL", "MIA"]
    rows = []
    for d in range(days):
        day = f"2026-01-{d + 1:02d}"
        order = teams[d % 6:] + teams[:d % 6]
        for a, b in zip(order[::2], order[1::2]):
            for team, opp in ((a, b), (b, a)):
                for k in range(5):
                    base = 10 + 4 * k
                    pts = base * (lift if opp == soft else 1.0) * rnd.uniform(0.95, 1.05)
                    rows.append((day, team, opp, "pts", round(pts, 1), f"{team}-{k}"))
                    rows.append((day, team, opp, "reb", round(4 + k * rnd.uniform(0.9, 1.1), 1), f"{team}-{k}"))
    return rows


def test_the_soft_defence_ranks_first_and_the_factor_is_shrunk():
    r = H.ratings([x[:5] for x in _logs()])
    phx = r["PHX"]["pts"]
    assert phx["rank"] == 1 and phx["of"] == 6
    raw = phx["pg"] / phx["league"]
    assert 1.0 < phx["factor"] < raw, "shrunk toward the league, not all the way"
    assert abs(phx["factor"] - (1 + (raw - 1) * phx["games"] / (phx["games"] + H.SHRINK_GAMES))) < 1e-3


def test_it_is_walk_forward():
    rows = [x[:5] for x in _logs()]
    early = H.ratings(rows, before="2026-01-06")
    assert all(c["games"] <= 5 for d in early.values() for c in d.values())
    assert H.ratings(rows, before="2026-01-01") == {}


def test_the_card_says_what_it_is_and_that_the_model_reads_it():
    card = H.matchup_card("PHX", H.ratings([x[:5] for x in _logs()]), "pts")
    assert card["opponent"] == "PHX" and card["rank"] == 1 and card["stat"] == "points allowed"
    assert "Read into the projection" in card["note"] and "per possession" in card["note"]
    assert H.matchup_card("PHX", {}, "pts") is None and H.matchup_card("PHX", {"PHX": {}}, "min") is None


def test_the_measured_transfer_moves_the_projection():
    # hoopsdvpfit.py on the box, 2026-09-27: the NBA's whole lean in every
    # stat, the WNBA's 78-100% — capped at the whole lean, never more.
    assert H.TRANSFER["nba"] == {"pts": 1.0, "reb": 1.0, "ast": 1.0, "fg3m": 1.0}
    assert H.TRANSFER["wnba"] == {"pts": 0.79, "reb": 0.78, "ast": 1.0, "fg3m": 0.89}
    assert all(0.0 < v <= 1.0 for lg in H.TRANSFER.values() for v in lg.values())
    rating = {"PHX": {"pts": {"pg": 90.0, "league": 80.0, "rank": 1, "of": 13, "games": 20, "factor": 1.10}}}
    m, note = H.projection_mult("nba", rating, "PHX", "pts")
    assert m == 1.10 and "+10% on his projection" in note and "the whole" in note
    m, note = H.projection_mult("wnba", rating, "PHX", "pts")
    assert m == 1.079 and "79% of the" in note
    assert H.projection_mult("nba", rating, "LVA", "pts") == (1.0, "")
    assert H.projection_mult("nba", rating, "PHX", "min") == (1.0, "")
    assert H.projection_mult("mlb", rating, "PHX", "pts") == (1.0, "")


def test_the_pipeline_multiplies_it_in():
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    src = open(_os.path.join(root, "engine", "nba", "pipeline.py"), encoding="utf-8").read()
    assert "proj = round(rate * proj_min * pmult * env_m * lay_m * dvp_m, 2)" in src
    build = open(_os.path.join(root, "nba_build.py"), encoding="utf-8").read()
    assert '"dvp_mult": _dm, "dvp_note": _dn,' in build


def test_attach_hangs_cards_on_the_picks():
    rating = H.ratings([x[:5] for x in _logs()])
    recs = [{"player": "A", "opponent": "PHX", "market": "pts"}, {"player": "B", "opponent": "XXX", "market": "pts"},
            {"player": "C", "opponent": "PHX", "market": "min"}, "junk"]
    assert H.attach(recs, rating) == 1 and recs[0]["matchup_card"]["rank"] == 1
    assert "matchup_card" not in recs[1] and "matchup_card" not in recs[2]


def test_opening_night_reads_last_season():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, player TEXT, "
                 "team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    for day, team, opp, m, v, p in _logs():
        conn.execute("INSERT INTO player_game_logs VALUES ('nba', 2025, ?, ?, ?, ?, ?, 'S', 1, ?, ?)",
                     (day, f"{p}-{day}", p, team, opp, m, v))
    rating, last = H.board_ratings(conn, "nba", "2026-10-22")
    assert last is True and rating["PHX"]["pts"]["rank"] == 1
    assert H.matchup_card("PHX", rating, "pts", last)["last_season"] is True


def test_the_fit_finds_a_planted_effect_and_not_a_missing_one():
    got = H.measure(_logs(days=60, lift=1.3))
    assert got["pts"]["slope"] > 0.5, got["pts"]
    flat = H.measure(_logs(days=60, lift=1.0))
    assert abs(flat["pts"]["slope"]) < 0.5 or "noise" in flat["pts"]["verdict"] or "not enough" in flat["pts"]["verdict"]
    assert "not enough games yet" in H.measure(_logs(days=8))["pts"]["verdict"]


def test_the_build_and_the_page_carry_it():
    assert "_dvp.board_ratings(conn, args.league, args.date)" in BUILD
    assert BUILD.index("_dvp.attach(recs") < BUILD.index('out["recommendations"] = recs')
    card = APP[APP.index("function matchupCardHTML("):APP.index("function pickInjuryNote(")]
    assert "c.note ? escapeHtml(c.note)" in card and 'c.last_season ? "last season" : "this season"' in card


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
