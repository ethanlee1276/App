"""A teammate BACK tonight: his games without him count for less.

Ethan, 2026-10-12, four outside reports on Bills @ Rams: "with Nacua
active [Adams] has only 58 yards in two games, versus 332 in the two
games Nacua missed." The teammate step moved a player when a teammate at
his position was OUT tonight and never asked the mirror question, so the
model read Adams off 26, 195, 137 and 32 yards and projected 90.5 against
a 64.5 line. engine/teammates.back divides each game a returning teammate
missed by the lift engine/matefit measured for that absence (no new
number), takes the form again, and moves the projection by the ratio —
measured held out by season (`python3 matefit.py --back`).

Two joins found on the way, both in the same step:
  * the snap file writes "D.J. Moore", every other feed "DJ Moore" — the
    two never met, so Moore ruled out would have reached nobody;
  * the snap file calls Cincinnati's backs "HB", so the Bengals had no
    running backs in the snap-ranked order at all.

Offline, on fixtures. Run directly: `python3 tests/test_a_teammate_back_is_read.py`
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import matefit as F                                   # noqa: E402
from engine import teammates as T                                 # noqa: E402
from engine.form import compute_form                              # noqa: E402
from engine.models import GameLog                                 # noqa: E402

WEEKS = (1, 2, 3, 4)


def _stat(week, name, pos, yds, rec, team="LA"):
    return {"season_type": "REG", "week": str(week), "team": team, "position": pos,
            "player_display_name": name, "targets": str(rec + 2), "receptions": str(rec),
            "receiving_yards": str(yds)}


def _snap(week, name, pos, pct, team="LA"):
    return {"game_type": "REG", "week": str(week), "team": team, "player": name,
            "position": pos, "offense_snaps": str(int(pct * 70)), "offense_pct": str(pct)}


# The Rams' receivers through week 4 of 2026, as the feeds have them:
# Nacua out weeks 2-3, Adams 26 / 195 / 137 / 32 yards around it.
ADAMS = {1: (26, 3), 2: (195, 8), 3: (137, 7), 4: (32, 4)}
STATS = ([_stat(w, "Davante Adams", "WR", *ADAMS[w]) for w in WEEKS]
         + [_stat(1, "Puka Nacua", "WR", 74, 5), _stat(4, "Puka Nacua", "WR", 125, 9)]
         + [_stat(w, "Konata Mumpfield", "WR", 20, 2) for w in WEEKS])
SNAPS = ([_snap(w, "Davante Adams", "WR", (0.54, 0.65, 0.83, 0.95)[w - 1]) for w in WEEKS]
         + [_snap(1, "Puka Nacua", "WR", 0.70), _snap(4, "Puka Nacua", "WR", 0.90)]
         + [_snap(w, "Konata Mumpfield", "WR", 0.40) for w in WEEKS])


def _form(logs, career):
    return compute_form(logs, career, None).mean


def _adams(market="rec_yds", logs=None):
    if logs is None:
        idx = 0 if market == "rec_yds" else 1
        logs = [GameLog(week=w, opponent="", value=float(ADAMS[w][idx])) for w in sorted(WEEKS, reverse=True)]
    return types.SimpleNamespace(player="Davante Adams", team="LA", position="WR", market=market, logs=logs,
                                 career_avg=sum(g.value for g in logs) / len(logs), reset_applied=False)


def _game(injuries=(), stats=STATS, snaps=SNAPS, week=5):
    d = T.depth_table(stats, {"LA"}, week, snaps)
    game = types.SimpleNamespace(home="LA", away="BUF", lineup=None)
    T.stamp(types.SimpleNamespace(games=[game], props=[]), d, list(injuries))
    return game, d


def test_the_returning_starter_is_seen_after_two_games():
    game, d = _game()
    assert [o[0] for o in d["order"]["LA|WR"]] == ["Davante Adams", "Konata Mumpfield"], \
        "the three-game order cannot see Nacua — the reason a second list exists"
    seen = d["seen"]["LA|WR"]
    assert seen[0][0] == "Puka Nacua" and seen[0][4] == [1, 4]
    assert d["weeks"]["LA"] == [1, 2, 3, 4]
    assert game.lineup["LA"]["seen"]["WR"] == seen and game.lineup["LA"]["weeks"] == [1, 2, 3, 4]


def test_adams_with_nacua_back_is_read_off_his_games_with_nacua():
    game, _d = _game()
    mult, why, card = T.effect(_adams(), game, form_mean=_form)
    eff = T.EFFECT_SNAPS
    # Week 2 was the first game Nacua missed (new), week 3 a later one (cont).
    want = [32.0, 137.0 / eff[("rec_yds", "WR", "above_cont")],
            195.0 / eff[("rec_yds", "WR", "above_new")], 26.0]
    logs = [GameLog(week=w, opponent="", value=v) for w, v in zip((4, 3, 2, 1), want)]
    raw = _adams().logs
    expect = _form(logs, sum(want) / 4) / _form(raw, sum(g.value for g in raw) / 4)
    assert abs(mult - expect) < 1e-9 and 0.8 < mult < 0.95, mult
    assert card["back"] == ["Puka Nacua"] and card["out"] == [] and card["case"] == "back"
    assert card["missed"] == [2, 3] and card["applied"] == round(mult, 3)
    assert card["headline"] == "Puka Nacua back at WR — 2 of his 4 games this season came without him"
    assert why.startswith("Teammate back: Puka Nacua back at WR") and f"×{mult:.2f}" in why
    assert card["note"] == ("Measured over four seasons: a WR's games without a teammate ahead of him run high "
                            f"(×1.10 and ×1.22), so those games are counted at that much less — applied (×{mult:.2f})")


def test_nobody_back_nothing_moves_and_the_returning_man_himself_is_untouched():
    game, _d = _game()
    nacua = types.SimpleNamespace(player="Puka Nacua", team="LA", position="WR", market="receptions",
                                  logs=[GameLog(week=4, opponent="", value=9.0), GameLog(week=1, opponent="", value=5.0)],
                                  career_avg=7.0, reset_applied=False)
    assert T.effect(nacua, game, form_mean=_form)[0] == 1.0, "he played every one of his own games"
    stats = [r for r in STATS if r["player_display_name"] != "Puka Nacua"]
    snaps = [r for r in SNAPS if r["player"] != "Puka Nacua"]
    g2, _ = _game(stats=stats, snaps=snaps)
    assert T.effect(_adams(), g2, form_mean=_form) == (1.0, "", None)


def test_somebody_out_tonight_is_the_absence_steps_question_not_this_one():
    out = types.SimpleNamespace(team="LA", player="Konata Mumpfield", status="OUT")
    game, _d = _game([out])
    mult, why, card = T.effect(_adams(), game, form_mean=_form)
    assert not (card or {}).get("back"), "no deflation while a man at his position is out"


def test_a_man_counts_as_back_only_once_he_has_played_the_last_game():
    # Nacua out weeks 3-4 instead: whether he plays tonight is not known
    # (not on a report is not playing), so his absence deflates nothing.
    stats = [r for r in STATS if r["player_display_name"] != "Puka Nacua"] + [
        _stat(1, "Puka Nacua", "WR", 74, 5), _stat(2, "Puka Nacua", "WR", 90, 7)]
    snaps = [r for r in SNAPS if r["player"] != "Puka Nacua"] + [
        _snap(1, "Puka Nacua", "WR", 0.7), _snap(2, "Puka Nacua", "WR", 0.9)]
    game, _d = _game(stats=stats, snaps=snaps)
    assert T.effect(_adams(), game, form_mean=_form) == (1.0, "", None)
    assert F.back_mates([("above", {1, 2}), ("below", {1, 2, 3, 4})], [1, 2, 3, 4]) == [("below", {1, 2, 3, 4})]


def test_absence_cases_and_the_deflation():
    cases = F.absences([1, 2, 3, 4], [("above", {1, 4})], [1, 2, 3, 4])
    assert cases == {2: ["above_new"], 3: ["above_cont"]}
    table = {("rec_yds", "WR", "above_new"): 1.25, ("rec_yds", "WR", "above_cont"): 1.1}
    assert F.deflated([26.0, 195.0, 137.0, 32.0], [1, 2, 3, 4], cases, table, "rec_yds", "WR") == \
        [26.0, 156.0, 137.0 / 1.1, 32.0]
    assert F.deflated([5.0], [2], cases, table, "receptions", "WR") == [5.0], "no shipped lift, no change"


def test_unmeasured_cells_college_and_carried_games_are_left_alone():
    game, _d = _game()
    te = types.SimpleNamespace(player="Davante Adams", team="LA", position="TE", market="receptions",
                               logs=_adams("receptions").logs, career_avg=5.5, reset_applied=False)
    assert T.back(te, game.lineup["LA"], _form) == (1.0, "", None), "a TE's catches failed the bar"
    assert ("receptions", "TE") not in T.BACK_CELLS
    college = dict(game.lineup["LA"], basis="cfb")
    assert T.back(_adams(), college, _form) == (1.0, "", None)
    # A carried game (last season's, weeks 1-3 boards) is never deflated.
    logs = _adams().logs + [GameLog(week=2, opponent="", value=60.0, prior=True)]
    mult, _why, card = T.back(_adams(logs=logs), game.lineup["LA"], _form)
    assert card and mult < 1.0 and card["missed"] == [2, 3]


def test_the_initials_meet_and_hb_is_a_back():
    assert T._norm("D.J. Moore") == T._norm("DJ Moore") == "dj moore"
    assert T._norm("D.K. Metcalf") == T._norm("DK Metcalf")
    assert T._norm("A.J. Brown") == "aj brown" and T._norm("Amon-Ra St. Brown") == "amon ra st brown"
    assert T._norm("Puka Nacua") != T._norm("Davante Adams")
    stats = [{"season_type": "REG", "week": "1", "team": "CIN", "position": "RB",
              "player_display_name": "Chase Brown", "carries": "15"}]
    snaps = [{"game_type": "REG", "week": "1", "team": "CIN", "player": "Chase Brown",
              "position": "HB", "offense_snaps": "50", "offense_pct": "0.72"}]
    games, _tw = F.games_from_snaps(stats, snaps)
    assert ("CIN", "RB", "Chase Brown") in games, "the snap file's HB is a running back"
    # Moore ruled out on a report that spells him "DJ": the order (snap file,
    # "D.J.") now sees it.
    order = [["Khalil Shakir", 0.63, 4, 4], ["Keon Coleman", 0.62, 4, 4], ["D.J. Moore", 0.52, 4, 4]]
    lu = {"order": {"WR": order}, "out": [T._norm("DJ Moore")], "maybe": [], "last": 4, "basis": "snaps",
          "seen": {"WR": []}, "weeks": [1, 2, 3, 4]}
    game = types.SimpleNamespace(home="LA", away="BUF", lineup={"BUF": lu})
    coleman = types.SimpleNamespace(player="Keon Coleman", team="BUF", position="WR", market="rec_yds",
                                    logs=[], career_avg=40.0, reset_applied=False)
    _m, _w, card = T.effect(coleman, game)
    assert card and card["out"] == ["D.J. Moore"] and card["case"] == "below_new"


def test_the_card_the_page_and_the_chain_agree():
    import json
    import shutil
    import subprocess
    import tempfile
    src = open(os.path.join(ROOT, "engine", "projection.py"), encoding="utf-8").read()
    assert "_mate_effect(prop, game, form_mean=_form_mean)" in src, "the projection hands over its own form"
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function mateCardHTML(c, titleOnly)" in js and '"Teammate back"' in js
    node = shutil.which("node")
    if node:
        def lift(name):
            f = js[js.index(f"function {name}("):]
            return f[:f.index("\n}\n") + 2]
        game, _d = _game()
        card = T.effect(_adams(), game, form_mean=_form)[2]
        prog = (lift("escapeHtml") + lift("mateCardHTML")
                + f"\nconsole.log(JSON.stringify([mateCardHTML({json.dumps(card)}), mateCardHTML({json.dumps(card)}, 1)]));")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(prog)
        try:
            out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(fh.name)
        assert out.returncode == 0, out.stderr
        html, title = json.loads(out.stdout)
        assert "Teammate back" in html and title == "Teammate back" and "Puka Nacua back at WR" in html
    ask = open(os.path.join(ROOT, "engine", "askbot.py"), encoding="utf-8").read()
    assert '"teammate_back"' in ask


def test_the_tables_are_what_the_measurement_shipped():
    """Pinned so a refit that moves them is seen (`python3 matefit.py --back`)."""
    assert T.BACK_CELLS == frozenset({("rec_yds", "RB"), ("rec_yds", "TE"), ("rec_yds", "WR"),
                                      ("receptions", "RB"), ("receptions", "WR"), ("rush_yds", "RB")})
    assert T.BACK_RESIDUAL == {("receptions", "RB", "below_back"): 0.903}
    held = {("receptions", "TE", 2022): {"raw": 10.0, "deflated": 9.0},
            ("receptions", "TE", 2023): {"raw": 10.0, "deflated": 10.1},
            ("receptions", "TE", 2025): {"raw": 10.0, "deflated": 10.2},
            ("rush_yds", "RB", 2022): {"raw": 10.0, "deflated": 9.0},
            ("rush_yds", "RB", 2023): {"raw": 10.0, "deflated": 10.05}}
    assert F.back_verdicts(held) == {("receptions", "TE"): False, ("rush_yds", "RB"): True}, \
        "two seasons the wrong way fails; one is allowed"
    fit = open(os.path.join(ROOT, "matefit.py"), encoding="utf-8").read()
    assert "--back" in fit and "BACK_CELLS" in fit and "BACK_RESIDUAL" in fit


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
