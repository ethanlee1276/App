"""A search names each thing once, and the season's other counts are small pills
(SEARCHDUP1, PLRPILLS1; 2026-11-18).

Ethan, with a screenshot of the search page for "Lions" (the Detroit Lions as a
team chip, then again under "Found in NFL" as a player, "Lions · DEF"): "we
don't need to have search results popping up twice on this page. Maybe I like
the pill icon for the team logos. Maybe just use that, but make them bigger."
And, with an X over the route chart's big season box on Amon-Ra St. Brown's
page: "the big box with his face is not needed anymore since we have his face
at the top ... find somewhere else to put that information for the games,
targets, receptions ... maybe put those in like smaller pill boxes." What
these hold:

  * the logs file a club's defence under the club's own name, and that row is
    the club: the league search, the logs search, the roster built from the
    logs and the team page's roster leave it out; a defender filed "DEF" stays;
  * the page says no "No NFL players match" under a team it found, and the
    team chips are bigger (a 26-pixel mark, more padding, a larger word);
  * the player's own page has no big season box (carrychart.js `own`), and
    the season card carries what that box said that its tiles do not: the
    games played and the role's other counts, as small pills, each once.

    python3 tests/test_a_search_names_each_thing_once.py
"""
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

from engine import db, playersearch as PS, rosters, teamdex as T      # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
PLR = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")


def _logs(path=None):
    c = db.connect(path or ":memory:")
    rows = []
    for g in range(1, 4):
        for who, pos, m, v in (("Detroit Lions", "DEF", "rec_yds", 3.0), ("Aidan Hutchinson", "DEF", "sacks", 1.0),
                               ("Amon-Ra St. Brown", "WR", "rec_yds", 70.0),
                               ("Amon-Ra St. Brown", "WR", "receptions", 7.0)):
            rows.append({"sport": "nfl", "season": 2026, "period": f"{g:03d}", "game_id": f"DET-{g:03d}",
                         "player": who, "team": "DET", "opponent": "GB", "position": pos, "home": 1,
                         "market": m, "value": v})
    db.upsert_player_logs(c, rows)
    c.commit()
    return c


def test_a_club_is_its_own_chip_never_a_player():
    assert "Detroit Lions" in [n.title() for n in ("detroit lions",)]
    assert PS.norm("Detroit Lions") in PS.club_names("nfl") and len(PS.club_names("nfl")) == 32
    hits = [{"player": "Detroit Lions", "sport": "nfl", "position": "DEF"},
            {"player": "Aidan Hutchinson", "sport": "nfl", "position": "DEF"},
            {"player": "Detroit Lions", "sport": "cfb", "position": "DEF"}]
    assert [h["player"] for h in PS.drop_clubs(hits)] == ["Aidan Hutchinson", "Detroit Lions"], \
        "a defender filed DEF stays; a name that is no club in its league stays"
    assert PS.drop_clubs([{"player": "Detroit Lions"}], "nfl") == []
    src = (ROOT / "engine" / "statlogs.py").read_text(encoding="utf-8")
    assert "return drop_clubs(_search_conn(conn, sport, q, limit, data_dir), sport)" in src
    assert "return drop_clubs(no_guess_beside_an_answer(merge(per, q, limit, order, prefer=prefer)))" in \
        (ROOT / "engine" / "playersearch.py").read_text(encoding="utf-8")


def test_the_rosters_and_the_team_page_leave_the_club_out():
    # The NFL's roster comes from the players feed, which lists each club's defence as a player.
    blob = {"DET": {"player_id": "DET", "full_name": "Detroit Lions", "first_name": "Detroit", "last_name": "Lions",
                    "team": "DET", "position": "DEF", "active": True, "status": "Active"},
            "1": {"player_id": "1", "full_name": "Aidan Hutchinson", "first_name": "Aidan", "last_name": "Hutchinson",
                  "team": "DET", "position": "DE", "active": True, "status": "Active", "depth_chart_order": 1}}
    built = rosters.build_rosters(blob)
    det = [p["player"] for p in built["teams"]["DET"]["players"]]
    assert det == ["Aidan Hutchinson"], det
    # The team page reads the logs, which file the defence under the club's name too.
    c = _logs()
    team = T.stat_tables(c, "nfl", "DET", 2026)
    names = {r["player"] for sec in team["sections"] for r in sec["rows"]}
    assert "Detroit Lions" not in names and "Amon-Ra St. Brown" in names, names
    # And a league whose roster is built from who played (basketball, baseball, college football).
    src = (ROOT / "engine" / "rosters.py").read_text(encoding="utf-8")
    assert src.count("if clubs and norm(") == 2


def test_the_page_says_nothing_under_a_team_it_found_and_the_chips_are_bigger():
    assert 'host.innerHTML = teamSearchHits(q).length ? "" : `<div class="empty">No' in APP
    i = APP.index("function renderTeamHits(")
    body = APP[i:APP.index("\n}\n", i)]
    assert "${teamMark(t.abbr, 26, teamsForSport(t.sport), t.sport)}" in body
    assert ".al-cat.tm-hit { gap: 9px; padding: 9px 15px; font-size: var(--fs-md); }" in CSS, \
        "two classes, so it wins over .al-cat's own padding further down the sheet"


STUBS = r"""
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';');
const escapeHtml = esc, escapeAttr = esc;
"""


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_the_season_card_carries_the_games_and_the_targets_as_pills():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    i = PLR.index("const PLR_PILL_SKIP")
    k = PLR.index("const plrIsRate")
    js = STUBS + PLR[i:PLR.index(";\n", i) + 2] + PLR[k:PLR.index(";\n", k) + 2] + _fn(PLR, "plrSeasonPills")
    d = {"season": 2026, "role": "receiving", "career": {
        "groups": [{"key": "rushing", "cols": [{"key": "car", "title": "Rushing attempts"}]},
                   {"key": "receiving", "cols": [{"key": "rec", "title": "Receptions"}, {"key": "tgt", "title": "Targets"},
                                                 {"key": "yds", "title": "Receiving yards"},
                                                 {"key": "avg", "title": "Yards per catch"},
                                                 {"key": "td", "title": "Receiving touchdowns"}]}],
        "rows": [{"season": 2025, "gp": 17, "values": {"receiving.tgt": 160}},
                 {"season": 2026, "gp": 9, "values": {"rushing.car": 2, "receiving.rec": 65, "receiving.tgt": 91,
                                                     "receiving.yds": 755, "receiving.avg": 11.6, "receiving.td": 7}}]}}
    nums = [{"key": "rec"}, {"key": "yds"}, {"key": "td"}, {"key": "avg"}]
    out = subprocess.run([node, "-e", js + f"\nprocess.stdout.write(JSON.stringify([plrSeasonPills({json.dumps(d)}, "
                          f"{json.dumps(nums)}), plrSeasonPills({{season: 2027, career: {json.dumps(d['career'])}}}, [])]));"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    got, none = json.loads(out.stdout)
    assert got == ('<div class="plr-pills"><span class="plr-pill">9 games</span>'
                   '<span class="plr-pill">91 targets</span></div>'), got
    assert none == "", "a season with no line of its own says nothing"
    assert "plrSeasonPills(d, nums)}</section>`;" in PLR
    css = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")
    assert ".plr-pills {" in css and ".plr-pill {" in css
    # The big season box is the chart's, and the player's own page draws it no more.
    cc = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
    assert 'const card = C.own ? "" : playerHero(d, sport, S.kind);' in cc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
