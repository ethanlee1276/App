"""Everything the NFL board reads reaches the number Most Likely shows.

Ethan, 2026-09-23: "make sure everything we pull, all the data we use is
actually being projected to the pick we are picking ... Most Likely is
number one ... if we need to say it under the card ... but we also need
our model to adjust accordingly to all the data."

Three things did not reach it, and now do:

  * A teammate out at his position (engine/teammates.py, measured by
    engine/matefit.py): the card said "Pacheco out, Hunt absorbed +11%" and
    the projection did not move. A back whose starter was just ruled out
    ran for 65% more than his own form, every season 2022-2025; that now
    moves the number, in its own "who plays around him" step.
  * A replacement quarterback's baseline averaged every appearance,
    including three-attempt relief outings, and under-projected his start
    by a third. Only games he quarterbacked count now (15+ attempts).
  * The QB-change drop sat inside the injury step, whose hand-tuned cap
    could clip it. Measured effects now sit outside the cap.

And a check that proves it on every build (inputcheck.wiring, in
`homecheck.py inputs`): base × every step = the projection shown, the
lineup step = what the cards under the pick say was applied, and each
Most Likely row's projection and probability come from its prop row.
"""
import copy
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import matefit as F                                       # noqa: E402
from engine import teammates as T                                     # noqa: E402
from engine import inputcheck as C                                    # noqa: E402
from engine.models import (Injury, Prop, SportsbookLine, GameLog, Game, Weather, Team,  # noqa: E402
                           DefenseProfile, REC_YDS, RECEPTIONS, RUSH_YDS, ANYTIME_TD, PASS_YDS)
from engine.sources import nflverse as N                              # noqa: E402


def test_the_case_is_read_from_the_depth_order():
    order = [("Starter", 18.0, 8, 9), ("Second", 9.0, 8, 9), ("Third", 3.0, 5, 6)]
    assert F.case_for(order, "Second", {"Second", "Third"}, 9) == "above_new", "the starter played last week"
    assert F.case_for(order, "Second", {"Second", "Third"}, 10) == "above_cont", "he was already out"
    assert F.case_for(order, "Starter", {"Starter", "Second"}, 9) == "below_cont"
    assert F.case_for(order, "Starter", {"Starter", "Third"}, 9) == "below_new"
    assert F.case_for(order, "Second", {"Starter", "Second", "Third"}, 9) is None, "all playing"
    assert F.case_for(order, "Someone", {"Starter"}, 9) is None, "not in the top three"


def test_the_fitter_recovers_a_known_boost():
    seasons = {}
    for season in (2022, 2023, 2024, 2025):
        rows = []
        for wk in range(1, 13):
            starter_out = wk in (7, 10)
            if not starter_out:
                rows.append({"season_type": "REG", "week": str(wk), "team": "KC", "position": "RB",
                             "player_display_name": "Starter", "carries": "18", "rushing_yards": "80"})
            rows.append({"season_type": "REG", "week": str(wk), "team": "KC", "position": "RB",
                         "player_display_name": "Backup", "carries": "12" if starter_out else "6",
                         "rushing_yards": "90" if starter_out else "45"})
        seasons[season] = rows
    res = F.measure(F.samples(seasons))
    got = res[("rush_yds", "RB", "above_new")]
    assert got["n"] == 8 and 1.9 < got["mult"] < 2.1, got


def test_what_ships_is_what_the_rule_says_on_the_box_scores():
    path = os.path.join(ROOT, "data", "cache", "player_stats_{}.csv")
    if not all(os.path.exists(path.format(s)) for s in (2022, 2023, 2024, 2025)):
        print("  SKIP box scores not in data/cache")
        return
    seasons = {}
    for s in (2022, 2023, 2024, 2025):
        with open(path.format(s), newline="") as fh:
            seasons[s] = list(csv.DictReader(fh))
    rule = F.shipped(F.measure(F.samples(seasons)))
    assert {k: round(v, 3) for k, v in rule.items()} == T.EFFECT, "re-run `python3 matefit.py` and ship what it says"
    assert not [k for k in T.EFFECT if k[0] == ANYTIME_TD], "touchdowns behind an absence measured too noisy"


