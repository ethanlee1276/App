"""The inventions, gated into the picks — each moves Most Likely and Edge only once its own held-out bar holds.

Ethan, 2026-10-17: "make sure we are wrapping all the features into the
most likely bets and edge bets where it makes sense. just cause we add
features and data and shit and say we did doesnt mean we are using them the
right way."

What these hold: with no verdict on disk nothing moves — not a chance, not
a hold, not a refusal, not a prior, not a volume, not a correlation; each
gate moves its own number the moment its saved verdict says HOLDS, by what
was measured and no more (the readings on one pick are capped together);
a posted pick keeps its chance and the journal keeps the first claim; the
market check takes the fair chance by opinion; a hold takes a pick off Most
Likely and refuses it on Edge, and so does a proven reading that takes the
edge away; the honest range holds a pick only where it was covered AND
better calibrated than our chance; the rookie prior, the role-scaled
volume, the air step and the simulated teammate correlation reach the
projection, the usage bridge and the parlay pricer, a banned pairing stays
banned; and the builds run the gates where the picks are made. No test
touches the network.

Run directly: `python3 tests/test_the_inventions_gated_into_the_picks.py`
"""
import json
import os
import random
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import conformal as CF                               # noqa: E402
from engine import ideagate as G                                 # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine import likelyboard as LB                             # noqa: E402
from engine import nflusage as NU                                # noqa: E402
from engine import parlays as P                                  # noqa: E402
from engine import practice as PR                                # noqa: E402
from engine import rolechange as RC                              # noqa: E402
from engine.models import Game, Weather                          # noqa: E402


