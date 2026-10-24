"""A game a player left hurt stays in the number and is named on the page.

Ethan, 2026-09-23, Garrett Wilson UNDER 79.5 receiving yards beside a
Lions defence ranked softest: "why is it offering an under prop … confirm
model is reading data right". His chart showed a 0 vs CLE — week 10 last
season, a knee, 19 snaps (39%) — counted as a full game, and nothing said
so. The page also showed 79.5 as THE line when it is the highest number
any book posts (odds.best_under_line: an under takes the most cushion,
the −233 pays for it) with the market's centre near 65, and a matchup card
reading "1st-most over 2 games" beside a +5% the card never explained.

MEASURED FIRST (2022-2025, snap counts joined to the box scores, a game
under half the player's own median share counted as partial):

    share of later outcomes ABOVE the projection
                        partial game IN     partial game OUT
    rec_yds   n 887          .50                 .46
    receptions n 1142        .52                 .48
    rush_yds  n 255          .49                 .45
    the very next game (return): rec_yds .47 / .38, receptions .54 / .43

The blend is centred WITH the partial game in and runs high without it —
a game a player left hurt predicts a quieter stretch. So the number keeps
it and the display names it: snap share on every log, a hollow bar on the
chart, "left early" on the log row and in the cooling-off line, and the
shopped-number and blend notes beside the two numbers that looked wrong.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import GameLog, Prop, SportsbookLine, Game, Weather, Team, DefenseProfile, REC_YDS  # noqa: E402
from engine.sources import nflverse as N                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()


def _logs():
    # Wilson's nine, newest first: two 2026 games, then 2025 carried in.
    vals = [(2, "GB", 57.0, False), (1, "TEN", 79.0, False), (10, "CLE", 0.0, True), (6, "DEN", 13.0, True),
            (5, "DAL", 71.0, True), (4, "MIA", 82.0, True), (3, "TB", 84.0, True), (2, "BUF", 50.0, True),
            (1, "PIT", 95.0, True)]
    return [GameLog(week=w, opponent=o, value=v, prior=p) for w, o, v, p in vals]


def _table():
    t = {("garrett wilson", 2026, 1): 0.96, ("garrett wilson", 2026, 2): 0.93}
    for w, pct in ((1, 1.0), (2, 0.94), (3, 1.0), (4, 0.98), (5, 0.94), (6, 0.84), (10, 0.39)):
        t[("garrett wilson", 2025, w)] = pct
    return t


def test_the_game_he_left_is_flagged_and_the_others_are_not():
    logs = _logs()
    N.stamp_snaps(logs, "Garrett Wilson", 2026, _table())
    assert [g.partial for g in logs] == [False, False, True, False, False, False, False, False, False]
    assert logs[2].snaps == 0.39 and logs[0].snaps == 0.93 and logs[3].snaps == 0.84, "84% is a full game"
    assert N.PARTIAL_SHARE == 0.5
    back = [GameLog(week=w, opponent="x", value=10.0) for w in (1, 2, 3)]
    N.stamp_snaps(back, "Committee Back", 2026, {("committee back", 2026, w): s for w, s in ((1, .3), (2, .1), (3, .35))})
    assert not any(g.partial for g in back), "a player whose usual share is under half has no partial games"
    N.stamp_snaps(logs, "Garrett Wilson", 2026, {})
    assert [g.partial for g in logs] == [False, False, True, False, False, False, False, False, False], "no table: untouched"


def test_it_stays_in_the_number_and_the_cooling_off_line_names_it():
    from engine.projection import build_projection
    logs = _logs()
    N.stamp_snaps(logs, "Garrett Wilson", 2026, _table())
    p = Prop(player="Garrett Wilson", team="NYJ", opponent="DET", position="WR", market=REC_YDS, logs=logs,
             career_avg=59.0, vs_opponent_avg=None, lines=[SportsbookLine("proxy", 58.5, -110, -110)], usage_role="wr1")
    pr = build_projection(p, Game(home="DET", away="NYJ", weather=Weather(dome=True)),
                          Team(abbr="DET", name="DET", defense=DefenseProfile(team="DET")))
    assert pr.form.sample_games == 9, "the partial game is still a game in the blend"
    cool = [x for x in pr.reasons if x.startswith("Cooling off")]
    assert cool == ["Cooling off — last 3 games -20 vs prior form (one of them a game he left early, 39% of the snaps)"], cool
    assert pr.chain["steps"][[s["key"] for s in pr.chain["steps"]].index("trend")]["mult"] == 1.0


def test_the_board_row_and_the_build_carry_it():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert '**({"snaps": round(float(g.snaps), 2)} if getattr(g, "snaps", None) is not None else {})' in src
    assert '**({"partial": True} if getattr(g, "partial", False) else {})' in src
    build = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    body = build[build.index("def build_slate("):]
    assert "snaps = snap_table(season, season - 1 if carry else None)" in body
    assert "stamp_snaps(logs, spec.player, season, snaps)" in body and "stamp_snaps(td_logs, p.player, season, snaps)" in body


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_the_chart_draws_the_game_hollow_and_counts_it():
    logs = [{"week": w, "opponent": o, "value": v, **({"partial": True, "snaps": .39} if o == "CLE" else {})}
            for w, o, v in ((2, "GB", 57), (1, "TEN", 79), (10, "CLE", 0), (6, "DEN", 13), (5, "DAL", 71))]
    row = {"player": "Garrett Wilson", "market": "rec_yds", "market_label": "Receiving Yards", "side": "UNDER",
           "line": 79.5, "odds": -233, "recent_values": [g["value"] for g in logs], "logs": logs}
    got = _node(_fn(APP, "escapeHtml") + _fn(VIS, "escapeAttr") + _fn(VIS, "propAnalysis")
                + f"\nconsole.log(JSON.stringify(propAnalysis({json.dumps(row)})));")
    if got is None:
        print("  SKIP node not installed")
        return
    assert "LAST 5 GAMES vs PROP LINE · 1 LEFT EARLY" in got
    assert got.count('stroke-dasharray="3 2"') == 1 and "left early (39% of snaps)" in got
    assert "5 / 5" in got, "the game still counts: the under settled on it"


def test_the_log_row_and_the_shopped_number_say_it():
    row = {"side": "UNDER", "line": 79.5, "odds": -233,
           "all_lines": [{"book": "DraftKings", "line": l} for l in (59.5, 64.5, 64.5, 69.5, 79.5)]}
    logs = [{"week": 10, "opponent": "CLE", "value": 0, "partial": True, "snaps": 0.39, "home": True},
            {"week": 6, "opponent": "DEN", "value": 13, "home": True}]
    prog = (_fn(APP, "escapeHtml") + "const oddsTxt = (o) => (o > 0 ? '+' : '') + o;\n"
            + _fn(APP, "shoppedLineNote") + _fn(APP, "propLogRows")
            + "\nconst state = {sport: 'nfl'};\n"
            + f"console.log(JSON.stringify([shoppedLineNote({json.dumps(row)}), propLogRows({json.dumps(row)}, {json.dumps(logs)}, 79.5, false, 5),"
              f" shoppedLineNote({json.dumps(dict(row, line=64.5))})]));")
    got = _node(prog)
    if got is None:
        print("  SKIP node not installed")
        return
    note, rows, centre = got
    assert "under at 79.5, the highest number any book posts (-233); the market’s centre is 64.5" in " ".join(note.split())
    assert "left early · 39% of snaps" in rows and rows.count("pp-log") == 2
    assert centre == "", "at the market's centre there is nothing to say"
    # `v` is the pick the page shows — the row itself on the edge board's
    # page, the Most Likely row's own line when opened from that board.
    # A bet opened from the Live tab was placed at its number, not shopped
    # on tonight's board, so it carries no shop note (2026-09-25).
    assert 'lk && lk.bet ? "" : shoppedLineNote(v)' in APP


def test_the_matchup_card_explains_a_two_game_rating():
    from engine import defensevs as DV
    rating = {"qb_pass_yds": {"pg": 329.0, "league": 220.0, "raw": 1.49, "factor": 1.07, "games": 2, "rank": 2, "of": 32},
              "wr_rec_yds": {"pg": 218.5, "league": 146.4, "raw": 1.49, "factor": 1.07, "games": 2, "rank": 1, "of": 32},
              "wr_td": {"pg": 1.0, "league": 1.0, "raw": 1.0, "factor": 1.0, "games": 2, "rank": 14, "of": 32}}
    mult, _why, card = DV.effect("DET", rating, "WR", "rec_yds")
    assert card["rank"] == 1 and card["model"]["games"] == 2 and card["model"]["season_weight"] == 0.14
    assert 0 < card["model"]["strength"] <= 1 and card["model"]["applied"] == round(mult, 3)
    got = _node(_fn(APP, "escapeHtml") + "const MU_EDGE = 6; const muNum = (x) => String(x); const muOrd = (x) => x + 'th';\n"
                + _fn(APP, "matchupCardHTML") + f"\nconsole.log(JSON.stringify(matchupCardHTML({json.dumps({'side': 'UNDER', 'matchup_card': card})})));")
    if got is None:
        print("  SKIP node not installed")
        return
    assert "after 2 games, 14% of that rating is this season and the rest is last season’s, at the measured pull" in " ".join(got.split())


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
