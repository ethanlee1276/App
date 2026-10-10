"""College's teammate-out and new-quarterback steps: measured on college games, applied like the NFL's.

Ethan, 2026-10-10: "do the teammate-out and new QB stuff for college now
... we want the same methods and tools and models as we use for nfl."

These check, one rule each: the depth order ranks a college team's players
on catches (carries plus catches for a back) over its earlier games; a
ranked teammate with no row in a game his team played is out, cased the
NFL's way; a starter with no pass is out and his replacement is tiered on
his earlier passing; the NFL's rule (2 SE, 3+ seasons) adopts a planted
effect and refuses noise; the store round-trips; the build stamps each
game before pricing and the projection's two steps then read college's
own table — never the NFL's — and nothing moves until college is
measured; the NFL's paths are unchanged.

Run directly: `python3 tests/test_the_college_lineup.py`
"""
import os
import sqlite3
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine.cfb import lineup as L                                 # noqa: E402

DAYS = ["2025-09-06", "2025-09-13", "2025-09-20", "2025-09-27", "2025-10-04", "2025-10-11"]


def _db(rows):
    from engine import db
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.row_factory = sqlite3.Row
    return c


def _log(season, day, team, player, pos, market, value, gid="1"):
    return ("cfb", season, day, f"{gid}-{day}", player, team, "OPP", pos, 1, market, float(value))


def _team_rows(season, team, days, wr1_out=(), qb1_out=(), boost=1.0, seed=0):
    """One team's season: WR1 (6 catches), WR2 (4), WR3 (2), RB1 (15
    carries), QB1 starts (30 attempts, 8 ypa), QB2 the backup (5.5 ypa)."""
    out = []
    for i, d in enumerate(days):
        out.append(_log(season, d, team, f"{team} QB2", "QB", "pass_att", 30 if d in qb1_out else 2))
        out.append(_log(season, d, team, f"{team} QB2", "QB", "pass_yds", 165 if d in qb1_out else 10))
        if d not in qb1_out:
            out.append(_log(season, d, team, f"{team} QB1", "QB", "pass_att", 30))
            out.append(_log(season, d, team, f"{team} QB1", "QB", "pass_yds", 240))
        if d not in wr1_out:
            out.append(_log(season, d, team, f"{team} WR1", "WR", "receptions", 6))
            out.append(_log(season, d, team, f"{team} WR1", "WR", "rec_yds", 80))
        wobble = 1 + 0.05 * (((i + seed) % 3) - 1)
        catches = 4 * wobble * (boost if d in wr1_out else 1.0)
        out.append(_log(season, d, team, f"{team} WR2", "WR", "receptions", round(catches, 2)))
        out.append(_log(season, d, team, f"{team} WR2", "WR", "rec_yds", round(catches * 12, 1)))
        out.append(_log(season, d, team, f"{team} WR3", "WR", "receptions", 2))
        out.append(_log(season, d, team, f"{team} WR3", "WR", "rec_yds", 25))
        out.append(_log(season, d, team, f"{team} RB1", "RB", "rush_att", 15))
        out.append(_log(season, d, team, f"{team} RB1", "RB", "rush_yds", 70))
    return out


def test_the_depth_order_ranks_catches_and_a_missing_teammate_is_out():
    c = _db(_team_rows(2025, "UGA", DAYS, wr1_out={DAYS[4]}))
    players, team_days = L.season_games(c, 2025)
    assert team_days["UGA"] == DAYS
    roster = players["UGA"]
    assert roster["UGA QB1"]["role"] == "QB" and roster["UGA RB1"]["role"] == "RB"
    order = L.ranked(roster, "WR", DAYS[:4])
    assert [o[0] for o in order] == ["UGA WR1", "UGA WR2", "UGA WR3"], "ranked on catches a game"
    pts = L.mate_samples(c, [2025])
    wr2 = [p for p in pts if p["g"] == "WR" and p["m"] == "receptions" and p["tier"] == "above_new"]
    assert wr2, "WR2 and WR3 in the game WR1 missed are the 'ranked above him, just out' case"
    assert any(p["tier"] is None for p in pts), "games with everyone playing are the baseline"


def test_a_starter_with_no_pass_is_out_and_his_replacement_is_tiered():
    c = _db(_team_rows(2025, "UGA", DAYS, qb1_out={DAYS[5]}))
    pts = L.qb_samples(c, [2025])
    tiers = {p["tier"] for p in pts}
    assert "downgrade" in tiers, "5.5 ypa behind an 8.0 starter is a downgrade"
    assert None in tiers
    assert L.tier_of({"A": (300, 2400), "B": (60, 470)}, "A", "B")[0] == "similar"   # 7.8 vs 8.0
    assert L.tier_of({"A": (300, 2400), "B": (40, 400)}, "A", "B")[0] == "downgrade"  # too few attempts


