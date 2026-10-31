"""A game in progress shows its live line, never the board's zeros.

Ethan, 2026-09-24, on a live Marlins @ Cubs card reading "−0.0 / +0.0",
"0 / 0" and "O 8.5 / U 8.5": "on live games we are not displaying the
live lines here. Fix that." Three causes, three fixes:

* the book takes its pre-game prices down at first pitch, so the board
  carried a live game's run line and moneyline at their not-offered zero
  and its total at the 8.5 default, and the card printed them as prices;
* the live market the in-play pull records only reached the page as a
  CHART, after three distinct prices — a card needs one;
* that pull rode only on the full prop pull, which the pacer rations to a
  few a day, so most of every game had no live quote at all.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import livelines as ll                      # noqa: E402
from engine import oddsbudget                           # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
LAUNCH = (ROOT / "launch.py").read_text(encoding="utf-8")
MLB_BUILD = (ROOT / "mlb_build.py").read_text(encoding="utf-8")
PIPE = (ROOT / "engine" / "mlb" / "pipeline.py").read_text(encoding="utf-8")


def _row(ts, p_home, spread=None, total=None, home="CHC", away="MIA", **kw):
    r = {"ts": ts, "sport": "mlb", "home": home, "away": away, "p_home": p_home,
         "books": 5, "home_odds": kw.get("home_odds", -150), "away_odds": kw.get("away_odds", 130)}
    if spread is not None:
        r["spread"] = spread
    if total is not None:
        r["total"] = total
    return r


# --- the engine ---------------------------------------------------------------
def test_the_newest_quote_is_the_raw_newest_row():
    # The win probability did not move between the last two pulls, but the
    # total did: `series` would keep the first of the pair and its 8.5.
    rows = [_row(100, 0.60, -1.5, 8.5), _row(200, 0.62, -1.5, 8.5),
            _row(300, 0.62, -1.5, 7.5, home_odds=-160, away_odds=140)]
    got = ll.latest_for(rows, "CHC", "MIA", "mlb")
    assert got == {"ts": 300, "books": 5, "home_ml": -160, "away_ml": 140,
                   "spread": -1.5, "total": 7.5}, got
    assert ll.latest_for(rows, "CHC", "MIA", "mlb", since=400) is None, "an earlier night never answers"
    assert ll.latest_for(rows, "NYY", "BOS", "mlb") is None


def test_one_pull_is_enough_for_the_card_and_the_chart_still_waits():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "live_lines.jsonl"
        ll.record([_row(time.time(), 0.61, -1.5, 7.5)], path)
        games = [{"home": "CHC", "away": "MIA", "live": {"state": "live"}},
                 {"home": "NYM", "away": "TEX", "live": {"state": "pre"}}]
        n = ll.attach(games, "mlb", path=path)
    assert n == 0, "one price is not a chart"
    assert "line_track" not in games[0]
    assert games[0]["live_line"]["total"] == 7.5 and games[0]["live_line"]["home_ml"] == -150
    assert "live_line" not in games[1], "only a game under way wears a live line"


def test_the_mlb_board_says_whether_a_book_posted_its_numbers():
    assert '"spread_posted": bool(getattr(g, "spread_is_posted", True)),' in PIPE
    assert '"total_posted": bool(getattr(g, "total_is_posted", True)),' in PIPE


# --- the pull and its budget lane ---------------------------------------------
def test_the_build_pulls_on_the_prop_pull_or_its_own_lane():
    assert 'ap.add_argument("--live-lines", action="store_true",' in MLB_BUILD
    assert "if _live_games and (args.odds or args.live_lines):" in MLB_BUILD


def test_the_lane_spends_baseballs_money_on_its_own_clock():
    assert 'MLB_LINES_CLOCK = "mlb_lines"' in LAUNCH
    assert oddsbudget.budget_sport("mlb_lines") == "mlb"


def test_the_launcher_asks_the_pacer_and_confirms_the_pull():
    i = LAUNCH.index("def refresh_mlb(")
    fn = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    ask = fn.index('args.append("--live-lines")')
    gate = fn[fn.rindex("if ", 0, ask):ask]
    assert "_live_lines_due(out)" in gate
    assert "_odds_affordable(" in gate and "sport=MLB_LINES_CLOCK" in gate and "credits=BOARD_ODDS_COST" in gate
    assert fn.index('args.append("--cached-odds")') < ask, "only when the full pull was declined"
    assert '_finish_paid_pull(live_spend, live_before, ok, tail, "MLB live lines",' in fn
    assert "sport=MLB_LINES_CLOCK)" in fn[fn.index("_finish_paid_pull(live_spend"):]


def test_basketball_has_the_same_lane():
    """2026-09-25, before NBA opening night: the NBA and WNBA builds pulled
    the live line only with their full odds pull — baseball's gap."""
    nba = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert 'ap.add_argument("--live-lines", action="store_true",' in nba
    assert "if _live_games and (args.odds or args.live_lines):" in nba
    for league, clock, out in (("nba", "NBA_LINES_CLOCK", "NBA_OUT"), ("wnba", "WNBA_LINES_CLOCK", "WNBA_OUT")):
        assert f'{clock} = "{league}_lines"' in LAUNCH
        assert oddsbudget.budget_sport(f"{league}_lines") == league
        i = LAUNCH.index(f"def refresh_{league}(")
        fn = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
        ask = fn.index('args.append("--live-lines")')
        gate = fn[fn.rindex("if ", 0, ask):ask]
        assert f"_live_lines_due({out})" in gate and f"sport={clock}" in gate, league
        assert "credits=BOARD_ODDS_COST" in gate
        assert fn.index('args.append("--cached-odds")') < ask, "only when the full pull was declined"
        assert f"sport={clock})" in fn[fn.index("_finish_paid_pull(live_spend"):], league