def _prop(player, pos, market, team="KC"):
    return Prop(player=player, team=team, opponent="DEN", position=pos, market=market,
                logs=[GameLog(w, "x", 50.0) for w in range(1, 6)], career_avg=50.0, vs_opponent_avg=None,
                lines=[SportsbookLine("book", 49.5, -110, -110)], usage_role="rb1")


class _Slate:
    def __init__(self, props, games):
        self.props, self.games = props, games


def _slate(out, last_played=9, reset=()):
    props = [_prop("Kareem Hunt", "RB", RUSH_YDS), _prop("Kareem Hunt", "RB", ANYTIME_TD),
             _prop("Travis Kelce", "TE", RECEPTIONS), _prop("Isiah Pacheco", "RB", RUSH_YDS)]
    games = [Game(home="KC", away="DEN", weather=Weather())]
    depth = {"order": {"KC|RB": [["Isiah Pacheco", 17.0, 8, last_played], ["Kareem Hunt", 8.0, 8, 9]],
                       "KC|TE": [["Travis Kelce", 7.0, 9, 9]]},
             "last": {"KC": 9}}
    injuries = [Injury(player=n, team="KC", position="RB", role="rb1", status=s) for n, s in out]
    sl = _Slate(props, games)
    T.stamp(sl, depth, injuries, reset_players=reset)
    return sl


def test_the_teammate_out_moves_the_number_and_the_card_says_so():
    sl = _slate([("Isiah Pacheco", "OUT")])
    g = sl.games[0]
    m, why, card = T.effect(sl.props[0], g)
    assert m == 1.647 and card["case"] == "above_new" and card["applied"] == 1.647
    assert card["headline"] == "Isiah Pacheco just ruled out ahead of him at RB"
    assert why == "Teammate out: Isiah Pacheco just ruled out ahead of him at RB — measured (×1.65)"
    assert "65% more than his own form — applied" in card["note"]
    m, why, card = T.effect(sl.props[1], g)
    assert (m, why) == (1.0, "") and card["note"].startswith("Shown for you"), "a touchdown is shown, not priced"
    assert T.effect(sl.props[2], g) == (1.0, "", None), "nobody out at his position"
    assert T.effect(sl.props[3], g) == (1.0, "", None), "the man who is out"
    # QUESTIONABLE IS NOT OUT — nothing is applied — but the card says what
    # the measured effect would be if he sits (2026-09-25).
    q = _slate([("Isiah Pacheco", "QUESTIONABLE")])
    m, why, card = T.effect(q.props[0], q.games[0])
    assert (m, why, card["applied"], card["out"]) == (1.0, "", 1.0, []), "questionable is not out"
    assert card["if_sits"] == {"who": ["Isiah Pacheco"], "mult": 1.647, "case": "above_new"}
    assert card["headline"] == "Isiah Pacheco questionable at RB"
    assert card["note"].startswith("Isiah Pacheco is questionable. If he sits, our projection moves "
                                   "+65% on rushing yards"), card["note"]
    assert "goes in on its own the moment he is ruled out" in card["note"]
    assert T.effect(q.props[2], q.games[0]) == (1.0, "", None), "a questionable back is no TE's news"


def test_a_reset_sample_already_carries_a_long_absence():
    sl = _slate([("Isiah Pacheco", "IR")], last_played=5)
    assert T.effect(sl.props[0], sl.games[0])[0] == 1.337, "out for weeks: the continuing case"
    sl = _slate([("Isiah Pacheco", "IR")], last_played=5, reset=["Kareem Hunt"])
    m, why, card = T.effect(sl.props[0], sl.games[0])
    assert (m, why, card["applied"]) == (1.0, "", 1.0) and "already carry it" in card["note"]


