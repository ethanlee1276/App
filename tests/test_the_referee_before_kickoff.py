"""The referee before kickoff: who has the game, his games beside the league's, and never a number moved.

Ethan, 2026-10-24: "yes build all of D" — the referee before kickoff among
them. engine/nflrefs names each game's referee from the first source that
has him (by hand, ESPN's summary, Football Zebras' weekly post) and reads
his games since 2024 off nflverse's schedule and play-by-play.

What these hold: a penalty is counted once, its yards either way, and the
home team's share kept; a referee's overs and home covers are against the
closing numbers, pushes left out, unplayed and unrefereed games left out;
a post's row names a referee only with two teams and a referee this league
knows, the visitor first; a post written as prose is read sentence by
sentence against the week's games, a passing mention losing to the
referee who names both teams and a tie naming no one; a name set by hand wins, ESPN next, Football
Zebras fills the rest, and a game a week away is not asked about; the
report's line says where he was named, puts the league beside every
number, flags a thin record and carries the measured caveat; with no
referee the report keeps its old line; and the tendencies are refitted
on Tuesdays, out of process.

Run directly: `python3 tests/test_the_referee_before_kickoff.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import nflrefs as R                                   # noqa: E402

NICK = {"steelers": "PIT", "saints": "NO", "49ers": "SF", "falcons": "ATL", "chiefs": "KC",
        "seahawks": "SEA", "new orleans saints": "NO", "pittsburgh steelers": "PIT"}
REFS = {"Clay Martin", "Shawn Hochuli", "Alex Kemp", "Land Clark"}


def test_a_penalty_is_counted_once_its_yards_either_way():
    plays = [{"game_id": "g1", "home_team": "NO", "penalty": "1", "penalty_team": "NO", "penalty_yards": "-10"},
             {"game_id": "g1", "home_team": "NO", "penalty": "1.0", "penalty_team": "PIT", "penalty_yards": "15"},
             {"game_id": "g1", "home_team": "NO", "penalty": "0", "penalty_team": "", "penalty_yards": ""},
             {"game_id": "g2", "home_team": "ATL", "penalty": "NA"}]
    got = R.penalties_by_game(plays)
    assert got == {"g1": {"flags": 2, "yards": 25.0, "home_flags": 1}}


def _game(gid, ref, hs, as_, total="44.5", spread="3.0", season="2025"):
    return {"game_id": gid, "season": season, "referee": ref, "home_score": hs, "away_score": as_,
            "total_line": total, "spread_line": spread}


def test_overs_and_covers_are_against_the_closing_numbers():
    sched = [_game("a", "Clay Martin", "30", "20"),          # 50 > 44.5 over; won by 10 > 3, covered
             _game("b", "Clay Martin", "20", "17", total="37"),  # a push on the total; won by 3, a push
             _game("c", "Clay Martin", "10", "24"),          # under; lost
             _game("d", "Alex Kemp", "", ""),                # not played
             _game("e", "", "21", "20"),                     # no referee
             _game("f", "Alex Kemp", "27", "24", season="2023")]  # before the window
    pen = {"a": {"flags": 14, "yards": 120.0, "home_flags": 6}, "c": {"flags": 10, "yards": 80.0, "home_flags": 5}}
    t = R.tendencies(sched, pen, first_season=2024)
    cm = t["refs"]["Clay Martin"]
    assert set(t["refs"]) == {"Clay Martin"} and t["seasons"] == [2025, 2025]
    assert cm["games"] == 3 and cm["lined"] == 2 and cm["over"] == 0.5
    assert cm["home_cover"] == 0.5, "the push on the spread is out: one cover of two"
    assert cm["home_win"] == round(2 / 3, 4)
    assert cm["flags"] == 12.0 and cm["yards"] == 100.0, "a game without play-by-play is not a zero"
    assert cm["home_share"] == round(11 / 24, 4)
    assert t["league"] == cm, "one referee is the league"


POST_TABLE = """<p>Here are the referee assignments for Week 7.</p>
<table><tr><th>Visitor</th><th>Home</th><th>Referee</th></tr>
<tr><td>Steelers</td><td>Saints</td><td>Clay Martin</td></tr>
<tr><td>49ers</td><td>Falcons</td><td>Shawn Hochuli</td></tr>
<tr><td>Chiefs</td><td>Seahawks</td><td>Bill Nobody</td></tr>
<tr><td>Chiefs</td><td colspan="2">Alex Kemp</td></tr></table>"""

POST_LINES = ("<p>Pittsburgh Steelers at New Orleans Saints &#8212; Land Clark<br/>"
              "Chiefs at Seahawks: Alex Kemp &amp; crew<br>Clay Martin, Shawn Hochuli: alternates</p>")


def test_a_post_names_a_referee_only_with_two_teams_and_a_known_name():
    got = R.parse_post(POST_TABLE, REFS, NICK)
    assert got == {"PIT@NO": "Clay Martin", "SF@ATL": "Shawn Hochuli"}, got
    lines = R.parse_post(POST_LINES, REFS, NICK)
    assert lines == {"PIT@NO": "Land Clark", "KC@SEA": "Alex Kemp"}, "the full names and the nicknames, visitor first"


PROSE = """<p>Embed from Getty Images</p>
<p>Alan Eck will be in Chicago on Thursday as the Patriots square off with the Bears.
Clete Blakeman, Adrian Hill, and Shawn Hochuli are off this week.</p>
<p>In the early window, Land Clark heads to New Orleans for Steelers-Saints, and Clay Martin has the
49ers in Atlanta. Alex Kemp works in Los Angeles on Sunday.</p>
<p>Sunday night: Kansas City at Seattle goes to Brad Allen; Brad Allen also worked the Super Bowl.</p>
<p>John Hussey has the Cowboys and the Eagles on Monday night, a rematch of the game Bill Vinovich worked
in Dallas.</p>"""
WEEK = ["NE@CHI", "PIT@NO", "SF@ATL", "LA@LV", "KC@SEA", "DAL@PHI"]
ALL_REFS = REFS | {"Alan Eck", "Clete Blakeman", "Adrian Hill", "Brad Allen", "John Hussey", "Bill Vinovich"}


def test_the_prose_post_is_read_sentence_by_sentence_against_the_weeks_games():
    # The box, 2026-10-24: Football Zebras' week 7 post is sentences, not a table.
    got = R.parse_post(PROSE, ALL_REFS, games=WEEK)
    assert got["NE@CHI"] == "Alan Eck", "a city and a nickname, both in the one game"
    assert got["PIT@NO"] == "Land Clark" and got["SF@ATL"] == "Clay Martin", "two referees in one sentence"
    assert "LA@LV" not in got, "Los Angeles alone is two teams; the game is LV's anyway"
    assert got["DAL@PHI"] == "John Hussey", "the later referee's Dallas is his own part of the sentence"
    assert got["KC@SEA"] == "Brad Allen", "teams before the referee, and his second mention names none"
    whys = {(n, w) for _s, n, _t, g, w in R.readings(PROSE, ALL_REFS, WEEK) if not g}
    assert ("Clete Blakeman", "no team named") in whys and ("Shawn Hochuli", "no team named") in whys
    # One referee read onto two games is neither's.
    twice = "<p>Alan Eck has Steelers-Saints.</p><p>Alan Eck has Chiefs-Seahawks.</p>"
    assert R.parse_post(twice, ALL_REFS, games=WEEK) == {}
    # Two referees each naming both teams of one game: a tie, and no name.
    tie = "<p>Alan Eck has Steelers-Saints.</p><p>Land Clark has Steelers-Saints.</p>"
    assert R.parse_post(tie, ALL_REFS, games=WEEK) == {}


def test_by_hand_wins_espn_next_football_zebras_fills_the_rest():
    today = dt.date(2026, 10, 24)
    games = [{"away": "PIT", "home": "NO", "date": "2026-10-25"},
             {"away": "SF", "home": "ATL", "date": "2026-10-25"},
             {"away": "KC", "home": "SEA", "date": "2026-10-26"},
             {"away": "BUF", "home": "MIA", "date": "2026-11-05"}]
    R.set_by_hand(2026, 7, ["pit@no=Clay Martin"])
    asked = []

    def espn(g):
        asked.append(g["away"])
        return {"gameInfo": {"officials": [{"fullName": "Shawn Hochuli", "position": {"displayName": "Referee"}},
                                           {"fullName": "Someone Else", "position": {"displayName": "Umpire"}}]}} \
            if g["away"] == "SF" else {}

    def zebras(season, week, refs, games=None):
        assert (season, week) == (2026, 7) and "KC@SEA" in games
        return {"KC@SEA": "Alex Kemp", "SF@ATL": "Wrong Name", "BUF@MIA": "Too Early"}
    got = R.assigned(games, 2026, 7, store={}, today=today, espn=espn, zebras=zebras)
    assert got == {"PIT@NO": ("Clay Martin", "set"), "SF@ATL": ("Shawn Hochuli", "espn"),
                   "KC@SEA": ("Alex Kemp", "footballzebras")}, got
    assert asked == ["SF", "KC"], "named by hand is not asked again; a game ten days out is not asked"
    nothing = R.assigned(games[1:], 2026, 8, store={}, today=today, espn=lambda g: {}, zebras=lambda *a: {})
    assert nothing == {}, "no source, no name"


def test_the_feed_post_must_be_the_weeks_and_the_seasons():
    posts = [{"title": {"rendered": "Week 6 referee assignments"}, "date": "2026-10-16",
              "content": {"rendered": POST_TABLE}},
             {"title": {"rendered": "Week 7 referee assignments"}, "date": "2025-10-16",
              "content": {"rendered": POST_TABLE}},
             {"title": {"rendered": "Week 7 referee assignments, 2026"}, "date": "2026-10-23T12:00:00",
              "content": {"rendered": POST_LINES}}]
    real = R._cached_json
    R._cached_json = lambda url, name: posts
    try:
        got = R.from_footballzebras(2026, 7, REFS)
    finally:
        R._cached_json = real
    assert set(got.values()) == {"Land Clark", "Alex Kemp"}, got
    assert "week%207" in R.FZ_FEED.format(week=7) and R.FZ_FEED.startswith("https://www.footballzebras.com/wp-json/")


STORE = {"league": {"games": 635, "flags": 12.89, "over": 0.5253, "home_cover": 0.512},
         "refs": {"Clay Martin": {"games": 38, "flags": 12.45, "over": 0.5, "home_cover": 0.5405},
                  "Tra Blake": {"games": 6, "flags": 11.9, "over": 0.62, "home_cover": 0.31}},
         "seasons": [2024, 2026]}


def test_the_reports_line_says_where_from_the_league_beside_and_the_caveat():
    line = R.words(R.card("Clay Martin", "footballzebras", STORE))
    assert line.startswith("Referee: Clay Martin (Football Zebras). His 38 games since 2024: ")
    assert "12.4 penalties a game (league 12.9)" in line or "12.5 penalties a game (league 12.9)" in line
    assert "50% over the closing total (league 53%)" in line
    assert "home teams covered 54% (league 51%)" in line
    assert line.endswith(R.CAVEAT) and "not part of the read" in R.CAVEAT
    thin = R.words(R.card("Tra Blake", "espn", STORE))
    assert "His 6 games since 2024, a thin sample:" in thin and "(ESPN)" in thin
    new = R.words(R.card("New Referee", "set", STORE))
    assert new.startswith("Referee: New Referee (named by hand). We have no games of his")
    assert R.words({}) == ""


def test_the_report_build_and_the_week_carry_it():
    rep = open(os.path.join(ROOT, "engine", "gamereport.py"), encoding="utf-8").read()
    assert 'lines.append(_ref_words(g.get("officials") or {}) or OFFICIALS)' in rep, "no referee: the old line"
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    at = build.index("_nflrefs.attach(result, args.season, args.week)")
    assert at < build.index("_greport.attach(result"), "stamped before the report reads it"
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert 'today.weekday() == 1 and state.get("nflrefs_attempted")' in maint
    assert '_spawn_module("engine.nflrefs", log, args=("--fit",))' in maint


def test_attach_stamps_the_named_games_and_never_raises():
    result = {"games": [{"away": "PIT", "home": "NO", "date": "2026-10-25"},
                        {"away": "SF", "home": "ATL", "date": "2026-10-25"}]}
    R.set_by_hand(2026, 9, ["PIT@NO=Clay Martin"])
    with open(R._store_path(), "w", encoding="utf-8") as fh:
        json.dump(STORE, fh)
    msg = R.attach(result, 2026, 9, today=dt.date(2026, 10, 24), espn=lambda g: {}, zebras=lambda *a: {})
    assert msg == "Referees: 1 of 2 game(s) named (1 named by hand)", msg
    assert result["games"][0]["officials"]["record"]["games"] == 38
    assert "officials" not in result["games"][1]
    assert R.attach({"games": None}, 2026, 9).startswith("Referees: 0 of 0")
    assert R.attach(None, 2026, 9).startswith("Referees skipped:")


def test_why_says_what_each_source_answered():
    # The box, 2026-10-24: 0 of 14 named, and nothing said which link broke.
    games = [{"away": "PIT", "home": "NO", "date": "2026-10-25"}, {"away": "SF", "home": "ATL", "date": "2026-10-25"}]

    def espn(g):
        if g["away"] == "SF":
            raise TimeoutError("slow")
        return {"gameInfo": {"venue": {}, "attendance": 0}}
    posts = [{"title": {"rendered": "Week 7 referee assignments"}, "date": "2026-10-23", "content": {"rendered": POST_TABLE}},
             {"title": {"rendered": "Officiating crews for the 2026 season"}, "date": "2026-08-01", "content": {"rendered": ""}}]
    lines = R.diagnose(games, 2026, 7, store={"refs": {n: {} for n in REFS}}, espn=espn, posts_fetch=lambda: posts)
    text = "\n".join(lines)
    assert "ESPN PIT@NO: no officials listed yet (gameInfo keys: ['attendance', 'venue'])" in text
    assert "ESPN SF@ATL: TimeoutError: slow" in text
    assert "the feed returned 2 post(s)" in text and "the week's post, 2 game(s) named" in text
    assert "'Officiating crews for the 2026 season': not the week's post" in text

    def blocked():
        raise OSError("HTTP Error 403: Forbidden")
    assert R.diagnose([], 2026, 7, store={}, posts_fetch=blocked)[-1] == \
        "  Football Zebras: OSError: HTTP Error 403: Forbidden"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