class _Models:
    """A private models folder for one test, the gate's cache emptied."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("QB_MODELS_DIR")
        os.environ["QB_MODELS_DIR"] = self.dir
        G._cache.clear()
        ID.LAST.clear()
        return self

    def put(self, name, data):
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump(data, fh)
        G._cache.clear()

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = self.old
        shutil.rmtree(self.dir)
        G._cache.clear()
        ID.LAST.clear()


NAME = "Dalton Kincaid"


def _secs(spike=True):
    """One slate's readings, every one pointing at Kincaid's under."""
    return {"sections": {
        "menu": {"rows": [{"check": "pass_rec", "lean": "parts", "z": 2.6, "book": "DraftKings",
                           "label": "Passing yards against his receivers' yards", "players": ["Josh Allen", NAME],
                           "parent": {"player": "Josh Allen", "market": "pass_yds"},
                           "parts": [{"player": NAME, "market": "rec_yds"}]}]},
        "recipe": {"rows": {f"{NAME}|rec_yds": {"expect": 45.0, "sd": 10.0}}},
        "attention": {"players": {NAME: {"spike": spike, "ratio": 3.4}}},
        "copies": {"rows": {f"{NAME}|rec_yds": {"by_group": 0.40, "by_book": 0.43, "line": 60.5}}},
        "practice": {"listed": {PR._norm(NAME): {"player": NAME, "team": "BUF", "designation": "Questionable",
                                                 "practice": "DNP · DNP · LP", "league": 0.62, "club": 0.41}}},
    }}


def _row(side="Under", prob=0.60, **kw):
    return {"player": NAME, "market": "rec_yds", "side": side, "line": 60.5, "projection": 52.0,
            "model_prob": prob, "odds": -115, **kw}


def _proven(m, practice=False):
    m.put("bookmenu_fit.json", {"nfl": {"verdict": {"pass_rec": {"parts": {"holds": True, "excess": 0.04}}}}})
    m.put("bookrecipe_fit.json", {"nfl": {"rec_yds": {"verdict": {"holds": True, "excess": 0.03}}}})
    m.put("attention_verdict.json", {"nfl": {"holds": True, "under_when_spiked": {"excess": 0.05}}})
    m.put("bookclusters.json", {"nfl": {"consensus": {"holds": True}}})
    if practice:
        m.put("practice_fit.json", {"nfl": {"held_out": {"holds": True}}})


def test_nothing_moves_without_a_verdict():
    with _Models():
        assert all(st in (G.UNMEASURED, G.ELSEWHERE, "never a number, by design") for *_x, st in G.state("nfl"))
        rows = [_row(), _row(side="Over", prob=0.58)]
        assert G.most_likely(rows, "nfl", _secs()) == 0
        assert [r["model_prob"] for r in rows] == [0.60, 0.58]
        assert not any(k in r for r in rows for k in ("idea_note", "idea_hold", "market_fair", "board_raw_prob"))
        res = {"recommendations": [dict(_row(side="Over"), hit_prob=0.56, recommended=True, stake_units=1.0)]}
        assert G.edge(res, "nfl", _secs()) == 0 and res["recommendations"][0]["recommended"]
        assert G.rookie_prior("Tet McMillan", "rec_yds", 1) is None
        assert G.role_ratio("carries", [0.7] * 6 + [0.3] * 2) == 1.0
        den = Game(home="DEN", away="KC", weather=Weather(temp_f=40.0, measured=True))
        assert G.kick_factor("fg_made", den, "nfl", "DEN") == (1.0, "")
        assert G.sim_rho("nfl", {"player": "Josh Allen", "market": "pass_yds"},
                         {"player": "Khalil Shakir", "market": "rec_yds"}) is None


def test_the_state_tells_measured_and_failed_from_never_measured():
    with _Models() as m:
        m.put("attention_verdict.json", {"nfl": {"holds": False, "under_when_spiked": {"excess": 0.01}}})
        got = dict((n, st) for n, _mod, _w, st in G.state("nfl"))
        assert got["attention"] == G.MEASURED, "measured, and it did not hold"
        assert got["menu"] == G.UNMEASURED, "no verdict on disk"
        assert got["endgame"] == G.ELSEWHERE and dict(
            (n, st) for n, _mod, _w, st in G.state("nhl"))["endgame"] in (G.MEASURED, G.UNMEASURED)
        assert G.state("nfl") and G.most_likely([_row()], "nfl", _secs()) == 0, "a failed verdict moves nothing"


def test_the_readings_move_the_chance_by_what_they_measured_capped():
    with _Models() as m:
        _proven(m)
        assert dict((n, st) for n, _mod, _w, st in G.state("nfl"))["attention"] == "HOLDS — applied"
        under, over = _row(), _row(side="Over", prob=0.58)
        assert G.most_likely([under, over], "nfl", _secs()) == 2
        assert under["model_prob"] == round(0.60 + G.MAX_SHIFT, 4), "+0.04 +0.03 +0.05 is capped at the most"
        assert under["board_raw_prob"] == 0.60 and under["idea_raw_prob"] == 0.60
        assert "menu does not add up" in under["idea_note"] and "outcome recipe" in under["idea_note"]
        assert "reading about him" in under["idea_note"]
        assert over["model_prob"] == round(0.58 - G.MAX_SHIFT, 4), "the same readings count against the over"
        assert under["market_fair"] == 0.60 and over["market_fair"] == 0.40
        ok, words = LB.market_check(dict(under, model_prob=0.80))
        assert "one vote per opinion" in words and ok is False, "80% against a 60% fair chance is far above it"
        assert LB.market_check(dict(under, model_prob=0.62))[0] is True
        quiet = _row(prob=0.61)
        G.most_likely([quiet], "nfl", _secs(spike=False))
        assert quiet["model_prob"] == 0.68, "menu and recipe alone: +0.07, under the cap"
        posted = _row(locked=True)
        G.most_likely([posted], "nfl", _secs())
        assert posted["model_prob"] == 0.60 and "idea_note" not in posted, "a posted pick keeps its number"
        game = {"kind": "game", "player": NAME, "market": "rec_yds", "side": "Under", "line": 60.5, "model_prob": 0.6}
        assert G.most_likely([game], "nfl", _secs()) == 0


def test_a_hold_takes_a_pick_off_most_likely_and_refuses_it_on_edge():
    with _Models() as m:
        _proven(m, practice=True)
        r = _row()
        G.most_likely([r], "nfl", _secs())
        assert r["idea_hold"].startswith("held back: men listed Questionable who DNP · DNP · LP played 41%")
        assert LB.held_reason(r, {}) == r["idea_hold"]
        assert LB.held_reason(dict(r, locked=True), {}) is None, "a posted pick keeps its seat"
        recs = [dict(_row(side="Over"), hit_prob=0.62, recommended=True, stake_units=1.0, reasons=["why"])]
        assert G.edge({"recommendations": recs}, "nfl", _secs()) == 1
        assert not recs[0]["recommended"] and recs[0]["stake_units"] == 0.0
        assert recs[0]["reasons"][0] == recs[0]["idea_refused"] and recs[0]["reasons"][1] == "why"


def test_a_proven_reading_that_takes_the_edge_away_refuses_it():
    with _Models() as m:
        m.put("attention_verdict.json", {"nfl": {"holds": True, "under_when_spiked": {"excess": 0.05}}})
        thin = dict(_row(side="Over", odds=-110), hit_prob=0.56, recommended=True, stake_units=1.0)
        fat = dict(_row(side="Over", odds=-110), hit_prob=0.62, recommended=True, stake_units=1.0)
        under = dict(_row(odds=-110), hit_prob=0.56, recommended=True, stake_units=1.0)
        res = {"recommendations": [thin, fat, under]}
        assert G.edge(res, "nfl", _secs()) == 1
        assert not thin["recommended"] and thin["idea_refused"].startswith("Refused: a proven reading takes the edge")
        assert fat["recommended"], "56% less 5 is under -110; 62% less 5 is not"
        assert under["recommended"], "the reading backs the under"


def test_the_honest_range_holds_only_where_it_beat_our_chance():
    rnd = random.Random(7)
    cal = CF.fit([rnd.gauss(0.0, 1.0) for _ in range(600)])
    for better, held in ((True, True), (False, False)):
        with _Models() as m:
            m.put("conformal.json", {"calibration": {"nfl|rec_yds": cal}, "held_out": {"nfl|rec_yds": {
                "holds": True, "brier_range": 0.20 if better else 0.26, "brier_model": 0.24}}})
            over, under = _row(side="Over", projection=50.0), _row(projection=50.0)
            G.most_likely([over, under], "nfl", {"sections": {}})
            assert bool(over.get("idea_hold")) is held, (better, over.get("idea_hold"))
            assert "idea_hold" not in under, "the range backs the under"
            if held:
                assert "the honest range puts his over at" in over["idea_hold"]


def test_the_rookie_prior_comes_from_his_college_line_once_proven():
    with _Models() as m:
        m.put("rookies.json", {"rookies": {"rec_yds": {"fit": {"w": [5.0, 0.5, -1.0]}, "held_out": {"holds": True}}},
                               "rookie_index": {"tet mcmillan": {"pick": 8, "college": {"rec_yds": {
                                   "school": "Arizona", "pg": 90.0, "games": 12}}}}})
        assert G.rookie_prior("Tet McMillan", "rec_yds", 2) == round(5.0 + 45.0 - __import__("math").log(8), 2)
        assert G.rookie_prior("Tet McMillan", "rec_yds", G.ROOKIE_GAMES) is None, "a month in, his own games"
        assert G.rookie_prior("Some Veteran", "rec_yds", 1) is None
    src = (ROOT / "engine" / "sources" / "nflverse.py").read_text(encoding="utf-8")
    assert "_ideagate.rookie_prior(spec.player, spec.market, len(logs))" in src
    assert 'thin.get("prior_games")' in src and 'props[-1].form_prior_kind = "rookie"' in src
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'base.shrink_kind === "rookie"' in app and "his last college season, translated to the NFL" in app


def _usage_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, player, team, period, market, value)")
    rows = []
    for w in range(1, 9):
        a, b = (14, 6) if w <= 6 else (6, 14)
        for name, c in (("James Cook", a), ("Ray Davis", b)):
            rows += [("nfl", 2026, name, "BUF", f"{w:03d}", "carries", c),
                     ("nfl", 2026, name, "BUF", f"{w:03d}", "rush_yds", 4.5 * c)]
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?)", rows)
    return conn


def test_the_usage_bridge_follows_the_detected_role_once_proven():
    from engine.fantasy import _short_key
    cook = _short_key("James Cook", "BUF")
    with _Models() as m:
        flat = NU.volume_roles(_usage_conn(), season=2026)[cook]["rush_yds"]
        # Before the detector holds, carries are every game by its age
        # (nflusage.ROLE_HALF_LIFE, 2026-10-17); once it holds, its role
        # scales the four flat weeks (14, 14, 6, 6 = 10) as it always did.
        aged = NU.ewma_opps([14.0] * 6 + [6.0] * 2, NU.ROLE_HALF_LIFE["carries"])
        assert flat["opp_per_game"] == round(aged, 2) and "role_ratio" not in flat, flat
        m.put("rolechange.json", {"shares": {"car": {"settings": RC.DEFAULT, "verdict": {"holds": True}}}})
        ratio = G.role_ratio("carries", [0.7] * 6 + [0.3] * 2)
        assert G.ROLE_RANGE[0] <= ratio < 0.8, ratio
        moved = NU.volume_roles(_usage_conn(), season=2026)[cook]["rush_yds"]
        assert moved["role_ratio"] == round(ratio, 3) and moved["opp_per_game"] == round(10.0 * ratio, 2)
        assert G.role_ratio("pass_att", [0.5] * 8) == 1.0, "no detector for attempts"


def test_the_air_step_reads_tonights_air_against_his_usual_once_proven():
    with _Models() as m:
        m.put("kickphysics.json", {"nfl": {"holds": True, "full": [4.5, -0.6, -0.05, 0.0, -1.5], "mean_dev": -0.02}})
        den = Game(home="DEN", away="KC", weather=Weather(temp_f=50.0, measured=True))
        mult, why = G.kick_factor("fg_made", den, "nfl", "KC")
        assert mult > 1.0 and "thinner than the air his record was kicked in" in why
        home, _w = G.kick_factor("fg_made", den, "nfl", "DEN")
        assert 1.0 <= home < mult, "a Denver kicker's record already flew through half of it"
        pts, _w = G.kick_factor("kick_pts", den, "nfl", "KC")
        assert abs((pts - 1.0) - G.FG_SHARE * (mult - 1.0)) < 1e-3, "kicking points move by the field goals' share"
        dome = Game(home="DET", away="DEN", weather=Weather(dome=True))
        assert G.kick_factor("fg_made", dome, "nfl", "DEN")[0] < 1.0, "sea-level air is thick for a Denver leg"
        blank = Game(home="DEN", away="KC", weather=Weather())
        assert G.kick_factor("fg_made", blank, "nfl", "KC") == (1.0, ""), "a 65° placeholder is no air"
        assert G.kick_factor("rec_yds", den, "nfl", "KC") == (1.0, "")
    proj = (ROOT / "engine" / "projection.py").read_text(encoding="utf-8")
    assert '_kick_factor(prop.market, game, sport, getattr(prop, "team", None))' in proj
    assert 'steps.append(chain.step("air", air_mult, air_why))' in proj
    from engine import chain
    assert chain.STEP_LABELS["air"]


def test_teammates_take_the_simulated_correlation_once_proven_and_a_ban_stays():
    allen = {"player": "Josh Allen", "team": "BUF", "market": "pass_yds", "side": "Over", "game": "MIA @ BUF"}
    shakir = {"player": "Khalil Shakir", "team": "BUF", "market": "rec_yds", "side": "Over", "game": "MIA @ BUF"}
    with _Models() as m:
        before = P.relate("nfl", allen, shakir)
        prior = P.relate_prior("nfl", allen, shakir)
        assert (before.rho, before.verdict) == (prior.rho, prior.verdict)
        ID.LAST["nfl"] = {"sections": {"sim": {"players": {"Josh Allen|pass_yds": {
            "links": [{"player": "Khalil Shakir", "market": "rec_yds", "rho": 0.31}]}}}}}
        assert P.relate("nfl", allen, shakir).rho == before.rho, "no verdict, the taxonomy's number"
        m.put("playsim.json", {"verdict": {"holds": True}})
        got = P.relate("nfl", allen, shakir)
        assert got.rho == 0.31 and got.measured and got.verdict == prior.verdict and "simulated games" in got.mechanism
        flip = P.relate("nfl", allen, dict(shakir, side="Under"))
        assert flip.rho == -0.31 and flip.verdict == P.relate_prior("nfl", allen, dict(shakir, side="Under")).verdict
        assert P.relate("nfl", allen, dict(shakir, player="Someone Else")).rho == prior.rho
    sim = (ROOT / "engine" / "playsim.py").read_text(encoding="utf-8")
    assert "P.relate_prior(sport," in sim, "the simulation is measured against the taxonomy, never itself"


def test_the_builds_run_the_gates_where_the_picks_are_made():
    nfl = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    attach = nfl.index('_ideas.attach("nfl", slate.props, result.get("games"), result, out=args.out)')
    assert attach < nfl.index("# ONE MOST LIKELY BOARD (engine/likelyboard)"), "readings before the board"
    assert attach < nfl.index('_gate.edge(result, "nfl")') < nfl.index("# ONE MOST LIKELY BOARD")
    assert nfl.count("_ideas.attach(") == 1
    cfb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert cfb.index('_ideas.attach("cfb"') < cfb.index('_gate.edge(out, "cfb")')
    board = (ROOT / "engine" / "likelyboard.py").read_text(encoding="utf-8")
    assert board.index("_gate.most_likely([pool[k] for k in order], sport)") < board.index('checks["model"] = prob >= bar')
    assert 'if r.get("idea_hold"):' in board and "one vote per opinion" in board
    usage = (ROOT / "engine" / "nflusage.py").read_text(encoding="utf-8")
    assert "ratio = _role_ratio(opp, shares)" in usage
    assert ID.LAST is not None and "LAST[sport] = data" in (ROOT / "engine" / "ideas.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
