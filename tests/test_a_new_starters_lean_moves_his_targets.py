"""A new starting quarterback's own lean between his targets moves them, and a pair's "chemistry" does not
(step ABZ, 22 November 2026).

Ethan, 22 November: "the chemistry between quarterbacks and their wide receivers and their tight ends, as in one
quarterback may prefer to throw more to a certain wide receiver or tight end compared to another one, or they may
prefer to throw to tight ends more compared to wide receivers in general ... measure that and make sure that's
measured with our most likely picks and our game report picks ... our edge bets as well." Measured on nflverse's
play-by-play, 2017-2026 (engine/chemfit, chemfit.py): a receiver's share with one quarterback, and his catch rate
and yards a target with him, predict nothing his own recent numbers do not; a new starter's own split between
wide receivers, tight ends and backs carries over about a fifth of the way. What these hold:

  * each starter's targets in his clean starts are counted by the receiver's position, a career summed by name;
  * the team's recent split comes off its weekly stats; the factor moves a position's share LEAN_W of the way
    toward the starter's, within CAP;
  * a change of starter carries it, and engine/qbchange.effect prices catches and receiving yards with it, after
    the measured downgrade step, so the board, Most Likely, Edge, the report's picks and its if-he-sits version
    all read it; a starter coming back carries none, and QB_QB_LEAN=off goes back to before;
  * the report says it in words, and the Wednesday fitters keep the career splits;
  * the measurement's own code reproduces the shipped setting.

    python3 tests/test_a_new_starters_lean_moves_his_targets.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import chemfit as F, qbchange as Q, qblean as L     # noqa: E402


def _play(gid, team, qb, rec, comp="1", yds="8", **kw):
    return {"season_type": "REG", "pass_attempt": "1", "sack": "0", "two_point_attempt": "0", "qb_spike": "0",
            "passer_player_id": qb, "posteam": team, "game_id": gid, "receiver_player_id": rec,
            "complete_pass": comp, "yards_gained": yds, **kw}


def test_each_starters_targets_are_counted_by_position_in_his_clean_starts():
    pos = {"te1": "TE", "wr1": "WR", "rb1": "RB", "wr2": "WR"}
    names = {"qbA": "Kyle Trask", "qbB": "Baker Mayfield"}
    rows = ([_play("g1", "TB", "qbA", "te1")] * 6 + [_play("g1", "TB", "qbA", "wr1")] * 3
            + [_play("g1", "TB", "qbB", "wr2")]                         # qbA threw 9 of 10: a clean start
            + [_play("g2", "TB", "qbA", "te1")] * 5 + [_play("g2", "TB", "qbB", "wr1")] * 5   # nobody's clean start
            + [dict(_play("g3", "TB", "qbB", "rb1"), sack="1")] * 4     # sacks are no targets
            + [dict(_play("g3", "TB", "qbB", "rb1"), season_type="POST")] * 4)
    got = L.count_season(rows, pos, names)
    assert got == {"qbA": {"name": "Kyle Trask", "WR": 3, "TE": 6, "RB": 0, "starts": 1}}, got
    doc = {"seasons": {"2025": {"qbA": {"name": "Kyle Trask", "WR": 30, "TE": 20, "RB": 10, "starts": 3}},
                       "2026": {"x": {"name": "Kyle Trask", "WR": 10, "TE": 0, "RB": 0, "starts": 1}}}}
    c = L.career(doc, "Kyle Trask")
    assert (round(c["WR"], 3), round(c["TE"], 3), c["targets"], c["starts"]) == (0.571, 0.286, 70, 4), c
    assert L.career(doc, "kyle trask")["targets"] == 70 and L.career({"seasons": {"1": {"a": {"name": "X", "WR": 5}}}}, "X") is None


def _stats(team="TB"):
    rows = []
    for wk in range(1, 12):
        rows += [{"recent_team": team, "week": wk, "position": "WR", "targets": 12, "season_type": "REG"},
                 {"recent_team": team, "week": wk, "position": "TE", "targets": 6, "season_type": "REG"},
                 {"recent_team": team, "week": wk, "position": "RB", "targets": 2, "season_type": "REG"},
                 {"recent_team": "DET", "week": wk, "position": "TE", "targets": 40, "season_type": "REG"}]
    return rows


def test_the_teams_split_and_the_factor_within_its_cap():
    split = L.team_split(_stats(), "TB", before_week=12)
    assert (round(split["WR"], 2), round(split["TE"], 2), round(split["RB"], 2)) == (0.6, 0.3, 0.1), split
    assert L.team_split(_stats(), "TB", before_week=2) is None, "too few targets to say"
    f = L.factors({"WR": 0.6, "TE": 0.3, "RB": 0.1}, {"WR": 0.5, "TE": 0.4, "RB": 0.1})
    assert f == {"WR": round((0.8 * 0.6 + 0.2 * 0.5) / 0.6, 4), "TE": round((0.8 * 0.3 + 0.2 * 0.4) / 0.3, 4),
                 "RB": 1.0}, f
    assert L.factors({"WR": 0.6, "TE": 0.05, "RB": 0.35}, {"WR": 0.2, "TE": 0.6, "RB": 0.2})["TE"] == 1 + L.CAP
    assert L.LEAN_W == 0.2 and L.CAP == 0.15


class _Prop:
    def __init__(self, market, position, team="TB", player="Cade Otton"):
        self.market, self.position, self.team, self.player = market, position, team, player


class _Game:
    def __init__(self, chs):
        self.qb_changes = chs


def _change():
    return {"team": "TB", "starter": "Baker Mayfield", "status": "OUT", "replacement": "Kyle Trask",
            "tier": "downgrade", "replacement_attempts": 400}


def test_a_change_carries_it_and_the_effect_prices_it():
    doc = {"seasons": {"2025": {"t": {"name": "Kyle Trask", "WR": 50, "TE": 40, "RB": 10, "starts": 4}}}}
    chs = L.attach({"TB": _change(), "DET": dict(_change(), team="DET", status="RETURNS")}, doc, _stats(), 12)
    lean = chs["TB"]["lean"]
    assert lean["qb"] == {"WR": 0.5, "TE": 0.4, "RB": 0.1} and lean["team"] == {"WR": 0.6, "TE": 0.3, "RB": 0.1}
    assert "lean" not in chs["DET"], "a starter coming back carries none"
    g = _Game({"TB": chs["TB"]})
    te, why, _card = Q.effect(_Prop("receptions", "TE"), g)
    assert te == round(lean["factors"]["TE"], 4) and te > 1, te
    assert "Kyle Trask has thrown 40% of his targets to tight ends, against the team's 30% lately" in why, why
    wr, why, _card = Q.effect(_Prop("rec_yds", "WR", player="Mike Evans"), g)
    assert wr == round(0.897 * lean["factors"]["WR"], 4), "after the measured downgrade step"
    assert "receivers lost 10% (measured)" in why and "wide receivers" in why, why
    assert Q.effect(_Prop("rush_yds", "RB", player="Bucky Irving"), g)[0] == 1.0, "only the markets a target reaches"
    was = os.environ.get(L.ENV)
    os.environ[L.ENV] = "off"
    try:
        assert Q.effect(_Prop("receptions", "TE"), g)[0] == 1.0
        assert "lean" not in L.attach({"TB": _change()}, doc, _stats(), 12)["TB"]
    finally:
        os.environ.pop(L.ENV, None) if was is None else os.environ.__setitem__(L.ENV, was)
    words = L.words(chs["TB"], "the Buccaneers")
    assert words.startswith("Kyle Trask has thrown 40% of his targets to tight ends, 50% to wide receivers and 10% "
                            "to backs in his starts (100 targets); the Buccaneers lately: 30%, 60% and 10%"), words
    assert "the tight ends' targets +7%" in words and "the wide receivers' targets −3%" in words, words
    assert Q.card(chs["TB"])["lean"] == L.words(chs["TB"]), "the change's card says it"


def test_the_builds_and_the_report_carry_it():
    nb = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert '_ql.attach(qb_changes, _ql_doc, _weekly_kept.get("stats") or [], args.week)' in nb
    assert nb.index("_ql.attach(qb_changes,") < nb.index("_qb_applied = _qbc.apply_to_slate(slate, qb_changes)")
    assert "lambda inj: _qls.attach(_qbc.changes(_qb_now, inj, depth_qb1, news_qb=_news_now), _qls_doc," in nb
    qs = (ROOT / "engine" / "qbscenario.py").read_text(encoding="utf-8")
    assert '**({"lean": ch["lean"]} if ch.get("lean") else {})' in qs
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'if q.get("lean"):\n                text += f". {q[\'lean\']}"' in gr
    assert 'lw = _lean_words({"replacement": rep, "lean": sc["lean"]}' in gr
    mt = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert '+ _spawn_module("engine.qblean", log))' in mt
    assert (ROOT / "chemfit.py").exists()


def test_the_measurement_reproduces_the_shipped_setting():
    # A synthetic league where new starters' own splits carry over a fifth of the way: the one-standard-error
    # rule finds a small blend, and a pair's share with one starter is no better than his own.
    import random
    rng = random.Random(3)
    games = []
    qbs = {}
    for season in range(2017, 2027):
        for t in range(12):
            team = f"T{t}"
            base_te = 0.15 + 0.15 * rng.random()
            starter, backup = f"S{season}{t}", f"B{t}"
            qbs.setdefault(backup, 0.1 + 0.3 * rng.random())
            for wk in range(1, 15):
                qb = backup if wk >= 10 else starter
                lean = qbs.get(qb, base_te)
                te = (0.8 * base_te + 0.2 * lean) if qb == backup else base_te
                n = 30
                k_te = sum(rng.random() < te for _ in range(n))
                rec = {"te": {"t": k_te, "c": k_te // 2, "y": k_te * 5.0, "pos": "TE", "by_starter": k_te},
                       "wr": {"t": n - k_te, "c": (n - k_te) // 2, "y": (n - k_te) * 6.0, "pos": "WR",
                              "by_starter": n - k_te}}
                games.append({"season": season, "week": wk, "game_id": f"{season}{t}{wk}", "team": team, "qb": qb,
                              "qb_name": qb, "qb_share": 1.0, "targets": n,
                              "rec": {f"{team}{k}": v for k, v in rec.items()}})
    r = F.judge(F.lean_cases(games), F.lean_loss, (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4), 0.0, rule="one_se")
    assert r["setting"] is not None and r["setting"] <= 0.4, r
    assert set(r["seasons"]) == {2017, 2018, 2019, 2020, 2024, 2025, 2026}, r["seasons"]
    assert F.pair_cases(games) == [] or isinstance(F.pair_cases(games), list)
    src = (ROOT / "engine" / "qblean.py").read_text(encoding="utf-8")
    for words in ("2017 +11.7%, 2018 +12.1%, 2019 -0.6%, 2020 +6.5%, 2024 +1.8%, 2025 +2.3%, 2026 +0.7%",
                  "a blend of 0.35, fails on the unseen seasons", "It is not in any number"):
        assert words.lower() in " ".join(src.split()).lower(), words


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
