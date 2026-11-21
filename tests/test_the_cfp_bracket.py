"""The College Football Playoff after selection day: the twelve, every round,
our line, the results and the champion (engine/cfprace.select_field,
playoff_bracket, playoff_odds).

Ethan, 2026-11-03, on the 30 October audit's list — "College Football
Playoff bracket after selection day: twelve seeds, every round, our line,
results" — "do all of them". What these hold:

  * the twelve are the four Power Four champions off the title games, the
    Group of Six's highest-ranked team, Notre Dame in the top twelve and the
    rest at large, seeded straight off the committee's final ranking; with a
    champion still to crown there is no field yet;
  * the field is named once, from a committee ranking dated selection day or
    later, kept, and read back after (the polls after the bowls are not the
    committee's);
  * the first round is 5 v 12, 6 v 11, 7 v 10, 8 v 9 at the higher seed; each
    bye seed meets its game's winner in a bowl; the semifinals and the title
    game follow, each result read off the scoreboard by the two sides in it,
    its bowl named; the champion is the title game's winner;
  * our line is on each game still to play and each team's chance to reach
    each round is played out with every result kept — both paid; the public
    copy keeps the bracket whole;
  * a game's night and bowl are the scoreboard's once it lists the game —
    the playoff nights still to come are read from selection day on — and a
    game listed but not played is never a result;
  * the race is built into January (the season before's), the college build
    runs it on a quiet day too, and the scoreboard keeps each game's billing.

Run directly: `python3 tests/test_the_cfp_bracket.py`
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import cfprace, gate                                 # noqa: E402


def _T():
    """The race tests' own small league (tests/test_the_playoff_race.py)."""
    import test_the_playoff_race as T
    return T

HFA, SD = 2.71, 16.5


def _season():
    """The fixture league played out, every conference's title game won by its
    best side on Dec 5."""
    T = _T()
    games, ratings, ranks = T._league()
    for g in games:
        if not g.get("completed"):
            g.update(completed=True, state="final", home_score=28, away_score=21)
    for c, tag in T.TAG.items():
        games.append({"home": f"{tag}0", "away": f"{tag}1", "home_conference": c, "away_conference": c,
                      "date": "2026-12-05", "season": 2026, "season_type": 2, "conference_game": True,
                      "neutral_site": True, "completed": True, "state": "final", "home_score": 31, "away_score": 24})
    return games, ratings, ranks


def _post(home, away, day, hs, as_, notes=""):
    return {"home": home, "away": away, "date": day, "season": 2026, "season_type": 3, "conference_game": False,
            "neutral_site": bool(notes), "completed": True, "state": "final", "home_score": hs, "away_score": as_,
            "notes": notes}


def _listed(home, away, day, notes=""):
    """A playoff game on the scoreboard before it is played."""
    return dict(_post(home, away, day, None, None, notes), completed=False, state="pre")


def _twelve():
    games, ratings, ranks = _season()
    return cfprace.select_field(games, ranks, 2026)


def _built(extra=(), today="2026-12-07"):
    games, ratings, ranks = _season()
    twelve = cfprace.select_field(games, ranks, 2026)
    return cfprace.build(games + list(extra), ratings, HFA, SD, today, ranks=ranks, sims=600, seed=3,
                         selection=twelve)


# --- selection day ------------------------------------------------------------------
def test_the_twelve_are_the_champions_the_group_of_six_and_the_rest_by_the_ranking():
    twelve = _twelve()
    assert [s["seed"] for s in twelve] == list(range(1, 13))
    bids = {s["team"]: s["bid"] for s in twelve}
    assert {t for t, b in bids.items() if b.endswith("champion")} == {"SE0", "BT0", "AC0", "B10"}
    assert bids.get("AM0") == "Group of Six's best", "the highest-ranked Group of Six side, champion or not"
    assert "ND" not in bids, "Notre Dame is in only inside the top twelve"
    ranked = [s["rank"] for s in twelve]
    assert ranked == sorted(ranked), "seeded straight off the final ranking"
    assert twelve[0]["record"] and twelve[0]["name"]
    games, _r, ranks = _T()._league()                 # no title games played yet
    assert cfprace.select_field(games, ranks, 2026) is None, "a champion still to crown: no field"