def test_the_projection_moves_by_it_outside_the_cap_and_the_chain_adds_up():
    from engine.projection import build_projection
    opp = Team(abbr="DEN", name="DEN", defense=DefenseProfile(team="DEN"))
    base = build_projection(_prop("Kareem Hunt", "RB", RUSH_YDS), Game(home="KC", away="DEN", weather=Weather()), opp)
    sl = _slate([("Isiah Pacheco", "OUT")])
    now = build_projection(sl.props[0], sl.games[0], opp)
    assert abs(now.mean / base.mean - 1.647) < 1e-6, "past the 1.18 hand-tuned cap: it was measured"
    steps = {s["key"]: s for s in now.chain["steps"]}
    assert steps["lineup"]["mult"] == 1.647 and steps["injury"]["mult"] == 1.0
    assert now.injury.mate_card["applied"] == 1.647
    prod = now.chain["base"]["value"]
    for s in now.chain["steps"]:
        prod *= s["mult"]
    assert abs(prod - now.mean) < 0.06, "base × every step is the number"


def test_a_relief_appearance_is_not_a_quarterback_s_start():
    rows = [{"season_type": "REG", "week": str(w), "player_display_name": "Davis Mills", "attempts": a,
             "passing_yards": y, "receiving_yards": "0"}
            for w, a, y in ((1, "3", "12"), (2, "31", "240"), (3, "6", "40"), (4, "28", "205"))]
    got = N.player_game_logs(rows, "Davis Mills", PASS_YDS, 5)
    assert [g.week for g in got] == [4, 2], "three attempts in mop-up is not what he does starting"
    assert N.QB_START_ATTEMPTS == 15.0
    assert not N.quarterbacked({"attempts": "4"}, PASS_YDS) and N.quarterbacked({"attempts": "4"}, REC_YDS)
    from engine.carry import carried_logs
    assert [g.value for g in carried_logs(rows, "Davis Mills", PASS_YDS)] == [205.0, 240.0]


def _row(player, market, side, line, proj, steps, prob, **kw):
    r = {"player": player, "market": market, "side": side, "line": line, "projection": proj,
         "hit_prob": prob, "chain": {"base": {"value": 40.0}, "steps": steps}}
    r.update(kw)
    return r


def test_the_wiring_check_passes_a_good_board_and_names_every_break():
    card = {"applied": 1.647, "headline": "Isiah Pacheco just ruled out ahead of him at RB"}
    good = _row("Kareem Hunt", RUSH_YDS, "OVER", 49.5, 65.9,
                [{"key": "usage", "mult": 1.0}, {"key": "lineup", "mult": 1.647}], 0.71, mate_card=card)
    ml = {"kind": "prop", "rung": "main", "player": "Kareem Hunt", "market": RUSH_YDS, "side": "OVER",
          "line": 49.5, "main_side": "OVER", "main_line": 49.5, "projection": 65.9, "model_prob": 0.71,
          "prob_source": "model"}
    assert C.wiring({"recommendations": [good], "most_likely": [ml]}) == {"checked": 2, "bad": []}
    bad = copy.deepcopy(good)
    bad["chain"]["steps"][1]["mult"] = 1.0
    got = C.wiring({"recommendations": [bad]})["bad"]
    assert any("steps multiply to 40.00" in x for x in got) and any("×1.647 was applied" in x for x in got)
    off = dict(ml, projection=60.0, model_prob=0.60)
    got = C.wiring({"recommendations": [good], "most_likely": [off]})["bad"]
    assert any("Most Likely projects 60.0" in x for x in got) and any("its prop row says 0.710" in x for x in got)
    stray = dict(ml, player="Nobody")
    assert "no prop row behind it" in C.wiring({"recommendations": [good], "most_likely": [stray]})["bad"][0]


def test_homecheck_prints_it():
    src = open(os.path.join(ROOT, "engine", "inputcheck.py"), encoding="utf-8").read()
    assert "w = wiring(board)" in src and 'flagged += [f"{sport} wiring: {x}"' in src
    hc = open(os.path.join(ROOT, "homecheck.py"), encoding="utf-8").read()
    body = hc[hc.index("def inputs("):hc.index("CHECKS = {")]
    assert "_board(sport, full=True)" in body, "the light copy drops the chains the wiring check reads"