def test_the_lane_is_due_only_with_a_game_under_way_and_the_cadence_round():
    import launch
    calls = []
    real_aff, real_last = ll.affordable, ll.last_pull_ts
    ll.last_pull_ts = lambda path=None: 0.0
    try:
        with tempfile.TemporaryDirectory() as d:
            quiet = Path(d) / "quiet.json"
            quiet.write_text(json.dumps({"games": [{"live": {"state": "pre"}}]}))
            busy = Path(d) / "busy.json"
            busy.write_text(json.dumps({"games": [{"live": {"state": "live"}}]}))
            ll.affordable = lambda last, now=None, gap=None: calls.append(last) or True
            assert launch._live_lines_due(str(quiet)) is False
            assert calls == [], "no game under way: the cadence is not even asked"
            assert launch._live_lines_due(str(busy)) is True
            ll.affordable = lambda last, now=None, gap=None: False
            assert launch._live_lines_due(str(busy)) is False, "too soon since the last pull"
            assert launch._live_lines_due(str(Path(d) / "missing.json")) is False
    finally:
        ll.affordable, ll.last_pull_ts = real_aff, real_last


# --- the card -------------------------------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = "\n".join(["const tzTime = (ms) => new Date(ms).toISOString().slice(11, 16);", _const("MINUS"), _const("RE_SIGN"), _const("trueMinus"), _const("american"),
                      _fn("escapeHtml"), _const("LIVE_LINE_MAX_AGE_S"), _fn("liveLineOf"),
                      _fn("liveLineTitle"), _fn("gameMarketsHTML"),
                      f"console.log(JSON.stringify((() => {{ {js} }})()));"])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_card_prints_the_live_line_and_never_a_zero():
    got = _node("""
      const now = 1790000000000, ts = now / 1000;
      const zeros = { away: "MIA", home: "CHC", live: { state: "live" }, spread: 0, away_ml: 0, home_ml: 0,
                      total: 8.5, spread_posted: false, total_posted: false };
      const cells = (h) => [...h.matchAll(/<b>([^<]*)<\\/b>/g)].map((m) => m[1]);
      const live = gameMarketsHTML({ ...zeros, live_line: { ts: ts - 240, books: 6, home_ml: -310, away_ml: 250,
                                                             spread: -1.5, total: 7.5 } }, { mlb: true, nowMs: now });
      const stale = gameMarketsHTML({ ...zeros, live_line: { ts: ts - 3600, home_ml: -310, away_ml: 250,
                                                              spread: -1.5, total: 7.5 } }, { mlb: true, nowMs: now });
      const none = gameMarketsHTML(zeros, { mlb: true, nowMs: now });
      const pre = gameMarketsHTML({ away: "BUF", home: "KC", live: { state: "live" }, spread: -2.5, total: 47,
                                    away_ml: 125, home_ml: -145 }, { nowMs: now });
      const noMl = gameMarketsHTML({ away: "NYY", home: "BOS", spread: -1.5, total: 9, away_ml: 0, home_ml: 0 }, { mlb: true });
      const filler = gameMarketsHTML({ away: "NYY", home: "BOS", spread: 0, total: 8.5, away_ml: 120, home_ml: -140,
                                       spread_posted: false, total_posted: false }, { mlb: true });
      return { live: cells(live), liveTag: /class="gc-mk-tag is-live"[^>]*>Live</.test(live),
               liveRow: live.includes('class="gc-mkts is-live"'), stale, none, pre: cells(pre),
               preTag: pre.includes(">Pregame</i>"), noMl: cells(noMl), filler: cells(filler) };""")
    if got is None:
        print("  SKIP node not installed")
        return
    assert got["live"] == ["MIA", "CHC", "+1.5", "−1.5", "+250", "−310", "O 7.5", "U 7.5"], got["live"]
    assert got["liveTag"] and got["liveRow"]
    assert got["stale"] == '<p class="gc-mkts-none">No live line yet</p>', "an hour-old quote is not shown"
    assert got["none"] == got["stale"], "the zeros never print as prices"
    assert got["pre"] == ["BUF", "KC", "+2.5", "−2.5", "+125", "−145", "O 47.0", "U 47.0"] and got["preTag"], \
        "with no live quote, the pre-game numbers say they are pre-game"
    assert got["noMl"][4:6] == ["—", "—"], "a zero moneyline is not offered, in any state"
    assert got["filler"][2:4] == ["—", "—"] and got["filler"][6:] == ["—", "—"], got["filler"]


def test_the_tag_is_styled_and_the_card_waits_for_nothing_under_way():
    assert ".gc-mk-teams .gc-mk-tag.is-live { color: var(--brand); }" in CSS
    assert ".gc-mkts-none {" in CSS
    i = APP.index("function gameCard(")
    card = APP[i:APP.index("\n}\n", i)]
    assert 'const inPlay = (g.live || {}).state === "live";' in card
    assert '"line not posted yet"' in card and "mkts || inPlay" in card


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
