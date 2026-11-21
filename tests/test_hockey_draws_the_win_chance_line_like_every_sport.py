"""Hockey's live game page draws the win chance through the game, as every other sport's does (step AAZ,
21 November 2026).

Ethan, 2026-11-21: "go into every page and make sure everything is matching. All the live pages are
matching ... everything's laid out the same visually." Read side by side on the day's live games, one
card differed: the line through the game (detail.js pbpWinChartHTML) is drawn from the chance the feed
gives after each play, which ESPN gives in football and basketball and not in hockey, so a hockey game
showed only our number now, as two bars titled "Win probability", where every other sport showed the
line titled "Win chance". The live build now gives each hockey play our own chance after it
(engine/livewp.play_chances, `our_wp`: the score and the clock against the league's scoring rate, the
bars' own number), and the page draws the same line from it, saying it is ours. The bars stand down
when the line is ours (they would say the same number twice), and while the game is on the line ends
on the scoreboard's own reading, since the feed's plays can trail the score by a play or two.

    python3 tests/test_hockey_draws_the_win_chance_line_like_every_sport.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import livewp                       # noqa: E402

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
BUILD = (ROOT / "livescore_build.py").read_text(encoding="utf-8")


def _play(period, clock, home, away, **kw):
    return {"kind": "hockey", "period": period, "clock": clock, "home_score": home, "away_score": away, **kw}


def test_each_hockey_play_gets_our_chance_after_it_on_a_clock_that_counts_up():
    plays = [_play(1, "0:00", 0, 0), _play(2, "10:00", 1, 0), _play(3, "19:30", 1, 0), _play(3, "19:30", 1, 1),
             _play(4, "2:00", 2, 1), _play(1, "", 0, 0), _play(1, "25:00", 0, 0), _play(None, "1:00", 0, 0),
             _play(2, "5:00", None, 0), "not a play"]
    assert livewp.play_chances(plays, "nhl") == 4
    want = [livewp.hockey_win_prob(0, 3600), livewp.hockey_win_prob(1, 1800), livewp.hockey_win_prob(1, 30),
            livewp.hockey_win_prob(0, 30)]
    assert [p["our_wp"] for p in plays[:4]] == [round(100 * w, 1) for w in want], plays[:4]
    # The period's clock counts UP: ten minutes into the second is half the game to play, and thirty seconds
    # left in the third with a one-goal lead is nearly won.
    assert 50 < plays[0]["our_wp"] < 56 and plays[1]["our_wp"] < plays[2]["our_wp"] and plays[2]["our_wp"] > 95
    assert 45 < plays[3]["our_wp"] < 55, "tied late: overtime's split"
    assert all("our_wp" not in p for p in plays[4:9]), "overtime, an unreadable clock or score: no reading"
    assert all("wp" not in p for p in plays[:9] if isinstance(p, dict)), "never the feed's own field"


def test_a_feed_that_gives_its_own_chance_and_every_other_league_is_left_alone():
    fed = [_play(1, "0:00", 0, 0, wp=55.0), _play(1, "5:00", 0, 0)]
    assert livewp.play_chances(fed, "nhl") == 0 and "our_wp" not in fed[1]
    for lg in ("nfl", "cfb", "nba", "cbb", "mlb", "wnba"):
        rows = [_play(1, "0:00", 0, 0)]
        assert livewp.play_chances(rows, lg) == 0 and "our_wp" not in rows[0], lg
    assert livewp.play_chances(None, "nhl") == 0 and livewp.play_chances("x", "nhl") == 0
    assert livewp.OUR_WP_LEAGUES == ("nhl",)


def test_the_live_build_gives_the_plays_their_chances_and_never_stops_for_it():
    i = BUILD.index("doc[\"plays\"] = espnplays.hoops_plays(payload, league, 0, sides=sides)")
    body = BUILD[i:i + 600]
    assert "livewp.play_chances(doc[\"plays\"], league)" in body and "except Exception:" in body


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    names = ("pbpWinRows", "pbpWinIsOurs", "pbpWinChartHTML", "pbpModelWinProbHTML")

    def fn(name):
        i = DETAIL.index(f"function {name}(")
        return DETAIL[i:DETAIL.index("\n}\n", i) + 3]
    prog = f"""
      const escapeHtml = (s) => String(s); const escapeAttr = (s) => String(s);
      const WP_W = 320, WP_H = 110;
      {"".join(fn(n) for n in names)}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_hockeys_line_from_ours_and_says_so():
    got = _node("""
      const at = (m) => new Date(Date.UTC(2026, 10, 21, 20, m)).toISOString();
      const plays = [54.1, 54.0, 53.9, 53.8, 53.8].map((w, i) => ({ our_wp: w, at: at(i) }));
      const live = { state: "live", win_prob: { home: "CGY", away: "CHI", home_win_prob: 0.707, away_win_prob: 0.293,
                     basis: "score and clock against the league's scoring rate" } };
      const nhl = { home: "CGY", away: "CHI", plays, live, generated_at: at(6) };
      const fed = { home: "SYR", away: "LAF", plays: [40, 45, 50, 55, 88].map((w, i) => ({ wp: w, wpa: 0, at: at(i) })),
                    live: { state: "live" } };
      const final = { ...nhl, live: { state: "final" } };
      return { chart: pbpWinChartHTML(nhl, "nhl"), ours: pbpWinIsOurs(nhl, "nhl"),
               rows: pbpWinRows(nhl, "nhl").rows.map((r) => r.wp),
               fed: pbpWinChartHTML(fed, "cbb"), fedOurs: pbpWinIsOurs(fed, "cbb"),
               finalRows: pbpWinRows(final, "nhl").rows.map((r) => r.wp),
               few: pbpWinChartHTML({ ...nhl, plays: plays.slice(0, 3) }, "nhl"),
               bars: pbpModelWinProbHTML(nhl) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["ours"] is True and "data-wp-ours" in got["chart"]
    assert "Win chance" in got["chart"] and "CGY 71% now" in got["chart"], "the line ends on the scoreboard's reading"
    assert "Ours, from the score and the clock" in got["chart"]
    assert got["rows"] == [54.1, 54.0, 53.9, 53.8, 53.8, 70.7] and got["finalRows"] == [54.1, 54.0, 53.9, 53.8, 53.8]
    assert got["fedOurs"] is False and "data-wp-ours" not in got["fed"] and "Ours, from" not in got["fed"]
    assert "SYR 88% now" in got["fed"], "the feed's line is drawn as it was"
    assert got["few"] == "", "a handful of plays first, as ever"
    assert "Win probability" in got["bars"], "the bars themselves are unchanged where they are drawn"


def test_the_bars_stand_down_where_the_line_is_ours():
    i = DETAIL.index("function gpNowHTML(")
    now = DETAIL[i:DETAIL.index("\n}\n", i)]
    assert "const ours = pbpWinIsOurs(d, league) ? \"\" : pbpModelWinProbHTML(d);" in now
    j = DETAIL.index("function gpStatsHTML(")
    stats = DETAIL[j:DETAIL.index("\n}\n", j)]
    assert "pbpWinIsOurs(d, league) ? \"\" : pbpModelWinProbHTML(d)" in stats


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
