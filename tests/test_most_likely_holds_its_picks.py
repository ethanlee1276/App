"""The Most Likely board holds its picks between refreshes.

Ethan, 2026-09-24: "One thing I'm noticing for the most likely bets is
they seem too change alot so it's hard too judge what picks the models
are comfortable with."

The board had no memory: every refresh rebuilt it from nothing, and the
number a pick showed was the likeliest rung at no heavier than -250 —
the rung nearest the cap, so a five-cent tick moved the pick's line,
price and percent while the player's projection never moved. Now a pick
keeps its number while that number clears every bar at its own price,
keeps its seat unless a newcomer is HOLD_MARGIN likelier, is remembered
for HOLD_GRACE_MIN after it leaves, and says when it went up. No bar is
relaxed for a held pick. `likely_turnover` counts what each build
changed and why, and `homecheck.py hold` prints it from the box.
"""
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                               # noqa: E402

FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54},
        "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60},
        "receptions": {"zero": [-0.82, 0.48], "sigma": 0.46}}
NOW = "2026-09-27T16:00:00Z"
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _always(_market):
    return True


def _ln(book, line, over, under=0):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _row(player="A Back", ladder=None, **kw):
    """A rush-yards prop whose main number calibrates to a coin flip, so
    the ladder is where anything likely is (tests/test_likely_rungs.py)."""
    got = {"player": player, "team": "DET", "opponent": "CHI", "market": "rush_yds",
           "market_label": "rush_yds", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
           "has_market": True, "fair_prob": 0.50, "projection": 62.0, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [55, 71, 48, 66], "game_date": "2026-09-27",
           "kickoff": "2026-09-27T17:00:00Z", "hit_prob": 0.56, "raw_prob": 0.58,
           "alt_lines": ladder if ladder is not None else [
               _ln("DraftKings", 40.5, -240), _ln("FanDuel", 40.5, -230),
               _ln("DraftKings", 50.5, -160), _ln("FanDuel", 50.5, -155)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def _board(props, previous=None, now=NOW, turnover=None, limit=K.LIMIT):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    try:
        return K.build(props, sport="nfl", fits=FITS, previous=previous, now=now,
                       turnover=turnover, limit=limit)
    finally:
        K.rankable = real


def _pick(board, player="A Back"):
    got = [r for r in board if r["player"] == player]
    return got[0] if got else None


# ── the number ────────────────────────────────────────────────────────────


def test_a_held_number_stays_while_a_likelier_one_appears_beside_it():
    fresh = K.from_prop(_row(), _always, fits=FITS)
    assert (fresh["line"], fresh["book"], fresh["odds"]) == (40.5, "FanDuel", -230), \
        "with no memory the likeliest rung under the cap is the pick"
    held = K.from_prop(_row(), _always, fits=FITS, prefer=[("over", 50.5)])
    assert (held["line"], held["odds"]) == (50.5, -155), \
        "the board showed 50.5 last time and 50.5 still clears — it stays"
    assert held["model_prob"] < fresh["model_prob"], "the shown number is the held rung's own"


def test_a_held_main_line_stays_the_main_line():
    row = _row(hit_prob=0.62, raw_prob=0.62, fair_prob=0.60, line=45.5, odds=-140)
    fresh = K.from_prop(row, _always, fits=FITS)
    assert fresh["rung"] == "alt", "a likelier rung beats the main number with no memory"
    held = K.from_prop(row, _always, fits=FITS, prefer=[("over", 45.5)])
    assert (held["rung"], held["line"]) == ("main", 45.5)


def test_a_number_that_fails_a_bar_moves_then_goes_back_when_it_clears():
    capped = [_ln("DraftKings", 40.5, -260), _ln("FanDuel", 40.5, -255),
              _ln("DraftKings", 50.5, -160)]
    b0 = _board([_row()], now="2026-09-27T14:00:00Z")
    assert _pick(b0)["line"] == 40.5 and _pick(b0)["since"] == "2026-09-27T14:00:00Z"
    b1 = _board([_row(ladder=capped)], previous=b0, now="2026-09-27T14:15:00Z")
    p1 = _pick(b1)
    assert (p1["line"], p1["odds"]) == (50.5, -160), "-255 is past the cap: the bar is not relaxed"
    assert p1["since"] == "2026-09-27T14:00:00Z" and p1["first_line"] == 40.5
    b2 = _board([_row()], previous=b1, now="2026-09-27T14:30:00Z")
    p2 = _pick(b2)
    assert p2["line"] == 40.5, "back to the number it went up at, not left where the tick put it"
    assert p2["since"] == "2026-09-27T14:00:00Z" and "first_line" not in p2


# ── the seat ──────────────────────────────────────────────────────────────


def test_a_seat_is_kept_unless_the_newcomer_is_clearly_likelier():
    def rows(new_prob):
        out = [{"kind": "prop", "player": f"S{i}", "team": "T", "market": "rec_yds",
                "model_prob": 0.80 - i * 0.01} for i in range(7)]
        out.append({"kind": "prop", "player": "Held", "team": "T", "market": "rec_yds", "model_prob": 0.70})
        out.append({"kind": "prop", "player": "New", "team": "T", "market": "rec_yds", "model_prob": new_prob})
        return out
    held = {K.hold_key(r): r for r in rows(0)[:8]}
    seated = {r["player"] for r in K._cut_players(rows(0.72), 8, held=held)}
    assert "Held" in seated and "New" not in seated, "two points likelier is not enough"
    seated = {r["player"] for r in K._cut_players(rows(0.735), 8, held=held)}
    assert "New" in seated and "Held" not in seated, "three and a half points is"
    assert {r["player"] for r in K._cut_players(rows(0.72), 8)} >= {"New"}, "no memory, no margin"


# ── what the board says about itself ──────────────────────────────────────


def test_no_previous_board_is_the_order_it_always_was():
    props = [_row(player=f"P{i}", projection=55.0 + i * 3) for i in range(8)]
    board = _board(props)
    probs = [r["model_prob"] for r in board]
    assert probs == sorted(probs, reverse=True)
    assert {r["since"] for r in board} == {NOW}
    assert all(r["first_prob"] == r["model_prob"] for r in board)


def test_since_and_first_prob_ride_forward_and_a_new_pick_is_stamped_now():
    b0 = _board([_row()], now="2026-09-27T12:00:00Z")
    b1 = _board([_row(projection=64.0), _row(player="B Back")], previous=b0)
    a, b = _pick(b1), _pick(b1, "B Back")
    assert a["since"] == "2026-09-27T12:00:00Z" and a["first_prob"] == _pick(b0)["model_prob"]
    assert a["model_prob"] != a["first_prob"], "the projection moved; the row says both"
    assert b["since"] == NOW


def test_the_turnover_says_why_each_pick_left():
    prev = [
        {"kind": "prop", "player": "Kicked Off", "team": "DET", "market": "rush_yds", "side": "over",
         "line": 40.5, "model_prob": 0.7, "since": "2026-09-27T10:00:00Z", "kickoff": "2026-09-27T15:00:00Z"},
        {"kind": "prop", "player": "Gone", "team": "DET", "market": "rush_yds", "side": "over",
         "line": 40.5, "model_prob": 0.7, "since": "2026-09-27T10:00:00Z", "kickoff": "2026-09-27T20:00:00Z"},
        {"kind": "prop", "player": "Floor", "team": "DET", "market": "rush_yds", "side": "over",
         "line": 40.5, "model_prob": 0.7, "since": "2026-09-27T10:00:00Z", "kickoff": "2026-09-27T20:00:00Z"},
        {"kind": "prop", "player": "A Back", "team": "DET", "market": "rush_yds", "side": "over",
         "line": 40.5, "model_prob": 0.7, "since": "2026-09-27T10:00:00Z", "kickoff": "2026-09-27T20:00:00Z"},
    ]
    turn: dict = {}
    board = _board([_row(), _row(player="Floor", hit_prob=0.3, raw_prob=0.3, alt_lines=[]),
                    _row(player="C Back")], previous=prev, turnover=turn)
    assert _pick(board)["since"] == "2026-09-27T10:00:00Z"
    assert turn["previous"] == 4 and turn["held"] == 1 and turn["new"] == 1
    assert turn["left"] == {"its game started": 1, "no longer offered": 1,
                            "under the likelihood floor": 1}, turn["left"]
    ghosts = {g["player"]: g for g in turn["held_out"]}
    assert set(ghosts) == {"Gone", "Floor"}, "a started game is not held out"
    assert ghosts["Gone"]["out_at"] == NOW and ghosts["Gone"]["since"] == "2026-09-27T10:00:00Z"
    assert turn["day"]["builds"] == 1 and turn["day"]["held"] == 1


def test_a_pick_held_out_returns_inside_the_hour_and_not_after():
    ghost = {"kind": "prop", "player": "A Back", "team": "DET", "market": "rush_yds", "side": "over",
             "line": 50.5, "model_prob": 0.66, "since": "2026-09-27T09:00:00Z",
             "out_at": "2026-09-27T15:30:00Z", "out_why": "a likelier pick took its seat"}
    turn: dict = {}
    back = _board([_row()], previous={"rows": [ghost], "day": {"builds": 3, "new": 2}}, turnover=turn)
    p = _pick(back)
    assert p["line"] == 50.5 and p["since"] == "2026-09-27T09:00:00Z", "back at its own number"
    assert turn["came_back"] == 1 and turn["new"] == 0
    assert turn["day"]["builds"] == 4 and turn["day"]["came_back"] == 1 and turn["day"]["new"] == 2
    late = _board([_row()], previous=[dict(ghost, out_at="2026-09-27T14:30:00Z")])
    assert _pick(late)["line"] == 40.5 and _pick(late)["since"] == NOW, "an hour and a half is a new pick"


def test_the_previous_board_is_the_same_slate_or_nothing():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "held_board_fixture.json")          # not a board name: no full copy
    doc = {"date": "2026-W04", "most_likely": [{"player": "X", "market": "rush_yds"}],
           "likely_turnover": {"held_out": [{"player": "Y", "out_at": NOW}, {"player": "Z"}],
                               "day": {"builds": 5}}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    got = K.previous_board(path, "2026-W04")
    assert [r["player"] for r in got["rows"]] == ["X", "Y"] and got["day"] == {"builds": 5}
    assert K.previous_board(path, "2026-W05") == {"rows": [], "day": {}}
    assert K.previous_board(os.path.join(d, "missing.json"), "2026-W04") == {"rows": [], "day": {}}
    # The light copy first: the same rows without their chains, and the MLB
    # full board is 8 MB to parse every refresh.
    with open(os.path.join(d, "held_board_fixture_picks.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(doc, most_likely=[{"player": "L", "market": "rush_yds"}]), fh)
    assert [r["player"] for r in K.previous_board(path, "2026-W04")["rows"]] == ["L", "Y"]
    shutil.rmtree(d)


# ── the replay behind HOLD_MARGIN's comment ───────────────────────────────


def _replay(hold, seed=3, players=10, refreshes=12):
    """Props on alternate ladders at three books, rebuilt every fifteen
    minutes with every rung's price ticking; the set of (player, market,
    side, line) on each board. The comment on HOLD_MARGIN is this, larger."""
    from engine.yardagefit import display_prob
    rng = random.Random(seed)
    rows, base = [], {}
    for i in range(players):
        for market, proj, step in (("rec_yds", rng.uniform(35, 85), 5),
                                   ("rush_yds", rng.uniform(40, 90), 5),
                                   ("receptions", rng.uniform(3, 7), 1)):
            line0 = round(proj) + 0.5
            recent = [max(0, proj + rng.gauss(0, proj * .3)) for _ in range(6)]
            alts = [{"book": b, "line": line0 - step * k} for k in (4, 3, 2, 1, -1)
                    for b in ("DraftKings", "FanDuel", "BetMGM")]
            rows.append(_row(player=f"P{i}", market=market, market_label=market, line=line0,
                             projection=proj, recent_values=recent, alt_lines=alts, hit_prob=.5,
                             raw_prob=.5, kickoff=""))

    def odds(q):
        return int(round(-100 * q / (1 - q))) if q >= .5 else int(round(100 * (1 - q) / q))
    boards, prev, turn = [], None, {}
    for t in range(refreshes):
        for r in rows:
            for a in r["alt_lines"]:
                k = (r["player"], r["market"], a["line"], a["book"])
                if k not in base:
                    p = display_prob(r["market"], r["projection"], a["line"], r["recent_values"], fits=FITS)
                    base[k] = min(max((p or .5) + rng.gauss(0, .03), .05), .95)
                p = min(max(base[k] + rng.gauss(0, .012), .05), .95)
                a["over_odds"], a["under_odds"] = odds(p + .022), odds(1 - p + .022)
        turn_next: dict = {}
        b = _board(rows, previous=({"rows": prev + turn.get("held_out", []), "day": {}}
                                   if hold and prev else None),
                   now=f"2026-09-27T{10 + t // 4:02d}:{(t % 4) * 15:02d}:00Z", turnover=turn_next,
                   limit=20)
        boards.append({(r["player"], r["market"], r["side"], r["line"]) for r in b})
        prev, turn = b, turn_next
    return sum(len(boards[i] - boards[i + 1]) for i in range(len(boards) - 1)) / (len(boards) - 1)


def test_the_replay_changes_fewer_picks_between_looks():
    without, held = _replay(False), _replay(True)
    assert without > 1.0, f"the replay has to churn to test anything ({without:.1f})"
    assert held <= 0.6 * without, (held, without)


# ── the builds, the paywall, the box ──────────────────────────────────────


def test_every_build_hands_the_hold_its_last_board():
    src = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()   # noqa: E731
    assert "likely_previous=_likely_prev(args.out, slate.date)" in src("nfl_build.py")
    pipe = src("engine", "pipeline.py")
    assert "previous=likely_previous," in pipe and '"likely_turnover": _likely_turnover,' in pipe
    assert "previous=_likely_prev(args.out, result.get(\"date\"))" in src("mlb_build.py")
    assert "previous=_likely_prev(args.out, args.date), turnover=_ml_turn)" in src("nba_build.py")
    assert "previous=_likely_prev(args.out, out.get(\"date\"))," in src("cfb_build.py"), \
        "college's payload date is the build date; args.date moves to the slate"
    for f in ("mlb_build.py", "nba_build.py", "cfb_build.py"):
        assert '"likely_turnover"] = _ml_turn' in src(f), f
    from engine import gate
    assert "likely_turnover" in gate.PAID_KEYS, "held_out names picks"
    import homecheck
    assert "hold" in homecheck.CHECKS


def test_the_box_report_reads_a_board():
    board = {"date": "2026-09-27", "most_likely": [
        {"since": "2026-09-27T10:00:00Z"}, {"since": "2026-09-27T14:30:00Z"}, {"since": "2026-09-27T15:50:00Z"}],
        "likely_turnover": {"at": NOW, "held": 2, "new": 1, "held_out": [{}],
                            "day": {"builds": 24, "since": "2026-09-27T10:00:00Z", "held": 900, "new": 30,
                                    "left": {"its game started": 12, "a likelier pick took its seat": 3}}}}
    got = "\n".join(K.hold_report("mlb", board))
    assert "3 picks · 24 build(s) since 2026-09-27T10:00:00Z" in got
    assert "up 3h+: 1   1-3h: 1   under 1h: 1" in got
    assert "left: its game started 12 · a likelier pick took its seat 3" in got
    assert "built before the hold" in "\n".join(K.hold_report("nfl", {"most_likely": [{}]}))


# ── the page ──────────────────────────────────────────────────────────────


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


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


def test_the_row_says_how_long_the_pick_has_been_up():
    now = dt.datetime.now(dt.timezone.utc)
    iso = lambda m: (now - dt.timedelta(minutes=m)).isoformat(timespec="seconds")   # noqa: E731
    prog = (_fn(APP, "escapeHtml") + "const escapeAttr = escapeHtml;\n"
            + "const wholePct = (x) => `${Math.round(Number(x) * 100)}%`;\n"
            + "const tzOpts = (o) => Object.assign({timeZone: 'America/New_York'}, o);\n"
            + "const tzTime = (d) => new Date(d).toLocaleTimeString('en-US', tzOpts({hour: 'numeric', minute: '2-digit'}));\n"
            + "const state = {data: {}};\nconst LIKELY_NEW_MIN = 60;\n" + _fn(APP, "likelyHeld")
            + _fn(APP, "likelyHeldTag") + _fn(APP, "likelyTagsHTML")
            + f"\nconsole.log(JSON.stringify([{{since: '{iso(200)}', first_prob: 0.71}}, "
            + f"{{since: '{iso(10)}', kind: 'game'}}, {{}}].map(likelyTagsHTML)));")
    got = _node(prog)
    if got is None:
        print("  SKIP node not installed")
        return
    assert ">Since " in got[0] and "71% when it went up" in got[0] and "ml-tag new" not in got[0]
    assert "ml-tag new" in got[1] and ">New<" in got[1], "a game row says it too"
    assert got[2] == ""
    assert "const held = likelyHeldTag(r);" in _fn(APP, "likelyTagsHTML"), \
        "on the tag row, which a phone does not cut off"


def test_the_pick_page_says_when_it_went_up():
    body = _fn(APP, "whyLikelyHTML")
    assert 'items.push(["On the board",' in body and "const held = likelyHeld(lk);" in body
    assert "and goes back to" in body, "a moved number says it returns"
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    block = css[css.index("/* How long the board has held a Most Likely pick"):]
    block = block[:block.index("\n\n")]
    assert ".ml-tag.new" in block and "#" not in block.split("*/", 1)[1] and "px solid" not in block


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