def test_the_field_is_named_once_from_the_final_ranking_and_kept():
    games, _ratings, ranks = _season()
    day = cfprace.selection_day(2026)
    assert day == dt.date(2026, 12, 6)
    path = Path(tempfile.mkdtemp()) / "sel.json"
    cfp = {"kind": "cfp", "name": "CFP Rankings", "date": "2026-12-06"}
    assert cfprace.selected(2026, day - dt.timedelta(days=1), games, ranks, cfp, path=str(path)) is None
    stale = dict(cfp, date="2026-12-01")
    assert cfprace.selected(2026, day, games, ranks, stale, path=str(path)) is None, "last week's ranking"
    assert cfprace.selected(2026, day, games, ranks, {"kind": "ap", "date": "2026-12-06"}, path=str(path)) is None
    twelve = cfprace.selected(2026, day, games, ranks, cfp, path=str(path))
    assert twelve and json.loads(path.read_text())["seeds"] == twelve
    later = cfprace.selected(2026, dt.date(2027, 1, 2), games, {}, {"kind": "ap", "date": "2027-01-02"},
                             path=str(path))
    assert later == twelve, "read back after, whatever the polls say"


# --- the rounds ----------------------------------------------------------------------
def test_the_first_round_is_at_the_higher_seed_and_the_byes_wait():
    out = _built()
    br = out["bracket"]
    assert br["set"] and br["champion"] is None
    fr = [(g["home_seed"], g["away_seed"], g["neutral"]) for g in br["first_round"]]
    assert fr == [(5, 12, False), (6, 11, False), (7, 10, False), (8, 9, False)]
    qf = br["quarterfinals"]
    assert [g["home_seed"] for g in qf] == [1, 2, 3, 4] and all(g["away"] is None and g["neutral"] for g in qf)
    assert qf[0]["from"] == ["fr4"], "the 1 seed meets the 8 v 9 winner"
    assert out["chances"][br["seeds"][0]["team"]]["quarterfinals"] == 1.0, "a bye is a quarterfinal"


def test_results_land_round_by_round_and_the_champion_is_crowned():
    first = _built()["bracket"]
    s = {x["seed"]: x["team"] for x in first["seeds"]}
    games = [_post(s[5], s[12], "2026-12-18", 20, 27), _post(s[6], s[11], "2026-12-18", 35, 10),
             _post(s[7], s[10], "2026-12-19", 24, 21), _post(s[8], s[9], "2026-12-19", 17, 14)]
    out = _built(games, today="2026-12-20")
    br = out["bracket"]
    f1 = br["first_round"][0]
    assert f1["done"] and f1["winner"] == s[12] and (f1["home_score"], f1["away_score"]) == (20, 27)
    q4 = br["quarterfinals"][3]
    assert (q4["home"], q4["away"]) == (s[4], s[12]), "the 4 seed meets the 5 v 12 winner"
    assert out["chances"][s[5]]["quarterfinals"] == 0 and out["chances"][s[5]]["title"] == 0
    rose = "College Football Playoff Quarterfinal at the Rose Bowl Game Presented by Prudential"
    games += [_post(s[1], s[8], "2027-01-01", 30, 20, rose), _post(s[2], s[7], "2027-01-01", 27, 24, "x"),
              _post(s[3], s[6], "2026-12-31", 14, 21, "x"), _post(s[12], s[4], "2026-12-31", 28, 24, "x")]
    out = _built(games, today="2027-01-02")
    br = out["bracket"]
    q1 = br["quarterfinals"][0]
    assert q1["bowl"] == "Rose Bowl Game" and q1["winner"] == s[1]
    q4 = br["quarterfinals"][3]
    assert q4["home"] == s[4] and (q4["home_score"], q4["away_score"]) == (24, 28), "scores follow the bracket's sides"
    sf = br["semifinals"]
    assert {sf[0]["home"], sf[0]["away"]} == {s[1], s[12]} and {sf[1]["home"], sf[1]["away"]} == {s[2], s[6]}
    games += [_post(s[1], s[12], "2027-01-09", 35, 17, "x"), _post(s[6], s[2], "2027-01-08", 21, 20, "x"),
              _post(s[6], s[1], "2027-01-19", 24, 31, "x")]
    out = _built(games, today="2027-01-20")
    br = out["bracket"]
    assert br["champion"] == s[1] and br["final"]["done"]
    assert out["chances"][s[1]]["title"] == 1.0 and out["bracket_lines"] == {}


