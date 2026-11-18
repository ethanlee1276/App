"""A team's page says only what is true, and in words (TEAMFIX1, 2026-11-17).

Three team pages were read on the live site's own data that day, as a user
would: Duke's, the Nuggets' and the Bills'. What was on them:

  * every final with no betting line on file read "0 covered" or "0 missed",
    and counted in a record against the spread that was the club's win-loss
    record under another name (the Nuggets 6-5, Duke 3-1). Every feed writes
    0.0 where a spread would go; only the NFL's and college football's
    closes are written over it. A zero with no total beside it is no line;
  * a basketball log keeps the box score's starter flag, "S" or "B", where a
    position goes (the minutes model reads it), and it was printed as one:
    "Patrick Ngongba II S" on the leaders, on every stat row, as the roster's
    two headings, as the depth chart's two rows (which cut the fifth starter
    off) and on a college player's own page ("Duke Blue Devils · S");
  * basketball's club had one leader tile, "PLAYERS PTS". Points, rebounds
    and assists each have their own now, and hockey's and baseball's
    sections name theirs;
  * sixteen NFL players' injury read "Concussion Concussion" (the feed's
    type and its detail, the same word), with the return day as a file's
    date ("return 2026-11-22");
  * an NFL game on Sunday was "On tonight's board" on a Tuesday.

    python3 tests/test_a_team_page_says_only_what_is_true.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, rosters, teamdex as T                                 # noqa: E402
from engine.sources import espninjuries                                      # noqa: E402

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def _games(sport, *rows):
    """`(season, period, home, away, home score, away score, spread, total)` rows of one league."""
    c = db.connect(":memory:")
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, spread, total) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [(sport, s, p, f"{a}@{h}", h, a, hs, as_, sp, to) for (s, p, h, a, hs, as_, sp, to) in rows])
    c.commit()
    return c


def test_a_zero_with_no_total_is_no_line():
    assert T._spread({"spread": 0.0, "total": None}) is None, "the feeds' placeholder"
    assert T._spread({"spread": None, "total": 44.5}) is None
    assert T._spread({"spread": 0.0, "total": 221.5}) == 0.0, "a pick'em has a total beside it"
    assert T._spread({"spread": -6.5, "total": None}) == -6.5
    # The Nuggets' eleven finals, as the NBA's feed stores them: no line on any.
    c = _games("nba", (2026, "2026-10-22", "OKC", "DEN", 96, 84, 0.0, None),
               (2026, "2026-10-24", "DEN", "NOP", 141, 135, 0.0, None),
               (2026, "2026-11-16", "DEN", "PHX", 105, 117, 0.0, None),
               (2026, "2026-11-14", "NOP", "DEN", 108, 116, -2.5, 228.5))
    now = T.profile(c, "nba", "DEN")["seasons"][0]
    assert now["record"] == "2-2" and now["games"] == 4, now
    assert (now["ats_w"], now["ats_l"], now["ats_p"]) == (1, 0, 0), ("only the game a line was stored for", now)
    assert (now["over"], now["under"]) == (0, 1)
    rows = {g["period"]: g for g in T.season_schedule(c, "nba", "DEN", 2026)["games"]}
    blank = rows["2026-10-22"]
    assert blank["line"] is None and blank["covered"] is None and blank["spread"] is None, blank
    lined = rows["2026-11-14"]
    assert lined["line"] == 2.5 and lined["covered"] is True and lined["ou"] == "under", lined
    # What the page prints for each: nothing for the first, "+2.5 covered" for the second.
    assert 'line ? `${line} ${g.covered === true ? "covered"' in MORE
    assert "${s.ats_w + s.ats_l + s.ats_p ? tile(\"Against the spread\"" in MORE, "and no tile for a record of nothing"


def _hoops(conn, sport, team, rows):
    logs = []
    for i, (player, flag, pts, reb, ast, mins) in enumerate(rows):
        for g in range(1, 4):
            for market, v in (("pts", pts), ("reb", reb), ("ast", ast), ("min", mins)):
                logs.append({"sport": sport, "season": 2026, "period": f"2026-11-{g:02d}", "game_id": f"g{g}",
                             "player": player, "team": team, "opponent": "MSU", "position": flag, "home": 1,
                             "market": market, "value": float(v)})
    db.upsert_player_logs(conn, logs)
    conn.commit()


DUKE = (("Patrick Ngongba II", "S", 15, 8, 3, 25), ("Cayden Boozer", "S", 9, 5, 9, 22), ("Dame Sarr", "S", 11, 11, 2, 23),
        ("John Blackwell", "S", 10, 2, 1, 26), ("Joaquim Boumtje Boumtje", "S", 10, 6, 0, 20),
        ("Caleb Foster", "B", 10, 3, 2, 19), ("Sebastian Wilkins", "B", 7, 5, 1, 18))


def test_the_starter_flag_is_never_printed_as_a_position():
    assert rosters.shown_position("cbb", "S") == "" and rosters.shown_position("nba", "b") == ""
    assert rosters.shown_position("cbb", "Starters") == "" and rosters.shown_position("wnba", "BENCH") == ""
    assert rosters.shown_position("nba", "PG") == "PG" and rosters.shown_position("cbb", "g") == "G"
    assert rosters.shown_position("nfl", "S") == "S", "a safety is a safety"
    assert rosters.shown_position("cfb", "B") == "B" and rosters.shown_position("mlb", "") == ""
    assert rosters.flag_group("cbb", "S") == "Starters" and rosters.flag_group("cbb", "B") == "Bench"
    assert rosters.flag_group("cbb", "G") == "" and rosters.flag_group("nfl", "S") == ""
    c = db.connect(":memory:")
    _hoops(c, "cbb", "DUKE", DUKE)
    # The stored flag is what it was: the minutes model reads it.
    assert {r[0] for r in c.execute("SELECT DISTINCT position FROM player_game_logs")} == {"S", "B"}
    st = T.stat_tables(c, "cbb", "DUKE", 2026)
    assert {r["position"] for sec in st["sections"] for r in sec["rows"]} == {""}, "no letter after a name"
    assert {L["position"] for L in st["leaders"]} == {""}
    # The roster built from who played: no position, the flag in words to group by, starters first.
    club = rosters.from_game_logs(c, "cbb", today="2026-11-04")["teams"]["DUKE"]["players"]
    assert {p["position"] for p in club} == {""}
    assert [p["depth_pos"] for p in club] == ["Starters"] * 5 + ["Bench"] * 2, [p["depth_pos"] for p in club]
    depth = T.usage_depth(c, "cbb", club)
    assert [g["position"] for g in depth["positions"]] == ["Starters", "Bench"]
    assert depth["positions"][0]["players"][0] == "John Blackwell" and len(depth["positions"][0]["players"]) == 5
    # The page: the roster groups by the flag's words, and a starters' row holds all five.
    assert 'const pos = p.position || p.depth_pos || "—";' in MORE
    assert 'rows.some((r) => r.position === "Starters") ? 5 : 4' in MORE


def test_a_college_players_own_page_has_no_letter_for_a_position():
    from engine import playerpage as PP
    path = Path(tempfile.mkdtemp()) / "history.db"
    c = db.connect(str(path))
    _hoops(c, "cbb", "DUKE", DUKE)
    c.close()
    data = Path(tempfile.mkdtemp())
    d = PP.page("cbb", "Cayden Boozer", db_path=str(path), data_dir=str(data))
    assert d["player"] == "Cayden Boozer" and d["position"] == "" and d["bio"]["position"] == "", (d["position"], d["bio"])
    src = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    assert "logged = rosters.shown_position(sport, (newest or {}).get(\"position\"))" in src


def test_each_kind_of_number_has_its_leader():
    c = db.connect(":memory:")
    _hoops(c, "cbb", "DUKE", DUKE)
    lead = T.stat_tables(c, "cbb", "DUKE", 2026)["leaders"]
    assert [(L["title"], L["market"], L["player"], L["value"]) for L in lead] == [
        ("Most", "pts", "Patrick Ngongba II", 45.0), ("Most", "reb", "Dame Sarr", 33.0),
        ("Most", "ast", "Cayden Boozer", 27.0)], lead
    # The tile's words are the title and the market's: "Most points", never "Players pts".
    assert "${escapeHtml(L.title)} ${escapeHtml(/_yds$/.test(L.market || \"\") ? \"yards\"" in (
        ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    names = {sec["key"]: [t for t, _m in sec.get("leaders") or ()] for shape in T.STAT_SECTIONS.values() for sec in shape}
    assert names["scoring"] == ["Most"] * 3 and names["skaters"] == ["Most"] * 3 and names["goalies"] == ["Most"]
    assert names["batting"] == ["Most"] * 2 and names["pitching"] == ["Most"]
    # Football's sections are their own leaders, as they were: "Passing yards".
    assert names["passing"] == [] and names["rushing"] == [] and names["receiving"] == []
    f = db.connect(":memory:")
    db.upsert_player_logs(f, [{"sport": "nfl", "season": 2026, "period": "001", "game_id": "BUF-001", "player": who,
                               "team": "BUF", "opponent": "NYJ", "position": pos, "home": 1, "market": m, "value": v}
                              for who, pos, m, v in (("Josh Allen", "QB", "pass_yds", 250.0), ("James Cook", "RB", "rush_yds", 110.0),
                                                     ("Dalton Kincaid", "TE", "rec_yds", 70.0))])
    f.commit()
    assert [(L["title"], L["market"], L["player"], L["position"]) for L in T.stat_tables(f, "nfl", "BUF", 2026)["leaders"]] == [
        ("Passing", "pass_yds", "Josh Allen", "QB"), ("Rushing", "rush_yds", "James Cook", "RB"),
        ("Receiving", "rec_yds", "Dalton Kincaid", "TE")]


def _injury(kind, detail):
    return {"injuries": [{"displayName": "Buffalo Bills", "injuries": [{
        "athlete": {"displayName": "Dee Alford", "position": {"abbreviation": "CB"}}, "status": "Questionable",
        "date": "2026-11-15T20:52Z", "details": {"type": kind, "detail": detail, "returnDate": "2026-11-22"}}]}]}


def test_an_injury_says_its_word_once_and_its_day_as_a_day():
    one = espninjuries.parse_injuries(_injury("Concussion", "Concussion"))[0]
    assert one["injury"] == "Concussion", one["injury"]
    assert espninjuries.parse_injuries(_injury("Knee", "Sprain"))[0]["injury"] == "Knee Sprain"
    assert espninjuries.parse_injuries(_injury("Knee", "Not Specified"))[0]["injury"] == "Knee"
    assert espninjuries.parse_injuries(_injury("Not Specified", "Illness"))[0]["injury"] == "Illness"
    assert espninjuries.parse_injuries(_injury("Not Specified", "Not Specified"))[0]["injury"] is None
    assert espninjuries.parse_injuries(_injury("Hamstring Strain", "strain"))[0]["injury"] == "Hamstring Strain"
    # "est. return Nov 22" since walk 11 (2026-11-18): "Back · back Nov 29" said the word twice.
    assert "`est. return ${teamDayWords(r.return_date)}`" in MORE and "`return ${r.return_date}`" not in MORE
    assert "`back ${teamDayWords(r.return_date)}`" not in MORE
    assert 'toLocaleDateString("en-US", { month: "short", day: "numeric" })' in MORE[MORE.index("function teamDayWords("):][:400]


def test_footballs_board_is_the_weeks():
    assert 'On ${["nfl", "cfb"].includes(d.sport) ? "this week’s" : "tonight’s"} board' in MORE
    assert "On tonight’s board</span>" not in MORE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