def _league(boost, seasons=(2022, 2023, 2024, 2025), teams=30):
    rows = []
    for s in seasons:
        days = [f"{s}-09-{6 + 7 * k:02d}" if 6 + 7 * k <= 30 else f"{s}-10-{6 + 7 * k - 30:02d}" for k in range(8)]
        for t in range(teams):
            out = {days[4 + (t % 4)]}
            rows += _team_rows(s, f"T{t}", days, wr1_out=out, boost=boost, seed=t)
    return _db(rows)


def test_the_nfls_rule_adopts_a_planted_effect_and_refuses_noise():
    real = L.fit(_league(1.6))
    key = ("receptions", "WR", "above_new")
    assert key in real["adopt_mates"] and 1.4 < real["adopt_mates"][key] < 1.8, real["mates"].get(key)
    flat = L.fit(_league(1.0))
    assert key not in flat["adopt_mates"], "no effect, nothing applied"


def test_the_store_round_trips_and_says_whether_college_is_measured():
    p = L._store()
    if p.exists():
        p.unlink()
    L._CACHE.clear()
    assert not L.measured() and L.mate_table() == {} and L.qb_mult("receptions", "WR", "downgrade") == 1.0
    L.save({"seasons": [2024, 2025], "adopt_mates": {("receptions", "WR", "above_new"): 1.3},
            "adopt_qb": {("rec_yds", "WR", "downgrade"): 0.88}})
    assert L.measured()
    assert L.mate_table() == {("receptions", "WR", "above_new"): 1.3}
    assert L.qb_mult("rec_yds", "wr", "downgrade") == 0.88 and L.qb_mult("rec_yds", "WR", None) == 1.0


def _slate():
    game = NS(home="UGA", away="VAN")
    props = [NS(market="pass_yds", team="UGA", player="UGA QB2", lines=[NS(book="fanduel")]),
             NS(market="receptions", team="UGA", player="UGA WR2", lines=[NS(book="fanduel")])]
    return NS(games=[game], props=props), game


def test_the_build_stamps_college_games_and_the_projection_reads_colleges_table():
    from engine import teammates as T, qbchange as Q
    c = _db(_team_rows(2025, "UGA", DAYS) + _team_rows(2024, "UGA", DAYS))
    slate, game = _slate()
    injuries = [NS(team="UGA", player="UGA WR1", status="OUT"), NS(team="UGA", player="UGA QB1", status="OUT")]
    got = L.attach(c, slate, [{"home": "UGA", "away": "VAN"}], injuries, 2025, "2025-10-18")
    lu = game.lineup["UGA"]
    assert lu["basis"] == "cfb" and lu["last"] == 6
    assert [o[0] for o in lu["order"]["WR"]][:2] == ["UGA WR1", "UGA WR2"]
    assert lu["out"] and "wr1" in lu["out"][0]
    ch = game.qb_changes["UGA"]
    assert ch["league"] == "cfb" and ch["replacement"] == "UGA QB2" and ch["tier"] == "downgrade"
    assert got["qb_changes"]["UGA"] is ch
    wr2 = NS(market="receptions", team="UGA", player="UGA WR2", position="WR")
    # Measured: college's own numbers apply, and the cards say so.
    L.save({"seasons": [2024, 2025], "adopt_mates": {("receptions", "WR", "above_new"): 1.3},
            "adopt_qb": {("receptions", "WR", "downgrade"): 0.9}})
    m, why, card = T.effect(wr2, game)
    assert m == 1.3 and "college" in card["note"], card
    qm, qwhy, qcard = Q.effect(wr2, game)
    assert qm == 0.9 and qcard["applied"] == 0.9 and "college" in qcard["note"]
    # A college table is never the NFL's: a key only the NFL measured stays 1.0.
    rb = NS(market="rush_yds", team="UGA", player="UGA RB1", position="RB")
    assert T.effect(rb, game)[0] == 1.0


def test_nothing_moves_until_college_is_measured():
    from engine import teammates as T, qbchange as Q
    p = L._store()
    if p.exists():
        p.unlink()
    L._CACHE.clear()
    c = _db(_team_rows(2025, "UGA", DAYS))
    slate, game = _slate()
    L.attach(c, slate, [{"home": "UGA", "away": "VAN"}],
             [NS(team="UGA", player="UGA WR1", status="OUT"), NS(team="UGA", player="UGA QB1", status="OUT")],
             2025, "2025-10-18")
    wr2 = NS(market="receptions", team="UGA", player="UGA WR2", position="WR")
    m, _why, card = T.effect(wr2, game)
    assert m == 1.0 and "not been measured" in card["note"]
    qm, _w, qcard = Q.effect(wr2, game)
    assert qm == 1.0 and "not been measured" in qcard["note"]


def test_the_nfls_paths_are_unchanged():
    from engine import teammates as T
    assert T.table_for({"basis": "targets"}) is T.EFFECT
    assert T.table_for({"basis": "snaps"}) is T.EFFECT_SNAPS
    assert T.table_for({}) is T.EFFECT


def test_the_build_runs_it_before_pricing_and_the_weekly_job_refits_it():
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert src.index("_clu.attach(") < src.index('out["recommendations"] = _price_props(_prop_slate, sport="cfb")')
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert '_spawn_module("engine.cfb.lineup", log)' in maint


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
