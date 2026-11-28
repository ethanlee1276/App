"""Walk 16's fixes (2026-11-19, step YG).

  - the race pages' opening line read "330 games played, 1005 left in the
    regular season" (WHEN_YOU_ARE_HOME, step XO, quoting the NHL's): a count
    past a thousand reads with its comma, as college's race already did
    ("1,005 left"), on the NFL's, the NBA's and the NHL's alike;
  - the Alerts page with nothing watched said twice that your things rise to
    the top ("rise to the top of this page", then "your own things rise above
    the two hundred that are not"); the second line now only says where the
    phone hears about them, and once something is watched, that it rises
    above the rest of the feed;
  - the Toolbox's strategy lab let a rule be tested on "NFL, College, MLB,
    NBA, NHL, UFC": college basketball and the WNBA were missing and
    "College" named neither college sport;
  - the prediction-market desk read no hockey slate (pm_build.SLATE_FILES),
    so Kalshi's NHL games carried no chance of ours, and the page's informed
    flow could not file a hockey trade under a league of its own.

    python3 tests/test_walk_sixteen_says_it_once.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
RACE = (JS / "race.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(prog: str):
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_race_says_its_game_counts_with_commas():
    ledes = re.findall(r'<p class="rc-note rc-lede">(?:(?!</p>).)*?left in the regular season\.</p>', RACE, re.S)
    assert len(ledes) == 2, f"the NFL's lede and the NBA's and NHL's: {len(ledes)}"
    prog = "\n".join([_fn(APP, "escapeHtml"), _fn(APP, "pluralWord"), _fn(APP, "plural")]) + f"""
      const ledes = {json.dumps(ledes)};
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const say = (src, d) => text(new Function("d", "plural", "escapeHtml", "return `" + src + "`;")(d, plural, escapeHtml));
      console.log(JSON.stringify(ledes.map((src) => [
        say(src, {{week: 12, games_played: 1336, games_left: 1005}}),
        say(src, {{week: 1, games_played: 1, games_left: 0}}),
      ])));"""
    got = _node(prog)
    if got is None:
        return
    nfl, season = got
    assert nfl[0] == "Week 12 next · 1,336 games played, 1,005 left in the regular season.", nfl[0]
    assert season[0] == "1,336 games played, 1,005 left in the regular season.", season[0]
    assert season[1] == "1 game played, 0 left in the regular season.", season[1]


def test_the_alerts_page_says_where_a_watch_rises_once():
    more = (JS / "more.js").read_text(encoding="utf-8")      # the Alerts page's file since 2026-11-19
    i = more.index("async function renderWatchZone(")
    body = more[i:more.index("\n/* THE FEED LEADS", i)]
    j = body.index("Your phone hears about them")
    line = body[body.rindex("`", 0, j):body.index("</p>", j)]
    prog = "const say = (n) => " + line.rstrip("}") + ";" + """
      console.log(JSON.stringify([say(0), say(1), say(3)]));"""
    got = _node(prog)
    if got is None:
        return
    assert got[0] == "Your phone hears about them with the switches above, under Yours.", got[0]
    assert got[1].endswith("under Yours, and here your watch rises above the rest of the feed."), got[1]
    assert got[2].endswith("under Yours, and here your watches rise above the rest of the feed."), got[2]
    assert "two hundred that are not" not in APP


def test_the_strategy_lab_tests_a_rule_in_every_league():
    extras = (JS / "extras.js").read_text(encoding="utf-8")
    i = extras.index('sel("lb-sport", "League", ')
    opts = re.findall(r'\["(\w+)", "([^"]+)"\]', extras[i:extras.index("\n", i)])
    assert [k for k, _ in opts] == ["all", "nfl", "cfb", "mlb", "nba", "cbb", "wnba", "nhl", "ufc"], opts
    assert dict(opts)["cfb"] == "College football" and dict(opts)["cbb"] == "College basketball"


def test_the_prediction_market_desk_reads_hockey():
    sys.path.insert(0, str(ROOT))
    import pm_build
    assert pm_build.SLATE_FILES["nhl"] == "nhl.json"
    more = (JS / "more.js").read_text(encoding="utf-8")
    assert '["nhl", "NHL"]' in more[more.index("const PMX_LEAGUES = "):more.index("];", more.index("const PMX_LEAGUES = "))]
    got = _node(_fn(APP, "pmFlowLeague") + """
      console.log(JSON.stringify([pmFlowLeague({slug: "nhl-tor-mtl-2026-11-19"}),
        pmFlowLeague({market: "Will the Oilers win the Stanley Cup?"}), pmFlowLeague({market: "NHL: Oilers vs Flames"}),
        pmFlowLeague({slug: "nba-lal-bos-2026-11-19"}), pmFlowLeague({market: "Mayor of Oslo"})]));""")
    if got is None:
        return
    assert got == ["nhl", "nhl", "nhl", "nba", "other"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
