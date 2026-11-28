"""A league's final standings table stays up through its offseason (2026-11-19).

Ethan, asked whether a league's final standings table should stay up during
the offseason: "Yes."

Since 2026-08-24 (tests/test_season_wait.py) an offseason standings page
waited on the season ahead and showed nothing else — MLB's and the WNBA's in
November read only "Waiting on the 2027 season". The wait stays, and the
season that finished rides beside it under its own key (`final`), labelled
final on the page:

  * the build keeps the finished season's table (the league's own, or our
    count of it, said so) and its postseason when one was played;
  * the feed is asked for that season by its own year, never for the season
    ahead (the 08-24 rule);
  * a season being played, or one with nothing on file, carries no `final`;
  * the page draws it under the wait, every heading saying "final" and the
    year, and a football page says the wait once.

    python3 tests/test_the_offseason_keeps_the_final_table.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import standings_build as SB                                     # noqa: E402
from engine.db import connect                                    # noqa: E402
from engine.sources import leaguestandings                       # noqa: E402

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
VISUALS = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")

NOV = "2026-11-19"


class _Feed:
    """The league feed: answers for the seasons it has, and counts every ask."""

    def __init__(self, by_season):
        self.by_season = by_season
        self.seen = []

    def __call__(self, sport, season):
        self.seen.append((sport, season))
        rows = self.by_season.get(season)
        if rows is None:
            raise RuntimeError("feed down")
        return rows


def _build(sport, today=NOV, feed=None, season=None, db=None):
    real_fetch, real_connect = leaguestandings.fetch, SB.connect
    stub = feed or _Feed({})
    leaguestandings.fetch = stub
    SB.connect = db or (lambda: connect(":memory:"))
    try:
        return SB.build(sport, season=season, today=today), stub
    finally:
        leaguestandings.fetch, SB.connect = real_fetch, real_connect


def _mlb_rows():
    from engine import divisions
    clubs = sorted(divisions.MAPS["mlb"])
    return [{"team": t, "wins": 100 - i, "losses": 62 + i, "points_for": 800 - i, "points_against": 650 + i}
            for i, t in enumerate(clubs)]


def test_the_finished_season_stays_up_beside_the_wait():
    b, feed = _build("mlb", feed=_Feed({2026: _mlb_rows()}))
    assert b["season"] == 2027 and b["season_wait"] is True, (b["season"], b["season_wait"])
    assert b["team_count"] == 0 and b["groups"] == [], "the waited-on season has no table of its own"
    fin = b["final"]
    assert fin["season"] == 2026 and fin["source"] == "league" and fin["team_count"] == 30, fin.get("team_count")
    assert len(fin["groups"]) == 6 and all(g["teams"] for g in fin["groups"]), [g["label"] for g in fin["groups"]]
    assert feed.seen == [("mlb", 2026)], f"asked for the finished season by its year, never the next: {feed.seen}"
    assert b["note"].endswith("Standings and the playoff picture fill in here as the season is played. "
                              "Until then, the 2026 season as it finished."), b["note"]
    assert "bracket" not in fin, "no postseason on file, none carried"
    assert b["bracket"]["started"] is False and b["projected_seeds"] == [], "the season ahead's bracket still waits"


def test_a_feed_that_is_down_counts_our_own_finals_and_says_so():
    db = connect(":memory:")
    games = [("mlb", 2026, "2026-06-0%d" % (i % 9 + 1), "NYY", "BOS", 5, 3) for i in range(4)] + \
            [("mlb", 2026, "2026-07-0%d" % (i % 9 + 1), "LAD", "SF", 2, 4) for i in range(3)]
    for i, (sport, season, period, home, away, hs, as_) in enumerate(games):
        db.execute("INSERT INTO games (game_id, sport, season, period, home, away, home_score, away_score)"
                   " VALUES (?,?,?,?,?,?,?,?)", (f"g{i}", sport, season, period, home, away, hs, as_))
    db.commit()
    b, feed = _build("mlb", feed=_Feed({}), db=lambda: db)
    fin = b["final"]
    assert fin["source"] == "computed" and fin["team_count"] == 4 and fin["games_counted"] == 7, fin
    assert fin["note"].startswith("Counted from the 7 finished game(s) we have ingested"), fin["note"]
    assert feed.seen == [("mlb", 2026)]


def test_a_season_being_played_or_with_nothing_on_file_carries_no_final():
    live, feed = _build("nba", today=NOV, feed=_Feed({2026: [{"team": "BOS", "wins": 10, "losses": 4}]}))
    assert live["season_wait"] is False and "final" not in live and feed.seen == [("nba", 2026)]
    empty, feed = _build("wnba", feed=_Feed({}))
    assert empty["season_wait"] is True and "final" not in empty, "nothing of 2026 on file: the wait alone"
    assert empty["note"].endswith("as the season is played."), empty["note"]
    explicit, feed = _build("mlb", season=2026, feed=_Feed({2026: _mlb_rows()}))
    assert explicit["season_wait"] is False and "final" not in explicit, "--season 2026 is that table itself"


def test_the_page_draws_the_final_under_the_wait():
    i = MORE.index("async function renderStandings()")
    body = MORE[i:MORE.index("\n}\n", i)]
    assert body.index("finalStandingsHTML(d, d.final, rankings)") < body.index('"No standings yet"'), \
        "a final table, when the build kept one, is drawn instead of the empty slate"
    fn = MORE[MORE.index("function finalStandingsHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    for words in ("postseason · final", "final standings", "the league’s own final records"):
        assert words in fn, words
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return

    def _fn(src, name):
        j = src.index(f"function {name}(")
        return src[j:src.index("\n}\n", j) + 2]

    prog = "\n".join([_fn(APP, "escapeHtml"), _fn(VISUALS, "escapeAttr"), _fn(APP, "pluralWord"), _fn(APP, "plural"),
                      _fn(MORE, "stdGroupsHTML"), _fn(MORE, "standingsGroupHTML"), _fn(MORE, "bracketHTML"),
                      _fn(MORE, "finalStandingsHTML")]) + """
      var _stdGroup = "", state = {sport: "mlb"};
      const icon = () => "";
      const standingsRowHTML = (t) => `<div class="std-row">${t.team}</div>`;
      const pressureHTML = () => "";
      const fin = {season: 2026, source: "league", groups: [{label: "AL East", teams: [{team: "NYY"}]},
        {label: "AL Central", teams: [{team: "CLE"}]}, {label: "AL West", teams: [{team: "SEA"}]}],
        bracket: {started: true, rounds: [{name: "World Series", matchups: [{teams: ["LAD", "NYY"],
        score: [4, 1], leader: "LAD"}]}]}};
      const d = {season: 2027, season_wait: true, note: "The 2027 MLB season has not started yet. Until then, the 2026 season as it finished."};
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      console.log(JSON.stringify([text(finalStandingsHTML(d, fin, "")),
        text(finalStandingsHTML(d, {...fin, bracket: undefined}, "<p>The 2027 season hasn’t kicked off.</p>"))]));"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    plain, football = json.loads(out.stdout)
    assert plain.startswith("The 2027 MLB season has not started yet."), plain[:120]
    assert "2026 postseason · final" in plain and "World Series LAD 4 NYY 1" in plain, plain
    assert "2026 final standings — the league’s own final records · 3 groups" in plain, plain
    assert "All AL East AL Central AL West" in plain, "three groups get their chips"
    assert football.startswith("The 2027 season hasn’t kicked off.") and "has not started yet" not in football, \
        "a football page says the wait once, in its rankings"
    assert "postseason" not in football, "no postseason played, none drawn"


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