def test_the_rows_the_page_and_ask_carry_it():
    from engine import askbot as A
    card = {"team": "KC", "headline": "Isiah Pacheco just ruled out ahead of him at RB", "applied": 1.647,
            "note": "Measured over four seasons"}
    assert A.compact({"player": "Kareem Hunt", "mate_card": card})["teammate_out"] == \
        "Isiah Pacheco just ruled out ahead of him at RB. Measured over four seasons"
    for f in ("pipeline.py", "likely.py", "touchdowns.py", "longshots.py"):
        assert "mate_card" in open(os.path.join(ROOT, "engine", f), encoding="utf-8").read(), f
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "_mates.stamp(slate," in build
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    esc = app[app.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fn = app[app.index("function mateCardHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    prog = esc + fn + f"\nconsole.log(JSON.stringify([mateCardHTML({json.dumps(card)}), mateCardHTML(null)]));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html, none = json.loads(out.stdout)
    assert none == "" and "Teammate out" in html and "Isiah Pacheco just ruled out ahead of him at RB" in html


def test_mlb_s_coherence_step_keeps_its_chain_reaching_the_number():
    """The droplet's first full wiring run, 2026-09-23: 44 MLB rows whose
    steps multiplied to 2.70 while the row showed 2.50 — the hits / total
    bases / home runs reconcile moved the mean after the chain was built."""
    from engine import chain as CH
    ch = CH.build(2.0, "form", [CH.step("park", 1.35)], 2.70)
    CH.adjust(ch, "coherence", 2.70, 2.50, "TB kept at or above hits")
    assert ch["mean"] == 2.5 and ch["steps"][-1]["key"] == "coherence" and CH.closes(ch)
    assert CH.STEP_LABELS["coherence"]
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"), encoding="utf-8").read()
    assert '_adjust(r.chain, "coherence", r.mean, hr_new, note)' in src
    assert '_adjust(t.chain, "coherence", t.mean, tb_new, note)' in src


def test_the_tape_scores_only_the_wallets_it_needs():
    from engine import predmarket as pm
    from engine.db import connect
    conn = connect(":memory:")
    pm.store_trades(conn, [{"venue": "polymarket", "tx": f"t{i}", "ts": 1000 + i, "wallet": w, "slug": "s",
                            "title": "", "outcome": "", "side": "BUY", "price": 0.5, "size": 10, "usd": 5.0}
                           for i, w in enumerate(["a", "a", "b", "c"])])
    full = pm.wallet_history(conn)
    some = pm.wallet_history(conn, wallets=["a", "c", "zz"])
    assert some == {k: full[k] for k in ("a", "c")} and pm.wallets_seen(conn) == 3


def test_a_most_likely_row_says_why_the_model_moved_it():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "${likelyTagsHTML(r)}</span></span>" in app
    esc = app[app.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fn = app[app.index("function likelyTagsHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    rows = [{"player": "Jauan Jennings", "mate_card": {"applied": 1.107, "out": ["Ricky Pearsall"], "headline": "h"}},
            {"player": "Zach Ertz", "qb_card": {"applied": 0.912, "headline": "Stroud out"}},
            {"player": "Malik Nabers", "mate_card": {"applied": 1.0, "out": ["X"], "headline": "shown only"}},
            {"player": "Kareem Hunt", "kind": "game"}]
    held = app[app.index("function likelyHeld("):]       # the "Since" chip — test_most_likely_holds_its_picks
    held = held[:held.index("\nfunction likelyRow(")]
    prog = (esc + "const escapeAttr = escapeHtml;\nconst state = {data: {thin: {'Malik Nabers': {games: 2}}}};\n"
            + "const tzOpts = (o) => o;\nconst tzTime = (d) => String(d);\nconst wholePct = (x) => x;\n"
            + "const LIKELY_NEW_MIN = 60;\nconst cardScanRead = () => null;\n" + held + fn
            + f"\nconsole.log(JSON.stringify({json.dumps(rows)}.map(likelyTagsHTML)));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert "Pearsall out +11%" in got[0] and "ml-tag up" in got[0]
    assert "QB change −9%" in got[1] and "ml-tag down" in got[1]
    assert "out" not in got[2] and "2 games in" in got[2], "shown-only is not a chip; a thin sample is"
    assert got[3] == ""


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                        # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