def test_a_listed_game_carries_its_night_and_bowl_and_is_no_result():
    out = _built()
    s = {x["seed"]: x["team"] for x in out["bracket"]["seeds"]}
    listed = [_listed(s[5], s[12], "2026-12-19"), _listed(s[6], s[11], "2026-12-18"),
              _listed(s[7], s[10], "2026-12-18"), _listed(s[8], s[9], "2026-12-19")]
    got = _built(listed)
    fr = got["bracket"]["first_round"]
    assert [g["date"] for g in fr] == ["2026-12-19", "2026-12-18", "2026-12-18", "2026-12-19"]
    assert not any(g["done"] or g["winner"] for g in fr) and got["chances"] == out["chances"], "no result"
    assert sorted(got["bracket_lines"]) == ["fr1", "fr2", "fr3", "fr4"]
    assert all(g["date"] == "" for g in out["bracket"]["first_round"]), "no night before the scoreboard lists it"
    # Once the 8 v 9 game is played, the 1 seed's quarterfinal is listed in its bowl.
    rose = "College Football Playoff Quarterfinal at the Rose Bowl Game Presented by Prudential"
    got = _built([_post(s[8], s[9], "2026-12-19", 17, 14), _listed(s[1], s[8], "2027-01-01", rose)],
                 today="2026-12-20")
    q1 = got["bracket"]["quarterfinals"][0]
    assert (q1["date"], q1["bowl"], q1["done"], q1["winner"]) == ("2027-01-01", "Rose Bowl Game", False, None)
    assert "qf1" in got["bracket_lines"]


def test_our_line_and_the_chances_are_paid_and_the_bracket_is_free():
    out = _built()
    lines = out["bracket_lines"]
    assert sorted(lines) == ["fr1", "fr2", "fr3", "fr4"], lines
    g = out["bracket"]["first_round"][0]
    _games, ratings, _ranks = _season()
    want = cfprace.win_prob(ratings[g["home"]], ratings[g["away"]], HFA, SD, False)
    assert abs(lines["fr1"]["p_home"] - round(want, 3)) < 1e-9, "at the higher seed's home field"
    assert abs(sum(c["title"] for c in out["chances"].values()) - 1) < 0.01
    assert gate.PAID_KEYS_BY_FILE["cfp_race.json"] == ("chances", "remaining", "swing", "bracket_lines")
    pub = gate.redact(out, "cfp_race.json")
    assert not pub["bracket_lines"] and not pub["chances"] and pub["bracket"] == out["bracket"]


# --- the season's calendar and the build -----------------------------------------------
def test_the_race_runs_into_january_and_on_quiet_days():
    assert cfprace.season_of(dt.date(2027, 1, 12)) == 2026 and cfprace.season_of(dt.date(2026, 9, 5)) == 2026
    src = (ROOT / "engine" / "cfprace.py").read_text(encoding="utf-8")
    assert "season = season_of(day)" in src and "_dt.date(season + 1, *PLAYOFF_END)" in src
    assert "games = load_season(season, day) + load_postseason(season, day)" in src
    assert cfprace.PLAYOFF_END == (1, 25)
    build = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    quiet = build[build.index('out.update(status="no games today",'):]
    quiet = quiet[:quiet.index("            return")]
    assert "_race.publish(ratings, fit, day, teams=teams" in quiet, "selection Sunday and the night after a title game"
    from engine.sources import cfbdata
    ev = {"events": [{"id": "9", "date": "2027-01-01T22:00Z", "season": {"year": 2026, "type": 3},
          "competitions": [{"neutralSite": True, "notes": [{"headline": "College Football Playoff Quarterfinal at the Rose Bowl Game"}],
                            "status": {"type": {"state": "post", "completed": True}},
                            "competitors": [{"homeAway": "home", "score": "30", "team": {"abbreviation": "OSU", "id": "1"}},
                                            {"homeAway": "away", "score": "20", "team": {"abbreviation": "ORE", "id": "2"}}]}]}]}
    row = cfbdata.parse_scoreboard(ev)[0]
    assert row["notes"] == "College Football Playoff Quarterfinal at the Rose Bowl Game" and row["season_type"] == 3


