"""Walk 13's fixes (2026-11-18, step YC): Duke's page and Cayden Boozer's, the
Oilers' and Connor McDavid's, the Lions' and Puka Nacua's, and the NBA
standings, read as a reader would on a phone.

  - Duke's team page ranked it "62nd of 564": every small school that played
    a Division I one was in the field. College ranks among Division I, as the
    game page's scan has since step XZ;
  - a college shooter's chart chips read "2026" and "2025" beside a page saying
    "2026–27 season", and the charts wrote "2025-26" where the pages write
    "2025–26"; one name for a split season everywhere a reader sees one (the
    NBA stats API keeps its own spelling for its query);
  - the team page's at-a-glance Record tile said the header's record again, and
    on the Oilers' page differently (17-3-3 above, 17-5 below);
  - Puka Nacua's last ten read "Wk 1 vs SF" and then "Wk 21 vs SEA": last
    January's conference final. A playoff week says its round;
  - his page, opened first, named no injury by his name while Latest said
    "IR · Knee - MCL": the page now asks for the injury board itself;
  - a return day was said three ways (team page, roster, pick card); now the
    injuries page's one ("return Sun, Nov 29").

    python3 tests/test_walk_thirteen_says_it_once.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JS = ROOT / "web" / "js"
MORE = (JS / "more.js").read_text(encoding="utf-8")
APP = (JS / "app.js").read_text(encoding="utf-8")
CC = (JS / "carrychart.js").read_text(encoding="utf-8")
PLR = (JS / "playerpage.js").read_text(encoding="utf-8")

from engine import db as D, teamdex                                             # noqa: E402


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def test_college_ranks_among_division_one_on_the_team_page():
    conn = D.connect(Path(tempfile.mkdtemp()) / "t.db")
    games = [  # (day, home, away, home score, away score)
        ("2026-11-02", "DUKE", "espn:2918", 113, 52),   # a small school: in no field
        ("2026-11-05", "DUKE", "UNC", 80, 70),
        ("2026-11-08", "KU", "UNC", 75, 60),
        ("2026-11-09", "espn:2918", "espn:77", 90, 40),  # two small schools
    ]
    for i, (day, home, away, hs, as_) in enumerate(games):
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('cbb', 2026, ?, ?, ?, ?, ?, ?)", (day, f"g{i}", home, away, hs, as_))
    conn.commit()
    duke = teamdex.profile(conn, "cbb", "DUKE")["seasons"][0]
    assert duke["teams_ranked"] == 3, duke                     # DUKE, UNC, KU
    assert duke["offense_rank"] == 1 and duke["record"] == "2-0", duke
    small = teamdex.profile(conn, "cbb", "espn:2918")["seasons"][0]
    assert small["offense_rank"] is None and small["defense_rank"] is None, "a small school keeps its numbers, unranked"
    assert small["record"] == "1-1"
    # Every other league is ranked among every club it stores, as before.
    for i, (home, away) in enumerate((("KC", "BUF"), ("DET", "GB"))):
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('nfl', 2026, '1', ?, ?, ?, 24, 17)", (f"n{i}", home, away))
    conn.commit()
    assert teamdex.profile(conn, "nfl", "KC")["seasons"][0]["teams_ranked"] == 4


def test_a_split_season_has_one_name():
    assert '/^(nba|nhl|cbb)$/.test(sport) ? `${y}–${String((+y + 1) % 100).padStart(2, "0")}`' in CC
    from engine import role
    from engine.nba import shots, tracking
    from engine.nhl import charts
    assert role.season_label("cbb", 2026) == "2026–27" and role.season_label("nfl", 2026) == "2026"
    assert shots.season_label(2025) == "2025–26" and charts.season_label(2025) == "2025–26"
    assert tracking.season_label(2024) == "2024-25", "the NBA stats API is asked in its own spelling"
    # The pages say it so already.
    assert "`${s}–${String((Number(s) + 1) % 100).padStart(2, \"0\")}`" in PLR
    assert "`${s}–${String((Number(s) + 1) % 100).padStart(2, \"0\")}`" in MORE


def test_the_glance_leaves_the_record_to_the_header():
    home = _fn(MORE, "teamHomeHTML")
    assert 'tile("Record", s.record)' not in home
    assert 'tile("Scored / game", s.pf_per_game, of(s.offense_rank))' in home
    head = _fn(MORE, "teamHeaderHTML")
    assert "const record = (std && std.row.record) || (season && season.record) || \"\";" in head, \
        "the header says the record: the league's own, else the finals on file"


def test_an_nfl_playoff_week_reads_as_its_round():
    node = shutil.which("node")
    i = APP.index("const NFL_ROUND = ")
    helper = APP[i:APP.index("\n", i)] + "\n" + _fn(APP, "nflWeekWord")
    if node:
        out = subprocess.run([node, "-e", helper + """
          console.log(JSON.stringify([nflWeekWord(21, "nfl"), nflWeekWord(19, "nfl"), nflWeekWord(22, "nfl"),
            nflWeekWord(9, "nfl"), nflWeekWord(19, "cfb"), nflWeekWord(18, "nfl")]));"""],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout) == ["Conference", "Wild Card", "Super Bowl", "Wk 9", "Wk 19", "Wk 18"]
    hist = _fn(APP, "historyProfileHTML")
    assert "nflWeekWord(l.week, r0.sport)" in hist and "`Wk ${l.week}`" not in hist
    assert APP.count("nflWeekWord(l.week, r.sport || state.sport)") == 2, "the priced card's table and its chart"
    assert "const NFL_ROUNDS = NFL_ROUND;" in MORE, "one table for the site"


def test_a_player_page_opened_first_asks_for_the_injury_board():
    fill = _fn(PLR, "plrFill")
    assert 'typeof loadInjuryBoard === "function" && typeof injTag === "function"' in fill
    assert "if (flag && !flag.innerHTML.trim()) flag.innerHTML = injTag(d.sport, d.player);" in fill


def test_a_return_day_is_said_one_way():
    assert 'const injRet = (r) => r.return_date ? `return ${formatGameDate(r.return_date) || r.return_date}` : "";' in APP
    assert "[inj.injury, injRet(inj)]" in _fn(APP, "pickInjuryNote")
    assert "[r.injury, injRet(r)]" in _fn(MORE, "teamInjuryRowHTML")
    assert "est. return" not in MORE and "function teamDayWords(" not in MORE


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