def test_the_scoreboard_is_read_for_the_playoff_nights_still_to_come_from_selection_day():
    from engine.sources import cfbdata
    asked = []
    real = cfbdata.load_range
    cfbdata.load_range = lambda a, b, ttl=24 * 3600, conferences=None: asked.append((a, b, ttl)) or []
    try:
        cfprace.load_postseason(2026, dt.date(2026, 12, 5))
        assert asked == [], "before selection day: nothing after it"
        cfprace.load_postseason(2026, dt.date(2026, 12, 6))
        soon = cfprace.SCHEDULE_TTL
        nights = ["2026-12-18", "2026-12-19", "2026-12-31", "2027-01-01", "2027-01-08", "2027-01-09", "2027-01-19"]
        assert asked == [(n, n, soon) for n in nights], asked
        asked.clear()
        cfprace.load_postseason(2026, dt.date(2026, 12, 20))
        assert asked == [("2026-12-07", "2026-12-16", 24 * 3600), ("2026-12-17", "2026-12-20", 30 * 60)] + \
            [(n, n, soon) for n in nights[2:]], asked
        asked.clear()
        cfprace.load_postseason(2026, dt.date(2027, 1, 20))
        assert all(t != soon for _a, _b, t in asked), "the title game played, no night left to come"
    finally:
        cfbdata.load_range = real
    race = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
    assert "the twelve the committee named. Our game model plays the playoff out" in race


# --- on the page ---------------------------------------------------------------------
def _render(payload):
    race = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
    js = f"""
    const state = {{ sport: "cfb", view: "race" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const teamMarkIn = (sp, t) => `<i data-mark="${{t}}"></i>`;
    const teamNameIn = (sp, t) => t;
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const formatGameDate = (s) => s;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    {race}
    console.log(JSON.stringify(cfpHTML({json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_the_bracket_with_our_line_for_a_member_only():
    out = _built()
    html = _render(out)
    assert "The College Football Playoff" in html and "The twelve" in html and "Winner of 8 v 9" in html
    assert "· our line " in html and "Our chances" in html and "If it started today" not in html
    free = _render(gate.redact(out, "cfp_race.json"))
    assert "The College Football Playoff" in free and "· our line " not in free and "member-lock" in free
    first = out["bracket"]
    s = {x["seed"]: x["team"] for x in first["seeds"]}
    games = [_post(s[5], s[12], "2026-12-18", 20, 27), _post(s[6], s[11], "2026-12-18", 35, 10),
             _post(s[7], s[10], "2026-12-19", 24, 21), _post(s[8], s[9], "2026-12-19", 17, 14),
             _post(s[1], s[8], "2027-01-01", 30, 20, "x at the Rose Bowl Game"), _post(s[2], s[7], "2027-01-01", 27, 24, "x"),
             _post(s[3], s[6], "2026-12-31", 14, 21, "x"), _post(s[12], s[4], "2026-12-31", 28, 24, "x"),
             _post(s[1], s[12], "2027-01-09", 35, 17, "x"), _post(s[6], s[2], "2027-01-08", 21, 20, "x"),
             _post(s[6], s[1], "2027-01-19", 24, 31, "x")]
    done = _render(gate.redact(_built(games, today="2027-01-20"), "cfp_race.json"))
    assert "win the national championship" in done and "Rose Bowl Game" in done and "final score" in done


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
